"""TASK-004 — ``bsupervisor agents`` and ``bsupervisor incidents`` CLI sub-apps.

Each sub-app is exercised through :class:`typer.testing.CliRunner` with
``build_client`` monkey-patched per module to a ``MagicMock``. The tests
focus on:

* sub-app wiring (subcommands registered + reachable),
* request shape (path / body / params on the mocked client),
* output shape (``--output json`` round-trips),
* ``--dry-run`` truly skipping HTTP,
* friendly error surface on 4xx (no stack trace, exit code != 0).

ANSI escape stripping is REQUIRED for help-text assertions because rich/Typer
splits flag tokens across color escapes in CI (non-TTY) — see Phase 3 PR #43.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from typer.testing import CliRunner

RULE_ID = "22222222-2222-2222-2222-222222222222"
INCIDENT_ID = "33333333-3333-3333-3333-333333333333"


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
# agents sub-app
# ---------------------------------------------------------------------------


def test_agents_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["agents", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    for sub in ("list", "add", "update", "delete", "run"):
        assert sub in out, f"missing sub-command {sub!r} in agents --help:\n{out}"


def test_agents_list_calls_rules_endpoint(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.get.return_value = _resp(200, [{"id": RULE_ID, "name": "r1", "action": "block"}])
    result = runner.invoke(app, _base("agents", "list"))
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once_with("/api/rules")
    assert json.loads(result.stdout)[0]["id"] == RULE_ID


def test_agents_list_dry_run_skips_http(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    result = runner.invoke(app, ["--url", "http://sup.test", "--dry-run", "-o", "json", "agents", "list"])
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/rules"


def test_agents_list_table_output_does_not_crash_on_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.get.return_value = _resp(200, [])
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--token", "tok", "-o", "table", "agents", "list"],
    )
    assert result.exit_code == 0, result.stderr


def test_agents_add_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    result = runner.invoke(
        app,
        [
            "--url",
            "http://sup.test",
            "--dry-run",
            "-o",
            "json",
            "agents",
            "add",
            "--name",
            "no-secrets",
            "--type",
            "pattern",
            "--pattern",
            ".env",
            "--severity",
            "critical",
            "--action",
            "block",
            "--description",
            "deny .env",
        ],
    )
    assert result.exit_code == 0, result.stderr
    fake.post.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/rules"
    body = payload["body"]
    assert body == {
        "name": "no-secrets",
        "type": "pattern",
        "pattern": ".env",
        "severity": "critical",
        "action": "block",
        "description": "deny .env",
        "enabled": True,
    }


def test_agents_add_posts_request(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(201, {"id": RULE_ID, "name": "r1"})
    result = runner.invoke(
        app,
        _base(
            "agents",
            "add",
            "--name",
            "r1",
            "--pattern",
            "secret",
            "--action",
            "warn",
        ),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.post.await_args
    assert args[0] == "/api/rules"
    body = kwargs["json"]
    assert body["name"] == "r1"
    assert body["pattern"] == "secret"
    assert body["action"] == "warn"
    assert json.loads(result.stdout)["id"] == RULE_ID


def test_agents_add_403_friendly_no_traceback(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(403, {"detail": "scope missing: supervisor:agents:write"})
    result = runner.invoke(
        app,
        _base("agents", "add", "--name", "r1", "--action", "block"),
    )
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "scope missing" in combined
    assert "Traceback" not in combined


def test_agents_update_only_sends_provided_fields(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "agents", "update", RULE_ID, "--enabled"],
    )
    assert result.exit_code == 0, result.stderr
    fake.request.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "PUT"
    assert payload["path"] == f"/api/rules/{RULE_ID}"
    assert payload["body"] == {"enabled": True}


def test_agents_update_requires_at_least_one_field(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    _fake(monkeypatch, "agents")
    result = runner.invoke(app, _base("agents", "update", RULE_ID))
    assert result.exit_code != 0
    assert "at least one" in (result.stdout + result.stderr).lower()


def test_agents_delete(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.delete.return_value = _resp(204, None)
    result = runner.invoke(app, _base("agents", "delete", RULE_ID))
    assert result.exit_code == 0, result.stderr
    fake.delete.assert_awaited_once_with(f"/api/rules/{RULE_ID}")
    assert json.loads(result.stdout) == {"deleted": True, "id": RULE_ID}


def test_agents_delete_if_exists_swallows_404(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.delete.return_value = _resp(404, {"detail": "Rule not found"})
    result = runner.invoke(app, _base("agents", "delete", RULE_ID, "--if-exists"))
    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {"deleted": False, "id": RULE_ID, "reason": "not_found"}


def test_agents_run_posts_event(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(
        201,
        {"event_id": "ev-1", "allowed": False, "reason": "blocked"},
    )
    result = runner.invoke(
        app,
        _base(
            "agents",
            "run",
            "--agent-id",
            "agent-1",
            "--source",
            "cli",
            "--event-type",
            "file_delete",
            "--action",
            "delete",
            "--target",
            "/app/.env",
        ),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.post.await_args
    assert args[0] == "/api/events"
    body = kwargs["json"]
    assert body["agent_id"] == "agent-1"
    assert body["source"] == "cli"
    assert body["target"] == "/app/.env"
    assert json.loads(result.stdout)["allowed"] is False


def test_agents_list_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.get.return_value = _resp(403, {"detail": "scope missing: supervisor:agents:read"})
    result = runner.invoke(app, _base("agents", "list"))
    assert result.exit_code != 0
    assert "scope missing" in (result.stdout + result.stderr)


def test_agents_update_calls_put(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.request.return_value = _resp(200, {"id": RULE_ID, "name": "renamed"})
    result = runner.invoke(
        app,
        _base(
            "agents",
            "update",
            RULE_ID,
            "--name",
            "renamed",
            "--type",
            "regex",
            "--pattern",
            ".*\\.env",
            "--severity",
            "high",
            "--action",
            "block",
            "--description",
            "updated desc",
            "--disabled",
        ),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.request.await_args
    assert args == ("PUT", f"/api/rules/{RULE_ID}")
    body = kwargs["json"]
    assert body == {
        "name": "renamed",
        "type": "regex",
        "pattern": ".*\\.env",
        "severity": "high",
        "action": "block",
        "description": "updated desc",
        "enabled": False,
    }


def test_agents_update_server_404(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.request.return_value = _resp(404, {"detail": "Rule not found"})
    result = runner.invoke(app, _base("agents", "update", RULE_ID, "--name", "x"))
    assert result.exit_code != 0
    assert "Rule not found" in (result.stdout + result.stderr)


def test_agents_delete_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "agents", "delete", RULE_ID],
    )
    assert result.exit_code == 0, result.stderr
    fake.delete.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "DELETE"
    assert payload["path"] == f"/api/rules/{RULE_ID}"


def test_agents_delete_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.delete.return_value = _resp(403, {"detail": "scope missing: supervisor:agents:write"})
    result = runner.invoke(app, _base("agents", "delete", RULE_ID))
    assert result.exit_code != 0
    assert "scope missing" in (result.stdout + result.stderr)


def test_agents_run_401_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(401, {"detail": "service token required for /api/events"})
    result = runner.invoke(
        app,
        _base(
            "agents",
            "run",
            "--agent-id",
            "agent-1",
            "--source",
            "cli",
            "--event-type",
            "x",
            "--action",
            "x",
            "--target",
            "x",
        ),
    )
    assert result.exit_code != 0
    assert "service token required" in (result.stdout + result.stderr)


def test_agents_run_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    result = runner.invoke(
        app,
        [
            "--url",
            "http://sup.test",
            "--dry-run",
            "-o",
            "json",
            "agents",
            "run",
            "--agent-id",
            "agent-1",
            "--source",
            "cli",
            "--event-type",
            "file_read",
            "--action",
            "read",
            "--target",
            "/tmp/x",
        ],
    )
    assert result.exit_code == 0, result.stderr
    fake.post.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/events"


# ---------------------------------------------------------------------------
# incidents sub-app
# ---------------------------------------------------------------------------


def test_incidents_subapp_help(runner: CliRunner) -> None:
    from bsupervisor.cli.main import app

    result = runner.invoke(app, ["incidents", "--help"])
    assert result.exit_code == 0, result.stderr
    out = _strip_ansi(result.stdout)
    for sub in ("list", "show", "ack", "resolve"):
        assert sub in out


def test_incidents_list(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(
        200,
        [
            {
                "id": INCIDENT_ID,
                "agent_id": "a",
                "title": "t",
                "status": "open",
                "severity": "critical",
                "event_count": 1,
                "started_at": "2026-05-08T00:00:00+00:00",
                "updated_at": "2026-05-08T00:00:00+00:00",
            }
        ],
    )
    result = runner.invoke(app, _base("incidents", "list"))
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once()
    args, kwargs = fake.get.await_args
    assert args[0] == "/api/incidents"
    # No filter params when both flags are unset.
    assert kwargs.get("params") in (None, {})
    assert json.loads(result.stdout)[0]["id"] == INCIDENT_ID


def test_incidents_list_with_filters(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(200, [])
    result = runner.invoke(
        app,
        _base(
            "incidents",
            "list",
            "--severity",
            "critical",
            "--since",
            "2026-05-01T00:00:00+00:00",
        ),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = fake.get.await_args
    assert args[0] == "/api/incidents"
    assert kwargs["params"]["severity"] == "critical"
    assert kwargs["params"]["since"] == "2026-05-01T00:00:00+00:00"


def test_incidents_list_table_output_empty(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(200, [])
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--token", "tok", "-o", "table", "incidents", "list"],
    )
    assert result.exit_code == 0, result.stderr


def test_incidents_show(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(
        200,
        {
            "id": INCIDENT_ID,
            "agent_id": "a",
            "title": "t",
            "status": "open",
            "severity": "high",
            "event_count": 2,
            "started_at": "2026-05-08T00:00:00+00:00",
            "updated_at": "2026-05-08T00:00:00+00:00",
            "timeline": [],
        },
    )
    result = runner.invoke(app, _base("incidents", "show", INCIDENT_ID))
    assert result.exit_code == 0, result.stderr
    fake.get.assert_awaited_once_with(f"/api/incidents/{INCIDENT_ID}")
    assert json.loads(result.stdout)["id"] == INCIDENT_ID


def test_incidents_ack(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.post.return_value = _resp(200, {"id": INCIDENT_ID, "status": "acknowledged"})
    result = runner.invoke(app, _base("incidents", "ack", INCIDENT_ID))
    assert result.exit_code == 0, result.stderr
    fake.post.assert_awaited_once_with(f"/api/incidents/{INCIDENT_ID}/ack")
    assert json.loads(result.stdout)["status"] == "acknowledged"


def test_incidents_resolve(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.post.return_value = _resp(200, {"id": INCIDENT_ID, "status": "resolved"})
    result = runner.invoke(app, _base("incidents", "resolve", INCIDENT_ID))
    assert result.exit_code == 0, result.stderr
    fake.post.assert_awaited_once_with(f"/api/incidents/{INCIDENT_ID}/resolve")
    assert json.loads(result.stdout)["status"] == "resolved"


def test_incidents_resolve_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "incidents", "resolve", INCIDENT_ID],
    )
    assert result.exit_code == 0, result.stderr
    fake.post.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "POST"
    assert payload["path"] == f"/api/incidents/{INCIDENT_ID}/resolve"


def test_incidents_list_dry_run_with_filters(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    result = runner.invoke(
        app,
        [
            "--url",
            "http://sup.test",
            "--dry-run",
            "-o",
            "json",
            "incidents",
            "list",
            "--severity",
            "high",
            "--since",
            "2026-05-01T00:00:00+00:00",
        ],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["params"]["severity"] == "high"
    assert payload["params"]["since"] == "2026-05-01T00:00:00+00:00"


def test_incidents_list_403_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(403, {"detail": "scope missing: supervisor:incidents:read"})
    result = runner.invoke(app, _base("incidents", "list"))
    assert result.exit_code != 0
    assert "scope missing" in (result.stdout + result.stderr)


def test_incidents_show_dry_run(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    result = runner.invoke(
        app,
        ["--url", "http://sup.test", "--dry-run", "-o", "json", "incidents", "show", INCIDENT_ID],
    )
    assert result.exit_code == 0, result.stderr
    fake.get.assert_not_awaited()
    payload = json.loads(result.stdout)
    assert payload["method"] == "GET"
    assert payload["path"] == f"/api/incidents/{INCIDENT_ID}"


def test_incidents_resolve_404_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.post.return_value = _resp(404, {"detail": "Incident not found"})
    result = runner.invoke(app, _base("incidents", "resolve", INCIDENT_ID))
    assert result.exit_code != 0
    assert "Incident not found" in (result.stdout + result.stderr)


def test_incidents_show_404_friendly(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "incidents")
    fake.get.return_value = _resp(404, {"detail": "Incident not found"})
    result = runner.invoke(app, _base("incidents", "show", INCIDENT_ID))
    assert result.exit_code != 0
    combined = result.stdout + result.stderr
    assert "Incident not found" in combined
    assert "Traceback" not in combined


# ---------------------------------------------------------------------------
# agents run — service-token-required surface (Phase 8 dogfood follow-up)
# ---------------------------------------------------------------------------


def _agents_run_args() -> list[str]:
    return _base(
        "agents",
        "run",
        "--agent-id",
        "synthetic-1",
        "--source",
        "cli",
        "--event-type",
        "prompt_send",
        "--action",
        "send",
        "--target",
        "BSV_BOOTSTRAP_TOKEN_HASH=fake",
    )


def test_agents_run_audience_mismatch_surfaces_actionable_message(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 8 dogfood (2026-05-11) caught a stiff JSON 401 with no
    indication that ``/api/events`` is service-only. The CLI now
    surfaces an explanation + dry-run / upstream / PAT options.
    """
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(
        401,
        {"detail": "service JWT verification failed: Audience doesn't match"},
    )
    result = runner.invoke(app, _agents_run_args())
    assert result.exit_code == 1
    combined = result.stdout + result.stderr
    assert "service-to-service endpoint" in combined
    assert "--dry-run" in combined
    assert "Traceback" not in combined


def test_agents_run_403_audience_also_caught(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    # Some deployments may emit 403 instead of 401 for the same
    # mismatch — keep the friendly path symmetric.
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(403, {"detail": "audience mismatch"})
    result = runner.invoke(app, _agents_run_args())
    assert result.exit_code == 1
    assert "service-to-service endpoint" in (result.stdout + result.stderr)


def test_agents_run_other_401_uses_default_handler(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    # An unrelated 401 (e.g. expired PAT) should NOT be miscategorized
    # as the audience-mismatch path.
    from bsupervisor.cli.main import app

    fake = _fake(monkeypatch, "agents")
    fake.post.return_value = _resp(401, {"detail": "opaque token is not active"})
    result = runner.invoke(app, _agents_run_args())
    assert result.exit_code == 1
    combined = result.stdout + result.stderr
    assert "opaque token is not active" in combined
    assert "service-to-service endpoint" not in combined
