"""Helpers that encrypt/decrypt the secret-bearing fields of ConnectionSettings.

The persisted JSON keeps the same shape as the unencrypted version, but every
sensitive string is wrapped with a small tagged payload so that:

1. Plaintext that pre-dates this change still decodes (backward-compatible read).
2. Encrypted values can be told apart from raw strings without ambiguity.
3. The DB never holds a usable credential after these helpers run.

We deliberately mark fields with the ``enc::v1::`` prefix instead of inventing
a separate column — this keeps the existing JSON schema and Alembic migrations
untouched. Phase 0/A can lift this into ``bsvibe-python`` once the surface
stabilises.
"""

from __future__ import annotations

import structlog

from bsupervisor.api.schemas import ConnectionSettings, IntegrationEntry
from bsupervisor.core.encryption import EncryptionManager

logger = structlog.get_logger(__name__)

_ENC_PREFIX = "enc::v1::"


def _encrypt_field(value: str, manager: EncryptionManager) -> str:
    if not value:
        return ""
    if value.startswith(_ENC_PREFIX):
        # Already encrypted — keep idempotent semantics so callers can re-PUT
        # the same payload they just GET'd without double-wrapping.
        return value
    return _ENC_PREFIX + manager.encrypt(value)


def _decrypt_field(value: str, manager: EncryptionManager) -> str:
    if not value:
        return ""
    if not value.startswith(_ENC_PREFIX):
        # Legacy plaintext (pre-encryption) — accept silently so existing rows
        # keep working until the next write encrypts them.
        return value
    payload = value[len(_ENC_PREFIX) :]
    try:
        return manager.decrypt(payload)
    except ValueError:
        # Bad key / tampered row — surface a redacted placeholder rather than
        # leaking plaintext or a stack trace through the API response.
        logger.warning("settings_secret_decrypt_failed")
        return ""


def encrypt_connections(payload: ConnectionSettings, manager: EncryptionManager) -> dict:
    """Return a dict suitable for persistence with all secret fields encrypted."""
    serialised = payload.model_dump()
    serialised["telegram_bot_token"] = _encrypt_field(serialised.get("telegram_bot_token", ""), manager)
    serialised["slack_webhook_url"] = _encrypt_field(serialised.get("slack_webhook_url", ""), manager)
    for integration in serialised.get("integrations", []):
        integration["api_key"] = _encrypt_field(integration.get("api_key", ""), manager)
    return serialised


def decrypt_connections(value: dict, manager: EncryptionManager) -> ConnectionSettings:
    """Inverse of :func:`encrypt_connections`."""
    if not isinstance(value, dict):  # pragma: no cover - defensive
        return ConnectionSettings()

    integrations_raw = value.get("integrations") or []
    integrations: list[IntegrationEntry] = []
    for entry in integrations_raw:
        integrations.append(
            IntegrationEntry(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                type=entry.get("type", ""),
                endpoint_url=entry.get("endpoint_url", ""),
                api_key=_decrypt_field(entry.get("api_key", ""), manager),
            )
        )

    return ConnectionSettings(
        integrations=integrations,
        telegram_bot_token=_decrypt_field(value.get("telegram_bot_token", ""), manager),
        slack_webhook_url=_decrypt_field(value.get("slack_webhook_url", ""), manager),
    )
