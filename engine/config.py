"""Config loader with deep merge into GitHub defaults."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULTS = {
    "platform": {
        "name": "github",
        "check_url": "https://github.com/{username}",
        "available_status": [404, 410],
        "taken_status": [200, 301, 302],
        "claim": {
            "enabled": True,
            "endpoint": "https://github.com/signup_check/username",
            "method": "POST",
            "referer": "https://github.com/signup",
            "headers": {
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            "payload": {"value": "{username}", "authenticity_token": ""},
            "success_status": [200],
            "success_match": '"available": true',
        },
    },
    "network": {
        "proxy_file": "proxies.txt", "proxy_mode": "random",
        "rotate_on_rate_limit": True, "timeout": 8,
        "connections": 250, "keepalive": 30, "retries": 2,
    },
    "headers": {"session_token": "", "cookie": ""},
    "rate_limit": {
        "cooldown_max": 30, "scale": 1.5,
        "throttle_headers": ["X-RateLimit-Remaining", "X-Throttle", "Retry-After"],
    },
    "sniper": {
        "default_min_len": 3,
        "default_max_len": 5,
        "default_charset": "letters_and_numbers",
        "default_auto_claim": False,
        "jitter": True,
    },
    "auth": {
        "enabled": True,
        "users_file": "users.json",
        "session_file": "session.json",
        "redeemed_file": "redeemed.json",
        "trial_minutes": 10,
        "trial_threads": 100,
        "premium_threads": 250,
    },
    "notification": {"discord_webhook": "", "telegram_token": "", "telegram_chat_id": ""},
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self.data = DEFAULTS
        if self.path.exists():
            try:
                self.data = _merge(DEFAULTS, json.loads(self.path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass

    def get(self, section: str, key=None, default=None):
        s = self.data.get(section, {})
        return s.get(key, default) if key is not None else s
