"""Long-polling supervisor.

Owns exactly one asyncio task per active inbox configured in ``polling`` mode.
Each task runs an isolated loop — its own database session, its own channel
instance, its own backoff — so a misbehaving provider can never take another
inbox (or the API process) down with it.

The API layer talks to the module level :data:`supervisor` singleton through
:func:`reload_inbox` / :func:`remove_inbox`, which are safe no-ops when the
supervisor is not running (for instance when workers run in a separate process).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from ..channels.base import BaseChannel, ChannelError, build_channel
from ..db import SessionLocal, utcnow
from ..models import Inbox, InboxMode
from ..services import conversations as conversation_service

logger = logging.getLogger(__name__)

#: Error backoff bounds, in seconds.
MIN_BACKOFF = 1.0
MAX_BACKOFF = 60.0
#: Pause between successful iterations — long polling already blocks upstream.
IDLE_DELAY = 0.5


class PollingSupervisor:
    """Manage the set of per-inbox polling tasks."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def inbox_ids(self) -> list[int]:
        """Ids of the inboxes currently being polled."""
        return sorted(self._tasks)

    # -- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        """Spawn a polling task for every active polling inbox."""
        if self._running:
            return
        self._running = True
        inbox_ids = await self._load_pollable_ids()
        async with self._lock:
            for inbox_id in inbox_ids:
                self._spawn(inbox_id)
        logger.info("polling supervisor started for %d inbox(es)", len(self._tasks))

    async def stop(self) -> None:
        """Cancel every polling task and wait for them to unwind."""
        self._running = False
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: B014 - shutdown is best effort
                pass
        logger.info("polling supervisor stopped")

    # -- runtime reconfiguration ----------------------------------------
    async def reload_inbox(self, inbox_id: int) -> None:
        """(Re)start the task for ``inbox_id`` after a configuration change."""
        if not self._running:
            return
        await self.remove_inbox(inbox_id)
        inbox = await self._get_inbox(inbox_id)
        if inbox is None or not self._is_pollable(inbox):
            return
        async with self._lock:
            self._spawn(inbox_id)
        logger.info("polling task (re)started for inbox %s", inbox_id)

    async def remove_inbox(self, inbox_id: int) -> None:
        """Stop polling ``inbox_id`` if a task exists for it."""
        async with self._lock:
            task = self._tasks.pop(inbox_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: B014 - teardown is best effort
            pass
        logger.info("polling task stopped for inbox %s", inbox_id)

    # -- internals -------------------------------------------------------
    def _spawn(self, inbox_id: int) -> None:
        if inbox_id in self._tasks:
            return
        self._tasks[inbox_id] = asyncio.create_task(
            self._run_inbox(inbox_id), name=f"poll-inbox-{inbox_id}"
        )

    @staticmethod
    def _is_pollable(inbox: Inbox) -> bool:
        return bool(inbox.is_active) and inbox.mode == InboxMode.POLLING.value

    async def _load_pollable_ids(self) -> list[int]:
        async with SessionLocal() as db:
            rows = await db.scalars(
                select(Inbox.id).where(
                    Inbox.is_active.is_(True), Inbox.mode == InboxMode.POLLING.value
                )
            )
            return list(rows)

    @staticmethod
    async def _get_inbox(inbox_id: int) -> Inbox | None:
        async with SessionLocal() as db:
            return await db.get(Inbox, inbox_id)

    async def _run_inbox(self, inbox_id: int) -> None:
        """Poll one inbox until cancelled, backing off exponentially on errors."""
        backoff = MIN_BACKOFF
        logger.info("polling inbox %s", inbox_id)
        try:
            while self._running:
                try:
                    alive = await self._poll_once(inbox_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    await self._record_error(inbox_id, exc)
                    logger.warning(
                        "inbox %s poll failed (%s), retrying in %.0fs",
                        inbox_id,
                        exc,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)
                    continue

                if not alive:
                    logger.info("inbox %s is no longer pollable, stopping", inbox_id)
                    return
                backoff = MIN_BACKOFF
                await asyncio.sleep(IDLE_DELAY)
        except asyncio.CancelledError:
            logger.debug("polling task for inbox %s cancelled", inbox_id)
            raise

    async def _poll_once(self, inbox_id: int) -> bool:
        """Run a single fetch/dispatch cycle. Returns ``False`` to stop the loop."""
        async with SessionLocal() as db:
            inbox = await db.get(Inbox, inbox_id)
            if inbox is None or not self._is_pollable(inbox):
                return False

            channel: BaseChannel = build_channel(inbox)
            try:
                events, cursor = await channel.fetch_updates(inbox.cursor)
                for event in events:
                    try:
                        await conversation_service.process_inbound_event(
                            db, inbox, channel, event
                        )
                    except Exception:
                        logger.exception(
                            "inbox %s failed to process %s event", inbox_id, event.kind
                        )
                        await db.rollback()
                if cursor:
                    inbox.cursor = cursor
                inbox.last_polled_at = utcnow()
                inbox.connection_status = "connected"
                inbox.connection_error = None
                await db.commit()
            finally:
                await channel.close()
        return True

    async def _record_error(self, inbox_id: int, exc: BaseException) -> None:
        """Persist the failure on the inbox so the UI can surface it."""
        detail = str(exc) if isinstance(exc, ChannelError) else f"{type(exc).__name__}: {exc}"
        try:
            async with SessionLocal() as db:
                inbox = await db.get(Inbox, inbox_id)
                if inbox is None:
                    return
                inbox.connection_status = "error"
                inbox.connection_error = detail[:1000]
                await db.commit()
        except Exception:  # pragma: no cover - the database may be down too
            logger.debug("could not persist connection error for inbox %s", inbox_id)


#: Process-wide singleton used by the API and the standalone runner.
supervisor = PollingSupervisor()


async def start() -> None:
    """Start the singleton supervisor."""
    await supervisor.start()


async def stop() -> None:
    """Stop the singleton supervisor."""
    await supervisor.stop()


async def reload_inbox(inbox_id: int) -> None:
    """Restart polling for ``inbox_id``; no-op when the supervisor is idle."""
    await supervisor.reload_inbox(inbox_id)


async def remove_inbox(inbox_id: int) -> None:
    """Stop polling ``inbox_id``; no-op when the supervisor is idle."""
    await supervisor.remove_inbox(inbox_id)
