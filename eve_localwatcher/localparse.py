"""Parse a Local member list — from the clipboard (EVE copy) or OCR lines —
into clean character names.

EVE character names: 3-37 chars, letters/digits/space, plus ' and - ; they may
contain at most one space between first and last name segments. We validate
loosely and drop anything that clearly isn't a name (UI noise, URLs, fits).
"""
from __future__ import annotations

import re
from typing import List

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 '\-]{2,36}$")
_URLISH = re.compile(r"https?://|@|\t.*\t")   # obvious non-name lines


def is_eve_name(line: str) -> bool:
    s = line.strip()
    if not _NAME_RE.match(s) or _URLISH.search(s):
        return False
    # real names have at most a couple of spaces; reject sentence-like lines
    return s.count(" ") <= 2


def parse_names(text: str) -> List[str]:
    """Extract unique valid character names, order preserved."""
    out: List[str] = []
    seen = set()
    for raw in (text or "").replace("\r", "\n").split("\n"):
        s = raw.strip()
        if is_eve_name(s) and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def looks_like_namelist(text: str) -> bool:
    """Heuristic: does this clipboard content look like a copied member list?

    Used so the clipboard watcher ignores normal copies (URLs, fits, chat).
    """
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    valid = sum(1 for l in lines if is_eve_name(l))
    return valid >= 2 and valid >= 0.6 * len(lines)
