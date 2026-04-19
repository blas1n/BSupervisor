"""Statistical anomaly detection for cost and event frequency.

Compares today's values against a rolling baseline (default 7 days)
using mean + threshold * stddev to detect spikes.
"""

import math
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
        """Run all anomaly detections and return combined results."""
        cost_anomalies = await self.detect_cost_anomalies()
        event_anomalies = await self.detect_event_anomalies()
        return cost_anomalies + event_anomalies

    async def detect_cost_anomalies(self) -> list[AnomalyResult]:
        """Detect agents whose today's cost is anomalously high."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lookback_start = today_start - timedelta(days=self.lookback_days)

        # Get today's cost per agent
        today_stmt = (
            select(CostRecord.agent_id, func.sum(CostRecord.cost_usd).label("total"))
            .where(CostRecord.timestamp >= today_start)
            .group_by(CostRecord.agent_id)
        )
        today_result = await self.session.execute(today_stmt)
        today_costs: dict[str, Decimal] = {row.agent_id: row.total for row in today_result.all()}

        if not today_costs:
            return []

        results: list[AnomalyResult] = []

        for agent_id, today_cost in today_costs.items():
            # Get historical daily costs
            history_stmt = (
                select(
                    func.date(CostRecord.timestamp).label("day"),
                    func.sum(CostRecord.cost_usd).label("total"),
                )
                .where(
                    CostRecord.agent_id == agent_id,
                    CostRecord.timestamp >= lookback_start,
                    CostRecord.timestamp < today_start,
                )
                .group_by(func.date(CostRecord.timestamp))
            )
            history_result = await self.session.execute(history_stmt)
            daily_costs = [row.total for row in history_result.all()]

            if len(daily_costs) < MIN_HISTORY_DAYS:
                continue

            mean, stddev = _compute_stats(daily_costs)
            if mean == 0:
                continue

            multiplier = float((today_cost - mean) / mean) if mean > 0 else 0.0
            threshold = mean + Decimal(str(self.threshold_multiplier)) * stddev
            is_anomaly = today_cost > threshold

            if is_anomaly:
                results.append(
                    AnomalyResult(
                        agent_id=agent_id,
                        metric="cost",
                        current_value=today_cost,
                        baseline_mean=mean,
                        baseline_stddev=stddev,
                        multiplier=round(multiplier, 2),
                        is_anomaly=True,
                    )
                )

        return results

    async def detect_event_anomalies(self) -> list[AnomalyResult]:
        """Detect agents whose today's event count is anomalously high."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lookback_start = today_start - timedelta(days=self.lookback_days)

        # Get today's event count per agent
        today_stmt = (
            select(AuditEvent.agent_id, func.count().label("total"))
            .where(AuditEvent.timestamp >= today_start)
            .group_by(AuditEvent.agent_id)
        )
        today_result = await self.session.execute(today_stmt)
        today_counts: dict[str, int] = {row.agent_id: row.total for row in today_result.all()}

        if not today_counts:
            return []

        results: list[AnomalyResult] = []

        for agent_id, today_count in today_counts.items():
            history_stmt = (
                select(
                    func.date(AuditEvent.timestamp).label("day"),
                    func.count().label("total"),
                )
                .where(
                    AuditEvent.agent_id == agent_id,
                    AuditEvent.timestamp >= lookback_start,
                    AuditEvent.timestamp < today_start,
                )
                .group_by(func.date(AuditEvent.timestamp))
            )
            history_result = await self.session.execute(history_stmt)
            daily_counts = [Decimal(str(row.total)) for row in history_result.all()]

            if len(daily_counts) < MIN_HISTORY_DAYS:
                continue

            mean, stddev = _compute_stats(daily_counts)
            if mean == 0:
                continue

            current = Decimal(str(today_count))
            multiplier = float((current - mean) / mean) if mean > 0 else 0.0
            threshold = mean + Decimal(str(self.threshold_multiplier)) * stddev
            is_anomaly = current > threshold

            if is_anomaly:
                results.append(
                    AnomalyResult(
                        agent_id=agent_id,
                        metric="event_count",
                        current_value=current,
                        baseline_mean=mean,
                        baseline_stddev=stddev,
                        multiplier=round(multiplier, 2),
                        is_anomaly=True,
                    )
                )

        return results


def _compute_stats(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Compute mean and population standard deviation.

    When stddev is very small (near zero), uses 10% of mean as a floor
    to avoid flagging minor variations as anomalies.
    """
    n = len(values)
    if n == 0:
        return Decimal("0"), Decimal("0")

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    stddev = Decimal(str(math.sqrt(float(variance))))

    # Floor: at least 10% of mean to handle zero-variance baselines
    min_stddev = mean * Decimal("0.1")
    if stddev < min_stddev:
        stddev = min_stddev

    return mean, stddev
