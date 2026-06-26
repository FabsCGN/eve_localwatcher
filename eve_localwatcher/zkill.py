"""zKillboard stats client.

zKill requires a descriptive User-Agent and polite use: we cache per character
for the session and throttle to ~1 request/second. Only non-friendly pilots are
ever queried (filtering happens upstream).
"""
from __future__ import annotations

import threading
import time
from typing import Dict, Optional

import requests

from .esi import user_agent

BASE = "https://zkillboard.com/api"
_TIMEOUT = 15
_MIN_INTERVAL = 1.05   # seconds between calls (zKill etiquette)


class ZKill:
    def __init__(self, contact: str = "") -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent(contact)
        self.s.headers["Accept"] = "application/json"
        self._cache: Dict[int, dict] = {}
        self._last_call = 0.0
        self._lock = threading.Lock()

    def _throttle(self) -> None:
        with self._lock:
            wait = _MIN_INTERVAL - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def stats(self, char_id: int) -> Optional[dict]:
        """Character stats dict, cached. None on failure/no data."""
        char_id = int(char_id)
        if char_id in self._cache:
            return self._cache[char_id]
        self._throttle()
        try:
            r = self.s.get(f"{BASE}/stats/characterID/{char_id}/", timeout=_TIMEOUT)
            if r.status_code != 200:
                return None
            data = r.json() or {}
            self._cache[char_id] = data
            return data
        except (requests.RequestException, ValueError):
            return None

    def recent_killmails(self, char_id: int, limit: int = 8) -> list:
        """Most-recent (killmail_id, hash) pairs for a character, newest first."""
        char_id = int(char_id)
        self._throttle()
        try:
            r = self.s.get(f"{BASE}/characterID/{char_id}/", timeout=_TIMEOUT)
            if r.status_code != 200:
                return []
            out = []
            for e in (r.json() or [])[:limit]:
                kid = e.get("killmail_id")
                h = (e.get("zkb") or {}).get("hash")
                if kid and h:
                    out.append((int(kid), h))
            return out
        except (requests.RequestException, ValueError):
            return []
