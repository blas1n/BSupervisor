"""Admin MCP tools — first-class definitions for the bsupervisor admin surface.

Each :class:`Tool` mirrors a CLI sub-app command and gates on the same scope
the corresponding REST route enforces. Handlers operate on ``ctx.db`` and
reuse the same core helpers (``RuleEngine``, ``IncidentTracker``, ``Reporter``,
``secret_vault``) that REST handlers use, so behavior stays in lockstep with
the REST surface without a typer auto-adapter.

Audit events fire via the dispatcher's ``audit_event`` hook on the validated
output dict. ``settings_set`` deliberately reports only the patched key (not
the secret value) so audit payloads never carry plaintext credentials.

Naming convention: ``bsupervisor_<subapp>_<action>``.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import structlog
from bsvibe_authz import User
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.schemas import (
    ConnectionSettings,
    CostAgentEntry,
    CostDataResponse,
    EventListItem,
    ExplanationResponse,
    RuleCreateRequest,
    RuleResponse,
)
from bsupervisor.config import settings as app_settings
from bsupervisor.core.dates import day_window
from bsupervisor.core.encryption import EncryptionManager
from bsupervisor.core.incident_tracker import IncidentTracker
from bsupervisor.core.reporter import Reporter
from bsupervisor.core.rule_engine import RuleEngine, invalidate_rules_cache
from bsupervisor.core.secret_vault import decrypt_connections, encrypt_connections
from bsupervisor.mcp.api import Tool, ToolContext, ToolError, ToolRegistry
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.incident import Incident, IncidentStatus
from bsupervisor.models.settings import Settings as SettingsModel

logger = structlog.get_logger(__name__)

CONNECTIONS_KEY = "connections"
_SETTABLE_KEYS = ("slack_webhook_url", "telegram_bot_token")
_TREND_DAYS = 30


# ---------------------------------------------------------------------------
# Errors — translated by the dispatcher to MCP error responses
# ---------------------------------------------------------------------------


class AdminToolNotFoundError(ToolError):
    """A targeted resource (rule / incident / etc.) does not exist."""


class AdminToolConflictError(ToolError):
    """Mutation would violate a uniqueness or state invariant."""


class AdminToolForbiddenError(ToolError):
    """Mutation rejected by domain rules (e.g. built-in rule deletion)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_db(ctx: ToolContext) -> AsyncSession:
    if ctx.db is None:  # pragma: no cover - defensive
        raise ToolError("admin tool requires ctx.db (AsyncSession)")
    return ctx.db


def _scope_to_tenant(stmt, user: User, model):
    if user.active_tenant_id:
        stmt = stmt.where((model.tenant_id == user.active_tenant_id) | (model.tenant_id.is_(None)))
    return stmt


def _rule_to_response(rule: AuditRule) -> RuleResponse:
    condition = rule.condition or {}
    return RuleResponse(
        id=str(rule.id),
        name=rule.name,
        type=condition.get("type", "pattern"),
        pattern=condition.get("pattern", ""),
        severity=condition.get("severity", "medium"),
        action=rule.action,
        description=rule.description,
        enabled=rule.enabled,
        built_in=rule.built_in,
        hit_count=0,
    )


_encryption_manager: EncryptionManager | None = None


def _get_encryption_manager() -> EncryptionManager:
    global _encryption_manager  # noqa: PLW0603
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager(key=app_settings.encryption_key)
    return _encryption_manager


# ---------------------------------------------------------------------------
# agents — rules CRUD + synthetic event evaluation
# ---------------------------------------------------------------------------


class AgentsListInput(BaseModel):
    model_config = {"extra": "forbid"}


class AgentsListOutput(BaseModel):
    rules: list[RuleResponse]


async def _agents_list(args: AgentsListInput, ctx: ToolContext) -> AgentsListOutput:
    session = _require_db(ctx)
    stmt = select(AuditRule).order_by(AuditRule.name)
    stmt = _scope_to_tenant(stmt, ctx.user, AuditRule)
    rules = (await session.execute(stmt)).scalars().all()
    return AgentsListOutput(rules=[_rule_to_response(r) for r in rules])


class AgentsAddOutput(RuleResponse):
    pass


async def _agents_add(args: RuleCreateRequest, ctx: ToolContext) -> AgentsAddOutput:
    session = _require_db(ctx)
    rule = AuditRule(
        name=args.name,
        description=args.description or args.name,
        condition=args.to_condition(),
        action=args.action,
        enabled=args.enabled,
        tenant_id=ctx.user.active_tenant_id,
    )
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AdminToolConflictError(f"Rule with name {args.name!r} already exists") from exc
    await session.refresh(rule)
    invalidate_rules_cache()

    logger.info("mcp_rule_created", rule_id=str(rule.id), name=rule.name, action=rule.action)
    base = _rule_to_response(rule)
    return AgentsAddOutput(**base.model_dump())


class AgentsUpdateInput(BaseModel):
    rule_id: str = Field(..., min_length=1)
    name: str | None = Field(None, min_length=1, max_length=255)
    type: str | None = Field(None, min_length=1, max_length=50)
    pattern: str | None = Field(None, max_length=1024)
    severity: str | None = Field(None, min_length=1, max_length=50)
    action: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = None
    enabled: bool | None = None

    model_config = {"extra": "forbid"}


class AgentsUpdateOutput(RuleResponse):
    pass


async def _agents_update(args: AgentsUpdateInput, ctx: ToolContext) -> AgentsUpdateOutput:
    session = _require_db(ctx)
    try:
        rule_uuid = UUID(args.rule_id)
    except ValueError as exc:
        raise AdminToolNotFoundError("Rule not found") from exc

    rule = await session.get(AuditRule, rule_uuid)
    if rule is None:
        raise AdminToolNotFoundError("Rule not found")
    if ctx.user.active_tenant_id and rule.tenant_id and rule.tenant_id != ctx.user.active_tenant_id:
        raise AdminToolNotFoundError("Rule not found")

    update_data = args.model_dump(exclude_unset=True, exclude={"rule_id"})
    if "name" in update_data:
        rule.name = update_data["name"]
    if "description" in update_data:
        rule.description = update_data["description"]
    if "action" in update_data:
        rule.action = update_data["action"]
    if "enabled" in update_data:
        rule.enabled = update_data["enabled"]
    if any(k in update_data for k in ("type", "pattern", "severity")):
        cond = dict(rule.condition or {})
        for key in ("type", "pattern", "severity"):
            if key in update_data:
                cond[key] = update_data[key]
        rule.condition = cond

    await session.commit()
    await session.refresh(rule)
    invalidate_rules_cache()

    logger.info("mcp_rule_updated", rule_id=str(rule.id), name=rule.name)
    base = _rule_to_response(rule)
    return AgentsUpdateOutput(**base.model_dump())


class AgentsDeleteInput(BaseModel):
    rule_id: str = Field(..., min_length=1)
    if_exists: bool = False

    model_config = {"extra": "forbid"}


class AgentsDeleteOutput(BaseModel):
    deleted: bool
    id: str
    reason: str | None = None


async def _agents_delete(args: AgentsDeleteInput, ctx: ToolContext) -> AgentsDeleteOutput:
    session = _require_db(ctx)
    try:
        rule_uuid = UUID(args.rule_id)
    except ValueError as exc:
        if args.if_exists:
            return AgentsDeleteOutput(deleted=False, id=args.rule_id, reason="not_found")
        raise AdminToolNotFoundError("Rule not found") from exc

    rule = await session.get(AuditRule, rule_uuid)
    if rule is None:
        if args.if_exists:
            return AgentsDeleteOutput(deleted=False, id=args.rule_id, reason="not_found")
        raise AdminToolNotFoundError("Rule not found")
    if ctx.user.active_tenant_id and rule.tenant_id and rule.tenant_id != ctx.user.active_tenant_id:
        if args.if_exists:
            return AgentsDeleteOutput(deleted=False, id=args.rule_id, reason="not_found")
        raise AdminToolNotFoundError("Rule not found")
    if rule.built_in:
        raise AdminToolForbiddenError("Built-in rules cannot be deleted")

    await session.delete(rule)
    await session.commit()
    invalidate_rules_cache()

    logger.info("mcp_rule_deleted", rule_id=args.rule_id)
    return AgentsDeleteOutput(deleted=True, id=args.rule_id)


class AgentsRunInput(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=255)
    source: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=255)
    target: str = Field(..., min_length=1, max_length=1024)

    model_config = {"extra": "forbid"}


class AgentsRunOutput(BaseModel):
    event_id: str
    allowed: bool
    reason: str | None = None
    explanation: ExplanationResponse | None = None


async def _agents_run(args: AgentsRunInput, ctx: ToolContext) -> AgentsRunOutput:
    """Synthetic event evaluation — admin smoke-test for the rule engine.

    Diverges from REST ``POST /api/events`` in that it skips the producer
    audit chain (``supervisor.rule.violated`` / ``supervisor.alert.published``);
    the dispatcher's ``audit_event`` hook covers the admin trail. Tenant binds
    from ``user.active_tenant_id`` rather than a service-token claim.
    """

    session = _require_db(ctx)
    if not ctx.user.active_tenant_id:
        raise AdminToolForbiddenError("admin caller must have an active tenant for synthetic events")

    timestamp = datetime.now(timezone.utc)
    event = AuditEvent(
        agent_id=args.agent_id,
        source=args.source,
        event_type=args.event_type,
        action=args.action,
        target=args.target,
        allowed=True,
        timestamp=timestamp,
        tenant_id=ctx.user.active_tenant_id,
    )
    rule_engine = RuleEngine(session)
    rule_result = await rule_engine.evaluate(event)
    event.allowed = rule_result.allowed
    if rule_result.explanation:
        event.explanation_json = asdict(rule_result.explanation)

    session.add(event)
    await session.flush()
    if not rule_result.allowed:
        await IncidentTracker(session).track_event(event)

    await session.commit()
    await session.refresh(event)

    explanation_resp = None
    if rule_result.explanation:
        explanation_resp = ExplanationResponse(**asdict(rule_result.explanation))

    return AgentsRunOutput(
        event_id=str(event.id),
        allowed=rule_result.allowed,
        reason=rule_result.reason,
        explanation=explanation_resp,
    )


# ---------------------------------------------------------------------------
# incidents
# ---------------------------------------------------------------------------


class IncidentListEntry(BaseModel):
    id: str
    agent_id: str
    title: str
    status: str
    severity: str
    event_count: int
    started_at: str
    updated_at: str


class IncidentsListInput(BaseModel):
    severity: str | None = None
    since: datetime | None = None

    model_config = {"extra": "forbid"}


class IncidentsListOutput(BaseModel):
    incidents: list[IncidentListEntry]


async def _incidents_list(args: IncidentsListInput, ctx: ToolContext) -> IncidentsListOutput:
    session = _require_db(ctx)
    stmt = select(Incident).order_by(Incident.updated_at.desc()).limit(50)
    stmt = _scope_to_tenant(stmt, ctx.user, Incident)
    if args.severity is not None:
        stmt = stmt.where(Incident.severity == args.severity)
    if args.since is not None:
        stmt = stmt.where(Incident.updated_at >= args.since)
    rows = (await session.execute(stmt)).scalars().all()
    return IncidentsListOutput(
        incidents=[
            IncidentListEntry(
                id=str(inc.id),
                agent_id=inc.agent_id,
                title=inc.title,
                status=inc.status,
                severity=inc.severity,
                event_count=inc.event_count,
                started_at=inc.started_at.isoformat(),
                updated_at=inc.updated_at.isoformat(),
            )
            for inc in rows
        ]
    )


class IncidentsShowInput(BaseModel):
    incident_id: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class TimelineEntry(BaseModel):
    id: str
    timestamp: str
    event_type: str
    action: str
    target: str
    allowed: bool


class IncidentsShowOutput(IncidentListEntry):
    timeline: list[TimelineEntry]


async def _incidents_show(args: IncidentsShowInput, ctx: ToolContext) -> IncidentsShowOutput:
    session = _require_db(ctx)
    try:
        incident_uuid = UUID(args.incident_id)
    except ValueError as exc:
        raise AdminToolNotFoundError("Incident not found") from exc

    stmt = select(Incident).where(Incident.id == incident_uuid)
    stmt = _scope_to_tenant(stmt, ctx.user, Incident)
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise AdminToolNotFoundError("Incident not found")

    events = await IncidentTracker(session).get_timeline(incident.id)
    timeline = [
        TimelineEntry(
            id=str(e.id),
            timestamp=e.timestamp.isoformat(),
            event_type=e.event_type,
            action=e.action,
            target=e.target,
            allowed=e.allowed,
        )
        for e in events
    ]
    return IncidentsShowOutput(
        id=str(incident.id),
        agent_id=incident.agent_id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        event_count=incident.event_count,
        started_at=incident.started_at.isoformat(),
        updated_at=incident.updated_at.isoformat(),
        timeline=timeline,
    )


class IncidentTransitionInput(BaseModel):
    incident_id: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


class IncidentTransitionOutput(BaseModel):
    id: str
    status: str


async def _incidents_transition(
    args: IncidentTransitionInput, ctx: ToolContext, *, target_status: IncidentStatus
) -> IncidentTransitionOutput:
    session = _require_db(ctx)
    try:
        incident_uuid = UUID(args.incident_id)
    except ValueError as exc:
        raise AdminToolNotFoundError("Incident not found") from exc

    stmt = select(Incident).where(Incident.id == incident_uuid)
    stmt = _scope_to_tenant(stmt, ctx.user, Incident)
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise AdminToolNotFoundError("Incident not found")

    incident.status = target_status
    await session.commit()
    logger.info("mcp_incident_transitioned", incident_id=str(incident.id), status=target_status.value)
    return IncidentTransitionOutput(id=str(incident.id), status=incident.status)


async def _incidents_ack(args: IncidentTransitionInput, ctx: ToolContext) -> IncidentTransitionOutput:
    return await _incidents_transition(args, ctx, target_status=IncidentStatus.ACKNOWLEDGED)


async def _incidents_resolve(args: IncidentTransitionInput, ctx: ToolContext) -> IncidentTransitionOutput:
    return await _incidents_transition(args, ctx, target_status=IncidentStatus.RESOLVED)


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


class AuditListInput(BaseModel):
    model_config = {"extra": "forbid"}


class AuditListOutput(BaseModel):
    events: list[EventListItem]


async def _audit_list(args: AuditListInput, ctx: ToolContext) -> AuditListOutput:
    session = _require_db(ctx)
    stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(100)
    if ctx.user.active_tenant_id:
        stmt = stmt.where(AuditEvent.tenant_id == ctx.user.active_tenant_id)
    events = (await session.execute(stmt)).scalars().all()

    items: list[EventListItem] = []
    for e in events:
        severity = "blocked" if not e.allowed else "safe"
        explanation = ExplanationResponse(**e.explanation_json) if e.explanation_json else None
        items.append(
            EventListItem(
                id=str(e.id),
                timestamp=e.timestamp.isoformat() if e.timestamp else "",
                agent_id=e.agent_id,
                action=e.action,
                severity=severity,
                rule_name=explanation.rule_name if explanation else None,
                details=e.target,
                explanation=explanation,
            )
        )
    return AuditListOutput(events=items)


class AuditShowInput(BaseModel):
    date: str = Field(..., description="Report date in YYYY-MM-DD format")

    model_config = {"extra": "forbid"}


class AuditShowOutput(BaseModel):
    report_id: str
    date: str
    total_events: int
    blocked_count: int
    total_cost_usd: str
    report_json: dict
    markdown: str


async def _audit_show(args: AuditShowInput, ctx: ToolContext) -> AuditShowOutput:
    session = _require_db(ctx)
    try:
        target_date = date_cls.fromisoformat(args.date)
    except ValueError as exc:
        raise AdminToolNotFoundError(f"Invalid date {args.date!r}; expected YYYY-MM-DD") from exc

    reporter = Reporter(session)
    report = await reporter.generate_daily_report(target_date)
    markdown = reporter.to_markdown(report)
    return AuditShowOutput(
        report_id=str(report.id),
        date=str(report.date),
        total_events=report.total_events,
        blocked_count=report.blocked_count,
        total_cost_usd=str(report.total_cost_usd),
        report_json=report.report_json,
        markdown=markdown,
    )


# ---------------------------------------------------------------------------
# costs
# ---------------------------------------------------------------------------


class CostsReportInput(BaseModel):
    days: int | None = Field(None, ge=1, le=365)
    by: str | None = None

    model_config = {"extra": "forbid"}


async def _costs_report(args: CostsReportInput, ctx: ToolContext) -> CostDataResponse:
    session = _require_db(ctx)

    # Mirror api/costs.py list_costs aggregation. ``args.days``/``args.by`` are
    # accepted to keep the CLI surface stable but currently do not influence
    # the aggregation (matches REST behaviour).
    from bsupervisor.models.cost_record import CostRecord

    now = datetime.now(timezone.utc)
    today_start, _ = day_window(now.date())

    tenant_filter = []
    if ctx.user.active_tenant_id:
        tenant_filter = [CostRecord.tenant_id == ctx.user.active_tenant_id]

    total_spent = (
        await session.execute(
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0"))).where(
                CostRecord.timestamp >= today_start, *tenant_filter
            )
        )
    ).scalar_one()

    budget = app_settings.daily_budget_usd
    budget_pct = float(total_spent / budget * 100) if budget > 0 else 0.0

    agent_rows = (
        await session.execute(
            select(
                CostRecord.agent_id,
                func.count().label("requests"),
                func.sum(CostRecord.tokens_in + CostRecord.tokens_out).label("tokens"),
                func.sum(CostRecord.cost_usd).label("cost"),
            )
            .where(CostRecord.timestamp >= today_start, *tenant_filter)
            .group_by(CostRecord.agent_id)
        )
    ).all()

    total_cost_val = float(total_spent) if total_spent else 0.0
    agents = []
    for row in agent_rows:
        agent_cost = float(row.cost) if row.cost else 0.0
        pct = (agent_cost / total_cost_val * 100) if total_cost_val > 0 else 0.0
        agents.append(
            CostAgentEntry(
                agent_id=row.agent_id,
                agent_name=row.agent_id,
                requests=row.requests or 0,
                tokens=int(row.tokens or 0),
                cost=f"${agent_cost:.2f}",
                percentage=round(pct, 1),
                daily_costs=[agent_cost],
            )
        )

    window_start, _ = day_window((now - timedelta(days=_TREND_DAYS - 1)).date())
    bucket_rows = (
        await session.execute(
            select(
                func.date(CostRecord.timestamp).label("day"),
                func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")).label("cost"),
            )
            .where(CostRecord.timestamp >= window_start, *tenant_filter)
            .group_by(func.date(CostRecord.timestamp))
        )
    ).all()
    by_day = {str(row.day): float(row.cost) if row.cost else 0.0 for row in bucket_rows}

    trend = []
    for i in range(_TREND_DAYS - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        date_str = d.strftime("%Y-%m-%d")
        trend.append({"date": date_str, "cost": by_day.get(date_str, 0.0)})

    return CostDataResponse(
        budget=f"${budget:.2f}",
        spent=f"${total_spent:.2f}",
        budget_percentage=round(budget_pct, 1),
        trend=trend,
        agents=agents,
        anomalies=[],
    )


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


async def _load_connections(session: AsyncSession) -> ConnectionSettings:
    stmt = select(SettingsModel).where(SettingsModel.key == CONNECTIONS_KEY)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return ConnectionSettings()
    return decrypt_connections(row.value, _get_encryption_manager())


class SettingsGetInput(BaseModel):
    key: str | None = None

    model_config = {"extra": "forbid"}


class SettingsGetOutput(BaseModel):
    connections: ConnectionSettings
    key: str | None = None
    value: str | None = None


async def _settings_get(args: SettingsGetInput, ctx: ToolContext) -> SettingsGetOutput:
    session = _require_db(ctx)
    connections = await _load_connections(session)
    if args.key is None:
        return SettingsGetOutput(connections=connections)
    if args.key not in _SETTABLE_KEYS:
        raise AdminToolNotFoundError(
            f"unknown key {args.key!r}; supported: {', '.join(_SETTABLE_KEYS)}",
        )
    value = getattr(connections, args.key, "")
    return SettingsGetOutput(connections=connections, key=args.key, value=value)


class SettingsSetInput(BaseModel):
    key: str = Field(..., min_length=1)
    value: str = Field(..., max_length=2048)

    model_config = {"extra": "forbid"}


class SettingsSetOutput(BaseModel):
    """Mutation receipt — never carries the secret value (audit-safe)."""

    updated: bool
    key: str


async def _settings_set(args: SettingsSetInput, ctx: ToolContext) -> SettingsSetOutput:
    session = _require_db(ctx)
    if args.key not in _SETTABLE_KEYS:
        raise AdminToolNotFoundError(
            f"unknown key {args.key!r}; supported: {', '.join(_SETTABLE_KEYS)}",
        )

    connections = await _load_connections(session)
    setattr(connections, args.key, args.value)

    encrypted_value = encrypt_connections(connections, _get_encryption_manager())

    stmt = select(SettingsModel).where(SettingsModel.key == CONNECTIONS_KEY)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = SettingsModel(
            key=CONNECTIONS_KEY,
            value=encrypted_value,
            description="Connection settings for external integrations",
        )
        session.add(row)
    else:
        row.value = encrypted_value

    await session.commit()
    logger.info("mcp_settings_updated", key=args.key)
    return SettingsSetOutput(updated=True, key=args.key)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


ADMIN_TOOLS: list[Tool] = [
    Tool(
        name="bsupervisor_agents_list",
        description="List all rules visible to the active tenant.",
        input_schema=AgentsListInput,
        output_schema=AgentsListOutput,
        handler=_agents_list,
        required_scopes=["supervisor:agents:read"],
    ),
    Tool(
        name="bsupervisor_agents_add",
        description="Create a new rule.",
        input_schema=RuleCreateRequest,
        output_schema=AgentsAddOutput,
        handler=_agents_add,
        required_scopes=["supervisor:agents:write"],
        audit_event="supervisor.rule.created",
    ),
    Tool(
        name="bsupervisor_agents_update",
        description="Patch an existing rule.",
        input_schema=AgentsUpdateInput,
        output_schema=AgentsUpdateOutput,
        handler=_agents_update,
        required_scopes=["supervisor:agents:write"],
        audit_event="supervisor.rule.updated",
    ),
    Tool(
        name="bsupervisor_agents_delete",
        description="Delete a rule (idempotent when if_exists=true).",
        input_schema=AgentsDeleteInput,
        output_schema=AgentsDeleteOutput,
        handler=_agents_delete,
        required_scopes=["supervisor:agents:write"],
        audit_event="supervisor.rule.deleted",
    ),
    Tool(
        name="bsupervisor_agents_run",
        description="Submit a synthetic event and surface the rule-engine decision.",
        input_schema=AgentsRunInput,
        output_schema=AgentsRunOutput,
        handler=_agents_run,
        required_scopes=["supervisor:agents:write"],
        audit_event="supervisor.event.evaluated",
    ),
    Tool(
        name="bsupervisor_incidents_list",
        description="List incidents (most recent first), optionally filtered by severity / since.",
        input_schema=IncidentsListInput,
        output_schema=IncidentsListOutput,
        handler=_incidents_list,
        required_scopes=["supervisor:incidents:read"],
    ),
    Tool(
        name="bsupervisor_incidents_show",
        description="Show one incident with its forensic timeline.",
        input_schema=IncidentsShowInput,
        output_schema=IncidentsShowOutput,
        handler=_incidents_show,
        required_scopes=["supervisor:incidents:read"],
    ),
    Tool(
        name="bsupervisor_incidents_ack",
        description="Acknowledge an incident (mark triage in progress).",
        input_schema=IncidentTransitionInput,
        output_schema=IncidentTransitionOutput,
        handler=_incidents_ack,
        required_scopes=["supervisor:incidents:write"],
        audit_event="supervisor.incident.acknowledged",
    ),
    Tool(
        name="bsupervisor_incidents_resolve",
        description="Resolve an incident (close the row).",
        input_schema=IncidentTransitionInput,
        output_schema=IncidentTransitionOutput,
        handler=_incidents_resolve,
        required_scopes=["supervisor:incidents:write"],
        audit_event="supervisor.incident.resolved",
    ),
    Tool(
        name="bsupervisor_audit_list",
        description="List the most recent audit events.",
        input_schema=AuditListInput,
        output_schema=AuditListOutput,
        handler=_audit_list,
        required_scopes=["supervisor:audit:read"],
    ),
    Tool(
        name="bsupervisor_audit_show",
        description="Show the daily audit report for a given YYYY-MM-DD date.",
        input_schema=AuditShowInput,
        output_schema=AuditShowOutput,
        handler=_audit_show,
        required_scopes=["supervisor:audit:read"],
    ),
    Tool(
        name="bsupervisor_costs_report",
        description="Show today's cost summary and 30-day trend.",
        input_schema=CostsReportInput,
        output_schema=CostDataResponse,
        handler=_costs_report,
        required_scopes=["supervisor:audit:read"],
    ),
    Tool(
        name="bsupervisor_settings_get",
        description="Show all settings, or one whitelisted scalar key.",
        input_schema=SettingsGetInput,
        output_schema=SettingsGetOutput,
        handler=_settings_get,
        required_scopes=["supervisor:*"],
    ),
    Tool(
        name="bsupervisor_settings_set",
        description="Set a whitelisted scalar key (slack_webhook_url | telegram_bot_token).",
        input_schema=SettingsSetInput,
        output_schema=SettingsSetOutput,
        handler=_settings_set,
        required_scopes=["supervisor:*"],
        audit_event="supervisor.settings.updated",
    ),
]


ADMIN_TOOL_NAMES: tuple[str, ...] = tuple(t.name for t in ADMIN_TOOLS)


def build_admin_registry() -> ToolRegistry:
    """Return a fresh :class:`ToolRegistry` populated with every admin tool.

    Transports (HTTP ``/mcp``, stdio) call this once during lifespan setup;
    domain tools — when added — register against the same registry instance.
    """

    registry = ToolRegistry()
    for tool in ADMIN_TOOLS:
        registry.register(tool)
    return registry


__all__ = [
    "ADMIN_TOOLS",
    "ADMIN_TOOL_NAMES",
    "AdminToolConflictError",
    "AdminToolForbiddenError",
    "AdminToolNotFoundError",
    "build_admin_registry",
]
