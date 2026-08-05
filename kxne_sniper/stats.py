"""Live counters shared between the engine and the dashboard."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Stats:
    total_checks: int = 0
    available: int = 0
    taken: int = 0
    license_label: str = "TRIAL"
    trial_remaining: float = 0.0
    skipped: int = 0
    errors: int = 0
    rate_limited: int = 0
    claims_attempted: int = 0
    claims_success: int = 0
    state: str = "IDLE"
    mode: str = ""
    target: str = ""
    pool_size: int = 0
    proxy_count: int = 0
    start_time: float = field(default_factory=time.monotonic)
    cps_window: deque = field(default_factory=lambda: deque(maxlen=400))
    events: deque = field(default_factory=lambda: deque(maxlen=30))

    def tick(self, outcome: str) -> None:
        self.total_checks += 1
        self.cps_window.append(time.monotonic())
        if outcome == "available":
            self.available += 1
        elif outcome == "taken":
            self.taken += 1
        elif outcome == "ratelimit":
            self.rate_limited += 1
            self.errors += 1
        else:
            self.errors += 1

    def cps(self) -> float:
        window = self.cps_window
        if len(window) < 2:
            return 0.0
        span = window[-1] - window[0]
        return (len(window) - 1) / span if span > 0 else 0.0

    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    def error_rate(self) -> float:
        return (self.errors / self.total_checks * 100.0) if self.total_checks else 0.0

    def add_event(self, text: str, style: str = "dim") -> None:
        self.events.append((time.strftime("%H:%M:%S"), text, style))
