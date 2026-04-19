"""Incident tracker — groups blocked events into forensic incidents."""

from datetime import timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.incident import Incident, IncidentStatus

logger = structlog.get_logger(__name__)

DEFAULT_WINDOW_MINUTES = 30
DEFAULT_TIMELINE_WINDOW_MINUTES = 60


class IncidentTracker:
    def __init__(self, session: AsyncSession, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> None:
        self.session = session
        self.window = timedelta(minutes=window_minutes)

    async def track_event(self, event: AuditEvent) -> Incident | None:
        """Track a blocked event, creating or merging into an incident.

        Returns None for allowed events.
        """
        if event.allowed:
            return None

        # Look for an existing open incident for this agent within the time window
        cutoff = event.timestamp - self.window
        stmt = (
            select(Incident)
            .where(
                Incident.agent_id == event.agent_id,
                Incident.status == IncidentStatus.OPEN,
                Incident.updated_at >= cutoff,
            )
            .order_by(Incident.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        incident = result.scalar_one_or_none()

        if incident is not None:
            incident.event_count += 1
            incident.updated_at = event.timestamp
            logger.info(
                "incident_event_merged",
                incident_id=str(incident.id),
                event_id=str(event.id),
                event_count=incident.event_count,
            )
        else:
            severity = self._determine_severity(event)
            incident = Incident(
                agent_id=event.agent_id,
                title=self._generate_title(event),
                status=IncidentStatus.OPEN,
                severity=severity,
                event_count=1,
                started_at=event.timestamp,
                updated_at=event.timestamp,
            )
            self.session.add(incident)
            logger.info(
                "incident_created",
                incident_id=str(incident.id) if incident.id else "pending",
                agent_id=event.agent_id,
                severity=severity,
            )

        await self.session.commit()
        await self.session.refresh(incident)
        return incident

    async def get_timeline(
        self,
        incident_id,
        window_minutes: int = DEFAULT_TIMELINE_WINDOW_MINUTES,
    ) -> list[AuditEvent]:
        """Get all events from the same agent around the incident time window."""
        result = await self.session.execute(select(Incident).where(Incident.id == incident_id))
        incident = result.scalar_one_or_none()
        if incident is None:
            return []

        window = timedelta(minutes=window_minutes)
        start = incident.started_at - window
        end = incident.updated_at + window

        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.agent_id == incident.agent_id,
                AuditEvent.timestamp >= start,
                AuditEvent.timestamp <= end,
            )
            .order_by(AuditEvent.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _determine_severity(self, event: AuditEvent) -> str:
        if event.event_type in ("file_delete", "shell_exec"):
            return "critical"
        return "high"

    def _generate_title(self, event: AuditEvent) -> str:
        return f"Blocked {event.event_type}: {event.target[:100]}"
