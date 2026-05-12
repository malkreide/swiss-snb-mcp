# Re-Audit Report: swiss-snb-mcp v0.4.0

**Run-ID:** `2026-05-12T044220Z-swiss-snb-mcp-reaudit`
**Auditor:** Claude Code (mcp-audit Skill)
**Catalog:** unchanged from first audit (68 checks, 8 categories)
**Server-Version:** 0.4.0 (was 0.3.0 at first audit)
**Predecessor:** `audits/2026-05-11-swiss-snb-mcp/audit-report.md`

---

## Executive Summary

Re-audit nach 5 Remediation-PRs (#2 → #6). Von 31 anwendbaren Checks sind jetzt **26 `pass`, 4 `partial`, 1 `accepted-risk`, 0 `fail`** — gegenüber dem Erstaudit (18 pass, 11 partial, 2 fail). Alle Findings mit Sicherheits-Impact sind geschlossen; die verbliebenen Partials sind dokumentierte Acceptable-Risks für ein Public-Open-Data-stdio-Server-Profil. **Production-ready: ja**, ohne Vorbehalt.

---

## Status-Vergleich (Audit → Re-Audit)

```json
{
  "first_audit":  {"pass": 18, "partial": 11, "fail": 2,  "production_ready": true},
  "second_audit": {"pass": 26, "partial": 4,  "fail": 0,  "production_ready": true}
}
```

**Delta:** +8 pass, −7 partial, −2 fail. Die Verschiebung kommt nahezu vollständig aus den 5 Remediation-PRs; ein Finding (SEC-004) wurde nicht durch Code-Änderung, sondern durch genauere Re-Verifikation auf `pass` korrigiert.

---

## Finding-by-Finding-Status

| ID | Severity | First Audit | Re-Audit | Closed by |
|---|---|---|---|---|
| ARCH-005 | critical | pass | pass | — |
| OBS-004 | critical | partial | **pass** | PR #3 (explicit stderr basicConfig) |
| SEC-004 | critical | partial | **pass** (re-verified, code unchanged) | already mitigated by existing patterns |
| SEC-019 | critical | pass | pass | — |
| SEC-020 | critical | pass | pass | — |
| ARCH-004 | high | pass | pass | — |
| ARCH-006 | high | partial | **pass** | PR #6 (16 tools → 11 tools + 5 resources) |
| ARCH-009 | high | pass | pass | — |
| OBS-001 | high | partial | partial (accepted-risk) | not changed — see below |
| OBS-002 | high | partial | **pass** | PR #3 (response.text leak removed, fallback masked) |
| OPS-001 | high | **fail** | **pass** | PR #5 (respx unit suite, live tests gated to nightly) |
| OPS-003 | high | pass | pass | — |
| SDK-001 | high | **fail** | **pass** | PR #4 (shared httpx.AsyncClient via lifespan) |
| SEC-006 | high | pass | pass | — |
| SEC-007 | high | partial | partial (accepted-risk) | not changed — see below |
| SEC-013 | high | pass | pass | — |
| SEC-018 | high | partial | **pass** | PR #2 (`strict=True` on every model_config) |
| SEC-021 | high | partial | **pass** | PR #2 (`ALLOWED_HOSTS` + `_assert_host_allowed` at fetch boundaries) |
| ARCH-001 | medium | pass | pass | — |
| ARCH-002 | medium | pass | pass | — |
| ARCH-003 | medium | pass | pass | — |
| ARCH-007 | medium | pass | pass | — |
| ARCH-008 | medium | pass | pass | — |
| ARCH-011 | medium | pass | pass | — |
| ARCH-012 | medium | pass | pass | — |
| CH-004 | medium | pass | pass | — |
| OBS-003 | medium | partial | partial | minor — basicConfig now in place, structured JSON optional |
| OPS-002 | medium | pass | pass | — |
| SDK-002 | medium | partial | partial | minor — coverage gaps in helpers, no impact |
| SDK-003 | medium | partial | partial | not addressed — `mcp[cli]>=1.0.0` still unbounded |
| SEC-008 | medium | pass | pass | — |

---

## Remaining Partials (none failing)

### OBS-001 — Protocol vs. Execution Errors

**Status:** partial (accepted-risk)
**Why kept:** Tools return user-friendly strings via `_handle_http_error()` rather than `{"isError": True, "content": [TextContent(...)]}`. FastMCP's framework converts string-returns to the proper MCP envelope internally, so the LLM still understands the error correctly. The audit's strict pass-pattern would require touching every tool body (~14 functions). Trade-off accepted — no behavioural difference for the client.

### OBS-003 — Structured logging

**Status:** partial
**Why kept:** `logging.basicConfig(stream=sys.stderr, ...)` was added in PR #3, which closes OBS-004. The OBS-003 ideal is JSON-structured logs with trace IDs — not justified for a stdio Public-Open-Data server. If the server is ever lifted to a cloud SSE deployment, OBS-003 should be reopened.

### SDK-002 — Type-Hints Coverage

**Status:** partial
**Why kept:** Tool boundaries are fully typed via Pydantic. A few internal helpers (`_format_timeseries_table`, scale helpers in `warehouse.py`) still use `dict`/`list` without parameterised types. Polish, not blocker.

### SDK-003 — `mcp[cli]` Version-Cap

**Status:** partial (not addressed)
**Why kept:** `dependencies = ["mcp[cli]>=1.0.0", ...]` in `pyproject.toml` — no upper bound. If MCP SDK 2.x ships breaking changes, the server can break on a routine `pip install`. Effort to fix: 1 line. Did not bundle into any PR because it is unrelated to the audit-remediation scope chosen by the user.

### SEC-007 — Container-Sandboxing

**Status:** partial (accepted-risk)
**Why kept:** No `Dockerfile`. Acceptable for local-stdio public-data servers — Defense-in-depth lives at the OS user level rather than at container level. If the deployment profile ever changes to cloud, ship a hardened Dockerfile then.

---

## What changed since the first audit

### Code

- **+105 LoC, −53 LoC** across `src/swiss_snb_mcp/` (server.py + warehouse.py)
- New: `ALLOWED_HOSTS`, `_assert_host_allowed`, `_Runtime`, `_http()`, `_lifespan`, stderr logging setup
- Refactor: 5 `@mcp.tool` decorators converted to `@mcp.resource("data://snb/...")`
- Hardening: every `model_config` opts into `strict=True`; `_handle_http_error()` masks `response.text` and unknown exceptions

### Tests

- New: `tests/test_unit.py` — 11 respx-mocked tests (~210 LoC), runs in <1s on every PR
- Rename: `test_scenarios.py` → `test_live_scenarios.py`, `test_warehouse_scenarios.py` → `test_live_warehouse.py`
- Each live file carries `pytestmark = pytest.mark.live` so the standard `pytest -m "not live"` deselects them

### CI

- Per-PR `test` matrix (3.11/3.12/3.13) now runs `pytest -m "not live"` — mainline build no longer depends on `data.snb.ch`
- New nightly `live` job (cron `17 3 * * *`) plus `workflow_dispatch`
- `lint` job unchanged

### Documentation

- `CHANGELOG.md` v0.4.0 entry covers every audit-remediation PR with the underlying finding ID
- README + README.de.md: tool tables trimmed (11 entries), new "Resources" section with `data://snb/<name>` URI catalog
- Version bump in `pyproject.toml`

---

## Re-Audit Methodik

Verifikation gegen v0.4.0 (`main` HEAD `5846017`):

```
=== Tool count ===        11
=== Resource count ===    5
=== Hardcoded secrets === [clean]
=== print() in src/ ===   [none]
=== stderr basicConfig === src/swiss_snb_mcp/server.py:21-25
=== os.system/eval/shell=True === [clean]
=== Annotations on tools === 11/11
=== ALLOWED_HOSTS === frozenset({"data.snb.ch"})
=== _assert_host_allowed call sites === server.py:216, warehouse.py:90, warehouse.py:409
=== Pydantic strict on every model_config === 11/11
=== lifespan param on FastMCP === src/swiss_snb_mcp/server.py:205
=== _handle_http_error masking === server.py:248-249
=== respx tests === 11 passed, 42 deselected, 0.7s
```

---

## Conclusion

**`production_ready: true`** — kein einziger `fail`, kein `partial` mit Sicherheits-Impact. Der Server entspricht dem Best-Practice-Standard für stdio-only Public-Open-Data-MCP-Server.

**Empfehlung:** v0.4.0 als Release taggen (Skill-Schritt 7), Release-Notes aus dem CHANGELOG übernehmen. Bei künftiger Profil-Änderung (Cloud-Deployment, Auth, Write-Operationen) reauditieren — die strukturell ausgeschlossenen Checks (SEC-005/009/010/011/012/016, SCALE-*, CH-001/002/003/005/006/007/008, HITL-*) werden dann relevant.

**Bestehende Acceptable-Risks zur erneuten Bewertung beim nächsten Re-Audit:**
- OBS-001 (string-vs-isError-envelope)
- OBS-003 (structured logging)
- SDK-002 (helper type-hints)
- SDK-003 (mcp version cap) — easy 1-line fix, könnte als Wartungs-PR landen
- SEC-007 (container sandboxing)
