"""Installation settings stored in the database + first-run bootstrap."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings as env_settings
from ..models import CannedResponse, Label, Setting, User

DEFAULTS: dict[str, Any] = {
    "installation_name": env_settings.app_name,
    "enable_registration": env_settings.enable_registration,
    "default_locale": "en",
    "logo_url": None,
    "auto_resolve_after_days": 0,
    # Master switch for outgoing email notifications (SMTP must also be set).
    "email_notifications_enabled": False,
}


async def get_all(db: AsyncSession) -> dict[str, Any]:
    rows = (await db.scalars(select(Setting))).all()
    stored = {row.key: (row.value or {}).get("value") for row in rows}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS or True}}


async def get(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = await db.get(Setting, key)
    if row is None:
        return DEFAULTS.get(key, default)
    return (row.value or {}).get("value", default)


async def set_value(db: AsyncSession, key: str, value: Any) -> None:
    row = await db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value={"value": value}))
    else:
        row.value = {"value": value}
    await db.flush()


async def user_count(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count(User.id))) or 0)


async def registration_allowed(db: AsyncSession) -> bool:
    """Signup is open when the flag is on, or when nobody has registered yet."""
    if await user_count(db) == 0:
        return True
    return bool(await get(db, "enable_registration", env_settings.enable_registration))


async def seed_defaults(db: AsyncSession) -> None:
    """Create the starter labels and canned responses on a fresh installation."""
    if await db.scalar(select(func.count(Label.id))):
        return
    for title, color in (
        ("device-setup", "#B02525"),
        ("lead", "#F2994A"),
        ("software", "#9B51E0"),
        ("billing", "#27AE60"),
    ):
        db.add(Label(title=title, color=color))
    for code, content in (
        ("hi", "Hi 👋, how may I help you?"),
        ("thanks", "Thank you for reaching out! Is there anything else I can help with?"),
        ("wait", "Give me a moment while I look into this for you."),
    ):
        db.add(CannedResponse(short_code=code, content=content))
    await db.flush()
