"""Die Gate-Skripte laufen auch auf einer Konsole, die kein UTF-8 spricht.

Befund auf `main` (9b88f6f), Windows 11, Ausgabe umgeleitet unter cp1252
(Pipe, pre-commit, Claude Code): `scripts/check_ruff_pin.py` und
`scripts/check_version_sync.py` fanden keine Abweichung und endeten trotzdem
mit Exit 1 -- ein `UnicodeEncodeError` an dem `→` (U+2192) in der
*Erfolgsmeldung*. Beide Gates waren damit dort immer rot.

Nur `→` bricht: `—`, `…` und Umlaute kennt cp1252. `→` in
`scripts/classify_live_scenarios.py` ist Eingabe (Regex gegen CI-Logs), keine
Ausgabe, und gehoert deshalb nicht hierher.

Die CI hat das nie gesehen: Linux-Runner sprechen UTF-8. Deshalb erzwingt
dieser Test die Kodierung per `PYTHONIOENCODING`, statt sich auf die Plattform
zu verlassen -- so faellt der Rueckfall auch auf Linux auf.

Geprueft wird jeder Ausgabeweg, der vorher `→` trug:

  - `check_ruff_pin.py`: nur der gruene Weg (stdout). Die roten Meldungen
    enthielten nie ein Zeichen ausserhalb von cp1252; ein Test dafuer bliebe
    ohne Reparatur gruen.
  - `check_version_sync.py`: der gruene Weg (stdout) und die Drift-Meldung
    (stderr), deren Bezeichnungen `server.json → …` und `README.md → …`
    lauteten.

Die Wege sind nicht gleich kaputt. stdout bricht mit Traceback ab. stderr
schreibt Python mit `errors="backslashreplace"`: Die Drift-Meldung endete
schon vorher ohne Traceback mit Exit 1, trug aber `server.json \\u2192 version`
statt eines lesbaren Pfeils. Deshalb prueft der rote Test den Wortlaut, nicht
nur das Fehlen eines Tracebacks -- sonst waere er auch ohne die Reparatur gruen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
RUFF_GATE = _ROOT / "scripts" / "check_ruff_pin.py"
SYNC_GATE = _ROOT / "scripts" / "check_version_sync.py"


def _env() -> dict[str, str]:
    """cp1252 erzwingen und den PATH auf das Python dieses Laufs beschraenken.

    `check_ruff_pin.py` fragt auch `shutil.which("ruff")` ab. Ein fremdes ruff
    weiter vorn im PATH machte den gruenen Lauf rot, aus einem Grund, der mit
    der Kodierung nichts zu tun hat. Mit nur dem Verzeichnis von
    `sys.executable` findet es dasselbe ruff wie `python -m ruff`.
    """
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env["PATH"] = str(Path(sys.executable).parent)
    return env


def _run(script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        encoding="cp1252",
        env=_env(),
        timeout=120,
    )


def _reachable_ruff() -> str:
    """Version des ruff, das das Gate im Subprozess finden wird."""
    try:
        done = subprocess.run(
            [sys.executable, "-m", "ruff", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("kein ruff im Python dieses Laufs (dev-Extra fehlt)")
    match = re.search(r"\d+\.\d+\.\d+", done.stdout)
    assert match, done.stdout
    return match.group(0)


def _ruff_baum(tmp_path: Path) -> Path:
    """Minimal-Repo, in dem `check_ruff_pin.py` gruen endet.

    Gepinnt wird auf die Version, die tatsaechlich erreichbar ist -- Gegenstand
    ist die Ausgabe, nicht der Pin dieses Repos.
    """
    version = _reachable_ruff()
    (tmp_path / "scripts").mkdir()
    shutil.copy2(RUFF_GATE, tmp_path / "scripts" / RUFF_GATE.name)
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")
    projekt = f'[project.optional-dependencies]\ndev = ["ruff=={version}"]\n'
    (tmp_path / "pyproject.toml").write_text(projekt, encoding="utf-8")
    hook = (
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        f"    rev: v{version}\n"
    )
    (tmp_path / ".pre-commit-config.yaml").write_text(hook, encoding="utf-8")
    return tmp_path / "scripts" / RUFF_GATE.name


def _sync_baum(tmp_path: Path, version: str, deklariert: str) -> Path:
    """Minimal-Repo, in dem jede Bezeichnung vorkommt, die vorher `→` trug.

    `server.json` mit `version` *und* einem Paket, dazu ein README-Badge. Fehlte
    eine davon, bliebe ihr Zeichen ungeprueft.
    """
    (tmp_path / "scripts").mkdir()
    shutil.copy2(SYNC_GATE, tmp_path / "scripts" / SYNC_GATE.name)
    projekt = f'[project]\nname = "wegwerf-paket"\nversion = "{version}"\n'
    (tmp_path / "pyproject.toml").write_text(projekt, encoding="utf-8")
    server = {"version": deklariert, "packages": [{"version": deklariert}]}
    (tmp_path / "server.json").write_text(json.dumps(server), encoding="utf-8")
    zeile = f"![Version](https://img.shields.io/badge/version-{deklariert}-blue)\n"
    (tmp_path / "README.md").write_text(zeile, encoding="utf-8")
    return tmp_path / "scripts" / SYNC_GATE.name


def test_ruff_pin_gruener_lauf_bricht_nicht_an_der_erfolgsmeldung(tmp_path: Path):
    ergebnis = _run(_ruff_baum(tmp_path))

    assert "Traceback" not in ergebnis.stderr, ergebnis.stderr
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "Ruff-Pin OK" in ergebnis.stdout, ergebnis.stdout
    assert ".pre-commit-config.yaml -> rev" in ergebnis.stdout, ergebnis.stdout


def test_version_sync_gruener_lauf_bricht_nicht_an_der_erfolgsmeldung(
    tmp_path: Path,
):
    ergebnis = _run(_sync_baum(tmp_path, "0.7.0", "0.7.0"))

    assert "Traceback" not in ergebnis.stderr, ergebnis.stderr
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "Versions-Sync OK" in ergebnis.stdout, ergebnis.stdout
    assert "README.md -> Versions-Badge" in ergebnis.stdout, ergebnis.stdout


def test_version_sync_drift_meldet_den_befund_statt_eines_tracebacks(
    tmp_path: Path,
):
    """Alle drei Stellen weichen ab; das Gate sammelt sie vor dem Abbruch."""
    ergebnis = _run(_sync_baum(tmp_path, "0.7.0", "0.6.0"))

    assert "Traceback" not in ergebnis.stderr, ergebnis.stderr
    assert ergebnis.returncode == 1
    for zeile in (
        "server.json -> version = '0.6.0'",
        "server.json -> packages[0].version = '0.6.0'",
        "README.md -> Versions-Badge = '0.6.0'",
    ):
        assert zeile in ergebnis.stderr, ergebnis.stderr
