"""Contact request bodies."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import Schema


class ContactCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    identifier: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    custom_attributes: dict[str, Any] = {}
    social_profiles: dict[str, Any] = {}


class ContactUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    identifier: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    country_code: str | None = None
    timezone: str | None = None
    blocked: bool | None = None
    custom_attributes: dict[str, Any] | None = None
    social_profiles: dict[str, Any] | None = None


class ContactNoteCreate(Schema):
    content: str = Field(min_length=1)


class BlockRequest(Schema):
    blocked: bool = True
