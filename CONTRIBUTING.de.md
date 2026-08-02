# Beitragen zu swiss-snb-mcp

[🇬🇧 English Version](CONTRIBUTING.md)

Vielen Dank für Ihr Interesse an einem Beitrag zu `swiss-snb-mcp`! Dieses Projekt ist Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide).

---

## Möglichkeiten zum Mitwirken

### Fehler melden

Eröffnen Sie ein [GitHub-Issue](https://github.com/malkreide/swiss-snb-mcp/issues) und geben Sie an:

- Eine klare Beschreibung des Problems
- Schritte zur Reproduktion
- Erwartetes vs. tatsächliches Verhalten
- Python-Version und Betriebssystem

### Einen neuen SNB-Cube vorschlagen

Das SNB-Datenportal enthält viele Cubes über die in diesem Server verifizierten hinaus. Wenn Sie eine nützliche Cube-ID entdecken:

1. Eröffnen Sie ein Issue mit dem Titel `[Cube] <cube_id>: <kurze Beschreibung>`
2. Geben Sie die Cube-ID, einen Beispiel-API-Aufruf und eine Beschreibung der enthaltenen Daten an
3. Verifizieren Sie sie idealerweise vor dem Einreichen gegen die Live-API

### Dokumentation verbessern

Tippfehler, unklare Erklärungen oder fehlende Beispiele sind als Pull Requests immer willkommen — kein Issue nötig.

### Code beitragen

1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch: `git checkout -b feat/mein-feature`
3. Halten Sie sich an den Code-Stil (Ruff für Linting/Formatierung)
4. Ergänzen oder aktualisieren Sie Tests in `tests/`
5. Führen Sie die Test-Suite vor dem Einreichen aus: `PYTHONPATH=src pytest tests/ -m "not live"`
6. Reichen Sie einen Pull Request mit einer klaren Beschreibung Ihrer Änderungen ein

---

## Entwicklungs-Setup

```bash
git clone https://github.com/malkreide/swiss-snb-mcp.git
cd swiss-snb-mcp
pip install -e ".[dev]"
pre-commit install
```

**Pre-Commit-Hook:**

`pre-commit install` ist ein einmaliger Schritt pro Clone. Er aktiviert die
Hooks aus `.pre-commit-config.yaml`, die den `lint`-Job der CI spiegeln:
`ruff check`, `ruff format`, den Versions-Sync-Check und den
Ruff-Pin-Sync-Check. Was durch den Hook kommt, kommt auch durch diesen Job.

Zwei Details, die man kennen sollte:

- Der Hook nutzt Ruff in der Version, die in `.pre-commit-config.yaml` gepinnt
  ist, in einer eigenen isolierten Umgebung — nicht das lokal installierte
  Ruff. Dieser Pin und der `ruff==…`-Pin in `.github/workflows/ci.yml` müssen
  übereinstimmen; beim Anheben beide Stellen ändern.
  `scripts/check_ruff_pin.py` erzwingt das, im Hook wie in der CI.
- `ruff format` formatiert die Dateien direkt um und lässt den Commit dann
  fehlschlagen. Die umformatierten Dateien stagen und erneut committen.
  `ruff check` meldet nur, genau wie die CI.

Die Hooks über den ganzen Baum laufen lassen, ohne zu committen:

```bash
pre-commit run --all-files
```

**Tests ausführen:**

```bash
# Unit-Tests (keine Netzwerkverbindung erforderlich)
PYTHONPATH=src pytest tests/ -m "not live"

# Integrationstests (Live-SNB-API)
PYTHONPATH=src pytest tests/ -m "live"
```

**Linten und formatieren:**

```bash
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/
```

---

## Commit-Konvention

Dieses Projekt verwendet [Conventional Commits](https://www.conventionalcommits.org/):

| Präfix | Verwendung |
|---|---|
| `feat:` | Neues Tool oder neuer SNB-Datensatz |
| `fix:` | Fehlerbehebung |
| `docs:` | Nur Dokumentation |
| `test:` | Tests hinzufügen oder aktualisieren |
| `refactor:` | Code-Umstrukturierung ohne Verhaltensänderung |
| `chore:` | Build, Abhängigkeiten, CI |

---

## Verhaltenskodex

Seien Sie respektvoll und konstruktiv. Dies ist ein kleines Open-Source-Projekt, das in der Freizeit gepflegt wird — Geduld wird geschätzt.

---

## Lizenz

Mit Ihrem Beitrag erklären Sie sich damit einverstanden, dass Ihre Beiträge unter der [MIT-Lizenz](LICENSE) lizenziert werden.
