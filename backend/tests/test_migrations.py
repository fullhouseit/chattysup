"""Regressions for the migration runner.

The bug these cover took production down on startup: every step shared one
transaction, so the first "already exists" — a routine outcome, because
``create_all`` builds new installations with the newest columns — aborted the
PostgreSQL transaction and every later statement, including the bookkeeping
insert, failed with ``InFailedSQLTransactionError``.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import migrations


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))
    yield engine
    await engine.dispose()


async def applied_ids(engine) -> set[str]:
    async with engine.connect() as conn:
        return set((await conn.execute(text("SELECT id FROM schema_migrations"))).scalars())


async def columns(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in rows}


@pytest.mark.asyncio
async def test_a_skipped_step_does_not_stop_the_ones_after_it(engine, monkeypatch):
    """The production failure: step 1 is already applied, steps 2-3 must run."""
    monkeypatch.setattr(
        migrations,
        "STEPS",
        [
            ("0001_already_there", "ALTER TABLE widgets ADD COLUMN id INTEGER"),
            ("0002_colour", "ALTER TABLE widgets ADD COLUMN colour VARCHAR(16)"),
            ("0003_size", "ALTER TABLE widgets ADD COLUMN size INTEGER"),
        ],
    )

    await migrations.run_migrations(engine)

    assert await columns(engine, "widgets") == {"id", "colour", "size"}
    assert await applied_ids(engine) == {"0001_already_there", "0002_colour", "0003_size"}


@pytest.mark.asyncio
async def test_running_twice_changes_nothing(engine, monkeypatch):
    monkeypatch.setattr(
        migrations,
        "STEPS",
        [("0001_colour", "ALTER TABLE widgets ADD COLUMN colour VARCHAR(16)")],
    )

    await migrations.run_migrations(engine)
    await migrations.run_migrations(engine)  # a restart must be a no-op

    assert await applied_ids(engine) == {"0001_colour"}


@pytest.mark.asyncio
async def test_a_real_failure_is_raised_and_not_recorded(engine, monkeypatch):
    """Recording a failed step would hide schema drift until the first request."""
    monkeypatch.setattr(
        migrations,
        "STEPS",
        [("0001_broken", "ALTER TABLE does_not_exist ADD COLUMN x INTEGER")],
    )

    with pytest.raises(migrations.MigrationError, match="0001_broken"):
        await migrations.run_migrations(engine)

    assert await applied_ids(engine) == set()


@pytest.mark.asyncio
async def test_a_failure_does_not_block_later_steps_from_being_attempted(engine, monkeypatch):
    """The first step failing must not poison the connection for the rest."""
    monkeypatch.setattr(
        migrations,
        "STEPS",
        [
            ("0001_colour", "ALTER TABLE widgets ADD COLUMN colour VARCHAR(16)"),
            ("0002_broken", "ALTER TABLE does_not_exist ADD COLUMN x INTEGER"),
        ],
    )

    with pytest.raises(migrations.MigrationError):
        await migrations.run_migrations(engine)

    # The step before the failure is committed and recorded on its own.
    assert "colour" in await columns(engine, "widgets")
    assert await applied_ids(engine) == {"0001_colour"}


@pytest.mark.parametrize(
    "message",
    [
        'column "payload_format" of relation "webhooks" already exists',
        "duplicate column name: email_notifications",
        'relation "schema_migrations" already exists',
    ],
)
def test_already_applied_is_recognised_across_backends(message):
    assert migrations._is_already_applied(RuntimeError(message))


def test_a_genuine_error_is_not_mistaken_for_already_applied():
    assert not migrations._is_already_applied(
        RuntimeError('relation "users" does not exist')
    )
    assert not migrations._is_already_applied(
        RuntimeError("column is of type boolean but default expression is of type integer")
    )


def test_shipped_steps_avoid_the_integer_boolean_default():
    """PostgreSQL rejects `DEFAULT 1` on a BOOLEAN column."""
    for step_id, sql in migrations.STEPS:
        normalised = " ".join(sql.upper().split())
        if "BOOLEAN" in normalised:
            assert "DEFAULT 1" not in normalised, step_id
            assert "DEFAULT TRUE" in normalised or "DEFAULT FALSE" in normalised, step_id
