"""Phase Audit Batch 2 — supervisor.* domain event emission glue.

BSupervisor adopts the producer-side contract documented in
``BSVibe_Audit_Design.md`` §3.1: domain writes append to a local
``audit_outbox`` table inside the request transaction, and a background
:class:`bsvibe_audit.OutboxRelay` ships them to BSVibe-Auth.

This module owns three things:

1. The module-level :class:`bsvibe_audit.AuditEmitter` singleton that
   every supervisor.* call site shares (``_supervisor_emitter``).
2. :func:`safe_emit` — a producer-side wrapper that swallows emit
   failures so the audit infra can never break a domain write. The
   sync-API contract for ``POST /api/events`` etc. depends on this.
3. :func:`build_relay` / :func:`make_actor` helpers used by
   :mod:`bsupervisor.main` and the four supervisor.* emit sites.

The schema integration (``register_audit_outbox_with(Base.metadata)``)
is wired in :mod:`bsupervisor.models` so a single Alembic
``target_metadata`` covers both BSupervisor's domain tables and the
shared outbox table — exactly what the bsvibe-audit contract requires.
"""

from __future__ import annotations

from typing import Any

import structlog
from bsvibe_audit import AuditActor, AuditEmitter, AuditSettings, OutboxRelay
from bsvibe_audit.events import AuditEventBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = structlog.get_logger(__name__)


# Singleton emitter shared by every supervisor.* call site. ``AuditEmitter``
# is intentionally tiny (no I/O, no commit) so it's safe to instantiate
# once at import time and reuse.
_supervisor_emitter: AuditEmitter = AuditEmitter()


def get_emitter() -> AuditEmitter:
    """Expose the shared emitter so DI / tests can override it."""

    return _supervisor_emitter


def make_actor(
    *,
    actor_type: str,
    actor_id: str,
    email: str | None = None,
    label: str | None = None,
) -> AuditActor:
    """Build an :class:`AuditActor` payload from a service principal.

    Centralised so every supervisor.* emit site uses the same shape.
    Service tokens default to ``actor_type='service'`` with ``actor_id``
    set to the JWT subject; user-driven endpoints (none today on
    supervisor.* paths) use ``actor_type='user'``.
    """

    return AuditActor(type=actor_type, id=actor_id, email=email, label=label)  # type: ignore[arg-type]


async def safe_emit(event: AuditEventBase, *, session: AsyncSession) -> None:
    """Emit an audit event without ever raising into the request handler.

    sync API regression guard: the four supervisor.* call sites all live
    on the hot path of ``POST /api/events`` / ``GET /api/anomalies``.
    Audit infra must never break those endpoints, so emit failures are
    logged and swallowed.
    """

    try:
        await _supervisor_emitter.emit(event, session=session)
    except Exception:  # noqa: BLE001 — audit must never break the domain write
        logger.warning(
            "supervisor_audit_emit_failed",
            event_type=getattr(event, "event_type", None),
            exc_info=True,
        )


def build_relay(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None,
    settings: AuditSettings | None = None,
) -> OutboxRelay:
    """Construct the :class:`OutboxRelay` from environment-based settings.

    The relay returned here is a no-op when ``BSVIBE_AUTH_AUDIT_URL`` is
    empty — that is the intended dev/CI default. Production deployments
    set the env vars through their normal pydantic-settings pipeline.
    """

    s = settings if settings is not None else AuditSettings()
    return OutboxRelay.from_settings(s, session_factory=session_factory)


def severity_from_explanation(explanation_json: dict[str, Any] | None) -> str:
    """Pull a severity string out of the ``explanation_json`` dict.

    Defaults to ``'medium'`` so the wire shape is non-empty. Used by
    both the rule.violated and alert.published emit sites so a single
    rule match yields consistent severity across both events.
    """

    if not explanation_json:
        return "medium"
    severity = explanation_json.get("severity")
    if isinstance(severity, str) and severity:
        return severity
    return "medium"


__all__ = [
    "AuditActor",
    "AuditSettings",
    "OutboxRelay",
    "build_relay",
    "get_emitter",
    "make_actor",
    "safe_emit",
    "severity_from_explanation",
    "_supervisor_emitter",
]
