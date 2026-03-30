"""Rules CRUD API endpoints."""

from uuid import UUID

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.api.schemas import RuleCreateRequest, RuleResponse, RuleUpdateRequest
from bsupervisor.core.rule_engine import invalidate_rules_cache
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["rules"])


def _rule_to_response(rule: AuditRule) -> RuleResponse:
    condition = rule.condition or {}
    return RuleResponse(
        id=str(rule.id),
        name=rule.name,
        type=condition.get("type", "pattern"),
        pattern=condition.get("pattern", ""),
        severity=condition.get("severity", "medium"),
        action=rule.action,
        description=rule.description,
        enabled=rule.enabled,
        built_in=False,
        hit_count=0,
    )


@router.get("/rules", response_model=list[RuleResponse])
async def list_rules(
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[RuleResponse]:
    result = await session.execute(select(AuditRule).order_by(AuditRule.name))
    rules = result.scalars().all()
    return [_rule_to_response(r) for r in rules]


@router.post("/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    payload: RuleCreateRequest,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    rule = AuditRule(
        name=payload.name,
        description=payload.description or payload.name,
        condition=payload.to_condition(),
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
    invalidate_rules_cache()

    logger.info("rule_created", rule_id=str(rule.id), name=rule.name, action=rule.action)
    return _rule_to_response(rule)


@router.put("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: UUID,
    payload: RuleUpdateRequest,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RuleResponse:
    rule = await session.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        rule.name = update_data["name"]
    if "description" in update_data:
        rule.description = update_data["description"]
    if "action" in update_data:
        rule.action = update_data["action"]
    if "enabled" in update_data:
        rule.enabled = update_data["enabled"]
    if any(k in update_data for k in ("type", "pattern", "severity")):
        rule.condition = payload.to_condition_updates(rule.condition or {})

    await session.commit()
    await session.refresh(rule)
    invalidate_rules_cache()

    logger.info("rule_updated", rule_id=str(rule.id), name=rule.name)
    return _rule_to_response(rule)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    rule = await session.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    await session.delete(rule)
    await session.commit()
    invalidate_rules_cache()

    logger.info("rule_deleted", rule_id=str(rule_id))
