"""Dashboard statistics for administrators."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select

from ...core.deps import DbSession, get_current_admin
from ...core.events import manager
from ...db import utcnow
from ...models import (
    Contact,
    Conversation,
    ConversationStatus,
    Inbox,
    Message,
    User,
    UserRole,
)
from ...serializers import iso

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)]
)

RECENT_ACTIVITY_LIMIT = 15


@router.get("/stats")
async def stats(db: DbSession) -> dict:
    """Aggregate counters powering the admin dashboard."""
    status_rows = (
        await db.execute(
            select(Conversation.status, func.count(Conversation.id)).group_by(
                Conversation.status
            )
        )
    ).all()
    by_status = {row[0]: int(row[1]) for row in status_rows}
    conversations = {
        status.value: by_status.get(status.value, 0) for status in ConversationStatus
    }
    conversations["total"] = sum(by_status.values())

    since = utcnow() - timedelta(days=1)
    messages_today = int(
        await db.scalar(
            select(func.count(Message.id)).where(Message.created_at >= since)
        )
        or 0
    )

    inbox_rows = (await db.scalars(select(Inbox).order_by(Inbox.name))).all()
    open_counts = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(Conversation.inbox_id, func.count(Conversation.id))
                .where(Conversation.status == ConversationStatus.OPEN.value)
                .group_by(Conversation.inbox_id)
            )
        ).all()
    }

    recent = (
        await db.scalars(
            select(Message)
            .where(Message.deleted_at.is_(None))
            .order_by(desc(Message.id))
            .limit(RECENT_ACTIVITY_LIMIT)
        )
    ).unique().all()

    online = set(manager.online_user_ids)
    agent_ids = set(
        (
            await db.scalars(
                select(User.id).where(User.is_active.is_(True))
            )
        ).all()
    )

    return {
        "conversations": conversations,
        "messages_today": messages_today,
        "contacts": int(await db.scalar(select(func.count(Contact.id))) or 0),
        "agents": len(agent_ids),
        "agents_online": len(online & agent_ids),
        "admins": int(
            await db.scalar(
                select(func.count(User.id)).where(User.role == UserRole.ADMIN.value)
            )
            or 0
        ),
        "inboxes": [
            {
                "id": inbox.id,
                "name": inbox.name,
                "channel_type": inbox.channel_type,
                "connection_status": inbox.connection_status,
                "open_conversations": open_counts.get(inbox.id, 0),
            }
            for inbox in inbox_rows
        ],
        "recent_activity": [
            {
                "id": message.id,
                "conversation_id": message.conversation_id,
                "inbox_id": message.inbox_id,
                "message_type": message.message_type,
                "private": message.private,
                "content": (message.content or "")[:180],
                "created_at": iso(message.created_at),
            }
            for message in recent
        ],
    }
