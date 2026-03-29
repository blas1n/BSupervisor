"""Event ingestion API endpoint."""

from datetime import datetime, timezone

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.api.schemas import EventRequest, EventResponse
from bsupervisor.core.rule_engine import RuleEngine
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])


@router.post("/events", response_model=EventResponse, status_code=201)
async def ingest_event(
    payload: EventRequest,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    timestamp = payload.timestamp or datetime.now(timezone.utc)

    event = AuditEvent(
        agent_id=payload.agent_id,
        source=payload.source,
        event_type=payload.event_type,
        action=payload.action,
        target=payload.target,
        metadata_json=payload.metadata,
        allowed=True,
        timestamp=timestamp,
    )

    # Evaluate rules before persisting
    rule_engine = RuleEngine(session)
    rule_result = await rule_engine.evaluate(event)
    event.allowed = rule_result.allowed

    session.add(event)
    await session.commit()
    await session.refresh(event)

    logger.info(
        "event_ingested",
        event_id=str(event.id),
        agent_id=event.agent_id,
        event_type=event.event_type,
        allowed=rule_result.allowed,
    )

    return EventResponse(
        event_id=str(event.id),
        allowed=rule_result.allowed,
        reason=rule_result.reason,
    )
