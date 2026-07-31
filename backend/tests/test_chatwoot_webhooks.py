"""Golden-payload tests for the Chatwoot compatibility layer.

Every assertion below is field-for-field against the shapes documented in the
Chatwoot research dossier (``*#webhook_data`` / ``EventDataPresenter``), plus
proof that the native webhook format is untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from app.compat import chatwoot
from app.models import (
    Attachment,
    Contact,
    ContactInbox,
    Conversation,
    ConversationLabel,
    Inbox,
    Label,
    Message,
    Team,
    User,
    Webhook,
)
from app.models.enums import (
    AttachmentType,
    ContentType,
    ConversationStatus,
    MessageStatus,
    MessageType,
    SenderType,
)
from app.services import webhooks as webhook_service

from .conftest import TestSession

T0 = datetime(2024, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2024, 5, 1, 12, 5, 0, 123000, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
async def world(db_session) -> dict[str, Any]:
    """A complete conversation graph: inbox, contact, link, agent, message."""
    inbox = Inbox(
        name="Support",
        channel_type="telegram",
        greeting_enabled=True,
        greeting_message="Hi!",
        created_at=T0,
        updated_at=T0,
    )
    contact = Contact(
        name="Bob",
        email="bob@example.com",
        phone="+15551234567",
        identifier="user-42",
        company="Acme",
        avatar_url="https://cdn/a.png",
        custom_attributes={"plan": "pro"},
        created_at=T0,
        updated_at=T0,
    )
    agent = User(
        email="jane@example.com",
        name="Jane Agent",
        display_name="Jane",
        role="agent",
        availability="online",
        created_at=T0,
        updated_at=T0,
    )
    team = Team(name="Tier 1", created_at=T0, updated_at=T0)
    db_session.add_all([inbox, contact, agent, team])
    await db_session.flush()

    link = ContactInbox(
        contact_id=contact.id, inbox_id=inbox.id, source_id="chat-99",
        created_at=T0, updated_at=T0,
    )
    label = Label(title="billing", created_at=T0, updated_at=T0)
    db_session.add_all([link, label])
    await db_session.flush()

    conversation = Conversation(
        inbox_id=inbox.id,
        contact_id=contact.id,
        contact_inbox_id=link.id,
        assignee_id=agent.id,
        team_id=team.id,
        status=ConversationStatus.OPEN.value,
        priority="none",
        last_activity_at=T1,
        waiting_since=T0,
        unread_count=2,
        source_id="chat-99",
        created_at=T0,
        updated_at=T1,
    )
    db_session.add(conversation)
    await db_session.flush()
    db_session.add(
        ConversationLabel(conversation_id=conversation.id, label_id=label.id)
    )

    message = Message(
        conversation_id=conversation.id,
        inbox_id=inbox.id,
        content="Hi, I need help",
        message_type=MessageType.INCOMING.value,
        content_type=ContentType.TEXT.value,
        status=MessageStatus.SENT.value,
        sender_type=SenderType.CONTACT.value,
        sender_id=contact.id,
        source_id="tg-1",
        created_at=T1,
        updated_at=T1,
    )
    db_session.add(message)
    await db_session.flush()
    await db_session.commit()

    # Eagerly resolve the relationships the compat layer reads, so the pure
    # serializers never trigger lazy IO from a sync context.
    await db_session.refresh(conversation, ["contact", "inbox", "assignee", "labels"])
    await db_session.refresh(message, ["attachments", "reactions"])

    return {
        "inbox": inbox,
        "contact": contact,
        "agent": agent,
        "team": team,
        "link": link,
        "conversation": conversation,
        "message": message,
        "label": label,
    }


POSTS: list[dict[str, Any]] = []


class RecordingClient:
    """Stand-in for ``httpx.AsyncClient`` capturing every delivery."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.default_timeout = kwargs.get("timeout")

    async def __aenter__(self) -> "RecordingClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def post(
        self,
        url: str,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        POSTS.append(
            {
                "url": url,
                "body": content,
                "headers": headers or {},
                "timeout": timeout if timeout is not None else self.default_timeout,
            }
        )
        return httpx.Response(200, request=httpx.Request("POST", url))


@pytest.fixture(autouse=True)
def recording(monkeypatch) -> None:
    POSTS.clear()
    webhook_service._last_status.clear()
    monkeypatch.setattr(webhook_service, "httpx", httpx)
    monkeypatch.setattr(webhook_service.httpx, "AsyncClient", RecordingClient)
    monkeypatch.setattr(webhook_service, "SessionLocal", TestSession)


async def _add_hook(db_session, **kwargs: Any) -> Webhook:
    hook = Webhook(active=True, created_at=T0, updated_at=T0, **kwargs)
    db_session.add(hook)
    await db_session.flush()
    await db_session.commit()
    return hook


def _body(index: int = 0) -> Any:
    import json

    return json.loads(POSTS[index]["body"])


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def test_account_shape() -> None:
    assert chatwoot.serialize_account() == {
        "id": chatwoot.CHATWOOT_ACCOUNT_ID,
        "name": chatwoot.CHATWOOT_ACCOUNT_NAME,
    }
    assert chatwoot.CHATWOOT_ACCOUNT_ID == 1


def test_inbox_webhook_data_is_two_keys(world) -> None:
    assert chatwoot.serialize_inbox(world["inbox"]) == {
        "id": world["inbox"].id,
        "name": "Support",
    }


def test_inbox_event_presenter_has_no_id_or_name(world) -> None:
    data = chatwoot.serialize_inbox(world["inbox"], full=True)
    assert "id" not in data and "name" not in data
    assert data["greeting_enabled"] is True
    assert data["greeting_message"] == "Hi!"
    assert data["sender_name_type"] == "friendly"
    assert data["created_at"] == "2024-05-01T12:00:00.000Z"


def test_contact_webhook_data_has_no_type_but_has_account(world) -> None:
    data = chatwoot.serialize_contact(world["contact"])
    assert set(data) == {
        "account",
        "additional_attributes",
        "avatar",
        "custom_attributes",
        "email",
        "id",
        "identifier",
        "name",
        "phone_number",
        "thumbnail",
        "blocked",
    }
    assert "type" not in data
    assert data["avatar"] == data["thumbnail"] == "https://cdn/a.png"
    assert data["phone_number"] == "+15551234567"
    assert data["additional_attributes"]["company_name"] == "Acme"


def test_contact_push_data_has_type_and_no_account(world) -> None:
    data = chatwoot.serialize_contact(world["contact"], push=True)
    assert data["type"] == "contact"
    assert "account" not in data and "avatar" not in data
    assert data["thumbnail"] == "https://cdn/a.png"


def test_user_webhook_vs_push(world) -> None:
    assert chatwoot.serialize_agent(world["agent"]) == {
        "id": world["agent"].id,
        "name": "Jane Agent",
        "email": "jane@example.com",
        "type": "user",
    }
    push = chatwoot.serialize_agent(world["agent"], push=True)
    assert push["available_name"] == "Jane"
    assert push["type"] == "user"
    assert push["availability_status"] == "online"


def test_sender_is_null_for_system_and_bot(world) -> None:
    assert chatwoot.serialize_sender(SenderType.SYSTEM.value, None) is None
    assert chatwoot.serialize_sender(SenderType.BOT.value, world["agent"]) is None
    assert chatwoot.serialize_sender(
        SenderType.CONTACT.value, world["contact"]
    )["name"] == "Bob"


def test_attachment_image_shape() -> None:
    attachment = Attachment(
        id=5,
        message_id=101,
        file_type=AttachmentType.IMAGE.value,
        file_name="pic.png",
        file_size=1234,
        mime_type="image/png",
        external_url="https://cdn/pic.png",
        meta={"width": 800, "height": 600},
    )
    assert chatwoot.serialize_attachment(attachment) == {
        "id": 5,
        "message_id": 101,
        "file_type": "image",
        "account_id": 1,
        "extension": "png",
        "content_type": "image/png",
        "data_url": "https://cdn/pic.png",
        "thumb_url": "",
        "file_size": 1234,
        "width": 800,
        "height": 600,
    }


def test_attachment_location_and_contact_variants() -> None:
    location = Attachment(
        id=6,
        message_id=101,
        file_type=AttachmentType.LOCATION.value,
        file_name="Home",
        meta={"latitude": 51.5, "longitude": -0.1},
    )
    assert chatwoot.serialize_attachment(location) == {
        "id": 6,
        "message_id": 101,
        "file_type": "location",
        "account_id": 1,
        "coordinates_lat": 51.5,
        "coordinates_long": -0.1,
        "fallback_title": "Home",
        "data_url": None,
    }
    card = Attachment(
        id=7,
        message_id=101,
        file_type=AttachmentType.CONTACT_CARD.value,
        file_name="Bob",
        meta={"phone": "+1"},
    )
    assert chatwoot.serialize_attachment(card) == {
        "id": 7,
        "message_id": 101,
        "file_type": "contact",
        "account_id": 1,
        "fallback_title": "Bob",
        "meta": {"phone": "+1"},
    }
    voice = Attachment(
        id=8, message_id=101, file_type=AttachmentType.VOICE.value, meta={}
    )
    assert chatwoot.serialize_attachment(voice)["file_type"] == "audio"
    assert chatwoot.serialize_attachment(voice)["transcribed_text"] == ""


def test_conversation_presenter_shape(world) -> None:
    conversation, message = world["conversation"], world["message"]
    data = chatwoot.serialize_conversation(
        conversation,
        last_message=message,
        contact_inbox=world["link"],
        team=world["team"],
    )
    assert set(data) == {
        "additional_attributes", "can_reply", "channel", "contact_inbox", "id",
        "inbox_id", "messages", "labels", "meta", "status", "custom_attributes",
        "snoozed_until", "unread_count", "first_reply_created_at", "priority",
        "waiting_since", "agent_last_seen_at", "contact_last_seen_at",
        "last_activity_at", "timestamp", "created_at", "updated_at", "account",
    }
    assert data["id"] == chatwoot.conversation_display_id(conversation)
    assert data["channel"] == "Channel::Telegram"
    assert data["status"] == "open"
    assert data["priority"] is None  # our "none" maps to Chatwoot's null
    assert data["labels"] == ["billing"]
    assert data["unread_count"] == 2
    # nil timestamps become 0, never null
    assert data["agent_last_seen_at"] == 0
    assert data["contact_last_seen_at"] == 0
    assert data["waiting_since"] == int(T0.timestamp())
    # ... but these two stay null
    assert data["snoozed_until"] is None
    assert data["first_reply_created_at"] is None
    # created_at int, updated_at float
    assert data["created_at"] == int(T0.timestamp())
    assert isinstance(data["created_at"], int)
    assert isinstance(data["updated_at"], float)
    assert data["timestamp"] == data["last_activity_at"] == int(T1.timestamp())
    # meta block
    assert set(data["meta"]) == {
        "sender", "assignee", "assignee_type", "team", "hmac_verified"
    }
    assert data["meta"]["sender"]["type"] == "contact"
    assert data["meta"]["assignee_type"] == "User"
    assert data["meta"]["team"] == {
        "id": world["team"].id, "name": "Tier 1", "icon": None, "icon_color": None
    }
    assert data["meta"]["hmac_verified"] is False
    assert data["contact_inbox"]["source_id"] == "chat-99"
    # messages: at most one, in the *push* form
    assert len(data["messages"]) == 1
    nested = data["messages"][0]
    assert nested["message_type"] == 0  # integer here
    assert nested["created_at"] == int(T1.timestamp())  # epoch here
    assert nested["conversation_id"] == chatwoot.conversation_display_id(conversation)
    assert nested["sender_type"] == "Contact"
    assert nested["status"] == "sent"


def test_conversation_messages_excludes_activity_and_private(world) -> None:
    activity = Message(
        conversation_id=world["conversation"].id,
        inbox_id=world["inbox"].id,
        content="Jane resolved it",
        message_type=MessageType.ACTIVITY.value,
        sender_type=SenderType.SYSTEM.value,
        created_at=T1,
        updated_at=T1,
    )
    data = chatwoot.serialize_conversation(world["conversation"], last_message=activity)
    assert data["messages"] == []

    note = Message(
        conversation_id=world["conversation"].id,
        inbox_id=world["inbox"].id,
        content="internal",
        message_type=MessageType.OUTGOING.value,
        private=True,
        sender_type=SenderType.USER.value,
        created_at=T1,
        updated_at=T1,
    )
    assert chatwoot.serialize_conversation(
        world["conversation"], last_message=note
    )["messages"] == []


def test_message_webhook_data_shape(world) -> None:
    data = chatwoot.serialize_message(
        world["message"],
        conversation=world["conversation"],
        inbox=world["inbox"],
        sender=world["contact"],
        contact=world["contact"],
        contact_inbox=world["link"],
    )
    assert set(data) == {
        "account", "additional_attributes", "content_attributes", "content_type",
        "content", "conversation", "created_at", "id", "inbox", "message_type",
        "private", "sender", "source_id",
    }
    # no status / conversation_id / inbox_id / updated_at at the top level
    for absent in ("status", "conversation_id", "inbox_id", "updated_at", "attachments"):
        assert absent not in data
    assert data["message_type"] == "incoming"  # string here
    assert data["created_at"] == "2024-05-01T12:05:00.123Z"  # ISO here
    assert data["inbox"] == {"id": world["inbox"].id, "name": "Support"}
    assert data["sender"]["email"] == "bob@example.com"
    assert "type" not in data["sender"]  # contact webhook_data has no type
    assert data["conversation"]["id"] == world["conversation"].id
    assert data["source_id"] == "tg-1"


def test_message_deleted_surfaces_as_content_attributes_deleted(world) -> None:
    world["message"].deleted_at = T1
    data = chatwoot.serialize_message(world["message"])
    assert data["content_attributes"]["deleted"] is True


def test_changed_attributes_is_array_of_single_key_objects() -> None:
    assert chatwoot.build_changed_attributes({"status": ("open", "resolved")}) == [
        {"status": {"previous_value": "open", "current_value": "resolved"}}
    ]
    assert chatwoot.build_changed_attributes({}) is None
    assert chatwoot.build_changed_attributes(None) is None


def test_webhook_sendable_filters_activity_only(world) -> None:
    message = world["message"]
    assert chatwoot.webhook_sendable(message) is True
    message.private = True
    assert chatwoot.webhook_sendable(message) is True  # private notes ARE sent
    message.message_type = MessageType.ACTIVITY.value
    assert chatwoot.webhook_sendable(message) is False


# ---------------------------------------------------------------------------
# Event envelopes
# ---------------------------------------------------------------------------
def test_conversation_created_is_flat_with_event_key(world) -> None:
    body = chatwoot.build_event("conversation_created", conversation=world["conversation"])
    assert body["event"] == "conversation_created"
    # No envelope: the conversation hash itself, with `event` merged in.
    assert "data" not in body
    assert body["status"] == "open" and body["inbox_id"] == world["inbox"].id
    assert "changed_attributes" not in body  # only updates carry it


def test_conversation_updated_carries_null_changed_attributes(world) -> None:
    body = chatwoot.build_event("conversation_updated", conversation=world["conversation"])
    assert body["changed_attributes"] is None

    body = chatwoot.build_event(
        "conversation_status_changed",
        conversation=world["conversation"],
        changes={"status": ("open", "resolved")},
    )
    assert body["event"] == "conversation_status_changed"
    assert body["changed_attributes"] == [
        {"status": {"previous_value": "open", "current_value": "resolved"}}
    ]


def test_typing_events_are_the_nested_ones(world) -> None:
    body = chatwoot.build_event(
        "conversation_typing_on",
        conversation=world["conversation"],
        user=world["agent"],
    )
    assert set(body) == {"event", "user", "conversation", "is_private"}
    assert body["user"]["type"] == "user"
    assert body["is_private"] is False
    off = chatwoot.build_event(
        "conversation_typing_off", conversation=world["conversation"], user=world["contact"]
    )
    assert off["event"] == "conversation_typing_off"
    assert "type" not in off["user"]  # contact webhook_data


def test_contact_and_inbox_events(world) -> None:
    body = chatwoot.build_event("contact_created", contact=world["contact"])
    assert body["event"] == "contact_created"
    assert "changed_attributes" not in body

    body = chatwoot.build_event(
        "contact_updated", contact=world["contact"], changes={"name": ("Bob", "Bobby")}
    )
    assert body["changed_attributes"] == [
        {"name": {"previous_value": "Bob", "current_value": "Bobby"}}
    ]

    body = chatwoot.build_event("inbox_updated", inbox=world["inbox"])
    assert body["event"] == "inbox_updated"
    assert body["account"] == chatwoot.serialize_account()
    assert "id" not in body and "name" not in body


def test_webwidget_triggered(world) -> None:
    body = chatwoot.build_event(
        "webwidget_triggered",
        contact_inbox=world["link"],
        contact=world["contact"],
        inbox=world["inbox"],
        conversation=world["conversation"],
        event_info={"referer": "https://example.com"},
    )
    assert body["event"] == "webwidget_triggered"
    assert body["source_id"] == "chat-99"
    assert body["event_info"] == {"referer": "https://example.com"}
    assert body["current_conversation"]["id"] == world["conversation"].id


def test_unknown_event_rejected() -> None:
    with pytest.raises(ValueError):
        chatwoot.build_event("message_deleted", message=None)


# ---------------------------------------------------------------------------
# Event mapping
# ---------------------------------------------------------------------------
def test_event_mapping_table() -> None:
    assert chatwoot.map_event("conversation.created", {}) == ["conversation_created"]
    assert chatwoot.map_event("conversation.updated", {}) == ["conversation_updated"]
    assert chatwoot.map_event("conversation.updated", {}, status_changed=True) == [
        "conversation_updated",
        "conversation_status_changed",
    ]
    assert chatwoot.map_event("conversation.typing", {"typing": True}) == [
        "conversation_typing_on"
    ]
    assert chatwoot.map_event("conversation.typing", {"typing": False}) == [
        "conversation_typing_off"
    ]
    assert chatwoot.map_event("message.created", {}) == ["message_created"]
    assert chatwoot.map_event("message.deleted", {}) == ["message_updated"]
    assert chatwoot.map_event("contact.updated", {}) == ["contact_updated"]
    assert chatwoot.map_event("inbox.updated", {}) == ["inbox_updated"]
    assert chatwoot.map_event("presence.updated", {}) == []


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
async def test_native_webhook_body_unchanged(db_session, world) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/native",
        subscriptions=["message.created"],
        secret="s3cret",
    )
    payload = {"message": {"id": world["message"].id}, "conversation_id": 1}
    await webhook_service._deliver_all("message.created", payload)

    assert len(POSTS) == 1
    post = POSTS[0]
    assert post["url"] == "https://example.com/native"
    assert set(_body()) == {"event", "timestamp", "data"}
    assert _body()["event"] == "message.created"
    assert _body()["data"] == payload
    assert post["headers"]["X-ChattySup-Event"] == "message.created"
    assert post["headers"]["User-Agent"] == "ChattySup-Webhook/1.0"
    assert "X-ChattySup-Signature" in post["headers"]
    assert "X-Chatwoot-Signature" not in post["headers"]


async def test_native_empty_subscriptions_still_means_all(db_session, world) -> None:
    await _add_hook(db_session, url="https://example.com/all", subscriptions=[])
    await webhook_service._deliver_all("contact.updated", {"contact": {"id": world["contact"].id}})
    assert len(POSTS) == 1
    assert _body()["event"] == "contact.updated"


async def test_native_never_receives_typing(db_session, world) -> None:
    await _add_hook(db_session, url="https://example.com/all", subscriptions=[])
    await webhook_service._deliver_all(
        "conversation.typing",
        {"conversation_id": world["conversation"].id, "typing": True, "actor": "user"},
    )
    assert POSTS == []


async def test_chatwoot_hook_gets_chatwoot_body_and_headers(db_session, world) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["message_created"],
        secret="cw-secret",
        payload_format="chatwoot",
    )
    await webhook_service._deliver_all(
        "message.created",
        {"message": {"id": world["message"].id}, "conversation_id": world["conversation"].id},
    )

    assert len(POSTS) == 1
    post, body = POSTS[0], _body()
    assert body["event"] == "message_created"
    assert body["message_type"] == "incoming"
    assert body["conversation"]["id"] == world["conversation"].id
    assert body["conversation"]["messages"][0]["message_type"] == 0
    assert body["inbox"] == {"id": world["inbox"].id, "name": "Support"}
    assert body["account"] == {"id": 1, "name": chatwoot.CHATWOOT_ACCOUNT_NAME}

    headers = post["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["X-Chatwoot-Delivery"]
    assert headers["X-Chatwoot-Signature"].startswith("sha256=")
    assert "X-ChattySup-Signature" not in headers
    assert post["timeout"] == webhook_service.CHATWOOT_TIMEOUT

    # signature covers "{timestamp}.{body}", not the body alone
    import hashlib
    import hmac

    expected = hmac.new(
        b"cw-secret",
        f"{headers['X-Chatwoot-Timestamp']}.".encode() + post["body"],
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Chatwoot-Signature"] == f"sha256={expected}"


async def test_chatwoot_subscription_filtering_uses_chatwoot_names(
    db_session, world
) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["message.created"],  # our name — meaningless for chatwoot
        payload_format="chatwoot",
    )
    await webhook_service._deliver_all(
        "message.created", {"message": {"id": world["message"].id}}
    )
    assert POSTS == []


async def test_chatwoot_hook_skips_activity_messages(db_session, world) -> None:
    async with TestSession() as session:
        activity = Message(
            conversation_id=world["conversation"].id,
            inbox_id=world["inbox"].id,
            content="Jane resolved this",
            message_type=MessageType.ACTIVITY.value,
            sender_type=SenderType.SYSTEM.value,
            created_at=T1,
            updated_at=T1,
        )
        session.add(activity)
        await session.commit()
        activity_id = activity.id

    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["message_created"],
        payload_format="chatwoot",
    )
    await webhook_service._deliver_all("message.created", {"message": {"id": activity_id}})
    assert POSTS == []


async def test_status_change_fans_out_to_two_chatwoot_events(db_session, world) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["conversation_updated", "conversation_status_changed"],
        payload_format="chatwoot",
    )
    conversation_id = world["conversation"].id
    await webhook_service._deliver_all(
        "conversation.created",
        {"conversation": {"id": conversation_id, "status": "open"}},
    )
    POSTS.clear()

    async with TestSession() as session:
        conversation = await session.get(Conversation, conversation_id)
        conversation.status = ConversationStatus.RESOLVED.value
        await session.commit()

    await webhook_service._deliver_all(
        "conversation.updated",
        {"conversation": {"id": conversation_id, "status": "resolved"}},
    )
    events = {_body(i)["event"] for i in range(len(POSTS))}
    assert events == {"conversation_updated", "conversation_status_changed"}
    changed = next(
        _body(i)["changed_attributes"]
        for i in range(len(POSTS))
        if _body(i)["event"] == "conversation_status_changed"
    )
    assert changed == [
        {"status": {"previous_value": "open", "current_value": "resolved"}}
    ]


async def test_conversation_update_without_status_change_emits_one_event(
    db_session, world
) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["conversation_updated", "conversation_status_changed"],
        payload_format="chatwoot",
    )
    payload = {"conversation": {"id": world["conversation"].id, "status": "open"}}
    await webhook_service._deliver_all("conversation.updated", payload)
    POSTS.clear()
    await webhook_service._deliver_all("conversation.updated", payload)
    assert len(POSTS) == 1
    assert _body()["event"] == "conversation_updated"
    assert _body()["changed_attributes"] is None


async def test_typing_reaches_chatwoot_hooks_only(db_session, world) -> None:
    await _add_hook(db_session, url="https://example.com/native", subscriptions=[])
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["conversation_typing_on"],
        payload_format="chatwoot",
    )
    await webhook_service._deliver_all(
        "conversation.typing",
        {
            "conversation_id": world["conversation"].id,
            "typing": True,
            "actor": "user",
            "user_id": world["agent"].id,
        },
    )
    assert [p["url"] for p in POSTS] == ["https://example.com/cw"]
    assert set(_body()) == {"event", "user", "conversation", "is_private"}
    assert _body()["user"]["type"] == "user"


async def test_message_deleted_becomes_message_updated(db_session, world) -> None:
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["message_updated"],
        payload_format="chatwoot",
    )
    async with TestSession() as session:
        message = await session.get(Message, world["message"].id)
        message.deleted_at = T1
        await session.commit()

    await webhook_service._deliver_all(
        "message.deleted",
        {"message_id": world["message"].id, "conversation_id": world["conversation"].id},
    )
    assert len(POSTS) == 1
    assert _body()["event"] == "message_updated"
    assert _body()["content_attributes"]["deleted"] is True


async def test_both_formats_delivered_side_by_side(db_session, world) -> None:
    await _add_hook(
        db_session, url="https://example.com/native", subscriptions=["message.created"]
    )
    await _add_hook(
        db_session,
        url="https://example.com/cw",
        subscriptions=["message_created"],
        payload_format="chatwoot",
    )
    await webhook_service._deliver_all(
        "message.created", {"message": {"id": world["message"].id}}
    )
    by_url = {p["url"]: p for p in POSTS}
    assert set(by_url) == {"https://example.com/native", "https://example.com/cw"}
    import json

    assert json.loads(by_url["https://example.com/native"]["body"])["event"] == (
        "message.created"
    )
    assert json.loads(by_url["https://example.com/cw"]["body"])["event"] == (
        "message_created"
    )


async def test_webhook_payload_format_defaults_to_native(db_session) -> None:
    hook = await _add_hook(db_session, url="https://example.com/x", subscriptions=[])
    assert hook.payload_format == "native"
