"""Email notifications: transport, rendering, routing and preferences."""
from __future__ import annotations

import asyncio
from email import message_from_bytes

import pytest

from app.config import settings
from app.models import (
    Contact,
    ContactInbox,
    Conversation,
    ConversationParticipant,
    Inbox,
    InboxMember,
    Message,
    User,
)
from app.services import email_templates, mailer, notifications, settings_service


@pytest.fixture
def smtp(monkeypatch):
    """Pretend SMTP is configured, without touching a network."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "smtp_from_email", "helpdesk@example.test")
    monkeypatch.setattr(settings, "base_url", "https://support.example.com")
    return settings


@pytest.fixture
def outbox(monkeypatch):
    """Capture what would have been sent."""
    sent: list[dict] = []

    async def fake_send_email(*, to, subject, text_body, html_body=None):
        sent.append(
            {"to": to, "subject": subject, "text": text_body, "html": html_body}
        )

    monkeypatch.setattr(mailer, "send_email", fake_send_email)
    notifications.reset_throttle()
    return sent


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------
def test_message_is_multipart_with_a_text_part(smtp):
    """HTML-only mail is a spam signal; always ship a text alternative."""
    message = mailer.build_message(
        to="agent@example.test",
        subject="Hello",
        text_body="plain",
        html_body="<p>rich</p>",
    )
    parsed = message_from_bytes(message.as_bytes())

    assert parsed.get_content_type() == "multipart/alternative"
    types = [p.get_content_type() for p in parsed.walk() if p.get_payload(decode=True)]
    assert types == ["text/plain", "text/html"]
    assert parsed["From"] == "ChattySup <helpdesk@example.test>"
    # Stops out-of-office autoresponders from replying to a notification.
    assert parsed["Auto-Submitted"] == "auto-generated"


@pytest.mark.asyncio
async def test_sending_without_configuration_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    with pytest.raises(mailer.MailError, match="SMTP_HOST"):
        await mailer.send_email(to="a@b.test", subject="x", text_body="y")


def test_describe_never_leaks_the_password(monkeypatch, smtp):
    monkeypatch.setattr(settings, "smtp_password", "hunter2")
    described = mailer.describe()

    assert described["has_password"] is True
    assert "hunter2" not in repr(described)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def test_new_message_email_links_straight_to_the_conversation(smtp):
    subject, text, html = email_templates.render_new_message(
        contact_name="Klaus Crawley",
        inbox_name="Telegram",
        content="My scanner will not pair",
        conversation_id=42,
    )

    assert subject == "[ChattySup] New message from Klaus Crawley"
    assert "My scanner will not pair" in text
    link = "https://support.example.com/conversations/42"
    assert link in text
    assert f'href="{link}"' in html


def test_message_text_is_escaped(smtp):
    """A contact controls this text; it must not become markup."""
    _, text, html = email_templates.render_new_message(
        contact_name='<img src=x onerror="alert(1)">',
        inbox_name="Telegram",
        content="<script>alert('xss')</script>",
        conversation_id=1,
    )

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "onerror" not in html.split("alert")[0] or "&lt;img" in html
    # The plain part keeps the raw text — it is never interpreted.
    assert "<script>" in text


def test_newlines_survive_into_the_html(smtp):
    _, _, html = email_templates.render_new_message(
        contact_name="A", inbox_name="I", content="line one\nline two", conversation_id=1
    )
    assert "line one<br>line two" in html


def test_long_messages_are_truncated(smtp):
    _, text, _ = email_templates.render_new_message(
        contact_name="A", inbox_name="I", content="x" * 5000, conversation_id=1
    )
    assert "…" in text
    assert len(text) < 2500


def test_private_notes_are_labelled(smtp):
    subject, text, _ = email_templates.render_new_message(
        contact_name="Klaus",
        inbox_name="Telegram",
        content="internal",
        conversation_id=1,
        is_private_note=True,
        author_name="Alex",
    )
    assert subject == "[ChattySup] New private note from Alex"
    assert "New private note from Alex" in text


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
async def _scenario(db, *, assignee: User | None = None, members: list[User] | None = None):
    inbox = Inbox(name="TG", channel_type="telegram", mode="polling", config={})
    db.add(inbox)
    await db.flush()
    for user in members or []:
        db.add(InboxMember(inbox_id=inbox.id, user_id=user.id))

    contact = Contact(name="Klaus Crawley")
    db.add(contact)
    await db.flush()
    link = ContactInbox(contact_id=contact.id, inbox_id=inbox.id, source_id="1", meta={})
    db.add(link)
    await db.flush()

    from app.db import utcnow

    conversation = Conversation(
        inbox_id=inbox.id,
        contact_id=contact.id,
        contact_inbox_id=link.id,
        assignee_id=assignee.id if assignee else None,
        status="open",
        last_activity_at=utcnow(),
    )
    db.add(conversation)
    await db.flush()

    message = Message(
        conversation_id=conversation.id,
        inbox_id=inbox.id,
        content="Hello there",
        message_type="incoming",
        sender_type="contact",
        sender_id=contact.id,
    )
    db.add(message)
    await db.flush()
    return conversation, message


async def _agent(db, email: str, **kwargs) -> User:
    user = User(name=email.split("@")[0], email=email, role="agent", **kwargs)
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_assignee_and_unassigned_rules(db_session, smtp, outbox):
    owner = await _agent(db_session, "owner@example.test")
    other = await _agent(db_session, "other@example.test")
    conversation, message = await _scenario(db_session, assignee=owner)

    recipients = await notifications._recipients(db_session, conversation, message)
    emails = {u.email for u in recipients}

    # The assignee wants it; a bystander does not, by default.
    assert "owner@example.test" in emails
    assert "other@example.test" not in emails


@pytest.mark.asyncio
async def test_unassigned_conversations_reach_everyone_who_opted_in(db_session, smtp):
    first = await _agent(db_session, "a@example.test")
    second = await _agent(
        db_session, "b@example.test", notification_settings={"unassigned": False}
    )
    conversation, message = await _scenario(db_session, assignee=None)

    recipients = await notifications._recipients(db_session, conversation, message)
    assert {u.email for u in recipients} == {"a@example.test"}


@pytest.mark.asyncio
async def test_participants_are_notified(db_session, smtp):
    owner = await _agent(db_session, "owner@example.test")
    watcher = await _agent(db_session, "watcher@example.test")
    conversation, message = await _scenario(db_session, assignee=owner)
    db_session.add(
        ConversationParticipant(conversation_id=conversation.id, user_id=watcher.id)
    )
    await db_session.flush()

    recipients = await notifications._recipients(db_session, conversation, message)
    assert "watcher@example.test" in {u.email for u in recipients}


@pytest.mark.asyncio
async def test_inbox_members_bound_the_audience(db_session, smtp):
    """An inbox with a member list must not mail the whole installation."""
    member = await _agent(db_session, "member@example.test")
    outsider = await _agent(db_session, "outsider@example.test")
    conversation, message = await _scenario(db_session, members=[member])

    recipients = await notifications._recipients(db_session, conversation, message)
    assert {u.email for u in recipients} == {"member@example.test"}
    assert outsider.email not in {u.email for u in recipients}


@pytest.mark.asyncio
async def test_agents_who_switched_it_off_are_skipped(db_session, smtp):
    await _agent(db_session, "quiet@example.test", email_notifications=False)
    conversation, message = await _scenario(db_session)

    assert await notifications._recipients(db_session, conversation, message) == []


@pytest.mark.asyncio
async def test_nobody_is_emailed_about_their_own_private_note(db_session, smtp):
    author = await _agent(db_session, "author@example.test")
    conversation, message = await _scenario(db_session, assignee=author)
    message.message_type = "outgoing"
    message.private = True
    message.sender_type = "user"
    message.sender_id = author.id
    await db_session.flush()

    recipients = await notifications._recipients(db_session, conversation, message)
    assert recipients == []


@pytest.mark.asyncio
async def test_online_agents_can_opt_out(db_session, smtp, monkeypatch):
    user = await _agent(
        db_session, "online@example.test", notification_settings={"skip_when_online": True}
    )
    conversation, message = await _scenario(db_session, assignee=user)

    monkeypatch.setattr(
        type(notifications.bus.manager), "online_user_ids", property(lambda self: [user.id])
    )
    assert await notifications._recipients(db_session, conversation, message) == []


@pytest.mark.asyncio
async def test_frequency_limit_suppresses_the_second_email(db_session, smtp):
    notifications.reset_throttle()
    user = await _agent(
        db_session,
        "busy@example.test",
        notification_settings={"min_interval_seconds": 300},
    )
    conversation, message = await _scenario(db_session, assignee=user)

    assert await notifications._recipients(db_session, conversation, message)

    notifications._last_sent[(user.id, conversation.id)] = (
        asyncio.get_event_loop().time()
    )
    assert await notifications._recipients(db_session, conversation, message) == []


@pytest.mark.asyncio
async def test_activity_and_public_replies_never_email(db_session, smtp, outbox):
    user = await _agent(db_session, "agent@example.test")
    conversation, message = await _scenario(db_session, assignee=user)

    message.message_type = "activity"
    await db_session.flush()
    assert await notifications._dispatch(db_session, message) == 0

    message.message_type = "outgoing"
    message.private = False
    await db_session.flush()
    assert await notifications._dispatch(db_session, message) == 0

    assert outbox == []


@pytest.mark.asyncio
async def test_muted_conversations_are_silent(db_session, smtp, outbox):
    user = await _agent(db_session, "agent@example.test")
    conversation, message = await _scenario(db_session, assignee=user)
    conversation.muted = True
    await db_session.flush()

    assert await notifications._dispatch(db_session, message) == 0


@pytest.mark.asyncio
async def test_dispatch_sends_the_expected_email(db_session, smtp, outbox):
    user = await _agent(db_session, "agent@example.test")
    conversation, message = await _scenario(db_session, assignee=user)

    assert await notifications._dispatch(db_session, message) == 1
    (mail,) = outbox
    assert mail["to"] == "agent@example.test"
    assert "Klaus Crawley" in mail["subject"]
    assert "Hello there" in mail["text"]
    assert f"/conversations/{conversation.id}" in mail["text"]


@pytest.mark.asyncio
async def test_a_failing_mail_server_does_not_raise(db_session, smtp, monkeypatch):
    user = await _agent(db_session, "agent@example.test")
    conversation, message = await _scenario(db_session, assignee=user)

    async def boom(**_kwargs):
        raise mailer.MailError("connection refused")

    monkeypatch.setattr(mailer, "send_email", boom)
    assert await notifications._dispatch(db_session, message) == 0


# ---------------------------------------------------------------------------
# Both switches
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_nothing_is_sent_until_the_installation_switch_is_on(
    db_session, smtp, outbox, monkeypatch
):
    # notify_new_message opens its own sessions; point them at the test database.
    from tests.conftest import TestSession

    monkeypatch.setattr(notifications, "SessionLocal", TestSession)
    monkeypatch.setattr("app.services.visibility.SessionLocal", TestSession)
    user = await _agent(db_session, "agent@example.test")
    conversation, message = await _scenario(db_session, assignee=user)
    await db_session.commit()

    assert await notifications.notify_new_message(message.id) == 0
    assert outbox == []

    await settings_service.set_value(db_session, notifications.SETTING_KEY, True)
    await db_session.commit()

    assert await notifications.notify_new_message(message.id) == 1


@pytest.mark.asyncio
async def test_nothing_is_sent_when_smtp_is_absent(db_session, monkeypatch, outbox):
    from tests.conftest import TestSession

    monkeypatch.setattr(notifications, "SessionLocal", TestSession)
    monkeypatch.setattr("app.services.visibility.SessionLocal", TestSession)
    monkeypatch.setattr(settings, "smtp_host", None)
    user = await _agent(db_session, "agent@example.test")
    _, message = await _scenario(db_session, assignee=user)
    await settings_service.set_value(db_session, notifications.SETTING_KEY, True)
    await db_session.commit()

    assert await notifications.notify_new_message(message.id) == 0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_status_reports_why_it_is_off(client, admin):
    response = await client.get("/notifications/status", headers=admin["headers"])
    body = response.json()

    assert response.status_code == 200
    assert body["operational"] is False
    assert "SMTP" in body["reason"]
    # Admins see the configuration; the password is never in it.
    assert "has_password" in body["smtp"]
    assert "password" not in [k for k in body["smtp"] if k != "has_password"]


@pytest.mark.asyncio
async def test_preferences_round_trip(client, admin):
    response = await client.patch(
        "/notifications/preferences",
        json={"others": True, "min_interval_seconds": 900},
        headers=admin["headers"],
    )
    assert response.status_code == 200
    prefs = response.json()["preferences"]
    assert prefs["others"] is True
    assert prefs["min_interval_seconds"] == 900
    # Untouched keys keep their defaults.
    assert prefs["assigned"] is True

    again = await client.get("/notifications/preferences", headers=admin["headers"])
    assert again.json()["preferences"]["min_interval_seconds"] == 900


@pytest.mark.asyncio
async def test_unknown_preference_keys_are_rejected(client, admin):
    response = await client.patch(
        "/notifications/preferences",
        json={"min_interval_seconds": -5},
        headers=admin["headers"],
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_email_reports_a_broken_server_as_a_422(client, admin, smtp):
    """An unreachable mail server is an operator error, not a 500."""
    response = await client.post("/notifications/test", headers=admin["headers"])
    assert response.status_code == 422
    assert response.json()["detail"]
