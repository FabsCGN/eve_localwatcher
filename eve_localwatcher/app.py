"""Control-panel GUI + alarm overlay (Tkinter, main thread only).

The Scanner runs on a worker thread and reports through a thread-safe queue
that this UI drains via ``root.after``. All Tk calls stay on the main thread.
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from . import alarm, capture, color, localparse, ocr, sso, threatcheck, winutil
from .config import Config, Region
from .region_select import select_region
from .scanner import (Scanner, TickResult, probe_spawn_region, resolve_one,
                      resolve_regions, sample_rows)
from .ui_tooltip import attach as tip

# Threat-panel colours per tier and the German labels for each warning flag.
TIER_COLOR = {"high": "#b30000", "medium": "#b8860b", "low": "#1a7a3c",
              "unknown": "#666666"}
FLAG_LABEL = {"hunter": "Hunter", "fresh": "Frischer Char", "cyno": "Cyno-Verdacht",
              "scanner": "Mögl. Scanner", "unknown": "Nicht aufgelöst"}

OVERLAY_SECONDS = 6
TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/wiki"

# Mouseover help for every setting.
TIPS = {
    "window": "Genau einen EVE-Client auswählen (voller Titel, z. B. 'EVE - "
              "Gank Flint'). Sonst folgt der Scan dem jeweils obersten EVE-"
              "Fenster und capturet beim Multiboxing den falschen Client.",
    "refresh": "Fensterliste neu einlesen (nach Client-Start/-Schließen).",
    "relative": "Bereiche relativ zur Fensterposition speichern — übersteht das "
                "Verschieben des EVE-Fensters. Ausschalten = feste Bildschirm-"
                "koordinaten.",
    "list_region": "Rechteck über die Piloten-Memberliste ziehen (Icon-Spalte "
                   "links + Namen).",
    "header_region": "Rechteck NUR über die Mitglieder-Zahl ziehen — ohne das "
                     "Personen-Icon links, das stört das OCR.",
    "icon_x": "X-Abstand der Icon-Spalte vom linken Rand der Pilotenliste. Nur "
              "die schmale Tag-Spalte treffen, niemals den Zeilenhintergrund "
              "(angeklickte Zeilen sind rot/dunkel hinterlegt).",
    "icon_w": "Breite des gesampelten Icon-Streifens (Pixel). Median über mehrere "
              "Pixel macht die Messung robust gegen Anti-Aliasing.",
    "row_h": "Höhe einer Pilotenzeile in Pixeln. So einstellen, dass jede Zeile "
             "mittig getroffen wird.",
    "row_y": "Y-Abstand der ersten Zeile vom oberen Rand der Pilotenliste.",
    "maxrows": "Sicherheits-Obergrenze, wie viele Zeilen pro Tick gesampelt "
               "werden. Die echte Zahl wird zusätzlich durch den Header-Count "
               "begrenzt.",
    "calibrate": "Aktuelles Local als sicher merken: lernt die vorkommenden Tag-"
                 "Farben als Friendly-Whitelist. In einem ruhigen Moment (nur "
                 "Alts + bekannte Friendlies) ausführen. Leere Slots werden "
                 "übersprungen.",
    "clear": "Alle gelernten Friendly-Farben löschen.",
    "tol": "Wie ähnlich eine Icon-Farbe einer Friendly-Farbe sein muss, um als "
           "friendly zu gelten (Farbabstand). Niedrig = streng (eigene Farbe "
           "weicht leicht ab → Fehlalarm). Hoch = locker (fremde Farbe gilt als "
           "friendly → Hostile rutscht durch).",
    "tagmin": "Helligkeitsschwelle: sitzt überhaupt ein Icon im Slot? Hellster "
              "RGB-Kanal unter dem Wert = leerer Slot, löst NIE Alarm aus. Hoch "
              "= nur klar helle Icons zählen (dunkle Tags evtl. übersehen). "
              "Niedrig = dunkler Hintergrund kann Fehlalarm geben.",
    "interval": "Wartezeit zwischen zwei Scans in Millisekunden. Kleiner = "
                "schnellere Reaktion, mehr CPU.",
    "sound": "WAV-Datei für den Alarm. Leer = System-Beep.",
    "autolearn": "RISKANT: lernt eine nicht-friendly Tag-Farbe automatisch als "
                 "safe, wenn sie X Sekunden präsent ist. Ein still sitzender "
                 "Hostile würde so als friendly gelernt. Standard: aus.",
    "autosecs": "Sekunden, die eine Farbe präsent sein muss, bevor Auto-Learn "
                "sie als friendly lernt.",
    "start": "Scan starten/stoppen.",
    "baseline": "Aktuellen Header-Count als neuen Referenzwert setzen (ab dem ein "
                "Anstieg Alarm auslöst).",
    "debug": "Einmal-Snapshot: loggt Header-Count und pro Zeile Farbe, Status "
             "(friendly/threat/leer) und Messwerte — zum Justieren der Regler.",
    "haven_on": "Liest den Pocket-Counter (z. B. 6/6). Erreicht N die Gesamtzahl "
                "M, kommt der 'Letzte Welle'-Alarm — danach neue Site anfliegen. "
                "Dieser Counter schaltet zugleich die Spawn-Detektoren scharf.",
    "haven_region": "Rechteck NUR um die Zahl 'N/M' ziehen — den grünen Balken "
                    "weglassen, er stört das OCR.",
    "haven_total": "Maximale Pocket-Zahl (Default 6). Werte mit anderer Gesamtzahl "
                   "oder N größer als M (z. B. 9/6) werden als OCR-Fehler verworfen. "
                   "Ausgelöst wird bei N = M.",
    "haven_sound": "Eigener WAV-Sound für den 'Letzte Welle'-Alarm, getrennt vom "
                   "Hostile-Alarm. Leer = System-Beep.",
    "volume": "Lautstärke dieses Alarms (0–100 %). Gilt nur für eigene WAV-Dateien; "
              "der Fallback-Beep ignoriert sie.",
    "dread_on": "Spawn-Detektor für ein Overview-Fenster, das NUR Dreads/Titans "
                "zeigt. Feuert, sobald dort in der letzten Welle etwas erscheint. "
                "Braucht den aktiven Pocket-Counter (wird nur in letzter Welle scharf).",
    "dread_region": "Rechteck über den Zeilenbereich des Dread/Titan-Overviews "
                    "ziehen (ohne Spaltenköpfe). Leer = dunkel, ein Spawn macht ihn hell.",
    "dread_sound": "Eigener WAV-Sound für den Dread/Titan-Spawn. Leer = System-Beep.",
    "faction_on": "Spawn-Detektor für ein Overview-Fenster, das NUR Faction-Haven-"
                  "Spawns (Battleships) zeigt. Feuert in der letzten Welle bei einem "
                  "Spawn. Braucht den aktiven Pocket-Counter.",
    "faction_region": "Rechteck über den Zeilenbereich des Faction-Overviews ziehen "
                      "(ohne Spaltenköpfe).",
    "faction_sound": "Eigener WAV-Sound für den Faction-Spawn. Leer = System-Beep.",
    "intel_top": "Intel-Fenster immer über dem Spielfenster halten.",
    "intel_alpha": "Transparenz des Intel-Fensters (20–100 %).",
    "intel_click": "Klick-durch: Mausklicks gehen durch das Intel-Fenster hindurch "
                   "ins Spiel. ACHTUNG: dann sind die zKill-Links nicht klickbar — "
                   "zum Bedienen/Verschieben wieder ausschalten.",
    "place_hostile": "Hostile-Popup verschieben: erscheint zum Ziehen, Doppel-"
                     "klick speichert. WICHTIG: weg von den Capture-Bereichen "
                     "legen, sonst liest der Scanner das Popup und löst erneut "
                     "Alarm aus.",
    "place_haven": "'Letzte Welle'-Popup verschieben: ziehen, Doppelklick speichert. "
                   "Ebenfalls außerhalb der Capture-Bereiche platzieren.",
    "enrich": "Threat-Check aktivieren (Netzwerk): nicht-blaue Piloten werden via "
              "ESI + zKillboard bewertet. Friendlies (Corp/Allianz/Fleet) werden "
              "vorher rausgefiltert und nie abgefragt.",
    "sso_login": "Einmal per EVE-SSO einloggen (Browser). Liefert Corp/Allianz "
                 "und deine Fleet, um Friendlies sauber rauszufiltern.",
    "zkill_contact": "Optional: Kontakt für den API-User-Agent (Höflichkeit ggü. "
                     "ESI/zKill). Muss KEINE E-Mail sein — ein EVE-Charname reicht, "
                     "oder leer lassen. Bleibt nur in deiner lokalen Config, wird "
                     "nicht mit dem Code verteilt.",
    "check_clip": "Lies die Zwischenablage (Strg+A/Strg+C in der Local-Member-"
                  "liste) und prüfe alle nicht-blauen Piloten.",
    "clipwatch": "Zwischenablage automatisch überwachen: sobald du eine Local-"
                 "Namensliste kopierst, startet der Check von selbst.",
    "local_alarm": "Hostile-Local-Überwachung an/aus (Header-Count + Farb-Sampling). "
                   "Aus = kein Hostile-Alarm, aber Haven/Threat-Check können laufen.",
    "auto_threat": "Wenn ein Nicht-Friendly erscheint, automatisch die Namen per "
                   "OCR lesen und den Threat-Check starten — ohne Strg+C. OCR ist "
                   "fehleranfälliger als die Zwischenablage; nicht gelesene Namen "
                   "werden als 'nicht aufgelöst' markiert.",
    "name_x": "X-Start des Namenstexts in der Pilotenliste (für die Namens-OCR).",
    "name_w": "Breite des Namensstreifens, der per OCR gelesen wird.",
}

# Fixed reference samples used in the slider previews alongside the real
# calibrated whitelist colours.
_EMPTY_SAMPLE = (22, 33, 40)        # a dark/empty slot
_DEMO_FRIENDLY = [(93, 29, 138), (50, 120, 230)]  # fallback if not calibrated


def _nudge(rgb, dr, dg, db):
    """Shift an RGB colour by deltas, clamped to 0..255 (for tolerance probes)."""
    return (max(0, min(255, int(rgb[0]) + dr)),
            max(0, min(255, int(rgb[1]) + dg)),
            max(0, min(255, int(rgb[2]) + db)))


class App:
    def __init__(self) -> None:
        self.cfg = Config.load()
        ocr.configure(self.cfg.tesseract_cmd)

        self.root = tk.Tk()
        self.root.title("Mister Lee's magischer Intelligentheit-Helfer")
        # Final size is computed from the content in _fit_to_content() once the UI
        # is built, so the tallest tab is fully visible without manual resizing.

        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._overlays: dict = {}   # kind -> {win, detail, after}
        self._last_clip = None
        self._threat_win = None
        self._threat_profiles: list = []
        self._lw_prev = False       # last-wave state last tick (for transition log)

        self.scanner = Scanner(
            self.cfg,
            on_tick=lambda r: self._events.put(("tick", r)),
            on_alarm=lambda r: self._events.put(("alarm", r)),
            on_config_change=lambda: self._events.put(("cfgchange", None)),
        )

        self._build_vars()
        self._build_ui()
        self._refresh_friendly_display()
        self._refresh_window_list()
        self._refresh_status_static()
        self._on_tag_change()
        self._on_tol_change()
        self._refresh_sso_status()
        self._refresh_ocr_warning()
        self._fit_to_content()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._poll_queue)
        self.root.after(1000, self._clip_poll)

    def _fit_to_content(self) -> None:
        """Open the window large enough that the tallest tab is fully visible.

        ttk.Notebook requests the size of its largest pane, so the window's
        requested height already covers every tab — we just adopt it (capped to
        the screen) instead of a fixed guess that cut off the longer tabs.
        """
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(self.root.winfo_reqwidth() + 16, sw - 40)
        h = min(self.root.winfo_reqheight() + 16, sh - 80)
        self.root.geometry(f"{int(w)}x{int(h)}")
        self.root.minsize(min(480, int(w)), min(540, int(h)))

    # ------------------------------------------------------------------- vars
    def _build_vars(self) -> None:
        c = self.cfg
        self.v_title = tk.StringVar(value=c.window_title)
        self.v_relative = tk.BooleanVar(value=c.use_window_relative)
        self.v_tol = tk.DoubleVar(value=c.color_tolerance)
        self.v_tagmin = tk.IntVar(value=c.tag_min_value)
        self.v_interval = tk.IntVar(value=c.scan_interval_ms)
        self.v_icon_x = tk.IntVar(value=c.icon_column_x_offset)
        self.v_icon_w = tk.IntVar(value=c.icon_sample_width)
        self.v_name_x = tk.IntVar(value=c.name_x_offset)
        self.v_name_w = tk.IntVar(value=c.name_width)
        self.v_local_alarm = tk.BooleanVar(value=c.local_alarm_enabled)
        self.v_auto_threat = tk.BooleanVar(value=c.auto_threat_enabled)
        self.v_row_h = tk.IntVar(value=c.row_height)
        self.v_row_y = tk.IntVar(value=c.first_row_y_offset)
        self.v_maxrows = tk.IntVar(value=c.max_visible_rows)
        self.v_sound = tk.StringVar(value=c.alarm_sound_path or "")
        self.v_alarm_vol = tk.DoubleVar(value=c.alarm_volume)
        self.v_autolearn = tk.BooleanVar(value=c.auto_learn_enabled)
        self.v_autosecs = tk.IntVar(value=c.auto_learn_seconds)
        self.v_haven_on = tk.BooleanVar(value=c.haven_enabled)
        self.v_haven_total = tk.IntVar(value=c.haven_expected_total)
        self.v_haven_sound = tk.StringVar(value=c.haven_alarm_sound_path or "")
        self.v_haven_vol = tk.DoubleVar(value=c.haven_volume)
        # last-wave spawn detectors
        self.v_dread_on = tk.BooleanVar(value=c.dread_enabled)
        self.v_dread_sound = tk.StringVar(value=c.dread_sound_path or "")
        self.v_dread_vol = tk.DoubleVar(value=c.dread_volume)
        self.v_faction_on = tk.BooleanVar(value=c.faction_enabled)
        self.v_faction_sound = tk.StringVar(value=c.faction_sound_path or "")
        self.v_faction_vol = tk.DoubleVar(value=c.faction_volume)
        self.v_enrich = tk.BooleanVar(value=c.enrichment_enabled)
        self.v_zkill_contact = tk.StringVar(value=c.zkill_contact)
        self.v_clipwatch = tk.BooleanVar(value=False)
        # intel floating window
        self.v_intel_top = tk.BooleanVar(value=c.intel_topmost)
        self.v_intel_alpha = tk.DoubleVar(value=c.intel_alpha)
        self.v_intel_click = tk.BooleanVar(value=c.intel_click_through)

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 3}
        root = self.root

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Start.TButton", font=("Segoe UI", 12, "bold"), padding=6)
        style.configure("TNotebook.Tab", padding=(14, 6))
        style.configure("Hint.TLabel", foreground="#b8860b")

        # === LIVE BAR (always visible) ===================================
        header = ttk.Frame(root)
        header.pack(fill="x", padx=10, pady=(10, 2))
        self.banner = tk.Label(header, text="●  Gestoppt", anchor="w",
                               font=("Segoe UI", 20, "bold"), fg="white",
                               bg="#555555", padx=16, pady=12)
        self.banner.pack(fill="x")
        self.lbl_metrics = ttk.Label(header, text="", foreground="#888")
        self.lbl_metrics.pack(fill="x", pady=(3, 0))

        controls = ttk.Frame(root)
        controls.pack(fill="x", padx=10, pady=4)
        self.btn_start = ttk.Button(controls, text="▶  Start", style="Start.TButton",
                                    command=self._toggle)
        self.btn_start.pack(side="left")
        tip(self.btn_start, TIPS["start"])
        btn_test = ttk.Button(controls, text="Alarm testen",
                              command=self._fire_test_alarm)
        btn_test.pack(side="left", padx=(8, 2))
        btn_dbg = ttk.Button(controls, text="🔍 Debug", command=self._debug_sample)
        btn_dbg.pack(side="left", padx=2)
        tip(btn_dbg, TIPS["debug"])
        btn_base = ttk.Button(controls, text="Baseline", command=self._reset_baseline)
        btn_base.pack(side="left", padx=2)
        tip(btn_base, TIPS["baseline"])
        self.lbl_hint = ttk.Label(root, text="", style="Hint.TLabel", wraplength=460)
        self.lbl_hint.pack(fill="x", padx=12, pady=(0, 2))
        self.lbl_ocrwarn = tk.Label(
            root, fg="#b8860b", cursor="hand2", anchor="w", justify="left",
            wraplength=470, font=("Segoe UI", 9, "underline"),
            text="⚠ Tesseract-OCR nicht installiert — Header-Count & Haven-Counter "
                 "sind deaktiviert. Klicken zum Installieren.")
        self.lbl_ocrwarn.bind("<Button-1>", lambda _e: webbrowser.open(TESSERACT_URL))

        # === SETUP (tabbed) =============================================
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=6)
        tab_cap = ttk.Frame(nb)
        tab_det = ttk.Frame(nb)
        tab_alarm = ttk.Frame(nb)
        tab_threat = ttk.Frame(nb)
        tab_log = ttk.Frame(nb)
        nb.add(tab_cap, text="Erfassung")
        nb.add(tab_det, text="Erkennung")
        nb.add(tab_alarm, text="Alarm & Haven")
        nb.add(tab_threat, text="Threat-Check")
        nb.add(tab_log, text="Log")

        # --- target window ---
        f1 = ttk.LabelFrame(tab_cap, text="EVE-Fenster (genau einen Client pinnen)")
        f1.pack(fill="x", **pad)
        ttk.Label(f1, text="Fenster:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.cmb_window = ttk.Combobox(f1, textvariable=self.v_title, width=30)
        self.cmb_window.grid(row=0, column=1, sticky="w")
        self.cmb_window.bind("<<ComboboxSelected>>", self._on_window_pick)
        tip(self.cmb_window, TIPS["window"])
        btn_refresh = ttk.Button(f1, text="⟳", width=3, command=self._refresh_window_list)
        btn_refresh.grid(row=0, column=2, padx=4)
        tip(btn_refresh, TIPS["refresh"])
        chk_rel = ttk.Checkbutton(f1, text="fensterrelativ", variable=self.v_relative)
        chk_rel.grid(row=1, column=1, sticky="w", padx=2)
        tip(chk_rel, TIPS["relative"])
        self.lbl_window = ttk.Label(f1, text="—", foreground="#888")
        self.lbl_window.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=2)

        # --- regions ---
        f2 = ttk.LabelFrame(tab_cap, text="Capture-Bereiche")
        f2.pack(fill="x", **pad)
        btn_list = ttk.Button(f2, text="Pilotenliste festlegen",
                              command=self._set_list_region)
        btn_list.grid(row=0, column=0, padx=6, pady=4, sticky="ew")
        tip(btn_list, TIPS["list_region"])
        btn_hdr = ttk.Button(f2, text="Header-Zahl festlegen",
                             command=self._set_header_region)
        btn_hdr.grid(row=0, column=1, padx=6, pady=4, sticky="ew")
        tip(btn_hdr, TIPS["header_region"])
        self.lbl_regions = ttk.Label(f2, text="", foreground="#888")
        self.lbl_regions.grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        f2.columnconfigure(0, weight=1)
        f2.columnconfigure(1, weight=1)

        # --- row / icon layout ---
        f3 = ttk.LabelFrame(tab_cap, text="Zeilen- & Icon-Layout (relativ zur Pilotenliste)")
        f3.pack(fill="x", **pad)
        self._spin(f3, 0, "Icon X-Offset", self.v_icon_x, 0, 200, "icon_x")
        self._spin(f3, 1, "Icon Sample-Breite", self.v_icon_w, 1, 60, "icon_w")
        self._spin(f3, 2, "Zeilenhöhe", self.v_row_h, 4, 80, "row_h")
        self._spin(f3, 3, "Erste Zeile Y-Offset", self.v_row_y, 0, 200, "row_y")
        self._spin(f3, 4, "Max. sichtbare Zeilen", self.v_maxrows, 1, 200, "maxrows")
        self._spin(f3, 5, "Name X-Offset (OCR)", self.v_name_x, 0, 400, "name_x")
        self._spin(f3, 6, "Name-Breite (OCR)", self.v_name_w, 20, 400, "name_w")

        # --- calibration ---
        f4 = ttk.LabelFrame(tab_det, text="Kalibrierung (Friendly-Whitelist)")
        f4.pack(fill="x", **pad)
        f4.columnconfigure(1, weight=1)
        btn_cal = ttk.Button(f4, text="Aktuelles Local als sicher merken",
                             command=self._calibrate)
        btn_cal.grid(row=0, column=0, columnspan=2, padx=6, pady=4, sticky="ew")
        tip(btn_cal, TIPS["calibrate"])
        btn_clr = ttk.Button(f4, text="Whitelist leeren", command=self._clear_friendly)
        btn_clr.grid(row=0, column=2, padx=6, pady=4)
        tip(btn_clr, TIPS["clear"])
        self.lbl_friendly = ttk.Label(f4, text="0 Farben")
        self.lbl_friendly.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        self.swatches = tk.Frame(f4)
        self.swatches.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=4)

        # Tag-Schwelle: presence gate ------------------------------------
        lbl_tag = ttk.Label(f4, text="Tag-Schwelle")
        lbl_tag.grid(row=3, column=0, sticky="w", padx=6, pady=(6, 0))
        sc_tag = ttk.Scale(f4, from_=20, to=200, variable=self.v_tagmin,
                           orient="horizontal", command=self._on_tag_change)
        sc_tag.grid(row=3, column=1, sticky="ew", padx=6)
        self.lbl_tagmin = ttk.Label(f4, text="", width=4)
        self.lbl_tagmin.grid(row=3, column=2, sticky="w", padx=6)
        tip(lbl_tag, TIPS["tagmin"])
        tip(sc_tag, TIPS["tagmin"])
        self.tag_preview = tk.Frame(f4)
        self.tag_preview.grid(row=4, column=0, columnspan=3, sticky="w", padx=6, pady=2)

        # Toleranz: friendly-similarity ----------------------------------
        lbl_tol = ttk.Label(f4, text="Toleranz")
        lbl_tol.grid(row=5, column=0, sticky="w", padx=6, pady=(6, 0))
        sc_tol = ttk.Scale(f4, from_=2, to=60, variable=self.v_tol,
                           orient="horizontal", command=self._on_tol_change)
        sc_tol.grid(row=5, column=1, sticky="ew", padx=6)
        self.lbl_tol = ttk.Label(f4, text="", width=4)
        self.lbl_tol.grid(row=5, column=2, sticky="w", padx=6)
        tip(lbl_tol, TIPS["tol"])
        tip(sc_tol, TIPS["tol"])
        self.tol_preview = tk.Frame(f4)
        self.tol_preview.grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=2)

        # --- feature toggle: hostile Local alarm ---
        chk_local = ttk.Checkbutton(
            tab_alarm, text="Hostile-Local-Alarm aktiv", variable=self.v_local_alarm,
            command=self._update_ready)
        chk_local.pack(anchor="w", padx=12, pady=(8, 0))
        tip(chk_local, TIPS["local_alarm"])

        # --- alarm / loop ---
        f5 = ttk.LabelFrame(tab_alarm, text="Alarm & Loop")
        f5.pack(fill="x", **pad)
        f5.columnconfigure(1, weight=1)
        lbl_iv = ttk.Label(f5, text="Intervall (ms)")
        lbl_iv.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        sb_iv = ttk.Spinbox(f5, from_=200, to=5000, increment=50,
                            textvariable=self.v_interval, width=8)
        sb_iv.grid(row=0, column=1, sticky="w")
        tip(lbl_iv, TIPS["interval"])
        tip(sb_iv, TIPS["interval"])
        lbl_snd = ttk.Label(f5, text="Sound:")
        lbl_snd.grid(row=1, column=0, sticky="w", padx=6)
        ent_snd = ttk.Entry(f5, textvariable=self.v_sound, width=24)
        ent_snd.grid(row=1, column=1, sticky="w")
        ttk.Button(f5, text="…", width=3, command=self._pick_sound)\
            .grid(row=1, column=2, padx=4)
        tip(lbl_snd, TIPS["sound"])
        tip(ent_snd, TIPS["sound"])
        chk_al = ttk.Checkbutton(f5, text="Auto-Learn (riskant)",
                                 variable=self.v_autolearn)
        chk_al.grid(row=2, column=0, sticky="w", padx=6, pady=3)
        sb_as = ttk.Spinbox(f5, from_=5, to=600, textvariable=self.v_autosecs, width=6)
        sb_as.grid(row=2, column=1, sticky="w")
        ttk.Label(f5, text="Sek.").grid(row=2, column=2, sticky="w")
        tip(chk_al, TIPS["autolearn"])
        tip(sb_as, TIPS["autosecs"])
        btn_place_h = ttk.Button(f5, text="Hostile-Popup platzieren",
                                 command=lambda: self._place_overlay("hostile"))
        btn_place_h.grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        tip(btn_place_h, TIPS["place_hostile"])
        self._vol_slider(f5, 4, self.v_alarm_vol)

        # --- last wave (pocket counter) ---
        f7 = ttk.LabelFrame(tab_alarm, text="Letzte Welle (Pocket-Counter)")
        f7.pack(fill="x", **pad)
        f7.columnconfigure(1, weight=1)
        chk_hv = ttk.Checkbutton(f7, text="aktiviert", variable=self.v_haven_on,
                                 command=self._update_ready)
        chk_hv.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        tip(chk_hv, TIPS["haven_on"])
        btn_hvreg = ttk.Button(f7, text="Counter-Bereich festlegen",
                               command=self._set_haven_region)
        btn_hvreg.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6)
        tip(btn_hvreg, TIPS["haven_region"])
        lbl_hvt = ttk.Label(f7, text="Max. Pockets")
        lbl_hvt.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        sb_hvt = ttk.Spinbox(f7, from_=2, to=20, textvariable=self.v_haven_total, width=6)
        sb_hvt.grid(row=1, column=1, sticky="w")
        tip(lbl_hvt, TIPS["haven_total"])
        tip(sb_hvt, TIPS["haven_total"])
        lbl_hvs = ttk.Label(f7, text="Sound:")
        lbl_hvs.grid(row=2, column=0, sticky="w", padx=6)
        ent_hvs = ttk.Entry(f7, textvariable=self.v_haven_sound, width=24)
        ent_hvs.grid(row=2, column=1, sticky="w")
        ttk.Button(f7, text="…", width=3, command=self._pick_haven_sound)\
            .grid(row=2, column=2, padx=4)
        ttk.Button(f7, text="'Letzte Welle'-Alarm testen",
                   command=self._fire_test_haven).grid(row=3, column=1, sticky="w",
                                                       padx=6, pady=3)
        btn_place_hv = ttk.Button(f7, text="Popup platzieren",
                                  command=lambda: self._place_overlay("haven"))
        btn_place_hv.grid(row=3, column=0, sticky="w", padx=6, pady=3)
        tip(btn_place_hv, TIPS["place_haven"])
        tip(lbl_hvs, TIPS["haven_sound"])
        tip(ent_hvs, TIPS["haven_sound"])
        self._vol_slider(f7, 4, self.v_haven_vol)
        self.lbl_haven = ttk.Label(f7, text="", foreground="#888")
        self.lbl_haven.grid(row=5, column=0, columnspan=3, sticky="w", padx=6)

        # --- last-wave spawn detectors (Dread/Titan + Faction) ---
        f9 = ttk.LabelFrame(tab_alarm,
                            text="Spawn-Detektoren (nur in letzter Welle)")
        f9.pack(fill="x", **pad)
        f9.columnconfigure(1, weight=1)
        self._build_spawn_block(
            f9, 0, "Dread / Titan", self.v_dread_on, self.v_dread_sound,
            self.v_dread_vol, self._set_dread_region, self._pick_dread_sound,
            self._fire_test_dread, lambda: self._place_overlay("dread"),
            lambda: self._test_spawn_region("dread"),
            "dread_on", "dread_region", "dread_sound")
        ttk.Separator(f9, orient="horizontal").grid(
            row=5, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        self._build_spawn_block(
            f9, 6, "Faction (Battleship)", self.v_faction_on, self.v_faction_sound,
            self.v_faction_vol, self._set_faction_region, self._pick_faction_sound,
            self._fire_test_faction, lambda: self._place_overlay("faction"),
            lambda: self._test_spawn_region("faction"),
            "faction_on", "faction_region", "faction_sound")
        self.lbl_spawn = ttk.Label(f9, text="", foreground="#888")
        self.lbl_spawn.grid(row=11, column=0, columnspan=3, sticky="w", padx=6,
                            pady=(4, 0))

        # --- threat-check ---
        f8 = ttk.LabelFrame(tab_threat, text="Threat-Check (ESI + zKillboard)")
        f8.pack(fill="x", **pad)
        f8.columnconfigure(1, weight=1)
        chk_en = ttk.Checkbutton(f8, text="aktiviert (Netzwerk)", variable=self.v_enrich)
        chk_en.grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        tip(chk_en, TIPS["enrich"])
        self.lbl_sso = ttk.Label(f8, text="", foreground="#888")
        self.lbl_sso.grid(row=1, column=0, columnspan=2, sticky="w", padx=6)
        btn_sso = ttk.Button(f8, text="EVE-SSO Login", command=self._sso_login)
        btn_sso.grid(row=1, column=2, padx=6, pady=2)
        tip(btn_sso, TIPS["sso_login"])
        lbl_zk = ttk.Label(f8, text="API-Kontakt (optional):")
        lbl_zk.grid(row=2, column=0, sticky="w", padx=6)
        ent_zk = ttk.Entry(f8, textvariable=self.v_zkill_contact, width=26)
        ent_zk.grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)
        tip(lbl_zk, TIPS["zkill_contact"])
        tip(ent_zk, TIPS["zkill_contact"])
        btn_clip = ttk.Button(f8, text="Local aus Zwischenablage prüfen",
                              command=self._check_from_clipboard)
        btn_clip.grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        tip(btn_clip, TIPS["check_clip"])
        chk_cw = ttk.Checkbutton(f8, text="Zwischenablage auto-überwachen",
                                 variable=self.v_clipwatch)
        chk_cw.grid(row=4, column=0, columnspan=2, sticky="w", padx=6)
        tip(chk_cw, TIPS["clipwatch"])
        chk_at = ttk.Checkbutton(f8, text="Auto-Threat: bei Neut Namen per OCR prüfen",
                                 variable=self.v_auto_threat, command=self._update_ready)
        chk_at.grid(row=5, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 0))
        tip(chk_at, TIPS["auto_threat"])
        ttk.Label(tab_threat, foreground="#888", wraplength=440, justify="left",
                  text="In der Local-Memberliste Strg+A / Strg+C drücken, dann hier "
                       "prüfen. Friendlies (Corp/Allianz/Fleet) werden vorher "
                       "rausgefiltert.").pack(fill="x", padx=14, pady=(2, 0))

        # --- intel floating window options ---
        f10 = ttk.LabelFrame(tab_threat, text="Intel-Fenster (Overlay)")
        f10.pack(fill="x", **pad)
        f10.columnconfigure(1, weight=1)
        chk_it = ttk.Checkbutton(f10, text="Immer oben", variable=self.v_intel_top,
                                 command=self._on_intel_opt_change)
        chk_it.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        tip(chk_it, TIPS["intel_top"])
        chk_ic = ttk.Checkbutton(f10, text="Klick-durch", variable=self.v_intel_click,
                                 command=self._on_intel_opt_change)
        chk_ic.grid(row=0, column=1, sticky="w", padx=6)
        tip(chk_ic, TIPS["intel_click"])
        lbl_ia = ttk.Label(f10, text="Transparenz")
        lbl_ia.grid(row=1, column=0, sticky="w", padx=6)
        sc_ia = ttk.Scale(f10, from_=20, to=100, orient="horizontal",
                          variable=self.v_intel_alpha,
                          command=lambda _e: self._on_intel_opt_change())
        sc_ia.grid(row=1, column=1, sticky="ew", padx=6)
        tip(lbl_ia, TIPS["intel_alpha"])
        tip(sc_ia, TIPS["intel_alpha"])

        # --- log (own tab) ---
        self.log = tk.Text(tab_log, height=9, state="disabled", wrap="word",
                           font=("Consolas", 9), relief="flat")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)

    def _spin(self, parent, row, label, var, lo, hi, tip_key=None):
        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=6, pady=2)
        sb = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=8)
        sb.grid(row=row, column=1, sticky="w", padx=6)
        if tip_key:
            tip(lbl, TIPS[tip_key])
            tip(sb, TIPS[tip_key])

    def _vol_slider(self, parent, row, var, label="Lautstärke") -> None:
        """A 0–100 % volume slider with a live percentage readout."""
        lbl = ttk.Label(parent, text=label)
        lbl.grid(row=row, column=0, sticky="w", padx=6, pady=2)
        sc = ttk.Scale(parent, from_=0, to=100, orient="horizontal", variable=var)
        sc.grid(row=row, column=1, sticky="ew", padx=6)
        out = ttk.Label(parent, width=5)
        out.grid(row=row, column=2, sticky="w")
        tip(lbl, TIPS["volume"])
        tip(sc, TIPS["volume"])

        def _upd(*_):
            out.config(text=f"{int(float(var.get()))} %")
        var.trace_add("write", _upd)
        _upd()

    def _build_spawn_block(self, parent, base, title, v_on, v_sound, v_vol,
                           set_region, pick_sound, fire_test, place_popup,
                           probe_test, tip_on, tip_region, tip_sound) -> None:
        """One Dread/Faction spawn-detector block, anchored at grid row ``base``
        (uses rows base..base+3)."""
        chk = ttk.Checkbutton(parent, text=title, variable=v_on,
                              command=self._update_ready)
        chk.grid(row=base, column=0, sticky="w", padx=6, pady=3)
        tip(chk, TIPS[tip_on])
        btn_reg = ttk.Button(parent, text="Overview-Bereich festlegen",
                             command=set_region)
        btn_reg.grid(row=base, column=1, columnspan=2, sticky="ew", padx=6)
        tip(btn_reg, TIPS[tip_region])
        lbl_s = ttk.Label(parent, text="Sound:")
        lbl_s.grid(row=base + 1, column=0, sticky="w", padx=6)
        ent_s = ttk.Entry(parent, textvariable=v_sound, width=24)
        ent_s.grid(row=base + 1, column=1, sticky="w")
        ttk.Button(parent, text="…", width=3, command=pick_sound)\
            .grid(row=base + 1, column=2, padx=4)
        tip(lbl_s, TIPS[tip_sound])
        tip(ent_s, TIPS[tip_sound])
        ttk.Button(parent, text="Popup platzieren", command=place_popup)\
            .grid(row=base + 2, column=0, sticky="w", padx=6, pady=3)
        ttk.Button(parent, text="Alarm testen", command=fire_test)\
            .grid(row=base + 2, column=1, sticky="w", padx=6, pady=3)
        btn_probe = ttk.Button(parent, text="Erkennung testen", command=probe_test)
        btn_probe.grid(row=base + 2, column=2, sticky="w", padx=4, pady=3)
        tip(btn_probe, "Liest den Overview-Bereich JETZT aus und schreibt ins Log, "
                       "ob er als belegt erkannt würde. Zum Prüfen etwas ins "
                       "Overview holen (z. B. Filter kurz rausnehmen).")
        self._vol_slider(parent, base + 3, v_vol)

    # ----------------------------------------------------------- previews
    def _on_tol_change(self, _evt=None) -> None:
        self.lbl_tol.config(text=f"{self.v_tol.get():.0f}")
        self._render_tol_preview()

    def _on_tag_change(self, _evt=None) -> None:
        self.lbl_tagmin.config(text=f"{self.v_tagmin.get():.0f}")
        self._render_tag_preview()

    def _friendly_or_demo(self):
        """Real calibrated colours, or demo colours if not calibrated yet."""
        return list(self.cfg.friendly_colors) or list(_DEMO_FRIENDLY)

    def _swatch_cell(self, parent, rgb, top, verdict, vcolor):
        cell = tk.Frame(parent)
        cell.pack(side="left", padx=3)
        tk.Label(cell, text=top, font=("Segoe UI", 7),
                 foreground="#888").pack()
        tk.Frame(cell, bg="#%02x%02x%02x" % tuple(rgb), width=26, height=20,
                 highlightthickness=1, highlightbackground="#555").pack()
        tk.Label(cell, text=verdict, font=("Segoe UI", 7, "bold"),
                 foreground=vcolor).pack()

    def _render_tag_preview(self) -> None:
        for w in self.tag_preview.winfo_children():
            w.destroy()
        thr = int(float(self.v_tagmin.get()))
        calibrated = bool(self.cfg.friendly_colors)
        # Real friendly colours + one fixed dark/empty reference sample.
        samples = [(c, calibrated) for c in self._friendly_or_demo()[:4]]
        samples.append((_EMPTY_SAMPLE, False))  # always-empty reference
        for rgb, _real in samples:
            val = max(int(rgb[0]), int(rgb[1]), int(rgb[2]))
            if val >= thr:
                verdict, vcol = "Icon", "#3a9"
            else:
                verdict, vcol = "leer", "#999"
            self._swatch_cell(self.tag_preview, rgb, f"val {val}", verdict, vcol)
        if not calibrated:
            tk.Label(self.tag_preview, text="  (Demo — bitte kalibrieren)",
                     font=("Segoe UI", 7), foreground="#a70").pack(side="left")

    def _render_tol_preview(self) -> None:
        for w in self.tol_preview.winfo_children():
            w.destroy()
        tol = float(self.v_tol.get())
        thr = int(float(self.v_tagmin.get()))
        fc = self._friendly_or_demo()
        base = fc[0]
        calibrated = bool(self.cfg.friendly_colors)
        # The first friendly colour plus graded nudges away from it, so probes
        # flip friendly→threat as the tolerance radius grows. Distances shown.
        probes = [base,
                  _nudge(base, 22, 10, -14),
                  _nudge(base, -34, 40, 16),
                  _nudge(base, 70, -28, -44)]
        for rgb in probes:
            val = max(int(rgb[0]), int(rgb[1]), int(rgb[2]))
            d = min(color.color_distance(rgb, k) for k in fc)
            if val < thr:
                verdict, vcol = "leer", "#999"
            elif d <= tol:
                verdict, vcol = "friendly", "#3a9"
            else:
                verdict, vcol = "threat", "#d54"
            self._swatch_cell(self.tol_preview, rgb, f"d {d:.0f}", verdict, vcol)
        if not calibrated:
            tk.Label(self.tol_preview, text="  (Demo — bitte kalibrieren)",
                     font=("Segoe UI", 7), foreground="#a70").pack(side="left")

    # ----------------------------------------------------------- settings sync
    def _apply_settings_to_cfg(self) -> None:
        c = self.cfg
        c.window_title = self.v_title.get().strip() or "EVE"
        c.use_window_relative = bool(self.v_relative.get())
        c.color_tolerance = float(self.v_tol.get())
        c.tag_min_value = int(self.v_tagmin.get())
        c.scan_interval_ms = int(self.v_interval.get())
        c.icon_column_x_offset = int(self.v_icon_x.get())
        c.icon_sample_width = int(self.v_icon_w.get())
        c.name_x_offset = int(self.v_name_x.get())
        c.name_width = int(self.v_name_w.get())
        c.local_alarm_enabled = bool(self.v_local_alarm.get())
        c.auto_threat_enabled = bool(self.v_auto_threat.get())
        c.row_height = int(self.v_row_h.get())
        c.first_row_y_offset = int(self.v_row_y.get())
        c.max_visible_rows = int(self.v_maxrows.get())
        c.alarm_sound_path = self.v_sound.get().strip() or None
        c.alarm_volume = int(self.v_alarm_vol.get())
        c.auto_learn_enabled = bool(self.v_autolearn.get())
        c.auto_learn_seconds = int(self.v_autosecs.get())
        c.haven_enabled = bool(self.v_haven_on.get())
        c.haven_expected_total = int(self.v_haven_total.get())
        c.haven_alarm_sound_path = self.v_haven_sound.get().strip() or None
        c.haven_volume = int(self.v_haven_vol.get())
        c.dread_enabled = bool(self.v_dread_on.get())
        c.dread_sound_path = self.v_dread_sound.get().strip() or None
        c.dread_volume = int(self.v_dread_vol.get())
        c.faction_enabled = bool(self.v_faction_on.get())
        c.faction_sound_path = self.v_faction_sound.get().strip() or None
        c.faction_volume = int(self.v_faction_vol.get())
        c.enrichment_enabled = bool(self.v_enrich.get())
        c.zkill_contact = self.v_zkill_contact.get().strip()
        c.intel_topmost = bool(self.v_intel_top.get())
        c.intel_alpha = int(self.v_intel_alpha.get())
        c.intel_click_through = bool(self.v_intel_click.get())
        c.save()

    # ----------------------------------------------------------- window pick
    def _refresh_window_list(self) -> None:
        """List every visible 'EVE' window so the user can pin one specific
        client. The full title (e.g. 'EVE - Gank Flint') is stored, so only that
        client matches — the scan no longer follows whichever client is on top."""
        titles: list[str] = []
        for _hwnd, title in winutil.list_windows("EVE"):
            if title not in titles:
                titles.append(title)
        self.cmb_window["values"] = titles
        cur = self.v_title.get().strip()
        if cur not in titles and titles:
            # Old default ("EVE") won't be a full title — adopt the first client.
            if not cur or not any(cur.lower() in t.lower() for t in titles):
                self.v_title.set(titles[0])
        self._on_window_pick()

    def _on_window_pick(self, _event=None) -> None:
        self.cfg.window_title = self.v_title.get().strip() or "EVE"
        self.cfg.save()
        self._refresh_status_static()
        if self.scanner.is_running():
            self._log(f"Aktives Fenster: '{self.cfg.window_title}'")

    # ------------------------------------------------------------- regions
    def _resolve_or_warn(self):
        self._apply_settings_to_cfg()
        if self.cfg.use_window_relative and \
                winutil.find_window_origin(self.cfg.window_title) is None:
            messagebox.showwarning(
                "Fenster nicht gefunden",
                f"Kein Fenster mit Titel '{self.cfg.window_title}' gefunden.\n"
                "EVE starten oder 'fensterrelativ' deaktivieren.")
            return None
        return resolve_regions(self.cfg)

    def _set_list_region(self) -> None:
        self._apply_settings_to_cfg()
        rect = select_region(self.root, "Pilotenliste aufziehen (Icon-Spalte + Namen)")
        if rect is None:
            return
        self._store_region("capture_region", rect)
        self._log(f"Pilotenliste gesetzt: {rect}")

    def _set_header_region(self) -> None:
        self._apply_settings_to_cfg()
        rect = select_region(
            self.root,
            "NUR die Zahl im Header aufziehen — OHNE das Personen-Icon links")
        if rect is None:
            return
        self._store_region("header_region", rect)
        self._log(f"Header gesetzt: {rect}")

    def _set_haven_region(self) -> None:
        self._apply_settings_to_cfg()
        rect = select_region(
            self.root, "NUR die Zahl 'N/M' aufziehen — ohne den grünen Balken")
        if rect is None:
            return
        self._store_region("haven_region", rect)
        self._log(f"Pocket-Counter gesetzt: {rect}")

    def _set_dread_region(self) -> None:
        self._apply_settings_to_cfg()
        rect = select_region(
            self.root, "Dread/Titan-Overview aufziehen — nur den Zeilenbereich")
        if rect is None:
            return
        self._store_region("dread_region", rect)
        self._log(f"Dread/Titan-Overview gesetzt: {rect}")

    def _set_faction_region(self) -> None:
        self._apply_settings_to_cfg()
        rect = select_region(
            self.root, "Faction-Overview aufziehen — nur den Zeilenbereich")
        if rect is None:
            return
        self._store_region("faction_region", rect)
        self._log(f"Faction-Overview gesetzt: {rect}")

    def _store_region(self, attr: str, rect_abs) -> None:
        x, y, w, h = rect_abs
        if self.cfg.use_window_relative:
            origin = winutil.find_window_origin(self.cfg.window_title)
            if origin is None:
                messagebox.showwarning(
                    "Fenster nicht gefunden",
                    "Konnte Fensterposition nicht lesen — Bereich wird absolut "
                    "gespeichert. Verschieben des Fensters bricht ihn dann.")
                origin = (0, 0)
            x, y = x - origin[0], y - origin[1]
        setattr(self.cfg, attr, Region(int(x), int(y), int(w), int(h)))
        self.cfg.save()
        self._refresh_status_static()

    # ----------------------------------------------------------- calibration
    def _calibrate(self) -> None:
        res = self._resolve_or_warn()
        if res is None:
            return
        cap_region, _hdr, _wf = res
        if cap_region is None:
            messagebox.showinfo("Erst Bereich festlegen",
                                "Bitte zuerst die Pilotenliste festlegen.")
            return
        try:
            img = capture.grab_once(cap_region)
        except Exception as e:
            messagebox.showerror("Capture-Fehler", str(e))
            return

        # Determine how many rows actually hold a pilot, so we don't learn the
        # empty list background (which would make untagged neutrals "friendly").
        count = self._current_count()
        if count is None:
            count = simpledialog.askinteger(
                "Pilotenzahl",
                "Tesseract nicht verfügbar.\nWie viele Piloten sind aktuell im "
                "Local (Header-Zahl)?", parent=self.root, minvalue=1, maxvalue=500)
            if count is None:
                return
        max_by_region = max(1, img.shape[0] // max(1, self.cfg.row_height))
        n = min(count, max_by_region, self.cfg.max_visible_rows)

        rows = sample_rows(img, self.cfg, n)
        # Only learn actual tag colours as friendly — never an empty/dark slot,
        # otherwise the background would be whitelisted as a colour.
        new_colors = [r.rgb for r in rows
                      if color.has_tag(r.rgb, self.cfg.tag_min_value)]
        skipped = len(rows) - len(new_colors)
        merged = color.dedupe_colors(
            list(self.cfg.friendly_colors) + new_colors, self.cfg.color_tolerance / 2)
        self.cfg.friendly_colors = merged
        self.cfg.baseline_count = count
        self.cfg.save()
        self._refresh_friendly_display()
        self._refresh_status_static()
        self._log(f"Kalibriert: {len(rows)} Zeilen, {len(new_colors)} Tag-Farben "
                  f"gelernt ({skipped} leere übersprungen), "
                  f"{len(merged)} Friendly gesamt, Baseline={count}.")

    def _clear_friendly(self) -> None:
        if messagebox.askyesno("Whitelist leeren", "Alle Friendly-Farben löschen?"):
            self.cfg.friendly_colors = []
            self.cfg.save()
            self._refresh_friendly_display()
            self._update_ready()

    def _current_count(self) -> Optional[int]:
        if not (self.cfg.header_region.is_valid() and ocr.available()):
            return None
        res = self._resolve_or_warn()
        if res is None:
            return None
        _cap, hdr, _wf = res
        if hdr is None:
            return None
        try:
            return ocr.read_count(capture.grab_once(hdr))
        except Exception:
            return None

    # --------------------------------------------------------------- debug
    def _debug_sample(self) -> None:
        """One-shot diagnostic: header OCR + per-row sampled colour & distance."""
        res = self._resolve_or_warn()
        if res is None:
            return
        cap_region, hdr, _wf = res

        # --- header ---
        if hdr is not None:
            try:
                himg = capture.grab_once(hdr)
                cnt = ocr.read_count(himg)
                raw = ocr._ocr_text(himg) if ocr.available() else "OCR aus"  # noqa: SLF001
                self._log(f"HEADER: count={cnt}  region={hdr}")
                self._log(f"  OCR roh: {raw}")
            except Exception as e:
                self._log(f"HEADER Fehler: {e}")
        else:
            self._log("HEADER: kein Bereich gesetzt")

        # --- rows ---
        if cap_region is None:
            self._log("LISTE: kein Bereich gesetzt")
            return
        try:
            img = capture.grab_once(cap_region)
        except Exception as e:
            self._log(f"LISTE Fehler: {e}")
            return
        max_by_region = max(1, img.shape[0] // max(1, self.cfg.row_height))
        n = min(self.cfg.max_visible_rows, max_by_region)
        rows = sample_rows(img, self.cfg, n)
        fc = self.cfg.friendly_colors
        self._log(f"LISTE: region={cap_region} {len(rows)} Zeilen, "
                  f"Toleranz={self.cfg.color_tolerance:.0f}, Bildhöhe={img.shape[0]}px")
        for r in rows:
            v = max(r.rgb)
            if fc:
                dist = min(color.color_distance(r.rgb, k) for k in fc)
                nearest = min(range(len(fc)),
                              key=lambda i: color.color_distance(r.rgb, fc[i]))
                self._log(f"  Z{r.index:>2} {str(r.rgb):>16} {r.status:<8} "
                          f"val={v:>3} dist={dist:5.1f} → #{nearest}")
            else:
                self._log(f"  Z{r.index:>2} {str(r.rgb):>16} {r.status:<8} val={v:>3}")

        # --- haven counter ---
        if self.cfg.haven_enabled:
            hreg = resolve_one(self.cfg, self.cfg.haven_region)
            if hreg is None:
                self._log("HAVEN: kein Bereich gesetzt")
            else:
                try:
                    himg = capture.grab_once(hreg)
                    frac = ocr.read_fraction(himg)
                    raw = ocr.read_fraction_text(himg)
                    self._log(f"HAVEN: region={hreg} gelesen={frac}")
                    self._log(f"  OCR roh: {raw}")
                except Exception as e:
                    self._log(f"HAVEN Fehler: {e}")

    # --------------------------------------------------------------- controls
    def _missing_step(self) -> Optional[str]:
        """The next setup step, considering which features are enabled.

        Start drives the scanner (Local-alarm / auto-threat / Haven); the manual
        Threat-Check runs independently of Start.
        """
        c = self.cfg
        if c.use_window_relative and \
                winutil.find_window_origin(c.window_title) is None:
            return "EVE-Fenster im Tab 'Erfassung' wählen."
        local = c.local_alarm_enabled or c.auto_threat_enabled
        if not (local or c.haven_enabled):
            return ("Kein Scan-Feature aktiv — Local-Alarm oder Haven aktivieren "
                    "(Threat-Check läuft separat über seinen Button).")
        if local:
            if not c.capture_region.is_valid() and not c.header_region.is_valid():
                return "Capture-Bereich im Tab 'Erfassung' festlegen."
            if c.capture_region.is_valid() and not c.friendly_colors:
                return ("Im Tab 'Erkennung' kalibrieren: 'Aktuelles Local als "
                        "sicher merken'.")
        if c.haven_enabled and not c.haven_region.is_valid():
            return "Pocket-Counter-Bereich im Tab 'Alarm & Haven' festlegen."
        # Spawn detectors only arm in the last wave → need the pocket counter.
        if (c.dread_enabled or c.faction_enabled) and not c.haven_enabled:
            return ("Spawn-Detektoren brauchen den Pocket-Counter — "
                    "'Letzte Welle' aktivieren und Bereich festlegen.")
        if c.dread_enabled and not c.dread_region.is_valid():
            return "Dread/Titan-Overview-Bereich festlegen ('Alarm & Haven')."
        if c.faction_enabled and not c.faction_region.is_valid():
            return "Faction-Overview-Bereich festlegen ('Alarm & Haven')."
        return None

    def _update_ready(self) -> None:
        """Enable Start only when set up; otherwise show the next step."""
        if self.scanner.is_running():
            self.lbl_hint.config(text="")
            return
        self._apply_settings_to_cfg()
        missing = self._missing_step()
        self.btn_start.config(state=("disabled" if missing else "normal"))
        self.lbl_hint.config(text=("Nächster Schritt: " + missing) if missing else "")

    def _toggle(self) -> None:
        if self.scanner.is_running():
            self.scanner.stop()
            self.btn_start.config(text="▶  Start")
            self._set_banner("●  Gestoppt", "idle")
            self.lbl_metrics.config(text="")
            self._log("Scanner gestoppt.")
            self._update_ready()
            return
        self._apply_settings_to_cfg()
        if self._missing_step():
            self._update_ready()
            return
        self.scanner.start()
        self.btn_start.config(text="⏸  Stop")
        self._set_banner("●  läuft …", "safe")
        self.lbl_hint.config(text="")
        self._log(f"Scanner gestartet (Intervall {self.cfg.scan_interval_ms} ms, "
                  f"OCR={'an' if ocr.available() else 'aus'}).")

    def _reset_baseline(self) -> None:
        self.cfg.baseline_count = self._current_count()
        self.cfg.save()
        self.scanner._last_alarmed_count = self.cfg.baseline_count  # noqa: SLF001
        self._log(f"Baseline zurückgesetzt auf {self.cfg.baseline_count}.")
        self._refresh_status_static()

    def _pick_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Alarm-Sound (WAV)", filetypes=[("WAV", "*.wav"), ("Alle", "*.*")])
        if path:
            self.v_sound.set(path)

    def _pick_haven_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="'Letzte Welle'-Sound (WAV)",
            filetypes=[("WAV", "*.wav"), ("Alle", "*.*")])
        if path:
            self.v_haven_sound.set(path)

    def _pick_dread_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Dread/Titan-Spawn-Sound (WAV)",
            filetypes=[("WAV", "*.wav"), ("Alle", "*.*")])
        if path:
            self.v_dread_sound.set(path)

    def _pick_faction_sound(self) -> None:
        path = filedialog.askopenfilename(
            title="Faction-Spawn-Sound (WAV)",
            filetypes=[("WAV", "*.wav"), ("Alle", "*.*")])
        if path:
            self.v_faction_sound.set(path)

    def _fire_test_haven(self) -> None:
        self._apply_settings_to_cfg()
        alarm.play(self.cfg.haven_alarm_sound_path, self.cfg.haven_volume / 100)
        self._show_overlay("haven", "Test — letzte Welle, danach neue Site!")

    def _fire_test_dread(self) -> None:
        self._apply_settings_to_cfg()
        alarm.play(self.cfg.dread_sound_path, self.cfg.dread_volume / 100)
        self._show_overlay("dread", "Test — Dread/Titan-Spawn!")

    def _fire_test_faction(self) -> None:
        self._apply_settings_to_cfg()
        alarm.play(self.cfg.faction_sound_path, self.cfg.faction_volume / 100)
        self._show_overlay("faction", "Test — Faction-Spawn!")

    def _test_spawn_region(self, which: str) -> None:
        """Grab the detector's overview region right now and log the verdict."""
        self._apply_settings_to_cfg()
        region = (self.cfg.dread_region if which == "dread"
                  else self.cfg.faction_region)
        name = "Dread/Titan" if which == "dread" else "Faction"
        try:
            res = probe_spawn_region(self.cfg, region)
        except Exception as e:
            self._log(f"❌ {name}-Erkennungstest fehlgeschlagen: {e}")
            return
        if res is None:
            self._log(f"❌ {name}: Overview-Bereich nicht gesetzt oder EVE-Fenster "
                      f"nicht gefunden.")
            return
        lit, needed, populated = res
        verdict = ("BELEGT — würde in der letzten Welle auslösen" if populated
                   else "leer — kein Alarm")
        self._log(f"🔍 {name}-Overview: {lit} helle Pixel "
                  f"(Schwelle {needed}) → {verdict}")

    # ----------------------------------------------------------- threat-check
    def _refresh_ocr_warning(self) -> None:
        if ocr.available():
            self.lbl_ocrwarn.pack_forget()
        else:
            self.lbl_ocrwarn.pack(fill="x", padx=12, pady=(0, 2),
                                  after=self.lbl_hint)

    def _refresh_sso_status(self) -> None:
        name = self.cfg.sso_character_name
        if self.cfg.sso_refresh_token and name:
            self.lbl_sso.config(text=f"Eingeloggt: {name}", foreground="#1a7a3c")
        elif self.cfg.sso_client_id:
            self.lbl_sso.config(text="Nicht eingeloggt", foreground="#b8860b")
        else:
            self.lbl_sso.config(text="Keine Client-ID gesetzt", foreground="#888")

    def _sso_login(self) -> None:
        self._apply_settings_to_cfg()
        if not self.cfg.sso_client_id:
            messagebox.showinfo("Keine Client-ID",
                                "Bitte zuerst die SSO Client-ID in der config.json "
                                "eintragen (developers.eveonline.com).")
            return
        self.lbl_sso.config(text="Login läuft (Browser) …", foreground="#888")
        self._log("SSO-Login gestartet — Browser geöffnet.")

        def work():
            try:
                tokens, info = sso.login(self.cfg.sso_client_id)
                self.cfg.sso_refresh_token = tokens.get("refresh_token")
                self.cfg.sso_character_id = info["character_id"]
                self.cfg.sso_character_name = info.get("name")
                self.cfg.save()
                self._events.put(("sso_ok", info.get("name")))
            except Exception as e:
                self._events.put(("sso_err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _check_from_clipboard(self) -> None:
        self._apply_settings_to_cfg()
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        names = localparse.parse_names(text)
        if not names:
            messagebox.showinfo("Keine Namen",
                                "Zwischenablage enthält keine erkennbare Namensliste.\n"
                                "In der Local-Memberliste Strg+A / Strg+C drücken.")
            return
        if not localparse.looks_like_namelist(text) and not messagebox.askyesno(
                "Unsicher", "Sieht nicht klar nach einer Namensliste aus. "
                            "Trotzdem prüfen?"):
            return
        self._run_threat_check(names)

    def _run_threat_check(self, names) -> None:
        if not self.cfg.enrichment_enabled:
            if not messagebox.askyesno("Threat-Check aus",
                                       "Threat-Check ist nicht aktiviert. Einmalig "
                                       "ausführen?"):
                return
        self._threat_profiles = []
        self._show_threat_panel(len(names))

        def work():
            try:
                profiles, agg, filtered = threatcheck.run_check(
                    self.cfg, names,
                    on_progress=lambda p: self._events.put(("threat_row", p)))
                self._events.put(("threat_done", (agg, filtered)))
            except Exception as e:
                self._events.put(("threat_err", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _clip_poll(self) -> None:
        if self.v_clipwatch.get():
            try:
                text = self.root.clipboard_get()
            except tk.TclError:
                text = ""
            h = hash(text)
            if h != self._last_clip:
                self._last_clip = h
                if localparse.looks_like_namelist(text):
                    self._apply_settings_to_cfg()
                    self._run_threat_check(localparse.parse_names(text))
        self.root.after(1000, self._clip_poll)

    # ---- threat panel window ----
    def _show_threat_panel(self, n_total: int) -> None:
        if getattr(self, "_threat_win", None) is None or not self._threat_win.winfo_exists():
            win = tk.Toplevel(self.root)
            win.title("Threat-Check")
            sh = win.winfo_screenheight()
            geo = f"600x{min(760, sh - 80)}"   # tall by default; fitted after render
            pos = self.cfg.intel_pos
            if pos and len(pos) == 2:
                geo += f"+{int(pos[0])}+{int(pos[1])}"
            win.geometry(geo)
            self._threat_win = win
            self._threat_head = tk.Label(win, text="", anchor="w", fg="white",
                                         bg="#444", font=("Segoe UI", 13, "bold"),
                                         padx=12, pady=10)
            self._threat_head.pack(fill="x")
            # drag the window by its header; persist the position on release
            self._threat_head.bind("<ButtonPress-1>", self._intel_drag_start)
            self._threat_head.bind("<B1-Motion>", self._intel_drag_move)
            self._threat_head.bind("<ButtonRelease-1>", self._intel_drag_end)
            # scrollable rows area
            outer = tk.Frame(win)
            outer.pack(fill="both", expand=True)
            self._threat_canvas = tk.Canvas(outer, highlightthickness=0)
            sb = ttk.Scrollbar(outer, orient="vertical",
                               command=self._threat_canvas.yview)
            self._threat_rows = tk.Frame(self._threat_canvas)
            self._threat_rows.bind("<Configure>", lambda _e: self._threat_canvas.configure(
                scrollregion=self._threat_canvas.bbox("all")))
            self._threat_canvas.create_window((0, 0), window=self._threat_rows, anchor="nw")
            self._threat_canvas.configure(yscrollcommand=sb.set)
            self._threat_canvas.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            self.root.after(50, self._apply_intel_window_opts)
        else:
            self._threat_win.deiconify()
            self._threat_win.lift()
            self._apply_intel_window_opts()
        for w in self._threat_rows.winfo_children():
            w.destroy()
        self._threat_head.config(text=f"Prüfe {n_total} Piloten …", bg="#444")

    # ---- intel floating-window options ----
    def _apply_intel_window_opts(self) -> None:
        """Apply topmost / opacity / click-through to the open intel window."""
        win = getattr(self, "_threat_win", None)
        if not win or not win.winfo_exists():
            return
        try:
            win.attributes("-topmost", bool(self.v_intel_top.get()))
            win.attributes("-alpha", max(20, int(self.v_intel_alpha.get())) / 100.0)
        except tk.TclError:
            pass
        hwnd = winutil.tk_hwnd(win)
        if hwnd:
            winutil.set_click_through(hwnd, bool(self.v_intel_click.get()))

    def _on_intel_opt_change(self, *_args) -> None:
        self.cfg.intel_topmost = bool(self.v_intel_top.get())
        self.cfg.intel_alpha = int(self.v_intel_alpha.get())
        self.cfg.intel_click_through = bool(self.v_intel_click.get())
        self.cfg.save()
        self._apply_intel_window_opts()

    def _intel_drag_start(self, e) -> None:
        win = self._threat_win
        self._intel_drag = {"ox": win.winfo_x(), "oy": win.winfo_y(),
                            "px": e.x_root, "py": e.y_root}

    def _intel_drag_move(self, e) -> None:
        d = getattr(self, "_intel_drag", None)
        if not d:
            return
        self._threat_win.geometry(
            f"+{d['ox'] + (e.x_root - d['px'])}+{d['oy'] + (e.y_root - d['py'])}")

    def _intel_drag_end(self, _e) -> None:
        win = getattr(self, "_threat_win", None)
        if win and win.winfo_exists():
            self.cfg.intel_pos = [win.winfo_x(), win.winfo_y()]
            self.cfg.save()

    def _render_threat_row(self, p) -> None:
        row = tk.Frame(self._threat_rows, bd=0)
        row.pack(fill="x", padx=8, pady=3)
        tk.Frame(row, bg=TIER_COLOR.get(p.tier, "#666"), width=10, height=40)\
            .pack(side="left", fill="y", padx=(0, 8))
        mid = tk.Frame(row)
        mid.pack(side="left", fill="x", expand=True)
        ent = " · ".join(x for x in (p.corp_name, p.alliance_name) if x) or "—"
        tk.Label(mid, text=p.name, font=("Segoe UI", 11, "bold"), anchor="w")\
            .pack(anchor="w")
        tk.Label(mid, text=ent, font=("Segoe UI", 9), fg="#888", anchor="w")\
            .pack(anchor="w")
        chips = tk.Frame(mid)
        chips.pack(anchor="w", pady=(2, 0))
        if p.danger is not None:
            self._chip(chips, f"Danger {p.danger}", p.tier)
        if p.gang_ratio is not None:
            self._chip(chips, f"Gang {p.gang_ratio}% · Solo {100 - p.gang_ratio}%",
                       "info")
        for fl in ("hunter", "cyno", "fresh", "scanner", "unknown"):
            if fl in p.flags:
                label = FLAG_LABEL[fl]
                if fl == "fresh" and p.age_days is not None:
                    label = f"Frischer Char · {p.age_days}d"
                self._chip(chips, label, p.tier if fl in ("hunter", "cyno") else "info")
        if p.recent_ships:
            ships = tk.Frame(mid)
            ships.pack(anchor="w", pady=(3, 0))
            tk.Label(ships, text="Zuletzt:", font=("Segoe UI", 8), fg="#888")\
                .pack(side="left", padx=(0, 2))
            for rs in p.recent_ships:
                kill = rs.kind == "kill"
                lab = tk.Label(ships, text=f"{rs.ship_name} {self._rel_age(rs.time)}",
                               font=("Segoe UI", 8, "underline"), cursor="hand2",
                               fg="#2c8a4a" if kill else "#b3473a")
                lab.pack(side="left", padx=2)
                lab.bind("<Button-1>", lambda _e, u=rs.url: webbrowser.open(u))
                tip(lab, ("Kill in diesem Schiff — klick: Killmail des Opfers"
                          if kill else
                          "Verlust dieses Schiffs — klick: sein Fitting"))
        right = tk.Frame(row)
        right.pack(side="right")
        if p.character_id:
            lnk = tk.Label(right, text="zKill ↗", fg="#3a7", cursor="hand2",
                           font=("Segoe UI", 9, "underline"))
            lnk.pack()
            lnk.bind("<Button-1>", lambda _e, c=p.character_id:
                     webbrowser.open(f"https://zkillboard.com/character/{c}/"))
        active = self._last_active_text(p.last_killmail_time)
        tk.Label(right, text=active[0], font=("Segoe UI", 8), fg=active[1]).pack()

    def _last_active_text(self, iso) -> tuple:
        """(text, colour) for the last-active line — only counts the last 30 days."""
        if iso:
            try:
                from datetime import datetime, timezone
                t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - t).days
            except (ValueError, TypeError):
                days = None
            if days is not None and days <= 30:
                return (f"aktiv vor {self._rel_age(iso)}", "#2c8a4a")
        return ("Keine Aktivität im letzten Monat", "#888")

    @staticmethod
    def _rel_age(iso: str) -> str:
        """Compact relative age like '5h' / '2d' / '3w' from an ISO timestamp."""
        if not iso:
            return ""
        try:
            from datetime import datetime, timezone
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            secs = (datetime.now(timezone.utc) - t).total_seconds()
        except (ValueError, TypeError):
            return ""
        if secs < 3600:
            return f"{int(secs // 60)}m"
        if secs < 86400:
            return f"{int(secs // 3600)}h"
        if secs < 7 * 86400:
            return f"{int(secs // 86400)}d"
        return f"{int(secs // (7 * 86400))}w"

    def _chip(self, parent, text, kind) -> None:
        bg = {"high": "#f3d0d0", "medium": "#f6e6c8", "low": "#d9ead0",
              "unknown": "#e2e0da", "info": "#d6e6f5"}.get(kind, "#e2e0da")
        fg = {"high": "#791f1f", "medium": "#633806", "low": "#27500a",
              "unknown": "#444441", "info": "#0c447c"}.get(kind, "#444441")
        tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 8),
                 padx=6, pady=1).pack(side="left", padx=2)

    def _threat_done(self, agg, filtered) -> None:
        # re-render sorted by severity
        order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
        for w in self._threat_rows.winfo_children():
            w.destroy()
        for p in sorted(self._threat_profiles, key=lambda x: order.get(x.tier, 9)):
            self._render_threat_row(p)
        cov = f"{agg['resolved']}/{agg['total']} geprüft"
        if agg["unresolved"]:
            cov += f" · {agg['unresolved']} unbekannt"
        head = (f"{agg['total']} nicht-blau · {agg['dangerous']} gefährlich · "
                f"{agg['hunters']} Hunter · {agg['fresh']} frisch · {cov}")
        worst = "low"
        for p in self._threat_profiles:
            if {"high": 0, "medium": 1}.get(p.tier, 9) < {"high": 0, "medium": 1}.get(worst, 9):
                worst = p.tier
        bg = TIER_COLOR.get("high" if agg["dangerous"] else "low", "#444")
        if not filtered:
            head += "  ⚠ kein SSO — Friendlies NICHT gefiltert"
            bg = "#b8860b"
        self._threat_head.config(text=head, bg=bg)
        self._fit_intel_to_content()
        self._log(f"Threat-Check: {head}")

    def _fit_intel_to_content(self) -> None:
        """Grow the intel window to show all rows without scrolling, capped to
        the screen. The top-left position is preserved (and nudged up only if the
        window would run off the bottom edge)."""
        win = getattr(self, "_threat_win", None)
        if not win or not win.winfo_exists():
            return
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        need_h = self._threat_head.winfo_reqheight() + \
            self._threat_rows.winfo_reqheight() + 24
        h = min(need_h, sh - 80)
        w = min(max(600, self._threat_rows.winfo_reqwidth() + 24), sw - 40)
        x, y = win.winfo_x(), win.winfo_y()
        if y + h > sh - 20:                 # keep it on-screen vertically
            y = max(0, sh - h - 60)
        win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")

    # --------------------------------------------------------------- queue pump
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "tick":
                    self._on_tick(payload)
                elif kind == "alarm":
                    self._on_alarm(payload)
                elif kind == "cfgchange":
                    self._refresh_friendly_display()
                    self._log("Auto-Learn: Farbe als safe gelernt.")
                elif kind == "sso_ok":
                    self._refresh_sso_status()
                    self._log(f"SSO-Login erfolgreich: {payload}")
                elif kind == "sso_err":
                    self._refresh_sso_status()
                    self._log(f"SSO-Login fehlgeschlagen: {payload}")
                    messagebox.showerror("SSO-Login", str(payload))
                elif kind == "threat_row":
                    self._threat_profiles.append(payload)
                    self._render_threat_row(payload)
                elif kind == "threat_done":
                    self._threat_done(*payload)
                elif kind == "threat_err":
                    self._log(f"Threat-Check Fehler: {payload}")
                    if getattr(self, "_threat_head", None):
                        self._threat_head.config(text=f"Fehler: {payload}", bg="#b30000")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    # banner colours: grey idle, green safe, amber warn, red threat
    _BANNER = {"idle": "#555555", "safe": "#1a7a3c",
               "warn": "#b8860b", "threat": "#b30000"}

    def _set_banner(self, text: str, state: str) -> None:
        self.banner.config(text=text, bg=self._BANNER[state])

    def _on_tick(self, r: TickResult) -> None:
        if not r.ok:
            self._set_banner("●  Kein Signal", "warn")
            self.lbl_metrics.config(text=r.error or "")
            return
        threats = len(r.threats)
        if threats:
            self._set_banner(f"⚠  HOSTILE — {threats}", "threat")
        else:
            self._set_banner("●  Sicher", "safe")
        parts = [f"Count {r.count if r.count is not None else '?'}",
                 f"Zeilen {len(r.rows)}", f"Threats {threats}"]
        if self.cfg.haven_enabled and r.haven_stage is not None:
            parts.append(f"Haven {r.haven_stage}/{r.haven_total}")
        if r.last_wave:
            parts.append("LETZTE WELLE")
        # Live pixel counts of the spawn-detector overviews ('?' = region not
        # resolvable) so a mis-set region or threshold is visible at a glance.
        if self.cfg.dread_enabled:
            parts.append(f"Dread {r.dread_lit if r.dread_lit is not None else '?'}px")
        if self.cfg.faction_enabled:
            parts.append(
                f"Faction {r.faction_lit if r.faction_lit is not None else '?'}px")
        self.lbl_metrics.config(text="   ·   ".join(parts))

        if bool(r.last_wave) != self._lw_prev:
            self._lw_prev = bool(r.last_wave)
            if self._lw_prev:
                self._log("🕐 Letzte Welle — Spawn-Detektoren scharf.")
            elif self.cfg.dread_enabled or self.cfg.faction_enabled:
                self._log("Spawn-Detektoren inaktiv (Site beendet / neuer Counter).")

    def _on_alarm(self, r: TickResult) -> None:
        # Hostile alarm (red overlay + primary sound) — only if that feature is on.
        if self.cfg.local_alarm_enabled and (r.new_threat or r.count_increased):
            reasons = []
            if r.count_increased:
                reasons.append(f"Count ↑ ({r.count})")
            if r.new_threat:
                reasons.append(f"{len(r.threats)} Nicht-Friendly")
            reason = " · ".join(reasons) or "Alarm"
            alarm.play(self.cfg.alarm_sound_path, self.cfg.alarm_volume / 100)
            self._show_overlay("hostile", reason)
            self._log(f"🚨 HOSTILE — {reason}  | region={r.cap_region} "
                      f"count={r.count} rows={len(r.rows)}")
            for t in r.threats[:8]:
                self._log(f"    THREAT Z{t.index} rgb={t.rgb}")

        # Auto threat-check: a new neut appeared and we OCR'd names → run a check.
        # Requires the Threat-Check feature to be on (avoids a modal prompt spam).
        if (self.cfg.auto_threat_enabled and self.cfg.enrichment_enabled
                and r.new_threat and r.threat_names):
            self._log(f"Auto-Threat: {len(r.threat_names)} Name(n) per OCR gelesen.")
            self._run_threat_check(r.threat_names)

        # Last-wave alarm (amber overlay + own sound).
        if r.haven_reached:
            detail = f"Pocket {r.haven_stage}/{r.haven_total} — danach neue Site!"
            alarm.play(self.cfg.haven_alarm_sound_path, self.cfg.haven_volume / 100)
            self._show_overlay("haven", detail)
            self._log(f"🏁 LETZTE WELLE — {detail}")

        # Last-wave spawn detectors (each its own overlay + sound).
        if r.dread_spawn:
            alarm.play(self.cfg.dread_sound_path, self.cfg.dread_volume / 100)
            self._show_overlay("dread", "Dread/Titan im Overview!")
            self._log("🐉 DREAD/TITAN-SPAWN")
        if r.faction_spawn:
            alarm.play(self.cfg.faction_sound_path, self.cfg.faction_volume / 100)
            self._show_overlay("faction", "Faction-Spawn im Overview!")
            self._log("🩸 FACTION-SPAWN")

    # --------------------------------------------------------------- overlay
    # Each alarm kind has its own popup so a hostile and a dread-check alarm can
    # show at the same time (stacked vertically).
    _OVERLAY_STYLE = {
        "hostile": ("⚠  HOSTILE IN LOCAL", "#b30000", "#ffdddd", 40),
        "haven":   ("🏁  LETZTE WELLE", "#b3720a", "#fff0d6", 160),
        "dread":   ("🐉  DREAD / TITAN", "#6a1b9a", "#f0dcff", 280),
        "faction": ("🩸  FACTION-SPAWN", "#9a1b3a", "#ffd8e0", 400),
    }

    _OVERLAY_W, _OVERLAY_H = 460, 110

    def _overlay_xy(self, kind: str, default_y: int) -> tuple:
        """Stored position for this overlay, or top-centred fallback."""
        pos = self.cfg.overlay_pos.get(kind)
        if pos and len(pos) == 2:
            return int(pos[0]), int(pos[1])
        sw = self.root.winfo_screenwidth()
        return (sw - self._OVERLAY_W) // 2, default_y

    def _show_overlay(self, kind: str, detail: str) -> None:
        title, bg, fg, ytop = self._OVERLAY_STYLE[kind]
        x, y = self._overlay_xy(kind, ytop)
        entry = self._overlays.get(kind)
        if entry is None or not entry["win"].winfo_exists():
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.attributes("-alpha", 0.92)
            ov.configure(bg=bg)
            ov.geometry(f"{self._OVERLAY_W}x{self._OVERLAY_H}+{x}+{y}")
            tk.Label(ov, text=title, bg=bg, fg="white",
                     font=("Segoe UI", 22, "bold")).pack(pady=(14, 0))
            detail_lbl = tk.Label(ov, text=detail, bg=bg, fg=fg,
                                  font=("Segoe UI", 12))
            detail_lbl.pack()
            ov.bind("<Button-1>", lambda _e, k=kind: self._hide_overlay(k))
            entry = {"win": ov, "detail": detail_lbl, "after": None}
            self._overlays[kind] = entry
        else:
            entry["detail"].config(text=detail)
            entry["win"].geometry(f"+{x}+{y}")   # honour a moved position
            entry["win"].deiconify()
            entry["win"].lift()
        if entry["after"]:
            self.root.after_cancel(entry["after"])
        entry["after"] = self.root.after(
            OVERLAY_SECONDS * 1000, lambda k=kind: self._hide_overlay(k))

    def _hide_overlay(self, kind: str) -> None:
        entry = self._overlays.get(kind)
        if entry and entry["win"].winfo_exists():
            entry["win"].withdraw()

    def _bind_recursive(self, widget, seq, func) -> None:
        widget.bind(seq, func)
        for child in widget.winfo_children():
            self._bind_recursive(child, seq, func)

    def _place_overlay(self, kind: str) -> None:
        """WYSIWYG placement: show the popup, let the user drag it, double-click
        to save its position. Removes the popup from the capture region so it no
        longer re-triggers the alarm."""
        self._show_overlay(kind, "Ziehen zum Verschieben · Doppelklick speichert")
        entry = self._overlays[kind]
        win = entry["win"]
        if entry["after"]:
            self.root.after_cancel(entry["after"])
            entry["after"] = None
        drag = {}

        def start(e):
            drag.update(ox=win.winfo_x(), oy=win.winfo_y(),
                        px=e.x_root, py=e.y_root)

        def move(e):
            win.geometry(f"+{drag['ox'] + (e.x_root - drag['px'])}"
                         f"+{drag['oy'] + (e.y_root - drag['py'])}")

        def save(_e):
            pos = (win.winfo_x(), win.winfo_y())
            self.cfg.overlay_pos[kind] = [pos[0], pos[1]]
            self.cfg.save()
            self._log(f"{kind}-Popup-Position gespeichert: {pos}")
            win.destroy()                 # fresh window next alarm, normal binds
            self._overlays.pop(kind, None)

        self._bind_recursive(win, "<ButtonPress-1>", start)
        self._bind_recursive(win, "<B1-Motion>", move)
        self._bind_recursive(win, "<Double-Button-1>", save)

    def _fire_test_alarm(self) -> None:
        self._apply_settings_to_cfg()
        alarm.play(self.cfg.alarm_sound_path, self.cfg.alarm_volume / 100)
        self._show_overlay("hostile", "Test-Alarm")

    # --------------------------------------------------------------- displays
    def _refresh_friendly_display(self) -> None:
        for w in self.swatches.winfo_children():
            w.destroy()
        cols = self.cfg.friendly_colors
        self.lbl_friendly.config(text=f"{len(cols)} Farben")
        for rgb in cols[:24]:
            hexc = "#%02x%02x%02x" % rgb
            tk.Frame(self.swatches, bg=hexc, width=18, height=18,
                     highlightthickness=1, highlightbackground="#444")\
                .pack(side="left", padx=1)
        # Previews reference the whitelist, so keep them in sync.
        if hasattr(self, "tag_preview"):
            self._render_tag_preview()
            self._render_tol_preview()

    def _refresh_status_static(self) -> None:
        origin = winutil.find_window_origin(self.v_title.get().strip() or "EVE")
        self.lbl_window.config(
            text=(f"Fenster gefunden @ {origin}" if origin else "Fenster nicht gefunden")
                 + (f"   |   OCR: {'verfügbar' if ocr.available() else 'NICHT installiert'}"))
        cr, hr = self.cfg.capture_region, self.cfg.header_region
        self.lbl_regions.config(
            text=f"Liste: {cr.as_tuple() if cr.is_valid() else '—'}   "
                 f"Header: {hr.as_tuple() if hr.is_valid() else '—'}   "
                 f"Baseline: {self.cfg.baseline_count}")
        if hasattr(self, "lbl_haven"):
            hv = self.cfg.haven_region
            self.lbl_haven.config(
                text=("aktiv · " if self.cfg.haven_enabled else "aus · ")
                     + f"Bereich: {hv.as_tuple() if hv.is_valid() else '—'}")
        if hasattr(self, "lbl_spawn"):
            dr, fa = self.cfg.dread_region, self.cfg.faction_region
            self.lbl_spawn.config(
                text=(f"Dread: {'an' if self.cfg.dread_enabled else 'aus'} "
                      f"{dr.as_tuple() if dr.is_valid() else '—'}   ·   "
                      f"Faction: {'an' if self.cfg.faction_enabled else 'aus'} "
                      f"{fa.as_tuple() if fa.is_valid() else '—'}"))
        if hasattr(self, "btn_start"):
            self._update_ready()

    def _log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----------------------------------------------------------------- lifecycle
    def _on_close(self) -> None:
        try:
            self.scanner.stop()
            self._apply_settings_to_cfg()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
