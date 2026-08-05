"""Usage limits: free trial = 10 minutes + half the max threads.
Premium = unlimited time + full thread pool."""
from __future__ import annotations

import time


class LicenseManager:
    def __init__(self, cfg):
        self.trial_minutes = float(cfg.get("auth", "trial_minutes", 10))
        self.cap_fraction = float(cfg.get("auth", "thread_cap_fraction", 0.5))

    def effective_threads(self, requested: int, premium: bool) -> int:
        if premium:
            return max(1, int(requested))
        return max(1, int(requested * self.cap_fraction))

    def remaining_seconds(self, expires_ts: float | None, premium: bool) -> float | None:
        if premium or expires_ts is None:
            return None
        return max(0.0, expires_ts - time.time())
