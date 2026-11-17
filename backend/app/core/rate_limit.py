"""Small in-process sliding-window rate limiter.

The API runs as a single Uvicorn process per container, so an in-memory
limiter is enough to stop brute-force and cost-abuse bursts without adding a
dependency. When the API is scaled horizontally, the same limits must also be
enforced at the reverse proxy (nginx ``limit_req``) or a shared store.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from collections.abc import Callable

from app.core.exceptions import AppException


class RateLimitExceededException(AppException):
    def __init__(self, *, retry_after_seconds: int, message: str) -> None:
        super().__init__(
            status_code=429,
            code="RATE_LIMIT_EXCEEDED",
            message=message,
            details={"retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.retry_after_seconds = retry_after_seconds


class SlidingWindowRateLimiter:
    """Counts events per key inside a rolling time window.

    The number of tracked keys is bounded (least recently used keys are
    evicted) so a flood of distinct keys cannot exhaust memory.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive.")

        self.limit = limit
        self.window_seconds = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._events: OrderedDict[str, deque[float]] = OrderedDict()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events.get(key)
        if events is None:
            return deque()

        threshold = now - self.window_seconds
        while events and events[0] <= threshold:
            events.popleft()

        if not events:
            self._events.pop(key, None)
        else:
            self._events.move_to_end(key)
        return events

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may be used again (0 if it is allowed now)."""
        now = self._clock()
        events = self._prune(key, now)
        if len(events) < self.limit:
            return 0
        wait = events[0] + self.window_seconds - now
        return max(1, math.ceil(wait))

    def hit(self, key: str) -> None:
        now = self._clock()
        events = self._prune(key, now)
        if not events:
            self._events[key] = events
        events.append(now)
        self._events.move_to_end(key)

        while len(self._events) > self._max_keys:
            self._events.popitem(last=False)

    def check_and_hit(self, key: str) -> int:
        """Record one event; return 0 when allowed, else seconds to wait."""
        wait = self.retry_after(key)
        if wait:
            return wait
        self.hit(key)
        return 0

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._events.clear()
        else:
            self._events.pop(key, None)
