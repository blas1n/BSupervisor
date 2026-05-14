"""bsvibe-authz dispatch + require_permission/require_admin matrix tests.

Phase 2a — user-facing read/list routes are gated by ``require_permission``
(permissive no-op when ``openfga_api_url`` is empty) and mutation /
admin-config routes by ``require_admin()`` (real JWT-role check).
``get_current_user`` from bsvibe-authz is a 2-way dispatch:

    1. ``bsv_sk_<...>`` opaque token   → User(scope=<introspection.scope>)
    2. anything else                   → User(...) via JWT verification
    3. invalid / missing Authorization → 401

Dispatch branches are exercised against ``GET /api/rules``
(``require_permission("bsupervisor.agents.read")``) so a regression in the
dispatch layer surfaces here. ``require_admin`` enforcement is exercised
against ``POST /api/rules``.
"""

from __future__ import annotations

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
OPAQUE_TOKEN = "bsv_sk_dispatch_test_value"  # noqa: S105 - fixture


def _make_authz_settings(*, with_introspection: bool = False) -> AuthzSettings:
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
        introspection_url="https://auth.bsvibe.dev/oauth/introspect" if with_introspection else "",
        introspection_client_id="bsupervisor",
        introspection_client_secret="dispatch-test-secret",
    )


def _make_user_jwt(
    *,
    sub: str = "user-1",
    tenant: str = "tenant-alpha",
    role: str | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": sub,
        "active_tenant_id": tenant,
        "iat": now,
        "exp": now + 600,
        "aud": "bsvibe",
    }
    if role is not None:
        payload["app_metadata"] = {"role": role}
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


class _DenyAllFGA:
    async def check(self, user: str, relation: str, object_: str) -> bool:
        return False

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []


def _wire_app(
    *,
    db_session,
    settings: AuthzSettings,
    introspection_client: _StubIntrospectionClient | None = None,
    fga: Any | None = None,
) -> None:
    """Wire the app dependency overrides for a dispatch test.

    We deliberately do NOT override ``get_current_user`` so the real
    bsvibe-authz dispatch runs end-to-end. ``fga`` defaults to an
    allow-all OpenFGA stub; pass ``_DenyAllFGA()`` to exercise a deny.
    """

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.dependency_overrides[get_openfga_client] = lambda: fga or _AllowAllFGA()
    app.dependency_overrides[get_permission_cache] = lambda: PermissionCache(ttl_s=0)
    app.dependency_overrides[get_introspection_cache] = lambda: IntrospectionCache(ttl_s=0)
    if introspection_client is not None:
        app.dependency_overrides[get_introspection_client] = lambda: introspection_client
    else:
        app.dependency_overrides[get_introspection_client] = lambda: None


# ---------------------------------------------------------------------------
# Branch 2: opaque token (bsv_sk_*) → introspection → require_permission
#           authorizes via OpenFGA check (allow → 200, deny → 403)
# ---------------------------------------------------------------------------
class TestOpaqueDispatch:
    async def test_opaque_token_allowed_by_openfga_grants_access(self, db_session) -> None:
        stub = _StubIntrospectionClient(
            IntrospectionResponse(
                active=True,
                sub="api-key-1",
                tenant="tenant-alpha",
                scope=["bsupervisor:agents:read"],
            )
        )
        _wire_app(
            db_session=db_session,
            settings=_make_authz_settings(with_introspection=True),
            introspection_client=stub,
            fga=_AllowAllFGA(),
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

    async def test_opaque_token_denied_by_openfga_returns_403(self, db_session) -> None:
        """When OpenFGA is deployed and the tuple check denies, require_permission 403s."""
        stub = _StubIntrospectionClient(
            IntrospectionResponse(
                active=True,
                sub="api-key-1",
                tenant="tenant-alpha",
                scope=["bsupervisor:agents:read"],
            )
        )
        _wire_app(
            db_session=db_session,
            settings=_make_authz_settings(with_introspection=True),
            introspection_client=stub,
            fga=_DenyAllFGA(),
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
# Branch 3: JWT path → require_permission / require_admin authorization
# ---------------------------------------------------------------------------
class TestJwtDispatch:
    async def test_jwt_reaches_require_permission_route_when_openfga_allows(self, db_session) -> None:
        """Phase 2a: a scope-less user JWT reaches a require_permission route.

        OpenFGA deployed + tuple allows → 200. (The frontend's wrapped
        session JWT carries ``scope=[]``; this is the regression the
        require_scope → require_permission swap fixes.)
        """
        _wire_app(db_session=db_session, settings=_make_authz_settings(), fga=_AllowAllFGA())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {_make_user_jwt()}"},
                )
                assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

    async def test_jwt_permissive_mode_passes_without_openfga(self, db_session) -> None:
        """Permissive mode: openfga_api_url empty → require_permission is a no-op pass.

        This is the prod-today configuration on product backends.
        """
        settings = _make_authz_settings()
        settings.openfga_api_url = ""
        _wire_app(db_session=db_session, settings=settings)
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {_make_user_jwt()}"},
                )
                assert resp.status_code == 200, resp.text
        finally:
            app.dependency_overrides.clear()

    async def test_jwt_without_admin_role_denied_on_require_admin_route(self, db_session) -> None:
        """Phase 2a: require_admin is a real enforced check — non-admin JWT 403s."""
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {_make_user_jwt()}"},
                    json={"name": "r1", "type": "pattern", "pattern": "x", "action": "warn"},
                )
                assert resp.status_code == 403, resp.text
        finally:
            app.dependency_overrides.clear()

    async def test_jwt_with_admin_role_reaches_require_admin_route(self, db_session) -> None:
        """An ``admin``-role JWT passes require_admin (200/201 or a non-403 handler code)."""
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/rules",
                    headers={"Authorization": f"Bearer {_make_user_jwt(role='admin')}"},
                    json={"name": "r-admin", "type": "pattern", "pattern": "x", "action": "warn"},
                )
                # require_admin passed — the handler ran (created or 409 dup, never 403).
                assert resp.status_code != 403, resp.text
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

    async def test_bsv_admin_prefix_rejected(self, db_session) -> None:
        # The legacy ``bsv_admin_*`` prefix is gone — any such token is now
        # an unrecognised garbage bearer and must be rejected with 401.
        _wire_app(db_session=db_session, settings=_make_authz_settings())
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/rules",
                    headers={"Authorization": "Bearer bsv_admin_anything"},
                )
                assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth-matrix catalog — Phase 2a. Every protected route MUST gate on the
# expected primitive:
#   - user-facing read/list  → ``require_permission("bsupervisor.<res>.<act>")``
#   - mutation / admin-config → ``require_admin()``
#   - service-only ingestion  → service JWT (no user gate; entry is None)
# Pinning prevents future refactors from silently downgrading a gate.
# ``require_permission`` is permissive (no-op) in prod today; ``require_admin``
# is a real enforced JWT-role check.
# ---------------------------------------------------------------------------
# value is ("permission", "<perm>") | ("admin", None) | None (service-only)
AUTH_CATALOG: dict[tuple[str, str], tuple[str, str | None] | None] = {
    ("GET", "/api/events"): ("permission", "bsupervisor.audit.read"),
    ("POST", "/api/events"): None,  # service-only — service JWT
    ("POST", "/api/events/{event_id}/feedback"): ("permission", "bsupervisor.audit.read"),
    ("GET", "/api/incidents"): ("permission", "bsupervisor.incidents.read"),
    ("GET", "/api/incidents/{incident_id}"): ("permission", "bsupervisor.incidents.read"),
    ("POST", "/api/incidents/{incident_id}/ack"): ("admin", None),
    ("POST", "/api/incidents/{incident_id}/resolve"): ("admin", None),
    ("GET", "/api/anomalies"): ("permission", "bsupervisor.agents.read"),
    ("GET", "/api/costs"): ("permission", "bsupervisor.audit.read"),
    ("POST", "/api/costs"): None,  # service-only
    ("GET", "/api/reports/daily"): ("permission", "bsupervisor.audit.read"),
    ("GET", "/api/rules"): ("permission", "bsupervisor.agents.read"),
    ("POST", "/api/rules"): ("admin", None),
    ("PUT", "/api/rules/{rule_id}"): ("admin", None),
    ("DELETE", "/api/rules/{rule_id}"): ("admin", None),
    ("GET", "/api/rule-packs"): ("permission", "bsupervisor.agents.read"),
    ("GET", "/api/rule-packs/{pack_id}"): ("permission", "bsupervisor.agents.read"),
    ("POST", "/api/rule-packs/{pack_id}/install"): ("admin", None),
    ("GET", "/api/settings"): ("admin", None),
    ("PUT", "/api/settings"): ("admin", None),
    ("GET", "/api/status"): ("permission", "bsupervisor.audit.read"),
}


def _find_route(method: str, path: str):
    from fastapi.routing import APIRoute

    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == path and method in route.methods:
            return route
    return None


def _no_legacy_scope(route) -> list[str | None]:
    return [getattr(d.call, "_bsvibe_scope", None) for d in route.dependant.dependencies if d.call is not None]


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [(m, p, v[1]) for (m, p), v in AUTH_CATALOG.items() if v is not None and v[0] == "permission"],
)
def test_route_gates_on_expected_permission(method: str, path: str, permission: str) -> None:
    """Each user-facing read route's deps stack references the catalog permission.

    We tag each ``require_permission`` dep at construction (see
    ``bsupervisor.api.deps.require_permission``) so the test can inspect the
    closure metadata without relying on closure internals.
    """
    matched = _find_route(method, path)
    assert matched is not None, f"route {method} {path} not found"

    perms = [getattr(d.call, "_bsvibe_permission", None) for d in matched.dependant.dependencies if d.call is not None]
    assert permission in perms, f"{method} {path} did not gate on require_permission({permission!r}); saw {perms}"
    scopes = _no_legacy_scope(matched)
    assert all(s is None for s in scopes), f"{method} {path} still carries a require_scope gate: {scopes}"


@pytest.mark.parametrize(
    ("method", "path"),
    [(m, p) for (m, p), v in AUTH_CATALOG.items() if v is not None and v[0] == "admin"],
)
def test_route_gates_on_require_admin(method: str, path: str) -> None:
    """Each mutation / admin-config route's deps stack references ``require_admin``."""
    matched = _find_route(method, path)
    assert matched is not None, f"route {method} {path} not found"

    admins = [getattr(d.call, "_bsvibe_admin", None) for d in matched.dependant.dependencies if d.call is not None]
    assert any(admins), f"{method} {path} did not gate on require_admin()"
    scopes = _no_legacy_scope(matched)
    assert all(s is None for s in scopes), f"{method} {path} still carries a require_scope gate: {scopes}"


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
        # RFC 9728 OAuth protected-resource metadata — unauthenticated
        # by design so MCP clients can discover the authorization
        # server before they have any token.
        if route.path == "/.well-known/oauth-protected-resource":
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            actual.add((method, route.path))
    missing = actual - set(AUTH_CATALOG.keys())
    unexpected = set(AUTH_CATALOG.keys()) - actual
    assert not missing, f"routes missing from auth catalog: {missing}"
    assert not unexpected, f"auth catalog has stale entries: {unexpected}"
