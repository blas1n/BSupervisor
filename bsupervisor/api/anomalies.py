"""Anomaly detection API endpoint."""

from bsvibe_audit import AuditResource
from bsvibe_audit.events.supervisor import AnomalyDetected
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import CurrentUser, require_scope
from bsupervisor.core.anomaly_detector import AnomalyDetector
from bsupervisor.core.audit import make_actor, safe_emit
from bsupervisor.models.database import get_session

router = APIRouter(prefix="/api", tags=["anomalies"])


class AnomalyEntry(BaseModel):
    agent_id: str
    metric: str
    current_value: str
    baseline_mean: str
    baseline_stddev: str
    multiplier: float
    is_anomaly: bool


@router.get("/anomalies", response_model=list[AnomalyEntry])
async def list_anomalies(
    user: CurrentUser,
    _allowed: None = Depends(require_scope("supervisor:agents:read")),
    session: AsyncSession = Depends(get_session),
) -> list[AnomalyEntry]:
    detector = AnomalyDetector(session)
    results = await detector.detect_all()

    # Phase Audit Batch 2 — emit one ``supervisor.anomaly.detected`` per
    # detected anomaly. Done here (rather than inside the detector) so
    # the emit shares the request transaction and the actor + tenant_id
    # are pulled from the calling user.
    actor = make_actor(
        actor_type="user",
        actor_id=user.id,
        email=user.email,
    )
    emitted_any = False
    for r in results:
        if not r.is_anomaly:
            continue
        await safe_emit(
            AnomalyDetected(
                actor=actor,
                tenant_id=user.active_tenant_id,
                resource=AuditResource(type="agent", id=r.agent_id),
                data={
                    "agent_id": r.agent_id,
                    "metric": r.metric,
                    "current_value": str(r.current_value),
                    "baseline_mean": str(r.baseline_mean),
                    "baseline_stddev": str(r.baseline_stddev),
                    "multiplier": r.multiplier,
                    "severity": "warning",
                },
            ),
            session=session,
        )
        emitted_any = True

    # ``GET /api/anomalies`` doesn't write anything else; commit the
    # outbox rows we just appended so the relay can pick them up.
    if emitted_any:
        await session.commit()

    return [
        AnomalyEntry(
            agent_id=r.agent_id,
            metric=r.metric,
            current_value=str(r.current_value),
            baseline_mean=str(r.baseline_mean),
            baseline_stddev=str(r.baseline_stddev),
            multiplier=r.multiplier,
            is_anomaly=r.is_anomaly,
        )
        for r in results
    ]
