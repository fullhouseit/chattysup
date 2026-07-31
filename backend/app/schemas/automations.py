"""Automation rule request bodies."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models import AutomationEvent
from .common import Schema


class AutomationCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_name: str = AutomationEvent.MESSAGE_CREATED.value
    conditions: list[dict[str, Any]] = []
    condition_logic: str = "and"
    actions: list[dict[str, Any]] = []
    active: bool = True
    inbox_id: int | None = None
    run_once_per_conversation: bool = False


class AutomationUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    event_name: str | None = None
    conditions: list[dict[str, Any]] | None = None
    condition_logic: str | None = None
    actions: list[dict[str, Any]] | None = None
    active: bool | None = None
    inbox_id: int | None = None
    run_once_per_conversation: bool | None = None
