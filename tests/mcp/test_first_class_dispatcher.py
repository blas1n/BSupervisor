"""Tests for the first-class MCP Tool primitive + ToolRegistry dispatcher.

Covers:
- ListTools surfaces every registered tool with the JSON schema derived from
  ``tool.input_schema.model_json_schema()``.
- CallTool validates args against ``input_schema`` (raises on bad input).
- CallTool enforces ``required_scopes`` against ``ctx.user`` (3-way dispatch
  scope semantics: ``"*"`` wildcard, ``":*"`` prefix, exact match).
- CallTool validates the handler's return value against ``output_schema``.
- CallTool fires ``ctx.audit_emit`` exactly when ``audit_event`` is set and
  the handler succeeded — never on validation/permission failure.
- Error cases: unknown tool, schema-invalid args, denied scope, handler raise,
  output-schema mismatch — all surface as typed errors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from bsvibe_authz import User
from pydantic import BaseModel, Field

from bsupervisor.mcp.api import (
    Tool,
    ToolContext,
    ToolInputError,
    ToolNotFoundError,
    ToolOutputError,
    ToolPermissionError,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _EchoIn(BaseModel):
    message: str = Field(..., min_length=1)


class _EchoOut(BaseModel):
    echoed: str


class _AddIn(BaseModel):
    a: int
    b: int


class _AddOut(BaseModel):
    total: int


class _BadOut(BaseModel):
    must_be_string: str


def _mk_user(scopes: list[str]) -> User:
    return User(id="user-test", scope=scopes, is_service=True)


def _mk_ctx(
    *,
    scopes: list[str],
    audit_emit: Callable[[str, dict], Awaitable[None]] | None = None,
) -> ToolContext:
    async def _noop_audit(event: str, payload: dict) -> None:  # pragma: no cover
        return None

    return ToolContext(
        user=_mk_user(scopes),
        audit_emit=audit_emit or _noop_audit,
    )


async def _echo_handler(args: _EchoIn, ctx: ToolContext) -> _EchoOut:
    return _EchoOut(echoed=args.message)


async def _add_handler(args: _AddIn, ctx: ToolContext) -> _AddOut:
    return _AddOut(total=args.a + args.b)


# ---------------------------------------------------------------------------
# ListTools surface
# ---------------------------------------------------------------------------


def test_list_tools_returns_mcp_tool_objects_with_input_schema() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="Echo a message back",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=["bsupervisor:audit:read"],
        )
    )

    listed = registry.list_tools()

    assert len(listed) == 1
    tool = listed[0]
    assert tool.name == "echo"
    assert tool.description == "Echo a message back"
    # JSON schema is the Pydantic model schema, not auto-derived.
    assert tool.inputSchema == _EchoIn.model_json_schema()


def test_register_duplicate_tool_name_raises() -> None:
    registry = ToolRegistry()
    tool = Tool(
        name="echo",
        description="x",
        input_schema=_EchoIn,
        output_schema=_EchoOut,
        handler=_echo_handler,
        required_scopes=[],
    )
    registry.register(tool)
    with pytest.raises(ValueError):
        registry.register(tool)


# ---------------------------------------------------------------------------
# CallTool — happy path + schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_tool_validates_input_and_returns_output_dict() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=[],
        )
    )

    out = await registry.call_tool("echo", {"message": "hi"}, _mk_ctx(scopes=[]))

    assert out == {"echoed": "hi"}


@pytest.mark.asyncio
async def test_call_tool_unknown_name_raises_not_found() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        await registry.call_tool("missing", {}, _mk_ctx(scopes=[]))


@pytest.mark.asyncio
async def test_call_tool_invalid_args_raises_input_error() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=[],
        )
    )

    with pytest.raises(ToolInputError):
        await registry.call_tool("echo", {"message": ""}, _mk_ctx(scopes=[]))


@pytest.mark.asyncio
async def test_call_tool_handler_returning_wrong_shape_raises_output_error() -> None:
    async def bad_handler(args: _EchoIn, ctx: ToolContext) -> _BadOut:
        # handler returns the wrong model — registry must catch this.
        return _BadOut(must_be_string="ok")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=bad_handler,  # type: ignore[arg-type]
            required_scopes=[],
        )
    )

    with pytest.raises(ToolOutputError):
        await registry.call_tool("echo", {"message": "x"}, _mk_ctx(scopes=[]))


# ---------------------------------------------------------------------------
# CallTool — scope enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_wildcard_grants_any_required_scope() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=["bsupervisor:audit:read"],
        )
    )

    out = await registry.call_tool("echo", {"message": "x"}, _mk_ctx(scopes=["*"]))

    assert out == {"echoed": "x"}


@pytest.mark.asyncio
async def test_scope_prefix_wildcard_grants_required_scope() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=["bsupervisor:agents:write"],
        )
    )

    out = await registry.call_tool("echo", {"message": "x"}, _mk_ctx(scopes=["bsupervisor:*"]))

    assert out == {"echoed": "x"}


@pytest.mark.asyncio
async def test_scope_denied_raises_permission_error_and_skips_handler() -> None:
    called: list[bool] = []

    async def handler(args: _EchoIn, ctx: ToolContext) -> _EchoOut:
        called.append(True)
        return _EchoOut(echoed=args.message)

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=handler,
            required_scopes=["bsupervisor:agents:write"],
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool("echo", {"message": "x"}, _mk_ctx(scopes=["bsupervisor:audit:read"]))

    assert called == []


@pytest.mark.asyncio
async def test_multiple_required_scopes_all_must_be_granted() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=["bsupervisor:agents:write", "bsupervisor:audit:read"],
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "echo",
            {"message": "x"},
            _mk_ctx(scopes=["bsupervisor:agents:write"]),  # missing audit:read
        )


# ---------------------------------------------------------------------------
# CallTool — audit emit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_emit_fires_on_success_when_event_set() -> None:
    captured: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:
        captured.append((event, payload))

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="add",
            description="x",
            input_schema=_AddIn,
            output_schema=_AddOut,
            handler=_add_handler,
            required_scopes=[],
            audit_event="supervisor.add.invoked",
        )
    )

    out = await registry.call_tool("add", {"a": 2, "b": 3}, _mk_ctx(scopes=[], audit_emit=emit))

    assert out == {"total": 5}
    assert captured == [("supervisor.add.invoked", {"total": 5})]


@pytest.mark.asyncio
async def test_audit_emit_does_not_fire_when_audit_event_unset() -> None:
    captured: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:  # pragma: no cover
        captured.append((event, payload))

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_scopes=[],
            # audit_event left None → read-only tool
        )
    )

    await registry.call_tool("echo", {"message": "hi"}, _mk_ctx(scopes=[], audit_emit=emit))

    assert captured == []


@pytest.mark.asyncio
async def test_audit_emit_does_not_fire_on_permission_denial() -> None:
    captured: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:  # pragma: no cover
        captured.append((event, payload))

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="add",
            description="x",
            input_schema=_AddIn,
            output_schema=_AddOut,
            handler=_add_handler,
            required_scopes=["bsupervisor:agents:write"],
            audit_event="supervisor.add.invoked",
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool("add", {"a": 1, "b": 2}, _mk_ctx(scopes=["bsupervisor:audit:read"], audit_emit=emit))

    assert captured == []


@pytest.mark.asyncio
async def test_audit_emit_does_not_fire_on_handler_exception() -> None:
    captured: list[tuple[str, dict]] = []

    async def emit(event: str, payload: dict) -> None:  # pragma: no cover
        captured.append((event, payload))

    async def boom(args: _AddIn, ctx: ToolContext) -> _AddOut:
        raise RuntimeError("kaboom")

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="add",
            description="x",
            input_schema=_AddIn,
            output_schema=_AddOut,
            handler=boom,
            required_scopes=[],
            audit_event="supervisor.add.invoked",
        )
    )

    with pytest.raises(RuntimeError):
        await registry.call_tool("add", {"a": 1, "b": 2}, _mk_ctx(scopes=[], audit_emit=emit))

    assert captured == []


# ---------------------------------------------------------------------------
# names / metadata
# ---------------------------------------------------------------------------


def test_registry_names_and_get() -> None:
    registry = ToolRegistry()
    tool = Tool(
        name="echo",
        description="x",
        input_schema=_EchoIn,
        output_schema=_EchoOut,
        handler=_echo_handler,
        required_scopes=[],
    )
    registry.register(tool)

    assert registry.names() == ["echo"]
    assert registry.get("echo") is tool
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")
