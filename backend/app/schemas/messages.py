"""Message request bodies (the create endpoint is multipart, see the router)."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class MessageUpdate(Schema):
    content: str = Field(min_length=1)


class ReactionRequest(Schema):
    emoji: str = Field(min_length=1, max_length=64)
