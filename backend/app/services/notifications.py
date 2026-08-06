"""Email notifications for agents.

Two switches must both be on before anything is sent:

1. **SMTP is configured** in the environment (``SMTP_HOST`` + a sender), and
2. **notifications are enabled** for the installation (Settings → Notifications).

A third, per-agent switch decides who actually receives what.

Sending is driven off the event bus, in a background task, so a slow or broken
mail server can never delay or fail the request that received the message.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import events as bus
from ..db import SessionLocal, utcnow
from ..models import (
    Contact,
    Conversation,
    ConversationParticipant,
    Inbox,
    InboxMember,
    Message,
    MessageType,
    User,
)
from . import email_templates, mailer, settings_service, visibility

logger = logging.getLogger(__name__)

#: Installation-wide switch, stored in the ``settings`` table.
SETTING_KEY = "email_notifications_enabled"

#: Per-agent preferences and their defaults. Anything absent falls back here,
#: so an agent created before this feature existed behaves sensibly.
DEFAULT_PREFERENCES: dict[str, Any] = {
    #: Conversations assigned to me.
    "assigned": True,
    #: Conversations nobody has picked up yet.
    "unassigned": True,
    #: Conversations I was added to as a participant.
    "participating": True,
    #: Conversations assigned to somebody else — off, or every agent gets
    #: every message in the whole installation.
    "others": False,
    #: Private notes my teammates leave on conversations I follow.
    "private_notes": True,
    #: Skip the email when I have the app open right now.
    "skip_when_online": False,
    #: Never send more than one mail per conversation within this window.
    #: ``0`` means "every message", which is the default.
    "min_interval_seconds": 0,
}

#: ``(user_id, conversation_id) -> monotonic timestamp of the last email``.
#: In-process only: a restart simply allows one extra mail, which is the safe
#: direction to fail in.
_last_sent: dict[tuple[int, int], float] = {}

_tasks: set[asyncio.Task] = set()


def preferences_for(user: User) -> dict[str, Any]:
    return {**DEFAULT_PREFERENCES, **(user.notification_settings or {})}


async def is_enabled(db: AsyncSession) -> bool:
    """Both the transport and the in-app switch have to be on."""
    if not mailer.is_configured():
        return False
    return bool(await settings_service.get(db, SETTING_KEY, False))


# ---------------------------------------------------------------------------
# Bus wiring
# ---------------------------------------------------------------------------
async def handle_event(event: str, payload: dict[str, Any]) -> None:
    """Bus listener — schedules the work without blocking the producer."""
    if event != bus.EVENT_MESSAGE_CREATED:
        return
    message_id = _message_id(payload)
    if message_id is None:
        return
    task = asyncio.create_task(notify_new_message(message_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _message_id(payload: dict[str, Any]) -> int | None:
    message = payload.get("message")
    if isinstance(message, dict):
        return message.get("id")
    return payload.get("message_id")


def install() -> None:
    """Register the listener (called once at startup)."""
    bus.subscribe(handle_event)


# ---------------------------------------------------------------------------
# The notification itself
# ---------------------------------------------------------------------------
async def notify_new_message(message_id: int) -> int:
    """Email every agent who should hear about this message. Returns the count."""
    try:
        # The producer publishes inside its transaction; wait for the commit.
        async with SessionLocal() as probe:
            if not await settings_service.get(probe, SETTING_KEY, False):
                return 0
            if not mailer.is_configured():
                return 0

        sent = await visibility.run_when_visible(Message, message_id, _dispatch)
        return sent or 0
    except Exception:  # pragma: no cover - a mail must never break intake
        logger.exception("email notification failed for message %s", message_id)
        return 0


async def _dispatch(db: AsyncSession, message: Message) -> int:
    # Re-read with the attachments eagerly loaded: a lazy load here would run
    # outside the async context and raise MissingGreenlet.
    message = await db.scalar(
        select(Message)
        .options(selectinload(Message.attachments))
        .where(Message.id == message.id)
    ) or message

    if message.deleted_at is not None:
        return 0
    # Activity entries ("Agent resolved the conversation") are noise in a mailbox.
    if message.message_type == MessageType.ACTIVITY.value:
        return 0
    # An agent's own reply to the customer is not news to the team.
    if message.message_type == MessageType.OUTGOING.value and not message.private:
        return 0

    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None or conversation.muted:
        return 0
    inbox = await db.get(Inbox, message.inbox_id)
    contact = await db.get(Contact, conversation.contact_id)

    recipients = await _recipients(db, conversation, message)
    if not recipients:
        return 0

    author = None
    if message.sender_id and message.message_type == MessageType.OUTGOING.value:
        author = await db.get(User, message.sender_id)

    subject, text_body, html_body = email_templates.render_new_message(
        contact_name=(contact.name if contact else "Unknown contact"),
        inbox_name=(inbox.name if inbox else "Inbox"),
        content=message.content or "",
        conversation_id=conversation.id,
        attachments=[a.file_name or a.file_type for a in message.attachments],
        is_private_note=message.private,
        author_name=(author.name if author else None),
        sent_at=message.created_at,
    )

    sent = 0
    for user in recipients:
        try:
            await mailer.send_email(
                to=user.email, subject=subject, text_body=text_body, html_body=html_body
            )
        except mailer.MailError as exc:
            logger.warning("notification to %s failed: %s", user.email, exc)
            continue
        _last_sent[(user.id, conversation.id)] = asyncio.get_event_loop().time()
        sent += 1

    if sent:
        logger.info(
            "emailed %d agent(s) about message %s in conversation %s",
            sent,
            message.id,
            conversation.id,
        )
    return sent


async def _recipients(
    db: AsyncSession, conversation: Conversation, message: Message
) -> list[User]:
    """Which agents want to hear about this message."""
    candidates = await _candidate_agents(db, conversation.inbox_id)
    participants = set(
        await db.scalars(
            select(ConversationParticipant.user_id).where(
                ConversationParticipant.conversation_id == conversation.id
            )
        )
    )
    online = set(bus.manager.online_user_ids)
    now = asyncio.get_event_loop().time()

    wanted: list[User] = []
    for user in candidates:
        # Never mail somebody about their own private note.
        if message.sender_id == user.id and message.message_type == MessageType.OUTGOING.value:
            continue

        prefs = preferences_for(user)
        if message.private and not prefs["private_notes"]:
            continue
        if prefs["skip_when_online"] and user.id in online:
            continue

        if conversation.assignee_id == user.id:
            if not prefs["assigned"]:
                continue
        elif user.id in participants:
            if not prefs["participating"]:
                continue
        elif conversation.assignee_id is None:
            if not prefs["unassigned"]:
                continue
        elif not prefs["others"]:
            continue

        interval = int(prefs["min_interval_seconds"] or 0)
        if interval:
            last = _last_sent.get((user.id, conversation.id))
            if last is not None and now - last < interval:
                continue

        wanted.append(user)
    return wanted


async def _candidate_agents(db: AsyncSession, inbox_id: int) -> list[User]:
    """Active agents with an address who could be mailed about this inbox.

    When an inbox has an explicit member list, only those agents are eligible —
    otherwise adding an inbox would start mailing the whole installation.
    """
    member_ids = list(
        await db.scalars(
            select(InboxMember.user_id).where(InboxMember.inbox_id == inbox_id)
        )
    )
    query = select(User).where(
        User.is_active.is_(True),
        User.email_notifications.is_(True),
        User.email.is_not(None),
    )
    if member_ids:
        query = query.where(User.id.in_(member_ids))
    return list(await db.scalars(query))


# ---------------------------------------------------------------------------
# Test email
# ---------------------------------------------------------------------------
async def send_test_email(user: User) -> None:
    """Prove the SMTP settings work. Raises :class:`mailer.MailError`."""
    subject, text_body, html_body = email_templates.render_test_email(
        recipient_name=user.display_name or user.name
    )
    await mailer.send_email(
        to=user.email, subject=subject, text_body=text_body, html_body=html_body
    )
    logger.info("test email sent to %s at %s", user.email, utcnow().isoformat())


def reset_throttle() -> None:
    """Forget the per-conversation cooldowns (used by tests)."""
    _last_sent.clear()
