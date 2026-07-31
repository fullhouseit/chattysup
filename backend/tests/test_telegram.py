"""Unit tests for the Telegram channel normalisation and outbound helpers.

Everything runs offline: the HTTP client is replaced with a recording stub, so
the tests assert on the exact Bot API calls the channel would have made.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.channels.base import (
    ChannelError,
    OutboundAttachment,
    OutboundMessage,
)
from app.channels.telegram import TelegramChannel, chunk_text
from app.channels.telegram.channel import MAX_TEXT_LENGTH
from app.models import AttachmentType, ContentType, Inbox

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
USER = {
    "id": 777,
    "is_bot": False,
    "first_name": "Ada",
    "last_name": "Lovelace",
    "username": "ada",
    "language_code": "en",
    "is_premium": True,
}
CHAT = {"id": 777, "type": "private", "first_name": "Ada", "username": "ada"}


def _update(update_id: int, **payload: Any) -> dict[str, Any]:
    return {"update_id": update_id, **payload}


def _message(**extra: Any) -> dict[str, Any]:
    return {"message_id": 42, "from": USER, "chat": CHAT, "date": 1_700_000_000, **extra}


class FakeApi:
    """Records calls instead of touching the network."""

    def __init__(self, results: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._results = list(results or [])

    async def call(self, method: str, **params: Any) -> Any:
        self.calls.append((method, params))
        if self._results:
            return self._results.pop(0)
        return {"message_id": 1000 + len(self.calls)}

    async def aclose(self) -> None:
        return None


@pytest.fixture
def inbox() -> Inbox:
    """An in-memory inbox — never attached to a session."""
    return Inbox(
        id=1,
        name="Support bot",
        channel_type="telegram",
        mode="polling",
        is_active=True,
        webhook_token="s3cret-token",
        config={"bot_token": "123:ABC", "download_media": True},
    )


@pytest.fixture
def channel(inbox: Inbox) -> TelegramChannel:
    return TelegramChannel(inbox)


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch, channel: TelegramChannel) -> FakeApi:
    api = FakeApi()
    monkeypatch.setattr(type(channel), "api", property(lambda self: api))
    return api


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
async def test_text_message(channel: TelegramChannel) -> None:
    events = channel._to_events(_update(1, message=_message(text="Hello there")))

    assert len(events) == 1
    event = events[0]
    assert event.kind == "message"
    assert event.chat_source_id == "777"
    assert event.message is not None
    assert event.message.source_id == "42"
    assert event.message.content == "Hello there"
    assert event.message.content_type == ContentType.TEXT.value
    assert event.message.attachments == []
    assert event.message.sent_at is not None

    contact = event.contact
    assert contact is not None
    assert contact.source_id == "777"
    assert contact.name == "Ada Lovelace"
    assert contact.username == "ada"
    assert contact.language == "en"
    assert contact.meta["telegram_user_id"] == 777
    assert contact.meta["chat_type"] == "private"
    assert contact.meta["is_premium"] is True


async def test_group_message_uses_chat_id_and_sender_name(
    channel: TelegramChannel,
) -> None:
    group = {"id": -100123, "type": "supergroup", "title": "Acme support"}
    events = channel._to_events(
        _update(2, message={**_message(text="hi"), "chat": group})
    )

    assert events[0].chat_source_id == "-100123"
    assert events[0].contact is not None
    assert events[0].contact.source_id == "-100123"
    assert events[0].contact.name == "Ada Lovelace"


async def test_photo_message(channel: TelegramChannel) -> None:
    photo = [
        {"file_id": "small", "file_size": 1024, "width": 90, "height": 60},
        {"file_id": "large", "file_size": 90_000, "width": 1280, "height": 850},
    ]
    events = channel._to_events(
        _update(3, message=_message(photo=photo, caption="Screenshot"))
    )

    message = events[0].message
    assert message is not None
    assert message.content == "Screenshot"
    assert len(message.attachments) == 1
    attachment = message.attachments[0]
    assert attachment.file_type == AttachmentType.IMAGE.value
    assert attachment.external_id == "large"
    assert attachment.thumb_external_id == "small"
    assert attachment.file_size == 90_000
    assert attachment.data is None


async def test_voice_message(channel: TelegramChannel) -> None:
    voice = {
        "file_id": "voice-1",
        "duration": 7,
        "mime_type": "audio/ogg",
        "file_size": 4242,
    }
    events = channel._to_events(_update(4, message=_message(voice=voice)))

    attachment = events[0].message.attachments[0]
    assert attachment.file_type == AttachmentType.VOICE.value
    assert attachment.external_id == "voice-1"
    assert attachment.mime_type == "audio/ogg"
    assert attachment.meta["duration"] == 7


async def test_sticker_message(channel: TelegramChannel) -> None:
    sticker = {
        "file_id": "sticker-1",
        "emoji": "🎉",
        "set_name": "Party",
        "is_animated": True,
        "is_video": False,
        "thumbnail": {"file_id": "sticker-thumb"},
    }
    events = channel._to_events(_update(5, message=_message(sticker=sticker)))

    message = events[0].message
    assert message.content == "🎉"
    assert message.content_type == ContentType.STICKER.value
    attachment = message.attachments[0]
    assert attachment.file_type == AttachmentType.STICKER.value
    assert attachment.thumb_external_id == "sticker-thumb"
    assert attachment.meta["set_name"] == "Party"
    assert attachment.meta["is_animated"] is True


async def test_reply_and_forward_attributes(channel: TelegramChannel) -> None:
    payload = _message(
        text="sure",
        reply_to_message={"message_id": 41, "chat": CHAT},
        forward_origin={"type": "hidden_user", "sender_user_name": "Anon"},
        entities=[{"type": "bold", "offset": 0, "length": 4}],
        message_thread_id=99,
        is_topic_message=True,
        via_bot={"username": "helperbot"},
    )
    events = channel._to_events(_update(6, message=payload))

    attributes = events[0].message.attributes
    assert attributes["reply_to_source_id"] == "41"
    assert attributes["forwarded_from"] == "Anon"
    assert attributes["entities"][0]["type"] == "bold"
    assert attributes["telegram_chat_id"] == 777
    assert attributes["message_thread_id"] == 99
    assert attributes["is_topic_message"] is True
    assert attributes["via_bot"] == "helperbot"


async def test_edited_message(channel: TelegramChannel) -> None:
    events = channel._to_events(
        _update(
            7,
            edited_message=_message(text="fixed typo", edit_date=1_700_000_500),
        )
    )

    assert events[0].kind == "message_edited"
    assert events[0].message.content == "fixed typo"
    assert events[0].message.source_id == "42"


async def test_message_reaction(channel: TelegramChannel) -> None:
    events = channel._to_events(
        _update(
            8,
            message_reaction={
                "chat": CHAT,
                "message_id": 42,
                "user": USER,
                "date": 1_700_000_600,
                "old_reaction": [],
                "new_reaction": [
                    {"type": "emoji", "emoji": "🔥"},
                    {"type": "custom_emoji", "custom_emoji_id": "555"},
                ],
            },
        )
    )

    event = events[0]
    assert event.kind == "reaction"
    assert event.target_source_id == "42"
    assert event.reactions == ["🔥", "555"]
    assert event.message is None


async def test_callback_query_becomes_message(channel: TelegramChannel) -> None:
    events = channel._to_events(
        _update(
            9,
            callback_query={
                "id": "cbq-1",
                "from": USER,
                "data": "order:refund",
                "message": _message(text="Choose"),
            },
        )
    )

    message = events[0].message
    assert message.content == "🔘 order:refund"
    assert message.source_id == "cb:cbq-1"
    assert message.attributes["callback_data"] == "order:refund"


async def test_ignored_updates(channel: TelegramChannel) -> None:
    assert channel._to_events(_update(10, channel_post=_message(text="news"))) == []
    assert channel._to_events(_update(11, poll_answer={"poll_id": "1"})) == []
    kicked = _update(
        12,
        my_chat_member={
            "chat": CHAT,
            "from": USER,
            "date": 1,
            "old_chat_member": {"status": "member"},
            "new_chat_member": {"status": "kicked"},
        },
    )
    assert channel._to_events(kicked) == []


async def test_location_and_contact_and_poll(channel: TelegramChannel) -> None:
    location = channel._to_events(
        _update(13, message=_message(location={"latitude": 1.5, "longitude": 2.5}))
    )[0].message
    assert location.content_type == ContentType.LOCATION.value
    assert location.attachments[0].meta["latitude"] == 1.5

    card = channel._to_events(
        _update(
            14,
            message=_message(contact={"phone_number": "+123", "first_name": "Bob"}),
        )
    )[0].message
    assert card.content_type == ContentType.CONTACT_CARD.value
    assert card.attachments[0].meta["phone_number"] == "+123"

    poll = channel._to_events(
        _update(
            15,
            message=_message(
                poll={
                    "id": "p1",
                    "question": "Coffee?",
                    "options": [{"text": "Yes"}, {"text": "No"}],
                }
            ),
        )
    )[0].message
    assert poll.content_type == ContentType.POLL.value
    assert poll.content == "Coffee?"
    assert poll.attachments[0].meta["options"] == ["Yes", "No"]


# ---------------------------------------------------------------------------
# Webhook verification
# ---------------------------------------------------------------------------
async def test_parse_webhook_requires_secret(channel: TelegramChannel) -> None:
    update = _update(16, message=_message(text="hi"))

    events = await channel.parse_webhook(
        update, {"X-Telegram-Bot-Api-Secret-Token": "s3cret-token"}
    )
    assert events[0].message.content == "hi"

    with pytest.raises(ChannelError):
        await channel.parse_webhook(update, {"x-telegram-bot-api-secret-token": "nope"})


# ---------------------------------------------------------------------------
# Outbound
# ---------------------------------------------------------------------------
async def test_chunk_text_splits_at_the_limit() -> None:
    assert chunk_text("") == []
    assert chunk_text("short") == ["short"]

    text = "word " * 2000  # ~10k characters
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= MAX_TEXT_LENGTH for chunk in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")

    blob = "x" * (MAX_TEXT_LENGTH * 2 + 5)
    hard = chunk_text(blob)
    assert [len(c) for c in hard] == [MAX_TEXT_LENGTH, MAX_TEXT_LENGTH, 5]


async def test_send_long_text_is_chunked(
    channel: TelegramChannel, fake_api: FakeApi
) -> None:
    result = await channel.send_message(
        "777", OutboundMessage(content="y" * (MAX_TEXT_LENGTH + 100))
    )

    assert [method for method, _ in fake_api.calls] == ["sendMessage", "sendMessage"]
    assert result.source_id == "1001"
    assert result.attributes["extra_source_ids"] == ["1002"]


async def test_send_text_options(channel: TelegramChannel, fake_api: FakeApi) -> None:
    await channel.send_message(
        "777",
        OutboundMessage(
            content="<b>hi</b>",
            reply_to_source_id="42",
            attributes={"format": "html", "disable_link_preview": True},
        ),
    )

    _, params = fake_api.calls[0]
    assert params["parse_mode"] == "HTML"
    assert params["reply_parameters"] == {"message_id": 42}
    assert params["link_preview_options"] == {"is_disabled": True}


async def test_send_photo_uses_multipart(
    channel: TelegramChannel, fake_api: FakeApi
) -> None:
    attachment = OutboundAttachment(
        file_type=AttachmentType.IMAGE.value,
        file_name="shot.png",
        mime_type="image/png",
        data=b"binary",
    )
    await channel.send_message(
        "777", OutboundMessage(content="look", attachments=[attachment])
    )

    method, params = fake_api.calls[0]
    assert method == "sendPhoto"
    assert params["caption"] == "look"
    assert params["files"]["photo"][0] == "shot.png"


async def test_send_reaction_maps_unsupported_emoji(
    channel: TelegramChannel, fake_api: FakeApi
) -> None:
    await channel.send_reaction("777", "42", ["🦖"])

    method, params = fake_api.calls[0]
    assert method == "setMessageReaction"
    assert params["reaction"] == [{"type": "emoji", "emoji": "👍"}]


async def test_download_disabled_raises(inbox: Inbox) -> None:
    inbox.config = {**inbox.config, "download_media": False}
    channel = TelegramChannel(inbox)

    with pytest.raises(ChannelError):
        await channel.download_file("file-1")
