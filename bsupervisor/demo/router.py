"""BSupervisor demo HTTP endpoints — issue + verify demo session JWT.

BSupervisor's data is shared across visitors (no per-tenant scoping in
its schema). The demo session is purely an auth token so the frontend can
call protected endpoints; no DB writes happen here.
"""

from __future__ import annotations

from bsvibe_demo import mint_demo_jwt
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from bsupervisor.demo.auth import (
    DEMO_COOKIE_NAME,
    DEMO_SHARED_TENANT_ID,
    get_demo_jwt_secret,
)

DEMO_SESSION_TTL_SECONDS = 7200

demo_router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class DemoSessionResponse(BaseModel):
    tenant_id: str
    token: str
    expires_in: int


@demo_router.post(
    "/session",
    status_code=status.HTTP_201_CREATED,
    response_model=DemoSessionResponse,
    summary="Issue a demo session JWT",
)
async def post_demo_session(
    response: Response,
    secret: str = Depends(get_demo_jwt_secret),
) -> DemoSessionResponse:
    """Issue a JWT for the shared demo tenant.

    Unlike BSGateway / BSNexus, no DB write happens — BSupervisor's demo
    data is pre-seeded at container startup and shared across visitors.
    """
    token = mint_demo_jwt(
        DEMO_SHARED_TENANT_ID,
        secret=secret,
        ttl_seconds=DEMO_SESSION_TTL_SECONDS,
    )

    response.set_cookie(
        key=DEMO_COOKIE_NAME,
        value=token,
        max_age=DEMO_SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
    )

    return DemoSessionResponse(
        tenant_id=str(DEMO_SHARED_TENANT_ID),
        token=token,
        expires_in=DEMO_SESSION_TTL_SECONDS,
    )
