"""Cost tracking — records and aggregates LLM usage costs per agent."""

from datetime import date, datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.models.cost_record import CostRecord

logger = structlog.get_logger(__name__)


class CostTracker:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_cost(
        self,
        agent_id: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: Decimal,
    ) -> CostRecord:
        record = CostRecord(
            agent_id=agent_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            timestamp=datetime.now(timezone.utc),
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        logger.info(
            "cost_recorded",
            agent_id=agent_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=str(cost_usd),
        )
        return record

    async def get_daily_cost(self, agent_id: str, target_date: date) -> Decimal:
        start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        stmt = (
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")))
            .where(CostRecord.agent_id == agent_id)
            .where(CostRecord.timestamp >= start)
            .where(CostRecord.timestamp <= end)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_daily_total(self, target_date: date) -> Decimal:
        start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

        stmt = (
            select(func.coalesce(func.sum(CostRecord.cost_usd), Decimal("0")))
            .where(CostRecord.timestamp >= start)
            .where(CostRecord.timestamp <= end)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
