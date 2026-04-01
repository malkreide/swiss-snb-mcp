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


# ---------------------------------------------------------------------------
# HTTP helper with retry logic
# ---------------------------------------------------------------------------


async def _fetch_warehouse(
    cube_id: str,
    endpoint: str,
    lang: str = "de",
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    """Fetch data from the SNB Warehouse REST API with retry on 503.

    URL pattern: {WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}
    Query params: fromDate, toDate (optional).

    Retries up to MAX_RETRIES times with exponential backoff on HTTP 503.
    """
    url = f"{WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}"
    params: dict[str, str] = {}
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503 and attempt < MAX_RETRIES - 1:
                last_exc = e
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < MAX_RETRIES - 1:
                last_exc = e
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            raise

    # Should not reach here, but just in case
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Scale conversion
# ---------------------------------------------------------------------------


def _scale_to_millions(value: float, scale: str) -> float:
    """Convert a raw warehouse value to millions using SCALE_FACTORS.

    Args:
        value: The raw numeric value from the API.
        scale: The scale key (e.g. "0", "3", "6", "9").

    Returns:
        The value expressed in millions (scale "6").
    """
    factor = SCALE_FACTORS.get(scale, 1)
    # Convert: value * factor gives the absolute number,
    # then divide by 1_000_000 to express in millions.
    return (value * factor) / 1_000_000


# ---------------------------------------------------------------------------
# Client-side timeseries filtering
# ---------------------------------------------------------------------------


def _filter_timeseries(
    timeseries: list[dict],
    dim_order: list[str],
    filters: dict[str, str],
) -> list[dict]:
    """Filter warehouse timeseries by dimension values in the metadata key.

    The metadata key format is e.g.:
        BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}

    The values inside braces are comma-separated and map positionally to
    dim_order. This function keeps only timeseries whose dimension values
    match ALL entries in `filters`.

    Args:
        timeseries: List of timeseries dicts from the warehouse API.
        dim_order: Ordered list of dimension names matching brace positions.
        filters: Dict mapping dimension name to required value.

    Returns:
        Filtered list of timeseries dicts.
    """
    if not filters:
        return timeseries

    result = []
    for ts in timeseries:
        key = ts.get("key", "")
        # Extract the part inside braces
        brace_start = key.find("{")
        brace_end = key.find("}")
        if brace_start == -1 or brace_end == -1:
            continue

        dim_values = key[brace_start + 1 : brace_end].split(",")
        if len(dim_values) != len(dim_order):
            continue

        # Build a dimension name -> value mapping
        dim_map = dict(zip(dim_order, dim_values))

        # Check all filters match
        match = True
        for dim_name, required_value in filters.items():
            if dim_map.get(dim_name) != required_value:
                match = False
                break

        if match:
            result.append(ts)

    return result


# ---------------------------------------------------------------------------
# Tool: snb_list_bank_groups
# ---------------------------------------------------------------------------


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
    """List all bank group IDs used in SNB Warehouse banking statistics (BSTA).

    Returns the 12 bank group identifiers (Bankengruppen) with their German
    labels. Use these IDs as filter values for the BANKENGRUPPE dimension
    in warehouse cube queries.

    Returns:
        str: Markdown table of bank group IDs and labels.
    """
    lines = [
        "## SNB Bankengruppen (Warehouse BSTA)\n",
        "| ID | Bezeichnung |",
        "|----|-------------|",
    ]
    for gid, label in BANK_GROUPS.items():
        lines.append(f"| `{gid}` | {label} |")

    lines.append(
        "\n*Verwendung: BANKENGRUPPE-Dimension in Warehouse-Cube-Abfragen "
        "(z.B. `bank_group: 'A30'` für alle Banken)*"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: snb_list_warehouse_cubes
# ---------------------------------------------------------------------------


@mcp.tool(
    name="snb_list_warehouse_cubes",
    annotations={
        "title": "List SNB Warehouse Data Cubes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_warehouse_cubes() -> str:
    """List available SNB Warehouse cube IDs for banking statistics (BSTA).

    Returns an overview of all supported Warehouse cubes grouped by type:
    - BSTA Bilanz (BIL): Balance sheet data (monthly and annual)
    - BSTA Erfolgsrechnung (EFR): Income statement data (annual)

    Includes cube ID schema explanation, dimension info, and usage notes.

    Returns:
        str: Markdown overview of warehouse cubes with IDs and dimensions.
    """
    lines = [
        "## SNB Warehouse Cubes – Bankenstatistik (BSTA)\n",
        "API-Basis: `https://data.snb.ch/api/warehouse/cube/`\n",
        "### Cube-ID Schema",
        "Format: `BSTA.SNB.{FREQ}.{TYPE}.{POSITION}`",
        "- **FREQ**: `JAHR_K` (jährlich, konsolidiert) oder `MONA_US` (monatlich, unkonsolidiert)",
        "- **TYPE**: `BIL` (Bilanz) oder `EFR` (Erfolgsrechnung)",
        "- **POSITION**: Bilanz-/Erfolgsrechnungsposition\n",
        "### BSTA Bilanz (BIL)\n",
        "Verfügbare Frequenzen: MONA_US (monatlich) und JAHR_K (jährlich)\n",
        "| Cube-ID | Position | Beschreibung |",
        "|---------|----------|--------------|",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.TOT` | AKT.TOT | Total Aktiven (jährlich) |",
        "| `BSTA.SNB.MONA_US.BIL.AKT.TOT` | AKT.TOT | Total Aktiven (monatlich) |",
        "| `BSTA.SNB.JAHR_K.BIL.PAS.TOT` | PAS.TOT | Total Passiven (jährlich) |",
        "| `BSTA.SNB.MONA_US.BIL.PAS.TOT` | PAS.TOT | Total Passiven (monatlich) |",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.HYP` | AKT.HYP | Hypothekarforderungen (jährlich) |",
        "| `BSTA.SNB.MONA_US.BIL.AKT.HYP` | AKT.HYP | Hypothekarforderungen (monatlich) |",
        "| `BSTA.SNB.JAHR_K.BIL.AKT.BET` | AKT.BET | Beteiligungen (jährlich) |",
        "| `BSTA.SNB.MONA_US.BIL.AKT.BET` | AKT.BET | Beteiligungen (monatlich) |",
        "",
        "**Dimensionen (BIL):** KONSOLIDIERUNGSSTUFE, INLANDAUSLAND, WAEHRUNG, BANKENGRUPPE\n",
        "### BSTA Erfolgsrechnung (EFR)\n",
        "Nur jährlich (JAHR_K) verfügbar.\n",
        "| Cube-ID | Position | Beschreibung |",
        "|---------|----------|--------------|",
        "| `BSTA.SNB.JAHR_K.EFR.GER` | GER | Geschäftsertrag |",
        "| `BSTA.SNB.JAHR_K.EFR.GAU` | GAU | Geschäftsaufwand |",
        "| `BSTA.SNB.JAHR_K.EFR.UER` | UER | Übriger Ertrag |",
        "| `BSTA.SNB.JAHR_K.EFR.AAU` | AAU | Anderer Aufwand |",
        "| `BSTA.SNB.JAHR_K.EFR.STE` | STE | Steuern |",
        "| `BSTA.SNB.JAHR_K.EFR.AEG` | AEG | Ausserordentliches Ergebnis |",
        "",
        "**Dimensionen (EFR):** KONSOLIDIERUNGSSTUFE, BANKENGRUPPE\n",
        "### Hinweise",
        "- Dimensionsfilter (`dimSel`): Die Warehouse-API unterstützt nur eingeschränktes Filtern.",
        "  Client-seitige Filterung nach BANKENGRUPPE wird automatisch durchgeführt.",
        "- Verwenden Sie `snb_list_bank_groups` für die vollständige Liste der Bankengruppen-IDs.",
    ]
    return "\n".join(lines)
