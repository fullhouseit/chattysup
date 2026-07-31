"""Outgoing webhook request bodies."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class WebhookCreate(Schema):
    url: str = Field(min_length=1, max_length=1024)
    name: str | None = None
    subscriptions: list[str] = []
    secret: str | None = None
    active: bool = True
    inbox_id: int | None = None


class WebhookUpdate(Schema):
    url: str | None = Field(default=None, min_length=1, max_length=1024)
    name: str | None = None
    subscriptions: list[str] | None = None
    secret: str | None = None
    active: bool | None = None
    inbox_id: int | None = None
