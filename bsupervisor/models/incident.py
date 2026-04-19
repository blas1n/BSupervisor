"""Incident model — groups related blocked events into forensic timelines."""

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, UUIDPrimaryKeyMixin


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class Incident(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "incidents"

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=IncidentStatus.OPEN)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
