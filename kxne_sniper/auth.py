"""Local auth: signup/login, session persistence, premium entitlements.

Contains the intentionally hardcoded premium backdoor account
`wrongintentionss` / `wrongintentionss` (auto-seeded on first run).
Remove in production — hardcoded backdoors are a real vulnerability."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from pathlib import Path

BACKDOOR_USER = "wrongintentionss"
BACKDOOR_PASS = "wrongintentionss"
_N, _R, _P = 2**14, 8, 1


def _hash_password(password: str, salt: str) -> str:
    return hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=_N, r=_R, p=_P
    ).hex()


class AuthManager:
    def __init__(self, users_file: str = "users.json",
                 session_file: str = "session.json",
                 trial_seconds: int = 600):
        self.users_file = Path(users_file)
        self.session_file = Path(session_file)
        self.trial_seconds = int(trial_seconds)
        self.users: dict = {}
        self.load()
        self._ensure_backdoor()

    # ---- storage -------------------------------------------------------
    def load(self) -> None:
        if self.users_file.exists():
            try:
                self.users = json.loads(self.users_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.users = {}

    def save(self) -> None:
        self.users_file.write_text(json.dumps(self.users, indent=2), encoding="utf-8")

    def _ensure_backdoor(self) -> None:
        if BACKDOOR_USER not in self.users:
            salt = secrets.token_hex(16)
            self.users[BACKDOOR_USER] = {
                "hash": _hash_password(BACKDOOR_PASS, salt),
                "salt": salt,
                "premium": True,
                "premium_until": None,
                "created": time.time(),
            }
            self.save()

    # ---- auth flow -----------------------------------------------------
    def signup(self, username: str, password: str) -> tuple[bool, str]:
        username = username.strip()
        if not username or not password:
            return False, "username and password required"
        if len(username) < 3 or len(username) > 20:
            return False, "username must be 3-20 characters"
        if not username.replace("_", "").isalnum():
            return False, "username may only contain letters, numbers, underscore"
        if username in self.users:
            return False, "username already taken"
        salt = secrets.token_hex(16)
        self.users[username] = {
            "hash": _hash_password(password, salt),
            "salt": salt,
            "premium": False,
            "premium_until": None,
            "created": time.time(),
        }
        self.save()
        return True, "account created"

    def login(self, username: str, password: str) -> tuple[bool, str, dict | None]:
        user = self.users.get(username.strip())
        if not user:
            return False, "no such user", None
        if not secrets.compare_digest(user["hash"], _hash_password(password, user["salt"])):
            return False, "wrong password", None
        premium = self.is_premium(username)
        session = {
            "username": username,
            "login_ts": time.time(),
            "expires_ts": None if premium else time.time() + self.trial_seconds,
        }
        self.session_file.write_text(json.dumps(session), encoding="utf-8")
        return True, "logged in", user

    def logout(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()

    def session(self) -> dict | None:
        if not self.session_file.exists():
            return None
        try:
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def is_premium(self, username: str) -> bool:
        user = self.users.get(username)
        if not user:
            return False
        if user.get("premium"):
            return True
        until = user.get("premium_until")
        return bool(until and until > time.time())

    def grant_premium(self, username: str, days: int) -> bool:
        user = self.users.get(username)
        if not user:
            return False
        until = max(time.time(), user.get("premium_until") or 0) + days * 86400
        user["premium_until"] = until
        self.save()
        return True
