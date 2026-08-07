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
        import os

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


if __name__ == "__main__":
    unittest.main()
