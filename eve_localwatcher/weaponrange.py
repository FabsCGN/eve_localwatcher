"""Max weapon range from bundled static data (generated from the EVE SDE).

Answers one question for the intel panel: "this pilot just killed something
with weapon X while flying hull Y — how far can that combination reach?"

The heavy lifting (SDE download, ammo selection, trait parsing) happens at
build time in ``tools/gen_weapon_ranges.py``; the committed
``data/weapon_ranges.json`` only holds factors, so runtime is dict lookups
and two multiplications. Assumptions baked in: max-range ammo loaded and all
relevant skills at V — hull bonus + weapon only, no modules/rigs/boosters.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional

_DATA_REL = ("data", "weapon_ranges.json")
_data: Optional[dict] = None
_failed = False


@dataclass
class WeaponRangeInfo:
    weapon_name: str
    range_km: Optional[float] = None     # optimal (turret) / flight range (missile)
    falloff_km: Optional[float] = None   # turrets only
    charge_name: Optional[str] = None    # assumed max-range ammo


def load_data() -> Optional[dict]:
    """Lazy-load the bundled JSON; returns None (and stays off) on any failure."""
    global _data, _failed
    if _data is not None or _failed:
        return _data
    candidates = [Path(__file__).resolve().parent.joinpath(*_DATA_REL)]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass, "eve_localwatcher", *_DATA_REL))
    for f in candidates:
        try:
            if f.is_file():
                _data = json.loads(f.read_text(encoding="utf-8"))
                return _data
        except Exception:
            break
    _failed = True
    return None


def max_range(ship_type_id: Optional[int], weapon_type_id: Optional[int]
              ) -> Optional[WeaponRangeInfo]:
    """Max possible range for (hull, weapon), or None if the weapon is unknown
    (drone, smartbomb, exotic) — the caller then shows the name only.
    Unknown hull degrades to multiplier 1.0 (range without hull bonus)."""
    d = load_data()
    if not d or not weapon_type_id:
        return None
    w = d.get("weapons", {}).get(str(weapon_type_id))
    if not w:
        return None
    hull = d.get("hulls", {}).get(str(ship_type_id)) or {}
    b = hull.get("b", {})
    skills = d.get("skills", {})
    cls = w.get("cls") or ""
    if w.get("kind") == "turret":
        charge = w.get("charge") or {}
        opt = (w.get("opt_m") or 0.0) * charge.get("mult", 1.0) \
            * skills.get("turret_optimal", 1.0) * b.get(cls + "_optimal", 1.0)
        fall = (w.get("fall_m") or 0.0) * charge.get("fmult", 1.0) \
            * b.get(cls + "_falloff", 1.0)
        if opt <= 0:
            return None
        return WeaponRangeInfo(w["name"], round(opt / 1000, 1),
                               round(fall / 1000, 1) if fall > 0 else None,
                               charge.get("name"))
    if w.get("kind") == "missile":
        m = w.get("missile") or {}
        rng = (m.get("vel_ms") or 0.0) * skills.get("missile_velocity", 1.0) \
            * b.get(cls + "_velocity", 1.0) \
            * (m.get("flight_s") or 0.0) * skills.get("missile_flight", 1.0) \
            * b.get(cls + "_flight", 1.0)
        if rng <= 0:
            return None
        return WeaponRangeInfo(w["name"], round(rng / 1000, 1), None,
                               m.get("name"))
    return None


def ewar_type_ids() -> FrozenSet[int]:
    d = load_data()
    if not d:
        return frozenset()
    return frozenset(int(t) for t in d.get("ewar_type_ids", []))
