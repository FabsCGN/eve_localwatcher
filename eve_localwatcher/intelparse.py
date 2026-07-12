"""Parse intel-channel chat lines into (system, pilot candidates) reports.

Pure functions — no I/O, fully unit-testable. Real-world lines look like:

    [ 2026.07.11 20:28:00 ] Ju Hee > N-M1A3*  Cj Allyn
    [ 2026.07.11 20:14:38 ] Desticy > V-LEKM +9 EVE-RO / Goonswarm Federation
    [ 2026.07.11 20:15:19 ] Desticy > https://dscan.info/... in P-Z gate, ...
    [ 2026.07.11 20:32:30 ] Ju Hee > clr.

Strategy: find a system token first (exact name anywhere on the map, or a
prefix that is unique WITHIN the radar bubble — "P-Z" is unambiguous there).
No bubble system → the line is ignored entirely (out of range / chatter).
Everything else that survives the noise filters becomes a pilot-name
candidate; candidates are validated later against ESI (one bulk call), so a
stray word that slipped through simply fails to resolve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import mapdata

LINE_RE = re.compile(
    r"^﻿?\[\s*(\d{4})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\s*\]"
    r"\s*(.+?)\s*>\s*(.*)$")
_URL_RE = re.compile(r"https?://\S+")
_COUNT_RE = re.compile(r"^\+?\d+$")
_JUNK_RE = re.compile(r"^[\d\W_]+$")
_NAME_OK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9' .\-]{2,36}$")

# common intel-channel chatter that must never become a pilot candidate
STATUS_WORDS = {
    "clr", "clear", "clr.", "status", "gate", "camp", "camping", "eyes",
    "gg", "guys", "on", "in", "at", "the", "a", "and", "und", "ping",
    "off", "keep", "going", "spike", "local", "red", "reds", "neut",
    "neuts", "hostile", "hostiles", "docked", "gone", "safe", "bubble",
    "wh", "cyno", "carrier", "dread", "titan", "fleet", "pls", "please",
    "check", "jumped", "coming", "warp", "warping",
}


@dataclass
class IntelReport:
    system_id: int
    system_name: str
    pilot_candidates: List[str] = field(default_factory=list)
    ts: Optional[datetime] = None
    raw: str = ""


def parse_line(line: str) -> Optional[Tuple[datetime, str, str]]:
    """(timestamp_utc, author, message) — None for MOTD/header/blank lines."""
    m = LINE_RE.match(line or "")
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    try:
        ts = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    except ValueError:
        return None
    return ts, m.group(7), m.group(8)


def _chunks(msg: str) -> List[str]:
    """Split a message into name-ish chunks: runs of ≥2 spaces and commas
    separate entities (the ingame list-paste style); fall back to single
    tokens when that yields just one chunk."""
    parts = [p.strip() for p in re.split(r" {2,}|,|\t", msg) if p.strip()]
    if len(parts) > 1:
        return parts
    return [p for p in msg.split() if p]


def extract_report(msg: str, ts: Optional[datetime],
                   bubble: Dict[int, int]) -> Optional[IntelReport]:
    """IntelReport if the message names a system inside ``bubble``, else None.

    ``bubble`` is {system_id: jumps} around the own system (mapdata
    ``systems_within``); prefix matching only happens against those ids.
    """
    if not msg or not bubble:
        return None
    raw = msg
    msg = _URL_RE.sub(" ", msg)
    # "… / Goonswarm Federation" — alliance suffix carries no pilot names
    msg = msg.split(" / ")[0]

    # find the system inside the chunks WITHOUT collapsing chunk boundaries —
    # multi-word pilot names ("Chani Crendraven") live in their own chunk and
    # must survive intact
    system_id = None
    rest_chunks: List[str] = []
    for chunk in _chunks(msg):
        if system_id is None:
            toks = chunk.split()
            hit = None
            for i, tok in enumerate(toks):
                sid = mapdata.resolve_system(tok, restrict_ids=bubble.keys())
                if sid is not None and int(sid) in bubble:
                    system_id, hit = int(sid), i
                    break
            if hit is not None:
                leftover = toks[:hit] + toks[hit + 1:]
                if leftover:
                    rest_chunks.append(" ".join(leftover))
                continue
        rest_chunks.append(chunk)
    if system_id is None:
        return None

    # pilot candidates from the remaining chunks
    candidates: List[str] = []
    for chunk in rest_chunks:
        chunk = chunk.strip(" .!?*")
        if not chunk or _COUNT_RE.match(chunk) or _JUNK_RE.match(chunk):
            continue
        if chunk.lower() in STATUS_WORDS:
            continue
        words = chunk.split()
        # drop leading/trailing status words inside a chunk ("in P-Z gate")
        while words and words[0].lower() in STATUS_WORDS:
            words = words[1:]
        while words and words[-1].lower() in STATUS_WORDS:
            words = words[:-1]
        if not words or len(words) > 3:
            continue
        cand = " ".join(words)
        if _NAME_OK_RE.match(cand) and cand.lower() not in STATUS_WORDS:
            candidates.append(cand)
    name = mapdata.name_for_id(system_id) or str(system_id)
    return IntelReport(system_id=system_id, system_name=name,
                       pilot_candidates=candidates[:8], ts=ts, raw=raw)
