"""Authentication dependencies for FastAPI endpoints."""

from __future__ import annotations

import structlog
from bsvibe_auth import SupabaseAuthProvider
from bsvibe_auth.fastapi import create_auth_dependency

from bsupervisor.config import settings

logger = structlog.get_logger(__name__)


def _build_auth_provider() -> SupabaseAuthProvider:
    """Create an AuthProvider from application settings."""
    return SupabaseAuthProvider(
        jwt_secret=settings.jwt_secret,
        supabase_url=settings.supabase_url or None,
    )


_auth_provider = _build_auth_provider()

get_current_user = create_auth_dependency(_auth_provider)
