"""Gemeinsame Retry-Politik gegen data.snb.ch (ARCH-014).

Warum ein eigenes Modul: `warehouse.py` importiert aus `server.py` (`_http`,
`_assert_host_allowed`, `mcp`), und `server.py` zieht `warehouse` erst ganz am
Dateiende nach, um den Zyklus zu brechen. Die Politik kann deshalb in keinem
der beiden liegen, ohne dass der jeweils andere sie nur ueber einen Umweg
bekaeme. Dieses Modul importiert nichts aus dem Paket und ist damit fuer beide
Seiten gleich erreichbar.

Anlass war der Live-Lauf vom 19.8.2026: Fuenf Szenarien fielen mit
«Request to data.snb.ch timed out», alle im Pfad von `server.py` — der als
einziger gar keinen Retry hatte, waehrend `warehouse.py` Budget, `Retry-After`
und Jitter fuehrte. Derselbe Wackler der Quelle warf die eine Haelfte um und
die andere nicht.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

# Eigener Alias, damit Tests die Wartezeit nullen koennen, ohne `asyncio.sleep`
# prozessweit zu entschaerfen. `monkeypatch.setattr(<modul>.asyncio, "sleep", ...)`
# sieht lokal aus, ersetzt `sleep` aber auf dem geteilten Modulobjekt — fuer
# httpx, respx, pytest-asyncio und jeden anderen Importeur im Prozess.
_sleep = asyncio.sleep

MAX_RETRIES = 3
RETRY_DELAYS = [2, 4, 8]  # seconds, exponential backoff

# --- Retry policy (ARCH-014) -------------------------------------------------
# RETRY_STATUS_CODES settles *what* is retried. These settle *how fast* and
# *how long*.

# Ceiling on a single wait — against a ladder that grows without bound and
# against a `Retry-After` the SNB may send but that we need not sit through.
MAX_DELAY_S = 20.0

# Jitter. Without it every client that hit the same outage retries in lockstep,
# and the load returns as a wave exactly when the warehouse recovers — the retry
# storm extends the outage it was meant to bridge.
JITTER_SPREAD = 0.5  # table delays land in [0.5x, 1.5x]

# On a `Retry-After` the spread is one-sided: the source said when to come back,
# so later is polite and earlier ignores the value we just read.
RETRY_AFTER_JITTER = 0.25  # lands in [1.0x, 1.25x]

# Statuses carrying a meaningful `Retry-After` (RFC 9110 §10.2.3).
RETRY_AFTER_STATUSES = frozenset({429, 503})

# 503 Service Unavailable and 423 Locked are both transient — the SNB
# warehouse returns 423 while a cube is being re-published.
RETRY_STATUS_CODES = {423, 503}

# Ceiling on the *whole* call — every attempt, every wait, together.
#
# An attempt count is not a bound: three attempts at a 15s timeout plus 2+4s of
# backoff are over a minute, and `MAX_RETRIES = 3` never says so. The limit that
# matters is not ours either: the caller has its own timeout, and past it nobody
# receives the answer — the work continues, the load lands on the SNB, and the
# result goes nowhere.
#
# Anchored on the Python MCP SDK's `MCP_DEFAULT_TIMEOUT = 30.0`. 25s leaves
# headroom for MCP framing and the tool layer. The warehouse serves prepared
# cubes and answers in well under a second when healthy, so there is no
# long-query case to protect as there is for the SPARQL servers.
TOTAL_BUDGET_S = 25.0


def parse_retry_after(resp: httpx.Response | None) -> float | None:
    """Seconds to wait per the response's ``Retry-After``, or None.

    RFC 9110 §10.2.3 allows delta-seconds and an HTTP-date; both occur, both are
    read. Anything unparseable yields None and the caller falls back to its own
    curve — a malformed header must not become a crash on the error path.
    """
    if resp is None or resp.status_code not in RETRY_AFTER_STATUSES:
        return None
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:  # RFC 9110 dates are GMT; a naive one means UTC
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def retry_delay(attempt: int, last_error: Exception | None) -> float:
    """Seconds to wait after the failed ``attempt`` (0-based, indexes RETRY_DELAYS).

    The source's own answer beats our guess: a ``Retry-After`` on a 429 or 503
    wins over the table, which is guessing at the same question.
    """
    hinted = parse_retry_after(getattr(last_error, "response", None))
    if hinted is not None:
        jittered = hinted * (1.0 + random.random() * RETRY_AFTER_JITTER)
    else:
        jittered = RETRY_DELAYS[attempt] * (
            1.0 - JITTER_SPREAD + random.random() * 2 * JITTER_SPREAD
        )
    # Cap *after* jitter — the other order made MAX_DELAY_S not a bound at all.
    return min(jittered, MAX_DELAY_S)


async def request_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, str] | None = None,
    total_budget: float = TOTAL_BUDGET_S,
) -> httpx.Response:
    """GET ``url`` mit Retry auf transiente Fehler; gibt die Antwort zurueck.

    Wiederholt bis zu ``MAX_RETRIES`` mal bei transienten HTTP-Fehlern (siehe
    RETRY_STATUS_CODES) sowie bei Timeout und Verbindungsfehler, mit
    gejittertem 2/4/8s-Backoff, gedeckelt auf MAX_DELAY_S; ein ``Retry-After``
    auf 429 oder 503 schlaegt die Tabelle.

    ``total_budget`` begrenzt den ganzen Aufruf — Versuche und Wartezeiten
    zusammen.

    Bewusst OHNE Auswertung des Rumpfs: Der Aufrufer entscheidet, ob er
    strenges JSON verlangt (`warehouse.py`) oder `response.json()` genuegt.
    Sonst muesste diese Funktion die Formregeln beider Seiten kennen.
    """
    last_exc: Exception | None = None
    # ARCH-014: the budget bounds the whole call, not just one wait. Monotonic,
    # so an NTP step cannot hand out or revoke budget.
    deadline = time.monotonic() + total_budget

    async def _wait(attempt: int, exc: Exception) -> bool:
        """Sleep before the next attempt. False means the budget is spent."""
        delay = retry_delay(attempt, exc)
        # A wait that outlasts the budget is a wait for nobody: the caller has
        # given up by the time it ends.
        if delay >= deadline - time.monotonic():
            return False
        await _sleep(delay)
        return True

    for attempt in range(MAX_RETRIES):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            # httpx applies its timeout per operation (connect/read/write/pool)
            # and the read timeout restarts with every chunk — that bounds each
            # step, not the call. `asyncio.timeout` is the wall-clock deadline
            # the budget actually promises.
            async with asyncio.timeout(remaining):
                response = await client.get(url, params=params, timeout=remaining)
                response.raise_for_status()
                return response
        except TimeoutError as e:  # budget gone, not just this attempt
            last_exc = e
            break
        except httpx.HTTPStatusError as e:
            if (
                e.response.status_code in RETRY_STATUS_CODES
                and attempt < MAX_RETRIES - 1
            ):
                last_exc = e
                if not await _wait(attempt, e):
                    break
                continue
            raise
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt < MAX_RETRIES - 1:
                last_exc = e
                if not await _wait(attempt, e):
                    break
                continue
            raise

    raise last_exc  # type: ignore[misc]
