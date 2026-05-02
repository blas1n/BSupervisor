"""Tests for the in-memory rate limiter on POST /api/events (Audit §H6)."""

import pytest

from bsupervisor.core.rate_limiter import InMemoryRateLimiter


class TestInMemoryRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is True

    def test_blocks_requests_over_limit(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is False
        assert limiter.allow("client-a") is False

    def test_isolates_buckets_per_key(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-b") is True
        # Each key has its own quota.
        assert limiter.allow("client-a") is False
        assert limiter.allow("client-b") is False

    def test_window_advances(self):
        """Old timestamps drop out of the rolling window."""
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)

        timestamps = iter([0.0, 1.0, 70.0])

        def fake_now() -> float:
            return next(timestamps)

        limiter._now = fake_now  # type: ignore[assignment]
        assert limiter.allow("client-a") is True
        assert limiter.allow("client-a") is False
        assert limiter.allow("client-a") is True  # window has expired

    def test_zero_limit_blocks_everything(self):
        """A limit of 0 must fail-closed even on the first request."""
        limiter = InMemoryRateLimiter(max_requests=0, window_seconds=60)
        assert limiter.allow("client-a") is False

    def test_negative_limit_rejected(self):
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=-1, window_seconds=60)

    def test_zero_window_rejected(self):
        with pytest.raises(ValueError):
            InMemoryRateLimiter(max_requests=1, window_seconds=0)


class TestEventsRateLimitIntegration:
    """Audit §H6 — POST /api/events must reject excess traffic, fail-closed."""

    @pytest.fixture(autouse=True)
    def _tight_limit(self, monkeypatch):
        from bsupervisor.api import events as events_module

        # Inject a tight limiter for the duration of the test.
        original = events_module._events_rate_limiter
        events_module._events_rate_limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        yield
        events_module._events_rate_limiter = original

    async def test_blocks_after_quota_exhausted(self, client):
        payload = {
            "agent_id": "agent-rl",
            "source": "rate-limit-source",
            "event_type": "file_access",
            "action": "read",
            "target": "/tmp/x",
        }
        # Two go through, the third must be rejected with 429.
        r1 = await client.post("/api/events", json=payload)
        r2 = await client.post("/api/events", json=payload)
        r3 = await client.post("/api/events", json=payload)

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r3.status_code == 429
        body = r3.json()
        assert "rate" in body.get("detail", "").lower()

    async def test_other_source_unaffected(self, client):
        common_payload = {
            "agent_id": "agent-rl",
            "event_type": "file_access",
            "action": "read",
            "target": "/tmp/x",
        }
        # Exhaust source-A.
        for _ in range(2):
            resp = await client.post("/api/events", json={**common_payload, "source": "source-a"})
            assert resp.status_code == 201
        blocked = await client.post("/api/events", json={**common_payload, "source": "source-a"})
        assert blocked.status_code == 429

        # Source-B still has its own quota.
        ok = await client.post("/api/events", json={**common_payload, "source": "source-b"})
        assert ok.status_code == 201
