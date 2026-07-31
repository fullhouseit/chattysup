"""Outgoing webhook subscriptions (admin) and the public inbound endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from ...channels.base import ChannelError, build_channel
from ...compat import chatwoot
from ...core import events as bus
from ...core.deps import DbSession, get_current_admin
from ...models import Inbox, Webhook
from ...schemas import WebhookCreate, WebhookUpdate
from ...serializers import iso
from ...services import conversations as conv_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(get_current_admin)]
)
#: Provider callbacks are authenticated by the per-inbox token in the path.
inbound_router = APIRouter(prefix="/webhooks", tags=["inbound"])


def _serialize(hook: Webhook) -> dict:
    return {
        "id": hook.id,
        "url": hook.url,
        "name": hook.name,
        "subscriptions": hook.subscriptions or [],
        "payload_format": hook.payload_format,
        "has_secret": bool(hook.secret),
        "active": hook.active,
        "inbox_id": hook.inbox_id,
        "last_status": hook.last_status,
        "last_error": hook.last_error,
        "last_delivered_at": iso(hook.last_delivered_at),
        "created_at": iso(hook.created_at),
    }


async def _get(db: DbSession, webhook_id: int) -> Webhook:
    hook = await db.get(Webhook, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return hook


def _vocabulary(payload_format: str) -> list[str]:
    """Event names valid for a given wire format."""
    if payload_format == "chatwoot":
        return list(chatwoot.CHATWOOT_EVENTS)
    return list(bus.ALL_EVENTS)


def _reject_unknown(subscriptions: list[str] | None, payload_format: str) -> None:
    unknown = set(subscriptions or []) - set(_vocabulary(payload_format))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown {payload_format} events: {', '.join(sorted(unknown))}. "
                f"Valid: {', '.join(_vocabulary(payload_format))}"
            ),
        )


@router.get("/events")
async def list_events(payload_format: str = "native") -> list[str]:
    """Event names a webhook of this format can subscribe to."""
    return _vocabulary(payload_format)


@router.get("")
async def list_webhooks(db: DbSession) -> list[dict]:
    rows = (await db.scalars(select(Webhook).order_by(Webhook.id))).all()
    return [_serialize(h) for h in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookCreate, db: DbSession) -> dict:
    _reject_unknown(payload.subscriptions, payload.payload_format)
    hook = Webhook(**payload.model_dump())
    db.add(hook)
    await db.flush()
    return _serialize(hook)


@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: int, payload: WebhookUpdate, db: DbSession
) -> dict:
    hook = await _get(db, webhook_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("subscriptions"):
        # Validate against the format the hook will have after this update.
        _reject_unknown(
            data["subscriptions"], data.get("payload_format", hook.payload_format)
        )
    for field, value in data.items():
        setattr(hook, field, value)
    await db.flush()
    return _serialize(hook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: int, db: DbSession) -> None:
    hook = await _get(db, webhook_id)
    await db.delete(hook)
    await db.flush()


# ---------------------------------------------------------------------------
# Inbound provider callbacks
# ---------------------------------------------------------------------------
@inbound_router.post("/{channel_type}/{token}")
async def receive(
    channel_type: str, token: str, request: Request, db: DbSession
) -> dict:
    """Entry point registered with the provider when an inbox runs in webhook mode."""
    inbox = await db.scalar(
        select(Inbox).where(
            Inbox.webhook_token == token, Inbox.channel_type == channel_type
        )
    )
    if not inbox:
        raise HTTPException(status_code=404, detail="Unknown webhook endpoint")
    if not inbox.is_active:
        return {"status": "ignored", "reason": "inbox inactive"}

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    headers = {k.lower(): v for k, v in request.headers.items()}

    channel = build_channel(inbox)
    try:
        events = await channel.parse_webhook(payload or {}, headers)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=501, detail="This channel does not support webhooks"
        ) from exc
    except ChannelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    handled = 0
    try:
        for event in events:
            await conv_service.process_inbound_event(db, inbox, channel, event)
            handled += 1
    finally:
        await channel.close()
    return {"status": "ok", "handled": handled}
