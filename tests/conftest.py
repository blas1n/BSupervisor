"""Shared test fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

# Provide required bsvibe-authz env vars *before* any module imports
# `bsvibe_authz` so its `Settings` cache initialises cleanly. Tests that
# need to flex these values can override via dependency injection.
os.environ.setdefault("BSVIBE_AUTH_URL", "https://auth.bsvibe.dev")
os.environ.setdefault("OPENFGA_API_URL", "http://openfga.test:8080")
os.environ.setdefault("OPENFGA_STORE_ID", "store-test")
os.environ.setdefault("OPENFGA_AUTH_MODEL_ID", "model-test")
os.environ.setdefault("SERVICE_TOKEN_SIGNING_SECRET", "test-service-signing-secret-do-not-use")
os.environ.setdefault("USER_JWT_SECRET", "test-user-jwt-secret-do-not-use")
os.environ.setdefault("USER_JWT_ALGORITHM", "HS256")
os.environ.setdefault("USER_JWT_AUDIENCE", "bsvibe")
os.environ.setdefault("USER_JWT_ISSUER", "https://auth.bsvibe.dev")

import pytest  # noqa: E402
from bsvibe_authz import User  # noqa: E402
from bsvibe_authz.deps import (  # noqa: E402
    get_current_user,
    get_openfga_client,
    reset_singletons,
)
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import bsupervisor.core.rule_engine as rule_engine_mod  # noqa: E402
from bsupervisor.api.deps import bsupervisor_service_auth  # noqa: E402
from bsupervisor.main import app  # noqa: E402
from bsupervisor.models import Base  # noqa: E402
from bsupervisor.models.database import get_session  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_rules_cache():
    """Clear the DB rules cache before each test to avoid cross-test leakage."""
    rule_engine_mod._rules_cache = None
    rule_engine_mod._rules_cache_ts = 0.0
    reset_singletons()
    yield
    rule_engine_mod._rules_cache = None
    rule_engine_mod._rules_cache_ts = 0.0
    reset_singletons()


@pytest.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


# Test user identity used by the default ``client`` fixture. Tests that
# need a different principal can override ``get_current_user`` directly
# in their own scope.
#
# Phase 2a: carries ``app_metadata.role = "owner"`` so the default client
# also passes ``require_admin()`` on mutation / admin-config routes. The
# allow-all OpenFGA stub below covers ``require_permission`` routes.
_fake_user = User(
    id="test-user-id",
    email="test@example.com",
    active_tenant_id="tenant-test",
    scope=["bsupervisor:*"],
    app_metadata={"role": "owner"},
)


class _AllowAllFGA:
    """Test stub: every OpenFGA check returns True."""

    async def check(self, user: str, relation: str, object_: str) -> bool:
        return True

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []


@pytest.fixture
async def client(db_session) -> AsyncIterator[AsyncClient]:
    """Authenticated, authorized HTTP client.

    Overrides ``get_current_user`` and the OpenFGA client so the existing
    Sprint 0–4 test suite continues to pass after the bsvibe-authz cutover.
    POST /api/events / POST /api/costs are now service-only — those tests
    additionally override ``bsupervisor_service_auth``.
    """

    async def _override_get_session():
        yield db_session

    async def _override_get_current_user() -> User:
        return _fake_user

    async def _override_service_auth():
        # Mimic a verified service token from BSGateway bound to the test tenant.
        from bsvibe_authz import ServiceTokenPayload

        return ServiceTokenPayload(
            iss="https://auth.bsvibe.dev",
            sub="service:bsgateway",
            aud="bsupervisor",
            scope="bsupervisor:events",
            iat=0,
            exp=2_000_000_000,
            token_type="service",
            tenant_id="tenant-test",
        )

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_openfga_client] = lambda: _AllowAllFGA()
    app.dependency_overrides[bsupervisor_service_auth] = _override_service_auth
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
