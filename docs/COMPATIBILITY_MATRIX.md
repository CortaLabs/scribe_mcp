# Compatibility Matrix

Baseline date: **2026-06-16**
Release framing: **v2.7.1 compatibility baseline**

## Baseline contract

This baseline keeps compatibility posture for the 2.7.1 latency, telemetry, and quality-governance release line: fast same-binding `set_project` reuse, queryable tool runtime telemetry, append/read timing surfaces, physical/logical reconciliation diagnostics, managed-doc case-report path repairs, unified create contract with anchored sections payload, structured error remediation envelopes, session write-authority contract, logging-never-blocked healing, agent-ready quality-check output, Atlas bulk quality checks, and Scribe write-barrier safety:

- **Core package version:** `scribe-mcp==2.7.1`
- **Default runtime posture:** Postgres-backed runtime contract
- **Standalone SQLite posture:** explicit local-only opt-in (`SCRIBE_MODE=standalone` + `SCRIBE_STORAGE_BACKEND=sqlite`)
- **Remote/client posture:** internal compatibility only, excluded by `SCRIBE_RELEASE_PROFILE=public`
- **Governed-memory posture:** project `CHANGELOG.md` is curated source; `.scribe/docs/GLOBAL_CHANGELOG.md` is derived output

`v3` is out of scope for this baseline.

## Supported combinations

| Core (`scribe-mcp`) | Status | Intended use |
| --- | --- | --- |
| `2.7.1` | Supported | Public Scribe install for local/core usage with faster repeated project binding, queryable runtime telemetry, deterministic document topology, agent-ready quality checks, write-barrier safety, and first-class bug/security report follow-up editing. |

## Not supported by this baseline

| Combination / practice | Status | Why |
| --- | --- | --- |
| Public onboarding that treats remote/client as generally available | Unsupported | Public release profile fail-closes remote/client startup. |
| Standalone SQLite presented as default runtime posture | Unsupported | Runtime settings default storage backend to Postgres. |
| Guidance that depends on repo-local/operator files as public setup | Unsupported | Those files are local convenience, not release contract. |
| Unversioned or mixed versions outside the baseline above | Not signed off | This baseline only certifies the combinations listed in this document. |

## What is shipped

### `scribe-mcp 2.7.1`

- CLI entry points include: `scribe`, `scribe-mcp`, `scribe-server`, `scribe-server-sse`
- Core runtime and tool surface in `src/scribe_mcp/**`
- Repeated same-session `set_project` calls for the same agent/project/root use a strict reuse path and expose `side_effects.binding_reused` instead of rewriting project/session/doc state; structured/compact reuse responses skip post-bind reminder refresh because no binding mutation occurred.
- Runtime telemetry persists durations, correlation IDs, measurement scope, and repo root across file and SQL tool-call sinks.
- `append_entry` returns phase timing for file WAL append, DB mirror work, state/reminder work, formatting, and total latency.
- Probe tooling supports JSON output, same-server root comparisons, and background telemetry draining so local proof does not leave asyncpg shutdown warnings.
- Diagnostics include physical/logical reconciliation for fresh DB installs with existing file-backed Scribe artifacts.
- Managed-doc hygiene includes scaffold-aware quality checks, project-local preflight archive routing, canonical research artifact naming, stale index-backup cleanup, and quality-check recovery for registered or discoverable package/research docs.
- Managed-doc project memory includes project `CHANGELOG.md`, derived global changelog reconciliation, advisory version context, research-context drift warnings, lifecycle/body-status mismatch warnings, and malformed changelog escaped-newline blocking checks.
- Managed-doc release governance also blocks missing accepted coverage for the active `pyproject.toml` version via `SCF_CHANGELOG_CURRENT_VERSION_MISSING` in `quality_check`, reminders, and `project_health`.
- Managed-doc quality output includes grouped warning families, ranked agent actions, body/file location mapping, nearest-section context, repair kind, edit-action hints, deterministic provenance, and additive handoff actions.
- Bulk quality mode checks all managed readiness docs or an explicit `doc_names` wave using the existing `quality_check` contract, with compact controls for clean docs, warnings, document caps, and action caps.
- Managed-doc topology includes canonical metadata normalization, typed deterministic edges, topology/metadata scan actions, safe/assisted metadata repair, stale cleanup recommendations, hard quality handoff checks, and sanitized downstream ingestion manifest inspection.
- Bug and security case tooling returns managed follow-up handles, `manage_docs` resolves governed bug/security reports by case id, governed path, explicit report path, or canonical category metadata before applying edits, and `link_fix` closes shared registry rows for resolved fix statuses.
- Scribe mutation surfaces fail closed while a Scribe-owned write barrier is active, and Postgres backup/restore helpers enforce owner-only custody before producing or consuming migration material.
- Exported remote transport blocks local operator-only tools unless their metadata explicitly declares remote invocation support.
- `read_recent` supplements sparse Postgres rows from the canonical progress log on the first page when the DB mirror is incomplete.
- Derived topology artifacts are local Scribe outputs under `.scribe/indexes/`; downstream consumers may ingest those sanitized records, but Scribe does not implement embeddings, semantic ranking, retrieval, or graph-RAG traversal.

## Versioning contract

- `main` is release-bound for `scribe-mcp`: pushes that touch package/release surfaces trigger the PyPI publish workflow.
- Any release-bound change must bump `pyproject.toml` before merge/push to `main`.

## Public boundary summary

- Public install/setup guidance must map to shipped package files and tracked docs.
- Local/operator overlays are never release truth.
- This baseline is intentionally conservative: compatibility first, breaking changes deferred.
