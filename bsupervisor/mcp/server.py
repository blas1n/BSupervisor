"""``build_server`` — wrap a :class:`ToolRegistry` behind an ``mcp.server.Server``.

The MCP SDK's ``Server`` exposes a decorator API (``@server.list_tools()`` /
``@server.call_tool()``) that the stdio and HTTP transports both consume.
This factory keeps the dispatcher (validate → authorise → execute → audit)
in :mod:`bsupervisor.mcp.api` and treats the SDK Server as a thin adapter:

- ``ListTools`` returns whatever :meth:`ToolRegistry.list_tools` produces.
- ``CallTool`` resolves a per-call :class:`ToolContext` via the supplied
  ``context_provider`` and forwards to :meth:`ToolRegistry.call_tool`. The
  registry returns a structured dict; the SDK auto-serialises it into both
  ``content`` (JSON text) and ``structuredContent`` and validates against
  the tool's ``outputSchema``.

Input validation is delegated to the registry (Pydantic), so the SDK's own
``jsonschema``-based validator is disabled (``validate_input=False``) — the
registry is the single source of truth for what a valid call looks like.

Domain tools (currently none — see ``.agent/mcp-inventory.md``) and admin
tools (TASK-004) register against the SAME ``ToolRegistry`` before this
factory wraps it, so both surfaces share one dispatcher and one auth path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from mcp.server import Server
from mcp.types import Tool as McpTool
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.mcp.api import ToolContext, ToolRegistry

logger = structlog.get_logger(__name__)

ContextProvider = Callable[[], Awaitable[ToolContext]]
"""Resolve a per-call :class:`ToolContext`. HTTP transport reads from request
headers; stdio reads once from the process environment."""

SessionFactory = Callable[[], Any]
"""Open a fresh :class:`AsyncSession` via async context manager protocol.

Same shape as ``sqlalchemy.ext.asyncio.async_sessionmaker``."""

DEFAULT_SERVER_NAME = "bsupervisor"


def build_server(
    registry: ToolRegistry,
    *,
    context_provider: ContextProvider,
    session_factory: SessionFactory | None = None,
    server_name: str = DEFAULT_SERVER_NAME,
) -> Server:
    """Construct an MCP ``Server`` that delegates to ``registry``.

    The SDK auto-translates exceptions raised inside ``call_tool`` into
    ``CallToolResult(isError=True, ...)`` responses, so the factory does not
    need to catch :class:`bsupervisor.mcp.api.ToolError` itself — letting them
    bubble keeps the error message intact while never leaking internals
    (the message is built inside the dispatcher).

    When ``session_factory`` is supplied (production HTTP wiring), each tool
    call opens a fresh :class:`AsyncSession`, stashes it on ``ctx.db`` for
    admin tools that need it, and closes after the handler returns. Round 4
    Finding 23 — without this thread, every admin tool 500'd with
    ``"admin tool requires ctx.db (AsyncSession)"`` even after F16 unblocked
    the auth introspection path.
    """

    server: Server = Server(server_name)

    @server.list_tools()
    async def _list_tools() -> list[McpTool]:
        return registry.list_tools()

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        ctx = await context_provider()
        if session_factory is None or ctx.db is not None:
            return await registry.call_tool(name, arguments or {}, ctx)
        async with session_factory() as session:
            session_: AsyncSession = session
            ctx.db = session_
            try:
                return await registry.call_tool(name, arguments or {}, ctx)
            finally:
                ctx.db = None

    return server


__all__ = ["ContextProvider", "DEFAULT_SERVER_NAME", "SessionFactory", "build_server"]
