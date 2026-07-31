"""Inboxes: channel instances, their configuration and their members."""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select

from ...channels.base import (
    ChannelConfigError,
    ChannelError,
    available_channels,
    build_channel,
    get_channel_class,
)
from ...core import events as bus
from ...core.deps import CurrentUser, DbSession, get_current_admin, get_current_user
from ...models import Inbox, InboxMember, InboxMode, User
from ...schemas import IdList, InboxCreate, InboxUpdate
from ...serializers import SECRET_MASK, serialize_inbox

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/inboxes", tags=["inboxes"], dependencies=[Depends(get_current_user)]
)
channels_router = APIRouter(
    prefix="/channels", tags=["channels"], dependencies=[Depends(get_current_user)]
)


@channels_router.get("")
async def list_channels() -> list[dict]:
    """Describe every registered channel so the UI can render its config form."""
    return available_channels()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _get_inbox(db: DbSession, inbox_id: int) -> Inbox:
    inbox = await db.get(Inbox, inbox_id)
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found")
    return inbox


async def _reload_worker(inbox_id: int) -> None:
    """Tell the worker supervisor to (re)start the poller for this inbox."""
    try:
        from ...workers import supervisor
    except Exception:  # pragma: no cover - workers are optional
        return
    try:
        await supervisor.reload_inbox(inbox_id)
    except Exception:  # pragma: no cover - never fail an API call on this
        logger.exception("worker reload failed for inbox %s", inbox_id)


async def _remove_worker(inbox_id: int) -> None:
    """Tell the worker supervisor to stop polling a deleted inbox."""
    try:
        from ...workers import supervisor
    except Exception:  # pragma: no cover - workers are optional
        return
    try:
        await supervisor.remove_inbox(inbox_id)
    except Exception:  # pragma: no cover
        logger.exception("worker removal failed for inbox %s", inbox_id)


def _token_is_identity(inbox: Inbox) -> bool:
    """Does this channel treat ``webhook_token`` as a permanent public id?"""
    try:
        return get_channel_class(inbox.channel_type).webhook_token_is_identity
    except ChannelConfigError:  # pragma: no cover - unknown channel type
        return False


def _merge_secrets(
    channel_type: str, current: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Keep the stored value whenever the client echoed back the secret mask."""
    try:
        secret_keys = {f.key for f in get_channel_class(channel_type).config_fields if f.secret}
    except ChannelConfigError:
        secret_keys = set()
    merged = dict(incoming)
    for key in secret_keys:
        if merged.get(key) in (SECRET_MASK, "", None) and current.get(key):
            merged[key] = current[key]
    return merged


async def _configure(db: DbSession, inbox: Inbox, config: dict[str, Any]) -> None:
    """Validate the config, run ``setup()`` and record the connection status."""
    channel_cls = get_channel_class(inbox.channel_type)
    try:
        # Validate through the inbox's own proxy: on networks where the
        # provider is only reachable through it, a direct check would fail.
        inbox.config = await channel_cls.validate_config(
            dict(config or {}), proxy=inbox.proxy_url
        )
    except ChannelConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if inbox.mode == InboxMode.WEBHOOK.value and not inbox.webhook_token:
        inbox.webhook_token = secrets.token_urlsafe(24)
    await db.flush()

    channel = build_channel(inbox)
    try:
        info = await channel.setup()
        inbox.connection_status = "connected"
        inbox.connection_error = None
        if info:
            inbox.config = {**(inbox.config or {}), **info.get("config", {})}
    except ChannelError as exc:
        inbox.connection_status = "error"
        inbox.connection_error = str(exc)
    finally:
        await channel.close()
    await db.flush()


async def _member_ids(db: DbSession, inbox_id: int) -> list[int]:
    return list(
        await db.scalars(select(InboxMember.user_id).where(InboxMember.inbox_id == inbox_id))
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("")
async def list_inboxes(db: DbSession, user: CurrentUser) -> list[dict]:
    inboxes = (await db.scalars(select(Inbox).order_by(Inbox.name))).all()
    return [serialize_inbox(i, reveal_secrets=False) for i in inboxes]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_admin)])
async def create_inbox(payload: InboxCreate, db: DbSession) -> dict:
    try:
        get_channel_class(payload.channel_type)
    except ChannelConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    inbox = Inbox(
        name=payload.name,
        channel_type=payload.channel_type,
        mode=payload.mode,
        avatar_url=payload.avatar_url,
        proxy_url=payload.proxy_url,
        is_active=payload.is_active,
        greeting_enabled=payload.greeting_enabled,
        greeting_message=payload.greeting_message,
        csat_enabled=payload.csat_enabled,
        auto_assignment_enabled=payload.auto_assignment_enabled,
        auto_resolve_after_minutes=payload.auto_resolve_after_minutes,
        working_hours=payload.working_hours or {},
        out_of_office_message=payload.out_of_office_message,
        config={},
        connection_status="unknown",
    )
    db.add(inbox)
    await db.flush()

    await _configure(db, inbox, payload.config)
    if payload.member_ids:
        await _set_members(db, inbox, payload.member_ids)

    await _reload_worker(inbox.id)
    await bus.publish(bus.EVENT_INBOX_UPDATED, {"inbox": serialize_inbox(inbox)})
    return serialize_inbox(inbox, reveal_secrets=False)


@router.get("/{inbox_id}")
async def get_inbox(inbox_id: int, db: DbSession) -> dict:
    return serialize_inbox(await _get_inbox(db, inbox_id))


@router.patch("/{inbox_id}", dependencies=[Depends(get_current_admin)])
async def update_inbox(inbox_id: int, payload: InboxUpdate, db: DbSession) -> dict:
    inbox = await _get_inbox(db, inbox_id)
    data = payload.model_dump(exclude_unset=True)
    config = data.pop("config", None)

    for field, value in data.items():
        setattr(inbox, field, value)
    # A webhook token is a per-mode delivery secret and is dropped when the
    # inbox stops receiving webhooks — unless the channel uses it as a permanent
    # public identifier (the API channel's ``inbox_identifier``), in which case
    # clearing it would silently rotate every configured Client API URL.
    if inbox.mode != InboxMode.WEBHOOK.value and not _token_is_identity(inbox):
        inbox.webhook_token = None
    await db.flush()

    merged = _merge_secrets(inbox.channel_type, dict(inbox.config or {}), config or {})
    await _configure(db, inbox, merged if config is not None else dict(inbox.config or {}))

    await _reload_worker(inbox.id)
    await bus.publish(bus.EVENT_INBOX_UPDATED, {"inbox": serialize_inbox(inbox)})
    return serialize_inbox(inbox, reveal_secrets=False)


@router.delete("/{inbox_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_current_admin)])
async def delete_inbox(inbox_id: int, db: DbSession) -> None:
    inbox = await _get_inbox(db, inbox_id)
    channel = build_channel(inbox)
    try:
        await channel.teardown()
    except ChannelError as exc:  # pragma: no cover - best effort
        logger.info("teardown failed for inbox %s: %s", inbox_id, exc)
    finally:
        await channel.close()

    await _remove_worker(inbox_id)
    await db.delete(inbox)
    await db.flush()


@router.post("/{inbox_id}/test", dependencies=[Depends(get_current_admin)])
async def test_inbox(inbox_id: int, db: DbSession) -> dict:
    """Ping the upstream provider and persist the outcome."""
    inbox = await _get_inbox(db, inbox_id)
    channel = build_channel(inbox)
    try:
        result = await channel.health_check()
        inbox.connection_status = "connected"
        inbox.connection_error = None
        await db.flush()
        return {"status": "ok", "result": result}
    except ChannelError as exc:
        inbox.connection_status = "error"
        inbox.connection_error = str(exc)
        await db.flush()
        return {"status": "error", "detail": str(exc)}
    finally:
        await channel.close()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
async def _set_members(db: DbSession, inbox: Inbox, user_ids: list[int]) -> None:
    await db.execute(delete(InboxMember).where(InboxMember.inbox_id == inbox.id))
    known = set(
        (await db.scalars(select(User.id).where(User.id.in_(user_ids or [-1])))).all()
    )
    for user_id in dict.fromkeys(user_ids):
        if user_id in known:
            db.add(InboxMember(inbox_id=inbox.id, user_id=user_id))
    await db.flush()


@router.get("/{inbox_id}/members")
async def get_members(inbox_id: int, db: DbSession) -> dict:
    await _get_inbox(db, inbox_id)
    return {"user_ids": await _member_ids(db, inbox_id)}


@router.put("/{inbox_id}/members", dependencies=[Depends(get_current_admin)])
async def put_members(inbox_id: int, payload: IdList, db: DbSession) -> dict:
    inbox = await _get_inbox(db, inbox_id)
    await _set_members(db, inbox, payload.user_ids)
    return {"user_ids": await _member_ids(db, inbox_id)}
