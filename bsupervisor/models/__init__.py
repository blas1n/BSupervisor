"""SQLAlchemy models for BSupervisor."""

from bsvibe_audit import register_audit_outbox_with

from bsupervisor.models.audit_event import AuditEvent
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.base import Base
from bsupervisor.models.cost_record import CostRecord
from bsupervisor.models.daily_report import DailyReport
from bsupervisor.models.incident import Incident
from bsupervisor.models.settings import Settings

# Phase Audit Batch 2 — re-attach the shared ``audit_outbox`` Table to
# BSupervisor's declarative ``Base.metadata`` so a single Alembic
# ``target_metadata`` covers both the domain tables and the outbox.
# Idempotent: ``register_audit_outbox_with`` is a no-op on re-import.
register_audit_outbox_with(Base.metadata)

__all__ = [
    "AuditEvent",
    "AuditRule",
    "Base",
    "CostRecord",
    "DailyReport",
    "Incident",
    "Settings",
]
