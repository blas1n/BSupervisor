"""Authentication dependencies for FastAPI endpoints.

Phase 2a — user-facing routes are gated by ``require_permission(...)``
(permissive no-op when ``openfga_api_url`` is empty, true on prod product
backends today) and mutation/admin-config routes by ``require_admin()``
(real role-claim check). The 2-way dispatch (JWT verify → PAT-JWT
introspection fallback; the legacy ``bsv_sk_*`` opaque branch was
retired in bsvibe-authz 1.3.0) lives in ``bsvibe-authz``; this module
is the BSupervisor-specific wrapper that:

- re-exports ``CurrentUser``, ``ServiceKeyAuth``, etc. from bsvibe-authz so
  every router imports auth primitives from a single place.
- wraps ``require_permission`` / ``require_admin`` with closure tags
  (``_bsvibe_permission`` / ``_bsvibe_admin``) so the auth-matrix test
  (``tests/api/test_auth.py``) can introspect each gate and pin the
  catalog — future refactors cannot silently downgrade a gate.

The legacy ``require_scope`` gate was removed in bsvibe-authz 2.0.0
(Tier 5 Phase 4); all routes are on ``require_permission`` / OpenFGA.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

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
)
from bsvibe_authz.deps import (
    require_admin as _authz_require_admin,
)
from bsvibe_authz.deps import (
    require_permission as _authz_require_permission,
)

logger = structlog.get_logger(__name__)

# Pre-built dependency — service JWTs MUST be scoped to ``aud="bsupervisor"``.
# Phase 2a: bsvibe-authz 1.2.0 flipped ServiceAudience/SERVICE_AUDIENCES to
# the bs-prefixed names; the audience literal here follows suit.
bsupervisor_service_auth = ServiceKeyAuth(audience="bsupervisor")


def require_permission(permission: str, **kwargs: object) -> Callable[..., Awaitable[None]]:
    """Wrap ``bsvibe_authz.require_permission`` and tag the closure.

    Phase 2a — user-facing read/list routes gate on a
    ``<product>.<resource>.<action>`` permission. In permissive mode
    (``openfga_api_url`` empty, true on prod product backends) this is a
    no-op pass for any authenticated user. The ``_bsvibe_permission`` tag
    lets the auth-matrix test pin the catalog.
    """
    dep = _authz_require_permission(permission, **kwargs)  # type: ignore[arg-type]
    dep._bsvibe_permission = permission  # type: ignore[attr-defined]
    return dep


def require_admin(**kwargs: object) -> Callable[..., Awaitable[None]]:
    """Wrap ``bsvibe_authz.require_admin`` and tag the closure.

    Phase 2a — mutation / admin-config routes gate on the JWT ``role``
    claim (``owner`` / ``admin`` pass; demo + service principals pass).
    This is a *real* enforced check in production. The ``_bsvibe_admin``
    tag lets the auth-matrix test pin the catalog.
    """
    dep = _authz_require_admin(**kwargs)  # type: ignore[arg-type]
    dep._bsvibe_admin = True  # type: ignore[attr-defined]
    return dep


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
    "require_admin",
    "require_permission",
]
