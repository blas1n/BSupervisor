"""Tests for :mod:`bsupervisor.mcp.server` ``build_server`` factory.

The factory wraps a :class:`bsupervisor.mcp.api.ToolRegistry` behind the
``mcp.server.Server`` protocol object: ListTools / CallTool decorators
delegate to the registry, while the per-call :class:`ToolContext` is
supplied by a transport-specific ``context_provider``. Tests follow the
``mcp-python-sdk-testing`` memory: NEVER spawn a subprocess — invoke
``server.request_handlers[ListToolsRequest]`` /
``server.request_handlers[CallToolRequest]`` directly with bound request
objects, the result is wrapped in :class:`ServerResult.root`.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import mcp.types as mcp_types
import pytest
from bsvibe_authz import Settings, User
from bsvibe_authz.cache import PermissionCache
from mcp.server import Server
from pydantic import BaseModel

from bsupervisor.mcp.api import Tool, ToolContext, ToolRegistry
from bsupervisor.mcp.server import build_server


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _PingIn(BaseModel):
    message: str


class _PingOut(BaseModel):
    echoed: str


class _MutateIn(BaseModel):
    payload: str


class _MutateOut(BaseModel):
    written: str


async def _ping_handler(args: _PingIn, ctx: ToolContext) -> _PingOut:
    return _PingOut(echoed=args.message)


async def _mutate_handler(args: _MutateIn, ctx: ToolContext) -> _MutateOut:
    return _MutateOut(written=args.payload)


class _FakeFGA:
    """OpenFGA stand-in — ``check`` returns ``allow``, ``write_tuple`` no-ops."""

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow

    async def check(self, user: str, relation: str, object_: str) -> bool:
        return self.allow

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []

    async def write_tuple(self, user: str, relation: str, object_: str) -> None:
        return None


def _mk_user() -> User:
    return User(id="u", active_tenant_id="tenant-1", is_service=False)


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="bsupervisor_ping",
            description="echo a message",
            input_schema=_PingIn,
            output_schema=_PingOut,
            handler=_ping_handler,
            required_permission="bsupervisor.audit.read",
        )
    )
    reg.register(
        Tool(
            name="bsupervisor_mutate",
            description="write payload",
            input_schema=_MutateIn,
            output_schema=_MutateOut,
            handler=_mutate_handler,
            required_permission="bsupervisor.agents.write",
            audit_event="supervisor.mutated",
        )
    )
    return reg


def _provider_factory(
    *,
    allow: bool = True,
    openfga_configured: bool = False,
    audit_calls: list[tuple[str, dict]] | None = None,
    counter: list[int] | None = None,
) -> Callable[[], Awaitable[ToolContext]]:
    """Build a context provider.

    ``openfga_configured`` toggles ``settings.openfga_api_url`` — empty
    means ``check_tenant_permission`` is permissive; set means it delegates
    to a fake FGA client whose verdict is ``allow``.
    """

    async def _audit(event: str, payload: dict) -> None:
        if audit_calls is not None:
            audit_calls.append((event, payload))

    settings = Settings(
        openfga_api_url="http://openfga.test" if openfga_configured else "",
    )

    async def _provider() -> ToolContext:
        if counter is not None:
            counter.append(1)
        return ToolContext(
            user=_mk_user(),
            audit_emit=_audit,
            fga=_FakeFGA(allow=allow),
            cache=PermissionCache(ttl_s=30),
            settings=settings,
        )

    return _provider


def _list_request() -> mcp_types.ListToolsRequest:
    return mcp_types.ListToolsRequest(method="tools/list")


def _call_request(
    name: str,
    arguments: dict | None,
) -> mcp_types.CallToolRequest:
    return mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_server_returns_named_server(registry: ToolRegistry) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider, server_name="bsupervisor")

    assert isinstance(server, Server)
    assert server.name == "bsupervisor"


def test_build_server_default_name(registry: ToolRegistry) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)

    assert server.name == "bsupervisor"


def test_request_handlers_registered(registry: ToolRegistry) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)

    assert mcp_types.ListToolsRequest in server.request_handlers
    assert mcp_types.CallToolRequest in server.request_handlers


@pytest.mark.asyncio
async def test_list_tools_delegates_to_registry(registry: ToolRegistry) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.ListToolsRequest]

    result = await handler(_list_request())
    list_tools_result = result.root

    assert isinstance(list_tools_result, mcp_types.ListToolsResult)
    names = [t.name for t in list_tools_result.tools]
    assert names == ["bsupervisor_ping", "bsupervisor_mutate"]
    # JSON schema lives with the Pydantic model, not a hand-written dict.
    ping = next(t for t in list_tools_result.tools if t.name == "bsupervisor_ping")
    assert "message" in ping.inputSchema["properties"]


@pytest.mark.asyncio
async def test_call_tool_returns_json_text_content(registry: ToolRegistry) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_ping", {"message": "hi"}))
    call_result = result.root

    assert isinstance(call_result, mcp_types.CallToolResult)
    assert call_result.isError is False
    assert len(call_result.content) == 1
    text = call_result.content[0].text
    assert json.loads(text) == {"echoed": "hi"}


@pytest.mark.asyncio
async def test_call_tool_invokes_provider_per_call(registry: ToolRegistry) -> None:
    counter: list[int] = []
    provider = _provider_factory(counter=counter)
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    await handler(_call_request("bsupervisor_ping", {"message": "a"}))
    await handler(_call_request("bsupervisor_ping", {"message": "b"}))

    assert len(counter) == 2


@pytest.mark.asyncio
async def test_call_tool_treats_missing_arguments_as_empty_dict(registry: ToolRegistry) -> None:
    """``arguments`` may be ``None`` per the MCP protocol — registry sees ``{}``."""

    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_ping", None))
    call_result = result.root

    # Empty args fail input validation (message is required) → SDK wraps the
    # ToolInputError in isError=True, never crashes the transport.
    assert call_result.isError is True


@pytest.mark.asyncio
async def test_call_tool_permission_denied_surfaces_as_iserror(
    registry: ToolRegistry,
) -> None:
    provider = _provider_factory(allow=False, openfga_configured=True)  # OpenFGA denies
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_ping", {"message": "hi"}))
    call_result = result.root

    assert call_result.isError is True
    assert "bsupervisor.audit.read" in call_result.content[0].text


@pytest.mark.asyncio
async def test_call_tool_unknown_tool_surfaces_as_iserror(
    registry: ToolRegistry,
) -> None:
    provider = _provider_factory()
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_nope", {}))
    call_result = result.root

    assert call_result.isError is True
    assert "bsupervisor_nope" in call_result.content[0].text


@pytest.mark.asyncio
async def test_call_tool_audit_emit_fires_on_mutating_tool(
    registry: ToolRegistry,
) -> None:
    audit_calls: list[tuple[str, dict]] = []
    provider = _provider_factory(audit_calls=audit_calls)
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_mutate", {"payload": "thing"}))

    assert result.root.isError is False
    assert audit_calls == [("supervisor.mutated", {"written": "thing"})]


@pytest.mark.asyncio
async def test_call_tool_no_audit_when_denied(registry: ToolRegistry) -> None:
    audit_calls: list[tuple[str, dict]] = []
    provider = _provider_factory(allow=False, openfga_configured=True, audit_calls=audit_calls)  # denied
    server = build_server(registry, context_provider=provider)
    handler = server.request_handlers[mcp_types.CallToolRequest]

    result = await handler(_call_request("bsupervisor_mutate", {"payload": "x"}))

    assert result.root.isError is True
    assert audit_calls == []
