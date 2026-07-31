"""ORM -> plain dict serialisation.

Both the REST API and the realtime/webhook payloads go through these helpers so
a browser and a webhook consumer always see the exact same object shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .core import storage
from .models import (
    Attachment,
    Contact,
    ContactNote,
    Conversation,
    Inbox,
    Label,
    Message,
    Team,
    User,
)

SECRET_MASK = "••••••••"


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def serialize_user(user: User | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.name,
        "display_name": user.display_name or user.name,
        "email": user.email,
        "role": user.role,
        "avatar_url": user.avatar_url,
        "availability": user.availability,
        "signature": user.signature,
        "is_active": user.is_active,
        "provider": user.provider,
        "created_at": iso(user.created_at),
    }


def serialize_team(team: Team, member_ids: list[int] | None = None) -> dict[str, Any]:
    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "allow_auto_assign": team.allow_auto_assign,
        "member_ids": member_ids if member_ids is not None else [],
    }


def serialize_label(label: Label) -> dict[str, Any]:
    return {
        "id": label.id,
        "title": label.title,
        "description": label.description,
        "color": label.color,
        "show_on_sidebar": label.show_on_sidebar,
    }


def serialize_inbox(inbox: Inbox, *, reveal_secrets: bool = False) -> dict[str, Any]:
    from .channels import get_channel_class
    from .channels.base import ChannelConfigError

    try:
        channel_cls = get_channel_class(inbox.channel_type)
        secret_keys = {f.key for f in channel_cls.config_fields if f.secret}
        capabilities = sorted(channel_cls.capabilities)
    except ChannelConfigError:
        secret_keys, capabilities = set(), []

    config = dict(inbox.config or {})
    if not reveal_secrets:
        for key in secret_keys:
            if config.get(key):
                config[key] = SECRET_MASK

    return {
        "id": inbox.id,
        "name": inbox.name,
        "channel_type": inbox.channel_type,
        "avatar_url": inbox.avatar_url,
        "is_active": inbox.is_active,
        "mode": inbox.mode,
        "proxy_url": inbox.proxy_url,
        "config": config,
        "capabilities": capabilities,
        "greeting_enabled": inbox.greeting_enabled,
        "greeting_message": inbox.greeting_message,
        "csat_enabled": inbox.csat_enabled,
        "auto_assignment_enabled": inbox.auto_assignment_enabled,
        "auto_resolve_after_minutes": inbox.auto_resolve_after_minutes,
        "working_hours": inbox.working_hours or {},
        "out_of_office_message": inbox.out_of_office_message,
        "connection_status": inbox.connection_status,
        "connection_error": inbox.connection_error,
        "last_polled_at": iso(inbox.last_polled_at),
        "webhook_url": (
            f"/api/v1/webhooks/{inbox.channel_type}/{inbox.webhook_token}"
            if inbox.webhook_token
            else None
        ),
        "created_at": iso(inbox.created_at),
    }


def serialize_contact(contact: Contact) -> dict[str, Any]:
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "avatar_url": contact.avatar_url,
        "identifier": contact.identifier,
        "company": contact.company,
        "title": contact.title,
        "location": contact.location,
        "country_code": contact.country_code,
        "timezone": contact.timezone,
        "blocked": contact.blocked,
        "custom_attributes": contact.custom_attributes or {},
        "social_profiles": contact.social_profiles or {},
        "last_activity_at": iso(contact.last_activity_at),
        "created_at": iso(contact.created_at),
    }


def serialize_contact_note(note: ContactNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "contact_id": note.contact_id,
        "user_id": note.user_id,
        "content": note.content,
        "created_at": iso(note.created_at),
    }


def serialize_attachment(attachment: Attachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "file_type": attachment.file_type,
        "file_name": attachment.file_name,
        "file_size": attachment.file_size,
        "mime_type": attachment.mime_type,
        "url": (
            storage.url_for(attachment.id)
            if attachment.storage_key
            else attachment.external_url
        ),
        "thumb_url": (
            f"{storage.url_for(attachment.id)}?variant=thumb"
            if attachment.thumb_key
            else None
        ),
        "meta": attachment.meta or {},
    }


def serialize_message(message: Message) -> dict[str, Any]:
    reactions: dict[str, dict[str, Any]] = {}
    for reaction in message.reactions:
        entry = reactions.setdefault(
            reaction.emoji, {"emoji": reaction.emoji, "count": 0, "by_me": False, "user_ids": []}
        )
        entry["count"] += 1
        if reaction.user_id:
            entry["user_ids"].append(reaction.user_id)

    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "inbox_id": message.inbox_id,
        "content": message.content,
        "message_type": message.message_type,
        "content_type": message.content_type,
        "private": message.private,
        "status": message.status,
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
        "source_id": message.source_id,
        "content_attributes": message.content_attributes or {},
        "attachments": [serialize_attachment(a) for a in message.attachments],
        "reactions": list(reactions.values()),
        "edited_at": iso(message.edited_at),
        "deleted_at": iso(message.deleted_at),
        "external_error": message.external_error,
        "created_at": iso(message.created_at),
    }


def serialize_conversation(
    conversation: Conversation,
    *,
    last_message: Message | None = None,
    sender: User | None = None,
) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "inbox_id": conversation.inbox_id,
        "inbox": (
            {
                "id": conversation.inbox.id,
                "name": conversation.inbox.name,
                "channel_type": conversation.inbox.channel_type,
                "avatar_url": conversation.inbox.avatar_url,
            }
            if conversation.inbox
            else None
        ),
        "contact": serialize_contact(conversation.contact) if conversation.contact else None,
        "assignee": serialize_user(conversation.assignee),
        "assignee_id": conversation.assignee_id,
        "team_id": conversation.team_id,
        "status": conversation.status,
        "priority": conversation.priority,
        "unread_count": conversation.unread_count,
        "muted": conversation.muted,
        "labels": [
            serialize_label(link.label) for link in conversation.labels if link.label
        ],
        "custom_attributes": conversation.custom_attributes or {},
        "last_activity_at": iso(conversation.last_activity_at),
        "waiting_since": iso(conversation.waiting_since),
        "snoozed_until": iso(conversation.snoozed_until),
        "resolved_at": iso(conversation.resolved_at),
        "created_at": iso(conversation.created_at),
        "last_message": serialize_message(last_message) if last_message else None,
        "sender": serialize_user(sender),
    }
