"""Rules CRUD API endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.schemas import RuleCreateRequest, RuleResponse, RuleUpdateRequest
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["rules"])


def _rule_to_response(rule: AuditRule) -> RuleResponse:
    return RuleResponse(
        id=str(rule.id),
        name=rule.name,
        description=rule.description,
        condition=rule.condition,
        action=rule.action,
        enabled=rule.enabled,
    )


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    session: AsyncSession = Depends(get_session),
) -> list[RuleResponse]:
    result = await session.execute(select(AuditRule).order_by(AuditRule.name))
    rules = result.scalars().all()
    return [_rule_to_response(r) for r in rules]


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    payload: RuleCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    rule = AuditRule(
        name=payload.name,
        description=payload.description,
        condition=payload.condition,
        action=payload.action,
        enabled=payload.enabled,
    )
    session.add(rule)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"Rule with name '{payload.name}' already exists")
    await session.refresh(rule)

    logger.info("rule_created", rule_id=str(rule.id), name=rule.name, action=rule.action)
    return _rule_to_response(rule)


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    payload: RuleUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    rule = await session.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await session.commit()
    await session.refresh(rule)

    logger.info("rule_updated", rule_id=str(rule.id), name=rule.name)
    return _rule_to_response(rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await session.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await session.delete(rule)
    await session.commit()

    logger.info("rule_deleted", rule_id=str(rule_id))
