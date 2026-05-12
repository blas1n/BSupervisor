"""Authentication dependencies for FastAPI endpoints.

Phase 5b — admin routes are gated by ``require_scope(...)`` (Phase 1
token-cutover catalog) instead of legacy OpenFGA tuples. The 3-way
dispatch (bootstrap → opaque → JWT) lives in ``bsvibe-authz``; this
module is the BSupervisor-specific wrapper that:

- re-exports ``CurrentUser``, ``ServiceKeyAuth``, etc. from bsvibe-authz so
  every router imports auth primitives from a single place.
- wraps ``require_scope`` with a closure tag (``_bsvibe_scope``) so the
  scope-matrix test (``tests/api/test_auth.py``) can introspect the gate.
- keeps ``require_permission`` re-exported for the rare OpenFGA-tuple use
  cases (currently none post-migration; retained as an escape hatch).
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
    require_permission,
)
from bsvibe_authz.deps import (
    require_scope as _authz_require_scope,
)

logger = structlog.get_logger(__name__)

# Pre-built dependency — service JWTs MUST be scoped to ``aud="supervisor"``.
# Round 5 Step 3: flipped from legacy ``bsupervisor`` to the MCP-aligned
# bare-name audience ``supervisor``. Step 1 of the cutover (bsvibe-authz
# 0.9.0) accepts both old + new audiences in pydantic validation; Step 5
# tightens to MCP-only.
bsupervisor_service_auth = ServiceKeyAuth(audience="supervisor")


def require_scope(scope: str) -> Callable[..., Awaitable[None]]:
    """Wrap ``bsvibe_authz.require_scope`` and tag the closure.

    Phase 1 token cutover gates admin routes on scope strings carried by
    bootstrap (``"*"``) and opaque (``supervisor:<resource>:<action>``)
    tokens. The ``_bsvibe_scope`` tag lets the scope-matrix test pin the
    catalog so future refactors cannot silently downgrade a gate.
    """
    dep = _authz_require_scope(scope)
    dep._bsvibe_scope = scope  # type: ignore[attr-defined]
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
    "require_permission",
    "require_scope",
]
