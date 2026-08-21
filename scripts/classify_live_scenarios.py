#!/usr/bin/env python3
"""Was hat der naechtliche Live-Lauf festgestellt — clear, finding oder unknown?

WARUM ES DIESE DATEI GIBT
-------------------------
Der `live`-Job in `ci.yml` faehrt seit jeher jede Nacht `python
tests/test_live_scenarios.py` und `python tests/test_live_warehouse.py` gegen
`data.snb.ch`. Das ist mehr, als die meisten Server im Portfolio haben — und es
fehlte trotzdem das Entscheidende: **Ein rotes Ergebnis sah niemand.**

Ein geplanter Lauf, dessen Ausgang nur als roter Eintrag im Actions-Tab landet,
ist eine teurere Variante von «laeuft nicht». Rote Cron-Jobs werden nach der
zweiten Woche nicht mehr angeschaut, und dann faellt der Ausfall wieder erst
einem Nutzer auf.

DREI ANTWORTEN, NICHT ZWEI
--------------------------
`if: failure()` kennt rot und nicht rot. Ein Live-Lauf hat drei Antworten:

  clear    Die Szenarien sind gelaufen und alle bestanden.
  finding  Die Szenarien sind gelaufen und mindestens eines ist gefallen.
  unknown  Sie sind NICHT gelaufen — Installation gescheitert, Timeout,
           Import-Fehler, oder null Szenarien eingesammelt.

Nur `finding` gehoert gefixt. `unknown` gehoert gesehen und darf **kein Issue
schliessen**: Zuzumachen hiesse zu behaupten, der Vergleich sei gelaufen.

DER LEERE LAUF
--------------
`main()` in beiden Szenariendateien gibt `FAILED == 0` zurueck. Waeren null
Szenarien registriert, waere das `True` — ein gruener Lauf, der nichts geprueft
hat. Deshalb wird die Summenzeile gelesen und nicht nur der Exit-Code:

    Total: 20 | Bestanden: 20 | Fehlgeschlagen: 0

`Total: 0` ist `unknown`, und eine fehlende Summenzeile ebenfalls. Ein Erfolg
ohne Szenario ist kein Erfolg — dieselbe Klasse Ausfall wie eine leere
Trefferliste, die wie eine Antwort aussieht.

WARUM ALS SKRIPT UND NICHT ALS `run:`-BLOCK
-------------------------------------------
Diese Einordnung entscheidet, ob ein Issue auf- oder zugeht. Sie ist der
einzige Teil des Workflows, der etwas behauptet — und in YAML kann sie niemand
testen. Der Test steht in `tests/test_classify_live_scenarios.py`.

Nicht zu verwechseln mit `classify_live_run.py` in den Schwester-Repos: Die
lesen ein JUnit-XML von pytest. Dieses Repo faehrt seine Szenarien als Skripte
mit eigener Summenzeile, also ist es eine andere Frage an eine andere Ausgabe —
und bekommt darum einen eigenen Namen statt derselben Datei mit anderem Inhalt.

Aufruf:
    python scripts/classify_live_scenarios.py scenarios.log:0 warehouse.log:1

Jedes Argument ist `<logdatei>:<exit-code>`. Gibt `state=` und `reason=` auf
stdout aus und haengt beides an `$GITHUB_OUTPUT` an, wenn gesetzt. Der
Exit-Code ist immer 0: Ueber rot oder gruen entscheidet der Workflow.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

CLEAR = "clear"
FINDING = "finding"
UNKNOWN = "unknown"

# Die Summenzeile, die beide Szenariendateien am Ende drucken. `Uebersprungen`
# steht nur in einer von beiden, deshalb optional.
SUMMARY = re.compile(
    r"Total:\s*(\d+)\s*\|\s*Bestanden:\s*(\d+)\s*\|\s*Fehlgeschlagen:\s*(\d+)"
)


def classify_one(log: Path, exit_code: int) -> tuple[str, str]:
    """(state, reason) fuer EINE Szenariendatei."""
    label = log.name
    if not log.is_file():
        return UNKNOWN, f"{label}: keine Ausgabe aufgezeichnet (Exit {exit_code})"
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return UNKNOWN, f"{label}: Ausgabe nicht lesbar ({exc})"

    matches = SUMMARY.findall(text)
    if not matches:
        return (
            UNKNOWN,
            f"{label}: keine Summenzeile in der Ausgabe (Exit {exit_code}) — der Lauf "
            "ist nicht bis zum Ende gekommen",
        )
    total, passed, failed = (int(v) for v in matches[-1])

    if total == 0:
        return (
            UNKNOWN,
            f"{label}: null Szenarien registriert — ein Erfolg ohne Szenario ist kein "
            "Erfolg",
        )
    if failed or exit_code == 1:
        return FINDING, f"{label}: {failed} von {total} Szenarien gefallen"
    if exit_code != 0:
        return (
            UNKNOWN,
            f"{label}: {passed} von {total} bestanden, aber Exit {exit_code} — der "
            "Prozess ist nicht sauber beendet worden",
        )
    return CLEAR, f"{label}: {passed} von {total} Szenarien bestanden"


# Ein Issue, das nur «3 von 20 gefallen» sagt, sieht bei einem Timeout genauso
# aus wie bei einem Vertragsbruch der Quelle. Genau diese Unterscheidung
# verlangt CLAUDE.md aber, bevor jemand anfaengt zu suchen — und sie stand
# bisher nur im Roh-Log des Laufs, das nach 90 Tagen weg ist.
TEST_HEADER = re.compile(r"^TEST:\s*(\S.*?)\s*$")
FAIL_LINE = re.compile(r"^\s*FAIL:\s*(\S.*?)\s*$")

# Nur die Verdikt-Zeile eines Blocks zaehlt («→ FAILED ✗»), nicht jedes
# Vorkommen des Wortes. Die Zusammenfassung am Dateiende listet jedes Szenario
# noch einmal mit «: FAILED ✗» — und sie faellt in den letzten TEST-Block.
# Gegen echte CI-Logs geprueft: mit blossem `"FAILED" in zeile` meldete der
# Extraktor das jeweils letzte Szenario faelschlich als gefallen.
VERDICT = re.compile(r"^\s*→\s*(PASSED|FAILED)\b")

# Issue-Koerper sind begrenzt, und ein Log kann beliebig lang werden. Gekappt
# wird sichtbar, nie still.
MAX_DETAIL_CHARS = 4000


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    """(Titel, Zeilen) je Szenario, in Reihenfolge des Logs."""
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        header = TEST_HEADER.match(line)
        if header:
            out.append((header.group(1), []))
        elif out:
            out[-1][1].append(line)
    return out


def failure_details(log: Path, max_chars: int = MAX_DETAIL_CHARS) -> str:
    """Die FAIL-Gruende der gefallenen Szenarien, als Klartext.

    Leer, wenn die Datei fehlt, unlesbar ist oder nichts gefallen ist — der
    Aufrufer haengt dann schlicht nichts an.
    """
    if not log.is_file():
        return ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    lines: list[str] = []
    for title, body in _blocks(text):
        verdicts = [m.group(1) for ln in body if (m := VERDICT.match(ln))]
        if not verdicts or verdicts[0] != "FAILED":
            continue
        reasons = [m.group(1) for ln in body if (m := FAIL_LINE.match(ln))]
        lines.append(f"- {title}")
        lines.extend(f"    {r}" for r in reasons)
    if not lines:
        return ""

    rendered = "\n".join(lines)
    if len(rendered) > max_chars:
        kept = rendered[:max_chars].rsplit("\n", 1)[0]
        dropped = rendered.count("\n") - kept.count("\n")
        rendered = f"{kept}\n… {dropped} weitere Zeile(n) gekappt (Limit {max_chars})"
    return rendered


def classify(pairs: list[tuple[Path, int]]) -> tuple[str, str]:
    """Ueber alle Szenariendateien zusammengefasst.

    Ein `finding` schlaegt alles: Ein gefallenes Szenario ist ein Befund, auch
    wenn die zweite Datei gar nicht erst lief. Ein `unknown` schlaegt `clear`,
    denn eine Haelfte, die nicht gemessen wurde, macht die andere nicht zur
    Gesamtaussage.
    """
    if not pairs:
        return UNKNOWN, "keine Szenariendatei angegeben"
    results = [classify_one(log, code) for log, code in pairs]
    reasons = "; ".join(reason for _, reason in results)
    states = {state for state, _ in results}
    if FINDING in states:
        return FINDING, reasons
    if UNKNOWN in states:
        return UNKNOWN, reasons
    return CLEAR, reasons


def _pair(raw: str) -> tuple[Path, int]:
    log, _, code = raw.rpartition(":")
    if not log or not code.lstrip("-").isdigit():
        raise argparse.ArgumentTypeError(
            f"erwartet <logdatei>:<exit-code>, nicht {raw!r}"
        )
    return Path(log), int(code)


# `key=wert` traegt nur eine Zeile. Mehrzeiliges muss in die Heredoc-Form,
# sonst endet der Wert an der ersten Zeilenschaltung.
DELIM = "LIVE_DETAILS_EOF"


def _fenced(name: str, value: str) -> str:
    """Mehrzeiliger GITHUB_OUTPUT-Eintrag, gegen Ausbruch gesichert.

    Der Inhalt stammt aus einem Log, in dem auch Antworten der Quelle stehen.
    Eine Zeile, die genau dem Delimiter entspricht, wuerde den Block vorzeitig
    schliessen und alles Weitere als eigene Outputs einschleusen — also fliegt
    so eine Zeile raus. Die Heredoc-Form selbst macht `key=wert`-Zeilen im
    Inhalt harmlos; nur der Delimiter ist gefaehrlich.
    """
    safe = "\n".join(ln for ln in value.splitlines() if ln.strip() != DELIM)
    return f"{name}<<{DELIM}\n{safe}\n{DELIM}\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="classify_live_scenarios")
    ap.add_argument("pairs", nargs="+", type=_pair, metavar="LOG:EXIT")
    args = ap.parse_args(argv)

    state, reason = classify(args.pairs)
    print(f"state={state}")
    print(f"reason={reason}")

    chunks = [
        f"{log.name}:\n{detail}"
        for log, _ in args.pairs
        if (detail := failure_details(log))
    ]
    details = "\n\n".join(chunks)
    if details:
        print(details)

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"state={state}\n")
            fh.write(f"reason={reason}\n")
            fh.write(_fenced("details", details))
    # Immer 0: Ueber rot oder gruen entscheidet der Workflow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
