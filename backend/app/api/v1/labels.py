"""Label catalogue."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...core.deps import DbSession, get_current_admin, get_current_user
from ...models import Label
from ...schemas import LabelCreate, LabelUpdate
from ...serializers import serialize_label

router = APIRouter(
    prefix="/labels", tags=["labels"], dependencies=[Depends(get_current_user)]
)


async def _get_label(db: DbSession, label_id: int) -> Label:
    label = await db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    return label


@router.get("")
async def list_labels(db: DbSession) -> list[dict]:
    rows = (await db.scalars(select(Label).order_by(Label.title))).all()
    return [serialize_label(label) for label in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_label(payload: LabelCreate, db: DbSession) -> dict:
    if await db.scalar(select(Label).where(Label.title == payload.title)):
        raise HTTPException(status_code=409, detail="Label already exists")
    label = Label(**payload.model_dump())
    db.add(label)
    await db.flush()
    return serialize_label(label)


@router.patch("/{label_id}")
async def update_label(label_id: int, payload: LabelUpdate, db: DbSession) -> dict:
    label = await _get_label(db, label_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(label, field, value)
    await db.flush()
    return serialize_label(label)


@router.delete(
    "/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
async def delete_label(label_id: int, db: DbSession) -> None:
    label = await _get_label(db, label_id)
    await db.delete(label)
    await db.flush()
