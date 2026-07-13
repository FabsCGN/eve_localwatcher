"""Cyno-suspect flag: both trigger populations of threat.assess()."""
from datetime import datetime, timedelta, timezone

from eve_localwatcher import threat


def _pub(age_days):
    if age_days is None:
        return {}
    bd = datetime.now(timezone.utc) - timedelta(days=age_days)
    return {"birthday": bd.isoformat().replace("+00:00", "Z")}


def _zstats(kills):
    return {"shipsDestroyed": kills, "dangerRatio": 10,
            "groups": {"1": {"groupID": 26, "shipsDestroyed": kills}}}


def _assess(age_days, kills, alliance):
    return threat.assess("Test Pilot", 1, _pub(age_days), _zstats(kills),
                         "Some Corp", alliance)


def test_old_empty_board_in_alliance_is_cyno():
    p = _assess(800, 2, "Some Alliance")
    assert "cyno" in p.flags
    assert p.tier in ("medium", "high")     # cyno raises to at least medium


def test_old_empty_board_without_alliance_is_not_cyno():
    assert "cyno" not in _assess(800, 2, None).flags


def test_old_active_board_in_alliance_is_not_cyno():
    assert "cyno" not in _assess(800, 20, "Some Alliance").flags


def test_middle_aged_empty_board_is_not_cyno():
    # older than fresh window but younger than the cyno age threshold
    assert "cyno" not in _assess(200, 0, "Some Alliance").flags


def test_young_no_kills_still_cyno():
    # regression: the original young-alt trigger stays intact (no alliance needed)
    assert "cyno" in _assess(30, 0, None).flags


def test_unknown_age_never_triggers_new_rule():
    assert "cyno" not in _assess(None, 0, "Some Alliance").flags


def test_thresholds_are_configurable():
    p = threat.assess("T", 1, _pub(400), _zstats(8), None, "A",
                      cyno_max_kills=10, cyno_min_age_days=350)
    assert "cyno" in p.flags


def test_aggregate_counts_cyno():
    ps = [_assess(800, 0, "A"), _assess(800, 50, "A")]
    assert threat.aggregate(ps)["cyno"] == 1


# --- killboard-evidence triggers (each alone is enough) --------------------
def _clean():
    """A pilot who passes none of the age/kill cyno triggers."""
    return dict(name="Vet", char_id=1, char_pub=_pub(500),
                zstats=_zstats(200), corp_name="C", alliance_name=None)


def test_cyno_fitted_losses_triggers():
    p = threat.assess(**_clean(), cyno_fitted_losses=5)
    assert "cyno" in p.flags
    assert p.cyno_fitted_losses == 5


def test_cyno_fitted_below_threshold_no_flag():
    assert "cyno" not in threat.assess(**_clean(), cyno_fitted_losses=4).flags


def test_cyno_capable_hulls_triggers():
    p = threat.assess(**_clean(), cyno_capable_hulls=6)
    assert "cyno" in p.flags
    assert p.cyno_capable_hulls == 6


def test_cyno_capable_below_threshold_no_flag():
    # "über 5" = strictly more than 5, so exactly 5 must NOT fire
    assert "cyno" not in threat.assess(**_clean(), cyno_capable_hulls=5).flags


def test_cyno_evidence_thresholds_configurable():
    p = threat.assess(**_clean(), cyno_capable_hulls=3, cyno_capable_min=3)
    assert "cyno" in p.flags


def test_no_cyno_evidence_stays_clean():
    assert "cyno" not in threat.assess(**_clean()).flags
