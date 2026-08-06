"""Tiny forward-only migration runner.

``Base.metadata.create_all`` handles new installations; this module patches
existing databases when columns are added between releases. Each step is a
plain SQL statement that must be safe to skip when it fails with "duplicate
column" / "already exists".
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# (id, sql) pairs applied in order. Never edit an applied step — append a new one.
STEPS: list[tuple[str, str]] = [
    (
        "0001_webhooks_payload_format",
        "ALTER TABLE webhooks ADD COLUMN payload_format VARCHAR(32) "
        "NOT NULL DEFAULT 'native'",
    ),
    (
        "0002_users_email_notifications",
        "ALTER TABLE users ADD COLUMN email_notifications BOOLEAN "
        "NOT NULL DEFAULT 1",
    ),
    (
        "0003_users_notification_settings",
        "ALTER TABLE users ADD COLUMN notification_settings JSON",
    ),
]


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
        applied = set(
            (await conn.execute(text("SELECT id FROM schema_migrations"))).scalars()
        )
        for step_id, sql in STEPS:
            if step_id in applied:
                continue
            try:
                await conn.execute(text(sql))
            except Exception as exc:  # pragma: no cover - idempotency guard
                logger.warning("migration %s skipped: %s", step_id, exc)
            await conn.execute(
                text("INSERT INTO schema_migrations (id) VALUES (:id)"),
                {"id": step_id},
            )
