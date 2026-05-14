"""Coverage tests for :mod:`bsupervisor.mcp.transport` internals.

The end-to-end behaviour is covered by ``tests/mcp/test_http_mount.py``.
Here we drive the leaf helpers (context provider, stdio logging
configurator, ASGI lifespan branch, stdio runner) directly so the module
clears the 80% gate even when the streamable-HTTP transport is not driven.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from bsupervisor.mcp import transport as mcp_transport
from bsupervisor.mcp.api import ToolPermissionError


def test_configure_stdio_logging_redirects_to_stderr() -> None:
    """All root handlers are replaced with a single stderr StreamHandler."""
    mcp_transport._configure_stdio_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0], logging.StreamHandler)


@pytest.mark.asyncio
async def test_http_context_provider_resolves_token_from_contextvar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The provider reads ``_current_authorization`` and feeds it to
    :func:`resolve_tool_context`."""

    raw = "bsv_sk_xyz"

    captured: dict[str, str | None] = {}

    async def _fake_resolve(*, authorization, **_):  # type: ignore[no-untyped-def]
        captured["auth"] = authorization
        return MagicMock()

    monkeypatch.setattr(mcp_transport, "resolve_tool_context", _fake_resolve)

    authz_settings, introspection_client, introspection_cache = mcp_transport._build_introspection_inputs()
    provider = mcp_transport._build_http_context_provider(
        authz_settings=authz_settings,
        introspection_client=introspection_client,
        introspection_cache=introspection_cache,
    )

    token_handle = mcp_transport._current_authorization.set(f"Bearer {raw}")
    try:
        await provider()
    finally:
        mcp_transport._current_authorization.reset(token_handle)

    assert captured["auth"] == f"Bearer {raw}"


@pytest.mark.asyncio
async def test_http_context_provider_translates_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``MCPAuthError`` from the dispatcher becomes a ``ToolPermissionError``
    so the SDK wraps it as ``isError=True`` instead of crashing the stream."""

    async def _fake_resolve(*, authorization, **_):  # type: ignore[no-untyped-def]
        raise mcp_transport.MCPAuthError("nope")

    monkeypatch.setattr(mcp_transport, "resolve_tool_context", _fake_resolve)

    authz_settings, introspection_client, introspection_cache = mcp_transport._build_introspection_inputs()
    provider = mcp_transport._build_http_context_provider(
        authz_settings=authz_settings,
        introspection_client=introspection_client,
        introspection_cache=introspection_cache,
    )
    with pytest.raises(ToolPermissionError):
        await provider()


def test_build_introspection_inputs_constructs_client_with_introspection_url_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for F16 (Round 4): the IntrospectionClient constructor takes
    ``introspection_url=``, not ``url=``. Passing the wrong kwarg crashes every
    MCP tool call with a TypeError. We exercise the real construction path with
    env vars set so the if-branch is taken."""
    from bsvibe_authz import IntrospectionClient

    monkeypatch.setenv("INTROSPECTION_URL", "https://auth.example.invalid/oauth/introspect")
    monkeypatch.setenv("INTROSPECTION_CLIENT_ID", "supervisor")
    monkeypatch.setenv("INTROSPECTION_CLIENT_SECRET", "test-secret")

    from bsvibe_authz.settings import reset_settings_cache

    reset_settings_cache()
    try:
        _, introspection_client, _ = mcp_transport._build_introspection_inputs()
    finally:
        reset_settings_cache()

    assert isinstance(introspection_client, IntrospectionClient)


@pytest.mark.asyncio
async def test_mcp_subapp_handles_lifespan_scope() -> None:
    """The Starlette sub-app returned by ``build_mcp_subapp`` completes a
    lifespan startup/shutdown cycle without touching the parent — that
    independence is what breaks the merged_lifespan recursion."""
    from fastapi import FastAPI

    parent = FastAPI()
    subapp = mcp_transport.build_mcp_subapp(parent)

    received: list[dict] = []

    async def _send(message: dict) -> None:
        received.append(message)

    messages = iter(
        [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
    )

    async def _receive() -> dict:
        return next(messages)

    await subapp({"type": "lifespan"}, _receive, _send)

    types = [m["type"] for m in received]
    assert "lifespan.startup.complete" in types
    assert "lifespan.shutdown.complete" in types


@pytest.mark.asyncio
async def test_mcp_subapp_delegates_to_session_manager() -> None:
    """The sub-app reads ``parent_app.state.mcp_session_manager`` lazily and
    captures the Authorization header into the ContextVar for the duration
    of ``handle_request``."""
    from fastapi import FastAPI

    parent = FastAPI()
    captured_auth: dict[str, str | None] = {}

    async def _fake_handle(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        captured_auth["seen"] = mcp_transport._current_authorization.get()

    fake_manager = MagicMock()
    fake_manager.handle_request = _fake_handle
    parent.state.mcp_session_manager = fake_manager

    subapp = mcp_transport.build_mcp_subapp(parent)

    async def _receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message: dict) -> None:
        return None

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"authorization", b"Bearer bsv_sk_token")],
        "query_string": b"",
        "raw_path": b"/",
    }
    await subapp(scope, _receive, _send)
    assert captured_auth["seen"] == "Bearer bsv_sk_token"
    # ContextVar must reset after the request to avoid bleeding across calls.
    assert mcp_transport._current_authorization.get() is None


@pytest.mark.asyncio
async def test_run_stdio_server_drives_sdk_stdio_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_stdio_server`` resolves auth, builds the server, and hands
    off to the SDK's ``stdio_server`` context manager. We patch every
    external dep so the test never touches real stdio or the env."""

    monkeypatch.setenv("BSUPERVISOR_PAT", "bsv_sk_xyz")

    async def _fake_resolve(*, authorization, **_):  # type: ignore[no-untyped-def]
        assert authorization == "Bearer bsv_sk_xyz"
        return MagicMock(scope=["bsupervisor:*"])

    monkeypatch.setattr(mcp_transport, "resolve_tool_context", _fake_resolve)

    fake_server = MagicMock()
    fake_server.run = AsyncMock(return_value=None)
    fake_server.create_initialization_options = MagicMock(return_value={})

    monkeypatch.setattr(mcp_transport, "build_server", lambda *a, **k: fake_server)

    class _FakeStdioCtx:
        async def __aenter__(self):
            return MagicMock(), MagicMock()

        async def __aexit__(self, *args):
            return None

    with patch(
        "mcp.server.stdio.stdio_server",
        return_value=_FakeStdioCtx(),
    ):
        await mcp_transport.run_stdio_server()

    fake_server.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_audit_emit_logs_event_keys() -> None:
    """``_mcp_audit_emit`` logs the event_type and the SORTED key list
    only — never the secret values inside the payload."""

    payload = {"updated": True, "key": "telegram_bot_token"}

    captured: list[dict] = []

    def _processor(_logger, _name, event_dict):  # type: ignore[no-untyped-def]
        captured.append(event_dict)
        return event_dict

    structlog.configure(processors=[_processor, structlog.processors.JSONRenderer()])

    try:
        await mcp_transport._mcp_audit_emit("supervisor.settings.updated", payload)
    finally:
        structlog.reset_defaults()

    assert any("event_type" in evt and evt["event_type"] == "supervisor.settings.updated" for evt in captured)
    relevant = next(evt for evt in captured if evt.get("event_type"))
    # The payload must NEVER appear in the log line — only the keys do.
    assert "telegram_bot_token" not in str(relevant)
    assert relevant["payload_keys"] == ["key", "updated"]


@pytest.mark.asyncio
async def test_build_server_opens_session_for_admin_tool_when_factory_provided() -> None:
    """Round 4 Finding 23: build_server must thread the session_factory
    through so ctx.db is populated for admin tools that require AsyncSession.
    Without this thread every admin tool 500'd with 'admin tool requires
    ctx.db (AsyncSession)' even after F16 unblocked the auth path."""
    from contextlib import asynccontextmanager
    from mcp.types import CallToolRequest, CallToolRequestParams
    from bsupervisor.mcp.api import Tool, ToolRegistry
    from pydantic import BaseModel

    class _Args(BaseModel):
        pass

    class _Out(BaseModel):
        db_was_set: bool

    captured: dict[str, object] = {}

    async def _handler(_args: _Args, ctx) -> _Out:  # type: ignore[no-untyped-def]
        captured["db"] = ctx.db
        return _Out(db_was_set=ctx.db is not None)

    reg = ToolRegistry()
    reg.register(
        Tool(
            name="probe",
            description="probe ctx.db",
            input_schema=_Args,
            output_schema=_Out,
            handler=_handler,
            required_scopes=[],
        )
    )

    sentinel = object()

    @asynccontextmanager
    async def fake_factory():
        yield sentinel

    async def ctx_provider():
        # Empty user / audit emit — we only care that session injection works.
        return mcp_transport.ToolContext(
            user=MagicMock(scope=["*"], id="u", email=None, is_service=False),
            audit_emit=AsyncMock(),
        )

    server = mcp_transport.build_server(
        reg,
        context_provider=ctx_provider,
        session_factory=fake_factory,
    )
    handler = server.request_handlers[CallToolRequest]
    req = CallToolRequest(
        method="tools/call",
        params=CallToolRequestParams(name="probe", arguments={}),
    )
    result = await handler(req)
    assert result.root.isError is False
    assert captured["db"] is sentinel
