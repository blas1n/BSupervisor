"""CostRecord model — tracks LLM usage costs per agent."""

from decimal import Decimal

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from bsupervisor.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CostRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cost_records"

    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
