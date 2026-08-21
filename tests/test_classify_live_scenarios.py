#!/usr/bin/env python3
"""Tests fuer scripts/classify_live_scenarios.py — die drei Antworten des Cron.

Der naechtliche `live`-Job faehrt seit jeher gegen `data.snb.ch`. Was fehlte,
war die Einordnung: Ein rotes Ergebnis sah niemand, und ein Exit-Code allein
haette einen leeren Lauf nicht von einem gruenen unterschieden.

`test_null_szenarien_ist_kein_erfolg` ist der Fall, um den es geht. `main()`
gibt `FAILED == 0` zurueck — bei null registrierten Szenarien also `True`.

Nur Standardbibliothek, kein Netz.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import classify_live_scenarios as cls


def log(tmp: Path, name: str, total: int, passed: int, failed: int) -> Path:
    path = tmp / name
    path.write_text(
        "  ✓ 01 – Irgendein Szenario: PASSED ✓\n\n"
        f"  Total: {total} | Bestanden: {passed} | Fehlgeschlagen: {failed}\n"
        "======================================================================\n",
        encoding="utf-8",
    )
    return path


class ClassifyOneTest(unittest.TestCase):
    def test_alles_bestanden_ist_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = log(Path(tmp), "scenarios.log", 20, 20, 0)
            state, reason = cls.classify_one(path, 0)
        self.assertEqual(state, cls.CLEAR)
        self.assertIn("20 von 20", reason)

    def test_ein_gefallenes_szenario_ist_ein_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = log(Path(tmp), "scenarios.log", 20, 19, 1)
            state, reason = cls.classify_one(path, 1)
        self.assertEqual(state, cls.FINDING)
        self.assertIn("1 von 20", reason)

    def test_null_szenarien_ist_kein_erfolg(self):
        """`main()` gibt `FAILED == 0` zurueck — bei null Szenarien also True."""
        with tempfile.TemporaryDirectory() as tmp:
            path = log(Path(tmp), "scenarios.log", 0, 0, 0)
            state, reason = cls.classify_one(path, 0)
        self.assertEqual(state, cls.UNKNOWN)
        self.assertIn("null Szenarien", reason)

    def test_keine_summenzeile_ist_unknown(self):
        """Import-Fehler, Timeout, Abbruch — der Lauf kam nicht bis zum Ende."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenarios.log"
            path.write_text("Traceback (most recent call last):\n", encoding="utf-8")
            state, reason = cls.classify_one(path, 1)
        self.assertEqual(state, cls.UNKNOWN)
        self.assertIn("keine Summenzeile", reason)

    def test_fehlende_datei_ist_unknown(self):
        state, _ = cls.classify_one(Path("/nonexistent/scenarios.log"), 137)
        self.assertEqual(state, cls.UNKNOWN)

    def test_gruene_summe_mit_fremdem_exit_ist_unknown(self):
        """Alles bestanden und trotzdem Exit 137: der Prozess wurde getoetet."""
        with tempfile.TemporaryDirectory() as tmp:
            path = log(Path(tmp), "scenarios.log", 20, 20, 0)
            state, reason = cls.classify_one(path, 137)
        self.assertEqual(state, cls.UNKNOWN)
        self.assertIn("Exit 137", reason)

    def test_die_letzte_summenzeile_zaehlt(self):
        """Die Dateien drucken Zwischenstaende; massgeblich ist die letzte."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenarios.log"
            path.write_text(
                "  Total: 5 | Bestanden: 5 | Fehlgeschlagen: 0\n"
                "  Total: 20 | Bestanden: 19 | Fehlgeschlagen: 1\n",
                encoding="utf-8",
            )
            state, reason = cls.classify_one(path, 1)
        self.assertEqual(state, cls.FINDING)
        self.assertIn("1 von 20", reason)

    def test_die_warehouse_summenzeile_mit_uebersprungen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "warehouse.log"
            path.write_text(
                "  Total: 20 | Bestanden: 20 | Fehlgeschlagen: 0 | Übersprungen: 0\n",
                encoding="utf-8",
            )
            state, _ = cls.classify_one(path, 0)
        self.assertEqual(state, cls.CLEAR)


class ClassifyAllTest(unittest.TestCase):
    """Zwei Dateien, ein Urteil. Die Reihenfolge der Vorrangregel ist die Aussage."""

    def test_beide_gruen_ist_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = log(Path(tmp), "scenarios.log", 20, 20, 0)
            b = log(Path(tmp), "warehouse.log", 20, 20, 0)
            state, _ = cls.classify([(a, 0), (b, 0)])
        self.assertEqual(state, cls.CLEAR)

    def test_ein_finding_schlaegt_alles(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = log(Path(tmp), "scenarios.log", 20, 19, 1)
            b = log(Path(tmp), "warehouse.log", 20, 20, 0)
            state, _ = cls.classify([(a, 1), (b, 0)])
        self.assertEqual(state, cls.FINDING)

    def test_ein_unknown_schlaegt_clear(self):
        """Eine nicht gemessene Haelfte macht die andere nicht zur Gesamtaussage."""
        with tempfile.TemporaryDirectory() as tmp:
            a = log(Path(tmp), "scenarios.log", 20, 20, 0)
            state, _ = cls.classify([(a, 0), (Path(tmp) / "fehlt.log", 1)])
        self.assertEqual(state, cls.UNKNOWN)

    def test_finding_schlaegt_auch_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = log(Path(tmp), "scenarios.log", 20, 19, 1)
            state, _ = cls.classify([(a, 1), (Path(tmp) / "fehlt.log", 1)])
        self.assertEqual(state, cls.FINDING)

    def test_keine_datei_ist_unknown(self):
        state, _ = cls.classify([])
        self.assertEqual(state, cls.UNKNOWN)


class CliTest(unittest.TestCase):
    def test_paare_werden_geparst_und_ausgegeben(self):

        with tempfile.TemporaryDirectory() as tmp:
            a = log(Path(tmp), "scenarios.log", 20, 20, 0)
            out = Path(tmp) / "gh-output"
            out.write_text("", encoding="utf-8")
            os.environ["GITHUB_OUTPUT"] = str(out)
            try:
                rc = cls.main([f"{a}:0"])
            finally:
                del os.environ["GITHUB_OUTPUT"]
            written = out.read_text(encoding="utf-8")
        self.assertEqual(rc, 0)
        self.assertIn("state=clear", written)

    def test_ein_argument_ohne_exit_code_wird_abgelehnt(self):
        with self.assertRaises(SystemExit):
            cls.main(["scenarios.log"])


# --- failure_details -------------------------------------------------------
#
# Ein Issue, das nur «3 von 20 gefallen» sagt, sieht bei einem Timeout genauso
# aus wie bei einem Vertragsbruch der Quelle. Am 19. und 20.8.2026 war es
# beides — an zwei aufeinanderfolgenden Nachten, in verschiedenen Suiten — und
# aus dem Issue ging das nicht hervor.

BLOCK = """\
======================================================================
TEST: {title}
======================================================================
Result ({n} chars):
{result}

Checks:
{checks}

→ {verdict} {mark}
"""


def _block(title, verdict="PASSED", checks=(), result="irgendwas"):
    lines = "\n".join(f"  {c}" for c in checks) or "  OK: alles gut"
    mark = "✓" if verdict == "PASSED" else "✗"
    return BLOCK.format(
        title=title,
        n=len(result),
        result=result,
        checks=lines,
        verdict=verdict,
        mark=mark,
    )


def _summary(total, passed, failed, rows=()):
    body = "\n".join(rows)
    return (
        "  ZUSAMMENFASSUNG\n"
        "======================================================================\n"
        f"{body}\n\n"
        f"  Total: {total} | Bestanden: {passed} | Fehlgeschlagen: {failed}\n"
        "======================================================================\n"
    )


class FailureDetailsTest(unittest.TestCase):
    def _write(self, tmp, text):
        path = Path(tmp) / "warehouse.log"
        path.write_text(text, encoding="utf-8")
        return path

    def test_fehlende_datei_ergibt_leer(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = cls.failure_details(Path(tmp) / "gibtsnicht.log")
        self.assertEqual(got, "")

    def test_alles_gruen_ergibt_leer(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._write(tmp, _block("01 – gut") + _summary(1, 1, 0))
            got = cls.failure_details(log)
        self.assertEqual(got, "")

    def test_gefallenes_szenario_bringt_titel_und_gruende(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._write(
                tmp,
                _block("01 – gut")
                + _block(
                    "07 – Bankenbilanz: monatlich",
                    verdict="FAILED",
                    checks=[
                        "FAIL: Expected success but got error: Error: timed out.",
                        "FAIL: 'Millionen CHF' not found in result",
                    ],
                )
                + _summary(2, 1, 1),
            )
            got = cls.failure_details(log)
        self.assertIn("07 – Bankenbilanz: monatlich", got)
        self.assertIn("timed out", got)
        self.assertIn("'Millionen CHF' not found in result", got)
        # Das gruene Szenario hat hier nichts verloren.
        self.assertNotIn("01 – gut", got)

    def test_zusammenfassung_macht_das_letzte_szenario_nicht_rot(self):
        """Regression: gegen die echten CI-Logs vom 20.8.2026 gefunden.

        Die Zusammenfassung listet jedes Szenario noch einmal mit «FAILED ✗»
        und faellt in den letzten TEST-Block. Wer auf das blosse Wort prueft
        statt auf die Verdikt-Zeile, meldet das letzte Szenario immer als
        gefallen — hier also ein gruenes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            log = self._write(
                tmp,
                _block(
                    "07 – kaputt",
                    verdict="FAILED",
                    checks=["FAIL: echt kaputt"],
                )
                + _block("20 – heil")
                + _summary(
                    2,
                    1,
                    1,
                    rows=[
                        "  ✗ 07 – kaputt: FAILED ✗",
                        "  ✓ 20 – heil: PASSED ✓",
                    ],
                ),
            )
            got = cls.failure_details(log)
        self.assertIn("07 – kaputt", got)
        self.assertNotIn("20 – heil", got)

    def test_kappung_wird_gemeldet_nicht_verschwiegen(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self._write(
                tmp,
                "".join(
                    _block(
                        f"{i:02d} – kaputt",
                        verdict="FAILED",
                        checks=["FAIL: " + "x" * 80],
                    )
                    for i in range(1, 40)
                )
                + _summary(39, 0, 39),
            )
            got = cls.failure_details(log, max_chars=300)
        self.assertLessEqual(len(got), 400)
        self.assertIn("gekappt", got)
        self.assertIn("Limit 300", got)


class FencedOutputTest(unittest.TestCase):
    """Der Inhalt stammt aus einem Log, in dem Antworten der Quelle stehen."""

    def test_mehrzeiliges_landet_in_der_heredoc_form(self):
        got = cls._fenced("details", "a\nb")
        self.assertEqual(got, f"details<<{cls.DELIM}\na\nb\n{cls.DELIM}\n")

    def test_delimiter_zeile_im_inhalt_wird_entfernt(self):
        """Sonst schliesst der Inhalt den Block und schleust eigene Outputs ein.

        Geprueft wird genau das: dass im Inhalt keine Zeile mehr steht, die den
        Block schliessen koennte. NICHT, dass `state=clear` verschwindet — das
        darf drinbleiben, die Heredoc-Form macht es inert (siehe Test unten).
        """
        got = cls._fenced("details", f"harmlos\n{cls.DELIM}\nstate=clear")
        kopf, _, rest = got.partition(f"details<<{cls.DELIM}\n")
        self.assertEqual(kopf, "")
        inhalt, _, schwanz = rest.rpartition(f"{cls.DELIM}\n")
        self.assertEqual(schwanz, "")
        self.assertNotIn(cls.DELIM, inhalt.splitlines())
        self.assertIn("harmlos", inhalt)

    def test_eingerueckter_delimiter_zaehlt_auch(self):
        got = cls._fenced("details", f"    {cls.DELIM}")
        self.assertEqual(got, f"details<<{cls.DELIM}\n\n{cls.DELIM}\n")

    def test_key_wert_zeilen_im_inhalt_sind_harmlos(self):
        """Die Heredoc-Form selbst entschaerft sie — nur der Delimiter zaehlt."""
        got = cls._fenced("details", "state=clear")
        self.assertIn("state=clear", got)


class MainDetailsTest(unittest.TestCase):
    def test_main_schreibt_details_als_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "warehouse.log"
            log.write_text(
                _block("07 – kaputt", verdict="FAILED", checks=["FAIL: weil"])
                + _summary(1, 0, 1),
                encoding="utf-8",
            )
            out = Path(tmp) / "gh-output"
            out.write_text("", encoding="utf-8")
            os.environ["GITHUB_OUTPUT"] = str(out)
            try:
                cls.main([f"{log}:1"])
            finally:
                del os.environ["GITHUB_OUTPUT"]
            written = out.read_text(encoding="utf-8")
        self.assertIn(f"details<<{cls.DELIM}", written)
        self.assertIn("07 – kaputt", written)
        self.assertIn("weil", written)

    def test_gruener_lauf_schreibt_leeren_details_block(self):
        """Der Block muss auch dann wohlgeformt sein, sonst bricht das YAML."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "scenarios.log"
            log.write_text(_block("01 – gut") + _summary(1, 1, 0), encoding="utf-8")
            out = Path(tmp) / "gh-output"
            out.write_text("", encoding="utf-8")
            os.environ["GITHUB_OUTPUT"] = str(out)
            try:
                cls.main([f"{log}:0"])
            finally:
                del os.environ["GITHUB_OUTPUT"]
            written = out.read_text(encoding="utf-8")
        self.assertIn(f"details<<{cls.DELIM}\n\n{cls.DELIM}", written)


if __name__ == "__main__":
    unittest.main()
