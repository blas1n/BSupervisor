"""Tests for daily report generator."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.reporter import Reporter
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.daily_report import DailyReport


async def _seed_events(session: AsyncSession, target_date: date) -> None:
    """Seed sample audit events for testing."""
    base_ts = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0, tzinfo=timezone.utc)
    events = [
        AuditEvent(
            agent_id="agent-1",
            source="cli",
            event_type="file_read",
            action="read",
            target="/data/file.txt",
            allowed=True,
            timestamp=base_ts,
        ),
        AuditEvent(
            agent_id="agent-1",
            source="cli",
            event_type="shell_exec",
            action="exec",
            target="ls -la",
            allowed=True,
            timestamp=base_ts,
        ),
        AuditEvent(
            agent_id="agent-1",
            source="cli",
            event_type="file_delete",
            action="delete",
            target="/secrets/.env",
            allowed=False,
            timestamp=base_ts,
        ),
        AuditEvent(
            agent_id="agent-2",
            source="api",
            event_type="file_write",
            action="write",
            target="/output/result.json",
            allowed=True,
            timestamp=base_ts,
        ),
        AuditEvent(
            agent_id="agent-2",
            source="api",
            event_type="shell_exec",
            action="exec",
            target="rm -rf /",
            allowed=False,
            timestamp=base_ts,
        ),
    ]
    session.add_all(events)
    await session.commit()


async def _seed_costs(session: AsyncSession, target_date: date) -> None:
    """Seed sample cost records for testing."""
    base_ts = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0, tzinfo=timezone.utc)
    costs = [
        CostRecord(
            agent_id="agent-1",
            model="gpt-4",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=Decimal("0.05"),
            timestamp=base_ts,
        ),
        CostRecord(
            agent_id="agent-1",
            model="gpt-4",
            tokens_in=2000,
            tokens_out=1000,
            cost_usd=Decimal("0.10"),
            timestamp=base_ts,
        ),
        CostRecord(
            agent_id="agent-1",
            model="claude-3",
            tokens_in=500,
            tokens_out=200,
            cost_usd=Decimal("0.03"),
            timestamp=base_ts,
        ),
        CostRecord(
            agent_id="agent-2",
            model="gpt-4",
            tokens_in=3000,
            tokens_out=1500,
            cost_usd=Decimal("0.15"),
            timestamp=base_ts,
        ),
    ]
    session.add_all(costs)
    await session.commit()


# --- Reporter unit tests ---


async def test_generate_report_empty_day(db_session: AsyncSession) -> None:
    """Report for a day with no data should have zero counts."""
    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(date(2026, 1, 1))

    assert report.date == date(2026, 1, 1)
    assert report.total_events == 0
    assert report.blocked_count == 0
    assert report.total_cost_usd == Decimal("0")
    assert report.report_json is not None


async def test_generate_report_with_events(db_session: AsyncSession) -> None:
    """Report correctly aggregates events."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    assert report.total_events == 5
    assert report.blocked_count == 2


async def test_generate_report_with_costs(db_session: AsyncSession) -> None:
    """Report correctly aggregates costs."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)
    await _seed_costs(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    assert report.total_cost_usd == Decimal("0.33")


async def test_report_json_cost_breakdown_by_agent(db_session: AsyncSession) -> None:
    """report_json includes cost breakdown by agent."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)
    await _seed_costs(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    cost_by_agent = report.report_json["cost_by_agent"]
    assert Decimal(cost_by_agent["agent-1"]) == Decimal("0.18")
    assert Decimal(cost_by_agent["agent-2"]) == Decimal("0.15")


async def test_report_json_cost_breakdown_by_model(db_session: AsyncSession) -> None:
    """report_json includes cost breakdown by model."""
    target = date(2026, 3, 15)
    await _seed_costs(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    cost_by_model = report.report_json["cost_by_model"]
    assert Decimal(cost_by_model["gpt-4"]) == Decimal("0.30")
    assert Decimal(cost_by_model["claude-3"]) == Decimal("0.03")


async def test_report_json_top_agents(db_session: AsyncSession) -> None:
    """report_json includes top agents by activity count."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    top_agents = report.report_json["top_agents"]
    # agent-1 has 3 events, agent-2 has 2
    assert top_agents[0]["agent_id"] == "agent-1"
    assert top_agents[0]["event_count"] == 3
    assert top_agents[1]["agent_id"] == "agent-2"
    assert top_agents[1]["event_count"] == 2


async def test_report_is_stored_in_db(db_session: AsyncSession) -> None:
    """generate_daily_report persists the report to daily_reports table."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)

    assert report.id is not None
    # Verify it's in the DB
    from sqlalchemy import select

    stmt = select(DailyReport).where(DailyReport.date == target)
    result = await db_session.execute(stmt)
    stored = result.scalar_one()
    assert stored.total_events == 5


async def test_report_filters_by_date(db_session: AsyncSession) -> None:
    """Events on other dates should not be included."""
    target = date(2026, 3, 15)
    other = date(2026, 3, 16)
    await _seed_events(db_session, target)

    # Add one event on a different day
    other_ts = datetime(2026, 3, 16, 10, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        AuditEvent(
            agent_id="agent-3",
            source="api",
            event_type="file_read",
            action="read",
            target="/tmp/x",
            allowed=True,
            timestamp=other_ts,
        )
    )
    await db_session.commit()

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)
    assert report.total_events == 5  # Only target date events

    report_other = await reporter.generate_daily_report(other)
    assert report_other.total_events == 1


async def test_generate_markdown(db_session: AsyncSession) -> None:
    """Markdown output is human-readable and contains key sections."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)
    await _seed_costs(db_session, target)

    reporter = Reporter(db_session)
    report = await reporter.generate_daily_report(target)
    markdown = reporter.to_markdown(report)

    assert "# Daily Report" in markdown
    assert "2026-03-15" in markdown
    assert "Total Events" in markdown
    assert "Blocked" in markdown
    assert "agent-1" in markdown
    assert "agent-2" in markdown


# --- API endpoint tests ---


async def test_get_daily_report_endpoint(client, db_session: AsyncSession) -> None:
    """GET /api/reports/daily returns a report."""
    target = date(2026, 3, 15)
    await _seed_events(db_session, target)
    await _seed_costs(db_session, target)

    resp = await client.get("/api/reports/daily", params={"date": "2026-03-15"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["date"] == "2026-03-15"
    assert data["total_events"] == 5
    assert data["blocked_count"] == 2
    assert Decimal(data["total_cost_usd"]) == Decimal("0.33")
    assert "cost_by_agent" in data["report_json"]
    assert "markdown" in data


async def test_get_daily_report_missing_date(client) -> None:
    """GET /api/reports/daily without date param returns 422."""
    resp = await client.get("/api/reports/daily")
    assert resp.status_code == 422


async def test_get_daily_report_invalid_date(client) -> None:
    """GET /api/reports/daily with invalid date returns 422."""
    resp = await client.get("/api/reports/daily", params={"date": "not-a-date"})
    assert resp.status_code == 422


async def test_generate_report_upsert_updates_existing(db_session: AsyncSession) -> None:
    """Generating a report for the same date twice should update, not duplicate."""
    target = date(2026, 3, 20)
    await _seed_events(db_session, target)

    reporter = Reporter(db_session)
    report1 = await reporter.generate_daily_report(target)
    report1_id = report1.id
    assert report1.total_events == 5

    # Add more events and regenerate
    base_ts = datetime(2026, 3, 20, 18, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        AuditEvent(
            agent_id="agent-3",
            source="api",
            event_type="file_read",
            action="read",
            target="/tmp/extra",
            allowed=True,
            timestamp=base_ts,
        )
    )
    await db_session.commit()

    report2 = await reporter.generate_daily_report(target)
    assert report2.total_events == 6
    assert report2.id == report1_id  # Same row updated

    # Verify only one report exists for this date
    from sqlalchemy import select

    stmt = select(DailyReport).where(DailyReport.date == target)
    result = await db_session.execute(stmt)
    reports = result.scalars().all()
    assert len(reports) == 1


async def test_get_daily_report_empty_day(client) -> None:
    """GET /api/reports/daily for a day with no data returns zeroes."""
    resp = await client.get("/api/reports/daily", params={"date": "2026-01-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 0
    assert data["blocked_count"] == 0
