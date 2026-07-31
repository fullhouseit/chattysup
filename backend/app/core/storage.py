"""Local filesystem storage for attachments.

The interface is deliberately narrow (``save_bytes`` / ``path_for`` / ``url_for``)
so an S3 backend can be dropped in later without touching call sites.
"""
from __future__ import annotations

import mimetypes
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str | None, fallback_ext: str = "") -> str:
    if not name:
        return f"file{fallback_ext}"
    name = _SAFE.sub("_", name.strip())[:180]
    return name or f"file{fallback_ext}"


def build_key(inbox_id: int, filename: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"inbox-{inbox_id}/{day}/{secrets.token_hex(8)}-{sanitize_filename(filename)}"


def path_for(key: str) -> Path:
    return settings.storage_dir / key


def save_bytes(key: str, data: bytes) -> Path:
    target = path_for(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def delete(key: str | None) -> None:
    if not key:
        return
    target = path_for(key)
    if target.is_file():
        target.unlink(missing_ok=True)


def url_for(attachment_id: int) -> str:
    return f"/api/v1/attachments/{attachment_id}/file"


def guess_mime(filename: str | None, default: str = "application/octet-stream") -> str:
    if not filename:
        return default
    return mimetypes.guess_type(filename)[0] or default
