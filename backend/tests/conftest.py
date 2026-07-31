"""Test harness: in-memory SQLite, an ASGI client and a dummy channel.

The environment is configured *before* ``app`` is imported so the settings
singleton picks up the throw-away database and storage directory.
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="chattysup-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{TMP_ROOT / 'test.db'}")
os.environ.setdefault("STORAGE_PATH", str(TMP_ROOT / "storage"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("RUN_WORKERS", "false")
os.environ.setdefault("ENABLE_REGISTRATION", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _ensure_channel_registry() -> None:
    """Import ``app.channels``, stubbing Telegram when it is not built yet."""
    try:
        import app.channels  # noqa: F401
    except Exception:
        from app.channels import base as channel_base

        stub = types.ModuleType("app.channels.telegram")

        class TelegramChannel(channel_base.BaseChannel):
            """Placeholder used only when the real channel is unavailable."""

            key = "telegram"
            display_name = "Telegram"

            async def send_message(self, chat_source_id, message):
                return channel_base.SendResult(source_id="stub")

        stub.TelegramChannel = TelegramChannel
        sys.modules["app.channels.telegram"] = stub
        import app.channels  # noqa: F401


_ensure_channel_registry()

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.channels.base import (  # noqa: E402
    BaseChannel,
    FieldSpec,
    InboundEvent,
    NormalizedContact,
    NormalizedMessage,
    SendResult,
    register,
)
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

#: Everything the dummy channel was asked to send, for assertions in tests.
SENT: list[tuple[str, Any]] = []


@register
class DummyChannel(BaseChannel):
    """An in-memory channel so tests never touch the network."""

    key = "dummy"
    display_name = "Dummy"
    description = "In-memory test channel"
    supports_polling = True
    supports_webhook = True
    capabilities = {"reactions", "typing"}
    config_fields = [
        FieldSpec(key="token", label="Token", kind="password", required=True, secret=True),
        FieldSpec(key="note", label="Note"),
    ]

    async def setup(self) -> dict[str, Any]:
        return {}

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "bot": "dummy"}

    async def send_message(self, chat_source_id: str, message) -> SendResult:
        SENT.append((chat_source_id, message))
        return SendResult(source_id=f"out-{len(SENT)}")

    async def send_reaction(self, chat_source_id, message_source_id, emojis) -> None:
        SENT.append((chat_source_id, ("reaction", emojis)))

    async def parse_webhook(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> list[InboundEvent]:
        return [
            InboundEvent(
                kind="message",
                chat_source_id=str(payload["chat_id"]),
                contact=NormalizedContact(
                    source_id=str(payload["chat_id"]),
                    name=payload.get("name", "Tester"),
                ),
                message=NormalizedMessage(
                    source_id=str(payload.get("message_id", "1")),
                    content=payload.get("text", ""),
                ),
            )
        ]


test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)


async def _override_get_db() -> AsyncIterator[Any]:
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture(autouse=True)
async def database() -> AsyncIterator[None]:
    """Fresh schema for every test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app.dependency_overrides[get_db] = _override_get_db
    SENT.clear()
    yield
    app.dependency_overrides.clear()
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
        yield ac


@pytest.fixture
async def admin(client: AsyncClient) -> dict[str, Any]:
    """Bootstrap the installation and return ``{token, user, headers}``."""
    response = await client.post(
        "/auth/register",
        json={"name": "Admin", "email": "admin@example.com", "password": "supersecret"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    body["headers"] = {"Authorization": f"Bearer {body['token']}"}
    return body


@pytest.fixture
async def inbox(client: AsyncClient, admin: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(
        "/inboxes",
        headers=admin["headers"],
        json={
            "name": "Support",
            "channel_type": "dummy",
            "mode": "webhook",
            "config": {"token": "s3cret"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def db_session() -> AsyncIterator[Any]:
    """A session on the same in-memory database the API fixtures use."""
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest.fixture(autouse=True)
def temp_storage(tmp_path, monkeypatch) -> None:
    """Keep attachments and avatars written by tests out of the repository."""
    from app.config import settings

    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "storage"))
