"""CostRecord model — tracks LLM usage costs per agent."""

from decimal import Decimal

from sqlalchemy import Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CostRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_records"

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)

    # Audit §M6 — composite index for the per-agent daily aggregation
    # (``WHERE agent_id = :id AND timestamp BETWEEN start AND end``) and a
    # standalone timestamp index for the totals/trend queries scanned by
    # ``GET /api/costs``.
    __table_args__ = (
        Index("ix_cost_records_agent_id_timestamp", "agent_id", "timestamp"),
        Index("ix_cost_records_timestamp", "timestamp"),
    )
