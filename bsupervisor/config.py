from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
