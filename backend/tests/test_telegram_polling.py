"""Long-polling regressions: stale webhooks and the lost-message window."""
from __future__ import annotations

import pytest

from app.channels.base import ChannelError
from app.channels.telegram import TelegramChannel
from app.models import Inbox

MESSAGE_UPDATE = {
    "update_id": 500,
    "message": {
        "message_id": 9,
        "from": {"id": 42, "is_bot": False, "first_name": "Sasha"},
        "chat": {"id": 42, "first_name": "Sasha", "type": "private"},
        "date": 1785500000,
        "text": "hello?",
    },
}

WEBHOOK_CONFLICT = (
    "Telegram getUpdates failed [409]: Conflict: can't use getUpdates method "
    "while webhook is active"
)


def make_inbox(**kwargs) -> Inbox:
    return Inbox(
        id=1,
        name="TG",
        channel_type="telegram",
        mode=kwargs.pop("mode", "polling"),
        config={"bot_token": "1:abc", **kwargs.pop("config", {})},
        **kwargs,
    )


class Sequence:
    """Successive answers for repeated calls to the same Bot API method."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)

    def next(self) -> object:
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class FakeApi:
    """Records every Bot API call and replays scripted answers."""

    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method, **params):
        self.calls.append((method, params))
        value = self.responses.get(method)
        if isinstance(value, Sequence):
            value = value.next()
        if isinstance(value, Exception):
            raise value
        return value

    async def aclose(self):
        return None

    def methods(self) -> list[str]:
        return [name for name, _ in self.calls]


def attach(channel: TelegramChannel, api: FakeApi) -> FakeApi:
    channel._api = api  # noqa: SLF001 - the point of the fake
    return api


@pytest.mark.asyncio
async def test_setup_removes_a_stale_webhook_before_polling():
    """A webhook from a previous owner makes getUpdates fail with 409 forever."""
    channel = TelegramChannel(make_inbox())
    api = attach(
        channel,
        FakeApi({"getWebhookInfo": {"url": "https://old.example/hook"}, "deleteWebhook": True}),
    )

    info = await channel.setup()

    assert "getWebhookInfo" in api.methods()
    assert "deleteWebhook" in api.methods()
    assert info["previous_webhook"] == "https://old.example/hook"


@pytest.mark.asyncio
async def test_first_poll_does_not_swallow_a_freshly_sent_message():
    """The backlog is dropped in setup(), so the first poll must deliver.

    The previous implementation spent the first poll on getUpdates(offset=-1)
    and discarded whatever it returned — silently eating the message a user
    sends right after connecting the bot.
    """
    channel = TelegramChannel(make_inbox(config={"skip_old_updates": True}))
    api = attach(channel, FakeApi({"getUpdates": [MESSAGE_UPDATE]}))

    events, cursor = await channel.fetch_updates(None)

    assert [e.kind for e in events] == ["message"]
    assert events[0].message.content == "hello?"
    assert cursor == "500"
    # Exactly one poll, and never the offset=-1 acknowledgement trick.
    assert api.methods() == ["getUpdates"]
    assert api.calls[0][1].get("offset") is None


@pytest.mark.asyncio
async def test_poll_recovers_from_a_webhook_conflict():
    """A 409 must self-heal by dropping the webhook, not back off forever."""
    channel = TelegramChannel(make_inbox())
    api = attach(
        channel,
        FakeApi(
            {
                "getUpdates": Sequence(ChannelError(WEBHOOK_CONFLICT), [MESSAGE_UPDATE]),
                "deleteWebhook": True,
            }
        ),
    )

    events, cursor = await channel.fetch_updates(None)

    assert api.methods() == ["getUpdates", "deleteWebhook", "getUpdates"]
    assert [e.kind for e in events] == ["message"]
    assert cursor == "500"


@pytest.mark.asyncio
async def test_unrelated_errors_still_propagate():
    channel = TelegramChannel(make_inbox())
    attach(channel, FakeApi({"getUpdates": ChannelError("Telegram getUpdates failed [401]")}))

    with pytest.raises(ChannelError):
        await channel.fetch_updates(None)


@pytest.mark.asyncio
async def test_health_check_warns_about_a_webhook_blocking_polling():
    channel = TelegramChannel(make_inbox())
    attach(
        channel,
        FakeApi(
            {
                "getMe": {"id": 1, "username": "bot", "first_name": "Bot"},
                "getWebhookInfo": {"url": "https://old.example/hook", "pending_update_count": 3},
            }
        ),
    )

    result = await channel.health_check()

    assert result["status"] == "warning"
    assert "blocks long polling" in result["warning"]
    assert result["pending_update_count"] == 3


@pytest.mark.asyncio
async def test_health_check_is_clean_when_no_webhook_is_registered():
    channel = TelegramChannel(make_inbox())
    attach(
        channel,
        FakeApi(
            {
                "getMe": {"id": 1, "username": "bot", "first_name": "Bot"},
                "getWebhookInfo": {"url": "", "pending_update_count": 0},
            }
        ),
    )

    assert (await channel.health_check())["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_mode_warns_when_telegram_forgot_the_hook():
    channel = TelegramChannel(make_inbox(mode="webhook"))
    attach(
        channel,
        FakeApi(
            {
                "getMe": {"id": 1, "username": "bot", "first_name": "Bot"},
                "getWebhookInfo": {"url": ""},
            }
        ),
    )

    result = await channel.health_check()
    assert result["status"] == "warning"
    assert "no webhook registered" in result["warning"]


def test_conflict_detection():
    assert TelegramChannel._is_webhook_conflict(ChannelError(WEBHOOK_CONFLICT))
    assert TelegramChannel._is_webhook_conflict(
        ChannelError("Telegram getUpdates failed [409]: Conflict")
    )
    assert not TelegramChannel._is_webhook_conflict(
        ChannelError("Telegram getUpdates failed [401]: Unauthorized")
    )
