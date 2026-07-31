"""Conversation request bodies."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .common import Schema


class ConversationUpdate(Schema):
    status: str | None = None
    priority: str | None = None
    assignee_id: int | None = None
    team_id: int | None = None
    muted: bool | None = None
    snoozed_until: datetime | None = None
    custom_attributes: dict[str, Any] | None = None


class LabelAssignment(Schema):
    """``PUT /conversations/{id}/labels`` — the complete desired label set."""

    labels: list[str] = []


class ParticipantCreate(Schema):
    user_id: int
