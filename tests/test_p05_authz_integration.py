"""Phase 0 P0.5 — bsvibe-authz integration tests.

Verifies that the BSupervisor auth layer:
1. Re-exports `CurrentUser` and `ServiceKeyAuth("bsupervisor")` from
   ``bsupervisor.api.deps`` (replacing the legacy bsvibe-auth shim).
2. Each route is guarded by ``require_permission(...)`` with the correct
   ``bsupervisor.<resource>.<action>`` identifier.
3. ``POST /api/events`` is service-only — accepts a service JWT scoped to
   ``aud="bsupervisor"`` and rejects user JWTs with 401/403.
4. ``verify_service_jwt`` from bsvibe-authz happy-path / unhappy-path works
   end-to-end for the BSupervisor receiver.

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


# ---------------------------------------------------------------------------
# require_permission — denied path returns 403
# ---------------------------------------------------------------------------


class TestRequirePermissionDeny:
    """When OpenFGA denies the user, the endpoint MUST return 403.

    Wires up an authenticated *user* request to ``GET /api/rules`` and uses
    ``fake_fga_deny`` to force a deny decision.
    """

    async def test_get_rules_denied_returns_403(self, db_session, authz_settings, fake_fga_deny) -> None:
        async def _override_get_session():
            yield db_session

        app.dependency_overrides[get_session] = _override_get_session
        app.dependency_overrides[get_settings_dep] = lambda: authz_settings
        app.dependency_overrides[get_openfga_client] = lambda: fake_fga_deny
        from bsvibe_authz.cache import PermissionCache

        cache = PermissionCache(ttl_s=0)
        app.dependency_overrides[get_permission_cache] = lambda: cache
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                token = _make_user_jwt()
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 403
                # OpenFGA was actually consulted (defense-in-depth check).
                assert len(fake_fga_deny.checks) == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# require_permission — happy path
# ---------------------------------------------------------------------------


class TestRequirePermissionAllow:
    async def test_get_rules_allowed(
        self,
        db_session,
        authz_settings,
        fake_fga,
    ) -> None:
        async def _override_get_session():
            yield db_session

        app.dependency_overrides[get_session] = _override_get_session
        app.dependency_overrides[get_settings_dep] = lambda: authz_settings
        app.dependency_overrides[get_openfga_client] = lambda: fake_fga
        from bsvibe_authz.cache import PermissionCache

        cache = PermissionCache(ttl_s=0)
        app.dependency_overrides[get_permission_cache] = lambda: cache
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                token = _make_user_jwt()
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                # OpenFGA was consulted exactly once for the rules.read check.
                assert any(call[1] == "read" for call in fake_fga.checks)
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Route → permission matrix snapshot
# ---------------------------------------------------------------------------


class TestRoutePermissionMatrix:
    """Each protected route MUST resolve to a known bsupervisor permission.

    The matrix below is the single source of truth for P0.5 BSupervisor
    (Phase 0 decision #7). When a route is added, this table must be
    updated *and* the route decorator must reference the same identifier.
    """

    EXPECTED: dict[tuple[str, str], str | None] = {
        # path, method → permission OR None for service-only / health
        ("GET", "/api/events"): "bsupervisor.events.read",
        ("POST", "/api/events"): None,  # service-only — no require_permission
        ("POST", "/api/events/{event_id}/feedback"): "bsupervisor.events.write",
        ("GET", "/api/incidents"): "bsupervisor.incidents.read",
        ("GET", "/api/incidents/{incident_id}"): "bsupervisor.incidents.read",
        ("POST", "/api/incidents/{incident_id}/resolve"): "bsupervisor.incidents.write",
        ("GET", "/api/anomalies"): "bsupervisor.anomalies.read",
        ("GET", "/api/costs"): "bsupervisor.costs.read",
        ("POST", "/api/costs"): None,  # service-only — ingestion
        ("GET", "/api/reports/daily"): "bsupervisor.reports.read",
        ("GET", "/api/rules"): "bsupervisor.rules.read",
        ("POST", "/api/rules"): "bsupervisor.rules.write",
        ("PUT", "/api/rules/{rule_id}"): "bsupervisor.rules.write",
        ("DELETE", "/api/rules/{rule_id}"): "bsupervisor.rules.write",
        ("GET", "/api/rule-packs"): "bsupervisor.rules.read",
        ("GET", "/api/rule-packs/{pack_id}"): "bsupervisor.rules.read",
        ("POST", "/api/rule-packs/{pack_id}/install"): "bsupervisor.rules.write",
        ("GET", "/api/settings"): "bsupervisor.config.read",
        ("PUT", "/api/settings"): "bsupervisor.config.write",
        ("GET", "/api/status"): "bsupervisor.status.read",
    }

    def test_matrix_keys_cover_every_protected_route(self) -> None:
        """Every API route in the FastAPI app must appear in EXPECTED."""
        from fastapi.routing import APIRoute

        actual: set[tuple[str, str]] = set()
        for route in app.router.routes:
            if not isinstance(route, APIRoute):
                continue
            if route.path.startswith("/api/health"):
                continue
            if route.path == "/openapi.json":
                continue
            for method in route.methods:
                if method == "HEAD":
                    continue
                actual.add((method, route.path))
        missing = actual - set(self.EXPECTED.keys())
        unexpected = set(self.EXPECTED.keys()) - actual
        assert not missing, f"routes missing from matrix: {missing}"
        assert not unexpected, f"matrix has stale entries: {unexpected}"
