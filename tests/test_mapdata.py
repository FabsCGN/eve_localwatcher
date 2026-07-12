"""Map graph: BFS distances, bubbles and system-token resolution."""
import pytest

from eve_localwatcher import mapdata

# synthetic graph: 1—2—3—4—5 chain, 6 hangs off 2, 7/8 isolated (no gates)
SYNTH = {
    "systems": {"1": ["Alpha", 0.5], "2": ["Beta", 0.4], "3": ["Gamma", -0.1],
                "4": ["Delta", -0.3], "5": ["Epsilon", -0.5],
                "6": ["P-ZMZV", 0.0], "7": ["Lonely", -1.0],
                "8": ["Alphard", 0.1]},
    "adj": {"1": [2], "2": [1, 3, 6], "3": [2, 4], "4": [3, 5], "5": [4],
            "6": [2]},
}


@pytest.fixture(autouse=True)
def synth_graph():
    saved = (mapdata._names, mapdata._by_lower, mapdata._adj, mapdata._failed)
    mapdata._install(SYNTH)
    yield
    mapdata._names, mapdata._by_lower, mapdata._adj, mapdata._failed = saved


def test_distance_and_symmetry():
    assert mapdata.distance(1, 1) == 0
    assert mapdata.distance(1, 3) == 2
    assert mapdata.distance(3, 1) == 2
    assert mapdata.distance(1, 5) == 4


def test_max_hops_bound():
    assert mapdata.distance(1, 5, max_hops=3) is None


def test_unreachable_returns_none():
    assert mapdata.distance(1, 7) is None       # Pochven/gateless case


def test_systems_within():
    b = mapdata.systems_within(2, 2)
    assert b == {2: 0, 1: 1, 3: 1, 6: 1, 4: 2}


def test_resolve_exact_case_insensitive():
    assert mapdata.resolve_system("gamma") == 3
    assert mapdata.resolve_system("P-ZMZV*") == 6     # punctuation stripped


def test_prefix_only_inside_bubble():
    bubble = {2: 0, 1: 1, 3: 1, 6: 1}
    assert mapdata.resolve_system("P-Z", restrict_ids=bubble.keys()) == 6
    assert mapdata.resolve_system("P-Z") is None      # no map-wide prefixing


def test_ambiguous_prefix_returns_none():
    bubble = {1: 1, 8: 2}          # Alpha vs Alphard share the prefix "Al"
    assert mapdata.resolve_system("Al", restrict_ids=bubble.keys()) is None
    assert mapdata.resolve_system("Alphar", restrict_ids=bubble.keys()) == 8
    assert mapdata.resolve_system("Xy", restrict_ids=bubble.keys()) is None
    # single characters never resolve (chat noise)
    assert mapdata.resolve_system("A", restrict_ids=bubble.keys()) is None


def test_names_and_security():
    assert mapdata.name_for_id(6) == "P-ZMZV"
    assert mapdata.id_for_name("beta") == 2
    assert mapdata.security(5) == -0.5


def test_real_data_if_present():
    """Against the committed JSON (skipped in a bare checkout)."""
    saved = (mapdata._names, mapdata._by_lower, mapdata._adj, mapdata._failed)
    mapdata._names = None
    mapdata._failed = False
    try:
        if not mapdata.load():
            pytest.skip("map_graph.json not generated")
        jita = mapdata.id_for_name("Jita")
        peri = mapdata.id_for_name("Perimeter")
        assert jita and peri and mapdata.distance(jita, peri) == 1
        assert len(mapdata.systems_within(jita, 2)) > 10
    finally:
        (mapdata._names, mapdata._by_lower, mapdata._adj,
         mapdata._failed) = saved
