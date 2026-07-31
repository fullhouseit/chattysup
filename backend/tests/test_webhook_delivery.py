"""Delivery-time regressions found by driving a live installation.

Both bugs below survived the conformance suites because those build their
payloads from rows that are already committed, while in production the bus
publishes from *inside* the producing transaction.
"""
from __future__ import annotations

import pytest

from app.core import events as bus
from app.services import webhooks


class _Visibility:
    """``_subject_visible`` that becomes true after ``n`` attempts."""

    def __init__(self, visible_after: int) -> None:
        self.visible_after = visible_after
        self.calls = 0

    async def __call__(self, db, event, payload) -> bool:
        self.calls += 1
        return self.calls > self.visible_after


@pytest.mark.asyncio
async def test_delivery_waits_for_the_producing_transaction(monkeypatch):
    """A row that is not committed yet must not silently drop the delivery.

    Reproduces the live failure: every ``message_created`` raised by the Client
    API and by the agent UI reached no Chatwoot webhook at all, because the
    dispatcher reloaded the message in its own session before the request that
    created it had committed.
    """
    visibility = _Visibility(visible_after=2)
    monkeypatch.setattr(webhooks, "_subject_visible", visibility)
    monkeypatch.setattr(webhooks, "VISIBILITY_DELAYS", (0.0, 0.01, 0.01, 0.01))

    built: list[set[str]] = []

    async def fake_build(db, event, payload, wanted, changes):
        built.append(wanted)
        return {name: b"{}" for name in wanted}

    monkeypatch.setattr(webhooks, "_build_chatwoot_bodies", fake_build)

    bodies = await webhooks._build_chatwoot_bodies_when_visible(
        bus.EVENT_MESSAGE_CREATED, {"message": {"id": 7}}, {"message_created"}, None
    )

    assert bodies == {"message_created": b"{}"}
    assert visibility.calls == 3, "should have retried until the row appeared"
    assert built == [{"message_created"}], "body built exactly once, after it was visible"


@pytest.mark.asyncio
async def test_delivery_gives_up_when_the_producer_rolled_back(monkeypatch):
    """A transaction that never commits must not retry forever."""
    visibility = _Visibility(visible_after=99)
    monkeypatch.setattr(webhooks, "_subject_visible", visibility)
    monkeypatch.setattr(webhooks, "VISIBILITY_DELAYS", (0.0, 0.01, 0.01))

    async def fail(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("must not build a body for an invisible row")

    monkeypatch.setattr(webhooks, "_build_chatwoot_bodies", fail)

    bodies = await webhooks._build_chatwoot_bodies_when_visible(
        bus.EVENT_MESSAGE_CREATED, {"message": {"id": 7}}, {"message_created"}, None
    )

    assert bodies == {}
    assert visibility.calls == 3, "bounded by VISIBILITY_DELAYS"


@pytest.mark.asyncio
async def test_subject_visible_tracks_real_rows(db_session):
    """The gate is the committed row, not the payload."""
    from app.models import Contact

    payload = {"contact": {"id": 4242}}
    assert not await webhooks._subject_visible(
        db_session, bus.EVENT_CONTACT_UPDATED, payload
    )

    contact = Contact(id=4242, name="Alex")
    db_session.add(contact)
    await db_session.flush()

    assert await webhooks._subject_visible(
        db_session, bus.EVENT_CONTACT_UPDATED, payload
    )


# ---------------------------------------------------------------------------
# Native webhook API: two vocabularies
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_native_api_can_create_a_chatwoot_webhook(client, admin):
    """Chatwoot hooks were unmanageable from our own API and UI."""
    response = await client.post(
        "/webhooks",
        json={
            "url": "https://example.test/hook",
            "payload_format": "chatwoot",
            "subscriptions": ["message_created", "conversation_status_changed"],
        },
        headers=admin["headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()["payload_format"] == "chatwoot"


@pytest.mark.asyncio
async def test_each_format_rejects_the_other_vocabulary(client, admin):
    chatwoot_with_native = await client.post(
        "/webhooks",
        json={
            "url": "https://example.test/a",
            "payload_format": "chatwoot",
            "subscriptions": ["message.created"],
        },
        headers=admin["headers"],
    )
    assert chatwoot_with_native.status_code == 422
    assert "message.created" in chatwoot_with_native.json()["detail"]

    native_with_chatwoot = await client.post(
        "/webhooks",
        json={
            "url": "https://example.test/b",
            "subscriptions": ["message_created"],
        },
        headers=admin["headers"],
    )
    assert native_with_chatwoot.status_code == 422


@pytest.mark.asyncio
async def test_events_endpoint_serves_both_vocabularies(client, admin):
    native = await client.get("/webhooks/events", headers=admin["headers"])
    chatwoot = await client.get(
        "/webhooks/events?payload_format=chatwoot", headers=admin["headers"]
    )

    assert "message.created" in native.json()
    assert "message_created" not in native.json()

    body = chatwoot.json()
    # The twelve events chatwoot/chatwoot's webhook_listener.rb can emit.
    assert "message_created" in body
    assert "conversation_typing_on" in body
    assert "inbox_updated" in body
    assert len(body) == 12
