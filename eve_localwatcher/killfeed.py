"""Live zKillboard killmail feed via the R2Z2 API (sequence-based polling).

R2Z2 replaced RedisQ (sunset May 2026). Contract: fetch the current sequence
from ``sequence.json``, then request ``{n}.json`` for increasing n; a 404
means we're caught up. Payload shape (verified live):

    {"killmail_id": ..., "hash": ..., "sequence_id": ..., "uploaded_at": ...,
     "esi": {full ESI killmail: solar_system_id, killmail_time, victim,
             attackers[{character_id, corporation_id, alliance_id,
                        ship_type_id, weapon_type_id, damage_done,
                        final_blow, ...}]},
     "zkb": {npc, solo, labels, totalValue, ...}}

Etiquette (documented, violators get IP-banned for an hour): sleep ≥6 s when
caught up, ≥100 ms between successful fetches, stay far under 15 req/s.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Optional

import requests

from .esi import user_agent

R2Z2_BASE = "https://r2z2.zkillboard.com/ephemeral"
CAUGHT_UP_SLEEP = 6.0     # after a 404 (no newer killmail yet)
FETCH_GAP = 0.11          # between successful fetches (~9/s max, limit is 15)
RESYNC_AFTER = 300.0      # persistent 404s → re-read sequence.json (gap jump)
_TIMEOUT = 12


class KillFeed:
    """Polls R2Z2 on the calling thread (run() is the Thread target).

    ``on_kill(payload)`` gets each new killmail dict (killmail_id, hash, the
    raw ESI killmail fields, zkb); ``on_status(msg)`` gets human-readable
    state changes. Both are called from the feed thread — keep them cheap and
    thread-safe (the radar just filters and posts to a queue).
    """

    def __init__(self, contact: str, on_kill: Callable[[dict], None],
                 on_status: Callable[[str], None],
                 stop: threading.Event) -> None:
        self._on_kill = on_kill
        self._on_status = on_status
        self._stop = stop
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent(contact)
        self.s.headers["Accept"] = "application/json"
        self._seen: deque = deque(maxlen=2000)   # killmail_id ring (dedupe)
        self._seen_set: set = set()

    # ------------------------------------------------------------------ http
    def _get_json(self, url: str) -> Optional[tuple]:
        """(status_code, json|None) — None result on network error."""
        try:
            r = self.s.get(url, timeout=_TIMEOUT)
            if r.status_code == 200:
                return 200, r.json()
            return r.status_code, None
        except (requests.RequestException, ValueError):
            return None

    def _current_sequence(self) -> Optional[int]:
        res = self._get_json(f"{R2Z2_BASE}/sequence.json")
        if res and res[0] == 200 and isinstance(res[1], dict):
            seq = res[1].get("sequence")
            return int(seq) if seq is not None else None
        return None

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        seq = None
        backoff = 2.0
        caught_up_since = None
        while not self._stop.is_set():
            if seq is None:
                seq = self._current_sequence()
                if seq is None:
                    self._on_status("Killfeed: zKillboard nicht erreichbar — "
                                    "neuer Versuch")
                    if self._stop.wait(min(backoff, 60.0)):
                        return
                    backoff = min(backoff * 2, 60.0)
                    continue
                backoff = 2.0
                self._on_status(f"Killfeed verbunden (Sequenz {seq})")

            res = self._get_json(f"{R2Z2_BASE}/{seq + 1}.json")
            if res is None:                                # network hiccup
                if self._stop.wait(min(backoff, 60.0)):
                    return
                backoff = min(backoff * 2, 60.0)
                continue
            backoff = 2.0

            status, payload = res
            if status == 200 and isinstance(payload, dict):
                seq += 1
                caught_up_since = None
                kid = payload.get("killmail_id")
                if kid is not None and kid not in self._seen_set:
                    if len(self._seen) == self._seen.maxlen:
                        self._seen_set.discard(self._seen[0])
                    self._seen.append(kid)
                    self._seen_set.add(kid)
                    try:
                        self._on_kill(payload)
                    except Exception:
                        pass          # a bad killmail must never kill the feed
                if self._stop.wait(FETCH_GAP):
                    return
            elif status == 404:                            # caught up
                now = time.monotonic()
                if caught_up_since is None:
                    caught_up_since = now
                elif now - caught_up_since > RESYNC_AFTER:
                    seq = None                             # gap? re-sync
                    caught_up_since = None
                    continue
                if self._stop.wait(CAUGHT_UP_SLEEP):
                    return
            elif status in (403, 429):
                self._on_status("Killfeed: Rate-Limit — 5 min Pause")
                if self._stop.wait(300.0):
                    return
            else:
                if self._stop.wait(min(backoff, 60.0)):
                    return
                backoff = min(backoff * 2, 60.0)
