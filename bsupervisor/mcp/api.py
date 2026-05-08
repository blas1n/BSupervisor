"""First-class MCP API — Tool primitive, ToolContext, ToolRegistry dispatcher.

Phase 7 design: tools are first-class definitions with explicit Pydantic
``input_schema`` + ``output_schema``, an async handler, ``required_scopes``
checked via the same ``bsvibe_authz`` semantics REST routes use, and an
optional ``audit_event`` that fires on success — mirroring how REST routers
are defined. CLI is a presentation layer; MCP is its own API surface that
calls the same service-layer functions REST handlers call. **No typer
auto-adapter.**

The dispatcher is transport-agnostic: HTTP ``/mcp`` and stdio both wrap the
same :class:`ToolRegistry`. Auth resolution lives in :mod:`bsupervisor.mcp.auth`
so the registry stays focused on tool dispatch.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from bsvibe_authz import User
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolError(Exception):
    """Base class for MCP-tool errors."""


class ToolNotFoundError(ToolError):
    """Requested tool name is not registered."""


class ToolInputError(ToolError):
    """Args do not validate against ``input_schema``."""


class ToolOutputError(ToolError):
    """Handler return value does not validate against ``output_schema``."""


class ToolPermissionError(ToolError):
    """User scope does not grant ``required_scopes``."""


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


AuditEmit = Callable[[str, dict[str, Any]], Awaitable[None]]
"""Fire an audit event (event_type, payload). Caller-supplied so the registry
stays decoupled from any particular outbox session."""


@dataclass
class ToolContext:
    """Runtime context handed to every tool handler.

    Mirrors the FastAPI request-scope context REST handlers see (``user`` for
    auth, ``db`` for the request session, ``audit_emit`` for outbox writes).
    Transports build this once per call via :func:`bsupervisor.mcp.auth.resolve_tool_context`.
    """

    user: User
    audit_emit: AuditEmit
    db: AsyncSession | None = None
    extras: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[BaseModel, ToolContext], Awaitable[BaseModel]]


@dataclass
class Tool:
    """First-class MCP tool definition.

    Equivalent to a single FastAPI route: input/output schemas plus the
    scope guard and audit event are part of the tool's identity, not glued
    on at registration time.
    """

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    handler: Handler
    required_scopes: list[str]
    audit_event: str | None = None


# ---------------------------------------------------------------------------
# Scope semantics — copied from bsvibe_authz.deps._scope_grants so the MCP
# transport behaves exactly like require_scope on REST.
# ---------------------------------------------------------------------------


def _scope_grants(user_scopes: list[str], required: str) -> bool:
    for granted in user_scopes:
        if granted == "*" or granted == required:
            return True
        if granted.endswith(":*") and required.startswith(granted[:-1]):
            return True
    return False


# ---------------------------------------------------------------------------
# Registry / dispatcher
# ---------------------------------------------------------------------------


class ToolRegistry:
    """In-memory catalog of first-class :class:`Tool` definitions."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # -- registration --------------------------------------------------------

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"unknown tool: {name}") from exc

    def names(self) -> list[str]:
        return list(self._tools.keys())

    # -- mcp.types surface ---------------------------------------------------

    def list_tools(self) -> list[mcp_types.Tool]:
        """Return every registered tool as an :class:`mcp.types.Tool`.

        ``inputSchema`` is the JSON schema of the Pydantic model — schemas
        live with the model definition, never auto-derived from a CLI.
        """

        return [
            mcp_types.Tool(
                name=t.name,
                description=t.description,
                inputSchema=t.input_schema.model_json_schema(),
                outputSchema=t.output_schema.model_json_schema(),
            )
            for t in self._tools.values()
        ]

    # -- dispatch ------------------------------------------------------------

    async def call_tool(
        self,
        name: str,
        args: dict[str, Any],
        ctx: ToolContext,
    ) -> dict[str, Any]:
        """Validate → authorise → execute → validate output → audit emit.

        The handler is only invoked once scope and input validation pass, so a
        denial never executes user-visible side effects. ``audit_event`` only
        fires after a successful handler + output-schema validation.
        """

        tool = self.get(name)

        # 1. enforce scopes — never invoke the handler on denial.
        for required in tool.required_scopes:
            if not _scope_grants(ctx.user.scope, required):
                logger.info(
                    "mcp_tool_denied",
                    tool=tool.name,
                    user_id=ctx.user.id,
                    required_scope=required,
                )
                raise ToolPermissionError(
                    f"missing required scope: {required}",
                )

        # 2. validate input against the Pydantic schema.
        try:
            parsed_args = tool.input_schema.model_validate(args)
        except ValidationError as exc:
            raise ToolInputError(f"invalid args for {tool.name}: {exc}") from exc

        # 3. run handler.
        result = await tool.handler(parsed_args, ctx)

        # 4. validate output — handlers must honour the declared output schema.
        try:
            validated = tool.output_schema.model_validate(
                result.model_dump() if isinstance(result, BaseModel) else result,
            )
        except ValidationError as exc:
            raise ToolOutputError(
                f"handler for {tool.name} returned invalid output: {exc}",
            ) from exc

        output_dict = validated.model_dump(mode="json")

        # 5. audit emit on success only.
        if tool.audit_event:
            await ctx.audit_emit(tool.audit_event, output_dict)

        return output_dict


__all__ = [
    "AuditEmit",
    "Handler",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolInputError",
    "ToolNotFoundError",
    "ToolOutputError",
    "ToolPermissionError",
    "ToolRegistry",
]
