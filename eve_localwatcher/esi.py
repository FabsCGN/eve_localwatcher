"""Minimal ESI (EVE Swagger Interface) client for the threat-check.

Public endpoints only here (name→id, affiliation, names, character birthday);
authenticated endpoints (fleet, contacts) are driven by the SSO module later.
Bulk endpoints resolve the whole Local in a handful of calls.
"""
from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from . import __version__

BASE = "https://esi.evetech.net/latest"
_TIMEOUT = 12
_RETRIES = 3


def user_agent(contact: str) -> str:
    """Descriptive User-Agent for ESI/zKill. The contact is optional etiquette
    (so an admin can reach the maintainer); app name + version alone is already
    a valid, polite UA, so leaving it blank is fine — and avoids shipping a
    personal address when the code is shared."""
    c = (contact or "").strip()
    base = f"FlintLocalWatcher/{__version__}"
    return f"{base} ({c})" if c else base


def _chunks(seq: List, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


class ESI:
    def __init__(self, contact: str = "") -> None:
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent(contact)
        self.s.headers["Accept"] = "application/json"
        self._name_cache: Dict[int, str] = {}   # id -> name (corps/alliances/types)
        self._km_cache: Dict[int, dict] = {}     # killmail_id -> full killmail

    def _request(self, method: str, url: str, **kw):
        last = None
        for attempt in range(_RETRIES):
            try:
                r = self.s.request(method, url, timeout=_TIMEOUT, **kw)
                if r.status_code in (420, 429, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    last = r
                    continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException as e:
                last = e
                time.sleep(0.8 * (attempt + 1))
        if isinstance(last, requests.Response):
            last.raise_for_status()
        raise last if last else RuntimeError("ESI request failed")

    # name -> character id (characters only; ignores corps/alliances buckets)
    def names_to_ids(self, names: Iterable[str]) -> Dict[str, int]:
        names = [n for n in names if n]
        out: Dict[str, int] = {}
        for batch in _chunks(names, 1000):
            data = self._request("POST", f"{BASE}/universe/ids/", json=batch)
            for c in (data or {}).get("characters", []) or []:
                out[c["name"]] = c["id"]
        return out

    # character id -> (corp_id, alliance_id|None, faction_id|None)
    def affiliations(self, ids: Iterable[int]) -> Dict[int, Tuple[int, Optional[int], Optional[int]]]:
        ids = list(dict.fromkeys(int(i) for i in ids))
        out = {}
        for batch in _chunks(ids, 1000):
            for a in self._request("POST", f"{BASE}/characters/affiliation/", json=batch):
                out[a["character_id"]] = (a.get("corporation_id"),
                                          a.get("alliance_id"), a.get("faction_id"))
        return out

    # id -> name for any category (corps, alliances, characters, types). Cached.
    def names_for_ids(self, ids: Iterable[int]) -> Dict[int, str]:
        ids = list(dict.fromkeys(int(i) for i in ids if i))
        missing = [i for i in ids if i not in self._name_cache]
        for batch in _chunks(missing, 1000):
            for n in self._request("POST", f"{BASE}/universe/names/", json=batch):
                self._name_cache[n["id"]] = n["name"]
        return {i: self._name_cache[i] for i in ids if i in self._name_cache}

    # full killmail (immutable → cached forever)
    def killmail(self, killmail_id: int, killmail_hash: str) -> dict:
        kid = int(killmail_id)
        if kid not in self._km_cache:
            self._km_cache[kid] = self._request(
                "GET", f"{BASE}/killmails/{kid}/{killmail_hash}/")
        return self._km_cache[kid]

    # full public character record (birthday, corp, alliance)
    def character(self, char_id: int) -> dict:
        return self._request("GET", f"{BASE}/characters/{int(char_id)}/")

    def character_location(self, char_id: int, access_token: str) -> Optional[int]:
        """Current solar_system_id of the character, or None.

        Requires the esi-location.read_location.v1 scope; a 403 (scope not
        granted) is raised for the caller to classify.
        """
        h = {"Authorization": f"Bearer {access_token}"}
        data = self._request("GET", f"{BASE}/characters/{int(char_id)}/location/",
                             headers=h)
        return (data or {}).get("solar_system_id")

    def fleet_member_ids(self, char_id: int, access_token: str) -> set:
        """Character ids of everyone in the caller's current fleet (empty if not
        in a fleet). Requires the esi-fleets.read_fleet.v1 scope."""
        h = {"Authorization": f"Bearer {access_token}"}
        # /characters/{id}/fleet/ returns 404 when the char isn't in a fleet.
        r = self.s.get(f"{BASE}/characters/{int(char_id)}/fleet/", headers=h,
                       timeout=_TIMEOUT)
        if r.status_code == 404:
            return set()
        r.raise_for_status()
        fleet_id = r.json().get("fleet_id")
        if not fleet_id:
            return set()
        members = self._request("GET", f"{BASE}/fleets/{fleet_id}/members/",
                                headers=h)
        return {m["character_id"] for m in members}
