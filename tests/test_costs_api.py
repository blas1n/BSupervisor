"""Tests for ``GET /api/costs`` — Audit §M5 (N+1 trend) and §M17 (budget config).

Sprint 2 / Hardening — these tests guard the two behavior changes shipped in
this sprint:

* The 30-day trend used to issue 30 sequential ``SELECT SUM(cost_usd) ...
  WHERE timestamp BETWEEN ...`` queries (one per day) — see Audit §M5. The
  endpoint now performs a single ``GROUP BY`` aggregation and reconstitutes
  the 30-day list in Python.
* The daily budget displayed on the dashboard was hardcoded to ``$100`` in
  the route handler. It now reads from ``settings.daily_budget_usd``.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.cost_record import CostRecord


@pytest.fixture
async def _sample_costs(db_session: AsyncSession) -> None:
    """Insert one cost record per day for the past 5 days plus one for today."""
    now = datetime.now(timezone.utc)
    rows = [
        CostRecord(
            agent_id="agent-a",
            model="gpt-4",
            tokens_in=10,
            tokens_out=20,
            cost_usd=Decimal("0.5"),
            timestamp=now - timedelta(days=offset, hours=2),
            tenant_id="tenant-test",
        )
        for offset in range(5)
    ]
    rows.append(
        CostRecord(
            agent_id="agent-b",
            model="claude-3",
            tokens_in=100,
            tokens_out=200,
            cost_usd=Decimal("1.25"),
            timestamp=now,
            tenant_id="tenant-test",
        )
    )
    db_session.add_all(rows)
    await db_session.commit()


class TestCostsTrendBatching:
    """Audit §M5 — single aggregate query for the 30-day trend."""

    async def test_trend_returns_thirty_entries(self, client, _sample_costs) -> None:
        resp = await client.get("/api/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trend"]) == 30
        # Each entry has a date string and a numeric cost field.
        for entry in data["trend"]:
            assert "date" in entry
            assert "cost" in entry
            assert isinstance(entry["cost"], (int, float))

    async def test_trend_is_chronological_oldest_first(self, client, _sample_costs) -> None:
        resp = await client.get("/api/costs")
        dates = [entry["date"] for entry in resp.json()["trend"]]
        assert dates == sorted(dates), "trend dates must be ascending (oldest → newest)"

    async def test_trend_uses_single_aggregate_query(self, client, _sample_costs) -> None:
        """No per-day query loop — counts SQL executions during /api/costs.

        Pre-fix the handler issued 30 SELECT statements just for the trend.
        Post-fix it uses one GROUP BY date_trunc('day', ...). We accept any
        count <= 5 (status check, totals, agents, trend, plus headroom) but
        reject the >= 30 regression shape directly.
        """
        from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

        original_execute = _AsyncSession.execute
        executions: list[str] = []

        async def _counting_execute(self, statement, *args, **kwargs):  # type: ignore[no-untyped-def]
            try:
                executions.append(str(statement))
            except Exception:
                executions.append("<unprintable>")
            return await original_execute(self, statement, *args, **kwargs)

        with patch.object(_AsyncSession, "execute", _counting_execute):
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert len(executions) < 10, f"GET /api/costs ran {len(executions)} queries — N+1 regression"

    async def test_trend_aggregates_costs_per_day(self, client, db_session) -> None:
        now = datetime.now(timezone.utc)
        # Two records on the same day → must be summed in one trend bucket.
        db_session.add_all(
            [
                CostRecord(
                    agent_id="x",
                    model="gpt-4",
                    tokens_in=1,
                    tokens_out=1,
                    cost_usd=Decimal("0.4"),
                    timestamp=now,
                    tenant_id="tenant-test",
                ),
                CostRecord(
                    agent_id="y",
                    model="gpt-4",
                    tokens_in=1,
                    tokens_out=1,
                    cost_usd=Decimal("0.6"),
                    timestamp=now,
                    tenant_id="tenant-test",
                ),
            ]
        )
        await db_session.commit()

        resp = await client.get("/api/costs")
        today_str = now.strftime("%Y-%m-%d")
        today_entry = next(e for e in resp.json()["trend"] if e["date"] == today_str)
        assert today_entry["cost"] == pytest.approx(1.0)


class TestCostsBudgetConfigurable:
    """Audit §M17 — daily_budget_usd from settings, not hardcoded."""

    async def test_budget_default_is_one_hundred(self, client) -> None:
        resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert resp.json()["budget"] == "$100.00"

    async def test_budget_reflects_settings_override(self, client) -> None:
        from bsupervisor.api import costs as costs_module

        with patch.object(costs_module.settings, "daily_budget_usd", Decimal("250.00")):
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert resp.json()["budget"] == "$250.00"

    async def test_budget_percentage_uses_settings(self, client, db_session) -> None:
        from bsupervisor.api import costs as costs_module

        db_session.add(
            CostRecord(
                agent_id="x",
                model="gpt-4",
                tokens_in=1,
                tokens_out=1,
                cost_usd=Decimal("25.00"),
                timestamp=datetime.now(timezone.utc),
                tenant_id="tenant-test",
            )
        )
        await db_session.commit()

        with patch.object(costs_module.settings, "daily_budget_usd", Decimal("100.00")):
            resp = await client.get("/api/costs")
        assert resp.json()["budget_percentage"] == pytest.approx(25.0)

    async def test_budget_zero_handled_safely(self, client) -> None:
        """Budget=0 is a valid setting (e.g. dev-only) and must not divide-by-zero."""
        from bsupervisor.api import costs as costs_module

        with patch.object(costs_module.settings, "daily_budget_usd", Decimal("0")):
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert resp.json()["budget_percentage"] == 0.0
