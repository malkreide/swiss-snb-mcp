[🇬🇧 English Version](README.md)

# swiss-snb-mcp

![Version](https://img.shields.io/badge/version-0.2.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![MCP](https://img.shields.io/badge/MCP-kompatibel-purple)

> MCP-Server für das Datenportal der Schweizerischen Nationalbank — Wechselkurse, Bilanz, Zinssätze, SARON und Geldmengen.

## Übersicht

`swiss-snb-mcp` verbindet KI-Modelle mit dem offiziellen Datenportal der Schweizerischen Nationalbank unter [data.snb.ch](https://data.snb.ch) über das Model Context Protocol (MCP). Der Zugriff erfolgt über die öffentliche REST-API — keine Authentifizierung erforderlich.

Der Server deckt zwei Stufen verifizierter Datensätze ab:

**Phase 1 — Dedizierte Tools:**
- **Wechselkurse** (Monatsmittel, Monatsende, Jahresdurchschnitte) für 27 Währungen in CHF
- **SNB-Bilanz**: Gold, Devisenanlagen, Notenumlauf, Giroguthaben, Totals

**Phase 2 — Via generische Cube-Tools (`snb_get_cube_data` + `snb_get_cube_metadata`):**
- **SNB-Leitzins und SARON** (täglich): Leitzins, SARON-Fixing, Engpassfinanzierungssatz, Sichtguthaben-Zinssätze
- **SARON Compound Rates**: Overnight, 1M, 3M, 6M
- **Internationale Geldmarktsätze**: SARON (CH), SOFR (USA), TONA (JP), SONIA (UK), €STR/EURIBOR (EZ)
- **Offizielle Leitzinssätze im Vergleich**: SNB, Fed, EZB, Bank of England, Bank of Japan
- **Geldmengenaggregate M1, M2, M3**: Bestände und Vorjahresveränderungen

Alle Daten stammen von der Schweizerischen Nationalbank und sind in CHF ausgewiesen.

## Funktionen

- `snb_get_exchange_rates` — Monatliche CHF-Kurse für EUR, USD, JPY, GBP, CNY und 22 weitere Währungen
- `snb_get_annual_exchange_rates` — Jahresdurchschnitte, Daten ab 1980
- `snb_get_balance_sheet` — SNB-Bilanzpositionen in Millionen CHF (monatlich)
- `snb_convert_currency` — Betrag in CHF umrechnen mit offiziellen SNB-Kursen
- `snb_get_cube_data` — Generischer Zugriff auf beliebige SNB-Cubes
- `snb_get_cube_metadata` — Dimensionen und Filterwerte eines Cubes abfragen
- `snb_list_currencies` — Alle 27 Währungs-IDs mit Bezeichnungen und Einheiten
- `snb_list_balance_sheet_positions` — Alle Bilanzpositionen (Aktiven/Passiven)
- `snb_list_known_cubes` — Übersicht aller 8 verifizierten Cubes (Phase 1 + 2) und Entdeckungshinweise

## Voraussetzungen

- Python 3.11+
- `uv` oder `pip`
- MCP-kompatibler Client (Claude Desktop, Claude Code oder beliebiger MCP-Host)

## Installation

**Via uvx (empfohlen — keine Installation nötig):**

```bash
uvx swiss-snb-mcp
```

**Via pip:**

```bash
pip install swiss-snb-mcp
```

**Aus dem Quellcode:**

```bash
git clone https://github.com/malkreide/swiss-snb-mcp.git
cd swiss-snb-mcp
pip install -e .
```

## Verwendung

**Claude Desktop — in `claude_desktop_config.json` eintragen:**

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

**Beispiel-Prompts:**

```
Was ist der aktuelle EUR/CHF-Kurs gemäss SNB?

Zeige mir die SNB-Bilanz der letzten 12 Monate — Gold und Devisenanlagen.

Rechne USD 45'000 in CHF um mit dem offiziellen SNB-Kurs.

Wie hat sich der EUR/CHF-Kurs seit 2015 entwickelt?

Wie war der CHF/USD-Kurs im Jahr des Frankenschocks 2015?
```

## Konfiguration

Kein API-Schlüssel oder Authentifizierung erforderlich. Das SNB-Datenportal ist vollständig öffentlich zugänglich.

**Optionale Umgebungsvariable:**

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `SNB_TIMEOUT` | `15` | HTTP-Timeout in Sekunden |

## Projektstruktur

```
swiss-snb-mcp/
├── src/
│   └── swiss_snb_mcp/
│       ├── __init__.py
│       └── server.py       # Alle Tools und FastMCP-Server
├── pyproject.toml
├── README.md
├── README.de.md
├── CHANGELOG.md
└── LICENSE
```

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE)

## Autor

Hayal · [malkreide](https://github.com/malkreide)

---

*Teil des Swiss Public Data MCP-Portfolios — KI-Modelle mit Schweizer Open-Data-Quellen verbinden.*
