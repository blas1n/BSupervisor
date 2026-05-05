"""BSupervisor demo auth — verifies the demo JWT issued by /demo/session.

BSupervisor has no tenant scoping, so this dep mainly gates access. The
JWT carries a synthetic tenant_id that's the same for all visitors of a
given demo deployment.
"""

from __future__ import annotations

import os
import uuid

from bsvibe_demo import DemoJWTError, decode_demo_jwt
from fastapi import HTTPException, Request, status

DEMO_COOKIE_NAME = "bsvibe_demo_session"
DEMO_SHARED_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000d3000")


def get_demo_jwt_secret() -> str:
    secret = os.environ.get("DEMO_JWT_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DEMO_JWT_SECRET not configured on demo backend",
        )
    return secret


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get(DEMO_COOKIE_NAME)


async def require_demo_session(request: Request) -> uuid.UUID:
    """Verify the demo JWT and return the tenant_id (always shared for BSupervisor)."""
    secret = get_demo_jwt_secret()
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo session not started — POST /api/v1/demo/session first",
        )

    try:
        claims = decode_demo_jwt(token, secret=secret)
    except DemoJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid demo session: {e}",
        ) from e

    return claims.tenant_id


def block_writes_in_demo_mode() -> None:
    """Dependency to attach to write endpoints — returns 403 in demo mode."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Demo mode is read-only — sign up at https://bsvibe.dev to enable writes",
    )
