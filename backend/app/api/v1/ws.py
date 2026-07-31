"""Realtime WebSocket endpoint.

Clients connect to ``/api/v1/ws?token=<jwt>``; the server pushes
``{"event": "<name>", "data": {...}}`` frames published on the event bus and
answers ``{"type": "ping"}`` with ``{"type": "pong"}``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...core import events as bus
from ...core.deps import COOKIE_NAME, resolve_user
from ...db import SessionLocal, utcnow
from ...serializers import serialize_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None) -> None:
    """Authenticate, register the socket and relay bus events to the browser."""
    raw_token = token or websocket.cookies.get(COOKIE_NAME)
    async with SessionLocal() as db:
        user = await resolve_user(db, raw_token)
        if user is not None:
            user.last_seen_at = utcnow()
            payload = serialize_user(user)
            await db.commit()

    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await bus.manager.connect(user.id, websocket)
    await websocket.send_json({"event": "connected", "data": {"user": payload}})
    await bus.publish(
        bus.EVENT_PRESENCE_UPDATED,
        {"user_id": user.id, "online": True, "online_user_ids": bus.manager.online_user_ids},
    )

    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - malformed frame / network reset
        logger.debug("websocket closed unexpectedly", exc_info=True)
    finally:
        await bus.manager.disconnect(user.id, websocket)
        await bus.publish(
            bus.EVENT_PRESENCE_UPDATED,
            {
                "user_id": user.id,
                "online": user.id in bus.manager.online_user_ids,
                "online_user_ids": bus.manager.online_user_ids,
            },
        )
