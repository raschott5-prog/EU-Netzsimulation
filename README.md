# MERIDIAN Grid — EU-weiter Netzsimulator

DC-Lastfluss über **40 Gebotszonen** in allen vier europäischen Synchronzonen
(Kontinentaleuropa inkl. Baltikum, Nordic, GB, Irland), 62 AC-Kuppelleitungen
+ 21 HVDC-Kabel — gespeist aus ENTSO-E-Realdaten (A75/A65) und **kalibriert
gegen gemessene Grenzflüsse (A11)**: Flüsse, Suszeptanzen und Leitungslimits.

**Physik-Grundsatz (Nagelbrett-Prinzip):** AC-Leitungen führen den Fluss,
den Kirchhoff diktiert — niemand steuert ihn. HVDC-Kabel sind der "Draht
mit Schalter": es fließt der eingestellte Sollwert. Frequenzregelung endet
an der Synchronzonen-Grenze; zerfällt das Netz, regelt sich jede Insel
selbst. Interaktiv: Zonen-Erzeugung/-Last verschieben, Leitungen drosseln
oder kappen, HVDC-Sollwerte stellen, N-1-Stresstest — alles im Browser.

## Schnellstart lokal

```bash
git clone <dein-repo>
cd meridian-grid
pip install -r requirements.txt
cp .env.example .env          # ENTSO-E-Key eintragen (kostenlos, s.u.)

python3 meridian_grid_live.py --check   # EIC-Codes + A11 + Kalibrierung prüfen
python3 meridian_grid_live.py           # → http://localhost:5002/grid
```

Ohne Key läuft alles auf Modell-Defaults (sichtbar gekennzeichnet).
Key beantragen: Account auf transparency.entsoe.eu anlegen, dann E-Mail an
transparency@entsoe.eu mit Betreff "Restful API access".

## GitHub Pages: der Simulator läuft ohne Server

Der Workflow `.github/workflows/snapshot.yml` holt **alle 30 Minuten**
ENTSO-E-Daten, kalibriert und deployt ein statisches Bundle nach GitHub
Pages. Der Browser rechnet Schocks und N-1 lokal (der JS-Solver ist
numerisch identisch zur Python-Engine); nur der Ist-Zustand kommt aus dem
Snapshot. Einrichtung — drei Klicks:

1. **Secret anlegen:** Settings → Secrets and variables → Actions →
   *New repository secret* → Name `ENTSOE_KEY`, Wert = dein Key.
2. **Pages aktivieren:** Settings → Pages → Source: **GitHub Actions**.
3. **Ersten Lauf starten:** Actions-Tab → "Grid-Snapshot → GitHub Pages"
   → *Run workflow*.

Danach ist die Karte unter `https://<user>.github.io/<repo>/` öffentlich.
Liefert ENTSO-E zu wenig Daten, schlägt der Job absichtlich fehl und der
**letzte gute Snapshot bleibt online** (kein stiller Rückfall auf Defaults).
Hinweis: Öffentliche Pages setzen ein öffentliches Repo voraus (oder einen
bezahlten Plan); der Key bleibt dabei als Secret geheim — er steht
nirgendwo im Code, `.env` ist git-ignoriert.

Der zweite Workflow (`tests.yml`) lässt bei jedem Push alle vier
Testsuiten laufen — komplett gemockt, ohne Netzzugriff.

## Dateien

| Datei | Zweck |
|---|---|
| `meridian_grid.py` | Physik-Kern: Topologie, DC-Load-Flow, Szenario-Engine |
| `meridian_grid_live.py` | ENTSO-E-Anbindung + Flask-Endpoints |
| `snapshot.py` | Statisches Pages-Bundle (von Actions per Cron aufgerufen) |
| `meridian_grid_viz.html` | Interaktive Netzkarte (läuft auch standalone) |
| `test_grid_live.py` | Unit-Tests: XML-Parsing, Pumpspeicher, Ausrichtung |
| `test_e2e.py` | End-to-End mit gemocktem ENTSO-E |
| `test_realdata_regression.py` | Reproduziert real beobachtete ENTSO-E-Macken |
| `test_calibration.py` | A11-Kalibrierung rekonstruiert ein "wahres" Netz |

## Voraussetzungen

```bash
pip install numpy flask requests
```

## Ohne Server

```bash
python3 meridian_grid.py          # 3 Szenarien in der Konsole
open meridian_grid_viz.html       # Karte auf Modell-Defaults
```

## Integration in energy_trader_finale.py

Vor `app.run(...)` einfügen:

```python
import meridian_grid_live
meridian_grid_live.register(app, http=HTTP, auth=_auth)
meridian_grid_live.start_background_loop()
```

Danach unter `/grid` und `/api/grid` im bestehenden Terminal erreichbar
(Key kommt aus `.env` bzw. `$ENTSOE_KEY`).

## Tests

```bash
python3 test_grid_live.py            # Parsing, State, Endpoints
python3 test_e2e.py                  # kompletter Pfad mit Mock-API
python3 test_realdata_regression.py  # gegen real beobachtete Datenmacken
python3 test_calibration.py          # Kalibrierung gegen konstruierte Wahrheit
```

## API

`GET /api/grid` — Lastfluss auf aktuellem Live-Stand.
Optionale Schocks als JSON-Parameter:

```
/api/grid?shocks={"gen":{"FR":{"nuclear":-20000}}}
/api/grid?shocks={"load":{"PL":5000}}
/api/grid?shocks={"line":{"DE-AT":0.5}}
```

`POST /api/grid/refresh` — sofortiger Neuabruf.

## Zeitliche Ausrichtung

ENTSO-E veröffentlicht je Zone mit sehr unterschiedlichem Verzug — real
gemessen 38 bis 248 Minuten. Nimmt man pro Zone einfach "den letzten Wert",
rechnet man einen Lastfluss, in dem Zonen dreieinhalb Stunden auseinander
liegen. Deshalb:

1. Es werden **vollständige Zeitreihen** geholt, nicht nur der letzte Punkt.
2. Daraus wird **ein gemeinsamer Zielzeitpunkt** für alle Zonen bestimmt.
3. Jede Zone wird als **vollständiger Schnitt** übernommen — nie einzelne
   Erzeugungstypen separat vorgetragen, sonst entstehen Teilsummen mit
   Phantom-Defiziten (real beobachtet bei BE: 3,6 statt 8–11 GW, also ein
   scheinbarer Import von 5,9 GW, der physikalisch unmöglich ist).
4. Zonen, deren letzter vollständiger Schnitt weiter als `MAX_FILL_MIN`
   (240 min) zurückliegt, fallen sichtbar auf `default`.

`/api/grid` weist `target_ts` und `max_fill_min` aus; die Karte zeigt beides
in der Datenqualitäts-Zeile.

## A11-Kalibrierung

`--check` und jeder Refresh holen zusätzlich die **gemessenen** physischen
Grenzflüsse (A11) und heften das Modell daran fest:

1. **HVDC-Sollwerte** werden direkt aus der Messung übernommen (Kabel folgen
   dem Fahrplan, nicht Kirchhoff — die Messung *ist* der Sollwert).
2. **AC-Suszeptanzen** werden iterativ gefittet (gedämpft, mit Schranken
   0.25–4.0), bis die Modellverteilung der Messung entspricht.
3. **Bilanzkorrektur je Zone**: Differenz zwischen gemessener physischer
   Netto-Position und A75/A65-Bilanz. Inhaltlich = Kleinanlagen unter der
   Meldeschwelle + Austausch mit Nachbarn außerhalb des Modells +
   Regelleistung. Diese drei sind aus Flussmessungen mathematisch **nicht
   trennbar** — geführt und ausgewiesen wird ehrlich nur die Summe.

Ergebnis: Der Basiszustand reproduziert die Messung (im Selbsttest Ø 6 MW
Restfehler); Szenario-Schocks sind Deltas auf einem realitätsverankerten
Zustand. `/api/grid/calibration` zeigt den vollständigen Fit-Report.

## Bewusst nicht enthalten

UA/MD (Datenlage kriegsbedingt lückig), LU (in DE-LU enthalten), MT/CY
(Inselnetze), TR (außerhalb EU-Datenraum). GB liefert post-Brexit auf der
ENTSO-E-Plattform oft lückige Daten und läuft dann sichtbar auf Defaults —
im Verifikationslauf vom 23.07. bestätigt; ebenso MK (meldet nicht) und AL
(nur Last). Diese drei laufen ehrlich gekennzeichnet auf Modell-Defaults.

## Zeitliche Ausrichtung: MW-gewichtet

Realdaten-Lektion (Lauf 23.07., 11:26): kleine Erzeugungskategorien (Waste,
Geothermal, Marine …) melden mit stundenlangem Verzug. Eine Vollständigkeits-
regel, die TYPEN zählt, wirft deshalb den gemeinsamen Netzschnitt um Stunden
zurück (beobachtet: 8 h alt, frische Zonen fielen auf default, A11 fand 0/77
Grenzen). Die Regel ist daher MW-GEWICHTET: ein Schnitt gilt als vollständig,
wenn die fehlenden Typen zusammen < 5 % der typischen Zonen-Erzeugung liegen
(mind. 150 MW). Kleine Nachzügler werden einzeln begrenzt vorgetragen; ein
fehlender großer Typ (Kernkraft, Braunkohle) blockiert weiterhin — das ist
der Anti-Phantom-Schutz aus der BE-Lektion.

## Empirische Limit-Kalibrierung (NTC)

Der erste kalibrierte Realdaten-Lauf (23.07., 11:50) zeigte 234 % Auslastung
im Startzustand — physisch unmöglich. Diagnose: Nach der A11-Kalibrierung
sind die *Flüsse* echt; also waren die *Limits* falsch. Ein gemessener Fluss
über der angenommenen NTC **widerlegt die Annahme** (BG→RS: 1405 MW über
einer geratenen 600er-NTC). Deshalb: Für jede Grenze wird das Betrags-
Maximum des 12h-A11-Fensters bestimmt; liegt es über der Annahme, wird die
NTC auf Maximum × 1,10 angehoben — nie abgesenkt (eine kleine Messung
beweist nicht, dass eine Leitung wenig kann). Angehobene Limits sind in
`/api/grid/calibration` unter `ntc_raised` einsehbar.

## Netzfrequenz (simuliert) & EU-Strommix

Die Karte zeigt je Synchronzone — und je abgetrennter Insel — die
**quasistationäre Netzfrequenz** nach Primärregelung: Δf = −ΔP/λ, mit
λ_CE = 15 GW/Hz (ENTSO-E-Auslegung: 3 GW FCR für 200 mHz), Nordic 6,
GB 2,5, Irland 0,45 GW/Hz; Inseln erben λ anteilig an ihrer Erzeugung.
Referenz ist der ungestörte Zustand (die Daten-Restbilanz der Kalibrierung
ist ein Messartefakt, keine Frequenzabweichung — Start = 50,000 Hz).
Statusstufen entsprechen den realen Schutzschwellen (49,8 FCR-Grenze,
49,0 Lastabwurf, 47,5 Kollaps, 50,2 PV-Abschaltung, 51,5 Erzeugerschutz);
jenseits des Lastabwurfs rechnet das Modell ehrlich gekennzeichnet statisch
weiter. Lehrbeispiele: FR −3 GW = exakt −200 mHz (der Auslegungsfall);
NordLink kappen → CE sinkt, Nordic steigt (DC koppelt keine Frequenz!);
Baltikum-Inselung → Insel bei ~49,0 Hz, Rest-CE bei −21 mHz.

Der **EU-Strommix** aggregiert die Erzeugung aller 40 Zonen je Kategorie
(inkl. "nicht erfasst" aus der Kalibrierung) als Balken + Legende mit
GW, Anteil und Δ gegenüber dem ungestörten Zustand — er reagiert live
auf jeden Eingriff.

## Robustheit gegen ENTSO-E-Drosselung

Ein Refresh feuert ~250 Requests (80 Zonen + 166 A11-Richtungen) — nahe am
ENTSO-E-Limit von ~400/min. Realdaten-Lauf 15:01: A11 brach von 76 auf 33
Grenzen ein, und mit ihm kehrten Phantom-Overloads zurück, weil gelernte
Limits verworfen wurden. Deshalb gilt jetzt: **(1)** 429/5xx-Antworten
werden mit Backoff wiederholt und in `--check` als Statistik ausgewiesen,
**(2)** A11-Historie wird über Refreshes fortgeschrieben (ein Aussetzer
löscht keine Grenzen), **(3)** gelernte NTC-Limits und Fit-Faktoren sind
**persistent** — was eine Grenze nachweislich getragen hat, ist ein Fakt
und verfällt nicht, nur weil die Messung gerade klemmt. **(4)** auch der
Zonen-Fetcher hat Retry (Lauf 16:49: die Drosselung traf systematisch die
hinteren Zonen der festen Abrufreihenfolge — BG/RS), **(5)** die Abruf-
reihenfolge wird gemischt, sodass Drossel-Pech jeden Zyklus andere Zonen
trifft und sich über den Serien-Behalt selbst heilt, **(6)** A11-Messungen
werden bis 240 min vorgetragen (träge Balkan-TSOs) — ein 3 h alter
gemessener Fluss ist fürs Pinning besser als eine ungepinnte Zone. Ungepinnte
Zonen werden in Statuszeile, `--check` und `/api/grid/calibration` als
Verdächtige ausgewiesen. Hinweis: Läuft das alte Energy-Terminal (Port 5001)
parallel gegen dieselbe API, teilen sich beide das Request-Budget.

## Grenzen ohne A11 (GB-Kabel)

Realdaten-Lauf 12:15: Genau 7 Grenzen liefern kein A11 — die sieben
GB-Kabel (post-Brexit). Die frühere Alles-oder-nichts-Bilanzkorrektur ließ
dadurch FR/BE/NL/DK1/NO2/IE/GB ungepinnt; der Abgleichfehler entlud sich
konzentriert auf Norwegens Binnengrenzen ("194 % NO3–NO5"). Jetzt gehen
unbemessene **DC-Kabel mit ihrem Sollwert** in die Bilanz ein (ein Sollwert
ist im Modell ohnehin gesetzt); die Unsicherheit landet in der Zonen-
korrektur der Kabel-Endpunkte statt in fremden AC-Leitungen. Nur
unbemessene **AC-Grenzen** verhindern weiterhin das Pinning. Die Liste
steht in `/api/grid/calibration` unter `unmeasured_borders`; die Karte
zeigt Fit-Fehler und Anzahl in der Statuszeile.

## N-1-Stresstest

Button „N-1 Stresstest" (bzw. `GET /api/grid/n1`, optional mit
`?shocks=...`): kappt jede der 83 Verbindungen einzeln auf dem aktuellen
Zustand — inkl. aktiver Schocks und Kalibrierung — und bewertet:
Inselbildung (+1000), neue Overloads (+10 je), Anstieg der max. Auslastung.
„Kritisch" heißt nur strukturelle Folge (Insel oder neue Überlastung).
Parallele DC-Kabel derselben Grenze (GB–IE: EWIC + Moyle) fallen einzeln
aus. Im Default-Zustand ist der kritischste Einzelausfall FR–ES: Iberien
hängt AC ausschließlich an den Pyrenäen — die Konstellation des iberischen
Blackouts vom April 2025.

## Leitungsschocks und die Delta-Ansicht

Eine Drosselung skaliert **Suszeptanz UND NTC** gemeinsam: −50 % heißt
"einer von zwei Stromkreisen weg" — weniger Durchlass *und* weniger Limit,
die Auslastung des Rests steigt. (Ein früherer Fehler skalierte nur die
Suszeptanz; eine gedrosselte Leitung sah dadurch *gesünder* aus.)
A11-Kalibrierfaktoren betreffen dagegen nur die Suszeptanz, nie die NTC.

Dass das Kappen *einer* Leitung im vermaschten Netz meist undramatisch
bleibt, ist keine Schwäche, sondern das **N-1-Prinzip**: Netze sind so
gebaut, dass jeder einzelne Ausfall langweilig ist. Die Umverteilung
(±100–300 MW über viele Kanten, teils mit Richtungsumkehr) zeigt die
**Delta-Ansicht** — Fluss jetzt vs. Fluss ohne Eingriffe. Dramatisch wird
es erst, wenn der *einzige* Pfad fällt (PL–LT → Inselbildung) oder das
Netz bereits unter Stress steht.

## Grenzen des Modells

- **Absolute MW-Werte sind nicht belastbar.** Die Suszeptanzen sind
  Plausibilitätsannahmen, keine gemessenen Reaktanzen. Flussrichtungen und
  Umverteilungsmuster stimmen qualitativ, die genauen Megawatt nicht.
  Kalibrierung gegen ENTSO-E A11 (physikalische Grenzflüsse) ist der
  nächste Schritt, um das zu ändern.
- **Italien meldet mehrere Gebotszonen** unter der nationalen Domain. Nur
  Zeitpunkte mit vollständiger Teilzonen-Abdeckung werden verwendet — sonst
  ergeben sich 15 GW statt realistischer ~48 GW Last.
- **A75 erfasst nur meldepflichtige Anlagen** (i. d. R. > 100 MW). Kleine PV
  und dezentrale Erzeugung fehlen, die Erzeugung wird also systematisch
  unterschätzt.
- **Das Modell ist kein geschlossenes System.** Reale Flüsse nach GB,
  Skandinavien, Balkan, Ukraine und Marokko fehlen. Der Rest erscheint als
  `external_balance_mw` und wird vom verteilten Slack aufgefangen — er wird
  explizit ausgewiesen statt stillschweigend verteilt.
- **Zonen ohne Live-Daten** laufen sichtbar auf `source: default` (in der
  Karte gestrichelt umrandet). Halb-echte Netze werden nie als gemessen
  ausgegeben.

## Datenquelle & Lizenzhinweis

Alle Live-Daten: **ENTSO-E Transparency Platform** (transparency.entsoe.eu),
Nutzung gemäß deren Bedingungen mit Quellenangabe. Dieses Modell ist ein
Lehr-/Analysewerkzeug — zonale Näherung, keine Betriebsführungs-Software.
