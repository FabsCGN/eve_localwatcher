"""Recent-kill weapon extraction from stubbed ESI/zKill killmail data."""
from datetime import datetime, timedelta, timezone

from eve_localwatcher import threatcheck

CHAR = 1001
VICTIM = 2002
SHIP = 33155      # Harbinger Navy Issue
WEAPON = 3025     # Heavy Beam Laser II


def _iso(minutes_ago):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return t.isoformat().replace("+00:00", "Z")


def _kill_mail(minutes_ago, weapon=WEAPON, attacker=CHAR):
    return {"killmail_time": _iso(minutes_ago),
            "victim": {"character_id": VICTIM, "ship_type_id": 587},
            "attackers": [{"character_id": attacker, "ship_type_id": SHIP,
                           "weapon_type_id": weapon}]}


def _loss_mail(minutes_ago):
    return {"killmail_time": _iso(minutes_ago),
            "victim": {"character_id": CHAR, "ship_type_id": SHIP},
            "attackers": [{"character_id": 3003, "ship_type_id": 587,
                           "weapon_type_id": 999}]}


class StubESI:
    def __init__(self, mails):
        self.mails = mails

    def killmail(self, kid, kh):
        return self.mails[kid]

    def names_for_ids(self, ids):
        return {i: f"Type {i}" for i in ids}


class StubZK:
    def __init__(self, n):
        self.n = n

    def recent_killmails(self, char_id, limit=8):
        return [(i, "hash") for i in range(min(self.n, limit))]


def _run(mails):
    esi = StubESI(mails)
    return threatcheck._recent_ships(esi, StubZK(len(mails)), CHAR)


def test_fresh_kill_yields_weapon():
    ships, _last, weapon = _run({0: _kill_mail(30)})
    assert weapon is not None
    ship_id, wid, wname, mins = weapon
    assert (ship_id, wid) == (SHIP, WEAPON)
    assert wname == f"Type {WEAPON}"
    assert 29 <= mins <= 31
    assert ships and ships[0].kind == "kill"


def test_old_kill_yields_no_weapon():
    _s, _l, weapon = _run({0: _kill_mail(180)})
    assert weapon is None


def test_loss_yields_no_weapon():
    _s, _l, weapon = _run({0: _loss_mail(30)})
    assert weapon is None


def test_weapon_equal_ship_means_no_weapon_recorded():
    _s, _l, weapon = _run({0: _kill_mail(30, weapon=SHIP)})
    assert weapon is None


def test_newest_fresh_kill_wins_over_duplicate_hull():
    # two kills in the same hull: the dedup must not skip the weapon check,
    # and the NEWEST kill's weapon is reported
    mails = {0: _kill_mail(10, weapon=WEAPON), 1: _kill_mail(60, weapon=555)}
    _s, _l, weapon = _run(mails)
    assert weapon[1] == WEAPON and 9 <= weapon[3] <= 11


def test_missing_timestamp_is_ignored():
    km = _kill_mail(30)
    del km["killmail_time"]
    _s, _l, weapon = _run({0: km})
    assert weapon is None
