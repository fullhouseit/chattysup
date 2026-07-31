"""Chatwoot-compatible payload layer.

Pure functions turning ChattySup ORM objects into the exact JSON Chatwoot's
outgoing webhooks emit (``*#webhook_data`` / ``Conversations::EventDataPresenter``
/ ``Inbox::EventDataPresenter`` in the Rails source).

Chatwoot's own serialisers are inconsistent in ways real consumers depend on, so
those inconsistencies are reproduced here **on purpose**:

* ``message_type`` is the **string** ``"incoming"`` at the top level of a message
  payload but the **integer** ``0`` inside ``conversation.messages[0]``;
* a message's top-level ``created_at`` is **ISO-8601 with milliseconds** while
  every timestamp inside ``conversation`` is an **epoch integer** — except
  ``conversation.updated_at`` which is an epoch **float**;
* ``attachments`` / ``echo_id`` / ``sender`` keys are *omitted*, never ``null``;
* nil timestamps collapse to ``0`` (``agent_last_seen_at``, ``waiting_since`` …)
  but ``snoozed_until`` / ``first_reply_created_at`` stay ``null``;
* a conversation's ``id`` is the per-account ``display_id``, not the PK, and
  ``conversation.messages[0].conversation_id`` is that display id too.

Where ChattySup has no equivalent for a Chatwoot field we emit the key anyway
with a defensible null/default rather than dropping it — Chatwoot clients index
by key, and a missing key breaks more consumers than a null one.

Nothing here talks to the database: every function takes objects (and, when a
relation is needed that our models do not eagerly load, an explicit keyword
argument) and returns plain JSON-able dicts.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ..core import storage
from ..models import (
    Attachment,
    Contact,
    ContactInbox,
    Conversation,
    Inbox,
    Message,
    Team,
    User,
)
from ..models.enums import (
    AttachmentType,
    ContentType,
    ConversationPriority,
    MessageStatus,
    MessageType,
    SenderType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: ChattySup is single-tenant; Chatwoot payloads always carry an account object.
#: Override with ``CHATWOOT_ACCOUNT_ID`` if a deployment must impersonate a
#: specific Chatwoot account id.
CHATWOOT_ACCOUNT_ID: int = int(os.environ.get("CHATWOOT_ACCOUNT_ID", "1"))

#: Name shown in the ``account`` sub-object of every payload.
CHATWOOT_ACCOUNT_NAME: str = os.environ.get("CHATWOOT_ACCOUNT_NAME", "ChattySup")

#: ``Webhook::ALLOWED_WEBHOOK_EVENTS`` (app/models/webhook.rb) — the full set of
#: event names a Chatwoot-format webhook may subscribe to. Chatwoot has no
#: ``message_deleted``; deletions surface as ``message_updated``.
CHATWOOT_EVENTS: tuple[str, ...] = (
    "conversation_status_changed",
    "conversation_updated",
    "conversation_created",
    "contact_created",
    "contact_updated",
    "message_created",
    "message_updated",
    "webwidget_triggered",
    "inbox_created",
    "inbox_updated",
    "conversation_typing_on",
    "conversation_typing_off",
)

#: Our ``ChannelType`` -> Chatwoot's Rails channel class name. Anything we do
#: not know about is reported as ``Channel::Api``, which is the channel Chatwoot
#: clients treat as "generic programmable inbox".
CHANNEL_CLASS: dict[str, str] = {
    "telegram": "Channel::Telegram",
    "web": "Channel::WebWidget",
    "email": "Channel::Email",
}
DEFAULT_CHANNEL_CLASS = "Channel::Api"

#: ``enum message_type`` in app/models/message.rb.
MESSAGE_TYPE_INT: dict[str, int] = {
    MessageType.INCOMING.value: 0,
    MessageType.OUTGOING.value: 1,
    MessageType.ACTIVITY.value: 2,
    MessageType.TEMPLATE.value: 3,
}

#: ``enum status`` in app/models/message.rb — Chatwoot has no ``pending``.
MESSAGE_STATUS: dict[str, str] = {
    MessageStatus.PENDING.value: "sent",
    MessageStatus.SENT.value: "sent",
    MessageStatus.DELIVERED.value: "delivered",
    MessageStatus.READ.value: "read",
    MessageStatus.FAILED.value: "failed",
}

#: Our ``ContentType`` -> Chatwoot's ``enum content_type``. Chatwoot has no
#: ``location`` / ``contact_card`` / ``poll`` / ``story`` / ``system`` content
#: type, so those degrade to ``text`` (the payload still carries the real
#: information through ``attachments`` / ``content_attributes``).
CONTENT_TYPE: dict[str, str] = {
    ContentType.TEXT.value: "text",
    ContentType.STICKER.value: "sticker",
    ContentType.LOCATION.value: "text",
    ContentType.CONTACT_CARD.value: "text",
    ContentType.POLL.value: "text",
    ContentType.STORY.value: "text",
    ContentType.SYSTEM.value: "text",
}

#: Our ``AttachmentType`` -> Chatwoot's ``enum file_type``.
FILE_TYPE: dict[str, str] = {
    AttachmentType.IMAGE.value: "image",
    AttachmentType.AUDIO.value: "audio",
    AttachmentType.VOICE.value: "audio",
    AttachmentType.VIDEO.value: "video",
    AttachmentType.VIDEO_NOTE.value: "video",
    AttachmentType.FILE.value: "file",
    AttachmentType.STICKER.value: "image",
    AttachmentType.ANIMATION.value: "video",
    AttachmentType.LOCATION.value: "location",
    AttachmentType.CONTACT_CARD.value: "contact",
}

#: ``sender_type`` column values in Chatwoot (capitalised class names).
SENDER_CLASS: dict[str, str | None] = {
    SenderType.CONTACT.value: "Contact",
    SenderType.USER.value: "User",
    SenderType.BOT.value: "AgentBot",
    SenderType.SYSTEM.value: None,
}


# ---------------------------------------------------------------------------
# Timestamp helpers — the three formats Chatwoot mixes
# ---------------------------------------------------------------------------
def epoch(value: datetime | None) -> int:
    """Epoch seconds. ``nil.to_i == 0`` in Ruby, so ``None`` becomes ``0``."""
    return int(value.timestamp()) if value else 0


def epoch_float(value: datetime | None) -> float:
    """Epoch seconds as a float (``updated_at`` on conversations only)."""
    return float(value.timestamp()) if value else 0.0


def iso8601(value: datetime | None) -> str | None:
    """Rails' ``ActiveSupport`` JSON time format: ``2020-03-03T13:05:57.000Z``.

    Rails' ``time_precision`` defaults to 3 fractional digits and a literal
    ``Z``; the dossier flags the exact format as unverified against a live
    instance, and this is the documented default.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return f"{value.strftime('%Y-%m-%dT%H:%M:%S')}.{value.microsecond // 1000:03d}Z"


def _channel_class(inbox: Inbox | None) -> str:
    if inbox is None:
        return DEFAULT_CHANNEL_CLASS
    return CHANNEL_CLASS.get(inbox.channel_type, DEFAULT_CHANNEL_CLASS)


def _attachment_url(attachment: Attachment) -> str | None:
    if attachment.storage_key:
        return storage.url_for(attachment.id)
    return attachment.external_url


# ---------------------------------------------------------------------------
# account / inbox
# ---------------------------------------------------------------------------
def serialize_account() -> dict[str, Any]:
    """``Account#webhook_data`` — ``{id, name}`` and nothing else."""
    return {"id": CHATWOOT_ACCOUNT_ID, "name": CHATWOOT_ACCOUNT_NAME}


def serialize_inbox(inbox: Inbox | None, *, full: bool = False) -> dict[str, Any] | None:
    """Chatwoot has **two** inbox shapes.

    ``full=False`` -> ``Inbox#webhook_data`` == ``{id, name}``, the object nested
    as ``inbox:`` inside message payloads.

    ``full=True`` -> ``Inbox::EventDataPresenter#webhook_data``, the body of the
    ``inbox_created`` / ``inbox_updated`` events. That presenter genuinely has
    **no ``id`` and no ``name``** (the dossier flags this as surprising but
    double-verified against the source), so we reproduce the omission.
    """
    if inbox is None:
        return None
    if not full:
        return {"id": inbox.id, "name": inbox.name}

    return {
        "allow_messages_after_resolved": True,
        "lock_to_single_conversation": False,
        "auto_assignment_config": {},
        "enable_auto_assignment": inbox.auto_assignment_enabled,
        # Chatwoot's e-mail collect / greeting flags; we only model greetings.
        "enable_email_collect": False,
        "greeting_enabled": inbox.greeting_enabled,
        "greeting_message": inbox.greeting_message,
        "csat_survey_enabled": inbox.csat_enabled,
        "business_name": None,
        "sender_name_type": "friendly",
        "timezone": "UTC",
        "out_of_office_message": inbox.out_of_office_message,
        "working_hours_enabled": bool(inbox.working_hours),
        "working_hours": inbox.working_hours or [],
        "created_at": iso8601(inbox.created_at),
        "updated_at": iso8601(inbox.updated_at),
        # Chatwoot dumps the raw channel AR record here (and leaks its columns).
        # We publish a curated, secret-free equivalent instead: our channel
        # config holds bot tokens.
        "channel": {
            "id": inbox.id,
            "channel_type": _channel_class(inbox),
            "name": inbox.name,
        },
    }


# ---------------------------------------------------------------------------
# contact
# ---------------------------------------------------------------------------
def serialize_contact(
    contact: Contact | None, *, push: bool = False
) -> dict[str, Any] | None:
    """``Contact#webhook_data`` (``push=False``) or ``#push_event_data``.

    The two differ in a way that trips everyone up: ``webhook_data`` embeds
    ``account`` and has both ``avatar`` and ``thumbnail`` but **no ``type``**,
    while ``push_event_data`` has ``type: "contact"`` and no ``account``/``avatar``.
    """
    if contact is None:
        return None

    avatar = contact.avatar_url or ""
    if push:
        return {
            "additional_attributes": _contact_additional_attributes(contact),
            "custom_attributes": contact.custom_attributes or {},
            "email": contact.email,
            "id": contact.id,
            "identifier": contact.identifier,
            "name": contact.name,
            "phone_number": contact.phone,
            "thumbnail": avatar,
            "blocked": contact.blocked,
            "type": "contact",
        }

    return {
        "account": serialize_account(),
        "additional_attributes": _contact_additional_attributes(contact),
        "avatar": avatar,
        "custom_attributes": contact.custom_attributes or {},
        "email": contact.email,
        "id": contact.id,
        "identifier": contact.identifier,
        "name": contact.name,
        "phone_number": contact.phone,
        "thumbnail": avatar,
        "blocked": contact.blocked,
    }


def _contact_additional_attributes(contact: Contact) -> dict[str, Any]:
    """Our first-class contact columns have no Chatwoot column; Chatwoot users
    keep exactly this sort of data in ``additional_attributes``."""
    data: dict[str, Any] = {}
    if contact.company:
        data["company_name"] = contact.company
    if contact.title:
        data["description"] = contact.title
    if contact.location:
        data["city"] = contact.location
    if contact.country_code:
        data["country_code"] = contact.country_code
    if contact.timezone:
        data["timezone"] = contact.timezone
    if contact.social_profiles:
        data["social_profiles"] = contact.social_profiles
    return data


def serialize_contact_inbox(
    contact_inbox: ContactInbox | None,
    *,
    contact: Contact | None = None,
    inbox: Inbox | None = None,
    source_id: str | None = None,
) -> dict[str, Any] | None:
    """The raw ``ContactInbox`` record Chatwoot embeds in ``conversation``.

    Chatwoot serialises the ActiveRecord object, so the payload carries every DB
    column including ``pubsub_token`` and ``hmac_verified``. We have no such
    columns; both are emitted with static values (unverified against a live
    instance, but the key set is what consumers destructure).
    """
    if contact_inbox is None:
        if source_id is None:
            return None
        # Synthesised from the conversation when the link row is unavailable.
        return {
            "id": None,
            "contact_id": contact.id if contact else None,
            "inbox_id": inbox.id if inbox else None,
            "source_id": source_id,
            "hmac_verified": False,
            "pubsub_token": None,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": contact_inbox.id,
        "contact_id": contact_inbox.contact_id,
        "inbox_id": contact_inbox.inbox_id,
        "source_id": contact_inbox.source_id,
        "hmac_verified": False,
        "pubsub_token": None,
        "created_at": iso8601(contact_inbox.created_at),
        "updated_at": iso8601(contact_inbox.updated_at),
    }


# ---------------------------------------------------------------------------
# users / senders
# ---------------------------------------------------------------------------
def serialize_agent(user: User | None, *, push: bool = False) -> dict[str, Any] | None:
    """``User#webhook_data`` (``push=False``) or ``User#push_event_data``."""
    if user is None:
        return None
    if push:
        return {
            "id": user.id,
            "name": user.name,
            "available_name": user.display_name or user.name,
            "avatar_url": user.avatar_url or "",
            "type": "user",
            "availability_status": user.availability,
            "thumbnail": user.avatar_url or "",
        }
    return {"id": user.id, "name": user.name, "email": user.email, "type": "user"}


def serialize_sender(
    sender_type: str | None,
    sender: Contact | User | None,
    *,
    push: bool = False,
) -> dict[str, Any] | None:
    """Polymorphic ``sender`` sub-object.

    Chatwoot returns ``null`` for system/bot senders in webhooks (``AgentBot``
    defines no ``webhook_data``, and ``sender.try(:webhook_data)`` therefore
    yields nil), which is what we do for ``SenderType.SYSTEM`` and
    ``SenderType.BOT``.
    """
    if sender is None:
        return None
    if sender_type == SenderType.CONTACT.value and isinstance(sender, Contact):
        return serialize_contact(sender, push=push)
    if sender_type == SenderType.USER.value and isinstance(sender, User):
        return serialize_agent(sender, push=push)
    return None


def serialize_team(team: Team | None) -> dict[str, Any] | None:
    """``Team#push_event_data``. We have no icon columns -> ``None``."""
    if team is None:
        return None
    return {"id": team.id, "name": team.name, "icon": None, "icon_color": None}


# ---------------------------------------------------------------------------
# attachment
# ---------------------------------------------------------------------------
def serialize_attachment(attachment: Attachment) -> dict[str, Any]:
    """``Attachment#push_event_data`` — one serialiser for webhooks *and* API.

    The key set varies by ``file_type``; see ``metadata_for_file_type``.
    """
    file_type = FILE_TYPE.get(attachment.file_type, "file")
    base = {
        "id": attachment.id,
        "message_id": attachment.message_id,
        "file_type": file_type,
        "account_id": CHATWOOT_ACCOUNT_ID,
    }
    meta = attachment.meta or {}
    data_url = _attachment_url(attachment)

    if file_type == "location":
        return {
            **base,
            "coordinates_lat": float(meta.get("latitude") or 0.0),
            "coordinates_long": float(meta.get("longitude") or 0.0),
            "fallback_title": attachment.file_name,
            "data_url": data_url,
        }
    if file_type == "contact":
        return {**base, "fallback_title": attachment.file_name, "meta": meta}

    thumb_url = (
        f"{storage.url_for(attachment.id)}?variant=thumb" if attachment.thumb_key else ""
    )
    data = {
        **base,
        "extension": _extension(attachment.file_name),
        "content_type": attachment.mime_type,
        "data_url": data_url,
        "thumb_url": thumb_url,
        "file_size": attachment.file_size,
        "width": meta.get("width"),
        "height": meta.get("height"),
    }
    if file_type == "audio":
        data["transcribed_text"] = meta.get("transcribed_text") or ""
    return data


def _extension(file_name: str | None) -> str | None:
    if not file_name or "." not in file_name:
        return None
    return file_name.rsplit(".", 1)[1] or None


# ---------------------------------------------------------------------------
# conversation
# ---------------------------------------------------------------------------
def conversation_display_id(conversation: Conversation) -> int:
    """Chatwoot exposes the per-account ``display_id``, never the PK.

    ChattySup is single-tenant and its conversation PK is already a per-account
    sequence, so the PK *is* the display id. Kept as a named function so a real
    ``display_id`` column can be introduced later without touching callers.
    """
    return conversation.id


def serialize_conversation(
    conversation: Conversation,
    *,
    last_message: Message | None = None,
    contact: Contact | None = None,
    inbox: Inbox | None = None,
    assignee: User | None = None,
    team: Team | None = None,
    contact_inbox: ContactInbox | None = None,
    labels: list[str] | None = None,
    include_account: bool = True,
) -> dict[str, Any]:
    """``Conversations::EventDataPresenter#webhook_data``.

    ``messages`` is an array of **at most one** element — the last non-activity,
    non-private message, rendered with ``webhook_push_event_data`` (integer
    ``message_type``, epoch ``created_at``). Pass it as ``last_message``; an
    activity or private message is filtered out here, exactly like the ``chat``
    scope does.
    """
    contact = contact if contact is not None else conversation.contact
    inbox = inbox if inbox is not None else conversation.inbox
    assignee = assignee if assignee is not None else conversation.assignee

    if labels is None:
        labels = [
            link.label.title for link in (conversation.labels or []) if link.label
        ]

    messages: list[dict[str, Any]] = []
    if last_message is not None and _is_chat_message(last_message):
        messages.append(
            serialize_message(
                last_message,
                push=True,
                conversation=conversation,
                inbox=inbox,
                sender=contact if last_message.sender_type == SenderType.CONTACT.value else assignee,
                contact_inbox=contact_inbox,
            )
        )

    priority = conversation.priority
    if priority == ConversationPriority.NONE.value:
        priority = None

    data: dict[str, Any] = {
        "additional_attributes": {},
        "can_reply": bool(inbox.is_active) if inbox is not None else True,
        "channel": _channel_class(inbox),
        "contact_inbox": serialize_contact_inbox(
            contact_inbox,
            contact=contact,
            inbox=inbox,
            source_id=conversation.source_id,
        ),
        "id": conversation_display_id(conversation),
        "inbox_id": conversation.inbox_id,
        "messages": messages,
        "labels": labels,
        "meta": {
            "sender": serialize_contact(contact, push=True),
            "assignee": serialize_agent(assignee, push=True),
            "assignee_type": "User" if assignee is not None else None,
            "team": serialize_team(team),
            "hmac_verified": False,
        },
        "status": conversation.status,
        "custom_attributes": conversation.custom_attributes or {},
        "snoozed_until": iso8601(conversation.snoozed_until),
        "unread_count": conversation.unread_count,
        "first_reply_created_at": iso8601(conversation.first_reply_created_at),
        "priority": priority,
        "waiting_since": epoch(conversation.waiting_since),
        "agent_last_seen_at": epoch(conversation.agent_last_seen_at),
        "contact_last_seen_at": epoch(conversation.contact_last_seen_at),
        "last_activity_at": epoch(conversation.last_activity_at),
        "timestamp": epoch(conversation.last_activity_at),
        "created_at": epoch(conversation.created_at),
        # Deliberately a float while everything around it is an integer.
        "updated_at": epoch_float(conversation.updated_at),
    }
    if include_account:
        data["account"] = serialize_account()
    return data


def _is_chat_message(message: Message) -> bool:
    """Chatwoot's ``chat`` scope: not an activity message and not private."""
    return message.message_type != MessageType.ACTIVITY.value and not message.private


def webhook_sendable(message: Message) -> bool:
    """``MessageFilterHelpers#webhook_sendable?``.

    Activity messages never produce ``message_created``/``message_updated``
    webhooks — but **private notes do**.
    """
    return message.message_type in (
        MessageType.INCOMING.value,
        MessageType.OUTGOING.value,
        MessageType.TEMPLATE.value,
    )


# ---------------------------------------------------------------------------
# message
# ---------------------------------------------------------------------------
def serialize_message(
    message: Message,
    *,
    conversation: Conversation | None = None,
    inbox: Inbox | None = None,
    sender: Contact | User | None = None,
    contact: Contact | None = None,
    assignee: User | None = None,
    team: Team | None = None,
    contact_inbox: ContactInbox | None = None,
    labels: list[str] | None = None,
    push: bool = False,
) -> dict[str, Any]:
    """``Message#webhook_data`` (``push=False``) or ``#webhook_push_event_data``.

    ``push=False`` is the top-level body of ``message_created``/``message_updated``:
    string ``message_type``, ISO-8601 ``created_at``, nested ``conversation`` /
    ``inbox`` / ``account`` objects and **no** ``status``/``conversation_id``.

    ``push=True`` is the nested ``conversation.messages[0]`` form: every DB
    column, integer ``message_type``, epoch ``created_at``, and
    ``conversation_id`` set to the conversation's *display id*.
    """
    content_attributes = dict(message.content_attributes or {})
    if message.deleted_at is not None:
        # Chatwoot has no message_deleted event; a deletion is a message_updated
        # carrying content_attributes.deleted.
        content_attributes["deleted"] = True
    if message.external_error:
        content_attributes.setdefault("external_error", message.external_error)

    attachments = [serialize_attachment(a) for a in message.attachments]

    if push:
        data: dict[str, Any] = {
            "id": message.id,
            "content": message.content,
            "account_id": CHATWOOT_ACCOUNT_ID,
            "inbox_id": message.inbox_id,
            "conversation_id": (
                conversation_display_id(conversation)
                if conversation is not None
                else message.conversation_id
            ),
            "message_type": MESSAGE_TYPE_INT.get(message.message_type, 0),
            "created_at": epoch(message.created_at),
            "updated_at": iso8601(message.updated_at),
            "private": message.private,
            "status": MESSAGE_STATUS.get(message.status, "sent"),
            "source_id": message.source_id,
            "content_type": CONTENT_TYPE.get(message.content_type, "text"),
            "content_attributes": content_attributes,
            "sender_type": SENDER_CLASS.get(message.sender_type),
            "sender_id": message.sender_id,
            "external_source_ids": {},
            "additional_attributes": {},
            "processed_message_content": message.content,
            "sentiment": {},
        }
        if conversation is not None:
            data["conversation"] = {
                "assignee_id": conversation.assignee_id,
                "unread_count": conversation.unread_count,
                "last_activity_at": epoch(conversation.last_activity_at),
                "contact_inbox": {
                    "source_id": (
                        contact_inbox.source_id
                        if contact_inbox is not None
                        else conversation.source_id
                    )
                },
            }
        if attachments:
            data["attachments"] = attachments
        sender_data = serialize_sender(message.sender_type, sender, push=True)
        if sender_data is not None:
            data["sender"] = sender_data
        return data

    body: dict[str, Any] = {
        "account": serialize_account(),
        "additional_attributes": {},
        "content_attributes": content_attributes,
        "content_type": CONTENT_TYPE.get(message.content_type, "text"),
        "content": message.content,
        "conversation": (
            serialize_conversation(
                conversation,
                last_message=message if _is_chat_message(message) else None,
                contact=contact,
                inbox=inbox,
                assignee=assignee,
                team=team,
                contact_inbox=contact_inbox,
                labels=labels,
            )
            if conversation is not None
            else None
        ),
        # ISO-8601 with milliseconds — the one timestamp Chatwoot does not
        # serialise as epoch seconds.
        "created_at": iso8601(message.created_at),
        "id": message.id,
        "inbox": serialize_inbox(inbox),
        "message_type": message.message_type,
        "private": message.private,
        "sender": serialize_sender(message.sender_type, sender),
        "source_id": message.source_id,
    }
    # Omitted entirely when empty — never [] and never null.
    if attachments:
        body["attachments"] = attachments
    return body


# ---------------------------------------------------------------------------
# changed_attributes
# ---------------------------------------------------------------------------
def build_changed_attributes(
    changes: dict[str, tuple[Any, Any]] | None,
) -> list[dict[str, dict[str, Any]]] | None:
    """``BaseListener#extract_changed_attributes``.

    An **array of single-key objects**, not one merged object, and ``None``
    (JSON ``null``) — not ``[]`` — when there is nothing.
    """
    if not changes:
        return None
    return [
        {key: {"previous_value": previous, "current_value": current}}
        for key, (previous, current) in changes.items()
    ]


# ---------------------------------------------------------------------------
# Event envelopes
# ---------------------------------------------------------------------------
def build_event(event_name: str, **objects: Any) -> dict[str, Any]:
    """Build the complete HTTP body for one Chatwoot webhook event.

    Chatwoot has **no envelope**: for ten of the twelve events the body is the
    resource's ``webhook_data`` hash with ``event`` merged in as one more
    top-level sibling key. Only ``conversation_typing_on``/``_off`` have a
    hand-built nested shape.

    Recognised keyword objects (all optional, per event):
    ``conversation``, ``message``, ``contact``, ``inbox``, ``user``,
    ``last_message``, ``sender``, ``assignee``, ``team``, ``contact_inbox``,
    ``labels``, ``changes`` (``{attr: (previous, current)}``), ``is_private``,
    ``event_info``, ``source_id``.
    """
    if event_name not in CHATWOOT_EVENTS:
        raise ValueError(f"Unknown Chatwoot webhook event: {event_name}")

    changed = build_changed_attributes(objects.get("changes"))

    if event_name in ("conversation_typing_on", "conversation_typing_off"):
        conversation = objects["conversation"]
        actor = objects.get("user")
        if isinstance(actor, Contact):
            user_data = serialize_contact(actor)
        else:
            user_data = serialize_agent(actor)
        # Exactly four top-level keys — the one genuinely nested envelope.
        return {
            "event": event_name,
            "user": user_data,
            "conversation": _conversation_body(conversation, objects),
            "is_private": bool(objects.get("is_private", False)),
        }

    if event_name in (
        "conversation_created",
        "conversation_updated",
        "conversation_status_changed",
    ):
        body = _conversation_body(objects["conversation"], objects)
        body["event"] = event_name
        if event_name != "conversation_created":
            # Present even when null; only contact/inbox events early-return.
            body["changed_attributes"] = changed
        return body

    if event_name in ("message_created", "message_updated"):
        message = objects["message"]
        body = serialize_message(
            message,
            conversation=objects.get("conversation"),
            inbox=objects.get("inbox"),
            sender=objects.get("sender"),
            contact=objects.get("contact"),
            assignee=objects.get("assignee"),
            team=objects.get("team"),
            contact_inbox=objects.get("contact_inbox"),
            labels=objects.get("labels"),
        )
        body["event"] = event_name
        return body

    if event_name in ("contact_created", "contact_updated"):
        body = serialize_contact(objects["contact"]) or {}
        body["event"] = event_name
        if event_name == "contact_updated":
            body["changed_attributes"] = changed
        return body

    if event_name in ("inbox_created", "inbox_updated"):
        body = serialize_inbox(objects["inbox"], full=True) or {}
        body["account"] = serialize_account()
        body["event"] = event_name
        if event_name == "inbox_updated":
            body["changed_attributes"] = changed
        return body

    # webwidget_triggered — ContactInbox#webhook_data + event + event_info.
    contact_inbox = objects.get("contact_inbox")
    contact = objects.get("contact")
    inbox = objects.get("inbox")
    conversation = objects.get("conversation")
    return {
        "id": contact_inbox.id if contact_inbox is not None else None,
        "contact": serialize_contact(contact),
        "inbox": serialize_inbox(inbox),
        "account": serialize_account(),
        "current_conversation": (
            _conversation_body(conversation, objects) if conversation is not None else None
        ),
        "source_id": (
            contact_inbox.source_id
            if contact_inbox is not None
            else objects.get("source_id")
        ),
        "event": "webwidget_triggered",
        "event_info": objects.get("event_info") or {},
    }


def _conversation_body(
    conversation: Conversation, objects: dict[str, Any]
) -> dict[str, Any]:
    return serialize_conversation(
        conversation,
        last_message=objects.get("last_message"),
        contact=objects.get("contact"),
        inbox=objects.get("inbox"),
        assignee=objects.get("assignee"),
        team=objects.get("team"),
        contact_inbox=objects.get("contact_inbox"),
        labels=objects.get("labels"),
    )


# ---------------------------------------------------------------------------
# Bus event -> Chatwoot event mapping
# ---------------------------------------------------------------------------
#: Every Chatwoot event each of our bus events *can* produce. The actual
#: selection for a given payload is made by :func:`map_event` — one of our
#: events may fan out to several of theirs (a conversation update that changed
#: ``status`` is both ``conversation_updated`` and ``conversation_status_changed``).
NATIVE_TO_CHATWOOT: dict[str, tuple[str, ...]] = {
    "conversation.created": ("conversation_created",),
    "conversation.updated": ("conversation_updated", "conversation_status_changed"),
    "conversation.typing": ("conversation_typing_on", "conversation_typing_off"),
    "message.created": ("message_created",),
    "message.updated": ("message_updated",),
    # Chatwoot has no message_deleted; a deletion is a message_updated whose
    # content_attributes carry ``deleted: true``.
    "message.deleted": ("message_updated",),
    # We have no contact.created bus event, so contact_created is reachable only
    # through build_event(), never through the dispatcher.
    "contact.updated": ("contact_updated",),
    "inbox.updated": ("inbox_updated",),
    # Presence is an agent-UI concern; Chatwoot has no webhook for it.
    "presence.updated": (),
}


def map_event(event: str, payload: dict[str, Any], *, status_changed: bool = False) -> list[str]:
    """Chatwoot event names one bus event should produce for this payload."""
    if event == "conversation.updated":
        names = ["conversation_updated"]
        if status_changed:
            names.append("conversation_status_changed")
        return names
    if event == "conversation.typing":
        return [
            "conversation_typing_on"
            if payload.get("typing", True)
            else "conversation_typing_off"
        ]
    return list(NATIVE_TO_CHATWOOT.get(event, ()))
