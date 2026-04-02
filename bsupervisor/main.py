"""BSupervisor — AI agent auditing and safety system."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from bsupervisor.api.costs import router as costs_router
from bsupervisor.api.events import router as events_router
from bsupervisor.api.reports import router as reports_router
from bsupervisor.api.rules import router as rules_router
from bsupervisor.api.settings import router as settings_router
from bsupervisor.api.status import router as status_router
from bsupervisor.core.seed_rules import seed_default_rules
from bsupervisor.models.database import async_session_factory, engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_startup", database_engine=engine.url.render_as_string(hide_password=True))

    async with async_session_factory() as session:
        seeded = await seed_default_rules(session)
        if seeded:
            logger.info("default_rules_seeded", count=seeded)

    yield
    await engine.dispose()
    logger.info("app_shutdown")


app = FastAPI(
    title="BSupervisor",
    description="AI agent auditing and safety system",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(events_router)
app.include_router(costs_router)
app.include_router(reports_router)
app.include_router(rules_router)
app.include_router(settings_router)
app.include_router(status_router)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok"}
