"""Statistical anomaly detection for cost and event frequency.

Compares today's values against a rolling baseline (default 7 days)
using mean + threshold * stddev to detect spikes.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord

logger = structlog.get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_THRESHOLD_MULTIPLIER = 3.0
MIN_HISTORY_DAYS = 3


@dataclass
class AnomalyResult:
    agent_id: str
    metric: str  # "cost" or "event_count"
    current_value: Decimal
    baseline_mean: Decimal
    baseline_stddev: Decimal
    multiplier: float
    is_anomaly: bool


class AnomalyDetector:
    def __init__(
        self,
        session: AsyncSession,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        threshold_multiplier: float = DEFAULT_THRESHOLD_MULTIPLIER,
    ) -> None:
        self.session = session
        self.lookback_days = lookback_days
        self.threshold_multiplier = threshold_multiplier

    async def detect_all(self) -> list[AnomalyResult]:
        cost_anomalies = await self._detect(CostRecord, func.sum(CostRecord.cost_usd), "cost")
        event_anomalies = await self._detect(AuditEvent, func.count(), "event_count")
        return cost_anomalies + event_anomalies

    async def detect_cost_anomalies(self) -> list[AnomalyResult]:
        return await self._detect(CostRecord, func.sum(CostRecord.cost_usd), "cost")

    async def detect_event_anomalies(self) -> list[AnomalyResult]:
        return await self._detect(AuditEvent, func.count(), "event_count")

    async def _detect(self, table, value_expr, metric: str) -> list[AnomalyResult]:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lookback_start = today_start - timedelta(days=self.lookback_days)

        today_stmt = (
            select(table.agent_id, value_expr.label("total"))
            .where(table.timestamp >= today_start)
            .group_by(table.agent_id)
        )
        today_result = await self.session.execute(today_stmt)
        today_totals: dict[str, Decimal] = {row.agent_id: Decimal(str(row.total)) for row in today_result.all()}
        if not today_totals:
            return []

        # Single grouped query for all agents' history (avoids N+1)
        history_stmt = (
            select(
                table.agent_id,
                func.date(table.timestamp).label("day"),
                value_expr.label("total"),
            )
            .where(
                table.agent_id.in_(today_totals.keys()),
                table.timestamp >= lookback_start,
                table.timestamp < today_start,
            )
            .group_by(table.agent_id, func.date(table.timestamp))
        )
        history_result = await self.session.execute(history_stmt)
        history: dict[str, list[Decimal]] = {}
        for row in history_result.all():
            history.setdefault(row.agent_id, []).append(Decimal(str(row.total)))

        results: list[AnomalyResult] = []
        for agent_id, today_total in today_totals.items():
            daily = history.get(agent_id, [])
            if len(daily) < MIN_HISTORY_DAYS:
                continue

            mean, stddev = _compute_stats(daily)
            if mean == 0:
                continue

            threshold = mean + Decimal(str(self.threshold_multiplier)) * stddev
            if today_total <= threshold:
                continue

            multiplier = float((today_total - mean) / mean)
            results.append(
                AnomalyResult(
                    agent_id=agent_id,
                    metric=metric,
                    current_value=today_total,
                    baseline_mean=mean,
                    baseline_stddev=stddev,
                    multiplier=round(multiplier, 2),
                    is_anomaly=True,
                )
            )

        return results


def _compute_stats(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Compute mean and population standard deviation.

    Floors stddev at 10% of mean so zero-variance baselines don't flag every
    minor variation as an anomaly.
    """
    if not values:
        return Decimal("0"), Decimal("0")

    mean = statistics.mean(values)
    stddev = Decimal(str(statistics.pstdev(values)))
    return mean, max(stddev, mean * Decimal("0.1"))
