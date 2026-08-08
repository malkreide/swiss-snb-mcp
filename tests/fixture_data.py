"""Zugriff auf die aufgezeichneten Fixtures unter ``tests/fixtures/``.

Diese Dateien sind **aufgezeichnet, nicht ausgedacht**: Quelle, Datum,
Auswahlregel und SHA-256 je Datei stehen in ``tests/fixtures/PROVENANCE.md``,
geschrieben von ``scripts/record_fixtures.py``.

Davor bestand jede Antwort dieser Suite aus einem Literal im Testmodul. Als
sie zum ersten Mal gegen die Quelle gehalten wurden, stimmte weder das Format
der Schluessel noch die Zahl der Dimensionen noch die Einheit.

Ein fehlender Name ist hier ein Fehler und keine leere Struktur. Ein Loader,
der bei einem Tippfehler ``{}`` zurueckgibt, erzeugt einen Test, der nichts
mehr prueft und trotzdem Erfolg meldet — die teuerste Sorte gruen.
"""

from __future__ import annotations

import copy
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"

_BRACES = re.compile(r"\{([^}]*)\}")


@cache
def _load(name: str) -> Any:
    path = FIXTURES / name
    if not path.is_file():
        available = sorted(p.name for p in FIXTURES.glob("*.json"))
        raise FileNotFoundError(
            f"Keine Fixture {name!r} unter {FIXTURES}. Vorhanden: {available}. "
            "Neu aufzeichnen mit `python scripts/record_fixtures.py`."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def payload(name: str) -> Any:
    """Die aufgezeichnete Antwort für ``name``.

    Es ist bewusst eine Kopie: Der Produktivcode bekommt diese Struktur über
    ``respx`` in die Hand, und ein Test, der sie verändert, würde sonst dem
    nächsten die Fixture unter den Füssen wegziehen.
    """
    return copy.deepcopy(_load(name))


def timeseries(name: str) -> list[dict[str, Any]]:
    """Die Reihen einer aufgezeichneten SNB-Antwort."""
    return payload(name)["timeseries"]


def dim_values(series: dict[str, Any]) -> list[str]:
    """Die Dimensionswerte aus ``metadata.key`` — positionsgleich zum Header.

    Aus der Fixture gelesen statt danebengeschrieben: Genau diese Zerlegung
    nimmt ``_filter_timeseries`` vor, und eine zweite Kopie davon im Testmodul
    wäre eine zweite Stelle, an der sie falsch sein kann.
    """
    m = _BRACES.search((series.get("metadata") or {}).get("key", ""))
    return m.group(1).split(",") if m else []


def currency_ids(name: str = "cube_devkum.json") -> set[str]:
    """Die Währungs-IDs, die der aufgezeichnete Wechselkurs-Cube führt."""
    return {d[1] for s in timeseries(name) if len(d := dim_values(s)) == 2}


def position_ids(name: str = "cube_snbbipo.json") -> set[str]:
    """Die Bilanzpositions-IDs des aufgezeichneten SNB-Bilanz-Cubes."""
    return {d[0] for s in timeseries(name) if len(d := dim_values(s)) == 1}
