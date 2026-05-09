"""BSupervisor settings — Phase A consumer of shared bsvibe-* packages.

The core wiring is delegated to:

* :class:`bsvibe_fastapi.FastApiSettings` — CORS allow-origins / methods /
  headers (``Annotated[list[str], NoDecode]`` + ``parse_csv_list``).
* :class:`bsvibe_sqlalchemy.DatabaseSettings` — ``database_url`` plus the
  five connection-pool knobs + ``db_pool_pre_ping`` + ``db_echo``.
* :class:`bsvibe_alerts.AlertSettings` — multi-channel alert routing
  (telegram / slack / structlog) with severity-based fan-out.

BSupervisor-specific fields (auth provider URL, daily budget, encryption
key, rate-limit budget, webhook URL, etc.) live on the concrete
:class:`Settings` subclass below.
"""

from decimal import Decimal

from bsvibe_alerts import AlertSettings
from bsvibe_fastapi import FastApiSettings
from bsvibe_sqlalchemy import DatabaseSettings
from pydantic import AliasChoices, Field
from pydantic_settings import SettingsConfigDict


class Settings(FastApiSettings, DatabaseSettings, AlertSettings):
    """BSupervisor settings — composes the three shared mixins.

    The CSV-list CORS contract (Audit §M18) is inherited from
    ``FastApiSettings``; the five DB-pool knobs (Audit §M20) come from
    ``DatabaseSettings``; the telegram/slack/structlog routing table
    (Phase A consumer migration) comes from ``AlertSettings``.
    """

    # DatabaseSettings supplies ``database_url``; we override the default
    # to the BSupervisor production-ish dev value.
    database_url: str = "postgresql+asyncpg://bsupervisor:bsupervisor_dev@postgres:5432/bsupervisor"

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Auth
    auth_provider: str = "local"
    bsvibe_auth_url: str = "https://auth.bsvibe.dev"

    # OAuth2 client_credentials grant — see BSVibe-Auth `/api/oauth/token`.
    # Optional; needed only when BSupervisor initiates outbound service calls
    # (currently receiver-only, but reserved for future cross-product flows).
    bsvibe_client_id: str = ""
    bsvibe_client_secret: str = ""

    # Phase 1 token-cutover hooks. bootstrap_token_hash is sha256(bsv_admin_…)
    # hex; raw bootstrap is never stored. introspection_url enables the
    # RFC 7662 opaque-token path; client_id/secret are the Basic-auth pair
    # on the central auth.bsvibe.dev /api/tokens/introspect endpoint.
    #
    # ``BSV_*``-prefixed aliases mirror the alias set on
    # :class:`bsvibe_authz.Settings` (bsvibe-python PR #21) so a single
    # ``.env`` configures the lib + product layers consistently. Note:
    # BSupervisor currently consumes the *lib* AuthzSettings directly via
    # ``bsvibe_authz.deps.get_settings`` (see ``bsupervisor/mcp/transport.py``
    # ``_build_introspection_inputs``); these declarations on the product
    # Settings keep the field surface aligned for any future wire that
    # would forward them into a per-product builder.
    bootstrap_token_hash: str = Field(
        default="",
        validation_alias=AliasChoices("bootstrap_token_hash", "bsv_bootstrap_token_hash"),
    )
    introspection_url: str = Field(
        default="",
        validation_alias=AliasChoices("introspection_url", "bsv_introspection_url"),
    )
    introspection_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("introspection_client_id", "bsv_introspection_client_id"),
    )
    introspection_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices(
            "introspection_client_secret", "bsv_introspection_client_secret"
        ),
    )

    # User-JWT verification — declared on the product Settings for
    # consistency with the lib Settings (which reads it from env via its
    # own AliasChoices). BSupervisor doesn't currently forward this into
    # a per-product authz builder; the lib reads ``USER_JWT_JWKS_URL``
    # directly. See handoff §사전 발견 #6.
    user_jwt_jwks_url: str = ""

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

    # ``model_config`` keeps the BSupervisor-specific ``.env`` opt-in; the
    # shared mixins default to ``env_file=None`` so deployments must opt in.
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
