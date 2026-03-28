from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://bsupervisor:bsupervisor_dev@postgres:5432/bsupervisor"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Auth
    auth_provider: str = "local"
    jwt_secret: str = "change-me-in-production"

    # Cost alerts
    daily_cost_threshold_usd: str = "50.00"

    # Webhook (optional)
    webhook_url: str = ""

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
