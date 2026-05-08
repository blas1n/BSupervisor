"""HTTP/stdio transports for the BSupervisor MCP surface.

Integration glue that turns the in-memory :class:`ToolRegistry` (admin
tools today, domain tools tomorrow) into a runnable MCP server attached
to the FastAPI app and the ``bsupervisor mcp`` CLI:

* :func:`mcp_lifespan` — an :func:`contextlib.asynccontextmanager` that
  builds the registry, wires the streamable-HTTP session manager, and
  publishes both onto ``app.state``. Composed into the parent FastAPI
  lifespan so the manager's anyio task group lives exactly as long as the
  process serves requests.
* :func:`mcp_streamable_http_asgi` — a tiny ASGI callable mounted at
  ``/mcp`` that captures the incoming ``Authorization`` header into a
  :class:`contextvars.ContextVar` before delegating to the manager. The
  context var is read by the per-call context provider so each tool
  dispatch reflects the caller's auth.
* :func:`run_stdio_server` — launches the same registry over stdin/stdout
  for Claude Desktop / ``bsupervisor mcp serve --transport stdio``. Reads
  the bootstrap token from the environment exactly once.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

import structlog
from bsvibe_authz import IntrospectionClient
from bsvibe_authz import Settings as AuthzSettings
from bsvibe_authz.cache import IntrospectionCache
from bsvibe_authz.deps import get_settings as get_authz_settings
from fastapi import FastAPI
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from bsupervisor.mcp.admin_tools import build_admin_registry
from bsupervisor.mcp.api import ToolContext, ToolPermissionError, ToolRegistry
from bsupervisor.mcp.auth import MCPAuthError, resolve_tool_context
from bsupervisor.mcp.server import build_server

logger = structlog.get_logger(__name__)

# Captured per-request from the inbound Authorization header. The
# streamable-HTTP handler does not expose request scope to the tool
# context_provider, so we pin it on a ContextVar instead. ``None`` means
# unauthenticated — :func:`resolve_tool_context` rejects with MCPAuthError.
_current_authorization: ContextVar[str | None] = ContextVar(
    "_mcp_current_authorization",
    default=None,
)

BOOTSTRAP_TOKEN_ENV = "BSV_BOOTSTRAP_TOKEN"


def _build_introspection_inputs() -> tuple[AuthzSettings, IntrospectionClient | None, IntrospectionCache]:
    """Resolve the cached :class:`AuthzSettings` plus introspection helpers.

    Mirrors the FastAPI dependency wiring so MCP and REST share one config
    surface. The introspection client is ``None`` whenever
    ``introspection_url`` is empty — opaque tokens then fall through and
    fail closed, matching the REST behaviour.
    """

    authz_settings = get_authz_settings()
    introspection_client: IntrospectionClient | None = None
    if authz_settings.introspection_url:
        introspection_client = IntrospectionClient(
            url=authz_settings.introspection_url,
            client_id=authz_settings.introspection_client_id or "",
            client_secret=authz_settings.introspection_client_secret or "",
        )
    introspection_cache = IntrospectionCache(ttl_s=authz_settings.permission_cache_ttl_s)
    return authz_settings, introspection_client, introspection_cache


async def _mcp_audit_emit(event_type: str, payload: dict[str, Any]) -> None:
    """Audit-emit shim for MCP transports.

    The full producer-side outbox path requires a request-scoped
    :class:`AsyncSession`; the streamable-HTTP handler does not flow a
    session into the tool dispatcher. We log a structured record (no
    secret values — the dispatcher already redacts ``settings_set``
    before calling us, and ``settings_set``'s output schema is the
    ``{updated, key}`` receipt) so operators can correlate MCP-driven
    changes. Outbox-write integration is reserved for Phase Audit Batch 3.
    """

    logger.info(
        "mcp_tool_audit",
        event_type=event_type,
        payload_keys=sorted(payload.keys()),
    )


def _build_http_context_provider(
    *,
    authz_settings: AuthzSettings,
    introspection_client: IntrospectionClient | None,
    introspection_cache: IntrospectionCache,
):
    """Return a context provider that reads from the ContextVar set by the ASGI handler."""

    async def _provider() -> ToolContext:
        authorization = _current_authorization.get()
        try:
            return await resolve_tool_context(
                authorization=authorization,
                settings=authz_settings,
                introspection_client=introspection_client,
                introspection_cache=introspection_cache,
                audit_emit=_mcp_audit_emit,
            )
        except MCPAuthError as exc:
            # Translate to ToolPermissionError so the SDK's CallToolResult
            # carries ``isError=True`` with a stable message — mirrors the
            # 401 a REST request would receive, never leaking the token.
            raise ToolPermissionError(str(exc)) from exc

    return _provider


@asynccontextmanager
async def mcp_lifespan(
    app: FastAPI,
    *,
    registry: ToolRegistry | None = None,
) -> AsyncIterator[ToolRegistry]:
    """Build and publish the MCP server onto ``app.state`` for its lifetime.

    The streamable-HTTP session manager owns an anyio task group that must
    be active to dispatch requests. Entering :meth:`StreamableHTTPSessionManager.run`
    inside the FastAPI lifespan ties that task group to the FastAPI process
    exactly. ``app.state.mcp_registry`` is the source of truth for
    ``/mcp/health`` and any future introspection endpoint.
    """

    bound_registry = registry if registry is not None else build_admin_registry()
    authz_settings, introspection_client, introspection_cache = _build_introspection_inputs()
    context_provider = _build_http_context_provider(
        authz_settings=authz_settings,
        introspection_client=introspection_client,
        introspection_cache=introspection_cache,
    )
    server = build_server(bound_registry, context_provider=context_provider)
    manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)

    app.state.mcp_registry = bound_registry
    app.state.mcp_session_manager = manager

    logger.info(
        "mcp_lifespan_starting",
        tool_count=len(bound_registry.names()),
        introspection_enabled=introspection_client is not None,
    )

    async with manager.run():
        try:
            yield bound_registry
        finally:
            logger.info("mcp_lifespan_stopping")


async def mcp_streamable_http_asgi(scope: dict, receive, send) -> None:
    """ASGI handler mounted at ``/mcp``. Forwards to the lifespan-bound manager."""

    if scope["type"] != "http":
        # Non-HTTP scopes (lifespan / websocket) get a no-op response — the
        # parent FastAPI app is the lifespan owner; this mount is a leaf
        # ASGI callable and must be safe to invoke in any phase.
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        return

    fastapi_app = scope.get("app")
    manager = getattr(getattr(fastapi_app, "state", None), "mcp_session_manager", None)
    if manager is None:
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"MCP server not initialized"})
        return

    headers = dict(scope.get("headers", []))
    raw_authorization = headers.get(b"authorization")
    authorization = raw_authorization.decode("latin-1") if raw_authorization else None

    token_handle = _current_authorization.set(authorization)
    try:
        await manager.handle_request(scope, receive, send)
    finally:
        _current_authorization.reset(token_handle)


# ---------------------------------------------------------------------------
# stdio transport — `bsupervisor mcp serve --transport stdio`
# ---------------------------------------------------------------------------


def _configure_stdio_logging() -> None:
    """Send all logs to stderr so the JSON-RPC stdout channel stays clean.

    Stdio MCP frames JSON-RPC messages on stdout — any rogue print or
    structlog handler that targets stdout corrupts the stream. Mirrors the
    BSage stdio launcher.
    """

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


async def run_stdio_server(*, registry: ToolRegistry | None = None) -> None:
    """Boot the same registry on stdin/stdout for Claude Desktop.

    Auth context is read once from ``BSV_BOOTSTRAP_TOKEN`` — stdio callers
    are local processes, so a single bootstrap token bound for the lifetime
    of the connection is the simplest correct posture.
    """

    from mcp.server.stdio import stdio_server

    _configure_stdio_logging()

    bound_registry = registry if registry is not None else build_admin_registry()
    authz_settings, introspection_client, introspection_cache = _build_introspection_inputs()

    bootstrap_token = os.environ.get(BOOTSTRAP_TOKEN_ENV, "").strip()
    fixed_authorization = f"Bearer {bootstrap_token}" if bootstrap_token else None

    async def _stdio_context_provider() -> ToolContext:
        try:
            return await resolve_tool_context(
                authorization=fixed_authorization,
                settings=authz_settings,
                introspection_client=introspection_client,
                introspection_cache=introspection_cache,
                audit_emit=_mcp_audit_emit,
            )
        except MCPAuthError as exc:
            raise ToolPermissionError(str(exc)) from exc

    server = build_server(bound_registry, context_provider=_stdio_context_provider)
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


__all__ = [
    "BOOTSTRAP_TOKEN_ENV",
    "mcp_lifespan",
    "mcp_streamable_http_asgi",
    "run_stdio_server",
]
