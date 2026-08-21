"""
SNB Warehouse API tools for swiss-snb-mcp.
Provides access to granular banking statistics (BSTA) via the
Warehouse REST API at data.snb.ch/api/warehouse/cube/.
"""

import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from swiss_snb_mcp.retry import (
    TOTAL_BUDGET_S,
    request_with_retry,
)
from swiss_snb_mcp.server import (
    Language,
    _assert_host_allowed,
    _handle_http_error,
    _http,
    mcp,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAREHOUSE_BASE_URL = "https://data.snb.ch/api/warehouse/cube"

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

# Dimensionsordnung, wie sie am 2026-08-08 gemessen wurde. Der Code richtet
# sich NICHT mehr danach — er liest sie je Cube aus `/dimensions/<lang>` (siehe
# `cube_dimensions`). Diese beiden Zeilen bleiben als Beleg stehen und werden
# von `tests/test_unit.py` gegen die aufgezeichneten Fixtures gehalten: Sie
# stimmen fuer die Jahresreihe und die Erfolgsrechnung — und eben nicht fuer
# die Monatsreihe, die fuenf Dimensionen fuehrt.
BIL_DIM_ORDER = ["KONSOLIDIERUNGSSTUFE", "INLANDAUSLAND", "WAEHRUNG", "BANKENGRUPPE"]
EFR_DIM_ORDER = ["KONSOLIDIERUNGSSTUFE", "BANKENGRUPPE"]


# ---------------------------------------------------------------------------
# HTTP helper with retry logic
# ---------------------------------------------------------------------------


class UpstreamShapeError(RuntimeError):
    """The source answered, but not with what it answers with.

    Kept apart from a transport failure on purpose: waiting helps with one and
    never with the other. `data.snb.ch` is an Angular app in front of an API,
    and an unknown path under `/api/` does not 404 — it falls through to the
    app shell and returns **HTTP 200 with `text/html`**. A client that only
    checks the status code reads that as success and then fails somewhere far
    from the cause.
    """


def _require_json(response: httpx.Response, url: str) -> dict:
    """Return the parsed body, or say plainly that it was not JSON."""
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        raise UpstreamShapeError(
            f"{url} antwortete mit HTTP {response.status_code}, aber "
            f"Content-Type '{content_type or 'unbekannt'}' statt JSON. Bei "
            "data.snb.ch heisst das in aller Regel: Diesen Pfad gibt es "
            "nicht, und die Web-App hat geantwortet."
        )
    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamShapeError(f"{url} lieferte kein lesbares JSON ({exc}).") from exc


# Dimensionsordnung: gelesen, nicht geraten.
#
# Der Schluessel einer Reihe traegt die Dimensionswerte positionsgleich in
# geschweiften Klammern — `BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}`. Welche
# Position welche Dimension ist, sagt der Cube selbst unter
# `/dimensions/<lang>`, mit stabilen IDs (KONSOLIDIERUNGSSTUFE, INLANDAUSLAND,
# WAEHRUNG, ...). Frueher stand die Ordnung hier als Konstante, und sie galt
# fuer die Jahresreihe: vier Dimensionen. Die Monatsreihe hat fuenf. Da
# `_filter_timeseries` jede Reihe verwirft, deren Laenge nicht passt, kam bei
# `frequency="monthly"` eine leere Tabelle heraus — HTTP 200, kein Fehler,
# keine Zeile.
_DIMENSION_CACHE: dict[
    tuple[str, str], tuple[tuple[str, ...], dict[str, dict[str, str]]]
] = {}


def _collect_items(items: list[dict], out: dict[str, str]) -> dict[str, str]:
    """Flatten a dimension's item tree into ``{id: name}`` (groups nest)."""
    for item in items:
        if "id" in item:
            out[item["id"]] = item.get("name", item["id"])
        _collect_items(item.get("dimensionItems", []) or [], out)
    return out


async def cube_dimensions(
    cube_id: str, lang: str = "de"
) -> tuple[tuple[str, ...], dict[str, dict[str, str]]]:
    """``(ordered dimension ids, {dimension id: {item id: label}})`` for a cube.

    Cached per (cube, language): the layout of a published cube changes with an
    edition, not with a request.
    """
    cached = _DIMENSION_CACHE.get((cube_id, lang))
    if cached is not None:
        return cached

    # Note the path: `dimensions/<lang>`, with no `json` segment. The data
    # endpoints take one (`data/json/<lang>`) and this one does not — asking
    # for `dimensions/json/<lang>` returns the web app, with HTTP 200.
    data = await _fetch_warehouse(cube_id, "dimensions", lang)
    dims = data.get("dimensions")
    if not isinstance(dims, list) or not dims:
        raise UpstreamShapeError(
            f"Der Cube '{cube_id}' nennt keine Dimensionen — ohne sie laesst "
            "sich kein Schluessel zerlegen."
        )
    order = tuple(d["id"] for d in dims)
    items = {
        d["id"]: _collect_items(d.get("dimensionItems", []) or [], {}) for d in dims
    }
    _DIMENSION_CACHE[(cube_id, lang)] = (order, items)
    return order, items


def _clear_dimension_cache() -> None:
    """Drop the cached cube layouts (used by tests)."""
    _DIMENSION_CACHE.clear()


async def _fetch_warehouse(
    cube_id: str,
    endpoint: str,
    lang: str = "de",
    from_date: str | None = None,
    to_date: str | None = None,
    total_budget: float = TOTAL_BUDGET_S,
) -> dict:
    """Fetch data from the SNB Warehouse REST API with retry on 503.

    URL pattern: {WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}
    Query params: fromDate, toDate (optional).

    Retries up to MAX_RETRIES times on transient HTTP errors (see
    RETRY_STATUS_CODES) with a jittered 2/4/8s backoff capped at MAX_DELAY_S; a
    ``Retry-After`` sent on a 429 or 503 overrides that table.

    ``total_budget`` bounds the whole call — attempts and waits together.
    """
    url = f"{WAREHOUSE_BASE_URL}/{cube_id}/{endpoint}/{lang}"
    _assert_host_allowed(url)
    params: dict[str, str] = {}
    if from_date:
        params["fromDate"] = from_date
    if to_date:
        params["toDate"] = to_date

    # Der Client kommt weiterhin von hier und nicht aus retry.py: `_http()` ist
    # an den Lifespan des Servers gebunden, den retry.py nicht kennen soll.
    response = await request_with_retry(_http(), url, params, total_budget=total_budget)
    # Ausserhalb der Retry-Schleife, und das ist Absicht: Eine Formabweichung
    # ist kein transienter Fehler. Sie noch zweimal zu wiederholen kostet nur
    # Zeit und Last, und die Antwort waere jedes Mal dieselbe.
    return _require_json(response, url)


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


def _key_dims(key: str) -> list[str]:
    """The dimension values a warehouse key carries, in cube order."""
    brace_start = key.find("{")
    brace_end = key.find("}")
    if brace_start == -1 or brace_end == -1:
        return []
    return key[brace_start + 1 : brace_end].split(",")


def _require_items(
    cube_id: str,
    dimension: str,
    wanted: set[str] | None,
    items: dict[str, dict[str, str]],
    *,
    preferred: str | None = None,
) -> set[str]:
    """Validate requested dimension items against what the cube declares.

    An id the cube does not have used to produce an empty table, which reads
    exactly like "this bank has no assets". It now says which ids exist.

    With nothing requested, ``preferred`` is taken when the cube declares it
    and every item otherwise — because the cube decides what "all banks"
    means, and the two BIL cubes disagree: the annual series calls that group
    ``A30``, the monthly one ``A40``. A default hard-wired to ``A30`` matched
    nothing in the monthly cube, which is one of the three reasons it returned
    an empty table.
    """
    available = items.get(dimension, {})
    if wanted is None:
        if preferred and preferred in available:
            return {preferred}
        return set(available)
    missing = sorted(wanted - set(available))
    if missing:
        raise UpstreamShapeError(
            f"{', '.join(missing)} gibt es in der Dimension {dimension} von "
            f"'{cube_id}' nicht. Vorhanden: "
            + ", ".join(f"{i} ({n})" for i, n in sorted(available.items()))
            + "."
        )
    return set(wanted)


def _filter_timeseries(
    timeseries: list[dict],
    dim_order: list[str],
    filters: dict[str, str | set[str]],
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
        filters: Dict mapping dimension name to required value (str) or
            set of acceptable values (set[str]).

    Returns:
        Filtered list of timeseries dicts.
    """
    if not filters:
        return timeseries

    result = []
    for ts in timeseries:
        meta = ts.get("metadata", {})
        key = meta.get("key", "") if meta else ts.get("key", "")
        dim_values = _key_dims(key)
        if not dim_values:
            continue

        # `dim_order` kommt jetzt aus `/dimensions/<lang>` des Cubes selbst.
        # Passt die Laenge trotzdem nicht, widerspricht die Quelle sich
        # innerhalb einer Antwort — das ist ein Befund und kein Grund, die
        # Reihe stillschweigend fallen zu lassen. Genau dieses `continue` hat
        # die Monatsreihe zu einer leeren Tabelle gemacht.
        if len(dim_values) != len(dim_order):
            raise UpstreamShapeError(
                f"Schluessel '{key}' traegt {len(dim_values)} Dimensionswerte, "
                f"der Cube nennt {len(dim_order)} Dimensionen "
                f"({', '.join(dim_order)}). Ohne eine eindeutige Zuordnung "
                "waere jede Eingrenzung geraten."
            )

        # Build a dimension name -> value mapping
        dim_map = dict(zip(dim_order, dim_values, strict=True))

        # Check all filters match
        match = True
        for dim_name, required_value in filters.items():
            actual = dim_map.get(dim_name)
            if isinstance(required_value, set):
                if actual not in required_value:
                    match = False
                    break
            else:
                if actual != required_value:
                    match = False
                    break

        if match:
            result.append(ts)

    return result


# ---------------------------------------------------------------------------
# Tool: snb_list_bank_groups
# ---------------------------------------------------------------------------


@mcp.resource(
    "data://snb/bank-groups",
    name="snb_list_bank_groups",
    title="List SNB Bank Groups",
    mime_type="text/markdown",
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
# Input models for generic warehouse tools
# ---------------------------------------------------------------------------


class WarehouseDataInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description=(
            "SNB Warehouse cube ID (uppercase, dot-separated), e.g. "
            "'BSTA.SNB.JAHR_K.BIL.AKT.TOT'. Use snb_list_warehouse_cubes "
            "to see confirmed working cube IDs."
        ),
        min_length=5,
        max_length=60,
        pattern=r"^[A-Z][A-Z0-9_.]+$",
    )
    from_date: str | None = Field(
        default=None,
        description="Start date. Use YYYY for annual cubes, YYYY-MM for monthly.",
    )
    to_date: str | None = Field(
        default=None,
        description="End date, same format as from_date.",
    )
    lang: Language = Field(default=Language.DE)


class WarehouseMetadataInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description="SNB Warehouse cube ID to inspect.",
        min_length=5,
        max_length=60,
        pattern=r"^[A-Z][A-Z0-9_.]+$",
    )
    lang: Language = Field(default=Language.DE)


# ---------------------------------------------------------------------------
# Tool: snb_get_warehouse_data
# ---------------------------------------------------------------------------


@mcp.tool(
    name="snb_get_warehouse_data",
    annotations={
        "title": "SNB Warehouse Cube Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_warehouse_data(params: WarehouseDataInput) -> str:
    """Retrieve raw data from any SNB Warehouse cube by ID.

    Generic tool for accessing SNB Warehouse cubes (BSTA banking statistics).
    Use snb_get_warehouse_metadata first to understand the cube structure.
    Use snb_list_warehouse_cubes to discover available cube IDs.

    Args:
        params (WarehouseDataInput):
            - cube_id: SNB Warehouse cube ID (uppercase, dot-separated).
            - from_date: Start date (YYYY for annual, YYYY-MM for monthly).
            - to_date: End date.
            - lang: Response language (de/en/fr).

    Returns:
        str: Timeseries data from the warehouse cube as Markdown + JSON.
    """
    try:
        data = await _fetch_warehouse(
            params.cube_id,
            "data/json",
            params.lang.value,
            params.from_date,
            params.to_date,
        )
        timeseries = data.get("timeseries", [])

        # Scale label from first timeseries metadata
        scale_label = ""
        if timeseries:
            first_ts = timeseries[0]
            scale = first_ts.get("scale", "0")
            scale_label = SCALE_LABELS.get(scale, f"Skala {scale}")

        lines = [
            f"## SNB Warehouse Cube `{params.cube_id}` — {len(timeseries)} Zeitreihe(n)\n",
            f"**Quelle:** data.snb.ch/api/warehouse/cube/{params.cube_id}",
        ]
        if scale_label:
            lines.append(f"**Einheit:** {scale_label}\n")

        if timeseries:
            # Brief summary of first 5 timeseries
            for ts in timeseries[:5]:
                header = ts.get("header", [])
                values = ts.get("values", [])
                label = " | ".join(h.get("dimItem", "") for h in header)
                last_val = values[-1] if values else None
                val_str = f"{last_val['value']}" if last_val else "–"
                date_str = last_val["date"] if last_val else "–"
                lines.append(f"- **{label}**: {val_str} ({date_str})")

            if len(timeseries) > 5:
                lines.append(f"- … und {len(timeseries) - 5} weitere Zeitreihen")

        lines.append("\n```json")
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        lines.append(json_str[:8000])
        if len(json_str) > 8000:
            lines.append("... (truncated, use a narrower date range)")
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


# ---------------------------------------------------------------------------
# Tool: snb_get_warehouse_metadata
# ---------------------------------------------------------------------------


@mcp.tool(
    name="snb_get_warehouse_metadata",
    annotations={
        "title": "SNB Warehouse Cube Metadata",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_warehouse_metadata(params: WarehouseMetadataInput) -> str:
    """Get metadata and dimension structure for any SNB Warehouse cube.

    Retrieves the cube's dimension definitions and last update date.
    Use this before querying snb_get_warehouse_data to understand
    what dimensions and filter values are available.

    Args:
        params (WarehouseMetadataInput):
            - cube_id: SNB Warehouse cube ID to inspect.
            - lang: Language for labels (de/en/fr).

    Returns:
        str: Cube ID, edition date, dimensions and their items.
    """
    try:
        # `dimensions/<lang>` — ohne `json`-Segment. Hier stand
        # `dimensions/json/<lang>`, in Analogie zu `data/json/<lang>`; diesen
        # Pfad gibt es nicht, und data.snb.ch beantwortet ihn mit HTTP 200 und
        # dem HTML-Geruest der Web-App. Dieses Werkzeug hat deshalb fuer jeden
        # Cube einen Fehler zurueckgegeben, seit es existiert.
        dim_data = await _fetch_warehouse(
            params.cube_id, "dimensions", params.lang.value
        )

        # Fetch last update (no language segment!)
        lu_url = f"{WAREHOUSE_BASE_URL}/{params.cube_id}/lastUpdate"
        _assert_host_allowed(lu_url)
        client = _http()
        try:
            lu_resp = await client.get(lu_url)
            lu_resp.raise_for_status()
            lu_data = lu_resp.json()
            edition_date = lu_data.get("editionDate", "unbekannt")
        except Exception:
            edition_date = "nicht verfügbar"

        lines = [
            f"## SNB Warehouse Metadata: `{params.cube_id}`",
            f"**Letzte Aktualisierung:** {edition_date}\n",
        ]

        for dim in dim_data.get("dimensions", []):
            lines.append(f"### Dimension: {dim['name']} (ID: `{dim['id']}`)")
            items = dim.get("dimensionItems", [])
            for item in items:
                sub_items = item.get("dimensionItems", [])
                if sub_items:
                    lines.append(f"  **{item['id']}**: {item['name']}")
                    for sub in sub_items:
                        lines.append(f"    - `{sub['id']}`: {sub['name']}")
                else:
                    lines.append(f"  - `{item['id']}`: {item['name']}")

        lines.append("\n```json")
        lines.append(json.dumps(dim_data, ensure_ascii=False, indent=2))
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


# ---------------------------------------------------------------------------
# Tool: snb_list_warehouse_cubes
# ---------------------------------------------------------------------------


@mcp.resource(
    "data://snb/warehouse-cubes",
    name="snb_list_warehouse_cubes",
    title="List SNB Warehouse Data Cubes",
    mime_type="text/markdown",
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


# ---------------------------------------------------------------------------
# Input model: BankingBalanceSheetInput
# ---------------------------------------------------------------------------


class BankingBalanceSheetInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    side: Literal["assets", "liabilities", "both"] = Field(
        default="both",
        description="Balance sheet side: 'assets', 'liabilities', or 'both'.",
    )
    bank_groups: list[str] | None = Field(
        default=None,
        description=(
            "Bank group IDs, e.g. ['A30', 'G10']. "
            "Use snb_list_bank_groups for valid IDs. Default: ['A30'] (all banks)."
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
    from_date: str | None = Field(
        default=None,
        description="Start date. YYYY for annual, YYYY-MM for monthly.",
    )
    to_date: str | None = Field(
        default=None,
        description="End date.",
    )
    lang: Language = Field(default=Language.DE)


# ---------------------------------------------------------------------------
# Tool: snb_get_banking_balance_sheet
# ---------------------------------------------------------------------------


@mcp.tool(
    name="snb_get_banking_balance_sheet",
    annotations={
        "title": "SNB Banking Balance Sheet (BSTA)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_banking_balance_sheet(params: BankingBalanceSheetInput) -> str:
    """Retrieve banking balance sheet data from SNB Warehouse (BSTA BIL cubes).

    Returns total assets and/or liabilities for selected bank groups from the
    Swiss banking statistics. Values are converted to millions of CHF.

    Args:
        params (BankingBalanceSheetInput):
            - side: 'assets', 'liabilities', or 'both'.
            - bank_groups: Bank group IDs (default: ['A30'] = all banks).
            - frequency: 'annual' or 'monthly'.
            - currency: Currency filter (default: 'T' = Total).
            - from_date / to_date: Date range.
            - lang: Response language.

    Returns:
        str: Markdown summary with values in Millionen CHF, plus JSON data.
    """
    try:
        freq = "JAHR_K" if params.frequency == "annual" else "MONA_US"

        # Determine which cube IDs to fetch based on side
        cube_ids: list[tuple[str, str]] = []
        if params.side in ("assets", "both"):
            cube_ids.append((f"BSTA.SNB.{freq}.BIL.AKT.TOT", "Aktiven"))
        if params.side in ("liabilities", "both"):
            cube_ids.append((f"BSTA.SNB.{freq}.BIL.PAS.TOT", "Passiven"))

        lines = [
            "## Bankenstatistik — Bilanz\n",
            "**Einheit:** Millionen CHF\n",
            "| Position | Bankengruppe | Gliederung | Wert | Datum |",
            "|----------|-------------|-----------|------|-------|",
        ]

        result_data: list[dict] = []

        for cube_id, side_label in cube_ids:
            order, items = await cube_dimensions(cube_id, params.lang.value)

            # Was der Aufrufer eingrenzen wollte — aber nur, was dieser Cube
            # ueberhaupt fuehrt, und mit einer Fehlermeldung statt einer leeren
            # Tabelle, wenn ein Wert nicht existiert. Die Konsolidierungsstufe
            # steht hier nicht mehr fest auf "K": die Monatsreihe kennt nur "U",
            # und drei Zeilen weiter unten war das der Grund, warum sie nichts
            # lieferte.
            filters: dict[str, str | set[str]] = {}
            if "WAEHRUNG" in order:
                filters["WAEHRUNG"] = _require_items(
                    cube_id, "WAEHRUNG", {params.currency.upper()}, items
                )
            if "BANKENGRUPPE" in order:
                filters["BANKENGRUPPE"] = _require_items(
                    cube_id,
                    "BANKENGRUPPE",
                    set(params.bank_groups) if params.bank_groups else None,
                    items,
                    preferred="A30",
                )

            data = await _fetch_warehouse(
                cube_id,
                "data/json",
                params.lang.value,
                params.from_date,
                params.to_date,
            )
            timeseries = data.get("timeseries", [])
            matched = _filter_timeseries(timeseries, list(order), filters)

            for ts in matched:
                meta = ts.get("metadata", {})
                scale = meta.get("scale", "0")
                values = ts.get("values", [])
                dim_map = dict(zip(order, _key_dims(meta.get("key", "")), strict=False))

                bg_id = dim_map.get("BANKENGRUPPE", "—")
                bg_label = items.get("BANKENGRUPPE", {}).get(
                    bg_id, BANK_GROUPS.get(bg_id, bg_id)
                )

                # Jede Dimension, die nicht eingegrenzt wurde, gehoert in die
                # Zeile. Vorher fehlte INLANDAUSLAND in Filter UND Ausgabe, und
                # damit standen Total, Inland und Ausland als drei Zeilen unter
                # derselben Beschriftung — wobei Inland + Ausland das Total
                # ergibt. Wer die erste Zeile nimmt, hat Glueck; wer summiert,
                # verdoppelt die Bilanz.
                breakdown = {
                    dim: items.get(dim, {}).get(val, val)
                    for dim, val in dim_map.items()
                    if dim not in filters and dim != "BANKENGRUPPE"
                }
                breakdown_label = " · ".join(breakdown.values()) or "—"

                for v in values:
                    raw_val = v.get("value")
                    if raw_val is None:
                        continue
                    mio = _scale_to_millions(float(raw_val), scale)
                    v["value_mio"] = round(mio, 1)

                if values:
                    last = values[-1]
                    mio_val = last.get("value_mio", 0)
                    mrd_val = mio_val / 1000
                    lines.append(
                        f"| {side_label} | {bg_label} | {breakdown_label} | "
                        f"{mio_val:,.1f} Mio. CHF ({mrd_val:,.1f} Mrd. CHF) | "
                        f"{last['date']} |"
                    )

                result_data.append(
                    {
                        "cube_id": cube_id,
                        "side": side_label,
                        "bank_group": bg_id,
                        "bank_group_label": bg_label,
                        "dimensions": dim_map,
                        "breakdown": breakdown,
                        "scale": scale,
                        "values": values,
                    }
                )

            if not matched:
                lines.append(
                    f"| ⚠ {cube_id}: keine Reihe passt zu den gewählten "
                    f"Filtern ({filters}) | | | | |"
                )

        lines.append("\n```json")
        json_str = json.dumps(result_data, ensure_ascii=False, indent=2)
        lines.append(json_str[:8000])
        if len(json_str) > 8000:
            lines.append("... (truncated, use a narrower date range)")
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


# ---------------------------------------------------------------------------
# Input model: BankingIncomeInput (EFR — income statement / Erfolgsrechnung)
# ---------------------------------------------------------------------------


class BankingIncomeInput(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    bank_groups: list[str] | None = Field(
        default=None,
        description=(
            "Bank group IDs. Default: ['A30']. Use snb_list_bank_groups for valid IDs."
        ),
        max_length=15,
    )
    from_year: str | None = Field(
        default=None,
        description="Start year (YYYY). Default: 5 years ago.",
        pattern=r"^\d{4}$",
    )
    to_year: str | None = Field(
        default=None,
        description="End year (YYYY). Default: current year.",
        pattern=r"^\d{4}$",
    )
    lang: Language = Field(default=Language.DE)


# ---------------------------------------------------------------------------
# Tool: snb_get_banking_income
# ---------------------------------------------------------------------------


@mcp.tool(
    name="snb_get_banking_income",
    annotations={
        "title": "SNB Banking Income Statement (BSTA EFR)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_banking_income(params: BankingIncomeInput) -> str:
    """Retrieve banking income statement data from SNB Warehouse (BSTA EFR cubes).

    Returns key income statement positions (Geschäftsertrag, Geschäftsaufwand,
    etc.) for selected bank groups. Values are converted to millions of CHF.

    Args:
        params (BankingIncomeInput):
            - bank_groups: Bank group IDs (default: ['A30'] = all banks).
            - from_year / to_year: Year range (YYYY).
            - lang: Response language.

    Returns:
        str: Markdown summary with values in Millionen CHF, plus JSON data.
    """
    try:
        wanted_groups = set(params.bank_groups) if params.bank_groups else None

        lines = [
            "## Bankenstatistik — Erfolgsrechnung\n",
            "**Einheit:** Millionen CHF\n",
            "| Position | Bankengruppe | Wert | Datum |",
            "|----------|-------------|------|-------|",
        ]

        result_data: list[dict] = []
        last_exc: Exception | None = None

        for pos_id, pos_name in EFR_POSITIONS.items():
            cube_id = f"BSTA.SNB.JAHR_K.EFR.{pos_id}"
            try:
                data = await _fetch_warehouse(
                    cube_id,
                    "data/json",
                    params.lang.value,
                    params.from_year,
                    params.to_year,
                )
            except Exception as e:
                last_exc = e
                lines.append(
                    f"| \u26a0 BSTA.SNB.JAHR_K.EFR.{pos_id}: nicht verfügbar | | | |"
                )
                continue

            order, items = await cube_dimensions(cube_id, params.lang.value)
            filters: dict[str, str | set[str]] = {
                "BANKENGRUPPE": _require_items(
                    cube_id, "BANKENGRUPPE", wanted_groups, items, preferred="A30"
                )
            }

            timeseries = data.get("timeseries", [])
            matched = _filter_timeseries(timeseries, list(order), filters)

            for ts in matched:
                meta = ts.get("metadata", {})
                scale = meta.get("scale", "0")
                values = ts.get("values", [])
                dim_map = dict(zip(order, _key_dims(meta.get("key", "")), strict=False))

                bg_id = dim_map.get("BANKENGRUPPE", "—")
                bg_label = items.get("BANKENGRUPPE", {}).get(
                    bg_id, BANK_GROUPS.get(bg_id, bg_id)
                )

                for v in values:
                    raw_val = v.get("value")
                    if raw_val is None:
                        continue
                    mio = _scale_to_millions(float(raw_val), scale)
                    v["value_mio"] = round(mio, 1)

                if values:
                    last = values[-1]
                    mio_val = last.get("value_mio", 0)
                    lines.append(
                        f"| {pos_name} | {bg_label} | "
                        f"{mio_val:,.1f} Mio. CHF | "
                        f"{last['date']} |"
                    )

                result_data.append(
                    {
                        "cube_id": cube_id,
                        "position": pos_id,
                        "position_name": pos_name,
                        "bank_group": bg_id,
                        "bank_group_label": bg_label,
                        "dimensions": dim_map,
                        "scale": scale,
                        "values": values,
                    }
                )

        # If every cube fetch failed (e.g. all annual cubes are locked while
        # the SNB re-publishes them), surface the underlying error instead of
        # returning a misleading empty "success" response.
        if not result_data and last_exc is not None:
            return _handle_http_error(last_exc)

        lines.append("\n```json")
        json_str = json.dumps(result_data, ensure_ascii=False, indent=2)
        lines.append(json_str[:8000])
        if len(json_str) > 8000:
            lines.append("... (truncated, use a narrower date range)")
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)
