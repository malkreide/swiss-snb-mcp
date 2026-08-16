# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen: `git fetch origin main && git rev-list --count HEAD..origin/main`
Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Gates lokal fahren, mit der GEPINNTEN ruff-Version aus der CI. Eine andere
Version meldet Abweichungen, die niemand verursacht hat.

### Tests

Gegenprobe ist Pflicht. Ein Test, der grün bleibt, wenn man die
Implementierung entfernt, prüft nichts. Jede neue Zusicherung einzeln
neutralisieren und zeigen, dass genau die zugehörigen Tests fallen.

Zwei Fallen, die beide grün blieben:

- Eine Fake-Uhr, die nur beim Schlafen vorrückt, kann eine Zusicherung über
  echte Zeit nicht widerlegen.
- `monkeypatch.setattr(modul.asyncio, "sleep", ...)` greift ins Modul
  `asyncio` selbst und entschärft die Mechanik im ganzen Prozess. Patche
  einen Modul-Alias (`_sleep = asyncio.sleep`), nicht das fremde Modul.

Handgeschriebene Fixtures kodieren die Annahme des Autors und können sie
nicht widerlegen. Mindestens eine aufgezeichnete Antwort pro externem
Endpunkt, mit Aufnahmedatum.

### Wenn etwas rot ist

Roter Live-Test: erst die Quelle abfragen, dann einordnen. Nicht aus der
Fehlermeldung schliessen. Am 3.8.2026 hiess "nicht gefunden" nicht, dass der
Datensatz weg war, sondern dass die Quelle die Schreibweise ihrer Kopfzeile
gewechselt hatte — vier von sechs Datensätzen produktiv kaputt, alle
Unit-Tests grün.

PR ohne jeden Check ist selten ein Repo ohne CI, meistens ein
Merge-Konflikt: GitHub berechnet dafür keinen Merge-Commit und startet nichts.

Ein Codex-Review auf einem PR wird beantwortet oder behoben, nie ignoriert.

## Teil 2 — dieses Repo

**ruff: eine Quelle.** Der Pin `0.16.1` steht in `pyproject.toml` und `.pre-
commit-config.yaml` — und **nicht** mehr als eigener Install-Schritt in der
CI.

Der CI-Schritt lief nach dem Install der Abhängigkeiten und überschrieb sie.
Eine Abweichung im Pin konnte deshalb in der CI gar nicht auffallen, sondern
nur lokal — wo niemand sie erwartet. Ein manuelles Nachinstallieren von ruff
vor den Gates ist damit nicht mehr nötig und wäre schädlich: Es würde eine
spätere Anhebung hier stillschweigend überstimmen.

`scripts/check_ruff_pin.py` erzwingt das — als pre-commit-Hook *und* als
CI-Schritt. Er prüft beide verbleibenden Stellen auf Gleichstand und
zusätzlich, dass `ci.yml` keinen eigenen Pin zurückbekommt.

**Gates, wörtlich aus der CI** (Jobs `test` und `lint`):

```bash
python -m py_compile src/swiss_snb_mcp/server.py src/swiss_snb_mcp/warehouse.py
python -c "from swiss_snb_mcp.server import mcp; print('Import OK')"
pytest -m "not live" -v
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/
python scripts/check_version_sync.py
python scripts/check_ruff_pin.py
```

Dazu ein Schritt „Format-Stabilität der Portfolio-Skripte": die zwischen den
Repos kopierten `scripts/check_*.py` werden gegen mehrere `line-length`-Werte
geprüft, weil dieses Repo mit 88 die schmalste Breite im Portfolio fährt. Kein
`include` unter `[tool.ruff]` setzen — der Umfang stimmt (13 Dateien über alle
drei Verzeichnisse, nachgemessen).

**Live-Tests:** eigener Job in `ci.yml`, nächtlich per Cron (`17 3 * * *`) plus
`workflow_dispatch`. Ein roter Lauf legt ein Issue an oder schliesst es wieder;
dafür braucht der Job `issues: write`. DRIFT-005 ist erfüllt.
