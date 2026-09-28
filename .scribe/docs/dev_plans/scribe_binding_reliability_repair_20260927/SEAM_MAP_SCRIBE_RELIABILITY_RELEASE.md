---
id: scribe_binding_reliability_repair_20260927-seam-map-scribe-reliability-release
title: Seam Map Scribe Reliability Release
doc_type: custom
doc_name: SEAM_MAP_SCRIBE_RELIABILITY_RELEASE
category: engineering
status: ready
version: '2.0'
last_updated: 2026-09-27 08:03:03 UTC
maintained_by: agent-20260927-075853-7092bc31
created_by: agent-20260927-054553-6f5070e5
owners:
- Blueprint
related_docs: []
tags:
- seam-map
- architecture
- reliability
- performance
- standalone-scribe
summary: DA-01 remote-backend test ownership amendment; SS-01 production ownership
  and frozen contracts unchanged
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:51:22 UTC
  created_via: create_doc
  last_edited_at: 2026-09-27 08:03:03 UTC
  last_edited_by: agent-20260927-075853-7092bc31
  last_action: apply_patch
  work_item_id: 6436d1cb-6834-4316-9ecc-678cd7890028
---
# Scribe Reliability Release — Meta-Architect v2 SEAM_MAP

## Header and decomposition rationale
<!-- ID: header -->

- seam_map_version: 2.0
- source_spec: SBR-ARCH-06 current work-item contract, revision 3d3a8febfecd4928c640b790ed19016c89724d61e3c8b9f85aa9b4cef853b817
- source_synthesis:
  - research/RESEARCH_BINDING_RCA.md
  - research/RESEARCH_BINDING_EFFICIENCY_AND_OWNERSHIP.md
  - research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md
  - research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md
  - research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md
  - WORK_ITEMS.md
  - PROGRESS_LOG.md through the 2026-09-27 05:44:49 UTC research gate
- verdict: fan_out
- decompose_pass: SBR-ARCH-06 / MODE=decompose
- release_scope: one standalone Scribe reliability and performance release
- release_version: 2.15.0
- release_boundary: one governed source-release commit and one PR after all validation gates pass
- external_consumer: council_mcp Atlas consumes the frozen generic adapter contract; Council retains all Aegis/work-item/provider-seat/spawn/projection/process orchestration.
- amendment: SBR-ARCH-AMEND-REMOTE-08 assigns tests/test_remote_backend.py to SS-09/DA-09 validation ownership after DA-01 confirmed its current in-memory/no-HTTP assertions conflict with frozen durable cross-backend semantics.
- amendment_scope: test ownership and count correction only; SS-01 production ownership, C-01, C-05, every other subsystem path, the contract ledger, DAG, budgets, and Council boundary remain frozen.

### Q2 arithmetic

Level 1 fires on every predicate:

1. Owned-file span is 59 physical files across 63 owned path entries, greater than 12.
2. The partition has 11 subsystems and 16 concrete contracts, satisfying at least 3 subsystems plus at least 2 cross-subsystem contracts.
3. The release has 7 dependency layers and at least 4 gated phases: contract/storage foundation, runtime implementation, deterministic validation, operator/performance validation, and release closure.

Level 2 self-confirmation:

- subsystem_count = 11
- physical_file_count = 59
- owned_path_entry_count = 63
- contract_count = 16
- collapse checks: one subsystem = false; six or fewer files = false; zero contracts = false
- result: fan_out

### Decomposition rationale

The stable seams are durable session binding, request-local target resolution, startup/import readiness, schema bootstrap, single-context telemetry, durable receipt storage, background scheduling/lifecycle, managed-document mutation durability, deterministic core validation, reference-profile/adapter validation, and release publication.

Every physical file has one whole-file owner except three large shared files, which use exact symbol anchors:

- src/scribe_mcp/storage/base.py#session_binding_contract owns only set_session_project/get_session_project; #background_receipt_contract owns only new background-receipt abstract methods.
- src/scribe_mcp/storage/postgres/__init__.py#session_binding_storage owns only set_session_project/get_session_project plus their row mapping; #setup_fast_path owns only PostgresStorage.setup; #background_receipt_storage owns only new background receipt CRUD/claim/transition methods.
- src/scribe_mcp/server.py#startup_ready owns _startup, resolve_tool_startup_profile, and _tool_can_skip_startup; #background_lifecycle owns BackgroundServiceStatus, schedule_background_task, drain_background_tasks, and queue/drain portions of _shutdown.

tests/test_remote_backend.py is a whole-file SS-09 validation path. Its binding assertions must validate the SS-01-produced C-01/C-05 behavior without sharing production ownership; src/scribe_mcp/storage/remote.py#session_binding_transport remains solely SS-01.
The SQLite schema anchor and document-runtime anchor are single-owner sub-file boundaries, not shared ownership. No two declared anchors contain the same existing or future symbol. A detail pass needing another anchor must stop for a map amendment.

Safety and durability foundations precede their consumers. Validation consumes only frozen public contracts. Release/version work is terminal and cannot start until the same source revision passes deterministic and reference-profile gates.

### Non-negotiable operator invariants

- set_project selects a caller-session default once; unchanged rebind is idempotent.
- An explicit ProjectTargetV1 may select any authorized registered workstation project, including another repository, without mutating the caller default.
- agent/persona labels are attribution only and never binding or partition identity.
- 10-plus callers are normal; required validation uses at least 32 concurrent same-label caller sessions.
- No cross-session, cross-project, or cross-repository interference is allowed.
- Any foreground total above 500 ms emits a correlated tripwire and is presumed excessive unless the public API explicitly returns a durable asynchronous receipt.
- Authority, validation, idempotency reservation, capacity admission, and authoritative local durability remain foreground.
- Heavy work uses durable receipts, bounded item/byte admission, canonical project partitions, lane separation, fair scheduling, global/per-project caps, backpressure, leases/fencing, finite retry, cancellation, restart recovery, telemetry, and no cross-project head-of-line blocking.
- The release is one SemVer 2.15.0 source release, one governed release commit boundary, and one PR.
- No Council-specific source, schema, field, test import, or orchestration behavior enters this map.
## Frozen performance and correctness budgets
<!-- ID: performance_budgets -->

- Warm unchanged default bind: p95 at most 150 ms; p99 at most 300 ms; zero persistent writes and no inventory/document generation.
- Explicit local-database target resolution: p95 at most 200 ms; default binding unchanged.
- Fresh server import: warm p95 at most 1.0 s; cold p95 at most 1.5 s.
- Pre-tool ready RSS at most 64 MiB; all-tools-loaded steady RSS at most 80 MiB.
- Process-to-ready: warm p95 at most 1.5 s; cold p95 at most 2.5 s.
- Optional object-store outage adds at most 50 ms to foreground startup and cannot block core tools or local durable logging.
- Warm storage setup p95 at most 100 ms; 32 simultaneous starts perform one DDL/bootstrap; warm non-bootstrap wait at most 500 ms.
- Foreground read reference target: p50 at most 75 ms, p95 at most 250 ms.
- Durable append and durable receipt acknowledgement: p95 at most 500 ms.
- All synchronous foreground classes: p95 at most 500 ms; every stage above 100 ms and every total above 500 ms emits correlated evidence.
- Call-stage timings account for at least 95 percent of server-observed duration.
- Each call performs at most one durable session-binding read and one project-record read.
- Under 32 callers: wrong target, default drift, cross-talk, lost accepted work, duplicate effect, stale-fence acceptance, and accepted work unreconciled after recovery are all zero.
- Continuously eligible project starvation windows of 5 seconds or more are zero.
- Queue item/byte/concurrency high-water marks never exceed configuration.
- Equal-weight projects: no project exceeds 50 percent service while a peer remains eligible; equal-capacity worker claim counts differ by at most one.
## Element 1 — Subsystems
<!-- ID: subsystems -->

### SS-01 — Binding persistence and generation

- responsibility: Own durable caller-session defaults and their cross-backend storage contract. Does not resolve requests, translate MCP errors, run bootstrap, or contain Council identity.
- owned_paths:
  - src/scribe_mcp/storage/models.py
  - src/scribe_mcp/storage/base.py#session_binding_contract
  - src/scribe_mcp/storage/postgres/__init__.py#session_binding_storage
  - src/scribe_mcp/storage/sqlite/sessions.py
  - src/scribe_mcp/storage/sqlite/domain_facade.py#session_binding_facade
  - src/scribe_mcp/storage/remote.py#session_binding_transport
- entry_surface: SessionBindingRecordV2 and StorageBackend set/get session binding methods.
- provides_contracts: [C-01, C-05]
- consumes_contracts: []
- depends_on: []
- est_file_count: 6
- risk_flags: [schema, durability, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-01

### SS-02 — Generic target resolution, immutable context, binding receipt, and typed errors

- responsibility: Own one-time default selection, request-local explicit target resolution, immutable request-context construction, and the public typed MCP error boundary. Does not own DDL, scheduling, or Council seat/admission/projection logic.
- owned_paths:
  - src/scribe_mcp/shared/tool_runtime.py
  - src/scribe_mcp/shared/logging_utils.py
  - src/scribe_mcp/shared/execution_context.py
  - src/scribe_mcp/state/manager.py
  - src/scribe_mcp/tools/set_project.py
  - src/scribe_mcp/mcp_adapter.py
- entry_surface: resolve_project_target, set_project binding receipt, ResolvedRequestContextV1, and ScribeErrorV1 normalization.
- provides_contracts: [C-02, C-03, C-04, C-11, C-16]
- consumes_contracts: [C-01]
- depends_on: [SS-01]
- est_file_count: 6
- risk_flags: [security_boundary, identity, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-02

### SS-03 — Import weight and core readiness

- responsibility: Own lightweight imports, lazy token estimation, core ready semantics, optional remote readiness, and startup service status. Does not own schema migration, provider process reuse, or scheduler implementation.
- owned_paths:
  - src/scribe_mcp/utils/__init__.py
  - src/scribe_mcp/utils/tokens.py
  - src/scribe_mcp/object_store/hybrid.py
  - src/scribe_mcp/object_store/providers/corta.py
  - src/scribe_mcp/server.py#startup_ready
- entry_surface: server _startup core-ready transition and ServiceStateV1.
- provides_contracts: [C-10]
- consumes_contracts: [C-07, C-09]
- depends_on: [SS-04, SS-07]
- est_file_count: 5
- risk_flags: [startup, performance, high_blast, arbiter_review]
- design_assignment: DA-03

### SS-04 — Schema bootstrap and migration authority

- responsibility: Own fingerprint fast checks, elected bootstrap, bounded startup deadlines, and the one schema delta for binding generation plus background receipts. Does not own receipt behavior or request routing.
- owned_paths:
  - src/scribe_mcp/storage/postgres/__init__.py#setup_fast_path
  - src/scribe_mcp/storage/postgres/schema.py
  - src/scribe_mcp/storage/postgres/internals.py
  - src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql
  - src/scribe_mcp/storage/sqlite/schema.py#background_receipt_schema
  - src/scribe_mcp/db/init.sql#reliability_receipt_schema
- entry_surface: ensure_schema_ready(deadline_ms) -> SchemaReadinessV1 and migration 007.
- provides_contracts: [C-07]
- consumes_contracts: [C-05, C-06]
- depends_on: [SS-01, SS-06]
- est_file_count: 6
- risk_flags: [schema, migration, startup, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-04

### SS-05 — Single-context hot path and correlated telemetry

- responsibility: Consume one immutable resolved context, eliminate duplicate context/project resolution in helpers and formatting, and emit one correlated timing envelope. Does not choose targets or mutate defaults.
- owned_paths:
  - src/scribe_mcp/shared/base_logging_tool.py
  - src/scribe_mcp/utils/formatters/dispatcher.py
  - src/scribe_mcp/runtime_timing_envelope.py
  - src/scribe_mcp/tools/get_project.py
  - src/scribe_mcp/tools/read_recent.py
  - src/scribe_mcp/tools/query_entries.py
- entry_surface: CallTimingEnvelopeV2 and tool-helper APIs accepting ResolvedRequestContextV1.
- provides_contracts: [C-12]
- consumes_contracts: [C-04, C-11]
- depends_on: [SS-02]
- est_file_count: 6
- risk_flags: [performance, observability, high_blast, arbiter_review]
- design_assignment: DA-05

### SS-06 — Durable background receipt store

- responsibility: Own host-neutral receipt models, atomic admission/accounting, idempotency, leases/fencing, and backend persistence. Does not schedule workers or execute document mutations.
- owned_paths:
  - src/scribe_mcp/background/models.py
  - src/scribe_mcp/background/store.py
  - src/scribe_mcp/storage/base.py#background_receipt_contract
  - src/scribe_mcp/storage/postgres/__init__.py#background_receipt_storage
  - src/scribe_mcp/storage/sqlite/background_receipts.py
  - src/scribe_mcp/storage/sqlite/__init__.py#background_receipt_adapter
- entry_surface: BackgroundReceiptStoreV1 admit/get/claim/transition/recover methods.
- provides_contracts: [C-06, C-08]
- consumes_contracts: []
- depends_on: []
- est_file_count: 6
- risk_flags: [schema, durability, concurrency, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-06

### SS-07 — Partitioned scheduler, workers, and server lifecycle

- responsibility: Own bounded fair scheduling, lane reserves, leases/fencing, retry/cancellation, restart recovery, and shutdown/drain. Does not persist receipts directly or encode Council process policy.
- owned_paths:
  - src/scribe_mcp/background/__init__.py
  - src/scribe_mcp/background/scheduler.py
  - src/scribe_mcp/background/worker.py
  - src/scribe_mcp/background/service.py
  - src/scribe_mcp/server.py#background_lifecycle
  - src/scribe_mcp/tools/health_check.py
- entry_surface: BackgroundJobServiceV1 submit/status/cancel/start/stop and bounded service health.
- provides_contracts: [C-09]
- consumes_contracts: [C-08]
- depends_on: [SS-06]
- est_file_count: 6
- risk_flags: [concurrency, lifecycle, durability, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-07

### SS-08 — Managed-document durable mutation and offline replay

- responsibility: Reuse apply-preview, atomic file, and WAL primitives for generation-safe receipts and replay. Does not create a parallel document engine or queue.
- owned_paths:
  - src/scribe_mcp/doc_management/apply_preview.py
  - src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks
  - src/scribe_mcp/tools/manage_docs.py
  - src/scribe_mcp/utils/files.py
- entry_surface: DocumentMutationReceiptV1 with queued/applied/duplicate/conflict/terminal_error readback.
- provides_contracts: [C-13]
- consumes_contracts: [C-02, C-03, C-04, C-08, C-09, C-11]
- depends_on: [SS-02, SS-06, SS-07]
- est_file_count: 4
- risk_flags: [durability, replay, document_integrity, high_blast, sentinel_review, arbiter_review]
- design_assignment: DA-08

### SS-09 — Deterministic core correctness validation

- responsibility: Own the reusable 32-session same-label swarm, exact-effects oracle, deterministic no-HOL gates, receipt/replay/cancellation/shutdown tests, and focused typed-error/document regressions. Does not own production code or live infrastructure.
- owned_paths:
  - tests/fixtures/swarm.py
  - tests/core/test_swarm_binding_reliability.py
  - tests/core/test_background_queue_contract.py
  - tests/core/test_wal_replay_exactly_once.py
  - tests/test_tool_runtime_repo_scope.py
  - tests/test_manage_docs_anchor_cas.py
  - tests/test_remote_backend.py
- entry_surface: offline core/regression lane with one set_project plus 100 mixed calls for each of 32 sessions.
- provides_contracts: [C-14]
- consumes_contracts: [C-01, C-02, C-03, C-04, C-08, C-09, C-11, C-12, C-13]
- depends_on: [SS-01, SS-02, SS-05, SS-06, SS-07, SS-08]
- est_file_count: 7
- split_status: SPLIT_REQUIRED at 7 paths; DA-09 must emit independently verifiable task packages rather than one seven-file package.
- risk_flags: [behavioral_gate, concurrency, durability]
- design_assignment: DA-09

### SS-10 — Reference-profile stress, adapter parity, and release evidence

- responsibility: Own disposable PostgreSQL/process stress, public adapter parity, import/RSS budgets, and the one machine-readable release evidence artifact. Does not contain Council projections or production credentials.
- owned_paths:
  - tests/integration/test_swarm_concurrency_stress.py
  - tests/integration/storage/conftest.py
  - benchmarks/swarm_concurrency.py
  - tests/migration/mcp_v2/test_compatibility_matrix.py
  - tests/security/test_session_provenance.py
  - tests/test_release_startup_probe.py
- entry_surface: ReliabilityReleaseEvidenceV1 derived from swarm-results.json for one source revision.
- provides_contracts: [C-15]
- consumes_contracts: [C-07, C-10, C-12, C-14]
- depends_on: [SS-03, SS-04, SS-05, SS-09]
- est_file_count: 6
- risk_flags: [performance_gate, integration, security_validation, arbiter_review]
- design_assignment: DA-10

### SS-11 — SemVer and public release surfaces

- responsibility: Own one 2.15.0 version bump and public documentation truth after all gates pass. Does not implement behavior, deploy, publish, or modify generated Council surfaces.
- owned_paths:
  - pyproject.toml
  - src/scribe_mcp/__init__.py
  - README.md
  - docs/RELEASE_SURFACE.md
  - docs/RELEASE_FILE_MAP.md
- entry_surface: version 2.15.0 source truth and public standalone Scribe contract documentation.
- provides_contracts: []
- consumes_contracts: [C-15]
- depends_on: [SS-10]
- est_file_count: 5
- risk_flags: [release, public_contract, arbiter_review]
- design_assignment: DA-11
## Element 2 — Contracts ledger
<!-- ID: contracts -->

All contracts are frozen. No detail assignment is blocked on a negotiable input.

### C-01 — SessionBindingStoreV2

- producer: SS-01
- consumers: [SS-02, SS-09]
- surface:
  - SessionBindingRecordV2 fields: caller_session_key_hash, project_key, project_name, canonical_repo_root, binding_generation, updated_at.
  - set_session_project(session_id: str, project_key: str, expected_generation: int | None = None) -> SessionBindingRecordV2.
  - get_session_project(session_id: str) -> SessionBindingRecordV2 | None.
  - Generation increments only when the default changes; unchanged rebind returns the existing record without a persistent write.
- stability: frozen
- direction: SS-01 -> {SS-02, SS-09}

### C-02 — ProjectTargetV1 and ResolvedProjectTargetV1

- producer: SS-02
- consumers: [SS-05, SS-08, SS-09, external:council_mcp/Atlas]
- surface:
  - ProjectTargetV1 fields: project_key?: str, project?: str, repo_root?: str.
  - resolve_project_target(caller_session_key: str, target: ProjectTargetV1 | None) -> ResolvedProjectTargetV1.
  - Precedence: explicit project_key; explicit name plus canonical root; unique name; caller default only when no explicit target.
  - Resolved fields: project_key, project_name, canonical_repo_root, repository_id, resolution_source, default_binding_generation.
  - Explicit resolution never writes the default.
- stability: frozen
- direction: SS-02 -> {SS-05, SS-08, SS-09, external:council_mcp/Atlas}

### C-03 — BindingReceiptV1

- producer: SS-02
- consumers: [SS-08, SS-09, external:council_mcp/Atlas]
- surface: fields ok, caller_session_key_hash, project_key, project_name, canonical_repo_root, binding_generation, binding_reused, persistent_write_performed, resolution_source, correlation_id.
- stability: frozen
- direction: SS-02 -> {SS-08, SS-09, external:council_mcp/Atlas}

### C-04 — ScribeErrorV1

- producer: SS-02
- consumers: [SS-05, SS-08, SS-09, external:council_mcp/Atlas]
- surface:
  - CallToolResult has isError=true and structuredContent {ok:false,error_code,message,retryable,target,candidates,remediation,correlation_id}.
  - Required codes: SCRIBE_BINDING_MISSING, SCRIBE_PROJECT_NOT_FOUND, SCRIBE_PROJECT_AMBIGUOUS, SCRIBE_PROJECT_ROOT_MISMATCH, SCRIBE_CALLER_SESSION_UNVERIFIED, SCRIBE_BINDING_GENERATION_STALE, SCRIBE_DOCUMENT_GENERATION_STALE, SCRIBE_BUSY, SCRIBE_SHUTTING_DOWN, SCRIBE_STALE_FENCE.
  - Expected failures never escape as raw transport exceptions.
- stability: frozen
- direction: SS-02 -> {SS-05, SS-08, SS-09, external:council_mcp/Atlas}

### C-05 — Binding schema delta

- producer: SS-01
- consumers: [SS-04]
- surface: migration 007 persists project_key and binding_generation for session bindings while retaining project_name only for display/compatibility; caller session key remains the unique authority.
- stability: frozen
- direction: SS-01 -> SS-04

### C-06 — Background receipt schema delta

- producer: SS-06
- consumers: [SS-04]
- surface: migration 007 and SQLite baseline persist operation_id, canonical_project_key, lane, idempotency_key, payload_digest, payload_bytes, durability_class, state, state_version, attempt_count, next_attempt_at, lease_owner, lease_expires_at, fencing_token, cancel_requested, result_ref, error_code, created_at, updated_at; uniqueness is canonical_project_key plus idempotency_key, with digest conflicts checked atomically.
- stability: frozen
- direction: SS-06 -> SS-04

### C-07 — SchemaReadinessV1

- producer: SS-04
- consumers: [SS-03, SS-10]
- surface:
  - ensure_schema_ready(deadline_ms: int) -> SchemaReadinessV1.
  - Fields: schema_fingerprint, migration_version, bootstrap_role, wait_ms, ready, error_code, retryable.
  - One elected bootstrapper runs DDL when stale; peers use bounded readiness wait and fail closed on mismatch.
- stability: frozen
- direction: SS-04 -> {SS-03, SS-10}

### C-08 — BackgroundReceiptStoreV1

- producer: SS-06
- consumers: [SS-07, SS-08, SS-09]
- surface:
  - admit(intent, limits) -> accepted original receipt | duplicate original receipt | typed digest conflict | typed busy with retry_after_ms | typed shutting_down.
  - get(operation_id) -> DurableOperationReceiptV1 | not found.
  - claim(partition, worker_id, lease_ms) -> receipt plus monotonically increasing fencing_token.
  - transition(operation_id, expected_state_version, fencing_token, outcome) -> updated receipt.
  - recover(now) reconstructs capacity from all nonterminal receipts.
  - Limits cover ready, retry_wait, and leased items and serialized payload bytes atomically.
- stability: frozen
- direction: SS-06 -> {SS-07, SS-08, SS-09}

### C-09 — BackgroundJobServiceV1

- producer: SS-07
- consumers: [SS-03, SS-08, SS-09]
- surface:
  - submit(intent: BackgroundIntentV1) -> DurableOperationReceiptV1.
  - get_status(operation_id) -> DurableOperationReceiptV1.
  - cancel(operation_id, expected_state_version) -> DurableOperationReceiptV1.
  - start() and stop(admission_close: bool = true, drain_deadline_ms: int = configured) -> BackgroundShutdownReceiptV1.
  - Canonical project partitions; control, durable, and heavy lanes; item/byte bounds; global/per-project caps; deficit round robin; finite seeded retry; leases/fencing; restart-safe recovery.
- stability: frozen
- direction: SS-07 -> {SS-03, SS-08, SS-09}

### C-10 — ServiceStateV1

- producer: SS-03
- consumers: [SS-10]
- surface: fields service, state(initializing|healthy|degraded|stopped), required_for_core_ready, last_error_code, last_transition_at, startup_phase_ms; optional remote/plugin/bridge services cannot block core-ready.
- stability: frozen
- direction: SS-03 -> SS-10

### C-11 — ResolvedRequestContextV1

- producer: SS-02
- consumers: [SS-05, SS-08, SS-09]
- surface: immutable fields caller_session_key_hash, resolved_target, default_binding_generation, agent_attribution, correlation_id, operating_mode, authorization_evidence; created once per call and passed to helpers/formatter without re-resolution.
- stability: frozen
- direction: SS-02 -> {SS-05, SS-08, SS-09}

### C-12 — CallTimingEnvelopeV2

- producer: SS-05
- consumers: [SS-09, SS-10]
- surface: correlated phases ingress_decode, session_binding_read, project_record_read, target_resolution, mode_resolution, tool_body, authority_and_validation, authoritative_durability, receipt_commit, hooks, response_format, audit_append, egress_serialize, unaccounted; includes total_ms, accounted_ratio, slow_stages, tripwire_exceeded.
- stability: frozen
- direction: SS-05 -> {SS-09, SS-10}

### C-13 — DocumentMutationReceiptV1

- producer: SS-08
- consumers: [SS-09]
- surface: fields operation_id, project_key, caller_session_key_hash, binding_generation, document_id, canonical_path, document_generation_before, document_generation_after, content_digest_before, content_digest_after, state(accepted|applied|duplicate|conflict|terminal_error|cancelled), replay_safe, correlation_id; replay re-resolves project and compares both generations before effect.
- stability: frozen
- direction: SS-08 -> SS-09

### C-14 — SwarmResultsV1

- producer: SS-09
- consumers: [SS-10]
- surface: one JSON source with source_revision, seed, topology, set_project_count, operation ledger, oracle cardinalities, queue metrics, timing histograms, fault timeline, teardown counts, and verdict; Markdown is generated from this JSON.
- stability: frozen
- direction: SS-09 -> SS-10

### C-15 — ReliabilityReleaseEvidenceV1

- producer: SS-10
- consumers: [SS-11]
- surface: fields source_revision, target_version=2.15.0, core_verdict, postgres_smoke_verdict, adapter_parity_verdict, import_budget_verdict, startup_budget_verdict, queue_budget_verdict, artifact_paths, exact_commands, environment_fingerprint; every verdict must be PASS for the same revision.
- stability: frozen
- direction: SS-10 -> SS-11

### C-16 — External Council adapter contract

- producer: SS-02
- consumers: [external:council_mcp/Atlas]
- surface:
  - Host input is only a server-verified caller_session_key plus optional ProjectTargetV1 and generic agent attribution.
  - Bind once with set_project and retain BindingReceiptV1.
  - Later explicit calls pass ProjectTargetV1 and consume ResolvedProjectTargetV1/ScribeErrorV1 without another set_project and without default mutation.
  - Council may map provider/seat/work-item state to caller_session_key upstream, but Scribe never receives Council seat, Aegis, work-item, spawn, projection, or provider-process fields.
  - Council runtime-binding truth requires a real BindingReceiptV1 or direct Scribe readback; local projection is not Scribe binding truth.
- stability: frozen
- direction: SS-02 -> external:council_mcp/Atlas
## Element 3 — Dependency DAG
<!-- ID: dag -->

### Edges

- [SS-01, SS-02] via C-01
- [SS-01, SS-04] via C-05
- [SS-06, SS-04] via C-06
- [SS-06, SS-07] via C-08
- [SS-02, SS-05] via C-04 and C-11
- [SS-04, SS-03] via C-07
- [SS-07, SS-03] via C-09
- [SS-02, SS-08] via C-02, C-03, C-04, and C-11
- [SS-06, SS-08] via C-08
- [SS-07, SS-08] via C-09
- [SS-01, SS-09] via C-01
- [SS-02, SS-09] via C-02, C-03, C-04, and C-11
- [SS-05, SS-09] via C-12
- [SS-06, SS-09] via C-08
- [SS-07, SS-09] via C-09
- [SS-08, SS-09] via C-13
- [SS-03, SS-10] via C-10
- [SS-04, SS-10] via C-07
- [SS-05, SS-10] via C-12
- [SS-09, SS-10] via C-14
- [SS-10, SS-11] via C-15

### Topological layers and detail sub-batches

- layer 0 / batch 0: [SS-01, SS-06]
- layer 1 / batch 1: [SS-02, SS-04]
- layer 2 / batch 2: [SS-05, SS-07]
- layer 3 / batch 3: [SS-03, SS-08]
- layer 4 / batch 4: [SS-09]
- layer 5 / batch 5: [SS-10]
- layer 6 / batch 6: [SS-11]

Every batch has at most two parallel detail passes, below the maximum of three. A detail pass may begin only after Atlas accepts this map and all listed input contracts remain frozen.
## Element 4 — Design assignments
<!-- ID: assignments -->

### DA-01 — Binding persistence detail

- owned_subsystems: [SS-01]
- owned_paths: [src/scribe_mcp/storage/models.py, src/scribe_mcp/storage/base.py#session_binding_contract, src/scribe_mcp/storage/postgres/__init__.py#session_binding_storage, src/scribe_mcp/storage/sqlite/sessions.py, src/scribe_mcp/storage/sqlite/domain_facade.py#session_binding_facade, src/scribe_mcp/storage/remote.py#session_binding_transport]
- input_contracts: []
- deliverable: PHASE_PLAN#sbr-binding-persistence plus CHECKLIST ids SBR-BIND-PERSIST.*
- dag_layer: 0
- parallelizable_with: [DA-06]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: schema-sensitive; require Sentinel and Arbiter review before schema consumer execution.

### DA-02 — Target resolution and typed errors detail

- owned_subsystems: [SS-02]
- owned_paths: [src/scribe_mcp/shared/tool_runtime.py, src/scribe_mcp/shared/logging_utils.py, src/scribe_mcp/shared/execution_context.py, src/scribe_mcp/state/manager.py, src/scribe_mcp/tools/set_project.py, src/scribe_mcp/mcp_adapter.py]
- input_contracts: [C-01]
- deliverable: PHASE_PLAN#sbr-target-resolution plus CHECKLIST ids SBR-BIND-RESOLVE.*
- dag_layer: 1
- parallelizable_with: [DA-04]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: security/identity boundary; no Council vocabulary or persona-keyed authority.

### DA-03 — Startup/import readiness detail

- owned_subsystems: [SS-03]
- owned_paths: [src/scribe_mcp/utils/__init__.py, src/scribe_mcp/utils/tokens.py, src/scribe_mcp/object_store/hybrid.py, src/scribe_mcp/object_store/providers/corta.py, src/scribe_mcp/server.py#startup_ready]
- input_contracts: [C-07, C-09]
- deliverable: PHASE_PLAN#sbr-startup-readiness plus CHECKLIST ids SBR-STARTUP.*
- dag_layer: 3
- parallelizable_with: [DA-08]
- blocked_by: []
- split_status: bounded at 5 files
- handoff_note: preserve exact server anchor boundary; no edits to background-lifecycle symbols.

### DA-04 — Schema bootstrap detail

- owned_subsystems: [SS-04]
- owned_paths: [src/scribe_mcp/storage/postgres/__init__.py#setup_fast_path, src/scribe_mcp/storage/postgres/schema.py, src/scribe_mcp/storage/postgres/internals.py, src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql, src/scribe_mcp/storage/sqlite/schema.py#background_receipt_schema, src/scribe_mcp/db/init.sql#reliability_receipt_schema]
- input_contracts: [C-05, C-06]
- deliverable: PHASE_PLAN#sbr-schema-bootstrap plus CHECKLIST ids SBR-SCHEMA.*
- dag_layer: 1
- parallelizable_with: [DA-02]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: one numbered migration delta; require zero ledger drift and special review.

### DA-05 — Hot path and telemetry detail

- owned_subsystems: [SS-05]
- owned_paths: [src/scribe_mcp/shared/base_logging_tool.py, src/scribe_mcp/utils/formatters/dispatcher.py, src/scribe_mcp/runtime_timing_envelope.py, src/scribe_mcp/tools/get_project.py, src/scribe_mcp/tools/read_recent.py, src/scribe_mcp/tools/query_entries.py]
- input_contracts: [C-04, C-11]
- deliverable: PHASE_PLAN#sbr-hot-path plus CHECKLIST ids SBR-HOTPATH.*
- dag_layer: 2
- parallelizable_with: [DA-07]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: retain authoritative foreground durability; only analytics/derived work may defer.

### DA-06 — Durable receipt store detail

- owned_subsystems: [SS-06]
- owned_paths: [src/scribe_mcp/background/models.py, src/scribe_mcp/background/store.py, src/scribe_mcp/storage/base.py#background_receipt_contract, src/scribe_mcp/storage/postgres/__init__.py#background_receipt_storage, src/scribe_mcp/storage/sqlite/background_receipts.py, src/scribe_mcp/storage/sqlite/__init__.py#background_receipt_adapter]
- input_contracts: []
- deliverable: PHASE_PLAN#sbr-receipt-store plus CHECKLIST ids SBR-RECEIPT.*
- dag_layer: 0
- parallelizable_with: [DA-01]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: new background package is the one intentional queue boundary; do not duplicate apply-preview storage behavior.

### DA-07 — Scheduler and lifecycle detail

- owned_subsystems: [SS-07]
- owned_paths: [src/scribe_mcp/background/__init__.py, src/scribe_mcp/background/scheduler.py, src/scribe_mcp/background/worker.py, src/scribe_mcp/background/service.py, src/scribe_mcp/server.py#background_lifecycle, src/scribe_mcp/tools/health_check.py]
- input_contracts: [C-08]
- deliverable: PHASE_PLAN#sbr-background-service plus CHECKLIST ids SBR-BG.*
- dag_layer: 2
- parallelizable_with: [DA-05]
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: host-neutral service only; no provider process count/reuse/idle-reap policy.

### DA-08 — Document durability detail

- owned_subsystems: [SS-08]
- owned_paths: [src/scribe_mcp/doc_management/apply_preview.py, src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks, src/scribe_mcp/tools/manage_docs.py, src/scribe_mcp/utils/files.py]
- input_contracts: [C-02, C-03, C-04, C-08, C-09, C-11]
- deliverable: PHASE_PLAN#sbr-document-durability plus CHECKLIST ids SBR-DOC-DUR.*
- dag_layer: 3
- parallelizable_with: [DA-03]
- blocked_by: []
- split_status: bounded at 4 files
- handoff_note: reuse atomic write, anchor CAS, apply-preview, and WAL; no second mutation engine.

### DA-09 — Core validation detail

- owned_subsystems: [SS-09]
- owned_paths: [tests/fixtures/swarm.py, tests/core/test_swarm_binding_reliability.py, tests/core/test_background_queue_contract.py, tests/core/test_wal_replay_exactly_once.py, tests/test_tool_runtime_repo_scope.py, tests/test_manage_docs_anchor_cas.py, tests/test_remote_backend.py]
- input_contracts: [C-01, C-02, C-03, C-04, C-08, C-09, C-11, C-12, C-13]
- deliverable: PHASE_PLAN#sbr-core-validation plus CHECKLIST ids SBR-CORE-VAL.*
- dag_layer: 4
- parallelizable_with: []
- blocked_by: []
- split_status: SPLIT_REQUIRED at 7 paths
- handoff_note: canonical test_agent only; manual clocks/events, no sleeps, no network, exact-effects oracle unchanged; isolate tests/test_remote_backend.py durable transport regression coverage in an independently verifiable task package.

### DA-10 — Stress/adapter/release evidence detail

- owned_subsystems: [SS-10]
- owned_paths: [tests/integration/test_swarm_concurrency_stress.py, tests/integration/storage/conftest.py, benchmarks/swarm_concurrency.py, tests/migration/mcp_v2/test_compatibility_matrix.py, tests/security/test_session_provenance.py, tests/test_release_startup_probe.py]
- input_contracts: [C-07, C-10, C-12, C-14]
- deliverable: PHASE_PLAN#sbr-release-validation plus CHECKLIST ids SBR-REL-VAL.*
- dag_layer: 5
- parallelizable_with: []
- blocked_by: []
- split_status: bounded at 6 files
- handoff_note: one repository-saturating operator lane; disposable state only; record environment and source revision.

### DA-11 — Release surfaces detail

- owned_subsystems: [SS-11]
- owned_paths: [pyproject.toml, src/scribe_mcp/__init__.py, README.md, docs/RELEASE_SURFACE.md, docs/RELEASE_FILE_MAP.md]
- input_contracts: [C-15]
- deliverable: PHASE_PLAN#sbr-release-closure plus CHECKLIST ids SBR-RELEASE.*
- dag_layer: 6
- parallelizable_with: []
- blocked_by: []
- split_status: bounded at 5 files
- handoff_note: update all version/public truth together to 2.15.0; one release commit boundary and one PR; no deploy or publish implied.
## Explicitly outside this SEAM_MAP
<!-- ID: exclusions -->

- Every path under /home/austin/projects/MCP_SPINE/council_mcp.
- Council/Aegis/work-item/provider-seat/spawn/bind-hook/roster/projection/completion/process reuse/process reap logic.
- Generated .council, .claude, .codex, AGENTS.md, and CLAUDE.md surfaces.
- Deployment, package publication, runtime restart/adoption, and production credentials.
- Provider-specific Codex or Claude behavior inside Scribe tests.
- A second swarm harness, queue implementation, document mutation engine, receipt store, or metrics result source.
- Full-suite execution; detail packages use targeted tests, direct neighbors, and import smoke only.
- Any release beyond the single 2.15.0 source release defined here.
## I1–I6 validation
<!-- ID: invariant_validation -->

### I1 — Pairwise-disjoint owned paths: PASS

- Compared all 63 owned path entries across 11 subsystem cards.
- Whole-file path intersection is empty.
- Shared physical files appear only through the exact anchors declared in the rationale.
- storage/base.py session-binding methods do not overlap new background-receipt methods.
- storage/postgres/__init__.py session-binding methods, setup method, and new background-receipt methods are distinct symbols.
- server.py startup-ready symbols do not overlap scheduling/drain/shutdown symbols.
- tests/test_remote_backend.py is owned only by SS-09; it validates the SS-01 remote binding transport contract without sharing src/scribe_mcp/storage/remote.py ownership.
- SQLite receipt DDL and document-runtime mutation hooks are single-owner anchors.
- A pass needing another anchor must stop for a map amendment.

### I2 — Acyclic DAG and valid layers: PASS

- Kahn/topological order covers all 11 nodes:
  - {SS-01, SS-06}
  - {SS-02, SS-04}
  - {SS-05, SS-07}
  - {SS-03, SS-08}
  - {SS-09}
  - {SS-10}
  - {SS-11}
- Every edge points from a lower layer to a higher layer; no back-edge exists.
- Maximum concurrent detail count is two, below the cap of three.

### I3 — One producer and complete consumption: PASS

- Each of C-01 through C-16 has exactly one producer.
- Every consumes_contracts entry resolves to one ledger contract.
- C-16 intentionally terminates at external council_mcp Atlas and creates no Scribe DAG edge.
- No Council contract is produced inside Scribe.

### I4 — Exactly one assignment per subsystem and bounded size: PASS

- SS-01 through SS-11 map one-to-one to DA-01 through DA-11.
- Assignment path-entry counts are 6, 6, 5, 6, 6, 6, 6, 4, 7, 6, and 5.
- SS-09/DA-09 is explicitly SPLIT_REQUIRED at seven paths; every other assignment remains at or below six.
- DA-09 must split its seven-path assignment into independently verifiable packages, and every detail pass must split any task package exceeding six files or one coherent behavior.

### I5 — Concrete contract surfaces: PASS

- Every contract names exact fields, signatures, states, precedence, or artifact shape.
- All 16 contracts are frozen.
- No consumer detail pass is blocked on a negotiable interface.
- Performance thresholds and error codes are explicit and testable.

### I6 — Complete in-boundary scope coverage: PASS

- Durable default, cross-project/cross-repo targeting, and typed errors: SS-01 and SS-02.
- Import/startup/object-store/schema weight: SS-03 and SS-04.
- Single-context hot path and telemetry: SS-05.
- Durable bounded background execution: SS-06 and SS-07.
- Managed-document durability/offline replay: SS-08.
- 32 callers, one set_project plus 100 mixed calls, remote-backend durable binding regression coverage, no interference/no-HOL, adapter parity, and budgets: SS-09 and SS-10.
- One SemVer release, governed commit boundary, PR, and public docs: SS-11.
- External Council adapter: C-16 only, with no council_mcp owned path.
- The explicit OUT list covers orchestration, generated surfaces, deployment/publication, and duplicate systems.
- No required Scribe change surface is orphaned; no path is outside the standalone release boundary.
## Work-item acceptance attestation map
<!-- ID: acceptance_map -->

- A1: The header records Q2 arithmetic and fan_out; I1–I6 each carry concrete PASS evidence.
- A2: SS-01 through SS-11 cover binding/error, startup/import/schema, hot-path telemetry, bounded background execution, managed-document replay, concurrency validation, and release surfaces.
- A3: Frozen budgets include the 500 ms tripwire, startup/import/RSS/call targets, 32-session minimum, no interference/no-HOL, and one set_project followed by 100 mixed calls.
- A4: C-16 is the exact external Council adapter contract; no council_mcp path or concept is owned by a Scribe subsystem.
- A5: DA-01 through DA-11 are fresh-pass-ready and pairwise disjoint; DA-09 alone is SPLIT_REQUIRED at seven paths, every other assignment is at most six, batches remain below the concurrency cap, and work terminates at one 2.15.0 release commit boundary and one PR.
## Handoff verdict
<!-- ID: handoff -->

READY FOR ATLAS INVARIANT ACCEPTANCE.

Frozen decisions:

- The partition, C-01 through C-16, all performance/correctness budgets, the external adapter boundary, and version 2.15.0.
- The 11 one-to-one detail assignments and 7 dependency layers.
- No detail pass owns any Council path.

Negotiable decisions:

- None. A newly discovered source conflict must return as a map amendment rather than being decided by Forge or a detail pass.

Required next action:

1. Atlas accepts or rejects this map against I1–I6.
2. On acceptance, dispatch fresh Blueprint MODE=detail passes in the declared batches; no more than three in parallel.
3. Do not dispatch release closure until ReliabilityReleaseEvidenceV1 passes for the same source revision.
