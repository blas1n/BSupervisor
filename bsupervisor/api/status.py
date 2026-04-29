"""Status API endpoint — today's summary."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import CurrentUser, require_permission
from bsupervisor.api.schemas import StatusResponse
from bsupervisor.core.dates import today_window
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.database import get_session

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(
    user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.status.read")),
    session: AsyncSession = Depends(get_session),
) -> StatusResponse:
    start, end = today_window()

    event_filter = [AuditEvent.timestamp >= start, AuditEvent.timestamp <= end]
    cost_filter = [CostRecord.timestamp >= start, CostRecord.timestamp <= end]
    if user.active_tenant_id:
        event_filter.append(AuditEvent.tenant_id == user.active_tenant_id)
        cost_filter.append(CostRecord.tenant_id == user.active_tenant_id)

    total_events = (
        await session.execute(select(func.count()).select_from(AuditEvent).where(*event_filter))
    ).scalar_one()

    blocked_count = (
        await session.execute(
            select(func.count()).select_from(AuditEvent).where(*event_filter).where(AuditEvent.allowed.is_(False))
        )
    ).scalar_one()

    total_cost = (
        await session.execute(select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0"))).where(*cost_filter))
    ).scalar_one()

    return StatusResponse(
        events_today=total_events,
        violations=blocked_count,
        blocked_actions=blocked_count,
        cost_total=f"${total_cost.normalize()}",
    )
