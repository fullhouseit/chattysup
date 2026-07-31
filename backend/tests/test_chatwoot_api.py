"""End-to-end coverage of the Chatwoot-compatible API surface.

Everything runs through the real ASGI app: an API-channel inbox is created with
our native admin API, a customer pushes a contact / conversation / message
through the **Client API**, the result is asserted in *our* native API too, and
an agent reply sent through the **Application API** is captured on the way out
to the inbox ``webhook_url`` and checked field for field against Chatwoot's
``message_created`` body — including the HMAC signature.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.channels.api_channel import channel as api_channel

#: Every outbound webhook delivery the API channel attempted.
DELIVERIES: list[dict[str, Any]] = []

WEBHOOK_URL = "https://hooks.example.test/chatwoot"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
class _RecordingClient:
    """Stand-in for ``httpx.AsyncClient`` inside the API channel only."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> "_RecordingClient":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def post(
        self, url: str, content: bytes | None = None, headers: dict | None = None
    ) -> httpx.Response:
        DELIVERIES.append(
            {"url": url, "body": content or b"", "headers": dict(headers or {})}
        )
        return httpx.Response(
            200, json={}, request=httpx.Request("POST", url)
        )

    async def get(self, url: str) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", url))


@pytest.fixture(autouse=True)
def capture_deliveries(monkeypatch) -> None:
    DELIVERIES.clear()
    monkeypatch.setattr(
        api_channel,
        "httpx",
        SimpleNamespace(
            AsyncClient=_RecordingClient,
            HTTPError=httpx.HTTPError,
            Response=httpx.Response,
        ),
    )


@pytest.fixture
async def raw_client() -> Any:
    """A client rooted at ``/`` — the Chatwoot paths are not under /api/v1."""
    transport = ASGITransport(app=__import__("app.main", fromlist=["app"]).app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def api_inbox(client: AsyncClient, admin: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        "/inboxes",
        headers=admin["headers"],
        json={
            "name": "Programmable",
            "channel_type": "api",
            "mode": "webhook",
            "config": {"webhook_url": WEBHOOK_URL},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def access_token(client: AsyncClient, admin: dict[str, Any]) -> str:
    response = await client.post(
        "/api_tokens", headers=admin["headers"], json={"name": "chatwoot"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


async def _identifier(client: AsyncClient, admin: dict[str, Any], inbox_id: int) -> str:
    """The inbox identifier, read back with secrets revealed."""
    response = await client.get(f"/inboxes/{inbox_id}", headers=admin["headers"])
    assert response.status_code == 200, response.text
    return response.json()["config"]["inbox_identifier"]


async def _hmac_secret(db_session, inbox_id: int) -> str:
    from app.models import Inbox

    inbox = await db_session.get(Inbox, inbox_id)
    return inbox.config["secret"]


# ---------------------------------------------------------------------------
# Channel registration
# ---------------------------------------------------------------------------
async def test_api_channel_is_registered_and_honest(client: AsyncClient) -> None:
    channels = (await client.get("/health")).json()["channels"]
    assert "api" in channels

    from app.channels import get_channel_class

    described = get_channel_class("api").describe()
    assert described["display_name"] == "API"
    assert described["supports_webhook"] is True
    assert described["supports_polling"] is False
    assert described["supports_proxy"] is False
    assert "reactions" not in described["capabilities"]


async def test_creating_an_api_inbox_mints_three_distinct_tokens(
    client: AsyncClient, admin: dict[str, Any], api_inbox: dict[str, Any], db_session
) -> None:
    from app.models import Inbox

    inbox = await db_session.get(Inbox, api_inbox["id"])
    config = inbox.config
    assert config["webhook_url"] == WEBHOOK_URL
    # inbox_identifier (public), hmac_token (inbound identity), secret (outbound
    # signature) — three different jobs, three different tokens.
    assert len({config["inbox_identifier"], config["hmac_token"], config["secret"]}) == 3
    # Pinned to the inbox row so a config edit cannot rotate a public URL segment.
    assert config["inbox_identifier"] == inbox.webhook_token

    # The two real secrets never leave the API in the clear.
    detail = await client.get(f"/inboxes/{api_inbox['id']}", headers=admin["headers"])
    assert detail.json()["config"]["hmac_token"] != config["hmac_token"]

    # The identifier survives an update; rotating it would break every client.
    updated = await client.patch(
        f"/inboxes/{api_inbox['id']}",
        headers=admin["headers"],
        json={"config": {"webhook_url": "https://hooks.example.test/other"}},
    )
    assert updated.status_code == 200, updated.text
    again = await client.get(f"/inboxes/{api_inbox['id']}", headers=admin["headers"])
    assert again.json()["config"]["inbox_identifier"] == config["inbox_identifier"]


# ---------------------------------------------------------------------------
# Client (Public) API
# ---------------------------------------------------------------------------
async def test_client_api_round_trip_lands_in_the_native_api(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])

    described = await raw_client.get(f"/public/api/v1/inboxes/{identifier}")
    assert described.status_code == 200, described.text
    assert described.json()["identifier"] == identifier
    assert described.json()["identity_validation_enabled"] is False

    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts",
        json={"name": "Bob", "email": "bob@example.com", "phone_number": "+15551234567"},
    )
    # Chatwoot answers 200 on every public create — never 201.
    assert created.status_code == 200, created.text
    contact = created.json()
    assert set(contact) == {"source_id", "pubsub_token", "id", "name", "email", "phone_number"}
    assert contact["name"] == "Bob"
    source_id = contact["source_id"]

    base = f"/public/api/v1/inboxes/{identifier}/contacts/{source_id}"
    conversation = await raw_client.post(f"{base}/conversations", json={})
    assert conversation.status_code == 200, conversation.text
    body = conversation.json()
    assert body["status"] == "open"
    assert body["messages"] == []
    display_id = body["id"]

    message = await raw_client.post(
        f"{base}/conversations/{display_id}/messages",
        json={"content": "Hi, I need help", "echo_id": "tmp-1"},
    )
    assert message.status_code == 200, message.text
    payload = message.json()
    # message_type is the INTEGER here (0 = incoming) and created_at epoch seconds.
    assert payload["message_type"] == 0
    assert isinstance(payload["created_at"], int)
    assert payload["conversation_id"] == display_id
    assert payload["sender"]["type"] == "contact"
    assert payload["content_attributes"]["echo_id"] == "tmp-1"

    listing = await raw_client.get(f"{base}/conversations/{display_id}/messages")
    assert [m["content"] for m in listing.json()] == ["Hi, I need help"]

    # …and the very same data is visible through OUR native API.
    native = await client.get("/conversations", headers=admin["headers"])
    assert native.status_code == 200, native.text
    thread = native.json()["data"][0]
    assert thread["id"] == display_id
    assert thread["contact"]["name"] == "Bob"

    native_messages = await client.get(
        f"/conversations/{display_id}/messages", headers=admin["headers"]
    )
    contents = [m["content"] for m in native_messages.json()]
    assert "Hi, I need help" in contents


async def test_unknown_inbox_identifier_is_a_chatwoot_404(
    raw_client: AsyncClient, api_inbox: dict[str, Any]
) -> None:
    response = await raw_client.post(
        "/public/api/v1/inboxes/nope-nope-nope/contacts", json={"name": "Ghost"}
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Resource could not be found"}


async def test_unknown_contact_source_id_is_a_chatwoot_404(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    response = await raw_client.get(
        f"/public/api/v1/inboxes/{identifier}/contacts/not-a-source-id"
    )
    assert response.status_code == 404
    assert response.json() == {"error": "Resource could not be found"}


async def test_hmac_identity_validation(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], db_session,
) -> None:
    await client.patch(
        f"/inboxes/{api_inbox['id']}",
        headers=admin["headers"],
        json={"config": {"webhook_url": WEBHOOK_URL, "hmac_mandatory": True}},
    )
    from app.models import Inbox

    inbox = await db_session.get(Inbox, api_inbox["id"])
    await db_session.refresh(inbox)
    identifier = inbox.config["inbox_identifier"]
    hmac_token = inbox.config["hmac_token"]

    bad = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts",
        json={"identifier": "user-42", "identifier_hash": "deadbeef"},
    )
    assert bad.status_code == 401
    assert bad.json()["error"].startswith("HMAC failed")

    good_hash = hmac.new(
        hmac_token.encode(), b"user-42", hashlib.sha256
    ).hexdigest()
    good = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts",
        json={"identifier": "user-42", "identifier_hash": good_hash, "name": "Bob"},
    )
    assert good.status_code == 200, good.text


# ---------------------------------------------------------------------------
# Application API
# ---------------------------------------------------------------------------
async def test_application_api_rejects_bad_tokens_like_chatwoot(
    raw_client: AsyncClient, api_inbox: dict[str, Any]
) -> None:
    for headers in ({}, {"api_access_token": "cs_nonsense"}, {"Authorization": "Bearer nope"}):
        response = await raw_client.get("/api/v1/accounts/1/conversations", headers=headers)
        assert response.status_code == 401, headers
        assert response.json() == {"error": "Invalid Access Token"}


async def test_application_api_lists_conversations_and_inboxes(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], access_token: str,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}

    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    source_id = created.json()["source_id"]
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{source_id}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    await raw_client.post(
        f"{base}/conversations/{display_id}/messages", json={"content": "Hello"}
    )

    inboxes = await raw_client.get("/api/v1/accounts/1/inboxes", headers=headers)
    assert inboxes.status_code == 200, inboxes.text
    entry = next(i for i in inboxes.json()["payload"] if i["id"] == api_inbox["id"])
    assert entry["channel_type"] == "Channel::Api"
    assert entry["inbox_identifier"] == identifier

    listing = await raw_client.get("/api/v1/accounts/1/conversations", headers=headers)
    assert listing.status_code == 200, listing.text
    data = listing.json()["data"]
    assert data["meta"]["all_count"] == 1
    thread = data["payload"][0]
    assert thread["id"] == display_id
    assert thread["meta"]["channel"] == "Channel::Api"
    assert thread["meta"]["sender"]["name"] == "Bob"
    assert isinstance(thread["updated_at"], float)

    show = await raw_client.get(
        f"/api/v1/accounts/1/conversations/{display_id}", headers=headers
    )
    assert show.json()["id"] == display_id

    messages = await raw_client.get(
        f"/api/v1/accounts/1/conversations/{display_id}/messages", headers=headers
    )
    assert messages.status_code == 200, messages.text
    assert messages.json()["payload"][0]["message_type"] == 0

    contacts = await raw_client.get("/api/v1/accounts/1/contacts", headers=headers)
    assert contacts.json()["meta"]["count"] == 1
    search = await raw_client.get(
        "/api/v1/accounts/1/contacts/search", headers=headers, params={"q": "Bob"}
    )
    assert [c["name"] for c in search.json()["payload"]] == ["Bob"]
    assert (
        await raw_client.get("/api/v1/accounts/1/contacts/search", headers=headers)
    ).status_code == 422


async def test_toggle_status_and_assignment(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], access_token: str,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]

    toggled = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{display_id}/toggle_status",
        headers=headers,
        json={"status": "resolved"},
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["payload"] == {
        "success": True,
        "current_status": "resolved",
        "conversation_id": display_id,
    }

    assigned = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{display_id}/assignments",
        headers=headers,
        json={"assignee_id": admin["user"]["id"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["id"] == admin["user"]["id"]


# ---------------------------------------------------------------------------
# Outbound delivery
# ---------------------------------------------------------------------------
async def test_agent_reply_is_posted_to_the_inbox_webhook_url(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], access_token: str, db_session,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}

    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts",
        json={"name": "Bob", "email": "bob@example.com"},
    )
    source_id = created.json()["source_id"]
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{source_id}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    await raw_client.post(
        f"{base}/conversations/{display_id}/messages", json={"content": "Hi"}
    )
    DELIVERIES.clear()

    reply = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{display_id}/messages",
        headers=headers,
        json={"content": "Sure, I can help with that"},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["message_type"] == 1  # outgoing, as an integer
    assert reply.json()["private"] is False

    assert len(DELIVERIES) == 1, DELIVERIES
    delivery = DELIVERIES[0]
    assert delivery["url"] == WEBHOOK_URL

    # --- headers ------------------------------------------------------
    sent = delivery["headers"]
    assert sent["Content-Type"] == "application/json"
    assert sent["Accept"] == "application/json"
    assert len(sent["X-Chatwoot-Delivery"]) == 36
    secret = await _hmac_secret(db_session, api_inbox["id"])
    expected = hmac.new(
        secret.encode(),
        f"{sent['X-Chatwoot-Timestamp']}.".encode() + delivery["body"],
        hashlib.sha256,
    ).hexdigest()
    # Signed over "{timestamp}.{raw_body}", prefixed with a literal sha256=.
    assert sent["X-Chatwoot-Signature"] == f"sha256={expected}"

    # --- body ---------------------------------------------------------
    body = json.loads(delivery["body"])
    assert body["event"] == "message_created"
    assert set(body) == {
        "account",
        "additional_attributes",
        "content_attributes",
        "content_type",
        "content",
        "conversation",
        "created_at",
        "id",
        "inbox",
        "message_type",
        "private",
        "sender",
        "source_id",
        "event",
    }
    assert body["content"] == "Sure, I can help with that"
    # String here, integer inside conversation.messages[0] — reproduced on purpose.
    assert body["message_type"] == "outgoing"
    assert body["created_at"].endswith("Z") and "T" in body["created_at"]
    assert body["account"] == {"id": 1, "name": "ChattySup"}
    assert body["inbox"] == {"id": api_inbox["id"], "name": "Programmable"}
    assert body["sender"] == {
        "id": admin["user"]["id"],
        "name": admin["user"]["name"],
        "email": admin["user"]["email"],
        "type": "user",
    }

    conversation = body["conversation"]
    assert conversation["id"] == display_id
    assert conversation["channel"] == "Channel::Api"
    assert conversation["status"] == "open"
    assert conversation["meta"]["sender"]["type"] == "contact"
    assert conversation["contact_inbox"]["source_id"] == source_id
    assert isinstance(conversation["created_at"], int)
    assert isinstance(conversation["updated_at"], float)
    assert conversation["messages"][0]["message_type"] == 1
    assert isinstance(conversation["messages"][0]["created_at"], int)

    # The remote returned no id, so our own message id becomes the source_id.
    stored = await raw_client.get(
        f"/api/v1/accounts/1/conversations/{display_id}/messages", headers=headers
    )
    outgoing = next(m for m in stored.json()["payload"] if m["message_type"] == 1)
    assert outgoing["source_id"] == str(body["id"])
    assert outgoing["status"] == "sent"


async def test_private_notes_are_never_pushed_upstream(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], access_token: str,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    DELIVERIES.clear()

    note = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{display_id}/messages",
        headers=headers,
        json={"content": "internal", "private": True},
    )
    assert note.status_code == 200, note.text
    assert note.json()["private"] is True
    assert DELIVERIES == []


# ---------------------------------------------------------------------------
# Webhook subscriptions
# ---------------------------------------------------------------------------
async def test_chatwoot_webhook_crud(
    raw_client: AsyncClient, api_inbox: dict[str, Any], access_token: str
) -> None:
    headers = {"api_access_token": access_token}

    empty = await raw_client.post(
        "/api/v1/accounts/1/webhooks",
        headers=headers,
        json={"webhook": {"url": "https://example.test/hook", "subscriptions": []}},
    )
    assert empty.status_code == 422
    assert "message" in empty.json()

    bogus = await raw_client.post(
        "/api/v1/accounts/1/webhooks",
        headers=headers,
        json={"webhook": {"url": "https://example.test/hook", "subscriptions": ["nope"]}},
    )
    assert bogus.status_code == 422

    created = await raw_client.post(
        "/api/v1/accounts/1/webhooks",
        headers=headers,
        json={
            "webhook": {
                "url": "https://example.test/hook",
                "name": "mine",
                "subscriptions": ["message_created", "conversation_created"],
            }
        },
    )
    assert created.status_code == 200, created.text
    hook = created.json()["payload"]["webhook"]
    assert hook["subscriptions"] == ["message_created", "conversation_created"]
    assert hook["secret"]  # generated server-side, never supplied by the client
    assert "webhook_type" not in hook and "created_at" not in hook

    listing = await raw_client.get("/api/v1/accounts/1/webhooks", headers=headers)
    assert [h["id"] for h in listing.json()["payload"]["webhooks"]] == [hook["id"]]

    updated = await raw_client.patch(
        f"/api/v1/accounts/1/webhooks/{hook['id']}",
        headers=headers,
        json={"webhook": {"subscriptions": ["message_updated"]}},
    )
    assert updated.json()["payload"]["webhook"]["subscriptions"] == ["message_updated"]

    deleted = await raw_client.delete(
        f"/api/v1/accounts/1/webhooks/{hook['id']}", headers=headers
    )
    assert deleted.status_code == 200
    assert deleted.content == b""


# ---------------------------------------------------------------------------
# Conversation targeting
# ---------------------------------------------------------------------------
async def test_client_api_message_lands_in_the_conversation_in_the_url(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], db_session,
) -> None:
    """The path names the conversation; the write must honour it."""
    from app.models import Conversation, Message

    identifier = await _identifier(client, admin, api_inbox["id"])
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    source_id = created.json()["source_id"]
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{source_id}"

    first = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]

    # A second, *newer* conversation for the same contact. The first is resolved
    # and stale, so "most recently active" would pick the second one.
    async with __import__("tests.conftest", fromlist=["TestSession"]).TestSession() as s:
        stale = await s.get(Conversation, first)
        stale.status = "resolved"
        from app.db import utcnow
        from datetime import timedelta

        stale.last_activity_at = utcnow() - timedelta(days=30)
        stale.resolved_at = utcnow() - timedelta(days=30)
        newer = Conversation(
            inbox_id=stale.inbox_id,
            contact_id=stale.contact_id,
            contact_inbox_id=stale.contact_inbox_id,
            source_id=stale.source_id,
            status="open",
            last_activity_at=utcnow(),
        )
        s.add(newer)
        await s.commit()
        newer_id = newer.id

    assert newer_id != first
    posted = await raw_client.post(
        f"{base}/conversations/{first}/messages", json={"content": "into the old one"}
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["conversation_id"] == first

    async with __import__("tests.conftest", fromlist=["TestSession"]).TestSession() as s:
        row = await s.get(Message, posted.json()["id"])
        assert row.conversation_id == first, "message was filed under another thread"


# ---------------------------------------------------------------------------
# Outbound payload fidelity for every producer
# ---------------------------------------------------------------------------
async def test_native_agent_reply_produces_a_complete_chatwoot_payload(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    """The native agent UI is not the Application API — it must deliver too."""
    identifier = await _identifier(client, admin, api_inbox["id"])
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    await raw_client.post(f"{base}/conversations/{display_id}/messages", json={"content": "Hi"})
    DELIVERIES.clear()

    # …posted through OUR native API, which lends no ambient session of its own.
    reply = await client.post(
        f"/conversations/{display_id}/messages",
        headers=admin["headers"],
        data={"content": "Native reply"},
    )
    assert reply.status_code == 201, reply.text

    assert len(DELIVERIES) == 1, DELIVERIES
    body = json.loads(DELIVERIES[0]["body"])
    assert body["event"] == "message_created"
    assert body["id"] == reply.json()["id"]
    assert isinstance(body["id"], int)
    assert body["created_at"] and body["created_at"].endswith("Z")
    assert body["message_type"] == "outgoing"
    assert body["sender"] == {
        "id": admin["user"]["id"],
        "name": admin["user"]["name"],
        "email": admin["user"]["email"],
        "type": "user",
    }
    nested = body["conversation"]["messages"][0]
    assert nested["id"] == body["id"]
    assert isinstance(nested["created_at"], int) and nested["created_at"] > 0

    # The stored upstream id is the message id, not a delivery UUID.
    assert reply.json()["source_id"] == str(body["id"])


async def test_retry_delivers_the_message_it_was_asked_to_retry(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    from app.models import Message

    identifier = await _identifier(client, admin, api_inbox["id"])
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]

    posted = await client.post(
        f"/conversations/{display_id}/messages",
        headers=admin["headers"],
        data={"content": "older"},
    )
    assert posted.status_code == 201, posted.text
    older = posted.json()

    # Strip its upstream id and mark it failed, then add a newer undelivered one.
    from .conftest import TestSession

    async with TestSession() as s:
        row = await s.get(Message, older["id"])
        row.source_id = None
        row.status = "failed"
        newer = Message(
            conversation_id=display_id,
            inbox_id=row.inbox_id,
            content="newer, still undelivered",
            message_type="outgoing",
            sender_type="user",
            sender_id=admin["user"]["id"],
            status="pending",
        )
        s.add(newer)
        await s.commit()

    DELIVERIES.clear()
    retried = await client.post(
        f"/messages/{older['id']}/retry", headers=admin["headers"]
    )
    assert retried.status_code == 200, retried.text
    assert len(DELIVERIES) == 1, DELIVERIES
    body = json.loads(DELIVERIES[0]["body"])
    assert body["id"] == older["id"]
    assert body["content"] == "older"


async def test_delivery_metadata_never_leaks_into_content_attributes(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], access_token: str,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]

    reply = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{display_id}/messages",
        headers=headers,
        json={"content": "hello"},
    )
    assert reply.status_code == 200, reply.text
    attributes = reply.json()["content_attributes"]
    assert "api" not in attributes
    assert WEBHOOK_URL not in json.dumps(attributes)

    # …and it is not republished to third parties either.
    body = json.loads(DELIVERIES[-1]["body"])
    assert WEBHOOK_URL not in json.dumps(body)


# ---------------------------------------------------------------------------
# The public inbox identifier is permanent
# ---------------------------------------------------------------------------
async def test_inbox_identifier_survives_a_mode_switch(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])

    switched = await client.patch(
        f"/inboxes/{api_inbox['id']}",
        headers=admin["headers"],
        json={"mode": "polling", "config": {"webhook_url": WEBHOOK_URL}},
    )
    assert switched.status_code == 200, switched.text
    assert await _identifier(client, admin, api_inbox["id"]) == identifier

    # …and the Client API URL still resolves.
    described = await raw_client.get(f"/public/api/v1/inboxes/{identifier}")
    assert described.status_code == 200, described.text

    back = await client.patch(
        f"/inboxes/{api_inbox['id']}",
        headers=admin["headers"],
        json={"mode": "webhook", "config": {"webhook_url": WEBHOOK_URL}},
    )
    assert back.status_code == 200, back.text
    assert await _identifier(client, admin, api_inbox["id"]) == identifier


# ---------------------------------------------------------------------------
# Delivery receipts, inbox provisioning and the signing secret
# ---------------------------------------------------------------------------
async def test_message_status_update_is_api_inbox_only(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any], inbox: dict[str, Any], access_token: str,
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    headers = {"api_access_token": access_token}
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    reply = (
        await raw_client.post(
            f"/api/v1/accounts/1/conversations/{display_id}/messages",
            headers=headers,
            json={"content": "hello"},
        )
    ).json()

    updated = await raw_client.patch(
        f"/api/v1/accounts/1/conversations/{display_id}/messages/{reply['id']}",
        headers=headers,
        json={"status": "delivered"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "delivered"

    failed = await raw_client.patch(
        f"/api/v1/accounts/1/conversations/{display_id}/messages/{reply['id']}",
        headers=headers,
        json={"status": "failed", "external_error": "carrier rejected"},
    )
    assert failed.json()["status"] == "failed"

    bogus = await raw_client.patch(
        f"/api/v1/accounts/1/conversations/{display_id}/messages/{reply['id']}",
        headers=headers,
        json={"status": "teleported"},
    )
    assert bogus.status_code == 422

    # A non-API inbox answers 403, exactly like ``ensure_api_inbox``.
    other = await raw_client.post(
        "/api/v1/accounts/1/conversations",
        headers=headers,
        json={"inbox_id": inbox["id"], "contact_id": 1, "source_id": "chat-1"},
    )
    assert other.status_code == 200, other.text
    other_id = other.json()["id"]
    note = await raw_client.post(
        f"/api/v1/accounts/1/conversations/{other_id}/messages",
        headers=headers,
        json={"content": "note", "private": True},
    )
    refused = await raw_client.patch(
        f"/api/v1/accounts/1/conversations/{other_id}/messages/{note.json()['id']}",
        headers=headers,
        json={"status": "read"},
    )
    assert refused.status_code == 403
    assert refused.json() == {
        "error": "Message status update is only allowed for API inboxes"
    }


async def test_inbox_provisioning_and_secret_rotation(
    raw_client: AsyncClient, access_token: str
) -> None:
    headers = {"api_access_token": access_token}
    created = await raw_client.post(
        "/api/v1/accounts/1/inboxes",
        headers=headers,
        json={
            "name": "Provisioned",
            "channel": {
                "type": "api",
                "webhook_url": "https://hooks.example.test/new",
                "additional_attributes": {"agent_reply_time_window": 24},
            },
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["channel_type"] == "Channel::Api"
    assert body["webhook_url"] == "https://hooks.example.test/new"
    assert body["inbox_identifier"] and body["hmac_token"]
    # A client verifying X-Chatwoot-Signature must be able to read the secret.
    assert body["secret"]
    assert body["additional_attributes"] == {"agent_reply_time_window": 24}

    # The Client API answers on the freshly minted identifier.
    described = await raw_client.get(
        f"/public/api/v1/inboxes/{body['inbox_identifier']}"
    )
    assert described.status_code == 200, described.text

    rotated = await raw_client.post(
        f"/api/v1/accounts/1/inboxes/{body['id']}/reset_secret", headers=headers
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"] != body["secret"]
    # Rotating the signing secret must not touch the public identifier.
    assert rotated.json()["inbox_identifier"] == body["inbox_identifier"]

    bogus = await raw_client.post(
        "/api/v1/accounts/1/inboxes",
        headers=headers,
        json={"name": "Nope", "channel": {"type": "carrier_pigeon"}},
    )
    assert bogus.status_code == 422


async def test_public_csat_message_update(
    client: AsyncClient, raw_client: AsyncClient, admin: dict[str, Any],
    api_inbox: dict[str, Any],
) -> None:
    identifier = await _identifier(client, admin, api_inbox["id"])
    created = await raw_client.post(
        f"/public/api/v1/inboxes/{identifier}/contacts", json={"name": "Bob"}
    )
    base = f"/public/api/v1/inboxes/{identifier}/contacts/{created.json()['source_id']}"
    display_id = (await raw_client.post(f"{base}/conversations", json={})).json()["id"]
    message = (
        await raw_client.post(
            f"{base}/conversations/{display_id}/messages", json={"content": "hi"}
        )
    ).json()

    updated = await raw_client.patch(
        f"{base}/conversations/{display_id}/messages/{message['id']}",
        json={"submitted_values": {"csat_survey_response": {"rating": 5}}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["content_attributes"]["submitted_values"] == {
        "csat_survey_response": {"rating": 5}
    }

    from datetime import timedelta

    from app.db import utcnow
    from app.models import Message

    from .conftest import TestSession

    async with TestSession() as s:
        row = await s.get(Message, message["id"])
        row.created_at = utcnow() - timedelta(days=15)
        await s.commit()

    stale = await raw_client.patch(
        f"{base}/conversations/{display_id}/messages/{message['id']}",
        json={"submitted_values": {"csat_survey_response": {"rating": 1}}},
    )
    assert stale.status_code == 422
    assert stale.json() == {
        "error": "You cannot update the CSAT survey after 14 days"
    }


# ---------------------------------------------------------------------------
# The Client API is JSON-only
# ---------------------------------------------------------------------------
async def test_unknown_public_api_paths_answer_json_not_the_spa(
    raw_client: AsyncClient,
) -> None:
    for path in ("/public/api/v1/inboxes", "/public/api/v1/bogus", "/public"):
        response = await raw_client.get(path)
        assert response.status_code == 404, f"{path}: {response.status_code}"
        assert response.headers["content-type"].startswith("application/json"), path
        assert response.json() == {"error": "Resource could not be found"}, path


# ---------------------------------------------------------------------------
# The native API is untouched
# ---------------------------------------------------------------------------
async def test_native_routes_are_not_shadowed(
    client: AsyncClient, admin: dict[str, Any], api_inbox: dict[str, Any]
) -> None:
    for path in ("/inboxes", "/conversations", "/contacts", "/webhooks"):
        response = await client.get(path, headers=admin["headers"])
        assert response.status_code == 200, f"{path}: {response.text}"
    assert (await client.get("/health")).status_code == 200
