# Phase 3: SNB Warehouse API Integration

**Date:** 2026-04-01
**Status:** Approved (Rev 2 — post-review, blockers resolved)
**Scope:** Warehouse-API-Zugang + dedizierte Tools fuer Bankenstatistik; Zahlungsbilanz via Standard-Cube-API

---

## 1. Background

The swiss-snb-mcp server currently supports two tiers of SNB data:

- **Phase 1:** Dedicated tools for exchange rates (monthly/annual) and SNB balance sheet via the standard Cube API (`/api/cube/`)
- **Phase 2:** Generic cube access for policy rates, SARON, money market rates, central bank rate comparisons, and monetary aggregates

Phase 3 extends the server in two directions:

1. **SNB Warehouse API** (`/api/warehouse/cube/`) for granular banking statistics:
   - **BSTA** — Swiss banking statistics (balance sheet, income statement by bank group)

2. **Standard Cube API** for balance of payments data (ZAST warehouse cubes do not exist as direct cube IDs — BoP data is available via standard cubes `bopoverq` and `auvekomq`):
   - **Balance of payments** — current account, capital account, financial account
   - **International investment position** — net external assets

### Key Differences: Cube API vs Warehouse API

| Feature | Standard `/api/cube/` | Warehouse `/api/warehouse/cube/` |
|---|---|---|
| Cube ID format | Lowercase, short (`devkum`) | Uppercase, dot-hierarchical (`BSTA.SNB.MONA_US.BIL.AKT.TOT`) |
| URL path for data | `/data/json/{lang}` | `/data/json/{lang}` (identical) |
| URL path for metadata | `/dimensions/{lang}` | `/dimensions/{lang}` (identical) |
| Additional endpoints | — | `/lastUpdate` returns `{"editionDate":"...","publicSinceDate":"..."}` |
| Dimension IDs | Generic (`D0`, `D1`) | Semantic (`BANKENGRUPPE`, `WAEHRUNG`) |
| Dimension filter (`dimSel`) | Not supported | **Broken** — returns empty values arrays. Must fetch all data and filter client-side. |
| Scale | Values directly in stated unit | `metadata.scale` field (string, e.g. `"3"` = thousands) |
| Separator in URLs | N/A | **Dots (`.`)** — e.g. `BSTA.SNB.JAHR_K.BIL.AKT.TOT` |
| Separator in metadata keys | N/A | **`@` after first segment** — e.g. `BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}` |

### Verified Cube IDs (from live API exploration)

**BSTA Balance Sheet (BIL):**
| Cube ID | Description | Size |
|---|---|---|
| `BSTA.SNB.JAHR_K.BIL.AKT.TOT` | Annual total assets, consolidated | ~42 KB |
| `BSTA.SNB.JAHR_K.BIL.PAS.TOT` | Annual total liabilities, consolidated | ~42 KB |
| `BSTA.SNB.MONA_US.BIL.AKT.TOT` | Monthly total assets, unconsolidated | ~329 KB |
| `BSTA.SNB.MONA_US.BIL.PAS.TOT` | Monthly total liabilities, unconsolidated | ~329 KB |
| `BSTA.SNB.JAHR_K.BIL.AKT.HYP` | Annual assets — mortgages | confirmed |
| `BSTA.SNB.JAHR_K.BIL.AKT.BET` | Annual assets — participations | confirmed |

**BSTA Income Statement (EFR) — 5-segment structure:**
| Cube ID | Description |
|---|---|
| `BSTA.SNB.JAHR_K.EFR.GER` | Geschaeftsertrag (operating income) |
| `BSTA.SNB.JAHR_K.EFR.GAU` | Geschaeftsaufwand (operating expenses) |
| `BSTA.SNB.JAHR_K.EFR.STE` | Steuern (taxes) |
| `BSTA.SNB.JAHR_K.EFR.UER` | Uebriger Ertrag (other income) |
| `BSTA.SNB.JAHR_K.EFR.AAU` | Anderer Aufwand (other expenses) |
| `BSTA.SNB.JAHR_K.EFR.AEG` | Ausserordentliches Ergebnis (extraordinary result) |

**EFR cube structure:** 2 dimensions only (KONSOLIDIERUNGSSTUFE, BANKENGRUPPE) — no WAEHRUNG or INLANDAUSLAND. Scale: `"3"` (thousands CHF). Data: 2015-2024.

**Balance of Payments (Standard Cube API):**
| Cube ID | Description |
|---|---|
| `bopoverq` | Zahlungsbilanz — Uebersicht (quarterly) |
| `auvekomq` | Auslandvermoegen — Komponenten (quarterly) |

**ZAST warehouse cubes:** All tested patterns returned HTTP 404. ZAST data is only accessible via the standard Cube API or the facet tree API (which requires browser sessions).

---

## 2. Architecture

### Approach: Modular Split (Ansatz B)

```
src/swiss_snb_mcp/
  __init__.py          (unchanged)
  server.py            (Phase 1/2 tools + mcp instance + BoP tool)
  warehouse.py         (NEW — Warehouse API tools for BSTA)
```

**`warehouse.py`** imports from `server.py`:
- `mcp` — the FastMCP instance (registers new tools on it)
- `Language` — Enum for de/en/fr
- `_handle_http_error` — error handling
- `DEFAULT_TIMEOUT` — HTTP timeout

**`server.py`** gets these additions:
1. **Import at end** (before `def main()`): `import swiss_snb_mcp.warehouse  # noqa: F401`
2. **`snb_get_balance_of_payments`** tool (uses standard Cube API, belongs in server.py)
3. **Updated `snb_list_known_cubes`** Phase-3 section

### Import Order Constraint

The `warehouse.py` import is a **side-effect import** — it registers tools on the shared `mcp` instance. This works because:
- `mcp` is defined at module level in `server.py` (line ~106)
- The import is placed at the end of `server.py`, after all definitions
- `warehouse.py` must NOT import tool functions from `server.py` — only module-level constants (`mcp`, `Language`, `_handle_http_error`, `DEFAULT_TIMEOUT`)
- The entry point `swiss_snb_mcp.server:main` guarantees `server.py` loads first

### Tool Annotations

All new tools follow the existing pattern:
```python
annotations={
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,   # for API-calling tools
    # or openWorldHint: False  # for static list tools
}
```

### Input Model Config

All new input models include:
```python
model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
```

---

## 3. HTTP Helper

New function in `warehouse.py`:

```python
WAREHOUSE_BASE_URL = "https://data.snb.ch/api/warehouse/cube"

async def _fetch_warehouse(
    cube_id: str,
    endpoint: str,
    lang: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
```

- Builds URL: `{WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}`
- Confirmed endpoints: `data/json` and `dimensions` (lang appended as path segment)
- Passes `fromDate` / `toDate` as query params
- Uses `httpx.AsyncClient` with `DEFAULT_TIMEOUT`
- **No `dim_sel` parameter** — dimSel is broken on the Warehouse API (returns empty values). All filtering is done client-side after fetching.
- **Retry with exponential backoff** on HTTP 503 (WAF rate limiting): max 3 retries, delays 2s/4s/8s
- Raises on other HTTP errors (handled by `_handle_http_error`)
- Response is always JSON when `/json/` is in the path (confirmed via live testing). No `Accept` header needed.

### Cube ID Validation

Warehouse cube IDs must match: `^[A-Z][A-Z0-9_.]+$`
(uppercase letters, digits, dots, underscores — e.g. `BSTA.SNB.JAHR_K.BIL.AKT.TOT`)

### Client-Side Filtering Helper

```python
def _filter_timeseries(
    timeseries: list[dict],
    filters: dict[str, set[str]],
) -> list[dict]:
    """Filter warehouse timeseries by metadata key components."""
```

The metadata key format is: `BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}`
The values in braces correspond to dimension values. This function parses the key and matches against the requested filter values (e.g. `{"BANKENGRUPPE": {"A30", "G10"}, "WAEHRUNG": {"T"}}`).

The dimension order in the key must be determined from the dimensions endpoint. For known cubes, the order is hardcoded:
- **BIL cubes:** `{KONSOLIDIERUNGSSTUFE, INLANDAUSLAND, WAEHRUNG, BANKENGRUPPE}`
- **EFR cubes:** `{KONSOLIDIERUNGSSTUFE, BANKENGRUPPE}`

---

## 4. Scale Conversion

Helper function:

```python
SCALE_FACTORS = {"0": 1, "3": 1_000, "6": 1_000_000, "9": 1_000_000_000}

def _scale_to_millions(value: float, scale: str) -> float:
    """Convert a warehouse raw value to millions."""
    factor = SCALE_FACTORS.get(scale, 1)
    return (value * factor) / 1_000_000
```

**Usage:**
- **Dedicated tools** call `_scale_to_millions` and display values in "Millionen CHF" (consistent with existing `snb_get_balance_sheet`)
- **Generic tools** show the raw value plus a scale label (e.g. "Werte in 1'000 CHF")

Scale label mapping:
```python
SCALE_LABELS = {
    "0": "Einheiten",
    "3": "1'000 CHF",
    "6": "Millionen CHF",
    "9": "Milliarden CHF",
}
```

**Note:** Scale labels are German-only (consistent with existing tools where static text is German and only API responses are localized via `lang`).

---

## 5. Tools

### 5.1 Generic Warehouse Tools (in `warehouse.py`)

#### `snb_get_warehouse_data`

Retrieve raw data from any SNB warehouse cube.

**Input model `WarehouseDataInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cube_id` | str | yes | — | Warehouse cube ID, e.g. `BSTA.SNB.MONA_US.BIL.AKT.TOT`. Pattern: `^[A-Z][A-Z0-9_.]+$` |
| `from_date` | str | no | None | Start date (YYYY-MM or YYYY) |
| `to_date` | str | no | None | End date |
| `lang` | Language | no | de | Response language |

**Output:**
- Markdown summary: cube ID, number of timeseries, scale label, first 5 series with latest value
- JSON dump (max 8000 chars, truncated with note if larger)
- No automatic scale conversion — scale shown as label

**Note:** `dim_sel` parameter removed from input model. dimSel is broken on the Warehouse API. Users should use dedicated tools for filtered access or narrow the date range.

#### `snb_get_warehouse_metadata`

Get dimension structure for any warehouse cube.

**Input model `WarehouseMetadataInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cube_id` | str | yes | — | Warehouse cube ID. Pattern: `^[A-Z][A-Z0-9_.]+$` |
| `lang` | Language | no | de | Response language |

**Output:**
- Markdown listing of all dimensions with their items (IDs and labels)
- Last update date (always fetched via second call to `/lastUpdate`)
- Full JSON dump of dimensions

**Behavior:** Always makes 2 API calls: `/dimensions/{lang}` + `/lastUpdate`.

---

### 5.2 Dedicated Banking Statistics Tools (in `warehouse.py`)

#### `snb_get_banking_balance_sheet`

Balance sheet totals of the Swiss banking sector by bank group.

**Input model `BankingBalanceSheetInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `side` | Literal["assets", "liabilities", "both"] | no | "both" | Aktiven, Passiven, or both |
| `bank_groups` | list[str] | no | `["A30"]` | Bank group IDs (max 15) |
| `frequency` | Literal["monthly", "annual"] | no | "annual" | MONA_US (monthly) or JAHR_K (annual) |
| `currency` | str | no | "T" (Total) | Currency filter: "T", "CHF", "USD", "EUR", "JPY", "EM" (precious metals), "U" (other) |
| `from_date` | str | no | 5 years ago (YYYY) or 60 months ago (YYYY-MM) depending on frequency | Start date |
| `to_date` | str | no | current | End date |
| `lang` | Language | no | de | |

**Behavior:**
- Builds cube IDs internally:
  - annual: `BSTA.SNB.JAHR_K.BIL.AKT.TOT` / `BSTA.SNB.JAHR_K.BIL.PAS.TOT`
  - monthly: `BSTA.SNB.MONA_US.BIL.AKT.TOT` / `BSTA.SNB.MONA_US.BIL.PAS.TOT`
- For `side="both"`: two API calls, results merged
- Fetches ALL data, then filters client-side by `bank_groups`, `currency`, and KONSOLIDIERUNGSSTUFE=K
- Scale conversion: `scale="3"` (thousands) → divided by 1000 → displayed in **Millionen CHF**
- Markdown summary: table with bank group, latest value, trend

#### `snb_get_banking_income`

Income statement of the Swiss banking sector by bank group.

**Input model `BankingIncomeInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bank_groups` | list[str] | no | `["A30"]` | Bank group IDs (max 15) |
| `from_year` | str | no | 5 years ago | Start year (YYYY). Pattern: `^\d{4}$` |
| `to_year` | str | no | current year | End year (YYYY). Pattern: `^\d{4}$` |
| `lang` | Language | no | de | |

**Behavior:**
- Queries these confirmed EFR cubes (annual only, 5-segment IDs):
  - `BSTA.SNB.JAHR_K.EFR.GER` — Geschaeftsertrag (operating income)
  - `BSTA.SNB.JAHR_K.EFR.GAU` — Geschaeftsaufwand (operating expenses)
  - `BSTA.SNB.JAHR_K.EFR.UER` — Uebriger Ertrag (other income)
  - `BSTA.SNB.JAHR_K.EFR.AAU` — Anderer Aufwand (other expenses)
  - `BSTA.SNB.JAHR_K.EFR.STE` — Steuern (taxes)
  - `BSTA.SNB.JAHR_K.EFR.AEG` — Ausserordentliches Ergebnis
- Makes 6 API calls (one per EFR cube), fetches all data, filters client-side by `bank_groups` and KONSOLIDIERUNGSSTUFE=K
- EFR cubes have only 2 dimensions: `{KONSOLIDIERUNGSSTUFE, BANKENGRUPPE}` — no WAEHRUNG or INLANDAUSLAND
- Scale conversion: `scale="3"` → Millionen CHF
- Markdown summary: table with position, bank group, latest value

**Constant:**
```python
EFR_POSITIONS = {
    "GER": "Geschaeftsertrag",
    "GAU": "Geschaeftsaufwand",
    "UER": "Uebriger Ertrag",
    "AAU": "Anderer Aufwand",
    "STE": "Steuern",
    "AEG": "Ausserordentliches Ergebnis",
}
```

---

### 5.3 Dedicated Balance of Payments Tool (in `server.py`)

#### `snb_get_balance_of_payments`

Swiss balance of payments and international investment position.

**Important:** This tool uses the **Standard Cube API** (`_fetch_snb`), NOT the Warehouse API. It belongs in `server.py` because ZAST warehouse cubes do not exist as direct IDs.

**Input model `BalanceOfPaymentsInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category` | Literal["overview", "iip"] | no | "overview" | `overview` = Zahlungsbilanz-Uebersicht, `iip` = Auslandvermoegen |
| `from_date` | str | no | 5 years ago | Start date (YYYY-QN format, e.g. "2020-Q1") |
| `to_date` | str | no | current | End date |
| `lang` | Language | no | de | |

**Behavior:**
- Maps category to standard cube IDs:
  - `"overview"` → `bopoverq` (Zahlungsbilanz Uebersicht, quarterly)
  - `"iip"` → `auvekomq` (Auslandvermoegen Komponenten, quarterly)
- Uses existing `_fetch_snb` helper (same as Phase 1/2 tools)
- Returns markdown summary + JSON data
- Values are already in the correct unit from the Cube API (no warehouse scale conversion needed)

**Note:** Simplified from the original 4-category design. The standard cube `bopoverq` contains the full BoP overview (Leistungsbilanz, Kapitalkonto, Finanzkonto combined). Separate category selection is not needed.

---

### 5.4 List Tools

#### `snb_list_warehouse_cubes` (in `warehouse.py`)

Static overview of the most important warehouse cube IDs. No API call.

**Output:** Markdown tables grouped by topic:
- BSTA — Bilanz monatlich (MONA_US): `BSTA.SNB.MONA_US.BIL.{AKT|PAS}.TOT`
- BSTA — Bilanz jaehrlich (JAHR_K): `BSTA.SNB.JAHR_K.BIL.{AKT|PAS}.{TOT|HYP|BET|SON|RUE}`
- BSTA — Erfolgsrechnung (EFR): `BSTA.SNB.JAHR_K.EFR.{GER|GAU|UER|AAU|STE|AEG}`

Plus:
- Explanation of the cube ID schema: `THEMA.PROVIDER.FREQUENZ_KONSOLIDIERUNG.KATEGORIE.SEITE.POSITION`
- Dimension order in metadata keys
- Pointer to `snb_get_warehouse_metadata` for discovery
- Note about dimSel limitation

#### `snb_list_bank_groups` (in `warehouse.py`)

Static list of all bank group IDs. No API call.

**Constants `BANK_GROUPS` (verified from live API):**

| ID | Label |
|----|-------|
| `A30` | Banken in der Schweiz (alle) |
| `G10` | Kantonalbanken |
| `G15` | Grossbanken |
| `G20` | Regionalbanken und Sparkassen |
| `G25` | Raiffeisenbanken |
| `G35` | Boersenbanken |
| `G45` | Andere Banken |
| `A10` | Privatbankiers |
| `A25` | Auslaendische Banken |
| `G65` | Auslaendisch beherrschte Banken |
| `G70` | Filialen auslaendischer Banken |
| `S10` | Banken in CH ohne Privatbankiers und Auslandfilialen |

---

## 6. Retry Logic (WAF Protection)

The SNB data portal has aggressive WAF protection. After ~100-150 rapid requests, HTTP 503 is returned for 30+ minutes.

**Implementation in `_fetch_warehouse`:**
```python
MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds, exponential backoff

async def _fetch_warehouse(...):
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503 and attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            raise
```

The existing `_fetch_snb` in `server.py` does NOT get retry logic (Phase 1/2 cubes are smaller and less likely to trigger WAF).

---

## 7. Changes to Existing Code

### `server.py`

1. **Add import** at end of file (before `def main()`):
   ```python
   import swiss_snb_mcp.warehouse  # noqa: F401
   ```

2. **Add `snb_get_balance_of_payments` tool** with `BalanceOfPaymentsInput` model (uses `_fetch_snb`)

3. **Add `bopoverq` and `auvekomq`** to the Phase 2 section of `snb_list_known_cubes`, and replace the Phase-3 "Noch nicht unterstuetzt" text with:
   ```
   Phase 3 — Warehouse-API (Bankenstatistik)
   Tools: snb_get_warehouse_data, snb_get_warehouse_metadata,
          snb_get_banking_balance_sheet, snb_get_banking_income,
          snb_list_warehouse_cubes, snb_list_bank_groups
   ```

### `pyproject.toml`

- Version bump: `0.2.0` → `0.3.0`

### `CHANGELOG.md`

- New entry for `[0.3.0]` documenting all Phase 3 additions

---

## 8. Testing

20 new test scenarios in `tests/test_warehouse_scenarios.py`:

| # | Scenario | Tool |
|---|----------|------|
| 1 | Generic warehouse data: BSTA annual total assets | `snb_get_warehouse_data` |
| 2 | Generic warehouse data: BSTA monthly total assets | `snb_get_warehouse_data` |
| 3 | Warehouse metadata: BSTA BIL dimensions | `snb_get_warehouse_metadata` |
| 4 | Warehouse metadata: BSTA EFR dimensions | `snb_get_warehouse_metadata` |
| 5 | Banking balance sheet: annual, all banks, both sides | `snb_get_banking_balance_sheet` |
| 6 | Banking balance sheet: annual, specific bank groups (G10, G15, G25) | `snb_get_banking_balance_sheet` |
| 7 | Banking balance sheet: monthly, assets only | `snb_get_banking_balance_sheet` |
| 8 | Banking balance sheet: liabilities only, CHF filter | `snb_get_banking_balance_sheet` |
| 9 | Banking income: all banks, default range | `snb_get_banking_income` |
| 10 | Banking income: Kantonalbanken vs Grossbanken | `snb_get_banking_income` |
| 11 | Balance of payments: overview (bopoverq) | `snb_get_balance_of_payments` |
| 12 | Balance of payments: IIP (auvekomq) | `snb_get_balance_of_payments` |
| 13 | Balance of payments: French language | `snb_get_balance_of_payments` |
| 14 | List warehouse cubes | `snb_list_warehouse_cubes` |
| 15 | List bank groups | `snb_list_bank_groups` |
| 16 | Invalid warehouse cube ID → error | `snb_get_warehouse_data` |
| 17 | Banking balance sheet in English | `snb_get_banking_balance_sheet` |
| 18 | Banking income in French | `snb_get_banking_income` |
| 19 | Scale conversion plausibility (value in Mio. CHF range) | `snb_get_banking_balance_sheet` |
| 20 | Warehouse retry on 503 (mock or integration) | `snb_get_warehouse_data` |

---

## 9. Summary of New Tools

| # | Tool | Location | Type | API Used |
|---|------|----------|------|----------|
| 1 | `snb_get_warehouse_data` | warehouse.py | Generic | Warehouse API |
| 2 | `snb_get_warehouse_metadata` | warehouse.py | Generic | Warehouse API (2 calls) |
| 3 | `snb_get_banking_balance_sheet` | warehouse.py | Dedicated | Warehouse API (1-2 calls + client filter) |
| 4 | `snb_get_banking_income` | warehouse.py | Dedicated | Warehouse API (6 calls + client filter) |
| 5 | `snb_get_balance_of_payments` | server.py | Dedicated | Standard Cube API |
| 6 | `snb_list_warehouse_cubes` | warehouse.py | List (static) | None |
| 7 | `snb_list_bank_groups` | warehouse.py | List (static) | None |

**Total new tools:** 7
**Total tools after Phase 3:** 16 (9 existing + 7 new)

---

## Appendix A: Resolved Review Blockers

| Blocker | Resolution |
|---------|-----------|
| B1: Cube ID separator `@` vs `.` | **`.` in URLs**, `@` only in internal metadata keys. Regex `^[A-Z][A-Z0-9_.]+$` is correct. |
| B2: Import order / circular dependency | Import placed at end of server.py. warehouse.py only imports module-level constants. Documented as constraint. |
| B3: Unresolved EFR + ZAST cube IDs | EFR confirmed (6 cubes, 5-segment). ZAST does not exist as warehouse — BoP moved to standard Cube API (`bopoverq`, `auvekomq`). |
| B4: JSON vs XML response | JSON returned when `/json/` is in path. No Accept header needed. Confirmed via live testing. |
| B5: Endpoint paths unknown | Confirmed: `/data/json/{lang}`, `/dimensions/{lang}`, `/lastUpdate`. |

## Appendix B: Resolved Review Improvements

| Improvement | Resolution |
|-------------|-----------|
| I1: Scale labels German-only | Accepted — consistent with existing German-first pattern. |
| I2: bank_groups max=12 | Raised to max=15 for future-proofing. |
| I3: dim_sel dict serialization | Removed dim_sel from input model entirely. Client-side filtering instead. |
| I4: Missing ConfigDict | Added to spec — all models use `ConfigDict(str_strip_whitespace=True, extra="forbid")`. |
| I5: `@` vs `.` in existing code | Will be corrected in snb_list_known_cubes update. |
| I6: Metadata 1-2 calls ambiguous | Clarified: always 2 calls (dimensions + lastUpdate). |
| I7: Missing annotations | Added — all tools follow existing annotation pattern. |
| I8: Monthly bank group limitation | Removed monthly bank group restriction. All data fetched and filtered client-side. |
