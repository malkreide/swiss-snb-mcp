"""Was der Server ueber sich selbst meldet — gemessen an der Antwort.

Spec `2026-07-28` legt `serverInfo` in das `_meta` jeder Antwort und laesst
`server/discover` zusaetzlich `websiteUrl` tragen. Beides fuellt das SDK aus
den Konstruktor-Argumenten von `MCPServer`; wird eines nicht uebergeben,
faellt es nicht aus, sondern geht LEER hinaus.

Genau das war hier der Fall. Am 18.9.2026 nachgemessen, in beiden Aeren:

    "_meta": {"io.modelcontextprotocol/serverInfo":
              {"name": "swiss_snb_mcp", "version": ""}}

Ein leerer String ist keine fehlende Angabe, sondern eine falsche: der Server
behauptet damit eine Version und nennt keine. Kein Test hatte das gesehen,
weil keiner in die Antwort geschaut hatte — `pyproject.toml`, `server.json`
und die README-Badges waren untereinander sauber synchron, und `src/` durfte
nach `check_version_sync.py` gar keine Nummer fuehren. Die Kette war an jeder
geprueften Stelle heil und endete trotzdem im Nichts.

Deshalb haengen die Zusicherungen hier an der Drahtform und nicht an
`mcp.version`: ein Blick auf das Attribut waere auch dann gruen, wenn das
Argument auf dem Weg zum `serverInfo` verlorenginge.
"""

from __future__ import annotations

import json
import pathlib

import anyio
from mcp.shared.memory import create_client_server_memory_streams
from mcp.shared.message import SessionMessage
from mcp_types import (
    CLIENT_CAPABILITIES_META_KEY,
    PROTOCOL_VERSION_META_KEY,
    SERVER_INFO_META_KEY,
    JSONRPCRequest,
)

from swiss_snb_mcp import __version__
from swiss_snb_mcp.server import REPOSITORY_URL, USER_AGENT, mcp

REPO = pathlib.Path(__file__).resolve().parents[1]

MODERN_VERSION = "2026-07-28"
HANDSHAKE_VERSION = "2025-11-25"


async def _one_answer(frame: dict[str, object]) -> dict:
    """Schickt einen Rahmen durch die Schleife, die stdio faehrt, und gibt die
    Antwort als Drahtform zurueck."""
    server = mcp._lowlevel_server
    init_options = server.create_initialization_options()
    async with (
        create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ),
        anyio.create_task_group() as tg,
    ):
        tg.start_soon(lambda: server.run(server_read, server_write, init_options))
        await client_write.send(SessionMessage(JSONRPCRequest.model_validate(frame)))
        answer = await client_read.receive()
        tg.cancel_scope.cancel()
    assert not isinstance(answer, Exception), answer
    return answer.message.model_dump(by_alias=True, exclude_none=True)


async def _discover() -> dict:
    return await _one_answer(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "server/discover",
            "params": {
                "_meta": {
                    PROTOCOL_VERSION_META_KEY: MODERN_VERSION,
                    CLIENT_CAPABILITIES_META_KEY: {},
                }
            },
        }
    )


async def _initialize() -> dict:
    return await _one_answer(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": HANDSHAKE_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "test_server_identity", "version": "0"},
            },
        }
    )


async def test_die_moderne_aera_meldet_die_paketversion() -> None:
    answer = await _discover()
    info = answer["result"]["_meta"][SERVER_INFO_META_KEY]

    assert info["version"] == __version__, (
        f"server/discover meldet serverInfo.version={info['version']!r}; "
        "erwartet ist die Version aus den Paket-Metadaten. Bei '' fehlt "
        "`version=` am MCPServer-Konstruktor."
    )


async def test_die_gemeldete_version_ist_nicht_leer() -> None:
    """Die Zeile, die den urspruenglichen Befund haelt.

    Der Test darueber allein reichte nicht: er vergliche `''` mit `''`, falls
    `__version__` selbst einmal leer wuerde — und waere dann gruen, waehrend
    der Server nichts meldet.
    """
    answer = await _discover()
    info = answer["result"]["_meta"][SERVER_INFO_META_KEY]

    assert info["version"], "der Server meldet eine leere Version"


async def test_auch_der_handshake_meldet_die_paketversion() -> None:
    """Beide Aeren einzeln geprueft.

    Das `serverInfo` der Legacy-Aera steht an einer anderen Stelle der Antwort
    (im `result`, nicht im `_meta`) und wird vom SDK getrennt gefuellt. Eine
    Zusicherung ueber die eine sagt nichts ueber die andere.
    """
    answer = await _initialize()
    info = answer["result"]["serverInfo"]

    assert info["version"] == __version__
    assert info["version"]


async def test_der_server_nennt_seine_projekt_url() -> None:
    """`websiteUrl` war nie gesetzt: `server.json` nannte das Ziel der
    Registry, der Server selbst schwieg."""
    answer = await _discover()
    info = answer["result"]["_meta"][SERVER_INFO_META_KEY]

    assert info.get("websiteUrl") == REPOSITORY_URL, (
        "server/discover meldet kein `websiteUrl`; erwartet ist "
        f"{REPOSITORY_URL}. Fehlt der Schluessel ganz, fehlt `website_url=` "
        "am MCPServer-Konstruktor."
    )


def test_die_projekt_url_ist_dieselbe_wie_in_server_json() -> None:
    """Zwei Stellen nennen die URL; eine Drift waere sonst unsichtbar.

    `check_version_sync.py` haelt die Versionen zusammen, nicht die URLs.
    """
    manifest = json.loads((REPO / "server.json").read_text(encoding="utf-8"))

    assert manifest["websiteUrl"] == REPOSITORY_URL


def test_der_user_agent_traegt_dieselbe_url() -> None:
    """Die Begruendung fuer `REPOSITORY_URL` festgehalten: eine Konstante,
    zwei Verwendungen. Faellt diese Zeile, ist wieder ein Literal entstanden.
    """
    assert f"(+{REPOSITORY_URL})" in USER_AGENT
