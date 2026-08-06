"""Waiting for a row published by a still-open transaction.

The event bus fires from *inside* the producing transaction, while listeners
(outgoing webhooks, email notifications) run as background tasks with their own
sessions — where the row is invisible until the producer commits. Without a
wait, the listener silently does nothing, which is exactly how every
``message_created`` webhook went missing until this was found in a live
installation.

Callers must open a **fresh session per attempt**: a session that has already
queried the table keeps its snapshot and would never observe the new row.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import SessionLocal

logger = logging.getLogger(__name__)

#: Cumulative wait of ~1.6s. Commits land in milliseconds; anything slower is
#: almost always a rollback, and a rollback has nothing to deliver.
DELAYS: tuple[float, ...] = (0.0, 0.05, 0.15, 0.4, 1.0)

T = TypeVar("T")


async def wait_for_row(
    model: type[T], identifier: Any, *, delays: tuple[float, ...] | None = None
) -> T | None:
    """Return the row once it is committed, or ``None`` if it never appears.

    The returned instance belongs to a session that is already closed, so read
    the attributes you need while it is loaded, or re-query in your own session.
    """
    if identifier is None:
        return None
    for delay in delays or DELAYS:
        if delay:
            await asyncio.sleep(delay)
        async with SessionLocal() as db:
            row = await db.get(model, identifier)
            if row is not None:
                return row
    return None


async def run_when_visible(
    model: type[Any],
    identifier: Any,
    handler: Any,
    *,
    delays: tuple[float, ...] | None = None,
) -> Any:
    """Call ``handler(db, row)`` in a fresh session once ``row`` is committed.

    Returns ``None`` when the row never becomes visible, so the caller can tell
    "nothing to do" from "handled".
    """
    if identifier is None:
        return None
    for delay in delays or DELAYS:
        if delay:
            await asyncio.sleep(delay)
        async with SessionLocal() as db:
            row = await db.get(model, identifier)
            if row is not None:
                return await handler(db, row)
    logger.debug("%s %s never became visible", model.__name__, identifier)
    return None


async def is_visible(db: AsyncSession, model: type[Any], identifier: Any) -> bool:
    """Is this row committed and readable in ``db``?"""
    if identifier is None:
        return False
    return await db.get(model, identifier) is not None
