"""Personal API token request bodies."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import Schema


class ApiTokenCreate(Schema):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = []
    expires_at: datetime | None = None
