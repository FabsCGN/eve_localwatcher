"""The scan loop: two-stage detection, debounce, optional auto-learn.

Runs in a background thread and reports via callbacks (so the Tk UI stays on
the main thread). The scanner never touches Tk directly.

Stage 1 (header count): a rise above the calibrated baseline means someone
joined — fires even if they appear below the visible rows.
Stage 2 (colour sampling): every visible pilot row whose icon-slot colour is
NOT in the friendly whitelist is a threat (an empty/untagged slot included).

Combined, they also cover the swap case (one out, one in, same count): Stage 1
misses it but Stage 2 sees the changed colour signature.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import color, ocr, winutil
from .capture import Capturer
from .config import Config, RegionTuple


@dataclass
class RowSample:
    index: int
    rgb: Tuple[int, int, int]
    status: str                       # color.FRIENDLY / THREAT / EMPTY

    @property
    def friendly(self) -> bool:
        return self.status == color.FRIENDLY

    @property
    def is_threat(self) -> bool:
        return self.status == color.THREAT


@dataclass
class TickResult:
    ok: bool
    window_found: bool
    count: Optional[int]              # header OCR result (None if unavailable)
    rows: List[RowSample] = field(default_factory=list)
    threats: List[RowSample] = field(default_factory=list)
    new_threat: bool = False          # a not-seen-before threat this tick
    count_increased: bool = False     # Stage 1 trigger
    cap_region: Optional[Tuple[int, int, int, int]] = None  # resolved abs region
    haven_stage: Optional[int] = None   # current Haven pocket (N in "N/M")
    haven_total: Optional[int] = None   # total pockets (M)
    haven_reached: bool = False         # just reached the final pocket → last-wave alarm
    last_wave: bool = False             # currently on the final pocket (detectors armed)
    dread_spawn: bool = False           # Dread/Titan overview went empty → populated
    faction_spawn: bool = False         # Faction overview went empty → populated
    threat_names: List[str] = field(default_factory=list)  # OCR'd names (auto-threat)
    error: Optional[str] = None


# Callbacks: (TickResult) -> None
TickCB = Callable[[TickResult], None]
AlarmCB = Callable[[TickResult], None]


def resolve_regions(cfg: Config) -> Tuple[Optional[RegionTuple], Optional[RegionTuple], bool]:
    """Turn stored (possibly window-relative) regions into absolute rects."""
    dx, dy, window_found = 0, 0, False
    if cfg.use_window_relative:
        origin = winutil.find_window_origin(cfg.window_title)
        if origin is not None:
            dx, dy = origin
            window_found = True
        else:
            # Window not found — can't resolve relative coords this tick.
            return None, None, False

    cap = cfg.capture_region.offset(dx, dy).as_tuple() if cfg.capture_region.is_valid() else None
    hdr = cfg.header_region.offset(dx, dy).as_tuple() if cfg.header_region.is_valid() else None
    return cap, hdr, window_found


def resolve_one(cfg: Config, region) -> Optional[RegionTuple]:
    """Resolve a single (possibly window-relative) region to absolute coords.

    Returns None if the region is unset, or window-relative but the window
    can't be located.
    """
    if not region.is_valid():
        return None
    dx, dy = 0, 0
    if cfg.use_window_relative:
        origin = winutil.find_window_origin(cfg.window_title)
        if origin is None:
            return None
        dx, dy = origin
    return region.offset(dx, dy).as_tuple()


def sample_rows(capture_img: np.ndarray, cfg: Config, n_rows: int) -> List[RowSample]:
    """Median-sample the icon column for the first ``n_rows`` pilot rows.

    Only the narrow left icon strip is read — never the row background — so a
    selected (highlighted) row is not mistaken for a hostile.
    """
    h, w, _ = capture_img.shape
    x0 = max(0, cfg.icon_column_x_offset)
    x1 = min(w, x0 + max(1, cfg.icon_sample_width))
    out: List[RowSample] = []
    rh = max(1, cfg.row_height)
    for i in range(n_rows):
        top = cfg.first_row_y_offset + i * rh
        cy = top + rh // 2
        y0 = max(0, cy - max(1, rh // 4))
        y1 = min(h, cy + max(1, rh // 4) + 1)
        if y0 >= y1 or x0 >= x1:
            break
        patch = capture_img[y0:y1, x0:x1]
        if patch.size == 0:
            break
        rgb = color.median_color(patch)
        status = color.classify(rgb, cfg.friendly_colors, cfg.color_tolerance,
                                cfg.tag_min_value)
        out.append(RowSample(i, rgb, status))
    return out


def ocr_row_name(capture_img: np.ndarray, cfg: Config, row_index: int) -> str:
    """OCR the name text of one pilot row (for the auto threat-check)."""
    h, w, _ = capture_img.shape
    rh = max(1, cfg.row_height)
    top = cfg.first_row_y_offset + row_index * rh
    y0 = max(0, top + 1)
    y1 = min(h, top + rh - 1)
    x0 = max(0, cfg.name_x_offset)
    x1 = min(w, x0 + max(1, cfg.name_width))
    if y0 >= y1 or x0 >= x1:
        return ""
    return ocr.read_line(capture_img[y0:y1, x0:x1])


class Scanner:
    def __init__(self, cfg: Config, on_tick: TickCB, on_alarm: AlarmCB,
                 on_config_change: Optional[Callable[[], None]] = None) -> None:
        self.cfg = cfg
        self._on_tick = on_tick
        self._on_alarm = on_alarm
        self._on_config_change = on_config_change
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # debounce / state
        self._seen_threat_buckets: set = set()
        self._last_alarmed_count: Optional[int] = None
        # auto-learn: bucket -> first-seen monotonic time
        self._threat_since: Dict[Tuple[int, int, int], float] = {}
        # haven: armed until we fire on the final pocket; re-armed below it
        self._haven_armed: bool = True
        self._haven_none_streak: int = 0
        self._haven_last_stage: Optional[int] = None  # last accepted N (monotonic filter)
        self._last_wave_active: bool = False           # on the final pocket right now
        # last-wave spawn detectors: armed while their overview is empty, fire once
        # when it becomes populated, re-arm when it empties again.
        self._dread_armed: bool = True
        self._faction_armed: bool = True

    # ---------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._reset_state()
        self._thread = threading.Thread(target=self._run, name="eve-scan", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _reset_state(self) -> None:
        self._seen_threat_buckets.clear()
        self._threat_since.clear()
        self._last_alarmed_count = self.cfg.baseline_count
        self._haven_armed = True
        self._haven_none_streak = 0
        self._haven_last_stage = None
        self._last_wave_active = False
        self._dread_armed = True
        self._faction_armed = True

    # -------------------------------------------------------------------- loop
    def _run(self) -> None:
        cap = Capturer()
        try:
            while not self._stop.is_set():
                t0 = time.monotonic()
                # One bad tick must never kill the scan loop — surface it and
                # keep going (otherwise the scanner dies silently).
                try:
                    result = self._tick(cap)
                    self._on_tick(result)
                    if result.ok and (result.new_threat or result.count_increased
                                      or result.haven_reached or result.dread_spawn
                                      or result.faction_spawn):
                        self._on_alarm(result)
                except Exception as e:  # pragma: no cover - defensive
                    try:
                        self._on_tick(TickResult(False, False, None,
                                                 error=f"tick crash: {e}"))
                    except Exception:
                        pass
                # sleep the remainder of the interval, staying responsive to stop
                elapsed = (time.monotonic() - t0) * 1000.0
                remaining = max(0.0, self.cfg.scan_interval_ms - elapsed) / 1000.0
                self._stop.wait(remaining)
        finally:
            cap.close()

    def _tick(self, cap: Capturer) -> TickResult:
        try:
            cap_region, hdr_region, window_found = resolve_regions(self.cfg)
        except Exception as e:  # pragma: no cover
            return TickResult(False, False, None, error=f"region resolve: {e}")

        if self.cfg.use_window_relative and not window_found:
            return TickResult(False, False, None,
                              error=f"EVE window '{self.cfg.window_title}' not found")

        # The hostile stages run if Local-alarm OR auto-threat needs them.
        local_active = self.cfg.local_alarm_enabled or self.cfg.auto_threat_enabled

        # --- Stage 1: header count ---------------------------------------
        count: Optional[int] = None
        if local_active and hdr_region is not None:
            try:
                count = ocr.read_count(cap.grab(hdr_region))
            except Exception as e:
                return TickResult(False, window_found, None, error=f"header grab: {e}")

        count_increased = False
        if count is not None:
            base = self._last_alarmed_count
            if base is not None and count > base:
                count_increased = True
            self._last_alarmed_count = count

        # --- Stage 2: colour sampling ------------------------------------
        rows: List[RowSample] = []
        img = None
        if local_active and cap_region is not None and self.cfg.friendly_colors:
            try:
                img = cap.grab(cap_region)
            except Exception as e:
                return TickResult(False, window_found, count, error=f"list grab: {e}")
            # Bound row count by the headcount when we have it, else fill region.
            max_by_region = max(1, img.shape[0] // max(1, self.cfg.row_height))
            n = min(self.cfg.max_visible_rows, max_by_region)
            if count is not None:
                n = min(n, count)
            rows = sample_rows(img, self.cfg, n)

        threats = [r for r in rows if r.is_threat]
        new_threat = self._update_threat_debounce(threats)
        self._maybe_auto_learn(threats)

        # OCR the names of threat rows for the auto threat-check (opt-in).
        threat_names: List[str] = []
        if self.cfg.auto_threat_enabled and img is not None and threats:
            for r in threats:
                nm = ocr_row_name(img, self.cfg, r.index)
                if nm:
                    threat_names.append(nm)

        # --- Stage 3: Haven pocket counter (opt-in) ----------------------
        haven_stage = haven_total = None
        haven_reached = False
        if self.cfg.haven_enabled:
            hreg = resolve_one(self.cfg, self.cfg.haven_region)
            if hreg is not None:
                try:
                    frac = ocr.read_fraction(cap.grab(hreg))
                except Exception as e:
                    return TickResult(False, window_found, count,
                                      error=f"haven grab: {e}")
                if frac is None:
                    # Counter gone for a few ticks = you left the site → re-arm
                    # for the next Haven (the low waves are often too fast to catch).
                    self._haven_none_streak += 1
                    if self._haven_none_streak >= 3:
                        self._haven_armed = True
                        self._haven_last_stage = None
                        self._end_last_wave()
                else:
                    self._haven_none_streak = 0
                    haven_stage, haven_total = frac
                    haven_reached = self._update_haven(haven_stage, haven_total)

        # --- Stage 4: last-wave spawn detectors (gated on the final pocket) ---
        dread_spawn = faction_spawn = False
        if self._last_wave_active:
            if self.cfg.dread_enabled:
                dread_spawn = self._detect_spawn(cap, self.cfg.dread_region, "dread")
            if self.cfg.faction_enabled:
                faction_spawn = self._detect_spawn(cap, self.cfg.faction_region,
                                                   "faction")

        return TickResult(
            ok=True, window_found=window_found, count=count, rows=rows,
            threats=threats, new_threat=new_threat, count_increased=count_increased,
            cap_region=cap_region, haven_stage=haven_stage, haven_total=haven_total,
            haven_reached=haven_reached, last_wave=self._last_wave_active,
            dread_spawn=dread_spawn, faction_spawn=faction_spawn,
            threat_names=threat_names)

    # --------------------------------------------------------------- haven
    def _update_haven(self, current: int, total: int) -> bool:
        """Fire once when the counter reaches the final pocket (N == M).

        Filters OCR noise that a panning camera produces:
          * the total must equal the expected pocket count (e.g. a read of
            ``9/6`` or ``6/8`` is impossible and dropped);
          * ``current`` must be within ``1..total`` (no ``7/6``);
          * the pocket must follow the sequence — same value, the next value
            (``+1``), or a reset to ``1`` for a fresh site. A jump like
            ``2 → 5`` is an OCR error and ignored.

        Re-arms as soon as the counter drops below the final pocket (a new
        Haven starting again).
        """
        expected = self.cfg.haven_expected_total
        if current is None or total != expected or not (1 <= current <= total):
            return False
        last = self._haven_last_stage
        if last is not None and current not in (last, last + 1, 1):
            return False  # implausible jump → OCR error
        self._haven_last_stage = current

        at_final = current >= total
        reached = False
        if at_final:
            self._last_wave_active = True
            if self._haven_armed:
                reached = True
                self._haven_armed = False
        else:
            self._haven_armed = True
            self._end_last_wave()
        return reached

    def _end_last_wave(self) -> None:
        """Leave the last wave: disable spawn detectors and re-arm them so the
        first spawn of the *next* last wave fires cleanly."""
        self._last_wave_active = False
        self._dread_armed = True
        self._faction_armed = True

    # ------------------------------------------------------- spawn detectors
    def _detect_spawn(self, cap: "Capturer", region, which: str) -> bool:
        """True once when ``region``'s overview goes from empty to populated.

        Presence is brightness-based: a populated overview row lights up pixels
        above the dark background. Fires once, re-arms when the overview empties.
        """
        reg = resolve_one(self.cfg, region)
        if reg is None:
            return False
        try:
            img = cap.grab(reg)
        except Exception:
            return False
        gray = (0.299 * img[:, :, 0] + 0.587 * img[:, :, 1]
                + 0.114 * img[:, :, 2])
        lit = int((gray > self.cfg.spawn_brightness_thr).sum())
        populated = lit >= self.cfg.spawn_min_bright_px
        armed_attr = f"_{which}_armed"
        if populated:
            if getattr(self, armed_attr):
                setattr(self, armed_attr, False)
                return True
        else:
            setattr(self, armed_attr, True)
        return False

    # ------------------------------------------------------------- debounce
    def _update_threat_debounce(self, threats: List[RowSample]) -> bool:
        """True if any threat colour appeared that wasn't present last tick.

        Fires once per new non-friendly colour; a persistent threat does not
        re-fire every tick.
        """
        current = {color.bucket(r.rgb) for r in threats}
        new = current - self._seen_threat_buckets
        self._seen_threat_buckets = current
        return bool(new)

    # ------------------------------------------------------------ auto-learn
    def _maybe_auto_learn(self, threats: List[RowSample]) -> None:
        if not self.cfg.auto_learn_enabled:
            self._threat_since.clear()
            return
        now = time.monotonic()
        current = {color.bucket(r.rgb): r.rgb for r in threats}
        # forget buckets that disappeared
        for b in list(self._threat_since):
            if b not in current:
                del self._threat_since[b]
        learned = False
        for b, rgb in current.items():
            self._threat_since.setdefault(b, now)
            if now - self._threat_since[b] >= self.cfg.auto_learn_seconds:
                if not color.is_friendly(rgb, self.cfg.friendly_colors,
                                         self.cfg.color_tolerance):
                    self.cfg.friendly_colors.append(rgb)
                    learned = True
        if learned:
            self.cfg.friendly_colors = color.dedupe_colors(
                self.cfg.friendly_colors, self.cfg.color_tolerance / 2)
            if self._on_config_change:
                self._on_config_change()
