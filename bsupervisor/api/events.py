"""Event ingestion API endpoint."""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.schemas import EventRequest, EventResponse
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events", response_model=EventResponse)
async def ingest_event(
    payload: EventRequest,
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    # Stub rule engine: always allow
    allowed = True
    reason = None

    timestamp = payload.timestamp or datetime.now(timezone.utc)

    event = AuditEvent(
        agent_id=payload.agent_id,
        source=payload.source,
        event_type=payload.event_type,
        action=payload.action,
        target=payload.target,
        metadata_json=payload.metadata,
        allowed=allowed,
        timestamp=timestamp,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    logger.info(
        "event_ingested",
        event_id=str(event.id),
        agent_id=event.agent_id,
        event_type=event.event_type,
        allowed=allowed,
    )

    return EventResponse(
        event_id=str(event.id),
        allowed=allowed,
        reason=reason,
    )
