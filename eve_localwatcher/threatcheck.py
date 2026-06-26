"""Orchestrator: a list of Local names → enriched ThreatProfiles.

Pipeline: resolve names → affiliations → build the friendly set (SSO) → drop
friendlies → enrich only the non-friendlies (corp/alliance names, char age,
zKill) → score. Friendlies never reach zKill — saves calls and honours the
"only what's not blue/green/purple" rule.

Runs synchronously; the UI wraps it in a background thread and uses
``on_progress`` to fill the panel as each pilot resolves.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from . import sso, threat
from .config import Config
from .esi import ESI
from .friendly import FriendlySet, build_friendly_set
from .zkill import ZKill

ProgressCB = Optional[Callable[[threat.ThreatProfile], None]]


def _recent_ships(esi: ESI, zk: ZKill, char_id: int, max_ships: int = 5,
                  scan: int = 8) -> list:
    """Distinct recently-flown ships (newest first) with a killmail link each.

    For a loss the ship is the victim hull (link shows the pilot's own fit); for
    a kill it's the pilot's attacker hull (link shows the victim's killmail).
    """
    entries = []
    seen = set()
    type_ids = []
    last_time = None
    for kid, kh in zk.recent_killmails(char_id, limit=scan):
        try:
            km = esi.killmail(kid, kh)
        except Exception:
            continue
        if last_time is None:
            last_time = km.get("killmail_time")   # newest mail = last activity
        vic = km.get("victim", {})
        if vic.get("character_id") == char_id:
            kind, ship = "loss", vic.get("ship_type_id")
        else:
            kind = "kill"
            ship = next((a.get("ship_type_id") for a in km.get("attackers", [])
                         if a.get("character_id") == char_id), None)
        if not ship or ship in seen:
            continue
        seen.add(ship)
        type_ids.append(ship)
        entries.append((ship, kind, kid, km.get("killmail_time", "")))
        if len(entries) >= max_ships:
            break
    names = esi.names_for_ids(type_ids) if type_ids else {}
    ships = [threat.RecentShip(names.get(s, f"#{s}"), kind, kid, t)
             for s, kind, kid, t in entries]
    return ships, last_time


def _access_token(cfg: Config) -> Optional[str]:
    if not (cfg.sso_client_id and cfg.sso_refresh_token):
        return None
    token, new_rt = sso.access_from_refresh(cfg.sso_client_id, cfg.sso_refresh_token)
    if new_rt and new_rt != cfg.sso_refresh_token:
        cfg.sso_refresh_token = new_rt
        cfg.save()
    return token


def run_check(cfg: Config, names: List[str], on_progress: ProgressCB = None
              ) -> Tuple[List[threat.ThreatProfile], dict, bool]:
    """Returns (profiles_for_non_friendlies, aggregate, filtered_ok).

    ``filtered_ok`` is False if the friendly filter couldn't be built (no SSO) —
    then nothing was filtered and the caller should warn.
    """
    esi = ESI(cfg.zkill_contact)
    zk = ZKill(cfg.zkill_contact)

    ids = esi.names_to_ids(names)                      # name -> char id
    aff = esi.affiliations(ids.values()) if ids else {}

    # friendly set (green/blue always if logged in; purple needs a live token)
    fs: Optional[FriendlySet] = None
    if cfg.sso_character_id:
        token = _access_token(cfg)
        fs = build_friendly_set(esi, cfg.sso_character_id, token,
                                cfg.blue_corp_ids, cfg.blue_alliance_ids)

    # split into unresolved + non-friendly (friendlies are dropped here)
    pending = []           # (name, cid, corp_id, alliance_id)
    profiles: List[threat.ThreatProfile] = []
    for name in names:
        cid = ids.get(name)
        if cid is None:
            profiles.append(threat.unresolved(name))
            continue
        corp_id, alliance_id, _ = aff.get(cid, (None, None, None))
        if fs and fs.is_friendly(cid, corp_id, alliance_id):
            continue
        pending.append((name, cid, corp_id, alliance_id))

    # resolve corp/alliance names for the non-friendlies in one bulk call
    ent_ids = {e for _, _, c, a in pending for e in (c, a) if e}
    ent = esi.names_for_ids(ent_ids) if ent_ids else {}

    for name, cid, corp_id, alliance_id in pending:
        try:
            pub = esi.character(cid)
        except Exception:
            pub = None
        zs = zk.stats(cid)
        p = threat.assess(name, cid, pub, zs, ent.get(corp_id),
                          ent.get(alliance_id), cfg.fresh_char_days)
        try:
            p.recent_ships, p.last_killmail_time = _recent_ships(esi, zk, cid)
        except Exception:
            p.recent_ships = []
        profiles.append(p)
        if on_progress:
            on_progress(p)

    return profiles, threat.aggregate(profiles), fs is not None
