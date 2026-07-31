"""End-to-end coverage of the REST contract using an in-memory database."""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from .conftest import SENT


async def _open_conversation(
    client: AsyncClient, inbox: dict[str, Any], headers: dict[str, str], **payload: Any
) -> dict[str, Any]:
    """Drive a message through the public inbound webhook and return the thread."""
    body = {"chat_id": "555", "text": "Hello there", "message_id": "m1", **payload}
    response = await client.post(inbox["webhook_url"].removeprefix("/api/v1"), json=body)
    assert response.status_code == 200, response.text

    listing = await client.get("/conversations", headers=headers)
    assert listing.status_code == 200, listing.text
    return listing.json()["data"][0]


# ---------------------------------------------------------------------------
# Health & bootstrap
# ---------------------------------------------------------------------------
async def test_health_lists_registered_channels(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert "dummy" in response.json()["channels"]


async def test_first_registration_creates_an_admin(client: AsyncClient) -> None:
    config = (await client.get("/auth/config")).json()
    assert config["has_users"] is False
    assert config["registration_enabled"] is True

    response = await client.post(
        "/auth/register",
        json={"name": "Root", "email": "root@example.com", "password": "supersecret"},
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"

    # Starter labels and canned responses were seeded.
    headers = {"Authorization": f"Bearer {response.json()['token']}"}
    labels = (await client.get("/labels", headers=headers)).json()
    assert {label["title"] for label in labels} >= {"billing", "lead"}


async def test_second_registration_is_blocked(
    client: AsyncClient, admin: dict[str, Any]
) -> None:
    response = await client.post(
        "/auth/register",
        json={"name": "Agent", "email": "agent@example.com", "password": "supersecret"},
    )
    assert response.status_code == 403


async def test_login_and_me(client: AsyncClient, admin: dict[str, Any]) -> None:
    bad = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "nope"}
    )
    assert bad.status_code == 401

    response = await client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "supersecret"},
    )
    assert response.status_code == 200
    token = response.json()["token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"

    assert (await client.get("/auth/me")).status_code in (200, 401)


async def test_unauthenticated_access_is_rejected(client: AsyncClient) -> None:
    fresh = AsyncClient(transport=client._transport, base_url=str(client.base_url))
    async with fresh:
        assert (await fresh.get("/conversations")).status_code == 401


# ---------------------------------------------------------------------------
# Inboxes
# ---------------------------------------------------------------------------
async def test_inbox_crud_with_a_registered_channel(
    client: AsyncClient, admin: dict[str, Any]
) -> None:
    channels = (await client.get("/channels", headers=admin["headers"])).json()
    assert any(c["key"] == "dummy" for c in channels)

    created = await client.post(
        "/inboxes",
        headers=admin["headers"],
        json={
            "name": "Support",
            "channel_type": "dummy",
            "mode": "webhook",
            "config": {"token": "s3cret", "note": "hi"},
        },
    )
    assert created.status_code == 201, created.text
    inbox = created.json()
    assert inbox["connection_status"] == "connected"
    assert inbox["webhook_url"] and "/webhooks/dummy/" in inbox["webhook_url"]
    assert inbox["config"]["token"] == "••••••••"  # secret is masked

    # The mask must not overwrite the stored secret.
    patched = await client.patch(
        f"/inboxes/{inbox['id']}",
        headers=admin["headers"],
        json={"name": "Support EU", "config": {"token": "••••••••", "note": "bye"}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Support EU"

    detail = await client.get(f"/inboxes/{inbox['id']}", headers=admin["headers"])
    assert detail.json()["config"]["note"] == "bye"

    tested = await client.post(
        f"/inboxes/{inbox['id']}/test", headers=admin["headers"]
    )
    assert tested.json() == {"status": "ok", "result": {"status": "ok", "bot": "dummy"}}

    missing_config = await client.post(
        "/inboxes",
        headers=admin["headers"],
        json={"name": "Broken", "channel_type": "dummy", "config": {}},
    )
    assert missing_config.status_code == 422

    members = await client.put(
        f"/inboxes/{inbox['id']}/members",
        headers=admin["headers"],
        json={"user_ids": [admin["user"]["id"]]},
    )
    assert members.json() == {"user_ids": [admin["user"]["id"]]}

    deleted = await client.delete(
        f"/inboxes/{inbox['id']}", headers=admin["headers"]
    )
    assert deleted.status_code == 204
    assert (await client.get("/inboxes", headers=admin["headers"])).json() == []


# ---------------------------------------------------------------------------
# Inbound webhook & conversations
# ---------------------------------------------------------------------------
async def test_inbound_webhook_creates_conversation_and_contact(
    client: AsyncClient, admin: dict[str, Any], inbox: dict[str, Any]
) -> None:
    conversation = await _open_conversation(client, inbox, admin["headers"])
    assert conversation["contact"]["name"] == "Tester"
    assert conversation["status"] == "open"
    assert conversation["last_message"]["content"] == "Hello there"
    assert conversation["unread_count"] == 1

    messages = await client.get(
        f"/conversations/{conversation['id']}/messages", headers=admin["headers"]
    )
    assert [m["message_type"] for m in messages.json()] == ["incoming"]

    unknown = await client.post("/webhooks/dummy/nope", json={"chat_id": "1"})
    assert unknown.status_code == 404


async def test_conversation_list_filters(
    client: AsyncClient, admin: dict[str, Any], inbox: dict[str, Any]
) -> None:
    first = await _open_conversation(client, inbox, admin["headers"])
    await client.post(
        inbox["webhook_url"].removeprefix("/api/v1"),
        json={"chat_id": "777", "name": "Bob", "text": "Billing question", "message_id": "m2"},
    )

    everything = (await client.get("/conversations", headers=admin["headers"])).json()
    assert everything["meta"]["total"] == 2
    assert everything["meta"]["counts"] == {"all": 2, "mine": 0, "unassigned": 2}

    # Search hits the contact name …
    by_name = (
        await client.get("/conversations?q=Bob", headers=admin["headers"])
    ).json()
    assert by_name["meta"]["total"] == 1

    # … and the message body.
    by_body = (
        await client.get("/conversations?q=Billing", headers=admin["headers"])
    ).json()
    assert by_body["meta"]["total"] == 1

    # Assignment moves the conversation into the "mine" bucket.
    assigned = await client.patch(
        f"/conversations/{first['id']}",
        headers=admin["headers"],
        json={"assignee_id": admin["user"]["id"], "priority": "high"},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assignee_id"] == admin["user"]["id"]

    mine = (
        await client.get("/conversations?assignee=me", headers=admin["headers"])
    ).json()
    assert mine["meta"]["total"] == 1
    assert mine["meta"]["counts"]["mine"] == 1
    unassigned = (
        await client.get("/conversations?assignee=unassigned", headers=admin["headers"])
    ).json()
    assert unassigned["meta"]["total"] == 1

    # Status changes go through the service layer and emit an activity message.
    resolved = await client.patch(
        f"/conversations/{first['id']}",
        headers=admin["headers"],
        json={"status": "resolved"},
    )
    assert resolved.json()["status"] == "resolved"
    open_only = (
        await client.get("/conversations?status=open", headers=admin["headers"])
    ).json()
    assert open_only["meta"]["total"] == 1

    by_inbox = (
        await client.get(
            f"/conversations?inbox_id={inbox['id']}&sort=priority",
            headers=admin["headers"],
        )
    ).json()
    assert by_inbox["meta"]["total"] == 2

    messages = (
        await client.get(
            f"/conversations/{first['id']}/messages", headers=admin["headers"]
        )
    ).json()
    assert any(m["message_type"] == "activity" for m in messages)


async def test_label_assignment_filters_conversations(
    client: AsyncClient, admin: dict[str, Any], inbox: dict[str, Any]
) -> None:
    conversation = await _open_conversation(client, inbox, admin["headers"])

    response = await client.put(
        f"/conversations/{conversation['id']}/labels",
        headers=admin["headers"],
        json={"labels": ["billing", "brand-new"]},
    )
    assert response.status_code == 200
    assert {label["title"] for label in response.json()["labels"]} == {
        "billing",
        "brand-new",
    }

    filtered = (
        await client.get("/conversations?labels=brand-new", headers=admin["headers"])
    ).json()
    assert filtered["meta"]["total"] == 1
    empty = (
        await client.get("/conversations?labels=unknown", headers=admin["headers"])
    ).json()
    assert empty["meta"]["total"] == 0

    cleared = await client.put(
        f"/conversations/{conversation['id']}/labels",
        headers=admin["headers"],
        json={"labels": []},
    )
    assert cleared.json()["labels"] == []


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
async def test_post_message_with_attachment_and_toggle_reaction(
    client: AsyncClient, admin: dict[str, Any], inbox: dict[str, Any]
) -> None:
    conversation = await _open_conversation(client, inbox, admin["headers"])

    response = await client.post(
        f"/conversations/{conversation['id']}/messages",
        headers=admin["headers"],
        data={"content": "Here you go", "private": "false"},
        files={"files": ("shot.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    )
    assert response.status_code == 201, response.text
    message = response.json()
    assert message["message_type"] == "outgoing"
    assert message["status"] == "sent"
    assert message["sender_id"] == admin["user"]["id"]
    assert len(message["attachments"]) == 1
    attachment = message["attachments"][0]
    assert attachment["file_type"] == "image"
    assert SENT and SENT[-1][0] == "555"

    download = await client.get(attachment["url"].removeprefix("/api/v1"), headers=admin["headers"])
    assert download.status_code == 200
    assert download.content == b"\x89PNG\r\n\x1a\nfake"

    note = await client.post(
        f"/conversations/{conversation['id']}/messages",
        headers=admin["headers"],
        data={"content": "internal note", "private": "true"},
    )
    assert note.json()["private"] is True

    empty = await client.post(
        f"/conversations/{conversation['id']}/messages",
        headers=admin["headers"],
        data={"content": "   "},
    )
    assert empty.status_code == 422

    # Reactions toggle on and off.
    on = await client.post(
        f"/messages/{message['id']}/reactions",
        headers=admin["headers"],
        json={"emoji": "👍"},
    )
    assert [r["emoji"] for r in on.json()["reactions"]] == ["👍"]
    off = await client.post(
        f"/messages/{message['id']}/reactions",
        headers=admin["headers"],
        json={"emoji": "👍"},
    )
    assert off.json()["reactions"] == []

    edited = await client.patch(
        f"/messages/{message['id']}",
        headers=admin["headers"],
        json={"content": "Here you go (edited)"},
    )
    assert edited.json()["content"] == "Here you go (edited)"
    assert edited.json()["edited_at"]

    assert (
        await client.delete(f"/messages/{message['id']}", headers=admin["headers"])
    ).status_code == 204


# ---------------------------------------------------------------------------
# Contacts, labels and the rest of the CRUD surface
# ---------------------------------------------------------------------------
async def test_contacts_and_notes(
    client: AsyncClient, admin: dict[str, Any], inbox: dict[str, Any]
) -> None:
    await _open_conversation(client, inbox, admin["headers"])

    listing = (await client.get("/contacts?q=Tester", headers=admin["headers"])).json()
    assert listing["meta"]["total"] == 1
    contact_id = listing["data"][0]["id"]

    updated = await client.patch(
        f"/contacts/{contact_id}",
        headers=admin["headers"],
        json={"email": "tester@example.com", "company": "Acme"},
    )
    assert updated.json()["email"] == "tester@example.com"

    note = await client.post(
        f"/contacts/{contact_id}/notes",
        headers=admin["headers"],
        json={"content": "VIP customer"},
    )
    assert note.status_code == 201
    notes = (await client.get(f"/contacts/{contact_id}/notes", headers=admin["headers"])).json()
    assert len(notes) == 1

    conversations = (
        await client.get(f"/contacts/{contact_id}/conversations", headers=admin["headers"])
    ).json()
    assert len(conversations) == 1

    blocked = await client.post(
        f"/contacts/{contact_id}/block", headers=admin["headers"], json={"blocked": True}
    )
    assert blocked.json()["blocked"] is True

    assert (
        await client.delete(
            f"/contacts/{contact_id}/notes/{note.json()['id']}", headers=admin["headers"]
        )
    ).status_code == 204


async def test_labels_canned_responses_and_automations(
    client: AsyncClient, admin: dict[str, Any]
) -> None:
    label = await client.post(
        "/labels",
        headers=admin["headers"],
        json={"title": "urgent-care", "color": "#FF0000"},
    )
    assert label.status_code == 201
    assert (
        await client.post(
            "/labels", headers=admin["headers"], json={"title": "urgent-care"}
        )
    ).status_code == 409
    assert (
        await client.patch(
            f"/labels/{label.json()['id']}",
            headers=admin["headers"],
            json={"color": "#00FF00"},
        )
    ).json()["color"] == "#00FF00"

    canned = await client.post(
        "/canned_responses",
        headers=admin["headers"],
        json={"short_code": "bye", "content": "Talk soon!"},
    )
    assert canned.status_code == 201

    catalogue = (await client.get("/automations/catalogue", headers=admin["headers"])).json()
    assert "message_created" in catalogue["events"]

    rule = await client.post(
        "/automations",
        headers=admin["headers"],
        json={
            "name": "Tag billing",
            "event_name": "message_created",
            "conditions": [
                {"attribute": "message_content", "operator": "contains", "values": ["invoice"]}
            ],
            "actions": [{"action": "add_label", "params": {"label": "billing"}}],
        },
    )
    assert rule.status_code == 201
    assert (await client.get("/automations", headers=admin["headers"])).json()[0]["name"] == (
        "Tag billing"
    )


async def test_users_teams_tokens_settings_and_stats(
    client: AsyncClient, admin: dict[str, Any]
) -> None:
    agent = await client.post(
        "/users",
        headers=admin["headers"],
        json={
            "name": "Agent Smith",
            "email": "smith@example.com",
            "password": "supersecret",
            "role": "agent",
        },
    )
    assert agent.status_code == 201
    agent_id = agent.json()["id"]

    login = await client.post(
        "/auth/login", json={"email": "smith@example.com", "password": "supersecret"}
    )
    agent_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    # Agents cannot reach admin-only endpoints.
    assert (await client.get("/users", headers=agent_headers)).status_code == 403

    team = await client.post(
        "/teams",
        headers=admin["headers"],
        json={"name": "Tier 1", "member_ids": [agent_id]},
    )
    assert team.json()["member_ids"] == [agent_id]
    updated = await client.put(
        f"/teams/{team.json()['id']}/members",
        headers=admin["headers"],
        json={"user_ids": []},
    )
    assert updated.json()["member_ids"] == []

    token = await client.post(
        "/api_tokens", headers=admin["headers"], json={"name": "ci"}
    )
    assert token.status_code == 201
    raw = token.json()["token"]
    assert raw.startswith("cs_")
    # The plaintext token authenticates just like the JWT.
    assert (
        await client.get("/auth/me", headers={"X-Api-Key": raw})
    ).json()["email"] == "admin@example.com"
    assert "token" not in (await client.get("/api_tokens", headers=admin["headers"])).json()[0]

    hook = await client.post(
        "/webhooks",
        headers=admin["headers"],
        json={"url": "https://example.com/hook", "subscriptions": ["message.created"]},
    )
    assert hook.status_code == 201
    events = (await client.get("/webhooks/events", headers=admin["headers"])).json()
    assert "conversation.updated" in events
    assert (
        await client.post(
            "/webhooks",
            headers=admin["headers"],
            json={"url": "https://example.com/x", "subscriptions": ["nope"]},
        )
    ).status_code == 422

    settings_response = await client.patch(
        "/settings", headers=admin["headers"], json={"installation_name": "Acme Support"}
    )
    assert settings_response.json()["installation_name"] == "Acme Support"
    assert (await client.get("/auth/config")).json()["installation_name"] == "Acme Support"

    stats = (await client.get("/admin/stats", headers=admin["headers"])).json()
    assert stats["agents"] == 2
    assert stats["conversations"]["total"] == 0
    assert stats["inboxes"] == []


async def test_sso_provider_administration(
    client: AsyncClient, admin: dict[str, Any]
) -> None:
    created = await client.post(
        "/sso_providers",
        headers=admin["headers"],
        json={
            "slug": "okta",
            "name": "Okta",
            "enabled": False,
            "config": {"issuer": "https://example.okta.com", "client_secret": "shh"},
        },
    )
    assert created.status_code == 201
    assert created.json()["config"]["client_secret"] == "••••••••"

    # A disabled provider is invisible to the login flow.
    assert (await client.get("/auth/sso/okta/login")).status_code == 404
    assert (await client.get("/auth/config")).json()["sso_providers"] == []

    enabled = await client.patch(
        f"/sso_providers/{created.json()['id']}",
        headers=admin["headers"],
        json={"enabled": True},
    )
    assert enabled.json()["enabled"] is True
    assert (await client.get("/auth/config")).json()["sso_providers"] == [
        {"slug": "okta", "name": "Okta", "kind": "oidc"}
    ]


@pytest.mark.parametrize(
    ("mime", "filename", "expected"),
    [
        ("image/png", "a.png", "image"),
        ("audio/ogg", "a.ogg", "voice"),
        ("audio/mpeg", "a.mp3", "audio"),
        ("video/mp4", "a.mp4", "video"),
        ("application/pdf", "a.pdf", "file"),
    ],
)
def test_attachment_type_mapping(mime: str, filename: str, expected: str) -> None:
    from app.api.v1.conversations import _attachment_type

    assert _attachment_type(mime, filename, is_voice=True) == expected
