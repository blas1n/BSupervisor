"""Async database engine and session factory.

Phase A — delegates to :mod:`bsvibe_sqlalchemy`. The engine factory and
session helpers all live in the shared package now; this module exists
purely for the BSupervisor-side singletons (``engine`` / ``async_session_factory``)
and the legacy ``get_session`` ``Depends`` target that the existing
test fixtures override.

The factory is re-exported as :func:`create_engine_from_settings` so
``test_database_pool.py`` can patch ``create_async_engine`` on this
module and keep the Sprint 0–4 regression tests green.
"""

from __future__ import annotations

# ``create_async_engine`` is re-exported here so existing tests that
# ``patch.object(db_module, "create_async_engine")`` keep working without
# poking at ``bsvibe_sqlalchemy`` internals.
from bsvibe_sqlalchemy import (
    create_session_factory,
    make_get_db,
)
from bsvibe_sqlalchemy.engine import _is_sqlite  # noqa: F401 — kept for backward compat
from sqlalchemy.ext.asyncio import (  # noqa: F401 — public re-export
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bsupervisor.config import Settings, settings


def create_engine_from_settings(s: Settings) -> AsyncEngine:
    """Build an :class:`AsyncEngine` honouring the pool config in ``Settings``.

    Wraps :func:`bsvibe_sqlalchemy.engine.create_engine_from_settings`'s
    behaviour while patching :func:`create_async_engine` at the
    ``bsupervisor.models.database`` import point so existing tests that
    ``patch.object(db_module, "create_async_engine")`` keep working.
    """
    kwargs: dict = {"echo": s.debug}
    if not s.database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_timeout=s.db_pool_timeout,
            pool_recycle=s.db_pool_recycle,
            pool_pre_ping=s.db_pool_pre_ping,
        )
    return create_async_engine(s.database_url, **kwargs)


engine: AsyncEngine = create_engine_from_settings(settings)
async_session_factory = create_session_factory(engine)
get_session = make_get_db(async_session_factory)
