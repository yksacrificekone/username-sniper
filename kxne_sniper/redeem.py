"""Premium redemption. Keys simulate payment methods:
Discord Nitro, Discord accounts, Robux, Roblox accounts, YouTube accounts,
TikTok accounts. Keys are one-time-use, stored in redeemed.json."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

TYPE_PATTERNS = {
    "nitro": re.compile(r"^NITRO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
    "discord_account": re.compile(r"^DCACC-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
    "robux": re.compile(r"^RBX-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
    "roblox_account": re.compile(r"^RBXACC-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
    "youtube_account": re.compile(r"^YTACC-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
    "tiktok_account": re.compile(r"^TTACC-[A-Z0-9]{4}-[A-Z0-9]{4}$", re.I),
}
TYPE_DAYS = {
    "nitro": 30, "discord_account": 30, "robux": 30,
    "roblox_account": 30, "youtube_account": 30, "tiktok_account": 30,
}


class RedemptionManager:
    def __init__(self, redeemed_file: str = "redeemed.json"):
        self.file = Path(redeemed_file)
        self.redeemed: dict = {}
        if self.file.exists():
            try:
                self.redeemed = json.loads(self.file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.redeemed = {}

    def redeem(self, username: str, code: str, ptype: str) -> tuple[bool, str]:
        ptype = ptype.lower()
        code = code.strip()
        key = f"{ptype}:{code.upper()}"
        if key in self.redeemed:
            return False, "code already used"
        pattern = TYPE_PATTERNS.get(ptype)
        if pattern is None or not pattern.match(code):
            return False, f"invalid {ptype} code format"
        days = TYPE_DAYS.get(ptype, 30)
        self.redeemed[key] = {"user": username, "when": time.time(), "days": days}
        self.file.write_text(json.dumps(self.redeemed, indent=2), encoding="utf-8")
        return True, f"premium granted: +{days} days"
