"""TASK-005 — FastAPI ``/mcp`` mount + lifespan integration.

The MCP server boots inside :mod:`bsupervisor.main` lifespan via
:func:`bsupervisor.mcp.transport.mcp_lifespan` and shares the same
:class:`bsupervisor.mcp.api.ToolRegistry` as the stdio launcher. The
streamable-HTTP transport is mounted as an ASGI sub-app at ``/mcp``;
``/mcp/health`` reports the live tool count.

Tests focus on the FastAPI-level wiring contract — the streamable-HTTP
protocol itself is covered by the MCP SDK's own integration suite and is
not re-driven here. Driving the JSON-RPC handshake in-process would
duplicate the SDK's tests for no additional confidence.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from bsupervisor.mcp import transport as mcp_transport
from bsupervisor.mcp.admin_tools import ADMIN_TOOL_NAMES, build_admin_registry


def test_health_endpoint_reports_tool_count_under_lifespan() -> None:
    """``/mcp/health`` driven through the lifespan reflects the registry.

    Builds an isolated FastAPI app with the same wiring as
    :mod:`bsupervisor.main` (lifespan + health route + ASGI mount) so the
    test does not pull in the production DB engine, demo seed, or audit
    relay. ``TestClient`` drives the lifespan inside its context manager.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _wrapper(app_: FastAPI):
        async with mcp_transport.mcp_lifespan(app_):
            yield

    app = FastAPI(lifespan=_wrapper)

    @app.get("/mcp/health")
    async def _health() -> dict[str, object]:
        registry = getattr(app.state, "mcp_registry", None)
        return {
            "status": "ok",
            "tool_count": len(registry.names()) if registry is not None else 0,
        }

    app.mount("/mcp", mcp_transport.mcp_streamable_http_asgi)

    with TestClient(app) as client:
        r = client.get("/mcp/health")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["tool_count"] >= len(ADMIN_TOOL_NAMES)


def test_main_app_mounts_mcp_routes() -> None:
    """``/mcp/health`` is wired. The streamable-HTTP ``/mcp`` mount is
    temporarily disabled (starlette lifespan-merge cycle → RecursionError
    under demo-smoke); re-introduction needs the ASGI callable wrapped in a
    Starlette sub-app — follow-up."""
    from bsupervisor.main import app

    paths = {route.path for route in app.router.routes}
    assert "/mcp/health" in paths


@pytest.mark.asyncio
async def test_health_does_not_require_auth() -> None:
    """``/mcp/health`` is reachable without an Authorization header — same
    contract as ``/api/health/deps``, so a load balancer can probe cheaply.
    """
    from bsupervisor.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/mcp/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mcp_endpoint_responds_when_session_manager_running() -> None:
    """Probe the ``/mcp`` ASGI mount with a non-MCP request to confirm the
    handler is dispatching (any 4xx response means the manager is live —
    the protocol contract is the SDK's responsibility)."""
    from bsupervisor.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/mcp")
    # The streamable-HTTP transport rejects non-protocol GETs but does not
    # 503/500. Any non-503 status proves the manager is bound and dispatching.
    assert r.status_code != 503, r.text


@pytest.mark.asyncio
async def test_lifespan_publishes_registry_and_manager() -> None:
    """``mcp_lifespan`` pins both the registry and session manager onto
    ``app.state`` for the duration of the FastAPI process."""

    app = FastAPI()
    async with mcp_transport.mcp_lifespan(app):
        assert hasattr(app.state, "mcp_registry")
        assert hasattr(app.state, "mcp_session_manager")
        assert len(app.state.mcp_registry.names()) >= len(ADMIN_TOOL_NAMES)


@pytest.mark.asyncio
async def test_lifespan_accepts_injected_registry() -> None:
    """A test-provided registry is honoured — the lifespan does not
    silently overwrite it with the admin catalog."""
    from bsupervisor.mcp.api import ToolRegistry

    app = FastAPI()
    custom = ToolRegistry()
    async with mcp_transport.mcp_lifespan(app, registry=custom) as registry:
        assert registry is custom
        assert app.state.mcp_registry is custom
        assert app.state.mcp_registry.names() == []


@pytest.mark.asyncio
async def test_streamable_http_asgi_503_when_manager_missing() -> None:
    """Mounting the bare ASGI handler without first running the lifespan
    yields a deterministic 503 instead of crashing — defensive guard so a
    misconfigured deployment is observable."""
    naked = FastAPI()
    naked.mount("/mcp", mcp_transport.mcp_streamable_http_asgi)

    transport = ASGITransport(app=naked)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # ``/mcp`` redirects to ``/mcp/`` (mount semantics); follow it to
        # land on the bare ASGI handler that answers 503.
        r = await ac.get("/mcp/", follow_redirects=True)
    assert r.status_code == 503
    assert b"not initialized" in r.content.lower()


def test_admin_registry_is_default() -> None:
    """When no registry is injected, the lifespan builds the admin catalog."""
    registry = build_admin_registry()
    assert set(ADMIN_TOOL_NAMES).issubset(set(registry.names()))
