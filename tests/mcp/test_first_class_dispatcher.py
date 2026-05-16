"""Tests for the first-class MCP Tool primitive + ToolRegistry dispatcher.

Covers:
- ListTools surfaces every registered tool with the JSON schema derived from
  ``tool.input_schema.model_json_schema()``.
- CallTool validates args against ``input_schema`` (raises on bad input).
- CallTool enforces ``required_permission`` via the tenant-scoped OpenFGA
  check (``bsvibe_authz.check_tenant_permission``) — Tier 5 Phase 3a, the
  same model the REST ``require_permission`` gate uses. The check is
  permissive when OpenFGA is unconfigured; with ``openfga_api_url`` set it
  delegates to a fake FGA client.
- CallTool validates the handler's return value against ``output_schema``.
- CallTool fires ``ctx.audit_emit`` exactly when ``audit_event`` is set and
  the handler succeeded — never on validation/permission failure.
- Error cases: unknown tool, schema-invalid args, denied permission, handler
  raise, output-schema mismatch — all surface as typed errors.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from bsvibe_authz import Settings, User
from bsvibe_authz.cache import PermissionCache
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


class _FakeFGA:
    """Minimal :class:`bsvibe_authz.deps.FGAClientProtocol` stand-in.

    ``allow`` is the verdict every ``check`` returns; ``write_tuple`` is a
    no-op so the dispatcher's lazy role-tuple provisioning never errors.
    """

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.checks: list[tuple[str, str, str]] = []

    async def check(self, user: str, relation: str, object_: str) -> bool:
        self.checks.append((user, relation, object_))
        return self.allow

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []

    async def write_tuple(self, user: str, relation: str, object_: str) -> None:
        return None


def _mk_user(*, is_demo: bool = False, tenant: str | None = "tenant-1") -> User:
    """A real (non-demo, non-service) user with an active tenant.

    Service principals and demo users bypass the OpenFGA check, so the
    enforcement tests use a plain user with a tenant binding.
    """
    return User(
        id="user-test",
        active_tenant_id=tenant,
        is_service=False,
        is_demo=is_demo,
    )


def _mk_ctx(
    *,
    user: User | None = None,
    fga: _FakeFGA | None = None,
    openfga_configured: bool = False,
    audit_emit: Callable[[str, dict], Awaitable[None]] | None = None,
    omit_authz_deps: bool = False,
) -> ToolContext:
    """Build a :class:`ToolContext`.

    ``openfga_configured`` toggles ``settings.openfga_api_url`` — empty
    means ``check_tenant_permission`` is permissive (test/demo posture);
    set means it delegates to ``fga``. ``omit_authz_deps`` simulates a
    transport that could not build the OpenFGA deps (fail-closed path).
    """

    async def _noop_audit(event: str, payload: dict) -> None:  # pragma: no cover
        return None

    if omit_authz_deps:
        return ToolContext(
            user=user or _mk_user(),
            audit_emit=audit_emit or _noop_audit,
        )

    settings = Settings(
        openfga_api_url="http://openfga.test" if openfga_configured else "",
    )
    return ToolContext(
        user=user or _mk_user(),
        audit_emit=audit_emit or _noop_audit,
        fga=fga or _FakeFGA(allow=True),
        cache=PermissionCache(ttl_s=30),
        settings=settings,
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
            required_permission="bsupervisor.audit.read",
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
        required_permission=None,
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
            required_permission=None,
        )
    )

    out = await registry.call_tool("echo", {"message": "hi"}, _mk_ctx())

    assert out == {"echoed": "hi"}


@pytest.mark.asyncio
async def test_call_tool_unknown_name_raises_not_found() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        await registry.call_tool("missing", {}, _mk_ctx())


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
            required_permission=None,
        )
    )

    with pytest.raises(ToolInputError):
        await registry.call_tool("echo", {"message": ""}, _mk_ctx())


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
            required_permission=None,
        )
    )

    with pytest.raises(ToolOutputError):
        await registry.call_tool("echo", {"message": "x"}, _mk_ctx())


# ---------------------------------------------------------------------------
# CallTool — permission enforcement (Tier 5 OpenFGA check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_permissive_when_openfga_unconfigured() -> None:
    """OpenFGA not deployed → check_tenant_permission passes any caller."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_permission="bsupervisor.audit.read",
        )
    )

    out = await registry.call_tool("echo", {"message": "x"}, _mk_ctx(openfga_configured=False))

    assert out == {"echoed": "x"}


@pytest.mark.asyncio
async def test_permission_granted_when_fga_allows() -> None:
    fga = _FakeFGA(allow=True)
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_permission="bsupervisor.agents.write",
        )
    )

    out = await registry.call_tool(
        "echo",
        {"message": "x"},
        _mk_ctx(fga=fga, openfga_configured=True),
    )

    assert out == {"echoed": "x"}
    # The tenant-scoped relation is the dot string with dots → underscores.
    assert fga.checks == [("user:user-test", "bsupervisor_agents_write", "tenant:tenant-1")]


@pytest.mark.asyncio
async def test_permission_denied_raises_error_and_skips_handler() -> None:
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
            required_permission="bsupervisor.agents.write",
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "echo",
            {"message": "x"},
            _mk_ctx(fga=_FakeFGA(allow=False), openfga_configured=True),
        )

    assert called == []


@pytest.mark.asyncio
async def test_permission_denied_when_user_has_no_active_tenant() -> None:
    """With OpenFGA configured a tenant-less caller cannot resolve the
    ``tenant:<id>`` object → check_tenant_permission returns False."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_permission="bsupervisor.audit.read",
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "echo",
            {"message": "x"},
            _mk_ctx(user=_mk_user(tenant=None), openfga_configured=True),
        )


@pytest.mark.asyncio
async def test_dispatch_fails_closed_when_authz_deps_missing() -> None:
    """A guarded tool must never dispatch without an OpenFGA decision —
    a transport that could not build fga/cache/settings is a denial."""
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
            required_permission="bsupervisor.audit.read",
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool("echo", {"message": "x"}, _mk_ctx(omit_authz_deps=True))

    assert called == []


@pytest.mark.asyncio
async def test_unguarded_tool_dispatches_without_authz_deps() -> None:
    """``required_permission=None`` tools skip the check entirely."""
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo",
            description="x",
            input_schema=_EchoIn,
            output_schema=_EchoOut,
            handler=_echo_handler,
            required_permission=None,
        )
    )

    out = await registry.call_tool("echo", {"message": "x"}, _mk_ctx(omit_authz_deps=True))

    assert out == {"echoed": "x"}


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
            required_permission=None,
            audit_event="supervisor.add.invoked",
        )
    )

    out = await registry.call_tool("add", {"a": 2, "b": 3}, _mk_ctx(audit_emit=emit))

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
            required_permission=None,
            # audit_event left None → read-only tool
        )
    )

    await registry.call_tool("echo", {"message": "hi"}, _mk_ctx(audit_emit=emit))

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
            required_permission="bsupervisor.agents.write",
            audit_event="supervisor.add.invoked",
        )
    )

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "add",
            {"a": 1, "b": 2},
            _mk_ctx(fga=_FakeFGA(allow=False), openfga_configured=True, audit_emit=emit),
        )

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
            required_permission=None,
            audit_event="supervisor.add.invoked",
        )
    )

    with pytest.raises(RuntimeError):
        await registry.call_tool("add", {"a": 1, "b": 2}, _mk_ctx(audit_emit=emit))

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
        required_permission=None,
    )
    registry.register(tool)

    assert registry.names() == ["echo"]
    assert registry.get("echo") is tool
    with pytest.raises(ToolNotFoundError):
        registry.get("missing")
