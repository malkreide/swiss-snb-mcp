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

## Die Live-Suite: wann sie läuft, und wer ein rotes Ergebnis sieht

**Kadenz:** täglich um 03:17 UTC, dazu jederzeit von Hand über *Actions → CI → Run
workflow*. Siehe [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

**Wer es sieht:** Ein roter Lauf öffnet ein Issue mit dem Label `upstream` und dem stabilen Titel «Live-Tests gegen data.snb.ch rot (<Datum>)». Ein zweiter roter Lauf erkennt das offene Issue am Titelanfang und hängt sich an denselben Thread, statt ein zweites aufzumachen. Wird die Suite wieder grün, schliesst sich das Issue selbst.

**Drei Antworten, nicht zwei.** `scripts/classify_live_scenarios.py` liest das JUnit-XML statt des
Exit-Codes und unterscheidet: `clear` (gelaufen, grün), `finding` (gelaufen,
etwas gefallen) und `unknown` (nicht gelaufen — Installation gescheitert, null
Tests eingesammelt, alle übersprungen). Ein `unknown` schliesst nie ein Issue:
Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der Quelle hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — so stirbt dieser Check, und er ist der einzige im Repo, der
einer falschen Grundannahme über data.snb.ch widersprechen kann. Jeder andere Test
prüft gegen eine Fixture, und die Fixture ist aus derselben Annahme geschrieben
wie der Code.

## Lizenz

Mit Ihrem Beitrag erklären Sie sich damit einverstanden, dass Ihre Beiträge unter der [MIT-Lizenz](LICENSE) lizenziert werden.

## Der nächtliche Live-Lauf: wer ein rotes Ergebnis sieht

**Kadenz:** jede Nacht um 03:17 UTC, dazu von Hand über *Actions → CI → Run
workflow*. Der `live`-Job läuft nie auf einem Pull Request — ein Ausfall von
`data.snb.ch` darf den Mainline-Build nicht in Geiselhaft nehmen.

Diesen Job gibt es, seit dieses Repo geschrieben wurde. Was fehlte, ist das
Folgende: **Ein rotes Ergebnis sah niemand.** Ein geplanter Lauf, dessen Ausgang
nur als roter Eintrag im Actions-Tab landet, ist eine teurere Variante von «läuft
nicht» — rote Cron-Jobs werden nach der zweiten Woche nicht mehr angeschaut.

**Wer es jetzt sieht:** Eine rote Nacht öffnet ein Issue mit dem Titel
`Live-Tests gegen data.snb.ch rot …` und dem Label `upstream` — und kommentiert
das bestehende, statt ein zweites aufzumachen. Bei einem *täglichen* Cron ist das
keine Feinheit, sondern der Unterschied zwischen einem Thread und dreissig Issues
im Monat. Wird der Lauf wieder grün, wird es geschlossen.

**Drei Antworten, nicht zwei.** `scripts/classify_live_scenarios.py` liest die
Summenzeile der Szenarienläufe statt nur den Exit-Code und trennt `clear`
(gelaufen, alle bestanden), `finding` (gelaufen, etwas gefallen) und `unknown`
(nicht gelaufen — Installation gescheitert, Timeout, Import-Fehler oder **null
registrierte Szenarien**). Der letzte Fall zählt: `main()` gibt `FAILED == 0`
zurück, was bei null Szenarien `True` ist — ein grüner Lauf, der nichts geprüft
hat. Ein `unknown` schliesst nie ein Issue: Zuzumachen hiesse zu behaupten, der
Vergleich sei gelaufen.

**Ein roter Live-Lauf heisst nicht zwingend «unser Fehler».** Er heisst: Der
Vertrag mit der SNB hat sich geändert, oder die Quelle ist gerade aus. Beides
gehört gesehen, nur das Erste gehört gefixt. Bitte den Lauf lesen, bevor der Job
deaktiviert wird — die Live-Szenarien sind die einzigen Tests hier, die einer
falschen Grundannahme über `data.snb.ch` widersprechen können, denn jeder andere
Test prüft gegen eine Fixture, die aus derselben Annahme geschrieben ist.
