"""Tiny forward-only migration runner.

``Base.metadata.create_all`` handles new installations; this module patches
existing databases when columns are added between releases. That split means a
step routinely finds its work already done — ``create_all`` created the table
*with* the new column on any installation younger than the step — so
"already exists" is a normal outcome, not a failure.

Two rules make that safe on PostgreSQL as well as SQLite:

* **Every step runs in its own transaction.** PostgreSQL aborts the entire
  transaction on the first error and refuses every later statement in it, so a
  single shared transaction turned one skipped step into a failed startup.
* **A step is recorded only when it really is applied** — either it ran, or the
  database says the change is already there. Anything else is a genuine schema
  problem and is raised, because limping on with a missing column only moves the
  failure to the first request that touches it.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """A step failed for a reason that is not "already applied"."""


# (id, sql) pairs applied in order. Never edit an applied step — append a new one.
STEPS: list[tuple[str, str]] = [
    (
        "0001_webhooks_payload_format",
        "ALTER TABLE webhooks ADD COLUMN payload_format VARCHAR(32) "
        "NOT NULL DEFAULT 'native'",
    ),
    (
        # `DEFAULT 1` was rejected by PostgreSQL ("column is of type boolean but
        # default expression is of type integer"). Editing this step is safe:
        # it can only have been recorded as applied on SQLite, where it did run.
        "0002_users_email_notifications",
        "ALTER TABLE users ADD COLUMN email_notifications BOOLEAN "
        "NOT NULL DEFAULT TRUE",
    ),
    (
        "0003_users_notification_settings",
        "ALTER TABLE users ADD COLUMN notification_settings JSON",
    ),
]

#: Substrings every supported backend uses to say "this change is already here".
#: PostgreSQL raises DuplicateColumn/DuplicateTable ("… already exists"), SQLite
#: raises OperationalError ("duplicate column name: …").
_ALREADY_APPLIED = ("already exists", "duplicate column")


def _is_already_applied(exc: BaseException) -> bool:
    """Did the step fail only because the database already had the change?"""
    parts = [type(exc).__name__, str(exc)]
    original = getattr(exc, "orig", None)
    if original is not None:
        parts += [type(original).__name__, str(original)]
    haystack = " ".join(parts).lower()
    return any(marker in haystack for marker in _ALREADY_APPLIED)


async def run_migrations(engine: AsyncEngine) -> None:
    if not STEPS:
        return

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "id VARCHAR(128) PRIMARY KEY)"
            )
        )

    async with engine.connect() as conn:
        applied = set(
            (await conn.execute(text("SELECT id FROM schema_migrations"))).scalars()
        )

    for step_id, sql in STEPS:
        if step_id in applied:
            continue

        try:
            # Its own transaction: on PostgreSQL a failure here must not be able
            # to poison the bookkeeping write below, or any later step.
            async with engine.begin() as conn:
                await conn.execute(text(sql))
            logger.info("migration %s applied", step_id)
        except Exception as exc:
            if not _is_already_applied(exc):
                raise MigrationError(f"migration {step_id} failed: {exc}") from exc
            logger.info("migration %s already present, recording it", step_id)

        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO schema_migrations (id) VALUES (:id)"),
                {"id": step_id},
            )
