> 🇨🇭 **Part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide)**

# 🏦 swiss-snb-mcp

![Version](https://img.shields.io/badge/version-0.2.0-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![Data Source](https://img.shields.io/badge/Data-data.snb.ch-red)](https://data.snb.ch)

> MCP server for the Swiss National Bank (SNB) data portal — exchange rates, balance sheet, interest rates, SARON, and monetary aggregates.

[🇩🇪 Deutsche Version](README.de.md)

---

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

**Anchor demo query:** *"What was the EUR/CHF exchange rate during the 2015 Franc shock, and where does the SNB policy rate stand today compared to the Fed and ECB?"*

---

## Features

- 💱 **Exchange rates** — monthly CHF rates for EUR, USD, JPY, GBP, CNY and 22 more currencies
- 📅 **Annual averages** — year-by-year rates from 1980 onwards
- 🏛️ **SNB balance sheet** — gold, foreign exchange investments, banknotes, sight deposits (monthly)
- 🔄 **Currency conversion** — convert any amount to CHF using official SNB rates
- 📈 **Policy rate & SARON** — daily fixing, Leitzins, compound rates (1M/3M/6M)
- 🌍 **International rate comparison** — SNB, Fed, ECB, Bank of England, Bank of Japan side by side
- 💰 **Monetary aggregates** — M1, M2, M3 stock levels and year-on-year growth
- 🔍 **Generic cube access** — query any SNB data cube by ID for advanced use cases
- 🔓 **No authentication required** — fully public SNB data portal

---

## Prerequisites

- Python 3.11+
- `uv` or `pip`
- MCP-compatible client (Claude Desktop, Claude Code, or any MCP host)

---

## Installation

**Via uvx (recommended — no permanent installation needed):**

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

---

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

**Config file locations:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Try it immediately in Claude Desktop:

> *"What is the current EUR/CHF exchange rate according to the SNB?"*
> *"Show me the SNB balance sheet for the last 12 months — gold and foreign reserves."*

---

## Configuration

No API key or authentication required. The SNB data portal is fully public.

**Optional environment variable:**

| Variable | Default | Description |
|---|---|---|
| `SNB_TIMEOUT` | `15` | HTTP request timeout in seconds |

---

## Available Tools

### Phase 1 — Dedicated Tools

| Tool | Description |
|---|---|
| `snb_get_exchange_rates` | Monthly CHF rates for EUR, USD, JPY, GBP, CNY and 22 more currencies |
| `snb_get_annual_exchange_rates` | Annual average rates, data from 1980 |
| `snb_get_balance_sheet` | SNB Bilanz positions in millions CHF (monthly) |
| `snb_convert_currency` | Convert any amount to CHF using official SNB rates |
| `snb_list_currencies` | List all 27 currency IDs with labels and units |
| `snb_list_balance_sheet_positions` | List all asset and liability position IDs |

### Phase 2 — Generic Cube Tools

| Tool | Description |
|---|---|
| `snb_get_cube_data` | Generic access to any SNB cube by ID |
| `snb_get_cube_metadata` | Inspect dimensions and filter values of any cube |
| `snb_list_known_cubes` | Overview of all 8 verified cubes (Phase 1 + 2) and discovery guide |

### Example Use Cases

| Query | Tool |
|---|---|
| *"What is the current EUR/CHF rate?"* | `snb_get_exchange_rates` |
| *"Convert CHF 10,000 to USD"* | `snb_convert_currency` |
| *"Show SNB gold reserves over the last year"* | `snb_get_balance_sheet` |
| *"What is the current SNB policy rate?"* | `snb_get_cube_data` (cube: `snb_leitzinsen`) |
| *"How do SNB, Fed and ECB rates compare?"* | `snb_get_cube_data` (cube: `zib_gab`) |
| *"What is the SARON 3M compound rate?"* | `snb_get_cube_data` (cube: `snb_saron_compound`) |
| *"How fast is M3 money supply growing?"* | `snb_get_cube_data` (cube: `snb_geldmengen`) |
| *"Which cubes are available?"* | `snb_list_known_cubes` |

---

## Architecture

```
┌─────────────────┐     ┌───────────────────────────┐     ┌──────────────────────┐
│   Claude / AI   │────▶│     Swiss SNB MCP         │────▶│     data.snb.ch      │
│   (MCP Host)    │◀────│     (MCP Server)          │◀────│                      │
└─────────────────┘     │                           │     │  REST API (JSON)     │
                        │  9 Tools                  │     │  Public · No Auth    │
                        │  Stdio | SSE              │     │                      │
                        │                           │     │  Exchange rates      │
                        │  Phase 1: dedicated tools │     │  Balance sheet       │
                        │  Phase 2: generic cubes   │     │  Interest rates      │
                        └───────────────────────────┘     │  SARON               │
                                                          │  Monetary aggregates │
                                                          └──────────────────────┘
```

### Cube Discovery Pattern

The SNB API follows a consistent cube-based structure. Use `snb_list_known_cubes` to explore verified cube IDs, then `snb_get_cube_metadata` to inspect dimensions before querying with `snb_get_cube_data`. This generic layer gives access to the full SNB data catalogue without needing dedicated tools for each dataset.

---

## Project Structure

```
swiss-snb-mcp/
├── src/
│   └── swiss_snb_mcp/
│       ├── __init__.py
│       └── server.py       # All tools and FastMCP server
├── tests/                  # Test suite
├── pyproject.toml          # Build configuration (hatchling)
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md               # This file (English)
└── README.de.md            # German version
```

---

## Known Limitations

- **Exchange rates:** Monthly averages only — no intraday or daily rates available via this API
- **Balance sheet:** Monthly data; some positions may have a publication lag of 1–2 months
- **Cube access:** Cube IDs are not officially documented by the SNB — use `snb_list_known_cubes` for verified IDs
- **Historical depth:** Coverage varies by series; exchange rates go back to 1980, some interest rate series start later
- **No forecasts:** All data is historical/realised — SNB does not publish forecasts via this API

---

## Testing

```bash
# Unit tests (no API key required)
PYTHONPATH=src pytest tests/ -m "not live"

# Integration tests (live SNB API)
PYTHONPATH=src pytest tests/ -m "live"
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting issues, suggesting new SNB cube IDs, and contributing code.

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Author

Hayal Oezkan · [github.com/malkreide](https://github.com/malkreide)

---

## Credits & Related Projects

- **Data:** [Swiss National Bank](https://data.snb.ch) — SNB data portal (public REST API)
- **Protocol:** [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic / Linux Foundation
- **Related:** [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) — MCP server for Zurich city open data
- **Related:** [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) — Swiss public transport MCP server
- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
