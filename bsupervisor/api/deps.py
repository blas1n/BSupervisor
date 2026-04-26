"""Authentication dependencies for FastAPI endpoints.

Phase 0 P0.5 — these now come from the shared ``bsvibe-authz`` package
so all four BSVibe products converge on a single auth surface.

- :data:`CurrentUser` — Annotated type alias for an authenticated user.
- :func:`get_current_user` — FastAPI dep that decodes a user JWT.
- :class:`ServiceKeyAuth` — service-only verifier (audience-scoped JWTs).
- :data:`bsupervisor_service_auth` — pre-built ``ServiceKeyAuth("bsupervisor")``.

Routes use :func:`require_permission` (re-exported below) to plug into
OpenFGA. The ``permission`` argument is always
``bsupervisor.<resource>.<action>`` per Lockin §3 #16.
"""

from __future__ import annotations

import structlog
from bsvibe_authz import (
    CurrentUser,
    ServiceKey,
    ServiceKeyAuth,
)
from bsvibe_authz.deps import (
    get_active_tenant_id,
    get_current_user,
    get_openfga_client,
    get_permission_cache,
    get_settings_dep,
    require_permission,
)

logger = structlog.get_logger(__name__)

# Pre-built dependency — service JWTs MUST be scoped to ``aud="bsupervisor"``.
bsupervisor_service_auth = ServiceKeyAuth(audience="bsupervisor")

__all__ = [
    "CurrentUser",
    "ServiceKey",
    "ServiceKeyAuth",
    "bsupervisor_service_auth",
    "get_active_tenant_id",
    "get_current_user",
    "get_openfga_client",
    "get_permission_cache",
    "get_settings_dep",
    "require_permission",
]
