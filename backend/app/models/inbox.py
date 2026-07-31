"""Inboxes — configured instances of a channel (a Telegram bot, an email box…)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, TimestampMixin
from .enums import ChannelType, InboxMode


class Inbox(Base, TimestampMixin):
    __tablename__ = "inboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    channel_type: Mapped[str] = mapped_column(
        String(64), default=ChannelType.TELEGRAM.value, index=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    #: Channel specific configuration. Secrets live here (bot token, …) and are
    #: redacted by the API serializers unless the caller is an administrator.
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    #: ``polling`` or ``webhook``.
    mode: Mapped[str] = mapped_column(String(32), default=InboxMode.POLLING.value)
    #: Optional per-inbox outbound proxy, e.g. ``http://user:pass@host:3128``.
    proxy_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: Random string included in the public webhook path for this inbox.
    webhook_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )

    # --- Behaviour ----------------------------------------------------
    greeting_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    greeting_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    csat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_assignment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_resolve_after_minutes: Mapped[int | None] = mapped_column(nullable=True)
    working_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    out_of_office_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Runtime state (written by the worker supervisor) ---------------
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown")
    connection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Provider cursor (Telegram ``update_id`` offset, IMAP UID, …).
    cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    members: Mapped[list["InboxMember"]] = relationship(  # noqa: F821
        back_populates="inbox", cascade="all, delete-orphan"
    )
