"""SSO provider request bodies.

``config`` carries the OIDC parameters consumed by ``app.api.v1.sso``::

    {
        "issuer": "https://accounts.example.com",
        "client_id": "...",
        "client_secret": "...",
        "scopes": "openid email profile",
        "jit_provisioning": true,
        "default_role": "agent"
    }
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models import SsoKind
from .common import Schema


class SsoProviderCreate(Schema):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=255)
    kind: str = SsoKind.OIDC.value
    enabled: bool = False
    config: dict[str, Any] = {}


class SsoProviderUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
