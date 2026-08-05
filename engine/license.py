"""Usage limits: TRIAL = 10 minutes + 100 workers. PREMIUM = unlimited + 250 workers."""
from __future__ import annotations

import time


class LicenseManager:
    def __init__(self, cfg):
        self.trial_minutes = float(cfg.get("auth", "trial_minutes", 10))
        self.trial_threads = int(cfg.get("auth", "trial_threads", 100))
        self.premium_threads = int(cfg.get("auth", "premium_threads", 250))

    def effective_threads(self, requested: int, premium: bool) -> int:
        cap = self.premium_threads if premium else self.trial_threads
        return max(1, min(int(requested), cap))

    def remaining_seconds(self, expires_ts: float | None, premium: bool) -> float | None:
        if premium or expires_ts is None:
            return None
        return max(0.0, expires_ts - time.time())
