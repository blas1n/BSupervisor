"""TASK-005 — end-to-end CLI dogfood smoke.

The other CLI tests stub ``build_client`` with a ``MagicMock`` to pin the
request shape. This file does the opposite: it wires the CLI through a
real FastAPI app via :class:`httpx.ASGITransport` so the request actually
hits the same routers / auth gates that production traffic sees, only
with the database swapped for an in-memory SQLite and ``get_current_user``
overridden to an admin-role principal.

What this proves:

* ``bsupervisor agents add`` → ``bsupervisor agents list`` round-trips
  through ``POST /api/rules`` + ``GET /api/rules`` and the rule appears.
* ``bsupervisor audit list -o json`` emits valid JSON (the docstring's
  ``| jq`` smoke-test surrogate).
* The admin-role principal clears every Phase 2a auth gate —
  ``require_permission`` on reads, ``require_admin`` on writes / config
  (catalog drift on a write would 403 here).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest
from bsvibe_core import configure_logging
from bsvibe_authz import User
from bsvibe_authz.deps import get_current_user, get_openfga_client
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from bsupervisor.api.deps import bsupervisor_service_auth
from bsupervisor.main import app as fastapi_app
from bsupervisor.models import Base
from bsupervisor.models.database import get_session


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# fixtures — mirror conftest.py wiring but scoped to this file so the e2e
# suite can be reasoned about in isolation.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _authz_env() -> None:
    os.environ.setdefault("BSVIBE_AUTH_URL", "https://auth.bsvibe.dev")
    os.environ.setdefault("OPENFGA_API_URL", "http://openfga.test:8080")
    os.environ.setdefault("OPENFGA_STORE_ID", "store-test")
    os.environ.setdefault("OPENFGA_AUTH_MODEL_ID", "model-test")
    os.environ.setdefault("SERVICE_TOKEN_SIGNING_SECRET", "test-service-signing-secret-do-not-use")
    os.environ.setdefault("USER_JWT_SECRET", "test-user-jwt-secret-do-not-use")


@pytest.fixture(autouse=True)
def _route_structlog_to_stderr() -> None:
    """Route structlog output to stderr for the duration of these tests.

    The CLI emits its result body to stdout via ``OutputFormatter``; the
    server-side rule-engine / router code emits structlog lines that, by
    default, also land on stdout. Letting both share stdout means
    ``json.loads(result.stdout)`` sees two JSON objects and bombs. Routing
    structlog to stderr keeps the CLI's stdout contract clean (one
    payload, one parse) without touching production wiring.
    """
    configure_logging(level="info", service_name="bsupervisor", stream=sys.stderr)


class _AllowAllFGA:
    async def check(self, user: str, relation: str, object_: str) -> bool:
        return True

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []

    async def write_tuple(self, user: str, relation: str, object_: str) -> None:
        # Forward-readiness lazy tuple-write hook (bsvibe-authz 1.3.0).
        return None


@pytest.fixture
async def asgi_client() -> AsyncIterator[AsyncClient]:
    """FastAPI app bound to in-memory SQLite + superuser scope."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    fake_user = User(
        id="bootstrap-admin",
        email="bootstrap@bsvibe.dev",
        active_tenant_id="tenant-test",
        # Phase 2a: read routes gate on ``require_permission`` (allowed by
        # the allow-all OpenFGA stub below); mutation / admin-config routes
        # gate on ``require_admin`` — so the principal carries an admin role.
        scope=["bsupervisor:*"],
        app_metadata={"role": "owner"},
    )

    async def _override_user() -> User:
        return fake_user

    async def _override_service_auth() -> Any:
        from bsvibe_authz import ServiceTokenPayload

        return ServiceTokenPayload(
            iss="https://auth.bsvibe.dev",
            sub="service:e2e",
            aud="bsupervisor",
            scope="bsupervisor.events",
            iat=0,
            exp=2_000_000_000,
            token_type="service",
            tenant_id="tenant-test",
        )

    fastapi_app.dependency_overrides[get_session] = _override_get_session
    fastapi_app.dependency_overrides[get_current_user] = _override_user
    fastapi_app.dependency_overrides[get_openfga_client] = lambda: _AllowAllFGA()
    fastapi_app.dependency_overrides[bsupervisor_service_auth] = _override_service_auth

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _bridge(monkeypatch: pytest.MonkeyPatch, modules: tuple[str, ...], asgi: AsyncClient) -> None:
    """Point each CLI module's ``build_client`` at the live ASGI transport.

    The CLI only awaits ``client.get / post / delete / request / aclose``
    — every method on :class:`httpx.AsyncClient` already, so we can hand
    the ASGI client over directly. ``aclose`` is a no-op here because the
    fixture owns the lifecycle.
    """

    class _Wrapped:
        def __init__(self, inner: AsyncClient) -> None:
            self._inner = inner

        async def get(self, path: str, **kwargs: Any) -> Any:
            return await self._inner.get(path, **kwargs)

        async def post(self, path: str, **kwargs: Any) -> Any:
            return await self._inner.post(path, **kwargs)

        async def delete(self, path: str, **kwargs: Any) -> Any:
            return await self._inner.delete(path, **kwargs)

        async def request(self, method: str, path: str, **kwargs: Any) -> Any:
            return await self._inner.request(method, path, **kwargs)

        async def aclose(self) -> None:
            return None

    wrapped = _Wrapped(asgi)
    for module in modules:
        monkeypatch.setattr(f"bsupervisor.cli.commands.{module}.build_client", lambda ctx, _w=wrapped: _w)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_agents_add_then_list_round_trips(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, asgi_client: AsyncClient
) -> None:
    """``add`` + ``list`` round-trip through the real router stack."""
    from bsupervisor.cli.main import app

    _bridge(monkeypatch, ("agents",), asgi_client)

    add_result = runner.invoke(
        app,
        [
            "--url",
            "http://test",
            "--token",
            "bootstrap-equivalent",
            "-o",
            "json",
            "agents",
            "add",
            "--name",
            "no-secrets",
            "--type",
            "pattern",
            "--pattern",
            ".env",
            "--severity",
            "critical",
            "--action",
            "block",
            "--description",
            "deny .env access",
        ],
    )
    assert add_result.exit_code == 0, add_result.stdout + add_result.stderr
    created = json.loads(add_result.stdout)
    assert created["name"] == "no-secrets"
    assert created["action"] == "block"
    rule_id = created["id"]

    list_result = runner.invoke(
        app,
        ["--url", "http://test", "--token", "bootstrap-equivalent", "-o", "json", "agents", "list"],
    )
    assert list_result.exit_code == 0, list_result.stdout + list_result.stderr
    rules = json.loads(list_result.stdout)
    names = {r["name"] for r in rules}
    ids = {r["id"] for r in rules}
    assert "no-secrets" in names
    assert rule_id in ids


def test_audit_list_emits_valid_json(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, asgi_client: AsyncClient
) -> None:
    """``audit list -o json`` parses cleanly (``| jq`` surrogate)."""
    from bsupervisor.cli.main import app

    _bridge(monkeypatch, ("audit",), asgi_client)

    result = runner.invoke(
        app,
        ["--url", "http://test", "--token", "bootstrap-equivalent", "-o", "json", "audit", "list"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)  # raises on invalid JSON
    assert isinstance(payload, list)


def test_bootstrap_principal_clears_auth_gates(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, asgi_client: AsyncClient
) -> None:
    """The admin-role superuser principal clears every CLI's auth gate.

    Phase 2a: read routes gate on ``require_permission`` (permissive /
    OpenFGA-allowed here), admin-config routes on ``require_admin``. If a
    router silently swaps to a stricter gate (or the principal loses its
    admin role), one of these calls will 403 — making catalog drift loud
    at the CLI surface, not just the unit-test surface.
    """
    from bsupervisor.cli.main import app

    _bridge(monkeypatch, ("agents", "audit", "costs", "settings", "incidents"), asgi_client)

    base = ["--url", "http://test", "--token", "bootstrap", "-o", "json"]
    for argv in (
        ["agents", "list"],
        ["incidents", "list"],
        ["audit", "list"],
        ["costs", "report"],
        ["settings", "get"],
    ):
        result = runner.invoke(app, base + argv)
        assert result.exit_code == 0, f"{argv}: {result.stdout + result.stderr}"


def test_settings_set_round_trip_persists(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, asgi_client: AsyncClient
) -> None:
    """``settings set slack_webhook_url X`` then ``settings get slack_webhook_url`` returns X."""
    from bsupervisor.cli.main import app

    _bridge(monkeypatch, ("settings",), asgi_client)

    base = ["--url", "http://test", "--token", "bootstrap", "-o", "json"]

    set_result = runner.invoke(
        app,
        base + ["settings", "set", "slack_webhook_url", "https://hooks.slack.com/services/TEST"],
    )
    assert set_result.exit_code == 0, set_result.stdout + set_result.stderr

    get_result = runner.invoke(app, base + ["settings", "get", "slack_webhook_url"])
    assert get_result.exit_code == 0, get_result.stdout + get_result.stderr
    payload = json.loads(get_result.stdout)
    assert payload == {
        "key": "slack_webhook_url",
        "value": "https://hooks.slack.com/services/TEST",
    }


def test_global_help_lists_all_subapps(runner: CliRunner) -> None:
    """``bsupervisor --help`` mentions every TASK-004/005 sub-app."""
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    out = _strip_ansi(result.output)
    for sub in ("agents", "incidents", "audit", "costs", "settings"):
        assert sub in out, f"missing sub-app {sub!r} in --help:\n{out}"
