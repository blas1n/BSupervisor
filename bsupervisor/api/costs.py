"""Cost ingestion and listing API endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.api.schemas import CostAgentEntry, CostDataResponse, CostRequest, CostResponse
from bsupervisor.core.cost_tracker import CostTracker
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["costs"])


@router.get("/costs", response_model=CostDataResponse)
async def list_costs(
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CostDataResponse:
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # Total spent today
    total_spent = (
        await session.execute(
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")))
            .where(CostRecord.timestamp >= today_start)
        )
    ).scalar_one()

    budget = Decimal("100.00")
    budget_pct = float(total_spent / budget * 100) if budget > 0 else 0.0

    # Per-agent breakdown
    agent_rows = (
        await session.execute(
            select(
                CostRecord.agent_id,
                func.count().label("requests"),
                func.sum(CostRecord.tokens_in + CostRecord.tokens_out).label("tokens"),
                func.sum(CostRecord.cost_usd).label("cost"),
            )
            .where(CostRecord.timestamp >= today_start)
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

    # 30-day trend
    trend = []
    for i in range(29, -1, -1):
        d = now - timedelta(days=i)
        day_start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        day_end = datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
        day_cost = (
            await session.execute(
                select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")))
                .where(CostRecord.timestamp >= day_start, CostRecord.timestamp <= day_end)
            )
        ).scalar_one()
        trend.append({"date": day_start.strftime("%Y-%m-%d"), "cost": float(day_cost)})

    return CostDataResponse(
        budget=f"${budget:.2f}",
        spent=f"${total_spent:.2f}",
        budget_percentage=round(budget_pct, 1),
        trend=trend,
        agents=agents,
        anomalies=[],
    )


@router.post("/costs", response_model=CostResponse, status_code=201)
async def ingest_cost(
    payload: CostRequest,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CostResponse:
    tracker = CostTracker(session)
    record = await tracker.record_cost(
        agent_id=payload.agent_id,
        model=payload.model,
        tokens_in=payload.tokens_in,
        tokens_out=payload.tokens_out,
        cost_usd=payload.cost_usd,
    )

    return CostResponse(
        cost_id=str(record.id),
        agent_id=record.agent_id,
        model=record.model,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        cost_usd=str(record.cost_usd.normalize()),
    )
