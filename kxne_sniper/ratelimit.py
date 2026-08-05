"""Intelligent rate-limit interpreter: pauses the whole fleet with
Retry-After/exponential backoff when the API starts throttling."""
from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, cooldown_max: float = 30.0, scale: float = 1.5,
                 throttle_headers: list[str] | None = None):
        self.cooldown_max = float(cooldown_max)
        self.scale = float(scale)
        self.throttle_headers = list(throttle_headers or [])
        self.consecutive = 0
        self.cooldown_until = 0.0
        self.total_hits = 0

    def _retry_after(self, headers: dict) -> float | None:
        ra = headers.get("Retry-After") or headers.get("retry-after")
        if ra:
            try:
                return min(float(ra), self.cooldown_max)
            except (TypeError, ValueError):
                pass
        for name in self.throttle_headers:
            if name.lower() == "retry-after":
                continue
            value = headers.get(name) or headers.get(name.lower())
            if value is None:
                continue
            try:
                if int(value) <= 0:
                    return 0.5
            except (TypeError, ValueError):
                continue
        return None

    def is_throttled(self, status: int, headers: dict) -> bool:
        if status in (429, 503):
            return True
        return self._retry_after(headers) is not None

    def register_hit(self, status: int, headers: dict) -> float:
        """Record a throttle event, compute and arm backoff, return delay."""
        self.total_hits += 1
        self.consecutive += 1
        delay = self._retry_after(headers)
        if delay is None:
            delay = min(0.5 * (self.scale ** self.consecutive), self.cooldown_max)
        self.cooldown_until = time.monotonic() + delay
        return delay

    def register_ok(self) -> None:
        self.consecutive = 0

    async def wait_if_needed(self) -> None:
        """Block callers until any active cooldown expires."""
        while True:
            remaining = self.cooldown_until - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.2))
