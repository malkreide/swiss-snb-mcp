[🇬🇧 English Version](README.md)

> 🇨🇭 **Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide)**

# 🏦 swiss-snb-mcp

![Version](https://img.shields.io/badge/version-0.2.0-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
[![Datenquelle](https://img.shields.io/badge/Daten-data.snb.ch-red)](https://data.snb.ch)

> MCP-Server für das Datenportal der Schweizerischen Nationalbank — Wechselkurse, Bilanz, Zinssätze, SARON und Geldmengen.

---

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

**Anker-Demo-Abfrage:** *«Wie war der EUR/CHF-Kurs während des Frankenschocks 2015, und wie steht der SNB-Leitzins heute im Vergleich zu Fed und EZB?»*

---

## Funktionen

- 💱 **Wechselkurse** — monatliche CHF-Kurse für EUR, USD, JPY, GBP, CNY und 22 weitere Währungen
- 📅 **Jahresdurchschnitte** — jahresweise Kurse ab 1980
- 🏛️ **SNB-Bilanz** — Gold, Devisenanlagen, Notenumlauf, Giroguthaben (monatlich)
- 🔄 **Währungsumrechnung** — Betrag in CHF umrechnen mit offiziellen SNB-Kursen
- 📈 **Leitzins & SARON** — tägliches Fixing, Leitzins, Compound Rates (1M/3M/6M)
- 🌍 **Internationaler Zinsvergleich** — SNB, Fed, EZB, Bank of England, Bank of Japan im direkten Vergleich
- 💰 **Geldmengenaggregate** — M1, M2, M3 Bestände und Vorjahreswachstum
- 🔍 **Generischer Cube-Zugriff** — beliebige SNB-Datenwürfel für erweiterte Anwendungsfälle
- 🔓 **Keine Authentifizierung erforderlich** — vollständig öffentliches SNB-Datenportal

---

## Voraussetzungen

- Python 3.11+
- `uv` oder `pip`
- MCP-kompatibler Client (Claude Desktop, Claude Code oder beliebiger MCP-Host)

---

## Installation

**Via uvx (empfohlen — keine dauerhafte Installation nötig):**

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

---

## Schnellstart

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

**Pfad zur Konfigurationsdatei:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Sofort in Claude Desktop ausprobieren:

> *«Was ist der aktuelle EUR/CHF-Kurs gemäss SNB?»*
> *«Zeige mir die SNB-Bilanz der letzten 12 Monate — Gold und Devisenanlagen.»*

---

## Konfiguration

Kein API-Schlüssel oder Authentifizierung erforderlich. Das SNB-Datenportal ist vollständig öffentlich zugänglich.

**Optionale Umgebungsvariable:**

| Variable | Standard | Beschreibung |
|---|---|---|
| `SNB_TIMEOUT` | `15` | HTTP-Timeout in Sekunden |

---

## Verfügbare Tools

### Phase 1 — Dedizierte Tools

| Tool | Beschreibung |
|---|---|
| `snb_get_exchange_rates` | Monatliche CHF-Kurse für EUR, USD, JPY, GBP, CNY und 22 weitere Währungen |
| `snb_get_annual_exchange_rates` | Jahresdurchschnitte, Daten ab 1980 |
| `snb_get_balance_sheet` | SNB-Bilanzpositionen in Millionen CHF (monatlich) |
| `snb_convert_currency` | Betrag in CHF umrechnen mit offiziellen SNB-Kursen |
| `snb_list_currencies` | Alle 27 Währungs-IDs mit Bezeichnungen und Einheiten |
| `snb_list_balance_sheet_positions` | Alle Bilanzpositionen (Aktiven/Passiven) |

### Phase 2 — Generische Cube-Tools

| Tool | Beschreibung |
|---|---|
| `snb_get_cube_data` | Generischer Zugriff auf beliebige SNB-Cubes nach ID |
| `snb_get_cube_metadata` | Dimensionen und Filterwerte eines Cubes abfragen |
| `snb_list_known_cubes` | Übersicht aller 8 verifizierten Cubes (Phase 1 + 2) und Entdeckungshinweise |

### Beispiel-Abfragen

| Abfrage | Tool |
|---|---|
| *«Was ist der aktuelle EUR/CHF-Kurs?»* | `snb_get_exchange_rates` |
| *«Rechne CHF 10'000 in USD um»* | `snb_convert_currency` |
| *«SNB-Goldreserven der letzten 12 Monate»* | `snb_get_balance_sheet` |
| *«Wie hoch ist der aktuelle SNB-Leitzins?»* | `snb_get_cube_data` (Cube: `snb_leitzinsen`) |
| *«SNB, Fed und EZB Zinsen im Vergleich»* | `snb_get_cube_data` (Cube: `zib_gab`) |
| *«SARON 3M Compound Rate der letzten 6 Monate»* | `snb_get_cube_data` (Cube: `snb_saron_compound`) |
| *«Wie schnell wächst die Geldmenge M3?»* | `snb_get_cube_data` (Cube: `snb_geldmengen`) |
| *«Welche Cubes sind verfügbar?»* | `snb_list_known_cubes` |

---

## Architektur

```
┌─────────────────┐     ┌───────────────────────────┐     ┌──────────────────────┐
│   Claude / KI   │────▶│     Swiss SNB MCP         │────▶│     data.snb.ch      │
│   (MCP Host)    │◀────│     (MCP Server)          │◀────│                      │
└─────────────────┘     │                           │     │  REST API (JSON)     │
                        │  9 Tools                  │     │  Öffentlich · Kein   │
                        │  Stdio | SSE              │     │  Login erforderlich  │
                        │                           │     │                      │
                        │  Phase 1: ded. Tools      │     │  Wechselkurse        │
                        │  Phase 2: gen. Cubes      │     │  Bilanz              │
                        └───────────────────────────┘     │  Zinssätze / SARON   │
                                                          │  Geldmengen          │
                                                          └──────────────────────┘
```

### Cube-Entdeckungsmuster

Die SNB-API folgt einer einheitlichen Cube-Struktur. Mit `snb_list_known_cubes` lassen sich verifizierte Cube-IDs erkunden, dann mit `snb_get_cube_metadata` die Dimensionen prüfen, bevor `snb_get_cube_data` für die eigentliche Abfrage genutzt wird. Diese generische Schicht ermöglicht Zugriff auf den gesamten SNB-Datenkatalog ohne dedizierte Tools pro Datensatz.

---

## Projektstruktur

```
swiss-snb-mcp/
├── src/
│   └── swiss_snb_mcp/
│       ├── __init__.py
│       └── server.py       # Alle Tools und FastMCP-Server
├── tests/                  # Testsammlung
├── pyproject.toml          # Build-Konfiguration (hatchling)
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md               # Englische Hauptversion
└── README.de.md            # Diese Datei (Deutsch)
```

---

## Bekannte Einschränkungen

- **Wechselkurse:** Nur Monatsmittel — keine Tages- oder Intraday-Kurse über diese API verfügbar
- **Bilanz:** Monatsdaten; einzelne Positionen können mit 1–2 Monaten Publikationsverzug erscheinen
- **Cube-Zugriff:** Cube-IDs sind von der SNB nicht offiziell dokumentiert — `snb_list_known_cubes` für verifizierte IDs verwenden
- **Historische Tiefe:** Abdeckung je nach Zeitreihe unterschiedlich; Wechselkurse ab 1980, einige Zinssätze beginnen später
- **Keine Prognosen:** Alle Daten sind historisch/realisiert — die SNB veröffentlicht keine Prognosen über diese API

---

## Tests

```bash
# Unit-Tests (keine API-Verbindung erforderlich)
PYTHONPATH=src pytest tests/ -m "not live"

# Integrationstests (Live-SNB-API)
PYTHONPATH=src pytest tests/ -m "live"
```

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

---

## Mitwirken

Hinweise zum Melden von Fehlern, Vorschlagen neuer SNB-Cube-IDs und Beiträgen zum Code: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE)

---

## Autor

Hayal Oezkan · [github.com/malkreide](https://github.com/malkreide)

---

## Credits & Verwandte Projekte

- **Daten:** [Schweizerische Nationalbank](https://data.snb.ch) — SNB-Datenportal (öffentliche REST-API)
- **Protokoll:** [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic / Linux Foundation
- **Verwandt:** [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) — MCP-Server für Zürcher Stadtdaten
- **Verwandt:** [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) — MCP-Server für den Schweizer ÖV
- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
