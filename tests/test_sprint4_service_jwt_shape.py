"""Sprint 4 — Phase 0 P0.7 service JWT shape pre-validation simulation.

Phase 0 (out-of-scope for Sprint 4 implementation) introduces
audience-scoped service JWTs issued by BSVibe-Auth, which BSGateway and
BSNexus will use to call BSupervisor's audit endpoints. The wire shape
is locked-in in ``BSVibe_Execution_Lockin.md §3 decision #16`` and
``§2 architectural shift #2``:

* ``aud`` claim: the receiving service's name (``aud: "bsupervisor"``)
* ``scope`` claim: a space- or comma-separated permission list,
  prefixed with the audience (``scope: "bsupervisor.read"`` or
  ``"bsupervisor.write"``)
* Subject (``sub``) is the calling service identifier
  (``sub: "bsgateway"`` / ``sub: "bsnexus"``)
* Issuer (``iss``) is BSVibe-Auth (``iss: "https://auth.bsvibe.dev"``)
* ``iat`` / ``exp`` standard JWT timing claims
* Algorithm: ES256 (matches the user JWT)

These tests do NOT mutate BSupervisor's auth provider — they simulate
what BSGateway / BSNexus will send and verify the *test fixture* itself
matches the documented shape so that the Phase 0 P0.7 PR can plug in a
production verifier with confidence. We assert:

1. The expected claim shape can be encoded and decoded losslessly.
2. The audience MUST equal ``bsupervisor`` for an inbound call to be
   acceptable to a future ``BsvibeServiceAuthProvider``; cross-service
   tokens (``aud: "bsage"``) are rejected.
3. The ``scope`` MUST contain the audience prefix; bare permissions
   (``scope: "read"``) are rejected as ambiguous.
4. ``exp`` is checked — expired tokens are rejected.
5. A token signed with the wrong key is rejected (signature check).

When P0.7 lands, a real ``BsvibeServiceAuthProvider`` plus a service
verification dependency will replace this simulation; until then the
test file documents the contract precisely.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest


# --- ES256 key pair generated at test startup -------------------------------
# We use cryptography's ec module to generate a fresh keypair per test run
# so we never check secrets into the repo.


def _generate_es256_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem) bytes for ES256."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


@pytest.fixture(scope="module")
def keypair() -> tuple[bytes, bytes]:
    return _generate_es256_keypair()


@pytest.fixture(scope="module")
def alt_keypair() -> tuple[bytes, bytes]:
    """A second keypair so we can simulate signature-mismatch attacks."""
    return _generate_es256_keypair()


def _service_jwt(
    private_pem: bytes,
    *,
    sub: str = "bsgateway",
    aud: str = "bsupervisor",
    scope: str = "bsupervisor.read",
    iss: str = "https://auth.bsvibe.dev",
    iat: int | None = None,
    exp: int | None = None,
    extra: dict | None = None,
) -> str:
    """Encode a service JWT in the shape Phase 0 P0.7 will mint."""
    now = int(time.time()) if iat is None else iat
    expires = now + 600 if exp is None else exp
    payload = {
        "sub": sub,
        "aud": aud,
        "scope": scope,
        "iss": iss,
        "iat": now,
        "exp": expires,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_pem, algorithm="ES256")


# ---------------------------------------------------------------------------
# Pre-validation contract
# ---------------------------------------------------------------------------


class TestServiceJwtRoundTrip:
    """Encode + decode preserves all required claims."""

    def test_round_trip_preserves_claims(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv)
        decoded = jwt.decode(
            token,
            pub,
            algorithms=["ES256"],
            audience="bsupervisor",
        )
        assert decoded["sub"] == "bsgateway"
        assert decoded["aud"] == "bsupervisor"
        assert decoded["scope"] == "bsupervisor.read"
        assert decoded["iss"] == "https://auth.bsvibe.dev"
        assert "iat" in decoded
        assert "exp" in decoded


class TestServiceJwtAudienceCheck:
    """Receiver MUST reject tokens scoped to a different audience."""

    def test_correct_audience_accepted(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv, aud="bsupervisor")
        decoded = jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")
        assert decoded["aud"] == "bsupervisor"

    def test_other_audience_rejected(self, keypair) -> None:
        """A token meant for bsage cannot authenticate to bsupervisor."""
        priv, pub = keypair
        token = _service_jwt(priv, aud="bsage")
        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")

    def test_missing_audience_rejected(self, keypair) -> None:
        priv, pub = keypair
        # Encode without aud claim manually.
        now = int(time.time())
        payload = {
            "sub": "bsgateway",
            "scope": "bsupervisor.read",
            "iss": "https://auth.bsvibe.dev",
            "iat": now,
            "exp": now + 600,
        }
        token = jwt.encode(payload, priv, algorithm="ES256")
        with pytest.raises((jwt.MissingRequiredClaimError, jwt.InvalidAudienceError)):
            jwt.decode(
                token,
                pub,
                algorithms=["ES256"],
                audience="bsupervisor",
                options={"require": ["aud"]},
            )


class TestServiceJwtScopeShape:
    """Receiver MUST require the audience-prefixed scope shape."""

    @staticmethod
    def _scope_matches(token_scope: str, audience: str, required_perm: str) -> bool:
        """Spec for the verifier coming in P0.7.

        A scope value is valid if it contains a token of the form
        ``<audience>.<required_perm>`` (space-separated, OAuth2-style).
        Bare permissions like ``read`` or cross-audience ones like
        ``bsage.read`` MUST NOT count.
        """
        wanted = f"{audience}.{required_perm}"
        return wanted in token_scope.split()

    def test_audience_prefixed_read_accepted(self) -> None:
        assert self._scope_matches("bsupervisor.read", "bsupervisor", "read") is True

    def test_audience_prefixed_write_accepted_alongside_read(self) -> None:
        assert self._scope_matches("bsupervisor.read bsupervisor.write", "bsupervisor", "write") is True

    def test_bare_permission_rejected(self) -> None:
        """A bare ``read`` is not enough — must be ``bsupervisor.read``."""
        assert self._scope_matches("read", "bsupervisor", "read") is False

    def test_other_audience_scope_rejected(self) -> None:
        """A token scoped to bsage MUST NOT pass bsupervisor.read."""
        assert self._scope_matches("bsage.read", "bsupervisor", "read") is False

    def test_substring_match_rejected(self) -> None:
        """``bsupervisor.readonly`` should NOT pass when ``bsupervisor.read`` is required."""
        assert self._scope_matches("bsupervisor.readonly", "bsupervisor", "read") is False


class TestServiceJwtExpiryEnforced:
    """Expired tokens MUST be rejected."""

    def test_expired_token_rejected(self, keypair) -> None:
        priv, pub = keypair
        past = int(time.time()) - 3600
        token = _service_jwt(priv, iat=past, exp=past + 60)  # expired 59 minutes ago
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")

    def test_fresh_token_accepted(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv)
        decoded = jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")
        # Token expiry is at least 60 seconds in the future.
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert decoded["exp"] >= future.timestamp() - 5  # tolerate skew


class TestServiceJwtSignatureCheck:
    """Tokens signed with the wrong key MUST be rejected."""

    def test_wrong_key_rejected(self, keypair, alt_keypair) -> None:
        priv_a, _ = keypair
        _, pub_b = alt_keypair  # verifier uses a *different* public key
        token = _service_jwt(priv_a)
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, pub_b, algorithms=["ES256"], audience="bsupervisor")

    def test_alg_none_rejected(self, keypair) -> None:
        """Receiver MUST NOT accept ``alg: none`` — even with a hand-crafted token."""
        _, pub = keypair
        # Build an unsigned ``alg=none`` token by hand. PyJWT will reject it
        # unless we explicitly pass ["none"] in algorithms — we don't, so this
        # documents that the Phase 0 verifier MUST keep ES256 in its list.
        forged = jwt.encode({"aud": "bsupervisor", "scope": "bsupervisor.read"}, key="", algorithm="none")
        with pytest.raises(jwt.InvalidAlgorithmError):
            jwt.decode(forged, pub, algorithms=["ES256"], audience="bsupervisor")


class TestServiceJwtSubjectIdentifiesCaller:
    """The ``sub`` claim is the calling service's name (used for audit trail)."""

    def test_subject_is_bsgateway_for_gateway_calls(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv, sub="bsgateway")
        decoded = jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")
        assert decoded["sub"] == "bsgateway"

    def test_subject_is_bsnexus_for_nexus_calls(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv, sub="bsnexus")
        decoded = jwt.decode(token, pub, algorithms=["ES256"], audience="bsupervisor")
        assert decoded["sub"] == "bsnexus"


class TestServiceJwtIssuerCheck:
    """Issuer MUST be BSVibe-Auth — receiver-side option."""

    def test_correct_issuer_decoded(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv, iss="https://auth.bsvibe.dev")
        decoded = jwt.decode(
            token,
            pub,
            algorithms=["ES256"],
            audience="bsupervisor",
            issuer="https://auth.bsvibe.dev",
        )
        assert decoded["iss"] == "https://auth.bsvibe.dev"

    def test_wrong_issuer_rejected(self, keypair) -> None:
        priv, pub = keypair
        token = _service_jwt(priv, iss="https://evil.example.com")
        with pytest.raises(jwt.InvalidIssuerError):
            jwt.decode(
                token,
                pub,
                algorithms=["ES256"],
                audience="bsupervisor",
                issuer="https://auth.bsvibe.dev",
            )
