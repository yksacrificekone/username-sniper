"""Core async engine: probe, checker mode, sniper mode, instant claim."""
from __future__ import annotations

import asyncio
import random
from pathlib import Path

from .config import Config
from .headers import random_headers
from .network import HttpClient, ProxyPool
from .notify import Notifier
from .ratelimit import RateLimiter
from .stats import Stats


from .filter import UsernameFilter  # add import

class SniperEngine:
    def __init__(self, cfg: Config, ui, notifier: Notifier,
                 license_provider=None, username_filter: UsernameFilter | None = None):
        self.cfg = cfg
        self.ui = ui
        self.notifier = notifier
        self.license_provider = license_provider
        self.username_filter = username_filter
        self.stats = Stats()
        ...
        self.http: HttpClient | None = None
        self.sem: asyncio.Semaphore | None = None
        self.rate_limiter = RateLimiter(
            cooldown_max=cfg.get("rate_limit", "cooldown_max", 30),
            scale=cfg.get("rate_limit", "scale", 1.5),
            throttle_headers=cfg.get("rate_limit", "throttle_headers", []),
        )
        self._results_file = None
        self._write_lock = asyncio.Lock()

    # ---- lifecycle -----------------------------------------------------
     async def _license_active(self) -> bool:
        if not self.license_provider:
            return True
        premium, remaining = self.license_provider()
        self.stats.license_label = "PREMIUM" if premium else "TRIAL"
        self.stats.trial_remaining = remaining or 0.0
        if premium:
            return True
        if remaining is not None and remaining <= 0:
            self.stats.state = "TRIAL EXPIRED"
            self.stats.add_event("Trial expired — premium required to continue", "bold red")
            return False
        return True
        )
        self.sem = asyncio.Semaphore(self.stats.pool_size)
        self.stats.add_event(
            f"Engine up — pool: {self.stats.pool_size} workers, "
            f"{self.stats.proxy_count} proxies", "cyan")

    async def close(self) -> None:
        if self.http:
            await self.http.close()
        if self._results_file:
            self._results_file.close()

    # ---- probing -------------------------------------------------------
    async def probe(self, username: str) -> str:
        """Returns 'available' | 'taken' | 'error'."""
        platform = self.cfg.get("platform", {})
        check_url = platform.get("check_url", "https://github.com/{username}").format(username=username)
        headers = random_headers(
            session_token=self.cfg.get("headers", "session_token", ""),
            cookie=self.cfg.get("headers", "cookie", ""),
        )
        try:
            async with self.sem:
                await self.rate_limiter.wait_if_needed()
                status, resp_headers, body, _proxy = await self.http.request(
                    "GET", check_url, headers=headers, allow_redirects=False)
        except Exception:
            self.stats.tick("error")
            return "error"

        if self.rate_limiter.is_throttled(status, resp_headers):
            delay = self.rate_limiter.register_hit(status, resp_headers)
            self.stats.tick("ratelimit")
            self.stats.add_event(f"HTTP {status} — backoff {delay:.1f}s", "yellow")
            if self.cfg.get("network", "rotate_on_rate_limit", True):
                self.http.pool.rotate()
            return "error"

        self.rate_limiter.register_ok()

        available_status = [int(x) for x in platform.get("available_status", [404])]
        taken_status = [int(x) for x in platform.get("taken_status", [200])]
        custom = platform.get("custom_available_match")

        if custom:
            available = custom in body[:8192].decode("utf-8", errors="ignore")
        elif status in available_status:
            available = True
        elif status in taken_status:
            available = False
        elif 400 <= status < 500:
            available = True          # 4xx on unknown resource = free name
        elif status < 400:
            available = False         # 2xx/3xx = name is taken/redirects
        else:
            self.stats.tick("error")
            return "error"

        self.stats.tick("available" if available else "taken")
        return "available" if available else "taken"

    # ---- checker mode --------------------------------------------------
    async def run_checker(self, usernames: list[str], out_path: str = "available.txt") -> None:
        self.stats.mode = "CHECKER"
        self.stats.state = "SEARCHING"
        self.stats.add_event(f"Checker mode — {len(usernames)} targets loaded", "cyan")

        self._results_file = Path(out_path).open("a", encoding="utf-8")

        async def check_one(username: str) -> None:
            result = await self.probe(username)
            if result == "available":
                async with self._write_lock:
                    self._results_file.write(username + "\n")
                    self._results_file.flush()
                self.stats.add_event(f"AVAILABLE → {username}", "green")

        batch = max(1, min(100, self.stats.pool_size * 4))
        for i in range(0, len(usernames), batch):
            chunk = usernames[i:i + batch]
            await asyncio.gather(*(check_one(u) for u in chunk))
            self.ui.refresh(self.stats)

        self.stats.state = "DONE"
        self.stats.add_event(
            f"Scan complete — {self.stats.available} available of {self.stats.total_checks} checked", "green")

    # ---- sniper mode ---------------------------------------------------
    async def run_sniper(self, username: str, interval: float) -> None:
        self.stats.mode = "SNIPER"
        self.stats.target = username
        self.stats.state = "SEARCHING"
        self.stats.add_event(f"Armed on @{username} — poll every {interval:.2f}s", "magenta")

        previous: str | None = None
        while True:
            result = await self.probe(username)
            self.ui.refresh(self.stats)

            if result == "available" and previous != "available":
                self.stats.state = "ATTEMPTING CLAIM"
                self.stats.add_event(f"@{username} freed — claiming NOW", "bold green")
                claim_status = await self.attempt_claim(username)
                if claim_status is not None and claim_status in (
                        self.cfg.get("platform", "claim", {}).get("success_status", [200, 201, 202])):
                    self.stats.claims_success += 1
                    self.stats.state = "SUCCESS"
                    self.stats.add_event(f"CLAIMED @{username} (HTTP {claim_status})", "bold green")
                    await self.notifier.on_claim_success(username, claim_status)
                else:
                    self.stats.state = "CLAIM FAILED"
                    self.stats.add_event(f"Claim returned HTTP {claim_status}", "bold red")
                self.ui.refresh(self.stats)
                break

            previous = result
            jitter = random.uniform(0.85, 1.15) if self.cfg.get("sniper", "jitter", True) else 1.0
            await asyncio.sleep(interval * jitter)

    # ---- claim ---------------------------------------------------------
    async def attempt_claim(self, username: str) -> int | None:
        """Fires the structured POST. Returns HTTP status (None on transport error)."""
        claim = self.cfg.get("platform", "claim", {}) or {}
        if not claim.get("enabled", False):
            self.stats.add_event("Claim disabled in config — skipping POST", "yellow")
            return None

        self.stats.claims_attempted += 1
        endpoint = claim.get("endpoint", "").format(username=username)
        method = claim.get("method", "POST")
        headers = random_headers(
            session_token=self.cfg.get("headers", "session_token", ""),
            cookie=self.cfg.get("headers", "cookie", ""),
            referer=claim.get("referer"),
        )
        headers.update({k: v.format(username=username) for k, v in claim.get("headers", {}).items()})
        payload = self._deep_format(claim.get("payload", {}), username)

        try:
            status, _resp_headers, body, _proxy = await self.http.request(
                method, endpoint, headers=headers, json=payload, retries=0)
        except Exception as exc:
            self.stats.add_event(f"Claim transport error: {exc}", "red")
            return None

        marker = claim.get("success_match")
        if marker and marker in body[:8192].decode("utf-8", errors="ignore"):
            return 200
        return status

    @staticmethod
    def _deep_format(obj, username: str):
        if isinstance(obj, str):
            return obj.format(username=username)
        if isinstance(obj, dict):
            return {k: SniperEngine._deep_format(v, username) for k, v in obj.items()}
        if isinstance(obj, list):
            return [SniperEngine._deep_format(v, username) for v in obj]
        return obj
