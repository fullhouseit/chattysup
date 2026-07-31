"""Single sign-on.

Administration of providers (``/sso_providers``) plus a self-contained OIDC
authorization-code + PKCE flow (``/auth/sso/{slug}/login`` and ``/callback``).

The provider ``config`` accepts::

    issuer              https://accounts.example.com   (discovery document root)
    authorization_url   optional explicit override
    token_url           optional explicit override
    userinfo_url        optional explicit override
    client_id / client_secret
    scopes              defaults to "openid email profile"
    jit_provisioning    create unknown users on first login (default true)
    default_role        role given to provisioned users (default "agent")
"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from ...config import settings
from ...core.deps import COOKIE_NAME, DbSession, get_current_admin
from ...core.security import create_access_token
from ...db import utcnow
from ...models import Availability, SsoKind, SsoProvider, User, UserRole
from ...schemas import SsoProviderCreate, SsoProviderUpdate

logger = logging.getLogger(__name__)

admin_router = APIRouter(
    prefix="/sso_providers",
    tags=["sso"],
    dependencies=[Depends(get_current_admin)],
)
router = APIRouter(prefix="/auth/sso", tags=["sso"])

#: Pending authorisation requests: state -> {verifier, slug, created_at}.
_STATES: dict[str, dict[str, Any]] = {}
STATE_TTL_SECONDS = 600
SECRET_MASK = "••••••••"


# ---------------------------------------------------------------------------
# Provider administration
# ---------------------------------------------------------------------------
def _serialize(provider: SsoProvider) -> dict:
    config = dict(provider.config or {})
    if config.get("client_secret"):
        config["client_secret"] = SECRET_MASK
    return {
        "id": provider.id,
        "slug": provider.slug,
        "name": provider.name,
        "kind": provider.kind,
        "enabled": provider.enabled,
        "config": config,
        "login_url": f"/api/v1/auth/sso/{provider.slug}/login",
        "callback_url": f"{settings.base_url}/api/v1/auth/sso/{provider.slug}/callback",
    }


@admin_router.get("")
async def list_providers(db: DbSession) -> list[dict]:
    rows = (await db.scalars(select(SsoProvider).order_by(SsoProvider.slug))).all()
    return [_serialize(p) for p in rows]


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def create_provider(payload: SsoProviderCreate, db: DbSession) -> dict:
    if payload.kind not in {k.value for k in SsoKind}:
        raise HTTPException(status_code=422, detail="Unknown SSO kind")
    if await db.scalar(select(SsoProvider).where(SsoProvider.slug == payload.slug)):
        raise HTTPException(status_code=409, detail="Slug already used")
    provider = SsoProvider(**payload.model_dump())
    db.add(provider)
    await db.flush()
    return _serialize(provider)


@admin_router.patch("/{provider_id}")
async def update_provider(
    provider_id: int, payload: SsoProviderUpdate, db: DbSession
) -> dict:
    provider = await db.get(SsoProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    data = payload.model_dump(exclude_unset=True)
    config = data.pop("config", None)
    if config is not None:
        merged = {**(provider.config or {}), **config}
        if config.get("client_secret") in (SECRET_MASK, "", None):
            merged["client_secret"] = (provider.config or {}).get("client_secret")
        provider.config = merged
    for field, value in data.items():
        setattr(provider, field, value)
    await db.flush()
    return _serialize(provider)


@admin_router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: int, db: DbSession) -> None:
    provider = await db.get(SsoProvider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.delete(provider)
    await db.flush()


# ---------------------------------------------------------------------------
# OIDC flow
# ---------------------------------------------------------------------------
async def _load_provider(db: DbSession, slug: str) -> SsoProvider:
    provider = await db.scalar(select(SsoProvider).where(SsoProvider.slug == slug))
    if not provider or not provider.enabled:
        raise HTTPException(status_code=404, detail="Unknown SSO provider")
    if provider.kind != SsoKind.OIDC.value:
        raise HTTPException(
            status_code=501, detail=f"'{provider.kind}' SSO is not implemented"
        )
    return provider


async def _discover(config: dict[str, Any]) -> dict[str, str]:
    """Resolve the provider endpoints, using the discovery document when needed."""
    endpoints = {
        "authorization_endpoint": config.get("authorization_url"),
        "token_endpoint": config.get("token_url"),
        "userinfo_endpoint": config.get("userinfo_url"),
    }
    if all(endpoints[k] for k in ("authorization_endpoint", "token_endpoint")):
        return {k: v for k, v in endpoints.items() if v}

    issuer = (config.get("issuer") or "").rstrip("/")
    if not issuer:
        raise HTTPException(status_code=500, detail="SSO provider has no issuer")
    url = f"{issuer}/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=10.0, proxy=settings.http_proxy) as client:
            response = await client.get(url)
            response.raise_for_status()
            document = response.json()
    except Exception as exc:
        logger.warning("OIDC discovery failed for %s: %s", url, exc)
        raise HTTPException(
            status_code=502, detail="Could not reach the identity provider"
        ) from exc
    return {k: v for k, v in {**document, **{k: v for k, v in endpoints.items() if v}}.items()}


def _prune_states() -> None:
    cutoff = time.time() - STATE_TTL_SECONDS
    for key, value in list(_STATES.items()):
        if value["created_at"] < cutoff:
            _STATES.pop(key, None)


def _callback_url(slug: str) -> str:
    return f"{settings.base_url.rstrip('/')}/api/v1/auth/sso/{slug}/callback"


@router.get("/{slug}/login")
async def sso_login(slug: str, db: DbSession) -> RedirectResponse:
    """Redirect the browser to the identity provider."""
    provider = await _load_provider(db, slug)
    config = provider.config or {}
    endpoints = await _discover(config)

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    _prune_states()
    _STATES[state] = {"verifier": verifier, "slug": slug, "created_at": time.time()}

    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.get("client_id", ""),
            "redirect_uri": _callback_url(slug),
            "scope": config.get("scopes") or "openid email profile",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{endpoints['authorization_endpoint']}?{query}")


@router.get("/{slug}/callback")
async def sso_callback(
    slug: str,
    db: DbSession,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Exchange the authorization code and log the user in."""
    provider = await _load_provider(db, slug)
    if error:
        raise HTTPException(status_code=400, detail=f"Identity provider error: {error}")

    _prune_states()
    pending = _STATES.pop(state or "", None)
    if not code or not pending or pending["slug"] != slug:
        raise HTTPException(status_code=400, detail="Invalid or expired SSO state")

    config = provider.config or {}
    endpoints = await _discover(config)

    async with httpx.AsyncClient(timeout=15.0, proxy=settings.http_proxy) as client:
        try:
            token_response = await client.post(
                endpoints["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _callback_url(slug),
                    "client_id": config.get("client_id", ""),
                    "client_secret": config.get("client_secret", ""),
                    "code_verifier": pending["verifier"],
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            tokens = token_response.json()
        except Exception as exc:
            logger.warning("OIDC token exchange failed: %s", exc)
            raise HTTPException(status_code=502, detail="Token exchange failed") from exc

        claims = _decode_id_token(tokens.get("id_token"))
        if not claims.get("email") and endpoints.get("userinfo_endpoint"):
            try:
                userinfo = await client.get(
                    endpoints["userinfo_endpoint"],
                    headers={"Authorization": f"Bearer {tokens.get('access_token', '')}"},
                )
                userinfo.raise_for_status()
                claims = {**claims, **userinfo.json()}
            except Exception as exc:  # pragma: no cover - optional endpoint
                logger.info("userinfo lookup failed: %s", exc)

    user = await _provision(db, provider, claims)
    token = create_access_token(user.id, email=user.email, role=user.role)
    response = RedirectResponse(f"{settings.base_url.rstrip('/')}/?sso=ok")
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.base_url.startswith("https://"),
        path="/",
    )
    return response


def _decode_id_token(id_token: str | None) -> dict[str, Any]:
    """Read the claims of a JWT without verifying it.

    The token arrived over a TLS back-channel call we made ourselves, so the
    transport already authenticates the issuer.
    """
    if not id_token:
        return {}
    try:
        import json

        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # pragma: no cover - malformed token
        logger.warning("could not decode id_token")
        return {}


async def _provision(
    db: DbSession, provider: SsoProvider, claims: dict[str, Any]
) -> User:
    """Find or (optionally) create the local account for an SSO identity."""
    config = provider.config or {}
    email = (claims.get("email") or "").strip().lower()
    subject = str(claims.get("sub") or "")
    if not email:
        raise HTTPException(
            status_code=400, detail="The identity provider returned no email address"
        )

    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        if not config.get("jit_provisioning", True):
            raise HTTPException(
                status_code=403, detail="No local account for this identity"
            )
        role = config.get("default_role") or UserRole.AGENT.value
        if role not in {r.value for r in UserRole}:
            role = UserRole.AGENT.value
        user = User(
            email=email,
            name=claims.get("name") or claims.get("preferred_username") or email,
            role=role,
            avatar_url=claims.get("picture"),
            availability=Availability.ONLINE.value,
            provider=provider.slug,
            provider_subject=subject,
        )
        db.add(user)
        await db.flush()
    else:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        user.provider = provider.slug
        user.provider_subject = subject or user.provider_subject

    user.last_seen_at = utcnow()
    await db.flush()
    return user
