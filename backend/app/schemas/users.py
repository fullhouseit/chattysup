"""Administrative user management bodies."""
from __future__ import annotations

from pydantic import Field, field_validator

from .auth import normalize_email
from .common import Schema


class UserCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: str = "agent"
    display_name: str | None = None
    avatar_url: str | None = None
    signature: str | None = None

    _email = field_validator("email")(normalize_email)


class UserUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    signature: str | None = None
    availability: str | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str | None) -> str | None:
        return normalize_email(value) if value else None
