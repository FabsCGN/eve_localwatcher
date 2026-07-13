"""Config round-trip for every radar field (the hand-written to_dict/from_dict
pattern silently drops fields that are added in only one place)."""
from eve_localwatcher.config import Config

RADAR_FIELDS = {
    "radar_enabled": True,
    "radar_jump_range": 7,
    "radar_own_system": "K7D-II",
    "radar_follow_location": True,
    "radar_intel_channel": "OnlyQuerious. Intel",
    "radar_chatlog_dir": r"C:\somewhere\Chatlogs",
    "radar_sound_path": r"C:\sounds\anflug.wav",
    "radar_volume": 55,
    "radar_max_pilots": 25,
    "radar_sighting_max_min": 45,
    "radar_max_enrich_per_kill": 3,
    "sso_scopes": ["esi-fleets.read_fleet.v1", "esi-location.read_location.v1"],
}


def test_radar_fields_roundtrip():
    c = Config()
    for k, v in RADAR_FIELDS.items():
        setattr(c, k, v)
    c2 = Config.from_dict(c.to_dict())
    for k, v in RADAR_FIELDS.items():
        assert getattr(c2, k) == v, k


def test_defaults_survive_empty_dict():
    c = Config.from_dict({})
    assert c.radar_enabled is False
    assert c.radar_jump_range == 5
    assert c.sso_scopes == []
