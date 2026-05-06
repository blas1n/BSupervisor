"""BSupervisor — AI agent auditing and safety system."""

from contextlib import asynccontextmanager

import structlog
from bsvibe_core import configure_logging
from bsvibe_fastapi import (
    RequestIdMiddleware,
    add_cors_middleware,
    make_health_router,
)
from fastapi import FastAPI
from sqlalchemy import text

from bsupervisor.api.anomalies import router as anomalies_router
from bsupervisor.api.costs import router as costs_router
from bsupervisor.api.events import router as events_router
from bsupervisor.api.incidents import router as incidents_router
from bsupervisor.api.reports import router as reports_router
from bsupervisor.api.rule_packs import router as rule_packs_router
from bsupervisor.api.rules import router as rules_router
from bsupervisor.api.settings import router as settings_router
from bsupervisor.api.status import router as status_router
from bsupervisor.config import settings
from bsupervisor.core.audit import build_relay
from bsupervisor.core.seed_rules import seed_default_rules
from bsupervisor.models.database import async_session_factory, engine

# Phase A — structured JSON logging via shared bsvibe-core helper.
configure_logging(level="info" if not settings.debug else "debug", service_name="bsupervisor")

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_startup", database_engine=engine.url.render_as_string(hide_password=True))

    async with async_session_factory() as session:
        seeded = await seed_default_rules(session)
        if seeded:
            logger.info("default_rules_seeded", count=seeded)

        # In demo mode, also pre-populate the shared demo tenant with
        # audit events + incidents so the visitor's dashboard renders
        # immediately. Idempotent via a sentinel-row check.
        if is_demo_mode():
            from bsupervisor.demo.seed import seed_demo_data  # noqa: PLC0415

            seeded_demo = await seed_demo_data(session)
            if seeded_demo:
                logger.info("demo_data_seeded", events=seeded_demo)

    # Phase Audit Batch 2 — start the shared bsvibe-audit OutboxRelay so
    # supervisor.* events queued in the per-request transaction get
    # shipped to BSVibe-Auth. The relay is a no-op when
    # ``BSVIBE_AUTH_AUDIT_URL`` is empty (dev / CI default).
    audit_relay = build_relay(session_factory=async_session_factory)
    await audit_relay.start()
    logger.info("audit_relay_started", running=audit_relay.is_running())

    try:
        yield
    finally:
        await audit_relay.stop()
        await engine.dispose()
        logger.info("app_shutdown")


app = FastAPI(
    title="BSupervisor",
    description="AI agent auditing and safety system",
    version="0.1.0",
    lifespan=lifespan,
)

# RequestIdMiddleware must wrap the rest so every log line emitted
# inside a handler carries ``request_id=<value>`` via structlog
# contextvars.
app.add_middleware(RequestIdMiddleware)

# Audit §M18 — CORS origins flow through pydantic-settings (was reading
# ``os.environ.get`` directly, bypassing validation). Phase A: delegated
# to the shared ``bsvibe_fastapi.add_cors_middleware`` helper.
add_cors_middleware(app, settings)

app.include_router(events_router)
app.include_router(incidents_router)
app.include_router(anomalies_router)
app.include_router(costs_router)
app.include_router(reports_router)
app.include_router(rules_router)
app.include_router(rule_packs_router)
app.include_router(settings_router)
app.include_router(status_router)


# ─── Demo mode (separate deployment, BSVIBE_DEMO_MODE=true) ──────────
from bsvibe_demo import is_demo_mode  # noqa: E402

if is_demo_mode():
    from bsupervisor.demo.router import demo_router  # noqa: E402

    app.include_router(demo_router)


# Phase A health/readiness — uses ``bsvibe_fastapi.make_health_router``
# under the BSupervisor ``/api`` prefix. The legacy ``/api/health/ready``
# route is kept as a thin alias so existing probes / dashboards do not
# break; ``/api/health/deps`` is the preferred shared name.
async def _health_deps() -> dict[str, str]:
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"database": "ok"}
    except Exception:
        logger.error("readiness_check_failed", exc_info=True)
        return {"database": "error"}


_health_router = make_health_router(deps_callable=_health_deps)
app.include_router(_health_router, prefix="/api")


@app.get("/api/health/ready")
async def readiness_check():
    """Legacy alias for :py:func:`make_health_router`'s ``/health/deps``.

    Kept so existing load-balancer probes and dashboards do not 404
    while the new ``/api/health/deps`` shape rolls out.
    """
    from fastapi.responses import JSONResponse

    deps = await _health_deps()
    all_ok = all(value == "ok" for value in deps.values())
    if all_ok:
        return JSONResponse(status_code=200, content={"status": "ready", **deps})
    return JSONResponse(status_code=503, content={"status": "not_ready", **deps})
