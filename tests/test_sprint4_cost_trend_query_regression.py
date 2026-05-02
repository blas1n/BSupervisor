"""Sprint 4 — N+1 query-count regression for ``GET /api/costs``.

Audit §M5 was fixed in Sprint 2 (PR #13) by replacing 30 sequential
``SELECT SUM(cost_usd) ... WHERE timestamp BETWEEN ...`` calls with a
single ``GROUP BY date(...)`` aggregation. The Sprint 2 PR added
``test_costs_api.test_trend_uses_single_aggregate_query`` which only
asserts ``< 10`` total executions.

Sprint 4 tightens the contract:

* The trend portion specifically MUST execute exactly one aggregation
  query (not "fewer than 10"). A regression that re-introduces the
  per-day loop would otherwise stay under 10 if the window shrank — we
  want the structural property, not an arbitrary numeric ceiling.
* Query count MUST stay constant regardless of how many CostRecord rows
  exist. With 0 rows, 1 row, and 200 rows the execution count is the
  same.
* Query count MUST stay constant regardless of how many distinct days
  the data spans. (The pre-fix code looped per-day; if data spread
  across 30 days, it issued 30 queries.)
* The ``func.date(timestamp)`` projection MUST appear in the trend
  query — not a Python-side bucketization fallback that scales linearly
  in record count.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.cost_record import CostRecord


def _patched_execute_counter():
    """Return ``(patcher_ctx, executions)`` capturing every ``AsyncSession.execute``."""
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    original = _AsyncSession.execute
    executions: list[str] = []

    async def _counting_execute(self, statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            executions.append(str(statement.compile(compile_kwargs={"literal_binds": False})))
        except Exception:
            executions.append(str(statement))
        return await original(self, statement, *args, **kwargs)

    return patch.object(_AsyncSession, "execute", _counting_execute), executions


@pytest.fixture
async def _seed_one_record_today(db_session: AsyncSession) -> None:
    db_session.add(
        CostRecord(
            agent_id="a",
            model="gpt-4",
            tokens_in=1,
            tokens_out=1,
            cost_usd=Decimal("0.10"),
            timestamp=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()


@pytest.fixture
async def _seed_thirty_distinct_days(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CostRecord(
                agent_id=f"a{day}",
                model="gpt-4",
                tokens_in=1,
                tokens_out=1,
                cost_usd=Decimal("1.00"),
                timestamp=now - timedelta(days=day, hours=1),
            )
            for day in range(30)
        ]
    )
    await db_session.commit()


@pytest.fixture
async def _seed_two_hundred_records(db_session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            CostRecord(
                agent_id=f"a{i % 5}",
                model="gpt-4",
                tokens_in=1,
                tokens_out=1,
                cost_usd=Decimal("0.05"),
                timestamp=now - timedelta(days=i % 30, minutes=i),
            )
            for i in range(200)
        ]
    )
    await db_session.commit()


def _trend_aggregate_count(executions: list[str]) -> int:
    """Count how many calls invoke ``date(...)`` GROUP BY — the trend query."""
    return sum(1 for s in executions if "date(" in s.lower() and "group by" in s.lower())


class TestTrendUsesExactlyOneAggregate:
    async def test_one_aggregate_query_with_zero_records(self, client) -> None:
        patcher, executions = _patched_execute_counter()
        with patcher:
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert _trend_aggregate_count(executions) == 1

    async def test_one_aggregate_query_with_single_record(
        self,
        client,
        _seed_one_record_today,
    ) -> None:
        patcher, executions = _patched_execute_counter()
        with patcher:
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert _trend_aggregate_count(executions) == 1

    async def test_one_aggregate_query_with_thirty_distinct_days(
        self,
        client,
        _seed_thirty_distinct_days,
    ) -> None:
        """Pre-fix this scenario produced 30 separate queries."""
        patcher, executions = _patched_execute_counter()
        with patcher:
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert _trend_aggregate_count(executions) == 1, (
            f"Trend issued {_trend_aggregate_count(executions)} aggregates "
            f"(expected 1) — N+1 regression. Total queries: {len(executions)}"
        )

    async def test_one_aggregate_query_with_two_hundred_records(
        self,
        client,
        _seed_two_hundred_records,
    ) -> None:
        """Query count must be invariant under load."""
        patcher, executions = _patched_execute_counter()
        with patcher:
            resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert _trend_aggregate_count(executions) == 1


class TestTrendQueryCountInvariantUnderLoad:
    """The total ``execute(...)`` count must not scale with record count."""

    async def test_query_count_stable_across_dataset_sizes(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        # Baseline: 0 records.
        patcher, baseline = _patched_execute_counter()
        with patcher:
            ok = await client.get("/api/costs")
        assert ok.status_code == 200
        baseline_count = len(baseline)

        # Insert a sizable dataset spread across many days/agents.
        now = datetime.now(timezone.utc)
        db_session.add_all(
            [
                CostRecord(
                    agent_id=f"agent-{i % 7}",
                    model="gpt-4",
                    tokens_in=1,
                    tokens_out=1,
                    cost_usd=Decimal("0.01"),
                    timestamp=now - timedelta(days=i % 30, minutes=i % 1440),
                )
                for i in range(120)
            ]
        )
        await db_session.commit()

        # Re-measure.
        patcher2, after = _patched_execute_counter()
        with patcher2:
            ok = await client.get("/api/costs")
        assert ok.status_code == 200

        assert len(after) == baseline_count, (
            f"Query count grew from {baseline_count} to {len(after)} as data "
            f"increased — that's the N+1 shape we just removed."
        )


class TestTrendShapeRegressionGuard:
    """The trend query must use ``func.date(...)`` GROUP BY — not Python-side fallback."""

    async def test_trend_aggregation_uses_date_grouping(
        self,
        client,
        _seed_thirty_distinct_days,
    ) -> None:
        patcher, executions = _patched_execute_counter()
        with patcher:
            resp = await client.get("/api/costs")
        assert resp.status_code == 200

        # Find the trend query — it groups by date and sums cost_usd.
        trend_queries = [s for s in executions if "date(" in s.lower() and "group by" in s.lower()]
        assert len(trend_queries) == 1
        assert "sum" in trend_queries[0].lower(), "trend query lost its SUM(cost_usd)"
