"""Conversation list, detail, mutations, labels, participants and messages."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import Select, case, delete, desc, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from ...config import settings
from ...core import events as bus
from ...core.deps import CurrentUser, DbSession, get_current_user
from ...core import storage
from ...models import (
    Attachment,
    AttachmentType,
    Contact,
    Conversation,
    ConversationLabel,
    ConversationParticipant,
    ConversationPriority,
    ConversationStatus,
    Label,
    Message,
    User,
)
from ...schemas import (
    ConversationUpdate,
    LabelAssignment,
    ParticipantCreate,
    clamp_page,
    page_meta,
)
from ...serializers import serialize_conversation, serialize_message, serialize_user
from ...services import conversations as conv_service

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)

PRIORITY_ORDER = {
    ConversationPriority.URGENT.value: 0,
    ConversationPriority.HIGH.value: 1,
    ConversationPriority.MEDIUM.value: 2,
    ConversationPriority.LOW.value: 3,
    ConversationPriority.NONE.value: 4,
}


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def _base_conditions(
    *,
    status_filter: str | None,
    inbox_id: int | None,
    labels: str | None,
    priority: str | None,
    q: str | None,
) -> list[ColumnElement[bool]]:
    """Build every WHERE clause except the assignee scope (needed for counts)."""
    conditions: list[ColumnElement[bool]] = []

    if status_filter and status_filter != "all":
        conditions.append(Conversation.status == status_filter)
    if inbox_id:
        conditions.append(Conversation.inbox_id == inbox_id)
    if priority and priority != "all":
        conditions.append(Conversation.priority == priority)

    titles = [t.strip() for t in (labels or "").split(",") if t.strip()]
    if titles:
        conditions.append(
            Conversation.id.in_(
                select(ConversationLabel.conversation_id)
                .join(Label, Label.id == ConversationLabel.label_id)
                .where(Label.title.in_(titles))
            )
        )

    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        conditions.append(
            or_(
                Conversation.contact_id.in_(
                    select(Contact.id).where(
                        or_(
                            Contact.name.ilike(like),
                            Contact.email.ilike(like),
                            Contact.phone.ilike(like),
                            Contact.identifier.ilike(like),
                        )
                    )
                ),
                Conversation.id.in_(
                    select(Message.conversation_id).where(Message.content.ilike(like))
                ),
            )
        )
    return conditions


def _assignee_condition(assignee: str | None, user: User) -> ColumnElement[bool] | None:
    value = (assignee or "all").strip()
    if value in ("", "all"):
        return None
    if value == "me":
        return Conversation.assignee_id == user.id
    if value == "unassigned":
        return Conversation.assignee_id.is_(None)
    if value.isdigit():
        return Conversation.assignee_id == int(value)
    return None


def _sorted(stmt: Select, sort: str | None) -> Select:
    if sort == "oldest":
        return stmt.order_by(Conversation.last_activity_at.asc())
    if sort == "priority":
        ordering = case(PRIORITY_ORDER, value=Conversation.priority, else_=9)
        return stmt.order_by(ordering.asc(), desc(Conversation.last_activity_at))
    return stmt.order_by(desc(Conversation.last_activity_at))


async def _last_messages(db: DbSession, conversation_ids: list[int]) -> dict[int, Message]:
    """Fetch the newest non-deleted message of each conversation in one query."""
    if not conversation_ids:
        return {}
    newest = (
        select(func.max(Message.id))
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.deleted_at.is_(None),
        )
        .group_by(Message.conversation_id)
    )
    messages = (await db.scalars(select(Message).where(Message.id.in_(newest)))).all()
    return {m.conversation_id: m for m in messages}


async def _senders(db: DbSession, messages: list[Message]) -> dict[int, User]:
    ids = {m.sender_id for m in messages if m.sender_type == "user" and m.sender_id}
    if not ids:
        return {}
    users = (await db.scalars(select(User).where(User.id.in_(ids)))).all()
    return {u.id: u for u in users}


@router.get("")
async def list_conversations(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    inbox_id: int | None = None,
    assignee: str | None = None,
    labels: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    sort: str = "latest",
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """Filtered, paginated conversation list with sidebar counters."""
    page, per_page = clamp_page(page, per_page)
    conditions = _base_conditions(
        status_filter=status_filter,
        inbox_id=inbox_id,
        labels=labels,
        priority=priority,
        q=q,
    )
    scope = _assignee_condition(assignee, user)

    stmt = select(Conversation).where(*conditions)
    if scope is not None:
        stmt = stmt.where(scope)
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(*conditions, *( [scope] if scope is not None else [] ))
        )
        or 0
    )

    stmt = _sorted(stmt, sort).limit(per_page).offset((page - 1) * per_page)
    rows = (await db.scalars(stmt)).unique().all()

    last_messages = await _last_messages(db, [c.id for c in rows])
    senders = await _senders(db, list(last_messages.values()))

    counts_row = (
        await db.execute(
            select(
                func.count(Conversation.id),
                func.sum(case((Conversation.assignee_id == user.id, 1), else_=0)),
                func.sum(case((Conversation.assignee_id.is_(None), 1), else_=0)),
            ).where(*conditions)
        )
    ).one()

    data = []
    for conversation in rows:
        last = last_messages.get(conversation.id)
        data.append(
            serialize_conversation(
                conversation,
                last_message=last,
                sender=senders.get(last.sender_id) if last and last.sender_id else None,
            )
        )

    return {
        "data": data,
        "meta": page_meta(
            total,
            page,
            per_page,
            counts={
                "all": int(counts_row[0] or 0),
                "mine": int(counts_row[1] or 0),
                "unassigned": int(counts_row[2] or 0),
            },
        ),
    }


# ---------------------------------------------------------------------------
# Detail & mutations
# ---------------------------------------------------------------------------
async def _get_conversation(db: DbSession, conversation_id: int) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: int, db: DbSession) -> dict:
    conversation = await _get_conversation(db, conversation_id)
    last = (await _last_messages(db, [conversation.id])).get(conversation.id)
    sender = (await _senders(db, [last])).get(last.sender_id) if last else None
    return serialize_conversation(conversation, last_message=last, sender=sender)


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: int, payload: ConversationUpdate, db: DbSession, user: CurrentUser
) -> dict:
    """Apply a partial update, routing status/assignee through the service layer."""
    conversation = await _get_conversation(db, conversation_id)
    data = payload.model_dump(exclude_unset=True)

    new_status = data.pop("status", None)
    snoozed_until = data.pop("snoozed_until", None)
    assignee_given = "assignee_id" in data
    assignee_id = data.pop("assignee_id", None)

    if data.get("priority") and data["priority"] not in {p.value for p in ConversationPriority}:
        raise HTTPException(status_code=422, detail="Unknown priority")

    for field, value in data.items():
        setattr(conversation, field, value)
    if snoozed_until is not None and new_status is None:
        conversation.snoozed_until = snoozed_until
    await db.flush()

    if assignee_given:
        assignee = await db.get(User, assignee_id) if assignee_id else None
        if assignee_id and not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
        await conv_service.assign(db, conversation, assignee, actor=user)

    if new_status:
        if new_status not in {s.value for s in ConversationStatus}:
            raise HTTPException(status_code=422, detail="Unknown status")
        await conv_service.set_status(
            db, conversation, new_status, actor=user, snoozed_until=snoozed_until
        )
    else:
        await conv_service.notify_conversation(db, conversation)

    await db.refresh(conversation)
    last = (await _last_messages(db, [conversation.id])).get(conversation.id)
    return serialize_conversation(conversation, last_message=last)


@router.post("/{conversation_id}/read")
async def mark_read(conversation_id: int, db: DbSession) -> dict:
    conversation = await _get_conversation(db, conversation_id)
    await conv_service.mark_read(db, conversation)
    return serialize_conversation(conversation)


@router.post("/{conversation_id}/typing")
async def typing(conversation_id: int, db: DbSession, user: CurrentUser) -> dict:
    """Relay an agent typing indicator upstream and to other agents."""
    conversation = await _get_conversation(db, conversation_id)
    await conv_service.send_typing_indicator(db, conversation)
    await bus.publish(
        bus.EVENT_CONVERSATION_TYPING,
        {"conversation_id": conversation.id, "typing": True, "actor": "user", "user_id": user.id},
    )
    return {"status": "ok"}


@router.put("/{conversation_id}/labels")
async def set_labels(
    conversation_id: int, payload: LabelAssignment, db: DbSession
) -> dict:
    """Replace the conversation labels, creating unknown titles on the fly."""
    conversation = await _get_conversation(db, conversation_id)
    titles = [t.strip() for t in payload.labels if t and t.strip()]

    label_ids: list[int] = []
    for title in dict.fromkeys(titles):
        label = await db.scalar(select(Label).where(Label.title == title))
        if not label:
            label = Label(title=title)
            db.add(label)
            await db.flush()
        label_ids.append(label.id)

    await db.execute(
        delete(ConversationLabel).where(
            ConversationLabel.conversation_id == conversation.id
        )
    )
    for label_id in label_ids:
        db.add(ConversationLabel(conversation_id=conversation.id, label_id=label_id))
    await db.flush()
    await db.refresh(conversation)

    await conv_service.notify_conversation(db, conversation)
    return serialize_conversation(conversation)


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------
@router.get("/{conversation_id}/participants")
async def list_participants(conversation_id: int, db: DbSession) -> list[dict]:
    await _get_conversation(db, conversation_id)
    rows = (
        await db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id
            )
        )
    ).unique().all()
    return [serialize_user(row.user) for row in rows if row.user]


@router.post("/{conversation_id}/participants", status_code=status.HTTP_201_CREATED)
async def add_participant(
    conversation_id: int, payload: ParticipantCreate, db: DbSession
) -> list[dict]:
    await _get_conversation(db, conversation_id)
    if not await db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    exists = await db.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == payload.user_id,
        )
    )
    if not exists:
        db.add(
            ConversationParticipant(
                conversation_id=conversation_id, user_id=payload.user_id
            )
        )
        await db.flush()
    return await list_participants(conversation_id, db)


@router.delete(
    "/{conversation_id}/participants/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_participant(conversation_id: int, user_id: int, db: DbSession) -> None:
    await db.execute(
        delete(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id,
        )
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    db: DbSession,
    before_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return a page of messages, oldest first, ending just before ``before_id``."""
    await _get_conversation(db, conversation_id)
    limit = min(max(1, limit), 200)
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if before_id:
        stmt = stmt.where(Message.id < before_id)
    rows = (
        await db.scalars(stmt.order_by(desc(Message.id)).limit(limit))
    ).unique().all()
    return [serialize_message(m) for m in reversed(rows)]


def _attachment_type(mime: str, filename: str, is_voice: bool) -> str:
    """Map an upload's mime type onto the internal attachment taxonomy."""
    mime = (mime or "").lower()
    if mime.startswith("image/"):
        return AttachmentType.IMAGE.value
    if mime == "audio/ogg" and filename.lower().endswith(".ogg") and is_voice:
        return AttachmentType.VOICE.value
    if mime.startswith("audio/"):
        return AttachmentType.AUDIO.value
    if mime.startswith("video/"):
        return AttachmentType.VIDEO.value
    return AttachmentType.FILE.value


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def create_message(
    conversation_id: int,
    db: DbSession,
    user: CurrentUser,
    content: str | None = Form(default=None),
    private: bool = Form(default=False),
    reply_to_message_id: int | None = Form(default=None),
    content_type: str = Form(default="text"),
    is_voice: bool = Form(default=False),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """Post an agent reply or a private note, with optional file attachments."""
    conversation = await _get_conversation(db, conversation_id)

    uploads = [f for f in files if f and f.filename]
    if not (content or "").strip() and not uploads:
        raise HTTPException(status_code=422, detail="Message is empty")

    attachments: list[Attachment] = []
    for upload in uploads:
        data = await upload.read()
        if len(data) > settings.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail=f"'{upload.filename}' exceeds the {settings.max_upload_size} byte limit",
            )
        mime = upload.content_type or storage.guess_mime(upload.filename)
        key = storage.build_key(conversation.inbox_id, upload.filename)
        storage.save_bytes(key, data)
        attachment = Attachment(
            file_type=_attachment_type(mime, upload.filename, is_voice),
            file_name=upload.filename,
            file_size=len(data),
            mime_type=mime,
            storage_key=key,
            meta={},
        )
        db.add(attachment)
        attachments.append(attachment)
    if attachments:
        await db.flush()

    message = await conv_service.create_outgoing_message(
        db,
        conversation,
        content=content,
        user=user,
        private=private,
        attachments=attachments,
        reply_to_message_id=reply_to_message_id,
        content_type=content_type,
    )
    return serialize_message(message)
