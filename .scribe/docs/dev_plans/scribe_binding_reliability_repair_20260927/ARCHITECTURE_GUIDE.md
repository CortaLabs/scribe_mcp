---
id: scribe_binding_reliability_repair_20260927-architecture
title: "Scribe Binding Reliability Release \u2014 Architecture Guide"
doc_type: architecture
doc_name: architecture
category: engineering
status: ready
version: '0.1'
last_updated: 2026-09-27 08:04:43 UTC
maintained_by: agent-20260927-075853-7092bc31
created_by: agent-20260927-061418-642053d3
owners:
- Blueprint
related_docs: []
tags:
- binding
- reliability
- architecture
- scribe-2.15.0
summary: DA-01 ownership blocker removed; remote-backend regression reassigned to
  SS-09/DA-09
canonical_doc_type: architecture
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 06:24:25 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-09-27 08:04:43 UTC
  last_edited_by: agent-20260927-075853-7092bc31
  last_action: apply_patch
  work_item_id: 6436d1cb-6834-4316-9ecc-678cd7890028
---
# Scribe Binding Reliability Release — Architecture Guide

**Author:** Blueprint
**Version:** 2.15.0 plan
**Status:** Ready
**Accepted source:** `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`

This guide projects the accepted Meta-Architect decomposition. It freezes boundaries, contracts, budgets, and dependency order; fresh `MODE=detail` passes own implementation-package design.

**SBR-ARCH-AMEND-REMOTE-08:** DA-01 source inspection found that `tests/test_remote_backend.py::TestSessionMethods` still requires `set/get_session_project` to remain in memory and avoid HTTP. The amendment assigns that whole test file to SS-09/DA-09 validation ownership so it can be reconciled with durable C-01/C-05 semantics; SS-01 retains sole ownership of the production remote transport.

## Problem and accepted scope
<!-- ID: problem_statement -->

The release repairs recurring caller-session binding loss, explicit cross-repository targeting, typed MCP errors, startup/import/schema weight, hot-path duplication, durable background work, managed-document replay, and concurrency validation as one standalone Scribe `2.15.0` source release.

Success means a caller binds its default once, explicit authorized targets never mutate that default, all foreground and receipt-producing operations respect the frozen budgets, 32 same-label sessions remain isolated, and the same source revision passes core plus reference-profile gates before public release surfaces change.

## Frozen invariants and non-goals
<!-- ID: requirements_constraints -->

- `set_project` selects one caller-session default; an unchanged rebind is idempotent and performs no persistent write.
- `ProjectTargetV1` may select any authorized registered project, including another repository, without mutating the caller default.
- Agent/persona labels are attribution only; caller-session identity is the binding and partition axis.
- Required validation uses at least 32 concurrent same-label caller sessions and proves zero cross-session, cross-project, and cross-repository interference.
- Authority, validation, idempotency reservation, capacity admission, and authoritative local durability remain foreground.
- Heavy work returns a durable receipt only after bounded admission and authoritative receipt persistence.
- The release boundary is one SemVer `2.15.0` source release, one governed source-release commit, and one PR after all gates pass.
- Council/Aegis/work-item/provider-seat/spawn/projection/process policy, generated Council surfaces, deployment, publication, runtime restart/adoption, and production credentials are outside this Scribe architecture.
- No second binding system, queue, receipt store, document mutation engine, replay oracle, or metrics source may be created.

## Accepted decomposition
<!-- ID: architecture_overview -->

| Subsystem | Responsibility | Contracts produced | Depends on | Detail pass |
|---|---|---|---|---|
| SS-01 | Durable caller-session defaults and cross-backend binding storage | C-01, C-05 | none | DA-01 |
| SS-06 | Durable receipt models, atomic admission/accounting, idempotency, leases/fencing, persistence | C-06, C-08 | none | DA-06 |
| SS-02 | Request-local target resolution, immutable context, binding receipt, typed MCP errors | C-02, C-03, C-04, C-11, C-16 | SS-01 | DA-02 |
| SS-04 | Fingerprint fast path, elected schema bootstrap, bounded readiness, migration 007 | C-07 | SS-01, SS-06 | DA-04 |
| SS-05 | Single resolved context on the hot path and correlated timing | C-12 | SS-02 | DA-05 |
| SS-07 | Partitioned fair scheduler, workers, recovery, cancellation, shutdown/drain | C-09 | SS-06 | DA-07 |
| SS-03 | Lightweight imports, core-ready semantics, optional-service readiness | C-10 | SS-04, SS-07 | DA-03 |
| SS-08 | Generation-safe managed-document mutation receipts and replay | C-13 | SS-02, SS-06, SS-07 | DA-08 |
| SS-09 | Deterministic 32-session core correctness, exact-effects validation, and remote-backend durable binding regression coverage | C-14 | SS-01, SS-02, SS-05, SS-06, SS-07, SS-08 | DA-09 |
| SS-10 | PostgreSQL/process stress, adapter parity, performance budgets, release evidence | C-15 | SS-03, SS-04, SS-05, SS-09 | DA-10 |
| SS-11 | Version and public release truth | none | SS-10 | DA-11 |

Topological layers are frozen as `[{SS-01,SS-06}, {SS-02,SS-04}, {SS-05,SS-07}, {SS-03,SS-08}, {SS-09}, {SS-10}, {SS-11}]`. Detail concurrency is at most three; this plan uses at most two assignments per layer.

## Frozen contracts C-01 through C-16
<!-- ID: detailed_design -->

All contracts are frozen. A source conflict requires a SEAM_MAP amendment; it is not a decision for Forge or a detail pass.

| ID | Producer → consumers | Frozen surface |
|---|---|---|
| C-01 `SessionBindingStoreV2` | SS-01 → SS-02, SS-09 | `SessionBindingRecordV2(caller_session_key_hash, project_key, project_name, canonical_repo_root, binding_generation, updated_at)`; `set_session_project(session_id, project_key, expected_generation=None)` and `get_session_project(session_id)`; generation changes only when the default changes. |
| C-02 `ProjectTargetV1` / `ResolvedProjectTargetV1` | SS-02 → SS-05, SS-08, SS-09, external Council | Optional `project_key`, `project`, `repo_root`; precedence is key, name+root, unique name, then caller default only when no explicit target; explicit resolution never writes the default. |
| C-03 `BindingReceiptV1` | SS-02 → SS-08, SS-09, external Council | `ok`, caller-session hash, project key/name/root, generation, reuse/write flags, resolution source, correlation ID. |
| C-04 `ScribeErrorV1` | SS-02 → SS-05, SS-08, SS-09, external Council | `CallToolResult(isError=true)` with `{ok:false,error_code,message,retryable,target,candidates,remediation,correlation_id}` and the accepted binding/project/document/busy/shutdown/fence code family. |
| C-05 binding schema delta | SS-01 → SS-04 | Migration 007 persists `project_key` and `binding_generation`; `project_name` remains display/compatibility only; caller session key stays unique authority. |
| C-06 background receipt schema delta | SS-06 → SS-04 | Migration 007 and SQLite baseline persist operation, canonical project, lane, idempotency/digest/bytes/durability, state/version/attempt/retry, lease/fence, cancellation, result/error, and timestamps; uniqueness is project key plus idempotency key with atomic digest conflict detection. |
| C-07 `SchemaReadinessV1` | SS-04 → SS-03, SS-10 | `ensure_schema_ready(deadline_ms)` returns fingerprint, migration version, bootstrap role, wait, ready, error, retryability; one elected bootstrapper runs DDL and peers wait boundedly. |
| C-08 `BackgroundReceiptStoreV1` | SS-06 → SS-07, SS-08, SS-09 | Atomic `admit`, `get`, `claim`, `transition`, and `recover`; item and serialized-byte limits include ready, retry-wait, and leased work. |
| C-09 `BackgroundJobServiceV1` | SS-07 → SS-03, SS-08, SS-09 | `submit`, `get_status`, `cancel`, `start`, and bounded `stop`; canonical project partitions, control/durable/heavy lanes, caps, deficit round robin, finite seeded retry, leases/fencing, restart recovery. |
| C-10 `ServiceStateV1` | SS-03 → SS-10 | Service state, core-readiness requirement, last error/transition, startup phase timing; optional remote/plugin/bridge services cannot block core-ready. |
| C-11 `ResolvedRequestContextV1` | SS-02 → SS-05, SS-08, SS-09 | Immutable caller-session hash, resolved target, default generation, attribution, correlation, mode, and authority evidence; created once and passed without re-resolution. |
| C-12 `CallTimingEnvelopeV2` | SS-05 → SS-09, SS-10 | Correlated ingress, binding/project reads, target/mode resolution, body, authority/durability/receipt, hooks, formatting/audit/egress, unaccounted, total, ratio, slow stages, and tripwire fields. |
| C-13 `DocumentMutationReceiptV1` | SS-08 → SS-09 | Operation/project/session/generation/document/path/digest fields and accepted/applied/duplicate/conflict/terminal/cancelled states; replay re-resolves project and compares binding plus document generations. |
| C-14 `SwarmResultsV1` | SS-09 → SS-10 | One JSON source with revision, seed, topology, bind count, operation ledger, oracle cardinalities, queue metrics, timings, faults, teardown, and verdict; Markdown is derived. |
| C-15 `ReliabilityReleaseEvidenceV1` | SS-10 → SS-11 | Same-revision core, PostgreSQL, adapter, import, startup, and queue verdicts plus artifact paths, commands, environment fingerprint, and target version `2.15.0`; every verdict must pass. |
| C-16 external Council adapter | SS-02 → `external:council_mcp/Atlas` | Host supplies only verified caller-session key, optional target, and generic attribution; bind once and retain C-03; later explicit calls use C-02/C-04 without rebind/default mutation; live binding truth requires a real receipt or direct Scribe readback. |

## Source ownership boundary
<!-- ID: directory_structure -->

The accepted map owns 59 physical Scribe files through 63 disjoint path entries. Three shared files use exact symbol anchors only:

- `src/scribe_mcp/storage/base.py`: `#session_binding_contract` versus `#background_receipt_contract`.
- `src/scribe_mcp/storage/postgres/__init__.py`: `#session_binding_storage`, `#setup_fast_path`, and `#background_receipt_storage`.
- `src/scribe_mcp/server.py`: `#startup_ready` versus `#background_lifecycle`.

`src/scribe_mcp/storage/remote.py#session_binding_transport` remains an SS-01/DA-01 production path. `tests/test_remote_backend.py` is now a whole-file SS-09/DA-09 validation path; it consumes C-01/C-05 behavior and does not share production ownership.

`src/scribe_mcp/storage/sqlite/schema.py#background_receipt_schema`, `src/scribe_mcp/db/init.sql#reliability_receipt_schema`, and `src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks` are single-owner sub-file boundaries. A detail pass needing another anchor stops for a map amendment.

SS-09/DA-09 now has seven paths and is `SPLIT_REQUIRED`: its detail pass must isolate the remote-backend durability regression into an independently verifiable task package. Every other subsystem and assignment remains at or below six paths.

## Storage and durability model
<!-- ID: data_storage -->

Caller defaults are durable, caller-session-keyed, generation-bearing records. Explicit targets resolve from registered project identity and canonical root without default mutation. Background admission commits a durable receipt before response, accounts item and byte capacity atomically, and uses leases plus fencing for recovery. Managed-document replay reuses the existing apply-preview, atomic-write, anchor-CAS, and WAL primitives and checks both binding and document generations before effect.

## Frozen performance and correctness budgets
<!-- ID: testing_strategy -->

- Warm unchanged default bind: p95 ≤150 ms, p99 ≤300 ms, zero persistent writes, no inventory/document generation.
- Explicit local-database target resolution: p95 ≤200 ms; default unchanged.
- Fresh server import: warm p95 ≤1.0 s, cold p95 ≤1.5 s; ready RSS ≤64 MiB; all-tools steady RSS ≤80 MiB.
- Process-to-ready: warm p95 ≤1.5 s, cold p95 ≤2.5 s; optional object-store outage adds ≤50 ms and never blocks core/local logging.
- Warm storage setup p95 ≤100 ms; 32 simultaneous starts perform one bootstrap; non-bootstrap wait ≤500 ms.
- Foreground read target: p50 ≤75 ms, p95 ≤250 ms. Durable append/receipt acknowledgement and every synchronous foreground class: p95 ≤500 ms.
- Every stage above 100 ms and every total above 500 ms emits correlated evidence; accounted timing is at least 95% of server-observed duration.
- Each call performs at most one durable binding read and one project-record read.
- Under 32 callers, wrong target/default drift/cross-talk/lost accepted work/duplicate effect/stale fence/unreconciled recovery counts are zero.
- No continuously eligible project starves for 5 seconds; configured item/byte/concurrency bounds never exceed; no equal-weight project exceeds 50% while a peer is eligible; equal-capacity worker claim counts differ by at most one.

Core validation uses deterministic clocks/events, canonical `test_agent`, disposable state, real scheduler/receipt code, the one shared exact-effects oracle, targeted neighbor tests, and import smoke. The single repository-saturating PostgreSQL/process lane runs only after core gates.

## Release and operations boundary
<!-- ID: deployment_operations -->

The architecture authorizes source planning and validation only. DA-11 may update version/public truth after C-15 passes for the same revision. Deployment, package publication, runtime restart/adoption, production credentials, and a `main` merge remain outside this plan and require their own authority.

## Detail-pass handoff rule
<!-- ID: open_questions -->

There are no negotiable contracts or open architecture questions. The DA-01 execution blocker is removed: DA-01 proceeds on its six SS-01 production paths without owning or editing `tests/test_remote_backend.py`; DA-09 owns that regression file and must split its seven-path assignment into bounded packages.

Each fresh `MODE=detail` pass reads only its accepted subsystem card and frozen inputs, authors bounded task packages under its declared PHASE_PLAN anchor and CHECKLIST prefix, and stops if it needs an unowned path, a changed contract, or a package larger than six files/one coherent behavior. C-01 and C-05 are unchanged.

## Evidence references
<!-- ID: references_appendix -->

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` — accepted decomposition and I1–I6 evidence.
- `research/RESEARCH_BINDING_RCA.md` — recurring binding/error RCA and standalone boundary.
- `research/RESEARCH_BINDING_EFFICIENCY_AND_OWNERSHIP.md` — measured bind costs and ownership.
- `research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` — import/startup/RSS/hot-path evidence.
- `research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md` — 32-session exact-effects validation design.
- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` — durable receipt, bounded fairness, recovery, cancellation, and shutdown validation.
