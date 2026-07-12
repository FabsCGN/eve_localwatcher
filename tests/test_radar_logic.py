"""Radar core logic: approach detection/debounce and killmail filtering."""
from datetime import datetime, timedelta, timezone

from eve_localwatcher.radar import (PilotTrack, Sighting, check_approach,
                                    kill_minutes_old, pick_attackers)

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


def sig(sysid, jumps, mins_ago, source="zkill"):
    return Sighting(sysid, f"S{sysid}", jumps, source,
                    NOW - timedelta(minutes=mins_ago))


def test_approach_fires_on_decreasing_distinct_systems():
    t = PilotTrack(1, "Hunter")
    t.sightings = [sig(102, 2, 1), sig(103, 3, 5)]
    assert check_approach(t, 5, NOW) == (3, 2)


def test_mixed_sources_count_as_movement():
    t = PilotTrack(1, "Hunter")
    t.sightings = [sig(102, 2, 1, "intel"), sig(103, 3, 5, "zkill")]
    assert check_approach(t, 5, NOW) == (3, 2)


def test_no_rewarn_without_further_decrease():
    t = PilotTrack(1, "Hunter")
    t.sightings = [sig(102, 2, 1), sig(103, 3, 5)]
    assert check_approach(t, 5, NOW) == (3, 2)
    t.sightings.insert(0, sig(102, 2, 0))          # still 2 jumps
    assert check_approach(t, 5, NOW) is None
    t.sightings.insert(0, sig(101, 1, 0, "intel"))  # closes further
    assert check_approach(t, 5, NOW) == (2, 1)


def test_same_system_twice_is_camping_not_movement():
    t = PilotTrack(2, "Camper")
    t.sightings = [sig(102, 2, 1), sig(102, 2, 10)]
    assert check_approach(t, 5, NOW) is None


def test_increasing_distance_no_warning():
    t = PilotTrack(3, "Leaver")
    t.sightings = [sig(104, 4, 1), sig(102, 2, 5)]
    assert check_approach(t, 5, NOW) is None


def test_stale_latest_sighting_no_warning():
    t = PilotTrack(4, "Old")
    t.sightings = [sig(102, 2, 20), sig(103, 3, 30)]
    assert check_approach(t, 5, NOW) is None


def test_latest_outside_range_no_warning():
    t = PilotTrack(5, "Far")
    t.sightings = [sig(107, 7, 1), sig(108, 8, 5)]
    assert check_approach(t, 5, NOW) is None


def test_single_sighting_never_warns():
    t = PilotTrack(6, "Once")
    t.sightings = [sig(102, 2, 1)]
    assert check_approach(t, 5, NOW) is None


def test_retreat_rearms():
    t = PilotTrack(7, "InOut")
    t.sightings = [sig(102, 2, 9), sig(103, 3, 10)]
    assert check_approach(t, 5, NOW) == (3, 2)
    t.sightings.insert(0, sig(104, 4, 5))          # retreats
    assert check_approach(t, 5, NOW) is None       # re-armed, but increasing
    t.sightings.insert(0, sig(102, 2, 1))          # comes back in
    assert check_approach(t, 5, NOW) == (4, 2)


def test_manual_sightings_ignored_for_movement():
    t = PilotTrack(8, "Manual")
    t.sightings = [Sighting(None, "", None, "manuell", NOW),
                   sig(103, 3, 5)]
    assert check_approach(t, 5, NOW) is None


# --------------------------------------------------------- killmail filtering
def _km(attackers):
    return {"attackers": attackers,
            "killmail_time": (NOW - timedelta(minutes=3)).isoformat()
            .replace("+00:00", "Z")}


def test_pick_attackers_filters_and_caps():
    km = _km([
        {"character_id": None, "damage_done": 900},              # NPC
        {"character_id": 10, "damage_done": 100, "final_blow": False},
        {"character_id": 11, "damage_done": 50, "final_blow": True},
        {"character_id": 12, "damage_done": 300, "final_blow": False},
        {"character_id": 99, "damage_done": 999, "final_blow": False},  # self
    ])
    picked = pick_attackers(km, own_char_id=99, fs=None, cap=2)
    assert [a["character_id"] for a in picked] == [11, 12]


def test_pick_attackers_friendly_filter():
    class FS:
        def is_friendly(self, cid, corp, alli):
            return cid == 10
    km = _km([{"character_id": 10, "damage_done": 500},
              {"character_id": 11, "damage_done": 100}])
    picked = pick_attackers(km, None, FS(), cap=5)
    assert [a["character_id"] for a in picked] == [11]


def test_kill_minutes_old():
    km = _km([])
    assert 2.5 < kill_minutes_old(km, NOW) < 3.5
    assert kill_minutes_old({"killmail_time": "kaputt"}, NOW) is None
    assert kill_minutes_old({}, NOW) is None
