"""Encryption manager for protecting secrets at rest.

Uses HMAC-SHA256 in counter mode as a stream cipher with HMAC authentication
for field-level encryption of sensitive data (API keys, webhook tokens, etc.).

Stdlib-only (no external `cryptography` dependency required) so the BSupervisor
service stays minimal. For higher-sensitivity workloads or Phase A consolidation
this can be swapped out for `cryptography.fernet.Fernet` without changing the
public surface (`encrypt` / `decrypt` / `mask`).

The same on-the-wire format as BSNexus's `EncryptionManager` is used so that
shared utilities can be extracted into `bsvibe-python` later without a
re-encryption migration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

# Minimum key length to refuse trivially weak keys at startup.
_MIN_KEY_LENGTH = 16


class EncryptionManager:
    """Symmetric authenticated encryption for short secrets.

    The supplied `key` is hashed once to a 32-byte master key. Every encrypted
    value carries a fresh 16-byte IV and a 32-byte HMAC tag, so identical
    plaintexts encrypt to distinct ciphertexts and any tamper attempt raises
    ``ValueError`` on decryption.
    """

    _IV_LEN = 16
    _TAG_LEN = 32

    def __init__(self, key: str) -> None:
        if not key or len(key) < _MIN_KEY_LENGTH:
            raise ValueError(
                f"Encryption key must be at least {_MIN_KEY_LENGTH} characters (got {len(key) if key else 0})"
            )
        self._key = hashlib.sha256(key.encode("utf-8")).digest()

    # ---- Public API ----------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return a urlsafe base64 token."""
        iv = os.urandom(self._IV_LEN)
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext = self._xor_stream(plaintext_bytes, iv)
        tag = hmac.new(self._key, iv + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(iv + ciphertext + tag).decode("ascii")

    def decrypt(self, token: str) -> str:
        """Decrypt a token previously produced by :meth:`encrypt`.

        Raises ``ValueError`` if the token is malformed, truncated, tampered
        with, or encrypted with a different key.
        """
        try:
            combined = base64.urlsafe_b64decode(token.encode("ascii"))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("Invalid encrypted token format") from exc

        if len(combined) < self._IV_LEN + self._TAG_LEN:
            raise ValueError("Invalid encrypted token: too short")

        iv = combined[: self._IV_LEN]
        tag = combined[-self._TAG_LEN :]
        ciphertext = combined[self._IV_LEN : -self._TAG_LEN]

        expected_tag = hmac.new(self._key, iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Decryption failed: integrity check did not match")

        return self._xor_stream(ciphertext, iv).decode("utf-8")

    def mask(self, value: str, *, visible_prefix: int = 3, visible_suffix: int = 4) -> str:
        """Return a redacted form of *value* that is safe to log or return in API responses."""
        if not value:
            return ""
        if len(value) <= visible_prefix + visible_suffix:
            return "*" * len(value)
        masked_len = len(value) - visible_prefix - visible_suffix
        return value[:visible_prefix] + "*" * masked_len + value[-visible_suffix:]

    # ---- Helpers -------------------------------------------------------

    def _xor_stream(self, data: bytes, iv: bytes) -> bytes:
        """XOR encrypt/decrypt using HMAC-SHA256 keystream blocks."""
        result = bytearray(len(data))
        block_count = (len(data) + 31) // 32
        for i in range(block_count):
            counter = i.to_bytes(4, "big")
            block = hmac.new(self._key, iv + counter, hashlib.sha256).digest()
            start = i * 32
            end = min(start + 32, len(data))
            for j in range(end - start):
                result[start + j] = data[start + j] ^ block[j]
        return bytes(result)

    @staticmethod
    def generate_key() -> str:
        """Generate a fresh 64-character hex key suitable for ``ENCRYPTION_KEY``."""
        return secrets.token_hex(32)
