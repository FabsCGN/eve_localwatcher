"""Recent-kill weapon extraction + cyno signals from stubbed killmail data."""
from datetime import datetime, timedelta, timezone

from eve_localwatcher import threatcheck, weaponrange

CHAR = 1001
VICTIM = 2002
SHIP = 33155      # Harbinger Navy Issue (not cyno-capable)
WEAPON = 3025     # Heavy Beam Laser II
NON_CYNO_SHIP = 587   # Rifter — a T1 frigate, never cyno-capable
CYNO_MOD = next(iter(weaponrange.cyno_modules()))
CYNO_SHIP = next(iter(weaponrange.cyno_capable_ships()))


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


def _run_full(mails):
    return threatcheck._recent_ships(StubESI(mails), StubZK(len(mails)), CHAR)


def _run(mails):
    # backward-compatible 3-tuple for the weapon-focused tests
    return _run_full(mails)[:3]


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


# --- cyno signal counting -------------------------------------------------
def _cyno_loss(minutes_ago, fitted=True, ship=CYNO_SHIP):
    items = [{"item_type_id": CYNO_MOD, "flag": 27}] if fitted else []
    return {"killmail_time": _iso(minutes_ago),
            "victim": {"character_id": CHAR, "ship_type_id": ship,
                       "items": items},
            "attackers": [{"character_id": 3003, "ship_type_id": NON_CYNO_SHIP}]}


def test_cyno_fitted_and_capable_counted():
    mails = {i: _cyno_loss(i * 2) for i in range(5)}
    _s, _l, _w, cyno = _run_full(mails)
    assert cyno.fitted_losses == 5
    assert cyno.capable_hulls == 5      # each loss hull is cyno-capable
    assert cyno.losses_seen == 5


def test_cyno_in_cargo_not_fitted():
    km = _cyno_loss(5)
    km["victim"]["items"][0]["flag"] = 5    # Cargo, not a high slot
    _s, _l, _w, cyno = _run_full({0: km})
    assert cyno.fitted_losses == 0
    assert cyno.capable_hulls == 1          # hull is still cyno-capable


def test_non_cyno_ship_and_no_module():
    km = _cyno_loss(5, fitted=False, ship=NON_CYNO_SHIP)
    _s, _l, _w, cyno = _run_full({0: km})
    assert cyno.fitted_losses == 0 and cyno.capable_hulls == 0


def test_kill_in_cyno_hull_counts_capable_not_fitted():
    # a KILL (char is attacker) flying a cyno-capable hull: capable, but a
    # cyno-fitted count only comes from losses
    km = {"killmail_time": _iso(5),
          "victim": {"character_id": VICTIM, "ship_type_id": NON_CYNO_SHIP},
          "attackers": [{"character_id": CHAR, "ship_type_id": CYNO_SHIP}]}
    _s, _l, _w, cyno = _run_full({0: km})
    assert cyno.capable_hulls == 1 and cyno.fitted_losses == 0
