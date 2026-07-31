"""Core domain service: contacts, conversations, messages and delivery.

Everything that mutates a conversation funnels through here so that realtime
events, webhooks, unread counters and automations stay consistent no matter
whether the change came from the REST API, a channel worker or an automation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import (
    BaseChannel,
    ChannelError,
    InboundEvent,
    NormalizedContact,
    OutboundMessage,
    build_channel,
)
from ..core import events as bus
from ..db import utcnow
from ..models import (
    Attachment,
    Contact,
    ContactInbox,
    ContentType,
    Conversation,
    ConversationStatus,
    Inbox,
    Message,
    MessageReaction,
    MessageStatus,
    MessageType,
    SenderType,
    User,
)
from ..serializers import serialize_conversation, serialize_message
from . import attachments as attachment_service

logger = logging.getLogger(__name__)

#: Reopen an existing conversation instead of creating a new one when the
#: contact writes again within this window after resolution.
REOPEN_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
async def find_or_create_contact(
    db: AsyncSession, inbox: Inbox, payload: NormalizedContact
) -> tuple[Contact, ContactInbox]:
    link = await db.scalar(
        select(ContactInbox).where(
            ContactInbox.inbox_id == inbox.id,
            ContactInbox.source_id == str(payload.source_id),
        )
    )
    if link:
        contact = await db.get(Contact, link.contact_id)
        assert contact is not None
        changed = False
        if payload.name and contact.name != payload.name:
            contact.name, changed = payload.name, True
        if payload.avatar_url and contact.avatar_url != payload.avatar_url:
            contact.avatar_url, changed = payload.avatar_url, True
        if payload.phone and not contact.phone:
            contact.phone, changed = payload.phone, True
        if payload.meta:
            link.meta = {**(link.meta or {}), **payload.meta}
        if changed:
            await db.flush()
            await bus.publish(
                bus.EVENT_CONTACT_UPDATED, {"contact": _contact_dict(contact)}
            )
        return contact, link

    contact = Contact(
        name=payload.name or f"Guest {payload.source_id}",
        avatar_url=payload.avatar_url,
        email=payload.email,
        phone=payload.phone,
        identifier=payload.username,
        timezone=payload.language,
        social_profiles={"telegram": payload.username} if payload.username else {},
        custom_attributes={},
        last_activity_at=utcnow(),
    )
    db.add(contact)
    await db.flush()

    link = ContactInbox(
        contact_id=contact.id,
        inbox_id=inbox.id,
        source_id=str(payload.source_id),
        meta=payload.meta or {},
    )
    db.add(link)
    await db.flush()
    return contact, link


def _contact_dict(contact: Contact) -> dict[str, Any]:
    from ..serializers import serialize_contact

    return serialize_contact(contact)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
async def find_or_create_conversation(
    db: AsyncSession, inbox: Inbox, contact: Contact, link: ContactInbox
) -> tuple[Conversation, bool]:
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.inbox_id == inbox.id,
            Conversation.contact_id == contact.id,
        )
        .order_by(desc(Conversation.last_activity_at))
        .limit(1)
    )

    if conversation is not None:
        if conversation.status != ConversationStatus.RESOLVED.value:
            return conversation, False
        age = utcnow() - (conversation.resolved_at or conversation.last_activity_at)
        if age.total_seconds() < REOPEN_WINDOW_HOURS * 3600:
            conversation.status = ConversationStatus.OPEN.value
            conversation.resolved_at = None
            await db.flush()
            return conversation, False

    conversation = Conversation(
        inbox_id=inbox.id,
        contact_id=contact.id,
        contact_inbox_id=link.id,
        source_id=link.source_id,
        status=ConversationStatus.OPEN.value,
        last_activity_at=utcnow(),
        waiting_since=utcnow(),
    )
    db.add(conversation)
    await db.flush()
    await db.refresh(conversation)
    return conversation, True


async def notify_conversation(
    db: AsyncSession, conversation: Conversation, event: str = bus.EVENT_CONVERSATION_UPDATED
) -> None:
    last_message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.deleted_at.is_(None))
        .order_by(desc(Message.id))
        .limit(1)
    )
    await bus.publish(
        event,
        {"conversation": serialize_conversation(conversation, last_message=last_message)},
    )


async def create_activity_message(
    db: AsyncSession, conversation: Conversation, content: str
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        inbox_id=conversation.inbox_id,
        content=content,
        message_type=MessageType.ACTIVITY.value,
        content_type=ContentType.SYSTEM.value,
        sender_type=SenderType.SYSTEM.value,
        status=MessageStatus.SENT.value,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_CREATED,
        {"message": serialize_message(message), "conversation_id": conversation.id},
    )
    return message


# ---------------------------------------------------------------------------
# Inbound pipeline
# ---------------------------------------------------------------------------
async def process_inbound_event(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> Message | None:
    """Apply one normalised provider event to the database."""
    handler = {
        "message": _handle_inbound_message,
        "message_edited": _handle_inbound_edit,
        "message_deleted": _handle_inbound_delete,
        "reaction": _handle_inbound_reaction,
        "read": _handle_inbound_read,
        "typing": _handle_inbound_typing,
    }.get(event.kind)
    if handler is None:
        logger.debug("ignoring unsupported inbound event kind %s", event.kind)
        return None
    return await handler(db, inbox, channel, event)


async def _resolve_thread(
    db: AsyncSession, inbox: Inbox, event: InboundEvent
) -> tuple[Contact, Conversation, bool] | None:
    payload = event.contact or NormalizedContact(source_id=event.chat_source_id)
    contact, link = await find_or_create_contact(db, inbox, payload)
    if contact.blocked:
        return None
    conversation, created = await find_or_create_conversation(db, inbox, contact, link)
    return contact, conversation, created


async def _handle_inbound_message(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> Message | None:
    assert event.message is not None
    source_id = event.message.source_id

    if source_id:
        existing = await db.scalar(
            select(Message).where(
                Message.inbox_id == inbox.id, Message.source_id == str(source_id)
            )
        )
        if existing:  # provider redelivery — nothing to do
            return existing

    resolved = await _resolve_thread(db, inbox, event)
    if resolved is None:
        return None
    contact, conversation, created = resolved

    attributes = dict(event.message.attributes or {})
    reply_to = attributes.get("reply_to_source_id")
    if reply_to:
        parent = await db.scalar(
            select(Message).where(
                Message.inbox_id == inbox.id, Message.source_id == str(reply_to)
            )
        )
        if parent:
            attributes["reply_to_message_id"] = parent.id
            attributes["reply_to_preview"] = {
                "id": parent.id,
                "content": (parent.content or "")[:180],
                "sender_type": parent.sender_type,
            }

    message = Message(
        conversation_id=conversation.id,
        inbox_id=inbox.id,
        content=event.message.content,
        content_type=event.message.content_type,
        message_type=MessageType.INCOMING.value,
        sender_type=SenderType.CONTACT.value,
        sender_id=contact.id,
        source_id=str(source_id) if source_id else None,
        status=MessageStatus.DELIVERED.value,
        content_attributes=attributes,
    )
    if event.message.sent_at:
        message.created_at = event.message.sent_at
    db.add(message)
    await db.flush()

    for norm in event.message.attachments:
        attachment = await attachment_service.persist_inbound_attachment(
            db, inbox, channel, norm
        )
        attachment.message_id = message.id
    await db.flush()
    await db.refresh(message)

    conversation.last_activity_at = message.created_at or utcnow()
    conversation.unread_count += 1
    conversation.contact_last_seen_at = utcnow()
    if conversation.waiting_since is None:
        conversation.waiting_since = utcnow()
    if conversation.status == ConversationStatus.RESOLVED.value:
        conversation.status = ConversationStatus.OPEN.value
        conversation.resolved_at = None
    contact.last_activity_at = utcnow()
    await db.flush()

    await bus.publish(
        bus.EVENT_MESSAGE_CREATED,
        {"message": serialize_message(message), "conversation_id": conversation.id},
    )
    await notify_conversation(
        db,
        conversation,
        bus.EVENT_CONVERSATION_CREATED if created else bus.EVENT_CONVERSATION_UPDATED,
    )

    # Automations run last so their replies land after the inbound message.
    from .automation import run_automations

    await run_automations(
        db,
        "conversation_created" if created else "message_created",
        conversation=conversation,
        message=message,
    )
    return message


async def _handle_inbound_edit(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> Message | None:
    assert event.message is not None
    message = await db.scalar(
        select(Message).where(
            Message.inbox_id == inbox.id,
            Message.source_id == str(event.message.source_id),
        )
    )
    if not message:
        return await _handle_inbound_message(db, inbox, channel, event)
    history = list((message.content_attributes or {}).get("edit_history", []))
    history.append({"content": message.content, "at": utcnow().isoformat()})
    message.content = event.message.content
    message.content_attributes = {
        **(message.content_attributes or {}),
        "edit_history": history[-10:],
    }
    message.edited_at = utcnow()
    await db.flush()
    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": serialize_message(message), "conversation_id": message.conversation_id},
    )
    return message


async def _handle_inbound_delete(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> Message | None:
    message = await db.scalar(
        select(Message).where(
            Message.inbox_id == inbox.id, Message.source_id == str(event.target_source_id)
        )
    )
    if not message:
        return None
    message.deleted_at = utcnow()
    await db.flush()
    await bus.publish(
        bus.EVENT_MESSAGE_DELETED,
        {"message_id": message.id, "conversation_id": message.conversation_id},
    )
    return message


async def _handle_inbound_reaction(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> Message | None:
    message = await db.scalar(
        select(Message).where(
            Message.inbox_id == inbox.id, Message.source_id == str(event.target_source_id)
        )
    )
    if not message:
        return None

    resolved = await _resolve_thread(db, inbox, event)
    contact_id = resolved[0].id if resolved else None

    for reaction in list(message.reactions):
        if reaction.contact_id is not None:
            await db.delete(reaction)
    await db.flush()

    for emoji in event.reactions:
        db.add(
            MessageReaction(message_id=message.id, emoji=emoji, contact_id=contact_id)
        )
    await db.flush()
    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": serialize_message(message), "conversation_id": message.conversation_id},
    )
    return message


async def _handle_inbound_read(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> None:
    return None


async def _handle_inbound_typing(
    db: AsyncSession, inbox: Inbox, channel: BaseChannel, event: InboundEvent
) -> None:
    link = await db.scalar(
        select(ContactInbox).where(
            ContactInbox.inbox_id == inbox.id,
            ContactInbox.source_id == str(event.chat_source_id),
        )
    )
    if not link:
        return None
    conversation = await db.scalar(
        select(Conversation)
        .where(Conversation.contact_id == link.contact_id, Conversation.inbox_id == inbox.id)
        .order_by(desc(Conversation.last_activity_at))
        .limit(1)
    )
    if conversation:
        await bus.publish(
            bus.EVENT_CONVERSATION_TYPING,
            {"conversation_id": conversation.id, "typing": True, "actor": "contact"},
        )
    return None


# ---------------------------------------------------------------------------
# Outbound pipeline
# ---------------------------------------------------------------------------
async def create_outgoing_message(
    db: AsyncSession,
    conversation: Conversation,
    *,
    content: str | None,
    user: User | None = None,
    private: bool = False,
    attachments: list[Attachment] | None = None,
    reply_to_message_id: int | None = None,
    content_type: str = ContentType.TEXT.value,
    content_attributes: dict[str, Any] | None = None,
    sender_type: str | None = None,
    deliver: bool = True,
) -> Message:
    attributes = dict(content_attributes or {})
    if reply_to_message_id:
        parent = await db.get(Message, reply_to_message_id)
        if parent:
            attributes["reply_to_message_id"] = parent.id
            attributes["reply_to_source_id"] = parent.source_id
            attributes["reply_to_preview"] = {
                "id": parent.id,
                "content": (parent.content or "")[:180],
                "sender_type": parent.sender_type,
            }

    message = Message(
        conversation_id=conversation.id,
        inbox_id=conversation.inbox_id,
        content=content,
        content_type=content_type,
        message_type=MessageType.OUTGOING.value,
        private=private,
        sender_type=sender_type or (SenderType.USER.value if user else SenderType.BOT.value),
        sender_id=user.id if user else None,
        status=MessageStatus.SENT.value if private else MessageStatus.PENDING.value,
        content_attributes=attributes,
    )
    db.add(message)
    await db.flush()

    for attachment in attachments or []:
        attachment.message_id = message.id
    await db.flush()
    await db.refresh(message)

    conversation.last_activity_at = utcnow()
    if not private:
        conversation.waiting_since = None
        if conversation.first_reply_created_at is None and user is not None:
            conversation.first_reply_created_at = utcnow()
    await db.flush()

    if deliver and not private:
        await deliver_message(db, conversation, message)

    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_CREATED,
        {"message": serialize_message(message), "conversation_id": conversation.id},
    )
    await notify_conversation(db, conversation)
    return message


async def deliver_message(
    db: AsyncSession, conversation: Conversation, message: Message
) -> None:
    """Push an outgoing message to the provider and record the outcome."""
    inbox = conversation.inbox or await db.get(Inbox, conversation.inbox_id)
    if inbox is None or not inbox.is_active:
        message.status = MessageStatus.FAILED.value
        message.external_error = "Inbox is inactive"
        await db.flush()
        return

    channel = build_channel(inbox)
    outbound = OutboundMessage(
        content=message.content,
        attachments=[attachment_service.to_outbound(a) for a in message.attachments],
        reply_to_source_id=(message.content_attributes or {}).get("reply_to_source_id"),
        attributes=message.content_attributes or {},
    )
    target = conversation.source_id
    if not target:
        link = await db.get(ContactInbox, conversation.contact_inbox_id or 0)
        target = link.source_id if link else None
    if not target:
        message.status = MessageStatus.FAILED.value
        message.external_error = "Conversation has no upstream chat id"
        await db.flush()
        return

    try:
        result = await channel.send_message(target, outbound)
        message.source_id = result.source_id
        message.status = MessageStatus.SENT.value
        message.external_error = None
        if result.attributes:
            message.content_attributes = {
                **(message.content_attributes or {}),
                **result.attributes,
            }
    except ChannelError as exc:
        message.status = MessageStatus.FAILED.value
        message.external_error = str(exc)
        logger.warning("delivery failed for message %s: %s", message.id, exc)
    except Exception as exc:  # pragma: no cover - defensive
        message.status = MessageStatus.FAILED.value
        message.external_error = f"{type(exc).__name__}: {exc}"
        logger.exception("unexpected delivery failure for message %s", message.id)
    finally:
        await channel.close()
    await db.flush()


async def retry_message(db: AsyncSession, message: Message) -> Message:
    conversation = await db.get(Conversation, message.conversation_id)
    assert conversation is not None
    message.status = MessageStatus.PENDING.value
    await db.flush()
    await deliver_message(db, conversation, message)
    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": serialize_message(message), "conversation_id": conversation.id},
    )
    return message


# ---------------------------------------------------------------------------
# Reactions from agents
# ---------------------------------------------------------------------------
async def toggle_reaction(
    db: AsyncSession, message: Message, user: User, emoji: str
) -> Message:
    existing = next(
        (r for r in message.reactions if r.user_id == user.id and r.emoji == emoji), None
    )
    if existing:
        await db.delete(existing)
    else:
        db.add(MessageReaction(message_id=message.id, emoji=emoji, user_id=user.id))
    await db.flush()
    await db.refresh(message)

    conversation = await db.get(Conversation, message.conversation_id)
    if conversation and message.source_id and not message.private:
        inbox = await db.get(Inbox, message.inbox_id)
        if inbox and inbox.is_active:
            channel = build_channel(inbox)
            emojis = [
                r.emoji for r in message.reactions if r.user_id is not None
            ]
            try:
                await channel.send_reaction(
                    conversation.source_id or "", message.source_id, emojis[:1]
                )
            except (NotImplementedError, ChannelError) as exc:
                logger.info("reaction not delivered upstream: %s", exc)
            finally:
                await channel.close()

    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": serialize_message(message), "conversation_id": message.conversation_id},
    )
    return message


# ---------------------------------------------------------------------------
# Conversation mutations
# ---------------------------------------------------------------------------
async def set_status(
    db: AsyncSession,
    conversation: Conversation,
    status: str,
    actor: User | None = None,
    snoozed_until: datetime | None = None,
) -> Conversation:
    if conversation.status == status and status != ConversationStatus.SNOOZED.value:
        return conversation
    conversation.status = status
    conversation.snoozed_until = (
        snoozed_until if status == ConversationStatus.SNOOZED.value else None
    )
    conversation.resolved_at = (
        utcnow() if status == ConversationStatus.RESOLVED.value else None
    )
    await db.flush()
    who = actor.name if actor else "Automation"
    await create_activity_message(db, conversation, f"{who} marked the conversation as {status}")
    await notify_conversation(db, conversation)
    if status == ConversationStatus.RESOLVED.value:
        from .automation import run_automations

        await run_automations(db, "conversation_resolved", conversation=conversation)
    return conversation


async def assign(
    db: AsyncSession,
    conversation: Conversation,
    assignee: User | None,
    actor: User | None = None,
) -> Conversation:
    conversation.assignee_id = assignee.id if assignee else None
    await db.flush()
    await db.refresh(conversation)
    if assignee and actor and assignee.id == actor.id:
        text = f"{actor.name} self-assigned this conversation"
    elif assignee:
        text = f"Assigned to {assignee.name}"
    else:
        text = "Conversation unassigned"
    await create_activity_message(db, conversation, text)
    await notify_conversation(db, conversation)
    return conversation


async def mark_read(db: AsyncSession, conversation: Conversation) -> Conversation:
    conversation.unread_count = 0
    conversation.agent_last_seen_at = utcnow()
    await db.flush()
    await notify_conversation(db, conversation)
    return conversation


async def send_typing_indicator(db: AsyncSession, conversation: Conversation) -> None:
    inbox = await db.get(Inbox, conversation.inbox_id)
    if not inbox or not inbox.is_active or not conversation.source_id:
        return
    channel = build_channel(inbox)
    try:
        await channel.send_typing(conversation.source_id)
    except Exception:  # pragma: no cover - best effort
        logger.debug("typing indicator failed")
    finally:
        await channel.close()
