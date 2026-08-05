"""Discord webhook + Telegram Bot API notification hook."""
from __future__ import annotations

import time

import aiohttp

from .config import Config


class Notifier:
    def __init__(self, cfg: Config):
        self.discord_webhook = cfg.get("notification", "discord_webhook", "")
        self.telegram_token = cfg.get("notification", "telegram_token", "")
        self.telegram_chat_id = cfg.get("notification", "telegram_chat_id", "")
        self.platform = cfg.get("platform", "name", "platform")

    @property
    def enabled(self) -> bool:
        return bool(self.discord_webhook or (self.telegram_token and self.telegram_chat_id))

    async def send(self, title: str, message: str, color: int = 0x00FF00) -> None:
        if not self.enabled:
            return
        async with aiohttp.ClientSession() as session:
            if self.discord_webhook:
                try:
                    await session.post(self.discord_webhook, json={
                        "content": f"**{title}**\n{message}",
                        "embeds": [{
                            "title": title,
                            "description": message,
                            "color": color,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }],
                    })
                except (aiohttp.ClientError, OSError):
                    pass
            if self.telegram_token and self.telegram_chat_id:
                try:
                    url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                    await session.post(url, json={
                        "chat_id": self.telegram_chat_id,
                        "text": f"{title}\n{message}",
                        "disable_web_page_preview": True,
                    })
                except (aiohttp.ClientError, OSError):
                    pass

    async def on_claim_success(self, username: str, status: int = 200) -> None:
        await self.send(
            f"🎯 KXNE SNIPER — CLAIMED @{username}",
            f"**Username:** `{username}`\n**Platform:** {self.platform}\n"
            f"**Claim status:** HTTP {status}\n"
            f"**Time:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
            color=0x00FF00,
        )
