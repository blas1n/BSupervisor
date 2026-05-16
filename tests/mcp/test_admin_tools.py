"""Tests for the admin MCP tool catalog.

Covers:
- Every CLI sub-app action is registered as a first-class tool with the
  expected name (``bsupervisor_<subapp>_<action>``).
- One ``CallTool`` per sub-app exercises the dispatcher end-to-end against
  a real ``db_session`` (no service-layer mocking — handlers call core
  helpers + ``ctx.db`` directly).
- ``required_permission`` strings on each tool match the REST route the
  CLI hits (Tier 5 ``<product>.<resource>.<action>`` dot strings).
- Mutating tools have ``audit_event`` set; read-only tools do not.

The tests deliberately avoid ``TestClient``/``ASGITransport`` — these are
in-process registry calls, the same in-process pattern the rest of
``tests/mcp/`` uses (memory ``mcp-python-sdk-testing``).

Tier 5 Phase 3a — tool authorization is the tenant-scoped OpenFGA check
(``check_tenant_permission``). The happy-path tests build a context with
OpenFGA unconfigured (``openfga_api_url=""``) so the check is permissive,
matching the test/demo posture; the denied-path test injects a fake FGA
client that returns False.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from bsvibe_authz import Settings, User
from bsvibe_authz.cache import PermissionCache

from bsupervisor.mcp.admin_tools import ADMIN_TOOL_NAMES, build_admin_registry
from bsupervisor.mcp.api import ToolContext, ToolPermissionError
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.incident import Incident, IncidentStatus

_TEST_TENANT = "tenant-test"


class _FakeFGA:
    """OpenFGA stand-in — every ``check`` returns ``allow``; ``write_tuple``
    is a no-op so the dispatcher's lazy role-tuple provisioning never errors."""

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow

    async def check(self, user: str, relation: str, object_: str) -> bool:
        return self.allow

    async def list_objects(self, user: str, relation: str, type_: str) -> list[str]:
        return []

    async def write_tuple(self, user: str, relation: str, object_: str) -> None:
        return None


def _admin_user() -> User:
    """A real (non-service) tenant admin — the steady-state MCP caller.

    ``app_metadata.role`` is set so the dispatcher's lazy role-tuple
    provisioning has something to write; OpenFGA stays unconfigured in
    the happy-path context so the check is permissive regardless.
    """
    return User(
        id="admin-user",
        email="admin@example.com",
        active_tenant_id=_TEST_TENANT,
        app_metadata={"role": "admin"},
        is_service=False,
    )


async def _noop_emit(event: str, payload: dict) -> None:
    return None


def _ctx(
    session,
    user: User | None = None,
    captured: list | None = None,
    *,
    fga: _FakeFGA | None = None,
    openfga_configured: bool = False,
) -> ToolContext:
    audit = _noop_emit
    if captured is not None:

        async def _capture(event: str, payload: dict) -> None:
            captured.append((event, payload))

        audit = _capture

    settings = Settings(
        openfga_api_url="http://openfga.test" if openfga_configured else "",
    )
    return ToolContext(
        user=user or _admin_user(),
        audit_emit=audit,
        db=session,
        fga=fga or _FakeFGA(allow=True),
        cache=PermissionCache(ttl_s=30),
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Catalog presence
# ---------------------------------------------------------------------------


def test_admin_registry_includes_all_expected_tool_names() -> None:
    registry = build_admin_registry()
    names = set(registry.names())

    expected = {
        "bsupervisor_agents_list",
        "bsupervisor_agents_add",
        "bsupervisor_agents_update",
        "bsupervisor_agents_delete",
        "bsupervisor_agents_run",
        "bsupervisor_incidents_list",
        "bsupervisor_incidents_show",
        "bsupervisor_incidents_ack",
        "bsupervisor_incidents_resolve",
        "bsupervisor_audit_list",
        "bsupervisor_audit_show",
        "bsupervisor_costs_report",
        "bsupervisor_settings_get",
        "bsupervisor_settings_set",
    }
    assert expected.issubset(names)
    assert set(ADMIN_TOOL_NAMES) == expected


def test_every_admin_tool_has_input_and_output_schema() -> None:
    registry = build_admin_registry()
    listed = registry.list_tools()

    for tool in listed:
        # Both schemas come from Pydantic models (no auto-derivation), so
        # the JSON schema is always a non-empty object.
        assert tool.inputSchema, f"{tool.name} missing inputSchema"
        assert tool.outputSchema, f"{tool.name} missing outputSchema"


def test_mutating_tools_have_audit_event_and_write_permission() -> None:
    registry = build_admin_registry()

    mutating = {
        "bsupervisor_agents_add": "bsupervisor.agents.write",
        "bsupervisor_agents_update": "bsupervisor.agents.write",
        "bsupervisor_agents_delete": "bsupervisor.agents.write",
        "bsupervisor_agents_run": "bsupervisor.agents.write",
        "bsupervisor_incidents_ack": "bsupervisor.incidents.write",
        "bsupervisor_incidents_resolve": "bsupervisor.incidents.write",
        # Tier 5: the old ``bsupervisor:*`` super-scope is retired —
        # settings_set maps to the matrix-valid ``settings.write``.
        "bsupervisor_settings_set": "bsupervisor.settings.write",
    }
    for name, expected_permission in mutating.items():
        tool = registry.get(name)
        assert tool.audit_event, f"{name} should have audit_event set"
        assert tool.required_permission == expected_permission, (
            f"{name} expected {expected_permission}, got {tool.required_permission}"
        )


def test_read_only_tools_have_no_audit_event() -> None:
    registry = build_admin_registry()
    read_only = {
        "bsupervisor_agents_list",
        "bsupervisor_incidents_list",
        "bsupervisor_incidents_show",
        "bsupervisor_audit_list",
        "bsupervisor_audit_show",
        "bsupervisor_costs_report",
        "bsupervisor_settings_get",
    }
    for name in read_only:
        tool = registry.get(name)
        assert tool.audit_event is None, f"{name} should not emit audit events"


def test_every_tool_permission_is_a_matrix_row() -> None:
    """Tier 5 — every tool's ``required_permission`` is a
    ``<product>.<resource>.<action>`` dot string drawn from the
    bsvibe-authz permission matrix (no wildcard, no colon grammar)."""
    registry = build_admin_registry()

    # The matrix rows under ``bsupervisor:`` — agents.read/write,
    # incidents.read/write, audit.read, settings.read/write.
    valid = {
        "bsupervisor.agents.read",
        "bsupervisor.agents.write",
        "bsupervisor.incidents.read",
        "bsupervisor.incidents.write",
        "bsupervisor.audit.read",
        "bsupervisor.settings.read",
        "bsupervisor.settings.write",
    }
    for name in ADMIN_TOOL_NAMES:
        tool = registry.get(name)
        assert tool.required_permission is not None, f"{name} has no required_permission"
        assert "*" not in tool.required_permission, f"{name} keeps a wildcard"
        assert ":" not in tool.required_permission, f"{name} keeps colon grammar"
        assert tool.required_permission in valid, f"{name} permission {tool.required_permission} is not a matrix row"


# ---------------------------------------------------------------------------
# Per-sub-app CallTool — one happy path per sub-app
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_list_returns_existing_rules(db_session) -> None:
    rule = AuditRule(
        name="rule-alpha",
        description="alpha",
        condition={"type": "pattern", "pattern": "secret", "severity": "high"},
        action="block",
        enabled=True,
        tenant_id=_TEST_TENANT,
    )
    db_session.add(rule)
    await db_session.commit()

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_list",
        {},
        _ctx(db_session),
    )

    assert isinstance(out["rules"], list)
    assert any(r["name"] == "rule-alpha" and r["action"] == "block" for r in out["rules"])


@pytest.mark.asyncio
async def test_incidents_list_returns_open_incidents(db_session) -> None:
    incident = Incident(
        agent_id="agent-1",
        title="Suspicious activity",
        status=IncidentStatus.OPEN,
        severity="high",
        event_count=1,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tenant_id=_TEST_TENANT,
    )
    db_session.add(incident)
    await db_session.commit()

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_incidents_list",
        {},
        _ctx(db_session),
    )

    assert isinstance(out["incidents"], list)
    assert any(i["title"] == "Suspicious activity" for i in out["incidents"])


@pytest.mark.asyncio
async def test_audit_list_returns_recent_events(db_session) -> None:
    event = AuditEvent(
        agent_id="agent-1",
        source="cli",
        event_type="prompt_send",
        action="send",
        target="https://example.com",
        allowed=True,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tenant_id=_TEST_TENANT,
    )
    db_session.add(event)
    await db_session.commit()

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_audit_list",
        {},
        _ctx(db_session),
    )

    assert isinstance(out["events"], list)
    assert any(e["agent_id"] == "agent-1" for e in out["events"])


@pytest.mark.asyncio
async def test_costs_report_returns_budget_envelope(db_session) -> None:
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_costs_report",
        {},
        _ctx(db_session),
    )

    # Empty DB → zero spent, but the trend window is densified to 30 days.
    assert "budget" in out
    assert "spent" in out
    assert "trend" in out
    assert len(out["trend"]) == 30


@pytest.mark.asyncio
async def test_settings_set_updates_value_and_emits_audit(db_session) -> None:
    captured: list = []
    registry = build_admin_registry()

    out = await registry.call_tool(
        "bsupervisor_settings_set",
        {"key": "slack_webhook_url", "value": "https://hooks.example.com/abc"},
        _ctx(db_session, captured=captured),
    )

    assert out["updated"] is True
    assert out["key"] == "slack_webhook_url"
    assert len(captured) == 1
    audit_event, audit_payload = captured[0]
    assert audit_event == "supervisor.settings.updated"
    # Audit payload MUST NOT include the raw secret value.
    assert "value" not in audit_payload
    assert audit_payload["key"] == "slack_webhook_url"


# ---------------------------------------------------------------------------
# Permission enforcement on admin tools — REST equivalence (Tier 5 OpenFGA)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_add_denied_when_openfga_denies(db_session) -> None:
    """With OpenFGA configured and the FGA client returning False, the
    write tool 403s before the handler runs — REST ``require_permission``
    equivalence for the MCP surface."""
    registry = build_admin_registry()

    with pytest.raises(ToolPermissionError):
        await registry.call_tool(
            "bsupervisor_agents_add",
            {"name": "x", "action": "block"},
            _ctx(db_session, fga=_FakeFGA(allow=False), openfga_configured=True),
        )


@pytest.mark.asyncio
async def test_agents_add_allowed_when_openfga_grants(db_session) -> None:
    """With OpenFGA configured and the FGA client returning True, the
    write tool dispatches normally."""
    registry = build_admin_registry()

    out = await registry.call_tool(
        "bsupervisor_agents_add",
        {"name": "rule-fga-allow", "action": "block"},
        _ctx(db_session, fga=_FakeFGA(allow=True), openfga_configured=True),
    )

    assert out["name"] == "rule-fga-allow"


# ---------------------------------------------------------------------------
# Agents — full CRUD coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_add_creates_rule_and_emits_audit(db_session) -> None:
    captured: list = []
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_add",
        {"name": "rule-new", "action": "warn", "pattern": "p", "severity": "low"},
        _ctx(db_session, captured=captured),
    )
    assert out["name"] == "rule-new"
    assert out["action"] == "warn"
    assert captured and captured[0][0] == "supervisor.rule.created"


@pytest.mark.asyncio
async def test_agents_add_duplicate_raises_conflict(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolConflictError

    registry = build_admin_registry()
    args = {"name": "dup", "action": "block"}
    await registry.call_tool("bsupervisor_agents_add", args, _ctx(db_session))
    with pytest.raises(AdminToolConflictError):
        await registry.call_tool("bsupervisor_agents_add", args, _ctx(db_session))


@pytest.mark.asyncio
async def test_agents_update_patches_fields(db_session) -> None:
    rule = AuditRule(
        name="upd-1",
        description="d",
        condition={"type": "pattern", "pattern": "p", "severity": "low"},
        action="log",
        enabled=True,
        tenant_id=_TEST_TENANT,
    )
    db_session.add(rule)
    await db_session.commit()

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_update",
        {"rule_id": str(rule.id), "action": "block", "enabled": False, "pattern": "p2", "description": "new"},
        _ctx(db_session),
    )
    assert out["action"] == "block"
    assert out["enabled"] is False
    assert out["pattern"] == "p2"
    assert out["description"] == "new"


@pytest.mark.asyncio
async def test_agents_update_unknown_id_raises_not_found(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_agents_update",
            {"rule_id": "not-a-uuid", "action": "block"},
            _ctx(db_session),
        )


@pytest.mark.asyncio
async def test_agents_delete_removes_rule(db_session) -> None:
    rule = AuditRule(
        name="del-1",
        description="d",
        condition={"type": "pattern", "pattern": "p", "severity": "low"},
        action="log",
        enabled=True,
        tenant_id=_TEST_TENANT,
    )
    db_session.add(rule)
    await db_session.commit()
    rule_id = str(rule.id)

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_delete",
        {"rule_id": rule_id},
        _ctx(db_session),
    )
    assert out["deleted"] is True
    assert out["id"] == rule_id


@pytest.mark.asyncio
async def test_agents_delete_if_exists_swallows_missing(db_session) -> None:
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_delete",
        {"rule_id": "00000000-0000-0000-0000-000000000000", "if_exists": True},
        _ctx(db_session),
    )
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


@pytest.mark.asyncio
async def test_agents_delete_if_exists_swallows_bad_uuid(db_session) -> None:
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_delete",
        {"rule_id": "not-a-uuid", "if_exists": True},
        _ctx(db_session),
    )
    assert out["deleted"] is False
    assert out["reason"] == "not_found"


@pytest.mark.asyncio
async def test_agents_delete_built_in_forbidden(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolForbiddenError

    rule = AuditRule(
        name="builtin-1",
        description="d",
        condition={"type": "pattern", "pattern": "p", "severity": "low"},
        action="log",
        enabled=True,
        built_in=True,
        tenant_id=None,
    )
    db_session.add(rule)
    await db_session.commit()

    registry = build_admin_registry()
    with pytest.raises(AdminToolForbiddenError):
        await registry.call_tool(
            "bsupervisor_agents_delete",
            {"rule_id": str(rule.id)},
            _ctx(db_session),
        )


@pytest.mark.asyncio
async def test_agents_run_evaluates_synthetic_event(db_session) -> None:
    captured: list = []
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_agents_run",
        {
            "agent_id": "agent-syn",
            "source": "cli",
            "event_type": "prompt_send",
            "action": "send",
            "target": "https://example.com",
        },
        _ctx(db_session, captured=captured),
    )
    assert isinstance(out["event_id"], str)
    assert isinstance(out["allowed"], bool)
    assert captured and captured[0][0] == "supervisor.event.evaluated"


@pytest.mark.asyncio
async def test_agents_run_requires_active_tenant(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolForbiddenError

    # OpenFGA stays unconfigured in ``_ctx`` → check_tenant_permission is
    # permissive even without a tenant, so the handler runs and it is the
    # handler's own tenant guard that raises here.
    user = User(id="no-tenant", email="x@y", is_service=False)
    registry = build_admin_registry()
    with pytest.raises(AdminToolForbiddenError):
        await registry.call_tool(
            "bsupervisor_agents_run",
            {
                "agent_id": "a",
                "source": "cli",
                "event_type": "e",
                "action": "x",
                "target": "t",
            },
            _ctx(db_session, user=user),
        )


# ---------------------------------------------------------------------------
# Incidents — show / ack / resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_incidents_show_returns_detail_with_timeline(db_session) -> None:
    incident = Incident(
        agent_id="a",
        title="t",
        status=IncidentStatus.OPEN,
        severity="high",
        event_count=1,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tenant_id=_TEST_TENANT,
    )
    db_session.add(incident)
    await db_session.commit()
    incident_id = str(incident.id)

    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_incidents_show",
        {"incident_id": incident_id},
        _ctx(db_session),
    )
    assert out["id"] == incident_id
    assert isinstance(out["timeline"], list)


@pytest.mark.asyncio
async def test_incidents_show_unknown_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_incidents_show",
            {"incident_id": "00000000-0000-0000-0000-000000000000"},
            _ctx(db_session),
        )


@pytest.mark.asyncio
async def test_incidents_show_bad_uuid_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_incidents_show",
            {"incident_id": "not-a-uuid"},
            _ctx(db_session),
        )


@pytest.mark.asyncio
async def test_incidents_ack_and_resolve_transitions(db_session) -> None:
    incident = Incident(
        agent_id="a",
        title="t",
        status=IncidentStatus.OPEN,
        severity="high",
        event_count=1,
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        tenant_id=_TEST_TENANT,
    )
    db_session.add(incident)
    await db_session.commit()
    incident_id = str(incident.id)

    registry = build_admin_registry()

    captured: list = []
    out = await registry.call_tool(
        "bsupervisor_incidents_ack",
        {"incident_id": incident_id},
        _ctx(db_session, captured=captured),
    )
    assert out["status"] == IncidentStatus.ACKNOWLEDGED.value
    assert captured and captured[0][0] == "supervisor.incident.acknowledged"

    captured.clear()
    out = await registry.call_tool(
        "bsupervisor_incidents_resolve",
        {"incident_id": incident_id},
        _ctx(db_session, captured=captured),
    )
    assert out["status"] == IncidentStatus.RESOLVED.value
    assert captured and captured[0][0] == "supervisor.incident.resolved"


@pytest.mark.asyncio
async def test_incidents_ack_unknown_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_incidents_ack",
            {"incident_id": "not-a-uuid"},
            _ctx(db_session),
        )
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_incidents_ack",
            {"incident_id": "00000000-0000-0000-0000-000000000000"},
            _ctx(db_session),
        )


# ---------------------------------------------------------------------------
# Audit show
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_show_returns_daily_report(db_session) -> None:
    registry = build_admin_registry()
    out = await registry.call_tool(
        "bsupervisor_audit_show",
        {"date": "2026-01-01"},
        _ctx(db_session),
    )
    assert out["date"] == "2026-01-01"
    assert isinstance(out["report_json"], dict)
    assert isinstance(out["markdown"], str)


@pytest.mark.asyncio
async def test_audit_show_invalid_date_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_audit_show",
            {"date": "not-a-date"},
            _ctx(db_session),
        )


# ---------------------------------------------------------------------------
# Settings get — full settings + drill into a key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_get_full_and_keyed(db_session) -> None:
    # First, set a value so that get-by-key returns it.
    registry = build_admin_registry()
    await registry.call_tool(
        "bsupervisor_settings_set",
        {"key": "telegram_bot_token", "value": "tok-XYZ"},
        _ctx(db_session),
    )

    full = await registry.call_tool(
        "bsupervisor_settings_get",
        {},
        _ctx(db_session),
    )
    assert full["connections"]["telegram_bot_token"] == "tok-XYZ"
    assert full["key"] is None
    assert full["value"] is None

    keyed = await registry.call_tool(
        "bsupervisor_settings_get",
        {"key": "telegram_bot_token"},
        _ctx(db_session),
    )
    assert keyed["key"] == "telegram_bot_token"
    assert keyed["value"] == "tok-XYZ"


@pytest.mark.asyncio
async def test_settings_get_unknown_key_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_settings_get",
            {"key": "not-allowed"},
            _ctx(db_session),
        )


@pytest.mark.asyncio
async def test_settings_set_unknown_key_raises(db_session) -> None:
    from bsupervisor.mcp.admin_tools import AdminToolNotFoundError

    registry = build_admin_registry()
    with pytest.raises(AdminToolNotFoundError):
        await registry.call_tool(
            "bsupervisor_settings_set",
            {"key": "not-allowed", "value": "x"},
            _ctx(db_session),
        )
