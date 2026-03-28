"""DailyReport model — stores daily aggregated audit reports."""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, JSON, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, UUIDPrimaryKeyMixin


class DailyReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "daily_reports"

    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    total_events: Mapped[int] = mapped_column(Integer, nullable=False)
    blocked_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
