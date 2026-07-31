"""Inbox request bodies."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models import InboxMode
from .common import Schema


class InboxCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    channel_type: str
    mode: str = InboxMode.POLLING.value
    avatar_url: str | None = None
    proxy_url: str | None = None
    config: dict[str, Any] = {}
    is_active: bool = True
    greeting_enabled: bool = False
    greeting_message: str | None = None
    csat_enabled: bool = False
    auto_assignment_enabled: bool = False
    auto_resolve_after_minutes: int | None = None
    working_hours: dict[str, Any] = {}
    out_of_office_message: str | None = None
    member_ids: list[int] | None = None


class InboxUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    mode: str | None = None
    avatar_url: str | None = None
    proxy_url: str | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None
    greeting_enabled: bool | None = None
    greeting_message: str | None = None
    csat_enabled: bool | None = None
    auto_assignment_enabled: bool | None = None
    auto_resolve_after_minutes: int | None = None
    working_hours: dict[str, Any] | None = None
    out_of_office_message: str | None = None
