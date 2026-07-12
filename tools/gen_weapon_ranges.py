"""Generate eve_localwatcher/data/weapon_ranges.json from the Fuzzwork SDE.

Dev-only tool — the generated JSON is committed and bundled into the exe; this
script is NOT shipped. Re-run after an EVE expansion changes weapon/hull stats.

Usage:
    python tools/gen_weapon_ranges.py --sde path/to/sde.sqlite [--report]

Without --sde the Fuzzwork dump (https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz,
~140 MB) is downloaded to the system temp dir and decompressed there.

What it emits (factors, not a full hull-x-weapon matrix — runtime multiplies):
- per turret/launcher type: base optimal/falloff resp. best missile (velocity,
  flight time), plus the max-range ammo of the matching charge size,
- per ship hull: range-relevant trait multipliers at skill level V, parsed from
  the English invTraits bonusText,
- the fixed all-V skill multipliers (Sharpshooter, Missile Projection/Bombardment),
- module type ids of the classic e-war groups (cyno-suspect bonus signal).

--report prints trait rows that look range-related but matched no rule, so
regex gaps after an SDE update are visible instead of silent.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path

SDE_URL = "https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz"
OUT_PATH = Path(__file__).resolve().parents[1] / "eve_localwatcher" / "data" / "weapon_ranges.json"

TURRET_FAMILY = {53: "energy", 55: "projectile", 74: "hybrid"}
SIZE_NAME = {1: "s", 2: "m", 3: "l", 4: "xl"}
WORD_SIZE = {"small": "s", "medium": "m", "large": "l", "capital": "xl"}

# All-V skill multipliers assumed at runtime (documented in the UI tooltip):
# Sharpshooter +5%/lvl turret optimal; Missile Projection +10%/lvl velocity;
# Missile Bombardment +10%/lvl flight time.
SKILLS = {"turret_optimal": 1.25, "missile_velocity": 1.5, "missile_flight": 1.5}

ATTR_NAMES = ("maxRange", "falloff", "weaponRangeMultiplier", "maxVelocity",
              "explosionDelay", "chargeGroup1", "chargeGroup2", "chargeGroup3",
              "chargeSize", "fallofMultiplier")   # sic — SDE typo is canonical

# Launcher groups excluded from the weapon table (can't shoot ships / fireworks).
LAUNCHER_EXCLUDE = ("Defender", "Festival", "Blueprint", "Snowball")

# Launcher group name -> missile class key used by the hull-trait table. Derived
# from the LAUNCHER (not the ammo group), because max-range ammo often lives in
# side groups like 'Advanced Torpedo' that hull bonus texts never mention.
LAUNCHER_CLS = {
    "Missile Launcher Rocket": "rocket",
    "Missile Launcher Light": "light_missile",
    "Missile Launcher Rapid Light": "light_missile",
    "Missile Launcher Heavy": "heavy_missile",
    "Missile Launcher Rapid Heavy": "heavy_missile",
    "Missile Launcher Heavy Assault": "heavy_assault_missile",
    "Missile Launcher Cruise": "cruise_missile",
    "Missile Launcher Torpedo": "torpedo",
    "Missile Launcher Rapid Torpedo": "torpedo",
    "Missile Launcher XL Torpedo": "xl_torpedo",
    "Missile Launcher XL Cruise": "xl_cruise_missile",
    "Missile Launcher Bomb": "bomb",
}

EWAR_GROUP_PATTERNS = ("ECM%", "%Sensor Damp%", "Target Painter%", "Warp Scrambler%",
                       "Stasis Web%", "Energy Neutralizer%", "Weapon Disruptor%",
                       "Warp Disruption Field%", "Stasis Grappler%")

TAG_RE = re.compile(r"<[^>]+>")
TURRET_RE = re.compile(r"\b(small|medium|large|capital)?\s*(energy|hybrid|projectile)"
                       r"\s+(?:weapon\s+)?turret", re.I)
# Missile kinds, most specific first; each maps a text pattern to the charge-group
# class key. Plain-"missile" bonuses (no kind named) apply to all of ALL_MISSILE.
MISSILE_KIND_PATTERNS = [
    (re.compile(r"\bxl\s+torpedo", re.I), "xl_torpedo"),
    (re.compile(r"\bxl\s+cruise", re.I), "xl_cruise_missile"),
    (re.compile(r"\bheavy\s+assault\b", re.I), "heavy_assault_missile"),
    (re.compile(r"\bheavy\b(?!\s+assault)", re.I), "heavy_missile"),
    (re.compile(r"\blight\b", re.I), "light_missile"),
    (re.compile(r"(?<!xl\s)\bcruise\b", re.I), "cruise_missile"),
    (re.compile(r"\brockets?\b", re.I), "rocket"),
    (re.compile(r"(?<!xl\s)\btorpedo", re.I), "torpedo"),
]
ALL_MISSILE = ["rocket", "light_missile", "heavy_missile", "heavy_assault_missile",
               "cruise_missile", "torpedo", "xl_torpedo", "xl_cruise_missile"]
# "max velocity" is flight speed (range-relevant); "explosion velocity" is an
# application stat and must NOT count as a range bonus.
VELOCITY_RE = re.compile(r"(?<!explosion\s)\bvelocity\b", re.I)


def fetch_sde(path_arg: str | None) -> Path:
    if path_arg:
        p = Path(path_arg)
        if not p.is_file():
            sys.exit(f"--sde file not found: {p}")
        if p.suffix == ".gz":
            out = p.with_suffix("")
            if not out.is_file():
                print(f"decompressing {p} ...")
                with gzip.open(p, "rb") as f, open(out, "wb") as o:
                    shutil.copyfileobj(f, o)
            return out
        return p
    tmp = Path(tempfile.gettempdir())
    gz, db = tmp / "fuzzwork-sde.sqlite.gz", tmp / "fuzzwork-sde.sqlite"
    if not db.is_file():
        print(f"downloading {SDE_URL} (~140 MB) ...")
        urllib.request.urlretrieve(SDE_URL, gz)
        print("decompressing ...")
        with gzip.open(gz, "rb") as f, open(db, "wb") as o:
            shutil.copyfileobj(f, o)
    return db


def load_attrs(cur, names) -> tuple[dict, dict]:
    """attr name -> id, and attr id -> {typeID: value}."""
    q = ("SELECT attributeID, attributeName FROM dgmAttributeTypes "
         f"WHERE attributeName IN ({','.join('?' * len(names))})")
    ids = {name: aid for aid, name in cur.execute(q, names)}
    missing = [n for n in names if n not in ids]
    if missing:
        sys.exit(f"attribute names not found in SDE (schema change?): {missing}")
    vals: dict = defaultdict(dict)
    q = ("SELECT typeID, attributeID, COALESCE(valueFloat, valueInt) "
         f"FROM dgmTypeAttributes WHERE attributeID IN ({','.join('?' * len(ids))})")
    for tid, aid, v in cur.execute(q, list(ids.values())):
        vals[aid][tid] = v
    return ids, vals


def build_weapons(cur, ids, vals) -> dict:
    a = lambda name, tid, default=None: vals[ids[name]].get(tid, default)

    # published charges per group: [(typeID, typeName)]
    charges_by_group: dict = defaultdict(list)
    for tid, name, gid in cur.execute(
            "SELECT typeID, typeName, groupID FROM invTypes WHERE published = 1"):
        charges_by_group[gid].append((tid, name))

    def charge_groups(tid):
        return [int(g) for g in (a("chargeGroup1", tid), a("chargeGroup2", tid),
                                 a("chargeGroup3", tid)) if g]

    weapons = {}

    # --- turrets --------------------------------------------------------
    for tid, name, gid in cur.execute(
            "SELECT typeID, typeName, groupID FROM invTypes "
            "WHERE groupID IN (53, 55, 74) AND published = 1"):
        opt = a("maxRange", tid)
        if not opt:
            continue
        size = SIZE_NAME.get(int(a("chargeSize", tid) or 0))
        cls = f"{TURRET_FAMILY[gid]}_{size}" if size else TURRET_FAMILY[gid]
        best = None   # (mult, fmult, charge_name)
        for cg in charge_groups(tid):
            for ctid, cname in charges_by_group.get(cg, []):
                csize = a("chargeSize", ctid)
                if size and csize and SIZE_NAME.get(int(csize)) != size:
                    continue
                mult = a("weaponRangeMultiplier", ctid, 1.0) or 1.0
                fmult = a("fallofMultiplier", ctid, 1.0) or 1.0
                if best is None or mult > best[0]:
                    best = (mult, fmult, cname)
        entry = {"name": name, "kind": "turret", "cls": cls,
                 "opt_m": round(opt, 1), "fall_m": round(a("falloff", tid, 0.0) or 0.0, 1)}
        if best:
            entry["charge"] = {"name": best[2], "mult": round(best[0], 4),
                               "fmult": round(best[1], 4)}
        weapons[str(tid)] = entry

    # --- missile launchers ----------------------------------------------
    launcher_groups = [
        (gid, gname) for gid, gname in cur.execute(
            "SELECT groupID, groupName FROM invGroups "
            "WHERE groupName LIKE 'Missile Launcher%'")
        if not any(x in gname for x in LAUNCHER_EXCLUDE)]
    group_name = {gid: gname for gid, gname in cur.execute(
        "SELECT groupID, groupName FROM invGroups")}
    for gid, gname in launcher_groups:
        cls = LAUNCHER_CLS.get(gname, gname.lower().replace(" ", "_"))
        for tid, name in charges_by_group.get(gid, []):   # launchers themselves
            best = None   # (range_m, vel, flight_s, missile_name)
            for cg in charge_groups(tid):
                if any(x in group_name.get(cg, "") for x in LAUNCHER_EXCLUDE):
                    continue
                for mtid, mname in charges_by_group.get(cg, []):
                    vel = a("maxVelocity", mtid)
                    delay_ms = a("explosionDelay", mtid)
                    if not vel or not delay_ms:
                        continue
                    flight = delay_ms / 1000.0
                    if best is None or vel * flight > best[0]:
                        best = (vel * flight, vel, flight, mname)
            if best:
                weapons[str(tid)] = {
                    "name": name, "kind": "missile", "cls": cls,
                    "missile": {"name": best[3], "vel_ms": round(best[1], 1),
                                "flight_s": round(best[2], 3)}}
    return weapons


def build_hulls(cur, report: bool) -> dict:
    hulls: dict = {}
    unmatched = []
    rows = cur.execute(
        "SELECT t.typeID, t.typeName, tr.skillID, tr.bonus, tr.bonusText "
        "FROM invTraits tr JOIN invTypes t ON t.typeID = tr.typeID "
        "JOIN invGroups g ON g.groupID = t.groupID "
        "JOIN invCategories c ON c.categoryID = g.categoryID "
        "WHERE c.categoryName = 'Ship' AND t.published = 1")
    for tid, tname, skill_id, bonus, text_raw in rows:
        if bonus is None:
            continue
        text = TAG_RE.sub("", text_raw or "").lower()
        keys = []
        for m in TURRET_RE.finditer(text):
            size_word, family = m.group(1), m.group(2).lower()
            sizes = [WORD_SIZE[size_word.lower()]] if size_word else \
                list(SIZE_NAME.values())
            for s in sizes:
                if "optimal range" in text:
                    keys.append(f"{family}_{s}_optimal")
                if "falloff" in text:
                    keys.append(f"{family}_{s}_falloff")
        has_vel = bool(VELOCITY_RE.search(text))
        if ("missile" in text or "rocket" in text or "torpedo" in text) \
                and (has_vel or "flight time" in text):
            kinds = [cls for pat, cls in MISSILE_KIND_PATTERNS if pat.search(text)]
            if not kinds:
                kinds = list(ALL_MISSILE)   # generic "missile velocity" bonus
            for k in kinds:
                if has_vel:
                    keys.append(f"{k}_velocity")
                if "flight time" in text:
                    keys.append(f"{k}_flight")
        if not keys:
            if report and ("optimal range" in text or "falloff" in text
                           or "velocity" in text or "flight time" in text) \
                    and ("turret" in text or "missile" in text
                         or "rocket" in text or "torpedo" in text):
                unmatched.append((tname, skill_id, bonus, text.strip()))
            continue
        # skillID > 0: per-level bonus, assume level V; skillID < 0: role bonus.
        mult = 1.0 + (bonus * 5 / 100.0 if skill_id and skill_id > 0
                      else bonus / 100.0)
        h = hulls.setdefault(str(tid), {"name": tname, "b": {}})
        for k in set(keys):
            h["b"][k] = round(h["b"].get(k, 1.0) * mult, 4)
    if report:
        print(f"\n--- {len(unmatched)} range-looking trait rows without a rule ---")
        for tname, sid, bonus, text in unmatched:
            print(f"  {tname} (skill {sid}, {bonus:+}%): {text}")
    return hulls


def build_ewar_ids(cur) -> list:
    where = " OR ".join("g.groupName LIKE ?" for _ in EWAR_GROUP_PATTERNS)
    q = ("SELECT t.typeID FROM invTypes t JOIN invGroups g ON g.groupID = t.groupID "
         f"WHERE t.published = 1 AND ({where})")
    return sorted(tid for (tid,) in cur.execute(q, EWAR_GROUP_PATTERNS))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sde", help="path to Fuzzwork sqlite (or .gz); downloads if omitted")
    ap.add_argument("--report", action="store_true",
                    help="print unmatched range-related trait rows")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    con = sqlite3.connect(fetch_sde(args.sde))
    cur = con.cursor()
    ids, vals = load_attrs(cur, ATTR_NAMES)
    weapons = build_weapons(cur, ids, vals)
    hulls = build_hulls(cur, args.report)
    ewar = build_ewar_ids(cur)

    data = {"version": 1,
            "sde": f"fuzzwork latest-sqlite, generated {datetime.date.today()}",
            "skills": SKILLS, "weapons": weapons, "hulls": hulls,
            "ewar_type_ids": ewar}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True),
                   encoding="utf-8")
    n_t = sum(1 for w in weapons.values() if w["kind"] == "turret")
    n_m = len(weapons) - n_t
    print(f"wrote {out} — {n_t} turrets, {n_m} launchers, {len(hulls)} hulls "
          f"with range traits, {len(ewar)} e-war modules "
          f"({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
