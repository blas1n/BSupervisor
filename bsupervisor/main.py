"""BSupervisor — AI agent auditing and safety system."""

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from bsupervisor.api.costs import router as costs_router
from bsupervisor.api.events import router as events_router
from bsupervisor.api.incidents import router as incidents_router
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

_cors_origins = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3500").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(events_router)
app.include_router(incidents_router)
app.include_router(costs_router)
app.include_router(reports_router)
app.include_router(rules_router)
app.include_router(settings_router)
app.include_router(status_router)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/api/health/ready")
async def readiness_check() -> JSONResponse:
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "database": "ok"},
        )
    except Exception:
        logger.error("readiness_check_failed", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "error"},
        )
