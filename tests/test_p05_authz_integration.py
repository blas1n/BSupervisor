"""Phase 0 P0.5 / Phase 5b — bsvibe-authz integration tests.

Verifies that the BSupervisor auth layer:
1. Re-exports `CurrentUser` and `ServiceKeyAuth("bsupervisor")` from
   ``bsupervisor.api.deps`` (replacing the legacy bsvibe-auth shim).
2. ``POST /api/events`` is service-only — accepts a service JWT scoped to
   ``aud="bsupervisor"`` and rejects user JWTs with 401/403.
3. ``verify_service_jwt`` from bsvibe-authz happy-path / unhappy-path works
   end-to-end for the BSupervisor receiver.

Phase 5b note: per-route admin gates moved from ``require_permission`` (OpenFGA
tuples) to ``require_scope`` (Phase 1 token-cutover catalog). The scope
matrix lives in ``tests/api/test_auth.py`` and is the single source of
truth post-migration.

Lockin §3 decision #16, Auth_Design §6.4.
"""

from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from bsvibe_authz import (
    AuthError,
    Settings as AuthzSettings,
    verify_service_jwt,
)
from bsvibe_authz.deps import (
    get_openfga_client,
    get_permission_cache,
    get_settings_dep,
)
from httpx import ASGITransport, AsyncClient

from bsupervisor.main import app
from bsupervisor.models.database import get_session


# ---------------------------------------------------------------------------
# Fixtures — bsvibe-authz Settings + JWT minting + fake OpenFGA
# ---------------------------------------------------------------------------


SERVICE_SIGNING_SECRET = "test-service-signing-secret-do-not-use-in-prod"
USER_JWT_SECRET = "test-user-jwt-secret-do-not-use-in-prod"
ISSUER = "https://auth.bsvibe.dev"


def _make_authz_settings() -> AuthzSettings:
    return AuthzSettings(
        bsvibe_auth_url=ISSUER,
        openfga_api_url="http://openfga.test:8080",
        openfga_store_id="store-test",
        openfga_auth_model_id="model-test",
        openfga_auth_token=None,
        service_token_signing_secret=SERVICE_SIGNING_SECRET,
        user_jwt_secret=USER_JWT_SECRET,
        user_jwt_algorithm="HS256",
        user_jwt_audience="bsvibe",
        user_jwt_issuer=ISSUER,
    )


def _make_user_jwt(
    *,
    sub: str = "00000000-0000-0000-0000-000000000001",
    active_tenant_id: str | None = "tenant-alpha",
    exp_offset: int = 600,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": sub,
        "email": "alice@bsvibe.dev",
        "active_tenant_id": active_tenant_id,
        "iat": now,
        "exp": now + exp_offset,
        "aud": "bsvibe",
    }
    return jwt.encode(payload, USER_JWT_SECRET, algorithm="HS256")


def _make_service_jwt(
    *,
    sub: str = "service:bsgateway",
    aud: str = "bsupervisor",
    scope: str = "bsupervisor.events",
    tenant_id: str | None = "tenant-alpha",
    exp_offset: int = 600,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": sub,
        "aud": aud,
        "scope": scope,
        "iat": now,
        "exp": now + exp_offset,
        "token_type": "service",
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, SERVICE_SIGNING_SECRET, algorithm="HS256")


class FakeFGAClient:
    """In-memory OpenFGA stub. Records every check and returns ``allow``."""

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.checks: list[tuple[str, str, str]] = []

    async def check(self, user: str, relation: str, object_: str) -> bool:
        self.checks.append((user, relation, object_))
        return self.allow

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []


@pytest.fixture
def authz_settings() -> AuthzSettings:
    return _make_authz_settings()


@pytest.fixture
def fake_fga() -> FakeFGAClient:
    return FakeFGAClient(allow=True)


@pytest.fixture
def fake_fga_deny() -> FakeFGAClient:
    return FakeFGAClient(allow=False)


@pytest.fixture
async def authz_client(db_session, authz_settings, fake_fga):
    """An ``AsyncClient`` with bsvibe-authz dependencies wired to fakes.

    Note: we intentionally *do not* override ``get_current_user`` here so
    each test exercises the real JWT verifier path.
    """

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_settings_dep] = lambda: authz_settings
    app.dependency_overrides[get_openfga_client] = lambda: fake_fga
    # Reset the module-level permission cache so allow/deny doesn't leak across
    # tests; we use a fresh cache instance per test.
    from bsvibe_authz.cache import PermissionCache

    cache = PermissionCache(ttl_s=0)  # ttl=0 → never reuse a decision across tests
    app.dependency_overrides[get_permission_cache] = lambda: cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Module re-export contract
# ---------------------------------------------------------------------------


class TestDepsReExports:
    """``bsupervisor.api.deps`` MUST surface bsvibe-authz primitives."""

    def test_current_user_alias_present(self) -> None:
        from bsupervisor.api import deps

        assert hasattr(deps, "CurrentUser")

    def test_service_key_auth_present(self) -> None:
        from bsupervisor.api import deps

        assert hasattr(deps, "ServiceKeyAuth")

    def test_get_current_user_uses_bsvibe_authz(self) -> None:
        """The legacy ``get_current_user`` must now come from bsvibe-authz so
        that test fixtures and middleware pivot to the shared library.
        """
        from bsupervisor.api import deps as bsupervisor_deps
        from bsvibe_authz.deps import get_current_user as authz_dep

        assert bsupervisor_deps.get_current_user is authz_dep


# ---------------------------------------------------------------------------
# Service JWT verification — happy / unhappy paths via bsvibe-authz directly
# ---------------------------------------------------------------------------


class TestServiceJwtVerifierE2E:
    """Verifies that ``verify_service_jwt`` accepts the JWT shape that
    BSGateway / BSNexus will issue for ``aud="bsupervisor"``.
    """

    def test_valid_bsupervisor_audience_accepted(self, authz_settings) -> None:
        token = _make_service_jwt(aud="bsupervisor", scope="bsupervisor.events")
        payload = verify_service_jwt(token, authz_settings, "bsupervisor")
        assert payload.aud == "bsupervisor"
        assert payload.has_scope("bsupervisor.events")
        assert payload.sub == "service:bsgateway"

    def test_wrong_audience_rejected(self, authz_settings) -> None:
        token = _make_service_jwt(aud="bsage", scope="bsage.read")
        with pytest.raises((AuthError, jwt.InvalidAudienceError)):
            verify_service_jwt(token, authz_settings, "bsupervisor")

    def test_scope_audience_mismatch_rejected(self, authz_settings) -> None:
        """A token claiming aud=bsupervisor but with a foreign-prefix scope must fail."""
        # Manually mint an "evil" token whose scope is for bsage even though
        # the audience claim says bsupervisor.
        token = _make_service_jwt(aud="bsupervisor", scope="bsage.read")
        with pytest.raises(AuthError):
            verify_service_jwt(token, authz_settings, "bsupervisor")

    def test_expired_rejected(self, authz_settings) -> None:
        token = _make_service_jwt(exp_offset=-60)
        with pytest.raises(AuthError):
            verify_service_jwt(token, authz_settings, "bsupervisor")


# ---------------------------------------------------------------------------
# POST /api/events — service-only
# ---------------------------------------------------------------------------


class TestEventsServiceOnly:
    """``POST /api/events`` MUST accept service JWTs and reject users."""

    async def test_post_events_service_jwt_accepted(self, authz_client: AsyncClient, fake_fga: FakeFGAClient) -> None:
        token = _make_service_jwt(scope="bsupervisor.events")
        resp = await authz_client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "agent_id": "agent-1",
                "source": "bsgateway",
                "event_type": "tool_use",
                "action": "exec",
                "target": "/tmp/x",
            },
        )
        assert resp.status_code == 201, resp.text

    async def test_post_events_user_jwt_rejected(self, authz_client: AsyncClient) -> None:
        """A user-issued JWT must NOT be accepted on the ingestion endpoint."""
        token = _make_user_jwt()
        resp = await authz_client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "agent_id": "agent-1",
                "source": "bsgateway",
                "event_type": "tool_use",
                "action": "exec",
                "target": "/tmp/x",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_post_events_unauthenticated_rejected(self, authz_client: AsyncClient) -> None:
        resp = await authz_client.post(
            "/api/events",
            json={
                "agent_id": "agent-1",
                "source": "bsgateway",
                "event_type": "tool_use",
                "action": "exec",
                "target": "/tmp/x",
            },
        )
        assert resp.status_code in (401, 403)

    async def test_post_events_service_jwt_without_tenant_rejected(self, authz_client: AsyncClient) -> None:
        token = _make_service_jwt(scope="bsupervisor.events", tenant_id=None)
        resp = await authz_client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "agent_id": "agent-1",
                "source": "bsgateway",
                "event_type": "tool_use",
                "action": "exec",
                "target": "/tmp/x",
            },
        )
        assert resp.status_code == 403


# Phase 5b note — Route gate semantics moved from OpenFGA tuples
# (``require_permission``) to scope strings (``require_scope``). The
# scope catalog and per-route assertions now live in
# ``tests/api/test_auth.py``; the matrix here was deleted to avoid
# duplicating the source of truth.
