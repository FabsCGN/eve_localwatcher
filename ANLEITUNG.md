# Mister Lee's magischer Intelligentheit-Helfer — Komplett-Anleitung

Ein passives Überwachungs-Tool für EVE-Ratting. Es liest per **Screen-Capture**
den Local deines laufenden EVE-Clients und schlägt Alarm, sobald ein
nicht-befreundeter Pilot auftaucht — und kann auf Knopfdruck jeden Neut per
ESI + zKillboard bewerten. Es greift **nie** in den Client ein (keine Tasten,
keine Klicks ins Spiel) → EULA-sicher.

> Diese Anleitung erklärt **jede** Funktion: *was* sie macht und *wie* sie
> funktioniert. Gedacht zum Weitergeben an Corpmates.

---

## 1. Das Grundprinzip in 30 Sekunden

Das Tool macht Screenshots eines kleinen Bildschirmbereichs (deine Local-
Memberliste) und wertet **Pixel** aus — keine Spieldaten, kein Memory-Reading.

Erkennung läuft **zweistufig**:
- **Stufe 1 – Header-Count:** Es liest per OCR die Mitgliederzahl im Local
  (z. B. „6"). Steigt die Zahl → jemand ist reingekommen → Alarm.
- **Stufe 2 – Farb-Sampling:** Pro Pilotenzeile liest es die Farbe des
  Standing-Icons links und entscheidet: **friendly** (in deiner Whitelist),
  **threat** (fremdes farbiges Icon) oder **leer** (kein Icon → ignoriert).

Nur ein *vorhandenes, nicht-friendly* Icon löst Stufe-2-Alarm aus. Neue Piloten
ohne Icon fängt Stufe 1 (der Zähler steigt).

**Alle Module sind einzeln zuschaltbar** (eigene Enable-Schalter): Hostile-Local-
Alarm, Haven Dread-Watch, Threat-Check und Auto-Threat. Du kannst z. B. nur die
Haven-Überwachung laufen lassen — die App verlangt dann auch nur deren
Einrichtung.

---

## 2. Installation & Start

**Voraussetzung (einmalig): Tesseract-OCR.** Wird für das Lesen von Zahlen
(Header-Count, Haven-Counter) gebraucht. Ohne Tesseract erscheint im Tool eine
gelbe Warnung mit Installationslink; das Farb-Sampling funktioniert trotzdem.
Download: <https://github.com/UB-Mannheim/tesseract/wiki>

**Starten — drei Wege:**
1. **`Mister Lees magischer Intelligentheit-Helfer.exe`** doppelklicken (kein
   Python nötig). Gebaut wird sie mit `.\build_exe.ps1`.
2. **`Flint Local Watcher.pyw`** doppelklicken (wenn Python installiert ist).
3. `python -m eve_localwatcher` im Terminal (Entwicklung).

---

## 3. Die Oberfläche

Ganz oben eine **permanente Live-Bahn**, darunter die Einstellungen in **Tabs**.

### Live-Bahn (immer sichtbar)
- **Status-Balken** (groß, farbig): grau = gestoppt, grün = **Sicher**, rot =
  **HOSTILE — N**. Der eine Blick, der zählt.
- **Werte-Zeile:** `Count · Zeilen · Threats · Haven` — die Live-Messwerte.
- **▶ Start / ⏸ Stop:** startet/stoppt die Überwachung. Start ist **gesperrt**,
  bis die Einrichtung steht; eine Zeile zeigt den nächsten Schritt.
- **Alarm testen / 🔍 Debug / Baseline:** Sound+Overlay testen · Diagnose-
  Snapshot · Header-Zähler-Referenz neu setzen.
- **Gelbe OCR-Warnung:** erscheint nur, wenn Tesseract fehlt (klickbar).

---

## 4. Erste Einrichtung (Schritt für Schritt)

1. EVE **im Fenstermodus** starten, Local-Memberliste sichtbar machen.
2. Tab **Erfassung** → im Dropdown **deinen Client wählen** (voller Titel).
3. **„Pilotenliste festlegen"** → Rechteck über die Memberliste ziehen.
4. **„Header-Zahl festlegen"** → Rechteck **nur über die Zahl** (ohne das
   Personen-Icon).
5. **Icon-Layout** justieren (siehe unten), so dass die Icon-Spalte mittig
   getroffen wird.
6. In einem **ruhigen Moment** (nur Friendlies im Local): Tab **Erkennung** →
   **„Aktuelles Local als sicher merken"**.
7. **▶ Start**.

---

## 5. Tab „Erfassung"

**EVE-Fenster (Dropdown + ⟳):** pinnt **genau einen** Client.
*Warum:* Beim Multiboxing heißen alle Fenster `EVE - Charname`. Ohne festes
Pinnen würde das Tool jeweils das oberste Fenster scannen und beim Client-Wechsel
den falschen capturen. ⟳ aktualisiert die Liste.

**fensterrelativ (Checkbox):** speichert alle Bereiche relativ zur
Fensterposition → übersteht das Verschieben des EVE-Fensters.

**Pilotenliste / Header-Zahl festlegen:** öffnen einen Vollbild-Auswahlmodus;
du ziehst ein Rechteck. *Wie:* die Koordinaten werden (fensterrelativ)
gespeichert und bei jedem Scan neu aufgelöst.

**Icon-Layout (relativ zur Pilotenliste):**
- **Icon X-Offset:** Abstand der Icon-Spalte vom linken Rand. *Wichtig:* nur die
  schmale Icon-Spalte treffen, **nie** den Zeilenhintergrund (angeklickte Zeilen
  sind rot/dunkel hinterlegt → sonst Fehlalarm).
- **Icon Sample-Breite:** wie breit gesampelt wird (Median über mehrere Pixel →
  robust gegen Anti-Aliasing).
- **Zeilenhöhe / Erste Zeile Y-Offset:** das Zeilenraster.
- **Max. sichtbare Zeilen:** Obergrenze pro Scan (zusätzlich durch den
  Header-Count begrenzt).
- **Name X-Offset / Name-Breite (OCR):** Lage und Breite des Namenstexts rechts
  neben den Icons — nur für **Auto-Threat** nötig (siehe Abschnitt 8). So
  einstellen, dass nur der Name erfasst wird, nicht das Icon.

---

## 6. Tab „Erkennung"

Hier definierst du, was **friendly** ist.

**Aktuelles Local als sicher merken (Kalibrierung):** lernt die aktuell
vorkommenden Tag-Farben als **Friendly-Whitelist**. *Wie:* es sampelt die
Icon-Spalte aller Piloten (begrenzt durch den Header-Count, damit kein leerer
Hintergrund gelernt wird) und speichert die echten Tag-Farben. Leere Slots
werden übersprungen.

**Whitelist leeren:** löscht alle gelernten Farben.

**Tag-Schwelle (Regler):** „Ist da überhaupt ein Icon?" Geprüft wird die
**Helligkeit** (hellster RGB-Kanal). Unter dem Wert = leerer Slot → **nie**
Alarm. *Live-Vorschau* zeigt, ob Beispielfarben als „Icon" oder „leer" gelten.

**Toleranz (Regler):** „Gehört diese Icon-Farbe zu meinen Freunden?" Misst den
**Farbabstand** zur Whitelist. Niedrig = streng (eigene Farbe weicht leicht ab →
Fehlalarm), hoch = locker (fremde Farbe gilt als friendly → Hostile rutscht
durch). *Live-Vorschau* zeigt friendly/threat je nach Abstand.

---

## 7. Tab „Alarm & Haven"

**Hostile-Local-Alarm aktiv (Enable-Schalter, oben):** schaltet die gesamte
Hostile-Erkennung (Header-Count + Farb-Sampling) an/aus. *Aus* = kein
Hostile-Alarm, aber Haven und Threat-Check können weiterlaufen. So nutzt du
einzelne Module unabhängig.

**Intervall (ms):** Zeit zwischen zwei Scans. Kleiner = schnellere Reaktion,
mehr CPU.

**Sound:** WAV-Datei für den Hostile-Alarm (leer = System-Beep).

**Auto-Learn (riskant, Default aus):** lernt eine fremde Tag-Farbe automatisch
als safe, wenn sie X Sekunden präsent ist. *Gefahr:* ein still sitzender Hostile
würde so als friendly gelernt → bewusst standardmäßig aus.

**Hostile-Popup platzieren:** das Alarm-Popup erscheint zum Ziehen, Doppelklick
speichert die Position. *Warum:* Die Capture liest Bildschirm-Pixel — liegt das
Popup über einem Capture-Bereich, liest der nächste Scan das Popup und löst
erneut Alarm aus. Deshalb das Popup **weg von den Bereichen** (am besten auf
einen zweiten Monitor) legen.

### Haven / Dread-Watch (Pocket-Counter)
Eine Haven hat 6 Pockets; in der letzten kann ein Dreadnought spawnen.
- **aktiviert:** schaltet den zweiten Detektor an.
- **Counter-Bereich festlegen:** Rechteck **nur um die Zahl `N/M`** (z. B. 6/6),
  ohne den grünen Balken.
- **Erwartete Pockets (Default 6):** Anzeige/Validierung. Ausgelöst wird
  **generisch bei N = M**.
- **Dread-Sound + Dread-Popup platzieren:** eigener Sound und ein **bernsten­
  farbenes** Overlay „⚠ DREAD-CHECK", getrennt vom roten Hostile-Alarm.
- *Verhalten:* feuert **einmal** beim Erreichen der letzten Pocket; sinkt der
  Zähler wieder (neue Haven ab 1/6), wird der Alarm neu scharf.

---

## 8. Tab „Threat-Check" (ESI + zKillboard)

Bewertet nicht-blaue Piloten wie localthreat.xyz — mit Browser-Links.

**aktiviert (Netzwerk):** schaltet die Online-Abfragen ein. Friendlies werden
**vor** jeder Abfrage rausgefiltert und nie an externe Server geschickt.

**EVE-SSO Login:** einmaliges Login über die offizielle EVE-Anmeldung (Browser).
*Wofür:* liefert deine **Corp/Allianz** und deine **aktuelle Fleet**, um
Friendlies sauber zu erkennen. *Wie:* OAuth2/PKCE, nur Lese-Scope
`esi-fleets.read_fleet.v1`; danach merkt sich das Tool ein Refresh-Token —
kein erneutes Login nötig.

**API-Kontakt (optional):** ein Name/Kontakt für den User-Agent der API-
Aufrufe (Höflichkeit ggü. ESI/zKill). Muss keine E-Mail sein, darf leer bleiben,
bleibt nur lokal.

**Local aus Zwischenablage prüfen:** der zuverlässige Weg. *Wie:* in der
Local-Memberliste **Strg+A → Strg+C**, dann diesen Knopf. Das Tool liest die
exakten Namen aus der Zwischenablage (kein OCR-Fehler, erfasst alle Piloten).

**Zwischenablage auto-überwachen:** sobald du eine Local-Namensliste kopierst,
startet der Check von selbst.

**Auto-Threat: bei Neut Namen per OCR prüfen (Enable-Schalter):** der
vollautomatische Weg. *Wie:* Erscheint ein Nicht-Friendly im Local, liest der
Scanner dessen Namen direkt per **OCR** vom Bildschirm und startet den
Threat-Check — **ohne** Strg+C. Dafür müssen im Tab *Erfassung* „Name X-Offset"
und „Name-Breite" passen. OCR ist fehleranfälliger als die Zwischenablage:
nicht lesbare Namen erscheinen als „nicht aufgelöst". Läuft nur, wenn der
Scanner per **Start** aktiv ist.

### Der Friendly-Filter — wer wird ausgeblendet?
„blue/green/purple" wird aus echten Beziehungen rekonstruiert:
- **green** = deine Corp · **blue** = deine Allianz (aus deiner Char-ID)
- **purple** = deine **Fleet** (aus dem SSO-Login)
- zusätzlich optionale manuelle Blue-Listen.

Alles davon wird **nie** abgefragt oder angezeigt — nur echte Neuts landen im
Panel.

---

## 9. Das Threat-Panel im Detail

Ein eigenes Fenster, das pro nicht-blauem Piloten eine Zeile zeigt, sortiert
nach Gefahr.

**Kopfzeile (Aggregat):** z. B. „7 nicht-blau · 3 gefährlich · 1 Hunter ·
1 frisch · 6/7 geprüft". Die **Abdeckung** („6/7 geprüft") ist bewusst laut — das
Panel sagt nie „sicher", solange nicht alles aufgelöst ist.

**Pro Pilotenzeile:**
- **Farbiger Balken links:** Gesamtgefahr (rot = high, bernstein = medium,
  grün = low, grau = unbekannt).
- **Name + Corp · Allianz.**
- **Chips:**
  - **Danger X** — zKill-Danger-Ratio (0–100).
  - **Gang X% · Solo Y%** — fliegt er meist im Verband oder allein?
  - **Hunter** — viele Kills in Cloaky/Recon/Dictor/Black-Ops/T3C-Hulls.
  - **Frischer Char · Nd** — Charakter jünger als 90 Tage (Warnung).
  - **Cyno-Verdacht** — jung **und** kaum Kills (klassischer Cyno-Alt; hebt die
    Stufe, statt zu beruhigen).
  - **Mögl. Scanner** — viel Covert-Ops-Nutzung + niedrige Gefahr (nur Hinweis,
    ändert die Stufe nicht).
  - **Nicht aufgelöst** — Name/Daten fehlen → „nicht als sicher werten".
- **Zuletzt: <Schiffe>** — die zuletzt geflogenen Hulls, klickbar:
  - **grün = Kill** in diesem Schiff → öffnet die **Killmail des Opfers**.
  - **rot = Verlust** dieses Schiffs → öffnet **seine eigene Killmail** (Fitting).
- **zKill ↗** — öffnet die Charakterseite auf zKillboard.
- **aktiv vor Xd** — letzte Killmail-Aktivität, **nur der letzten 30 Tage**.
  Keine Aktivität in dem Zeitraum → „Keine Aktivität im letzten Monat".

*Wie die Daten entstehen:* Namen → ESI (IDs, Corp/Allianz, Char-Alter) →
zKillboard (Danger, Gang-Ratio, Schiffsklassen, letzte Killmails). Alles läuft
im Hintergrund; das Panel füllt sich Zeile für Zeile. Ergebnisse werden für die
Sitzung zwischengespeichert.

---

## 10. Tab „Log"
Zeitgestempeltes Protokoll: Alarme (mit Region & gesampelten Farben),
Kalibrierungen, Threat-Check-Ergebnisse, Fehler. Erste Anlaufstelle bei
Problemen.

**🔍 Debug** (in der Live-Bahn) schreibt einen Snapshot ins Log: Header-OCR roh
+ pro Zeile gesampelte Farbe, Status (friendly/threat/leer) und Messwerte —
zum Justieren von Tag-Schwelle/Toleranz.

---

## 11. Tipps & Fallstricke
- **Header/Haven eng um die Zahl ziehen** — Icons/Balken stören das OCR.
- **Popups weg von den Capture-Bereichen** (sonst Selbst-Alarm).
- **Multibox:** einen Client pinnen; ein Fenster scannen reicht (alle im selben
  System).
- **Bei Fehlalarmen:** Debug-Sample machen, dann Tag-Schwelle/Toleranz nach den
  `val`/`dist`-Werten justieren.

## 12. Was das Tool NICHT tut
Keine Eingaben in EVE, kein Memory-Reading, kein Botting. Es liest Bildschirm +
Zwischenablage (nur Namenslisten) und öffentliche APIs. Friendlies verlassen den
Rechner nie. Der API-Kontakt steckt nur in deiner lokalen Config, nicht im Code.
