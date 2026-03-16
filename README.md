# swiss-snb-mcp

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)

> MCP server for the Swiss National Bank (SNB) data portal — exchange rates, balance sheet, interest rates, SARON, and monetary aggregates.

[🇩🇪 Deutsche Version](README.de.md)

## Overview

`swiss-snb-mcp` connects AI models to the official Swiss National Bank data portal at [data.snb.ch](https://data.snb.ch) via the Model Context Protocol (MCP). It provides structured access to SNB's public REST API — no authentication required.

The server covers two tiers of datasets, all confirmed against the live API:

**Phase 1 — Dedicated tools:**
- **Exchange rates** (monthly averages, month-end rates, annual averages) for 27 currencies against CHF
- **SNB balance sheet** (Bilanz): gold reserves, foreign exchange investments, banknotes in circulation, sight deposits, and totals

**Phase 2 — Via generic cube tools (`snb_get_cube_data` + `snb_get_cube_metadata`):**
- **SNB policy rate (Leitzins) and SARON** daily fixing, emergency facility rate, sight deposit rates
- **SARON compound rates**: Overnight, 1M, 3M, 6M
- **International money market rates**: SARON (CH), SOFR (USA), TONA (JP), SONIA (UK), €STR/EURIBOR (EZ)
- **Official central bank rates**: SNB, Fed, ECB, Bank of England, Bank of Japan
- **Monetary aggregates M1, M2, M3**: stock levels and year-on-year changes

All data is sourced from the Swiss National Bank and expressed in CHF.

## Features

- `snb_get_exchange_rates` — monthly CHF rates for EUR, USD, JPY, GBP, CNY and 22 more currencies
- `snb_get_annual_exchange_rates` — annual average rates, data from 1980
- `snb_get_balance_sheet` — SNB Bilanz positions in millions CHF (monthly)
- `snb_convert_currency` — convert any amount to CHF using official SNB rates
- `snb_get_cube_data` — generic access to any SNB cube by ID
- `snb_get_cube_metadata` — inspect dimensions and filter values of any cube
- `snb_list_currencies` — list all 27 currency IDs with labels and units
- `snb_list_balance_sheet_positions` — list all asset and liability position IDs
- `snb_list_known_cubes` — overview of all 8 verified cubes (Phase 1 + 2) and discovery guide

## Prerequisites

- Python 3.11+
- `uv` or `pip`
- MCP-compatible client (Claude Desktop, Claude Code, or any MCP host)

## Installation

**Via uvx (recommended — no install needed):**

```bash
uvx swiss-snb-mcp
```

**Via pip:**

```bash
pip install swiss-snb-mcp
```

**From source:**

```bash
git clone https://github.com/malkreide/swiss-snb-mcp.git
cd swiss-snb-mcp
pip install -e .
```

## Usage / Quickstart

**Claude Desktop — add to `claude_desktop_config.json`:**

```json
{
  "mcpServers": {
    "swiss-snb-mcp": {
      "command": "uvx",
      "args": ["swiss-snb-mcp"]
    }
  }
}
```

**Example prompts:**

```
What is the current EUR/CHF exchange rate according to the SNB?

Show me the SNB balance sheet for the last 12 months — gold and foreign reserves.

Convert USD 45,000 to CHF using the official SNB rate.

How has the EUR/CHF rate developed since 2015?

What is the current SNB policy rate (Leitzins) and how has it changed since 2022?

Show me the SARON 3M compound rate for the last 6 months.

How do the SNB, Fed, ECB, and Bank of England interest rates compare right now?

What is the current M3 money supply in Switzerland and how fast is it growing?
```

## Configuration

No API key or authentication required. The SNB data portal is fully public.

**Optional environment variable:**

| Variable | Default | Description |
|----------|---------|-------------|
| `SNB_TIMEOUT` | `15` | HTTP request timeout in seconds |

## Project Structure

```
swiss-snb-mcp/
├── src/
│   └── swiss_snb_mcp/
│       ├── __init__.py
│       └── server.py       # All tools and FastMCP server
├── pyproject.toml
├── README.md
├── README.de.md
├── CHANGELOG.md
└── LICENSE
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

## License

MIT License — see [LICENSE](LICENSE)

## Author

Hayal · [malkreide](https://github.com/malkreide)

---

*Part of the Swiss Public Data MCP portfolio — connecting AI models to Swiss open data sources.*
