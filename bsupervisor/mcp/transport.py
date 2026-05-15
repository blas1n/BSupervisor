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
  the PAT from the environment exactly once.
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
from starlette.applications import Starlette
from starlette.routing import Mount

from bsupervisor.mcp.admin_tools import build_admin_registry
from bsupervisor.mcp.api import ToolContext, ToolPermissionError, ToolRegistry
from bsupervisor.mcp.auth import MCPAuthError, resolve_tool_context
from bsupervisor.mcp.server import build_server
from bsupervisor.models.database import async_session_factory

logger = structlog.get_logger(__name__)

# Captured per-request from the inbound Authorization header. The
# streamable-HTTP handler does not expose request scope to the tool
# context_provider, so we pin it on a ContextVar instead. ``None`` means
# unauthenticated — :func:`resolve_tool_context` rejects with MCPAuthError.
_current_authorization: ContextVar[str | None] = ContextVar(
    "_mcp_current_authorization",
    default=None,
)

STDIO_TOKEN_ENV = "BSUPERVISOR_PAT"


def _build_introspection_inputs() -> tuple[AuthzSettings | None, IntrospectionClient | None, IntrospectionCache]:
    """Resolve the cached :class:`AuthzSettings` plus introspection helpers.

    Mirrors the FastAPI dependency wiring so MCP and REST share one config
    surface. The introspection client is ``None`` whenever
    ``introspection_url`` is empty — PAT-JWT tokens then fall through and
    fail closed, matching the REST behaviour.

    If the bsvibe-authz Settings cannot be constructed (e.g. demo / smoke
    deployments that intentionally skip the auth env vars), return None for
    settings + client so the PAT-JWT path still works. ``ValidationError``
    is caught explicitly because pydantic-settings raises it when required
    fields are missing — which is acceptable in demo envs.
    """

    from pydantic import ValidationError

    try:
        authz_settings: AuthzSettings | None = get_authz_settings()
    except ValidationError as exc:
        logger.info("mcp_authz_settings_unavailable", reason="missing_env", missing=str(exc))
        # No introspection — JWT path remains the only auth mode.
        return None, None, IntrospectionCache(ttl_s=60)

    introspection_client: IntrospectionClient | None = None
    if authz_settings.introspection_url:
        introspection_client = IntrospectionClient(
            introspection_url=authz_settings.introspection_url,
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
    authz_settings: AuthzSettings | None,
    introspection_client: IntrospectionClient | None,
    introspection_cache: IntrospectionCache,
):
    """Return a context provider that reads from the ContextVar set by the ASGI handler.

    ``authz_settings`` is None in demo deployments where the bsvibe-authz
    env vars are intentionally absent — no-introspection mode. Auth
    resolution still works because ``resolve_tool_context`` reads the
    local Settings only (no introspection wire)."""

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

    # Lazy context provider — resolves the bsvibe-authz Settings + introspection
    # helpers on every call instead of at lifespan-startup. This keeps demo /
    # smoke deployments (which intentionally skip the bsvibe-authz env vars)
    # bootable; per-request auth still rejects (401) until the env is wired,
    # but the rest of the app comes up.
    async def _lazy_context_provider() -> ToolContext:
        authorization = _current_authorization.get()
        authz_settings, introspection_client, introspection_cache = _build_introspection_inputs()
        if authz_settings is None:
            # bsvibe-authz Settings unavailable — introspection path can't be
            # verified either (no hash). Surface as auth failure.
            raise ToolPermissionError("authz settings unavailable")
        try:
            return await resolve_tool_context(
                authorization=authorization,
                settings=authz_settings,
                introspection_client=introspection_client,
                introspection_cache=introspection_cache,
                audit_emit=_mcp_audit_emit,
            )
        except MCPAuthError as exc:
            raise ToolPermissionError(str(exc)) from exc

    server = build_server(
        bound_registry,
        context_provider=_lazy_context_provider,
        session_factory=async_session_factory,
    )
    manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)

    app.state.mcp_registry = bound_registry
    app.state.mcp_session_manager = manager

    logger.info(
        "mcp_lifespan_starting",
        tool_count=len(bound_registry.names()),
    )

    async with manager.run():
        try:
            yield bound_registry
        finally:
            logger.info("mcp_lifespan_stopping")


def build_mcp_subapp(parent_app: FastAPI) -> Starlette:
    """Wrap the streamable-HTTP ASGI handler in a Starlette sub-app so the
    lifespan_context is independent from the parent FastAPI app.

    Mounting a bare ASGI callable directly with ``app.mount("/mcp", fn)``
    triggers starlette's ``merged_lifespan`` recursion (the mounted callable's
    default lifespan_context resolves back through the parent's, and the
    parent re-merges it on every iteration — RecursionError under
    ``app.router.lifespan_context``). A Starlette sub-app owns its own
    explicit no-op lifespan, breaking the cycle.

    The endpoint reads the streamable-HTTP session manager from
    ``parent_app.state`` lazily (set by :func:`mcp_lifespan` during parent
    startup), so it doesn't matter that the sub-app is constructed before
    the parent's lifespan has run.
    """

    async def _http_handler(scope: dict, receive, send) -> None:
        manager = getattr(parent_app.state, "mcp_session_manager", None)
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

    return Starlette(routes=[Mount("/", app=_http_handler)])


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

    Auth context is read once from ``BSUPERVISOR_PAT`` — stdio callers
    are local processes, so a single PAT bound for the lifetime of the
    connection is the simplest correct posture.
    """

    from mcp.server.stdio import stdio_server

    _configure_stdio_logging()

    bound_registry = registry if registry is not None else build_admin_registry()
    authz_settings, introspection_client, introspection_cache = _build_introspection_inputs()

    pat = os.environ.get(STDIO_TOKEN_ENV, "").strip()
    fixed_authorization = f"Bearer {pat}" if pat else None

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
    "STDIO_TOKEN_ENV",
    "build_mcp_subapp",
    "mcp_lifespan",
    "run_stdio_server",
]
