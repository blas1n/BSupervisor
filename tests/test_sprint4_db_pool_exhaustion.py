"""Sprint 4 — DB connection-pool exhaustion graceful behaviour (Audit §M20).

Sprint 2 wired pool sizing through ``Settings`` and added a factory that
omits pool args for SQLite. The unit suite (``test_database_pool.py``)
verifies the wire-through. Sprint 4 covers the *runtime* contract:

* When the pool is exhausted (more concurrent borrowers than
  ``pool_size + max_overflow``), additional borrowers MUST wait up to
  ``pool_timeout`` and then raise — not deadlock or silently corrupt
  state.
* The factory MUST honour an explicit ``pool_timeout=0`` for
  fast-failure deployments.
* SQLite's NullPool MUST NOT receive any pool sizing kwargs (sqlalchemy
  raises if it does).
* Settings overrides (``db_pool_*``) MUST be observable on the engine
  the factory returns.

We exercise the engine factory directly (not the full FastAPI app)
because the production engine is global and shared across tests; we don't
want to monkey-patch it. This still gives us a real pool to exercise.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import TimeoutError as SAOperationalTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from bsupervisor.config import Settings
from bsupervisor.models import database as db_module


@pytest.fixture
def pg_settings_factory():
    """Build a Settings instance that *looks* like Postgres without connecting."""

    def _build(**overrides) -> Settings:
        defaults = {
            "database_url": "postgresql+asyncpg://user:pw@localhost/test",
        }
        defaults.update(overrides)
        return Settings(**defaults)

    return _build


class TestPoolFactoryHonoursOverrides:
    def test_explicit_overrides_propagate(self, pg_settings_factory) -> None:
        from unittest.mock import patch

        s = pg_settings_factory(
            db_pool_size=3,
            db_max_overflow=2,
            db_pool_timeout=5,
            db_pool_recycle=120,
        )
        with patch.object(db_module, "create_async_engine") as mock_create:
            db_module.create_engine_from_settings(s)

        kwargs = mock_create.call_args.kwargs
        assert kwargs["pool_size"] == 3
        assert kwargs["max_overflow"] == 2
        assert kwargs["pool_timeout"] == 5
        assert kwargs["pool_recycle"] == 120
        assert kwargs["pool_pre_ping"] is True

    def test_zero_pool_timeout_allowed_for_fast_fail(self, pg_settings_factory) -> None:
        """``pool_timeout=0`` is a legitimate "fail-immediately" setting."""
        from unittest.mock import patch

        s = pg_settings_factory(db_pool_timeout=0)
        with patch.object(db_module, "create_async_engine") as mock_create:
            db_module.create_engine_from_settings(s)

        assert mock_create.call_args.kwargs["pool_timeout"] == 0

    def test_sqlite_branch_does_not_pass_pool_kwargs(self) -> None:
        """SQLite uses NullPool — passing pool_size raises TypeError."""
        from unittest.mock import patch

        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        with patch.object(db_module, "create_async_engine") as mock_create:
            db_module.create_engine_from_settings(s)

        kwargs = mock_create.call_args.kwargs
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs
        assert "pool_timeout" not in kwargs
        assert "pool_recycle" not in kwargs
        assert "pool_pre_ping" not in kwargs


class TestSqliteEngineRoundTrip:
    """The factory must produce a usable engine for the test profile."""

    async def test_sqlite_engine_executes_a_query(self) -> None:
        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        engine: AsyncEngine = db_module.create_engine_from_settings(s)
        try:
            from sqlalchemy import text

            async with engine.connect() as conn:
                row = (await conn.execute(text("SELECT 42"))).scalar_one()
            assert row == 42
        finally:
            await engine.dispose()

    async def test_sqlite_does_not_use_queue_pool(self) -> None:
        """SQLite gets SQLAlchemy's default async pool (StaticPool/NullPool),
        NOT a tunable QueuePool — confirms the factory's branch removed the
        pool-sizing kwargs, otherwise SQLAlchemy would pick QueuePool."""
        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        engine: AsyncEngine = db_module.create_engine_from_settings(s)
        try:
            assert not isinstance(engine.pool, QueuePool)
        finally:
            await engine.dispose()


class TestPoolExhaustionGracefulOnRealPool:
    """A real (non-NullPool) engine raises TimeoutError on exhaustion, not deadlock."""

    async def test_pool_exhaustion_raises_timeout(self) -> None:
        """Confirm the pool refuses additional borrowers after pool_size+max_overflow."""
        # We can't run a real Postgres in unit tests, but we can attach a
        # QueuePool to an in-memory aiosqlite database. SQLite's async
        # implementation respects pool sizing here because we override it.
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import AsyncAdaptedQueuePool

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,  # 1s wait then bail
        )
        try:
            from sqlalchemy import text

            # Borrow the only connection.
            held_conn = await engine.connect()

            async def _try_borrow() -> bool:
                try:
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                    return True
                except SAOperationalTimeoutError:
                    return False

            # Second borrower must time out gracefully.
            ok = await _try_borrow()
            assert ok is False, "Pool exhaustion must raise sqlalchemy TimeoutError, not deadlock or 500"

            # After the held connection is released, traffic resumes.
            await held_conn.close()
            ok = await _try_borrow()
            assert ok is True
        finally:
            await engine.dispose()

    async def test_concurrent_borrowers_serialize_when_pool_full(self) -> None:
        """When pool is full, waiters queue (FIFO) and each succeed in turn."""
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import AsyncAdaptedQueuePool

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=AsyncAdaptedQueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=10,
        )
        try:
            results: list[int] = []

            async def _borrow_and_run(value: int) -> None:
                async with engine.connect() as conn:
                    row = (await conn.execute(text(f"SELECT {value}"))).scalar_one()
                    results.append(row)

            await asyncio.gather(*[_borrow_and_run(i) for i in range(5)])
            assert sorted(results) == [0, 1, 2, 3, 4]
        finally:
            await engine.dispose()
