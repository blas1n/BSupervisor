"""BSupervisor — AI agent auditing and safety system."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from bsupervisor.api.costs import router as costs_router
from bsupervisor.api.events import router as events_router
from bsupervisor.api.reports import router as reports_router
from bsupervisor.api.rules import router as rules_router
from bsupervisor.api.status import router as status_router
from bsupervisor.models.database import engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_startup", database_engine=engine.url.render_as_string(hide_password=True))
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
app.include_router(status_router)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok"}
