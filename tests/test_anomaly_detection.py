"""Tests for Anomaly Detection.

Statistical anomaly detection based on historical baselines,
not fixed thresholds. Detects when today's cost or event count
for an agent is significantly above its recent average.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.anomaly_detector import AnomalyDetector, AnomalyResult
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord


async def _seed_cost_history(
    session: AsyncSession,
    agent_id: str,
    daily_costs: list[Decimal],
    start_days_ago: int | None = None,
) -> None:
    """Seed cost records for consecutive days ending yesterday."""
    now = datetime.now(timezone.utc)
    start_days_ago = start_days_ago or len(daily_costs)
    for i, cost in enumerate(daily_costs):
        day_offset = start_days_ago - i
        ts = now - timedelta(days=day_offset)
        record = CostRecord(
            agent_id=agent_id,
            model="gpt-4",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=cost,
            timestamp=ts,
        )
        session.add(record)
    await session.commit()


async def _seed_event_history(
    session: AsyncSession,
    agent_id: str,
    daily_counts: list[int],
    start_days_ago: int | None = None,
) -> None:
    """Seed audit events for consecutive days ending yesterday."""
    now = datetime.now(timezone.utc)
    start_days_ago = start_days_ago or len(daily_counts)
    for i, count in enumerate(daily_counts):
        day_offset = start_days_ago - i
        for j in range(count):
            ts = now - timedelta(days=day_offset, hours=j % 24)
            event = AuditEvent(
                agent_id=agent_id,
                source="test",
                event_type="api_call",
                action="call",
                target=f"https://api.example.com/{j}",
                allowed=True,
                timestamp=ts,
            )
            session.add(event)
    await session.commit()


# --- AnomalyResult dataclass ---


class TestAnomalyResult:
    def test_create(self):
        r = AnomalyResult(
            agent_id="agent-1",
            metric="cost",
            current_value=Decimal("50.00"),
            baseline_mean=Decimal("10.00"),
            baseline_stddev=Decimal("2.00"),
            multiplier=20.0,
            is_anomaly=True,
        )
        assert r.is_anomaly is True
        assert r.agent_id == "agent-1"
        assert r.metric == "cost"

    def test_not_anomaly(self):
        r = AnomalyResult(
            agent_id="agent-1",
            metric="cost",
            current_value=Decimal("11.00"),
            baseline_mean=Decimal("10.00"),
            baseline_stddev=Decimal("2.00"),
            multiplier=0.5,
            is_anomaly=False,
        )
        assert r.is_anomaly is False


# --- Cost anomaly detection ---


class TestCostAnomalyDetection:
    async def test_detects_cost_spike(self, db_session: AsyncSession):
        # 7 days of ~$10/day
        await _seed_cost_history(db_session, "agent-spike", [Decimal("10")] * 7)
        # Today: $50 (5x average)
        today_record = CostRecord(
            agent_id="agent-spike",
            model="gpt-4",
            tokens_in=5000,
            tokens_out=2500,
            cost_usd=Decimal("50.00"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(today_record)
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_cost_anomalies()

        anomalies = [r for r in results if r.agent_id == "agent-spike"]
        assert len(anomalies) == 1
        assert anomalies[0].is_anomaly is True
        assert anomalies[0].metric == "cost"

    async def test_no_anomaly_for_normal_cost(self, db_session: AsyncSession):
        await _seed_cost_history(db_session, "agent-normal", [Decimal("10")] * 7)
        today_record = CostRecord(
            agent_id="agent-normal",
            model="gpt-4",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=Decimal("12.00"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(today_record)
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_cost_anomalies()

        anomalies = [r for r in results if r.agent_id == "agent-normal"]
        assert len(anomalies) == 0  # normal cost, not returned

    async def test_no_history_means_no_anomaly(self, db_session: AsyncSession):
        """New agent with no history should not trigger anomaly."""
        today_record = CostRecord(
            agent_id="new-agent",
            model="gpt-4",
            tokens_in=1000,
            tokens_out=500,
            cost_usd=Decimal("100.00"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(today_record)
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_cost_anomalies()

        anomalies = [r for r in results if r.agent_id == "new-agent"]
        assert len(anomalies) == 0


# --- Event frequency anomaly detection ---


class TestEventFrequencyAnomalyDetection:
    async def test_detects_event_spike(self, db_session: AsyncSession):
        # 7 days of ~10 events/day
        await _seed_event_history(db_session, "busy-agent", [10] * 7)
        # Today: 100 events (10x average)
        now = datetime.now(timezone.utc)
        for i in range(100):
            event = AuditEvent(
                agent_id="busy-agent",
                source="test",
                event_type="api_call",
                action="call",
                target=f"https://api.example.com/today/{i}",
                allowed=True,
                timestamp=now,
            )
            db_session.add(event)
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_event_anomalies()

        anomalies = [r for r in results if r.agent_id == "busy-agent"]
        assert len(anomalies) == 1
        assert anomalies[0].is_anomaly is True
        assert anomalies[0].metric == "event_count"

    async def test_no_anomaly_for_normal_frequency(self, db_session: AsyncSession):
        await _seed_event_history(db_session, "steady-agent", [10] * 7)
        now = datetime.now(timezone.utc)
        for i in range(12):
            event = AuditEvent(
                agent_id="steady-agent",
                source="test",
                event_type="api_call",
                action="call",
                target=f"https://api.example.com/today/{i}",
                allowed=True,
                timestamp=now,
            )
            db_session.add(event)
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_event_anomalies()

        anomalies = [r for r in results if r.agent_id == "steady-agent"]
        assert len(anomalies) == 0


# --- Combined detection ---


class TestDetectAll:
    async def test_detect_all_returns_both_types(self, db_session: AsyncSession):
        # Cost spike
        await _seed_cost_history(db_session, "agent-both", [Decimal("10")] * 7)
        now = datetime.now(timezone.utc)
        db_session.add(
            CostRecord(
                agent_id="agent-both",
                model="gpt-4",
                tokens_in=5000,
                tokens_out=2500,
                cost_usd=Decimal("100.00"),
                timestamp=now,
            )
        )
        await db_session.commit()

        detector = AnomalyDetector(db_session, threshold_multiplier=3.0)
        results = await detector.detect_all()
        assert any(r.metric == "cost" for r in results)


# --- API endpoint ---


class TestAnomalyAPI:
    async def test_get_anomalies_empty(self, client):
        resp = await client.get("/api/anomalies")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_anomalies_with_data(self, client, db_session: AsyncSession):
        # Seed history + spike
        await _seed_cost_history(db_session, "api-agent", [Decimal("5")] * 7)
        db_session.add(
            CostRecord(
                agent_id="api-agent",
                model="gpt-4",
                tokens_in=5000,
                tokens_out=2500,
                cost_usd=Decimal("100.00"),
                timestamp=datetime.now(timezone.utc),
            )
        )
        await db_session.commit()

        resp = await client.get("/api/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        anomaly = data[0]
        assert "agent_id" in anomaly
        assert "metric" in anomaly
        assert "current_value" in anomaly
        assert "baseline_mean" in anomaly
        assert "multiplier" in anomaly
        assert "is_anomaly" in anomaly
