"""Coverage tests for :mod:`bsupervisor.mcp.transport` internals.

The end-to-end behaviour is covered by ``tests/mcp/test_http_mount.py``.
Here we drive the leaf helpers (context provider, stdio logging
configurator, ASGI lifespan branch, stdio runner) directly so the module
clears the 80% gate even when the streamable-HTTP transport is not driven.
"""

from __future__ import annotations

import hashlib
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

    raw = "bsv_admin_xyz"
    monkeypatch.setenv("BOOTSTRAP_TOKEN_HASH", hashlib.sha256(raw.encode()).hexdigest())

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


@pytest.mark.asyncio
async def test_streamable_http_asgi_handles_lifespan_scope() -> None:
    """The bare ASGI mount completes a lifespan startup/shutdown cycle even
    when the parent app never bound a session manager."""

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

    await mcp_transport.mcp_streamable_http_asgi({"type": "lifespan"}, _receive, _send)

    types = [m["type"] for m in received]
    assert types == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


@pytest.mark.asyncio
async def test_streamable_http_asgi_delegates_to_session_manager() -> None:
    """When ``app.state.mcp_session_manager`` is bound, the ASGI handler
    forwards directly. The Authorization header is captured into the
    ContextVar for the duration of ``handle_request``."""

    captured_auth: dict[str, str | None] = {}
    fake_app = MagicMock()
    fake_app.state.mcp_session_manager = MagicMock()

    async def _fake_handle(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        captured_auth["seen"] = mcp_transport._current_authorization.get()

    fake_app.state.mcp_session_manager.handle_request = _fake_handle

    async def _receive() -> dict:
        return {}

    async def _send(message: dict) -> None:
        return None

    scope = {
        "type": "http",
        "app": fake_app,
        "headers": [(b"authorization", b"Bearer bsv_admin_token")],
    }
    await mcp_transport.mcp_streamable_http_asgi(scope, _receive, _send)
    assert captured_auth["seen"] == "Bearer bsv_admin_token"
    # ContextVar must reset after the request to avoid bleeding across calls.
    assert mcp_transport._current_authorization.get() is None


@pytest.mark.asyncio
async def test_run_stdio_server_drives_sdk_stdio_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_stdio_server`` resolves auth, builds the server, and hands
    off to the SDK's ``stdio_server`` context manager. We patch every
    external dep so the test never touches real stdio or the env."""

    monkeypatch.setenv("BSV_BOOTSTRAP_TOKEN", "bsv_admin_xyz")

    async def _fake_resolve(*, authorization, **_):  # type: ignore[no-untyped-def]
        assert authorization == "Bearer bsv_admin_xyz"
        return MagicMock(scope=["*"])

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
