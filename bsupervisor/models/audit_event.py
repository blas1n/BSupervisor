"""AuditEvent model — stores every action taken by an AI agent."""

from sqlalchemy import JSON, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target: Mapped[str] = mapped_column(String(1024), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    explanation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    feedback_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    # P0.5 — tenant scoping. Nullable in Phase 0 because legacy events
    # ingested before the multi-tenant cutover have no tenant; backfill
    # is deferred to Phase 0.4-후속.
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, default=None)

    # Audit §M6 — composite index for incident timeline queries
    # (``WHERE agent_id = :id AND timestamp BETWEEN ... ORDER BY timestamp``)
    # and a standalone timestamp index for the daily-window scans used by
    # status / reporter.
    __table_args__ = (
        Index("ix_audit_events_agent_id_timestamp", "agent_id", "timestamp"),
        Index("ix_audit_events_timestamp", "timestamp"),
    )
