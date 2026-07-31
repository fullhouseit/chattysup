"""Canned responses (``/shortcode`` replies)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...core.deps import DbSession, get_current_user
from ...models import CannedResponse
from ...schemas import CannedResponseCreate, CannedResponseUpdate

router = APIRouter(
    prefix="/canned_responses",
    tags=["canned_responses"],
    dependencies=[Depends(get_current_user)],
)


def _serialize(row: CannedResponse) -> dict:
    return {"id": row.id, "short_code": row.short_code, "content": row.content}


async def _get(db: DbSession, response_id: int) -> CannedResponse:
    row = await db.get(CannedResponse, response_id)
    if not row:
        raise HTTPException(status_code=404, detail="Canned response not found")
    return row


@router.get("")
async def list_canned_responses(db: DbSession) -> list[dict]:
    rows = (
        await db.scalars(select(CannedResponse).order_by(CannedResponse.short_code))
    ).all()
    return [_serialize(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_canned_response(
    payload: CannedResponseCreate, db: DbSession
) -> dict:
    exists = await db.scalar(
        select(CannedResponse).where(CannedResponse.short_code == payload.short_code)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Short code already used")
    row = CannedResponse(short_code=payload.short_code, content=payload.content)
    db.add(row)
    await db.flush()
    return _serialize(row)


@router.patch("/{response_id}")
async def update_canned_response(
    response_id: int, payload: CannedResponseUpdate, db: DbSession
) -> dict:
    row = await _get(db, response_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await db.flush()
    return _serialize(row)


@router.delete("/{response_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_canned_response(response_id: int, db: DbSession) -> None:
    row = await _get(db, response_id)
    await db.delete(row)
    await db.flush()
