"""Tests for authentication integration."""

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.main import app
from bsupervisor.models.database import get_session


async def test_unauthenticated_request_rejected(db_engine, db_session: AsyncSession) -> None:
    """Endpoints should reject requests without valid auth."""

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    # Do NOT override get_current_user — let it run for real
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/status")
        assert resp.status_code == 401 or resp.status_code == 403

    app.dependency_overrides.clear()


async def test_health_check_no_auth_required(db_engine, db_session: AsyncSession) -> None:
    """Health check should work without authentication."""

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    app.dependency_overrides.clear()


async def test_authenticated_request_succeeds(client) -> None:
    """Endpoints should succeed with valid auth (mocked in conftest)."""
    resp = await client.get("/api/status")
    assert resp.status_code == 200


async def test_all_endpoints_require_auth(db_engine, db_session: AsyncSession) -> None:
    """All API endpoints except health should require auth."""

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        endpoints = [
            ("GET", "/api/rules"),
            ("GET", "/api/status"),
            ("POST", "/api/events"),
            ("POST", "/api/costs"),
        ]
        for method, path in endpoints:
            resp = await ac.request(method, path)
            assert resp.status_code in (401, 403, 422), f"{method} {path} returned {resp.status_code}"

    app.dependency_overrides.clear()
