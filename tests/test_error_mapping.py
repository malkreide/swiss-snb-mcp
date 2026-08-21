"""`_handle_http_error`: welcher Fehler welche Meldung bekommt.

Anlass sind die roten Live-Laeufe vom 20.8.2026. Die Warehouse-Szenarien 07
und 08 meldeten «Unexpected error processing the request. See server log for
details» — die generische Auffangmeldung. Der Traceback im CI-Log zeigte den
Grund: `asyncio.timeout` in warehouse.py wirft beim Ablauf des Budgets den
EINGEBAUTEN `TimeoutError`, und der ist kein Untertyp von
`httpx.TimeoutException`. Der Timeout-Zweig griff also nie.

Das ist keine Kosmetik: «unerwartet, siehe Server-Log» sagt dem Aufrufer, dass
etwas kaputt ist. «Timeout, bitte nochmal» sagt ihm, was er tun kann — und
letzteres stand schon bereit.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from swiss_snb_mcp.server import _handle_http_error

GENERISCH = (
    "Error: Unexpected error processing the request. See server log for details."
)
TIMEOUT = "Error: Request to data.snb.ch timed out. Please try again."


def _status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://data.snb.ch/api/x")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("x", request=request, response=response)


class TestTimeouts:
    def test_httpx_timeout(self):
        assert _handle_http_error(httpx.ReadTimeout("x")) == TIMEOUT

    def test_eingebauter_timeout_error(self):
        """Der Fall, der am 20.8.2026 als «unerwartet» durchrutschte."""
        assert _handle_http_error(TimeoutError()) == TIMEOUT

    def test_asyncio_timeout_error_ist_derselbe_typ(self):
        """Vorbedingung, damit der Test oben nicht am falschen Namen haengt.

        Seit 3.11 ist `asyncio.TimeoutError` nur ein Alias auf den eingebauten
        Typ. Waere er es nicht, deckte der Test darueber den Weg ueber
        `asyncio.timeout` nicht ab.
        """
        assert asyncio.TimeoutError is TimeoutError

    def test_die_beiden_typen_sind_wirklich_unverwandt(self):
        """Die Annahme, die den Fehler erzeugt hat, hier festgenagelt.

        Waere `httpx.TimeoutException` ein Untertyp von `TimeoutError`, haette
        der urspruengliche Zweig genuegt und dieser Test waere sinnlos.
        """
        assert not issubclass(httpx.TimeoutException, TimeoutError)
        assert not issubclass(TimeoutError, httpx.TimeoutException)

    async def test_ein_abgelaufenes_asyncio_budget_landet_im_timeout_zweig(self):
        """Nicht der Typ von Hand, sondern der echte Mechanismus.

        Ein von Hand geworfener `TimeoutError` kodiert meine Annahme darueber,
        was `asyncio.timeout` wirft. Hier laeuft ein echtes Budget ab.
        """
        with pytest.raises(TimeoutError) as excinfo:
            async with asyncio.timeout(0.01):
                await asyncio.sleep(5)
        assert _handle_http_error(excinfo.value) == TIMEOUT


class TestUebrigeZuordnung:
    """Die anderen Zweige duerfen der Timeout-Erweiterung nicht zum Opfer fallen."""

    def test_connect_error(self):
        got = _handle_http_error(httpx.ConnectError("x"))
        assert "Cannot reach data.snb.ch" in got

    @pytest.mark.parametrize(
        ("code", "fragment"),
        [(404, "HTTP 404"), (400, "HTTP 400"), (423, "HTTP 423"), (500, "HTTP 500")],
    )
    def test_http_status_behaelt_seine_meldung(self, code: int, fragment: str):
        got = _handle_http_error(_status(code))
        assert fragment in got
        assert got != TIMEOUT
        assert got != GENERISCH

    def test_wirklich_unerwartetes_bleibt_generisch(self):
        """Die Auffangmeldung soll nicht verschwinden, nur seltener werden."""
        assert _handle_http_error(ValueError("x")) == GENERISCH
