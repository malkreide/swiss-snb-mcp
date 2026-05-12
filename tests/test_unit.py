"""Unit tests for swiss-snb-mcp.

These tests run fast, run in CI on every PR, and never touch the network.
HTTP calls are intercepted by `respx`. For end-to-end coverage against the
live SNB API see `tests/test_live_scenarios.py` and
`tests/test_live_warehouse.py` (marker: `live`).
"""

import sys
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from swiss_snb_mcp.server import (
    _assert_host_allowed,
    _lifespan,
    mcp,
    snb_get_balance_sheet,
    snb_get_cube_data,
    snb_get_exchange_rates,
    BalanceSheetInput,
    CubeDataInput,
    ExchangeRatesInput,
)
from swiss_snb_mcp.warehouse import (
    snb_get_warehouse_data,
    WarehouseDataInput,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def lifespan_started():
    """Open the shared httpx.AsyncClient via _lifespan for the duration of the test."""
    async with _lifespan(mcp):
        yield


def _devkum_response() -> dict:
    """Minimal but structurally faithful response for the devkum cube."""
    return {
        "timeseries": [
            {
                "header": [
                    {"dim": "Währung", "dimItem": "Euro (EUR)"},
                    {"dim": "Periodizität", "dimItem": "Monatsmittel"},
                ],
                "metadata": {"key": "M.devkum.EUR1.M", "unit": "CHF"},
                "values": [
                    {"date": "2024-01", "value": 0.95},
                    {"date": "2024-02", "value": 0.96},
                ],
            }
        ]
    }


def _snbbipo_response() -> dict:
    # The balance-sheet tool filters by `{POS_ID}` or `{POS_ID,` in metadata.key.
    return {
        "timeseries": [
            {
                "header": [{"dim": "Position", "dimItem": "Gold (GFG)"}],
                "metadata": {"key": "M.snbbipo.{GFG}", "unit": "Mio. CHF"},
                "values": [
                    {"date": "2024-12", "value": 65000},
                    {"date": "2025-01", "value": 66000},
                ],
            }
        ]
    }


def _warehouse_response() -> dict:
    return {
        "timeseries": [
            {
                "header": [{"dim": "Bankengruppe", "dimItem": "Alle Banken"}],
                "metadata": {
                    "key": "BSTA@SNB.JAHR_K.BIL.AKT.TOT{K,T,T,A30}",
                    "unit": "1000 CHF",
                    "scale": "3",
                },
                "values": [{"date": "2024", "value": 1234567}],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Happy-path tool coverage (respx-mocked)
# ---------------------------------------------------------------------------


@respx.mock
async def test_snb_get_exchange_rates_happy_path(lifespan_started):
    route = respx.get("https://data.snb.ch/api/cube/devkum/data/json/de").mock(
        return_value=httpx.Response(200, json=_devkum_response())
    )

    result = await snb_get_exchange_rates(ExchangeRatesInput())

    assert route.called
    assert "EUR" in result
    assert "0.95" in result or "0.96" in result


@respx.mock
async def test_snb_get_balance_sheet_happy_path(lifespan_started):
    route = respx.get("https://data.snb.ch/api/cube/snbbipo/data/json/de").mock(
        return_value=httpx.Response(200, json=_snbbipo_response())
    )

    result = await snb_get_balance_sheet(BalanceSheetInput())

    assert route.called
    assert "Gold" in result or "GFG" in result


@respx.mock
async def test_snb_get_cube_data_generic(lifespan_started):
    route = respx.get("https://data.snb.ch/api/cube/devkua/data/json/en").mock(
        return_value=httpx.Response(200, json=_devkum_response())
    )

    from swiss_snb_mcp.server import Language

    result = await snb_get_cube_data(CubeDataInput(cube_id="devkua", lang=Language.EN))

    assert route.called
    assert "devkua" in result.lower()


@respx.mock
async def test_snb_get_warehouse_data_happy_path(lifespan_started):
    route = respx.get(
        "https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.BIL.AKT.TOT/data/json/de"
    ).mock(return_value=httpx.Response(200, json=_warehouse_response()))

    result = await snb_get_warehouse_data(
        WarehouseDataInput(cube_id="BSTA.SNB.JAHR_K.BIL.AKT.TOT")
    )

    assert route.called
    assert "Bankengruppe" in result or "1234567" in result


# ---------------------------------------------------------------------------
# Error-handling: confirm no information leak (OBS-002)
# ---------------------------------------------------------------------------


@respx.mock
async def test_404_returns_friendly_error_with_no_body_leak(lifespan_started):
    respx.get("https://data.snb.ch/api/cube/devkum/data/json/de").mock(
        return_value=httpx.Response(404, text="SECRET-INTERNAL-CODE-99")
    )
    result = await snb_get_exchange_rates(ExchangeRatesInput())
    assert "404" in result
    assert "SECRET-INTERNAL-CODE-99" not in result


@respx.mock
async def test_500_does_not_leak_response_body(lifespan_started):
    respx.get("https://data.snb.ch/api/cube/devkum/data/json/de").mock(
        return_value=httpx.Response(
            500, text="postgres://admin:hunter2@db.internal/snb error"
        )
    )
    result = await snb_get_exchange_rates(ExchangeRatesInput())
    assert "500" in result
    assert "postgres" not in result
    assert "hunter2" not in result


# ---------------------------------------------------------------------------
# Defense-in-depth: allow-list and Pydantic strict mode
# ---------------------------------------------------------------------------


def test_allow_list_rejects_non_snb_host():
    with pytest.raises(PermissionError):
        _assert_host_allowed("https://evil.example.com/anything")


def test_allow_list_accepts_snb_host():
    _assert_host_allowed("https://data.snb.ch/api/cube/devkum/data/json/de")


def test_pydantic_strict_rejects_int_coerced_to_str():
    with pytest.raises(Exception) as excinfo:
        CubeDataInput(cube_id=12345)
    assert "ValidationError" in type(excinfo.value).__name__


def test_pydantic_strict_rejects_extra_fields():
    with pytest.raises(Exception) as excinfo:
        CubeDataInput(cube_id="devkum", bogus_field="x")
    assert "ValidationError" in type(excinfo.value).__name__


def test_cube_id_pattern_rejects_path_traversal():
    with pytest.raises(Exception):
        CubeDataInput(cube_id="../../../etc/passwd")
