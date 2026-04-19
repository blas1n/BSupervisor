"""Rule template packs API endpoints."""

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.core.rule_engine import invalidate_rules_cache
from bsupervisor.core.rule_packs import get_pack, list_packs
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.database import get_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["rule-packs"])


class PackSummary(BaseModel):
    id: str
    name: str
    description: str
    category: str
    rule_count: int


class PackRuleEntry(BaseModel):
    name: str
    description: str
    action: str


class PackDetail(BaseModel):
    id: str
    name: str
    description: str
    category: str
    rule_count: int
    rules: list[PackRuleEntry]


class InstallResponse(BaseModel):
    pack_id: str
    installed: int
    skipped: int


@router.get("/rule-packs", response_model=list[PackSummary])
async def list_rule_packs(
    _user: BSVibeUser = Depends(get_current_user),
) -> list[PackSummary]:
    return [PackSummary(**p) for p in list_packs()]


@router.get("/rule-packs/{pack_id}", response_model=PackDetail)
async def get_rule_pack(
    pack_id: str,
    _user: BSVibeUser = Depends(get_current_user),
) -> PackDetail:
    pack = get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Rule pack not found")
    rules = [PackRuleEntry(name=r["name"], description=r["description"], action=r["action"]) for r in pack["rules"]]
    return PackDetail(
        id=pack["id"],
        name=pack["name"],
        description=pack["description"],
        category=pack["category"],
        rule_count=pack["rule_count"],
        rules=rules,
    )


@router.post("/rule-packs/{pack_id}/install", response_model=InstallResponse)
async def install_rule_pack(
    pack_id: str,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InstallResponse:
    pack = get_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Rule pack not found")

    installed = 0
    skipped = 0

    for rule_data in pack["rules"]:
        # Check if rule already exists by name
        result = await session.execute(select(AuditRule).where(AuditRule.name == rule_data["name"]))
        if result.scalar_one_or_none() is not None:
            skipped += 1
            continue

        rule = AuditRule(
            name=rule_data["name"],
            description=rule_data["description"],
            condition=rule_data["condition"],
            action=rule_data["action"],
            enabled=True,
            built_in=True,
        )
        session.add(rule)
        installed += 1

    if installed > 0:
        await session.commit()
        invalidate_rules_cache()
        logger.info("rule_pack_installed", pack_id=pack_id, installed=installed, skipped=skipped)

    return InstallResponse(pack_id=pack_id, installed=installed, skipped=skipped)
