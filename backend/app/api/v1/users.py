"""Agent management (administrators only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...core.deps import CurrentAdmin, DbSession, get_current_admin
from ...core.security import hash_password
from ...models import User, UserRole
from ...schemas import UserCreate, UserUpdate
from ...serializers import serialize_user

router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(get_current_admin)]
)


async def _get_user(db: DbSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("")
async def list_users(db: DbSession) -> list[dict]:
    users = (await db.scalars(select(User).order_by(User.name))).all()
    return [serialize_user(u) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DbSession) -> dict:
    if await db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    if payload.role not in {r.value for r in UserRole}:
        raise HTTPException(status_code=422, detail="Unknown role")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name,
        avatar_url=payload.avatar_url,
        signature=payload.signature,
    )
    db.add(user)
    await db.flush()
    return serialize_user(user)


@router.get("/{user_id}")
async def get_user(user_id: int, db: DbSession) -> dict:
    return serialize_user(await _get_user(db, user_id))


@router.patch("/{user_id}")
async def update_user(user_id: int, payload: UserUpdate, db: DbSession) -> dict:
    user = await _get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)

    password = data.pop("password", None)
    if password:
        user.password_hash = hash_password(password)
    if data.get("role") and data["role"] not in {r.value for r in UserRole}:
        raise HTTPException(status_code=422, detail="Unknown role")
    email = data.get("email")
    if email and email != user.email:
        if await db.scalar(select(User).where(User.email == email)):
            raise HTTPException(status_code=409, detail="Email already registered")

    for field, value in data.items():
        setattr(user, field, value)
    await db.flush()
    return serialize_user(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, admin: CurrentAdmin) -> None:
    user = await _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself")
    await db.delete(user)
    await db.flush()
