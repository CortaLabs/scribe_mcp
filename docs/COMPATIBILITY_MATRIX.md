# Compatibility Matrix

Baseline date: **2026-06-16**
Release framing: **v2.8.0.x compatibility baseline (current: 2.8.0.1)**

## Baseline contract

This baseline keeps compatibility posture for the 2.8.0.x refinement-sweep release line — currently `2.8.0.1`, a packaging patch on top of the 2.8.0 feature baseline (builds on 2.7.2 furnace-project quality-check performance, 2.7.1 latency, telemetry, and quality-governance). The 2.8.0.x line is a backward-compatible **additive + fix** line over 2.7.2 with **no breaking public API, CLI, or schema/data contract changes**. The 2.8.0 feature baseline bundles the completed `scribe_refinement_audit` sweep:

- **Host schema + case correctness:** host-facing `manage_docs` input-schema enrichment (live `action` enum sourced from the action manifest plus documented `metadata` sub-keys, `additionalProperties` preserved); unified bug/case status vocabulary (closure states such as `wontfix`/`duplicate` preserved consistently); exact (non-substring) case-path resolution that refuses to act on ambiguous matches.
- **Maintainability / honest envelopes:** removal of the dead cross-project search engine in `query_entries` (15 symbols; the file dropped from ~2,587 to ~1,868 lines) and dead self-healing paths in `utils/error_handler.py`. As part of this, `query_entries` now returns honest result envelopes on paths that were previously dead or silently misleading — see the named behavior change below.
- **read_file correctness + performance:** real pagination slicing and a single-pass AST structure visitor; the message-predicate is now pushed into SQL on both SQLite and Postgres (the headline performance fix) instead of being applied after the fact.
- **Reminder engine:** previously-dead reminder conditions wired live with category-keyed priority sorting, warm-rebind refresh, and configurable knobs.
- **Discoverability + onboarding:** rewritten `append_entry`/`health_check` tool descriptions; `manage_docs`/`read_file` docstrings that surface the full governance action set and `read_file` scan flags; a completed `/scribe-integration` skill and a new `/scribe-onboarding` install skill; new-project reminder hints that point to both skills.
- **Frontmatter preservation fix:** user-set managed-doc `title` is now preserved instead of being clobbered (tracked as BUG-2026-06-17-0002).
- **Packaging:** `asyncpg` is a core dependency, so a plain `pip install scribe-mcp` is Postgres-ready and matches the default Postgres runtime posture (the `[postgres]` extra is a redundant no-op alias kept only for explicit-intent convenience); plus plugin manifests; and the plugin + onboarding bundles **vendored into the wheel** (`src/scribe_mcp/plugins_bundle/**` and `src/scribe_mcp/onboarding/**` via package-data, with `resolve_codex_plugin_root()` preferring the packaged bundle) so `pip install scribe-mcp` works with no clone.

It continues to carry the prior in-line capabilities: fast same-binding `set_project` reuse, queryable tool runtime telemetry, append/read timing surfaces, physical/logical reconciliation diagnostics, managed-doc case-report path repairs, unified create contract with anchored sections payload, structured error remediation envelopes, session write-authority contract, logging-never-blocked healing, agent-ready quality-check output, Atlas bulk quality checks, and Scribe write-barrier safety:

- **Core package version:** `scribe-mcp==2.8.0.1` (packaging patch on the 2.8.0 feature baseline)
- **Default runtime posture:** Postgres-backed runtime contract
- **Standalone SQLite posture:** explicit local-only opt-in (`SCRIBE_MODE=standalone` + `SCRIBE_STORAGE_BACKEND=sqlite`)
- **Remote/client posture:** internal compatibility only, excluded by `SCRIBE_RELEASE_PROFILE=public`
- **Governed-memory posture:** project `CHANGELOG.md` is curated source; `.scribe/docs/GLOBAL_CHANGELOG.md` is derived output

`v3` is out of scope for this baseline.

## Supported combinations

| Core (`scribe-mcp`) | Status | Intended use |
| --- | --- | --- |
| `2.8.0.1` | Supported (current) | Current public Scribe install. Packaging patch on the 2.8.0 feature baseline: plugin bundles now ship the full Scribe skill set (not just `scribe-mcp-usage`'s `SKILL.md`), the no-op `[postgres]` extra messaging is clarified (`asyncpg` is already a core dependency), and a clean-room wheel install check is added. No feature, API, CLI, or schema changes over 2.8.0. |
| `2.8.0` | Supported (feature baseline) | Feature baseline for the 2.8.0.x line. Bundles the `scribe_refinement_audit` sweep: host-facing `manage_docs` input-schema enrichment, unified case-status vocabulary + exact case-path resolution, dead-code/honest-envelope maintainability cleanup, `read_file` pagination + single-pass AST + SQL-pushdown message filtering, a wired reminder engine, tool discoverability + onboarding skills, a managed-doc `title`-preservation fix, and packaging that vendors the plugin/onboarding bundles into the wheel. Backward-compatible additive + fix release; no breaking public API/CLI/schema contract. |
| `2.7.2` | Supported (previous) | Prior patch line with furnace-project quality-check O(N^2) elimination; 2.8.0.x is a drop-in upgrade with no breaking public API changes. |
| `2.7.1` | Supported (previous) | Earlier patch line; superseded by 2.7.2 and 2.8.0. |

## Notable behavior change in 2.8.0 (non-breaking)

One behavior change is worth naming explicitly because it changes a return value rather than only adding capability:

- **`query_entries` with a non-project `search_scope` now returns an honest `ok: false` teaching error** instead of a silent no-op. That cross-project search engine path was dead/broken, so prior "success" responses could be empty or misleading. This is a correctness fix (honest envelope), not a removal of a working contract: project-scoped `query_entries` behavior is unchanged, and emergency/degraded paths likewise return honest `ok: false` envelopes rather than fabricated rows. No public API/CLI/schema contract is broken.

## Not supported by this baseline

| Combination / practice | Status | Why |
| --- | --- | --- |
| Public onboarding that treats remote/client as generally available | Unsupported | Public release profile fail-closes remote/client startup. |
| Standalone SQLite presented as default runtime posture | Unsupported | Runtime settings default storage backend to Postgres. |
| Guidance that depends on repo-local/operator files as public setup | Unsupported | Those files are local convenience, not release contract. |
| Unversioned or mixed versions outside the baseline above | Not signed off | This baseline only certifies the combinations listed in this document. |

## What is shipped

### `scribe-mcp 2.7.2`

2.7.2 adds furnace-project quality-check O(N^2) elimination: per-inline-span line-number computation replaced with a precomputed line-offset index + bisect; `offset_in_scope` linear scan replaced with per-kind sorted interval index + bisect. Measured: 18,867-line PHASE_PLAN quality check 18.0s → 1.15s; furnace `set_project` ~20.3s → ~2.1s. Also in this line: `read_recent` limit/n returns exactly the requested row count; progress-log supplementation gated for DB-authoritative projects; readiness doc-quality cache key is O(1) via directory-stat sentinel; `count_entries()` uses the scribe_metrics counter as an O(1) fast path; session-binding lookups cached; research-index rglob hoisted out of per-doc loop.

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
