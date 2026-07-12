"""Range math against the real committed weapon_ranges.json.

Expected values are the SDE-derived chains (best ammo, all skills V, hull
bonus only), frozen with ±5% tolerance so balance patches after a data
regeneration fail loudly instead of silently drifting.
"""
import pytest

from eve_localwatcher import weaponrange

HBL2 = 3025            # Heavy Beam Laser II
HNI = 33155            # Harbinger Navy Issue
ARTY1400 = 2961        # 1400mm Howitzer Artillery II
TORNADO = 4310
HAML2 = 25715          # Heavy Assault Missile Launcher II
CERBERUS = 11993
TORP2 = 2420           # Torpedo Launcher II
GOLEM = 28710


def test_data_loads():
    d = weaponrange.load_data()
    assert d is not None
    # floor counts: a silent generator regression must fail loudly
    assert sum(1 for w in d["weapons"].values() if w["kind"] == "turret") > 150
    assert sum(1 for w in d["weapons"].values() if w["kind"] == "missile") > 50
    assert len(d["hulls"]) > 100
    assert len(d["ewar_type_ids"]) > 100


def test_harbinger_navy_beam_laser():
    # 26.4 km base × 1.8 Aurora × 1.25 Sharpshooter V × 1.25 hull role = 74.25
    info = weaponrange.max_range(HNI, HBL2)
    assert info.weapon_name == "Heavy Beam Laser II"
    assert info.charge_name == "Aurora M"
    assert info.range_km == pytest.approx(74.2, rel=0.05)


def test_tornado_artillery_has_falloff():
    info = weaponrange.max_range(TORNADO, ARTY1400)
    assert info.range_km == pytest.approx(108.0, rel=0.05)
    assert info.falloff_km == pytest.approx(48.1, rel=0.05)


def test_cerberus_ham_missile_chain():
    # vel × 1.5 Projection × 2.0 hull HAM bonus × flight × 1.5 Bombardment
    info = weaponrange.max_range(CERBERUS, HAML2)
    assert info.range_km == pytest.approx(60.8, rel=0.05)
    assert info.falloff_km is None


def test_golem_torpedo_velocity_only_no_explosion_velocity():
    # regression: "explosion velocity" traits must NOT count as range bonus
    info = weaponrange.max_range(GOLEM, TORP2)
    assert info.range_km == pytest.approx(65.6, rel=0.05)


def test_unknown_weapon_returns_none():
    assert weaponrange.max_range(HNI, 999999999) is None
    assert weaponrange.max_range(HNI, None) is None


def test_unknown_hull_degrades_to_no_hull_bonus():
    info = weaponrange.max_range(999999999, HBL2)
    # same chain without the 1.25 hull bonus
    assert info.range_km == pytest.approx(74.2 / 1.25, rel=0.05)


def test_ewar_ids_frozen_set():
    ids = weaponrange.ewar_type_ids()
    assert isinstance(ids, frozenset) and len(ids) > 100
