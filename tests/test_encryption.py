"""Tests for the encryption manager (S1-2 secret encryption at rest)."""

import pytest

from bsupervisor.core.encryption import EncryptionManager


class TestEncryptionRoundTrip:
    def test_round_trip_returns_original(self):
        manager = EncryptionManager(key="a-test-key-32-bytes-or-more-characters")
        plaintext = "sk-secret-api-key-12345"
        ciphertext = manager.encrypt(plaintext)
        assert ciphertext != plaintext
        assert manager.decrypt(ciphertext) == plaintext

    def test_round_trip_empty_string(self):
        manager = EncryptionManager(key="another-test-key-with-enough-length")
        assert manager.decrypt(manager.encrypt("")) == ""

    def test_round_trip_unicode(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        plaintext = "토큰-한글-😀-utf8"
        assert manager.decrypt(manager.encrypt(plaintext)) == plaintext

    def test_ciphertext_changes_per_call(self):
        """Same plaintext should encrypt to different ciphertexts (random IV)."""
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        plaintext = "secret"
        c1 = manager.encrypt(plaintext)
        c2 = manager.encrypt(plaintext)
        assert c1 != c2
        assert manager.decrypt(c1) == plaintext
        assert manager.decrypt(c2) == plaintext


class TestEncryptionTamperDetection:
    def test_tampered_ciphertext_fails(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        ciphertext = manager.encrypt("plaintext")
        # Flip a byte in the middle of the ciphertext
        tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
        with pytest.raises(ValueError):
            manager.decrypt(tampered)

    def test_truncated_ciphertext_fails(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        with pytest.raises(ValueError):
            manager.decrypt("short")

    def test_garbage_input_fails(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        with pytest.raises(ValueError):
            manager.decrypt("@@@not-valid-base64@@@!!!")


class TestEncryptionKeyRotation:
    def test_different_keys_cannot_decrypt(self):
        manager_a = EncryptionManager(key="key-aaaa-with-sufficient-length-bytes")
        manager_b = EncryptionManager(key="key-bbbb-with-sufficient-length-bytes")
        ciphertext = manager_a.encrypt("secret")
        with pytest.raises(ValueError):
            manager_b.decrypt(ciphertext)


class TestEncryptionMasking:
    def test_mask_short_value(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        assert manager.mask("abc") == "***"

    def test_mask_typical_api_key(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        masked = manager.mask("sk-1234567890abcdef")
        assert masked.startswith("sk-")
        assert masked.endswith("cdef")
        assert "*" in masked

    def test_mask_empty_string(self):
        manager = EncryptionManager(key="test-key-with-sufficient-length-bytes")
        assert manager.mask("") == ""


class TestEncryptionRequiresKey:
    def test_empty_key_rejected(self):
        with pytest.raises(ValueError):
            EncryptionManager(key="")

    def test_short_key_rejected(self):
        with pytest.raises(ValueError):
            EncryptionManager(key="too-short")


class TestSecretVaultHelpers:
    """Round-trip and idempotency tests for `secret_vault`."""

    def _payload(self):
        from bsupervisor.api.schemas import ConnectionSettings, IntegrationEntry

        return ConnectionSettings(
            integrations=[
                IntegrationEntry(
                    id="i1",
                    name="Vendor",
                    type="openai",
                    endpoint_url="https://api.vendor",
                    api_key="sk-secret-321",
                ),
            ],
            telegram_bot_token="tg-secret",
            slack_webhook_url="https://hooks.slack/x",
        )

    def test_encrypt_then_decrypt_round_trip(self):
        from bsupervisor.core.secret_vault import decrypt_connections, encrypt_connections

        manager = EncryptionManager(key="round-trip-test-key-with-length")
        original = self._payload()
        encrypted = encrypt_connections(original, manager)

        # Encrypted dict must NOT contain raw secrets.
        flat = str(encrypted)
        assert "sk-secret-321" not in flat
        assert "tg-secret" not in flat

        restored = decrypt_connections(encrypted, manager)
        assert restored.integrations[0].api_key == "sk-secret-321"
        assert restored.telegram_bot_token == "tg-secret"
        assert restored.slack_webhook_url == "https://hooks.slack/x"

    def test_encrypt_idempotent_for_already_encrypted(self):
        from bsupervisor.core.secret_vault import encrypt_connections

        manager = EncryptionManager(key="idempotent-test-key-with-enough-length")
        original = self._payload()
        once = encrypt_connections(original, manager)

        # Re-wrap an already-encrypted payload — still readable, still single-wrapped.
        from bsupervisor.api.schemas import ConnectionSettings, IntegrationEntry

        wrapped_again = encrypt_connections(
            ConnectionSettings(
                integrations=[
                    IntegrationEntry(
                        id="i1",
                        name="Vendor",
                        type="openai",
                        endpoint_url="https://api.vendor",
                        api_key=once["integrations"][0]["api_key"],
                    ),
                ],
                telegram_bot_token=once["telegram_bot_token"],
                slack_webhook_url=once["slack_webhook_url"],
            ),
            manager,
        )
        assert wrapped_again["integrations"][0]["api_key"] == once["integrations"][0]["api_key"]
        assert wrapped_again["telegram_bot_token"] == once["telegram_bot_token"]

    def test_decrypt_returns_empty_when_key_changed(self):
        """A rotated/wrong key must NOT crash the read endpoint or leak ciphertext."""
        from bsupervisor.core.secret_vault import decrypt_connections, encrypt_connections

        original_manager = EncryptionManager(key="original-key-with-enough-length-bytes")
        rotated_manager = EncryptionManager(key="rotated-key-with-enough-length-bytes")
        encrypted = encrypt_connections(self._payload(), original_manager)

        restored = decrypt_connections(encrypted, rotated_manager)
        # Failure mode: redacted blanks instead of ciphertext or stack trace.
        assert restored.integrations[0].api_key == ""
        assert restored.telegram_bot_token == ""
