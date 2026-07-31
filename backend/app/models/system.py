"""Automations, webhooks, API access tokens, SSO providers and settings."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base, TimestampMixin
from .enums import AutomationEvent, SsoKind


class Automation(Base, TimestampMixin):
    """Rule engine entry: ``event`` + ``conditions`` -> ``actions``.

    ``conditions`` is a list of ``{attribute, operator, values}`` objects joined
    by ``condition_logic`` (``and`` / ``or``). ``actions`` is a list of
    ``{action, params}`` objects. See ``services/automation.py``.
    """

    __tablename__ = "automations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_name: Mapped[str] = mapped_column(
        String(64), default=AutomationEvent.MESSAGE_CREATED.value, index=True
    )
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    condition_logic: Mapped[str] = mapped_column(String(8), default="and")
    actions: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Optional inbox scope; ``None`` means "all inboxes".
    inbox_id: Mapped[int | None] = mapped_column(
        ForeignKey("inboxes.id", ondelete="CASCADE"), nullable=True
    )
    #: Fire at most once per conversation.
    run_once_per_conversation: Mapped[bool] = mapped_column(Boolean, default=False)
    execution_count: Mapped[int] = mapped_column(default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AutomationRun(Base):
    """Bookkeeping so ``run_once_per_conversation`` rules stay idempotent."""

    __tablename__ = "automation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CannedResponse(Base, TimestampMixin):
    __tablename__ = "canned_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    short_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content: Mapped[str] = mapped_column(Text)


class Webhook(Base, TimestampMixin):
    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(1024))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Event names, e.g. ``["message.created", "conversation.updated"]``.
    subscriptions: Mapped[list] = mapped_column(JSON, default=list)
    #: Used to sign payloads with ``X-ChattySup-Signature`` (HMAC-SHA256).
    secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    inbox_id: Mapped[int | None] = mapped_column(
        ForeignKey("inboxes.id", ondelete="CASCADE"), nullable=True
    )
    last_status: Mapped[int | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApiToken(Base, TimestampMixin):
    """Bearer token for the public API (`Authorization: Bearer cs_…`)."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    #: First characters of the token, shown in the UI for identification.
    prefix: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SsoProvider(Base, TimestampMixin):
    """Placeholder configuration for a future OIDC/SAML login."""

    __tablename__ = "sso_providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default=SsoKind.OIDC.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    #: issuer, client_id, client_secret, scopes, jit_provisioning, default_role…
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class Setting(Base, TimestampMixin):
    """Key/value installation settings editable from the admin screen."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
