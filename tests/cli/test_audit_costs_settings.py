"""TASK-005 — ``bsupervisor audit / costs / settings`` CLI sub-apps.

Same harness as ``test_agents_incidents.py``: each sub-app is exercised
through :class:`typer.testing.CliRunner` with ``build_client`` patched
per module to a ``MagicMock``. Tests cover wiring, request shape,
``--dry-run`` skipping HTTP, output round-trip, and friendly 4xx.

ANSI escape stripping is required for help-text assertions — rich/Typer
splits flag tokens across color escapes in CI (non-TTY).
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from typer.testing import CliRunner


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _resp(status_code: int = 200, payload: object | None = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status_code
    r.json.return_value = payload
    r.text = json.dumps(payload, default=str) if payload is not None else ""
    return r


def _fake(monkeypatch: pytest.MonkeyPatch, module: str) -> MagicMock:
    client = MagicMock(name=f"CliHttpClient[{module}]")
    client.aclose = AsyncMock(return_value=None)
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.delete = AsyncMock()
    client.request = AsyncMock()
    monkeypatch.setattr(f"bsupervisor.cli.commands.{module}.build_client", lambda ctx: client)
    return client


def _base(*extra: str) -> list[str]:
    args = ["--url", "http://sup.test", "--token", "tok", "-o", "json"]
    args += list(extra)
    return args


# ---------------------------------------------------------------------------
# audit sub-app
# ---------------------------------------------------------------------------


def test_audit_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["audit", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    for sub in ("list", "show"):
        assert sub in out, f"missing sub-command {sub!r} in audit --help:\n{out}"


def test_audit_list_calls_events_endpoint(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    fake.get.return_value = _resp(
        200,
        [
            {
                "id": "ev-1",
                "timestamp": "2026-05-08T00:00:00+00:00",
                "agent_id": "a",
                "action": "read",
                "severity": "safe",
                "rule_name": None,
                "details": "/tmp/x",
                "explanation": None,
            }
        ],
    )
    result = runner.invoke(app, _base("audit", "list"))
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once_with("/api/events")
    assert json.loads(result.stdout)[0]["id"] == "ev-1"


def test_audit_list_dry_run_skips_http(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    result = runner.invoke(app, ["--url", "http://sup.test", "--dry-run", "-o", "json", "audit", "list"])
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/events"


def test_audit_list_table_output_does_not_crash_on_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    fake.get.return_value = _resp(200, [])
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--token", "tok", "-o", "table", "audit", "list"],
    )
    assert result.exit_code == 0, result.stderr


def test_audit_show_calls_daily_report(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    fake.get.return_value = _resp(
        200,
        {
            "report_id": "r-1",
            "date": "2026-05-08",
            "total_events": 12,
            "blocked_count": 1,
            "total_cost_usd": "0.42",
            "report_json": {},
            "markdown": "# Daily Audit",
        },
    )
    result = runner.invoke(app, _base("audit", "show", "2026-05-08"))
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.get.await_args
    assert args[0] == "/api/reports/daily"
    assert kwargs["params"] == {"date": "2026-05-08"}
    assert json.loads(result.stdout)["date"] == "2026-05-08"


def test_audit_show_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "audit", "show", "2026-05-08"],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/reports/daily"
    assert payload["params"] == {"date": "2026-05-08"}


def test_audit_list_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    fake.get.return_value = _resp(403, {"detail": "scope missing: supervisor:audit:read"})
    result = runner.invoke(app, _base("audit", "list"))
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "scope missing" in combined
    assert "Traceback" not in combined


def test_audit_show_404_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "audit")
    fake.get.return_value = _resp(404, {"detail": "Report not found"})
    result = runner.invoke(app, _base("audit", "show", "2026-05-08"))
    assert result.exit_code != 0
    assert "Report not found" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# costs sub-app
# ---------------------------------------------------------------------------


def test_costs_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["costs", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    assert "report" in out


def test_costs_report_calls_costs_endpoint(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "costs")
    fake.get.return_value = _resp(
        200,
        {
            "budget": "$100.00",
            "spent": "$1.23",
            "budget_percentage": 1.2,
            "trend": [],
            "agents": [],
            "anomalies": [],
        },
    )
    result = runner.invoke(app, _base("costs", "report"))
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.get.await_args
    assert args[0] == "/api/costs"
    # No filter params when neither --days nor --by is set.
    assert kwargs.get("params") in (None, {})
    assert json.loads(result.stdout)["budget"] == "$100.00"


def test_costs_report_forwards_days_and_by(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "costs")
    fake.get.return_value = _resp(
        200,
        {
            "budget": "$100.00",
            "spent": "$0.00",
            "budget_percentage": 0.0,
            "trend": [],
            "agents": [],
            "anomalies": [],
        },
    )
    result = runner.invoke(app, _base("costs", "report", "--days", "7", "--by", "model"))
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.get.await_args
    assert args[0] == "/api/costs"
    assert kwargs["params"]["days"] == "7"
    assert kwargs["params"]["by"] == "model"


def test_costs_report_rejects_invalid_by(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    _fake(monkeypatch, "costs")
    result = runner.invoke(app, _base("costs", "report", "--by", "potato"))
    assert result.exit_code != 0
    assert "by" in (result.stdout + result.stderr).lower()


def test_costs_report_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "costs")
    result = runner.invoke(
        app,
        [
            "--url",
            "http://sup.test",
            "--dry-run",
            "-o",
            "json",
            "costs",
            "report",
            "--days",
            "30",
            "--by",
            "tenant",
        ],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/costs"
    assert payload["params"] == {"days": "30", "by": "tenant"}


def test_costs_report_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "costs")
    fake.get.return_value = _resp(403, {"detail": "scope missing: supervisor:audit:read"})
    result = runner.invoke(app, _base("costs", "report"))
    assert result.exit_code != 0
    assert "scope missing" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# settings sub-app
# ---------------------------------------------------------------------------


def test_settings_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["settings", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    for sub in ("get", "set"):
        assert sub in out


def test_settings_get_full_payload(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(
        200,
        {
            "connections": {
                "integrations": [],
                "telegram_bot_token": "",
                "slack_webhook_url": "https://hooks.slack.com/services/X",
            }
        },
    )
    result = runner.invoke(app, _base("settings", "get"))
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once_with("/api/settings")
    payload = json.loads(result.stdout)
    assert payload["connections"]["slack_webhook_url"].endswith("/X")


def test_settings_get_key_drills_in(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(
        200,
        {
            "connections": {
                "integrations": [],
                "telegram_bot_token": "T-123",
                "slack_webhook_url": "",
            }
        },
    )
    result = runner.invoke(app, _base("settings", "get", "telegram_bot_token"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"key": "telegram_bot_token", "value": "T-123"}


def test_settings_get_unknown_key_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(
        200,
        {"connections": {"integrations": [], "telegram_bot_token": "", "slack_webhook_url": ""}},
    )
    result = runner.invoke(app, _base("settings", "get", "nope"))
    assert result.exit_code != 0
    assert "unknown" in (result.stdout + result.stderr).lower()


def test_settings_get_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "settings", "get"],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/settings"


def test_settings_set_round_trip(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(
        200,
        {"connections": {"integrations": [], "telegram_bot_token": "", "slack_webhook_url": ""}},
    )
    fake.request.return_value = _resp(
        200,
        {
            "connections": {
                "integrations": [],
                "telegram_bot_token": "",
                "slack_webhook_url": "https://hooks.slack.com/services/Y",
            }
        },
    )
    result = runner.invoke(
        app,
        _base("settings", "set", "slack_webhook_url", "https://hooks.slack.com/services/Y"),
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once_with("/api/settings")
    args, kwargs = fake.request.await_args
    assert args == ("PUT", "/api/settings")
    body = kwargs["json"]
    assert body["slack_webhook_url"] == "https://hooks.slack.com/services/Y"
    # Round-trip preserves untouched fields.
    assert body["telegram_bot_token"] == ""
    assert body["integrations"] == []


def test_settings_set_unknown_key_rejected(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    _fake(monkeypatch, "settings")
    result = runner.invoke(app, _base("settings", "set", "potato", "x"))
    assert result.exit_code != 0
    combined = (result.stdout + result.stderr).lower()
    assert "unknown" in combined or "supported" in combined


def test_settings_set_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    result = runner.invoke(
        app,
        [
            "--url",
            "http://sup.test",
            "--dry-run",
            "-o",
            "json",
            "settings",
            "set",
            "telegram_bot_token",
            "T-456",
        ],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    fake.request.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "PUT"
    assert payload["path"] == "/api/settings"
    # Dry-run discloses the requested patch but not a fully realised body
    # (because that requires a server round-trip).
    assert payload["patch"] == {"telegram_bot_token": "T-456"}


def test_settings_get_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(403, {"detail": "scope missing: supervisor:*"})
    result = runner.invoke(app, _base("settings", "get"))
    assert result.exit_code != 0
    assert "scope missing" in (result.stdout + result.stderr)


def test_settings_set_get_failure_short_circuits(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the GET round-trip fails, ``set`` reports the error and does NOT PUT."""
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "settings")
    fake.get.return_value = _resp(503, {"detail": "service unavailable"})
    result = runner.invoke(
        app,
        _base("settings", "set", "slack_webhook_url", "https://hooks.slack.com/services/Z"),
    )
    assert result.exit_code != 0
    fake.request.assert_not_awaited()
    assert "service unavailable" in (result.stdout + result.stderr)
