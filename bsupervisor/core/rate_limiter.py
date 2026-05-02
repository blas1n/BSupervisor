"""In-memory token-bucket rate limiter for `POST /api/events` (Audit §H6).

The limiter is intentionally simple — a per-key sliding window of timestamps —
so that a misconfiguration or a downstream cache outage cannot fail OPEN. It
runs in-process so every BSupervisor replica gets its own quota; we are not
trying to coordinate across replicas here, just to refuse a single source's
spike before it touches the rule engine + DB.

For a Phase A rollup this becomes a Redis-backed limiter inside
`bsvibe-fastapi`; until then we keep zero external dependencies.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class InMemoryRateLimiter:
    """Sliding-window per-key rate limiter, thread-safe."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests < 0:
            raise ValueError("max_requests must be >= 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max_requests = max_requests
        self._window_seconds = float(window_seconds)
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record a request for *key* and return True if it fits in the window."""
        if self._max_requests == 0:
            return False

        now = self._now()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket
            # Drop timestamps outside the window.
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_requests:
                return False
            bucket.append(now)
            return True

    @staticmethod
    def _now() -> float:
        return time.monotonic()
