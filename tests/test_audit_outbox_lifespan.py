"""Phase Audit Batch 2 — relay lifespan + outbox table wiring.

These tests pin two structural invariants that the rest of the audit
emit suite assumes are true:

1. ``register_audit_outbox_with(Base.metadata)`` ran at import time, so
   the SQLAlchemy ``audit_outbox`` table is part of the BSupervisor
   ``Base.metadata`` and the SQLite ``conftest`` ``create_all`` covers
   it without a separate migration step.
2. The relay singleton honours ``AuditSettings`` — when no audit URL is
   configured, ``relay.start()`` is a no-op and ``is_running()`` stays
   False (so dev / CI runs never try to reach BSVibe-Auth).
"""

from __future__ import annotations

import pytest

from bsupervisor.models import Base


def test_audit_outbox_table_registered_with_base_metadata():
    """``audit_outbox`` is part of the same MetaData Alembic targets."""
    assert "audit_outbox" in Base.metadata.tables, (
        "register_audit_outbox_with(Base.metadata) must run at import time so "
        "Alembic autogen + the test ``create_all`` see the table."
    )

    table = Base.metadata.tables["audit_outbox"]
    cols = {c.name for c in table.columns}
    # Mirror ``bsvibe_audit.outbox.schema.AuditOutboxRecord``.
    assert {
        "id",
        "event_id",
        "event_type",
        "occurred_at",
        "payload",
        "delivered_at",
        "retry_count",
        "last_error",
        "next_attempt_at",
        "dead_letter",
    }.issubset(cols)


@pytest.mark.asyncio
async def test_relay_disabled_when_audit_url_empty(monkeypatch):
    """No audit URL ⇒ relay never schedules a task."""
    from bsupervisor.core import audit as audit_mod

    monkeypatch.setenv("BSVIBE_AUTH_AUDIT_URL", "")
    relay = audit_mod.build_relay(session_factory=None)
    await relay.start()
    assert relay.is_running() is False
    await relay.stop()


@pytest.mark.asyncio
async def test_relay_started_and_stopped(monkeypatch):
    """When configured, the relay task starts and stop() cancels cleanly."""
    from bsupervisor.core import audit as audit_mod

    monkeypatch.setenv("BSVIBE_AUTH_AUDIT_URL", "https://auth.bsvibe.dev/api/audit/events")
    monkeypatch.setenv("BSVIBE_AUTH_AUDIT_SERVICE_TOKEN", "fake-token")
    monkeypatch.setenv("AUDIT_RELAY_INTERVAL_S", "0.05")

    # We need a session factory; reuse the test sqlite engine setup.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bsupervisor.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)

    relay = audit_mod.build_relay(session_factory=factory)
    await relay.start()
    assert relay.is_running() is True
    await relay.stop()
    assert relay.is_running() is False
    await engine.dispose()
