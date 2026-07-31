"""Contacts, their notes, conversations and the block list."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, or_, select

from ...core import events as bus
from ...core.deps import CurrentUser, DbSession, get_current_user
from ...models import Contact, ContactNote, Conversation, Message
from ...schemas import (
    BlockRequest,
    ContactCreate,
    ContactNoteCreate,
    ContactUpdate,
    clamp_page,
    page_meta,
)
from ...serializers import (
    serialize_contact,
    serialize_contact_note,
    serialize_conversation,
)

router = APIRouter(
    prefix="/contacts", tags=["contacts"], dependencies=[Depends(get_current_user)]
)


async def _get_contact(db: DbSession, contact_id: int) -> Contact:
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


async def _publish(contact: Contact) -> None:
    await bus.publish(bus.EVENT_CONTACT_UPDATED, {"contact": serialize_contact(contact)})


@router.get("")
async def list_contacts(
    db: DbSession,
    q: str | None = None,
    page: int = 1,
    per_page: int = 25,
    sort: str = "recent",
) -> dict[str, Any]:
    page, per_page = clamp_page(page, per_page)
    conditions = []
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        conditions.append(
            or_(
                Contact.name.ilike(like),
                Contact.email.ilike(like),
                Contact.phone.ilike(like),
                Contact.identifier.ilike(like),
                Contact.company.ilike(like),
            )
        )

    total = int(
        await db.scalar(select(func.count()).select_from(Contact).where(*conditions)) or 0
    )
    stmt = select(Contact).where(*conditions)
    if sort == "name":
        stmt = stmt.order_by(Contact.name.asc())
    elif sort == "oldest":
        stmt = stmt.order_by(Contact.created_at.asc())
    else:
        stmt = stmt.order_by(desc(Contact.last_activity_at), desc(Contact.id))
    stmt = stmt.limit(per_page).offset((page - 1) * per_page)

    rows = (await db.scalars(stmt)).all()
    return {
        "data": [serialize_contact(c) for c in rows],
        "meta": page_meta(total, page, per_page),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_contact(payload: ContactCreate, db: DbSession) -> dict:
    contact = Contact(**payload.model_dump())
    db.add(contact)
    await db.flush()
    await _publish(contact)
    return serialize_contact(contact)


@router.get("/{contact_id}")
async def get_contact(contact_id: int, db: DbSession) -> dict:
    return serialize_contact(await _get_contact(db, contact_id))


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: int, payload: ContactUpdate, db: DbSession
) -> dict:
    contact = await _get_contact(db, contact_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.flush()
    await _publish(contact)
    return serialize_contact(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: int, db: DbSession) -> None:
    contact = await _get_contact(db, contact_id)
    await db.delete(contact)
    await db.flush()


@router.get("/{contact_id}/conversations")
async def contact_conversations(contact_id: int, db: DbSession) -> list[dict]:
    await _get_contact(db, contact_id)
    rows = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.contact_id == contact_id)
            .order_by(desc(Conversation.last_activity_at))
        )
    ).unique().all()

    result = []
    for conversation in rows:
        last = await db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id, Message.deleted_at.is_(None)
            )
            .order_by(desc(Message.id))
            .limit(1)
        )
        result.append(serialize_conversation(conversation, last_message=last))
    return result


@router.get("/{contact_id}/notes")
async def list_notes(contact_id: int, db: DbSession) -> list[dict]:
    await _get_contact(db, contact_id)
    rows = (
        await db.scalars(
            select(ContactNote)
            .where(ContactNote.contact_id == contact_id)
            .order_by(desc(ContactNote.id))
        )
    ).all()
    return [serialize_contact_note(n) for n in rows]


@router.post("/{contact_id}/notes", status_code=status.HTTP_201_CREATED)
async def create_note(
    contact_id: int, payload: ContactNoteCreate, db: DbSession, user: CurrentUser
) -> dict:
    await _get_contact(db, contact_id)
    note = ContactNote(contact_id=contact_id, user_id=user.id, content=payload.content)
    db.add(note)
    await db.flush()
    return serialize_contact_note(note)


@router.delete(
    "/{contact_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_note(contact_id: int, note_id: int, db: DbSession) -> None:
    note = await db.get(ContactNote, note_id)
    if not note or note.contact_id != contact_id:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.flush()


@router.post("/{contact_id}/block")
async def block_contact(
    contact_id: int, payload: BlockRequest, db: DbSession
) -> dict:
    contact = await _get_contact(db, contact_id)
    contact.blocked = payload.blocked
    await db.flush()
    await _publish(contact)
    return serialize_contact(contact)
