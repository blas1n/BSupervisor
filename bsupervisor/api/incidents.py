"""Incident timeline API endpoints."""

from uuid import UUID

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.core.incident_tracker import IncidentTracker
from bsupervisor.models.database import get_session
from bsupervisor.models.incident import Incident, IncidentStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["incidents"])


class IncidentListItem(BaseModel):
    id: str
    agent_id: str
    title: str
    status: str
    severity: str
    event_count: int
    started_at: str
    updated_at: str


class TimelineEntry(BaseModel):
    id: str
    timestamp: str
    event_type: str
    action: str
    target: str
    allowed: bool


class IncidentDetail(BaseModel):
    id: str
    agent_id: str
    title: str
    status: str
    severity: str
    event_count: int
    started_at: str
    updated_at: str
    timeline: list[TimelineEntry]


class ResolveResponse(BaseModel):
    id: str
    status: str


@router.get("/incidents", response_model=list[IncidentListItem])
async def list_incidents(
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[IncidentListItem]:
    result = await session.execute(select(Incident).order_by(Incident.updated_at.desc()).limit(50))
    incidents = result.scalars().all()
    return [
        IncidentListItem(
            id=str(inc.id),
            agent_id=inc.agent_id,
            title=inc.title,
            status=inc.status,
            severity=inc.severity,
            event_count=inc.event_count,
            started_at=inc.started_at.isoformat(),
            updated_at=inc.updated_at.isoformat(),
        )
        for inc in incidents
    ]


@router.get("/incidents/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: UUID,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> IncidentDetail:
    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    events = await IncidentTracker(session).get_timeline(incident.id)

    timeline = [
        TimelineEntry(
            id=str(e.id),
            timestamp=e.timestamp.isoformat(),
            event_type=e.event_type,
            action=e.action,
            target=e.target,
            allowed=e.allowed,
        )
        for e in events
    ]

    return IncidentDetail(
        id=str(incident.id),
        agent_id=incident.agent_id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        event_count=incident.event_count,
        started_at=incident.started_at.isoformat(),
        updated_at=incident.updated_at.isoformat(),
        timeline=timeline,
    )


@router.post("/incidents/{incident_id}/resolve", response_model=ResolveResponse)
async def resolve_incident(
    incident_id: UUID,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ResolveResponse:
    result = await session.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = IncidentStatus.RESOLVED
    await session.commit()

    logger.info("incident_resolved", incident_id=incident_id)

    return ResolveResponse(id=str(incident.id), status=incident.status)
