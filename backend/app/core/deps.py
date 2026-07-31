"""FastAPI dependencies: authentication and authorisation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import ApiToken, User, UserRole
from .security import decode_token, hash_api_token

DbSession = Annotated[AsyncSession, Depends(get_db)]

COOKIE_NAME = "chattysup_token"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    api_key = request.headers.get("X-Api-Key")
    if api_key:
        return api_key.strip()
    return request.cookies.get(COOKIE_NAME)


async def resolve_user(db: AsyncSession, token: str | None) -> User | None:
    """Resolve a JWT *or* an API token to a user."""
    if not token:
        return None

    if token.startswith("cs_"):
        row = await db.scalar(
            select(ApiToken).where(
                ApiToken.token_hash == hash_api_token(token), ApiToken.active.is_(True)
            )
        )
        if not row:
            return None
        if row.expires_at and row.expires_at < datetime.now(timezone.utc):
            return None
        row.last_used_at = datetime.now(timezone.utc)
        user = await db.get(User, row.user_id)
        return user if user and user.is_active else None

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user = await db.get(User, int(payload["sub"]))
    return user if user and user.is_active else None


async def get_current_user(request: Request, db: DbSession) -> User:
    user = await resolve_user(db, _extract_token(request))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
