"""bsvibe-authz 3-way dispatch + require_scope migration tests.

Phase 5b — replaces the legacy ``require_permission`` (OpenFGA tuple) gate
with scope-based authorization. ``get_current_user`` from bsvibe-authz is a
3-way dispatch:

    1. ``bsv_admin_<...>`` bootstrap token → User(scope=["*"])
    2. ``bsv_sk_<...>`` opaque token       → User(scope=<introspection.scope>)
    3. anything else                       → User(scope=[]) via JWT verification
    4. invalid / missing Authorization     → 401

Each branch is exercised against ``GET /api/rules`` (admin: scope-protected)
so a regression in the dispatch layer surfaces here.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import jwt
import pytest
from bsvibe_authz import (
    IntrospectionResponse,
    Settings as AuthzSettings,
)
from bsvibe_authz.cache import IntrospectionCache, PermissionCache
from bsvibe_authz.deps import (
    get_introspection_cache,
    get_introspection_client,
    get_openfga_client,
    get_permission_cache,
    get_settings_dep,
)
from httpx import ASGITransport, AsyncClient

from bsupervisor.main import app
from bsupervisor.models.database import get_session

ISSUER = "https://auth.bsvibe.dev"
USER_JWT_SECRET = "test-user-jwt-secret-do-not-use-in-prod"
SERVICE_SIGNING_SECRET = "test-service-signing-secret-do-not-use-in-prod"
BOOTSTRAP_TOKEN = "bsv_admin_dispatch_test_value"  # noqa: S105 - fixture
BOOTSTRAP_HASH = hashlib.sha256(BOOTSTRAP_TOKEN.encode()).hexdigest()
OPAQUE_TOKEN = "bsv_sk_dispatch_test_value"  # noqa: S105 - fixture


def _make_authz_settings(*, with_bootstrap: bool = False, with_introspection: bool = False) -> AuthzSettings:
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
        bootstrap_token_hash=BOOTSTRAP_HASH if with_bootstrap else "",
        introspection_url="https://auth.bsvibe.dev/api/tokens/introspect" if with_introspection else "",
        introspection_client_id="bsupervisor",
        introspection_client_secret="dispatch-test-secret",
    )


def _make_user_jwt(*, sub: str = "user-1", tenant: str = "tenant-alpha") -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": sub,
        "active_tenant_id": tenant,
        "iat": now,
        "exp": now + 600,
        "aud": "bsvibe",
    }
    return jwt.encode(payload, USER_JWT_SECRET, algorithm="HS256")


class _StubIntrospectionClient:
    """In-memory introspection stub returning a configurable response."""

    def __init__(self, response: IntrospectionResponse) -> None:
        self._response = response
        self.calls: list[str] = []

    async def introspect(self, token: str) -> IntrospectionResponse:
        self.calls.append(token)
        return self._response


class _AllowAllFGA:
    async def check(self, user: str, relation: str, object_: str) -> bool:
        return True

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []


def _wire_app(
    *,
    db_session,
    settings: AuthzSettings,
    introspection_client: _StubIntrospectionClient | None = None,
) -> None:
    """Wire the app dependency overrides for a dispatch test.

    We deliberately do NOT override ``get_current_user`` so the real
    bsvibe-authz dispatch runs end-to-end.
    """

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_openfga_client] = lambda: _AllowAllFGA()
    app.dependency_overrides[get_permission_cache] = lambda: PermissionCache(ttl_s=0)
    app.dependency_overrides[get_introspection_cache] = lambda: IntrospectionCache(ttl_s=0)
    if introspection_client is not None:
        app.dependency_overrides[get_introspection_client] = lambda: introspection_client
    else:
        app.dependency_overrides[get_introspection_client] = lambda: None


# ---------------------------------------------------------------------------
# Branch 1: bootstrap token (bsv_admin_*) → scope=["*"] → 200
# ---------------------------------------------------------------------------
class TestBootstrapDispatch:
    async def test_valid_bootstrap_token_grants_admin_scope(self, db_session) -> None:
        _wire_app(db_session=db_session, settings=_make_authz_settings(with_bootstrap=True))
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {BOOTSTRAP_TOKEN}"},
                )
                assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

    async def test_bootstrap_token_with_wrong_hash_rejected(self, db_session) -> None:
        # Settings configured with the *correct* hash, but client sends a
        # different bsv_admin_ token — must 401, not silently accept.
        _wire_app(db_session=db_session, settings=_make_authz_settings(with_bootstrap=True))
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": "Bearer bsv_admin_some_other_token"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Branch 2: opaque token (bsv_sk_*) → scope from introspection → 200/403
# ---------------------------------------------------------------------------
class TestOpaqueDispatch:
    async def test_opaque_token_with_supervisor_scope_grants_access(self, db_session) -> None:
        stub = _StubIntrospectionClient(
            IntrospectionResponse(
                active=True,
                sub="api-key-1",
                tenant="tenant-alpha",
                scope=["supervisor:agents:read"],
            )
        )
        _wire_app(
            db_session=db_session,
            settings=_make_authz_settings(with_introspection=True),
            introspection_client=stub,
        )
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {OPAQUE_TOKEN}"},
                )
                assert resp.status_code == 200, resp.text
                assert stub.calls == [OPAQUE_TOKEN]
        finally:
            app.dependency_overrides.clear()

    async def test_opaque_token_missing_scope_returns_403(self, db_session) -> None:
        stub = _StubIntrospectionClient(
            IntrospectionResponse(
                active=True,
                sub="api-key-1",
                tenant="tenant-alpha",
                scope=["supervisor:incidents:read"],  # not agents:read
            )
        )
        _wire_app(
            db_session=db_session,
            settings=_make_authz_settings(with_introspection=True),
            introspection_client=stub,
        )
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {OPAQUE_TOKEN}"},
                )
                assert resp.status_code == 403, resp.text
        finally:
            app.dependency_overrides.clear()

    async def test_inactive_opaque_token_rejected(self, db_session) -> None:
        stub = _StubIntrospectionClient(IntrospectionResponse(active=False))
        _wire_app(
            db_session=db_session,
            settings=_make_authz_settings(with_introspection=True),
            introspection_client=stub,
        )
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {OPAQUE_TOKEN}"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Branch 3: JWT path → User.scope = [] → require_scope yields 403
# ---------------------------------------------------------------------------
class TestJwtDispatch:
    async def test_valid_jwt_without_scope_denied_by_require_scope(self, db_session) -> None:
        """Phase 5b semantics: scope-less JWTs cannot reach scope-gated admin routes."""
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {_make_user_jwt()}"},
                )
                # Authentication succeeds; authorization (require_scope) fails.
                assert resp.status_code == 403, resp.text
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Branch 4: invalid / missing Authorization → 401
# ---------------------------------------------------------------------------
class TestInvalidDispatch:
    async def test_missing_authorization_returns_401(self, db_session) -> None:
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/rules")
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    async def test_garbage_jwt_returns_401(self, db_session) -> None:
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": "Bearer not-a-jwt-at-all"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    async def test_bsv_admin_token_rejected_when_path_disabled(self, db_session) -> None:
        # bootstrap_token_hash unset → bsv_admin_ tokens MUST 401 even with
        # the right prefix (defense-in-depth: never accept the prefix alone).
        _wire_app(db_session=db_session, settings=_make_authz_settings(with_bootstrap=False))
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {BOOTSTRAP_TOKEN}"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# require_scope catalog — every protected route MUST gate on a scope from
# the Phase 5b supervisor catalog. Pinning prevents future refactors from
# silently downgrading a gate (mirrors BSGateway PR #43 approach).
# ---------------------------------------------------------------------------
SCOPE_CATALOG: dict[tuple[str, str], str | None] = {
    ("GET", "/api/events"): "supervisor:audit:read",
    ("POST", "/api/events"): None,  # service-only — service JWT, not scope
    ("POST", "/api/events/{event_id}/feedback"): "supervisor:audit:read",
    ("GET", "/api/incidents"): "supervisor:incidents:read",
    ("GET", "/api/incidents/{incident_id}"): "supervisor:incidents:read",
    ("POST", "/api/incidents/{incident_id}/ack"): "supervisor:incidents:write",
    ("POST", "/api/incidents/{incident_id}/resolve"): "supervisor:incidents:write",
    ("GET", "/api/anomalies"): "supervisor:agents:read",
    ("GET", "/api/costs"): "supervisor:audit:read",
    ("POST", "/api/costs"): None,  # service-only
    ("GET", "/api/reports/daily"): "supervisor:audit:read",
    ("GET", "/api/rules"): "supervisor:agents:read",
    ("POST", "/api/rules"): "supervisor:agents:write",
    ("PUT", "/api/rules/{rule_id}"): "supervisor:agents:write",
    ("DELETE", "/api/rules/{rule_id}"): "supervisor:agents:write",
    ("GET", "/api/rule-packs"): "supervisor:agents:read",
    ("GET", "/api/rule-packs/{pack_id}"): "supervisor:agents:read",
    ("POST", "/api/rule-packs/{pack_id}/install"): "supervisor:agents:write",
    ("GET", "/api/settings"): "supervisor:*",
    ("PUT", "/api/settings"): "supervisor:*",
    ("GET", "/api/status"): "supervisor:audit:read",
}


@pytest.mark.parametrize(
    ("method", "path", "expected_scope"),
    [(m, p, s) for (m, p), s in SCOPE_CATALOG.items() if s is not None],
)
def test_route_gates_on_expected_scope(method: str, path: str, expected_scope: str) -> None:
    """Each protected route's deps stack must reference the catalog scope.

    We tag each ``require_scope`` dep at construction (see
    ``bsupervisor.api.deps.require_scope``) so the test can inspect the
    closure metadata without relying on closure internals.
    """
    from fastapi.routing import APIRoute

    matched = None
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != path:
            continue
        if method not in route.methods:
            continue
        matched = route
        break
    assert matched is not None, f"route {method} {path} not found"

    scopes = [getattr(d.call, "_bsvibe_scope", None) for d in matched.dependant.dependencies if d.call is not None]
    assert expected_scope in scopes, f"{method} {path} did not gate on {expected_scope!r}; saw {scopes}"


def test_catalog_covers_every_protected_route() -> None:
    from fastapi.routing import APIRoute

    actual: set[tuple[str, str]] = set()
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.startswith("/api/health"):
            continue
        if route.path == "/openapi.json":
            continue
        # ``/mcp/health`` is the MCP-surface liveness probe — load
        # balancers hit it without auth, same contract as ``/api/health``.
        if route.path == "/mcp/health":
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            actual.add((method, route.path))
    missing = actual - set(SCOPE_CATALOG.keys())
    unexpected = set(SCOPE_CATALOG.keys()) - actual
    assert not missing, f"routes missing from scope catalog: {missing}"
    assert not unexpected, f"scope catalog has stale entries: {unexpected}"
