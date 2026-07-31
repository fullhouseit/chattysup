"""Automation rules and the catalogue that drives the rule builder UI."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...core.deps import DbSession, get_current_admin, get_current_user
from ...models import Automation
from ...schemas import AutomationCreate, AutomationUpdate
from ...serializers import iso
from ...services import automation as automation_service

router = APIRouter(
    prefix="/automations", tags=["automations"], dependencies=[Depends(get_current_user)]
)


def _serialize(rule: Automation) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "event_name": rule.event_name,
        "conditions": rule.conditions or [],
        "condition_logic": rule.condition_logic,
        "actions": rule.actions or [],
        "active": rule.active,
        "inbox_id": rule.inbox_id,
        "run_once_per_conversation": rule.run_once_per_conversation,
        "execution_count": rule.execution_count,
        "last_executed_at": iso(rule.last_executed_at),
        "created_at": iso(rule.created_at),
    }


async def _get(db: DbSession, automation_id: int) -> Automation:
    rule = await db.get(Automation, automation_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation not found")
    return rule


@router.get("/catalogue")
async def catalogue() -> dict:
    """Events, attributes, operators and actions supported by the engine."""
    return automation_service.catalogue()


@router.get("")
async def list_automations(db: DbSession) -> list[dict]:
    rows = (await db.scalars(select(Automation).order_by(Automation.id))).all()
    return [_serialize(r) for r in rows]


@router.post(
    "", status_code=status.HTTP_201_CREATED, dependencies=[Depends(get_current_admin)]
)
async def create_automation(payload: AutomationCreate, db: DbSession) -> dict:
    known_events = set(automation_service.catalogue()["events"])
    if payload.event_name not in known_events:
        raise HTTPException(status_code=422, detail="Unknown automation event")
    rule = Automation(**payload.model_dump())
    db.add(rule)
    await db.flush()
    return _serialize(rule)


@router.patch("/{automation_id}", dependencies=[Depends(get_current_admin)])
async def update_automation(
    automation_id: int, payload: AutomationUpdate, db: DbSession
) -> dict:
    rule = await _get(db, automation_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("event_name") and data["event_name"] not in set(
        automation_service.catalogue()["events"]
    ):
        raise HTTPException(status_code=422, detail="Unknown automation event")
    for field, value in data.items():
        setattr(rule, field, value)
    await db.flush()
    return _serialize(rule)


@router.delete(
    "/{automation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
async def delete_automation(automation_id: int, db: DbSession) -> None:
    rule = await _get(db, automation_id)
    await db.delete(rule)
    await db.flush()
