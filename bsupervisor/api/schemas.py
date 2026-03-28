"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EventRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=255)
    source: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=255)
    target: str = Field(..., min_length=1, max_length=1024)
    metadata: dict | None = None
    timestamp: datetime | None = None

    model_config = {"extra": "forbid"}


class EventResponse(BaseModel):
    event_id: str
    allowed: bool
    reason: str | None = None


class CostRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=255)
    model: str = Field(..., min_length=1, max_length=255)
    tokens_in: int = Field(..., ge=0)
    tokens_out: int = Field(..., ge=0)
    cost_usd: Decimal = Field(...)

    model_config = {"extra": "forbid"}


class CostResponse(BaseModel):
    cost_id: str
    agent_id: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: str
