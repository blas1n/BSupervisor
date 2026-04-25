from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_origins(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        return [o.strip() for o in raw if o and o.strip()]
    return [o.strip() for o in raw.split(",") if o.strip()]


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bsupervisor:bsupervisor_dev@postgres:5432/bsupervisor"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Auth
    auth_provider: str = "local"
    bsvibe_auth_url: str = "https://auth.bsvibe.dev"

    # Cost alerts
    daily_cost_threshold_usd: Decimal = Decimal("50.00")

    # Audit §M17 — daily budget shown on the costs dashboard. Was hardcoded to
    # $100 in `api/costs.py`, which made the budget gauge meaningless for any
    # tenant whose actual spend pattern differs. Now configurable.
    daily_budget_usd: Decimal = Field(default=Decimal("100.00"), ge=Decimal("0"))

    # Webhook (optional)
    webhook_url: str = ""

    # Encryption — used to protect stored credentials (integration api keys,
    # telegram tokens, slack webhook URLs). MUST be set in production.
    # The dev default is intentionally noisy so it shows up in audits.
    encryption_key: str = "dev-encryption-key-change-in-production-32b"

    # Rate limiting for POST /api/events (fail-closed in-memory limiter).
    # Per-source bucket; requests beyond the budget within a 60s window
    # return HTTP 429 without touching the rule engine or the database.
    events_rate_limit_per_minute: int = 600

    # Audit §M18 — CORS origins. Was previously read directly via
    # `os.environ.get` in `main.py`, bypassing pydantic-settings validation
    # and making the value invisible to `Settings()`. Now consolidated.
    # ``NoDecode`` keeps pydantic-settings from JSON-parsing the env value;
    # the field validator below splits on commas instead, matching the prior
    # behavior of ``os.environ.get(...).split(",")``.
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3500"])

    # Audit §M20 — DB connection pool sizing. SQLAlchemy defaults
    # (pool_size=5, max_overflow=10) are easily exhausted by long-running
    # report jobs running alongside dashboard polling. These knobs let us
    # tune per deployment without re-releasing.
    db_pool_size: int = Field(default=10, ge=0)
    db_max_overflow: int = Field(default=20, ge=0)
    db_pool_timeout: int = Field(default=30, ge=0)
    db_pool_recycle: int = Field(default=1800, ge=0)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _parse_cors(cls, value: str | list[str] | None) -> list[str]:
        if value is None or value == "":
            return ["http://localhost:3500"]
        return _split_origins(value)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
