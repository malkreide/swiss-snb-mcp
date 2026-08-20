# SessionStart-Hook: Klon-Aktualität

`session-start.sh` meldet beim Sessionstart, wie viele Commits der
ausgecheckte Stand hinter `origin/<Standard-Branch>` liegt. Bei 0 schweigt er.

## Grund

Ein veralteter Klon hat am 3.8.2026 **zweimal** eine rote CI erzeugt, deren
Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
die das Gate einführten, an dem der Branch scheiterte. Wer den Fehler im
eigenen Diff sucht, sucht in den falschen Dateien. Die Prüfung kostet eine
Sekunde und ersetzt diese Fehlersuche.

`CLAUDE.md` verlangt die Prüfung ohnehin vor jeder Arbeit. Sie stand dort
bisher nur als Bitte an den Leser — der Hook führt sie aus.

## Oberste Regel: blockiert nie

Ein Hook, der bei Netzproblemen die Arbeit anhält, wird nach dem zweiten Mal
abgeschaltet und schützt danach gar nichts. Deshalb geht jeder dieser Fälle
**still** durch und endet mit Status 0:

| Fall | Verhalten |
| --- | --- |
| Kein Netz / flatterndes DNS | Zeitschranke greift, keine Ausgabe |
| Kein Remote `origin` | keine Ausgabe |
| `git` nicht im `PATH` | keine Ausgabe |
| Kein Git-Repo | keine Ausgabe |
| Unbeborener HEAD (frisches `git init`) | keine Ausgabe |
| Standard-Branch nicht ermittelbar | keine Ausgabe |
| Stand ist aktuell (0 Commits zurück) | keine Ausgabe |
| Detached HEAD | wird normal gezählt und gemeldet |

Umgesetzt ist das durch: kein `set -e`, jeden Aufruf einzeln abgesichert, eine
harte Zeitschranke um **jeden** Netzzugriff, und ein unbedingtes `exit 0` am
Ende. `stderr` wird verworfen, damit git-Rauschen nicht als Fehler erscheint
(`CLAUDE_STALE_CHECK_DEBUG=1` hebt das auf).

Detached HEAD ist bewusst kein Ausschlussgrund: `HEAD..<tip>` ist dort genauso
definiert, und die Aufgabe fragt nach dem **ausgecheckten Stand**, nicht nach
einem Branch.

## Zeitschranke

`CLAUDE_STALE_CHECK_TIMEOUT` (Vorgabe **4 s**) gilt pro Netzzugriff. Im
schlechtesten Fall sind das zwei Zugriffe (`ls-remote`, dann `fetch`), also
8 s; die `timeout: 15` in `settings.json` ist die äussere Reissleine darum.

Der häufige Fall braucht nur **einen** Zugriff: `ls-remote` liefert den
Remote-Tip als SHA mit. Liegt der lokal schon vor, wird direkt gezählt und gar
nicht gefetcht.

`timeout` (coreutils) wird benutzt, wenn vorhanden, sonst `gtimeout`, sonst
ein eigener Poll-Loop mit Hintergrundprozess — nicht «ungeschützt laufen
lassen». Abgeräumt wird mit `TERM` vor `KILL`, damit git seine Ref-Locks noch
aufräumt.

## Der Standard-Branch wird ermittelt, nicht angenommen

Drei Repos im Portfolio (`openlex-mcp`, `swiss-courts-mcp`, `swisstopo-mcp`)
heissen ihren Standard-Branch `master`. Ein fest verdrahtetes `main` hat schon
einmal einen Branch 15 Commits alt werden lassen, weil die Prüfung still ins
Leere lief.

Ermittelt wird in dieser Reihenfolge:

1. `git ls-remote --symref origin HEAD` — autoritativ, und in einem **flachen
   Klon die einzige Quelle**: dort ist `refs/remotes/origin/HEAD` gar nicht
   gesetzt. Genau so wird dieses Repo in Claude Code on the web ausgecheckt,
   ein rein lokaler Ansatz wäre dort also wirkungslos.
2. `git symbolic-ref refs/remotes/origin/HEAD` — Fallback ohne Netz.
3. Sonst: keine Ausgabe.

## FETCH_HEAD nur aus diesem Lauf

`FETCH_HEAD` wird ausschliesslich gelesen, wenn der `fetch` in **diesem** Lauf
erfolgreich war. Ohne diese Bedingung würde ein fehlgeschlagener Fetch auf
einen `FETCH_HEAD` von gestern zurückfallen und eine Zahl melden, die niemand
nachvollziehen kann — schlimmer als keine Meldung.

## Flache Klone

In einem flachen Klon (`--depth`) kann die Zählung nach oben abweichen, wenn
die gemeinsame Basis jenseits der Kappungsgrenze liegt. Die Meldung ist dann
eher zu laut als zu leise — für eine Warnung die richtige Richtung.

## Stellschrauben

| Variable | Wirkung |
| --- | --- |
| `CLAUDE_SKIP_STALE_CHECK=1` | Hook komplett überspringen |
| `CLAUDE_STALE_CHECK_TIMEOUT=n` | Sekunden pro Netzzugriff (Vorgabe 4) |
| `CLAUDE_STALE_CHECK_DEBUG=1` | `stderr` sichtbar lassen statt verwerfen |

## Warum der Grund nicht in `settings.json` steht

`settings.json` ist striktes JSON, kein JSONC. Ein Kommentar dort würde die
Datei unparsebar machen — und eine kaputte `settings.json` blockiert genau
die Session, die dieser Hook nie blockieren darf. Der Grund steht deshalb hier
und im Kopf von `session-start.sh`.

## Test

`tests/test_session_start_hook.py` fährt den Hook als Prozess gegen echte
Wegwerf-Repos — aktueller Stand, N Commits zurück, unerreichbarer Remote,
`master` statt `main`, detached HEAD, kein Repo, kein `git` im `PATH` — und
gegen ein absichtlich hängendes `git`, das über die Zeitschranke abgeräumt
werden muss. Eine handgeschriebene Attrappe von `git fetch` könnte die Aussage
«hängt nie» nicht widerlegen; ein echtes, hängendes `git` kann es.

### Gegenprobe

Jede Zusicherung wurde einzeln neutralisiert. Zwei Mutationen überlebten den
ersten Anlauf — die zugehörigen Tests wurden daraufhin nachgeschärft:

| Neutralisiert | Fällt |
| --- | --- |
| Standard-Branch hart auf `main` | `test_master_statt_main` |
| Zeitschranke entfernt | `TestZeitschranke` (hängt bis zum Abbruch) |
| Schweigen bei 0 aufgehoben | `test_schweigt_wenn_aktuell` + 3 weitere |
| `exit 0` → `exit $?` | `test_status_0_auch_wenn_die_ausgabe_selbst_scheitert` |
| `\|\| return 0` am `fetch` entfernt | `test_abgeraeumter_fetch_meldet_nichts_aus_altem_fetch_head` |

Die beiden Überlebenden sind lehrreich:

- **`exit 0`** sah zunächst redundant aus, weil jeder Pfad in `main` ohnehin
  `return 0` macht. Es gibt aber einen echten Fall: Ist stdout geschlossen,
  scheitert das `printf` — und ohne das `exit 0` reicht der Hook ausgerechnet
  im Meldefall einen Fehler an die Session durch. Genau dieser Fall wird jetzt
  geprüft.
- **`|| return 0` am `fetch`** war mit einem *sauber* scheiternden Fetch nicht
  zu widerlegen: git leert `FETCH_HEAD` dabei selbst. Der gefährliche Fall ist
  der *abgeräumte* Fetch — die Zeitschranke schiesst ihn ab, der alte
  `FETCH_HEAD` bleibt unversehrt liegen und würde eine Zahl von gestern
  melden. Der Test simuliert jetzt genau das.
