"""Periodic housekeeping for conversations.

Two jobs run on every tick (``settings.automation_tick_seconds``):

* **wake** conversations whose snooze deadline has passed;
* **auto-resolve** conversations idle for longer than the owning inbox's
  ``auto_resolve_after_minutes``.

Both go through :mod:`app.services.conversations` so activity messages,
realtime events, webhooks and automations fire exactly as if an agent had
clicked the button.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..db import SessionLocal, utcnow
from ..models import Conversation, ConversationStatus, Inbox
from ..services import conversations as conversation_service

logger = logging.getLogger(__name__)


async def wake_snoozed(db: AsyncSession) -> int:
    """Reopen every conversation whose ``snoozed_until`` is in the past."""
    now = utcnow()
    rows = await db.scalars(
        select(Conversation).where(
            Conversation.status == ConversationStatus.SNOOZED.value,
            Conversation.snoozed_until.is_not(None),
            Conversation.snoozed_until <= now,
        )
    )
    count = 0
    for conversation in rows:
        await conversation_service.set_status(
            db, conversation, ConversationStatus.OPEN.value
        )
        count += 1
    return count


async def auto_resolve_idle(db: AsyncSession) -> int:
    """Resolve conversations idle beyond their inbox's auto-resolve window."""
    now = utcnow()
    inboxes = await db.scalars(
        select(Inbox).where(
            Inbox.is_active.is_(True),
            Inbox.auto_resolve_after_minutes.is_not(None),
            Inbox.auto_resolve_after_minutes > 0,
        )
    )
    count = 0
    for inbox in inboxes:
        cutoff = now - timedelta(minutes=int(inbox.auto_resolve_after_minutes or 0))
        rows = await db.scalars(
            select(Conversation).where(
                Conversation.inbox_id == inbox.id,
                Conversation.status.in_(
                    [ConversationStatus.OPEN.value, ConversationStatus.PENDING.value]
                ),
                Conversation.last_activity_at <= cutoff,
            )
        )
        for conversation in rows:
            await conversation_service.set_status(
                db, conversation, ConversationStatus.RESOLVED.value
            )
            count += 1
    return count


async def tick() -> tuple[int, int]:
    """Run one housekeeping pass. Returns ``(woken, resolved)`` counters."""
    async with SessionLocal() as db:
        try:
            woken = await wake_snoozed(db)
            resolved = await auto_resolve_idle(db)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    if woken or resolved:
        logger.info("scheduler woke %d and resolved %d conversation(s)", woken, resolved)
    return woken, resolved


class Scheduler:
    """Runs :func:`tick` on a fixed interval in a background task."""

    def __init__(self, interval: int | None = None) -> None:
        self.interval = interval or settings.automation_tick_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="conversation-scheduler")
        logger.info("scheduler started (every %ss)", self.interval)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: B014 - shutdown is best effort
            pass
        logger.info("scheduler stopped")

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.interval)
                try:
                    await tick()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("scheduler tick failed")
        except asyncio.CancelledError:
            logger.debug("scheduler task cancelled")
            raise


#: Process-wide singleton used by the API and the standalone runner.
scheduler = Scheduler()


async def start() -> None:
    """Start the singleton scheduler."""
    await scheduler.start()


async def stop() -> None:
    """Stop the singleton scheduler."""
    await scheduler.stop()
