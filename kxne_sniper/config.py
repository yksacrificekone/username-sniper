"""Config loader with deep-merge so missing keys fall back to safe defaults."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "platform": {
        "name": "github",
        "check_url": "https://github.com/{username}",
        "check_method": "GET",
        "available_status": [404],
        "taken_status": [200],
        "custom_available_match": None,
        "claim": {"enabled": False, "endpoint": "", "method": "POST",
                  "headers": {}, "payload": {}, "success_status": [200, 201, 202]},
    },
    "network": {
        "proxy_file": "proxies.txt", "proxy_mode": "random",
        "rotate_on_rate_limit": True, "timeout": 8,
        "connections": 200, "keepalive": 30, "retries": 2,
    },
    "headers": {"session_token": "", "cookie": ""},
    "rate_limit": {"cooldown_max": 30, "scale": 1.5,
                   "throttle_headers": ["X-RateLimit-Remaining", "X-Throttle", "Retry-After"]},
    "sniper": {"interval": 0.35, "jitter": True},
    "notification": {"discord_webhook": "", "telegram_token": "", "telegram_chat_id": ""},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self.data = DEFAULT_CONFIG
        if self.path.exists():
            try:
                self.data = _deep_merge(DEFAULT_CONFIG, json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"[red]Invalid JSON in {self.path}: {exc}[/]") from exc

    def get(self, section: str, key: str | None = None, default=None):
        section_data = self.data.get(section, {})
        if key is None:
            return section_data
        return section_data.get(key, default)
