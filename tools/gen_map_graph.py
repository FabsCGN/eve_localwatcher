"""Generate eve_localwatcher/data/map_graph.json from the Fuzzwork SDE.

Dev-only tool — the generated JSON is committed and bundled into the exe.
Re-run after an EVE expansion changes the map (rare).

Usage:
    python tools/gen_map_graph.py --sde path/to/sde.sqlite

Emits the k-space stargate graph used by the kill radar: every solar system
in the 30xxxxxx id range (named even when gateless, so killmails can always
be labelled) plus the undirected gate adjacency. Wormholes/Abyssal (31/32xx)
are excluded — they can never be inside a gate-jump bubble.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from gen_weapon_ranges import fetch_sde   # same --sde / download-to-temp logic

OUT_PATH = Path(__file__).resolve().parents[1] / "eve_localwatcher" / "data" / "map_graph.json"

KSPACE_MIN, KSPACE_MAX = 30000000, 30999999


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sde", help="path to Fuzzwork sqlite (or .gz); downloads if omitted")
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args()

    con = sqlite3.connect(fetch_sde(args.sde))
    cur = con.cursor()

    systems = {}
    for sid, name, sec in cur.execute(
            "SELECT solarSystemID, solarSystemName, security FROM mapSolarSystems "
            "WHERE solarSystemID BETWEEN ? AND ?", (KSPACE_MIN, KSPACE_MAX)):
        systems[str(sid)] = [name, round(sec or 0.0, 1)]

    adj = defaultdict(set)
    for a, b in cur.execute(
            "SELECT fromSolarSystemID, toSolarSystemID FROM mapSolarSystemJumps"):
        if str(a) in systems and str(b) in systems:
            adj[a].add(b)
            adj[b].add(a)

    data = {"generated": str(datetime.date.today()),
            "systems": systems,
            "adj": {str(k): sorted(v) for k, v in adj.items()}}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True),
                   encoding="utf-8")
    n_edges = sum(len(v) for v in adj.values()) // 2
    print(f"wrote {out} — {len(systems)} systems, {n_edges} gate edges "
          f"({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
