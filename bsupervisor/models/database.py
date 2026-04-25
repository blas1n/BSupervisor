"""Async database engine and session factory.

Audit §M20 — pool sizing and recycle interval are configurable via
``settings.db_pool_*``. The factory short-circuits the pool-sizing knobs for
SQLite (which uses NullPool and would error on ``pool_size=...``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bsupervisor.config import Settings, settings


def create_engine_from_settings(s: Settings) -> AsyncEngine:
    """Build an ``AsyncEngine`` honoring the pool config in ``Settings``.

    SQLite (used in tests) wires through NullPool, which doesn't accept
    pool sizing arguments — those are skipped automatically.
    """
    kwargs: dict[str, Any] = {"echo": s.debug}
    if not s.database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_timeout=s.db_pool_timeout,
            pool_recycle=s.db_pool_recycle,
            pool_pre_ping=True,
        )
    return create_async_engine(s.database_url, **kwargs)


engine: AsyncEngine = create_engine_from_settings(settings)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
