"""Installation settings request body."""
from __future__ import annotations

from typing import Any

from pydantic import RootModel


class SettingsUpdate(RootModel[dict[str, Any]]):
    """Free-form key/value patch applied to the ``settings`` table."""

    root: dict[str, Any] = {}
