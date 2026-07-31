"""Regressions around channel configuration and network error reporting."""
from __future__ import annotations

import httpx
import pytest

from app.channels.base import ChannelConfigError
from app.channels.telegram import TelegramChannel
from app.channels.telegram.api import TelegramApi

PROXY = "http://user:hunter2@proxy.internal:3128"


@pytest.mark.asyncio
async def test_validate_config_uses_the_inbox_proxy(monkeypatch):
    """The proxy typed into the form must be used to verify the token.

    Without this the check goes out directly and fails on any host that can
    only reach Telegram through the proxy.
    """
    seen: dict[str, str | None] = {}

    original_init = TelegramApi.__init__

    def spy(self, token, *, proxy=None, timeout=30.0):
        seen["proxy"] = proxy
        original_init(self, token, proxy=proxy, timeout=timeout)

    async def fake_call(self, method, **kwargs):
        assert method == "getMe"
        return {"id": 42, "username": "supportbot", "first_name": "Support"}

    monkeypatch.setattr(TelegramApi, "__init__", spy)
    monkeypatch.setattr(TelegramApi, "call", fake_call)

    config = await TelegramChannel.validate_config({"bot_token": "1:abc"}, proxy=PROXY)

    assert seen["proxy"] == PROXY
    assert config["bot_username"] == "supportbot"
    assert config["bot_id"] == 42


@pytest.mark.asyncio
async def test_validate_config_reports_the_transport_failure(monkeypatch):
    """A refused connection must not collapse into an empty message."""

    async def boom(self, method, **kwargs):
        raise httpx.ConnectError("")  # httpx often carries no message at all

    monkeypatch.setattr(TelegramApi, "call", TelegramApi.call)
    monkeypatch.setattr(
        httpx.AsyncClient, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError(""))
    )

    with pytest.raises(ChannelConfigError) as excinfo:
        await TelegramChannel.validate_config({"bot_token": "1:abc"})

    message = str(excinfo.value)
    assert message.strip()
    assert not message.rstrip().endswith(":")
    assert "cannot connect to api.telegram.org" in message
    assert "ConnectError" in message


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ConnectError(""), "cannot connect to api.telegram.org"),
        (httpx.ProxyError(""), "through the proxy"),
        (httpx.ConnectTimeout(""), "timed out"),
    ],
)
def test_transport_errors_are_actionable(exc, expected):
    api = TelegramApi("1:abc", proxy=PROXY, timeout=15.0)
    message = api._transport_error("getMe", exc)

    assert expected in message
    # The class name stands in for an empty str(exc).
    assert type(exc).__name__ in message
    # Credentials must never be echoed back to the operator.
    assert "hunter2" not in message
    assert "proxy.internal:3128" in message


def test_proxy_password_is_redacted():
    api = TelegramApi("1:abc", proxy=PROXY)
    assert api._safe_proxy() == "http://user:***@proxy.internal:3128"


def test_no_proxy_is_stated_explicitly():
    api = TelegramApi("1:abc")
    assert "no proxy configured" in api._transport_error("getMe", httpx.ConnectError(""))
