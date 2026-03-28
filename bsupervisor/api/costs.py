"""Cost ingestion API endpoint."""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.schemas import CostRequest, CostResponse
from bsupervisor.core.cost_tracker import CostTracker
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["costs"])


@router.post("/costs", response_model=CostResponse, status_code=201)
async def ingest_cost(
    payload: CostRequest,
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
