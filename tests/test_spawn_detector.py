"""Spawn detectors: change-vs-baseline detection.

Regression for the false alarm where static bright overview text ("Nothing
Found", column headers) made an EMPTY overview count as populated the moment
the last wave armed the detectors.
"""
import numpy as np

from eve_localwatcher.config import Config, Region
from eve_localwatcher.scanner import Scanner


class FakeCap:
    """Overview mock: static bright 'Nothing Found' text on dark background,
    plus an optional NPC row that can be toggled."""

    def __init__(self):
        self.npc_visible = False

    def grab(self, reg):
        img = np.full((40, 100, 3), 10, dtype=np.uint8)
        img[15:25, 30:70] = 160          # static text — always bright
        if self.npc_visible:
            img[2:10, 2:90] = 200        # NPC row appears at the top
        return img


def make_scanner():
    cfg = Config()
    cfg.use_window_relative = False
    cfg.dread_enabled = True
    cfg.dread_region = Region(0, 0, 100, 40)
    s = Scanner(cfg, on_tick=lambda r: None, on_alarm=lambda r: None)
    s._reset_state()
    return s, cfg


def test_static_text_does_not_fire_on_last_wave_start():
    s, cfg = make_scanner()
    cap = FakeCap()
    # outside the last wave: learn the empty look (static text included)
    fired, px = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert not fired and px > cfg.spawn_min_bright_px  # bright, but only learning
    # last wave starts, overview unchanged → must NOT fire (the old bug)
    s._last_wave_active = True
    for _ in range(5):
        fired, changed = s._detect_spawn(cap, cfg.dread_region, "dread")
        assert not fired and changed == 0


def test_npc_appearance_fires_once_and_rearms():
    s, cfg = make_scanner()
    cap = FakeCap()
    s._detect_spawn(cap, cfg.dread_region, "dread")     # learn empty
    s._last_wave_active = True
    cap.npc_visible = True
    fired, changed = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert fired and changed >= cfg.spawn_min_bright_px
    fired, _ = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert not fired                                    # persistent NPC: no re-fire
    cap.npc_visible = False                             # died/despawned → matches baseline
    fired, changed = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert not fired and changed == 0
    cap.npc_visible = True                              # second spawn
    fired, _ = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert fired


def test_mid_wave_start_treats_first_frame_as_empty():
    s, cfg = make_scanner()
    cap = FakeCap()
    s._last_wave_active = True                          # scan started mid-wave
    fired, changed = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert not fired and changed == 0                   # first frame = baseline
    cap.npc_visible = True
    fired, _ = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert fired


def test_baseline_refreshes_outside_last_wave():
    s, cfg = make_scanner()
    cap = FakeCap()
    s._detect_spawn(cap, cfg.dread_region, "dread")
    cap.npc_visible = True                              # UI changed between sites
    s._detect_spawn(cap, cfg.dread_region, "dread")     # re-learns while not last wave
    s._last_wave_active = True
    fired, changed = s._detect_spawn(cap, cfg.dread_region, "dread")
    assert not fired and changed == 0                   # new look IS the baseline
