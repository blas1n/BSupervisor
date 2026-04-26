"""Event ingestion and listing API endpoints."""

import uuid
from dataclasses import asdict
from datetime import datetime, timezone

import structlog
from bsvibe_authz import User
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import (
    CurrentUser,
    ServiceKey,
    bsupervisor_service_auth,
    require_permission,
)
from bsupervisor.api.schemas import (
    EventListItem,
    EventRequest,
    EventResponse,
    ExplanationResponse,
    FeedbackRequest,
    FeedbackResponse,
)
from bsupervisor.config import settings as app_settings
from bsupervisor.core.incident_tracker import IncidentTracker
from bsupervisor.core.rate_limiter import InMemoryRateLimiter
from bsupervisor.core.rule_engine import RuleEngine
from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["events"])

# Module-level limiter so quotas survive across requests within a process.
# Window is 60s — `events_rate_limit_per_minute` is the per-source budget.
# Tests can swap this out by reassigning ``events._events_rate_limiter``.
_events_rate_limiter = InMemoryRateLimiter(
    max_requests=app_settings.events_rate_limit_per_minute,
    window_seconds=60.0,
)


def _rate_limit_key(payload: EventRequest) -> str:
    """Bucket key for rate-limiting incoming events.

    ``source`` is the upstream system (bsnexus, cli, …). We deliberately do
    NOT use ``agent_id`` because hostile traffic can rotate that field; the
    source field is operator-controlled.
    """
    return f"source:{payload.source}"


@router.get("/events", response_model=list[EventListItem])
async def list_events(
    user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.events.read")),
    session: AsyncSession = Depends(get_session),
) -> list[EventListItem]:
    stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(100)
    if user.active_tenant_id:
        stmt = stmt.where(
            (AuditEvent.tenant_id == user.active_tenant_id) | (AuditEvent.tenant_id.is_(None)),
        )
    result = await session.execute(stmt)
    events = result.scalars().all()

    items = []
    for e in events:
        severity = "blocked" if not e.allowed else "safe"
        explanation = ExplanationResponse(**e.explanation_json) if e.explanation_json else None
        items.append(
            EventListItem(
                id=str(e.id),
                timestamp=e.timestamp.isoformat() if e.timestamp else "",
                agent_id=e.agent_id,
                action=e.action,
                severity=severity,
                rule_name=explanation.rule_name if explanation else None,
                details=e.target,
                explanation=explanation,
            )
        )
    return items


@router.post("/events", response_model=EventResponse, status_code=201)
async def ingest_event(
    payload: EventRequest,
    svc: ServiceKey = Depends(bsupervisor_service_auth),
    session: AsyncSession = Depends(get_session),
) -> EventResponse:
    """Ingest an event.

    P0.5 — service-only: BSGateway / BSNexus call this with their service JWT
    (``aud="bsupervisor"``, scope ``bsupervisor.events``). Sprint 1 H6 rate
    limiter is preserved untouched.
    """
    if not _events_rate_limiter.allow(_rate_limit_key(payload)):
        logger.warning(
            "events_rate_limited",
            source=payload.source,
            agent_id=payload.agent_id,
            caller=svc.sub,
        )
        raise HTTPException(status_code=429, detail="rate limit exceeded for this source")

    timestamp = payload.timestamp or datetime.now(timezone.utc)

    # The service token MAY carry a tenant_id — when it does, every event it
    # ingests is bound to that tenant. Untenanted ingestion is allowed for
    # the ``service:`` calling convention as a transitional measure (Phase 0).
    event = AuditEvent(
        agent_id=payload.agent_id,
        source=payload.source,
        event_type=payload.event_type,
        action=payload.action,
        target=payload.target,
        metadata_json=payload.metadata,
        allowed=True,
        timestamp=timestamp,
        tenant_id=svc.tenant_id,
    )

    # Evaluate rules before persisting
    rule_engine = RuleEngine(session)
    rule_result = await rule_engine.evaluate(event)
    event.allowed = rule_result.allowed

    if rule_result.explanation:
        event.explanation_json = asdict(rule_result.explanation)

    session.add(event)
    await session.flush()

    if not rule_result.allowed:
        await IncidentTracker(session).track_event(event)

    await session.commit()
    await session.refresh(event)

    logger.info(
        "event_ingested",
        event_id=str(event.id),
        agent_id=event.agent_id,
        event_type=event.event_type,
        allowed=rule_result.allowed,
        caller=svc.sub,
        tenant_id=svc.tenant_id,
    )

    explanation_resp = None
    if rule_result.explanation:
        explanation_resp = ExplanationResponse(**asdict(rule_result.explanation))

    return EventResponse(
        event_id=str(event.id),
        allowed=rule_result.allowed,
        reason=rule_result.reason,
        explanation=explanation_resp,
    )


@router.post("/events/{event_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    event_id: uuid.UUID,
    payload: FeedbackRequest,
    user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.events.write")),
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    stmt = select(AuditEvent).where(AuditEvent.id == event_id)
    if user.active_tenant_id:
        stmt = stmt.where(
            (AuditEvent.tenant_id == user.active_tenant_id) | (AuditEvent.tenant_id.is_(None)),
        )
    result = await session.execute(stmt)
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    event.feedback_json = {
        "is_false_positive": payload.is_false_positive,
        "comment": payload.comment,
    }
    await session.commit()

    logger.info("feedback_submitted", event_id=str(event_id), is_false_positive=payload.is_false_positive)

    return FeedbackResponse(event_id=str(event_id), accepted=True)


# Silence "imported but unused" — User is part of the public type surface
# and exported here so dependent modules can ``from bsupervisor.api.events
# import User`` if needed.
__all__ = ["User", "ingest_event", "list_events", "router", "submit_feedback"]
