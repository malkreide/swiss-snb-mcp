#!/usr/bin/env python3
"""Zeichnet die Unit-Test-Fixtures von den echten SNB-Endpunkten auf.

    python scripts/record_fixtures.py

WARUM ES DAS GIBT. Ein handgeschriebener Mock kodiert die Annahme seines
Autors und kann sie deshalb prinzipiell nicht widerlegen: Produktivcode und
Fixture stammen aus demselben Kopf, derselben Stunde, derselben Lektuere der
Doku. Wo beide irren, irren beide gleich, und die Suite bleibt dauerhaft
gruen.

Dieses Repo hatte davor drei Antwort-Bauer im Testmodul --
`_devkum_response`, `_snbbipo_response`, `_warehouse_response` --, jeder mit
einer einzigen Reihe und dem Kommentar "minimal but structurally faithful".
Sie waren es nicht:

  * `metadata.key` lautete `M.devkum.EUR1.M`; die Quelle schreibt
    `EPB@SNB.devkum{M0,EUR1}`.
  * Der Warehouse-Header trug **eine** Dimension; die Quelle liefert **vier**
    (Jahresreihe) beziehungsweise **fuenf** (Monatsreihe). Genau daran haengt
    `_filter_timeseries`, und genau das hat kein Test je gesehen.
  * `unit` war `Mio. CHF` und `1000 CHF`; die Quelle schreibt
    `In Millionen Franken` und `CHF` mit `scale: "3"`.

DIE AUSSCHNITTE. devkum ist 889 KB, snbbipo 347 KB -- Vollabzuege waeren
unlesbar. Die Auswahlregel ist trotzdem nicht "die ersten N Reihen", denn die
haette hier ausgerechnet das weggeschnitten, worum es geht. Stattdessen:
**alle Reihen bleiben, die Wertelisten werden gekuerzt.** Ueber die
Dimensionen argumentiert der Code, die Werte zeigt er nur an. Der Zuschnitt
laesst damit die Frage "welche Waehrungen/Positionen/Bankengruppen gibt es
ueberhaupt" beantwortbar -- und genau die hat drei Befunde ergeben.

Jede Regel steht mit Datum und SHA-256 in `tests/fixtures/PROVENANCE.md`.
Ohne Datum ist "aufgezeichnet" nach zwei Jahren von "ausgedacht" nicht mehr
zu unterscheiden, weil die Datei gleich aussieht.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "src"))

CUBE_BASE = "https://data.snb.ch/api/cube"
WAREHOUSE_BASE = "https://data.snb.ch/api/warehouse/cube"

# Wie viele Werte je Reihe erhalten bleiben. Genug fuer einen Zeitraumfilter
# und eine Tabelle, wenig genug fuer eine lesbare Datei.
KEEP_VALUES = 24
KEEP_VALUES_ANNUAL = 6

# Der Schluessel traegt die Dimensionswerte in geschweiften Klammern:
# `EPB@SNB.devkum{M0,EUR1}` bzw. `BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}`.
_BRACES = re.compile(r"\{([^}]*)\}")


def dims(series: dict) -> list[str]:
    """Die Dimensionswerte aus `metadata.key`, positionsgleich zum Header."""
    m = _BRACES.search((series.get("metadata") or {}).get("key", ""))
    return m.group(1).split(",") if m else []


def _trim(payload: dict, keep: int) -> dict:
    """Alle Reihen behalten, je Reihe nur die letzten `keep` Werte."""
    for ts in payload.get("timeseries", []):
        ts["values"] = ts.get("values", [])[-keep:]
    return payload


def record() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d")
    entries: list[dict] = []

    def write(name: str, payload: object, url: str, rule: str) -> None:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        (FIXTURES / name).write_text(text, encoding="utf-8")
        entries.append(
            {
                "name": name,
                "url": url,
                "rule": rule,
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        print(f"ok  {name:<34} {len(text.encode('utf-8')):>8} B")

    with httpx.Client(timeout=120.0, follow_redirects=True) as c:

        def get(url: str) -> dict:
            r = c.get(url)
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", "").lower():
                # data.snb.ch ist eine Angular-App vor einer API: Ein Pfad, den
                # es nicht gibt, faellt auf das App-Geruest durch und antwortet
                # mit HTTP 200 und text/html. Wer nur den Status prueft, zeichnet
                # eine Fixture aus einer Fehlerseite auf.
                raise SystemExit(
                    f"{url} antwortete mit Content-Type "
                    f"'{r.headers.get('content-type')}' statt JSON — diesen "
                    "Pfad gibt es vermutlich nicht."
                )
            return r.json()

        def record_dimensions(cube_id: str) -> dict:
            """Die Dimensionsdeklaration eines Warehouse-Cubes.

            Sie ist seit diesem Durchgang Teil des Vertrags: Der Server liest
            die Reihenfolge der Dimensionen daraus, statt sie als Konstante zu
            fuehren. Und der Pfad ist die halbe Geschichte — `dimensions/<lang>`
            ohne `json`-Segment. Mit `json` antwortet die Web-App, HTTP 200.
            """
            url = f"{WAREHOUSE_BASE}/{cube_id}/dimensions/de"
            payload = get(url)
            write(
                f"dimensions_{cube_id.replace('.', '_').lower()}.json",
                payload,
                url,
                "vollstaendig — die Datei ist klein und jede Dimension zaehlt: "
                "aus ihrer Reihenfolge liest der Server, welche Position im "
                "Schluessel welche Dimension ist",
            )
            return payload

        # -- 1) Wechselkurse, Monatsdaten -------------------------------------
        url = f"{CUBE_BASE}/devkum/data/json/de"
        devkum = get(url)
        series = devkum["timeseries"]
        periods = {d[0] for s in series if (d := dims(s))}
        if not {"M0", "M1"} <= periods:
            raise SystemExit(
                f"devkum fuehrt die Periodizitaeten {sorted(periods)} -- ohne "
                "M0 (Monatsmittel) UND M1 (Monatsende) prueft der Filter "
                "`include_month_end` nichts mehr."
            )
        write(
            "cube_devkum.json",
            _trim(devkum, KEEP_VALUES),
            url,
            f"alle {len(series)} Reihen, je die letzten {KEEP_VALUES} Werte. "
            "Alle Reihen bleiben, weil die Fixture damit auch belegt, WELCHE "
            "Waehrungen der Cube fuehrt -- ein Zuschnitt nach Position haette "
            "genau das verdeckt",
        )

        # -- 2) Wechselkurse, Jahresdaten -------------------------------------
        url = f"{CUBE_BASE}/devkua/data/json/en"
        devkua = get(url)
        write(
            "cube_devkua_en.json",
            _trim(devkua, KEEP_VALUES_ANNUAL),
            url,
            f"alle {len(devkua['timeseries'])} Reihen, je die letzten "
            f"{KEEP_VALUES_ANNUAL} Werte; auf Englisch, weil der generische "
            "Cube-Zugriff die Sprache durchreicht und das sonst ungeprueft bleibt",
        )

        # -- 3) SNB-Bilanzpositionen -------------------------------------------
        url = f"{CUBE_BASE}/snbbipo/data/json/de"
        snbbipo = get(url)
        write(
            "cube_snbbipo.json",
            _trim(snbbipo, KEEP_VALUES),
            url,
            f"alle {len(snbbipo['timeseries'])} Positionen, je die letzten "
            f"{KEEP_VALUES} Werte",
        )

        # -- 4) Bankenstatistik, Bilanz, Jahresreihe --------------------------
        #
        # Diese Fixture muss mehr als einen INLANDAUSLAND-Wert je Bankengruppe
        # behalten: Der Server filtert diese Dimension nicht und beschriftet
        # sie nicht, also kommen Total, Inland und Ausland als drei Zeilen
        # unter demselben Etikett heraus. Mit nur einer Auspraegung waere das
        # aus der Fixture nicht zu sehen -- so wie bisher.
        for cube, label in (
            ("BSTA.SNB.JAHR_K.BIL.AKT.TOT", "Aktiven"),
            ("BSTA.SNB.JAHR_K.BIL.PAS.TOT", "Passiven"),
        ):
            declared = record_dimensions(cube)
            url = f"{WAREHOUSE_BASE}/{cube}/data/json/de"
            payload = get(url)
            rows = payload["timeseries"]
            widths = {len(dims(s)) for s in rows}
            if widths != {len(declared["dimensions"])}:
                raise SystemExit(
                    f"{cube}: Schluessel mit {sorted(widths)} Werten, aber "
                    f"{len(declared['dimensions'])} deklarierte Dimensionen — "
                    "die Quelle widerspricht sich innerhalb einer Antwort."
                )
            if widths != {4}:
                raise SystemExit(
                    f"{cube}: Schluessel mit {sorted(widths)} Dimensionen, "
                    "erwartet genau 4 (BIL_DIM_ORDER). Die Dimensionsordnung "
                    "des Servers gehoert geprueft."
                )
            a30 = {d[1] for s in rows if (d := dims(s))[3] == "A30" and d[2] == "T"}
            if len(a30) < 2:
                raise SystemExit(
                    f"{cube}: nur {a30} in INLANDAUSLAND fuer A30/Total -- dann "
                    "belegt die Fixture die Mehrfachzeilen nicht mehr."
                )
            write(
                f"warehouse_bil_{label.lower()}_jahr.json",
                _trim(payload, KEEP_VALUES_ANNUAL),
                url,
                f"alle {len(rows)} Reihen ({label}, Jahresdaten), je die letzten "
                f"{KEEP_VALUES_ANNUAL} Werte. Alle Reihen bleiben, weil erst "
                f"die vollstaendige Besetzung der Dimension INLANDAUSLAND "
                f"({sorted(a30)} bei Bankengruppe A30) sichtbar macht, dass "
                "der Server drei Aggregate unter einer Beschriftung fuehrt",
            )

        # -- 5) Bankenstatistik, Bilanz, MONATSreihe --------------------------
        #
        # Der eigentliche Fund. `snb_get_banking_balance_sheet(frequency=
        # "monthly")` filtert mit BIL_DIM_ORDER (vier Dimensionen) gegen einen
        # Cube mit fuenf -- `_filter_timeseries` verwirft jede Reihe, deren
        # Laenge nicht passt, und zwar stumm. Ergebnis: eine leere Tabelle mit
        # HTTP 200. Die Fixture haelt die fuenfte Dimension fest.
        declared = record_dimensions("BSTA.SNB.MONA_US.BIL.AKT.TOT")
        url = f"{WAREHOUSE_BASE}/BSTA.SNB.MONA_US.BIL.AKT.TOT/data/json/de"
        monthly = get(url)
        widths = {len(dims(s)) for s in monthly["timeseries"]}
        if widths != {len(declared["dimensions"])}:
            raise SystemExit(
                "Monatsreihe: Schluesselbreite und Dimensionsdeklaration "
                "stimmen nicht ueberein."
            )
        if widths == {4}:
            raise SystemExit(
                "Die Monatsreihe hat jetzt ebenfalls vier Dimensionen -- dann "
                "ist der Fund geheilt und die Fixture belegt ihn nicht mehr. "
                "Test und PROVENANCE anpassen."
            )
        header_dims = [h["dim"] for h in monthly["timeseries"][0]["header"]]
        write(
            "warehouse_bil_aktiven_monat.json",
            _trim(monthly, KEEP_VALUES),
            url,
            f"alle {len(monthly['timeseries'])} Reihen, je die letzten "
            f"{KEEP_VALUES} Werte. Der Schluessel traegt hier "
            f"{sorted(widths)[0]} Dimensionen statt vier "
            f"({', '.join(header_dims)})",
        )

        # -- 6) Bankenstatistik, Erfolgsrechnung ------------------------------
        record_dimensions("BSTA.SNB.JAHR_K.EFR.GER")
        url = f"{WAREHOUSE_BASE}/BSTA.SNB.JAHR_K.EFR.GER/data/json/de"
        efr = get(url)
        widths = {len(dims(s)) for s in efr["timeseries"]}
        if widths != {2}:
            raise SystemExit(
                f"EFR.GER: Schluessel mit {sorted(widths)} Dimensionen, "
                "erwartet genau 2 (EFR_DIM_ORDER)."
            )
        write(
            "warehouse_efr_ger.json",
            _trim(efr, KEEP_VALUES_ANNUAL),
            url,
            f"alle {len(efr['timeseries'])} Reihen (Geschaeftsertrag), je die "
            f"letzten {KEEP_VALUES_ANNUAL} Werte",
        )

    _write_provenance(recorded_at, entries)
    print(f"\nPROVENANCE.md geschrieben, Aufzeichnungsdatum {recorded_at}")
    return 0


def _write_provenance(recorded_at: str, entries: list[dict]) -> None:
    lines = [
        "# Herkunft der Fixtures",
        "",
        "**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**",
        "",
        f"Aufgezeichnet am **{recorded_at}** von `data.snb.ch`, unveraendert bis",
        "auf die je Datei dokumentierte Auswahl.",
        "",
        "Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht",
        "mehr zu unterscheiden — die Datei sieht gleich aus, und niemand weiss,",
        "ob sie den Stand von gestern zeigt oder den von vor drei",
        "Schema-Wechseln. Das Datum macht diesen Abstand zu einer lesbaren Zahl.",
        "",
        "**Es sind Ausschnitte, keine Vollabzuege** — aber nicht nach Position",
        "zugeschnitten. In jeder Datei bleiben **alle Reihen** erhalten und nur",
        "die Wertelisten sind gekuerzt: Ueber die Dimensionen argumentiert der",
        "Code, die Werte zeigt er an. Waeren stattdessen «die ersten N Reihen»",
        "aufgezeichnet worden, liesse sich nicht mehr sehen, welche Waehrungen,",
        "Positionen und Bankengruppen die Quelle ueberhaupt fuehrt — und genau",
        "daran haengen drei der Befunde.",
        "",
        "Eine Fixture belegt damit die *Form* der Antwort und einen datierten",
        "Ausschnitt ihres Inhalts — nicht den Bestand. Aussagen ueber",
        "Vollstaendigkeit gehoeren in Live-Tests (`pytest -m live`).",
        "",
    ]
    for e in entries:
        lines += [
            f"## `{e['name']}`",
            "",
            f"- **Quelle:** `{e['url']}`",
            f"- **Aufgezeichnet:** {recorded_at}",
            f"- **Auswahl:** {e['rule']}",
            f"- **Groesse:** {e['bytes']} B",
            f"- **SHA-256:** `{e['sha256']}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(record())
    except httpx.HTTPError as exc:  # ein halber Satz ist schlimmer als keiner
        print(f"FEHLER: Quelle nicht erreichbar: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
