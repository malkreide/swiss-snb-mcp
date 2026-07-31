# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
