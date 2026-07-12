# Mister Lee's magischer Intelligentheit-Helfer

Eine passive Desktop-App, die den **Local-Chat eines laufenden EVE-Clients per
Screen-Capture überwacht** und **Alarm auslöst, sobald ein nicht-befreundeter
Pilot im Local erscheint** — unabhängig davon, ob er etwas schreibt.

Der Alarm feuert **beim Erscheinen**, nicht erst bei einer Chat-Nachricht.

## Wie es funktioniert

Erkennung ist zweistufig und arbeitsteilig:

1. **Header-Count (Stufe 1):** OCR der Zahl im Local-Header. Steigt der Count →
   jemand ist rein → Alarm. Das ist die **primäre Neuzugangs-Erkennung** — sie
   fängt auch den Neut-Hunter ohne Standing-Icon und Piloten unterhalb des
   sichtbaren Bereichs.
2. **Color-Sampling (Stufe 2):** Pro Zeile wird die Farbe der Standing-/Tag-Icon-
   Spalte ganz links gesampelt und klassifiziert in **friendly / threat / empty**:
   - **empty** — Slot ist dunkler als die *Tag-Schwelle* (`tag_min_value`): es
     sitzt gar kein farbiges Icon dort → **kein Alarm**.
   - **friendly** — Farbe ist in der kalibrierten Whitelist → kein Alarm.
   - **threat** — ein *vorhandenes* Icon, dessen Farbe **nicht** friendly ist →
     **Alarm** (z. B. Rot/Orange/Grau).

   > Wichtig: Leere/dunkle Slots lösen **keinen** Alarm aus. Das verhindert
   > Phantom-Alarme, wenn sich die gesampelte Zeile verschiebt (z. B. beim
   > Multiboxing / Client-Wechsel verschiebt sich der aktive Spieler). Die
   > Erkennung von Neuzugängen ohne Icon übernimmt Stufe 1 (Header-Count).

## Installation (Windows)

```powershell
# 1. Abhängigkeiten
python -m pip install -r requirements.txt

# 2. Tesseract OCR (für Stufe 1 / Header-Count) — einmalig:
#    https://github.com/UB-Mannheim/tesseract/wiki
#    Standardpfad: C:\Program Files\Tesseract-OCR\tesseract.exe
#    Liegt es woanders, in der config.json unter "tesseract_cmd" eintragen.
```

> Ohne Tesseract läuft die App weiter — Stufe 1 (Header-Count) ist dann
> deaktiviert, Stufe 2 (Color-Sampling) funktioniert. Bei der Kalibrierung wird
> dann nach der Pilotenzahl gefragt.

## Starten

Drei Wege — vom bequemsten zum entwicklernächsten:

**1. Als ausführbare Datei (.exe, kein Python nötig)**
Einmalig bauen:
```powershell
.\build_exe.ps1
```
Ergebnis: `dist\Mister Lees magischer Intelligentheit-Helfer.exe` — frei
verschiebbar (z. B. auf den Desktop) und per **Doppelklick** startbar, ohne
Terminal. (Tesseract bleibt eine separate Installation, siehe oben; die .exe
findet es automatisch.) Das Icon stammt aus `icon.ico` im Projektordner —
ersetze diese Datei durch dein eigenes Bild, um das App-Icon zu ändern.

**2. Doppelklick-Starter (Python installiert, kein Build)**
`Flint Local Watcher.pyw` doppelklicken — läuft über `pythonw`, also ohne
Konsolenfenster.

**3. Per Terminal (Entwicklung)**
```powershell
python -m eve_localwatcher
```

## Bedienung

Oben eine **permanente Live-Bahn**: eine große Status-Bahn (grau = gestoppt,
grün = sicher, rot = Hostile), darunter die Live-Werte und der **Start/Stop**-
Knopf. Start ist **deaktiviert**, bis die Einrichtung steht — eine Zeile zeigt
den nächsten Schritt an.

Die ganze Einrichtung liegt in **Tabs** darunter:
- **Erfassung** — EVE-Fenster, Capture-Bereiche, Zeilen-/Icon-Layout, Namens-OCR
- **Erkennung** — Kalibrierung, Tag-Schwelle, Toleranz (mit Live-Vorschau)
- **Alarm & Haven** — Hostile-Local-Alarm, Sounds + **Lautstärke je Alarm**,
  Popup-Platzierung, „Letzte Welle"-Counter, Spawn-Detektoren
- **Threat-Check** — SSO-Login, Zwischenablage-Check, Auto-Threat, Intel-Fenster
- **Log** — Verlauf & Debug-Ausgabe

**Jedes Feature ist einzeln zuschaltbar** — du musst nicht alles nutzen:
- **Hostile-Local-Alarm** (Tab *Alarm & Haven*) — Header-Count + Farb-Sampling
- **Letzte Welle** (Tab *Alarm & Haven*) — Pocket-Counter `N/M`; Alarm „letzte
  Welle, danach neue Site anfliegen"
- **Spawn-Detektoren** (Tab *Alarm & Haven*) — eigene Alarme für Dread/Titan- und
  Faction-(Battleship-)Spawns; nur in der letzten Welle scharf
- **Threat-Check** (Tab *Threat-Check*) — manuelle Bewertung per Zwischenablage
- **Auto-Threat** (Tab *Threat-Check*) — liest bei einem Neut die Namen per OCR
  und startet den Threat-Check automatisch

Jeder Alarm hat einen **eigenen WAV-Sound und einen Lautstärke-Regler** (0–100 %).

Der **Start**-Knopf treibt die Scan-Features (Local-Alarm / Letzte Welle /
Spawn-Detektoren / Auto-Threat); der manuelle Threat-Check läuft unabhängig über
seinen eigenen Knopf. Sind nur einzelne Features aktiv, verlangt die App auch nur
deren Einrichtung (z. B. „nur Letzte Welle" braucht keine Farb-Kalibrierung).

## Erste Einrichtung

1. **EVE windowed** starten, Local-Memberliste sichtbar machen (festes Layout).
   Beim Multiboxing im Dropdown **„EVE-Fenster" genau einen Client wählen**
   (voller Titel `EVE - Charname`). Sonst würde der Scan dem jeweils obersten
   Client folgen und die fensterrelativen Bereiche zeigten auf den falschen
   Client. ⟳ aktualisiert die Liste.
2. **„Pilotenliste festlegen"** → Rechteck über die Memberliste ziehen
   (Icon-Spalte links + Namen).
3. **„Header (Local [N]) festlegen"** → Rechteck **nur über die Zahl** ziehen
   (das Personen-Icon links **weglassen** — es stört das OCR). Der Member-Count
   wird als blanke Zahl neben dem Icon gerendert, nicht als `Local [N]`.
4. **Zeilen-/Icon-Layout** justieren:
   - `Icon X-Offset` / `Icon Sample-Breite`: nur die **schmale Icon-Spalte ganz
     links** treffen — **niemals** den Zeilenhintergrund (eine angeklickte Zeile
     hat einen roten/dunklen Hintergrund und würde sonst als Hostile gewertet).
   - `Zeilenhöhe` / `Erste Zeile Y-Offset`: so einstellen, dass jede Zeile mittig
     getroffen wird.
5. In einem **ruhigen Moment** (nur eigene Alts + bekannte Friendlies im Local):
   **„Aktuelles Local als sicher merken"** → die vorkommenden Icon-Farben werden
   als Friendly-Set gespeichert.
6. **„▶ Start"**.

## Letzte Welle + Spawn-Detektoren (optional)

Eine Haven hat mehrere Pockets; in der letzten Welle können Dreads/Titans oder
Faction-Battleships spawnen. Dafür gibt es drei zusammenhängende, opt-in
Detektoren — jeder mit **eigenem WAV-Sound, eigenem Lautstärke-Regler und
eigenem, verschiebbarem Overlay**:

**1. „Letzte Welle" (Pocket-Counter).** Liest den Counter (`N/M`, z. B. `6/6`)
und meldet beim Erreichen der letzten Pocket: *letzte Welle, danach neue Site
anfliegen.*

- Frame **„Letzte Welle"**: aktivieren, **„Counter-Bereich festlegen"** (Rechteck
  **nur um die Zahl** `N/M`, den grünen Balken weglassen), Sound + Lautstärke.
- **„Max. Pockets"** (Default 6) ist die Plausibilitätsgrenze: Lesungen mit
  abweichender Gesamtzahl oder `N > M` (z. B. `9/6`) werden als OCR-Fehler
  **verworfen** — typisch beim Kameraschwenk.
- **Monotonie-Filter:** akzeptiert nur denselben Wert, `+1` oder einen Reset auf
  `1` (neue Site). Vor-/Rücksprünge eines Schwenks (z. B. `3 → 6 → 4`) werden
  gefiltert. So gibt es keine Fehlalarme durch verrutschte OCR-Werte.
- Feuert **einmal** beim Erreichen der letzten Pocket; sinkt der Zähler wieder
  oder verschwindet (neue Site), wird der Alarm neu scharf.

**2. + 3. Spawn-Detektoren (Dread/Titan, Faction-Battleship).** Erzeuge in EVE
**zwei eigene Overview-Fenster**, eines gefiltert auf Dreads/Titans, eines auf
die Faction-Battleships. Jeder Detektor beobachtet sein Overview-Rechteck und
schlägt Alarm, **sobald dort etwas erscheint** (Helligkeits-Erkennung: leer =
dunkel, Spawn = helle Zeile). Feuert einmal pro Spawn, re-armt wenn das Overview
wieder leer ist.

- Frame **„Spawn-Detektoren"**: je Block aktivieren, **„Overview-Bereich
  festlegen"** (nur den Zeilenbereich, ohne Spaltenköpfe), Sound + Lautstärke.
- **Nur in der letzten Welle scharf:** die Spawn-Detektoren werten erst, wenn der
  Pocket-Counter die letzte Pocket erreicht hat. Sie **brauchen** also den
  aktiven „Letzte Welle"-Counter. Ist der Counter mittendrin kurz nicht lesbar
  (Kamera, Verdeckung), bleiben die Detektoren bis zu **~60 s** scharf; ein
  frischer Counter (`1/6`) beendet die letzte Welle sofort.
- **„Erkennung testen"**: liest das Overview-Rechteck sofort aus und schreibt ins
  Log, ob es als belegt erkannt würde — zum Prüfen einfach kurz den Filter
  rausnehmen, damit etwas im Overview steht.
- **Live-Diagnose:** die Statuszeile zeigt bei aktivierten Detektoren laufend
  `Dread N px` / `Faction N px` (helle Pixel im Rechteck; `?` = Bereich nicht
  auflösbar) sowie `LETZTE WELLE`, solange die Detektoren scharf sind. Das
  Scharf-/Unscharf-Schalten wird zusätzlich geloggt.

Alle laufen im selben Scan-Loop wie der Hostile-Scan; mehrere Alarme können
gleichzeitig erscheinen (gestapelte Overlays).

## Konfiguration

Wird automatisch unter `%USERPROFILE%\.eve_localwatcher\config.json` gespeichert.
`config.example.json` zeigt alle Felder. Wichtige Parameter:

| Feld | Bedeutung |
|---|---|
| `capture_region`, `header_region` | Bereiche, **relativ zum Fenster** (übersteht Verschieben) |
| `icon_column_x_offset`, `icon_sample_width` | wo die Icon-Spalte gesampelt wird |
| `row_height`, `first_row_y_offset` | Zeilenraster |
| `friendly_colors[]` | kalibrierte Whitelist (nicht hardcoden) |
| `color_tolerance` | HSV-Feature-Distanz (Default 18). Zu eng → Fehlalarme |
| `tag_min_value` | Helligkeitsschwelle (Default 70). Slot dunkler als das ⇒ „leer", kein Alarm. Trennt echte Icons vom dunklen Hintergrund |
| `scan_interval_ms` | Loop-Intervall (Default 750) |
| `alarm_sound_path`, `alarm_volume` | optionaler WAV + Lautstärke 0–100 (Hostile) |
| `haven_*`, `dread_*`, `faction_*` | Region/Sound/Lautstärke je Detektor (Letzte Welle, Dread/Titan, Faction) |
| `haven_expected_total` | Max. Pockets (Default 6) — Plausibilitätsgrenze gegen OCR-Fehler |
| `spawn_brightness_thr`, `spawn_min_bright_px` | Schwellen der Spawn-Präsenzerkennung (heller Pixel-Anteil) |
| `intel_*` | Intel-Fenster: Position, Transparenz, Immer-oben, Klick-durch |
| `auto_learn_enabled` | **Default aus** — ein still sitzender Hostile würde sonst als safe gelernt |

## Alarm-Popups platzieren

Die Capture erfolgt über **Bildschirm-Pixel** — liegt ein Alarm-Popup über
einem Capture-Bereich, liest der nächste Scan das Popup und löst erneut Alarm
aus (Rückkopplung). Deshalb beide Popups **weg von den Bereichen** legen:

- „Hostile-Popup platzieren" (Frame *Alarm & Loop*) bzw. „Popup platzieren" in
  den Frames *Letzte Welle* und *Spawn-Detektoren* klicken → das Popup erscheint →
  **ziehen** → **Doppelklick speichert** die Position (pro Monitor, übersteht
  Neustart).
- Ohne gespeicherte Position erscheinen die Popups oben-zentriert (vier Alarm-
  arten gestapelt: Hostile, Letzte Welle, Dread/Titan, Faction).

## Intel-Fenster (Threat-Check als Overlay)

Das Threat-Check-Ergebnisfenster lässt sich als **Overlay über dem Spiel**
nutzen (Frame *Intel-Fenster* im Tab *Threat-Check*):

- **Immer oben** — hält das Fenster über dem EVE-Client.
- **Transparenz** — Regler 20–100 %.
- **Klick-durch** — Mausklicks gehen durch das Fenster ins Spiel. Achtung: dann
  sind die zKill-Links nicht klickbar; zum Bedienen/Verschieben wieder ausschalten.
- **Verschieben** — an der Kopfzeile ziehen; die Position bleibt gespeichert.
- Bei einem neuen Intel-Scan wird der **Inhalt zurückgesetzt**, das Fenster bleibt
  aber offen an seiner Position.

## Bekannte Fallstricke (im Tool behandelt)

- **Selection-Highlight ≠ Standing-Farbe** → es wird nur die schmale Icon-Spalte
  gesampelt, nie der Zeilenhintergrund.
- **Local scrollt bei vollem System** → Header-Count (Stufe 1) kompensiert.
- **Leere Slots unterhalb der Pilotenliste** → die Zeilenanzahl wird durch den
  Header-Count begrenzt, damit leerer Listen-Hintergrund nicht als „Neutral"
  fehlgewertet wird.
- **DPI-Scaling** → Prozess wird beim Start per-monitor DPI-aware gesetzt, damit
  Auswahl- und Capture-Koordinaten übereinstimmen.

## Noch nicht enthalten (nach MVP)

Enrichment via ESI/zKillboard, Namen-OCR, Watchlist (Named-Targets). Auto-Learn
ist vorhanden, aber standardmäßig aus.

## Projektstruktur

```
eve_localwatcher/
  __main__.py      # Einstieg: DPI-aware + App starten
  app.py           # Tkinter-Control-Panel + Alarm-Overlay (Main-Thread)
  scanner.py       # Scan-Loop: Stufe 1 + 2, Debounce, Auto-Learn (Worker-Thread)
  capture.py       # mss-Screen-Capture
  color.py         # HSV-Feature-Distanz + Friendly-Test
  ocr.py           # Header-Count via Tesseract (graceful fallback)
  alarm.py         # akustischer Alarm mit Lautstärke (WAV-Sample-Skalierung + winsound)
  region_select.py # Vollbild-Rechteck-Auswahl
  winutil.py       # DPI, Fenstersuche, Virtual-Screen
  config.py        # Config-Modell + JSON-Persistenz
```
