"""Primitives shared by every request schema and list endpoint."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base request model: unknown keys are ignored rather than rejected."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class IdList(Schema):
    """Body of the ``PUT .../members`` style endpoints."""

    user_ids: list[int] = []


def clamp_page(page: int | None, per_page: int | None, *, max_per_page: int = 100) -> tuple[int, int]:
    """Normalise user supplied pagination parameters."""
    safe_page = max(1, int(page or 1))
    safe_per_page = min(max(1, int(per_page or 25)), max_per_page)
    return safe_page, safe_per_page


def page_meta(total: int, page: int, per_page: int, **extra: Any) -> dict[str, Any]:
    """Build the ``meta`` block returned by paginated list endpoints."""
    return {"total": total, "page": page, "per_page": per_page, **extra}
