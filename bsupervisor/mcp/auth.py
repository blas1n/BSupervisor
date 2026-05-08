"""MCP-transport auth dispatcher — 3-way bootstrap → opaque → JWT.

Mirrors :func:`bsvibe_authz.deps.get_current_user` but for MCP transports
(HTTP ``/mcp`` and stdio). Returning a :class:`ToolContext` directly means
both transports share the same auth resolution path with zero duplication.

Token-redaction: failures log only the prefix discriminant, never the raw
token. The 3-way dispatch is identical to REST, so an MCP caller cannot
escalate beyond the scopes their token already grants.
"""

from __future__ import annotations

import structlog
from bsvibe_authz import (
    AuthError,
    IntrospectionClient,
    Settings,
    parse_user_token,
    verify_bootstrap_token,
    verify_opaque_token,
    verify_user_jwt,
)
from bsvibe_authz.cache import IntrospectionCache
from fastapi.security.utils import get_authorization_scheme_param

from bsupervisor.mcp.api import AuditEmit, ToolContext

logger = structlog.get_logger(__name__)

BOOTSTRAP_TOKEN_PREFIX = "bsv_admin_"
OPAQUE_TOKEN_PREFIX = "bsv_sk_"


class MCPAuthError(Exception):
    """Authentication failed for an MCP transport request."""


async def _noop_audit(event: str, payload: dict) -> None:
    """Default audit-emit when the transport does not provide one — no-op."""

    return None


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise MCPAuthError("missing Authorization header")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer" or not token:
        raise MCPAuthError("invalid Authorization scheme")
    return token


async def resolve_tool_context(
    *,
    authorization: str | None,
    settings: Settings,
    introspection_client: IntrospectionClient | None,
    introspection_cache: IntrospectionCache,
    audit_emit: AuditEmit | None = None,
) -> ToolContext:
    """Resolve ``Authorization`` header → :class:`ToolContext`.

    Dispatch order matches :func:`bsvibe_authz.deps.get_current_user`:

    1. ``bsv_admin_*`` bootstrap → :func:`verify_bootstrap_token`
    2. ``bsv_sk_*`` opaque → introspection (when client is configured)
    3. otherwise → user JWT → :func:`parse_user_token`

    Raises :class:`MCPAuthError` for any failure; transports translate to
    transport-specific error codes (HTTP 401, MCP error response).
    """

    token = _extract_bearer(authorization)

    try:
        if token.startswith(BOOTSTRAP_TOKEN_PREFIX):
            user = verify_bootstrap_token(token, settings)
        elif token.startswith(OPAQUE_TOKEN_PREFIX) and introspection_client is not None:
            user = await verify_opaque_token(token, introspection_client, introspection_cache)
        else:
            payload = verify_user_jwt(token, settings)
            user = parse_user_token(payload)
    except AuthError as exc:
        # Never log the raw token — only the prefix discriminant.
        prefix = token[: len(BOOTSTRAP_TOKEN_PREFIX)] if len(token) >= len(BOOTSTRAP_TOKEN_PREFIX) else "?"
        logger.info("mcp_auth_failed", token_prefix=prefix, reason=str(exc))
        raise MCPAuthError(str(exc)) from exc

    return ToolContext(
        user=user,
        audit_emit=audit_emit or _noop_audit,
    )


__all__ = [
    "BOOTSTRAP_TOKEN_PREFIX",
    "MCPAuthError",
    "OPAQUE_TOKEN_PREFIX",
    "resolve_tool_context",
]
