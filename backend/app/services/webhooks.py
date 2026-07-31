"""Outgoing webhook delivery.

Subscribes to the in-process event bus and forwards matching events to every
active :class:`~app.models.system.Webhook`. Payloads are signed with
``X-ChattySup-Signature`` (hex HMAC-SHA256 of the raw body) when a secret is set.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from sqlalchemy import select

from ..core import events as bus
from ..core.security import sign_payload
from ..db import SessionLocal, utcnow
from ..models import Webhook

logger = logging.getLogger(__name__)

TIMEOUT = 10.0
MAX_ATTEMPTS = 3
_tasks: set[asyncio.Task] = set()


async def dispatch(event: str, payload: dict[str, Any]) -> None:
    """Bus listener — schedules deliveries without blocking the caller."""
    if event == bus.EVENT_CONVERSATION_TYPING:
        return
    task = asyncio.create_task(_deliver_all(event, payload))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _deliver_all(event: str, payload: dict[str, Any]) -> None:
    try:
        async with SessionLocal() as db:
            hooks = (
                await db.scalars(select(Webhook).where(Webhook.active.is_(True)))
            ).all()
            targets = [h for h in hooks if not h.subscriptions or event in h.subscriptions]
            if not targets:
                return
            body = json.dumps(
                {"event": event, "timestamp": utcnow().isoformat(), "data": payload},
                default=str,
            ).encode("utf-8")

            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                for hook in targets:
                    await _deliver_one(client, hook, event, body)
            await db.commit()
    except Exception:  # pragma: no cover - webhook errors must stay contained
        logger.exception("webhook dispatch failed for %s", event)


async def _deliver_one(
    client: httpx.AsyncClient, hook: Webhook, event: str, body: bytes
) -> None:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ChattySup-Webhook/1.0",
        "X-ChattySup-Event": event,
    }
    if hook.secret:
        headers["X-ChattySup-Signature"] = sign_payload(hook.secret, body)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.post(hook.url, content=body, headers=headers)
            hook.last_status = response.status_code
            hook.last_delivered_at = utcnow()
            if response.is_success:
                hook.last_error = None
                return
            hook.last_error = f"HTTP {response.status_code}"
        except Exception as exc:
            hook.last_status = None
            hook.last_error = f"{type(exc).__name__}: {exc}"
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(2**attempt)


def install() -> None:
    """Register the dispatcher on the event bus (called once at startup)."""
    bus.subscribe(dispatch)
