"""Installation settings (administrators only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...core.deps import DbSession, get_current_admin
from ...schemas import SettingsUpdate
from ...services import settings_service

router = APIRouter(
    prefix="/settings", tags=["settings"], dependencies=[Depends(get_current_admin)]
)


@router.get("")
async def get_settings(db: DbSession) -> dict:
    return await settings_service.get_all(db)


@router.patch("")
async def update_settings(payload: SettingsUpdate, db: DbSession) -> dict:
    """Persist every supplied key; unknown keys are stored verbatim."""
    for key, value in payload.root.items():
        await settings_service.set_value(db, key, value)
    return await settings_service.get_all(db)
