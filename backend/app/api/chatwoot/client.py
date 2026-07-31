"""Chatwoot **Client (Public) API** — ``/public/api/v1/inboxes/…``.

Mounted on the exact paths Chatwoot uses so an SDK or widget written against a
real Chatwoot instance works unmodified.

Identity model (``Public::Api::V1::InboxesController``):

* ``{inbox_identifier}`` is ``channel_api.identifier`` — our
  ``inbox.config["inbox_identifier"]``;
* ``{contact_identifier}`` is the **ContactInbox ``source_id``**, not the
  contact id and not ``contact.identifier``. It is a bearer credential:
  whoever holds it acts as that contact;
* ``{conversation_id}`` is the conversation's display id (our PK).

There is no token anywhere. Optional HMAC identity validation uses the channel's
``hmac_token`` over ``params[:identifier]`` and is *mandatory* when the inbox
sets ``hmac_mandatory``.

Everything that writes goes through :mod:`app.services.conversations`, so an
inbound message here is indistinguishable downstream from one that arrived over
Telegram: automations run, realtime events fire, native webhooks are delivered.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy import desc, select
from starlette.datastructures import UploadFile

from ...channels.api_channel import ApiChannel
from ...channels.base import (
    InboundEvent,
    NormalizedAttachment,
    NormalizedContact,
    NormalizedMessage,
    build_channel,
)
from ...compat import chatwoot
from ...core import events as bus
from ...core.deps import DbSession
from ...db import utcnow
from ...models import (
    AttachmentType,
    Contact,
    ContactInbox,
    Conversation,
    ConversationStatus,
    Inbox,
    Message,
    MessageType,
    SenderType,
    User,
)
from ...services import conversations as conv_service
from . import (
    ChatwootError,
    ChatwootRoute,
    conversation_uuid,
    not_found,
    read_params,
    unauthorized,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/api/v1",
    tags=["chatwoot-client"],
    route_class=ChatwootRoute,
)

#: Attachment MIME prefix -> our ``AttachmentType`` (Chatwoot's ``file_type``
#: helper does the same job from the uploaded part's content type).
_FILE_TYPE_BY_PREFIX = {
    "image/": AttachmentType.IMAGE.value,
    "audio/": AttachmentType.AUDIO.value,
    "video/": AttachmentType.VIDEO.value,
}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
async def _find_inbox(db: DbSession, inbox_identifier: str) -> Inbox:
    """``Channel::Api.find_by!(identifier: params[:inbox_id])``.

    The identifier lives inside the JSON config column, so the (small) set of
    API inboxes is scanned in Python rather than with a portability-hostile
    JSON path expression.
    """
    rows = await db.scalars(
        select(Inbox).where(Inbox.channel_type == ApiChannel.key)
    )
    for inbox in rows:
        if (inbox.config or {}).get("inbox_identifier") == inbox_identifier:
            return inbox
    raise not_found()


async def _find_link(db: DbSession, inbox: Inbox, source_id: str) -> ContactInbox:
    link = await db.scalar(
        select(ContactInbox).where(
            ContactInbox.inbox_id == inbox.id, ContactInbox.source_id == source_id
        )
    )
    if link is None:
        raise not_found()
    return link


async def _find_conversation(
    db: DbSession, inbox: Inbox, link: ContactInbox, conversation_id: int
) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.inbox_id != inbox.id
        or conversation.contact_id != link.contact_id
    ):
        raise not_found()
    return conversation


def _verify_hmac(inbox: Inbox, params: dict[str, Any], link: ContactInbox | None) -> None:
    """``process_hmac`` — HMAC-SHA256(hmac_token, identifier), hex, no prefix.

    Chatwoot raises a bare ``StandardError`` here, which escapes its rescue list
    and surfaces as a 500. We answer ``401`` instead: a failed credential check
    is not a server fault, and no Chatwoot client depends on the 500.
    """
    config = inbox.config or {}
    provided = str(params.get("identifier_hash") or "")
    if not provided and not config.get("hmac_mandatory"):
        return

    expected = hmac.new(
        str(config.get("hmac_token") or "").encode("utf-8"),
        str(params.get("identifier") or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise unauthorized("HMAC failed: Invalid Identifier Hash Provided")
    if link is not None:
        link.meta = {**(link.meta or {}), "hmac_verified": True}


def _pubsub_token(link: ContactInbox) -> str:
    """Realtime subscription token. Minted once and kept on the link row."""
    meta = dict(link.meta or {})
    token = meta.get("pubsub_token")
    if not token:
        token = secrets.token_urlsafe(24)
        meta["pubsub_token"] = token
        link.meta = meta
    return token


# ---------------------------------------------------------------------------
# Serialisers — ``app/views/public/api/v1/models/*``
# ---------------------------------------------------------------------------
def _contact_body(contact: Contact) -> dict[str, Any]:
    """``public/api/v1/models/_contact`` — four fields, nothing more."""
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "phone_number": contact.phone,
    }


async def _sender_of(
    db: DbSession, message: Message, contact: Contact | None
) -> Contact | User | None:
    """Resolve the polymorphic sender so the payload keeps its ``sender`` key."""
    if message.sender_id is None:
        return None
    if message.sender_type == SenderType.CONTACT.value:
        if contact is not None and contact.id == message.sender_id:
            return contact
        return await db.get(Contact, message.sender_id)
    if message.sender_type == SenderType.USER.value:
        return await db.get(User, message.sender_id)
    return None


async def _message_body(
    db: DbSession,
    message: Message,
    conversation: Conversation,
    contact: Contact | None = None,
) -> dict[str, Any]:
    """``public/api/v1/models/_message``.

    Built from the compat layer's push representation, so ``message_type`` is
    the **integer** and ``created_at`` epoch seconds — the two places where the
    REST shape differs from the webhook shape.
    """
    push = chatwoot.serialize_message(
        message,
        push=True,
        conversation=conversation,
        sender=await _sender_of(db, message, contact),
    )
    body = {
        "id": push["id"],
        "content": push["content"],
        "message_type": push["message_type"],
        "content_type": push["content_type"],
        "content_attributes": push["content_attributes"],
        "created_at": push["created_at"],
        "conversation_id": push["conversation_id"],
    }
    # Omitted entirely when empty — never [] and never null.
    if "attachments" in push:
        body["attachments"] = push["attachments"]
    if "sender" in push:
        body["sender"] = push["sender"]
    return body


async def _conversation_body(
    db: DbSession, conversation: Conversation, messages: list[Message], contact: Contact
) -> dict[str, Any]:
    """``public/api/v1/models/_conversation``.

    ``contact`` is the raw record in Chatwoot (a jbuilder quirk that leaks every
    column); we publish the full compat contact instead, which carries the same
    information without exposing internals we do not model.
    """
    return {
        "id": chatwoot.conversation_display_id(conversation),
        "uuid": conversation_uuid(conversation.id),
        "inbox_id": conversation.inbox_id,
        "contact_last_seen_at": chatwoot.epoch(conversation.contact_last_seen_at),
        "status": conversation.status,
        "agent_last_seen_at": chatwoot.epoch(conversation.agent_last_seen_at),
        "messages": [
            await _message_body(db, m, conversation, contact) for m in messages
        ],
        "contact": chatwoot.serialize_contact(contact, push=True),
    }


async def _chat_messages(db: DbSession, conversation: Conversation) -> list[Message]:
    """Chatwoot's ``chat`` scope: no activity messages, no private notes."""
    rows = await db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.message_type != MessageType.ACTIVITY.value,
            Message.private.is_(False),
            Message.deleted_at.is_(None),
        )
        .order_by(Message.id)
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------
@router.get("/inboxes/{inbox_identifier}")
async def show_inbox(inbox_identifier: str, db: DbSession) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    config = inbox.config or {}
    return {
        "identifier": config.get("inbox_identifier"),
        "identity_validation_enabled": bool(config.get("hmac_mandatory")),
        "name": inbox.name,
        "timezone": "UTC",
        "working_hours": inbox.working_hours or [],
        "working_hours_enabled": bool(inbox.working_hours),
        "csat_survey_enabled": inbox.csat_enabled,
        "greeting_enabled": inbox.greeting_enabled,
    }


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
async def _resolve_contact(
    db: DbSession, inbox: Inbox, source_id: str, params: dict[str, Any]
) -> tuple[Contact, ContactInbox]:
    """``ContactInboxWithContactBuilder``: source_id, then identifier/email/phone."""
    link = await db.scalar(
        select(ContactInbox).where(
            ContactInbox.inbox_id == inbox.id, ContactInbox.source_id == source_id
        )
    )
    if link is not None:
        contact = await db.get(Contact, link.contact_id)
        assert contact is not None
        return contact, link

    contact = None
    for column, value in (
        (Contact.identifier, params.get("identifier")),
        (Contact.email, params.get("email")),
        (Contact.phone, params.get("phone_number")),
    ):
        if value:
            contact = await db.scalar(select(Contact).where(column == str(value)))
            if contact is not None:
                break

    if contact is None:
        # Creation goes through the service so avatars and contact events are
        # handled exactly as they are for a provider-driven contact.
        channel = build_channel(inbox)
        try:
            contact, link = await conv_service.find_or_create_contact(
                db,
                inbox,
                NormalizedContact(
                    source_id=source_id,
                    name=str(params.get("name") or ""),
                    email=params.get("email"),
                    phone=params.get("phone_number"),
                    avatar_url=params.get("avatar_url"),
                ),
                channel,
            )
        finally:
            await channel.close()
        return contact, link

    link = ContactInbox(contact_id=contact.id, inbox_id=inbox.id, source_id=source_id, meta={})
    db.add(link)
    await db.flush()
    return contact, link


def _apply_contact_params(contact: Contact, params: dict[str, Any]) -> bool:
    changed = False
    for attribute, key in (
        ("name", "name"),
        ("email", "email"),
        ("phone", "phone_number"),
        ("avatar_url", "avatar_url"),
        ("identifier", "identifier"),
    ):
        value = params.get(key)
        if value and getattr(contact, attribute) != value:
            setattr(contact, attribute, value)
            changed = True
    custom = params.get("custom_attributes")
    if isinstance(custom, dict) and custom:
        contact.custom_attributes = {**(contact.custom_attributes or {}), **custom}
        changed = True
    return changed


@router.post("/inboxes/{inbox_identifier}/contacts")
async def create_contact(
    inbox_identifier: str, request: Request, db: DbSession
) -> dict[str, Any]:
    """Chatwoot answers **200**, not 201, on every public create."""
    inbox = await _find_inbox(db, inbox_identifier)
    params = await read_params(request)
    _verify_hmac(inbox, params, None)

    source_id = str(params.get("source_id") or uuid.uuid4())
    contact, link = await _resolve_contact(db, inbox, source_id, params)
    if _apply_contact_params(contact, params):
        await db.flush()
        await bus.publish(
            bus.EVENT_CONTACT_UPDATED, {"contact": {"id": contact.id}}
        )

    token = _pubsub_token(link)
    await db.flush()
    return {"source_id": link.source_id, "pubsub_token": token, **_contact_body(contact)}


@router.get("/inboxes/{inbox_identifier}/contacts/{contact_identifier}")
async def show_contact(
    inbox_identifier: str, contact_identifier: str, request: Request, db: DbSession
) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    _verify_hmac(inbox, dict(request.query_params), link)
    contact = await db.get(Contact, link.contact_id)
    assert contact is not None
    return {
        "source_id": link.source_id,
        "pubsub_token": _pubsub_token(link),
        **_contact_body(contact),
    }


@router.patch("/inboxes/{inbox_identifier}/contacts/{contact_identifier}")
async def update_contact(
    inbox_identifier: str, contact_identifier: str, request: Request, db: DbSession
) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    params = await read_params(request)
    _verify_hmac(inbox, params, link)

    contact = await db.get(Contact, link.contact_id)
    assert contact is not None
    # ``identifier`` cannot be changed through the public update.
    params.pop("identifier", None)
    if _apply_contact_params(contact, params):
        await db.flush()
        await bus.publish(bus.EVENT_CONTACT_UPDATED, {"contact": {"id": contact.id}})
    return {
        "source_id": link.source_id,
        "pubsub_token": _pubsub_token(link),
        **_contact_body(contact),
    }


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
@router.get("/inboxes/{inbox_identifier}/contacts/{contact_identifier}/conversations")
async def list_conversations(
    inbox_identifier: str, contact_identifier: str, db: DbSession
) -> list[dict[str, Any]]:
    """A bare JSON array — this endpoint has no ``payload`` envelope."""
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    contact = await db.get(Contact, link.contact_id)
    assert contact is not None

    rows = await db.scalars(
        select(Conversation)
        .where(
            Conversation.inbox_id == inbox.id, Conversation.contact_id == link.contact_id
        )
        .order_by(Conversation.id)
    )
    return [
        await _conversation_body(db, c, await _chat_messages(db, c), contact)
        for c in rows
    ]


@router.post("/inboxes/{inbox_identifier}/contacts/{contact_identifier}/conversations")
async def create_conversation(
    inbox_identifier: str, contact_identifier: str, request: Request, db: DbSession
) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    contact = await db.get(Contact, link.contact_id)
    assert contact is not None
    params = await read_params(request)

    conversation, created = await conv_service.find_or_create_conversation(
        db, inbox, contact, link
    )
    custom = params.get("custom_attributes")
    if isinstance(custom, dict) and custom:
        conversation.custom_attributes = {
            **(conversation.custom_attributes or {}),
            **custom,
        }
    await db.flush()
    await conv_service.notify_conversation(
        db,
        conversation,
        bus.EVENT_CONVERSATION_CREATED if created else bus.EVENT_CONVERSATION_UPDATED,
    )
    return await _conversation_body(
        db, conversation, await _chat_messages(db, conversation), contact
    )


@router.get(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}/conversations/{conversation_id}"
)
async def show_conversation(
    inbox_identifier: str, contact_identifier: str, conversation_id: int, db: DbSession
) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)
    contact = await db.get(Contact, link.contact_id)
    assert contact is not None
    return await _conversation_body(
        db, conversation, await _chat_messages(db, conversation), contact
    )


@router.post(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/toggle_status"
)
async def toggle_status(
    inbox_identifier: str, contact_identifier: str, conversation_id: int, db: DbSession
) -> dict[str, Any]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)
    target = (
        ConversationStatus.OPEN.value
        if conversation.status == ConversationStatus.RESOLVED.value
        else ConversationStatus.RESOLVED.value
    )
    await conv_service.set_status(db, conversation, target)
    contact = await db.get(Contact, link.contact_id)
    assert contact is not None
    return await _conversation_body(
        db, conversation, await _chat_messages(db, conversation), contact
    )


@router.post(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/toggle_typing"
)
async def toggle_typing(
    inbox_identifier: str,
    contact_identifier: str,
    conversation_id: int,
    request: Request,
    db: DbSession,
) -> Response:
    """``head :ok`` — 200 with an empty body."""
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)
    params = await read_params(request)
    await bus.publish(
        bus.EVENT_CONVERSATION_TYPING,
        {
            "conversation_id": conversation.id,
            "typing": str(params.get("typing_status", "on")).lower() != "off",
            "actor": "contact",
        },
    )
    return Response(status_code=200)


@router.post(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/update_last_seen"
)
async def update_last_seen(
    inbox_identifier: str, contact_identifier: str, conversation_id: int, db: DbSession
) -> Response:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)
    conversation.contact_last_seen_at = utcnow()
    await db.flush()
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@router.get(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/messages"
)
async def list_messages(
    inbox_identifier: str,
    contact_identifier: str,
    conversation_id: int,
    db: DbSession,
    before: int | None = None,
) -> list[dict[str, Any]]:
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)

    query = select(Message).where(
        Message.conversation_id == conversation.id,
        Message.message_type != MessageType.ACTIVITY.value,
        Message.private.is_(False),
        Message.deleted_at.is_(None),
    )
    if before is not None:
        query = query.where(Message.id < before)
    rows = list(await db.scalars(query.order_by(desc(Message.id)).limit(20)))
    contact = await db.get(Contact, link.contact_id)
    return [
        await _message_body(db, m, conversation, contact) for m in reversed(rows)
    ]


#: ``You cannot update the CSAT survey after 14 days``.
CSAT_WINDOW_DAYS = 14


@router.patch(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/messages/{message_id}"
)
async def update_message(
    inbox_identifier: str,
    contact_identifier: str,
    conversation_id: int,
    message_id: int,
    request: Request,
    db: DbSession,
) -> dict[str, Any]:
    """CSAT only — the sole field Chatwoot permits here is ``submitted_values``."""
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)

    message = await db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise not_found()

    created = message.created_at
    if created is not None:
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if utcnow() - created > timedelta(days=CSAT_WINDOW_DAYS):
            raise ChatwootError(
                422, {"error": "You cannot update the CSAT survey after 14 days"}
            )

    params = await read_params(request)
    submitted = params.get("submitted_values")
    if submitted is not None:
        message.content_attributes = {
            **(message.content_attributes or {}),
            "submitted_values": submitted,
        }
        await db.flush()
        await db.refresh(message)
        await bus.publish(
            bus.EVENT_MESSAGE_UPDATED,
            {"message": {"id": message.id}, "conversation_id": conversation.id},
        )
    return await _message_body(
        db, message, conversation, await db.get(Contact, link.contact_id)
    )


def _normalize_attachments(params: dict[str, Any]) -> list[NormalizedAttachment]:
    raw = params.get("attachments")
    if raw is None:
        return []
    uploads = raw if isinstance(raw, list) else [raw]
    normalised: list[NormalizedAttachment] = []
    for upload in uploads:
        if not isinstance(upload, UploadFile):
            continue
        content_type = upload.content_type or ""
        file_type = next(
            (
                value
                for prefix, value in _FILE_TYPE_BY_PREFIX.items()
                if content_type.startswith(prefix)
            ),
            AttachmentType.FILE.value,
        )
        normalised.append(
            NormalizedAttachment(
                file_type=file_type,
                file_name=upload.filename,
                mime_type=content_type or None,
                data=upload.file.read(),
            )
        )
    return normalised


@router.post(
    "/inboxes/{inbox_identifier}/contacts/{contact_identifier}"
    "/conversations/{conversation_id}/messages"
)
async def create_message(
    inbox_identifier: str,
    contact_identifier: str,
    conversation_id: int,
    request: Request,
    db: DbSession,
) -> dict[str, Any]:
    """Only ``content``, ``echo_id`` and ``attachments`` are accepted.

    ``message_type`` is hard-coded incoming and the sender is forced to the
    contact — exactly like Chatwoot. The write is funnelled through
    ``process_inbound_event`` so it is indistinguishable from a provider
    delivered message downstream.
    """
    inbox = await _find_inbox(db, inbox_identifier)
    link = await _find_link(db, inbox, contact_identifier)
    conversation = await _find_conversation(db, inbox, link, conversation_id)
    params = await read_params(request)

    attributes: dict[str, Any] = {}
    if params.get("echo_id"):
        attributes["echo_id"] = params["echo_id"]

    channel = build_channel(inbox)
    try:
        message = await conv_service.process_inbound_event(
            db,
            inbox,
            channel,
            InboundEvent(
                kind="message",
                chat_source_id=link.source_id,
                contact=NormalizedContact(source_id=link.source_id),
                message=NormalizedMessage(
                    content=params.get("content"),
                    attachments=_normalize_attachments(params),
                    attributes=attributes,
                ),
            ),
            # The URL names the conversation; without this the message would be
            # filed under the contact's most recently active thread instead.
            conversation=conversation,
        )
    finally:
        await channel.close()

    if message is None:
        raise ChatwootError(422, {"message": "Message could not be created"})
    return await _message_body(
        db, message, conversation, await db.get(Contact, link.contact_id)
    )
