"""Outgoing webhook delivery.

Subscribes to the in-process event bus and forwards matching events to every
active :class:`~app.models.system.Webhook`.

Each hook is delivered in **its own wire format**, selected by
``Webhook.payload_format``:

``native`` (default)
    Our historical shape — ``{"event", "timestamp", "data"}`` with our dotted
    event names, signed with ``X-ChattySup-Signature`` (hex HMAC-SHA256 of the
    raw body), 3 attempts, 10s timeout. Unchanged, bit for bit.

``chatwoot``
    Chatwoot's own payloads (see :mod:`app.compat.chatwoot`): no envelope, the
    resource hash with ``event`` merged in as a sibling key, Chatwoot event
    names, ``X-Chatwoot-Signature: sha256=<hex>`` over ``"{timestamp}.{body}"``
    plus ``X-Chatwoot-Timestamp`` / ``X-Chatwoot-Delivery``, one attempt, 5s
    timeout. ``subscriptions`` for such a hook holds Chatwoot event names.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..compat import chatwoot
from ..core import events as bus
from ..core.security import sign_payload
from ..db import SessionLocal, utcnow
from ..models import Contact, ContactInbox, Conversation, Inbox, Message, Team, User, Webhook
from ..models.enums import MessageType, SenderType

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
MAX_ATTEMPTS = 3

#: Chatwoot fires once, with a 5s open+read timeout, and never retries account
#: or API-inbox webhooks (``lib/webhooks/trigger.rb``).
CHATWOOT_TIMEOUT = 5.0
CHATWOOT_MAX_ATTEMPTS = 1

FORMAT_NATIVE = "native"
FORMAT_CHATWOOT = "chatwoot"

_tasks: set[asyncio.Task] = set()

#: Last seen status per conversation id. Our bus does not carry old/new values,
#: so this is how a ``conversation.updated`` is recognised as a status change
#: (Chatwoot splits that into a second ``conversation_status_changed`` event and
#: fills ``changed_attributes``).
_last_status: dict[int, str] = {}
_LAST_STATUS_LIMIT = 10_000


async def dispatch(event: str, payload: dict[str, Any]) -> None:
    """Bus listener — schedules deliveries without blocking the caller."""
    task = asyncio.create_task(_deliver_all(event, payload))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _track_status(event: str, payload: dict[str, Any]) -> dict[str, tuple[Any, Any]] | None:
    """Return ``{"status": (previous, current)}`` when the status just changed."""
    conversation = payload.get("conversation") or {}
    conversation_id = conversation.get("id")
    status = conversation.get("status")
    if conversation_id is None or status is None:
        return None
    if len(_last_status) > _LAST_STATUS_LIMIT:  # pragma: no cover - bounded cache
        _last_status.clear()
    previous = _last_status.get(conversation_id)
    _last_status[conversation_id] = status
    if event == bus.EVENT_CONVERSATION_CREATED:
        return None
    if previous is not None and previous != status:
        return {"status": (previous, status)}
    return None


async def _deliver_all(event: str, payload: dict[str, Any]) -> None:
    try:
        changes = _track_status(event, payload)
        async with SessionLocal() as db:
            hooks = (
                await db.scalars(select(Webhook).where(Webhook.active.is_(True)))
            ).all()

            native_hooks = [h for h in hooks if h.payload_format != FORMAT_CHATWOOT]
            chatwoot_hooks = [h for h in hooks if h.payload_format == FORMAT_CHATWOOT]

            # --- native (unchanged) ---------------------------------------
            native_targets: list[Webhook] = []
            native_body = b""
            if event != bus.EVENT_CONVERSATION_TYPING:
                native_targets = [
                    h
                    for h in native_hooks
                    if not h.subscriptions or event in h.subscriptions
                ]
                if native_targets:
                    native_body = json.dumps(
                        {
                            "event": event,
                            "timestamp": utcnow().isoformat(),
                            "data": payload,
                        },
                        default=str,
                    ).encode("utf-8")

            # --- chatwoot -------------------------------------------------
            chatwoot_bodies: dict[str, bytes] = {}
            if chatwoot_hooks:
                wanted = {
                    name
                    for hook in chatwoot_hooks
                    for name in chatwoot.map_event(
                        event, payload, status_changed=changes is not None
                    )
                    if name in (hook.subscriptions or [])
                }
                if wanted:
                    chatwoot_bodies = await _build_chatwoot_bodies(
                        db, event, payload, wanted, changes
                    )

            chatwoot_targets = [
                (hook, name)
                for hook in chatwoot_hooks
                for name in chatwoot.map_event(
                    event, payload, status_changed=changes is not None
                )
                if name in (hook.subscriptions or []) and name in chatwoot_bodies
            ]

            if not native_targets and not chatwoot_targets:
                return

            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                for hook in native_targets:
                    await _deliver_one(client, hook, event, native_body)
                for hook, name in chatwoot_targets:
                    await _deliver_chatwoot(client, hook, name, chatwoot_bodies[name])
            await db.commit()
    except Exception:  # pragma: no cover - webhook errors must stay contained
        logger.exception("webhook dispatch failed for %s", event)


async def _deliver_one(
    client: httpx.AsyncClient, hook: Webhook, event: str, body: bytes
) -> None:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ChattySup-Webhook/1.0",
        "X-ChattySup-Event": event,
    }
    if hook.secret:
        headers["X-ChattySup-Signature"] = sign_payload(hook.secret, body)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.post(hook.url, content=body, headers=headers)
            hook.last_status = response.status_code
            hook.last_delivered_at = utcnow()
            if response.is_success:
                hook.last_error = None
                return
            hook.last_error = f"HTTP {response.status_code}"
        except Exception as exc:
            hook.last_status = None
            hook.last_error = f"{type(exc).__name__}: {exc}"
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(2**attempt)


def chatwoot_headers(secret: str | None, body: bytes, delivery_id: str) -> dict[str, str]:
    """``Webhooks::Trigger#request_headers``.

    The signature covers ``"{timestamp}.{raw_body}"`` — not the body alone — and
    carries a literal ``sha256=`` prefix. Signature headers are emitted only
    when a secret is configured.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Chatwoot-Delivery": delivery_id,
    }
    if secret:
        timestamp = str(int(time.time()))
        digest = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + body,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Chatwoot-Timestamp"] = timestamp
        headers["X-Chatwoot-Signature"] = f"sha256={digest}"
    return headers


async def _deliver_chatwoot(
    client: httpx.AsyncClient, hook: Webhook, event: str, body: bytes
) -> None:
    headers = chatwoot_headers(hook.secret, body, str(uuid.uuid4()))
    for attempt in range(1, CHATWOOT_MAX_ATTEMPTS + 1):
        try:
            response = await client.post(
                hook.url, content=body, headers=headers, timeout=CHATWOOT_TIMEOUT
            )
            hook.last_status = response.status_code
            hook.last_delivered_at = utcnow()
            if response.is_success:
                hook.last_error = None
                return
            hook.last_error = f"HTTP {response.status_code}"
        except Exception as exc:
            hook.last_status = None
            hook.last_error = f"{type(exc).__name__}: {exc}"
        if attempt < CHATWOOT_MAX_ATTEMPTS:  # pragma: no cover - single attempt
            await asyncio.sleep(2**attempt)


# ---------------------------------------------------------------------------
# Chatwoot body construction
# ---------------------------------------------------------------------------
async def _build_chatwoot_bodies(
    db: AsyncSession,
    event: str,
    payload: dict[str, Any],
    wanted: set[str],
    changes: dict[str, tuple[Any, Any]] | None,
) -> dict[str, bytes]:
    """Reload the ORM objects the payload refers to and render each event body.

    The bus carries *native serialised dicts*, while the compat layer works on
    ORM objects, so the ids in the payload are resolved back to rows here. This
    only runs when at least one Chatwoot-format hook is subscribed.
    """
    context = await _load_context(db, event, payload)
    if context is None:
        return {}
    context["changes"] = changes
    if event == bus.EVENT_CONVERSATION_TYPING:
        context["is_private"] = False

    bodies: dict[str, bytes] = {}
    for name in wanted:
        try:
            body = chatwoot.build_event(name, **context)
        except (KeyError, ValueError):  # pragma: no cover - defensive
            logger.warning("cannot build chatwoot event %s from %s", name, event)
            continue
        bodies[name] = json.dumps(body, default=str).encode("utf-8")
    return bodies


def _identifier(payload: dict[str, Any], key: str, *fallbacks: str) -> Any:
    nested = payload.get(key)
    if isinstance(nested, dict) and nested.get("id") is not None:
        return nested["id"]
    for name in fallbacks:
        if payload.get(name) is not None:
            return payload[name]
    return None


async def _load_context(
    db: AsyncSession, event: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    if event in (bus.EVENT_MESSAGE_CREATED, bus.EVENT_MESSAGE_UPDATED, bus.EVENT_MESSAGE_DELETED):
        message_id = _identifier(payload, "message", "message_id")
        message = await db.get(Message, message_id) if message_id is not None else None
        if message is None or not chatwoot.webhook_sendable(message):
            # Activity messages never produce Chatwoot message webhooks.
            return None
        conversation = await db.get(Conversation, message.conversation_id)
        context = await _conversation_context(db, conversation)
        context["message"] = message
        context["sender"] = await _resolve_sender(db, message, context.get("contact"))
        return context

    if event in (bus.EVENT_CONVERSATION_CREATED, bus.EVENT_CONVERSATION_UPDATED):
        conversation_id = _identifier(payload, "conversation", "conversation_id")
        conversation = (
            await db.get(Conversation, conversation_id)
            if conversation_id is not None
            else None
        )
        if conversation is None:
            return None
        context = await _conversation_context(db, conversation)
        context["last_message"] = await _last_chat_message(db, conversation.id)
        return context

    if event == bus.EVENT_CONVERSATION_TYPING:
        conversation_id = payload.get("conversation_id")
        conversation = (
            await db.get(Conversation, conversation_id)
            if conversation_id is not None
            else None
        )
        if conversation is None:
            return None
        context = await _conversation_context(db, conversation)
        context["last_message"] = await _last_chat_message(db, conversation.id)
        user_id = payload.get("user_id")
        if payload.get("actor") == "contact":
            context["user"] = context.get("contact")
        elif user_id is not None:
            context["user"] = await db.get(User, user_id)
        else:
            context["user"] = conversation.assignee
        return context

    if event == bus.EVENT_CONTACT_UPDATED:
        contact_id = _identifier(payload, "contact", "contact_id")
        contact = await db.get(Contact, contact_id) if contact_id is not None else None
        if contact is None:
            return None
        return {"contact": contact}

    if event == bus.EVENT_INBOX_UPDATED:
        inbox_id = _identifier(payload, "inbox", "inbox_id")
        inbox = await db.get(Inbox, inbox_id) if inbox_id is not None else None
        if inbox is None:
            return None
        return {"inbox": inbox}

    return None


async def _conversation_context(
    db: AsyncSession, conversation: Conversation | None
) -> dict[str, Any]:
    if conversation is None:
        return {}
    contact_inbox = (
        await db.get(ContactInbox, conversation.contact_inbox_id)
        if conversation.contact_inbox_id
        else None
    )
    team = await db.get(Team, conversation.team_id) if conversation.team_id else None
    return {
        "conversation": conversation,
        "contact": conversation.contact,
        "inbox": conversation.inbox,
        "assignee": conversation.assignee,
        "team": team,
        "contact_inbox": contact_inbox,
    }


async def _resolve_sender(
    db: AsyncSession, message: Message, contact: Contact | None
) -> Contact | User | None:
    if message.sender_type == SenderType.CONTACT.value:
        if contact is not None:
            return contact
        return await db.get(Contact, message.sender_id) if message.sender_id else None
    if message.sender_type == SenderType.USER.value and message.sender_id:
        return await db.get(User, message.sender_id)
    return None


async def _last_chat_message(db: AsyncSession, conversation_id: int) -> Message | None:
    """Chatwoot's ``chat`` scope: not an activity message, not private."""
    return await db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.message_type != MessageType.ACTIVITY.value,
            Message.private.is_(False),
        )
        .order_by(desc(Message.id))
        .limit(1)
    )


def install() -> None:
    """Register the dispatcher on the event bus (called once at startup)."""
    bus.subscribe(dispatch)
