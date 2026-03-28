"""Tests for cost tracking — CostTracker class and POST /api/costs endpoint."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.core.cost_tracker import CostTracker
from bsupervisor.models.cost_record import CostRecord


class TestCostTrackerRecordCost:
    async def test_record_cost_creates_record(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        await tracker.record_cost(
            agent_id="agent-1",
            model="gpt-4",
            tokens_in=100,
            tokens_out=50,
            cost_usd=Decimal("0.005"),
        )

        result = await db_session.execute(select(CostRecord))
        record = result.scalar_one()
        assert record.agent_id == "agent-1"
        assert record.model == "gpt-4"
        assert record.tokens_in == 100
        assert record.tokens_out == 50
        assert record.cost_usd == Decimal("0.005")

    async def test_record_cost_multiple_records(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        await tracker.record_cost("agent-1", "gpt-4", 100, 50, Decimal("0.005"))
        await tracker.record_cost("agent-2", "claude-3", 200, 100, Decimal("0.010"))

        result = await db_session.execute(select(CostRecord))
        records = result.scalars().all()
        assert len(records) == 2


class TestCostTrackerGetDailyCost:
    async def test_get_daily_cost_single_agent(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        today = date.today()

        record1 = CostRecord(
            agent_id="agent-1",
            model="gpt-4",
            tokens_in=100,
            tokens_out=50,
            cost_usd=Decimal("0.005"),
            timestamp=datetime.now(timezone.utc),
        )
        record2 = CostRecord(
            agent_id="agent-1",
            model="gpt-4",
            tokens_in=200,
            tokens_out=100,
            cost_usd=Decimal("0.010"),
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add_all([record1, record2])
        await db_session.commit()

        cost = await tracker.get_daily_cost("agent-1", today)
        assert cost == Decimal("0.015")

    async def test_get_daily_cost_filters_by_agent(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        today = date.today()

        record1 = CostRecord(
            agent_id="agent-1", model="gpt-4", tokens_in=100, tokens_out=50,
            cost_usd=Decimal("0.005"), timestamp=datetime.now(timezone.utc),
        )
        record2 = CostRecord(
            agent_id="agent-2", model="gpt-4", tokens_in=200, tokens_out=100,
            cost_usd=Decimal("0.010"), timestamp=datetime.now(timezone.utc),
        )
        db_session.add_all([record1, record2])
        await db_session.commit()

        cost = await tracker.get_daily_cost("agent-1", today)
        assert cost == Decimal("0.005")

    async def test_get_daily_cost_no_records_returns_zero(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        cost = await tracker.get_daily_cost("agent-1", date.today())
        assert cost == Decimal("0")

    async def test_get_daily_cost_filters_by_date(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)

        record = CostRecord(
            agent_id="agent-1", model="gpt-4", tokens_in=100, tokens_out=50,
            cost_usd=Decimal("0.005"),
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        db_session.add(record)
        await db_session.commit()

        cost = await tracker.get_daily_cost("agent-1", date(2025, 1, 15))
        assert cost == Decimal("0.005")

        cost_other_day = await tracker.get_daily_cost("agent-1", date(2025, 1, 16))
        assert cost_other_day == Decimal("0")


class TestCostTrackerGetDailyTotal:
    async def test_get_daily_total_all_agents(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        today = date.today()

        record1 = CostRecord(
            agent_id="agent-1", model="gpt-4", tokens_in=100, tokens_out=50,
            cost_usd=Decimal("0.005"), timestamp=datetime.now(timezone.utc),
        )
        record2 = CostRecord(
            agent_id="agent-2", model="claude-3", tokens_in=200, tokens_out=100,
            cost_usd=Decimal("0.010"), timestamp=datetime.now(timezone.utc),
        )
        db_session.add_all([record1, record2])
        await db_session.commit()

        total = await tracker.get_daily_total(today)
        assert total == Decimal("0.015")

    async def test_get_daily_total_no_records_returns_zero(self, db_session: AsyncSession) -> None:
        tracker = CostTracker(db_session)
        total = await tracker.get_daily_total(date.today())
        assert total == Decimal("0")


class TestCostAPI:
    async def test_post_cost_valid(self, client) -> None:
        resp = await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": "0.005",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == "agent-1"
        assert data["model"] == "gpt-4"
        assert data["tokens_in"] == 100
        assert data["tokens_out"] == 50
        assert data["cost_usd"] == "0.005"
        assert "cost_id" in data

    async def test_post_cost_missing_field(self, client) -> None:
        resp = await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
        })
        assert resp.status_code == 422

    async def test_post_cost_persists_to_db(self, client, db_session: AsyncSession) -> None:
        await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": "0.005",
        })

        result = await db_session.execute(select(CostRecord))
        record = result.scalar_one()
        assert record.agent_id == "agent-1"
        assert record.cost_usd == Decimal("0.005")

    async def test_post_cost_negative_tokens_rejected(self, client) -> None:
        resp = await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
            "tokens_in": -1,
            "tokens_out": 50,
            "cost_usd": "0.005",
        })
        assert resp.status_code == 422

    async def test_post_cost_extra_fields_rejected(self, client) -> None:
        resp = await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": "0.005",
            "extra_field": "bad",
        })
        assert resp.status_code == 422

    async def test_post_cost_decimal_precision(self, client) -> None:
        resp = await client.post("/api/costs", json={
            "agent_id": "agent-1",
            "model": "gpt-4",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": "0.00000123",
        })
        assert resp.status_code == 201
        assert resp.json()["cost_usd"] == "0.00000123"
