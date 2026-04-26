"""Settings API endpoints for managing connection configurations."""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api.deps import CurrentUser, require_permission
from bsupervisor.api.schemas import ConnectionSettings, SettingsResponse
from bsupervisor.config import settings as app_settings
from bsupervisor.core.encryption import EncryptionManager
from bsupervisor.core.secret_vault import decrypt_connections, encrypt_connections
from bsupervisor.models.database import get_session
from bsupervisor.models.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["settings"])

CONNECTIONS_KEY = "connections"

_encryption_manager: EncryptionManager | None = None


def get_encryption_manager() -> EncryptionManager:
    """Return the process-wide :class:`EncryptionManager`, instantiated on first use."""
    global _encryption_manager  # noqa: PLW0603
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager(key=app_settings.encryption_key)
    return _encryption_manager


async def _get_connections(session: AsyncSession) -> ConnectionSettings:
    """Load connection settings from DB, or return defaults."""
    stmt = select(Settings).where(Settings.key == CONNECTIONS_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return ConnectionSettings()
    return decrypt_connections(row.value, get_encryption_manager())


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    _user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.config.read")),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    connections = await _get_connections(session)
    return SettingsResponse(connections=connections)


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    payload: ConnectionSettings,
    _user: CurrentUser,
    _allowed: None = Depends(require_permission("bsupervisor.config.write")),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    stmt = select(Settings).where(Settings.key == CONNECTIONS_KEY)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    encrypted_value = encrypt_connections(payload, get_encryption_manager())

    if row is None:
        row = Settings(
            key=CONNECTIONS_KEY,
            value=encrypted_value,
            description="Connection settings for external integrations",
        )
        session.add(row)
    else:
        row.value = encrypted_value

    await session.commit()
    logger.info("settings_updated", key=CONNECTIONS_KEY)
    return SettingsResponse(connections=payload)
