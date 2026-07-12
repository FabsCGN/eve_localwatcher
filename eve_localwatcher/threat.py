"""Threat scoring: turn ESI + zKill data into a per-pilot ThreatProfile.

Design decisions (locked in brainstorm):
- Fresh char < 90 days → warning that RAISES the tier (a cyno alt looks harmless
  by design: young + no kills must never read as "safe").
- Scanner/explorer → neutral INFO hint only; never changes the tier.
- Partial coverage is loud: unresolved/no-data pilots are 'unknown', not 'safe'.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

# EVE inventory group IDs.
GROUP_HUNTER = {
    833: "Force Recon", 906: "Combat Recon", 834: "Stealth Bomber",
    894: "Heavy Interdiction Cruiser", 541: "Interdictor", 898: "Black Ops",
    963: "Strategic Cruiser", 1305: "Tactical Destroyer",
}
GROUP_SCANNER = {830: "Covert Ops"}     # the scanning/exploration frigates
GROUP_NAMES = {
    25: "Frigate", 26: "Cruiser", 27: "Battleship", 28: "Hauler",
    324: "Assault Frigate", 358: "HAC", 419: "Battlecruiser", 420: "Destroyer",
    463: "Mining Barge", 540: "Command Ship", 543: "Exhumer", 547: "Carrier",
    831: "Interceptor", 832: "Logistics", 900: "Marauder", 941: "Orca",
    **GROUP_HUNTER, **GROUP_SCANNER,
}

TIER_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class RecentShip:
    ship_name: str
    kind: str            # 'kill' (char was attacker) or 'loss' (char was victim)
    killmail_id: int
    time: str            # ISO killmail_time

    @property
    def url(self) -> str:
        return f"https://zkillboard.com/kill/{self.killmail_id}/"


@dataclass
class ThreatProfile:
    name: str
    character_id: Optional[int] = None
    corp_name: Optional[str] = None
    alliance_name: Optional[str] = None
    age_days: Optional[int] = None
    danger: Optional[int] = None            # zKill dangerRatio 0..100
    gang_ratio: Optional[int] = None        # zKill gangRatio 0..100 (rest = solo)
    last_killmail_time: Optional[str] = None  # newest killmail (kill or loss)
    ships_destroyed: int = 0
    ships_lost: int = 0
    top_groups: List[Tuple[int, int]] = field(default_factory=list)  # (groupID, uses)
    recent_ships: List[RecentShip] = field(default_factory=list)
    # weapon used on a kill within the last 2 h (max range: best ammo, all V)
    recent_weapon_name: Optional[str] = None
    recent_weapon_range_km: Optional[float] = None
    recent_weapon_falloff_km: Optional[float] = None
    recent_weapon_charge: Optional[str] = None
    recent_kill_min_ago: Optional[int] = None
    flags: Set[str] = field(default_factory=set)   # hunter/fresh/cyno/scanner/unknown
    tier: str = "unknown"
    resolved: bool = True

    def top_group_names(self, n: int = 2) -> str:
        return " / ".join(GROUP_NAMES.get(g, f"#{g}") for g, _ in self.top_groups[:n])


def _age_days(birthday: Optional[str]) -> Optional[int]:
    if not birthday:
        return None
    try:
        bd = datetime.fromisoformat(birthday.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - bd).days
    except (ValueError, TypeError):
        return None


def _group_usage(zstats: dict) -> List[Tuple[int, int]]:
    groups = (zstats or {}).get("groups") or {}
    usage = []
    for g in groups.values():
        gid = g.get("groupID")
        uses = (g.get("shipsDestroyed") or 0) + (g.get("shipsLost") or 0)
        if gid is not None and uses:
            usage.append((int(gid), int(uses)))
    usage.sort(key=lambda x: x[1], reverse=True)
    return usage


def unresolved(name: str) -> ThreatProfile:
    """A pilot whose name couldn't be resolved (OCR miss / ESI fail)."""
    return ThreatProfile(name=name, resolved=False, tier="unknown", flags={"unknown"})


def assess(name: str, char_id: Optional[int], char_pub: Optional[dict],
           zstats: Optional[dict], corp_name: Optional[str],
           alliance_name: Optional[str], fresh_days: int = 90,
           cyno_max_kills: int = 5, cyno_min_age_days: int = 365) -> ThreatProfile:
    p = ThreatProfile(name=name, character_id=char_id, corp_name=corp_name,
                      alliance_name=alliance_name)
    p.age_days = _age_days((char_pub or {}).get("birthday"))
    z = zstats or {}
    p.danger = z.get("dangerRatio")
    p.gang_ratio = z.get("gangRatio")
    p.ships_destroyed = z.get("shipsDestroyed") or 0
    p.ships_lost = z.get("shipsLost") or 0
    p.top_groups = _group_usage(z)

    groups_raw = list(((z.get("groups") or {}).values()))

    def _kills(g):
        return g.get("shipsDestroyed") or 0

    def _uses(g):
        return (g.get("shipsDestroyed") or 0) + (g.get("shipsLost") or 0)

    total_kills = sum(_kills(g) for g in groups_raw)
    hunter_kills = sum(_kills(g) for g in groups_raw if g.get("groupID") in GROUP_HUNTER)
    total_uses = sum(_uses(g) for g in groups_raw)
    scanner_uses = sum(_uses(g) for g in groups_raw if g.get("groupID") in GROUP_SCANNER)
    has_data = bool(groups_raw) or p.danger is not None or p.ships_destroyed or p.ships_lost

    # --- flags ---
    # Hunter = actual KILLS in cloaky/recon/dictor/black-ops/T3C hulls — not just
    # having flown or lost one (that flagged industrialists like Chribba).
    if hunter_kills >= 10 or (total_kills >= 5 and hunter_kills / max(1, total_kills) >= 0.3):
        p.flags.add("hunter")
    fresh = p.age_days is not None and p.age_days < fresh_days
    if fresh:
        p.flags.add("fresh")
        if p.ships_destroyed < 5:
            p.flags.add("cyno")        # young + almost no kills → cyno-alt suspicion
    # The other classic cyno population: an AGED char with an empty killboard
    # that still sits in an alliance — a parked, skill-farmed dedicated alt.
    if (p.age_days is not None and p.age_days >= cyno_min_age_days
            and p.ships_destroyed <= cyno_max_kills
            and alliance_name):
        p.flags.add("cyno")
    # scanner: dominant covops use, not a hunter, low/unknown danger (neutral hint)
    if ("hunter" not in p.flags and total_uses
            and scanner_uses / total_uses >= 0.4
            and (p.danger is None or p.danger < 30)):
        p.flags.add("scanner")

    # --- tier (scanner is intentionally NOT considered) ---
    if not has_data and not fresh:
        p.tier = "unknown"             # no record at all → never call it "safe"
        p.flags.add("unknown")
    elif "hunter" in p.flags or (p.danger is not None and p.danger >= 70):
        p.tier = "high"
    elif (p.danger is not None and p.danger >= 40) or "cyno" in p.flags or fresh:
        p.tier = "medium"              # fresh char always at least medium
    else:
        p.tier = "low"                 # has a record, little/no offensive danger
    return p


def aggregate(profiles: List[ThreatProfile]) -> Dict[str, int]:
    resolved = [p for p in profiles if p.resolved]
    return {
        "total": len(profiles),
        "resolved": len(resolved),
        "unresolved": len(profiles) - len(resolved),
        "dangerous": sum(1 for p in resolved if p.tier in ("high", "medium")),
        "hunters": sum(1 for p in resolved if "hunter" in p.flags),
        "fresh": sum(1 for p in resolved if "fresh" in p.flags),
        "cyno": sum(1 for p in resolved if "cyno" in p.flags),
        "scanners": sum(1 for p in resolved if "scanner" in p.flags),
    }
