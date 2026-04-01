"""Settings API endpoints for managing connection configurations."""

import structlog
from bsvibe_auth import BSVibeUser
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import get_current_user
from bsupervisor.api.schemas import ConnectionSettings, SettingsResponse
from bsupervisor.models.database import get_session
from bsupervisor.models.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])

CONNECTIONS_KEY = "connections"


async def _get_connections(session: AsyncSession) -> ConnectionSettings:
    """Load connection settings from DB, or return defaults."""
    stmt = select(Settings).where(Settings.key == CONNECTIONS_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return ConnectionSettings()
    return ConnectionSettings(**row.value)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    connections = await _get_connections(session)
    return SettingsResponse(connections=connections)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: ConnectionSettings,
    _user: BSVibeUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    stmt = select(Settings).where(Settings.key == CONNECTIONS_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = Settings(
            key=CONNECTIONS_KEY,
            value=payload.model_dump(),
            description="Connection settings for external integrations",
        )
        session.add(row)
    else:
        row.value = payload.model_dump()

    await session.commit()
    logger.info("settings_updated", key=CONNECTIONS_KEY)
    return SettingsResponse(connections=payload)
