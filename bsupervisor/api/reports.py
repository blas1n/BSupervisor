"""Daily report API endpoint."""

from datetime import date

from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.core.reporter import Reporter
from bsupervisor.models.database import get_session

router = APIRouter(prefix="/api", tags=["reports"])


class DailyReportResponse(BaseModel):
    report_id: str
    date: str
    total_events: int
    blocked_count: int
    total_cost_usd: str
    report_json: dict
    markdown: str


@router.get("/reports/daily", response_model=DailyReportResponse)
async def get_daily_report(
    date: date = Query(..., description="Report date in YYYY-MM-DD format"),
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DailyReportResponse:
    reporter = Reporter(session)
    report = await reporter.generate_daily_report(date)
    markdown = reporter.to_markdown(report)

    return DailyReportResponse(
        report_id=str(report.id),
        date=str(report.date),
        total_events=report.total_events,
        blocked_count=report.blocked_count,
        total_cost_usd=str(report.total_cost_usd),
        report_json=report.report_json,
        markdown=markdown,
    )
