"""Cost ingestion and listing API endpoints."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import (
    CurrentUser,
    ServiceKey,
    bsupervisor_service_auth,
    require_permission,
)
from bsupervisor.api.schemas import CostAgentEntry, CostDataResponse, CostRequest, CostResponse
from bsupervisor.config import settings
from bsupervisor.core.cost_tracker import CostTracker
from bsupervisor.core.dates import day_window
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["costs"])

# Length of the dashboard sparkline window. Audit §M5 — keeping this as a
# named constant makes it easy to test and tune.
TREND_DAYS = 30


@router.get("/costs", response_model=CostDataResponse)
async def list_costs(
    user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.costs.read")),
    session: AsyncSession = Depends(get_session),
) -> CostDataResponse:
    now = datetime.now(timezone.utc)
    today_start, _ = day_window(now.date())

    tenant_filter = []
    if user.active_tenant_id:
        tenant_filter = [CostRecord.tenant_id == user.active_tenant_id]

    # Total spent today
    total_spent = (
        await session.execute(
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0"))).where(
                CostRecord.timestamp >= today_start,
                *tenant_filter,
            )
        )
    ).scalar_one()

    # Audit §M17 — budget read from settings (was hardcoded to $100).
    budget = settings.daily_budget_usd
    budget_pct = float(total_spent / budget * 100) if budget > 0 else 0.0

    # Per-agent breakdown (already a single GROUP BY).
    agent_rows = (
        await session.execute(
            select(
                CostRecord.agent_id,
                func.count().label("requests"),
                func.sum(CostRecord.tokens_in + CostRecord.tokens_out).label("tokens"),
                func.sum(CostRecord.cost_usd).label("cost"),
            )
            .where(CostRecord.timestamp >= today_start, *tenant_filter)
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

    # Audit §M5 — 30-day trend in a single GROUP BY query (was 30 separate
    # queries in a Python loop). We bucket by calendar UTC day using
    # ``func.date(...)`` (portable across SQLite and PostgreSQL); the result
    # is a sparse map ``{date_str: cost}`` that we densify into TREND_DAYS
    # entries below so days with no traffic still show up as ``0``.
    window_start, _ = day_window((now - timedelta(days=TREND_DAYS - 1)).date())
    bucket_rows = (
        await session.execute(
            select(
                func.date(CostRecord.timestamp).label("day"),
                func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")).label("cost"),
            )
            .where(CostRecord.timestamp >= window_start, *tenant_filter)
            .group_by(func.date(CostRecord.timestamp))
        )
    ).all()
    by_day = {str(row.day): float(row.cost) if row.cost else 0.0 for row in bucket_rows}

    trend = []
    for i in range(TREND_DAYS - 1, -1, -1):
        d = (now - timedelta(days=i)).date()
        date_str = d.strftime("%Y-%m-%d")
        trend.append({"date": date_str, "cost": by_day.get(date_str, 0.0)})

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
    svc: ServiceKey = Depends(bsupervisor_service_auth),
    session: AsyncSession = Depends(get_session),
) -> CostResponse:
    """Service-only ingestion endpoint.

    P0.5 — BSGateway / BSNexus call this with their service JWT
    (``aud="bsupervisor"``). Tenant binding comes from the required
    service token ``tenant_id`` claim.
    """
    if not svc.tenant_id:
        raise HTTPException(status_code=403, detail="service token missing tenant_id")

    tracker = CostTracker(session)
    record = await tracker.record_cost(
        agent_id=payload.agent_id,
        model=payload.model,
        tokens_in=payload.tokens_in,
        tokens_out=payload.tokens_out,
        cost_usd=payload.cost_usd,
        tenant_id=svc.tenant_id,
    )

    return CostResponse(
        cost_id=str(record.id),
        agent_id=record.agent_id,
        model=record.model,
        tokens_in=record.tokens_in,
        tokens_out=record.tokens_out,
        cost_usd=str(record.cost_usd.normalize()),
    )
