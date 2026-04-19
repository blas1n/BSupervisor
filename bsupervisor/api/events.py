"""Event ingestion and listing API endpoints."""

import uuid
from datetime import datetime, timezone

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.api.schemas import (
    EventListItem,
    EventRequest,
    EventResponse,
    ExplanationResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from bsupervisor.core.incident_tracker import IncidentTracker
from bsupervisor.core.rule_engine import RuleEngine
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events", response_model=list[EventListItem])
async def list_events(
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(100))
    events = result.scalars().all()

    items = []
    for e in events:
        if not e.allowed:
            severity = "blocked"
        else:
            severity = "safe"
        items.append(
            EventListItem(
                id=str(e.id),
                timestamp=e.timestamp.isoformat() if e.timestamp else "",
                agent_id=e.agent_id,
                action=e.action,
                severity=severity,
                details=e.target,
            )
        )
    return items


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

    if rule_result.explanation:
        event.explanation_json = rule_result.explanation.to_dict()

    session.add(event)
    await session.commit()
    await session.refresh(event)

    # Track incidents for blocked events
    if not rule_result.allowed:
        tracker = IncidentTracker(session)
        await tracker.track_event(event)

    logger.info(
        "event_ingested",
        event_id=str(event.id),
        agent_id=event.agent_id,
        event_type=event.event_type,
        allowed=rule_result.allowed,
    )

    explanation_resp = None
    if rule_result.explanation:
        explanation_resp = ExplanationResponse(**rule_result.explanation.to_dict())

    return EventResponse(
        event_id=str(event.id),
        allowed=rule_result.allowed,
        reason=rule_result.reason,
        explanation=explanation_resp,
    )


@router.post("/events/{event_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    event_id: str,
    payload: FeedbackRequest,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Event not found")

    result = await session.execute(select(AuditEvent).where(AuditEvent.id == event_uuid))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event.feedback_json = {
        "is_false_positive": payload.is_false_positive,
        "comment": payload.comment,
    }
    await session.commit()

    logger.info("feedback_submitted", event_id=event_id, is_false_positive=payload.is_false_positive)

    return FeedbackResponse(event_id=event_id, accepted=True)
