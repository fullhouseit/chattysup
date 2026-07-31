"""Label request bodies."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class LabelCreate(Schema):
    title: str = Field(min_length=1, max_length=128)
    description: str | None = None
    color: str = "#1F93FF"
    show_on_sidebar: bool = True


class LabelUpdate(Schema):
    title: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    color: str | None = None
    show_on_sidebar: bool | None = None
