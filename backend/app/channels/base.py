"""Channel abstraction.

A *channel* is a pluggable integration with an external messaging provider
(Telegram, WhatsApp, email…). An *inbox* is a configured instance of a channel.

Adding a new source means:

1. subclassing :class:`BaseChannel`,
2. describing its settings with :class:`FieldSpec` (the admin UI renders the
   form from this — no frontend change needed),
3. calling :func:`register` on the class.

Everything else — conversation routing, storage, automations, webhooks, the
UI — works unchanged because channels only ever exchange the normalised
dataclasses defined below.
"""
from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

from ..models import AttachmentType, ContentType, Inbox


class ChannelError(RuntimeError):
    """Recoverable failure while talking to the provider."""


class ChannelConfigError(ChannelError):
    """The inbox configuration is invalid (bad token, missing field, …)."""


# ---------------------------------------------------------------------------
# Configuration descriptors — drive the dynamic settings form in the frontend.
# ---------------------------------------------------------------------------
FieldKind = Literal["text", "password", "textarea", "number", "boolean", "select", "url"]


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: FieldKind = "text"
    required: bool = False
    placeholder: str = ""
    help_text: str = ""
    default: Any = None
    secret: bool = False
    options: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Normalised payloads exchanged between channels and the core.
# ---------------------------------------------------------------------------
@dataclass
class NormalizedAttachment:
    file_type: str = AttachmentType.FILE.value
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    #: Provider identifier used to lazily download / re-send the file.
    external_id: str | None = None
    external_url: str | None = None
    #: Already downloaded bytes, when the provider hands them over inline.
    data: bytes | None = None
    thumb_external_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedContact:
    source_id: str
    name: str = ""
    username: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    phone: str | None = None
    language: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedMessage:
    source_id: str | None = None
    content: str | None = None
    content_type: str = ContentType.TEXT.value
    attachments: list[NormalizedAttachment] = field(default_factory=list)
    sent_at: datetime | None = None
    #: ``reply_to``, ``forwarded_from``, ``entities``, sticker emoji …
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundEvent:
    """A single normalised thing that happened upstream."""

    kind: Literal[
        "message", "message_edited", "message_deleted", "reaction", "read", "typing"
    ]
    chat_source_id: str
    contact: NormalizedContact | None = None
    message: NormalizedMessage | None = None
    #: For ``reaction`` events: the full emoji set now present on the message.
    reactions: list[str] = field(default_factory=list)
    target_source_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundAttachment:
    file_type: str
    file_name: str
    mime_type: str | None = None
    data: bytes | None = None
    #: Reuse a provider-side file instead of re-uploading bytes.
    external_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    content: str | None = None
    attachments: list[OutboundAttachment] = field(default_factory=list)
    reply_to_source_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    source_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Channel contract
# ---------------------------------------------------------------------------
class BaseChannel(abc.ABC):
    #: Stable identifier stored in ``Inbox.channel_type``.
    key: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    #: Lucide icon name rendered by the frontend.
    icon: ClassVar[str] = "message-circle"
    color: ClassVar[str] = "#1F93FF"

    supports_polling: ClassVar[bool] = False
    supports_webhook: ClassVar[bool] = False
    supports_proxy: ClassVar[bool] = False
    #: ``True`` when ``Inbox.webhook_token`` is a permanent public identifier
    #: rather than a per-mode delivery secret. Such a token must survive a mode
    #: change: clients have it baked into their URLs and rotating it 404s them.
    webhook_token_is_identity: ClassVar[bool] = False
    #: Optional feature flags: ``reactions``, ``typing``, ``edit``, ``delete``,
    #: ``voice``, ``stickers``, ``read_receipts``.
    capabilities: ClassVar[set[str]] = set()
    config_fields: ClassVar[list[FieldSpec]] = []

    def __init__(self, inbox: Inbox) -> None:
        self.inbox = inbox
        self.config: dict[str, Any] = dict(inbox.config or {})

    # -- lifecycle -------------------------------------------------------
    @classmethod
    async def validate_config(
        cls, config: dict[str, Any], *, proxy: str | None = None
    ) -> dict[str, Any]:
        """Validate/normalise raw form input. Raises :class:`ChannelConfigError`.

        ``proxy`` is the inbox-level proxy the operator just entered. It is not
        part of ``config``, yet any implementation that reaches the provider to
        verify credentials must honour it — otherwise validation would go out
        directly and fail on networks that only reach the provider through the
        proxy.
        """
        for spec in cls.config_fields:
            if spec.required and not config.get(spec.key):
                raise ChannelConfigError(f"Field '{spec.label}' is required")
        return config

    async def setup(self) -> dict[str, Any]:
        """Called after the inbox is created/updated. Returns info for the UI."""
        return {}

    async def teardown(self) -> None:
        """Called before the inbox is deleted or switched to another mode."""

    async def health_check(self) -> dict[str, Any]:
        """Ping the provider. Raises :class:`ChannelError` when unreachable."""
        return {"status": "ok"}

    async def close(self) -> None:
        """Release network resources."""

    # -- inbound ---------------------------------------------------------
    async def fetch_updates(
        self, cursor: str | None
    ) -> tuple[list[InboundEvent], str | None]:
        """Long-polling entry point. Returns events and the next cursor."""
        raise NotImplementedError

    async def parse_webhook(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> list[InboundEvent]:
        """Convert one provider webhook body into normalised events."""
        raise NotImplementedError

    # -- outbound --------------------------------------------------------
    @abc.abstractmethod
    async def send_message(
        self, chat_source_id: str, message: OutboundMessage
    ) -> SendResult:
        ...

    async def send_reaction(
        self, chat_source_id: str, message_source_id: str, emojis: list[str]
    ) -> None:
        raise NotImplementedError

    async def send_typing(self, chat_source_id: str) -> None:
        return None

    async def edit_message(
        self, chat_source_id: str, message_source_id: str, content: str
    ) -> None:
        raise NotImplementedError

    async def delete_message(self, chat_source_id: str, message_source_id: str) -> None:
        raise NotImplementedError

    async def mark_read(self, chat_source_id: str, message_source_id: str) -> None:
        return None

    # -- media -----------------------------------------------------------
    async def download_file(self, external_id: str) -> tuple[bytes, str | None, str | None]:
        """Return ``(bytes, filename, mime_type)`` for a provider file id."""
        raise NotImplementedError

    async def fetch_avatar(
        self, contact: NormalizedContact
    ) -> tuple[bytes, str | None, str | None] | None:
        """Return the contact's profile picture as ``(bytes, filename, mime)``.

        ``None`` means the provider has no picture for this contact (or does
        not expose one). Advertise ``"avatars"`` in :attr:`capabilities` when
        implementing this.
        """
        return None

    # -- introspection ---------------------------------------------------
    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "key": cls.key,
            "display_name": cls.display_name,
            "description": cls.description,
            "icon": cls.icon,
            "color": cls.color,
            "supports_polling": cls.supports_polling,
            "supports_webhook": cls.supports_webhook,
            "supports_proxy": cls.supports_proxy,
            "capabilities": sorted(cls.capabilities),
            "config_fields": [f.to_dict() for f in cls.config_fields],
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, type[BaseChannel]] = {}


def register(channel_cls: type[BaseChannel]) -> type[BaseChannel]:
    _REGISTRY[channel_cls.key] = channel_cls
    return channel_cls


def get_channel_class(key: str) -> type[BaseChannel]:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ChannelConfigError(f"Unknown channel type '{key}'") from None


def build_channel(inbox: Inbox) -> BaseChannel:
    return get_channel_class(inbox.channel_type)(inbox)


def available_channels() -> list[dict[str, Any]]:
    return [cls.describe() for cls in _REGISTRY.values()]


def registry() -> dict[str, type[BaseChannel]]:
    return dict(_REGISTRY)
