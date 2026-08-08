# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Behoben — vier Befunde, die aus dem Aufzeichnen der Fixtures kamen

Jeder Payload dieser Suite war ein Literal im Testmodul: `_devkum_response`,
`_snbbipo_response`, `_warehouse_response`, jeder mit **einer** Reihe und dem
Kommentar «minimal but structurally faithful». Beim ersten Vergleich mit der
Quelle stimmte davon fast nichts — und mit den Abweichungen kamen vier
ausgelieferte Fehler heraus.

Was die Bauer behaupteten und was `data.snb.ch` liefert:

| | erfunden | aufgezeichnet |
|---|---|---|
| `metadata.key` | `M.devkum.EUR1.M` | `EPB@SNB.devkum{M0,EUR1}` |
| Warehouse-Header | 1 Dimension | **4** (Jahresreihe), **5** (Monatsreihe) |
| `unit` | `Mio. CHF` / `1000 CHF` | `In Millionen Franken` / `CHF` mit `scale: "3"` |

Der Header war der Knackpunkt: `_filter_timeseries` zerlegt den Schluessel
positionsgleich zu den Dimensionen. Eine Fixture mit einer Dimension hat diese
Zerlegung nie gesehen.

**1. `frequency="monthly"` lieferte immer eine leere Tabelle.** Die
Dimensionsordnung stand als Konstante `BIL_DIM_ORDER` im Code — vier Eintraege,
gemessen an der Jahresreihe. Die Monatsreihe desselben Werkzeugs fuehrt **fuenf**
Dimensionen; die vierte ist die sektorale Gliederung nach ESVG.
`_filter_timeseries` verwarf jede Reihe, deren Laenge nicht passte, und zwar
stumm. Ergebnis: HTTP 200, eine Tabelle mit Kopfzeile und nichts darunter. Zwei
weitere Gruende kamen dazu und haetten je fuer sich genuegt: die
Konsolidierungsstufe stand fest auf `K` (die Monatsreihe kennt nur `U`), und die
Vorgabe `A30` fuer alle Banken heisst dort `A40`.

Der Cube nennt seine Dimensionsordnung selbst — unter `/dimensions/<lang>`, mit
stabilen IDs. Der Server liest sie jetzt, statt sie zu kennen. Gemessen:
36 Zeilen statt null. `BIL_DIM_ORDER` und `EFR_DIM_ORDER` bleiben als Beleg im
Code stehen und werden im Test gegen die aufgezeichneten Deklarationen
gehalten — sie stimmen fuer zwei von drei Cubes, und der dritte ist der Punkt.

**2. `snb_get_warehouse_metadata` war kaputt, seit es existiert.** Es baute
`dimensions/json/<lang>` — in Analogie zu `data/json/<lang>`, und das war die
naheliegende Annahme. Den Pfad gibt es nicht. `data.snb.ch` ist eine
Angular-App vor einer API, und ein unbekannter Pfad unter `/api/` gibt kein
404, sondern **HTTP 200 mit `text/html`** und dem Geruest der Web-App. Wer nur
den Statuscode prueft, liest das als Erfolg. Richtig ist `dimensions/<lang>`,
ohne `json`-Segment. Neu prueft `_fetch_warehouse` zusaetzlich den
Content-Type und wirft `UpstreamShapeError`, statt irgendwo weit weg von der
Ursache zu scheitern.

**3. Drei Aggregate standen unter derselben Beschriftung.** Die Jahresreihe
fuehrt `INLANDAUSLAND` mit Total, Inland und Ausland. Der Server filterte diese
Dimension nicht und zeigte sie nicht an, also kamen fuer «alle Banken, Total
Waehrung» **drei** Zeilen heraus, identisch beschriftet — und Inland + Ausland
ergibt das Total. Gemessen fuer 2025: 2'179,6 + 1'240,1 = 3'419,7 Mrd. CHF. Wer
die erste Zeile nahm, hatte Glueck; wer summierte, verdoppelte die Bilanz.
Jede Dimension, die nicht eingegrenzt wurde, steht jetzt namentlich in der
Zeile (Spalte «Gliederung»).

**4. Eine Waehrung wurde angeboten, die es nicht gibt.** `CURRENCIES` fuehrte
`INR100`; weder `devkum` noch `devkua` kennen es. `snb_list_currencies` bot es
an, und jede Abfrage darauf antwortete mit «keine Daten» — derselbe Satz wie
bei einem Tippfehler. Umgekehrt fehlten `USD3M` und `USD6M`, die es gibt: die
USD-Terminkurse. Beides korrigiert, und ein Test haelt die Tabelle jetzt in
**beide** Richtungen gegen die aufgezeichnete Antwort; eine Richtung allein
haette genau die Haelfte durchgelassen. Dazu prueft `snb_convert_currency` die
Einheit gegen die Beschriftung der Quelle («DKK 100.-», «EUR 1.-») und bricht
bei Widerspruch ab, statt zu rechnen: ein um Faktor 100 falscher Kurs liefert
ein vollstaendiges, formatiertes, plausibles Ergebnis.

**Nullbefunde, die genauso dazugehoeren:** Die 28 Bilanzpositionen
(`BALANCE_SHEET_POSITIONS`), die 12 Bankengruppen (`BANK_GROUPS`) und die
6 Positionen der Erfolgsrechnung stimmen vollstaendig mit der Quelle ueberein.
Auch das ist jetzt zugesichert statt angenommen.

**Wo ein angefragter Dimensionswert im Cube nicht existiert**, nennt die
Fehlermeldung die vorhandenen — statt eine leere Tabelle zu liefern, die sich
liest wie «diese Banken haben keine Aktiven».

### Behoben — der Live-Lauf meldete 16 Fehler, die er nicht benennen konnte

Beide Live-Suiten liefen **doppelt**. Ihre Szenarien hiessen `test_01_…` bis
`test_20_…`, also hat pytest jedes einzeln eingesammelt und ausserhalb von
`_lifespan` ausgefuehrt — dort ist der geteilte HTTP-Client nicht offen, und
jedes Szenario mit Netzzugriff faellt zwangslaeufig. Danach lief derselbe Satz
noch einmal ueber `test_all_live_*_scenarios`, diesmal korrekt und gruen. Die
Zaehler summierten beide Durchgaenge: `Total: 40 | Bestanden: 24 |
Fehlgeschlagen: 16` bei 20 Szenarien, waehrend die Zusammenfassung jedes
Szenario einmal rot und einmal gruen auflistete.

Der Lauf war damit seit jeher rot, und deshalb steht der Job auf
`continue-on-error` — ein Signal, das immer Alarm gibt, ist abgeschaltet. Genau
dieses Signal haette Befund 1 und 2 gefunden: Szenario 07 faehrt die
Monatsbilanz, Szenario 03 die Dimensionsmetadaten.

Die Szenarien heissen jetzt `scenario_NN_…` und laufen nur noch ueber den einen
Einstiegspunkt. Gemessen: 40 von 40 gruen, beide Suiten.

### Hinzugefuegt — die Fixtures sind aufgezeichnet, nicht mehr ausgedacht

**`scripts/record_fixtures.py`** holt elf Antworten von `data.snb.ch` — die
Wechselkurs-, Bilanz- und Bankenstatistik-Cubes samt ihrer
Dimensionsdeklarationen — und schreibt `tests/fixtures/PROVENANCE.md` mit
Quelle, **Aufzeichnungsdatum**, Auswahlregel und SHA-256 je Datei. Ohne Datum
ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht mehr zu
unterscheiden.

**Die Auswahlregel ist nicht «die ersten N».** `devkum` ist 889 KB, ein
Vollabzug waere unlesbar — aber ein Zuschnitt nach Position haette hier
ausgerechnet das weggeschnitten, worum es geht. Stattdessen bleiben **alle
Reihen** erhalten und nur die Wertelisten sind gekuerzt: Ueber die Dimensionen
argumentiert der Code, die Werte zeigt er an. Nur so bleibt die Frage «welche
Waehrungen, Positionen und Bankengruppen fuehrt die Quelle ueberhaupt»
beantwortbar — und an ihr haengen drei der vier Befunde.

Das Skript bricht ausserdem ab, statt eine unbrauchbare Fixture zu schreiben:
wenn `devkum` keine Monatsende-Reihen mehr fuehrt (dann prueft der Filter
nichts), wenn die Jahresreihe nur noch eine Auspraegung von `INLANDAUSLAND`
hat (dann belegt sie Befund 3 nicht mehr), wenn die Monatsreihe auf vier
Dimensionen schrumpft (dann ist Befund 1 geheilt), oder wenn ein Endpunkt mit
`text/html` antwortet (dann zeichnete man eine Fehlerseite auf).

**`tests/fixture_data.py`** laedt sie und behandelt einen fehlenden Namen als
Fehler statt als leere Struktur — ein Loader, der bei einem Tippfehler `{}`
zurueckgibt, erzeugt einen Test, der nichts mehr prueft und trotzdem Erfolg
meldet.

**Gegenprobe gefuehrt:** Mit zurueckgedrehtem Code — feste Dimensionsordnung,
alter Metadaten-Pfad, `INR100` zurueck in der Tabelle — fallen sechs der neuen
Tests. Erwartungen werden durchgehend aus der Fixture abgeleitet statt
danebengeschrieben; eine feste Zahl waere beim naechsten Aufzeichnen falsch,
ohne dass sich etwas Gepruefte geaendert haette.

Der Rahmen dazu steht im Skill [`mcp-data-fidelity`](https://github.com/malkreide/mcp-data-fidelity-skill)
unter Regel 5 und im Katalog-Check `OPS-009`.

### Hinzugefuegt — der naechtliche Live-Lauf wird sichtbar, wenn er faellt

Der `live`-Job faehrt seit jeher jede Nacht `python tests/test_live_scenarios.py`
und `python tests/test_live_warehouse.py` gegen `data.snb.ch`. Das ist mehr, als
die meisten Server im Portfolio haben — und es fehlte trotzdem das Entscheidende:
**Ein rotes Ergebnis sah niemand.**

Ein geplanter Lauf, dessen Ausgang nur als roter Eintrag im Actions-Tab landet,
ist eine teurere Variante von «laeuft nicht». Rote Cron-Jobs werden nach der
zweiten Woche nicht mehr angeschaut, und dann faellt der Ausfall wieder erst
einem Nutzer auf.

Eine rote Nacht oeffnet jetzt ein Issue mit stabilem Titel-Praefix und Label
`upstream` und kommentiert ein bestehendes, statt ein zweites aufzumachen — bei
einem taeglichen Cron der Unterschied zwischen einem Thread und dreissig Issues
im Monat. Ein wieder gruener Lauf schliesst es.

**Drei Antworten, nicht zwei.** `if: failure()` kennt rot und nicht rot; ein
gescheitertes `pip install` saehe damit aus wie ein gebrochener Vertrag mit der
SNB. `scripts/classify_live_scenarios.py` liest deshalb die Summenzeile der
Szenarienlaeufe und trennt `clear`, `finding` und `unknown`. Ein `unknown`
schliesst nie ein Issue: zuzumachen hiesse zu behaupten, der Vergleich sei
gelaufen.

Der Fall, der die Einordnung noetig macht, steht im eigenen Code: `main()` gibt
`FAILED == 0` zurueck. Bei null registrierten Szenarien ist das `True` — ein
gruener Lauf, der nichts geprueft hat. `Total: 0` ist deshalb `unknown`, und eine
fehlende Summenzeile ebenfalls.

Die Einordnung steht in einem Skript mit eigenem Test
(`tests/test_classify_live_scenarios.py`, 15 Tests) und nicht in einem
`run:`-Block: Sie entscheidet, ob ein Issue auf- oder zugeht, und das ist der
einzige Teil des Jobs, der etwas behauptet.

Die Szenarien-Ausgabe geht ueber `env` ins `github-script`, nicht ueber `${{ }}`
— sie ist fremder Text, der sonst in einem JavaScript-Template-Literal landet.
Das Label wird vor dem ersten Issue angelegt, sonst scheitert genau die Nacht, in
der es gebraucht wird. `permissions: issues: write` kommt dazu.

Gemessen mit `live_schedule_probe` aus `mcp-continuous-auditor`: vorher
`LIVE_SCHEDULED_SILENT`, jetzt `LIVE_SCHEDULED`.

### Added

- **Retry-Politik gegenueber dem SNB-Warehouse** (ARCH-014): `Retry-After` wird
  gelesen und schlaegt die Backoff-Tabelle, der Backoff ist gestreut, und ein
  Gesamtbudget von 25 s begrenzt den ganzen Aufruf.

  `Retry-After` bei 429/503 in beiden Formen der RFC 9110 §10.2.3. Ein
  unbrauchbarer Header fuehrt zurueck auf die Tabelle statt zum Absturz.

  Jitter: `RETRY_DELAYS[attempt]` war deterministisch, alle Clients retryen im
  Gleichtakt, und die Last kommt als Welle zurueck, genau wenn das Warehouse
  sich erholt. Neu [0.5x, 1.5x]; auf einem `Retry-After` einseitig
  [1.0x, 1.25x]. Gedeckelt bei 20 s **nach** dem Jittern, damit der Deckel eine
  echte Schranke ist.

  Gesamtbudget verankert an `MCP_DEFAULT_TIMEOUT = 30.0` des Python-SDK. Das
  Warehouse liefert vorbereitete Cubes und antwortet gesund deutlich unter einer
  Sekunde — anders als bei den SPARQL-Servern gibt es hier keinen Langlaeufer zu
  schuetzen. Der Request liegt in einer `asyncio.timeout`-Deadline, weil httpx'
  Timeout pro Operation gilt und den Aufruf nicht begrenzen kann.


### Hinzugefuegt

- **`scripts/check_ruff_pin.py` und je ein Schritt dafuer in CI und Hook.** Der
  Check vergleicht die `rev` des ruff-pre-commit-Repos in
  `.pre-commit-config.yaml` mit dem `ruff==`-Pin im lint-Job und meldet auch,
  wenn einer der beiden Pins ganz fehlt.

  Anlass ist eine Luecke im Eintrag darunter: der Pre-Commit-Hook existiert, um
  lokal genau die Formatierung zu erzwingen, die der lint-Job prueft. Das haelt
  nur, solange beide dieselbe Ruff-Version nennen. Laufen die Pins
  auseinander, formatiert der Hook nach der einen und die CI prueft nach der
  anderen — der Hook meldet gruen, die CI wird rot. Das ist derselbe
  Fehlschlag, gegen den der Hook eingefuehrt wurde, nur eine Ebene hoeher.

  Abgesichert war das bis dahin durch einen Kommentar in beiden Dateien, der
  darum bittet, sie zusammen zu bumpen. Bitten ist keine Pruefung — dieselbe
  Bauart von Luecke wie bei `server.json`, wo die committete Version von nichts
  widerlegt wurde.

  Gegengeprueft mit vier gebauten Vorzustaenden: nur `ci.yml` gebumpt, nur die
  `rev` gebumpt, `rev` entfernt, `ruff==`-Pin entfernt. Alle vier melden und
  beenden sich mit Exit 1.

- **`tests/` und `scripts/` sind jetzt ruff-sauber und werden geprueft.** Bisher
  deckten Hook und lint-Job nur `src/` ab; beide pruefen jetzt
  `src/ tests/ scripts/`, und der Hook laeuft ohne `files`-Filter ueber jede
  Python-Datei im Repo.

  Der Grund fuer die alte Einschraenkung war, dass `tests/` und `scripts/` 22
  Lint-Befunde und drei unformatierte Dateien trugen; sie einzubeziehen haette
  Commits an unberuehrtem Alt-Code blockiert. Die Befunde sind jetzt behoben,
  damit faellt der Grund weg.

  Behoben wurden: ungenutzte Importe (`json`, `datetime`, `timedelta`),
  unsortierte Import-Bloecke, f-Strings ohne Platzhalter, ein verschachteltes
  `with` (SIM117) und drei `pytest.raises(Exception)` (B017), die jetzt auf
  `pydantic.ValidationError` zeigen statt auf den Namen der Exception zu
  vergleichen — ein blindes `Exception` haette dort auch ein `TypeError`
  durchgehen lassen.

  Die drei E402-Befunde kamen daher, dass in den beiden Live-Test-Dateien eine
  Funktionsdefinition und eine Zuweisung zwischen `sys.path.insert()` und den
  Projekt-Importen standen. Statt sie per `noqa` stumm zu schalten, steht das
  Path-Setup jetzt direkt vor den Projekt-Importen — dasselbe Muster, das
  `test_unit.py` schon nutzte und das ruff akzeptiert.

  Gegengeprueft: `pytest -m "not live"` meldet unveraendert 13 passed, die
  Sammlung der Live-Tests unveraendert 42 — die Importe tragen also weiterhin.
  Der einzige vollstaendig gemockte Live-Test (`test_20_retry_logic`, der das
  umgeschriebene `with` enthaelt) laeuft gruen.

- **`.pre-commit-config.yaml` — der `lint`-Job der CI, lokal vorgezogen.** Die
  Hooks fahren dieselben drei Schritte wie der Job: `ruff check src/`,
  `ruff format src/` und `scripts/check_version_sync.py`.

  Anlass ist ein realer Fehlschlag in diesem Repo: `ruff format --check src/`
  brach auf `df973d8` ab, und der Fix kam vier Minuten spaeter als eigener
  Commit hinterher. Lokal war nichts aufgefallen, und das hat einen Grund —
  `pyproject.toml` verlangt fuer die Entwicklung `ruff>=0.5`, die CI pinnt
  `ruff==0.15.8`. Zwei Versionen, zwei Formatierungen.

  pre-commit loest genau das: es installiert Ruff in einer eigenen Umgebung in
  der Version, die in `.pre-commit-config.yaml` steht. Nicht mehr das lokal
  installierte Ruff entscheidet, sondern der Pin. Damit die beiden Pins nicht
  auseinanderlaufen, steht in beiden Dateien ein Verweis auf die jeweils
  andere.

  Bewusst nur `src/`, wie der CI-Job: `tests/` und `scripts/` sind heute nicht
  ruff-sauber (22 Lint-Befunde, drei unformatierte Dateien). Sie einzubeziehen
  haette Commits an unberuehrtem Alt-Code blockiert, das die CI durchwinkt —
  der Hook waere strenger gewesen als die Regel, die tatsaechlich gilt.

  Gegengeprueft: mit dem realen Vorzustand von `df973d8` meldet der Hook
  `ruff format … Failed` und beendet sich mit Exit 1, der Commit kaeme also
  nicht durch.

- **`scripts/check_version_sync.py` und ein CI-Schritt dafuer.** Der Check
  vergleicht `pyproject.toml` gegen `server.json` und die README-Badges und
  meldet zusaetzlich jede von Hand gepflegte Versionsnummer unter `src/`.

  Anlass ist ein Befund in genau diesem Repo: `server.json` stand auf `0.4.3`,
  waehrend `pyproject.toml` bei `0.4.4` war. Aufgefallen ist es niemandem, und
  das hat einen strukturellen Grund — `publish.yml` schreibt das Feld beim
  Veroeffentlichen aus dem Tag-Namen, die committete Zahl wirkt also nie auf
  das Artefakt und wird von nichts widerlegt. Sie ist aber die Zahl, die
  Menschen im Repo lesen.

  Dieses Repo war eines von nur zwei im Portfolio ohne diesen Check, und beide
  waren verstimmt; die uebrigen 31 tragen ihn und waren alle synchron.

  Der Schritt haengt im `lint`-Job, nicht in der Test-Matrix: der Check kommt
  mit der Standardbibliothek aus und braucht keine Installation.

  Gegengeprueft: mit dem realen Vorzustand (`server.json` auf 0.4.3) meldet der
  Check `DRIFT` und beendet sich mit Exit 1.

## [0.4.5] - 2026-07-31

### Hinzugefuegt

- **Der Server nennt jetzt seinen Namen.** Bisher ging gegenueber jedem
  Upstream der httpx-Default hinaus: der Betreiber der Datenquelle sah
  eine Bibliothek, nicht uns, und hatte keinen Weg, uns bei Fehlverhalten
  zu erreichen. Neu traegt den HTTP-Client
  `swiss-snb-mcp/<version> (+github.com/malkreide/swiss-snb-mcp)`.

- **`__version__` kommt aus den Paket-Metadaten.** Vorher von Hand
  gepflegt bzw. gar nicht vorhanden. Ein Literal waere genau die Drift,
  die dieses Portfolio gerade ueberall beseitigt hat.

  Die Version stammt aus `importlib.metadata` und kann nicht getrennt vom
  Paket driften.

## [0.4.4] - 2026-06-07

### Fixed
- Republish release because the PyPI upload for `0.4.3` collided with an older,
  stale artifact already occupying that version. PyPI is immutable, so the
  current build is shipped under a new version number.
- `publish.yml` now sets `skip-existing: true` so the workflow no longer fails
  hard when a version already exists on PyPI.

## [0.4.0] - 2026-05-12

Audit-driven hardening release. All changes are responses to findings from the
[mcp-audit-skill](https://github.com/malkreide/mcp-audit-skill) audit (initial
report in `audits/2026-05-11-swiss-snb-mcp/audit-report.md`, post-remediation
re-audit in `audits/2026-05-12-swiss-snb-mcp-reaudit/audit-report.md` — final
score 27 pass / 3 partial / 0 fail).

### Added
- **5 MCP resources** for static catalogs (`data://snb/currencies`,
  `data://snb/balance-sheet-positions`, `data://snb/cubes`,
  `data://snb/warehouse-cubes`, `data://snb/bank-groups`).
- Egress allow-list (`ALLOWED_HOSTS = {"data.snb.ch"}`) enforced before every
  outbound HTTP request (SEC-021).
- Pydantic `strict=True` on every tool input model — type coercion at the
  tool boundary is rejected (SEC-018).
- `_lifespan` opens one shared `httpx.AsyncClient` for the whole server
  lifetime instead of per call (SDK-001). Performance + reduces WAF 503s.
- Explicit `logging.basicConfig(stream=sys.stderr, ...)` at module top — stdout
  stays reserved for the JSON-RPC protocol (OBS-004).
- `tests/test_unit.py` with 11 respx-mocked unit tests. CI runs `pytest -m
  "not live"` on every PR; live tests moved to a nightly schedule (OPS-001).

### Changed
- **BREAKING:** The 5 listing capabilities are now MCP **resources**, not tools.
  Clients that called `snb_list_currencies()` etc. as tools must switch to
  `read_resource("data://snb/currencies")` etc. Tool count drops 16 → 11
  (ARCH-006).
- `_handle_http_error()` no longer leaks `response.text[:200]` or exception
  class names into LLM-visible output. Unknown exceptions are logged with
  full traceback to stderr and reduced to a generic user message (OBS-002).
- Live test scripts renamed: `tests/test_scenarios.py` → `test_live_scenarios.py`,
  `tests/test_warehouse_scenarios.py` → `test_live_warehouse.py`. Each carries
  `pytest.mark.live`; the legacy `python tests/test_live_*.py` script entry
  still works.
- Cap `mcp[cli]` at `>=1.0.0,<2.0.0` so a future SDK 2.x breaks loudly at
  install time rather than silently at runtime (SDK-003).

## [0.3.0] - 2026-04-01

### Added
- **Phase 3: Warehouse-API und Zahlungsbilanz**
- `snb_get_warehouse_data` — generischer Zugang zu SNB Warehouse Cubes (BSTA, etc.)
- `snb_get_warehouse_metadata` — Dimensionen und letzte Aktualisierung eines Warehouse Cubes
- `snb_get_banking_balance_sheet` — Bankbilanzen nach Bankengruppe (monatlich/jährlich, Aktiven/Passiven)
- `snb_get_banking_income` — Erfolgsrechnung nach Bankengruppe (Geschäftsertrag/-aufwand, jährlich)
- `snb_get_balance_of_payments` — Zahlungsbilanz und Auslandvermögen (bopoverq, auvekomq)
- `snb_list_warehouse_cubes` — Übersicht der wichtigsten Warehouse Cube-IDs
- `snb_list_bank_groups` — Liste aller 12 Bankengruppen-IDs mit Bezeichnung
- Neues Modul `warehouse.py` für Warehouse-API-Tools (modularer Split)
- Client-seitiges Filtern (dimSel auf Warehouse-API fehlerhaft)
- Retry mit Exponential Backoff bei HTTP 503 (WAF-Schutz)
- 20 neue Integrations-Testszenarien für Warehouse-Tools

### Changed
- `snb_list_known_cubes` aktualisiert mit Phase-3-Tools und Zahlungsbilanz-Cubes
- `bopoverq` und `auvekomq` als neue Phase-2-Cubes aufgenommen

### Notes
- Warehouse-API verwendet Punkte (`.`) als Separator in Cube-IDs (URLs),
  `@` nur in internen Metadata-Keys
- EFR-Cubes haben 5-Segment-IDs (nicht 6): `BSTA.SNB.JAHR_K.EFR.{Position}`
- ZAST-Warehouse-Cubes existieren nicht als direkte IDs —
  Zahlungsbilanz via Standard-Cube-API (bopoverq, auvekomq)

## [0.2.0] - 2026-03-16

### Added
- `snb_list_known_cubes`: 5 zusätzliche verifizierte Cube-IDs (Phase 2)
  - `snbgwdzid` — SNB-Leitzins, SARON-Fixing und Sichtguthaben-Zinssätze (täglich)
  - `zirepo` — SARON Compound Rates Overnight / 1M / 3M / 6M
  - `zimoma` — Monatliche Geldmarktsätze im int. Vergleich (SARON, SOFR, TONA, SONIA, €STR, EURIBOR)
  - `snboffzisa` — Offizielle Leitzinssätze im Vergleich (SNB, Fed, EZB, BoE, BoJ)
  - `snbmonagg` — Geldmengenaggregate M1, M2, M3 + Komponenten (Bargeld, Sicht-, Spar-, Termineinlagen)
- Hinweis auf Warehouse-API (Bankenstatistik) in `snb_list_known_cubes` als Phase-3-Marker

### Notes
- Alle neuen Cubes sind direkt über `snb_get_cube_data` und `snb_get_cube_metadata` nutzbar,
  ohne weitere Code-Änderungen
- Bankenstatistik (Bilanzsumme nach Bankengruppe) liegt im Warehouse-API
  (`/api/warehouse/cube/BSTA@SNB…`) und bleibt Phase 3

## [0.1.0] - 2026-03-16

### Added
- `snb_get_exchange_rates` — monthly CHF exchange rates for 27 currencies (cube: devkum)
- `snb_get_annual_exchange_rates` — annual average rates back to 1980 (cube: devkua)
- `snb_get_balance_sheet` — SNB balance sheet positions in millions CHF (cube: snbbipo)
- `snb_convert_currency` — currency conversion using official SNB monthly average rates
- `snb_get_cube_data` — generic access to any SNB cube by ID
- `snb_get_cube_metadata` — inspect dimensions and filter values of any cube
- `snb_list_currencies` — list all 27 supported currency IDs with labels and unit multipliers
- `snb_list_balance_sheet_positions` — list all asset and liability position IDs
- `snb_list_known_cubes` — overview of verified cubes and cube discovery guide
- Bilingual documentation (English / German)
- FastMCP server with stdio and Streamable HTTP transport support
