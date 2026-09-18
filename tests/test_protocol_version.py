"""ARCH-012: die beiden Spec-Revisionen, gegen die dieser Server geprueft ist.

Das SDK bietet keinen setzbaren Pin — die Aushandlung liegt in der
Session-Schicht, weder `MCPServer.__init__` noch `Settings` nimmt den Parameter
entgegen. Ein Pin ist hier deshalb eine erklaerte Konstante plus eine
Zusicherung, die bricht, sobald ein SDK-Bump sie verschiebt. Bewusst CI-seitig
und nicht zur Laufzeit: brechen soll unser Build, nicht der Betrieb von
jemandem, der `mcp` weiter oben aktualisiert hat.

`mcp` 2.x bedient ZWEI Protokoll-Aeren ueber denselben Server; die erste
Anfrage einer Verbindung entscheidet, welche gilt:

* die **Legacy-Aera** mit `initialize`-Handshake — was heutige Clients
  sprechen. Sie deckelt bei `LATEST_HANDSHAKE_VERSION`.
* die **Modern-Aera** mit Pro-Request-Envelope, die `LATEST_MODERN_VERSION`
  erreicht.

**`LATEST_PROTOCOL_VERSION` ist ein Alias auf die MODERNE Version.** Wer nur
dagegen pinnt — die naheliegende Einzelzeile — sichert die Aera, in der heute
praktisch niemand spricht, und laesst die andere frei wandern. Beide stehen
deshalb getrennt hier.

Nachgemessen statt aus Konstantennamen geschlossen: die Aushandlung steht in
`mcp/server/runner.py::_negotiate_initialize` und lautet

    negotiated = requested if requested in HANDSHAKE_PROTOCOL_VERSIONS
                 else LATEST_HANDSHAKE_VERSION

— sie haengt an keinem Transport, gilt also fuer stdio ebenso wie fuer HTTP.

Der gemessene Teil stand hier zwei Fassungen lang als fehlend — mit der
Begruendung, dieses Repo baue keine ASGI-App, durch die sich ein `initialize`
schicken liesse. Die Begruendung war falsch, und zwar zweifach: die moderne
Aera braucht ueberhaupt kein `initialize`, und der Handshake laeuft ohnehin
nicht ueber HTTP, sondern ueber denselben Duplex-Stream, den stdio fuettert.
Was fehlte, war nicht ein Transport, sondern ein Stream-Paar.

Die Zusicherungen ab `test_die_moderne_aera_antwortet_...` fahren deshalb
`Server.run()` ueber ein Speicher-Stream-Paar und schicken echte
JSON-RPC-Rahmen hinein — dieselbe Schleife (`serve_dual_era_loop`), die stdio
im Betrieb faehrt, nur ohne Prozessgrenze. Gemessen wird die Antwort, nicht die
Konstante.

Die Konstanten-Pins darueber bleiben trotzdem stehen: sie sagen, WELCHE
Revision dokumentiert ist, und brechen bei einem SDK-Bump auch dann, wenn die
Aushandlung als solche weiter funktioniert. Das sind zwei verschiedene Fragen.

Ein grauer Fleck, benannt statt verschwiegen: das Stream-Paar haengt an
`mcp._lowlevel_server`. Einen oeffentlichen Weg, eine `MCPServer` ueber rohe
Rahmen anzusprechen, gibt es in `mcp` 2.2 nicht — `Client(mcp)` faehrt
in-process am Framing vorbei (`DirectDispatcher`) und kann die
Aera-Entscheidung deshalb gar nicht ausloesen.
"""

from __future__ import annotations

import pathlib
import re

import anyio
from mcp.shared.memory import create_client_server_memory_streams
from mcp.shared.message import SessionMessage
from mcp.types.version import (
    LATEST_HANDSHAKE_VERSION,
    LATEST_MODERN_VERSION,
    LATEST_PROTOCOL_VERSION,
)
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    PROTOCOL_VERSION_META_KEY,
    JSONRPCRequest,
)
from mcp_types.jsonrpc import INVALID_REQUEST, UNSUPPORTED_PROTOCOL_VERSION

from swiss_snb_mcp.server import mcp

REPO = pathlib.Path(__file__).resolve().parents[1]

# Die Revisionen, die die READMEs nennen. Sie stehen hier und nicht im `src/`:
# das SDK bestimmt sie, der Server setzt sie nicht. Eine Konstante im
# Auslieferungspfad waere eine zweite Wahrheit, die driften kann — genau so kam
# `bag-epl-mcp` dazu, Aufrufern `2025-06-18` zu melden.
DOCUMENTED_HANDSHAKE_VERSION = "2025-11-25"
DOCUMENTED_MODERN_VERSION = "2026-07-28"

# Datei und Ueberschrift, unter der die beiden Revisionen dokumentiert stehen.
README_SECTIONS = (
    ("README.md", "## MCP Protocol Version"),
    ("README.de.md", "## MCP-Protokollversion"),
)


def test_die_handshake_aera_steht_wo_die_readme_sie_nennt() -> None:
    """Die Aera, die bestehende Clients sprechen — der lasttragende Pin."""
    assert LATEST_HANDSHAKE_VERSION == DOCUMENTED_HANDSHAKE_VERSION, (
        f"das SDK deckelt den Handshake jetzt bei {LATEST_HANDSHAKE_VERSION}, "
        f"die READMEs sagen {DOCUMENTED_HANDSHAKE_VERSION}. Nicht blind "
        "nachziehen: erst das Spec-Changelog zwischen den beiden Revisionen "
        "lesen, dann README.md, README.de.md und CHANGELOG.md zusammen mit "
        "dieser Konstante bewegen."
    )


def test_die_moderne_aera_steht_wo_die_readme_sie_nennt() -> None:
    assert LATEST_MODERN_VERSION == DOCUMENTED_MODERN_VERSION, (
        f"das SDK erreicht modern jetzt {LATEST_MODERN_VERSION}, die READMEs "
        f"sagen {DOCUMENTED_MODERN_VERSION}"
    )


def test_latest_protocol_version_ist_der_alias_auf_die_moderne_aera() -> None:
    """Die Falle, gegen die dieses Repo abgesichert wird, benannt.

    Ohne diese Zeile liest sich der naheliegende Einzeiler
    `PIN == LATEST_PROTOCOL_VERSION` wie eine vollstaendige Zusicherung. Sie
    ist es nicht, und man sieht es dem Namen nicht an. Faellt dieser Test, hat
    das SDK die Bedeutung des Alias geaendert — dann ist die Aufteilung oben
    neu zu bewerten, nicht nur eine Zahl.
    """
    assert LATEST_PROTOCOL_VERSION == LATEST_MODERN_VERSION
    assert LATEST_PROTOCOL_VERSION != LATEST_HANDSHAKE_VERSION


def test_die_beiden_aeren_sind_verschieden() -> None:
    """Sagt, wann die Aufteilung oben wieder verschwinden darf.

    Faellt das SDK die Aeren eines Tages auf eine Revision zusammen, ist die
    doppelte Zusicherung redundant und gehoert zurueckgebaut. Dieser Test ist
    die Stelle, an der das auffaellt.
    """
    assert LATEST_MODERN_VERSION > LATEST_HANDSHAKE_VERSION


def test_der_pin_ist_eine_datierte_revision_kein_bewegliches_ziel() -> None:
    """«latest» oder eine Spanne wuerde den Zweck des Pins aufheben."""
    for value in (DOCUMENTED_HANDSHAKE_VERSION, DOCUMENTED_MODERN_VERSION):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), value


def test_beide_readmes_nennen_dieselben_beiden_revisionen() -> None:
    """Ein Pin, den die Doku anders angibt, ist kein Pin.

    Jede Sprache einzeln geprueft: im Portfolio sind EN und DE desselben Repos
    schon dreimal auseinandergelaufen, weil nur eine Fassung nachgezogen wurde
    und niemand die andere daneben gelegt hat.
    """
    for name, anchor in README_SECTIONS:
        text = (REPO / name).read_text(encoding="utf-8")
        parts = text.split(anchor, 1)
        assert len(parts) > 1, f"{name} hat keinen Abschnitt «{anchor}»"
        body = parts[1][:2500]
        for value in (DOCUMENTED_HANDSHAKE_VERSION, DOCUMENTED_MODERN_VERSION):
            assert value in body, f"{name} nennt {value} nicht im Abschnitt «{anchor}»"


# ---------------------------------------------------------------------------
# Gemessen: echte JSON-RPC-Rahmen durch die Schleife, die stdio faehrt
# ---------------------------------------------------------------------------


def _modern_frame(
    method: str,
    *,
    request_id: int = 1,
    version: str = DOCUMENTED_MODERN_VERSION,
    params: dict[str, object] | None = None,
) -> dict[str, object]:
    """Eine Anfrage mit dem Pro-Request-Envelope der modernen Aera.

    Handgebaut statt ueber einen Client-Helfer: der Envelope IST das, was hier
    geprueft wird. Ein Helfer, der ihn aus derselben SDK-Konstante fuellt, die
    der Server danach akzeptiert, koennte eine Aenderung an beiden Enden nicht
    widerlegen.
    """
    envelope = {
        PROTOCOL_VERSION_META_KEY: version,
        CLIENT_CAPABILITIES_META_KEY: {},
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {**(params or {}), "_meta": envelope},
    }


def _initialize_frame(version: str, *, request_id: int = 1) -> dict[str, object]:
    """Der Handshake der Legacy-Aera."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": version,
            "capabilities": {},
            "clientInfo": {"name": "test_protocol_version", "version": "0"},
        },
    }


async def _exchange(frames: list[dict[str, object]]) -> list[dict]:
    """Schickt `frames` nacheinander durch eine Verbindung und gibt die
    Antworten zurueck.

    EINE Verbindung fuer alle Rahmen, mit Absicht: die Aera-Entscheidung faellt
    pro Verbindung und genau einmal. Ein Helfer, der je Rahmen neu verbindet,
    koennte die Sperre in beide Richtungen nicht zeigen.
    """
    server = mcp._lowlevel_server
    init_options = server.create_initialization_options()
    responses: list[dict] = []
    async with (
        create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ),
        anyio.create_task_group() as tg,
    ):
        tg.start_soon(lambda: server.run(server_read, server_write, init_options))
        for frame in frames:
            message = JSONRPCRequest.model_validate(frame)
            await client_write.send(SessionMessage(message))
            answer = await client_read.receive()
            assert not isinstance(answer, Exception), answer
            responses.append(
                answer.message.model_dump(by_alias=True, exclude_none=True)
            )
        tg.cancel_scope.cancel()
    return responses


async def test_die_moderne_aera_antwortet_auf_den_envelope() -> None:
    """Der Kern: ein Rahmen mit Envelope wird bedient, ohne jeden Handshake.

    `server/discover` nennt in `supportedVersions` die Revisionen, in denen die
    Verbindung gerade steht — das ist die Aussage des Servers ueber sich
    selbst, nicht unsere Konstante von oben, die nur danebengehalten wird.
    """
    (answer,) = await _exchange([_modern_frame("server/discover")])

    assert "error" not in answer, answer
    assert answer["result"]["supportedVersions"] == [DOCUMENTED_MODERN_VERSION]


async def test_der_handshake_deckelt_bei_der_aelteren_revision() -> None:
    """Ein Client, der `2026-07-28` per `initialize` verlangt, bekommt den
    Deckel zurueck — die moderne Revision kennt diese Methode nicht.

    Die naheliegende Fehllesart waere, aus `LATEST_PROTOCOL_VERSION` zu
    schliessen, der Handshake erreiche `2026-07-28`. Diese Zeile misst das
    Gegenteil an der Antwort.
    """
    (answer,) = await _exchange([_initialize_frame(DOCUMENTED_MODERN_VERSION)])

    assert answer["result"]["protocolVersion"] == DOCUMENTED_HANDSHAKE_VERSION


async def test_der_handshake_gibt_die_verlangte_revision_zurueck() -> None:
    """Gegenstueck zum Deckel: eine Revision AUS der Handshake-Aera kommt
    unveraendert zurueck. Ohne diese Zeile waere der Test oben auch dann
    gruen, wenn der Server jede Anfrage mit derselben Zahl beantwortete."""
    (answer,) = await _exchange([_initialize_frame(DOCUMENTED_HANDSHAKE_VERSION)])

    assert answer["result"]["protocolVersion"] == DOCUMENTED_HANDSHAKE_VERSION


async def test_auf_einer_modernen_verbindung_wird_initialize_abgelehnt() -> None:
    """Die Aera-Sperre, Richtung eins."""
    _, answer = await _exchange(
        [
            _modern_frame("tools/list", request_id=1),
            _initialize_frame(DOCUMENTED_HANDSHAKE_VERSION, request_id=2),
        ]
    )

    assert answer["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert answer["error"]["data"]["supported"] == [DOCUMENTED_MODERN_VERSION]


async def test_auf_einer_legacy_verbindung_wird_der_envelope_abgelehnt() -> None:
    """Die Aera-Sperre, Richtung zwei.

    Beide Richtungen stehen hier, weil eine allein nichts ueber die Sperre
    sagt: ein Server, der schlicht jede zweite Anfrage einer Verbindung
    ablehnte, bestuende jeden einzelnen der beiden Tests.
    """
    _, answer = await _exchange(
        [
            _initialize_frame(DOCUMENTED_HANDSHAKE_VERSION, request_id=1),
            _modern_frame("tools/list", request_id=2),
        ]
    )

    assert answer["error"]["code"] == INVALID_REQUEST


async def test_eine_unbekannte_revision_wird_benannt_abgelehnt() -> None:
    """Die Absage nennt, was ginge — sonst raet der Aufrufer.

    `-32022` ist der eine Code, bei dem ein aushandelnder Client NICHT auf eine
    aeltere Revision zurueckfaellt; er braucht die Liste im `data`-Feld.
    """
    (answer,) = await _exchange([_modern_frame("tools/list", version="2099-01-01")])

    assert answer["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
    assert answer["error"]["data"]["requested"] == "2099-01-01"
    assert answer["error"]["data"]["supported"] == [DOCUMENTED_MODERN_VERSION]
