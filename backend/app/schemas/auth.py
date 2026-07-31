"""Authentication and profile request bodies."""
from __future__ import annotations

import re

from pydantic import Field, field_validator

from .common import Schema

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(value: str) -> str:
    """Lower-case and sanity-check an email address."""
    email = (value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email address")
    return email


class RegisterRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    email: str
    password: str = Field(min_length=8, max_length=128)

    _email = field_validator("email")(normalize_email)


class LoginRequest(Schema):
    email: str
    password: str

    _email = field_validator("email")(normalize_email)


class ProfileUpdate(Schema):
    """``PATCH /auth/me`` — every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    avatar_url: str | None = None
    signature: str | None = None
    availability: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    current_password: str | None = None
