"""Unit tests for swiss-snb-mcp.

These tests run fast, run in CI on every PR, and never touch the network.
HTTP calls are intercepted by `respx`. For end-to-end coverage against the
live SNB API see `tests/test_live_scenarios.py` and
`tests/test_live_warehouse.py` (marker: `live`).

Die Antworten sind **aufgezeichnet, nicht ausgedacht**: Quelle, Datum,
Auswahlregel und SHA-256 je Datei stehen in `tests/fixtures/PROVENANCE.md`,
neu aufzeichnen mit `python scripts/record_fixtures.py`.

Davor standen hier drei Bauer — `_devkum_response`, `_snbbipo_response`,
`_warehouse_response` —, jeder mit einer einzigen Reihe und dem Kommentar
"minimal but structurally faithful". Was der Vergleich mit der Quelle ergeben
hat, steht im CHANGELOG; kurz: der Schluessel hatte ein anderes Format, der
Warehouse-Header eine statt vier Dimensionen, und die Einheit gab es so nicht.
"""

import sys
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fixture_data import (
    currency_ids,
    dim_values,
    payload,
    position_ids,
    timeseries,
)

from swiss_snb_mcp.server import (
    BALANCE_SHEET_POSITIONS,
    CURRENCIES,
    CURRENCY_UNITS,
    BalanceSheetInput,
    CubeDataInput,
    ExchangeRatesInput,
    _assert_host_allowed,
    _lifespan,
    _unit_from_label,
    mcp,
    snb_get_balance_sheet,
    snb_get_cube_data,
    snb_get_exchange_rates,
)
from swiss_snb_mcp.warehouse import (
    BANK_GROUPS,
    BIL_DIM_ORDER,
    EFR_DIM_ORDER,
    BankingIncomeInput,
    WarehouseDataInput,
    WarehouseMetadataInput,
    _clear_dimension_cache,
    snb_get_banking_income,
    snb_get_warehouse_data,
    snb_get_warehouse_metadata,
)

CUBE = "https://data.snb.ch/api/cube"
WAREHOUSE = "https://data.snb.ch/api/warehouse/cube"

BIL_JAHR = "BSTA.SNB.JAHR_K.BIL.AKT.TOT"
BIL_MONAT = "BSTA.SNB.MONA_US.BIL.AKT.TOT"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def lifespan_started():
    """Open the shared httpx.AsyncClient via _lifespan for the duration of the test."""
    async with _lifespan(mcp):
        yield


@pytest.fixture(autouse=True)
def _fresh_dimension_cache():
    """Die Cube-Layouts werden zwischengespeichert — je Test neu."""
    _clear_dimension_cache()
    yield
    _clear_dimension_cache()


def mock_warehouse(cube_id: str, data_fixture: str) -> None:
    """Beide Endpunkte eines Warehouse-Cubes: Struktur und Daten.

    Die Dimensionsdeklaration gehoert dazu, seit der Server sie liest statt sie
    zu kennen. Der Pfad ist bewusst ohne `json`-Segment gemockt: Mit
    `dimensions/json/de` antwortet data.snb.ch mit HTTP 200 und dem HTML der
    Web-App, und genau diesen Pfad hat der Server jahrelang gebaut.
    """
    slug = cube_id.replace(".", "_").lower()
    respx.get(f"{WAREHOUSE}/{cube_id}/dimensions/de").mock(
        return_value=httpx.Response(200, json=payload(f"dimensions_{slug}.json"))
    )
    respx.get(f"{WAREHOUSE}/{cube_id}/data/json/de").mock(
        return_value=httpx.Response(200, json=payload(data_fixture))
    )


# ---------------------------------------------------------------------------
# Happy-path tool coverage (respx-mocked, aus aufgezeichneten Antworten)
# ---------------------------------------------------------------------------


@respx.mock
async def test_snb_get_exchange_rates_happy_path(lifespan_started):
    route = respx.get(f"{CUBE}/devkum/data/json/de").mock(
        return_value=httpx.Response(200, json=payload("cube_devkum.json"))
    )

    result = await snb_get_exchange_rates(ExchangeRatesInput(currencies=["EUR1"]))

    assert route.called
    # Erwartung aus der Fixture abgeleitet: eine hingeschriebene Zahl waere
    # beim naechsten Aufzeichnen falsch, ohne dass sich etwas Geprueftes
    # geaendert haette.
    eur = next(
        s for s in timeseries("cube_devkum.json") if dim_values(s) == ["M0", "EUR1"]
    )
    assert f"{eur['values'][-1]['value']:.5f}" in result
    # Monatsende (M1) bleibt draussen, solange es nicht verlangt wurde.
    month_end = next(
        s for s in timeseries("cube_devkum.json") if dim_values(s) == ["M1", "EUR1"]
    )
    assert month_end["metadata"]["key"] not in result


@respx.mock
async def test_snb_get_balance_sheet_happy_path(lifespan_started):
    route = respx.get(f"{CUBE}/snbbipo/data/json/de").mock(
        return_value=httpx.Response(200, json=payload("cube_snbbipo.json"))
    )

    result = await snb_get_balance_sheet(BalanceSheetInput(positions=["GFG"]))

    assert route.called
    gold = next(s for s in timeseries("cube_snbbipo.json") if dim_values(s) == ["GFG"])
    latest = gold["values"][-1]
    # Aus der Fixture abgeleitet: Betrag, Einheit und Stichmonat.
    assert f"{latest['value']:,.1f} Mio. CHF" in result
    assert latest["date"] in result
    assert BALANCE_SHEET_POSITIONS["GFG"] in result


@respx.mock
async def test_snb_get_cube_data_generic(lifespan_started):
    route = respx.get(f"{CUBE}/devkua/data/json/en").mock(
        return_value=httpx.Response(200, json=payload("cube_devkua_en.json"))
    )

    from swiss_snb_mcp.server import Language

    result = await snb_get_cube_data(CubeDataInput(cube_id="devkua", lang=Language.EN))

    assert route.called
    assert "devkua" in result.lower()


@respx.mock
async def test_snb_get_warehouse_data_happy_path(lifespan_started):
    route = respx.get(f"{WAREHOUSE}/{BIL_JAHR}/data/json/de").mock(
        return_value=httpx.Response(
            200, json=payload("warehouse_bil_aktiven_jahr.json")
        )
    )

    result = await snb_get_warehouse_data(WarehouseDataInput(cube_id=BIL_JAHR))

    assert route.called
    assert "Bankengruppe" in result


# ---------------------------------------------------------------------------
# Die Tabellen dieses Moduls, gegen die Quelle gehalten
# ---------------------------------------------------------------------------


def test_currency_table_matches_the_recorded_cube():
    """Die Waehrungstabelle stimmt mit devkum ueberein — in beide Richtungen.

    Bis zu diesem Durchgang hatte das niemand geprueft, und sie wich in beide
    Richtungen ab: `INR100` stand in der Tabelle und gibt es im Cube nicht, so
    dass `snb_list_currencies` eine Waehrung anbot, auf die jede Abfrage mit
    «keine Daten» antwortet — also mit derselben Meldung wie ein Tippfehler.
    Umgekehrt fehlten die beiden USD-Terminkurse, die es gibt.

    Die Zusicherung laeuft in beide Richtungen, weil nur eine Richtung genau
    die Haelfte des Fehlers durchgelassen haette.
    """
    live = currency_ids()
    assert live, "Fixture ohne Waehrungen — Auswahlregel pruefen"
    assert set(CURRENCIES) == live, (
        f"nur in der Tabelle: {sorted(set(CURRENCIES) - live)}; "
        f"nur im Cube: {sorted(live - set(CURRENCIES))}"
    )
    assert live <= set(CURRENCY_UNITS)


def test_currency_units_match_the_labels_the_source_writes():
    """Die Einheit steht in der Reihenbeschriftung: «DKK 100.-», «EUR 1.-».

    Ein um Faktor 100 falscher Umrechnungskurs ist die unangenehmste Sorte
    falsch — das Ergebnis ist vollstaendig, formatiert und plausibel. Also
    wird die Tabelle gegen die Quelle gehalten, statt ihr geglaubt zu werden.
    """
    checked = 0
    for series in timeseries("cube_devkum.json"):
        dims = dim_values(series)
        if len(dims) != 2:
            continue
        label = series["header"][-1]["dimItem"]
        from_source = _unit_from_label(label)
        if from_source is None:
            continue
        checked += 1
        assert CURRENCY_UNITS[dims[1]] == from_source, (
            f"{dims[1]}: Tabelle {CURRENCY_UNITS[dims[1]]}, Quelle «{label}»"
        )
    assert checked >= 20, "zu wenige Beschriftungen mit Einheit — Zuschnitt pruefen"


def test_balance_sheet_positions_match_the_recorded_cube():
    """Nullbefund, und er gehoert genauso festgehalten: 28 von 28 stimmen."""
    live = position_ids()
    assert live, "Fixture ohne Positionen — Auswahlregel pruefen"
    assert set(BALANCE_SHEET_POSITIONS) == live


def test_bank_group_table_matches_the_recorded_cube():
    """Ebenfalls ein Nullbefund: 12 von 12 Bankengruppen stimmen."""
    live = {dim_values(s)[-1] for s in timeseries("warehouse_bil_aktiven_jahr.json")}
    assert live
    assert live <= set(BANK_GROUPS), f"unbekannt: {sorted(live - set(BANK_GROUPS))}"


# ---------------------------------------------------------------------------
# Der Fund: die Monatsreihe fuehrt fuenf Dimensionen, nicht vier
# ---------------------------------------------------------------------------


def test_the_hardcoded_dimension_order_only_ever_fitted_the_annual_cube():
    """Warum die Ordnung nicht mehr als Konstante taugt.

    `BIL_DIM_ORDER` hat vier Eintraege und passte zur Jahresreihe. Die
    Monatsreihe desselben Werkzeugs fuehrt fuenf Dimensionen — die vierte ist
    die sektorale Gliederung nach ESVG. `_filter_timeseries` verwarf jede
    Reihe, deren Laenge nicht passte, und zwar stumm: `frequency="monthly"`
    lieferte eine leere Tabelle mit HTTP 200.

    Die alte Fixture konnte das nicht zeigen. Sie hatte eine Dimension.
    """
    annual = payload("dimensions_bsta_snb_jahr_k_bil_akt_tot.json")["dimensions"]
    monthly = payload("dimensions_bsta_snb_mona_us_bil_akt_tot.json")["dimensions"]
    efr = payload("dimensions_bsta_snb_jahr_k_efr_ger.json")["dimensions"]

    assert [d["id"] for d in annual] == BIL_DIM_ORDER
    assert [d["id"] for d in efr] == EFR_DIM_ORDER
    assert [d["id"] for d in monthly] != BIL_DIM_ORDER
    assert len(monthly) == len(annual) + 1
    assert "SEKTORESVG" in {d["id"] for d in monthly}

    # Und die Schluessel der Datenantwort tragen genau so viele Werte.
    for fixture, declared in (
        ("warehouse_bil_aktiven_jahr.json", annual),
        ("warehouse_bil_aktiven_monat.json", monthly),
    ):
        widths = {len(dim_values(s)) for s in timeseries(fixture)}
        assert widths == {len(declared)}


@respx.mock
async def test_monthly_banking_balance_sheet_returns_rows(lifespan_started):
    """Der Fund als Zusicherung: die Monatsreihe liefert Zeilen.

    Gegenprobe: Mit der fest verdrahteten Vier-Dimensionen-Ordnung ist das
    Ergebnis leer — kein Fehler, keine Zeile, HTTP 200.
    """
    from swiss_snb_mcp.warehouse import (
        BankingBalanceSheetInput,
        snb_get_banking_balance_sheet,
    )

    mock_warehouse(BIL_MONAT, "warehouse_bil_aktiven_monat.json")
    result = await snb_get_banking_balance_sheet(
        BankingBalanceSheetInput(side="assets", frequency="monthly")
    )
    rows = [line for line in result.splitlines() if line.startswith("| Aktiven")]
    expected = [
        s
        for s in timeseries("warehouse_bil_aktiven_monat.json")
        if dim_values(s)[2] == "T"
    ]
    assert expected, "Fixture ohne Total-Waehrung — Auswahlregel pruefen"
    assert len(rows) == len(expected)


@respx.mock
async def test_unfiltered_dimensions_are_named_in_every_row(lifespan_started):
    """Drei Aggregate unter einer Beschriftung — nicht mehr.

    Der Jahres-Cube fuehrt INLANDAUSLAND mit Total, Inland und Ausland. Der
    Server filterte diese Dimension nicht und zeigte sie nicht an, also kamen
    drei Zeilen heraus, die identisch beschriftet waren und von denen eine die
    Summe der beiden anderen ist. Wer die erste nahm, hatte Glueck; wer
    summierte, verdoppelte die Bilanz.
    """
    from swiss_snb_mcp.warehouse import (
        BankingBalanceSheetInput,
        snb_get_banking_balance_sheet,
    )

    mock_warehouse(BIL_JAHR, "warehouse_bil_aktiven_jahr.json")
    result = await snb_get_banking_balance_sheet(
        BankingBalanceSheetInput(side="assets")
    )
    rows = [line for line in result.splitlines() if line.startswith("| Aktiven")]

    declared = payload("dimensions_bsta_snb_jahr_k_bil_akt_tot.json")["dimensions"]
    regions = next(d for d in declared if d["id"] == "INLANDAUSLAND")["dimensionItems"]
    assert len(regions) > 1, "Fixture mit nur einer Auspraegung — belegt nichts"
    assert len(rows) == len(regions)

    # Jede Auspraegung steht namentlich in genau einer Zeile — und zwar in der
    # Gliederungsspalte, exakt. Ein Teilstring-Vergleich taeugte hier: «Inland»
    # steckt auch in «Total Inland und Ausland», und genau diese Verwechslung
    # ist der Fehler, um den es geht.
    breakdowns = [row.split("|")[3].strip() for row in rows]
    assert len(set(breakdowns)) == len(rows), f"nicht unterscheidbar: {breakdowns}"
    for item in regions:
        assert sum(item["name"] in cell.split(" · ") for cell in breakdowns) == 1, (
            f"«{item['name']}» steht nicht in genau einer Zeile — dann sind sie "
            "wieder nicht auseinanderzuhalten"
        )


@respx.mock
async def test_requesting_a_group_the_cube_lacks_says_which_exist(lifespan_started):
    """Kein leeres Ergebnis, wo eine Auskunft moeglich ist.

    Die Jahresreihe nennt alle Banken `A30`, die Monatsreihe `A40`. Ein `A30`
    gegen die Monatsreihe ergab bisher eine leere Tabelle — was sich liest wie
    «diese Banken haben keine Aktiven».
    """
    from swiss_snb_mcp.warehouse import (
        BankingBalanceSheetInput,
        snb_get_banking_balance_sheet,
    )

    mock_warehouse(BIL_MONAT, "warehouse_bil_aktiven_monat.json")
    result = await snb_get_banking_balance_sheet(
        BankingBalanceSheetInput(
            side="assets", frequency="monthly", bank_groups=["A30"]
        )
    )
    declared = payload("dimensions_bsta_snb_mona_us_bil_akt_tot.json")["dimensions"]
    groups = next(d for d in declared if d["id"] == "BANKENGRUPPE")["dimensionItems"]
    assert result.startswith("Error:")
    assert "A30" in result
    for item in groups:
        assert item["id"] in result


@respx.mock
async def test_banking_income_reads_the_declared_order(lifespan_started):
    from swiss_snb_mcp.warehouse import EFR_POSITIONS

    for pos in EFR_POSITIONS:
        cube = f"BSTA.SNB.JAHR_K.EFR.{pos}"
        respx.get(f"{WAREHOUSE}/{cube}/dimensions/de").mock(
            return_value=httpx.Response(
                200, json=payload("dimensions_bsta_snb_jahr_k_efr_ger.json")
            )
        )
        respx.get(f"{WAREHOUSE}/{cube}/data/json/de").mock(
            return_value=httpx.Response(200, json=payload("warehouse_efr_ger.json"))
        )

    result = await snb_get_banking_income(BankingIncomeInput())
    assert not result.startswith("Error:")
    a30 = [
        s for s in timeseries("warehouse_efr_ger.json") if dim_values(s)[-1] == "A30"
    ]
    assert a30, "Fixture ohne A30 — Auswahlregel pruefen"
    assert result.count("| Geschäftsertrag |") == len(a30)


# ---------------------------------------------------------------------------
# Der zweite Fund: ein Pfad, den es nicht gibt, antwortet mit HTTP 200
# ---------------------------------------------------------------------------


@respx.mock
async def test_warehouse_metadata_asks_the_path_that_exists(lifespan_started):
    """`dimensions/<lang>`, nicht `dimensions/json/<lang>`.

    Der zweite Pfad war der naheliegende — die Datenendpunkte tragen ein
    `json`-Segment. Es gibt ihn nicht, und data.snb.ch beantwortet ihn mit
    HTTP 200 und dem HTML-Geruest der Web-App. Dieses Werkzeug hat deshalb
    fuer jeden Cube einen Fehler geliefert, seit es existiert.

    Die Gegenprobe steckt in dem, was hier NICHT gemockt ist: respx laesst
    keinen ungemockten Aufruf durch, also faellt dieser Test, sobald wieder
    jemand den Pfad mit `json` baut.
    """
    respx.get(f"{WAREHOUSE}/{BIL_JAHR}/dimensions/de").mock(
        return_value=httpx.Response(
            200, json=payload("dimensions_bsta_snb_jahr_k_bil_akt_tot.json")
        )
    )
    respx.get(f"{WAREHOUSE}/{BIL_JAHR}/lastUpdate").mock(
        return_value=httpx.Response(200, json={"editionDate": "20260618_1137"})
    )

    result = await snb_get_warehouse_metadata(WarehouseMetadataInput(cube_id=BIL_JAHR))
    assert not result.startswith("Error:")
    for dim in payload("dimensions_bsta_snb_jahr_k_bil_akt_tot.json")["dimensions"]:
        assert dim["id"] in result


@respx.mock
async def test_html_masquerading_as_a_200_is_refused(lifespan_started):
    """Ein Ausfall, der wie eine Antwort aussieht — und jetzt benannt wird."""
    respx.get(f"{WAREHOUSE}/{BIL_JAHR}/dimensions/de").mock(
        return_value=httpx.Response(
            200,
            html="<!doctype html><html><title>Datenportal</title></html>",
        )
    )
    result = await snb_get_warehouse_metadata(WarehouseMetadataInput(cube_id=BIL_JAHR))
    assert result.startswith("Error:")
    assert "JSON" in result


# ---------------------------------------------------------------------------
# Error-handling: confirm no information leak (OBS-002)
# ---------------------------------------------------------------------------


@respx.mock
async def test_404_returns_friendly_error_with_no_body_leak(lifespan_started):
    respx.get(f"{CUBE}/devkum/data/json/de").mock(
        return_value=httpx.Response(404, text="SECRET-INTERNAL-CODE-99")
    )
    result = await snb_get_exchange_rates(ExchangeRatesInput())
    assert "404" in result
    assert "SECRET-INTERNAL-CODE-99" not in result


@respx.mock
async def test_500_does_not_leak_response_body(lifespan_started):
    respx.get(f"{CUBE}/devkum/data/json/de").mock(
        return_value=httpx.Response(
            500, text="postgres://admin:hunter2@db.internal/snb error"
        )
    )
    result = await snb_get_exchange_rates(ExchangeRatesInput())
    assert "500" in result
    assert "postgres" not in result
    assert "hunter2" not in result


# ---------------------------------------------------------------------------
# Transient SNB lock (HTTP 423) handling
# ---------------------------------------------------------------------------


@respx.mock
async def test_423_returns_locked_message(lifespan_started, monkeypatch):
    # A 423 should produce a clear, identifiable "temporarily locked" message
    # (HTTP 423 is what the SNB warehouse returns while re-publishing a cube).
    import swiss_snb_mcp.warehouse as wh

    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(wh, "_sleep", _no_sleep)
    respx.get(f"{WAREHOUSE}/{BIL_JAHR}/data/json/de").mock(
        return_value=httpx.Response(423, text="locked")
    )

    result = await snb_get_warehouse_data(WarehouseDataInput(cube_id=BIL_JAHR))
    assert "423" in result
    assert result.startswith("Error:")
    assert "locked" not in result.lower() or "temporarily locked" in result.lower()


@respx.mock
async def test_banking_income_all_locked_surfaces_error(lifespan_started, monkeypatch):
    # When every EFR cube is locked, the income tool must surface the error
    # instead of returning a misleading empty "success" response.
    import swiss_snb_mcp.warehouse as wh

    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(wh, "_sleep", _no_sleep)
    respx.get(url__regex=r".*/warehouse/cube/BSTA\.SNB\.JAHR_K\.EFR\..*").mock(
        return_value=httpx.Response(423, text="locked")
    )

    result = await snb_get_banking_income(BankingIncomeInput())
    assert result.startswith("Error:")
    assert "423" in result


# ---------------------------------------------------------------------------
# Defense-in-depth: allow-list and Pydantic strict mode
# ---------------------------------------------------------------------------


def test_allow_list_rejects_non_snb_host():
    with pytest.raises(PermissionError):
        _assert_host_allowed("https://evil.example.com/anything")


def test_allow_list_accepts_snb_host():
    _assert_host_allowed(f"{CUBE}/devkum/data/json/de")


def test_pydantic_strict_rejects_int_coerced_to_str():
    with pytest.raises(ValidationError):
        CubeDataInput(cube_id=12345)


def test_pydantic_strict_rejects_extra_fields():
    with pytest.raises(ValidationError):
        CubeDataInput(cube_id="devkum", bogus_field="x")


def test_cube_id_pattern_rejects_path_traversal():
    with pytest.raises(ValidationError):
        CubeDataInput(cube_id="../../../etc/passwd")
