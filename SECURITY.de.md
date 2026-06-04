# Sicherheitsrichtlinie & Sicherheitslage

[🇬🇧 English Version](SECURITY.md)

`swiss-snb-mcp` wurde gegen den internen MCP-Best-Practice-Audit-Katalog
(68 Checks, 8 Kategorien) gehärtet. Dieses Dokument fasst die Sicherheitslage
zusammen und dokumentiert die **akzeptierten Risiken** für Kontrollen, die für
ein reines stdio-Profil eines Public-Open-Data-Servers bewusst zurückgestellt
werden.

## Schwachstelle melden

Bitte eröffnen Sie ein privates Security Advisory im GitHub-Repository oder
kontaktieren Sie die in `README.md` genannte verantwortliche Person. Erstellen Sie
für ausnutzbare Schwachstellen **keine** öffentlichen Issues.

## Zusammenfassung der Sicherheitslage

Dies ist ein **rein lesender**, **PII-freier** MCP-Server für **öffentliche Open
Data**. Alle 11 Tools fragen ausschliesslich data.snb.ch ab. Das jüngste
Re-Audit (v0.4.0, `audits/2026-05-12-swiss-snb-mcp-reaudit/`) ergab
**27 pass / 3 partial / 0 fail** — produktionsreif, ohne offenes Finding mit
Sicherheits-Impact. Bereits umgesetzte Härtungsmassnahmen:

| Bereich | Kontrolle |
|---|---|
| Egress | HTTPS-erzwungene Allow-List ausschliesslich für `data.snb.ch`, vor jeder ausgehenden Anfrage durch `_assert_host_allowed` durchgesetzt (SEC-021) |
| TLS | Zertifikatsprüfung standardmässig aktiv (httpx-Standard; nie deaktiviert) (SEC-004) |
| Transport | Standardmässig stdio — stdout ist für den JSON-RPC-Stream reserviert (OBS-004) |
| Input | Pydantic-v2-Strict-Validierung (`strict=True`) für jedes Tool-Input-Modell (SEC-018) |
| Secrets | Keine API-Keys oder Zugangsdaten — das SNB-Datenportal ist vollständig öffentlich, es gibt nichts zu speichern oder zu leaken (SEC-013/ARCH-005) |
| Fehler | Upstream-Antworten und Stack-Traces werden nur nach stderr geloggt; das Modell sieht eine generische, bereinigte Meldung (`_handle_http_error`) (OBS-002) |
| Stdout | Reserviert für den JSON-RPC-Stream; Logging via `basicConfig` fest auf stderr (OBS-004) |
| Verbindungen | Ein gemeinsamer `httpx.AsyncClient` über die Server-Lifespan geöffnet, nicht pro Aufruf (SDK-001) |
| Tests | respx-mockierte Unit-Suite läuft bei jedem PR (3.11/3.12/3.13); Live-API-Tests auf einen Nightly-Job beschränkt (OPS-001) |

Die vollständigen Berichte finden Sie unter `audits/`, die Härtungshistorie in
`CHANGELOG.md`.

## Akzeptierte Risiken

Die folgenden Audit-Prüfungen bleiben bewusst **partial**. Keine hat einen
Sicherheits-Impact für einen reinen stdio-Public-Open-Data-Server, und jede ist
im Re-Audit-Bericht (`audits/2026-05-12-swiss-snb-mcp-reaudit/audit-report.md`)
dokumentiert.

### OBS-001 — Protokoll- vs. Ausführungsfehler-Envelope

**Status:** akzeptiertes Risiko.
Tools geben benutzerfreundliche Strings über `_handle_http_error()` zurück statt
eines expliziten `isError`-Envelopes. FastMCP wandelt String-Rückgaben in den
korrekten MCP-Envelope um, sodass der Client Fehler weiterhin richtig
interpretiert. Das strikte Pass-Muster würde jeden Tool-Body berühren — ohne
verhaltensmässigen Nutzen.

### OBS-003 — Strukturiertes Logging

**Status:** akzeptiertes Risiko.
`logging.basicConfig(stream=sys.stderr, …)` ist vorhanden (schliesst OBS-004).
JSON-strukturierte Logs mit Trace-IDs sind für einen stdio-Server nicht
gerechtfertigt. Neu zu bewerten, falls der Server je auf ein Cloud-/SSE-Deployment
gehoben wird.

### SDK-002 — Abdeckung der Type-Hints

**Status:** akzeptiertes Risiko.
Die Tool-Grenzen sind über Pydantic vollständig typisiert. Einige interne Helfer
verwenden noch blosse `dict`/`list` ohne parametrisierte Typen — Politur, kein
Blocker.

### SDK-003 — `mcp[cli]`-Versions-Cap

**Status:** akzeptiertes Risiko.
`mcp[cli]>=1.0.0` hat keine Obergrenze; ein künftiges SDK 2.x könnte eine
Routine-Installation brechen. Als einzeiliger Wartungs-Fix vermerkt.

### SEC-007 — Container-Sandboxing

**Status:** akzeptiertes Risiko.
Kein `Dockerfile`. Akzeptabel für lokale stdio-Public-Data-Server —
Defense-in-Depth liegt auf der OS-Benutzerebene. Ein gehärtetes Image
ausliefern, falls sich das Deployment-Profil je in die Cloud verschiebt.

## Re-Evaluierungs-Auslöser

Diese Akzeptanzen sollten neu bewertet werden, falls der Server jemals:

- **Schreib**-Funktionalität erhält oder beginnt, **PII** zu verarbeiten, oder
- Tools **dynamisch** / aus entfernten Quellen registriert, oder
- auf ein **Cloud-/SSE**-Deployment verschoben wird (dann werden OBS-003, SEC-007
  und die Netzwerk-Binding-Checks relevant), oder
- hinter einem gemeinsamen MCP-Gateway aggregiert wird (dann Tool-Allow-Listing
  und Poisoning-Erkennung auf Gateway-Ebene umsetzen).
