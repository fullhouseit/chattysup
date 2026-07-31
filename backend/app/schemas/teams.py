"""Team request bodies."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class TeamCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    allow_auto_assign: bool = True
    member_ids: list[int] = []


class TeamUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    allow_auto_assign: bool | None = None
    member_ids: list[int] | None = None
