"""
20 diverse test scenarios for swiss-snb-mcp
Tests run against the LIVE SNB API at data.snb.ch (no mocks).
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

from swiss_snb_mcp.server import (
    snb_get_exchange_rates,
    snb_get_annual_exchange_rates,
    snb_get_balance_sheet,
    snb_convert_currency,
    snb_get_cube_data,
    snb_get_cube_metadata,
    snb_list_currencies,
    snb_list_balance_sheet_positions,
    snb_list_known_cubes,
    ExchangeRatesInput,
    AnnualExchangeRatesInput,
    BalanceSheetInput,
    ConvertCurrencyInput,
    CubeDataInput,
    CubeMetadataInput,
    Language,
)

# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

PASSED = 0
FAILED = 0
RESULTS = []


def now_month():
    return datetime.now().strftime("%Y-%m")


def months_ago(n):
    d = datetime.now() - timedelta(days=30 * n)
    return d.strftime("%Y-%m")


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
# 20 Test Scenarios
# ─────────────────────────────────────────────────────

async def test_01_monthly_fx_eur_usd():
    """Scenario 1: Monthly EUR and USD exchange rates for the last 3 months."""
    await run_test(
        "01 – Monatliche Wechselkurse EUR/USD (3 Monate)",
        snb_get_exchange_rates(ExchangeRatesInput(
            currencies=["EUR1", "USD1"],
            from_date=months_ago(3),
            to_date=now_month(),
        )),
        checks=["__SUCCESS__", "EUR", "USD", "CHF"],
    )


async def test_02_monthly_fx_all_currencies_default():
    """Scenario 2: Default call – all currencies, default date range."""
    await run_test(
        "02 – Alle Währungen, Standardzeitraum",
        snb_get_exchange_rates(ExchangeRatesInput()),
        checks=["__SUCCESS__", "devkum"],
    )


async def test_03_monthly_fx_with_month_end():
    """Scenario 3: EUR rates with both monthly average AND month-end rates."""
    await run_test(
        "03 – EUR mit Monatsmittel + Monatsende",
        snb_get_exchange_rates(ExchangeRatesInput(
            currencies=["EUR1"],
            include_month_end=True,
            from_date=months_ago(6),
        )),
        checks=["__SUCCESS__", "EUR"],
    )


async def test_04_monthly_fx_french():
    """Scenario 4: Exchange rates in French language."""
    await run_test(
        "04 – Wechselkurse auf Französisch",
        snb_get_exchange_rates(ExchangeRatesInput(
            currencies=["GBP1", "JPY100"],
            lang=Language.FR,
            from_date="2025-01",
            to_date="2025-06",
        )),
        checks=["__SUCCESS__", "CHF"],
    )


async def test_05_annual_fx_long_history():
    """Scenario 5: Annual exchange rates over a 20-year period."""
    await run_test(
        "05 – Jährliche Wechselkurse 2005–2025 (20 Jahre)",
        snb_get_annual_exchange_rates(AnnualExchangeRatesInput(
            currencies=["EUR1", "USD1"],
            from_year="2005",
            to_year="2025",
        )),
        checks=["__SUCCESS__", "devkua", "2005"],
    )


async def test_06_annual_fx_single_year():
    """Scenario 6: Annual rate for a single year."""
    await run_test(
        "06 – Jahresdurchschnitt 2020 (Einzeljahr)",
        snb_get_annual_exchange_rates(AnnualExchangeRatesInput(
            currencies=["CHF1"] if False else ["USD1"],
            from_year="2020",
            to_year="2020",
        )),
        checks=["__SUCCESS__", "2020"],
    )


async def test_07_balance_sheet_default():
    """Scenario 7: SNB balance sheet with default key positions."""
    await run_test(
        "07 – SNB Bilanz (Standard-Schlüsselpositionen)",
        snb_get_balance_sheet(BalanceSheetInput()),
        checks=["__SUCCESS__", "Millionen CHF", "snbbipo"],
    )


async def test_08_balance_sheet_all_assets():
    """Scenario 8: All asset positions of the SNB balance sheet."""
    await run_test(
        "08 – SNB Bilanz: Alle Aktiven",
        snb_get_balance_sheet(BalanceSheetInput(
            positions=["GFG", "D", "RIWF", "IZ", "T0"],
            from_date=months_ago(6),
        )),
        checks=["__SUCCESS__", "Mio. CHF"],
    )


async def test_09_balance_sheet_english():
    """Scenario 9: Balance sheet in English language."""
    await run_test(
        "09 – SNB Bilanz auf Englisch",
        snb_get_balance_sheet(BalanceSheetInput(
            positions=["T0", "T1"],
            lang=Language.EN,
            from_date=months_ago(12),
        )),
        checks=["__SUCCESS__"],
    )


async def test_10_convert_eur_to_chf():
    """Scenario 10: Convert 10,000 EUR to CHF."""
    await run_test(
        "10 – Umrechnung 10'000 EUR → CHF",
        snb_convert_currency(ConvertCurrencyInput(
            amount=10000.0,
            currency_id="EUR1",
        )),
        checks=["__SUCCESS__", "CHF", "EUR", "Monatsmittel"],
    )


async def test_11_convert_jpy_to_chf():
    """Scenario 11: Convert JPY (100-unit currency) to CHF."""
    await run_test(
        "11 – Umrechnung 500'000 JPY → CHF (100er-Einheit)",
        snb_convert_currency(ConvertCurrencyInput(
            amount=500000.0,
            currency_id="JPY100",
        )),
        checks=["__SUCCESS__", "CHF", "JPY"],
    )


async def test_12_convert_with_reference_month():
    """Scenario 12: Convert USD with a specific historical reference month."""
    await run_test(
        "12 – Umrechnung 45'000 USD mit Referenzmonat 2024-06",
        snb_convert_currency(ConvertCurrencyInput(
            amount=45000.0,
            currency_id="USD1",
            reference_month="2024-06",
        )),
        checks=["__SUCCESS__", "CHF", "2024-06"],
    )


async def test_13_convert_invalid_currency():
    """Scenario 13: Convert with an invalid currency ID → expect error."""
    await run_test(
        "13 – Ungültige Währung (XYZ1) → Fehlermeldung",
        snb_convert_currency(ConvertCurrencyInput(
            amount=100.0,
            currency_id="XYZ1",
        )),
        checks=["__ERROR__"],
    )


async def test_14_cube_data_saron():
    """Scenario 14: Generic cube access – SARON/policy rate data."""
    await run_test(
        "14 – Cube-Daten: SNB-Leitzins/SARON (snbgwdzid)",
        snb_get_cube_data(CubeDataInput(
            cube_id="snbgwdzid",
            from_date="2024-01",
            to_date="2024-12",
        )),
        checks=["__SUCCESS__", "snbgwdzid"],
    )


async def test_15_cube_data_monetary_aggregates():
    """Scenario 15: Generic cube – M1/M2/M3 monetary aggregates."""
    await run_test(
        "15 – Cube-Daten: Geldmengen M1/M2/M3 (snbmonagg)",
        snb_get_cube_data(CubeDataInput(
            cube_id="snbmonagg",
            from_date="2024-01",
            to_date="2024-12",
        )),
        checks=["__SUCCESS__", "snbmonagg"],
    )


async def test_16_cube_metadata_exchange_rates():
    """Scenario 16: Metadata inspection for the monthly exchange rate cube."""
    await run_test(
        "16 – Metadaten: Cube devkum (Monatskurse)",
        snb_get_cube_metadata(CubeMetadataInput(
            cube_id="devkum",
        )),
        checks=["__SUCCESS__", "Dimension", "devkum"],
    )


async def test_17_cube_metadata_international_rates():
    """Scenario 17: Metadata for international money market rates cube."""
    await run_test(
        "17 – Metadaten: Cube zimoma (Int. Geldmarktsätze)",
        snb_get_cube_metadata(CubeMetadataInput(
            cube_id="zimoma",
            lang=Language.EN,
        )),
        checks=["__SUCCESS__", "Dimension", "zimoma"],
    )


async def test_18_list_currencies():
    """Scenario 18: List all available currency IDs."""
    await run_test(
        "18 – Währungsliste (27 Währungen)",
        snb_list_currencies(),
        checks=["EUR1", "USD1", "JPY100", "GBP1", "CNY100", "XDR1"],
    )


async def test_19_list_balance_sheet_positions():
    """Scenario 19: List all balance sheet position IDs."""
    await run_test(
        "19 – Bilanzpositionen-Liste (Aktiven + Passiven)",
        snb_list_balance_sheet_positions(),
        checks=["Aktiven", "Passiven", "GFG", "T0", "T1", "N"],
    )


async def test_20_list_known_cubes():
    """Scenario 20: List all known cubes with descriptions."""
    await run_test(
        "20 – Übersicht bekannte SNB Cubes",
        snb_list_known_cubes(),
        checks=["devkum", "devkua", "snbbipo", "snbgwdzid", "zirepo", "zimoma", "snboffzisa", "snbmonagg"],
    )


# ─────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("  swiss-snb-mcp — 20 Testszenarien gegen LIVE SNB API")
    print("=" * 70)

    tests = [
        test_01_monthly_fx_eur_usd,
        test_02_monthly_fx_all_currencies_default,
        test_03_monthly_fx_with_month_end,
        test_04_monthly_fx_french,
        test_05_annual_fx_long_history,
        test_06_annual_fx_single_year,
        test_07_balance_sheet_default,
        test_08_balance_sheet_all_assets,
        test_09_balance_sheet_english,
        test_10_convert_eur_to_chf,
        test_11_convert_jpy_to_chf,
        test_12_convert_with_reference_month,
        test_13_convert_invalid_currency,
        test_14_cube_data_saron,
        test_15_cube_data_monetary_aggregates,
        test_16_cube_metadata_exchange_rates,
        test_17_cube_metadata_international_rates,
        test_18_list_currencies,
        test_19_list_balance_sheet_positions,
        test_20_list_known_cubes,
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
