"""AuditRule model — defines rules for evaluating agent actions."""

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, UUIDPrimaryKeyMixin


class AuditRule(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_rules"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    built_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # P0.5 — nullable for built-in rules (which apply to every tenant)
    # and for legacy rules created before the multi-tenant cutover.
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, default=None)
