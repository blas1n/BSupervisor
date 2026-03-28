from fastapi import FastAPI

from bsupervisor.api.events import router as events_router

app = FastAPI(
    title="BSupervisor",
    description="AI agent auditing and safety system",
    version="0.1.0",
)

app.include_router(events_router)


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok"}
