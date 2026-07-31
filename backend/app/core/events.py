"""In-process event bus + WebSocket fan-out.

Every domain mutation publishes an event here. Two consumers subscribe:

* :class:`ConnectionManager` pushes it to connected browsers over WebSocket;
* the webhook dispatcher forwards it to configured HTTP endpoints.

The bus is intentionally simple (asyncio only, single process). Swapping it for
Redis pub/sub later only requires reimplementing :func:`publish`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Listener = Callable[[str, dict[str, Any]], Awaitable[None]]

# Canonical event names emitted by the service.
EVENT_CONVERSATION_CREATED = "conversation.created"
EVENT_CONVERSATION_UPDATED = "conversation.updated"
EVENT_CONVERSATION_TYPING = "conversation.typing"
EVENT_MESSAGE_CREATED = "message.created"
EVENT_MESSAGE_UPDATED = "message.updated"
EVENT_MESSAGE_DELETED = "message.deleted"
EVENT_CONTACT_UPDATED = "contact.updated"
EVENT_INBOX_UPDATED = "inbox.updated"
EVENT_PRESENCE_UPDATED = "presence.updated"

ALL_EVENTS = [
    EVENT_CONVERSATION_CREATED,
    EVENT_CONVERSATION_UPDATED,
    EVENT_CONVERSATION_TYPING,
    EVENT_MESSAGE_CREATED,
    EVENT_MESSAGE_UPDATED,
    EVENT_MESSAGE_DELETED,
    EVENT_CONTACT_UPDATED,
    EVENT_INBOX_UPDATED,
    EVENT_PRESENCE_UPDATED,
]

_listeners: list[Listener] = []


def subscribe(listener: Listener) -> None:
    _listeners.append(listener)


async def publish(event: str, payload: dict[str, Any]) -> None:
    """Fan out ``event`` to every listener without letting one failure win."""
    for listener in list(_listeners):
        try:
            await listener(event, payload)
        except Exception:  # pragma: no cover - defensive
            logger.exception("event listener failed for %s", event)


class ConnectionManager:
    """Tracks WebSocket connections per user id."""

    def __init__(self) -> None:
        self._connections: dict[int, set[Any]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: Any) -> None:
        async with self._lock:
            self._connections[user_id].add(websocket)

    async def disconnect(self, user_id: int, websocket: Any) -> None:
        async with self._lock:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)

    @property
    def online_user_ids(self) -> list[int]:
        return list(self._connections.keys())

    async def send_to_user(self, user_id: int, message: dict[str, Any]) -> None:
        for ws in list(self._connections.get(user_id, ())):
            with contextlib.suppress(Exception):
                await ws.send_json(message)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)


manager = ConnectionManager()


async def _websocket_listener(event: str, payload: dict[str, Any]) -> None:
    await manager.broadcast({"event": event, "data": payload})


subscribe(_websocket_listener)
