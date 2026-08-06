"""Notification preference payloads."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class NotificationPreferences(Schema):
    """Every field optional: the client sends only what it changes."""

    email_notifications: bool | None = None
    assigned: bool | None = None
    unassigned: bool | None = None
    participating: bool | None = None
    others: bool | None = None
    private_notes: bool | None = None
    skip_when_online: bool | None = None
    min_interval_seconds: int | None = Field(default=None, ge=0, le=86_400)
