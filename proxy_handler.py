"""
proxy_handler.py
Loads proxies.txt, rotates HTTP/S and SOCKS5 proxies per-request.
"""

import random
import threading
from pathlib import Path


class ProxyHandler:
    def __init__(self, proxy_file: str = "proxies.txt", mode: str = "rotate"):
        self._proxies: list[str] = []
        self._index: int = 0
        self._lock = threading.Lock()
        self._mode = mode  # "rotate" | "random"
        self._load(proxy_file)

    # ------------------------------------------------------------------ #
    def _load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # normalise bare host:port to http://
                if not line.startswith(("http://", "https://", "socks5://")):
                    line = f"http://{line}"
                self._proxies.append(line)

    # ------------------------------------------------------------------ #
    def get(self) -> dict | None:
        """Return an aiohttp-compatible proxy dict, or None for direct."""
        if not self._proxies:
            return None
        if self._mode == "random":
            proxy_url = random.choice(self._proxies)
        else:
            with self._lock:
                proxy_url = self._proxies[self._index % len(self._proxies)]
                self._index += 1
        return proxy_url  # aiohttp accepts a plain URL string as `proxy=`

    # ------------------------------------------------------------------ #
    def count(self) -> int:
        return len(self._proxies)

    def has_proxies(self) -> bool:
        return bool(self._proxies)
