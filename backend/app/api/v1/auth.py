"""Authentication: bootstrap registration, login, logout and the profile."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from ...config import settings
from ...core.deps import COOKIE_NAME, CurrentUser, DbSession
from ...core.security import create_access_token, hash_password, verify_password
from ...db import utcnow
from ...models import Availability, SsoProvider, User, UserRole
from ...schemas import LoginRequest, ProfileUpdate, RegisterRequest
from ...serializers import serialize_user
from ...services import settings_service

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = settings.access_token_expire_minutes * 60


def _set_cookie(response: Response, token: str) -> None:
    """Store the JWT in an httpOnly cookie so the SPA survives a reload."""
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https://"),
        path="/",
    )


async def _issue(db: DbSession, user: User, response: Response) -> dict:
    token = create_access_token(user.id, email=user.email, role=user.role)
    _set_cookie(response, token)
    user.last_seen_at = utcnow()
    await db.flush()
    return {"token": token, "user": serialize_user(user)}


@router.get("/config")
async def auth_config(db: DbSession) -> dict:
    """Public bootstrap payload consumed by the login screen."""
    providers = (
        await db.scalars(select(SsoProvider).where(SsoProvider.enabled.is_(True)))
    ).all()
    return {
        "installation_name": await settings_service.get(
            db, "installation_name", settings.app_name
        ),
        "registration_enabled": await settings_service.registration_allowed(db),
        "has_users": await settings_service.user_count(db) > 0,
        "sso_providers": [
            {"slug": p.slug, "name": p.name, "kind": p.kind} for p in providers
        ],
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response, db: DbSession) -> dict:
    """Create an account. The very first user becomes the administrator."""
    if not await settings_service.registration_allowed(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled"
        )
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )

    first_user = await settings_service.user_count(db) == 0
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN.value if first_user else UserRole.AGENT.value,
        availability=Availability.ONLINE.value,
    )
    db.add(user)
    await db.flush()
    if first_user:
        await settings_service.seed_defaults(db)
    return await _issue(db, user, response)


@router.post("/login")
async def login(payload: LoginRequest, response: Response, db: DbSession) -> dict:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )
    return await _issue(db, user, response)


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return serialize_user(user)


@router.patch("/me")
async def update_me(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> dict:
    data = payload.model_dump(exclude_unset=True)
    new_password = data.pop("password", None)
    current_password = data.pop("current_password", None)

    if new_password:
        if not verify_password(current_password or "", user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        user.password_hash = hash_password(new_password)

    availability = data.get("availability")
    if availability is not None and availability not in {a.value for a in Availability}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown availability value",
        )

    for field, value in data.items():
        setattr(user, field, value)
    await db.flush()
    return serialize_user(user)
