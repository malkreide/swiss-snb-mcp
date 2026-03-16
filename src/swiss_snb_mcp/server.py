"""
Swiss National Bank (SNB) MCP Server
Provides access to the SNB data portal: exchange rates, balance sheet,
and monetary statistics via the public REST API at data.snb.ch.
"""

import json
from typing import Optional
from enum import Enum

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SNB_BASE_URL = "https://data.snb.ch/api/cube"
DEFAULT_TIMEOUT = 15.0

# Known cube identifiers (verified against the live API)
CUBE_EXCHANGE_RATES_MONTHLY = "devkum"   # Wechselkurse Monatsmittel/-ende
CUBE_EXCHANGE_RATES_ANNUAL  = "devkua"   # Wechselkurse Jahresdurchschnitt
CUBE_BALANCE_SHEET          = "snbbipo"  # SNB-Bilanzpositionen

# Currency dimension item IDs → human-readable labels
CURRENCIES = {
    "EUR1":    "Euro (EUR)",
    "USD1":    "US-Dollar (USD)",
    "GBP1":    "Pfund Sterling (GBP)",
    "JPY100":  "Japanischer Yen – 100 JPY",
    "CNY100":  "Chinesischer Renminbi – 100 CNY",
    "CAD1":    "Kanadischer Dollar (CAD)",
    "AUD1":    "Australischer Dollar (AUD)",
    "NZD1":    "Neuseeländischer Dollar (NZD)",
    "SGD1":    "Singapur-Dollar (SGD)",
    "HKD100":  "Hongkong-Dollar – 100 HKD",
    "KRW100":  "Südkoreanischer Won – 100 KRW",
    "MYR100":  "Malaysischer Ringgit – 100 MYR",
    "THB100":  "Thailändischer Baht – 100 THB",
    "NOK100":  "Norwegische Krone – 100 NOK",
    "SEK100":  "Schwedische Krone – 100 SEK",
    "DKK100":  "Dänische Krone – 100 DKK",
    "CZK100":  "Tschechische Krone – 100 CZK",
    "HUF100":  "Ungarischer Forint – 100 HUF",
    "PLN100":  "Polnischer Zloty – 100 PLN",
    "TRY100":  "Türkische Lira – 100 TRY",
    "RUB1":    "Russischer Rubel (RUB)",
    "ZAR1":    "Südafrikanischer Rand (ZAR)",
    "BRL100":  "Brasilianischer Real – 100 BRL",
    "MXN100":  "Mexikanischer Peso – 100 MXN",
    "ARS1":    "Argentinischer Peso (ARS)",
    "INR100":  "Indische Rupie – 100 INR",
    "XDR1":    "Sonderziehungsrechte IWF (XDR)",
}

# Unit multipliers — how many foreign units correspond to 1 rate value
CURRENCY_UNITS = {
    "EUR1": 1, "USD1": 1, "GBP1": 1, "CAD1": 1, "AUD1": 1,
    "NZD1": 1, "SGD1": 1, "ZAR1": 1, "RUB1": 1, "ARS1": 1, "XDR1": 1,
    "JPY100": 100, "CNY100": 100, "HKD100": 100, "KRW100": 100,
    "MYR100": 100, "THB100": 100, "NOK100": 100, "SEK100": 100,
    "DKK100": 100, "CZK100": 100, "HUF100": 100, "PLN100": 100,
    "TRY100": 100, "BRL100": 100, "MXN100": 100, "INR100": 100,
}

# SNB balance sheet position IDs
BALANCE_SHEET_POSITIONS = {
    # Aktiven
    "GFG":   "Gold und Forderungen aus Goldgeschäften",
    "D":     "Devisenanlagen",
    "RIWF":  "Reserveposition beim IWF",
    "IZ":    "Internationale Zahlungsmittel",
    "W":     "Währungshilfekredite",
    "FRGSF": "Forderungen aus Repo-Geschäften in CHF",
    "FRGUSD":"Forderungen aus Repo-Geschäften in USD",
    "GSGSF": "Guthaben aus Swap-Geschäften gegen CHF",
    "IG":    "Inländische Geldmarktforderungen",
    "GD":    "Gedeckte Darlehen",
    "FI":    "Forderungen gegenüber Inlandkorrespondenten",
    "WSF":   "Wertschriften in CHF",
    "DS":    "Darlehen an Stabilisierungsfonds",
    "UA":    "Übrige Aktiven",
    "T0":    "Total Aktiven",
    # Passiven
    "N":     "Notenumlauf",
    "GB":    "Girokonten inländischer Banken",
    "VB":    "Verbindlichkeiten gegenüber dem Bund",
    "GBI":   "Girokonten ausländischer Banken und Institutionen",
    "US":    "Übrige Sichtverbindlichkeiten",
    "VRGSF": "Verbindlichkeiten aus Repo-Geschäften in CHF",
    "ES":    "Eigene Schuldverschreibungen",
    "UT":    "Übrige Terminverbindlichkeiten",
    "VF":    "Verbindlichkeiten in Fremdwährungen",
    "AIWFS": "Ausgleichsposten für IWF-Sonderziehungsrechte",
    "SP":    "Sonstige Passiven",
    "RE":    "Rückstellungen und Eigenkapital",
    "T1":    "Total Passiven",
}

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "swiss_snb_mcp",
    instructions=(
        "MCP server for the Swiss National Bank (SNB) data portal at data.snb.ch. "
        "Provides access to official Swiss monetary statistics: exchange rates (monthly "
        "and annual), SNB balance sheet positions, SNB policy rate (Leitzins), SARON and "
        "repo compound rates, international money market rates, official central bank rates "
        "in comparison (Fed, ECB, BoE, BoJ), monetary aggregates M1/M2/M3, and a generic "
        "cube data tool for additional datasets. All monetary data is in CHF. "
        "No authentication required."
    ),
)

# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

async def _fetch_snb(path: str, params: dict | None = None) -> dict:
    """Fetch data from the SNB REST API and return parsed JSON."""
    url = f"{SNB_BASE_URL}/{path}"
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def _handle_http_error(e: Exception) -> str:
    """Return a clear, actionable error message for HTTP failures."""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 404:
            return (
                "Error: Cube or endpoint not found (HTTP 404). "
                "Check the cube ID with snb_get_cube_metadata or snb_list_known_cubes."
            )
        if code == 400:
            return (
                "Error: Bad request (HTTP 400). "
                "Verify date format (YYYY-MM for monthly, YYYY for annual) and parameter names."
            )
        return f"Error: SNB API returned HTTP {code}: {e.response.text[:200]}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request to data.snb.ch timed out. Please try again."
    if isinstance(e, httpx.ConnectError):
        return "Error: Cannot reach data.snb.ch. Check network connectivity."
    return f"Error: Unexpected error ({type(e).__name__}): {str(e)[:200]}"


def _format_timeseries_table(
    timeseries: list[dict],
    filter_dim_id: str | None = None,
    filter_dim_value: str | None = None,
) -> str:
    """Format a list of SNB timeseries into a readable markdown table."""
    lines = []
    for ts in timeseries:
        header_labels = [h["dimItem"] for h in ts.get("header", [])]
        meta = ts.get("metadata", {})
        values = ts.get("values", [])
        if not values:
            continue
        label = " | ".join(header_labels)
        unit = meta.get("unit", "")
        lines.append(f"\n**{label}** ({unit})")
        lines.append("| Datum | Wert |")
        lines.append("|-------|------|")
        for v in values:
            date = v.get("date", "")
            val = v.get("value")
            val_str = f"{val:.5f}" if val is not None else "–"
            lines.append(f"| {date} | {val_str} |")
    return "\n".join(lines) if lines else "Keine Daten für den gewählten Zeitraum."


def _latest_value(timeseries: list[dict], dim_id: str) -> dict | None:
    """Return the most recent value entry for a timeseries matching dim_id."""
    for ts in timeseries:
        for h in ts.get("header", []):
            if h.get("dimItem", "").startswith(dim_id) or dim_id in h.get("dimItem", ""):
                values = ts.get("values", [])
                return values[-1] if values else None
    return None

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class Language(str, Enum):
    DE = "de"
    EN = "en"
    FR = "fr"


class ExchangeRatesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    currencies: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of currency IDs to retrieve, e.g. ['EUR1', 'USD1', 'GBP1']. "
            "Use snb_list_currencies to see all available IDs. "
            "If omitted, all currencies are returned."
        ),
        max_length=30,
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date in YYYY-MM format, e.g. '2024-01'. Defaults to 12 months ago.",
        pattern=r"^\d{4}-\d{2}$",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM format, e.g. '2025-03'. Defaults to today's month.",
        pattern=r"^\d{4}-\d{2}$",
    )
    include_month_end: bool = Field(
        default=False,
        description="If True, also include month-end rates in addition to monthly averages.",
    )
    lang: Language = Field(
        default=Language.DE,
        description="Response language: 'de' (German), 'en' (English), 'fr' (French).",
    )


class AnnualExchangeRatesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    currencies: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of currency IDs, e.g. ['EUR1', 'USD1']. "
            "Use snb_list_currencies to see all available IDs. "
            "If omitted, all currencies are returned."
        ),
        max_length=30,
    )
    from_year: Optional[str] = Field(
        default=None,
        description="Start year, e.g. '2020'. Defaults to 5 years ago.",
        pattern=r"^\d{4}$",
    )
    to_year: Optional[str] = Field(
        default=None,
        description="End year, e.g. '2025'. Defaults to current year.",
        pattern=r"^\d{4}$",
    )
    lang: Language = Field(default=Language.DE)


class BalanceSheetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    positions: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of balance sheet position IDs, e.g. ['GFG', 'D', 'T0', 'GB', 'T1']. "
            "Use snb_list_balance_sheet_positions to see all available IDs. "
            "If omitted, key positions are returned (Gold, Devisen, Noten, Giroguthaben, Totals)."
        ),
        max_length=30,
    )
    from_date: Optional[str] = Field(
        default=None,
        description="Start date in YYYY-MM format. Defaults to 24 months ago.",
        pattern=r"^\d{4}-\d{2}$",
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date in YYYY-MM format. Defaults to latest available.",
        pattern=r"^\d{4}-\d{2}$",
    )
    lang: Language = Field(default=Language.DE)


class ConvertCurrencyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    amount: float = Field(
        ...,
        description="Amount in the foreign currency to convert to CHF.",
        gt=0,
    )
    currency_id: str = Field(
        ...,
        description=(
            "SNB currency ID, e.g. 'EUR1', 'USD1', 'JPY100'. "
            "Use snb_list_currencies for all valid IDs."
        ),
        min_length=3,
        max_length=10,
    )
    reference_month: Optional[str] = Field(
        default=None,
        description=(
            "Month for which to use the exchange rate, in YYYY-MM format. "
            "Defaults to the most recent available month."
        ),
        pattern=r"^\d{4}-\d{2}$",
    )


class CubeDataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description=(
            "SNB cube identifier, e.g. 'devkum', 'devkua', 'snbbipo'. "
            "Use snb_list_known_cubes to see confirmed working cubes, "
            "or browse data.snb.ch to discover additional cube IDs via the URL."
        ),
        min_length=3,
        max_length=20,
        pattern=r"^[a-z][a-z0-9]+$",
    )
    from_date: Optional[str] = Field(
        default=None,
        description=(
            "Start date. Use YYYY-MM for monthly cubes, YYYY for annual cubes. "
            "Defaults to the last 24 months / 5 years."
        ),
    )
    to_date: Optional[str] = Field(
        default=None,
        description="End date, same format as from_date.",
    )
    lang: Language = Field(default=Language.DE)


class CubeMetadataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    cube_id: str = Field(
        ...,
        description="SNB cube identifier to inspect.",
        min_length=3,
        max_length=20,
        pattern=r"^[a-z][a-z0-9]+$",
    )
    lang: Language = Field(default=Language.DE)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="snb_get_exchange_rates",
    annotations={
        "title": "SNB Monthly Exchange Rates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_exchange_rates(params: ExchangeRatesInput) -> str:
    """Retrieve monthly CHF exchange rates from the Swiss National Bank (data.snb.ch).

    Returns monthly average rates (and optionally month-end rates) for all major
    currencies against the Swiss Franc (CHF). Data source: SNB cube 'devkum'.
    Rates are expressed as the CHF value of the stated foreign currency unit
    (e.g. EUR1: 1 EUR = 0.9416 CHF; JPY100: 100 JPY = 0.58 CHF).

    Args:
        params (ExchangeRatesInput):
            - currencies: List of currency IDs (e.g. ['EUR1', 'USD1']). Default: all.
            - from_date: Start month YYYY-MM. Default: 12 months ago.
            - to_date: End month YYYY-MM. Default: current month.
            - include_month_end: Also include month-end rates. Default: False.
            - lang: Response language (de/en/fr). Default: de.

    Returns:
        str: Markdown table with dates and CHF exchange rates per currency.
             Includes publication date and data source metadata.

    Schema:
        {
          "cube_id": "devkum",
          "publishing_date": "YYYY-MM-DD HH:MM",
          "currencies_returned": int,
          "timeseries": [
            {
              "currency": str,
              "type": "Monatsmittel" | "Monatsende",
              "unit": str,
              "values": [{"date": "YYYY-MM", "value": float}]
            }
          ]
        }
    """
    try:
        path = f"{CUBE_EXCHANGE_RATES_MONTHLY}/data/json/{params.lang.value}"
        query: dict = {}
        if params.from_date:
            query["fromDate"] = params.from_date
        if params.to_date:
            query["toDate"] = params.to_date

        data = await _fetch_snb(path, query or None)
        timeseries = data.get("timeseries", [])

        # Filter by currency if requested
        if params.currencies:
            wanted = set(c.upper() for c in params.currencies)
            timeseries = [
                ts for ts in timeseries
                if any(
                    h.get("dimItem", "").split(" – ")[-1].split(" ")[0] in wanted
                    or any(w in h.get("dimItem", "") for w in wanted)
                    for h in ts.get("header", [])
                )
            ]
            # More direct filter using key
            timeseries_filtered = []
            for ts in data.get("timeseries", []):
                meta_key = ts.get("metadata", {}).get("key", "")
                for c in params.currencies:
                    if c.upper() in meta_key:
                        # Respect include_month_end filter
                        if not params.include_month_end:
                            if "M1" in meta_key:
                                continue
                        timeseries_filtered.append(ts)
                        break
            timeseries = timeseries_filtered
        else:
            # Filter out month-end rates unless requested
            if not params.include_month_end:
                timeseries = [
                    ts for ts in timeseries
                    if "M1" not in ts.get("metadata", {}).get("key", "")
                ]

        if not timeseries:
            return (
                "Keine Daten für die gewählten Parameter gefunden. "
                "Prüfen Sie die Währungs-IDs mit snb_list_currencies."
            )

        # Build structured result
        result = {
            "cube_id": CUBE_EXCHANGE_RATES_MONTHLY,
            "description": "SNB Wechselkurse – Monatsdaten (CHF-Gegenwert)",
            "source": "https://data.snb.ch",
            "currencies_returned": len(timeseries),
            "timeseries": [],
        }

        for ts in timeseries:
            header = ts.get("header", [])
            meta = ts.get("metadata", {})
            values = ts.get("values", [])
            currency_label = next(
                (h["dimItem"] for h in header if "Währung" in h.get("dim", "")
                 or any(code in h.get("dimItem", "") for code in CURRENCIES)),
                header[-1]["dimItem"] if header else "Unbekannt"
            )
            rate_type = next(
                (h["dimItem"] for h in header if "Monat" in h.get("dimItem", "")),
                "Monatsmittel"
            )
            result["timeseries"].append({
                "currency": currency_label,
                "type": rate_type,
                "unit": meta.get("unit", "CHF"),
                "key": meta.get("key", ""),
                "values": values,
            })

        # Human-readable summary
        lines = [
            f"## SNB Wechselkurse (Monatsdaten) — {len(timeseries)} Zeitreihe(n)\n",
            f"**Quelle:** data.snb.ch | **Cube:** `{CUBE_EXCHANGE_RATES_MONTHLY}`\n",
        ]

        for ts_data in result["timeseries"]:
            vals = ts_data["values"]
            if not vals:
                continue
            last = vals[-1]
            first = vals[0]
            trend = ""
            if len(vals) >= 2:
                delta = last["value"] - first["value"]
                pct = (delta / first["value"]) * 100
                trend = f" (Δ {pct:+.2f}% seit {first['date']})"

            lines.append(
                f"**{ts_data['currency']}** | Aktuellster Wert: "
                f"**{last['value']:.5f} CHF** ({last['date']}){trend}"
            )

        lines.append("\n---\n*Alle Kurse als CHF-Gegenwert um 11 Uhr*")
        lines.append("\n```json")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_get_annual_exchange_rates",
    annotations={
        "title": "SNB Annual Exchange Rates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_annual_exchange_rates(params: AnnualExchangeRatesInput) -> str:
    """Retrieve annual average CHF exchange rates from the SNB (cube 'devkua').

    Returns yearly average exchange rates for all major currencies against CHF.
    Useful for multi-year trend analysis, budget planning, and financial reporting.
    Data goes back to 1980 for most currencies.

    Args:
        params (AnnualExchangeRatesInput):
            - currencies: List of currency IDs (e.g. ['EUR1', 'USD1']). Default: all.
            - from_year: Start year, e.g. '2015'. Default: 5 years ago.
            - to_year: End year, e.g. '2025'. Default: current year.
            - lang: Response language. Default: de.

    Returns:
        str: Markdown summary and JSON data with annual exchange rates.
    """
    try:
        path = f"{CUBE_EXCHANGE_RATES_ANNUAL}/data/json/{params.lang.value}"
        query: dict = {}
        if params.from_year:
            query["fromDate"] = params.from_year
        if params.to_year:
            query["toDate"] = params.to_year

        data = await _fetch_snb(path, query or None)
        timeseries = data.get("timeseries", [])

        # Filter by currency
        if params.currencies:
            wanted = set(c.upper() for c in params.currencies)
            filtered = []
            for ts in timeseries:
                meta_key = ts.get("metadata", {}).get("key", "")
                if any(c in meta_key for c in wanted):
                    filtered.append(ts)
            timeseries = filtered

        if not timeseries:
            return (
                "Keine Daten für die gewählten Parameter. "
                "Prüfen Sie die Währungs-IDs mit snb_list_currencies."
            )

        result = {
            "cube_id": CUBE_EXCHANGE_RATES_ANNUAL,
            "description": "SNB Wechselkurse – Jahresdurchschnitte (CHF-Gegenwert)",
            "source": "https://data.snb.ch",
            "currencies_returned": len(timeseries),
            "timeseries": [],
        }

        lines = [f"## SNB Wechselkurse (Jahresdurchschnitte) — {len(timeseries)} Zeitreihe(n)\n"]

        for ts in timeseries:
            header = ts.get("header", [])
            meta = ts.get("metadata", {})
            values = ts.get("values", [])
            currency_label = header[-1]["dimItem"] if header else "Unbekannt"

            result["timeseries"].append({
                "currency": currency_label,
                "unit": meta.get("unit", "CHF"),
                "key": meta.get("key", ""),
                "values": values,
            })

            if values:
                last = values[-1]
                first = values[0]
                trend = ""
                if len(values) >= 2:
                    delta = last["value"] - first["value"]
                    pct = (delta / first["value"]) * 100
                    trend = f" (Δ {pct:+.2f}% seit {first['date']})"
                lines.append(
                    f"**{currency_label}** | Letzter Jahreswert: "
                    f"**{last['value']:.5f} CHF** ({last['date']}){trend}"
                )

        lines.append("\n```json")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_get_balance_sheet",
    annotations={
        "title": "SNB Balance Sheet Positions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_balance_sheet(params: BalanceSheetInput) -> str:
    """Retrieve SNB balance sheet (Bilanz) data from the data portal (cube 'snbbipo').

    Returns monthly balance sheet positions of the Swiss National Bank in millions
    of CHF. Covers assets (gold, foreign exchange reserves, repos) and liabilities
    (banknotes in circulation, sight deposits of domestic banks, government deposits).

    Key positions:
    - GFG: Gold und Forderungen aus Goldgeschäften
    - D: Devisenanlagen (foreign exchange reserves — the world's largest relative to GDP)
    - N: Notenumlauf (banknotes in circulation)
    - GB: Girokonten inländischer Banken (sight deposits)
    - T0/T1: Total Aktiven / Total Passiven

    Args:
        params (BalanceSheetInput):
            - positions: List of position IDs. Default: key positions (GFG, D, N, GB, T0, T1).
            - from_date: Start month YYYY-MM. Default: 24 months ago.
            - to_date: End month YYYY-MM. Default: latest available.
            - lang: Response language. Default: de.

    Returns:
        str: Markdown summary and JSON data in millions CHF.
    """
    try:
        path = f"{CUBE_BALANCE_SHEET}/data/json/{params.lang.value}"
        query: dict = {}
        if params.from_date:
            query["fromDate"] = params.from_date
        if params.to_date:
            query["toDate"] = params.to_date

        data = await _fetch_snb(path, query or None)
        timeseries = data.get("timeseries", [])

        # Default key positions if none specified
        default_positions = {"GFG", "D", "N", "GB", "T0", "T1"}
        filter_positions = (
            set(p.upper() for p in params.positions)
            if params.positions
            else default_positions
        )

        filtered = []
        for ts in timeseries:
            meta_key = ts.get("metadata", {}).get("key", "")
            for pos_id in filter_positions:
                if f"{{{pos_id}}}" in meta_key or f"{{{pos_id}," in meta_key:
                    filtered.append((pos_id, ts))
                    break

        if not filtered:
            return (
                "Keine Daten für die gewählten Positionen. "
                "Prüfen Sie die Positions-IDs mit snb_list_balance_sheet_positions."
            )

        result = {
            "cube_id": CUBE_BALANCE_SHEET,
            "description": "SNB Bilanzpositionen (in Millionen CHF)",
            "source": "https://data.snb.ch",
            "positions_returned": len(filtered),
            "timeseries": [],
        }

        lines = [
            f"## SNB Bilanz — {len(filtered)} Position(en)\n",
            f"**Einheit:** Millionen CHF | **Quelle:** data.snb.ch\n",
        ]

        for pos_id, ts in filtered:
            header = ts.get("header", [])
            meta = ts.get("metadata", {})
            values = ts.get("values", [])
            label = BALANCE_SHEET_POSITIONS.get(pos_id, header[0]["dimItem"] if header else pos_id)

            result["timeseries"].append({
                "position_id": pos_id,
                "label": label,
                "unit": meta.get("unit", "Millionen CHF"),
                "key": meta.get("key", ""),
                "values": values,
            })

            if values:
                last = values[-1]
                val_bn = last["value"] / 1000  # to billions
                lines.append(
                    f"**{label}** (`{pos_id}`) | "
                    f"Aktuell: **{last['value']:,.1f} Mio. CHF** "
                    f"({val_bn:.1f} Mrd. CHF) — {last['date']}"
                )

        lines.append("\n```json")
        lines.append(json.dumps(result, ensure_ascii=False, indent=2))
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_convert_currency",
    annotations={
        "title": "Currency Conversion via SNB Rates",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_convert_currency(params: ConvertCurrencyInput) -> str:
    """Convert a foreign currency amount to CHF using official SNB exchange rates.

    Uses the monthly average rate (Monatsmittel) from the SNB data portal.
    Suitable for budget calculations, cost estimations, and financial planning.

    Args:
        params (ConvertCurrencyInput):
            - amount: Amount in foreign currency to convert.
            - currency_id: SNB currency ID (e.g. 'EUR1', 'USD1', 'JPY100').
            - reference_month: Month YYYY-MM for the rate. Default: most recent.

    Returns:
        str: CHF equivalent, exchange rate used, and reference date.

    Example:
        amount=45000, currency_id='USD1' → CHF equivalent of USD 45,000
        amount=100, currency_id='JPY100' → CHF equivalent of JPY 100
    """
    try:
        cid = params.currency_id.upper()
        path = f"{CUBE_EXCHANGE_RATES_MONTHLY}/data/json/de"
        query: dict = {}
        if params.reference_month:
            query["fromDate"] = params.reference_month
            query["toDate"] = params.reference_month

        data = await _fetch_snb(path, query or None)
        timeseries = data.get("timeseries", [])

        # Find the matching timeseries (monthly average, not month-end)
        matching_ts = None
        for ts in timeseries:
            meta_key = ts.get("metadata", {}).get("key", "")
            # Must contain the currency ID and M0 (monthly average), not M1 (month-end)
            if f"{{{cid}}}" in meta_key or f",{cid}}}" in meta_key or f"{{{cid}," in meta_key:
                if "M0" in meta_key and "M1" not in meta_key:
                    matching_ts = ts
                    break
            # Fallback: just find currency without specifying type
            if cid in meta_key and "M1" not in meta_key:
                matching_ts = ts
                break

        if not matching_ts:
            available = [CURRENCIES.get(k, k) for k in list(CURRENCIES.keys())[:10]]
            return (
                f"Error: Währung '{cid}' nicht gefunden. "
                f"Verfügbare Währungs-IDs: {', '.join(list(CURRENCIES.keys())[:15])}. "
                f"Vollständige Liste mit snb_list_currencies."
            )

        values = matching_ts.get("values", [])
        if not values:
            return f"Error: Keine Kursdaten für '{cid}' im angegebenen Zeitraum."

        latest = values[-1]
        rate = latest["value"]
        date = latest["date"]
        unit = CURRENCY_UNITS.get(cid, 1)
        currency_label = CURRENCIES.get(cid, cid)

        # Calculate CHF amount
        # rate = CHF per `unit` foreign currency units
        chf_per_one = rate / unit
        chf_amount = params.amount * chf_per_one

        result = {
            "input": {
                "amount": params.amount,
                "currency_id": cid,
                "currency_label": currency_label,
            },
            "rate": {
                "value": rate,
                "unit": f"{unit} {cid.rstrip('0123456789')} = {rate:.5f} CHF",
                "date": date,
                "type": "Monatsmittel (11 Uhr)",
                "source": "data.snb.ch",
            },
            "result": {
                "chf_amount": round(chf_amount, 2),
                "chf_formatted": f"CHF {chf_amount:,.2f}",
            },
        }

        lines = [
            f"## Währungsumrechnung: {params.amount:,.2f} {cid.rstrip('0123456789')} → CHF\n",
            f"**Betrag:** {params.amount:,.2f} {currency_label}",
            f"**SNB-Kurs ({date}):** {rate:.5f} CHF pro {unit} {cid.rstrip('0123456789')} (Monatsmittel)",
            f"**Ergebnis:** **CHF {chf_amount:,.2f}**\n",
            f"*Quelle: data.snb.ch, Kurs vom {date}*",
            "\n```json",
            json.dumps(result, ensure_ascii=False, indent=2),
            "```",
        ]

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_get_cube_data",
    annotations={
        "title": "SNB Generic Cube Data",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_cube_data(params: CubeDataInput) -> str:
    """Retrieve raw data from any SNB data cube by ID.

    Generic tool for accessing SNB cubes beyond the dedicated tools.
    Use snb_get_cube_metadata first to understand the cube structure.
    Browse https://data.snb.ch to discover cube IDs from the URL pattern:
    data.snb.ch/de/topics/{topic}/cube/{cubeId}

    Args:
        params (CubeDataInput):
            - cube_id: SNB cube identifier (lowercase), e.g. 'devkum', 'snbbipo'.
            - from_date: Start date (YYYY-MM for monthly, YYYY for annual).
            - to_date: End date.
            - lang: Response language (de/en/fr).

    Returns:
        str: Raw timeseries data from the cube as JSON.
    """
    try:
        path = f"{params.cube_id}/data/json/{params.lang.value}"
        query: dict = {}
        if params.from_date:
            query["fromDate"] = params.from_date
        if params.to_date:
            query["toDate"] = params.to_date

        data = await _fetch_snb(path, query or None)
        timeseries = data.get("timeseries", [])

        lines = [
            f"## SNB Cube `{params.cube_id}` — {len(timeseries)} Zeitreihe(n)\n",
            f"**Quelle:** data.snb.ch/api/cube/{params.cube_id}\n",
        ]

        if timeseries:
            # Brief summary
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
        lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:8000])
        if len(json.dumps(data)) > 8000:
            lines.append("... (truncated, use a narrower date range)")
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_get_cube_metadata",
    annotations={
        "title": "SNB Cube Metadata and Dimensions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def snb_get_cube_metadata(params: CubeMetadataInput) -> str:
    """Get metadata and dimension structure for any SNB data cube.

    Retrieves the cube's dimension definitions, available filter values,
    and structure. Use this before querying snb_get_cube_data to understand
    what parameters and filters are available.

    Args:
        params (CubeMetadataInput):
            - cube_id: SNB cube identifier, e.g. 'devkum', 'snbbipo'.
            - lang: Language for labels (de/en/fr).

    Returns:
        str: Cube ID, dimensions, and all available dimension item IDs with labels.
    """
    try:
        path = f"{params.cube_id}/dimensions/{params.lang.value}"
        data = await _fetch_snb(path)

        lines = [f"## SNB Cube Metadata: `{params.cube_id}`\n"]

        for dim in data.get("dimensions", []):
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
        lines.append(json.dumps(data, ensure_ascii=False, indent=2))
        lines.append("```")

        return "\n".join(lines)

    except Exception as e:
        return _handle_http_error(e)


@mcp.tool(
    name="snb_list_currencies",
    annotations={
        "title": "List Available SNB Currencies",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_currencies() -> str:
    """List all currency IDs available in SNB exchange rate cubes.

    Returns the full list of currency identifiers that can be used as filter
    values in snb_get_exchange_rates, snb_get_annual_exchange_rates, and
    snb_convert_currency.

    Note on units: some currencies are quoted per 100 units (e.g. JPY100 = 100 JPY).
    The rate value always represents CHF per the stated unit quantity.

    Returns:
        str: Markdown table of currency IDs, names, and unit multipliers.
    """
    lines = [
        "## Verfügbare Währungen (SNB-Devisenkurse)\n",
        "| ID | Bezeichnung | Einheit |",
        "|----|-------------|---------|",
    ]
    for cid, label in CURRENCIES.items():
        unit = CURRENCY_UNITS.get(cid, 1)
        unit_str = f"{unit} {cid.rstrip('0123456789')}"
        lines.append(f"| `{cid}` | {label} | {unit_str} |")

    lines.append(
        "\n*Verwendung: `currencies: ['EUR1', 'USD1']` in snb_get_exchange_rates*"
    )
    return "\n".join(lines)


@mcp.tool(
    name="snb_list_balance_sheet_positions",
    annotations={
        "title": "List SNB Balance Sheet Positions",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_balance_sheet_positions() -> str:
    """List all balance sheet position IDs for the SNB balance sheet cube (snbbipo).

    Returns asset (Aktiven) and liability (Passiven) position IDs with German labels.
    Use these IDs as filter values in snb_get_balance_sheet.

    Returns:
        str: Markdown table of position IDs and labels, grouped by Aktiven/Passiven.
    """
    aktiven = {k: v for k, v in BALANCE_SHEET_POSITIONS.items()
               if k in {"GFG","D","RIWF","IZ","W","FRGSF","FRGUSD","GSGSF",
                        "IG","GD","FI","WSF","DS","UA","T0"}}
    passiven = {k: v for k, v in BALANCE_SHEET_POSITIONS.items()
                if k not in aktiven}

    lines = [
        "## SNB Bilanzpositionen (cube: `snbbipo`)\n",
        "Einheit: Millionen CHF\n",
        "### Aktiven",
        "| ID | Bezeichnung |",
        "|----|-------------|",
    ]
    for pid, label in aktiven.items():
        lines.append(f"| `{pid}` | {label} |")

    lines.append("\n### Passiven")
    lines.append("| ID | Bezeichnung |")
    lines.append("|----|-------------|")
    for pid, label in passiven.items():
        lines.append(f"| `{pid}` | {label} |")

    lines.append(
        "\n*Verwendung: `positions: ['GFG', 'D', 'T0']` in snb_get_balance_sheet*"
    )
    return "\n".join(lines)


@mcp.tool(
    name="snb_list_known_cubes",
    annotations={
        "title": "List Known SNB Data Cubes",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def snb_list_known_cubes() -> str:
    """List all verified SNB data cube IDs with descriptions and available tools.

    Returns Phase 1 cubes (dedicated tools) and Phase 2 cubes (accessible via
    snb_get_cube_data + snb_get_cube_metadata without any code changes).

    Phase 1 cubes: devkum (monthly FX), devkua (annual FX), snbbipo (balance sheet)
    Phase 2 cubes: snbgwdzid (Leitzins/SARON daily), zirepo (SARON compound rates),
                   zimoma (international money market rates), snboffzisa (central bank
                   rates comparison), snbmonagg (M1/M2/M3 aggregates)

    Additional cube IDs can be discovered by browsing data.snb.ch and reading the
    URL pattern: .../topics/{topic}/cube/{cubeId}

    Returns:
        str: Markdown tables of cube IDs grouped by phase, with descriptions,
             tools, frequency, and discovery guidance.
    """
    known_cubes = [
        # ── Phase 1: dedizierte Tools ─────────────────────────────────────────
        {
            "id": "devkum",
            "description": "Wechselkurse – Monatsmittel und Monatsende (27 Währungen)",
            "tool": "snb_get_exchange_rates",
            "frequency": "monatlich",
            "from": "1999",
        },
        {
            "id": "devkua",
            "description": "Wechselkurse – Jahresdurchschnitte (27 Währungen)",
            "tool": "snb_get_annual_exchange_rates",
            "frequency": "jährlich",
            "from": "1980",
        },
        {
            "id": "snbbipo",
            "description": "SNB-Bilanzpositionen (Gold, Devisen, Notenumlauf, Giroguthaben …)",
            "tool": "snb_get_balance_sheet",
            "frequency": "monatlich",
            "from": "2000",
        },
        # ── Phase 2: verifiziert, via snb_get_cube_data nutzbar ───────────────
        {
            "id": "snbgwdzid",
            "description": (
                "SNB-Leitzins (LZ), SARON-Fixing Handelsschluss, Engpassfinanzierungssatz (ENG), "
                "Zinssatz auf Sichtguthaben bis/über Limite (ZIGBL/ZIG) — Tagesdaten"
            ),
            "tool": "snb_get_cube_data",
            "frequency": "täglich",
            "from": "2000",
        },
        {
            "id": "zirepo",
            "description": (
                "SARON Compound Rates: Overnight (H0), 1M (H6), 3M (H7), 6M (H8); "
                "Tomorrow Next (SARTN), 1W (SAR1W) — Repo-Referenzzinssätze"
            ),
            "tool": "snb_get_cube_data",
            "frequency": "täglich",
            "from": "2009",
        },
        {
            "id": "zimoma",
            "description": (
                "Monatliche Geldmarktsätze im int. Vergleich: "
                "SARON (CH), SOFR (USA), TONA (JP), SONIA (UK), €STR + EURIBOR (Eurozone)"
            ),
            "tool": "snb_get_cube_data",
            "frequency": "monatlich",
            "from": "1999",
        },
        {
            "id": "snboffzisa",
            "description": (
                "Offizielle Leitzinssätze im Vergleich: "
                "SNB (CH), Fed (USA), EZB (Eurozone), Bank of England (UK), Bank of Japan (JP)"
            ),
            "tool": "snb_get_cube_data",
            "frequency": "periodisch",
            "from": "1999",
        },
        {
            "id": "snbmonagg",
            "description": (
                "Geldmengenaggregate: M1 (Bargeld + Sichteinlagen + Transaktionskonti), "
                "M2 (M1 + Spareinlagen), M3 (M2 + Termineinlagen) — "
                "Bestand und Vorjahresveränderung"
            ),
            "tool": "snb_get_cube_data",
            "frequency": "monatlich",
            "from": "1995",
        },
    ]

    phase1 = [c for c in known_cubes if c["tool"] != "snb_get_cube_data"]
    phase2 = [c for c in known_cubes if c["tool"] == "snb_get_cube_data"]

    lines = [
        "## Bekannte SNB Data Cubes\n",
        "### Phase 1 — Dedizierte Tools",
        "| Cube-ID | Beschreibung | Tool | Frequenz | Verfügbar seit |",
        "|---------|-------------|------|----------|----------------|",
    ]
    for c in phase1:
        lines.append(
            f"| `{c['id']}` | {c['description']} | `{c['tool']}` | {c['frequency']} | {c['from']} |"
        )

    lines.extend([
        "\n### Phase 2 — Via `snb_get_cube_data` + `snb_get_cube_metadata`",
        "| Cube-ID | Beschreibung | Frequenz | Verfügbar seit |",
        "|---------|-------------|----------|----------------|",
    ])
    for c in phase2:
        lines.append(
            f"| `{c['id']}` | {c['description']} | {c['frequency']} | {c['from']} |"
        )

    lines.extend([
        "\n### Weitere Cubes entdecken",
        "Besuche https://data.snb.ch und navigiere zu einem Datensatz.",
        "Die Cube-ID erscheint in der URL: `.../topics/{topic}/cube/**cubeId**`",
        "\nNutzung: `snb_get_cube_metadata` (Dimensionen verstehen) → `snb_get_cube_data` (Daten abrufen).",
        "\n**Bekannte Themen-Bereiche:**",
        "- `snb` – SNB-Kennzahlen, Leitzins, Geldmengen, Bilanz",
        "- `ziredev` – Devisen / Wechselkurse",
        "- `uvo` – Übrige volkswirtschaftliche Daten",
        "- `aube` – Aussenbeziehungen",
        "\n**Phase 3 — Noch nicht unterstützt:**",
        "Die detaillierte Bankenstatistik (Bilanzsumme, Kreditvolumen nach Bankengruppe)",
        "liegt im Warehouse-API unter `/api/warehouse/cube/BSTA@SNB…` mit eigener Filtersprache.",
        "Direkte Abfrage via `snb_get_cube_data` ist noch nicht möglich.",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
