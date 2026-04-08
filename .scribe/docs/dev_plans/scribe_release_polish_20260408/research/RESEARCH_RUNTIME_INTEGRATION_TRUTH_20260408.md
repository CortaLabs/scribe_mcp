---
id: scribe_release_polish_20260408-research-runtime-integration-truth-20260408
title: "\U0001F52C Council\u2194Scribe runtime split and deployment truth audit \u2014\
  \ scribe_release_polish_20260408"
doc_type: RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408
doc_name: RESEARCH_RUNTIME_INTEGRATION_TRUTH_20260408
category: engineering
status: draft
version: '0.1'
last_updated: 2026-04-08 02:41:39 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Council↔Scribe runtime split and deployment truth audit — scribe_release_polish_20260408
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-04-08 02:16:42 UTC

> This document captures the runtime and deployment boundary between Scribe boot behavior, client-side remote configuration, and Council-exported bootstrap artifacts so downstream stages do not confuse packaging with runtime truth.

---
## Executive Summary
<!-- ID: executive_summary -->
Scribe’s runtime truth is split across three separate contracts that must not be conflated:
- Runtime boot: `scribe-server` / `scribe-mcp` launch the default local stdio server, and `scribe-server-sse` is the optional authenticated HTTP/SSE path.
- Client configuration: `SCRIBE_REMOTE_URL` + `SCRIBE_REMOTE_AUTH_TOKEN` describe an optional remote/client posture, not the default boot path.
- Exported bootstrap config: Council-side export tooling generates `.mcp.json` / `.codex/config.toml` for installed-package consumers; those files are bootstrap artifacts, not Scribe runtime truth.

The practical conclusion is that the release-safe story for Scribe starts with local stdio, adds package-first entrypoints, then optionally supports authenticated SSE or remote/client consumption. Council export output remains a consumer bootstrap layer, not a source of runtime behavior.
<!-- ID: research_scope -->
**Research Lead:** scribe-research-analyst

**Investigation Window:** 2026-04-08

**Focus Areas:**
- Verify the default boot path and package entrypoints in `README.md`, `pyproject.toml`, and `src/scribe_mcp/__main__.py`.
- Confirm the server and transport split in `src/scribe_mcp/server.py` and `src/scribe_mcp/server_sse.py`.
- Distinguish remote/client configuration from runtime boot in `src/scribe_mcp/config/settings.py` and `docs/REMOTE_CLIENT.md`.
- Validate release-safe bootstrap guidance in `docs/RELEASE_SURFACE.md`, `docs/RELEASE_FILE_MAP.md`, `docs/examples/*.example`, and `deploy/README.md`.
- Cross-check Council export behavior against `.scribe/docs/dev_plans/dataset_foundry_mcp_parity_2026/research/RESEARCH_council_mcp_export.md`.

**Dependencies & Constraints:**
- Treat Council export output as consumer bootstrap only, not as proof of Scribe runtime semantics.
- Prefer tracked examples under `docs/examples/` over repo-root overlay files when documenting client setup.
- Keep server-side transport auth distinct from client-side remote auth so operators do not collapse the two posture models.
<!-- ID: findings -->
### Finding 1
- **Summary:** Scribe runtime boot, client configuration, and Council export are three distinct contracts that must not be conflated.
- **Evidence:** `README.md:18-99`, `pyproject.toml:31-41`, `src/scribe_mcp/__main__.py:1-58`, `src/scribe_mcp/server.py:196-248`, `src/scribe_mcp/server.py:1140-1176`, `src/scribe_mcp/server_sse.py:60-124`, `docs/RELEASE_SURFACE.md:1-18`, and `.scribe/docs/dev_plans/dataset_foundry_mcp_parity_2026/research/RESEARCH_council_mcp_export.md:27-60`, `:110-170`.
- **Confidence:** High

### Finding 2
- **Summary:** The release-safe public story is local/core stdio default, installed-package stdio entrypoints, optional authenticated SSE, optional remote/client posture, and no unsupported unauthenticated public exposure.
- **Evidence:** `README.md:60-75`, `src/scribe_mcp/__main__.py:1-8`, `docs/RELEASE_FILE_MAP.md:35-58`, `src/scribe_mcp/server_sse.py:60-124`, `src/scribe_mcp/server_sse.py:422-538`, `docs/REMOTE_CLIENT.md:1-48`, `src/scribe_mcp/config/settings.py:447-451`, and `deploy/README.md:20-95`.
- **Confidence:** High

### Finding 3
- **Summary:** Naming drift exists around transport/auth labels, but it is documentation-level contract drift rather than a runtime defect.
- **Evidence:** `src/scribe_mcp/config/settings.py:362-365`, `src/scribe_mcp/config/settings.py:447-451`, `docs/REMOTE_CLIENT.md:1-48`, `README.md:60-75`, `src/scribe_mcp/__main__.py:1-58`, `install.sh:13-34`, `src/scribe_mcp/cli/main.py:1-120`, `src/scribe_mcp/cli/main.py:270-552`, `docs/RELEASE_SURFACE.md:5-35`, and `docs/RELEASE_FILE_MAP.md:89-118`.
- **Confidence:** High

### Additional Notes
- The code paths are already coherent; the remaining gap is explicit operator-facing vocabulary and one cross-reference table that maps the runtime and client names into a single posture matrix.
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- The runtime entrypoints are intentionally split: `src/scribe_mcp/__main__.py` drives the package/server launch path, `src/scribe_mcp/server.py` owns the default stdio server, and `src/scribe_mcp/server_sse.py` owns the optional SSE transport.
- Configuration handling keeps transport auth and remote/client auth separate in `src/scribe_mcp/config/settings.py`, which is the right runtime shape even though the docs still need a clearer operator-facing naming table.
- The CLI dispatcher in `src/scribe_mcp/cli/main.py` is a separate tool surface, not a synonym for the server runtime, so release docs must avoid collapsing those names.

**System Interactions:**
- Release-facing docs, tracked examples, and deployment guidance all describe the same runtime split from different angles: local stdio by default, optional authenticated SSE, and optional remote/client use when the operator explicitly deploys that posture.
- Council export tooling sits beside that runtime contract and generates consumer bootstrap artifacts; it does not define Scribe server behavior.
- The release-safe examples under `docs/examples/` and the surface maps in `docs/RELEASE_SURFACE.md` / `docs/RELEASE_FILE_MAP.md` are the correct documentation anchors for packaging and bootstrap instructions.

**Risk Assessment:**
- Primary risk: operator confusion from overlapping labels (`scribe-server`, `scribe-server-sse`, `--transport sse`, `SCRIBE_TRANSPORT_AUTH_TOKEN`, `SCRIBE_REMOTE_AUTH_TOKEN`) that could lead to incorrect bootstrap or mistaken assumptions about public exposure.
- Secondary risk: future Council-side export changes could be misread as runtime changes unless the docs keep the bootstrap/runtime distinction explicit.
- Mitigation: keep the runtime/export split and auth-token split explicit in release docs and add one canonical posture table for operators.
<!-- ID: recommendations -->
### Immediate Next Steps
- Publish one operator-facing naming table that maps `scribe-server`, `scribe-server-sse`, `--transport sse`, `SCRIBE_TRANSPORT_AUTH_TOKEN`, and `SCRIBE_REMOTE_AUTH_TOKEN` into a single posture matrix.
- Keep the public Scribe story in this order: local/core stdio default, package-first installed entrypoints, optional authenticated SSE server, optional remote/client posture.
- Continue to point users at tracked examples under `docs/examples/` rather than repo-root overlay files for release-safe bootstrap instructions.

### Long-Term Opportunities
- Fold the runtime/export distinction into a short cross-reference paragraph in the release docs so future Council-side export changes cannot be mistaken for runtime semantics.
- Revisit the documentation vocabulary around server-side versus client-side auth tokens if additional transport modes are added.
<!-- ID: appendix -->
- **References:** `README.md`, `pyproject.toml`, `src/scribe_mcp/__main__.py`, `src/scribe_mcp/server.py`, `src/scribe_mcp/server_sse.py`, `src/scribe_mcp/config/settings.py`, `src/scribe_mcp/cli/main.py`, `docs/RELEASE_SURFACE.md`, `docs/RELEASE_FILE_MAP.md`, `docs/REMOTE_CLIENT.md`, `docs/examples/mcp.json.example`, `docs/examples/opencode.json.example`, `deploy/README.md`, and `.scribe/docs/dev_plans/dataset_foundry_mcp_parity_2026/research/RESEARCH_council_mcp_export.md`.
- **Attachments:** None. The evidence is fully captured in the cited source files and the later sections of this report.
<!-- ID: summary -->
# Summary
Scribe has three distinct truths that must not be conflated: runtime boot, client configuration, and exported bootstrap config.

- **Runtime boot**: `scribe-server` / `scribe-mcp` boot the local stdio server by default, while `scribe-server-sse` is the optional HTTP/SSE server path.
- **Client configuration**: `SCRIBE_REMOTE_URL` + `SCRIBE_REMOTE_AUTH_TOKEN` describe the optional remote/client posture, not the stdio boot path.
- **Exported config**: Council-side export tooling generates `.mcp.json` / `.codex/config.toml` for installed-package consumers; it is a bootstrap artifact, not the Scribe runtime contract.

Confidence: high. Evidence comes from `README.md:18-99`, `pyproject.toml:31-41`, `src/scribe_mcp/__main__.py:1-58`, `src/scribe_mcp/server.py:196-248`, `src/scribe_mcp/server.py:1140-1176`, `src/scribe_mcp/server_sse.py:60-124`, `docs/RELEASE_SURFACE.md:1-18`, and the Council export research at `.scribe/docs/dev_plans/dataset_foundry_mcp_parity_2026/research/RESEARCH_council_mcp_export.md:27-60` and `:110-170`.

<!-- ID: supported_modes -->
# Supported Modes and Intended Audience

| Mode | Intended audience | What it is | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| Local/core stdio | Normal local users and downstream integrators | Default public posture; runs the MCP server over stdin/stdout | `README.md:60-75`, `src/scribe_mcp/__main__.py:1-8`, `src/scribe_mcp/server.py:1140-1176` | High |
| Installed-package stdio entrypoints | Operators and packaging consumers | `scribe`, `scribe-mcp`, and `scribe-server` are package entrypoints that launch the shipped package, not repo-relative scripts | `pyproject.toml:31-41`, `docs/RELEASE_FILE_MAP.md:35-58` | High |
| Optional SSE server | Managed deployment operators | HTTP/SSE server with required auth token and loopback-safe default binding unless explicitly overridden | `src/scribe_mcp/__main__.py:1-8`, `src/scribe_mcp/server_sse.py:60-124`, `src/scribe_mcp/server_sse.py:422-538`, `deploy/README.md:20-95` | High |
| Optional remote/client posture | Client-side consumers connecting to a remote Scribe service | Uses `SCRIBE_REMOTE_URL` and `SCRIBE_REMOTE_AUTH_TOKEN`; not the default public story | `README.md:60-75`, `docs/REMOTE_CLIENT.md:1-48`, `src/scribe_mcp/config/settings.py:447-451` | High |
| Casual public exposure | Nobody; explicitly unsupported | Publicly reachable unauthenticated deployment | `README.md:60-75`, `docs/REMOTE_CLIENT.md:26-48`, `deploy/README.md:20-95` | High |

The operator-facing message is: Scribe is a local server by default, can be installed as a package-first stdio runtime, can optionally expose an authenticated SSE server, and can optionally be consumed through a remote/client configuration when the operator explicitly deploys that posture.

<!-- ID: contract_split -->
# Export vs Runtime Contract

Council export config and Scribe runtime boot are separate contracts.

- The Council export research shows `council mcp export` writes bootstrap config for the active council only, includes only enabled `project` and `council` scoped servers, and excludes local servers and other councils’ records. That means export output is for consumer bootstrap, not a runtime truth source. Confidence: high. Evidence: `.scribe/docs/dev_plans/dataset_foundry_mcp_parity_2026/research/RESEARCH_council_mcp_export.md:27-60` and `:110-170`.
- Scribe’s public docs reinforce that repo-root overlays are not release truth; tracked examples under `docs/examples/` are the release-safe client bootstrap files. Confidence: high. Evidence: `docs/RELEASE_SURFACE.md:5-18` and `:25-35`, plus `docs/RELEASE_FILE_MAP.md:75-118`.
- The shipped example config for local/core bootstrap uses the installed `scribe-server` command and Scribe state env vars, which is the package-first stdio contract downstream integrators should expect. Confidence: high. Evidence: `docs/examples/mcp.json.example:1-12` and `docs/examples/opencode.json.example:1-21`.
- The release file map marks `src/scribe_mcp/__main__.py` as the installed CLI/server entry target and `src/scribe_mcp/server_sse.py` as the SSE transport entry point, which matches the runtime split in code. Confidence: high. Evidence: `docs/RELEASE_FILE_MAP.md:35-58`.

Bottom line: export/client configuration is a bootstrap artifact for consumers, while stdio/SSE boot behavior is the runtime contract implemented by Scribe itself.

<!-- ID: naming_drift -->
# Naming and Contract Drift

The implementation is coherent, but several names still blur the boundary between boot semantics, client config, and packaging.

- **Server-side vs client-side auth token names are split across docs and settings.** `Settings.load()` treats `SCRIBE_TRANSPORT_AUTH_TOKEN` / `SCRIBE_AUTH_TOKEN` as the server-side transport auth token, while `SCRIBE_REMOTE_AUTH_TOKEN` is the canonical client-side variable and still aliases the transport names for single-environment setups. That is workable, but it must be labeled explicitly or downstream users will assume the same variable drives both sides. Confidence: high. Evidence: `src/scribe_mcp/config/settings.py:362-365`, `src/scribe_mcp/config/settings.py:447-451`, `docs/REMOTE_CLIENT.md:1-48`, `README.md:60-75`.
- **The optional SSE posture has three names in circulation.** The code exposes `--transport sse`, the console script is `scribe-server-sse`, and `install.sh` offers a `trusted-sse` profile. These all point to the same optional HTTP/SSE capability, but they are different labels for operators to memorize. Confidence: high. Evidence: `src/scribe_mcp/__main__.py:1-58`, `pyproject.toml:31-41`, `install.sh:13-34`.
- **`scribe` is a CLI dispatcher, not the server process itself.** The CLI module is a universal tool runner with `call`, `session`, `tools`, `bootstrap`, and `plugins` subcommands. If docs use `scribe` casually, downstream integrators can confuse it with the server runtime. Confidence: high. Evidence: `src/scribe_mcp/cli/main.py:1-120` and `:270-552`.
- **Repo-root overlay files remain an easy trap.** `docs/RELEASE_SURFACE.md` and `docs/RELEASE_FILE_MAP.md` correctly say `.mcp.json`, `opencode.json`, `.claude/`, `.codex/`, and `.council/` are local overlays, but those names still appear in the repo and can be mistaken for shipped truth. Confidence: high. Evidence: `docs/RELEASE_SURFACE.md:5-35`, `docs/RELEASE_FILE_MAP.md:89-118`.

These are documentation/contract-label issues, not runtime defects.

<!-- ID: handoff -->
# Handoff Notes

What the next stage should preserve:

1. Keep the public Scribe story in this order: **local/core stdio default**, **package-first installed entrypoints**, **optional authenticated SSE server**, **optional remote/client posture**.
2. Treat `council mcp export` and similar config-generation paths as bootstrap artifacts for consumers, not as proof of how Scribe boots.
3. Keep the server/client token names separated in docs: server-side transport auth versus client-side remote auth.
4. Prefer tracked examples under `docs/examples/` over repo-root overlay files when documenting client setup.
5. If Council-side docs are revised later, keep the Scribe report aligned with the installed-package contract already frozen in the compatibility matrix.

Open gap: the repo would benefit from one explicit cross-reference paragraph that maps `scribe-server`, `scribe-server-sse`, `--transport sse`, `SCRIBE_TRANSPORT_AUTH_TOKEN`, and `SCRIBE_REMOTE_AUTH_TOKEN` into one naming table for operators. Confidence: medium. The underlying code is already consistent; the remaining issue is presentation clarity.
