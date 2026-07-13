"""Kill radar: fuses the zKillboard live feed, the ingame intel channel and
manual threat checks into one pilot history around the player's home system.

Event flow (all worker threads post to the app's Tk event queue):

    killfeed (R2Z2) ──┐
    chatlog tail ─────┼─→ _add_sighting ─→ ("radar_sighting", PilotTrack copy)
    manual check ─────┘        │
                               └─ approach? ─→ ("radar_approach", (track, a, b))

Pilots from kills/intel are enriched on a dedicated worker (nearest system
first) through the same ``threatcheck.enrich_one`` pipeline the manual check
uses — with LONG-LIVED ESI/ZKill clients, so caches and the zKill throttle
survive across events.
"""
from __future__ import annotations

import copy
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from . import chatlog, intelparse, mapdata, threat, threatcheck
from .config import Config
from .esi import ESI
from .friendly import FriendlySet, build_friendly_set
from .killfeed import KillFeed
from .zkill import ZKill

APPROACH_FRESH_MIN = 10       # latest sighting must be at most this old
APPROACH_REARM_MIN = 30       # silence this long re-arms the warning
LOCATION_POLL_S = 10.0
FRIENDLY_REFRESH_S = 600.0
PROFILE_TTL_S = 1800.0        # re-enrich a pilot after 30 min
STALE_KILL_MIN = 15           # ignore killmails older than this (backlog)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Sighting:
    system_id: Optional[int]      # None for #manuell (no location known)
    system_name: str
    jumps: Optional[int]          # distance to own system at sighting time
    source: str                   # "zkill" | "intel" | "manuell"
    ts: datetime
    ship_name: Optional[str] = None


@dataclass
class PilotTrack:
    character_id: int
    name: str
    profile: Optional[threat.ThreatProfile] = None   # None while pending
    sightings: List[Sighting] = field(default_factory=list)  # newest first
    sources: Set[str] = field(default_factory=set)
    last_update: datetime = field(default_factory=_now)
    warned_at_jumps: Optional[int] = None            # approach debounce


def pick_attackers(km: dict, own_char_id: Optional[int],
                   fs: Optional[FriendlySet], cap: int) -> List[dict]:
    """Attacker entries worth tracking: real characters, not self, not
    friendly, capped to the most relevant (final blow, then damage)."""
    out = []
    for a in km.get("attackers") or []:
        cid = a.get("character_id")
        if not cid or cid == own_char_id:
            continue
        if fs and fs.is_friendly(cid, a.get("corporation_id"),
                                 a.get("alliance_id")):
            continue
        out.append(a)
    out.sort(key=lambda a: (not a.get("final_blow"),
                            -(a.get("damage_done") or 0)))
    return out[:max(1, cap)]


def kill_minutes_old(km: dict, now: Optional[datetime] = None) -> Optional[float]:
    try:
        t = datetime.fromisoformat(
            (km.get("killmail_time") or "").replace("Z", "+00:00"))
        return ((now or _now()) - t).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None


def check_approach(track: PilotTrack, jump_range: int,
                   now: Optional[datetime] = None) -> Optional[tuple]:
    """(prev_jumps, new_jumps) when the pilot demonstrably closes in.

    Requires ≥2 sightings in DIFFERENT systems with decreasing distance, the
    newest within range and fresh; warns once per continued approach
    (re-warns only on a further decrease). Mutates ``warned_at_jumps``.
    """
    now = now or _now()
    s = [x for x in track.sightings if x.system_id is not None
         and x.jumps is not None]
    if len(s) < 2:
        return None
    latest = s[0]
    # retreat or long silence re-arms
    if track.warned_at_jumps is not None:
        if latest.jumps > track.warned_at_jumps or \
                (now - latest.ts) > timedelta(minutes=APPROACH_REARM_MIN):
            track.warned_at_jumps = None
    if latest.jumps > jump_range:
        return None
    if (now - latest.ts) > timedelta(minutes=APPROACH_FRESH_MIN):
        return None
    prev = next((x for x in s[1:]
                 if x.system_id != latest.system_id and x.jumps > latest.jumps),
                None)
    if prev is None:
        return None
    if track.warned_at_jumps is not None and \
            latest.jumps >= track.warned_at_jumps:
        return None
    track.warned_at_jumps = latest.jumps
    return prev.jumps, latest.jumps


class Radar:
    def __init__(self, cfg: Config, events: "queue.Queue[tuple]") -> None:
        self.cfg = cfg
        self._events = events
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._lock = threading.Lock()
        self._own_system: Optional[int] = None
        self._bubble: Dict[int, int] = {}
        self._tracks: "Dict[int, PilotTrack]" = {}
        self._friendly: Optional[FriendlySet] = None
        self._esi = ESI(cfg.zkill_contact)
        self._zk = ZKill(cfg.zkill_contact)
        self._enrich_q: "queue.PriorityQueue[tuple]" = queue.PriorityQueue()
        self._enrich_seq = 0
        self._profile_cache: Dict[int, tuple] = {}   # cid -> (profile, mono_ts)

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        if not mapdata.load():
            self._status("Radar: Kartendaten fehlen — Radar bleibt aus.")
            return
        manual = mapdata.id_for_name(self.cfg.radar_own_system) \
            if self.cfg.radar_own_system else None
        self.set_own_system(manual)
        targets = [("radar-killfeed", self._run_killfeed),
                   ("radar-chatlog", self._run_chatlog),
                   ("radar-enrich", self._run_enrich)]
        if self.cfg.radar_follow_location and not manual:
            targets.append(("radar-location", self._run_location))
        self._threads = [threading.Thread(target=fn, name=nm, daemon=True)
                         for nm, fn in targets]
        for t in self._threads:
            t.start()
        self._status("Radar gestartet"
                     + (f" — System {self.cfg.radar_own_system}" if manual else
                        " — warte auf SSO-Standort"))

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []

    def is_running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    def _status(self, msg: str) -> None:
        self._events.put(("radar_status", msg))

    # ------------------------------------------------------------- geometry
    def set_own_system(self, system_id: Optional[int]) -> None:
        with self._lock:
            if system_id == self._own_system:
                return
            self._own_system = system_id
            self._bubble = mapdata.systems_within(
                system_id, max(1, min(8, self.cfg.radar_jump_range))) \
                if system_id else {}
        if system_id:
            self._status(f"Radar-Bubble: {mapdata.name_for_id(system_id)} "
                         f"±{self.cfg.radar_jump_range} "
                         f"({len(self._bubble)} Systeme)")

    # ------------------------------------------------------- worker threads
    def _run_killfeed(self) -> None:
        kf = KillFeed(self.cfg.zkill_contact, self._on_killmail_payload,
                      self._status, self._stop)
        kf.run()

    def _on_killmail_payload(self, payload: dict) -> None:
        try:
            if (payload.get("zkb") or {}).get("npc"):
                return                              # pure NPC kill
            km = payload.get("esi") or {}
            with self._lock:
                bubble = self._bubble
            jumps = bubble.get(km.get("solar_system_id"))
            if jumps is None:
                return
            age = kill_minutes_old(km)
            if age is None or age > STALE_KILL_MIN:
                return
            self._refresh_friendly_if_due()
            attackers = pick_attackers(km, self.cfg.sso_character_id,
                                       self._friendly,
                                       self.cfg.radar_max_enrich_per_kill)
            if not attackers:
                return
            ids = [a["character_id"] for a in attackers]
            extra = [a.get(k) for a in attackers
                     for k in ("ship_type_id", "corporation_id", "alliance_id")
                     if a.get(k)]
            names = self._esi.names_for_ids(ids + extra)
            ts = datetime.fromisoformat(
                km["killmail_time"].replace("Z", "+00:00"))
            sysid = int(km["solar_system_id"])
            sysname = mapdata.name_for_id(sysid) or str(sysid)
            for a in attackers:
                cid = a["character_id"]
                name = names.get(cid, f"#{cid}")
                ship = names.get(a.get("ship_type_id"))
                self._add_sighting(
                    cid, name,
                    Sighting(sysid, sysname, jumps, "zkill", ts, ship),
                    corp_name=names.get(a.get("corporation_id")),
                    alli_name=names.get(a.get("alliance_id")))
        except Exception as e:
            self._events.put(("radar_err", f"Killfeed-Verarbeitung: {e}"))

    def _run_chatlog(self) -> None:
        channel = (self.cfg.radar_intel_channel or "").strip()
        if not channel:
            return
        d = chatlog.find_chatlog_dir(self.cfg.radar_chatlog_dir)
        if d is None:
            self._status("Intel-Kanal: Chatlog-Ordner nicht gefunden — "
                         "nur Killfeed aktiv.")
            return
        tail = chatlog.ChatlogTail(d, channel)
        if tail.current_file is None:
            self._status(f"Intel-Kanal: keine Logdatei für '{channel}' — "
                         "Kanal im Spiel geöffnet?")
        else:
            self._status(f"Intel-Kanal: lese {tail.current_file.name}")
        while not self._stop.wait(1.0):
            try:
                for line in tail.poll():
                    parsed = intelparse.parse_line(line)
                    if not parsed:
                        continue
                    ts, _author, msg = parsed
                    with self._lock:
                        bubble = dict(self._bubble)
                    rep = intelparse.extract_report(msg, ts, bubble)
                    if rep:
                        self._on_intel(rep, bubble)
            except Exception as e:
                self._events.put(("radar_err", f"Intel-Kanal: {e}"))

    def _on_intel(self, rep: intelparse.IntelReport,
                  bubble: Dict[int, int]) -> None:
        jumps = bubble.get(rep.system_id)
        if jumps is None:
            return
        if not rep.pilot_candidates:
            self._status(f"Intel: {rep.system_name} ({jumps} J) gemeldet — "
                         "keine Pilotennamen erkannt")
            return
        ids = self._esi.names_to_ids(rep.pilot_candidates)
        if not ids:
            return
        aff = self._esi.affiliations(ids.values())
        ent = self._esi.names_for_ids(
            {e for c, a, _f in aff.values() for e in (c, a) if e})
        self._refresh_friendly_if_due()
        for name, cid in ids.items():
            corp, alli, _ = aff.get(cid, (None, None, None))
            if self._friendly and self._friendly.is_friendly(cid, corp, alli):
                continue
            self._add_sighting(
                cid, name,
                Sighting(rep.system_id, rep.system_name, jumps, "intel",
                         rep.ts or _now()),
                corp_name=ent.get(corp), alli_name=ent.get(alli))

    def _run_location(self) -> None:
        token = None
        token_ts = 0.0
        while not self._stop.wait(LOCATION_POLL_S):
            if self.cfg.radar_own_system:      # manual override appeared
                continue
            if not self.cfg.sso_character_id:
                continue
            try:
                if token is None or time.monotonic() - token_ts > 900:
                    token = threatcheck.access_token(self.cfg)
                    token_ts = time.monotonic()
                if not token:
                    continue
                sysid = self._esi.character_location(
                    self.cfg.sso_character_id, token)
                if sysid:
                    self.set_own_system(int(sysid))
            except Exception as e:
                if "403" in str(e):
                    self._status("Standort-Folgen: Scope fehlt — bitte "
                                 "einmal neu per SSO einloggen.")
                    return
                token = None                    # token expired → re-fetch

    def _run_enrich(self) -> None:
        while not self._stop.is_set():
            try:
                _prio, _seq, name, cid, corp, alli = self._enrich_q.get(
                    timeout=1.0)
            except queue.Empty:
                continue
            cached = self._profile_cache.get(cid)
            if cached and time.monotonic() - cached[1] < PROFILE_TTL_S:
                profile = cached[0]
            else:
                try:
                    profile = threatcheck.enrich_one(
                        self._esi, self._zk, self.cfg, name, cid, corp, alli)
                    self._profile_cache[cid] = (profile, time.monotonic())
                except Exception as e:
                    self._events.put(("radar_err", f"Anreicherung {name}: {e}"))
                    continue
            with self._lock:
                track = self._tracks.get(cid)
                if track:
                    track.profile = profile
                    snap = copy.deepcopy(track)
            if track:
                self._events.put(("radar_sighting", snap))

    # ------------------------------------------------------- sighting store
    def _refresh_friendly_if_due(self) -> None:
        now = time.monotonic()
        due = getattr(self, "_friendly_ts", 0.0)
        if self._friendly is not None and now - due < FRIENDLY_REFRESH_S:
            return
        self._friendly_ts = now
        if not self.cfg.sso_character_id:
            return
        try:
            token = threatcheck.access_token(self.cfg)
            self._friendly = build_friendly_set(
                self._esi, self.cfg.sso_character_id, token,
                self.cfg.blue_corp_ids, self.cfg.blue_alliance_ids)
        except Exception:
            pass

    def _add_sighting(self, cid: int, name: str, s: Sighting,
                      profile: Optional[threat.ThreatProfile] = None,
                      enrich: bool = True, corp_name: Optional[str] = None,
                      alli_name: Optional[str] = None) -> None:
        with self._lock:
            track = self._tracks.get(cid)
            if track is None:
                track = PilotTrack(character_id=cid, name=name)
                self._tracks[cid] = track
            if profile is not None:
                track.profile = profile
            # dedupe: same system + source within 60 s is the same event
            if track.sightings:
                last = track.sightings[0]
                if last.system_id == s.system_id and last.source == s.source \
                        and abs((s.ts - last.ts).total_seconds()) < 60:
                    track.last_update = _now()
                    return
            track.sightings.insert(0, s)
            track.sources.add(s.source)
            track.last_update = _now()
            cutoff = _now() - timedelta(minutes=self.cfg.radar_sighting_max_min)
            track.sightings = [x for x in track.sightings if x.ts >= cutoff][:12]
            # trim the history to the configured number of pilot cards
            if len(self._tracks) > self.cfg.radar_max_pilots:
                oldest = min(self._tracks.values(), key=lambda t: t.last_update)
                if oldest.character_id != cid:
                    del self._tracks[oldest.character_id]
            approach = check_approach(track, self.cfg.radar_jump_range)
            snap = copy.deepcopy(track)
        self._events.put(("radar_sighting", snap))
        if approach:
            self._events.put(("radar_approach", (snap, *approach)))
        if enrich and profile is None:
            cached = self._profile_cache.get(cid)
            if cached and time.monotonic() - cached[1] < PROFILE_TTL_S:
                with self._lock:
                    self._tracks[cid].profile = cached[0]
                    snap = copy.deepcopy(self._tracks[cid])
                self._events.put(("radar_sighting", snap))
            else:
                self._enrich_seq += 1
                self._enrich_q.put((s.jumps if s.jumps is not None else 99,
                                    self._enrich_seq, name, cid, None, None))

    # ------------------------------------------------------------- manual
    def note_manual_profile(self, p: threat.ThreatProfile) -> None:
        """Fold a manually checked pilot (clipboard/OCR) into the history."""
        if not p.character_id:
            return
        self._profile_cache[p.character_id] = (p, time.monotonic())
        self._add_sighting(p.character_id, p.name,
                           Sighting(None, "", None, "manuell", _now()),
                           profile=p, enrich=False)
