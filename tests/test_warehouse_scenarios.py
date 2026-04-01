"""
Test scenarios for swiss-snb-mcp Warehouse API tools.
Tests run against the LIVE SNB Warehouse API at data.snb.ch (no mocks).
"""

import asyncio
import io
import json
import sys
import traceback
from datetime import datetime, timedelta

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add source to path
sys.path.insert(0, "src")

from swiss_snb_mcp.server import Language, _handle_http_error
from swiss_snb_mcp.warehouse import (
    snb_list_warehouse_cubes,
    snb_list_bank_groups,
    snb_get_warehouse_data,
    snb_get_warehouse_metadata,
    snb_get_banking_balance_sheet,
    snb_get_banking_income,
    WarehouseDataInput,
    WarehouseMetadataInput,
    BankingBalanceSheetInput,
    BankingIncomeInput,
    _fetch_warehouse,
)

# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

PASSED = 0
FAILED = 0
RESULTS = []


async def run_test(name: str, coro, checks: list[str] | None = None):
    """Run a single test scenario and report results."""
    global PASSED, FAILED
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    try:
        result = await coro
        # Basic check: result should be a non-empty string
        assert isinstance(result, str), f"Expected str, got {type(result)}"
        assert len(result) > 0, "Result is empty"

        # Check for error indicators
        is_error = result.startswith("Error:") or result.startswith("Keine Daten")

        # Run custom checks
        check_results = []
        if checks:
            for check in checks:
                if check.startswith("!"):
                    # Negative check: string should NOT be present
                    target = check[1:]
                    if target in result:
                        check_results.append(f"  FAIL: '{target}' should NOT be in result")
                    else:
                        check_results.append(f"  OK: '{target}' correctly absent")
                elif check == "__ERROR__":
                    # Expect an error response
                    if is_error:
                        check_results.append(f"  OK: Got expected error response")
                    else:
                        check_results.append(f"  FAIL: Expected error but got success")
                elif check == "__SUCCESS__":
                    if not is_error:
                        check_results.append(f"  OK: Got successful response")
                    else:
                        check_results.append(f"  FAIL: Expected success but got error: {result[:100]}")
                else:
                    if check in result:
                        check_results.append(f"  OK: Found '{check}'")
                    else:
                        check_results.append(f"  FAIL: '{check}' not found in result")

        all_checks_pass = all("FAIL" not in cr for cr in check_results)

        # Print result preview (truncated)
        preview = result[:500] + ("..." if len(result) > 500 else "")
        print(f"Result ({len(result)} chars):\n{preview}")
        if check_results:
            print("\nChecks:")
            for cr in check_results:
                print(cr)

        if all_checks_pass:
            PASSED += 1
            status = "PASSED ✓"
        else:
            FAILED += 1
            status = "FAILED ✗"

        print(f"\n→ {status}")
        RESULTS.append((name, status, None))

    except Exception as e:
        FAILED += 1
        tb = traceback.format_exc()
        print(f"EXCEPTION: {e}\n{tb}")
        RESULTS.append((name, "ERROR ✗", str(e)))


# ─────────────────────────────────────────────────────
# Test Scenarios
# ─────────────────────────────────────────────────────

async def test_01_warehouse_data_annual():
    """Scenario 1: Generic warehouse data - BSTA annual total assets."""
    await run_test(
        "01 – Warehouse-Daten: BSTA jährlich Total Aktiven",
        snb_get_warehouse_data(WarehouseDataInput(cube_id="BSTA.SNB.JAHR_K.BIL.AKT.TOT", from_date="2020", to_date="2024")),
        checks=["__SUCCESS__", "BSTA.SNB.JAHR_K.BIL.AKT.TOT", "Zeitreihe"],
    )


async def test_02_warehouse_data_monthly():
    """Scenario 2: Generic warehouse data - BSTA monthly total assets."""
    await run_test(
        "02 – Warehouse-Daten: BSTA monatlich Total Aktiven",
        snb_get_warehouse_data(WarehouseDataInput(cube_id="BSTA.SNB.MONA_US.BIL.AKT.TOT", from_date="2024-01", to_date="2024-06")),
        checks=["__SUCCESS__", "BSTA.SNB.MONA_US.BIL.AKT.TOT"],
    )


async def test_03_warehouse_metadata_bil():
    """Scenario 3: Warehouse metadata - BSTA BIL dimensions."""
    await run_test(
        "03 – Metadaten: BSTA BIL Dimensionen",
        snb_get_warehouse_metadata(WarehouseMetadataInput(cube_id="BSTA.SNB.JAHR_K.BIL.AKT.TOT")),
        checks=["__SUCCESS__", "BANKENGRUPPE", "WAEHRUNG", "Dimension"],
    )


async def test_04_warehouse_metadata_efr():
    """Scenario 4: Warehouse metadata - BSTA EFR dimensions."""
    await run_test(
        "04 – Metadaten: BSTA EFR Dimensionen",
        snb_get_warehouse_metadata(WarehouseMetadataInput(cube_id="BSTA.SNB.JAHR_K.EFR.GER")),
        checks=["__SUCCESS__", "BANKENGRUPPE", "Dimension"],
    )


async def test_14_list_warehouse_cubes():
    """Scenario 14: List all available warehouse cubes."""
    await run_test(
        "14 – Warehouse Cube-Übersicht",
        snb_list_warehouse_cubes(),
        checks=[
            "BSTA.SNB.JAHR_K.BIL.AKT.TOT",
            "BSTA.SNB.JAHR_K.EFR.GER",
            "MONA_US",
            "BANKENGRUPPE",
        ],
    )


async def test_15_list_bank_groups():
    """Scenario 15: List all bank group IDs."""
    await run_test(
        "15 – Bankengruppen-Liste",
        snb_list_bank_groups(),
        checks=["A30", "G10", "G15", "G25", "Kantonalbanken", "Grossbanken"],
    )


async def test_16_invalid_cube_id():
    """Scenario 16: Error handling with invalid warehouse cube ID."""
    async def _fetch_invalid():
        try:
            await _fetch_warehouse(
                cube_id="INVALID.CUBE.ID",
                endpoint="data",
                lang="de",
            )
            return "Error: Expected an exception but none was raised"
        except Exception as e:
            return _handle_http_error(e)

    await run_test(
        "16 – Ungültige Warehouse Cube-ID → Fehlermeldung",
        _fetch_invalid(),
        checks=["__ERROR__"],
    )


# ─────────────────────────────────────────────────────
# Banking Balance Sheet Tests (Task 6)
# ─────────────────────────────────────────────────────

async def test_05_banking_balance_sheet_default():
    """Scenario 5: Banking balance sheet - annual, default (all banks, both sides)."""
    await run_test(
        "05 – Bankenbilanz: jährlich, alle Banken, beide Seiten",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput()),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_06_banking_balance_sheet_multi_groups():
    """Scenario 6: Banking balance sheet - specific bank groups, assets only."""
    await run_test(
        "06 – Bankenbilanz: G10, G15, G25, nur Aktiven",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            bank_groups=["G10", "G15", "G25"], side="assets"
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_07_banking_balance_sheet_monthly():
    """Scenario 7: Banking balance sheet - monthly, assets, date range."""
    await run_test(
        "07 – Bankenbilanz: monatlich, Aktiven, 2024-01 bis 2024-06",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            frequency="monthly", side="assets",
            from_date="2024-01", to_date="2024-06"
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_08_banking_balance_sheet_liabilities_chf():
    """Scenario 8: Banking balance sheet - liabilities, CHF currency."""
    await run_test(
        "08 – Bankenbilanz: Passiven, Währung CHF",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            side="liabilities", currency="CHF"
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_17_banking_balance_sheet_english():
    """Scenario 17: Banking balance sheet - English language, assets."""
    await run_test(
        "17 – Bankenbilanz: Englisch, Aktiven",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            lang=Language.EN, side="assets"
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_19_banking_balance_sheet_plausibility():
    """Scenario 19: Banking balance sheet - plausibility check for 2023."""
    await run_test(
        "19 – Bankenbilanz: Plausibilität 2023, Aktiven",
        snb_get_banking_balance_sheet(BankingBalanceSheetInput(
            side="assets", from_date="2023", to_date="2023"
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


# ─────────────────────────────────────────────────────
# Banking Income Tests (Task 7)
# ─────────────────────────────────────────────────────

async def test_09_banking_income_default():
    """Scenario 9: Banking income - default (all banks)."""
    await run_test(
        "09 – Erfolgsrechnung: alle Banken",
        snb_get_banking_income(BankingIncomeInput()),
        checks=["__SUCCESS__", "Millionen CHF", "Geschäftsertrag"],
    )


async def test_10_banking_income_multi_groups():
    """Scenario 10: Banking income - G10, G15."""
    await run_test(
        "10 – Erfolgsrechnung: Kantonal- und Grossbanken",
        snb_get_banking_income(BankingIncomeInput(
            bank_groups=["G10", "G15"]
        )),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


async def test_18_banking_income_french():
    """Scenario 18: Banking income - French language."""
    await run_test(
        "18 – Erfolgsrechnung: Französisch",
        snb_get_banking_income(BankingIncomeInput(lang=Language.FR)),
        checks=["__SUCCESS__", "Millionen CHF"],
    )


# ─────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("  swiss-snb-mcp — Warehouse Testszenarien gegen LIVE SNB API")
    print("=" * 70)

    tests = [
        test_01_warehouse_data_annual,
        test_02_warehouse_data_monthly,
        test_03_warehouse_metadata_bil,
        test_04_warehouse_metadata_efr,
        test_05_banking_balance_sheet_default,
        test_06_banking_balance_sheet_multi_groups,
        test_07_banking_balance_sheet_monthly,
        test_08_banking_balance_sheet_liabilities_chf,
        test_09_banking_income_default,
        test_10_banking_income_multi_groups,
        test_14_list_warehouse_cubes,
        test_15_list_bank_groups,
        test_16_invalid_cube_id,
        test_17_banking_balance_sheet_english,
        test_18_banking_income_french,
        test_19_banking_balance_sheet_plausibility,
    ]

    for test_fn in tests:
        await test_fn()

    # ── Summary ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("  ZUSAMMENFASSUNG")
    print("=" * 70)
    for name, status, err in RESULTS:
        icon = "✓" if "PASSED" in status else "✗"
        line = f"  {icon} {name}: {status}"
        if err:
            line += f" ({err[:60]})"
        print(line)

    print(f"\n  Total: {PASSED + FAILED} | Bestanden: {PASSED} | Fehlgeschlagen: {FAILED}")
    print("=" * 70)

    return FAILED == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
