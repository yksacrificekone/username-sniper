"""
platforms/base.py
Abstract contract every platform module must satisfy.
"""

from abc import ABC, abstractmethod
import aiohttp


class BasePlatform(ABC):
    NAME: str = ""
    COLOR: str = "#ffffff"

    def __init__(self, account_cfg: dict):
        self.account_cfg = account_cfg

    # ------------------------------------------------------------------ #
    @abstractmethod
    async def is_available(
        self,
        username: str,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
    ) -> bool:
        """Return True if the username is available on this platform."""
        ...

    @abstractmethod
    async def claim(
        self,
        username: str,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
    ) -> bool:
        """Attempt to claim the username. Return True on success."""
        ...

    # ------------------------------------------------------------------ #
    def build_headers(self, extra: dict | None = None) -> dict:
        base = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
        if extra:
            base.update(extra)
        return base
