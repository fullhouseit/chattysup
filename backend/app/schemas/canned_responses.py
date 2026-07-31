"""Canned response request bodies."""
from __future__ import annotations

from pydantic import Field

from .common import Schema


class CannedResponseCreate(Schema):
    short_code: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)


class CannedResponseUpdate(Schema):
    short_code: str | None = Field(default=None, min_length=1, max_length=64)
    content: str | None = Field(default=None, min_length=1)
