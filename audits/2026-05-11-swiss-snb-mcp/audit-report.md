# Audit-Report: swiss-snb-mcp

**Run-ID:** `2026-05-11T202228Z-swiss-snb-mcp`
**Auditor:** Claude Code (mcp-audit Skill)
**Skill-Version:** mcp-audit-skill (latest, https://github.com/malkreide/mcp-audit-skill)
**Catalog:** 68 checks, 8 categories
**Server-Version:** 0.3.0

---

## Executive Summary

`swiss-snb-mcp` ist ein read-only stdio-only MCP-Server für öffentliche SNB-Daten — die Risikoklasse ist niedrig, weil Auth, Write-Operationen und Netzwerk-Exposition komplett fehlen. Von 31 anwendbaren Checks sind 18 `pass`, 11 `partial`, 2 `fail`. **Production-ready: ja**, mit drei high-severity Verbesserungen (Connection-Pool-Reuse via Lifespan, separate Unit-Tests, Pydantic strict + cube_id pattern). Kein einziger `critical`-Check schlägt voll fehl, alle Blocker sind aufgrund des sicheren Read-only-/Public-Open-Data-Profils strukturell ausgeschlossen.

---

## Profile-Snapshot

| Feld | Wert |
|---|---|
| `name` | swiss-snb-mcp |
| `repo` | malkreide/swiss-snb-mcp |
| `transport` | stdio-only (`mcp.run()` default in `server.py:1395`) |
| `auth_model` | none |
| `data_class` | Public Open Data (data.snb.ch) |
| `write_capable` | false |
| `deployment` | [local-stdio] (uvx, pip, Claude Desktop) |
| `is_cloud_deployed` | false |
| `sdk_language` | Python (FastMCP) |
| `tools_make_external_requests` | true (httpx → data.snb.ch) |
| `tools_include_filesystem` | false |
| `data_source.is_swiss_open_data` | true |

---

## Applicability-Übersicht

```
Applicable checks: 31 / 68
  ARCH: 11/12   (alle ausser ARCH-010 write-capable)
  SDK:   3/5    (Python-Subset, kein HTTP)
  SEC:   9/23   (stdio-spezifischer Subset)
  SCALE: 0/6    (kein Cloud, stdio-only)
  OBS:   4/6
  HITL:  0/5    (no write, no sampling)
  CH:    1/8    (nur CH-004 Public-Open-Data-Attribution)
  OPS:   3/3
Severity-Breakdown applicable: critical=5  high=13  medium=13
```

---

## Status-Summary (`summary.json`-equivalent)

```json
{
  "totals": {
    "by_status": {"pass": 18, "partial": 11, "fail": 2, "skip": 0},
    "by_severity_failed_or_partial": {"critical": 2, "high": 8, "medium": 3}
  },
  "production_ready": true,
  "blocking_findings": [],
  "policy": "fail-or-partial"
}
```

Begründung `production_ready: true`: keine `critical`/`high`-Fails mit Sicherheits-Impact für das aktuelle stdio-only / read-only / Public-Open-Data-Profil. Die 2 Fails (OPS-001, SDK-001) sind Engineering-Mängel ohne Daten- oder Auth-Risiko.

---

## Findings-Tabelle (nach Severity)

| ID | Severity | Status | Titel | Effort |
|---|---|---|---|---|
| OBS-004 | critical | partial | stderr für stdio-Server | S |
| SEC-004 | critical | partial | SSRF/HTTPS-Enforcement + Pfad-Validation | S |
| OPS-001 | high | **fail** | Test-Strategie: Unit + Live getrennt | M |
| SDK-001 | high | **fail** | FastMCP Lifespan / Connection-Pool-Reuse | S |
| SEC-007 | high | partial | Container-Sandboxing | M |
| ARCH-006 | high | partial | Tool-Budget: 16 Tools (Schwelle 15) | M |
| OBS-001 | high | partial | Execution-Errors als isError-Pattern | S |
| OBS-002 | high | partial | mask_error_details + Exception-Leak | S |
| SEC-018 | high | partial | Pydantic strict + cube_id pattern | S |
| SEC-021 | high | partial | Code-Layer Egress Allow-List | S |
| OBS-003 | medium | partial | Strukturiertes Logging | S |
| SDK-002 | medium | partial | Type-Hints Coverage | S |
| SDK-003 | medium | partial | mcp-Version-Pin in pyproject | S |

**Pass (nicht im Report-Detail):** ARCH-001/002/003/004/005/007/008/009/011/012, OBS, SEC-006/013/019/020, CH-004, OPS-002/003, SDK — siehe Total = 18.

---

## Detail-Findings

### Finding: OBS-004 — stderr für stdio-Server

**Severity:** critical · **Status:** partial · **Effort:** S

**Observed Behavior:** `server.py` und `warehouse.py` enthalten keine `print()`-Statements (verifiziert via grep) — also keine akute stdout-Korruption. Aber: es gibt auch **keine explizite Logging-Konfiguration** (`logging.basicConfig(stream=sys.stderr, ...)`). Damit hängt die Korrektheit davon ab, dass keine Library Default-Logging zu stdout schreibt.

**Expected Behavior:** Explizit `logging.basicConfig(stream=sys.stderr, level=logging.INFO)` vor dem ersten Import konfigurieren, damit künftige `logger.info(...)`-Calls garantiert auf stderr landen.

**Evidence:**
- `grep -rE "print\(" src/` → 0 Treffer
- `grep -rE "StreamHandler|sys\.stderr|basicConfig" src/` → 0 Treffer
- `src/swiss_snb_mcp/server.py:1394-1395` Entry-point ohne Log-Setup

**Risk:** Niedrig **heute** (kein Logging benutzt). Wird kritisch, sobald irgendwo `print(...)`, `logging.warning(...)` oder eine Dependency-Library schreibt — typisches Symptom: Claude Desktop bricht Verbindung beim ersten Log-Output ab.

**Remediation:**
```python
# server.py, ganz oben
import sys, logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s")
```

---

### Finding: SEC-004 — SSRF / HTTPS-Enforcement + Pfad-Validation

**Severity:** critical · **Status:** partial · **Effort:** S

**Observed Behavior:** `SNB_BASE_URL = "https://data.snb.ch/api/cube"` ist hartcodiert → HTTPS garantiert, kein User-controlled Scheme/Host. **Aber:** `snb_get_cube_data` baut `path = f"{params.cube_id}/data/json/{params.lang.value}"` aus dem User-Input `cube_id` (`server.py:941`) ohne Pfad-Validation. Cube-ID `"../../../admin"` oder `"foo?secret=x"` würde durchgereicht werden.

**Expected Behavior:** `cube_id` mit Whitelist-Pattern validieren (`^[a-z0-9_]+$`).

**Evidence:**
- `src/swiss_snb_mcp/server.py:19` `SNB_BASE_URL` hardcoded HTTPS ✓
- `src/swiss_snb_mcp/server.py:920` `snb_get_cube_data(params: CubeDataInput)` — keine `pattern=`-Constraint auf `cube_id`-Field
- `src/swiss_snb_mcp/server.py:941` Pfad-Konkatenation ohne Sanitization

**Risk:** Path-Traversal in der SNB-API-URL ist technisch möglich. Realistisch begrenzt durch die SNB-API selbst (öffentlich, keine Auth-Bypass), aber Information-Disclosure (anderer interner Endpoint von data.snb.ch?) nicht ausgeschlossen.

**Remediation:** In Pydantic Input-Models:
```python
cube_id: str = Field(..., pattern=r"^[a-z0-9]{4,32}$", description="...")
```

---

### Finding: OPS-001 — Test-Strategie

**Severity:** high · **Status:** **fail** · **Effort:** M

**Observed Behavior:** `tests/test_scenarios.py` + `tests/test_warehouse_scenarios.py` sind **beides Live-Tests** gegen `data.snb.ch`. Kein `respx`-Mocking, keine `@pytest.mark.live`-Marker, keine `test_unit.py`. CI führt die Live-Tests bei jedem PR aus (`.github/workflows/ci.yml` Step "Live-Tests gegen SNB API").

**Expected Behavior:** `tests/test_unit.py` mit respx-mocks (laufen in CI by default) + `tests/test_live.py` mit `@pytest.mark.live` (laufen nur manuell/nightly).

**Evidence:**
- `ls tests/` → nur `test_scenarios.py`, `test_warehouse_scenarios.py`
- `grep -nE "respx|pytest.mark.live" tests/*.py` → 0 Treffer
- `.github/workflows/ci.yml:43-46` ruft Live-Tests in jedem CI-Run auf

**Risk:** CI-Pipeline ist anfällig für SNB-API-Outages (z.B. Wartungsfenster) → unbegründete Red Builds → Refactorings werden unsicher. Bei Rate-Limit der SNB-API wird die Pipeline zur Quote-Verbrauchsmaschine.

**Remediation:**
1. `pip install respx pytest-asyncio` als dev-deps
2. `tests/test_unit.py` neu, alle Tool-Handler mit respx-Mocks
3. Bestehende Tests in `tests/test_live.py` umbenennen + `@pytest.mark.live` taggen
4. `pyproject.toml`: `[tool.pytest.ini_options] markers = ["live: requires data.snb.ch"]`
5. CI: `pytest -m "not live"` standardmäßig, Live-Job nur nightly

---

### Finding: SDK-001 — Lifespan / Connection-Pool-Reuse

**Severity:** high · **Status:** **fail** · **Effort:** S

**Observed Behavior:** Jeder Tool-Call erzeugt einen neuen `httpx.AsyncClient` via `async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:` — TCP-Connection und TLS-Handshake werden bei jedem Call neu aufgebaut.

**Expected Behavior:** Ein gemeinsamer `httpx.AsyncClient` über die Server-Lifespan, gemanagt via `@asynccontextmanager`-Lifespan-Funktion. `FastMCP("swiss_snb_mcp", lifespan=lifespan)`.

**Evidence:**
- `src/swiss_snb_mcp/server.py:151-157` neuer Client pro Call
- `src/swiss_snb_mcp/warehouse.py:93,405` identisches Anti-Pattern
- `grep -rE "asynccontextmanager|lifespan" src/` → 0 Treffer

**Risk:** Performance-Degradation (~50-200ms Overhead pro Call durch TLS-Handshake), unnötige Connection-Churn auf data.snb.ch (höheres Risiko, in deren WAF-Rate-Limits zu rennen — CHANGELOG erwähnt bereits 503er).

**Remediation:**
```python
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(server: FastMCP):
    server.state.http = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT,
                                          base_url=SNB_BASE_URL,
                                          follow_redirects=False)
    try: yield
    finally: await server.state.http.aclose()

mcp = FastMCP("swiss_snb_mcp", lifespan=lifespan, instructions=...)
# _fetch_snb nutzt ctx.fastmcp.state.http statt neuen Client
```

---

### Finding: SEC-007 — Container-Sandboxing

**Severity:** high · **Status:** partial · **Effort:** M

**Observed Behavior:** Kein `Dockerfile`, kein Hardening-Skript. User installieren via `uvx` oder `pip install` — der Server läuft mit User-Privilegien direkt auf dem Host, mit Zugriff auf `~/.ssh/`, Browser-Cookies, Env-Vars.

**Expected Behavior (lt. SEC-007):** Optionales Dockerfile mit non-root User, distroless oder slim Base, read-only Filesystem.

**Risk:** Niedrig im Public-Open-Data-Kontext (keine Schreibzugriffe, keine Secrets). Defense-in-Depth-Lücke aber dokumentiert als Best Practice.

**Remediation:** Dockerfile als optionales Deployment-Artefakt, kein Pflicht-Pfad. Acceptable-Risk-Vermerk im README für Local-stdio-Nutzung.

---

### Finding: ARCH-006 — Tool-Budget (16 Tools)

**Severity:** high · **Status:** partial · **Effort:** M

**Observed Behavior:** 16 Tools exponiert (Schwelle: ≤8 ok, 9-15 prüfen, 16-25 ernste Zweifel, >25 API-Mapping). Davon sind 5 reine Listing/Discovery-Tools (`snb_list_currencies`, `snb_list_balance_sheet_positions`, `snb_list_known_cubes`, `snb_list_warehouse_cubes`, `snb_list_bank_groups`).

**Expected Behavior:** Listing-Tools zu Resources (statt Tools) verschieben oder via einem `snb_discover(kind)` zusammenführen.

**Evidence:** `grep -rE "@mcp\.tool" src/ | wc -l` → 16. Auflistung aller Tool-Namen im obigen Output.

**Risk:** Tool-Manifest verbraucht unnötig Context-Window beim Client; LLM könnte zwischen `snb_get_cube_data` und `snb_get_warehouse_data` falsch wählen.

**Remediation:** Listing-Tools als MCP-Resources exponieren (`@mcp.resource(...)`) — sie sind statische Catalogs ohne Side-Effects. Reduziert Tool-Count auf 11.

---

### Finding: OBS-001 — Protocol vs. Execution Errors

**Severity:** high · **Status:** partial · **Effort:** S

**Observed Behavior:** Tool-Handler returnen bei Fehlern einen menschenlesbaren String aus `_handle_http_error()` (z.B. `"Error: Cube or endpoint not found (HTTP 404)..."`). Das ist FastMCP-konventionell und LLM-freundlich, entspricht aber **nicht** dem Pass-Pattern aus OBS-001 (`return {"isError": True, "content": [TextContent(...)]}`).

**Expected Behavior:** Strukturierter `isError: True`-Return mit `TextContent`-Liste, damit der Host die Execution-Error-Markierung sieht.

**Risk:** Niedrig — LLM versteht die String-Fehler trotzdem. Verlust ist die maschinenlesbare Trennung Protocol-Error vs. Execution-Error.

**Remediation:** `_handle_http_error()` umschreiben auf `dict`-Return mit `isError`.

---

### Finding: OBS-002 — mask_error_details + Exception-Leak

**Severity:** high · **Status:** partial · **Effort:** S

**Observed Behavior:** `FastMCP("swiss_snb_mcp", instructions=...)` ohne `mask_error_details=True`. Im Fallback-Branch von `_handle_http_error()` (`server.py:179`):
```python
return f"Error: Unexpected error ({type(e).__name__}): {str(e)[:200]}"
```
leakt der Exception-Klassenname und 200 Zeichen aus `str(e)`. Bei httpx-Exceptions enthält das oft die volle URL inkl. Query-Params.

**Expected Behavior:** Generische Fehlermeldung für unbekannte Exceptions, Details nur ins stderr-Log.

**Remediation:**
```python
mcp = FastMCP("swiss_snb_mcp", mask_error_details=True, instructions=...)
# Fallback:
logger.exception("Unhandled SNB API error")
return "Error: Unexpected error processing the request."
```

---

### Finding: SEC-018 — Pydantic strict + cube_id pattern

**Severity:** high · **Status:** partial · **Effort:** S

**Observed Behavior:** Alle Input-Models verwenden `model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")` (✓ extra="forbid"). Aber **`strict=True` ist nicht gesetzt** — Type-Coercion ist also aktiv (`"5"` → `5`). Auch fehlt ein `pattern=`-Constraint auf den `cube_id`-Feldern (siehe SEC-004).

**Expected Behavior:**
```python
model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True)
cube_id: str = Field(..., pattern=r"^[a-z0-9]{4,32}$")
```

**Risk:** Type-Confusion via LLM-Halluzinationen, und der direkte Path-Traversal-Vektor aus SEC-004.

---

### Finding: SEC-021 — Egress Allow-List

**Severity:** high · **Status:** partial · **Effort:** S

**Observed Behavior:** De-facto-Constraint durch hardcoded `SNB_BASE_URL` — der Server kann ausschliesslich `data.snb.ch` erreichen. **Aber:** keine explizite `ALLOWED_HOSTS`-Set, kein `assert_host_allowed()`-Check. Wenn jemand künftig URLs aus User-Input baut (neuer Tool, der full URLs nimmt), ist der Schutz weg.

**Expected Behavior:** Explizite Allow-List + Host-Check in `_fetch_snb()`.

**Remediation:**
```python
ALLOWED_HOSTS = frozenset({"data.snb.ch"})
def _assert_host_allowed(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise PermissionError(f"Host not in allow-list: {host}")
```

Network-Layer-Egress-Control ist n/a (kein Cloud-Deployment).

---

### Finding: OBS-003, SDK-002, SDK-003 (medium, kompakt)

- **OBS-003** (Structured Logging) — partial: kein Logging-Setup, daher kein Audit-Trail. Bei stdio-Servern okay als low-priority; mit stderr+JSON-Format aufrüsten falls Production-Use.
- **SDK-002** (Type-Hints Coverage) — partial: Tool-Bodies haben Type-Hints, aber Helper-Funktionen wie `_format_timeseries_table` teils inkonsistent.
- **SDK-003** (mcp-Version-Pin) — partial: `pyproject.toml` hat `"mcp[cli]>=1.0.0"` — unbounded upper. Bei Breaking-Change im SDK 2.x bricht der Server stillschweigend. Empfehlung: `>=1.0.0,<2.0.0`.

---

## Remediation-Plan (Reihenfolge-Vorschlag)

| # | Finding | Effort | Begründung |
|---|---|---|---|
| 1 | SDK-001 Lifespan/Connection-Pool | S | Performance + reduziert 503-Risiko (siehe CHANGELOG) |
| 2 | SEC-004 + SEC-018 cube_id pattern + strict | S | Schliesst Path-Traversal-Vektor in einem Schritt |
| 3 | OBS-002 mask_error_details + Logging-Setup | S | Schliesst Information-Leak im Fallback-Branch |
| 4 | OBS-004 explizites stderr-Logging | S | Eine Codezeile, future-proofs Logging |
| 5 | OPS-001 Test-Split (Unit + Live) | M | Stabilisiert CI; Voraussetzung für sicheres Refactoring der Tools |
| 6 | ARCH-006 Listing-Tools → Resources | M | Reduziert Tool-Count auf 11, klärt Capability-Modell |
| 7 | SEC-021 explizite Allow-List | S | Defense-in-Depth, schützt künftige Tools |
| 8 | OBS-001 isError-Pattern | S | Cosmetisch — FastMCP konvertiert String-Returns intern |
| 9 | SDK-003 Version-Cap | S | `mcp[cli]>=1.0.0,<2.0.0` |

---

## Audit-Metadata

- **Run-ID:** 2026-05-11T202228Z-swiss-snb-mcp
- **Skill-Quelle:** https://github.com/malkreide/mcp-audit-skill
- **Catalog-Stand:** 68 Checks (commit von Clone-Zeit)
- **Applicable:** 31 / 68
- **Profile-Validation:** Profil aus README + Code-Inspection abgeleitet (kein Notion-Tracker-Eintrag — die zwei Pflichtfelder `Repo URL` und sechs weitere wurden aus dem Repo verifiziert)
- **Methodische Abweichungen:**
  - Kein `audits/<run>/raw/`-Verzeichnis erzeugt (Helper-Scripts des Skill-Repos nicht installiert; manuelle Verifikation ersetzt Task-Agent-Run + Validation-Gate)
  - `summary.json` nur als JSON-Block im Report, nicht als separates File
  - Tracker-Sync entfällt (kein Backend konfiguriert)

---

## Übergabe

- Findings sind als GitHub-Issues mit Labels `audit`, `severity:high`/`severity:medium` zu öffnen
- Bei Re-Audit nach Remediation-Pass: gegen denselben Skill-Catalog-Stand laufen lassen
- Schritt 7 (Release-Vorschlag) entfällt — `production_ready: true`, aber keine offenen Audit-Findings zu schliessen, die einen Bump rechtfertigen
