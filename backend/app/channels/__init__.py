"""Channel registry. Importing this package registers every built-in channel."""
from .base import (  # noqa: F401
    BaseChannel,
    ChannelConfigError,
    ChannelError,
    FieldSpec,
    InboundEvent,
    NormalizedAttachment,
    NormalizedContact,
    NormalizedMessage,
    OutboundAttachment,
    OutboundMessage,
    SendResult,
    available_channels,
    build_channel,
    get_channel_class,
    register,
    registry,
)
from .api_channel import ApiChannel  # noqa: F401
from .telegram import TelegramChannel  # noqa: F401

__all__ = [
    "ApiChannel",
    "BaseChannel",
    "ChannelConfigError",
    "ChannelError",
    "FieldSpec",
    "InboundEvent",
    "NormalizedAttachment",
    "NormalizedContact",
    "NormalizedMessage",
    "OutboundAttachment",
    "OutboundMessage",
    "SendResult",
    "TelegramChannel",
    "available_channels",
    "build_channel",
    "get_channel_class",
    "register",
    "registry",
]
