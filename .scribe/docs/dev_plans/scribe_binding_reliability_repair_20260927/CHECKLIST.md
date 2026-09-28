---
id: scribe_binding_reliability_repair_20260927-checklist
title: "Scribe Binding Reliability Release \u2014 Planning Checklist"
doc_type: checklist
doc_name: checklist
category: engineering
status: in_progress
version: '0.1'
last_updated: 2026-09-28 17:02:41 UTC
maintained_by: agent-20260928-170236-294a8702
created_by: agent-20260927-061418-642053d3
owners:
- Blueprint
related_docs: []
tags:
- binding
- reliability
- checklist
- acceptance
summary: Planning synthesis complete; 39 implementation packages registered and execution/validation
  checklist remains active.
canonical_doc_type: checklist
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 06:24:36 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-09-28 17:02:41 UTC
  last_edited_by: agent-20260928-170236-294a8702
  last_action: replace_section
  work_item_id: 5309eca6-4d91-477e-b0c8-7087b6d65338
---
# Scribe Binding Reliability Release — Planning Checklist

**Author:** Blueprint
**Version:** 2.15.0 plan
**Status:** In Progress
**Accepted source:** `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`

Each assignment section is a stable custody region. Fresh `MODE=detail` passes replace the `.DETAIL` scaffold item with bounded package items that retain the declared prefix and remain inside the accepted ownership/contract boundary.

## DA-01 — Binding persistence (`SBR-BIND-PERSIST.*`)
<!-- ID: sbr-binding-persistence -->
- [x] `SBR-BIND-PERSIST.1` — Generation-bearing `SessionBindingRecordV2` exists with the frozen six fields; first generation is 1; C-05 migration input preserves session authority, backfills `project_key` plus generation, and leaves DDL to SS-04. | Proof: Council item c7e2047d completed at revision 3c747918 with 4/4 current receipts and no content drift.
- [ ] `SBR-BIND-PERSIST.2` — Abstract C-01 signatures return records; unchanged rebind is zero-write with stable timestamp/generation; stale `expected_generation` fails before a write. Current state: registry item 67c2e302 is completed, but all four receipts are content-stale because `base.py` changed after review. The post-review delta is the additive background-receipt interface block; keep unchecked until a current delta gate formalizes that non-overlap.
- [ ] `SBR-BIND-PERSIST.3` — PostgreSQL atomically proves first/change/no-op/stale-CAS behavior and isolates concurrent same-label callers by session ID; exact persisted project identity is returned.
- [ ] `SBR-BIND-PERSIST.4` — SQLite plus facade match PostgreSQL record, generation, zero-write, conflict, and concurrent same-label semantics without modifying schema ownership.
- [x] `SBR-BIND-PERSIST.5` — Remote delegates binding truth through durable transport and strictly decodes C-01 in source; `SBR-CORE-VAL.1` and `.5` retain mandatory swarm/parity/reconnect proof and the stale `tests/test_remote_backend.py` expectation update before release. | Proof: Council item 398c8030 completed at revision 34c8b74f with 4/4 current receipts and no content drift.
- [ ] `SBR-BIND-PERSIST.GATE` — DA-09 core swarm proves 32 concurrent same-label sessions, independent generations, zero cross-talk, and exact zero persistent writes on unchanged rebind; DA-10 reference lane proves live PostgreSQL/Remote parity; Sentinel and Arbiter PASS before SS-02 consumes C-01.
## DA-06 — Durable receipt store (`SBR-RECEIPT.*`)
<!-- ID: sbr-receipt-store -->

- [x] `SBR-RECEIPT.1` — Add the host-neutral `background/models.py`, `BackgroundReceiptStoreV1`, and `StorageBackend#background_receipt_contract`; prove exact C-08 signatures, closed states, outcome/version/fence invariants, fail-closed defaults, import/compile and existing-neighbor checks; DA-09/Crucible still owns the mandatory named contract test before release. | Proof: Council item 16a55120 completed at revision d48c8067 with 4/4 current receipts and no content drift.
- [ ] `SBR-RECEIPT.2` — Add SQLite receipt operations plus the `SQLiteStorage` adapter; after DA-04 C-06 lands, prove atomic global/per-project item+byte admission, duplicate/digest-conflict zero mutation, deterministic claim/CAS/fencing, terminal release once, reopen recovery, import smoke, and the named SQLite/neighbor tests.
- [ ] `SBR-RECEIPT.3` — Add the `PostgresStorage#background_receipt_storage` block; after DA-04 C-06 lands, prove transaction-safe capacity, idempotency races, `SKIP LOCKED` lease exclusivity, stale-fence/version rejection, restart recovery, normalized backend parity, import smoke, and the named PostgreSQL/neighbor tests.
- [ ] `SBR-RECEIPT.REVIEWS` — Before SS-06 handoff, record Crucible behavioral evidence and mandatory Sentinel plus Arbiter PASS for all three packages; no completion claim before the C-06 schema dependency and DA-09/DA-10 proof owners land.

## DA-02 — Target resolution and typed errors (`SBR-BIND-RESOLVE.*`)
<!-- ID: sbr-target-resolution -->

- [x] `SBR-BIND-RESOLVE.1` — Add frozen C-02/C-03/C-11 request, target, receipt, attribution, authorization-evidence, and immutable-context types in `execution_context.py`; prove raw-key non-disclosure, exact caller-session hashing, attribution-only labels, object identity preservation, import smoke, and the named DA-09/DA-10 contract tests. | Proof: Council item 6058f4c6 completed at revision 5a332102 with 4/4 current receipts and no content drift.
- [ ] `SBR-BIND-RESOLVE.2` — Add the single persisted-project C-02 resolver in `logging_utils.py` plus `StateManager#registered_target_resolution`; prove key → name+root → unique-name → default precedence, authorized cross-repo targeting without default mutation, deterministic ambiguity/root-mismatch/missing/wrong-target errors, zero effects, import smoke, and neighbor tests.
- [ ] `SBR-BIND-RESOLVE.3` — Make `set_project` the sole exact-session C-01 default writer and return C-03 for every successful format; prove first/change/unchanged generations, unchanged and stale-generation zero writes, receipt flags, no label/global authority, and the 05:57 trace-derived delayed second write after one bind without rebind.
- [ ] `SBR-BIND-RESOLVE.4` — Integrate one C-02 resolution and one immutable C-11 in `tool_runtime.py`, plus C-04 normalization in `mcp_adapter.py`; prove structured `isError=true` parity, generic C-16 bind-once/external-adapter behavior, same-handle reconnect, same-label new-handle isolation, ambiguity/stale-generation/wrong-target denials, and no Council source vocabulary.
- [ ] `SBR-BIND-RESOLVE.REVIEWS` — DA-09 records the deterministic 32 same-label sessions × 100 mixed calls oracle with zero wrong target/default drift/cross-talk/duplicate/untyped effects; DA-10 records modern/legacy adapter/process parity; Sentinel and Arbiter PASS all four packages before downstream consumers use C-02/C-03/C-04/C-11/C-16.

## DA-04 — Schema bootstrap (`SBR-SCHEMA.*`)
<!-- ID: sbr-schema-bootstrap -->
- [x] SBR-SCHEMA.1 — Add the sole additive 007_reliability_receipts PostgreSQL migration source for exact C-05/C-06 plus readiness metadata; statically prove backfill/constraints/indexes and no destructive or direct-ledger SQL, while SBR-SCHEMA.GATE/DA-10 retain mandatory disposable-target apply, idempotency, ledger, backup, and restore proof. | Proof: Council item 5309eca6 completed at revision a248358d with 4/4 current receipts and no content drift.
- [ ] SBR-SCHEMA.2 — Mirror migration 007 into fresh PostgreSQL init and fresh/legacy SQLite schema; prove exact logical PostgreSQL/SQLite/init parity, additive reopen compatibility, project_name preservation, and side-effect-free schema imports. Current implementation evidence: behavioral PASS at schema.py 1e406d46f92ff10a725c9fc27a854e41c56c02f27ae4ae867d6499b18ea4b946 and init.sql 7b58753777c5e19552683cf4884a4bab602a5dc5dc93d2dd20a9481a75f9ee49 with 24 focused tests. Completion remains open: the fresh exact-seat Witness gate failed before review because COUNCIL_SEAT_JSON was absent (Council event 1224c45e), so current truth, security, and quality receipts are missing.
- [ ] SBR-SCHEMA.3 — Implement SchemaReadinessV1, fingerprint fast check, pg_try_advisory_lock election, deadline-aware pool/retry, bounded <=500 ms peer wait, fail-closed mismatch, and setup compatibility; prove 32 simultaneous starts elect one bootstrapper with zero ledger drift.
- [ ] SBR-SCHEMA.GATE — Run import smoke and focused neighbor tests, then the single DA-10 PostgreSQL/process lane; on an approved disposable target retain AgentKit status -> plan -> backup -> apply -> status plus restore receipts; require Sentinel and Arbiter PASS before C-07 handoff.
## DA-05 — Hot path and telemetry (`SBR-HOTPATH.*`)
<!-- ID: sbr-hot-path -->
- [ ] SBR-HOTPATH.1 — Add the sole C-12 timing model/recorder and context-aware formatter finalizer; prove exact phases/ratio math, one C-11 correlation, strict >100 ms stage and >500 ms total tripwires, zero synchronous formatter project reads, preserved V1 timing consumers/formats, and foreground local audit durability.
- [ ] SBR-HOTPATH.2 — Pass the exact installed C-11 through LoggingToolMixin and get_project; prove object identity, attribution-only agent handling, explicit/default target preservation, no compatibility authority, no second project fetch, unchanged output/SITREP behavior, and non-verbose derived-work restraint.
- [ ] SBR-HOTPATH.3 — Reuse one C-11 and one ProjectRecord through read_recent/query_entries and one formatter call; prove pagination/filter/DB-file parity, immediate consistent snapshots, C-04 honesty, no repeated binding/project reads, one C-12, and zero target/default mutation.
- [ ] SBR-HOTPATH.GATE — DA-09 retains hermetic 32-session x 100-call evidence with <=1 binding read and <=1 project-record read per call, C-11 identity, >=95% timing coverage, exact manual-clock tripwire deltas, and zero wrong-target/default-drift/cross-talk/duplicate effects; DA-10 retains the held reference-profile raw p50/p95/p99 report with reads p50 <=75 ms and p95 <=250 ms, durable append/receipt p95 <=500 ms, all synchronous p95 <=500 ms, and p99 reported without an invented cap; Arbiter PASS is mandatory.
## DA-07 — Scheduler and lifecycle (`SBR-BG.*`)
<!-- ID: sbr-background-service -->
- [ ] `SBR-BG.1` — Add `background/scheduler.py` with canonical project/lane partitions, strict control/durable reserves, global/per-project caps, deterministic two-level DRR, item/byte/concurrency high-water metrics, no-HOL causal progress, zero starvation windows at least 5 seconds, and no project above 50 percent service while an equal-weight peer remains eligible.
- [ ] `SBR-BG.2` — Add `background/worker.py` with one fenced claim path, exact state-version/fencing transitions, stable seeded finite retry, permanent/dead-letter handling, commit-aware cancellation, worker-death/higher-fence recovery, stale completion rejection, exact-effect idempotency, and equal-capacity worker claim imbalance at most one.
- [ ] `SBR-BG.3` — Add `BackgroundJobServiceV1` plus explicit package exports; prove global/per-project item+byte admission, typed duplicate/conflict/busy/shutdown outcomes, p95 at most 500 ms control/read and receipt acknowledgement on the reference profile, idempotent start/stop, bounded events/health, and zero lost accepted receipts after fresh-runtime recovery.
- [ ] `SBR-BG.4` — Integrate only `server.py#background_lifecycle` and `health_check.py`; preserve legacy task helpers, start one C-09 service after authoritative storage, close admission before claims/drain/backend close, checkpoint recoverable work at deadline, leak zero workers/tasks/handles, and expose only bounded redacted health metrics.
- [ ] `SBR-BG.REVIEWS` — DA-09 records hermetic/manual-clock proof plus the 32 same-label caller × 100 mixed-call composition with zero wrong target/default drift/cross-talk/lost accepted receipts/duplicate effects/stale-fence acceptance, no HOL, bounds respected, and exact metrics; DA-10 records the single PostgreSQL/process lane; Sentinel and Arbiter PASS all four packages before C-09 handoff.
## DA-03 — Startup and import readiness (`SBR-STARTUP.*`)
<!-- ID: sbr-startup-readiness -->
- [x] `SBR-STARTUP.1` — Make `utils/__init__.py` response/token exports lazy and `tokens.py` construction side-effect-free; preserve the public export set, deterministic cheap estimation, lazy one-time exact encoder, metrics shape, and zero tiktoken/metrics-path mutation during server import. | Proof: Council item 2d48d2b5 completed at revision 610f818b with 3/3 current receipts and no content drift.
- [x] `SBR-STARTUP.2` — Split Hybrid/Corta client setup from one explicit bounded remote-health probe; preserve one client, local-first durability, normal remote operations, cancellation, and zero network I/O in foreground setup. | Proof: Council item 81007204 completed at revision 40fb285c with 3/3 current receipts and no content drift.
- [ ] `SBR-STARTUP.3` — Add exact C-10 service states in `server.py#startup_ready`; require successful C-07 plus recovered/running+accepting C-09 before ready, while optional object-store/bridge health runs in tracked background work and shutdown ordering remains unchanged.
- [ ] `SBR-STARTUP.GATE` — DA-10 records same-revision raw proof for warm/cold import p95 <=1.0/1.5 s, pre-tool/all-tools RSS <=64/80 MiB, warm/cold ready p95 <=1.5/2.5 s, optional-outage delta <=50 ms, exact C-10 states, local durable logging/tool listing under outage, zero import-time mutation/false-ready/teardown leak; Arbiter PASSes all three packages.
## DA-08 — Document durability (`SBR-DOC-DUR.*`)
<!-- ID: sbr-document-durability -->
- [x] `SBR-DOC-DUR.1` — Extend only `utils/files.py` so stable same-digest WAL admission is idempotent, same-ID/different-digest admission conflicts without effect, corrupt rows fail closed, restart readback is deterministic, atomic overwrite stays file+directory `fsync` durable, legacy append WAL is unchanged, and no queue/state machine is added. | proof=Source SHA256 9de185f35136a35a034dbbf7e8245d671dcb2d810a6fab4e9e219a5be8b95119; required import and py_compile PASS; package tests 15 passed; direct-neighbor tests 64 passed; ephemeral restart/idempotency/conflict/corruption/0600/legacy replay probe PASS; scoped diff-check PASS.
- [ ] `SBR-DOC-DUR.2` — Add sanitized `DocumentMutationReceiptV1` plus generation/digest/anchor fencing in existing apply-preview/runtime hooks; map C-08/C-09 accepted/duplicate/conflict/cancel/terminal outcomes, permit `accepted + queued_offline` only after WAL durability, and refuse stale/wrong target before effect with exact C-04.
- [ ] `SBR-DOC-DUR.3` — Keep `manage_docs` thin while converging the existing registration, index, and quality paths; commit WAL and return `applied` only after post-digest/generation plus applicable convergence, with restart skipping an already-observed after-digest effect.
- [ ] `SBR-DOC-DUR.GATE` — DA-09 proves outage before admission, crash before effect, crash after replace before commit, repeated restart, wrong project/root/path, stale binding/document generation/anchor/fence, same-digest duplicate, digest conflict, pre/post-effect cancellation, terminal replay, zero lost accepted work, zero duplicate effect, and registration/index/quality convergence.
- [ ] `SBR-DOC-DUR.REVIEWS` — Existing focused apply-preview/WAL/anchor-CAS/registration/quality/security tests and import smokes pass; receipt acknowledgement p95 is at most 500 ms; Sentinel and Arbiter PASS `.1`-`.3` before C-13 handoff to DA-09.
## DA-09 — Core validation (`SBR-CORE-VAL.*`)
<!-- ID: sbr-core-validation -->
- [ ] `SBR-CORE-VAL.1` — Add `tests/fixtures/swarm.py` and `tests/core/test_swarm_binding_reliability.py`. Prove 32 same-label `test_agent` callers across four repositories and 16 projects each bind once and execute the exact 100-call mix; cover delayed second-write, explicit same/cross-repository targets, isolated reconnect/new-handle/cleanup, causal no-HOL, one C-11/C-12 and at most one binding/project read, exact-effects reconciliation, clean teardown, and sole-source C-14 serialization. Proof commands: `PYTHONPATH=src:tests ./.venv/bin/python -c 'from fixtures.swarm import ManualClock, CausalGate, SwarmResultsV1, build_swarm_topology, build_mixed_schedule, reconcile_exact_effects'`; `./.venv/bin/python -m py_compile tests/fixtures/swarm.py tests/core/test_swarm_binding_reliability.py`; `./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py -m "core and regression and not integration and not slow and not performance"`; `./.venv/bin/pytest -q tests/test_set_project.py tests/test_set_project_runtime_scope_contract.py tests/test_session_project_cache.py tests/test_mcp_adapter.py`.
- [ ] `SBR-CORE-VAL.2` — Add `tests/core/test_background_queue_contract.py` after .1. Prove atomic item/byte admission bounds, duplicate/conflict/busy/shutdown outcomes, canonical partitions/lanes, fairness and causal no-HOL, global/project/worker caps, manual-clock retry, lease/fence recovery, cancellation barriers, bounded shutdown, exact metrics, and no lost/duplicate accepted effect. Proof commands: `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background import BackgroundIntentV1, BackgroundJobServiceV1, BackgroundServiceConfigV1, BackgroundShutdownReceiptV1; from scribe_mcp.background.scheduler import BackgroundSchedulerV1'`; `./.venv/bin/python -m py_compile tests/core/test_background_queue_contract.py`; `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py -m "core and regression and not integration and not slow and not performance"`; `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_health_check.py`.
- [ ] `SBR-CORE-VAL.3` — Add `tests/core/test_wal_replay_exactly_once.py` after .2. Prove pre/post-effect crash windows, concurrent/repeated replay, truncated tail, project-failure isolation, offline recovery, runtime reconstruction, stable duplicate/conflict truth, replay target/generation/digest/anchor/fence checks, cancellation boundaries, and one registration/index/quality convergence with exactly one effect and terminal receipt per accepted operation. Proof commands: `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.utils.files import WriteAheadLog, WalEntryConflictError, WalJournalCorruptError; from scribe_mcp.doc_management.apply_preview import DocumentMutationReceiptV1, DocumentMutationState'`; `./.venv/bin/python -m py_compile tests/core/test_wal_replay_exactly_once.py`; `./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py -m "core and regression and not integration and not slow and not performance"`; `./.venv/bin/pytest -q tests/test_multi_repo_file_ops.py tests/test_write_barrier_contract.py tests/test_apply_preview_engine.py tests/test_manage_docs_apply_preview.py tests/integration/test_manage_docs_apply_preview_lifecycle.py`.
- [ ] `SBR-CORE-VAL.4` — Extend `tests/test_tool_runtime_repo_scope.py` and `tests/test_manage_docs_anchor_cas.py` after .3. Prove target precedence, canonical caller key, one immutable C-11, at most one binding/project read, exact typed C-04/MCP envelopes, sanitized candidates, explicit-target default preservation, effect-free target/generation/digest/anchor/fence denials, and current-generation post-crash convergence. Proof commands: `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key; from scribe_mcp.shared.execution_context import ResolvedRequestContextV1; from scribe_mcp.mcp_adapter import ScribeErrorV1, normalize_tool_result; from scribe_mcp.tools.manage_docs import manage_docs'`; `./.venv/bin/python -m py_compile tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py`; `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py -m "core and regression and not integration and not slow and not performance"`; `./.venv/bin/pytest -q tests/test_mcp_adapter.py tests/test_logging_utils.py tests/test_append_entry_explicit_project_resolution.py tests/test_query_entries_explicit_project_resolution.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_quality_check.py tests/security/test_project_binding_policy.py`.
- [ ] `SBR-CORE-VAL.5` — Update only `tests/test_remote_backend.py` after `SBR-BIND-PERSIST.5`. Replace the stale in-memory/no-HTTP binding expectations with mocked authenticated-transport proof of all six C-01 fields, generation/CAS/no-write outcomes, reconnect cache non-authority, malformed-response errors, and preserved local/no-HTTP behavior for non-binding session methods. Proof commands: `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; from scribe_mcp.storage.base import SessionBindingRecordV2'`; `./.venv/bin/python -m py_compile tests/test_remote_backend.py`; `./.venv/bin/pytest -q tests/test_remote_backend.py::TestSessionMethods`; `./.venv/bin/pytest -q tests/test_remote_backend.py::TestRemoteAuth tests/test_remote_backend.py::TestErrorHandling`.

Completion gate: run every package command separately, then the six-test-module SS-09 aggregate command from `PHASE_PLAN.md#sbr-core-validation` at one source revision. Crucible records behavioral PASS; any red production behavior returns to its upstream owner without weakening the oracle. Handoff to DA-10 requires clean teardown, zero oracle defects, and C-14 as the sole JSON-equivalent result.
## DA-10 — Stress, adapter, and release evidence (`SBR-REL-VAL.*`)
<!-- ID: sbr-release-validation -->
- [ ] `SBR-REL-VAL.1` — Disposable PostgreSQL fixture rejects production/configured DSNs and shared fallback, creates/drops only `scribe_swarm_<uuid>`, redacts secrets, and passes: `PYTHONPATH=src ./.venv/bin/python -m py_compile tests/integration/storage/conftest.py` plus `SCRIBE_SWARM_DISPOSABLE=1 PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py -m postgres`.
- [ ] `SBR-REL-VAL.2` — C-14-based PostgreSQL/process stress proves 32 same-label callers × 100 calls, one bind each, queue bounds, typed backpressure, fairness, fencing, recovery, cancellation/shutdown, zero cross-project HOL, all frozen latency/RSS/error budgets, and baseline teardown. Smoke proof: `SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL="$SCRIBE_TEST_POSTGRES_URL" SCRIBE_SWARM_PROFILE=smoke SCRIBE_SWARM_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/swarm-smoke PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py -m "integration and postgres and performance and slow"`.
- [ ] `SBR-REL-VAL.3` — Public adapter compact trace passes for every supported direct/stdio/HTTP/legacy surface with identical target/default/replay/error semantics, server-owned reconnect identity, explicit source-backed `N/A` only, no Council assumptions, and passes: `PYTHONPATH=src ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py tests/security/test_session_provenance.py -m "core or regression or mcp_v2" -k "stdio or http or application_handle or reconnect or adapter_parity"`.
- [ ] `SBR-REL-VAL.4` — Import/RSS/process-ready/optional-outage/schema-32/hot-path probes preserve raw samples and pass every frozen threshold; C-07 elects one bootstrapper, C-10 optional failures do not block core ready, C-12 accounts for ≥95 percent with bounded reads and required tripwires; passes `PYTHONPATH=src ./.venv/bin/pytest -q tests/test_release_startup_probe.py`.
- [ ] `SBR-REL-VAL.5` — Thin runner acquires the only `SBR_REFERENCE_STRESS` lane, rejects dirty/mixed revisions, records exact commands and sanitized environment, digest-links subordinate JSON, returns nonzero for any red/missing/leaked evidence, and emits JSON-derived Markdown only.
- [ ] `SBR-REL-VAL.C15.CORE` — `core_verdict == "PASS"` from C-14 `SwarmResultsV1` for the release revision.
- [ ] `SBR-REL-VAL.C15.POSTGRES` — `postgres_smoke_verdict == "PASS"` for the disposable 32×100 PostgreSQL/process run at that same revision.
- [ ] `SBR-REL-VAL.C15.ADAPTER` — `adapter_parity_verdict == "PASS"` for every supported public Scribe adapter at that same revision.
- [ ] `SBR-REL-VAL.C15.IMPORT` — `import_budget_verdict == "PASS"` for warm/cold import, module/filesystem side effects, pre-tool RSS, and all-tools RSS at that same revision.
- [ ] `SBR-REL-VAL.C15.STARTUP` — `startup_budget_verdict == "PASS"` for warm/cold ready, optional outage, C-07 election/wait, and C-12 hot-path budgets at that same revision.
- [ ] `SBR-REL-VAL.C15.QUEUE` — `queue_budget_verdict == "PASS"` for bounds, typed backpressure, fair service, worker balance, fencing, recovery, and no cross-project HOL at that same revision.
- [ ] `SBR-REL-VAL.C15.REVISION` — `source_revision` is one clean Git commit; `target_version == "2.15.0"`; all artifact revisions/environment fingerprints match; `artifact_paths` are repo-relative and digest-verified; `exact_commands` and secret-free `environment_fingerprint` are populated.
- [ ] `SBR-REL-VAL.C15.TEARDOWN` — Databases, temp repos, journals, tasks, handles, sessions, workers, ports, processes, locks, and environment return to recorded baseline with no production state touched.
- [ ] `SBR-REL-VAL.C15.COMPLETE` — `reliability-release-evidence.json` exists and every required verdict above is `PASS`; any `FAIL`, required `N/A`, missing evidence, dirty/mixed revision, digest mismatch, or cleanup leak blocks DA-11.

Completion gate: run every package command separately, then acquire `SBR_REFERENCE_STRESS` once and run `SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL="$SCRIBE_TEST_POSTGRES_URL" SCRIBE_SWARM_PROFILE=release SCRIBE_SWARM_CALLERS=64 SCRIBE_SWARM_SMOKE_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_WARMUP_SECONDS=300 SCRIBE_SWARM_DURATION_SECONDS=1800 SCRIBE_SWARM_RECOVERY_SECONDS=300 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/sbr-2.15.0 PYTHONPATH=src ./.venv/bin/python benchmarks/swarm_concurrency.py --profile release --target-version 2.15.0 --postgres-url-env SCRIBE_TEST_POSTGRES_URL --results-dir benchmarks/artifacts/sbr-2.15.0`. Crucible records behavioral PASS, Witness verifies revision/contracts/ownership, Sentinel verifies credential redaction/disposable cleanup, and Arbiter reviews the high-blast performance/integration gate.
## DA-11 — Release surfaces (`SBR-RELEASE.*`)
<!-- ID: sbr-release-closure -->
- [ ] `SBR-RELEASE.1` — Execute the single bounded SS-11 package only after every prior implementation/validation/review gate and frozen C-15 pass for one clean source revision.
- [ ] `SBR-RELEASE.PREFLIGHT` — C-15 targets `2.15.0`, all six verdicts are `PASS`, all artifacts exist, and `source_revision` equals the pre-edit HEAD recorded as the required release-commit parent.
- [ ] `SBR-RELEASE.DIFF` — Working and staged release diffs contain exactly the five SS-11 files; `git diff --check` passes and unrelated dirty paths remain unstaged.
- [ ] `SBR-RELEASE.VERSION` — Package metadata, `scribe_mcp.__version__`, README release contract, release-surface line, and release-file-map current markers all equal `2.15.0`; existing exports remain.
- [ ] `SBR-RELEASE.DOCS` — README Current release highlights is the synchronized public changelog; both maps describe standalone Scribe source truth and no stale `2.14.0`/`2.13.0`/`v2.7.1` current marker remains.
- [ ] `SBR-RELEASE.TESTS` — Import/version assertions, version-context neighbor tests, MCP v2 public-readback regression, and stale-marker checks pass using the exact PHASE_PLAN commands.
- [ ] `SBR-RELEASE.SECRETS` — The staged five-file patch passes the high-confidence secret scan without printing a secret value; its binary patch SHA-256 is recorded.
- [ ] `SBR-RELEASE.BRANCH` — The release commit is created on a named non-protected branch, never directly on `dev` or `main`; branch and pre/post SHAs are recorded.
- [ ] `SBR-RELEASE.REMOTE` — `origin` resolves to `https://github.com/CortaLabs/scribe_mcp.git`; the pushed remote branch SHA equals local HEAD.
- [ ] `SBR-RELEASE.COMMIT` — Authorized Git custody creates exactly one commit titled `release: scribe-mcp 2.15.0`, containing exactly the five SS-11 paths, whose sole parent equals C-15 `source_revision`.
- [ ] `SBR-RELEASE.PUSH` — The governed source branch is pushed after PASS evidence; no tag, release artifact, package upload, deployment, or runtime adoption occurs.
- [ ] `SBR-RELEASE.PR` — Exactly one PR is opened with the pushed branch as head and `dev` as base; evidence records URL/state, head/base, commits, files, checks, C-15 parent, release commit, patch digest, and the no-publish/no-deploy/no-`main`-merge boundary.
- [ ] `SBR-RELEASE.NO-PUBLISH` — No PyPI publish, GitHub release/tag, deployment, service restart/adoption, production credential use, branch-protection change, or production-triggering merge to `main` is performed or implied.
## Final standalone Scribe release gates
<!-- ID: sbr-final-release-gates -->

- [ ] `SBR-FINAL.CONTRACTS` — C-01 through C-16 and every frozen budget remain unchanged or an accepted SEAM_MAP amendment is recorded.
- [ ] `SBR-FINAL.REVISION` — C-14 core evidence and C-15 reference-profile evidence are PASS for the same source revision.
- [ ] `SBR-FINAL.REVIEWS` — All package-declared behavioral, truth, quality, security, and schema-sensitive review gates are current for that revision.
- [ ] `SBR-FINAL.RELEASE` — Version/public truth is `2.15.0`; one governed source-release commit boundary and one PR are prepared. Deployment, publication, runtime adoption, and production-triggering `main` merge are not implied.

## Joint external Council acceptance gates
<!-- ID: sbr-joint-council-acceptance -->

- [ ] `SBR-JOINT.ADAPTER` — Council consumes only C-16: verified caller-session key, optional C-02 target, generic attribution, C-03 receipt, and C-04 errors.
- [ ] `SBR-JOINT.BIND-ONCE` — Cold bind, reconnect/default readback, same-repo explicit target, and cross-repository explicit target succeed without repeated `set_project` or default mutation.
- [ ] `SBR-JOINT.ISOLATION` — Same-label sibling sessions and provider variants show zero binding drift, cross-talk, wrong target, or peer-session theft.
- [ ] `SBR-JOINT.TRUTH` — Council labels local projection separately from live Scribe binding truth and claims live truth only from C-03 or direct Scribe readback.
- [ ] `SBR-JOINT.OWNERSHIP` — Aegis, work-item, seat/spawn, provider-process, projection, completion, process reuse/reap, and generated-surface behavior remain wholly outside Scribe source and schema.
## Implementation Registry Synthesis
<!-- ID: sbr-implementation-registry-synthesis -->

- [x] Preserve all 20 prior manifest rows without amendment or orphaning. <!-- id: SBR-REGISTRY.PRESERVE -->
- [x] Register all 39 executable `SBR-BIND-PERSIST.*` through `SBR-RELEASE.1` packages with exact plan goals, ownership, forbidden boundaries, verification, acceptance, specialists, contracts, dependencies, and evidence requirements. <!-- id: SBR-REGISTRY.COVERAGE -->
- [x] Serialize every repeated physical file and keep the single repository-saturating release-validation lane ordered. <!-- id: SBR-REGISTRY.DISJOINT -->
- [x] Hold `SBR-RELEASE.1` behind `SBR-PLAN-SYNTH-12` and all 38 preceding executable package completions/current-revision PASS receipts. <!-- id: SBR-REGISTRY.RELEASE-HOLD -->
- [x] Validate and apply the full manifest through direct Council MCP: 59 rows, 39 created, 0 updated, 0 orphaned, 0 errors. <!-- id: SBR-REGISTRY.IMPORT -->
- [ ] After `SBR-PLAN-SYNTH-12` completes, dispatch the first wave only: `SBR-BIND-PERSIST.1`, `SBR-BIND-RESOLVE.1`, `SBR-STARTUP.1`, and `SBR-STARTUP.2`. <!-- id: SBR-REGISTRY.FIRST-WAVE -->

<!-- ID: work_packages_checklist -->
> **Generated section — do not hand-edit.** Rendered from the `WORK_ITEMS.md` manifest by `render_plan_projection`; hand edits are overwritten on the next `council work render-plan`.

- [x] SBR-BIND-PERSIST.1 — SBR BIND PERSIST.1
- [ ] SBR-BIND-RECONNECT.1 — Persisted actor binding survives application-handle reconstruction
- [x] SBR-BIND-RESOLVE.1 — SBR BIND RESOLVE.1
- [x] SBR-OBJKEY-BUG-13 — Restore Scribe backup sync policy
- [x] SBR-STARTUP.1 — SBR STARTUP.1
- [x] SBR-STARTUP.2 — SBR STARTUP.2
- [x] SBR-BIND-PERSIST.2 — Abstract generation/CAS contract
- [x] SBR-BIND-PERSIST.5 — Remote durable transport parity
- [x] SBR-RECEIPT.1 — Host-neutral receipt models and storage contract
- [x] SBR-ARCH-AMEND-SCHEMA-SCOPE-15 — Align migration 007 ownership and non-destructive trigger DDL
- [x] SBR-ARCH-AMEND-SCHEMA-STARTUP-14 — Align migration 007 plan with startup-safe legacy classification
- [x] SBR-DOC-DUR.1 — Idempotent WAL and atomic document-write substrate
- [x] SBR-SCHEMA.1 — Migration 007 reliability upgrade
- [x] SBR-ARCH-AMEND-SCHEMA2-16 — SBR ARCH AMEND SCHEMA2 16
- [ ] SBR-SCHEMA.2 — Fresh and legacy SQLite/PostgreSQL baseline parity
- [ ] SBR-BIND-PERSIST.4 — SQLite parity and facade
- [ ] SBR-RECEIPT.2 — SQLite atomic receipt persistence
- [ ] SBR-SCHEMA.3 — Fingerprinted elected bootstrap and bounded readiness
- [ ] SBR-BIND-PERSIST.3 — PostgreSQL atomic persistence
- [ ] SBR-REL-VAL.1 — Disposable PostgreSQL reference fixture
- [ ] SBR-BIND-RESOLVE.2 — Registered project target resolution and default preservation
- [ ] SBR-RECEIPT.3 — PostgreSQL atomic persistence and backend parity
- [ ] SBR-BG.1 — Canonical partition and lane-fair scheduler
- [ ] SBR-BIND-RESOLVE.3 — One-time default binding and BindingReceiptV1
- [x] SBR-ARCH-AMEND-TOKEN-EFFICIENCY-19 — SBR ARCH AMEND TOKEN EFFICIENCY 19
- [ ] SBR-BG.2 — Fenced worker, finite retry, and cancellation protocol
- [ ] SBR-BIND-RESOLVE.4 — One-pass runtime context, typed MCP errors, and generic external adapter
- [x] SBR-TOKEN-RESEARCH-18 — SBR TOKEN RESEARCH 18
- [ ] CSBH-S1 — Generic Scribe bootstrap and durable caller adoption
- [ ] SBR-BG.3 — BackgroundJobServiceV1 admission, recovery, metrics, and API
- [ ] SBR-HOTPATH.1 — C-12 timing model and context-aware response finalization
- [ ] CSBH-S2 — Scribe transport ingress and reconnect
- [ ] SBR-BG.4 — Server lifecycle integration and bounded health projection
- [ ] SBR-DOC-DUR.2 — C-13 generation-fenced admission and restart replay
- [ ] SBR-HOTPATH.2 — Single-context logging helper and get-project read path
- [ ] SBR-DOC-DUR.3 — `manage_docs` readback and registration/index/quality convergence
- [ ] SBR-HOTPATH.3 — Read-recent/query single-record execution and timing closure
- [ ] SBR-STARTUP.3 — C-10 core-ready and optional-service states
- [ ] SBR-CORE-VAL.1 — Shared swarm fixture and 32-session binding oracle
- [ ] SBR-REL-VAL.4 — Import, RSS, ready, schema, and hot-path budgets
- [ ] SBR-CORE-VAL.2 — Bounded queue, fairness, cancellation, and shutdown contract
- [ ] SBR-CORE-VAL.5 — Remote C-01 durable binding expectation
- [ ] SBR-CORE-VAL.3 — WAL and document replay exactly-once oracle
- [ ] SBR-CORE-VAL.4 — Typed runtime and managed-document refusal regressions
- [ ] SBR-REL-VAL.2 — 32-caller PostgreSQL/process stress and queue proof
- [ ] SBR-REL-VAL.3 — Provider-neutral public adapter parity
- [ ] SBR-REL-VAL.5 — Single-lane release runner and C-15 evidence
- [ ] SBR-RELEASE.1 — Synchronize 2.15.0 release truth and open the governed dev PR
- [x] SBR-ARCH-06 — Scribe Reliability Release Seam Map
- [x] SBR-ARCH-AMEND-REMOTE-08 — Remote Binding Test Ownership Amendment
- [ ] SBR-CONC-04 — Scribe Swarm Concurrency Validation Research
- [x] SBR-CONC-A5-05 — Scribe Background Queue Validation Delta
- [x] SBR-DETAIL-DA01 — Binding Persistence Detail Plan
- [x] SBR-DETAIL-DA02 — Target Resolution And Typed Errors Detail Plan
- [x] SBR-DETAIL-DA03 — Startup And Import Readiness Detail Plan
- [x] SBR-DETAIL-DA04 — Schema Bootstrap Detail Plan
- [x] SBR-DETAIL-DA05 — Hot Path And Telemetry Detail Plan
- [x] SBR-DETAIL-DA06 — Durable Receipt Store Detail Plan
- [x] SBR-DETAIL-DA07 — Background Scheduler And Lifecycle Detail Plan
- [x] SBR-DETAIL-DA08 — Managed Document Durability Detail Plan
- [x] SBR-DETAIL-DA09 — Core Reliability Validation Detail Plan
- [x] SBR-DETAIL-DA10 — Reference Stress And Release Evidence Detail Plan
- [x] SBR-DETAIL-DA11 — Release Surfaces Detail Plan
- [x] SBR-EFF-02 — Scribe Binding Efficiency And Ownership Research
- [x] SBR-PERF-03 — Scribe Server Weight And Latency RCA
- [x] SBR-PLAN-SCAFFOLD-07 — Scribe Reliability Detail Planning Scaffold
- [x] SBR-PLAN-SYNTH-12 — Implementation Registry Synthesis
- [x] SBR-RCA-01 — SBR RCA 01
- [ ] SBR-SCHEMA-007-STARTUP-SAFE — SBR SCHEMA 007 STARTUP SAFE
