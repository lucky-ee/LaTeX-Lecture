"""In-memory sliding-window rate limiter.

State lives in this process only: with several workers or replicas, each keeps
its own counts, so the effective limit is multiplied by the number of processes.
Move to a shared store (e.g. Redis) before scaling out.
"""

import time
from collections import deque
from collections.abc import Callable

_SWEEP_EVERY = 1000


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0

    def check(self, key: str) -> float | None:
        """Record a request from `key`. Returns None if allowed, else seconds until it would be."""
        if self.limit <= 0:
            return None
        now = self._clock()
        self._checks += 1
        if self._checks % _SWEEP_EVERY == 0:
            self._sweep(now)

        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return self.window - (now - hits[0])
        hits.append(now)
        return None

    def _sweep(self, now: float) -> None:
        """Forget clients with no requests inside the window, so memory doesn't grow forever."""
        stale = [key for key, hits in self._hits.items() if not hits or now - hits[-1] >= self.window]
        for key in stale:
            del self._hits[key]
