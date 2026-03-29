"""Tests for SQLAlchemy models."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models import AuditEvent, AuditRule, CostRecord, DailyReport


async def test_audit_event_creation(db_session: AsyncSession) -> None:
    event = AuditEvent(
        agent_id="agent-001",
        source="bsnexus",
        event_type="file_access",
        action="read",
        target="/etc/passwd",
        metadata_json={"ip": "127.0.0.1"},
        allowed=True,
    )
    db_session.add(event)
    await db_session.commit()

    result = await db_session.execute(select(AuditEvent))
    row = result.scalar_one()
    assert row.agent_id == "agent-001"
    assert row.source == "bsnexus"
    assert row.event_type == "file_access"
    assert row.action == "read"
    assert row.target == "/etc/passwd"
    assert row.metadata_json == {"ip": "127.0.0.1"}
    assert row.allowed is True
    assert row.id is not None
    assert isinstance(row.timestamp, datetime)


async def test_audit_event_defaults(db_session: AsyncSession) -> None:
    event = AuditEvent(
        agent_id="agent-002",
        source="external",
        event_type="api_call",
        action="invoke",
        target="https://example.com",
    )
    db_session.add(event)
    await db_session.commit()

    result = await db_session.execute(select(AuditEvent))
    row = result.scalar_one()
    assert row.allowed is True
    assert row.metadata_json is None
    assert row.timestamp is not None


async def test_audit_rule_creation(db_session: AsyncSession) -> None:
    rule = AuditRule(
        name="block-env-delete",
        description="Block deletion of .env files",
        condition={"event_type": "file_delete", "target_pattern": "*.env"},
        action="block",
        enabled=True,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(AuditRule))
    row = result.scalar_one()
    assert row.name == "block-env-delete"
    assert row.description == "Block deletion of .env files"
    assert row.condition == {"event_type": "file_delete", "target_pattern": "*.env"}
    assert row.action == "block"
    assert row.enabled is True
    assert row.id is not None


async def test_audit_rule_defaults(db_session: AsyncSession) -> None:
    rule = AuditRule(
        name="test-rule",
        description="A test rule",
        condition={"event_type": "any"},
        action="log",
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(AuditRule))
    row = result.scalar_one()
    assert row.enabled is True


async def test_cost_record_creation(db_session: AsyncSession) -> None:
    record = CostRecord(
        agent_id="agent-001",
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        cost_usd=Decimal("0.0045"),
    )
    db_session.add(record)
    await db_session.commit()

    result = await db_session.execute(select(CostRecord))
    row = result.scalar_one()
    assert row.agent_id == "agent-001"
    assert row.model == "claude-sonnet-4-20250514"
    assert row.tokens_in == 1000
    assert row.tokens_out == 500
    assert row.cost_usd == Decimal("0.0045")
    assert isinstance(row.cost_usd, Decimal)
    assert row.id is not None
    assert isinstance(row.timestamp, datetime)


async def test_cost_record_decimal_precision(db_session: AsyncSession) -> None:
    record = CostRecord(
        agent_id="agent-001",
        model="gpt-4",
        tokens_in=100,
        tokens_out=50,
        cost_usd=Decimal("0.00000123"),
    )
    db_session.add(record)
    await db_session.commit()

    result = await db_session.execute(select(CostRecord))
    row = result.scalar_one()
    assert row.cost_usd == Decimal("0.00000123")


async def test_daily_report_creation(db_session: AsyncSession) -> None:
    report = DailyReport(
        date=date(2026, 3, 28),
        total_events=150,
        blocked_count=5,
        total_cost_usd=Decimal("12.50"),
        report_json={
            "top_agents": [{"agent_id": "agent-001", "events": 100}],
            "cost_breakdown": {"claude-sonnet-4-20250514": "10.00"},
        },
    )
    db_session.add(report)
    await db_session.commit()

    result = await db_session.execute(select(DailyReport))
    row = result.scalar_one()
    assert row.date == date(2026, 3, 28)
    assert row.total_events == 150
    assert row.blocked_count == 5
    assert row.total_cost_usd == Decimal("12.50")
    assert isinstance(row.total_cost_usd, Decimal)
    assert row.report_json["top_agents"][0]["agent_id"] == "agent-001"
    assert row.id is not None


async def test_multiple_events(db_session: AsyncSession) -> None:
    for i in range(3):
        db_session.add(
            AuditEvent(
                agent_id=f"agent-{i}",
                source="test",
                event_type="action",
                action="do",
                target=f"/target/{i}",
                allowed=i != 1,
            )
        )
    await db_session.commit()

    result = await db_session.execute(select(AuditEvent))
    rows = result.scalars().all()
    assert len(rows) == 3
    assert sum(1 for r in rows if not r.allowed) == 1
