"""TASK-003 — bsupervisor CLI skeleton smoke tests.

Mirrors the BSGateway PR #43 pattern (the precedent for Phase 5b CLIs):

* `bsupervisor/cli/main.py::app` is a `typer.Typer` produced by
  `bsvibe_cli_base.cli_app` so it inherits the standard global flag
  set (--profile, --output, --tenant, --token, --url, --dry-run).
* `--help` renders non-empty and exits 0.
* `bsupervisor/cli/_client.py::build_client` returns a configured
  `CliHttpClient` derived from a `CliContext`, with no network call
  on construction.
* `bsupervisor = "bsupervisor.cli.main:app"` is declared in
  `[project.scripts]` so `uv run bsupervisor --help` works.

ANSI escape stripping is REQUIRED for help-text assertions because
rich/Typer splits flag tokens across color escapes in CI (non-TTY) —
see Phase 3 PR #43 lesson.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import typer
from bsvibe_cli_base import CliContext, CliHttpClient, OutputFormatter, ProfileStore
from typer.testing import CliRunner


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_main_app_is_typer_instance() -> None:
    from bsupervisor.cli.main import app

    assert isinstance(app, typer.Typer)
    assert app.info.name == "bsupervisor"


def test_help_renders_with_global_flags() -> None:
    from bsupervisor.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    out = _strip_ansi(result.output)
    for flag in ("--profile", "--output", "--tenant", "--token", "--url", "--dry-run"):
        assert flag in out, f"missing global flag {flag} in --help output:\n{out}"


def test_pyproject_declares_console_script() -> None:
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    parsed = tomllib.loads(pyproject)
    scripts = parsed.get("project", {}).get("scripts", {})
    assert scripts.get("bsupervisor") == "bsupervisor.cli.main:app", (
        f'expected `bsupervisor = "bsupervisor.cli.main:app"` in [project.scripts]; got {scripts!r}'
    )


def test_build_client_returns_configured_cli_http_client(tmp_path: Path) -> None:
    from bsupervisor.cli._client import build_client

    formatter = OutputFormatter(format="json")
    ctx = CliContext(
        profile=None,
        url="https://supervisor.example.test",
        tenant_id="t-123",
        token="bearer-abc",
        dry_run=False,
        formatter=formatter,
        profile_store=ProfileStore(path=tmp_path / "profiles.toml"),
    )
    client = build_client(ctx)
    assert isinstance(client, CliHttpClient)
    assert client._base_url == "https://supervisor.example.test"
    assert client._token == "bearer-abc"
    assert client._headers.get("X-Tenant-ID") == "t-123"


def test_build_client_omits_tenant_header_when_unset(tmp_path: Path) -> None:
    from bsupervisor.cli._client import build_client

    formatter = OutputFormatter(format="json")
    ctx = CliContext(
        profile=None,
        url="https://supervisor.example.test",
        tenant_id=None,
        token="bearer-abc",
        dry_run=False,
        formatter=formatter,
        profile_store=ProfileStore(path=tmp_path / "profiles.toml"),
    )
    client = build_client(ctx)
    assert "X-Tenant-ID" not in client._headers


def test_build_client_rejects_empty_url(tmp_path: Path) -> None:
    from bsupervisor.cli._client import build_client

    formatter = OutputFormatter(format="json")
    ctx = CliContext(
        profile=None,
        url="",
        tenant_id=None,
        token=None,
        dry_run=False,
        formatter=formatter,
        profile_store=ProfileStore(path=tmp_path / "profiles.toml"),
    )
    with pytest.raises(typer.BadParameter):
        build_client(ctx)
