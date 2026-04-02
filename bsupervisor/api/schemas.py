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


class EventListItem(BaseModel):
    id: str
    timestamp: str
    agent_id: str
    action: str
    severity: str
    rule_name: str | None = None
    details: str | None = None


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


class CostAgentEntry(BaseModel):
    agent_id: str
    agent_name: str
    requests: int
    tokens: int
    cost: str
    percentage: float
    daily_costs: list[float]


class CostDataResponse(BaseModel):
    budget: str
    spent: str
    budget_percentage: float
    trend: list[dict]
    agents: list[CostAgentEntry]
    anomalies: list[str]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

VALID_RULE_ACTIONS = {"block", "warn", "log"}


class StatusResponse(BaseModel):
    events_today: int
    violations: int
    blocked_actions: int
    cost_total: str


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------


class RuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(default="pattern", min_length=1, max_length=50)
    pattern: str = Field(default="", max_length=1024)
    severity: str = Field(default="medium", min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=2000)
    enabled: bool = True

    model_config = {"extra": "forbid"}

    def model_post_init(self, __context) -> None:
        if self.action not in VALID_RULE_ACTIONS:
            raise ValueError(f"action must be one of {VALID_RULE_ACTIONS}")

    def to_condition(self) -> dict:
        return {"type": self.type, "pattern": self.pattern, "severity": self.severity}


class RuleUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    type: str | None = Field(None, min_length=1, max_length=50)
    pattern: str | None = Field(None, max_length=1024)
    severity: str | None = Field(None, min_length=1, max_length=50)
    action: str | None = Field(None, min_length=1, max_length=50)
    description: str | None = None
    enabled: bool | None = None

    model_config = {"extra": "forbid"}

    def model_post_init(self, __context) -> None:
        if self.action is not None and self.action not in VALID_RULE_ACTIONS:
            raise ValueError(f"action must be one of {VALID_RULE_ACTIONS}")

    def to_condition_updates(self, existing: dict) -> dict:
        cond = dict(existing)
        if self.type is not None:
            cond["type"] = self.type
        if self.pattern is not None:
            cond["pattern"] = self.pattern
        if self.severity is not None:
            cond["severity"] = self.severity
        return cond


class RuleResponse(BaseModel):
    id: str
    name: str
    type: str
    pattern: str
    severity: str
    action: str
    description: str
    enabled: bool
    built_in: bool
    hit_count: int


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


VALID_INTEGRATION_TYPES = {"bsnexus", "bsgateway", "bsage", "openai", "anthropic", "custom"}


class IntegrationEntry(BaseModel):
    id: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=50)
    endpoint_url: str = Field(default="", max_length=2048)
    api_key: str = Field(default="", max_length=2048)

    model_config = {"extra": "forbid"}

    def model_post_init(self, __context) -> None:
        if self.type not in VALID_INTEGRATION_TYPES:
            raise ValueError(f"type must be one of {VALID_INTEGRATION_TYPES}")


class ConnectionSettings(BaseModel):
    integrations: list[IntegrationEntry] = Field(default_factory=list)
    telegram_bot_token: str = ""
    slack_webhook_url: str = ""

    model_config = {"extra": "forbid"}


class SettingsResponse(BaseModel):
    connections: ConnectionSettings
