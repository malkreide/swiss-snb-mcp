# Phase 3: SNB Warehouse API — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 7 new MCP tools for SNB Warehouse API access (banking statistics, income statement) and standard Cube API balance of payments — bringing the total from 9 to 16 tools.

**Architecture:** Modular split — new `warehouse.py` module for Warehouse API tools, balance of payments added to existing `server.py`. The two modules share a single `mcp` FastMCP instance. Client-side filtering replaces broken `dimSel`. Retry with exponential backoff for WAF 503 errors.

**Tech Stack:** Python 3.11+, FastMCP, httpx, Pydantic v2

**Spec:** `docs/superpowers/specs/2026-04-01-phase3-warehouse-api-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/swiss_snb_mcp/warehouse.py` | **CREATE** | Warehouse API HTTP helper, constants (BANK_GROUPS, EFR_POSITIONS, SCALE), input models, 6 tools: `snb_get_warehouse_data`, `snb_get_warehouse_metadata`, `snb_get_banking_balance_sheet`, `snb_get_banking_income`, `snb_list_warehouse_cubes`, `snb_list_bank_groups` |
| `src/swiss_snb_mcp/server.py` | **MODIFY** | Add `BalanceOfPaymentsInput` model, `snb_get_balance_of_payments` tool, update `snb_list_known_cubes`, add `import swiss_snb_mcp.warehouse` |
| `tests/test_warehouse_scenarios.py` | **CREATE** | 20 integration test scenarios against live Warehouse API |
| `pyproject.toml` | **MODIFY** | Version bump 0.2.0 → 0.3.0 |
| `CHANGELOG.md` | **MODIFY** | Add [0.3.0] entry |

---

## Chunk 1: Foundation — Constants, HTTP Helper, and Static List Tools

### Task 1: Create `warehouse.py` with constants and imports

**Files:**
- Create: `src/swiss_snb_mcp/warehouse.py`

- [ ] **Step 1: Create warehouse.py with module docstring, imports, and all constants**

```python
"""
SNB Warehouse API tools for swiss-snb-mcp.
Provides access to granular banking statistics (BSTA) via the
Warehouse REST API at data.snb.ch/api/warehouse/cube/.
"""

import asyncio
import json
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field, ConfigDict

from swiss_snb_mcp.server import mcp, Language, _handle_http_error, DEFAULT_TIMEOUT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAREHOUSE_BASE_URL = "https://data.snb.ch/api/warehouse/cube"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds, exponential backoff

BANK_GROUPS = {
    "A30": "Banken in der Schweiz (alle)",
    "G10": "Kantonalbanken",
    "G15": "Grossbanken",
    "G20": "Regionalbanken und Sparkassen",
    "G25": "Raiffeisenbanken",
    "G35": "Börsenbanken",
    "G45": "Andere Banken",
    "A10": "Privatbankiers",
    "A25": "Ausländische Banken",
    "G65": "Ausländisch beherrschte Banken",
    "G70": "Filialen ausländischer Banken",
    "S10": "Banken in CH ohne Privatbankiers und Auslandfilialen",
}

EFR_POSITIONS = {
    "GER": "Geschäftsertrag",
    "GAU": "Geschäftsaufwand",
    "UER": "Übriger Ertrag",
    "AAU": "Anderer Aufwand",
    "STE": "Steuern",
    "AEG": "Ausserordentliches Ergebnis",
}

SCALE_FACTORS = {"0": 1, "3": 1_000, "6": 1_000_000, "9": 1_000_000_000}

SCALE_LABELS = {
    "0": "Einheiten",
    "3": "1'000 CHF",
    "6": "Millionen CHF",
    "9": "Milliarden CHF",
}

# Dimension order in metadata keys for known cube types
# Key format: BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}
BIL_DIM_ORDER = ["KONSOLIDIERUNGSSTUFE", "INLANDAUSLAND", "WAEHRUNG", "BANKENGRUPPE"]
EFR_DIM_ORDER = ["KONSOLIDIERUNGSSTUFE", "BANKENGRUPPE"]
```

- [ ] **Step 2: Verify the import works**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python -c "from swiss_snb_mcp.warehouse import BANK_GROUPS; print(len(BANK_GROUPS))"`
Expected: `12`

- [ ] **Step 3: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py
git commit -m "feat: add warehouse.py with constants and imports"
```

---

### Task 2: Implement `_fetch_warehouse` HTTP helper with retry logic

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Create: `tests/test_warehouse_scenarios.py` (test runner scaffold + test 16)

- [ ] **Step 1: Write test scaffold and the error-handling test (test 16)**

Create `tests/test_warehouse_scenarios.py` with the same structure as `tests/test_scenarios.py` (import helper, run_test function, UTF-8 fix).

**Important: Test file imports** must include both warehouse and server modules:
```python
from swiss_snb_mcp.warehouse import (
    snb_get_warehouse_data, snb_get_warehouse_metadata,
    snb_get_banking_balance_sheet, snb_get_banking_income,
    snb_list_warehouse_cubes, snb_list_bank_groups,
    WarehouseDataInput, WarehouseMetadataInput,
    BankingBalanceSheetInput, BankingIncomeInput,
    _fetch_warehouse,
)
from swiss_snb_mcp.server import (
    snb_get_balance_of_payments, BalanceOfPaymentsInput, Language,
)
import httpx  # needed for test 20 mock
```

Add test 16:

```python
async def test_16_invalid_cube_id():
    """Scenario 16: Invalid warehouse cube ID -> error."""
    await run_test(
        "16 - Ungueltige Warehouse Cube-ID -> Fehler",
        snb_get_warehouse_data(WarehouseDataInput(
            cube_id="INVALID.CUBE.ID.DOES.NOT.EXIST",
        )),
        checks=["__ERROR__"],
    )
```

- [ ] **Step 2: Implement `_fetch_warehouse` with retry logic**

Add to `warehouse.py` after the constants:

```python
async def _fetch_warehouse(
    cube_id: str,
    endpoint: str,
    lang: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Fetch data from the SNB Warehouse REST API with retry on 503."""
    url = f"{WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}"
    params: dict = {}
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await client.get(url, params=params or None)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 503 and attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                raise
    # Unreachable, but satisfies type checker
    raise RuntimeError("Retry loop exited unexpectedly")
```

- [ ] **Step 3: Add `_scale_to_millions` and `_filter_timeseries` helpers**

```python
def _scale_to_millions(value: float, scale: str) -> float:
    """Convert a warehouse raw value to millions."""
    factor = SCALE_FACTORS.get(scale, 1)
    return (value * factor) / 1_000_000


def _filter_timeseries(
    timeseries: list[dict],
    dim_order: list[str],
    filters: dict[str, set[str]],
) -> list[dict]:
    """Filter warehouse timeseries by metadata key dimension values.

    The metadata key format is: BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}
    The values in braces correspond to dimensions in dim_order.
    """
    result = []
    for ts in timeseries:
        meta_key = ts.get("metadata", {}).get("key", "")
        # Extract dimension values from braces: {K,T,T,A30} -> ["K","T","T","A30"]
        brace_start = meta_key.find("{")
        brace_end = meta_key.find("}")
        if brace_start == -1 or brace_end == -1:
            continue
        dim_values = meta_key[brace_start + 1 : brace_end].split(",")
        if len(dim_values) != len(dim_order):
            continue

        match = True
        for dim_name, dim_val in zip(dim_order, dim_values):
            if dim_name in filters and dim_val not in filters[dim_name]:
                match = False
                break
        if match:
            result.append(ts)
    return result
```

- [ ] **Step 4: Run test 16 to verify error handling works**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: Test 16 PASSED (gets HTTP 404 → error message)

- [ ] **Step 5: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add _fetch_warehouse with retry logic, scale conversion, and client-side filtering"
```

---

### Task 3: Implement `snb_list_bank_groups` and `snb_list_warehouse_cubes`

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Modify: `tests/test_warehouse_scenarios.py` (add tests 14, 15)

- [ ] **Step 1: Write tests 14 and 15**

```python
async def test_14_list_warehouse_cubes():
    """Scenario 14: List warehouse cubes."""
    await run_test(
        "14 - Warehouse Cubes Uebersicht",
        snb_list_warehouse_cubes(),
        checks=["BSTA.SNB.JAHR_K.BIL.AKT.TOT", "BSTA.SNB.JAHR_K.EFR.GER",
                "MONA_US", "BANKENGRUPPE"],
    )

async def test_15_list_bank_groups():
    """Scenario 15: List bank groups."""
    await run_test(
        "15 - Bankengruppen-Liste",
        snb_list_bank_groups(),
        checks=["A30", "G10", "G15", "G25", "Kantonalbanken", "Grossbanken"],
    )
```

- [ ] **Step 2: Implement `snb_list_bank_groups`**

```python
@mcp.tool(
    name="snb_list_bank_groups",
    annotations={
        "title": "List SNB Bank Groups",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_bank_groups() -> str:
    """List all bank group IDs for the SNB banking statistics (BSTA cubes).

    Returns the complete list of bank group identifiers that can be used
    as filter values in snb_get_banking_balance_sheet and snb_get_banking_income.

    Returns:
        str: Markdown table of bank group IDs and German labels.
    """
    lines = [
        "## SNB Bankengruppen (Warehouse: BSTA-Cubes)\n",
        "| ID | Bezeichnung |",
        "|----|-------------|",
    ]
    for gid, label in BANK_GROUPS.items():
        lines.append(f"| `{gid}` | {label} |")
    lines.append(
        "\n*Verwendung: `bank_groups: ['A30', 'G10']` in "
        "snb_get_banking_balance_sheet / snb_get_banking_income*"
    )
    return "\n".join(lines)
```

- [ ] **Step 3: Implement `snb_list_warehouse_cubes`**

```python
@mcp.tool(
    name="snb_list_warehouse_cubes",
    annotations={
        "title": "List SNB Warehouse Cubes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_warehouse_cubes() -> str:
    """List the most important SNB Warehouse cube IDs with descriptions.

    The Warehouse API at data.snb.ch/api/warehouse/cube/ hosts granular
    banking statistics not available through the standard Cube API.
    Cube IDs are uppercase, dot-separated hierarchical identifiers.

    Returns:
        str: Markdown tables of warehouse cube IDs grouped by category,
             plus cube ID schema explanation and discovery guidance.
    """
    lines = [
        "## SNB Warehouse Cubes\n",
        "### BSTA — Bilanz (BIL)",
        "| Cube-ID | Beschreibung | Frequenz |",
        "|---------|-------------|----------|",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.TOT` | Total Aktiven (jährlich, konsolidiert) | jährlich |",
        "| `BSTA.SNB.JAHR_K.BIL.PAS.TOT` | Total Passiven (jährlich, konsolidiert) | jährlich |",
        "| `BSTA.SNB.MONA_US.BIL.AKT.TOT` | Total Aktiven (monatlich) | monatlich |",
        "| `BSTA.SNB.MONA_US.BIL.PAS.TOT` | Total Passiven (monatlich) | monatlich |",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.HYP` | Hypothekarforderungen | jährlich |",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.BET` | Beteiligungen | jährlich |",
        "\n### BSTA — Erfolgsrechnung (EFR)",
        "| Cube-ID | Beschreibung | Frequenz |",
        "|---------|-------------|----------|",
        "| `BSTA.SNB.JAHR_K.EFR.GER` | Geschäftsertrag | jährlich |",
        "| `BSTA.SNB.JAHR_K.EFR.GAU` | Geschäftsaufwand | jährlich |",
        "| `BSTA.SNB.JAHR_K.EFR.UER` | Übriger Ertrag | jährlich |",
        "| `BSTA.SNB.JAHR_K.EFR.AAU` | Anderer Aufwand | jährlich |",
        "| `BSTA.SNB.JAHR_K.EFR.STE` | Steuern | jährlich |",
        "| `BSTA.SNB.JAHR_K.EFR.AEG` | Ausserordentliches Ergebnis | jährlich |",
        "\n### Cube-ID-Schema",
        "`THEMA.PROVIDER.FREQUENZ_KONSOLIDIERUNG.KATEGORIE.SEITE.POSITION`",
        "- **THEMA:** BSTA (Bankenstatistik)",
        "- **PROVIDER:** SNB",
        "- **FREQUENZ:** JAHR_K (jährlich, konsolidiert), MONA_US (monatlich, unkonsolidiert)",
        "- **KATEGORIE:** BIL (Bilanz), EFR (Erfolgsrechnung)",
        "- **SEITE:** AKT (Aktiven), PAS (Passiven) — nur bei BIL",
        "- **POSITION:** TOT (Total), HYP (Hypotheken), BET (Beteiligungen), etc.",
        "\n### Dimensionen",
        "**BIL-Cubes:** KONSOLIDIERUNGSSTUFE, INLANDAUSLAND, WAEHRUNG, BANKENGRUPPE",
        "**EFR-Cubes:** KONSOLIDIERUNGSSTUFE, BANKENGRUPPE",
        "\n### Hinweise",
        "- `dimSel`-Parameter ist auf der Warehouse-API fehlerhaft — dedizierte Tools filtern client-seitig",
        "- Nutzung: `snb_get_warehouse_metadata` (Dimensionen) → `snb_get_warehouse_data` (Daten)",
        "- Bankengruppen-IDs: `snb_list_bank_groups`",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests 14 and 15**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: Tests 14, 15 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_list_bank_groups and snb_list_warehouse_cubes"
```

---

## Chunk 2: Generic Warehouse Tools

### Task 4: Implement `snb_get_warehouse_data`

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Modify: `tests/test_warehouse_scenarios.py` (add tests 1, 2)

- [ ] **Step 1: Write tests 1 and 2**

```python
async def test_01_warehouse_data_annual():
    """Scenario 1: Generic warehouse data - BSTA annual total assets."""
    await run_test(
        "01 - Warehouse-Daten: BSTA jaehrlich Total Aktiven",
        snb_get_warehouse_data(WarehouseDataInput(
            cube_id="BSTA.SNB.JAHR_K.BIL.AKT.TOT",
            from_date="2020",
            to_date="2024",
        )),
        checks=["__SUCCESS__", "BSTA.SNB.JAHR_K.BIL.AKT.TOT", "Zeitreihe"],
    )

async def test_02_warehouse_data_monthly():
    """Scenario 2: Generic warehouse data - BSTA monthly total assets."""
    await run_test(
        "02 - Warehouse-Daten: BSTA monatlich Total Aktiven",
        snb_get_warehouse_data(WarehouseDataInput(
            cube_id="BSTA.SNB.MONA_US.BIL.AKT.TOT",
            from_date="2024-01",
            to_date="2024-06",
        )),
        checks=["__SUCCESS__", "BSTA.SNB.MONA_US.BIL.AKT.TOT"],
    )
```

- [ ] **Step 2: Add `WarehouseDataInput` model and `snb_get_warehouse_data` tool**

Input model:
```python
class WarehouseDataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description=(
            "SNB Warehouse cube ID (uppercase, dot-separated), e.g. "
            "'BSTA.SNB.JAHR_K.BIL.AKT.TOT'. "
            "Use snb_list_warehouse_cubes to see confirmed working cube IDs."
        ),
        min_length=5,
        max_length=60,
        pattern=r"^[A-Z][A-Z0-9_.]+$",
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date. Use YYYY for annual cubes, YYYY-MM for monthly.",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date, same format as from_date.",
    )
    lang: Language = Field(default=Language.DE)
```

Tool implementation follows the same pattern as `snb_get_cube_data` in `server.py`: fetch data via `_fetch_warehouse`, wrap in `try/except` calling `_handle_http_error`, build markdown summary of first 5 timeseries, append truncated JSON (max 8000 chars). Add scale label from first timeseries metadata.

- [ ] **Step 3: Run tests 1 and 2**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: Tests 1, 2 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_get_warehouse_data for generic warehouse access"
```

---

### Task 5: Implement `snb_get_warehouse_metadata`

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Modify: `tests/test_warehouse_scenarios.py` (add tests 3, 4)

- [ ] **Step 1: Write tests 3 and 4**

```python
async def test_03_warehouse_metadata_bil():
    """Scenario 3: Warehouse metadata - BSTA BIL dimensions."""
    await run_test(
        "03 - Metadaten: BSTA BIL Dimensionen",
        snb_get_warehouse_metadata(WarehouseMetadataInput(
            cube_id="BSTA.SNB.JAHR_K.BIL.AKT.TOT",
        )),
        checks=["__SUCCESS__", "BANKENGRUPPE", "WAEHRUNG", "Dimension"],
    )

async def test_04_warehouse_metadata_efr():
    """Scenario 4: Warehouse metadata - BSTA EFR dimensions."""
    await run_test(
        "04 - Metadaten: BSTA EFR Dimensionen",
        snb_get_warehouse_metadata(WarehouseMetadataInput(
            cube_id="BSTA.SNB.JAHR_K.EFR.GER",
        )),
        checks=["__SUCCESS__", "BANKENGRUPPE", "Dimension"],
    )
```

- [ ] **Step 2: Add `WarehouseMetadataInput` model and `snb_get_warehouse_metadata` tool**

Input model:
```python
class WarehouseMetadataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description="SNB Warehouse cube ID to inspect.",
        min_length=5,
        max_length=60,
        pattern=r"^[A-Z][A-Z0-9_.]+$",
    )
    lang: Language = Field(default=Language.DE)
```

Tool implementation: Two API calls. Wrap in `try/except` calling `_handle_http_error`. Follow the pattern of `snb_get_cube_metadata` in `server.py`. Include lastUpdate date in the markdown header.

**Call 1 — Dimensions:** Use `_fetch_warehouse(cube_id, "dimensions", lang)`.

**Call 2 — Last Update:** The `/lastUpdate` endpoint does NOT take a language path segment. Do NOT use `_fetch_warehouse` for this. Use a direct httpx call:
```python
async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
    last_update_url = f"{WAREHOUSE_BASE_URL}/{params.cube_id}/lastUpdate"
    try:
        lu_resp = await client.get(last_update_url)
        lu_resp.raise_for_status()
        lu_data = lu_resp.json()
        edition_date = lu_data.get("editionDate", "unbekannt")
    except Exception:
        edition_date = "nicht verfügbar"
```

- [ ] **Step 3: Run tests 3 and 4**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: Tests 3, 4 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_get_warehouse_metadata with lastUpdate support"
```

---

## Chunk 3: Dedicated Banking Statistics Tools

### Task 6: Implement `snb_get_banking_balance_sheet`

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Modify: `tests/test_warehouse_scenarios.py` (add tests 5, 6, 7, 8, 17, 19)

- [ ] **Step 1: Write tests 5, 6, 7, 8**

```python
async def test_05_banking_bs_annual_both():
    """Scenario 5: Banking balance sheet - annual, all banks, both sides."""
    await run_test(
        "05 - Bankbilanz: jaehrlich, alle Banken, beidseitig",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput()),
        checks=["__SUCCESS__", "Millionen CHF", "A30"],
    )

async def test_06_banking_bs_specific_groups():
    """Scenario 6: Banking balance sheet - specific bank groups."""
    await run_test(
        "06 - Bankbilanz: Kantonalbanken, Grossbanken, Raiffeisen",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            bank_groups=["G10", "G15", "G25"],
            side="assets",
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )

async def test_07_banking_bs_monthly():
    """Scenario 7: Banking balance sheet - monthly, assets only."""
    await run_test(
        "07 - Bankbilanz: monatlich, Aktiven",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            frequency="monthly",
            side="assets",
            from_date="2024-01",
            to_date="2024-06",
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )

async def test_08_banking_bs_liabilities_chf():
    """Scenario 8: Banking balance sheet - liabilities, CHF filter."""
    await run_test(
        "08 - Bankbilanz: Passiven, nur CHF",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            side="liabilities",
            currency="CHF",
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )
```

- [ ] **Step 2: Write tests 17 (English) and 19 (scale plausibility)**

```python
async def test_17_banking_bs_english():
    """Scenario 17: Banking balance sheet in English."""
    await run_test(
        "17 - Bankbilanz auf Englisch",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            lang=Language.EN,
            side="assets",
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )

async def test_19_scale_plausibility():
    """Scenario 19: Scale conversion plausibility check.
    Total assets of all Swiss banks should be in the range of 2-5 trillion CHF
    = 2'000'000 - 5'000'000 Mio. CHF."""
    await run_test(
        "19 - Scale-Plausibilitaet (Gesamtaktiven 2-5 Bio. CHF)",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            side="assets",
            from_date="2023",
            to_date="2023",
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )
```

Note: Test 19 is a soft plausibility check — verify the output visually to confirm values are in the millions (not thousands or billions) range for total bank assets.

- [ ] **Step 3: Add `BankingBalanceSheetInput` model**

```python
class BankingBalanceSheetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    side: Literal["assets", "liabilities", "both"] = Field(
        default="both",
        description="Balance sheet side: 'assets', 'liabilities', or 'both'.",
    )
    bank_groups: Optional[list[str]] = Field(
        default=None,
        description=(
            "Bank group IDs, e.g. ['A30', 'G10', 'G15']. "
            "Use snb_list_bank_groups for all valid IDs. Default: ['A30'] (all banks)."
        ),
        max_length=15,
    )
    frequency: Literal["annual", "monthly"] = Field(
        default="annual",
        description="Data frequency: 'annual' (JAHR_K) or 'monthly' (MONA_US).",
    )
    currency: str = Field(
        default="T",
        description="Currency filter: 'T' (Total), 'CHF', 'USD', 'EUR', 'JPY', 'EM', 'U'.",
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date. YYYY for annual, YYYY-MM for monthly. Default: 5 years / 60 months ago.",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date, same format as from_date.",
    )
    lang: Language = Field(default=Language.DE)
```

- [ ] **Step 4: Implement `snb_get_banking_balance_sheet` tool**

Key implementation logic (entire tool body wrapped in `try/except` calling `_handle_http_error`):
1. Determine frequency prefix: `"annual"` → `"JAHR_K"`, `"monthly"` → `"MONA_US"`
2. Build cube IDs based on `side`: assets → `BSTA.SNB.{freq}.BIL.AKT.TOT`, liabilities → `...PAS.TOT`, both → fetch both and merge
3. Fetch full data via `_fetch_warehouse(cube_id, "data/json", lang, from_date, to_date)`
4. Apply client-side filter via `_filter_timeseries` with `BIL_DIM_ORDER`:
   - `KONSOLIDIERUNGSSTUFE`: `{"K"}` (consolidated)
   - `WAEHRUNG`: `{params.currency.upper()}`
   - `BANKENGRUPPE`: `set(params.bank_groups or ["A30"])`
5. For each matching timeseries: extract scale from metadata, convert values via `_scale_to_millions`
6. Build markdown summary table + JSON output

- [ ] **Step 5: Run tests 5, 6, 7, 8, 17, 19**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: All PASSED

- [ ] **Step 6: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_get_banking_balance_sheet with client-side filtering"
```

---

### Task 7: Implement `snb_get_banking_income`

**Files:**
- Modify: `src/swiss_snb_mcp/warehouse.py`
- Modify: `tests/test_warehouse_scenarios.py` (add tests 9, 10, 18)

- [ ] **Step 1: Write tests 9, 10, 18**

```python
async def test_09_banking_income_default():
    """Scenario 9: Banking income - all banks, default range."""
    await run_test(
        "09 - Erfolgsrechnung: alle Banken",
        snb_get_banking_income(BankingIncomeInput()),
        checks=["__SUCCESS__", "Millionen CHF", "Geschäftsertrag"],
    )

async def test_10_banking_income_comparison():
    """Scenario 10: Banking income - Kantonalbanken vs Grossbanken."""
    await run_test(
        "10 - Erfolgsrechnung: Kantonalbanken vs Grossbanken",
        snb_get_banking_income(BankingIncomeInput(
            bank_groups=["G10", "G15"],
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )

async def test_18_banking_income_french():
    """Scenario 18: Banking income in French."""
    await run_test(
        "18 - Erfolgsrechnung auf Franzoesisch",
        snb_get_banking_income(BankingIncomeInput(
            lang=Language.FR,
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )
```

- [ ] **Step 2: Add `BankingIncomeInput` model**

```python
class BankingIncomeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    bank_groups: Optional[list[str]] = Field(
        default=None,
        description=(
            "Bank group IDs. Default: ['A30'] (all banks). "
            "Use snb_list_bank_groups for valid IDs."
        ),
        max_length=15,
    )
    from_year: Optional[str] = Field(
        default=None,
        description="Start year (YYYY). Default: 5 years ago.",
        pattern=r"^\d{4}$",
    )
    to_year: Optional[str] = Field(
        default=None,
        description="End year (YYYY). Default: current year.",
        pattern=r"^\d{4}$",
    )
    lang: Language = Field(default=Language.DE)
```

- [ ] **Step 3: Implement `snb_get_banking_income` tool**

Key implementation logic:
1. Loop over `EFR_POSITIONS` dict (6 entries: GER, GAU, UER, AAU, STE, AEG)
2. For each: fetch `BSTA.SNB.JAHR_K.EFR.{pos_id}` via `_fetch_warehouse`
3. Filter client-side via `_filter_timeseries` with `EFR_DIM_ORDER`:
   - `KONSOLIDIERUNGSSTUFE`: `{"K"}`
   - `BANKENGRUPPE`: `set(params.bank_groups or ["A30"])`
4. Scale conversion: `_scale_to_millions(value, scale)`
5. Build markdown: table with columns Position | Bankengruppe | Letzter Wert | Jahr
6. Handle individual cube failures gracefully: wrap each cube fetch in its own `try/except`, log a warning line in the output (e.g. "⚠ BSTA.SNB.JAHR_K.EFR.AEG: nicht verfügbar"), continue with remaining cubes
7. Outer function body also wrapped in `try/except` calling `_handle_http_error` for unexpected errors

- [ ] **Step 4: Run tests 9, 10, 18**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add src/swiss_snb_mcp/warehouse.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_get_banking_income for income statement by bank group"
```

---

## Chunk 4: Balance of Payments + server.py Integration

### Task 8: Implement `snb_get_balance_of_payments` in server.py

**Files:**
- Modify: `src/swiss_snb_mcp/server.py` (add BalanceOfPaymentsInput + tool)
- Modify: `tests/test_warehouse_scenarios.py` (add tests 11, 12, 13)

- [ ] **Step 1: Write tests 11, 12, 13**

```python
async def test_11_bop_overview():
    """Scenario 11: Balance of payments - overview."""
    await run_test(
        "11 - Zahlungsbilanz: Uebersicht (bopoverq)",
        snb_get_balance_of_payments(BalanceOfPaymentsInput(
            category="overview",
        )),
        checks=["__SUCCESS__", "bopoverq"],
    )

async def test_12_bop_iip():
    """Scenario 12: Balance of payments - IIP."""
    await run_test(
        "12 - Auslandvermoegen (auvekomq)",
        snb_get_balance_of_payments(BalanceOfPaymentsInput(
            category="iip",
        )),
        checks=["__SUCCESS__", "auvekomq"],
    )

async def test_13_bop_french():
    """Scenario 13: Balance of payments - French language."""
    await run_test(
        "13 - Zahlungsbilanz auf Franzoesisch",
        snb_get_balance_of_payments(BalanceOfPaymentsInput(
            category="overview",
            lang=Language.FR,
        )),
        checks=["__SUCCESS__"],
    )
```

- [ ] **Step 2: Add `BalanceOfPaymentsInput` model to server.py**

Add after `CubeMetadataInput` class in `server.py` (search for `class CubeMetadataInput`):

```python
class BalanceOfPaymentsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    category: Literal["overview", "iip"] = Field(
        default="overview",
        description=(
            "Balance of payments category: "
            "'overview' (Zahlungsbilanz, cube bopoverq) or "
            "'iip' (Auslandvermögen, cube auvekomq)."
        ),
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date, e.g. '2020-Q1' or '2020'. Default: 5 years ago.",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date, same format as from_date.",
    )
    lang: Language = Field(default=Language.DE)
```

- [ ] **Step 3: Implement `snb_get_balance_of_payments` tool in server.py**

Add after the `snb_get_cube_metadata` tool in `server.py` (search for `async def snb_get_cube_metadata`). Implementation follows the pattern of `snb_get_cube_data` — maps category to cube ID, calls `_fetch_snb`, wraps in `try/except` with `_handle_http_error`, builds markdown + JSON:

```python
BOP_CUBES = {
    "overview": ("bopoverq", "Zahlungsbilanz — Übersicht (Quartalsdaten)"),
    "iip": ("auvekomq", "Auslandvermögen — Komponenten (Quartalsdaten)"),
}
```

- [ ] **Step 4: Run tests 11, 12, 13**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add src/swiss_snb_mcp/server.py tests/test_warehouse_scenarios.py
git commit -m "feat: add snb_get_balance_of_payments using standard Cube API"
```

---

### Task 9: Update `snb_list_known_cubes` and add warehouse import

**Files:**
- Modify: `src/swiss_snb_mcp/server.py`

- [ ] **Step 1: Add `bopoverq` and `auvekomq` to the Phase 2 cubes list in `snb_list_known_cubes`**

In the `known_cubes` list inside `snb_list_known_cubes`, add these two entries **after the last Phase 2 entry (`snbmonagg`)** — they will be at the end of the list, just before the `]` closing bracket:

```python
        # ── Phase 3: Zahlungsbilanz (Standard-Cube-API) ──────────────────────
        {
            "id": "bopoverq",
            "description": "Zahlungsbilanz — Übersicht (Leistungs-, Kapital-, Finanzkonto)",
            "tool": "snb_get_balance_of_payments",
            "frequency": "quartalsweise",
            "from": "2000",
        },
        {
            "id": "auvekomq",
            "description": "Auslandvermögen — Komponenten (Direktinvestitionen, Portfolio, Derivate)",
            "tool": "snb_get_balance_of_payments",
            "frequency": "quartalsweise",
            "from": "2000",
        },
```

These cubes have their own dedicated tool (`snb_get_balance_of_payments`), so the existing filter `c["tool"] != "snb_get_cube_data"` will automatically place them in the Phase 1 table. This is correct — they show up alongside other cubes with dedicated tools. No filter changes needed.

- [ ] **Step 2: Replace the Phase 3 "Noch nicht unterstützt" section**

In `server.py`, find the Phase 3 block inside `snb_list_known_cubes` (search for `"Phase 3 — Noch nicht unterstützt"`) and replace these 4 lines:
```python
"\n**Phase 3 — Noch nicht unterstützt:**",
"Die detaillierte Bankenstatistik (Bilanzsumme, Kreditvolumen nach Bankengruppe)",
"liegt im Warehouse-API unter `/api/warehouse/cube/BSTA@SNB…` mit eigener Filtersprache.",
"Direkte Abfrage via `snb_get_cube_data` ist noch nicht möglich.",
```

With:
```python
"\n**Phase 3 — Warehouse-API (Bankenstatistik)**",
"Detaillierte Bankenstatistik nach Bankengruppe via Warehouse-API:",
"- `snb_get_banking_balance_sheet` — Bankbilanzen (Aktiven/Passiven, monatlich/jährlich)",
"- `snb_get_banking_income` — Erfolgsrechnung (Geschäftsertrag/-aufwand, jährlich)",
"- `snb_get_warehouse_data` / `snb_get_warehouse_metadata` — Generischer Zugang",
"- `snb_list_warehouse_cubes` / `snb_list_bank_groups` — Übersicht und Referenz",
```

- [ ] **Step 3: Add warehouse import before `def main()`**

Add at the end of `server.py`, just before the `def main():` function:

```python
# ---------------------------------------------------------------------------
# Phase 3: Warehouse API tools (side-effect import — registers tools on mcp)
# ---------------------------------------------------------------------------

import swiss_snb_mcp.warehouse  # noqa: F401
```

- [ ] **Step 4: Verify the full server loads correctly**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python -c "from swiss_snb_mcp.server import mcp; tools = mcp.list_tools() if hasattr(mcp, 'list_tools') else list(mcp._tools.values()); print(f'{len(tools)} tools registered')"`
Expected: `16 tools registered` (9 original + 7 new)

- [ ] **Step 5: Commit**

```bash
git add src/swiss_snb_mcp/server.py
git commit -m "feat: update snb_list_known_cubes for Phase 3 and add warehouse import"
```

---

## Chunk 5: Full Test Suite, Version Bump, and Changelog

### Task 10: Finalize test file and add test 20

**Files:**
- Modify: `tests/test_warehouse_scenarios.py` (add test 20, wire up main runner)

- [ ] **Step 1: Add test 20 (retry / WAF scenario)**

Test 20 validates retry logic via a unit test with mocked httpx responses:

```python
async def test_20_retry_logic():
    """Scenario 20: Verify _fetch_warehouse retries on HTTP 503."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from swiss_snb_mcp.warehouse import _fetch_warehouse

    # Mock httpx to return 503 twice, then 200
    mock_response_503 = MagicMock()
    mock_response_503.status_code = 503
    mock_response_503.raise_for_status.side_effect = httpx.HTTPStatusError(
        "503", request=MagicMock(), response=mock_response_503
    )

    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.raise_for_status.return_value = None
    mock_response_200.json.return_value = {"timeseries": []}

    call_count = 0
    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return mock_response_503
        return mock_response_200

    try:
        with patch("swiss_snb_mcp.warehouse.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # Patch asyncio.sleep to not actually wait
            with patch("swiss_snb_mcp.warehouse.asyncio.sleep", new_callable=AsyncMock):
                result = await _fetch_warehouse("BSTA.SNB.JAHR_K.BIL.AKT.TOT", "data/json", "de")

        assert call_count == 3, f"Expected 3 calls (2 retries + 1 success), got {call_count}"
        assert result == {"timeseries": []}
        PASSED_COUNT_HERE  # increment global PASSED
        print(f"  OK: Retry logic works (503 -> 503 -> 200, {call_count} calls)")
        print(f"\n→ PASSED ✓")
    except Exception as e:
        FAILED_COUNT_HERE  # increment global FAILED
        print(f"  FAIL: {e}")
        print(f"\n→ FAILED ✗")
```

Note: This is a unit test with mocks, not an integration test. Adjust the global counter variable names to match the test runner's `PASSED`/`FAILED` globals.

- [ ] **Step 2: Wire up all 20 tests in the `main()` runner function**

Ensure all test functions are called in order in `main()`, matching the pattern from `tests/test_scenarios.py`.

- [ ] **Step 3: Run the full test suite**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: 20/20 PASSED (or close — note WAF may block after many requests)

**IMPORTANT:** If WAF triggers during the test run, wait 30+ minutes and re-run. Consider running tests in smaller batches to avoid rate limiting.

- [ ] **Step 4: Commit**

```bash
git add tests/test_warehouse_scenarios.py
git commit -m "test: complete 20 warehouse integration test scenarios"
```

---

### Task 11: Version bump and changelog

**Files:**
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Bump version in `pyproject.toml`**

Change `version = "0.2.0"` to `version = "0.3.0"`.

- [ ] **Step 2: Add changelog entry**

Add after `## [Unreleased]` in `CHANGELOG.md`:

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "chore: bump version to 0.3.0 and update changelog for Phase 3"
```

---

### Task 12: Run existing Phase 1/2 tests to verify no regressions

**Files:** None modified — verification only.

- [ ] **Step 1: Run the original test suite**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_scenarios.py`
Expected: 20/20 PASSED (no regressions from server.py changes)

- [ ] **Step 2: Run the new warehouse test suite**

Run: `cd /c/Users/hayal/swiss-snb-mcp && python tests/test_warehouse_scenarios.py`
Expected: 20/20 PASSED

- [ ] **Step 3: Verify the package installs cleanly**

Run: `cd /c/Users/hayal/swiss-snb-mcp && pip install -e . 2>&1 | tail -3`
Expected: `Successfully installed swiss-snb-mcp-0.3.0`

- [ ] **Step 4: Push all commits**

Run: `cd /c/Users/hayal/swiss-snb-mcp && git push`
Expected: All commits pushed to origin/main
