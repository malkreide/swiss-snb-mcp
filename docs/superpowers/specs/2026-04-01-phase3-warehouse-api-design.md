# Phase 3: SNB Warehouse API Integration

**Date:** 2026-04-01
**Status:** Approved
**Scope:** Maximaler Umfang — generischer Warehouse-Zugang + dedizierte Tools fuer Bankenstatistik und Zahlungsbilanz

---

## 1. Background

The swiss-snb-mcp server currently supports two tiers of SNB data:

- **Phase 1:** Dedicated tools for exchange rates (monthly/annual) and SNB balance sheet via the standard Cube API (`/api/cube/`)
- **Phase 2:** Generic cube access for policy rates, SARON, money market rates, central bank rate comparisons, and monetary aggregates

Phase 3 extends the server to the **SNB Warehouse API** (`/api/warehouse/cube/`), which hosts granular statistical datasets not available through the standard Cube API:

- **BSTA** — Swiss banking statistics (balance sheet, income statement by bank group)
- **ZAST** — Balance of payments and international investment position
- **BIZ** — BIS derivatives statistics
- **SNB1A** — SNB monetary policy warehouse data

### Key Differences: Cube API vs Warehouse API

| Feature | Standard `/api/cube/` | Warehouse `/api/warehouse/cube/` |
|---|---|---|
| Cube ID format | Lowercase, short (`devkum`) | Uppercase, dot-hierarchical (`BSTA.SNB.MONA_US.BIL.AKT.TOT`) |
| Dimension IDs | Generic (`D0`, `D1`) | Semantic (`BANKENGRUPPE`, `WAEHRUNG`) |
| Dimension filter | Not supported (all returned) | `dimSel=WAEHRUNG(T,CHF),BANKENGRUPPE(A30)` |
| Granularity | Pre-aggregated tables | Individual positions with multi-dimensional breakdowns |
| Scale | Values directly in stated unit | `metadata.scale` field (e.g. `"3"` = thousands) |
| Number of cubes | ~10-20 | Hundreds |

---

## 2. Architecture

### Approach: Modular Split (Ansatz B)

```
src/swiss_snb_mcp/
  __init__.py          (unchanged)
  server.py            (unchanged — Phase 1/2 tools + mcp instance)
  warehouse.py         (NEW — Phase 3 tools)
```

**`warehouse.py`** imports from `server.py`:
- `mcp` — the FastMCP instance (registers new tools on it)
- `Language` — Enum for de/en/fr
- `_handle_http_error` — error handling
- `DEFAULT_TIMEOUT` — HTTP timeout

**`server.py`** gets one addition at the end:
```python
import swiss_snb_mcp.warehouse  # noqa: F401 — registers Warehouse tools on mcp
```

**Rationale:** The two API systems (Cube vs Warehouse) are conceptually different enough to warrant separate modules. The existing `server.py` remains untouched except for the import line and an update to the Phase-3 note in `snb_list_known_cubes`.

---

## 3. HTTP Helper

New function in `warehouse.py`:

```python
WAREHOUSE_BASE_URL = "https://data.snb.ch/api/warehouse/cube"

async def _fetch_warehouse(
    cube_id: str,
    endpoint: str,
    lang: str,
    dim_sel: dict[str, list[str]] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
```

- Builds URL: `{WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}`
- Builds `dimSel` query parameter from dict: `{"WAEHRUNG": ["T", "CHF"]}` becomes `WAEHRUNG(T,CHF)`
- Passes `fromDate` / `toDate` as query params
- Uses `httpx.AsyncClient` with `DEFAULT_TIMEOUT`
- Raises on HTTP errors (handled by `_handle_http_error`)

### Cube ID Validation

Warehouse cube IDs must match: `^[A-Z][A-Z0-9_.]+$`
(uppercase letters, digits, dots, underscores — e.g. `BSTA.SNB.JAHR_K.BIL.AKT.TOT`)

---

## 4. Scale Conversion

Helper function:

```python
SCALE_FACTORS = {"0": 1, "3": 1_000, "6": 1_000_000, "9": 1_000_000_000}

def _scale_to_millions(value: float, scale: str) -> float:
    """Convert a warehouse raw value to millions CHF."""
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

---

## 5. Tools

### 5.1 Generic Tools

#### `snb_get_warehouse_data`

Retrieve raw data from any SNB warehouse cube.

**Input model `WarehouseDataInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cube_id` | str | yes | — | Warehouse cube ID, e.g. `BSTA.SNB.MONA_US.BIL.AKT.TOT` |
| `dim_sel` | dict[str, list[str]] | no | None (all) | Dimension filters, e.g. `{"WAEHRUNG": ["T"], "BANKENGRUPPE": ["A30"]}` |
| `from_date` | str | no | None | Start date (YYYY-MM, YYYY, or YYYY-QN) |
| `to_date` | str | no | None | End date |
| `lang` | Language | no | de | Response language |

**Output:**
- Markdown summary: cube ID, number of timeseries, scale label, first 5 series with latest value
- JSON dump (max 8000 chars, truncated with note if larger)
- No automatic scale conversion

#### `snb_get_warehouse_metadata`

Get dimension structure for any warehouse cube.

**Input model `WarehouseMetadataInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `cube_id` | str | yes | — | Warehouse cube ID |
| `lang` | Language | no | de | Response language |

**Output:**
- Markdown listing of all dimensions with their items (IDs and labels)
- Last update date (from `/lastUpdate` endpoint)
- Full JSON dump

---

### 5.2 Dedicated Banking Statistics Tools

#### `snb_get_banking_balance_sheet`

Balance sheet totals of the Swiss banking sector by bank group.

**Input model `BankingBalanceSheetInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `side` | Literal["assets", "liabilities", "both"] | no | "both" | Aktiven, Passiven, or both |
| `bank_groups` | list[str] | no | `["A30"]` | Bank group IDs (max 12) |
| `frequency` | Literal["monthly", "annual"] | no | "annual" | MONA_US (monthly) or JAHR_K (annual) |
| `currency` | str | no | "T" (Total) | Currency filter |
| `from_date` | str | no | 5 years ago | Start date |
| `to_date` | str | no | current | End date |
| `lang` | Language | no | de | |

**Behavior:**
- Builds cube IDs internally:
  - annual: `BSTA.SNB.JAHR_K.BIL.AKT.TOT` / `BSTA.SNB.JAHR_K.BIL.PAS.TOT`
  - monthly: `BSTA.SNB.MONA_US.BIL.AKT.TOT` / `BSTA.SNB.MONA_US.BIL.PAS.TOT`
- For `side="both"`: two API calls, results merged
- `dimSel` built from parameters: `BANKENGRUPPE(A30,G10),WAEHRUNG(T)`
- Monthly cubes only have `BANKENGRUPPE(A40)` — if user requests specific bank groups with monthly frequency, the tool should warn or fall back
- Scale conversion to **Millionen CHF**
- Markdown summary: table with bank group, latest value, trend

#### `snb_get_banking_income`

Income statement of the Swiss banking sector by bank group.

**Input model `BankingIncomeInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `bank_groups` | list[str] | no | `["A30"]` | Bank group IDs |
| `from_year` | str | no | 5 years ago | Start year (YYYY) |
| `to_year` | str | no | current year | End year |
| `lang` | Language | no | de | |

**Behavior:**
- Uses `BSTA.SNB.JAHR_K.EFR.*` cubes (annual only)
- Queries key income statement positions (to be discovered via metadata during implementation — likely includes Geschaeftsertrag, Geschaeftsaufwand, Geschaeftserfolg)
- `dimSel`: `BANKENGRUPPE(A30,G10,...)`
- Scale conversion to Millionen CHF

**Note:** The exact EFR cube IDs and available positions need to be confirmed during implementation via `snb_get_warehouse_metadata`. The tool will store a curated map of the most important positions as constants.

---

### 5.3 Dedicated Balance of Payments Tool

#### `snb_get_balance_of_payments`

Swiss balance of payments and international investment position.

**Input model `BalanceOfPaymentsInput`:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `category` | Literal["current_account", "capital_account", "financial_account", "iip"] | yes | — | Which part of the BoP |
| `from_date` | str | no | 5 years ago | Start date (YYYY-QN or YYYY) |
| `to_date` | str | no | current | End date |
| `lang` | Language | no | de | |

**Behavior:**
- Maps `category` to ZAST cube IDs via `ZAST_CATEGORY_MAP` constant
- The exact cube IDs need to be confirmed during implementation via metadata exploration
- Scale conversion to Millionen CHF
- Markdown summary with key positions

**Note:** ZAST cube IDs follow the pattern `ZAST.SNB.IEA.BOPC.{level}.{category}.{position}`. The exact mapping needs to be verified during implementation.

---

### 5.4 List Tools

#### `snb_list_warehouse_cubes`

Static overview of the most important warehouse cube IDs. No API call.

**Output:** Markdown tables grouped by topic:
- BSTA — Bilanz monatlich (MONA_US)
- BSTA — Bilanz jaehrlich (JAHR_K)
- BSTA — Erfolgsrechnung (EFR)
- BSTA — Ausserbilanz (AUR_U)
- ZAST — Zahlungsbilanz
- BIZ — Derivatestatistik

Plus explanation of the cube ID schema and pointer to `snb_get_warehouse_metadata`.

#### `snb_list_bank_groups`

Static list of all bank group IDs. No API call.

**Constants `BANK_GROUPS`:**

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

## 6. Changes to Existing Code

### `server.py`

1. **Add import** at end of file (before `def main()`):
   ```python
   import swiss_snb_mcp.warehouse  # noqa: F401
   ```

2. **Update `snb_list_known_cubes`**: Replace the Phase-3 "Noch nicht unterstuetzt" text with a reference to the new warehouse tools:
   ```
   Phase 3 — Warehouse-API (Bankenstatistik, Zahlungsbilanz)
   → snb_get_warehouse_data, snb_get_warehouse_metadata
   → snb_get_banking_balance_sheet, snb_get_banking_income
   → snb_get_balance_of_payments
   → snb_list_warehouse_cubes, snb_list_bank_groups
   ```

### `pyproject.toml`

- Version bump: `0.2.0` → `0.3.0`

### `CHANGELOG.md`

- New entry for `[0.3.0]` documenting all Phase 3 additions

---

## 7. Testing

20 new test scenarios in `tests/test_warehouse_scenarios.py`:

| # | Scenario | Tool |
|---|----------|------|
| 1 | Generic warehouse data: BSTA monthly total assets | `snb_get_warehouse_data` |
| 2 | Generic warehouse data: ZAST cube | `snb_get_warehouse_data` |
| 3 | Warehouse metadata: BSTA dimensions | `snb_get_warehouse_metadata` |
| 4 | Warehouse metadata: ZAST dimensions | `snb_get_warehouse_metadata` |
| 5 | Banking balance sheet: annual, all banks, both sides | `snb_get_banking_balance_sheet` |
| 6 | Banking balance sheet: annual, specific bank groups (G10, G15, G25) | `snb_get_banking_balance_sheet` |
| 7 | Banking balance sheet: monthly, assets only | `snb_get_banking_balance_sheet` |
| 8 | Banking balance sheet: liabilities only, CHF filter | `snb_get_banking_balance_sheet` |
| 9 | Banking income: all banks, default range | `snb_get_banking_income` |
| 10 | Banking income: Kantonalbanken vs Grossbanken | `snb_get_banking_income` |
| 11 | Balance of payments: current account | `snb_get_balance_of_payments` |
| 12 | Balance of payments: capital account | `snb_get_balance_of_payments` |
| 13 | Balance of payments: financial account | `snb_get_balance_of_payments` |
| 14 | Balance of payments: international investment position | `snb_get_balance_of_payments` |
| 15 | List warehouse cubes | `snb_list_warehouse_cubes` |
| 16 | List bank groups | `snb_list_bank_groups` |
| 17 | Invalid warehouse cube ID → error | `snb_get_warehouse_data` |
| 18 | Banking balance sheet in English | `snb_get_banking_balance_sheet` |
| 19 | Balance of payments in French | `snb_get_balance_of_payments` |
| 20 | Scale conversion plausibility (value in Mio. CHF range) | `snb_get_banking_balance_sheet` |

---

## 8. Summary of New Tools

| # | Tool | Type | API Calls |
|---|------|------|-----------|
| 1 | `snb_get_warehouse_data` | Generic | 1 (data) |
| 2 | `snb_get_warehouse_metadata` | Generic | 1-2 (dimensions + lastUpdate) |
| 3 | `snb_get_banking_balance_sheet` | Dedicated | 1-2 (AKT + PAS) |
| 4 | `snb_get_banking_income` | Dedicated | 1+ (EFR cubes) |
| 5 | `snb_get_balance_of_payments` | Dedicated | 1+ (ZAST cubes) |
| 6 | `snb_list_warehouse_cubes` | List (static) | 0 |
| 7 | `snb_list_bank_groups` | List (static) | 0 |

**Total new tools:** 7
**Total tools after Phase 3:** 16 (9 existing + 7 new)
