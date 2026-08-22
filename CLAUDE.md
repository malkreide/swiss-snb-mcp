# CLAUDE.md

## Teil 1 — Konventionen (portfolio-weit)

### Vor der Arbeit

Klon-Aktualität prüfen — Standard-Branch ermitteln, nicht `main` annehmen:

```bash
B=$(git ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p')
git fetch origin "${B:?Standard-Branch nicht ermittelbar}" &&
  git rev-list --count HEAD..FETCH_HEAD
```

Drei Server im Portfolio heissen ihren Standard-Branch `master`
(`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`); dort scheitert ein fest
verdrahtetes `origin/main` mit «couldn't find remote ref main». Wer das für ein
Netzproblem hält, arbeitet weiter auf genau dem veralteten Klon, vor dem dieser
Absatz warnt. Den `:?`-Schutz nicht weglassen: Bei leerem `B` fetcht git still
den Remote-HEAD und endet mit 0.

Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht.
Am 3.8.2026 zweimal passiert — beide Male fehlten genau die Commits, die
das Gate einführten, an dem der Branch scheiterte.

Seit `.claude/settings.json` läuft diese Prüfung beim Sessionstart von selbst
(`.claude/hooks/session-start.sh`, Begründung und Testlage in
`.claude/hooks/README.md`). Sie meldet nur, wenn Commits fehlen, und blockiert
nie — ohne Netz oder ohne Remote geht sie still durch. Der Hook ersetzt den
Befehl oben also nicht, er erinnert bloss zuverlässiger als ein Absatz.

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

### Wenn Codex gar nicht erst hinsieht

Die Zeile oben unterstellt, dass es einen Befund geben *kann*. Das ist nicht
immer so, und man sieht es dem PR nicht an.

Am 21.8.2026 war das Code-Review-Kontingent zwischen 08:41 und 09:48
aufgebraucht — davor echte Reviews, danach in 30 Repos nur noch:

```
You have reached your Codex usage limits for code reviews.
```

Bis mindestens zum 22.8. um 08:30, also 23 Stunden später, blieb es dabei. In
der Zwischenzeit sind 32 PRs mit formal erfülltem Häkchen gemergt worden, ohne
dass jemand hineingesehen hat.

Drei Gründe, warum Codex schweigt, und nur einer davon ist harmlos:

- **Kein Befund** — dann reagiert er mit 👍 und schreibt nichts.
- **Der PR ist ein Draft** — darauf läuft Codex nicht an.
- **Das Kontingent ist weg** — dann schreibt er die Meldung oben.

«Kein Kommentar» heisst also nicht «geprüft und sauber». Unterscheiden lässt es
sich an der Form: Ein echter Review ist ein Review-Objekt («💡 Codex Review»,
mit Commit-Angabe), die Limit-Meldung ein gewöhnlicher Issue-Kommentar. Das
sind zwei verschiedene Abfragen — `get_reviews` gegen `get_comments`; wer nur
eine davon nimmt, übersieht die andere Hälfte. Genau so ist die Limit-Meldung
zuerst durchgerutscht.

Portfolio-weit nachsehen:

```
search_pull_requests: user:malkreide commenter:chatgpt-codex-connector[bot] updated:>=<Datum>
```

Findet nur, wo er *kommentiert* hat. Repos ohne PR-Aktivität tauchen nicht auf
— das ist kein Beleg, dass dort geprüft wurde.

Zweiter Weg, den Prüfer zu verlieren, ganz ohne Kontingentproblem: zu schnell
mergen. Am 21./22.8. lagen zwischen «ready for review» und Merge mehrfach drei
bis fünf Sekunden. Codex wird beim Umschalten von Draft auf ready ausgelöst und
braucht danach Zeit; wer sofort mergt, hat das Häkchen gesetzt und den Review
nicht abgewartet.

Das Kontingent hängt am Konto, nicht am Repo, und Code-Reviews haben einen
eigenen Topf — nur GitHub-getriggerte Reviews zählen hinein. ChatGPT-Pläne
fahren ein rollendes Fünf-Stunden-Fenster plus Wochenlimits; welches greift,
steht im Codex-Dashboard. Zeigt das freies Kontingent, während Reviews weiter
scheitern, ist das ein bekannter Fehler bei mehreren verbundenen Konten — dann
den GitHub-Connector in den Codex-Einstellungen trennen und neu verbinden.

### Wenn zwei Agenten dasselbe tun

Vor dem Anlegen eines Branches mit vorgegebenem Namen prüfen, ob es ihn schon
gibt:

```bash
git ls-remote --heads origin claude/<name> | wc -l
```

Steht dort `1`, arbeitet jemand anderes daran — mit Schreibrecht auf denselben
Ref.

Ein PR mit leerem Diff wird geschlossen, nicht gemergt. Der Test ist
`get_files` auf dem PR: kommt `[]` zurück, ändert er nichts. Ein grüner Check
sagt dazu nichts — die CI prüft den Head, nicht die Differenz zur Basis.

Am 21.8.2026 liefen zwei Sessions dieselbe Aufgabe über 45 Repos, auf den
Branches `claude/codex-review-audit-templates-9sn6mx` und
`claude/codex-review-audit-7ioh56`. Wo die eine zuerst nach `main` kam, wurde
`main` in den Branch der anderen gemergt und der add/add-Konflikt zugunsten
von `main` aufgelöst. Übrig blieben 14 PRs, die durch sämtliche Gates grün
liefen und nichts enthielten; sie wurden gemergt und hinterliessen leere
Merge-Commits. Mit den zwei Folge-PRs, die aus demselben Grund gegenstandslos
waren, waren 16 der 59 PRs jenes Tages reine Reibung.

Dieselbe Klasse wie der handgeschriebene Stub, der denselben Feldnamen annahm
wie der Code: Nichts ist rot, weil nichts geprüft wird, worauf es ankommt.

## Teil 2 — dieses Repo

**ruff: eine Quelle.** Der Pin `0.16.1` steht in `pyproject.toml` und `.pre-
commit-config.yaml` — und **nicht** mehr als eigener Install-Schritt in der
CI.

Im `test`-Job lief der entfernte CI-Schritt nach dem Install der
Abhängigkeiten und überschrieb sie. Eine Abweichung im Pin konnte deshalb in
der CI gar nicht auffallen, sondern nur lokal — wo niemand sie erwartet. Ein
manuelles Nachinstallieren von ruff vor den Gates ist damit nicht mehr nötig
und wäre schädlich: Es würde eine spätere Anhebung hier stillschweigend
überstimmen.

Im `lint`-Job lag der Fall anders: Dort war der ruff-Pin die **einzige**
Installation. An seiner Stelle steht jetzt `pip install -e ".[dev]"`, und
dieser Schritt ist nicht redundant — ohne ihn hat der Job überhaupt kein ruff
(`ruff: command not found`). Er sieht nur so aus wie der Install im `test`-Job.

`scripts/check_ruff_pin.py` erzwingt das — als pre-commit-Hook *und* als
CI-Schritt. Er prüft beide verbleibenden Stellen auf Gleichstand und
zusätzlich, dass `ci.yml` keinen eigenen Pin zurückbekommt.

Vor dem Lauf `ruff --version` prüfen: ein älteres ruff früher im `PATH`
schlägt den Pin, ohne dass der Install etwas meldet.

Auf `python -m ruff` auszuweichen hilft nicht: `check_ruff_pin.py` prüft beide
Aufrufwege (`shutil.which("ruff")` *und* `python -m ruff`). Ist einer veraltet,
sind die ruff-Gates grün und dieses hier rot. Den `PATH` richten, nicht den
Aufruf.

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
`include` unter `[tool.ruff]` setzen — der Umfang sind die drei Pfade im
Gate-Befehl selbst. Wer ihn prüfen will, zählt nach statt hier abzulesen:
`ruff check src/ tests/ scripts/ --show-files | wc -l`. `ruff format` meldet
dabei eine Datei mehr als `ruff check`, weil 0.16 auch Markdown formatiert
und damit `tests/fixtures/PROVENANCE.md` mitnimmt — 13 und 14, kein Fehler.

Die Skript-Liste dieses Schritts ist handgepflegt: in `ci.yml` stehen zwei
Dateinamen, kein Glob. Ein weiteres portfolioweit kopiertes Skript wird dort
nicht von selbst mitgeprüft.

**Die zwei Jobs sind ungleich breit.** `test` fährt die Matrix 3.11/3.12/3.13,
`lint` läuft ohne Matrix auf 3.11. Die vier Gates ab `ruff check` laufen also
einmal, nicht dreimal — ein grünes 3.12/3.13 sagt über sie nichts aus. `test`
setzt kein `fail-fast: false`.

**Live-Tests:** eigener Job in `ci.yml`, nächtlich per Cron (`17 3 * * *`) plus
`workflow_dispatch`; auf PRs übersprungen (`if: github.event_name ==
'schedule' || … 'workflow_dispatch'`). Ein roter Lauf legt ein Issue an oder
schliesst es wieder; dafür braucht er `issues: write`. DRIFT-005 ist erfüllt.

Dieses `issues: write` steht **am `live`-Job**, nicht auf Workflow-Ebene: Dort
hätte es auch der `GITHUB_TOKEN` jedes PR-Laufs bekommen. Auf Workflow-Ebene
steht nur `contents: read`.

Der `live`-Job wiederholt `contents: read` deshalb, weil ein
`permissions`-Block am Job den auf Workflow-Ebene **ersetzt** statt ihn zu
ergänzen. Die Zeile sieht redundant aus; ohne sie fällt `actions/checkout` um.
