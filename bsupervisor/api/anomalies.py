"""Anomaly detection API endpoint."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import CurrentUser, require_permission
from bsupervisor.core.anomaly_detector import AnomalyDetector
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
    _user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.anomalies.read")),
    session: AsyncSession = Depends(get_session),
) -> list[AnomalyEntry]:
    detector = AnomalyDetector(session)
    results = await detector.detect_all()
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
