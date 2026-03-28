"""Status API endpoint — today's summary."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.schemas import StatusResponse
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.database import get_session

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(
    session: AsyncSession = Depends(get_session),
) -> StatusResponse:
    today = datetime.now(timezone.utc).date()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    end = datetime(today.year, today.month, today.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

    total_events = (
        await session.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.timestamp >= start, AuditEvent.timestamp <= end)
        )
    ).scalar_one()

    blocked_count = (
        await session.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.timestamp >= start, AuditEvent.timestamp <= end)
            .where(AuditEvent.allowed.is_(False))
        )
    ).scalar_one()

    total_cost = (
        await session.execute(
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0"))).where(
                CostRecord.timestamp >= start, CostRecord.timestamp <= end
            )
        )
    ).scalar_one()

    return StatusResponse(
        total_events_today=total_events,
        blocked_count_today=blocked_count,
        total_cost_today=str(total_cost.normalize()),
    )
