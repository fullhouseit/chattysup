"""Contacts and their per-channel identities."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, TimestampMixin


class Contact(Base, TimestampMixin):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    identifier: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    custom_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    social_profiles: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[list["ContactNote"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )
    channels: Mapped[list["ContactInbox"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )


class ContactInbox(Base, TimestampMixin):
    """Links a contact to an inbox through the provider specific identifier."""

    __tablename__ = "contact_inboxes"
    __table_args__ = (
        UniqueConstraint("inbox_id", "source_id"),
        Index("ix_contact_inboxes_contact", "contact_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    inbox_id: Mapped[int] = mapped_column(ForeignKey("inboxes.id", ondelete="CASCADE"))
    #: Telegram chat id, email address, phone number …
    source_id: Mapped[str] = mapped_column(String(255))
    #: Provider payload snapshot (username, language_code, …).
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    contact: Mapped[Contact] = relationship(back_populates="channels")


class ContactNote(Base, TimestampMixin):
    __tablename__ = "contact_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE")
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)

    contact: Mapped[Contact] = relationship(back_populates="notes")
