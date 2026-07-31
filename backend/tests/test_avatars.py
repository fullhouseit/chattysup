"""Contact avatars mirrored from the channel."""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.channels.telegram import TelegramChannel
from app.db import utcnow
from app.models import Contact, ContactInbox, Inbox
from app.services import avatars as avatar_service
from tests.test_telegram_polling import FakeApi, attach, make_inbox

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

PROFILE_PHOTOS = {
    "total_count": 1,
    "photos": [
        [
            {"file_id": "small", "width": ns, "height": ns}
            for ns in (60, 160, 640)
        ]
    ],
}


class AvatarApi(FakeApi):
    """Fake that also answers getFile/download for the chosen photo."""

    def __init__(self, photos=PROFILE_PHOTOS) -> None:
        super().__init__({"getUserProfilePhotos": photos})
        self.requested_file_id: str | None = None

    async def get_file(self, file_id):
        self.requested_file_id = file_id
        return {"file_path": "photos/file_7.jpg", "file_size": len(PNG)}

    async def download(self, file_path):
        return PNG


@pytest.mark.asyncio
async def test_fetch_avatar_picks_a_reasonable_size():
    channel = TelegramChannel(make_inbox())
    api = attach(channel, AvatarApi())
    # Distinguish the sizes so the choice is observable.
    api.responses["getUserProfilePhotos"] = {
        "photos": [
            [
                {"file_id": "tiny", "width": 60},
                {"file_id": "mid", "width": 160},
                {"file_id": "huge", "width": 640},
            ]
        ]
    }

    data, name, mime = await channel.fetch_avatar(
        _contact(meta={"telegram_user_id": 555})
    )

    assert data == PNG
    assert name and mime.startswith("image/")
    # The smallest size at or above the threshold, not the 640px original.
    assert api.requested_file_id == "mid"


@pytest.mark.asyncio
async def test_fetch_avatar_returns_none_without_a_photo():
    channel = TelegramChannel(make_inbox())
    attach(channel, AvatarApi(photos={"total_count": 0, "photos": []}))

    assert await channel.fetch_avatar(_contact(meta={"telegram_user_id": 5})) is None


@pytest.mark.asyncio
async def test_fetch_avatar_skips_group_chats():
    """A negative chat id is a group; getUserProfilePhotos cannot take it."""
    channel = TelegramChannel(make_inbox())
    api = attach(channel, AvatarApi())

    assert await channel.fetch_avatar(_contact(source_id="-100123", meta={})) is None
    assert api.methods() == []


@pytest.mark.asyncio
async def test_avatar_is_stored_and_linked_to_the_contact(db_session):
    inbox, contact, link, channel = await _fixture(db_session)

    stored = await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, _contact(meta={"telegram_user_id": 555})
    )

    assert stored is True
    assert contact.avatar_url.startswith("/api/v1/attachments/")
    assert contact.avatar_url.endswith("/file")
    assert link.meta["avatar_checked_at"]


@pytest.mark.asyncio
async def test_avatar_is_not_refetched_while_the_contact_has_one(db_session):
    inbox, contact, link, channel = await _fixture(db_session)
    contact.avatar_url = "/api/v1/attachments/1/file"

    assert not await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, _contact()
    )
    assert channel._api.methods() == []


@pytest.mark.asyncio
async def test_contacts_without_a_photo_are_not_polled_every_message(db_session):
    """A contact who hides their avatar must not cost a lookup per message."""
    inbox, contact, link, channel = await _fixture(db_session, photos={"photos": []})

    payload = _contact(meta={"telegram_user_id": 555})
    assert not await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, payload
    )
    calls_after_first = len(channel._api.calls)

    assert not await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, payload
    )
    assert len(channel._api.calls) == calls_after_first

    # …until the re-check window lapses.
    link.meta = {"avatar_checked_at": (utcnow() - timedelta(days=8)).isoformat()}
    await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, payload
    )
    assert len(channel._api.calls) > calls_after_first


@pytest.mark.asyncio
async def test_a_failing_lookup_never_breaks_intake(db_session):
    inbox, contact, link, channel = await _fixture(db_session)

    async def boom(*_a, **_k):
        raise RuntimeError("telegram is down")

    channel.fetch_avatar = boom

    assert not await avatar_service.ensure_contact_avatar(
        db_session, inbox, channel, contact, link, _contact()
    )
    assert contact.avatar_url is None


# --- helpers ---------------------------------------------------------------
def _contact(source_id="555", meta=None):
    from app.channels.base import NormalizedContact

    return NormalizedContact(source_id=source_id, name="Alex B", meta=meta or {})


async def _fixture(db_session, photos=PROFILE_PHOTOS):
    inbox = Inbox(name="TG", channel_type="telegram", mode="polling", config={"bot_token": "1:a"})
    db_session.add(inbox)
    await db_session.flush()

    contact = Contact(name="Alex B")
    db_session.add(contact)
    await db_session.flush()

    link = ContactInbox(contact_id=contact.id, inbox_id=inbox.id, source_id="555", meta={})
    db_session.add(link)
    await db_session.flush()

    channel = TelegramChannel(inbox)
    attach(channel, AvatarApi(photos=photos))
    return inbox, contact, link, channel
