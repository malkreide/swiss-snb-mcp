"""
Ruff-Pins auf Gleichlauf prüfen.

Ruff ist an zwei Stellen gepinnt, und beide müssen dieselbe Version nennen:

  - `.github/workflows/ci.yml`: `pip install ruff==X.Y.Z` im lint-Job
  - `.pre-commit-config.yaml`: `rev: vX.Y.Z` beim ruff-pre-commit-Repo

Hintergrund: der Pre-Commit-Hook existiert, um genau die Formatierung lokal zu
erzwingen, die der lint-Job prüft. Läuft der eine Pin dem anderen davon,
formatiert der Hook nach der einen und die CI prüft nach der anderen Version —
und der Hook meldet grün, während die CI rot wird. Das ist derselbe Fehlschlag,
gegen den der Hook eingeführt wurde, nur eine Ebene höher und ohne dass ihn
etwas widerlegt: ein Kommentar in beiden Dateien bittet darum, sie zusammen zu
bumpen, aber bitten ist keine Prüfung.

Das `v`-Präfix der pre-commit-`rev` gehört zum Git-Tag, nicht zur Version, und
wird vor dem Vergleich abgeschnitten.

Fehlt einer der beiden Pins, ist das ebenfalls ein Fehler: dann prüft dieses
Skript stillschweigend nichts mehr, und der Zustand, den es absichern soll,
wäre wieder unbeobachtet.

Verwendung:
    python scripts/check_ruff_pin.py     # exit 1 bei Abweichung

Bewusst nur Standardbibliothek — wie check_version_sync.py läuft der Check
damit ohne Projekt-Installation in schlanken CI-Jobs. Deshalb auch Regex statt
PyYAML: für zwei Felder lohnt keine Abhängigkeit.

Formatierung: dieselben zwei Regeln wie in check_version_sync.py, denn diese
Datei wird genauso zwischen den Repos kopiert, und dort stehen `line-length`
88, 100, 110 und 120 nebeneinander. `ruff format` zieht einen Ausdruck
zusammen, sobald er in die jeweilige Breite passt — eine Zeile zwischen 89 und
120 Zeichen wäre also in der einen Hälfte der Repos formatgerecht und in der
anderen nicht, und `ruff format --check` fiele beim Kopieren um:

  - keine Zeile über 88 Zeichen — lange Ausdrücke bekommen eine lokale
    Variable statt eines Umbruchs
  - keine impliziten String-Verkettungen über mehrere Zeilen, ausser in
    Aufrufen mit Magic Trailing Comma
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
PRECOMMIT = ROOT / ".pre-commit-config.yaml"

# `pip install ruff==0.15.8` — auch mit Leerzeichen um `==` und selbst dann,
# wenn auf derselben Zeile weitere Pakete stehen.
_PIP_PIN = re.compile(r"\bruff\s*==\s*([0-9][^\s'\"]*)")

# Der Eintrag des ruff-pre-commit-Repos, bis zum nächsten `- repo:` oder
# Dateiende. `rev:` wird nur innerhalb dieses Ausschnitts gesucht, damit die
# `rev` eines anderen Repos nicht versehentlich gelesen wird.
_RUFF_REPO_BLOCK = re.compile(
    r"^\s*-\s*repo:\s*\S*ruff-pre-commit\s*$(.*?)(?=^\s*-\s*repo:|\Z)",
    re.MULTILINE | re.DOTALL,
)
_REV = re.compile(r"^\s*rev:\s*['\"]?(\S+?)['\"]?\s*$", re.MULTILINE)


def ci_pins() -> list[str]:
    """Alle in ci.yml gepinnten Ruff-Versionen."""
    return _PIP_PIN.findall(CI.read_text(encoding="utf-8"))


def precommit_pin() -> str | None:
    """Die `rev` des ruff-pre-commit-Repos, ohne `v`-Präfix."""
    block = _RUFF_REPO_BLOCK.search(PRECOMMIT.read_text(encoding="utf-8"))
    if block is None:
        return None
    rev = _REV.search(block.group(1))
    if rev is None:
        return None
    return rev.group(1).removeprefix("v")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    print(
        "\nBeide Stellen im selben Commit bumpen: `rev:` in "
        ".pre-commit-config.yaml und `pip install ruff==…` im lint-Job von "
        ".github/workflows/ci.yml. Sonst formatiert der Hook nach der einen "
        "und die CI prüft nach der anderen Version.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    ci = ci_pins()
    hook = precommit_pin()

    if not ci:
        fail("KEIN PIN: in .github/workflows/ci.yml steht kein `ruff==<version>`.")
    if hook is None:
        missing = "fehlt das ruff-pre-commit-Repo oder dessen `rev:`."
        fail(f"KEIN PIN: in .pre-commit-config.yaml {missing}")

    divergent = sorted({v for v in ci if v != hook})
    if divergent:
        others = ", ".join(repr(v) for v in divergent)
        head = f"DRIFT: .pre-commit-config.yaml pinnt Ruff auf {hook!r},"
        fail(f"{head} .github/workflows/ci.yml auf {others}.")

    checked = ".pre-commit-config.yaml → rev, .github/workflows/ci.yml → ruff=="
    print(f"Ruff-Pin OK ({hook}; geprüft: {checked})")


if __name__ == "__main__":
    main()
