"""TASK-005 — ``bsupervisor mcp`` Typer sub-app.

``bsupervisor mcp serve`` boots the MCP server (stdio by default) using the
SAME :class:`bsupervisor.mcp.api.ToolRegistry` the FastAPI app mounts at
``/mcp``. ``bsupervisor mcp list-tools`` prints the catalog so an operator
can confirm what surface a given build exposes without starting a server.

ANSI escape stripping is required for help-text assertions — rich/Typer
splits flag tokens across color escapes in CI (non-TTY). Phase 3 PR #43.
"""

from __future__ import annotations

import json
import re
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_mcp_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    for sub in ("serve", "list-tools"):
        assert sub in out, f"missing sub-command {sub!r} in mcp --help:\n{out}"


def test_mcp_list_tools_prints_admin_catalog(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app
    from bsupervisor.mcp.admin_tools import ADMIN_TOOL_NAMES

    result = runner.invoke(app, ["-o", "json", "mcp", "list-tools"])
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    names = [t["name"] for t in payload]
    for expected in ADMIN_TOOL_NAMES:
        assert expected in names, f"missing tool {expected!r} in list-tools output"
    # Each entry surfaces the permission + audit_event so operators can audit.
    sample = next(t for t in payload if t["name"] == "bsupervisor_agents_add")
    assert sample["required_permission"] == "bsupervisor.agents.write"
    assert sample["audit_event"] == "supervisor.rule.created"


def test_mcp_serve_dry_run_skips_runtime(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--dry-run`` must short-circuit BEFORE booting any transport."""
    import bsupervisor.cli.commands.mcp as mod

    called: list[str] = []

    def _boom(*_args, **_kwargs) -> None:
        called.append("ran")

    monkeypatch.setattr(mod, "_run_stdio", _boom)

    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["--dry-run", "-o", "json", "mcp", "serve"])
    assert result.exit_code == 0, result.stderr
    assert called == [], "dry-run must not boot stdio transport"

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["transport"] == "stdio"


def test_mcp_serve_invokes_stdio_runner(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """``mcp serve --transport stdio`` (default) calls
    :func:`bsupervisor.mcp.stdio.run_stdio_server` exactly once."""
    import bsupervisor.cli.commands.mcp as mod

    fake = MagicMock(name="run_stdio_server")
    monkeypatch.setattr(mod, "_run_stdio", fake)

    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["mcp", "serve"])
    assert result.exit_code == 0, result.stderr
    fake.assert_called_once()


def test_mcp_serve_http_transport_emits_redirect_hint(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--transport http`` is intentionally not implemented inside
    ``bsupervisor mcp serve`` — the FastAPI app already mounts ``/mcp``,
    so the operator should run uvicorn instead. Surface that as an error
    with the recommended command, not a silent no-op."""
    import bsupervisor.cli.commands.mcp as mod

    monkeypatch.setattr(mod, "_run_stdio", MagicMock())

    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["mcp", "serve", "--transport", "http"])
    assert result.exit_code != 0
    err = _strip_ansi(result.stderr or result.output)
    assert "uvicorn" in err.lower()


def test_mcp_serve_unknown_transport_rejected(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["mcp", "serve", "--transport", "carrier-pigeon"])
    assert result.exit_code != 0


def test_mcp_serve_help_lists_transport_flag(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["mcp", "serve", "--help"])
    assert result.exit_code == 0
    out = _strip_ansi(result.stdout)
    assert "--transport" in out
