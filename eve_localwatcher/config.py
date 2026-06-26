"""Configuration model + JSON persistence.

All geometry is stored *relative to the EVE window origin* (top-left of the
window) when ``use_window_relative`` is true, so the capture survives the user
moving the window. At scan time the live window origin is added back to obtain
absolute screen coordinates.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

CONFIG_DIR = Path(os.path.expanduser("~")) / ".eve_localwatcher"
CONFIG_PATH = CONFIG_DIR / "config.json"

# An (x, y, w, h) rectangle. Origin is the window top-left when window-relative,
# otherwise the virtual desktop top-left.
RegionTuple = Tuple[int, int, int, int]


@dataclass
class Region:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0

    def as_tuple(self) -> RegionTuple:
        return (self.x, self.y, self.w, self.h)

    def is_valid(self) -> bool:
        return self.w > 0 and self.h > 0

    def offset(self, dx: int, dy: int) -> "Region":
        return Region(self.x + dx, self.y + dy, self.w, self.h)

    @classmethod
    def from_obj(cls, obj) -> "Region":
        if obj is None:
            return cls()
        if isinstance(obj, (list, tuple)):
            return cls(*obj)
        return cls(int(obj.get("x", 0)), int(obj.get("y", 0)),
                   int(obj.get("w", 0)), int(obj.get("h", 0)))


@dataclass
class Config:
    # --- target window ---------------------------------------------------
    window_title: str = "EVE"          # substring matched against window titles
    use_window_relative: bool = True   # store/resolve regions relative to window

    # --- capture geometry (see Region docstring) -------------------------
    capture_region: Region = field(default_factory=Region)  # the pilot list
    header_region: Region = field(default_factory=Region)   # the "Local [N]" count

    # --- feature switches (use modules independently) --------------------
    local_alarm_enabled: bool = True   # hostile Local detection (stage 1 + 2)
    auto_threat_enabled: bool = False  # OCR names + auto threat-check on a neut

    # --- row / icon-column layout within capture_region ------------------
    first_row_y_offset: int = 0   # y of the first row's top, inside capture_region
    row_height: int = 18          # vertical pixels per pilot row
    icon_column_x_offset: int = 4 # x of the colour-tag icon, inside capture_region
    icon_sample_width: int = 10   # width of the icon strip to median-sample
    name_x_offset: int = 24       # x where the name text starts (for name OCR)
    name_width: int = 150         # width of the name strip to OCR
    max_visible_rows: int = 30    # safety cap on rows sampled per tick

    # --- friendly whitelist (calibrated, never hardcoded) ----------------
    friendly_colors: List[Tuple[int, int, int]] = field(default_factory=list)
    color_tolerance: float = 18.0   # HSV-feature distance threshold (0..~173)
    # A slot only counts as a tag (and can alarm) if its brightest channel is
    # >= this. Empty/dark background slots fall below it and are ignored.
    tag_min_value: int = 70

    # --- loop / alarm ----------------------------------------------------
    scan_interval_ms: int = 750
    alarm_sound_path: Optional[str] = None
    baseline_count: Optional[int] = None  # "safe" Local headcount from calibration

    # --- auto-learn (off by default — a sitting hostile could be learnt) -
    auto_learn_enabled: bool = False
    auto_learn_seconds: int = 60

    # --- overlay popup positions (kind -> [x, y]); empty = auto-centred ---
    overlay_pos: dict = field(default_factory=dict)

    # --- Haven / Dread-Watch (opt-in second detector) --------------------
    haven_enabled: bool = False
    haven_region: Region = field(default_factory=Region)   # the "N/M" counter
    haven_expected_total: int = 6   # expected pocket count (validation/display)
    haven_alarm_sound_path: Optional[str] = None            # second, distinct sound

    # --- Threat-check enrichment (opt-in, network) -----------------------
    enrichment_enabled: bool = False
    zkill_contact: str = ""          # e-mail/char for the API User-Agent (etiquette)
    fresh_char_days: int = 90        # char younger than this → fresh-char warning
    sso_client_id: str = ""          # your EVE app client id (developers.eveonline.com)
    sso_refresh_token: Optional[str] = None   # stored after one-time SSO login
    sso_character_id: Optional[int] = None
    sso_character_name: Optional[str] = None
    # friendly entities derived from SSO (corp/alliance/fleet/blues), cached
    blue_corp_ids: List[int] = field(default_factory=list)
    blue_alliance_ids: List[int] = field(default_factory=list)

    # --- optional explicit Tesseract path --------------------------------
    tesseract_cmd: Optional[str] = None

    # ------------------------------------------------------------------ IO
    def to_dict(self) -> dict:
        return {
            "window_title": self.window_title,
            "use_window_relative": self.use_window_relative,
            "capture_region": vars(self.capture_region),
            "header_region": vars(self.header_region),
            "first_row_y_offset": self.first_row_y_offset,
            "row_height": self.row_height,
            "icon_column_x_offset": self.icon_column_x_offset,
            "icon_sample_width": self.icon_sample_width,
            "name_x_offset": self.name_x_offset,
            "name_width": self.name_width,
            "local_alarm_enabled": self.local_alarm_enabled,
            "auto_threat_enabled": self.auto_threat_enabled,
            "max_visible_rows": self.max_visible_rows,
            "friendly_colors": [list(c) for c in self.friendly_colors],
            "color_tolerance": self.color_tolerance,
            "tag_min_value": self.tag_min_value,
            "scan_interval_ms": self.scan_interval_ms,
            "alarm_sound_path": self.alarm_sound_path,
            "baseline_count": self.baseline_count,
            "auto_learn_enabled": self.auto_learn_enabled,
            "auto_learn_seconds": self.auto_learn_seconds,
            "overlay_pos": self.overlay_pos,
            "enrichment_enabled": self.enrichment_enabled,
            "zkill_contact": self.zkill_contact,
            "fresh_char_days": self.fresh_char_days,
            "sso_client_id": self.sso_client_id,
            "sso_refresh_token": self.sso_refresh_token,
            "sso_character_id": self.sso_character_id,
            "sso_character_name": self.sso_character_name,
            "blue_corp_ids": list(self.blue_corp_ids),
            "blue_alliance_ids": list(self.blue_alliance_ids),
            "haven_enabled": self.haven_enabled,
            "haven_region": vars(self.haven_region),
            "haven_expected_total": self.haven_expected_total,
            "haven_alarm_sound_path": self.haven_alarm_sound_path,
            "tesseract_cmd": self.tesseract_cmd,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        c = cls()
        c.window_title = d.get("window_title", c.window_title)
        c.use_window_relative = d.get("use_window_relative", c.use_window_relative)
        c.capture_region = Region.from_obj(d.get("capture_region"))
        c.header_region = Region.from_obj(d.get("header_region"))
        c.first_row_y_offset = d.get("first_row_y_offset", c.first_row_y_offset)
        c.row_height = d.get("row_height", c.row_height)
        c.icon_column_x_offset = d.get("icon_column_x_offset", c.icon_column_x_offset)
        c.icon_sample_width = d.get("icon_sample_width", c.icon_sample_width)
        c.name_x_offset = d.get("name_x_offset", c.name_x_offset)
        c.name_width = d.get("name_width", c.name_width)
        c.local_alarm_enabled = d.get("local_alarm_enabled", c.local_alarm_enabled)
        c.auto_threat_enabled = d.get("auto_threat_enabled", c.auto_threat_enabled)
        c.max_visible_rows = d.get("max_visible_rows", c.max_visible_rows)
        c.friendly_colors = [tuple(int(v) for v in c2)
                             for c2 in d.get("friendly_colors", [])]
        c.color_tolerance = d.get("color_tolerance", c.color_tolerance)
        c.tag_min_value = d.get("tag_min_value", c.tag_min_value)
        c.scan_interval_ms = d.get("scan_interval_ms", c.scan_interval_ms)
        c.alarm_sound_path = d.get("alarm_sound_path", c.alarm_sound_path)
        c.baseline_count = d.get("baseline_count", c.baseline_count)
        c.auto_learn_enabled = d.get("auto_learn_enabled", c.auto_learn_enabled)
        c.auto_learn_seconds = d.get("auto_learn_seconds", c.auto_learn_seconds)
        c.overlay_pos = d.get("overlay_pos") or {}
        c.enrichment_enabled = d.get("enrichment_enabled", c.enrichment_enabled)
        c.zkill_contact = d.get("zkill_contact", c.zkill_contact)
        c.fresh_char_days = d.get("fresh_char_days", c.fresh_char_days)
        c.sso_client_id = d.get("sso_client_id", c.sso_client_id)
        c.sso_refresh_token = d.get("sso_refresh_token", c.sso_refresh_token)
        c.sso_character_id = d.get("sso_character_id", c.sso_character_id)
        c.sso_character_name = d.get("sso_character_name", c.sso_character_name)
        c.blue_corp_ids = [int(x) for x in d.get("blue_corp_ids", [])]
        c.blue_alliance_ids = [int(x) for x in d.get("blue_alliance_ids", [])]
        c.haven_enabled = d.get("haven_enabled", c.haven_enabled)
        c.haven_region = Region.from_obj(d.get("haven_region"))
        c.haven_expected_total = d.get("haven_expected_total", c.haven_expected_total)
        c.haven_alarm_sound_path = d.get("haven_alarm_sound_path",
                                         c.haven_alarm_sound_path)
        c.tesseract_cmd = d.get("tesseract_cmd", c.tesseract_cmd)
        return c

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic on Windows for same-volume

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError, KeyError):
            return cls()
