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

    pack_names = [r["name"] for r in pack["rules"]]
    existing = await session.execute(select(AuditRule.name).where(AuditRule.name.in_(pack_names)))
    existing_names = {row[0] for row in existing.all()}

    to_install = [r for r in pack["rules"] if r["name"] not in existing_names]
    for rule_data in to_install:
        session.add(
            AuditRule(
                name=rule_data["name"],
                description=rule_data["description"],
                condition=rule_data["condition"],
                action=rule_data["action"],
                enabled=True,
                built_in=True,
            )
        )

    installed = len(to_install)
    skipped = len(pack_names) - installed

    if installed > 0:
        await session.commit()
        invalidate_rules_cache()
        logger.info("rule_pack_installed", pack_id=pack_id, installed=installed, skipped=skipped)

    return InstallResponse(pack_id=pack_id, installed=installed, skipped=skipped)
