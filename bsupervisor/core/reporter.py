"""Daily report generator — aggregates audit events and costs."""

from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.daily_report import DailyReport

logger = structlog.get_logger(__name__)


class Reporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate_daily_report(self, target_date: date) -> DailyReport:
        """Generate and persist a daily report for the given date."""
        start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        total_events = await self._count_events(start, end)
        blocked_count = await self._count_blocked(start, end)
        total_cost_usd = await self._sum_costs(start, end)
        cost_by_agent = await self._cost_by_agent(start, end)
        cost_by_model = await self._cost_by_model(start, end)
        top_agents = await self._top_agents(start, end)

        report_json = {
            "cost_by_agent": {k: str(v) for k, v in cost_by_agent.items()},
            "cost_by_model": {k: str(v) for k, v in cost_by_model.items()},
            "top_agents": top_agents,
        }

        # Upsert: update existing report for this date or create new one
        existing_stmt = select(DailyReport).where(DailyReport.date == target_date)
        existing_result = await self._session.execute(existing_stmt)
        report = existing_result.scalar_one_or_none()

        if report is not None:
            report.total_events = total_events
            report.blocked_count = blocked_count
            report.total_cost_usd = total_cost_usd
            report.report_json = report_json
        else:
            report = DailyReport(
                date=target_date,
                total_events=total_events,
                blocked_count=blocked_count,
                total_cost_usd=total_cost_usd,
                report_json=report_json,
            )
            self._session.add(report)

        await self._session.commit()
        await self._session.refresh(report)

        logger.info(
            "daily_report_generated",
            date=str(target_date),
            total_events=total_events,
            blocked_count=blocked_count,
            total_cost_usd=str(total_cost_usd),
        )
        return report

    def to_markdown(self, report: DailyReport) -> str:
        """Render a DailyReport as a human-readable Markdown string."""
        lines = [
            f"# Daily Report — {report.date}",
            "",
            "## Summary",
            "",
            f"- **Total Events**: {report.total_events}",
            f"- **Blocked**: {report.blocked_count}",
            f"- **Total Cost**: ${report.total_cost_usd}",
            "",
        ]

        cost_by_agent = report.report_json.get("cost_by_agent", {})
        if cost_by_agent:
            lines.append("## Cost by Agent")
            lines.append("")
            for agent_id, cost in cost_by_agent.items():
                lines.append(f"- **{agent_id}**: ${cost}")
            lines.append("")

        cost_by_model = report.report_json.get("cost_by_model", {})
        if cost_by_model:
            lines.append("## Cost by Model")
            lines.append("")
            for model, cost in cost_by_model.items():
                lines.append(f"- **{model}**: ${cost}")
            lines.append("")

        top_agents = report.report_json.get("top_agents", [])
        if top_agents:
            lines.append("## Top Agents by Activity")
            lines.append("")
            for entry in top_agents:
                lines.append(f"- **{entry['agent_id']}**: {entry['event_count']} events")
            lines.append("")

        return "\n".join(lines)

    # --- private query helpers ---

    async def _count_events(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.timestamp >= start, AuditEvent.timestamp <= end)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _count_blocked(self, start: datetime, end: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.timestamp >= start, AuditEvent.timestamp <= end)
            .where(AuditEvent.allowed.is_(False))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _sum_costs(self, start: datetime, end: datetime) -> Decimal:
        stmt = (
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")))
            .where(CostRecord.timestamp >= start, CostRecord.timestamp <= end)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def _cost_by_agent(self, start: datetime, end: datetime) -> dict[str, Decimal]:
        stmt = (
            select(CostRecord.agent_id, func.sum(CostRecord.cost_usd))
            .where(CostRecord.timestamp >= start, CostRecord.timestamp <= end)
            .group_by(CostRecord.agent_id)
            .order_by(CostRecord.agent_id)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def _cost_by_model(self, start: datetime, end: datetime) -> dict[str, Decimal]:
        stmt = (
            select(CostRecord.model, func.sum(CostRecord.cost_usd))
            .where(CostRecord.timestamp >= start, CostRecord.timestamp <= end)
            .group_by(CostRecord.model)
            .order_by(CostRecord.model)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def _top_agents(self, start: datetime, end: datetime) -> list[dict]:
        stmt = (
            select(AuditEvent.agent_id, func.count().label("event_count"))
            .where(AuditEvent.timestamp >= start, AuditEvent.timestamp <= end)
            .group_by(AuditEvent.agent_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        result = await self._session.execute(stmt)
        return [{"agent_id": row[0], "event_count": row[1]} for row in result.all()]
