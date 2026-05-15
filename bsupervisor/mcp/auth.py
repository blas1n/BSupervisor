"""MCP-transport auth dispatcher.

Thin delegate over :func:`bsvibe_authz.deps.get_current_user`. The
library helper performs the full JWT verify → PAT-JWT
introspection-fallback dispatch (the legacy ``bsv_sk_*`` opaque-token
branch was retired in bsvibe-authz 1.3.0), so the only thing this
module owns is the :class:`ToolContext` shape both transports (HTTP
``/mcp`` and stdio) return + translating ``HTTPException`` to
:class:`MCPAuthError`.

Token-redaction (never log raw tokens) is enforced inside bsvibe-authz.
"""

from __future__ import annotations

import structlog
from bsvibe_authz import IntrospectionClient, Settings
from bsvibe_authz.cache import IntrospectionCache
from bsvibe_authz.deps import get_current_user
from fastapi import HTTPException

from bsupervisor.mcp.api import AuditEmit, ToolContext

logger = structlog.get_logger(__name__)


class MCPAuthError(Exception):
    """Authentication failed for an MCP transport request."""


async def _noop_audit(event: str, payload: dict) -> None:
    """Default audit-emit when the transport does not provide one — no-op."""
    return None


async def resolve_tool_context(
    *,
    authorization: str | None,
    settings: Settings,
    introspection_client: IntrospectionClient | None,
    introspection_cache: IntrospectionCache,
    audit_emit: AuditEmit | None = None,
) -> ToolContext:
    """Resolve ``Authorization`` header → :class:`ToolContext`.

    Delegates to :func:`bsvibe_authz.deps.get_current_user` for the JWT
    verify + PAT-JWT introspection fallback dispatch (the ``bsv_sk_*``
    opaque branch was retired in bsvibe-authz 1.3.0). Library-level
    changes propagate automatically — no mirror fixes here.
    """
    try:
        user = await get_current_user(
            authorization=authorization,
            settings=settings,
            introspection_client=introspection_client,
            introspection_cache=introspection_cache,
        )
    except HTTPException as exc:
        raise MCPAuthError(str(exc.detail)) from exc

    return ToolContext(user=user, audit_emit=audit_emit or _noop_audit)


__all__ = [
    "MCPAuthError",
    "resolve_tool_context",
]
