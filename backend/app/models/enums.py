"""Enumerations shared across the domain model.

All enums are plain ``str`` subclasses so they serialise transparently to JSON
and are stored as human readable values in the database.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class UserRole(StrEnum):
    ADMIN = "admin"
    AGENT = "agent"


class Availability(StrEnum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"


class ConversationStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"


class ConversationPriority(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MessageType(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    ACTIVITY = "activity"
    TEMPLATE = "template"


class MessageStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class SenderType(StrEnum):
    CONTACT = "contact"
    USER = "user"
    SYSTEM = "system"
    BOT = "bot"


class ContentType(StrEnum):
    TEXT = "text"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT_CARD = "contact_card"
    POLL = "poll"
    STORY = "story"
    SYSTEM = "system"


class AttachmentType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VOICE = "voice"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
    FILE = "file"
    STICKER = "sticker"
    ANIMATION = "animation"
    LOCATION = "location"
    CONTACT_CARD = "contact_card"


class ChannelType(StrEnum):
    TELEGRAM = "telegram"
    WEB = "web"
    EMAIL = "email"


class InboxMode(StrEnum):
    """How a channel receives updates from the upstream provider."""

    POLLING = "polling"
    WEBHOOK = "webhook"


class AutomationEvent(StrEnum):
    CONVERSATION_CREATED = "conversation_created"
    CONVERSATION_UPDATED = "conversation_updated"
    MESSAGE_CREATED = "message_created"
    CONVERSATION_RESOLVED = "conversation_resolved"


class SsoKind(StrEnum):
    OIDC = "oidc"
    SAML = "saml"
