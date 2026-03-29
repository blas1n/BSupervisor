"""Tests for configuration."""

from decimal import Decimal

from bsupervisor.config import Settings, settings


def test_settings_defaults() -> None:
    s = Settings()
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.debug is False
    assert s.auth_provider == "local"
    assert s.daily_cost_threshold_usd == "50.00"


def test_settings_singleton_exists() -> None:
    assert settings is not None
    assert isinstance(settings, Settings)
