"""Tests for CORS wiring — Audit §M18.

The previous wiring read ``os.environ.get("CORS_ALLOWED_ORIGINS", ...)`` at
import time in ``main.py``, bypassing pydantic-settings entirely. The
consolidated implementation reads from ``settings.cors_allowed_origins`` so
all configuration flows through one validated source.
"""

import re

from starlette.middleware.cors import CORSMiddleware

from bsupervisor.config import Settings


def _cors_origins_in_app() -> list[str]:
    """Extract the configured CORS allow-list from the live FastAPI app."""
    from bsupervisor.main import app

    for mw in app.user_middleware:
        if mw.cls is CORSMiddleware:
            return list(mw.kwargs.get("allow_origins", []))
    return []


def test_main_does_not_call_os_environ_directly() -> None:
    """``main.py`` must not import ``os`` for CORS configuration anymore."""
    import inspect

    import bsupervisor.main as main_mod

    source = inspect.getsource(main_mod)
    # Allow `os` only if used elsewhere — but the original CORS lookup must go.
    assert 'os.environ.get("CORS_ALLOWED_ORIGINS"' not in source
    assert not re.search(r"os\.environ\.get\(['\"]CORS_ALLOWED_ORIGINS['\"]", source)


def test_app_uses_settings_cors_origins() -> None:
    """The CORSMiddleware must be configured from ``settings.cors_allowed_origins``."""
    origins = _cors_origins_in_app()
    # Default settings → at least the localhost origin must be present.
    assert any("localhost" in o for o in origins)


def test_settings_cors_default_matches_documented_value() -> None:
    s = Settings()
    assert s.cors_allowed_origins == ["http://localhost:3500"]
