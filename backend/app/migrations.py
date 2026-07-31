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
STEPS: list[tuple[str, str]] = []


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
