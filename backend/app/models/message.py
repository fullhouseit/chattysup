"""Messages, attachments and reactions."""
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
from .enums import ContentType, MessageStatus, MessageType, SenderType


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        UniqueConstraint("inbox_id", "source_id", name="uq_messages_inbox_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    inbox_id: Mapped[int] = mapped_column(ForeignKey("inboxes.id", ondelete="CASCADE"))

    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_type: Mapped[str] = mapped_column(String(32), default=MessageType.INCOMING.value)
    content_type: Mapped[str] = mapped_column(String(32), default=ContentType.TEXT.value)
    #: ``True`` for internal notes that are never delivered to the contact.
    private: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=MessageStatus.SENT.value)

    sender_type: Mapped[str] = mapped_column(String(32), default=SenderType.CONTACT.value)
    sender_id: Mapped[int | None] = mapped_column(nullable=True)

    #: Provider message identifier, used for de-duplication and for editing /
    #: reacting to messages upstream.
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    #: Free-form provider metadata: ``reply_to``, ``forwarded_from``, sticker
    #: emoji, edit history, delivery errors, …
    content_attributes: Mapped[dict] = mapped_column(JSON, default=dict)

    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    external_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="selectin"
    )
    reactions: Mapped[list["MessageReaction"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="selectin"
    )


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    file_type: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size: Mapped[int | None] = mapped_column(nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Path relative to ``settings.storage_dir`` once the file is downloaded.
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: Remote URL when the file lives at the provider (not yet mirrored).
    external_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    #: Provider file identifier (Telegram ``file_id``) used for re-sending.
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumb_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: duration, waveform, width/height, latitude/longitude, sticker emoji…
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    message: Mapped[Message | None] = relationship(back_populates="attachments")


class MessageReaction(Base, TimestampMixin):
    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "emoji", "user_id", "contact_id", name="uq_reaction_identity"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    emoji: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True
    )

    message: Mapped[Message] = relationship(back_populates="reactions")
