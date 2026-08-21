"""Retry policy toward the SNB Warehouse (ARCH-014): Retry-After, jitter, budget."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from swiss_snb_mcp import retry as r
from swiss_snb_mcp import server as srv
from swiss_snb_mcp import warehouse as w

URL = f"{w.WAREHOUSE_BASE_URL}/BSTA/data/de"


def _resp(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", URL))


class TestParseRetryAfter:
    def test_delta_seconds(self):
        assert r.parse_retry_after(_resp(429, "120")) == 120.0

    def test_http_date_in_the_future(self):
        when = datetime.now(UTC) + timedelta(seconds=90)
        got = r.parse_retry_after(_resp(503, format_datetime(when, usegmt=True)))
        assert got is not None
        assert 80 <= got <= 95

    def test_http_date_in_the_past_means_now(self):
        when = datetime.now(UTC) - timedelta(hours=1)
        assert (
            r.parse_retry_after(_resp(503, format_datetime(when, usegmt=True))) == 0.0
        )

    def test_absent_header(self):
        assert r.parse_retry_after(_resp(429)) is None

    def test_malformed_header_does_not_raise(self):
        assert r.parse_retry_after(_resp(429, "next Tuesday")) is None
        assert r.parse_retry_after(_resp(429, "")) is None
        assert r.parse_retry_after(_resp(429, "-5")) is None

    def test_ignored_on_other_statuses(self):
        assert r.parse_retry_after(_resp(500, "30")) is None

    def test_no_response_at_all(self):
        assert r.parse_retry_after(None) is None


class TestRetryDelay:
    def test_retry_after_beats_the_table(self):
        # RETRY_DELAYS[0] = 2 spans [1, 3]s — 9 can only come from the header.
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "9"))
        assert 9.0 <= r.retry_delay(0, exc) <= 9.0 * (1 + r.RETRY_AFTER_JITTER)

    def test_retry_after_is_never_undercut(self):
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "5"))
        for _ in range(50):
            assert r.retry_delay(0, exc) >= 5.0

    def test_absurd_retry_after_is_capped(self):
        # Exactly the cap: capping happens after jitter. Equality still
        # discriminates — the bare table would give 2s here.
        exc = httpx.HTTPStatusError("503", request=None, response=_resp(503, "86400"))
        assert r.retry_delay(0, exc) == r.MAX_DELAY_S

    def test_the_cap_is_a_real_bound_not_a_midpoint(self):
        """MAX_DELAY_S must hold even when jitter swings up (Codex review, parlament#35)."""
        exc = httpx.HTTPStatusError("429", request=None, response=_resp(429, "86400"))
        for attempt in range(len(r.RETRY_DELAYS)):
            for _ in range(20):
                assert r.retry_delay(attempt, None) <= r.MAX_DELAY_S
                assert r.retry_delay(attempt, exc) <= r.MAX_DELAY_S

    def test_delay_is_spread(self):
        draws = {r.retry_delay(2, None) for _ in range(30)}
        assert len(draws) > 1, "delay is deterministic — jitter is not applied"
        base = r.RETRY_DELAYS[2]
        assert all(
            base * (1 - r.JITTER_SPREAD) <= d <= base * (1 + r.JITTER_SPREAD)
            for d in draws
        )


@pytest.fixture(autouse=True)
def http_client(monkeypatch):
    """`_fetch_warehouse` takes its client from the lifespan, which no test runs.

    The existing suite patches `warehouse._http` per test; doing it once here
    keeps the retry tests about retries.
    """
    client = httpx.AsyncClient()
    monkeypatch.setattr(w, "_http", lambda: client)
    return client


@pytest.fixture
def fake_clock(monkeypatch):
    """A clock that only advances when the client sleeps.

    Without it the budget can never run out: patched-out sleeps take no
    wall-clock time, ``time.monotonic()`` never moves, and the test would pass
    whatever the budget logic did.
    """
    now = {"t": 1000.0}
    slept: list[float] = []

    async def _sleep(seconds):
        slept.append(seconds)
        now["t"] += seconds

    # Auf `retry`, nicht auf `warehouse`: Dort liegt die Schleife seit dem
    # Umzug. Ein Patch auf das alte Modul waere wirkungslos, und die Suite
    # wuerde die echte Backoff-Leiter abwarten statt etwas zu pruefen.
    monkeypatch.setattr(r.time, "monotonic", lambda: now["t"])
    monkeypatch.setattr(r, "_sleep", _sleep)
    return slept


@respx.mock
async def test_retry_after_reaches_the_sleep(fake_clock):
    respx.get(URL).mock(side_effect=[_resp(503, "7"), httpx.Response(200, json={})])
    await w._fetch_warehouse("BSTA", "data")
    assert len(fake_clock) == 1
    assert 7.0 <= fake_clock[0] <= 7.0 * (1 + r.RETRY_AFTER_JITTER)


@respx.mock
async def test_404_still_fails_fast_without_waiting(fake_clock):
    """A non-retryable status is a statement about the request, not the moment."""
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await w._fetch_warehouse("BSTA", "data")
    assert route.call_count == 1
    assert fake_clock == []


@respx.mock
async def test_budget_cuts_the_ladder_short(fake_clock):
    route = respx.get(URL).mock(side_effect=httpx.ConnectError(""))
    with pytest.raises((httpx.ConnectError, TimeoutError)):
        await w._fetch_warehouse("BSTA", "data", total_budget=1.0)
    assert route.call_count < r.MAX_RETRIES, "budget did not bound the ladder"
    assert route.call_count >= 1, "the first attempt must always go out"


@respx.mock
async def test_full_ladder_runs_when_the_budget_allows(fake_clock):
    """Counter-direction: a wide budget must not cut anything short."""
    route = respx.get(URL).mock(side_effect=httpx.ConnectError(""))
    with pytest.raises(httpx.ConnectError):
        await w._fetch_warehouse("BSTA", "data", total_budget=600.0)
    assert route.call_count == r.MAX_RETRIES


@respx.mock
async def test_per_request_timeout_is_clamped_to_the_remaining_budget(fake_clock):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    await w._fetch_warehouse("BSTA", "data", total_budget=4.0)
    sent = route.calls.last.request.extensions["timeout"]
    assert sent["read"] == pytest.approx(4.0), sent


@respx.mock
async def test_a_slow_response_is_cut_by_the_wall_clock_deadline():
    """The budget must bind even when the httpx timeout never fires.

    httpx applies its timeout per operation and the read timeout restarts with
    every chunk, so a slowly trickling response can outlast the total budget
    without any single read timing out. Hence a real ``asyncio.timeout``.

    Deliberately without ``fake_clock``: this guarantee is about real time, and
    a clock that only moves when something sleeps could not refute it.
    """
    import asyncio as real_asyncio
    import time as real_time

    async def _slow(request):
        await real_asyncio.sleep(1.0)
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=_slow)
    started = real_time.monotonic()
    with pytest.raises(TimeoutError):
        await w._fetch_warehouse("BSTA", "data", total_budget=0.05)
    elapsed = real_time.monotonic() - started
    assert elapsed < 0.5, f"deadline did not cut: {elapsed:.2f}s"


def test_default_budget_stays_under_the_mcp_client_default():
    """The warehouse serves prepared cubes — no long-query case to protect."""
    from mcp.shared._httpx_utils import MCP_DEFAULT_TIMEOUT

    assert r.TOTAL_BUDGET_S < MCP_DEFAULT_TIMEOUT


# --- Die Naht, und warum sie nicht `asyncio.sleep` ist -----------------------


def test_der_retry_geht_ueber_den_alias():
    """Sonst patchen die Tests eine Naht, die der Code gar nicht benutzt.

    Umgeht das Modul den Alias, bleibt der Patch wirkungslos und die Suite
    wartet die echte Backoff-Leiter ab. Kein Test faellt dabei — sie wird nur
    um ein Vielfaches langsamer, und eine laengere Laufzeit ist kein Signal,
    das jemand liest. Diese Zusicherung macht daraus einen Fehlschlag.
    """
    quelle = inspect.getsource(r)
    assert "await _sleep(" in quelle, "der Retry ruft den Modul-Alias nicht mehr auf"
    assert "await asyncio.sleep(" not in quelle, "der Retry umgeht den Alias"
    # Und die Schleife liegt wirklich dort, wo die Fixture patcht: Waere sie
    # zurueck in warehouse.py, zeigte die Fake-Uhr wieder ins Leere.
    assert "await _sleep(" not in inspect.getsource(w), (
        "der Retry ist zurueck in warehouse.py — die Fake-Uhr patcht dann das "
        "falsche Modul"
    )


# --- Der server.py-Pfad faehrt dieselbe Politik ------------------------------
#
# Am 19.8.2026 fielen fuenf Live-Szenarien mit «Request to data.snb.ch timed
# out» — alle im Pfad von `server.py`, der als einziger gar keinen Retry hatte,
# waehrend `warehouse.py` denselben Wackler der Quelle uebersprang. Diese
# Zusicherungen halten fest, dass beide Haelften jetzt gleich reagieren.

SNB_URL = f"{srv.SNB_BASE_URL}/devkum/data/de"


@pytest.fixture
def server_client(monkeypatch):
    """`_fetch_snb` holt seinen Client aus dem Lifespan, den kein Test faehrt.

    Eigener Patch und nicht der von `warehouse`: `warehouse` bindet `_http`
    beim Import in den eigenen Namensraum, ein Patch dort erreicht `server`
    nicht — und umgekehrt.
    """
    client = httpx.AsyncClient()
    monkeypatch.setattr(srv, "_http", lambda: client)
    return client


@respx.mock
async def test_server_pfad_wiederholt_nach_503(server_client, fake_clock):
    route = respx.get(SNB_URL).mock(
        side_effect=[_resp(503), httpx.Response(200, json={"ok": True})]
    )
    got = await srv._fetch_snb("devkum/data/de")
    assert got == {"ok": True}
    assert route.call_count == 2
    assert len(fake_clock) == 1, "ohne Wartezeit ist es kein Backoff"


@respx.mock
async def test_server_pfad_wiederholt_nach_timeout(server_client, fake_clock):
    """Der Fall vom 19.8.2026, in klein."""
    route = respx.get(SNB_URL).mock(
        side_effect=[httpx.ReadTimeout("x"), httpx.Response(200, json={"ok": True})]
    )
    got = await srv._fetch_snb("devkum/data/de")
    assert got == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_server_pfad_achtet_den_retry_after(server_client, fake_clock):
    respx.get(SNB_URL).mock(side_effect=[_resp(503, "7"), httpx.Response(200, json={})])
    await srv._fetch_snb("devkum/data/de")
    assert 7.0 <= fake_clock[0] <= 7.0 * (1 + r.RETRY_AFTER_JITTER)


@respx.mock
async def test_server_pfad_gibt_bei_404_sofort_auf(server_client, fake_clock):
    """Ein 404 wird nicht besser, wenn man dreimal fragt."""
    route = respx.get(SNB_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await srv._fetch_snb("devkum/data/de")
    assert route.call_count == 1
    assert fake_clock == [], "auf einen 404 darf nicht gewartet werden"


@respx.mock
async def test_server_pfad_bleibt_im_budget(server_client, fake_clock):
    respx.get(SNB_URL).mock(return_value=_resp(503))
    with pytest.raises(httpx.HTTPStatusError):
        await srv._fetch_snb("devkum/data/de")
    assert sum(fake_clock) <= r.TOTAL_BUDGET_S


def test_beide_haelften_teilen_eine_quelle():
    """Zwei Kopien derselben Politik driften; genau das war der Ausgangspunkt.

    Geprueft wird die Abwesenheit einer zweiten Schleife, nicht ihre
    Anwesenheit an einer Stelle: Ein `import` allein sagt noch nicht, dass
    daneben nicht doch wieder von Hand wiederholt wird.
    """
    schleife = "for attempt in range("
    # Vorbedingung: Die gesuchte Zeichenkette existiert ueberhaupt. Ohne sie
    # waere die Suche unten immer erfolglos und der Test immer gruen — er
    # pruefte dann die Schreibweise meines Musters, nicht den Code.
    assert schleife in inspect.getsource(r), (
        "die Schleife sieht anders aus als gesucht — das Muster ist veraltet"
    )
    for modul in (srv, w):
        assert schleife not in inspect.getsource(modul), (
            f"{modul.__name__} hat wieder eine eigene Retry-Schleife"
        )
