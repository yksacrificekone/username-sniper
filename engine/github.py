"""GitHub combo sniper engine.

Generates RANDOM username combos (min_len..max_len chars from the chosen
charset) and probes github.com/{username} as fast as the license allows.
404 on the profile = name is FREE -> logged, optionally auto-claimed.
TRIAL: 100 workers · PREMIUM: 250 workers."""
from __future__ import annotations

import asyncio
import random
import re
import string
import time
from collections import deque
from dataclasses import dataclass, field

from .config import Config
from .headers import random_headers
from .network import HttpClient, ProxyPool
from .notify import Notifier
from .ratelimit import RateLimiter

CHARSETS = {
    "letters": string.ascii_lowercase,
    "letters_and_numbers": string.ascii_lowercase + string.digits,
    # GitHub rules: no underscores, hyphens allowed but never leading/trailing/double
    "all": string.ascii_lowercase + string.digits + "-",
}

_VALID = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9]))*[a-z0-9]$")


def random_combo(min_len: int, max_len: int, charset: str) -> str:
    length = random.randint(min_len, max_len)
    return "".join(random.choice(charset) for _ in range(length))


@dataclass
class Stats:
    mode: str = "IDLE"
    state: str = "IDLE"
    total_checks: int = 0
    available: int = 0
    taken: int = 0
    errors: int = 0
    rate_limited: int = 0
    invalid: int = 0
    claims_attempted: int = 0
    claims_success: int = 0
    workers: int = 0
    busy: int = 0
    proxies: int = 0
    cps: float = 0.0
    elapsed: float = 0.0
    error_rate: float = 0.0
    license: str = "TRIAL"
    time_left: float = 0.0
    running: bool = False
    started: float = field(default_factory=time.monotonic)
    events: list = field(default_factory=list)
    available_names: list = field(default_factory=list)
    _window: deque = field(default_factory=lambda: deque(maxlen=800))

    def add_event(self, msg: str, kind: str = "info") -> None:
        self.events.append([time.strftime("%H:%M:%S"), msg, kind])
        del self.events[:-40]

    def tick(self, outcome: str) -> None:
        self.total_checks += 1
        self._window.append(time.monotonic())
        if outcome == "available":
            self.available += 1
        elif outcome == "taken":
            self.taken += 1
        elif outcome == "ratelimit":
            self.rate_limited += 1
            self.errors += 1
        else:
            self.errors += 1
        w = self._window
        if len(w) >= 2:
            span = w[-1] - w[0]
            self.cps = (len(w) - 1) / span if span > 0 else 0.0
        self.elapsed = time.monotonic() - self.started
        self.error_rate = (self.errors / self.total_checks * 100.0) if self.total_checks else 0.0

    def snapshot(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class GitHubEngine:
    def __init__(self, cfg: Config, license_provider=None):
        self.cfg = cfg
        self.stats = Stats()
        self.license_provider = license_provider
        self.notifier = Notifier(cfg)
        self.http: HttpClient | None = None
        self.sem: asyncio.Semaphore | None = None
        self.rate_limiter = RateLimiter(
            cooldown_max=cfg.get("rate_limit", "cooldown_max", 30),
            scale=cfg.get("rate_limit", "scale", 1.5),
            throttle_headers=cfg.get("rate_limit", "throttle_headers", []),
        )
        self._stop = asyncio.Event()

    # ---- lifecycle -----------------------------------------------------
    async def start(self) -> None:
        net = self.cfg.get("network", {})
        pool = ProxyPool(net.get("proxy_file", "proxies.txt"), net.get("proxy_mode", "random"))
        self.stats.workers = int(net.get("connections", 250))
        self.stats.proxies = len(pool)
        self.http = HttpClient(
            pool, timeout=float(net.get("timeout", 8)),
            conn_limit=self.stats.workers,
            keepalive=float(net.get("keepalive", 30)),
            retries=int(net.get("retries", 2)),
        )
        self.sem = asyncio.Semaphore(self.stats.workers)

    async def close(self) -> None:
        if self.http:
            await self.http.close()

    def stop(self) -> None:
        self._stop.set()

    # ---- license -------------------------------------------------------
    async def _license_ok(self) -> bool:
        if not self.license_provider:
            return True
        premium, remaining = self.license_provider()
        self.stats.license = "PREMIUM" if premium else "TRIAL"
        self.stats.time_left = remaining or 0.0
        if premium:
            return True
        if remaining is not None and remaining <= 0:
            self.stats.state = "TRIAL EXPIRED"
            self.stats.add_event("Trial expired — premium required", "bad")
            return False
        return True

    # ---- probe ---------------------------------------------------------
    async def probe(self, username: str) -> str:
        """Returns 'available' | 'taken' | 'error'."""
        platform = self.cfg.get("platform", {})
        url = platform.get("check_url", "https://github.com/{username}").format(username=username)
        headers = random_headers(
            session_token=self.cfg.get("headers", "session_token", ""),
            cookie=self.cfg.get("headers", "cookie", ""),
        )
        try:
            async with self.sem:
                await self.rate_limiter.wait_if_needed()
                status, resp_headers, _body, _proxy = await self.http.request(
                    "GET", url, headers=headers, allow_redirects=False)
        except Exception:
            self.stats.tick("error")
            return "error"

        if self.rate_limiter.is_throttled(status, resp_headers):
            delay = self.rate_limiter.register_hit(status, resp_headers)
            self.stats.tick("ratelimit")
            self.stats.add_event(f"HTTP {status} — backoff {delay:.1f}s", "warn")
            if self.cfg.get("network", "rotate_on_rate_limit", True):
                self.http.pool.rotate()
            return "error"

        self.rate_limiter.register_ok()

        available_status = [int(x) for x in platform.get("available_status", [404, 410])]
        taken_status = [int(x) for x in platform.get("taken_status", [200, 301, 302])]
        if status in available_status:
            available = True
        elif status in taken_status:
            available = False
        else:
            self.stats.tick("error")
            return "error"

        self.stats.tick("available" if available else "taken")
        return "available" if available else "taken"

    # ---- claim ---------------------------------------------------------
    async def claim(self, username: str) -> int | None:
        """Fires the GitHub signup-check POST. Returns HTTP status."""
        claim = self.cfg.get("platform", "claim", {}) or {}
        if not claim.get("enabled", True):
            self.stats.add_event("Claim disabled in config", "warn")
            return None
        self.stats.claims_attempted += 1
        endpoint = claim.get("endpoint", "").format(username=username)
        headers = random_headers(
            session_token=self.cfg.get("headers", "session_token", ""),
            cookie=self.cfg.get("headers", "cookie", ""),
            referer=claim.get("referer"),
        )
        headers.update({k: str(v).format(username=username) for k, v in claim.get("headers", {}).items()})
        payload = self._fmt(claim.get("payload", {}), username)
        try:
            status, _h, body, _p = await self.http.request(
                claim.get("method", "POST"), endpoint, headers=headers, json=payload, retries=0)
        except Exception as exc:
            self.stats.add_event(f"Claim transport error: {exc}", "bad")
            return None
        marker = claim.get("success_match")
        if marker:
            return 200 if marker in body[:8192].decode("utf-8", errors="ignore") else None
        return status

    @staticmethod
    def _fmt(obj, username: str):
        if isinstance(obj, str):
            return obj.format(username=username)
        if isinstance(obj, dict):
            return {k: GitHubEngine._fmt(v, username) for k, v in obj.items()}
        if isinstance(obj, list):
            return [GitHubEngine._fmt(v, username) for v in obj]
        return obj

    # ---- combo sniper --------------------------------------------------
    async def run_sniper(self, settings: dict) -> None:
        self._stop.clear()
        self.stats.mode = "COMBO SNIPER"
        self.stats.state = "SEARCHING"
        self.stats.running = True

        min_len = max(1, min(39, int(settings.get("min_len", 3))))
        max_len = max(min_len, min(39, int(settings.get("max_len", 5))))
        charset = CHARSETS.get(settings.get("charset", "letters_and_numbers"),
                               CHARSETS["letters_and_numbers"])
        auto_claim = bool(settings.get("auto_claim", False))
        label = settings.get("charset", "letters_and_numbers")

        self.stats.add_event(
            f"Combos {min_len}-{max_len} chars · charset: {label} · "
            f"workers: {self.stats.workers} · auto-claim: {auto_claim}", "info")

        def next_name() -> str:
            while True:
                name = random_combo(min_len, max_len, charset)
                if _VALID.match(name):
                    return name
                self.stats.invalid += 1

        async def worker(_idx: int) -> None:
            while not self._stop.is_set():
                if not await self._license_ok():
                    return
                name = next_name()
                result = await self.probe(name)
                if result == "available":
                    self.stats.available_names.append(name)
                    self.stats.add_event(f"AVAILABLE → {name}", "good")
                    if auto_claim:
                        status = await self.claim(name)
                        if status is not None and status in (
                                [int(x) for x in
                                 ((self.cfg.get("platform", "claim", {}) or {}).get("success_status", [200]))]):
                            self.stats.claims_success += 1
                            self.stats.state = "SUCCESS"
                            self.stats.add_event(f"CLAIMED @{name} (HTTP {status})", "good")
                            await self.notifier.on_claim_success(name, status)

        await asyncio.gather(*(worker(i) for i in range(self.stats.workers)))
        self.stats.busy = 0
        self.stats.state = "STOPPED" if self._stop.is_set() else "DONE"
        self.stats.running = False
        self.stats.add_event(
            f"Run ended — {self.stats.available} available / {self.stats.total_checks} checked", "info")
