"""Proxy pool + pooled aiohttp client. HTTP/S proxies rotate per request,
SOCKS5 proxies get a dedicated pooled session each."""
from __future__ import annotations

import asyncio
import random
from pathlib import Path

import aiohttp

try:
    from aiohttp_socks import ProxyConnector
    HAVE_SOCKS = True
except ImportError:
    HAVE_SOCKS = False


class ProxyPool:
    def __init__(self, path: str | None = None, mode: str = "random"):
        self.mode = mode if mode in ("random", "sequential") else "random"
        self.proxies: list[str] = []
        self._index = 0
        self._last: str | None = None
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "//")):
                if "://" not in line:
                    line = "http://" + line
                self.proxies.append(line)

    def __len__(self) -> int:
        return len(self.proxies)

    def next(self) -> str | None:
        if not self.proxies:
            return None
        if self.mode == "sequential":
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1
            self._last = proxy
            return proxy
        proxy = random.choice(self.proxies)
        self._last = proxy
        return proxy

    def rotate(self) -> str | None:
        """Pick a different proxy than the last one (used on rate-limit hits)."""
        if not self.proxies:
            return None
        if len(self.proxies) < 2:
            self._last = self.proxies[0]
            return self._last
        candidates = [p for p in self.proxies if p != self._last]
        self._last = random.choice(candidates)
        return self._last


class HttpClient:
    def __init__(self, pool: ProxyPool, timeout: float = 8.0,
                 conn_limit: int = 200, keepalive: float = 30.0, retries: int = 2):
        self.pool = pool
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.conn_limit = conn_limit
        self.keepalive = keepalive
        self.retries = retries
        self._direct: aiohttp.ClientSession | None = None
        self._socks: dict[str, aiohttp.ClientSession] = {}
        self._lock = asyncio.Lock()
        self._warned_no_socks = False

    async def request(self, method: str, url: str, *, headers: dict | None = None,
                      retries: int | None = None, read_limit: int = 8192, **kwargs):
        """Returns (status, headers_dict, body_bytes, proxy_used)."""
        retries = self.retries if retries is None else retries
        proxy = self.pool.next() if len(self.pool) else None
        last_err: Exception | None = None

        for attempt in range(retries + 1):
            try:
                if proxy and proxy.startswith(("socks4://", "socks5://", "socks5h://")):
                    if not HAVE_SOCKS:
                        if not self._warned_no_socks:
                            print("[yellow]aiohttp-socks missing — SOCKS5 proxies skipped, using direct connections[/]")
                            self._warned_no_socks = True
                        proxy = None
                    else:
                        session = await self._socks_session(proxy)
                        async with session.request(method, url, headers=headers,
                                                    timeout=self.timeout, **kwargs) as resp:
                            body = await resp.content.read(read_limit)
                            return resp.status, dict(resp.headers), body, proxy
                else:
                    session = await self._direct_session()
                    async with session.request(method, url, headers=headers, proxy=proxy,
                                               timeout=self.timeout, **kwargs) as resp:
                        body = await resp.content.read(read_limit)
                        return resp.status, dict(resp.headers), body, proxy
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                last_err = exc
                await asyncio.sleep(0.1 * (attempt + 1))
        raise last_err or aiohttp.ClientError("request failed")

    async def _direct_session(self) -> aiohttp.ClientSession:
        if self._direct is None or self._direct.closed:
            connector = aiohttp.TCPConnector(
                limit=self.conn_limit, limit_per_host=0,
                keepalive_timeout=self.keepalive, ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self._direct = aiohttp.ClientSession(connector=connector)
        return self._direct

    async def _socks_session(self, proxy: str) -> aiohttp.ClientSession:
        async with self._lock:
            session = self._socks.get(proxy)
            if session is None or session.closed:
                connector = ProxyConnector.from_url(proxy, limit=self.conn_limit)
                session = aiohttp.ClientSession(connector=connector)
                self._socks[proxy] = session
            return session

    async def close(self) -> None:
        if self._direct and not self._direct.closed:
            await self._direct.close()
        for session in self._socks.values():
            if not session.closed:
                await session.close()
        self._socks.clear()
