# Mister Lee's magischer Intelligentheit-Helfer

Ein passives Desktop-Werkzeug für EVE Online. Es beobachtet den **Local-Chat**
deines laufenden EVE-Clients und schlägt **sofort Alarm, wenn ein
nicht-befreundeter Pilot auftaucht** — nicht erst, wenn er etwas schreibt.
Zusätzlich kann es beim Ratten/Havens den letzten Wave-Counter überwachen,
Dread/Titan- oder Faction-Spawns erkennen, und jeden verdächtigen Piloten per
Knopfdruck online nachschlagen (zKillboard, EVE-eigene Datenbank) — inklusive
**Waffen-Reichweite aus seinem letzten Kill** und einer **Cyno-Alt-Warnung**.
Ein **Kill-Radar** verfolgt zusätzlich Kills und deinen Intel-Kanal rund um
dein System und warnt, wenn sich jemand nachweislich nähert — bevor er im
Local steht.

**Wichtig — was das Tool NICHT tut:** Es klickt nichts, tippt nichts und
greift nie in das Spiel ein. Es macht nur **Screenshots eines kleinen
Bildschirmbereichs** und liest gelegentlich die Zwischenablage aus (nur wenn
du selbst per Strg+C etwas kopierst). Kein Memory-Reading, kein Botting —
regelkonform nach der EVE-EULA.

---

## Inhalt

1. [Das Grundprinzip](#1-das-grundprinzip)
2. [Installation](#2-installation-windows)
3. [Starten](#3-starten)
4. [Die Oberfläche](#4-die-oberfläche)
5. [Erste Einrichtung](#5-erste-einrichtung-schritt-für-schritt)
6. [Tab „Erfassung"](#6-tab-erfassung)
7. [Tab „Erkennung"](#7-tab-erkennung)
8. [Tab „Alarm & Haven"](#8-tab-alarm--haven)
9. [Letzte Welle & Spawn-Detektoren](#9-letzte-welle--spawn-detektoren)
10. [Tab „Threat-Check"](#10-tab-threat-check)
11. [Das Intel-Fenster im Detail](#11-das-intel-fenster-im-detail)
12. [Waffen-Range-Intel](#12-waffen-range-intel)
13. [Cyno-Verdacht](#13-cyno-verdacht)
14. [Kill-Radar & Intel-Kanal](#14-kill-radar--intel-kanal)
15. [Tab „Log"](#15-tab-log)
16. [Alarm-Popups richtig platzieren](#16-alarm-popups-richtig-platzieren)
17. [Konfigurationsdatei](#17-konfigurationsdatei)
18. [Tipps & bekannte Fallstricke](#18-tipps--bekannte-fallstricke)
19. [Für Entwickler](#19-für-entwickler)

---

## 1. Das Grundprinzip

Das Tool macht regelmäßig (mehrmals pro Sekunde) einen Screenshot deiner
**Local-Mitgliederliste** und wertet nur die **Pixel** darin aus — keine
Spieldaten, kein Zugriff auf den EVE-Prozess selbst.

Die Hostile-Erkennung läuft **zweistufig**, damit sie sowohl schnell als auch
zuverlässig ist:

- **Stufe 1 — Header-Zahl (schnell, fängt alles):** Ganz oben im Local steht
  die Anzahl der Piloten, z. B. „14". Das Tool liest diese Zahl per
  Texterkennung (OCR). Steigt sie, ist jemand Neues reingekommen — Alarm.
  Das fängt auch Piloten, die (noch) kein sichtbares Standing-Icon haben oder
  unterhalb der sichtbaren Liste stehen.
- **Stufe 2 — Icon-Farbe (genauer, sagt WER):** Für jede sichtbare
  Pilotenzeile liest das Tool die Farbe des kleinen Standing-Symbols ganz
  links und ordnet sie einer von drei Kategorien zu:
  - **leer** — da ist gar kein farbiges Symbol (der Platz ist zu dunkel) →
    kein Alarm. Das verhindert Fehlalarme durch leere Listenplätze.
  - **friendly** — die Farbe steht auf deiner selbst erstellten Whitelist
    (siehe [Kalibrierung](#7-tab-erkennung)) → kein Alarm.
  - **threat** — es gibt ein Symbol, aber seine Farbe ist **nicht** auf der
    Whitelist (z. B. Rot, Orange, Grau für neutral/hostile) → **Alarm**.

Beide Stufen ergänzen sich: Stufe 1 merkt sofort „da kam wer rein", Stufe 2
sagt dir, ob es ein Freund oder eine Bedrohung ist.

**Jedes Feature hat einen eigenen Ein/Aus-Schalter.** Du musst nicht alles
nutzen — z. B. kannst du nur die „Letzte Welle"-Überwachung laufen lassen,
ohne die Hostile-Erkennung einzurichten.

---

## 2. Installation (Windows)

```powershell
# 1. Python-Abhängigkeiten installieren
python -m pip install -r requirements.txt

# 2. Tesseract OCR installieren (einmalig, für die Zahlen-Erkennung):
#    https://github.com/UB-Mannheim/tesseract/wiki
#    Standard-Installationspfad: C:\Program Files\Tesseract-OCR\tesseract.exe
#    Liegt es woanders, trage den Pfad in der config.json unter
#    "tesseract_cmd" ein.
```

Tesseract ist ein kostenloses, separates Programm zum Lesen von Text aus
Bildern — das Tool selbst bringt keine Texterkennung mit. **Ohne Tesseract
läuft die App trotzdem**: Die Header-Zahlen-Erkennung (Stufe 1, Pocket-Counter
für „Letzte Welle") ist dann aus, die Icon-Farb-Erkennung (Stufe 2)
funktioniert weiterhin. Im Programm erscheint dann eine gelbe Warnung mit
Link zur Installation.

---

## 3. Starten

Drei Wege, vom einfachsten zum entwicklernächsten:

**Weg 1 — fertige .exe (kein Python nötig, empfohlen für die meisten):**
```powershell
.\build_exe.ps1
```
Ergebnis: `dist\Mister Lees magischer Intelligentheit-Helfer.exe`. Diese
Datei kannst du frei verschieben (z. B. auf den Desktop) und per
**Doppelklick** starten — kein Terminal, kein Python nötig. Tesseract bleibt
eine separate Installation (siehe oben), die .exe findet es automatisch. Das
App-Icon kommt aus `icon.ico` im Projektordner.

**Weg 2 — Doppelklick-Starter (wenn Python bereits installiert ist):**
`Flint Local Watcher.pyw` doppelklicken — startet ohne sichtbares
Konsolenfenster.

**Weg 3 — Terminal (für Entwicklung/Debugging):**
```powershell
python -m eve_localwatcher
```

---

## 4. Die Oberfläche

Die App nutzt ein **modernes dunkles Design** (Sun-Valley-Theme im
Windows-11-Stil, inklusive dunkler Titelleiste). Der **Fenstertitel zeigt
immer die Versionsnummer** an (z. B. „… — v2.0.0-beta.3"), damit du sofort
siehst, welchen Stand eine .exe hat. Sollte das Theme-Paket einmal fehlen,
startet die App trotzdem — dann nur im schlichten Standard-Look.

Oben im Fenster sitzt eine **permanente Statusleiste**, die immer sichtbar
bleibt, egal welcher Tab gerade offen ist:

- **Große Status-Bahn** — grau = gestoppt, grün = alles sicher, rot = Hostile
  im Local. Der eine Blick, der zählt.
- **Werte-Zeile** — die aktuellen Live-Messwerte (Anzahl Piloten, gesampelte
  Zeilen, erkannte Threats, ggf. Haven-Fortschritt).
- **▶ Start / ⏸ Stop** — startet bzw. stoppt die komplette Überwachung. Der
  Start-Knopf ist **gesperrt**, solange die nötige Einrichtung fehlt; eine
  Hinweiszeile zeigt an, was noch fehlt.
- **Alarm testen** — spielt Sound + Bildschirm-Overlay einmal probeweise ab.
- **🔍 Debug** — schreibt einen Diagnose-Schnappschuss ins Log (siehe
  [Tab „Log"](#15-tab-log)).
- **Baseline** — setzt die Referenzzahl für den Header-Count neu (nützlich
  nach manuellem Local-Wechsel).

Darunter liegt die eigentliche Einrichtung in **fünf Tabs**: *Erfassung*,
*Erkennung*, *Alarm & Haven*, *Threat-Check*, *Log*.

---

## 5. Erste Einrichtung (Schritt für Schritt)

1. **EVE im Fenstermodus** starten und die Local-Mitgliederliste sichtbar
   machen (feste Position, nicht ständig verschieben).
2. Tab **Erfassung** → im Dropdown **genau deinen Client auswählen** (voller
   Fenstertitel, z. B. „EVE - Charname"). Beim Multiboxing heißen mehrere
   Fenster gleich — ohne diese Auswahl würde das Tool dem jeweils obersten
   Fenster folgen und beim Client-Wechsel den falschen Bildschirm lesen.
3. **„Pilotenliste festlegen"** klicken → mit der Maus ein Rechteck über die
   komplette Memberliste ziehen (Icon-Spalte links **und** die Namen).
4. **„Header-Zahl festlegen"** klicken → ein Rechteck **nur um die Zahl**
   ziehen, ohne das kleine Personen-Icon davor — das würde die
   Texterkennung stören.
5. **Zeilen- & Icon-Layout** fein justieren (Details siehe
   [Tab „Erfassung"](#6-tab-erfassung)), bis jede Zeile korrekt getroffen wird.
6. In einem **ruhigen Moment** — nur eigene Alts und bekannte Freunde im
   Local — auf Tab **Erkennung**: **„Aktuelles Local als sicher merken"**
   klicken. Das merkt sich die aktuell sichtbaren Icon-Farben als
   „friendly".
7. **▶ Start** klicken.

---

## 6. Tab „Erfassung"

Hier legst du fest, **wo auf dem Bildschirm** das Tool hinschaut.

- **EVE-Fenster (Dropdown + ⟳-Knopf):** pinnt genau einen laufenden
  EVE-Client fest. ⟳ liest die Fensterliste neu ein (z. B. nach dem Starten
  eines weiteren Clients).
- **„fensterrelativ" (Häkchen):** speichert alle Bereiche relativ zur
  Position des EVE-Fensters, nicht als feste Bildschirmkoordinaten. Dadurch
  übersteht die Einrichtung ein Verschieben des Fensters — du musst nicht
  neu kalibrieren.
- **„Pilotenliste festlegen" / „Header-Zahl festlegen":** öffnen einen
  Vollbild-Auswahlmodus zum Rechteck-Ziehen. Die Koordinaten werden
  gespeichert und bei jedem Scan neu berechnet.
- **Zeilen- & Icon-Layout** (relativ zur Pilotenliste):
  - *Icon X-Offset / Icon Sample-Breite* — wo genau die schmale
    Standing-Icon-Spalte liegt. **Wichtig:** hier darf nur das Icon selbst
    getroffen werden, niemals der Zeilenhintergrund — eine gerade
    angeklickte Zeile ist rot/dunkel hinterlegt und würde sonst
    fälschlich als Bedrohung gelesen.
  - *Zeilenhöhe / Erste Zeile Y-Offset* — das Raster, mit dem jede
    Pilotenzeile gefunden wird. So einstellen, dass jede Zeile mittig
    getroffen wird.
  - *Max. sichtbare Zeilen* — eine Sicherheits-Obergrenze; die tatsächliche
    Zahl wird zusätzlich durch den Header-Count begrenzt.
  - *Name X-Offset / Name-Breite* — wo der Pilotenname als Text steht. Nur
    nötig, wenn du **Auto-Threat** nutzen willst (Namen automatisch per OCR
    lesen, siehe [Tab „Threat-Check"](#10-tab-threat-check)).

---

## 7. Tab „Erkennung"

Hier definierst du, was für Stufe 2 als „friendly" gilt.

- **„Aktuelles Local als sicher merken":** liest die Icon-Farben aller
  gerade sichtbaren Piloten und speichert sie als **Friendly-Whitelist**.
  Mach das nur in einem ruhigen Moment mit ausschließlich bekannten
  Piloten im Local — sonst lernt das Tool eine fremde Farbe versehentlich
  als sicher.
- **„Whitelist leeren":** löscht alle gelernten Farben, falls du neu
  anfangen willst.
- **Tag-Schwelle (Regler):** beantwortet die Frage „ist da überhaupt ein
  Icon?" — gemessen wird die Helligkeit der Farbe. Ist sie darunter, gilt
  der Platz als leer und löst **nie** Alarm aus. Eine Live-Vorschau zeigt
  dir, wie Beispielfarben eingestuft würden.
- **Toleranz (Regler):** beantwortet die Frage „gehört diese Icon-Farbe zu
  meinen Freunden?" — gemessen wird der Farbabstand zur Whitelist. Zu
  niedrig eingestellt: schon kleine Farbschwankungen deiner eigenen Icons
  lösen Fehlalarme aus. Zu hoch eingestellt: fremde, ähnliche Farben
  rutschen als „friendly" durch. Auch hier gibt es eine Live-Vorschau.

---

## 8. Tab „Alarm & Haven"

**Oben — der Haupt-Hostile-Alarm:**

- **„Hostile-Local-Alarm aktiv" (Schalter):** schaltet die komplette
  Hostile-Erkennung (Stufe 1 + 2) an oder aus. Ist er aus, laufen andere
  Module wie „Letzte Welle" oder Threat-Check trotzdem unabhängig weiter.
- **Intervall (ms):** Wartezeit zwischen zwei Scans. Kleiner = schnellere
  Reaktion, aber etwas mehr Prozessorlast.
- **Sound + Lautstärke:** eigene WAV-Datei für diesen Alarm (leer = ein
  einfacher System-Piepton), Regler 0–100 %.
- **Auto-Learn (Standardmäßig aus, mit Bedacht nutzen):** lernt eine fremde
  Icon-Farbe automatisch als sicher, wenn sie X Sekunden lang präsent
  bleibt. Das ist praktisch bei ruhigem Nullsec-Verkehr, aber riskant: ein
  Hostile, der sich einfach nur ruhig verhält, würde nach der eingestellten
  Zeit fälschlich als „friendly" gelernt.
- **„Hostile-Popup platzieren":** legt fest, wo das Alarm-Overlay auf dem
  Bildschirm erscheint (siehe [Abschnitt 16](#16-alarm-popups-richtig-platzieren)).

Darunter folgen die Blöcke für **Letzte Welle** und die beiden
**Spawn-Detektoren** — siehe nächster Abschnitt.

---

## 9. Letzte Welle & Spawn-Detektoren

Diese drei Module gehören zusammen und sind für das **Ratten in Havens**
gedacht (mehrere „Pockets"/Wellen, in der letzten kann etwas Gefährliches
spawnen). Jedes hat einen **eigenen Sound, eigenen Lautstärke-Regler und ein
eigenes, frei verschiebbares Bildschirm-Overlay**.

### 9.1 „Letzte Welle" (Pocket-Counter)

Ratting-Sites zeigen meist einen Zähler wie `4/6` — aktuelle Pocket /
Gesamtzahl. Dieses Modul liest diesen Zähler und meldet, sobald die letzte
Pocket erreicht ist: *„Letzte Welle — danach neue Site anfliegen."*

- **aktivieren**, dann **„Counter-Bereich festlegen"** → ein Rechteck **nur
  um die Zahl** `N/M` ziehen, den grünen Fortschrittsbalken daneben
  weglassen (der stört die Texterkennung).
- **„Max. Pockets"** (Standard 6) ist eine Plausibilitätsgrenze: liest das
  Tool einen unpassenden Wert (z. B. eine andere Gesamtzahl als erwartet,
  oder `N` größer als `M`), wird das als OCR-Fehler verworfen — das
  passiert typischerweise bei einem schnellen Kameraschwenk.
- Zusätzlich wird nur ein **plausibler nächster Wert** akzeptiert: derselbe
  Stand, +1, oder ein Rücksprung auf 1 (neue Site). Ein kurzer Ausreißer
  durch einen Kameraschwenk (z. B. `3 → 6 → 4`) wird ignoriert.
- Der Alarm feuert **einmal**, sobald die letzte Pocket erreicht ist. Fällt
  der Zähler wieder (z. B. weil eine neue Site angeflogen wurde), wird der
  Alarm für die nächste letzte Welle neu scharf geschaltet.

### 9.2 Spawn-Detektoren (Dread/Titan, Faction-Battleship)

Für diese beiden Module brauchst du in EVE **zwei eigene, gefilterte
Overview-Fenster**: eines zeigt nur Dreadnoughts/Titanen, das andere nur
Faction-Battleships. Jeder Detektor beobachtet sein zugehöriges
Overview-Rechteck und schlägt Alarm, **sobald darin etwas Neues auftaucht**.

**Wie die Erkennung funktioniert (wichtig zu verstehen):** Ein „leeres"
gefiltertes Overview ist optisch nicht komplett dunkel — es steht z. B.
„Nothing Found" oder es sind Spaltenüberschriften zu sehen. Das Tool merkt
sich deshalb laufend, wie dieser **Leerzustand genau aussieht** (solange
gerade keine letzte Welle läuft), und vergleicht während der letzten Welle
jeden neuen Screenshot damit. Taucht eine NPC-Zeile auf, ändert sich das
Bild gegenüber diesem gelernten Leerzustand deutlich → Alarm. Verschwindet
der Spawn wieder (z. B. weil er zerstört wurde), entspricht das Overview
wieder dem Leerzustand und der Detektor ist für den nächsten Spawn neu
scharf.

- Je Block **aktivieren**, dann **„Overview-Bereich festlegen"** → ein
  Rechteck über den Zeilenbereich des gefilterten Overviews ziehen
  (Spaltenüberschriften und „Nothing Found" dürfen mit im Rechteck sein,
  das stört nicht mehr).
- **Während einer Site das Overview-Fenster nicht verschieben, in der
  Größe ändern oder umfiltern** — jede solche optische Änderung würde als
  Spawn gewertet werden.
- **Nur während der letzten Welle scharf:** Beide Detektoren werten erst,
  sobald der Pocket-Counter (siehe oben) die letzte Pocket erreicht hat —
  sie brauchen also das aktive „Letzte Welle"-Modul. Ist der Counter
  mittendrin kurz nicht lesbar (Kamera-Schwenk, Verdeckung durch ein
  Fenster), bleiben die Detektoren bis zu **rund 60 Sekunden** trotzdem
  scharf, damit ein kurzer Aussetzer sie nicht versehentlich deaktiviert.
  Ein frischer Counter (z. B. `1/6`, neue Site) beendet die letzte Welle
  dagegen sofort.
- **„Erkennung testen"-Knopf:** liest den Overview-Bereich sofort einmal
  aus. Läuft der Scan gerade, wird gegen den gelernten Leerzustand
  verglichen und du siehst direkt im Log, ob der Bereich als „belegt"
  gelten würde — zum Ausprobieren einfach kurz den Ingame-Filter
  herausnehmen, damit etwas im Overview steht.
- **Live-Diagnose in der Statuszeile:** solange ein Detektor aktiv ist,
  zeigt die Werte-Zeile laufend seinen Messwert — außerhalb der letzten
  Welle die Zahl heller Bildpunkte (zum Prüfen, ob der Bereich überhaupt
  richtig sitzt), während der letzten Welle mit einem `Δ` davor die Zahl
  der gegenüber dem Leerzustand veränderten Bildpunkte — genau das, was
  den Alarm auslöst.

Alle drei Module laufen im selben Hintergrund-Scan wie die Hostile-
Erkennung; mehrere Alarme können gleichzeitig als gestapelte Overlays
erscheinen.

---

## 10. Tab „Threat-Check"

Bewertet einzelne Piloten automatisch anhand öffentlicher Daten — ähnlich
wie bekannte Community-Tools, aber direkt im Spiel-Overlay nutzbar.

- **„aktiviert (Netzwerk)":** schaltet die Online-Abfragen überhaupt erst
  ein. Ohne diesen Schalter passiert hier nichts.
- **„EVE-SSO Login":** ein einmaliges Login über die **offizielle
  EVE-Anmeldeseite** im Browser (kein Passwort wird je von diesem Tool
  gesehen). Damit erkennt das Tool zuverlässig deine eigene Corp, Allianz
  und aktuelle Flotte, um Freunde von der Bewertung auszuschließen. Danach
  merkt sich das Tool ein Anmelde-Token — du musst dich nicht erneut
  einloggen.
- **API-Kontakt (optional):** ein Name oder eine Kontaktmöglichkeit, die
  bei Abfragen an zKillboard mitgeschickt wird (dortige Höflichkeitsregel
  für automatisierte Zugriffe). Muss keine E-Mail-Adresse sein, darf leer
  bleiben, verlässt nie deinen Rechner außer als Teil der Abfrage selbst.
- **„Local aus Zwischenablage prüfen":** der zuverlässigste Weg, eine ganze
  Local-Liste zu bewerten. In EVE in der Mitgliederliste **Strg+A, dann
  Strg+C** drücken, danach diesen Knopf klicken. Das Tool liest die
  kopierten Namen exakt aus der Zwischenablage — kein OCR-Fehler möglich,
  alle Piloten werden erfasst.
- **„Zwischenablage auto-überwachen":** sobald du irgendwann eine
  Local-Namensliste kopierst, startet die Bewertung automatisch, ohne dass
  du extra klicken musst.
- **„Auto-Threat: bei Neut Namen per OCR prüfen":** der vollautomatische
  Weg. Sobald ein nicht-befreundeter Pilot im Local erscheint, liest der
  Scanner dessen Namen direkt vom Bildschirm per Texterkennung und startet
  die Bewertung von selbst — ganz ohne Zwischenablage. Dafür müssen im Tab
  *Erfassung* „Name X-Offset" und „Name-Breite" korrekt eingestellt sein.
  Texterkennung ist fehleranfälliger als die Zwischenablage: nicht lesbare
  Namen erscheinen als „nicht aufgelöst" statt als falscher Name.

**Wer wird automatisch ausgeblendet?** Deine eigene Corp und Allianz (aus
deinem SSO-Login) sowie deine aktuelle Fleet werden **nie** online
abgefragt oder im Ergebnisfenster angezeigt — nur echte Fremde landen in
der Bewertung. Zusätzlich lassen sich manuelle Listen für „immer als
Freund behandeln" hinterlegen.

---

## 11. Das Intel-Fenster im Detail

Die Ergebnisse des Threat-Checks erscheinen in einem eigenen, frei
verschiebbaren Fenster — pro bewertetem Piloten eine Zeile, automatisch
nach Gefahr sortiert.

**Die Kopfzeile** fasst alles zusammen, z. B. „7 nicht-blau · 3 gefährlich
· 1 Hunter · 1 Cyno? · 1 frisch · 6/7 geprüft". Die Abdeckungszahl
(„6/7 geprüft") wird bewusst immer angezeigt: Solange nicht jeder Pilot
vollständig ausgewertet werden konnte, gilt bewusst **nichts** automatisch
als „sicher".

**Pro Pilotenzeile siehst du:**

- **Farbiger Balken links** — Gesamteinstufung: rot = hohe Gefahr, bernstein
  = mittel, grün = niedrig, grau = unbekannt (zu wenig Daten).
- **Name, Corporation, Allianz.**
- **Farbige Info-Chips**, je nach Datenlage:
  - **Danger N** — ein Wert von 0–100 von zKillboard, wie „gefährlich" der
    Pilot in seinen bisherigen Kämpfen war.
  - **Gang N% · Solo N%** — fliegt er meist in der Gruppe oder allein?
  - **Hunter** — viele Kills in typischen Jäger-Schiffen (getarnte
    Aufklärer, Recon, Interdictor, Black-Ops, Tactical-Destroyer).
  - **Frischer Char · Nd** — der Charakter ist jünger als die eingestellte
    Schwelle (Standard 90 Tage) — ein Warnhinweis, kein Beweis.
  - **CYNO?** — das Profil eines typischen Cyno-Alts, siehe
    [Abschnitt 13](#13-cyno-verdacht).
  - **Mögl. Scanner** — viel Nutzung von Aufklärungsschiffen bei geringer
    Gefahreneinstufung — reiner Hinweis, ändert die Gesamtwertung nicht.
  - **⚔ Waffenname ~N km** — siehe [Abschnitt 12](#12-waffen-range-intel).
  - **Nicht aufgelöst** — für diesen Namen konnten keine Daten gefunden
    werden (z. B. Tippfehler bei der OCR) — wird bewusst **nicht** als
    „sicher" behandelt.
- **„Zuletzt: …"** — die zuletzt geflogenen Schiffe, jeweils anklickbar:
  grün = ein **Kill** in diesem Schiff (Klick öffnet die Killmail des
  Opfers), rot = ein **Verlust** dieses Schiffs (Klick öffnet die eigene
  Killmail, zeigt sein Fitting).
- **„zKill ↗"** — öffnet die Charakterseite auf zKillboard im Browser.
- **„aktiv vor Nd"** — wann die letzte Killmail-Aktivität war, nur für die
  letzten 30 Tage angezeigt. Keine Aktivität in dieser Zeit → „Keine
  Aktivität im letzten Monat".

**Fenster-Einstellungen** (Frame *Intel-Fenster* im Tab *Threat-Check*):

- **„Immer oben"** — hält das Fenster über dem EVE-Client, statt dass es
  dahinter verschwindet.
- **Transparenz-Regler** — von 20 % bis 100 % Deckkraft.
- **„Klick-durch"** — Mausklicks gehen durch das Fenster hindurch ins
  Spiel. Praktisch als reines Overlay, aber dann sind die zKill-Links
  nicht mehr anklickbar — zum Bedienen oder Verschieben wieder ausschalten.
- **Verschieben** — an der Kopfzeile des Fensters ziehen; die Position wird
  gespeichert und bleibt auch nach einem Neustart erhalten.
- Bei einem neuen Threat-Check wird der Inhalt zurückgesetzt, das Fenster
  bleibt aber an seiner gespeicherten Position offen.

---

## 12. Waffen-Range-Intel

Hatte ein bewerteter Pilot **innerhalb der letzten 2 Stunden** einen
bestätigten Kill, zeigt seine Zeile im Intel-Fenster zusätzlich einen
violetten Chip mit dem dabei benutzten Waffensystem und dessen
**maximal möglicher Reichweite**, zum Beispiel:

> ⚔ Heavy Beam Laser II ~74 km (+10 km Falloff)

Das beantwortet die Frage „wie weit weg muss ich mindestens bleiben, wenn
der auf mich zielt?". Die Reichweite wird bewusst als **ungünstigster
Fall** berechnet, damit du dich nicht in falscher Sicherheit wiegst:

- Es wird angenommen, dass die **reichweitenstärkste verfügbare Munition**
  geladen ist (z. B. Aurora-Kristalle bei Beam-Lasern) — eine Killmail
  verrät nicht, welche Munition wirklich geladen war.
- Es wird angenommen, dass alle relevanten Fähigkeiten des Piloten auf dem
  **höchstmöglichen Stand (Level V)** trainiert sind.
- Reichweitenboni der geflogenen **Schiffshülle** werden eingerechnet —
  **ohne** zusätzliche Ausrüstung wie Module, Rigs oder Booster, da diese
  aus der Killmail nicht ersichtlich sind.

Abgedeckt sind **Geschütze** (Optimalreichweite + Falloff) und
**Raketenwerfer** (Reichweite = Fluggeschwindigkeit × Flugzeit der
Rakete). Bei Drohnen, Smartbombs oder ähnlichen Sonderfällen wird nur der
Waffenname ohne Reichweite angezeigt.

Für diese Berechnung ist **keine zusätzliche Internetabfrage** nötig — alle
nötigen Daten (Killmail-Details) sind ohnehin bereits Teil der normalen
Threat-Check-Abfrage. Die Grundwerte zu Waffen und Schiffen stammen aus
einer mitgelieferten Tabelle, die aus der öffentlichen EVE-Datenbank
erzeugt wurde (für Entwickler: `python tools/gen_weapon_ranges.py`
regeneriert sie nach einem Spiel-Update).

---

## 13. Cyno-Verdacht

Ein „Cyno-Alt" ist ein Charakter, der hauptsächlich dafür existiert, ein
Sprungfeuer (Cynosural Field) zu zünden und damit gegnerischen Kapitalschiffen
den Weg zu öffnen — oft unauffällig, bis es zu spät ist. Der Threat-Check
markiert Piloten mit einem typischen Cyno-Alt-Profil mit einem auffälligen,
**roten `CYNO?`-Chip**. **Sobald eines** der folgenden Muster zutrifft, wird
der Chip gesetzt:

1. **Junger Charakter mit fast keinen Kills** — jünger als die eingestellte
   „Frischer Char"-Schwelle (Standard 90 Tage) und kaum Kämpfe auf dem
   Killboard. Klassisches Bild eines frisch erstellten Wegwerf-Alts.
2. **Alter Charakter mit leerem Killboard, aber in einer Allianz** — älter
   als ein Jahr (einstellbar), fast keine Kills, sitzt aber trotzdem in
   einer Allianz. Das ist das Bild eines gezielt hochtrainierten, geparkten
   Alts, der monate- oder jahrelang „schläft" und nur für den einen Zünd-
   Moment aktiviert wird.
3. **Mehrfach mit gefittetem Cyno gestorben** — unter den letzten ~30
   Verlusten hatten **mindestens 5** tatsächlich ein Cynosural-Field-Modul
   im Fitting. Härtester Beweis: Der Char hat nachweislich wiederholt einen
   Cyno geflogen.
4. **Fliegt überwiegend cyno-fähige Schiffe** — **mehr als 5** der letzten
   ~30 gezeigten Schiffe sind Hüllen, die überhaupt einen Cyno tragen können
   (Force Recon, Black Ops, Covert Ops, Stealth Bomber, HIC, Strategic
   Cruiser, Blockade Runner, Deep Space Transport, Hauler). Welche Schiffe
   „cyno-fähig" sind, wird direkt aus den EVE-Spieldaten abgeleitet.

Ein Cyno-Verdacht hebt die Gesamteinstufung des Piloten automatisch auf
mindestens „mittel" an — er wird also nie als harmlos dargestellt, nur weil
sonst nichts Auffälliges vorliegt. Der Chip-Tooltip nennt den konkreten
Grund; die Kopfzeile des Intel-Fensters zählt die Verdachtsfälle mit.

Alle Schwellen (Kill-/Altersgrenzen, die 5 Cyno-Verluste, die >5 cyno-fähigen
Schiffe, die Scan-Tiefe von 30 Killmails) lassen sich über die
Konfigurationsdatei anpassen, siehe [Abschnitt 17](#17-konfigurationsdatei).

---

## 14. Kill-Radar & Intel-Kanal

Das Radar macht das Tool **vorausschauend**: Statt erst zu warnen, wenn ein
Feind im Local steht, beobachtet es, was **rund um dein System** passiert —
über zwei automatische Quellen plus deine manuellen Checks, zusammengeführt
in einer **Piloten-Historie** im Intel-Fenster.

**Quelle 1 — Live-Kills (Tag `#zkill`):** Das Tool verfolgt den weltweiten
Killmail-Livestream von zKillboard. Passiert ein Kill innerhalb deines
eingestellten **Jump-Radius** (1–8 Sprünge um dein System), werden die
beteiligten Angreifer automatisch ausgewertet — inklusive Waffen-Reichweite
und Cyno-Verdacht — und erscheinen als Karte im Intel-Fenster. Eine
Roaming-Gang hinterlässt fast immer eine Spur aus Kills auf dem Weg zu dir;
so siehst du sie kommen, bevor sie da ist. (Reine NPC-Kills, deine eigenen
Kills und Friendlies werden übersprungen; pro Kill werden maximal die
5 relevantesten Angreifer ausgewertet.)

**Quelle 2 — dein Intel-Kanal (Tag `#intel`):** Trage den exakten Namen
deines Ingame-Intel-Channels ein (z. B. „OnlyQuerious. Intel"). Das Tool
liest die Chat-Logdatei des Kanals live mit (EVE schreibt sie automatisch
auf die Festplatte — auch das ist rein passiv). Meldet jemand ein System
innerhalb deines Radius, werden die genannten Piloten ausgewertet; Systeme
außerhalb werden ignoriert. Auch Kurzformen wie „P-Z" funktionieren, weil
nur gegen die Systeme deiner Umgebung abgeglichen wird.

**Quelle 3 — manuelle Checks (Tag `#manuell`):** Alles, was du per
Zwischenablage oder Auto-Threat prüfst, reiht sich in dieselbe Historie ein.
Übrigens: Es reicht jetzt auch, einen **einzelnen Pilotennamen** zu kopieren
und „Local aus Zwischenablage prüfen" zu klicken.

**Die Historie:** Im Intel-Fenster gibt es **eine Karte pro Pilot**, sortiert
nach der neuesten Aktivität. Jede Karte zeigt die bekannte Bewertung (Danger,
Hunter, CYNO?, Waffen-Range …), die Herkunfts-Tags und den
**Sichtungs-Verlauf**, z. B. „8QT-H4 (2 J) vor 3 min ← V-3YG7 (4 J) vor
8 min" — du siehst also wörtlich, wie sich jemand bewegt.

**Die Anflug-Warnung:** Liegen von einem Piloten **mindestens zwei
Sichtungen aus verschiedenen Systemen** vor und **sinkt** dabei seine
Jump-Distanz zu dir, feuert ein separater Alarm („⚠ ANFLUG: Name · 3 → 2
Jumps · Sabre") mit eigenem Sound, eigener Lautstärke und eigenem
verschiebbarem Popup. Einmal gewarnt wird erst wieder gewarnt, wenn er noch
näher kommt; dreht er ab, wird die Warnung neu scharf. Ein Pilot, der
zweimal im selben System gemeldet wird, ist ein Camper — keine Anflug-Warnung.

**Dein eigenes System** bestimmst du auf zwei Arten (Frame *Kill-Radar &
Intel-Kanal* im Tab *Threat-Check*):

- **Manuell eintragen** (z. B. „K7D-II") — gilt immer, ideal für stationäres
  Ratten. Das Feld prüft live, ob der Name existiert.
- **„Standort per SSO folgen"** — das Tool fragt deine Position alle paar
  Sekunden über die offizielle EVE-API ab und zieht die Radar-Blase
  automatisch mit, wenn du jumpst. Dafür braucht es eine zusätzliche
  Berechtigung (Standort lesen): einmal neu über **EVE-SSO Login** anmelden,
  falls das Tool darauf hinweist.

Das Radar startet und stoppt mit dem **▶ Start**-Knopf wie alle anderen
Module — braucht aber **keine** Bildschirm-Einrichtung: Du kannst es auch
als einziges Feature laufen lassen. Alle Abfragen sind lesend und halten
sich an die Etikette-Regeln der zKillboard-API.

---

## 15. Tab „Log"

Ein zeitgestempeltes Protokoll aller wichtigen Ereignisse: ausgelöste
Alarme (inkl. betroffenem Bereich und gesampelter Farbe), Kalibrierungen,
Threat-Check-Ergebnisse, Fehler. Die erste Anlaufstelle, wenn etwas nicht
wie erwartet funktioniert.

Der **🔍 Debug**-Knopf in der oberen Statusleiste schreibt einen
vollständigen Diagnose-Schnappschuss ins Log: die roh gelesene Header-Zahl,
sowie pro Zeile die gesampelte Farbe, ihre Einstufung (friendly/threat/leer)
und die genauen Messwerte. Damit lässt sich die Tag-Schwelle bzw. Toleranz
im Tab *Erkennung* gezielt nachjustieren.

---

## 16. Alarm-Popups richtig platzieren

Die Bildschirmerfassung liest **Bildschirm-Pixel**. Legt sich ein
Alarm-Popup zufällig über einen der Capture-Bereiche, liest der nächste Scan
das Popup selbst und löst dadurch erneut Alarm aus — ein Rückkopplungs-
Effekt. Deshalb müssen alle Popups **außerhalb** der überwachten Bereiche
liegen (am besten auf einem zweiten Monitor, falls vorhanden):

- Über den jeweiligen „Popup platzieren"-Knopf (Hostile-Alarm, Letzte Welle,
  Dread/Titan, Faction) erscheint das Popup probeweise.
- Mit der Maus an die gewünschte Stelle **ziehen**.
- **Doppelklick** speichert die Position dauerhaft (pro angeschlossenem
  Monitor getrennt, übersteht einen Neustart der App).
- Ohne gespeicherte Position erscheinen alle vier Popup-Arten
  standardmäßig oben-mittig, gestapelt übereinander.

---

## 17. Konfigurationsdatei

Alle Einstellungen werden automatisch unter
`%USERPROFILE%\.eve_localwatcher\config.json` gespeichert — du musst diese
Datei normalerweise nie von Hand bearbeiten, das Tool schreibt sie bei jeder
Änderung automatisch. `config.example.json` im Projektordner zeigt alle
möglichen Felder mit Beispielwerten. Für alle, die doch mal direkt
nachschauen oder anpassen möchten, hier die wichtigsten Felder:

| Feld | Bedeutung |
|---|---|
| `capture_region`, `header_region` | Überwachte Bereiche, relativ zum EVE-Fenster gespeichert |
| `icon_column_x_offset`, `icon_sample_width` | Position der Icon-Spalte |
| `row_height`, `first_row_y_offset` | Zeilenraster der Pilotenliste |
| `friendly_colors[]` | Die per Kalibrierung gelernte Whitelist |
| `color_tolerance` | Toleranz-Regler-Wert (Standard 18). Zu niedrig → Fehlalarme durch eigene Farbschwankungen |
| `tag_min_value` | Tag-Schwellen-Wert (Standard 70). Darunter gilt ein Platz als „leer", nie Alarm |
| `scan_interval_ms` | Wartezeit zwischen zwei Scans in Millisekunden (Standard 750) |
| `alarm_sound_path`, `alarm_volume` | Sound-Datei und Lautstärke (0–100) des Hostile-Alarms |
| `haven_*`, `dread_*`, `faction_*` | Bereich/Sound/Lautstärke je Modul (Letzte Welle, Dread/Titan, Faction) |
| `haven_expected_total` | Erwartete Anzahl Pockets (Standard 6) — Plausibilitätsprüfung |
| `spawn_brightness_thr`, `spawn_min_bright_px` | Empfindlichkeit der Spawn-Erkennung (siehe Abschnitt 9.2) |
| `intel_*` | Position, Transparenz, „Immer oben", „Klick-durch" des Intel-Fensters |
| `cyno_max_kills`, `cyno_min_age_days` | Cyno-Verdacht Alter/Kills (Standard: 5 Kills, 365 Tage) |
| `cyno_scan_depth`, `cyno_fitted_min_losses`, `cyno_capable_min_ships` | Cyno-Killboard-Beweise: wie viele Killmails gescannt werden (30), ab wie vielen Cyno-Verlusten (5) bzw. cyno-fähigen Schiffen (6) der Tag gesetzt wird |
| `radar_*` | Kill-Radar: `radar_jump_range` (1–8), `radar_own_system`, `radar_follow_location`, `radar_intel_channel`, Sound/Lautstärke der Anflug-Warnung, Historien-Limits |
| `auto_learn_enabled` | Standardmäßig **aus** — siehe Warnhinweis in Abschnitt 8 |

---

## 18. Tipps & bekannte Fallstricke

- **Header- und Counter-Bereiche eng um die reine Zahl ziehen** — Icons oder
  Fortschrittsbalken im selben Rechteck stören die Texterkennung.
- **Popups immer außerhalb der überwachten Bereiche platzieren** (siehe
  Abschnitt 15) — sonst löst sich das Tool selbst aus.
- **Beim Multiboxing** reicht es, einen Client zu pinnen — solange alle
  Accounts im selben System sind, siehst du dieselbe Local-Liste.
- **Bei Fehlalarmen:** einen 🔍-Debug-Schnappschuss machen und anhand der
  darin angezeigten Mess- und Abstandswerte die Tag-Schwelle bzw. Toleranz
  im Tab *Erkennung* nachjustieren.
- **Overview-Fenster für die Spawn-Detektoren** während einer aktiven Site
  nicht verschieben, in der Größe ändern oder umfiltern.
- **DPI-Skalierung von Windows** wird automatisch berücksichtigt — die
  Bildschirmauswahl und die eigentliche Erfassung sollten also auch bei
  Skalierung ≠ 100 % zueinander passen.

---

## 19. Für Entwickler

<details>
<summary>Projektstruktur, Module, Tests (aufklappen)</summary>

```
eve_localwatcher/
  __main__.py      # Einstieg: DPI-aware + App starten
  app.py           # Tkinter-Control-Panel + Alarm-Overlay + Intel-Fenster (Main-Thread)
  scanner.py       # Scan-Loop: Hostile-Erkennung, Haven/Letzte-Welle, Spawn-Detektoren (Worker-Thread)
  capture.py       # mss-Screen-Capture
  color.py         # HSV-Feature-Distanz + Friendly-Klassifizierung
  ocr.py           # Texterkennung via Tesseract (mit Fallback ohne Tesseract)
  localparse.py    # Parsen einer kopierten Local-Mitgliederliste in saubere Namen
  region_select.py # Vollbild-Rechteck-Auswahl
  winutil.py       # DPI, Fenstersuche, Virtual-Screen (Win32)
  config.py        # Config-Datenmodell + JSON-Persistenz
  alarm.py         # Akustischer Alarm mit Lautstärkeregelung (WAV-Skalierung + winsound)
  esi.py           # Minimaler EVE-ESI-Client (Namen↔IDs, Affiliation, Killmails, Fleet)
  zkill.py         # zKillboard-Client (Stats, letzte Killmails), gedrosselt + gecacht
  threat.py        # Bewertungslogik: ThreatProfile, Flags (Hunter/Fresh/Cyno/Scanner), Tier
  threatcheck.py   # Orchestriert Namen → ESI → zKillboard → ThreatProfile
  weaponrange.py   # Läuft zur Laufzeit: Waffenreichweite aus der gebündelten Datentabelle
  mapdata.py       # Systemgraph (BFS-Jump-Distanzen, Bubble, Namensauflösung)
  killfeed.py      # zKillboard-Livefeed (R2Z2, sequenzbasiert, ratenkonform)
  chatlog.py       # EVE-Chatlog-Discovery (OneDrive-aware) + UTF-16-Tailing
  intelparse.py    # Intel-Zeilen-Parser (System in Bubble + Pilot-Kandidaten)
  radar.py         # Kill-Radar-Orchestrator (Threads, Sichtungen, Anflug-Logik)
  friendly.py      # Baut das Friendly-Set aus SSO-Affiliation + aktueller Fleet
  sso.py           # EVE-SSO-Login (OAuth2/PKCE)
  ui_tooltip.py     # Hover-Tooltip-Widget

tools/
  gen_weapon_ranges.py   # Erzeugt data/weapon_ranges.json aus dem EVE-SDE (dev-only)
  gen_map_graph.py       # Erzeugt data/map_graph.json (Systemgraph) aus dem SDE

tests/            # pytest-Suite (Range-Mathematik, Cyno-Trigger, Spawn-Detektoren, ...)
```

Tests laufen mit `python -m pytest tests/ -q`.

Threading-Modell: Der `Scanner` läuft auf einem Hintergrund-Thread und rührt
nie direkt an Tk-Widgets; er meldet Ergebnisse über eine `queue.Queue`, die
der Tk-Main-Thread per `root.after(...)` abpumpt. Netzwerk-Abfragen (Threat-
Check, SSO) folgen demselben Muster über einen eigenen Hintergrund-Thread.

</details>
