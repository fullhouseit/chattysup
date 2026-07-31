"""Chatwoot **Application API** subset — ``/api/v1/accounts/{account_id}/…``.

Authenticated with Chatwoot's raw ``api_access_token`` header (no ``Bearer``
prefix); our own ``Authorization: Bearer`` / ``X-Api-Key`` schemes are accepted
too, so one credential works against both surfaces. Tokens resolve through the
existing :class:`~app.models.system.ApiToken` model.

ChattySup is single tenant, so ``{account_id}`` is accepted and echoed but never
used to scope a query — hard-coding ``1``, as most Chatwoot clients do, works.

Path safety: our native API lives at ``/api/v1/<resource>`` and this router only
ever claims ``/api/v1/accounts/…``. ``accounts`` is not a native resource, and
the native routers are mounted first, so nothing here can shadow them.

Response shapes come from the jbuilder templates, which differ from the webhook
payloads in ways clients depend on — ``message_type`` is an **integer** here and
``created_at`` epoch seconds — so every body is rendered from the compat layer's
``push=True`` representation.
"""
from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...channels.api_channel import ApiChannel, use_session
from ...channels.base import (
    InboundEvent,
    NormalizedContact,
    NormalizedMessage,
    build_channel,
)
from ...compat import chatwoot
from ...core import events as bus
from ...core.deps import resolve_user
from ...db import get_db, utcnow
from ...models import (
    Contact,
    ContactInbox,
    Conversation,
    ConversationStatus,
    Inbox,
    Message,
    MessageStatus,
    MessageType,
    SenderType,
    Team,
    User,
    Webhook,
)
from ...services import conversations as conv_service
from . import (
    ChatwootRoute,
    conversation_uuid,
    forbidden,
    invalid,
    not_found,
    parameter_missing,
    read_params,
    unauthorized,
)

logger = logging.getLogger(__name__)

RESULTS_PER_PAGE = 15


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def _token(request: Request) -> str | None:
    """Chatwoot's header first, then the schemes our native API already uses."""
    token = request.headers.get("api_access_token")
    if token:
        return token.strip()
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    api_key = request.headers.get("X-Api-Key")
    return api_key.strip() if api_key else None


async def current_api_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    user = await resolve_user(db, _token(request))
    if user is None:
        raise unauthorized()
    return user


CurrentApiUser = Annotated[User, Depends(current_api_user)]
Db = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(
    prefix="/api/v1/accounts/{account_id}",
    tags=["chatwoot-application"],
    route_class=ChatwootRoute,
)


# ---------------------------------------------------------------------------
# Serialisers — ``app/views/api/v1/**``
# ---------------------------------------------------------------------------
def _agent_body(user: User | None) -> dict[str, Any] | None:
    """``api/v1/models/_agent``."""
    if user is None:
        return None
    return {
        "id": user.id,
        "account_id": chatwoot.CHATWOOT_ACCOUNT_ID,
        "availability_status": user.availability,
        "auto_offline": True,
        "confirmed": True,
        "email": user.email,
        "provider": user.provider,
        "available_name": user.display_name or user.name,
        "custom_attributes": {},
        "name": user.name,
        "role": user.role,
        "thumbnail": user.avatar_url or "",
    }


def _contact_body(
    contact: Contact, *, contact_inboxes: list[tuple[ContactInbox, Inbox]] | None = None
) -> dict[str, Any]:
    """``api/v1/models/_contact`` — built on the compat push representation."""
    push = chatwoot.serialize_contact(contact, push=True) or {}
    body: dict[str, Any] = {
        "additional_attributes": push["additional_attributes"],
        "availability_status": "online" if contact.last_activity_at else "offline",
        "email": push["email"],
        "id": push["id"],
        "name": push["name"],
        "phone_number": push["phone_number"],
        "blocked": push["blocked"],
        "identifier": push["identifier"],
        "thumbnail": push["thumbnail"],
        "custom_attributes": push["custom_attributes"],
    }
    # Conditionally emitted, never null.
    if contact.last_activity_at is not None:
        body["last_activity_at"] = chatwoot.epoch(contact.last_activity_at)
    if contact.created_at is not None:
        body["created_at"] = chatwoot.epoch(contact.created_at)
    if contact_inboxes is not None:
        body["contact_inboxes"] = [
            {"source_id": link.source_id, "inbox": _inbox_body(inbox)}
            for link, inbox in contact_inboxes
        ]
    return body


def _inbox_body(inbox: Inbox) -> dict[str, Any]:
    """``api/v1/models/_inbox``, including the API channel block."""
    presenter = chatwoot.serialize_inbox(inbox, full=True) or {}
    config = inbox.config or {}
    body: dict[str, Any] = {
        "id": inbox.id,
        "avatar_url": inbox.avatar_url or "",
        "channel_id": inbox.id,
        "name": inbox.name,
        "channel_type": chatwoot.CHANNEL_CLASS.get(
            inbox.channel_type, chatwoot.DEFAULT_CHANNEL_CLASS
        ),
        "greeting_enabled": presenter["greeting_enabled"],
        "greeting_message": presenter["greeting_message"],
        "working_hours_enabled": presenter["working_hours_enabled"],
        "enable_email_collect": presenter["enable_email_collect"],
        "csat_survey_enabled": presenter["csat_survey_enabled"],
        "csat_config": {},
        "enable_auto_assignment": presenter["enable_auto_assignment"],
        "auto_assignment_config": presenter["auto_assignment_config"],
        "out_of_office_message": presenter["out_of_office_message"],
        "working_hours": presenter["working_hours"],
        "timezone": presenter["timezone"],
        "callback_webhook_url": None,
        "allow_messages_after_resolved": presenter["allow_messages_after_resolved"],
        "lock_to_single_conversation": presenter["lock_to_single_conversation"],
        "sender_name_type": presenter["sender_name_type"],
        "business_name": presenter["business_name"],
    }
    if inbox.channel_type == ApiChannel.key:
        additional: dict[str, Any] = {}
        if config.get("agent_reply_time_window") is not None:
            additional["agent_reply_time_window"] = config["agent_reply_time_window"]
        body.update(
            {
                "webhook_url": config.get("webhook_url"),
                "inbox_identifier": config.get("inbox_identifier"),
                "hmac_token": config.get("hmac_token"),
                # The key clients read to verify our outbound
                # ``X-Chatwoot-Signature``; Chatwoot emits it to administrators.
                "secret": config.get("secret"),
                "additional_attributes": additional,
            }
        )
    return body


async def _sender_of(
    db: AsyncSession, message: Message, contact: Contact | None
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
    db: AsyncSession, message: Message, conversation: Conversation
) -> dict[str, Any]:
    """``api/v1/models/_message`` — integer ``message_type``, epoch ``created_at``."""
    push = chatwoot.serialize_message(
        message,
        push=True,
        conversation=conversation,
        sender=await _sender_of(db, message, conversation.contact),
    )
    body: dict[str, Any] = {
        "id": push["id"],
        "content": push["content"],
        "inbox_id": push["inbox_id"],
        "conversation_id": push["conversation_id"],
        "message_type": push["message_type"],
        "content_type": push["content_type"],
        "status": push["status"],
        "content_attributes": push["content_attributes"],
        "created_at": push["created_at"],
        "private": push["private"],
        "source_id": push["source_id"],
    }
    echo_id = (message.content_attributes or {}).get("echo_id")
    if echo_id:
        body["echo_id"] = echo_id
    if "sender" in push:
        body["sender"] = push["sender"]
    if "attachments" in push:
        body["attachments"] = push["attachments"]
    return body


async def _last_message(
    db: AsyncSession, conversation_id: int, *, exclude_activity: bool
) -> Message | None:
    query = select(Message).where(
        Message.conversation_id == conversation_id, Message.deleted_at.is_(None)
    )
    if exclude_activity:
        query = query.where(Message.message_type != MessageType.ACTIVITY.value)
    return await db.scalar(query.order_by(desc(Message.id)).limit(1))


async def _conversation_body(
    db: AsyncSession, conversation: Conversation
) -> dict[str, Any]:
    """``api/v1/conversations/partials/_conversation``.

    Derived from the compat presenter, then reshaped to the REST partial:
    ``channel`` moves into ``meta``, ``contact_inbox``/``account`` drop out and
    ``uuid``/``account_id``/``muted``/``last_non_activity_message`` appear.
    """
    team = await db.get(Team, conversation.team_id) if conversation.team_id else None
    presenter = chatwoot.serialize_conversation(
        conversation, team=team, include_account=False
    )
    latest = await _last_message(db, conversation.id, exclude_activity=False)
    last_non_activity = await _last_message(db, conversation.id, exclude_activity=True)

    meta: dict[str, Any] = {
        "sender": _contact_body(conversation.contact),
        "channel": presenter["channel"],
        "hmac_verified": presenter["meta"]["hmac_verified"],
    }
    if conversation.assignee is not None:
        meta["assignee"] = _agent_body(conversation.assignee)
        meta["assignee_type"] = "User"
    if presenter["meta"]["team"] is not None:
        meta["team"] = presenter["meta"]["team"]

    return {
        "meta": meta,
        "id": presenter["id"],
        "messages": (
            [await _message_body(db, latest, conversation)]
            if latest is not None
            else []
        ),
        "account_id": chatwoot.CHATWOOT_ACCOUNT_ID,
        "uuid": conversation_uuid(conversation.id),
        "additional_attributes": presenter["additional_attributes"],
        "agent_last_seen_at": presenter["agent_last_seen_at"],
        "assignee_last_seen_at": presenter["agent_last_seen_at"],
        "can_reply": presenter["can_reply"],
        "contact_last_seen_at": presenter["contact_last_seen_at"],
        "custom_attributes": presenter["custom_attributes"],
        "inbox_id": presenter["inbox_id"],
        "labels": presenter["labels"],
        "muted": conversation.muted,
        "snoozed_until": presenter["snoozed_until"],
        "status": presenter["status"],
        "created_at": presenter["created_at"],
        "updated_at": presenter["updated_at"],
        "timestamp": presenter["timestamp"],
        # ``.to_i`` in the jbuilder, so 0 rather than null when never replied.
        "first_reply_created_at": chatwoot.epoch(conversation.first_reply_created_at),
        "unread_count": presenter["unread_count"],
        "last_non_activity_message": (
            await _message_body(db, last_non_activity, conversation)
            if last_non_activity is not None
            else None
        ),
        "last_activity_at": presenter["last_activity_at"],
        "priority": presenter["priority"],
        "waiting_since": presenter["waiting_since"],
        "sla_policy_id": None,
    }



# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
async def _get_conversation(db: AsyncSession, conversation_id: int) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise not_found()
    return conversation


@router.get("/conversations")
async def list_conversations(
    db: Db,
    user: CurrentApiUser,
    status: str | None = None,
    assignee_type: str = "all",
    page: int = 1,
) -> dict[str, Any]:
    query = select(Conversation)
    if status:
        query = query.where(Conversation.status == status)
    if assignee_type == "me":
        query = query.where(Conversation.assignee_id == user.id)
    elif assignee_type == "unassigned":
        query = query.where(Conversation.assignee_id.is_(None))

    rows = list(
        await db.scalars(
            query.order_by(desc(Conversation.last_activity_at))
            .limit(25)
            .offset(max(page - 1, 0) * 25)
        )
    )

    async def _count(*where: Any) -> int:
        return int(
            await db.scalar(select(func.count(Conversation.id)).where(*where)) or 0
        )

    return {
        "data": {
            "meta": {
                "mine_count": await _count(Conversation.assignee_id == user.id),
                "assigned_count": await _count(Conversation.assignee_id.isnot(None)),
                "unassigned_count": await _count(Conversation.assignee_id.is_(None)),
                "all_count": await _count(),
            },
            "payload": [await _conversation_body(db, c) for c in rows],
        }
    }


@router.get("/conversations/{conversation_id}")
async def show_conversation(
    conversation_id: int, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    return await _conversation_body(db, await _get_conversation(db, conversation_id))


@router.post("/conversations")
async def create_conversation(
    request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    params = await read_params(request)
    inbox_id = params.get("inbox_id")
    if inbox_id is None:
        raise parameter_missing("param is missing or the value is empty: inbox_id")
    inbox = await db.get(Inbox, int(inbox_id))
    if inbox is None:
        raise not_found()

    contact: Contact | None = None
    if params.get("contact_id") is not None:
        contact = await db.get(Contact, int(params["contact_id"]))
    source_id = params.get("source_id")

    link: ContactInbox | None = None
    if source_id:
        link = await db.scalar(
            select(ContactInbox).where(
                ContactInbox.inbox_id == inbox.id,
                ContactInbox.source_id == str(source_id),
            )
        )
        if link is not None and contact is not None and link.contact_id != contact.id:
            raise invalid("source_id should be unique")
    if link is None:
        if contact is None:
            raise parameter_missing("param is missing or the value is empty: contact_id")
        link = await db.scalar(
            select(ContactInbox).where(
                ContactInbox.inbox_id == inbox.id, ContactInbox.contact_id == contact.id
            )
        )
        if link is None:
            channel = build_channel(inbox)
            try:
                _, link = await conv_service.find_or_create_contact(
                    db,
                    inbox,
                    NormalizedContact(
                        source_id=str(source_id or secrets.token_urlsafe(16)),
                        name=contact.name,
                    ),
                    channel,
                )
            finally:
                await channel.close()
            link.contact_id = contact.id
            await db.flush()
    if contact is None:
        contact = await db.get(Contact, link.contact_id)
    assert contact is not None

    conversation, created = await conv_service.find_or_create_conversation(
        db, inbox, contact, link
    )
    if params.get("status"):
        conversation.status = str(params["status"])
    if params.get("assignee_id") is not None:
        conversation.assignee_id = int(params["assignee_id"])
    if params.get("team_id") is not None:
        conversation.team_id = int(params["team_id"])
    if isinstance(params.get("custom_attributes"), dict):
        conversation.custom_attributes = {
            **(conversation.custom_attributes or {}),
            **params["custom_attributes"],
        }
    await db.flush()
    await conv_service.notify_conversation(
        db,
        conversation,
        bus.EVENT_CONVERSATION_CREATED if created else bus.EVENT_CONVERSATION_UPDATED,
    )

    first = params.get("message")
    if isinstance(first, dict) and first.get("content"):
        async with use_session(db):
            await conv_service.create_outgoing_message(
                db, conversation, content=str(first["content"]), user=user
            )
    return await _conversation_body(db, conversation)


@router.post("/conversations/{conversation_id}/toggle_status")
async def toggle_conversation_status(
    conversation_id: int, request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    conversation = await _get_conversation(db, conversation_id)
    params = await read_params(request)
    target = str(params.get("status") or "").strip()
    if not target:
        target = (
            ConversationStatus.OPEN.value
            if conversation.status == ConversationStatus.RESOLVED.value
            else ConversationStatus.RESOLVED.value
        )
    if target not in {s.value for s in ConversationStatus}:
        raise invalid(f"Status is not included in the list: {target}")
    await conv_service.set_status(db, conversation, target, actor=user)
    return {
        "payload": {
            "success": True,
            "current_status": conversation.status,
            "conversation_id": chatwoot.conversation_display_id(conversation),
        }
    }


@router.post("/conversations/{conversation_id}/assignments")
async def create_assignment(
    conversation_id: int, request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    conversation = await _get_conversation(db, conversation_id)
    params = await read_params(request)
    assignee_id = params.get("assignee_id")

    assignee: User | None = None
    if assignee_id not in (None, "", 0, "0"):
        assignee = await db.get(User, int(assignee_id))
        if assignee is None:
            raise not_found()
    await conv_service.assign(db, conversation, assignee, actor=user)
    return _agent_body(assignee) or {}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: int,
    db: Db,
    user: CurrentApiUser,
    before: int | None = None,
    after: int | None = None,
) -> dict[str, Any]:
    conversation = await _get_conversation(db, conversation_id)
    query = select(Message).where(
        Message.conversation_id == conversation.id, Message.deleted_at.is_(None)
    )
    if before is not None:
        query = query.where(Message.id < before)
    if after is not None:
        query = query.where(Message.id > after)
    rows = list(await db.scalars(query.order_by(desc(Message.id)).limit(20)))

    return {
        "meta": {
            "labels": [
                link.label.title for link in (conversation.labels or []) if link.label
            ],
            "additional_attributes": {},
            "contact": chatwoot.serialize_contact(conversation.contact, push=True),
            "assignee": chatwoot.serialize_agent(conversation.assignee, push=True),
            # Raw datetimes here, unlike everywhere else — a real Chatwoot quirk.
            "agent_last_seen_at": (
                conversation.agent_last_seen_at.isoformat()
                if conversation.agent_last_seen_at
                else None
            ),
            "assignee_last_seen_at": (
                conversation.agent_last_seen_at.isoformat()
                if conversation.agent_last_seen_at
                else None
            ),
        },
        "payload": [
            await _message_body(db, m, conversation) for m in reversed(rows)
        ],
    }


@router.post("/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: int, request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    conversation = await _get_conversation(db, conversation_id)
    params = await read_params(request)
    inbox = await db.get(Inbox, conversation.inbox_id)
    assert inbox is not None

    message_type = str(params.get("message_type") or MessageType.OUTGOING.value)
    if message_type == MessageType.INCOMING.value and inbox.channel_type != ApiChannel.key:
        raise invalid("Incoming messages are only allowed in Api inboxes")

    attributes = dict(params.get("content_attributes") or {})
    if params.get("echo_id"):
        attributes["echo_id"] = params["echo_id"]

    if message_type == MessageType.INCOMING.value:
        channel = build_channel(inbox)
        try:
            message = await conv_service.process_inbound_event(
                db,
                inbox,
                channel,
                InboundEvent(
                    kind="message",
                    chat_source_id=conversation.source_id or "",
                    contact=NormalizedContact(source_id=conversation.source_id or ""),
                    message=NormalizedMessage(
                        source_id=params.get("source_id"),
                        content=params.get("content"),
                        attributes=attributes,
                    ),
                ),
                conversation=conversation,
            )
        finally:
            await channel.close()
        if message is None:
            raise invalid("Message could not be created")
        return await _message_body(db, message, conversation)

    # Outgoing (and private notes). The ambient session lets the API channel
    # render the outbound webhook body from this very transaction.
    async with use_session(db):
        message = await conv_service.create_outgoing_message(
            db,
            conversation,
            content=params.get("content"),
            user=user,
            private=bool(params.get("private", False)),
            content_attributes=attributes,
        )
    return await _message_body(db, message, conversation)


#: ``enum status`` on ``Message`` in Chatwoot, mapped onto ours.
_MESSAGE_STATUS = {
    "sent": MessageStatus.SENT.value,
    "delivered": MessageStatus.DELIVERED.value,
    "read": MessageStatus.READ.value,
    "failed": MessageStatus.FAILED.value,
}


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
async def update_message_status(
    conversation_id: int,
    message_id: int,
    request: Request,
    db: Db,
    user: CurrentApiUser,
) -> dict[str, Any]:
    """``Messages::StatusUpdateService`` — the API-inbox delivery receipt.

    ``before_action :ensure_api_inbox`` makes this **403** on every other
    channel; that is how integrations report ``delivered``/``read``/``failed``
    back to us for messages we pushed to their webhook URL.
    """
    conversation = await _get_conversation(db, conversation_id)
    inbox = await db.get(Inbox, conversation.inbox_id)
    if inbox is None or inbox.channel_type != ApiChannel.key:
        raise forbidden("Message status update is only allowed for API inboxes")

    message = await db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        raise not_found()

    params = await read_params(request)
    status = str(params.get("status") or "")
    if status not in _MESSAGE_STATUS:
        raise invalid(f"Status is not included in the list: {status}", ["status"])

    message.status = _MESSAGE_STATUS[status]
    external_error = params.get("external_error")
    if status == "failed":
        message.external_error = str(external_error) if external_error else None
    elif external_error is None:
        message.external_error = None
    await db.flush()
    await db.refresh(message)
    await bus.publish(
        bus.EVENT_MESSAGE_UPDATED,
        {"message": {"id": message.id}, "conversation_id": conversation.id},
    )
    return await _message_body(db, message, conversation)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------
async def _contact_inboxes(
    db: AsyncSession, contact: Contact
) -> list[tuple[ContactInbox, Inbox]]:
    links = list(
        await db.scalars(
            select(ContactInbox).where(ContactInbox.contact_id == contact.id)
        )
    )
    pairs: list[tuple[ContactInbox, Inbox]] = []
    for link in links:
        inbox = await db.get(Inbox, link.inbox_id)
        if inbox is not None:
            pairs.append((link, inbox))
    return pairs


@router.get("/contacts")
async def list_contacts(
    db: Db, user: CurrentApiUser, page: int = 1, include_contact_inboxes: bool = True
) -> dict[str, Any]:
    total = int(await db.scalar(select(func.count(Contact.id))) or 0)
    rows = list(
        await db.scalars(
            select(Contact)
            .order_by(desc(Contact.last_activity_at), desc(Contact.id))
            .limit(RESULTS_PER_PAGE)
            .offset(max(page - 1, 0) * RESULTS_PER_PAGE)
        )
    )
    return {
        "meta": {"count": total, "current_page": str(page)},
        "payload": [
            _contact_body(
                c,
                contact_inboxes=(
                    await _contact_inboxes(db, c) if include_contact_inboxes else None
                ),
            )
            for c in rows
        ],
    }


@router.get("/contacts/search")
async def search_contacts(
    db: Db, user: CurrentApiUser, q: str | None = None, page: int = 1
) -> dict[str, Any]:
    if not q:
        raise parameter_missing("Specify search string with parameter q")
    pattern = f"%{q}%"
    where = or_(
        Contact.name.ilike(pattern),
        Contact.email.ilike(pattern),
        Contact.phone.ilike(pattern),
        Contact.identifier.like(pattern),
    )
    total = int(await db.scalar(select(func.count(Contact.id)).where(where)) or 0)
    offset = max(page - 1, 0) * RESULTS_PER_PAGE
    rows = list(
        await db.scalars(
            select(Contact)
            .where(where)
            .order_by(Contact.id)
            .limit(RESULTS_PER_PAGE)
            .offset(offset)
        )
    )
    return {
        "meta": {
            "count": total,
            "current_page": str(page),
            "has_more": offset + len(rows) < total,
        },
        "payload": [_contact_body(c) for c in rows],
    }


@router.get("/contacts/{contact_id}")
async def show_contact(contact_id: int, db: Db, user: CurrentApiUser) -> dict[str, Any]:
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise not_found()
    return {
        "payload": _contact_body(
            contact, contact_inboxes=await _contact_inboxes(db, contact)
        )
    }


@router.post("/contacts")
async def create_contact(
    request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    params = await read_params(request)
    contact = Contact(
        name=str(params.get("name") or ""),
        email=params.get("email"),
        phone=params.get("phone_number"),
        identifier=params.get("identifier"),
        avatar_url=params.get("avatar_url"),
        blocked=bool(params.get("blocked", False)),
        custom_attributes=params.get("custom_attributes") or {},
        last_activity_at=utcnow(),
    )
    db.add(contact)
    await db.flush()

    link: ContactInbox | None = None
    inbox_id = params.get("inbox_id")
    if inbox_id is not None:
        inbox = await db.get(Inbox, int(inbox_id))
        if inbox is None:
            raise not_found()
        link = ContactInbox(
            contact_id=contact.id,
            inbox_id=inbox.id,
            source_id=str(params.get("source_id") or secrets.token_urlsafe(16)),
            meta={},
        )
        db.add(link)
        await db.flush()

    await bus.publish(bus.EVENT_CONTACT_UPDATED, {"contact": {"id": contact.id}})
    payload: dict[str, Any] = {
        "contact": _contact_body(
            contact, contact_inboxes=await _contact_inboxes(db, contact)
        )
    }
    if link is not None:
        inbox = await db.get(Inbox, link.inbox_id)
        payload["contact_inbox"] = {
            "inbox": _inbox_body(inbox) if inbox else None,
            "source_id": link.source_id,
        }
    return {"payload": payload}


@router.patch("/contacts/{contact_id}")
async def update_contact(
    contact_id: int, request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise not_found()
    params = await read_params(request)

    for attribute, key in (
        ("name", "name"),
        ("email", "email"),
        ("phone", "phone_number"),
        ("identifier", "identifier"),
        ("avatar_url", "avatar_url"),
    ):
        if params.get(key) is not None:
            setattr(contact, attribute, params[key])
    if params.get("blocked") is not None:
        contact.blocked = bool(params["blocked"])
    # Chatwoot *merges* both attribute bags rather than replacing them.
    if isinstance(params.get("custom_attributes"), dict):
        contact.custom_attributes = {
            **(contact.custom_attributes or {}),
            **params["custom_attributes"],
        }
    await db.flush()
    await bus.publish(bus.EVENT_CONTACT_UPDATED, {"contact": {"id": contact.id}})
    return {
        "payload": _contact_body(
            contact, contact_inboxes=await _contact_inboxes(db, contact)
        )
    }


# ---------------------------------------------------------------------------
# Inboxes
# ---------------------------------------------------------------------------
@router.get("/inboxes")
async def list_inboxes(db: Db, user: CurrentApiUser) -> dict[str, Any]:
    rows = list(await db.scalars(select(Inbox).order_by(Inbox.id)))
    return {"payload": [_inbox_body(inbox) for inbox in rows]}


#: ``channel_type_from_params`` — Chatwoot's input names for the channels we
#: actually implement. Everything else is rejected rather than silently created.
_CHANNEL_INPUT = {"api": ApiChannel.key, "telegram": "telegram"}


@router.post("/inboxes")
async def create_inbox(request: Request, db: Db, user: CurrentApiUser) -> dict[str, Any]:
    """``Api::V1::Accounts::InboxesController#create``.

    Only ``Channel::Api::EDITABLE_ATTRS`` are honoured for an API inbox
    (``webhook_url``, ``hmac_mandatory``, ``additional_attributes``); the three
    tokens are minted server-side and never accepted as input.
    """
    params = await read_params(request)
    channel = params.get("channel")
    if not isinstance(channel, dict) or not channel.get("type"):
        raise parameter_missing("param is missing or the value is empty: channel")
    channel_type = _CHANNEL_INPUT.get(str(channel["type"]))
    if channel_type is None:
        raise invalid(f"Channel type is not supported: {channel['type']}", ["channel"])

    config: dict[str, Any] = {}
    if channel_type == ApiChannel.key:
        config["webhook_url"] = channel.get("webhook_url")
        config["hmac_mandatory"] = bool(channel.get("hmac_mandatory", False))
        extra = channel.get("additional_attributes")
        if isinstance(extra, dict) and extra.get("agent_reply_time_window") is not None:
            config["agent_reply_time_window"] = extra["agent_reply_time_window"]
    else:  # pragma: no cover - non-API channels need their own credentials
        config = {k: v for k, v in channel.items() if k != "type"}

    inbox = Inbox(
        name=str(params.get("name") or "Inbox"),
        channel_type=channel_type,
        mode="webhook",
        config={},
        working_hours={},
        connection_status="unknown",
    )
    db.add(inbox)
    await db.flush()

    from ...api.v1.inboxes import _configure

    try:
        await _configure(db, inbox, config)
    except HTTPException as exc:
        raise invalid(str(exc.detail), ["channel"]) from exc

    await bus.publish(bus.EVENT_INBOX_UPDATED, {"inbox": {"id": inbox.id}})
    return _inbox_body(inbox)


@router.post("/inboxes/{inbox_id}/reset_secret")
async def reset_inbox_secret(
    inbox_id: int, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    """``reset_secret`` — 404 on anything that is not an API inbox."""
    inbox = await db.get(Inbox, inbox_id)
    if inbox is None or inbox.channel_type != ApiChannel.key:
        raise not_found()
    from ...channels.api_channel.channel import generate_token

    inbox.config = {**(inbox.config or {}), "secret": generate_token()}
    await db.flush()
    return _inbox_body(inbox)


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------
def _webhook_body(hook: Webhook, inbox: Inbox | None) -> dict[str, Any]:
    """``api/v1/accounts/webhooks/_webhook`` — no ``webhook_type``, no timestamps."""
    body: dict[str, Any] = {
        "id": hook.id,
        "name": hook.name,
        "url": hook.url,
        "account_id": chatwoot.CHATWOOT_ACCOUNT_ID,
        "subscriptions": hook.subscriptions or [],
        "secret": hook.secret,
    }
    if inbox is not None:
        body["inbox"] = {"id": inbox.id, "name": inbox.name}
    return body


def _webhook_params(params: dict[str, Any]) -> dict[str, Any]:
    """``params.require(:webhook)`` — Rails' ``wrap_parameters`` makes the
    unwrapped form work too, so both are accepted."""
    inner = params.get("webhook")
    return dict(inner) if isinstance(inner, dict) else dict(params)


def _validate_subscriptions(subscriptions: Any) -> list[str]:
    """``validate_webhook_subscriptions`` — an empty array is invalid, and there
    is no "subscribe to everything" wildcard."""
    if not isinstance(subscriptions, list) or not subscriptions:
        raise invalid(
            "Validation failed: Subscriptions should have at least one event",
            ["subscriptions"],
        )
    unknown = [s for s in subscriptions if s not in chatwoot.CHATWOOT_EVENTS]
    if unknown:
        raise invalid(
            f"Validation failed: Subscriptions invalid event name {', '.join(unknown)}",
            ["subscriptions"],
        )
    return [str(s) for s in subscriptions]


@router.get("/webhooks")
async def list_webhooks(db: Db, user: CurrentApiUser) -> dict[str, Any]:
    rows = list(
        await db.scalars(
            select(Webhook)
            .where(Webhook.payload_format == "chatwoot")
            .order_by(Webhook.id)
        )
    )
    out = []
    for hook in rows:
        inbox = await db.get(Inbox, hook.inbox_id) if hook.inbox_id else None
        out.append(_webhook_body(hook, inbox))
    return {"payload": {"webhooks": out}}


@router.post("/webhooks")
async def create_webhook(
    request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    params = _webhook_params(await read_params(request))
    url = str(params.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise invalid("Validation failed: Url is invalid", ["url"])
    if await db.scalar(select(Webhook).where(Webhook.url == url)):
        raise invalid("Validation failed: Url has already been taken", ["url"])

    hook = Webhook(
        url=url,
        name=params.get("name"),
        subscriptions=_validate_subscriptions(params.get("subscriptions")),
        # The client never supplies the secret; Chatwoot generates it.
        secret=secrets.token_urlsafe(18),
        payload_format="chatwoot",
        active=True,
        inbox_id=int(params["inbox_id"]) if params.get("inbox_id") else None,
    )
    db.add(hook)
    await db.flush()
    inbox = await db.get(Inbox, hook.inbox_id) if hook.inbox_id else None
    return {"payload": {"webhook": _webhook_body(hook, inbox)}}


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: int, request: Request, db: Db, user: CurrentApiUser
) -> dict[str, Any]:
    hook = await db.get(Webhook, webhook_id)
    if hook is None or hook.payload_format != "chatwoot":
        raise not_found()
    params = _webhook_params(await read_params(request))
    if params.get("url"):
        hook.url = str(params["url"])
    if "name" in params:
        hook.name = params["name"]
    if params.get("subscriptions") is not None:
        hook.subscriptions = _validate_subscriptions(params["subscriptions"])
    if params.get("inbox_id") is not None:
        hook.inbox_id = int(params["inbox_id"])
    await db.flush()
    inbox = await db.get(Inbox, hook.inbox_id) if hook.inbox_id else None
    return {"payload": {"webhook": _webhook_body(hook, inbox)}}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int, db: Db, user: CurrentApiUser
) -> Response:
    """``head :ok`` — 200 with an empty body."""
    hook = await db.get(Webhook, webhook_id)
    if hook is None or hook.payload_format != "chatwoot":
        raise not_found()
    await db.delete(hook)
    await db.flush()
    return Response(status_code=200)
