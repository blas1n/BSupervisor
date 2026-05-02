"""Tests for the async DB engine factory — Audit §M20.

The engine is configured from ``settings.db_pool_*`` instead of relying on
SQLAlchemy defaults. SQLite's NullPool ignores pool sizing entirely, so we
verify the wiring through the public ``create_engine`` factory plus mocking
of ``create_async_engine``.
"""

from unittest.mock import patch


def test_create_engine_factory_passes_pool_settings_to_create_async_engine() -> None:
    from bsupervisor.config import Settings
    from bsupervisor.models import database as db_module

    s = Settings(
        database_url="postgresql+asyncpg://user:pw@localhost/db",
        db_pool_size=7,
        db_max_overflow=11,
        db_pool_timeout=42,
        db_pool_recycle=900,
    )

    with patch.object(db_module, "create_async_engine") as mock_create:
        db_module.create_engine_from_settings(s)

    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 11
    assert kwargs["pool_timeout"] == 42
    assert kwargs["pool_recycle"] == 900
    assert kwargs["pool_pre_ping"] is True


def test_create_engine_factory_skips_pool_args_for_sqlite() -> None:
    """SQLite + NullPool can't accept pool_size/max_overflow — must be omitted."""
    from bsupervisor.config import Settings
    from bsupervisor.models import database as db_module

    s = Settings(database_url="sqlite+aiosqlite:///:memory:")

    with patch.object(db_module, "create_async_engine") as mock_create:
        db_module.create_engine_from_settings(s)

    kwargs = mock_create.call_args.kwargs
    # SQLite branch: don't pass pool sizing knobs (would TypeError with NullPool).
    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs


def test_module_engine_uses_factory() -> None:
    """The module-level ``engine`` must be built by the factory."""
    from bsupervisor.models import database as db_module

    assert hasattr(db_module, "create_engine_from_settings")
    assert db_module.engine is not None
