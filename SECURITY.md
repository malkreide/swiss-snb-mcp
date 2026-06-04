# Security Policy & Posture

[🇩🇪 Deutsche Version](SECURITY.de.md)

`swiss-snb-mcp` was hardened against the internal MCP best-practice audit
catalogue (68 checks, 8 categories). This document summarises the security
posture and records the **accepted-risk** decisions for controls that are
deliberately deferred for a stdio-only public-open-data server profile.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository, or contact the
maintainer listed in `README.md`. Do not file public issues for exploitable
vulnerabilities.

## Posture summary

This is a **read-only**, **no-PII**, **public-open-data** MCP server. All 11
tools only query data.snb.ch. The latest re-audit (v0.4.0,
`audits/2026-05-12-swiss-snb-mcp-reaudit/`) scored **27 pass / 3 partial /
0 fail** — production-ready with no security-impacting findings open.
Hardening already in place:

| Area | Control |
|---|---|
| Egress | HTTPS-only allow-list to `data.snb.ch`, enforced by `_assert_host_allowed` before every outbound request (SEC-021) |
| TLS | Certificate verification on by default (httpx default; never disabled) (SEC-004) |
| Transport | stdio by default — stdout reserved for the JSON-RPC stream (OBS-004) |
| Input | Pydantic v2 strict validation (`strict=True`) on every tool input model (SEC-018) |
| Secrets | No API keys or credentials — the SNB data portal is fully public, so there is nothing to store or leak (SEC-013/ARCH-005) |
| Errors | Upstream bodies and stack traces logged to stderr only; the model sees a generic, sanitised message (`_handle_http_error`) (OBS-002) |
| Stdout | Reserved for the JSON-RPC stream; logging pinned to stderr via `basicConfig` (OBS-004) |
| Connections | One shared `httpx.AsyncClient` opened via the server lifespan, not per call (SDK-001) |
| Tests | respx-mocked unit suite runs on every PR (3.11/3.12/3.13); live API tests gated to a nightly job (OPS-001) |

See `audits/` for the full reports and `CHANGELOG.md` for the hardening history.

## Accepted risks

The following audit checks remain **partial** by design. None has a security
impact for a stdio-only public-open-data server, and each is documented in the
re-audit report (`audits/2026-05-12-swiss-snb-mcp-reaudit/audit-report.md`).

### OBS-001 — Protocol vs. execution error envelope

**Status:** accepted risk.
Tools return user-friendly strings via `_handle_http_error()` rather than an
explicit `isError` envelope. FastMCP converts string returns into the proper
MCP envelope, so the client still interprets errors correctly. The strict
pass-pattern would require touching every tool body with no behavioural benefit.

### OBS-003 — Structured logging

**Status:** accepted risk.
`logging.basicConfig(stream=sys.stderr, …)` is in place (closing OBS-004).
JSON-structured logs with trace IDs are not justified for a stdio server. Revisit
if the server is ever lifted to a cloud/SSE deployment.

### SDK-002 — Type-hint coverage

**Status:** accepted risk.
Tool boundaries are fully typed via Pydantic. A few internal helpers still use
bare `dict`/`list` without parameterised types — polish, not a blocker.

### SDK-003 — `mcp[cli]` version cap

**Status:** accepted risk.
`mcp[cli]>=1.0.0` has no upper bound; a future SDK 2.x could break a routine
install. Tracked as a one-line maintenance fix.

### SEC-007 — Container sandboxing

**Status:** accepted risk.
No `Dockerfile`. Acceptable for local-stdio public-data servers — defense-in-depth
lives at the OS user level. Ship a hardened image if the deployment profile ever
moves to the cloud.

## Re-evaluation triggers

These acceptances should be revisited if the server ever:

- gains **write** capability or starts processing **PII**, or
- registers tools **dynamically** / from remote sources, or
- is moved to a **cloud / SSE** deployment (then OBS-003, SEC-007 and the
  network-binding checks become relevant), or
- is aggregated behind a shared MCP gateway (then implement gateway-level tool
  allow-listing and poisoning detection there).
