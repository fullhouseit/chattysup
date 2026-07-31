"""Conversations, labels and the join table between them."""
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
from .enums import ConversationPriority, ConversationStatus


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_status_activity", "status", "last_activity_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inbox_id: Mapped[int] = mapped_column(
        ForeignKey("inboxes.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), index=True
    )
    contact_inbox_id: Mapped[int | None] = mapped_column(
        ForeignKey("contact_inboxes.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(32), default=ConversationStatus.OPEN.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(32), default=ConversationPriority.NONE.value
    )
    #: Denormalised counters/markers keeping the conversation list cheap.
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    agent_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contact_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_reply_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    waiting_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(default=0)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    greeting_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    custom_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Provider identifier of the source thread (Telegram chat id).
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    contact: Mapped["Contact"] = relationship(lazy="joined")  # noqa: F821
    inbox: Mapped["Inbox"] = relationship(lazy="joined")  # noqa: F821
    assignee: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821
    labels: Mapped[list["ConversationLabel"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class Label(Base, TimestampMixin):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="#1F93FF")
    show_on_sidebar: Mapped[bool] = mapped_column(Boolean, default=True)


class ConversationLabel(Base):
    __tablename__ = "conversation_labels"
    __table_args__ = (UniqueConstraint("conversation_id", "label_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"), index=True
    )

    label: Mapped[Label] = relationship(lazy="joined")


class ConversationParticipant(Base):
    """Agents watching a conversation they are not assigned to."""

    __tablename__ = "conversation_participants"
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(lazy="joined")  # noqa: F821
