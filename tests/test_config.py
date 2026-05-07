"""Tests for configuration."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from bsupervisor.config import Settings, settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.debug is False
    assert s.auth_provider == "local"
    assert s.daily_cost_threshold_usd == Decimal("50.00")


def test_token_cutover_hooks_default_empty() -> None:
    s = Settings()
    assert s.bootstrap_token_hash == ""
    assert s.introspection_url == ""
    assert s.introspection_client_id == ""
    assert s.introspection_client_secret == ""


def test_token_cutover_hooks_loaded_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BOOTSTRAP_TOKEN_HASH", "abc123")
    monkeypatch.setenv("INTROSPECTION_URL", "https://auth.bsvibe.dev/api/tokens/introspect")
    monkeypatch.setenv("INTROSPECTION_CLIENT_ID", "supervisor")
    monkeypatch.setenv("INTROSPECTION_CLIENT_SECRET", "secret")
    s = Settings()
    assert s.bootstrap_token_hash == "abc123"
    assert s.introspection_url.endswith("/introspect")
    assert s.introspection_client_id == "supervisor"
    assert s.introspection_client_secret == "secret"


def test_settings_singleton_exists() -> None:
    assert settings is not None
    assert isinstance(settings, Settings)


# ---------------------------------------------------------------------------
# Audit §M17 — daily budget configurability
# ---------------------------------------------------------------------------


class TestDailyBudget:
    def test_daily_budget_default_is_one_hundred_usd(self) -> None:
        """Default preserves the previous hardcoded value (api/costs.py:40)."""
        s = Settings()
        assert s.daily_budget_usd == Decimal("100.00")

    def test_daily_budget_overridable_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("DAILY_BUDGET_USD", "250.50")
        s = Settings()
        assert s.daily_budget_usd == Decimal("250.50")

    def test_daily_budget_rejects_negative(self, monkeypatch) -> None:
        monkeypatch.setenv("DAILY_BUDGET_USD", "-1")
        with pytest.raises(ValidationError):
            Settings()


# ---------------------------------------------------------------------------
# Audit §M18 — CORS via pydantic-settings
# ---------------------------------------------------------------------------


class TestCorsAllowedOrigins:
    def test_cors_default_localhost(self) -> None:
        s = Settings()
        assert s.cors_allowed_origins == ["http://localhost:3500"]

    def test_cors_parses_comma_separated_env(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "CORS_ALLOWED_ORIGINS",
            "https://supervisor.bsvibe.dev,https://api.bsvibe.dev",
        )
        s = Settings()
        assert s.cors_allowed_origins == [
            "https://supervisor.bsvibe.dev",
            "https://api.bsvibe.dev",
        ]

    def test_cors_strips_whitespace_and_drops_empties(self, monkeypatch) -> None:
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "  https://a.io  , ,https://b.io,")
        s = Settings()
        assert s.cors_allowed_origins == ["https://a.io", "https://b.io"]


# ---------------------------------------------------------------------------
# Audit §M20 — DB connection pool sizing
# ---------------------------------------------------------------------------


class TestDbPoolSettings:
    def test_pool_defaults(self) -> None:
        s = Settings()
        # Conservative defaults appropriate for a single Mac-Mini deploy.
        assert s.db_pool_size == 10
        assert s.db_max_overflow == 20
        assert s.db_pool_timeout == 30
        assert s.db_pool_recycle == 1800

    def test_pool_overridable(self, monkeypatch) -> None:
        monkeypatch.setenv("DB_POOL_SIZE", "5")
        monkeypatch.setenv("DB_MAX_OVERFLOW", "7")
        monkeypatch.setenv("DB_POOL_TIMEOUT", "60")
        monkeypatch.setenv("DB_POOL_RECYCLE", "900")
        s = Settings()
        assert s.db_pool_size == 5
        assert s.db_max_overflow == 7
        assert s.db_pool_timeout == 60
        assert s.db_pool_recycle == 900

    def test_pool_size_rejects_negative(self, monkeypatch) -> None:
        monkeypatch.setenv("DB_POOL_SIZE", "-1")
        with pytest.raises(ValidationError):
            Settings()
