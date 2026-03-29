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


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

VALID_RULE_ACTIONS = {"block", "warn", "log"}


class StatusResponse(BaseModel):
    total_events_today: int
    blocked_count_today: int
    total_cost_today: str


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


class RuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    condition: dict
    action: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True

    model_config = {"extra": "forbid"}

    @classmethod
    def model_validate(cls, *args, **kwargs):
        obj = super().model_validate(*args, **kwargs)
        if obj.action not in VALID_RULE_ACTIONS:
            raise ValueError(f"action must be one of {VALID_RULE_ACTIONS}")
        return obj

    def model_post_init(self, __context) -> None:
        if self.action not in VALID_RULE_ACTIONS:
            raise ValueError(f"action must be one of {VALID_RULE_ACTIONS}")


class RuleUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, min_length=1)
    condition: dict | None = None
    action: str | None = Field(None, min_length=1, max_length=50)
    enabled: bool | None = None

    model_config = {"extra": "forbid"}

    def model_post_init(self, __context) -> None:
        if self.action is not None and self.action not in VALID_RULE_ACTIONS:
            raise ValueError(f"action must be one of {VALID_RULE_ACTIONS}")


class RuleResponse(BaseModel):
    id: str
    name: str
    description: str
    condition: dict
    action: str
    enabled: bool
