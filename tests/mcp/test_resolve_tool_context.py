"""Tests for resolve_tool_context — MCP-transport auth dispatch.

Mirrors ``bsvibe_authz.deps.get_current_user`` (JWT → PAT-JWT
introspection fallback) but for MCP transports (HTTP /mcp + stdio).
Used by both transports so the auth path is identical between them.

The legacy ``bsv_sk_*`` opaque-token branch was removed in Tier 2 of
the 2026-05 auth cleanup (bsvibe-authz 1.3.0). Introspection now serves
only the PAT-JWT fallback path.

Audit emission is wired by the caller via ``audit_emit_factory`` so the
registry stays decoupled from any particular outbox session.
"""

from __future__ import annotations

import time

import jwt
import pytest
from bsvibe_authz import IntrospectionResponse, Settings, User
from bsvibe_authz.cache import IntrospectionCache

from bsupervisor.mcp.auth import MCPAuthError, resolve_tool_context


def _settings(**overrides) -> Settings:
    base = {
        "bsvibe_auth_url": "https://auth.bsvibe.dev",
        "openfga_api_url": "http://openfga.test:8080",
        "openfga_store_id": "store-test",
        "openfga_auth_model_id": "model-test",
        "service_token_signing_secret": "test-service-signing-secret-do-not-use",
        "user_jwt_secret": "test-user-jwt-secret-do-not-use",
        "user_jwt_algorithm": "HS256",
        "user_jwt_audience": "bsvibe",
        "user_jwt_issuer": "https://auth.bsvibe.dev",
    }
    base.update(overrides)
    return Settings(**base)


class _StubIntrospectionClient:
    """Returns a pre-canned introspection response."""

    def __init__(self, response: IntrospectionResponse) -> None:
        self._response = response
        self.calls: list[str] = []

    async def introspect(self, token: str) -> IntrospectionResponse:
        self.calls.append(token)
        return self._response


@pytest.mark.asyncio
async def test_missing_authorization_raises() -> None:
    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization=None,
            settings=_settings(),
            introspection_client=None,
            introspection_cache=IntrospectionCache(ttl_s=30),
        )


@pytest.mark.asyncio
async def test_non_bearer_scheme_raises() -> None:
    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization="Basic abc",
            settings=_settings(),
            introspection_client=None,
            introspection_cache=IntrospectionCache(ttl_s=30),
        )


@pytest.mark.asyncio
async def test_bsv_sk_opaque_token_no_longer_dispatches_to_introspection() -> None:
    """Regression: the legacy ``bsv_sk_*`` opaque-token branch was removed
    in bsvibe-authz 1.3.0. Such tokens are now treated as non-JWT garbage
    bearers — introspection is never called and the request 401s."""
    client = _StubIntrospectionClient(
        IntrospectionResponse(
            active=True,
            sub="service:bsgateway",
            tenant="tenant-test",
            scope=["bsupervisor:audit:read"],
        )
    )

    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization="Bearer bsv_sk_xyz",
            settings=_settings(),
            introspection_client=client,  # type: ignore[arg-type]
            introspection_cache=IntrospectionCache(ttl_s=30),
        )
    assert client.calls == []


@pytest.mark.asyncio
async def test_user_jwt_returns_user() -> None:
    settings = _settings()
    payload = {
        "sub": "user-123",
        "email": "u@example.com",
        "active_tenant_id": "tenant-test",
        "aud": settings.user_jwt_audience,
        "iss": settings.user_jwt_issuer,
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
    }
    token = jwt.encode(payload, settings.user_jwt_secret, algorithm="HS256")

    ctx = await resolve_tool_context(
        authorization=f"Bearer {token}",
        settings=settings,
        introspection_client=None,
        introspection_cache=IntrospectionCache(ttl_s=30),
    )

    assert isinstance(ctx.user, User)
    assert ctx.user.id == "user-123"
    assert ctx.user.email == "u@example.com"


@pytest.mark.asyncio
async def test_invalid_jwt_raises() -> None:
    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization="Bearer not-a-real-jwt",
            settings=_settings(),
            introspection_client=None,
            introspection_cache=IntrospectionCache(ttl_s=30),
        )


@pytest.mark.asyncio
async def test_pat_jwt_falls_back_to_introspection() -> None:
    """Device-grant PATs are JWTs signed with SERVICE_TOKEN_SIGNING_SECRET,
    not USER_JWT_SECRET — verify_user_jwt rejects them. Introspection picks
    them up by jti. Mirrors bsvibe-authz get_current_user."""
    response = IntrospectionResponse(
        active=True,
        sub="user-pat",
        tenant="tenant-test",
        scope=["bsgateway:models:read"],
    )
    client = _StubIntrospectionClient(response)

    bogus_pat = jwt.encode(
        {"sub": "user-pat", "exp": 9_999_999_999, "token_type": "pat"},
        "different-signing-secret",
        algorithm="HS256",
    )

    ctx = await resolve_tool_context(
        authorization=f"Bearer {bogus_pat}",
        settings=_settings(),
        introspection_client=client,  # type: ignore[arg-type]
        introspection_cache=IntrospectionCache(ttl_s=30),
    )

    assert ctx.user.id == "user-pat"
    assert client.calls == [bogus_pat]


@pytest.mark.asyncio
async def test_pat_jwt_inactive_raises() -> None:
    client = _StubIntrospectionClient(IntrospectionResponse(active=False))

    bogus_pat = jwt.encode(
        {"sub": "x", "exp": 9_999_999_999},
        "different-signing-secret",
        algorithm="HS256",
    )

    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization=f"Bearer {bogus_pat}",
            settings=_settings(),
            introspection_client=client,  # type: ignore[arg-type]
            introspection_cache=IntrospectionCache(ttl_s=30),
        )


@pytest.mark.asyncio
async def test_pat_jwt_no_introspection_client_raises() -> None:
    """JWT-shaped token + introspection unconfigured → 401 (no fallback)."""
    bogus_pat = jwt.encode(
        {"sub": "x", "exp": 9_999_999_999},
        "different-signing-secret",
        algorithm="HS256",
    )

    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization=f"Bearer {bogus_pat}",
            settings=_settings(),
            introspection_client=None,
            introspection_cache=IntrospectionCache(ttl_s=30),
        )


@pytest.mark.asyncio
async def test_non_jwt_garbage_does_not_call_introspection() -> None:
    """Random non-JWT strings should not waste an introspection call."""
    client = _StubIntrospectionClient(IntrospectionResponse(active=False))

    with pytest.raises(MCPAuthError):
        await resolve_tool_context(
            authorization="Bearer not-a-jwt",
            settings=_settings(),
            introspection_client=client,  # type: ignore[arg-type]
            introspection_cache=IntrospectionCache(ttl_s=30),
        )
    assert client.calls == []


@pytest.mark.asyncio
async def test_audit_emit_factory_is_attached_to_context() -> None:
    settings = _settings()
    client = _StubIntrospectionClient(
        IntrospectionResponse(
            active=True,
            sub="audit-emit-test",
            tenant="t",
            scope=["bsupervisor:audit:read"],
        ),
    )

    captured: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:
        captured.append((event, payload))

    # JWT-shaped PAT signed with a different secret → verify_user_jwt fails,
    # introspection picks it up via the PAT-JWT fallback (now the only
    # path that reaches introspection since bsvibe-authz 1.3.0).
    pat = jwt.encode(
        {"sub": "audit-emit-test", "exp": 9_999_999_999, "token_type": "pat"},
        "different-signing-secret",
        algorithm="HS256",
    )

    ctx = await resolve_tool_context(
        authorization=f"Bearer {pat}",
        settings=settings,
        introspection_client=client,  # type: ignore[arg-type]
        introspection_cache=IntrospectionCache(ttl_s=30),
        audit_emit=emit,
    )

    await ctx.audit_emit("e", {"k": "v"})
    assert captured == [("e", {"k": "v"})]
