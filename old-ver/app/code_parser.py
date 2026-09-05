from __future__ import annotations

import re

_PATTERN = re.compile(r"(?<![A-Z0-9])([A-Z]{2,10})[ _-]?(\d{2,7})(?![A-Z0-9])", re.I)
_TECHNICAL_PREFIXES = {"MOVIE", "VIDEO", "H", "X", "FPS", "BIT", "AAC", "HEVC", "AVC"}


def normalize_code(code: str) -> str:
    match = _PATTERN.search(code.upper())
    if not match:
        return code.strip().upper()
    prefix, number = match.groups()
    if prefix in _TECHNICAL_PREFIXES or (prefix == "X" and number in {"264", "265"}):
        return ""
    return f"{prefix}-{number}"


def extract_codes(text: str) -> list[str]:
    return list(dict.fromkeys(code for m in _PATTERN.finditer(text) if (code := normalize_code(m.group(0)))))
