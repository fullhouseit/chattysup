"""Personal API tokens for the public REST API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...core.deps import CurrentUser, DbSession, get_current_user
from ...core.security import generate_api_token
from ...models import ApiToken
from ...schemas import ApiTokenCreate
from ...serializers import iso

router = APIRouter(
    prefix="/api_tokens", tags=["api_tokens"], dependencies=[Depends(get_current_user)]
)


def _serialize(token: ApiToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "scopes": token.scopes or [],
        "active": token.active,
        "user_id": token.user_id,
        "expires_at": iso(token.expires_at),
        "last_used_at": iso(token.last_used_at),
        "created_at": iso(token.created_at),
    }


@router.get("")
async def list_tokens(db: DbSession, user: CurrentUser) -> list[dict]:
    rows = (
        await db.scalars(
            select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.id)
        )
    ).all()
    return [_serialize(t) for t in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_token(
    payload: ApiTokenCreate, db: DbSession, user: CurrentUser
) -> dict:
    """Mint a token. The plaintext value is returned exactly once."""
    raw, prefix, token_hash = generate_api_token()
    token = ApiToken(
        name=payload.name,
        prefix=prefix,
        token_hash=token_hash,
        user_id=user.id,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
    )
    db.add(token)
    await db.flush()
    return {**_serialize(token), "token": raw}


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(token_id: int, db: DbSession, user: CurrentUser) -> None:
    token = await db.get(ApiToken, token_id)
    if not token or (token.user_id != user.id and not user.is_admin):
        raise HTTPException(status_code=404, detail="Token not found")
    await db.delete(token)
    await db.flush()
