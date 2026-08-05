"""Username policy engine: min/max length + charset modes.

Modes: no_numbers | no_symbols | letters_and_numbers | letters_only | all"""
from __future__ import annotations

import re

MODES = {
    "no_numbers": re.compile(r"^[a-zA-Z_\-\.]+$"),
    "no_symbols": re.compile(r"^[a-zA-Z0-9]+$"),
    "letters_and_numbers": re.compile(r"^[a-zA-Z0-9]+$"),
    "letters_only": re.compile(r"^[a-zA-Z]+$"),
    "all": re.compile(r"^.+$"),
}


class UsernameFilter:
    def __init__(self, section: dict):
        self.min_chars = int(section.get("min_chars", 3))
        self.max_chars = int(section.get("max_chars", 20))
        self.mode = section.get("mode", "letters_and_numbers")
        self.regex = MODES.get(self.mode, MODES["letters_and_numbers"])
        self.blocklist = {str(x).lower() for x in section.get("blocklist", [])}

    def validate(self, name: str) -> tuple[bool, str]:
        if len(name) < self.min_chars:
            return False, f"below {self.min_chars} chars"
        if len(name) > self.max_chars:
            return False, f"over {self.max_chars} chars"
        if not self.regex.match(name):
            return False, f"violates '{self.mode}' charset"
        if name.lower() in self.blocklist:
            return False, "blocklisted"
        return True, ""

    def filter_names(self, names: list[str]) -> tuple[list[str], int]:
        kept, skipped = [], 0
        for name in names:
            ok, _ = self.validate(name)
            if ok:
                kept.append(name)
            else:
                skipped += 1
        return kept, skipped
