"""Sprint 4 — integration regression for Sprint 1 H5 (encryption) + H8 (policy).

Both Sprint 1 hardenings touch the same code path (`api/settings.py` for
H5, `core/rule_engine.py` for H8). The unit suites cover each in
isolation; this Sprint 4 file exercises them together through the public
API surface so a refactor that drops one cannot pass review while the
other still has green unit tests.

Scenarios:
* Encrypt-at-rest + plaintext rotation: write a settings record under one
  encryption key, rotate the key, read back — must redact (not crash, not
  leak ciphertext) without pretending the credential is still usable.
* Policy + encryption together: a stored AuditRule with an unknown
  matcher key must NOT block events even when the secret pipeline is
  active. The two systems are layered and must not entangle.
* `enc::v1::` envelope is opaque to the policy engine — even if a rule
  somehow looks at the persisted secret JSON, an encrypted value must not
  match a substring rule that was authored against the plaintext.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bsupervisor.api import settings as settings_module
from bsupervisor.core.encryption import EncryptionManager
from bsupervisor.core.secret_vault import decrypt_connections, encrypt_connections
from bsupervisor.models.audit_rule import AuditRule
from bsupervisor.models.settings import Settings


@pytest.fixture(autouse=True)
def _reset_encryption_manager():
    """Reset the encryption singleton between tests."""
    original = settings_module._encryption_manager
    settings_module._encryption_manager = None
    yield
    settings_module._encryption_manager = original


def _payload(api_key: str = "sk-secret-policy", tg: str = "tg-secret"):
    return {
        "integrations": [
            {
                "id": "i1",
                "name": "Vendor",
                "type": "openai",
                "endpoint_url": "https://api.vendor",
                "api_key": api_key,
            }
        ],
        "telegram_bot_token": tg,
        "slack_webhook_url": "https://hooks.slack/x",
    }


class TestEncryptionPlusKeyRotation:
    async def test_rotated_key_redacts_without_crash(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        """If the encryption_key changes between writes, GET must redact, not 500."""
        # Write under key K1.
        with patch.object(settings_module.app_settings, "encryption_key", "k1-with-enough-length-bytes"):
            put = await client.put("/api/settings", json=_payload())
            assert put.status_code == 200

        # Reset manager so the next call instantiates with a new key.
        settings_module._encryption_manager = None

        # Read under key K2 (rotated). Must produce a 200 with empty secrets.
        with patch.object(settings_module.app_settings, "encryption_key", "k2-with-enough-length-bytes"):
            get = await client.get("/api/settings")
            assert get.status_code == 200
            conn = get.json()["connections"]
            assert conn["integrations"][0]["api_key"] == ""
            assert conn["telegram_bot_token"] == ""

    async def test_persisted_value_never_contains_plaintext(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        with patch.object(settings_module.app_settings, "encryption_key", "test-key-that-is-long-enough-bytes"):
            put = await client.put("/api/settings", json=_payload(api_key="sk-VERY-private-XYZ"))
            assert put.status_code == 200

        row = (await db_session.execute(select(Settings).where(Settings.key == "connections"))).scalar_one()
        flat = repr(row.value)
        assert "sk-VERY-private-XYZ" not in flat
        assert "tg-secret" not in flat


class TestPolicyDoesNotMatchEncryptedEnvelope:
    """A rule that looked at plaintext must not coincidentally match `enc::v1::`."""

    def test_enc_envelope_distinguishable(self) -> None:
        manager = EncryptionManager(key="rotation-test-key-with-length-bytes")
        encrypted = encrypt_connections(
            type("P", (), {"model_dump": lambda self: _payload()})(),  # type: ignore[arg-type]
            manager,
        )
        # Ensure each persisted secret is wrapped, distinguishable from raw text,
        # and the raw plaintext does not appear in the persisted blob.
        assert encrypted["telegram_bot_token"].startswith("enc::v1::")
        assert encrypted["integrations"][0]["api_key"].startswith("enc::v1::")
        assert "sk-secret-policy" not in repr(encrypted)

    def test_decrypted_value_round_trips(self) -> None:
        from bsupervisor.api.schemas import ConnectionSettings, IntegrationEntry

        manager = EncryptionManager(key="round-trip-key-with-enough-length")
        original = ConnectionSettings(
            integrations=[
                IntegrationEntry(
                    id="i1",
                    name="V",
                    type="openai",
                    endpoint_url="https://x",
                    api_key="sk-original-secret-99",
                )
            ],
            telegram_bot_token="tg-99",
            slack_webhook_url="",
        )
        wire = encrypt_connections(original, manager)
        restored = decrypt_connections(wire, manager)
        assert restored.integrations[0].api_key == "sk-original-secret-99"
        assert restored.telegram_bot_token == "tg-99"


class TestPolicyRuleWithEncryptionPipelineActive:
    """An H8 mis-keyed rule must not block events even when secrets are encrypted."""

    async def test_unknown_key_rule_never_blocks_events(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        # 1. Persist a settings row (touches encryption pipeline).
        with patch.object(settings_module.app_settings, "encryption_key", "policy-test-key-length-bytes"):
            put = await client.put("/api/settings", json=_payload(api_key="sk-leaky-secret"))
            assert put.status_code == 200

        # 2. Persist a misconfigured rule (typo in matcher key).
        rule = AuditRule(
            name="typo_rule_keys",
            description="Matcher key is misspelled — must not match",
            condition={"target_patten": "*"},  # typo
            action="block",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        # 3. Send an event — must NOT be blocked. Fail-closed for misconfig
        # means "no match", not "match everything".
        ev = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-policy",
                "source": "src",
                "event_type": "shell_exec",
                "action": "exec",
                "target": "ls -la",
            },
        )
        assert ev.status_code == 201
        body = ev.json()
        assert body["allowed"] is True

    async def test_rule_with_invalid_action_skipped_event_passes(
        self,
        client,
        db_session: AsyncSession,
    ) -> None:
        rule = AuditRule(
            name="rule_invalid_action",
            description="Persisted action outside whitelist",
            condition={"event_type": "shell_exec"},
            action="rm-rf-/",  # not in {block,warn,log}
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()

        ev = await client.post(
            "/api/events",
            json={
                "agent_id": "agent-X",
                "source": "src",
                "event_type": "shell_exec",
                "action": "exec",
                "target": "echo hello",
            },
        )
        assert ev.status_code == 201
        body = ev.json()
        # Built-in dangerous-shell rule may still match — for this test we
        # use a benign command so only the bad-action rule could match.
        assert body["allowed"] is True
        assert body.get("reason") is None


class TestEncryptionH5IdempotentRePut:
    """Re-PUT'ing the GET response (UI flow) must not double-wrap secrets."""

    async def test_re_put_does_not_double_encrypt(
        self,
        client,
    ) -> None:
        with patch.object(settings_module.app_settings, "encryption_key", "idempotent-test-key-bytes"):
            put1 = await client.put("/api/settings", json=_payload(api_key="sk-orig"))
            assert put1.status_code == 200

            get1 = await client.get("/api/settings")
            assert get1.status_code == 200
            # GET decrypts back to plaintext.
            assert get1.json()["connections"]["integrations"][0]["api_key"] == "sk-orig"

            # User edits another field and re-PUT's the same payload — the
            # re-encryption must not corrupt the previously stored secret.
            edited = get1.json()["connections"]
            put2 = await client.put("/api/settings", json=edited)
            assert put2.status_code == 200

            get2 = await client.get("/api/settings")
            assert get2.json()["connections"]["integrations"][0]["api_key"] == "sk-orig"
