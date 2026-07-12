"""Orchestrator: a list of Local names → enriched ThreatProfiles.

Pipeline: resolve names → affiliations → build the friendly set (SSO) → drop
friendlies → enrich only the non-friendlies (corp/alliance names, char age,
zKill) → score. Friendlies never reach zKill — saves calls and honours the
"only what's not blue/green/purple" rule.

Runs synchronously; the UI wraps it in a background thread and uses
``on_progress`` to fill the panel as each pilot resolves.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List, Optional, Tuple

from . import sso, threat, weaponrange
from .config import Config
from .esi import ESI
from .friendly import FriendlySet, build_friendly_set
from .zkill import ZKill

ProgressCB = Optional[Callable[[threat.ThreatProfile], None]]

# A kill within this window is fresh enough to warn about the weapon's reach.
RECENT_KILL_WINDOW_MIN = 120


def _minutes_ago(iso: Optional[str]) -> Optional[int]:
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - t).total_seconds() // 60)
    except (ValueError, TypeError):
        return None


def _weapon_from_kill(km: dict, char_id: int, ship: Optional[int]
                      ) -> Optional[Tuple[int, int]]:
    """(weapon_type_id, minutes_ago) if the char scored this kill within the
    window and the mail records an actual weapon (weapon == ship means none)."""
    mins = _minutes_ago(km.get("killmail_time"))
    if mins is None or not 0 <= mins <= RECENT_KILL_WINDOW_MIN:
        return None
    wid = next((a.get("weapon_type_id") for a in km.get("attackers", [])
                if a.get("character_id") == char_id), None)
    if not wid or wid == ship:
        return None
    return wid, mins


def _recent_ships(esi: ESI, zk: ZKill, char_id: int, max_ships: int = 5,
                  scan: int = 8) -> tuple:
    """Distinct recently-flown ships (newest first) with a killmail link each,
    plus the weapon of the newest own kill within RECENT_KILL_WINDOW_MIN.

    For a loss the ship is the victim hull (link shows the pilot's own fit); for
    a kill it's the pilot's attacker hull (link shows the victim's killmail).
    """
    entries = []
    seen = set()
    type_ids = []
    last_time = None
    weapon = None            # (ship_type_id, weapon_type_id, minutes_ago)
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
            # before the hull dedup, so a repeated hull can't skip the check;
            # mails are newest-first → the first hit is the newest kill
            if weapon is None:
                w = _weapon_from_kill(km, char_id, ship)
                if w:
                    weapon = (ship, w[0], w[1])
                    type_ids.append(w[0])
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
    if weapon:
        ship_id, wid, mins = weapon
        weapon = (ship_id, wid, names.get(wid, f"#{wid}"), mins)
    return ships, last_time, weapon


def _access_token(cfg: Config) -> Optional[str]:
    if not (cfg.sso_client_id and cfg.sso_refresh_token):
        return None
    token, new_rt = sso.access_from_refresh(cfg.sso_client_id, cfg.sso_refresh_token)
    if new_rt and new_rt != cfg.sso_refresh_token:
        cfg.sso_refresh_token = new_rt
        cfg.save()
    return token


# public alias — the radar's location poller and friendly refresh use it too
access_token = _access_token


def enrich_one(esi: ESI, zk: ZKill, cfg: Config, name: str, cid: int,
               corp_name: Optional[str], alliance_name: Optional[str]
               ) -> threat.ThreatProfile:
    """Full per-pilot enrichment (public record, zKill stats, recent ships,
    recent-kill weapon range) into a scored ThreatProfile.

    Shared by run_check and the radar's persistent enrichment worker — pass
    long-lived ESI/ZKill instances there so their caches and the zKill
    throttle survive across pilots.
    """
    try:
        pub = esi.character(cid)
    except Exception:
        pub = None
    zs = zk.stats(cid)
    p = threat.assess(name, cid, pub, zs, corp_name, alliance_name,
                      cfg.fresh_char_days, cfg.cyno_max_kills,
                      cfg.cyno_min_age_days)
    try:
        p.recent_ships, p.last_killmail_time, weapon = _recent_ships(esi, zk, cid)
    except Exception:
        p.recent_ships = []
        weapon = None
    if weapon:
        ship_id, wid, wname, mins = weapon
        p.recent_weapon_name = wname
        p.recent_kill_min_ago = mins
        try:
            info = weaponrange.max_range(ship_id, wid)
        except Exception:
            info = None
        if info:
            p.recent_weapon_range_km = info.range_km
            p.recent_weapon_falloff_km = info.falloff_km
            p.recent_weapon_charge = info.charge_name
    return p


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
        p = enrich_one(esi, zk, cfg, name, cid,
                       ent.get(corp_id), ent.get(alliance_id))
        profiles.append(p)
        if on_progress:
            on_progress(p)

    return profiles, threat.aggregate(profiles), fs is not None
