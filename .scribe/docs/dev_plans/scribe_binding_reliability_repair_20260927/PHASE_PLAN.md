---
id: scribe_binding_reliability_repair_20260927-phase-plan
title: "Scribe Binding Reliability Release \u2014 Detail Assignment Plan"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: ready
version: '0.1'
last_updated: 2026-09-28 03:18:32 UTC
maintained_by: agent-20260928-031001-a8f2997e
created_by: agent-20260927-061418-642053d3
owners:
- Blueprint
related_docs: []
tags:
- binding
- reliability
- phase-plan
- detail-pass
summary: Align migration 007 planning contract with startup-safe legacy binding classification.
canonical_doc_type: phase_plan
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 06:24:30 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-09-28 03:18:32 UTC
  last_edited_by: agent-20260928-031001-a8f2997e
  last_action: apply_patch
  work_item_id: 79214097-cf6a-45d7-be29-5bf95e282e39
---
# Scribe Binding Reliability Release — Detail Assignment Plan

**Author:** Blueprint
**Version:** 2.15.0 plan
**Status:** Ready
**Accepted source:** `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`

Sections are ordered by the accepted DAG layers. They are stable custody regions for fresh `MODE=detail` passes. They intentionally contain no implementation task packages.

## DA-01 — Binding persistence detail
<!-- ID: sbr-binding-persistence -->
### APPROACH_SUMMARY

- Goal: implement frozen `C-01 SessionBindingStoreV2` and emit exact `C-05` migration input, without owning target resolution, schema execution, or Council identity.
- Files to modify: `storage/models.py`; `storage/base.py#session_binding_contract`; `storage/postgres/__init__.py#session_binding_storage`; `storage/sqlite/sessions.py`; `storage/sqlite/domain_facade.py#session_binding_facade`; `storage/remote.py#session_binding_transport` (all under `src/scribe_mcp/`).
- Files forbidden: every other source file; `tests/**`; SQLite/PostgreSQL schema and migration files; Council/generated/config/version surfaces.
- Out of scope: request resolution, MCP error envelopes, binding receipts, non-binding cache policy, bootstrap/DDL, Council identity, deployment, publication, and release changes.
- Verification: import-smoke every modified module; run named neighbor tests separately with `-s`; DA-09 proves the 32-session core oracle and DA-10 proves live PostgreSQL/Remote parity.
- Readiness: packages 1-4 are READY. Package 5 is CONTRACT-BLOCKED because frozen C-01 requires durable Remote transport while unowned `tests/test_remote_backend.py:138-167,367-381` requires binding methods to remain in-memory/no-HTTP; Atlas must assign that stale test expectation before Forge starts package 5.

### Task Package: SBR-BIND-PERSIST.1 — Generation record and C-05 input

**Goal**
- Add the single shared binding record and freeze migration 007's SS-01 input.

**Depends On**
- None.

**Files to Read**
- SS-01/C-01/C-05 in the SEAM_MAP; architecture storage section; `src/scribe_mcp/storage/models.py`; existing `sqlite/schema.py` and `db/init.sql` shapes.

**Files to Modify**
- `src/scribe_mcp/storage/models.py`: add `SessionBindingRecordV2` only.

**Files Forbidden**
- All other source/test paths, especially SS-04 schema/migration ownership.

**Public Contracts / Signatures**
- `SessionBindingRecordV2(caller_session_key_hash: str, project_key: str, project_name: str, canonical_repo_root: str, binding_generation: int, updated_at: datetime)`.
- First generation is `1`; generation is at least 1; timestamp is timezone-aware.

**Migration Inputs**
- Migration 007 adds `project_key` and `binding_generation` to `session_projects`, preserves `project_name` for display/compatibility and `session_id` as unique authority, and backfills live rows to generation 1.
- Backfill resolves a legacy row only when its session identity, canonical repository root, and project name identify exactly one project. Zero matches, multiple matches, absent project name, missing session identity, or missing resolved project key remain preserved with `project_key=NULL`, `binding_state='unresolved'`, and stable reasons `project_identity_zero_matches`, `project_identity_ambiguous`, `project_name_absent`, `session_missing`, or `project_key_missing`; they cannot drive keyed writes, do not abort server startup, and never guess a project. This package emits no DDL.

**Implementation Constraints**
1. Reuse the model module/validation helpers; no parallel model.
2. Expose only SHA-256 of caller session key; raw `session_id` stays private.
3. Persisted project identity is authoritative; agent/persona and ambient state are not.
4. Keep the value object free of SQL, HTTP, Council, and runtime resolution.

**Required Tests**
- DA-09 owns `tests/core/test_swarm_binding_reliability.py::test_session_binding_record_v2_rejects_invalid_generation_and_naive_timestamp`.

**Verification Commands**
- `./.venv/bin/python -c 'from scribe_mcp.storage.models import SessionBindingRecordV2; print(SessionBindingRecordV2.__name__)'`
- `./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_sqlite_session_linkage_invariants -q`

**Acceptance Criteria**
- [ ] Exact six fields/types; invalid generation/naive timestamp fail.
- [ ] C-05 input is sufficient for SS-04 without DDL authority here.
- [ ] No Council/persona/agent authority field.

**Out of Scope**
- Backend methods, DDL, target resolution, receipts, runtime errors.

**Handoff Notes**
- Forge: only `models.py`; STOP on wider need.
- Mantis: own compatibility regressions; do not weaken C-01.
- Crucible: add the named disposable core test.
- Sentinel: verify hash-only caller exposure.
- Arbiter: reject duplicate models or schema work.

### Task Package: SBR-BIND-PERSIST.2 — Abstract generation/CAS contract

**Goal**
- Replace the name-only abstract methods with frozen C-01 idempotency and CAS semantics.

**Depends On**
- `SBR-BIND-PERSIST.1`.

**Files to Read**
- `src/scribe_mcp/storage/base.py`; `storage/models.py`.

**Files to Modify**
- `src/scribe_mcp/storage/base.py#session_binding_contract`: two methods and model import only.

**Files Forbidden**
- Every other `StorageBackend` method and file.

**Public Contracts / Signatures**
- `async set_session_project(self, session_id: str, project_key: str, expected_generation: int | None = None) -> SessionBindingRecordV2`.
- `async get_session_project(self, session_id: str) -> SessionBindingRecordV2 | None`.

**Implementation Constraints**
1. First bind is generation 1; changed target increments once; unchanged target returns the existing record/timestamp.
2. Unchanged bind performs zero persistent writes. Supplied stale generation fails before any write, including same-target requests; omitted generation uses current truth.
3. Missing session/project or stale generation uses existing storage conflict semantics; SS-02 owns MCP translation.
4. Agent/persona cannot enter signature or partition key.

**Required Tests**
- DA-09 owns `test_binding_contract_generation_and_zero_write_semantics` in the core swarm module.

**Verification Commands**
- `./.venv/bin/python -c 'from scribe_mcp.storage.base import StorageBackend; from scribe_mcp.storage.models import SessionBindingRecordV2; print(StorageBackend.set_session_project.__name__)'`

**Acceptance Criteria**
- [ ] Exact C-01 signatures and backend-neutral first/change/no-op/stale behavior.
- [ ] Expected failures remain storage conflicts, not MCP envelopes.

**Out of Scope**
- Concrete backends, schema, resolution, error translation.

**Handoff Notes**
- Forge: only two methods/import.
- Mantis: signature drift is a contract defect.
- Crucible: validate through DA-09 backend matrix.
- Sentinel: verify caller-session-only authority.
- Arbiter: reject aliases preserving string-return behavior.

### Task Package: SBR-BIND-PERSIST.3 — PostgreSQL atomic persistence

**Goal**
- Implement atomic PostgreSQL generation, CAS, and zero-write no-op behavior.

**Depends On**
- `.1`, `.2`, and SS-04 migration 007 in the validation substrate.

**Files to Read**
- `storage/postgres/__init__.py:1837-1863`; `tests/storage/test_session_storage_invariants.py`; shared storage contract test.

**Files to Modify**
- `src/scribe_mcp/storage/postgres/__init__.py#session_binding_storage`: two methods and private row mapper only.

**Files Forbidden**
- `PostgresStorage.setup`, migration helpers, unrelated queries/tests/paths.

**Public Contracts / Signatures**
- Implement both package-2 C-01 methods exactly.

**Implementation Constraints**
1. Resolve `project_key` to persisted name/root inside the transaction.
2. Lock caller/binding truth, enforce expectation, atomically insert generation 1 or change at `current + 1`.
3. Same target returns without `UPDATE`, timestamp change, or generation advance.
4. Same-session races cannot claim one next generation; same-label/different-session callers remain independent.
5. Preserve live-session integrity; no DDL.

**Required Tests**
- Preserve `test_postgres_session_linkage_invariants`; DA-09 owns exact write-count/matrix tests; DA-10 owns live race stress.

**Verification Commands**
- `./.venv/bin/python -c 'from scribe_mcp.storage.postgres import PostgresStorage; print(PostgresStorage.set_session_project.__name__)'`
- `./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_postgres_session_linkage_invariants -q`
- `./.venv/bin/pytest -s tests/integration/storage/test_storage_backend_shared_contract.py::test_session_transport_mode_project_and_scoped_reuse_contract -q`

**Acceptance Criteria**
- [ ] First/change/no-op/stale outcomes match C-01.
- [ ] No-op has zero write and stable timestamp.
- [ ] Session ID alone isolates same-label callers.
- [ ] Record identity comes from persisted project.

**Out of Scope**
- Setup, migrations, pools, project APIs, SS-02 runtime.

**Handoff Notes**
- Forge: stay inside anchor.
- Mantis: reproduce races with two tasks/one disposable session.
- Crucible: assert exact writes/generations.
- Sentinel: review SQL parameterization, raw-key exposure, fail-closed CAS.
- Arbiter: require one transactional path.

### Task Package: SBR-BIND-PERSIST.4 — SQLite parity and facade

**Goal**
- Match PostgreSQL behavior while preserving SQLite's write lock and session guard.

**Depends On**
- `.1`, `.2`, and SS-04 SQLite baseline readiness.

**Files to Read**
- `storage/sqlite/sessions.py:122-164`; `storage/sqlite/domain_facade.py:197-213`; session invariant tests.

**Files to Modify**
- `src/scribe_mcp/storage/sqlite/sessions.py`: binding helpers/types/imports only.
- `src/scribe_mcp/storage/sqlite/domain_facade.py#session_binding_facade`: two delegates only.

**Files Forbidden**
- `storage/sqlite/schema.py`, other SQLite domains, tests, non-SS-01 paths.

**Public Contracts / Signatures**
- Facade exposes exact C-01; helpers keep injected initialize/read/write collaborators and return typed records.

**Implementation Constraints**
1. Under `write_lock`, read truth, enforce CAS, and skip `execute_fn` on unchanged target.
2. First/change/stale/missing outcomes equal PostgreSQL.
3. Readback joins persisted project identity.
4. Session ID, never label, is the partition.
5. Consume SS-04 schema; do not alter DDL.

**Required Tests**
- Preserve `test_sqlite_session_linkage_invariants`; DA-09 owns SQLite/PostgreSQL parity and 32-session matrix.

**Verification Commands**
- `./.venv/bin/python -c 'from scribe_mcp.storage.sqlite.domain_facade import SQLiteDomainFacadeMixin; from scribe_mcp.storage.sqlite import sessions; print(SQLiteDomainFacadeMixin.set_session_project.__name__, sessions.set_session_project.__name__)'`
- `./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_sqlite_session_linkage_invariants -q`
- `./.venv/bin/pytest -s tests/integration/storage/test_storage_backend_shared_contract.py::test_session_transport_mode_project_and_scoped_reuse_contract -q`

**Acceptance Criteria**
- [ ] Record, generation, no-op, conflict, and same-label isolation equal PostgreSQL.
- [ ] Unchanged bind calls no writer; unknown-session conflict remains.

**Out of Scope**
- Schema, non-binding session methods, runtime resolution.

**Handoff Notes**
- Forge: helper/facade only.
- Mantis: deterministic lock/CAS reproducer for failures.
- Crucible: compare records/write counts across backends.
- Sentinel: verify raw keys stay private.
- Arbiter: reject backend-specific behavior.

### Task Package: SBR-BIND-PERSIST.5 — Remote durable transport parity

**Goal**
- Use existing authenticated backend transport for C-01; local process map is never authoritative binding truth.

**Depends On**
- `.1`, `.2`, and accepted `SBR-ARCH-AMEND-REMOTE-08`.

**Files to Read**
- `storage/remote.py:41-77,189-216,470-507`; stale `tests/test_remote_backend.py:138-167,367-381` remains read-only context.

**Files to Modify**
- `src/scribe_mcp/storage/remote.py#session_binding_transport`: strict decoder, cache typing, two methods only.

**Files Forbidden**
- Tests; other Remote methods/routes; Council paths.

**Public Contracts / Signatures**
- Exact C-01 methods; payload/response uses the six record field names.

**Implementation Constraints**
1. Delegate set/get through authenticated `_call`; remote authoritative backend decides generation/CAS/no-write.
2. Strictly decode all fields and reject malformed/naive responses.
3. Local cache may mirror success for cleanup/diagnostics but cannot satisfy authoritative get after reconnect/failure.
4. Preserve remote error mapping and public-release prohibition.
5. Do not broaden endpoints or alter unrelated session behavior.

**Required Tests**
- This is a source-only package. `SBR-CORE-VAL.1` creates the swarm proof and `SBR-CORE-VAL.5` replaces stale Remote binding expectations; both remain mandatory before release. DA-10 owns live adapter proof.

**Verification Commands**
- `./.venv/bin/python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; print(RemoteStorageBackend.set_session_project.__name__)'`
- `./.venv/bin/python -m py_compile src/scribe_mcp/storage/remote.py`
- `./.venv/bin/pytest -q tests/test_remote_backend.py::TestRemoteAuth tests/test_remote_backend.py::TestErrorHandling`
- `git diff --check -- src/scribe_mcp/storage/remote.py`

**Acceptance Criteria**
- [ ] Remote source strictly decodes the six-field record and delegates generation/CAS/no-write to authenticated durable transport.
- [ ] Restart/reconnect cannot replace durable truth with empty local cache.
- [ ] Same-label sessions partition only by session key.
- [ ] Missing swarm and stale Remote expectations remain explicitly owned by mandatory downstream `SBR-CORE-VAL.1` and `.5`.

**Out of Scope**
- Other session methods, new routes, resolution, deployment, test mutation.

**Handoff Notes**
- Forge: source anchor only.
- Mantis: own decoder/transport regressions after reproducer.
- Crucible: execute current source checks; full parity remains in CORE-VAL.1/.5.
- Sentinel: review auth, raw-key exposure, malformed response.
- Arbiter: reject client-local authoritative truth.

### DA-01 Dependency and Review Order

1. Implement `.1`, then `.2`.
2. SS-04 consumes C-05 and makes schema ready.
3. Implement `.3` and `.4` in parallel; `.5` only after amendment.
4. DA-09 runs core 32-session/no-write oracle; DA-10 runs live PostgreSQL/Remote proof.
5. Sentinel and Arbiter PASS before SS-02 consumes C-01.
## DA-06 — Durable receipt store detail
<!-- ID: sbr-receipt-store -->

### APPROACH_SUMMARY

- Goal: expose one host-neutral durable receipt-store boundary that implements frozen C-06/C-08 without scheduling workers or executing mutations.
- Files to modify: exactly the six SS-06 paths listed below, partitioned across `SBR-RECEIPT.1` through `.3`.
- Files forbidden: every unlisted source/test/config/generated/Council path; especially migration 007 and baseline schema files owned by DA-04, scheduler/lifecycle files owned by DA-07, mutation execution files owned by DA-08, and validation fixtures/tests owned by DA-09/DA-10.
- Out of scope: worker scheduling, fairness policy, retry policy selection, document effects, MCP/Council/provider semantics, schema/version/public-release edits, deployment, and runtime adoption.
- Verification plan: contract/import proof first, SQLite behavior second, PostgreSQL parity third; behavioral tests are exact downstream DA-09/DA-10 targets and the existing apply-preview/storage neighbor suites remain green.

Frozen surfaces: C-06 persists `operation_id`, `canonical_project_key`, `lane`, `idempotency_key`, `payload_digest`, `payload_bytes`, `durability_class`, `state`, `state_version`, `attempt_count`, `next_attempt_at`, `lease_owner`, `lease_expires_at`, `fencing_token`, `cancel_requested`, `result_ref`, `error_code`, `created_at`, and `updated_at`. C-08 exposes `admit`, `get`, `claim`, `transition`, and `recover`; admission is atomic for item and serialized-byte limits and returns accepted, duplicate, digest-conflict, busy, or shutting-down outcomes.

### Task Package: SBR-RECEIPT.1 — Host-neutral receipt models and storage contract

**Goal**

- Define the closed receipt state machine, typed outcomes, façade, and backend contract once. This package owns no persistence SQL.

**Depends On**

- None. It produces the source contract consumed by `SBR-RECEIPT.2`, `SBR-RECEIPT.3`, DA-04/C-06 schema materialization, and DA-07/DA-08/DA-09 consumers.

**Files to Read**

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SS-06, C-06, C-08, DA-06.
- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F2, F5, F6, and Q1/Q2.
- `src/scribe_mcp/storage/models.py` (`ApplyPreviewReceiptRecord` validation pattern).
- `src/scribe_mcp/storage/base.py` (`StorageBackend` fail-closed receipt methods).

**Files to Modify**

- `src/scribe_mcp/background/models.py` — new canonical background receipt types only.
- `src/scribe_mcp/background/store.py` — `BackgroundReceiptStoreV1` façade only.
- `src/scribe_mcp/storage/base.py#background_receipt_contract` — five fail-closed backend methods only.

**Files Forbidden**

- The other three SS-06 backend adapter paths until their packages run.
- `src/scribe_mcp/storage/models.py`; all schema/migration files; all scheduler, server, document-management, MCP, Council, config, version, and test files.

**Public Contracts / Signatures**

- `BackgroundReceiptState = Literal["accepted", "ready", "leased", "retry_wait", "succeeded", "failed_terminal", "cancelled"]`.
- `BackgroundLane = Literal["control", "durable", "heavy"]`.
- `BackgroundOperationIntentV1(operation_id: str, canonical_project_key: str, lane: BackgroundLane, idempotency_key: str, payload_digest: str, payload_bytes: int, durability_class: str, created_at: datetime)`.
- `BackgroundQueueLimitsV1(max_pending_items: int, max_pending_bytes: int, max_project_pending_items: int, max_project_pending_bytes: int, retry_after_ms: int, accepting: bool = True)`.
- `DurableOperationReceiptV1(operation_id: str, canonical_project_key: str, lane: BackgroundLane, idempotency_key: str, payload_digest: str, payload_bytes: int, durability_class: str, state: BackgroundReceiptState, state_version: int, attempt_count: int, next_attempt_at: datetime | None, lease_owner: str | None, lease_expires_at: datetime | None, fencing_token: int, cancel_requested: bool, result_ref: str | None, error_code: str | None, created_at: datetime, updated_at: datetime)`.
- `BackgroundAdmissionResultV1(status: Literal["accepted", "duplicate", "digest_conflict", "busy", "shutting_down"], receipt: DurableOperationReceiptV1 | None, retry_after_ms: int | None)`.
- `BackgroundPartitionV1(canonical_project_key: str, lane: BackgroundLane)`.
- `BackgroundTransitionOutcomeV1(state: BackgroundReceiptState, next_attempt_at: datetime | None = None, cancel_requested: bool = False, result_ref: str | None = None, error_code: str | None = None)`.
- `BackgroundRecoverySnapshotV1(receipts: tuple[DurableOperationReceiptV1, ...], pending_items: int, pending_bytes: int, reclaimable_operation_ids: tuple[str, ...])`.
- `BackgroundReceiptNotFoundError`, `BackgroundStateVersionConflictError`, and `BackgroundStaleFenceError` are the only transition exceptions; admission uses `BackgroundAdmissionResultV1`, never exceptions for duplicate/conflict/busy/shutdown.
- `BackgroundReceiptStoreV1.__init__(backend: StorageBackend, *, clock: Callable[[], datetime]) -> None`.
- `BackgroundReceiptStoreV1.admit(intent: BackgroundOperationIntentV1, limits: BackgroundQueueLimitsV1) -> BackgroundAdmissionResultV1`.
- `BackgroundReceiptStoreV1.get(operation_id: str) -> DurableOperationReceiptV1 | None`.
- `BackgroundReceiptStoreV1.claim(partition: BackgroundPartitionV1, worker_id: str, lease_ms: int) -> DurableOperationReceiptV1 | None`.
- `BackgroundReceiptStoreV1.transition(operation_id: str, expected_state_version: int, fencing_token: int, outcome: BackgroundTransitionOutcomeV1) -> DurableOperationReceiptV1`.
- `BackgroundReceiptStoreV1.recover(now: datetime) -> BackgroundRecoverySnapshotV1`.
- `StorageBackend` adds matching `admit_background_receipt(..., now)`, `get_background_receipt(...)`, `claim_background_receipt(..., now)`, `transition_background_receipt(..., now)`, and `recover_background_receipts(now)` async methods; defaults raise `NotImplementedError` exactly as apply-preview storage does.

**Implementation Constraints**

1. Use frozen dataclasses and closed `Literal`/frozenset domains. Validate non-empty identifiers, 64-character lowercase SHA-256 digests, non-negative byte/attempt/fence values, positive versions/limits/lease durations, and timezone-aware timestamps.
2. Initial receipts are `accepted`, `state_version=1`, `attempt_count=0`, `fencing_token=0`, with no lease/result/error. Every successful mutation increments `state_version` exactly once; failed CAS/fence checks mutate nothing.
3. Legal transitions are `accepted -> ready|cancelled`, `ready -> leased|cancelled`, `leased -> retry_wait|succeeded|failed_terminal|cancelled`, `retry_wait -> leased|cancelled`; terminal states never transition. `claim` is the only operation that enters `leased`, increments `attempt_count`, and increments `fencing_token`.
4. `transition` from `leased` requires the current fencing token. Stale fences and state-version mismatches are distinct typed failures. Leaving `leased` clears owner/expiry; terminal outcomes clear retry time and carry only contract-appropriate result/error fields.
5. `recover` is read/reconstruction only: it counts every nonterminal receipt (`accepted`, `ready`, `leased`, `retry_wait`), identifies expired leased rows as reclaimable, and never runs work or rewrites receipts. A later `claim` performs the fenced reclaim.
6. The façade injects one clock and delegates; it contains no scheduler, fairness, retry-backoff, document, host, or provider logic. Reuse `StorageBackend`; do not create a second persistence abstraction.

**Required Tests**

- DA-09/Crucible adds `tests/storage/test_background_receipt_contract.py` proving frozen dataclass validation, the legal transition matrix, exact method signatures, fail-closed backend defaults, deterministic clock propagation, version CAS, stale-fence classification, and recovery accounting. SS-06 Forge does not edit that test path.
- Regression neighbors: `tests/storage/test_apply_preview_receipt_contract.py` and `tests/test_storage_factory_backends.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.models import BackgroundAdmissionResultV1, BackgroundOperationIntentV1, BackgroundQueueLimitsV1, BackgroundRecoverySnapshotV1, BackgroundTransitionOutcomeV1, DurableOperationReceiptV1; from scribe_mcp.background.store import BackgroundReceiptStoreV1; from scribe_mcp.storage.base import StorageBackend'`
- `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py` (after DA-09 owns the test).
- `./.venv/bin/pytest -q tests/storage/test_apply_preview_receipt_contract.py tests/test_storage_factory_backends.py`.

**Acceptance Criteria**

- [ ] C-08 public names and signatures are importable and host-neutral.
- [ ] Closed states, version/fence invariants, terminal immutability, and recovery accounting are enforced by models plus façade/backend contract.
- [ ] Unsupported backends fail closed; no fallback to memory or apply-preview storage exists.

**Out of Scope**

- SQL, DDL, scheduler choice, retry timing policy, effects, document replay, MCP error rendering, Council/provider logic, and test-file edits.

**Handoff Notes**

- Forge: stop if an additional source path or a changed C-06/C-08 field/signature is needed.
- Crucible: own the named contract test under DA-09 and prove every acceptance item without sleeps.
- Sentinel: review identifier/digest validation, result/error-reference data exposure, untrusted byte claims, and denial-of-service bounds.
- Arbiter: require one façade/one backend contract, closed state semantics, and no duplicate queue abstraction.

### Task Package: SBR-RECEIPT.2 — SQLite atomic receipt persistence

**Goal**

- Implement SQLite admission, lookup, fenced claim/transition, and restart reconstruction behind the shared contract, using the existing SQLite locking/WAL helpers.

**Depends On**

- `SBR-RECEIPT.1`.
- Behavioral validation depends on DA-04 materializing frozen C-06 in the SQLite baseline/migration; this package must not edit those schema files.

**Files to Read**

- `src/scribe_mcp/storage/sqlite/internals.py` (`SQLiteInternals` connection, write-gate, WAL, busy-retry behavior).
- `src/scribe_mcp/storage/sqlite/apply_preview_receipts.py` and its SQLite tests.
- DA-04 C-06 schema package/readback before behavioral validation.

**Files to Modify**

- `src/scribe_mcp/storage/sqlite/background_receipts.py` — SQLite operations and row decoder.
- `src/scribe_mcp/storage/sqlite/__init__.py#background_receipt_adapter` — imports plus five contract adapters only.

**Files Forbidden**

- `src/scribe_mcp/storage/sqlite/internals.py`, `schema.py`, migrations, apply-preview modules, every PostgreSQL file, every scheduler/document/MCP/Council/config/version/test file.

**Public Contracts / Signatures**

- `SQLiteStorage.admit_background_receipt(intent, limits, *, now) -> BackgroundAdmissionResultV1`.
- `SQLiteStorage.get_background_receipt(operation_id) -> DurableOperationReceiptV1 | None`.
- `SQLiteStorage.claim_background_receipt(partition, worker_id, lease_ms, *, now) -> DurableOperationReceiptV1 | None`.
- `SQLiteStorage.transition_background_receipt(operation_id, expected_state_version, fencing_token, outcome, *, now) -> DurableOperationReceiptV1`.
- `SQLiteStorage.recover_background_receipts(now) -> BackgroundRecoverySnapshotV1`.
- Module functions in `background_receipts.py` use keyword-only injected `initialise_fn`, existing SQLite query callbacks/lock, the same contract arguments, and the same return types; no second backend class.

**Implementation Constraints**

1. Decode every C-06 column into `DurableOperationReceiptV1` with timezone-aware timestamps and booleans/integers normalized identically to PostgreSQL.
2. Admission uses one write-critical section and an atomic `INSERT ... SELECT ... WHERE` capacity predicate. Count and sum all nonterminal states globally and for the canonical project; enforce item and byte maxima before insertion. Never split the capacity decision and insert across independently interleavable writes.
3. The unique `(canonical_project_key, idempotency_key)` row is authoritative: same digest returns `duplicate` with the original row; different digest returns `digest_conflict`; both consume zero new capacity and mutate nothing. Closed admission returns `shutting_down`; an in-boundary capacity miss returns `busy` with bounded `retry_after_ms` and no row.
4. Claim uses one conditional `UPDATE ... RETURNING` over the deterministic oldest eligible row in the requested canonical project/lane: `ready`, due `retry_wait`, or expired `leased`. It sets owner/expiry, increments attempt/version/fence once, and cannot grant two active leases.
5. Transition uses `WHERE operation_id=? AND state_version=? AND fencing_token=?` plus legal-state predicates and `RETURNING`. Classify no-row results as not-found, version conflict, or stale fence without mutation; release capacity only by entering a terminal state once.
6. Recovery is a read-only ordered query over all nonterminal rows, reconstructs exact item/byte totals, and reports expired leased operations as reclaimable. Reopening `SQLiteStorage` must return the same receipts and totals.
7. Reuse `_initialise`, `_write_lock`, `SQLiteInternals` query/busy-retry behavior, and WAL configuration. Do not open an ad hoc database, add a second pool, add sleeps, or copy apply-preview tables/logic.

**Required Tests**

- DA-09/Crucible adds `tests/storage/test_sqlite_background_receipts.py`: exact item/byte boundary, 32-way last-slot race, duplicate/digest conflict zero mutation, retry-wait capacity retention, terminal release once, deterministic claim order, lease expiry/higher fence, stale completion rejection, version CAS, reopen recovery, and no accepted row on busy/shutdown.
- Existing neighbors `tests/storage/test_sqlite_apply_preview_receipts.py` and `tests/integration/storage/test_storage_backend_shared_contract.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.sqlite.background_receipts import admit_background_receipt, claim_background_receipt, get_background_receipt, recover_background_receipts, transition_background_receipt'`
- `./.venv/bin/pytest -q tests/storage/test_sqlite_background_receipts.py` (after DA-04 schema and DA-09 test ownership land).
- `./.venv/bin/pytest -q tests/storage/test_sqlite_apply_preview_receipts.py tests/integration/storage/test_storage_backend_shared_contract.py`.

**Acceptance Criteria**

- [ ] SQLite never exceeds configured global/per-project item or byte limits, including under 32 concurrent admissions.
- [ ] Duplicate, digest-conflict, busy, and shutdown outcomes create no hidden row or capacity drift.
- [ ] State versions and fencing reject stale writers; fresh reopen reconstructs every accepted nonterminal receipt and exact capacity.

**Out of Scope**

- C-06 DDL, PostgreSQL, scheduling/fairness, retry calculation, worker/effect execution, document mutation, Council/provider semantics, and test-file edits.

**Handoff Notes**

- Forge: implement only the two owned paths and stop on any need to alter SQLite internals/schema.
- Crucible: use deterministic gates/manual time; no wall-clock sleeps or fake receipt store.
- Sentinel: inspect SQL parameterization, digest/idempotency isolation, byte-bound bypass, lock contention, stale-fence enforcement, and secret-bearing fields.
- Arbiter: compare against existing SQLite apply-preview durability patterns and reject duplicated pool/transaction infrastructure.

### Task Package: SBR-RECEIPT.3 — PostgreSQL atomic persistence and backend parity

**Goal**

- Implement the same receipt semantics on PostgreSQL with transaction-safe capacity admission and multi-worker fenced claiming.

**Depends On**

- `SBR-RECEIPT.1`.
- Behavioral validation depends on DA-04 migration 007/C-06 being present in a disposable PostgreSQL schema and on `SBR-RECEIPT.2` defining the parity baseline.

**Files to Read**

- `src/scribe_mcp/storage/postgres/__init__.py` apply-preview receipt methods, pool helpers, and row decoders.
- `src/scribe_mcp/storage/postgres/internals.py` pool lifecycle.
- `tests/integration/storage/test_postgres_apply_preview_receipts.py` and `test_apply_preview_backend_parity.py` as neighboring patterns.

**Files to Modify**

- `src/scribe_mcp/storage/postgres/__init__.py#background_receipt_storage` — imports, decoder, and five contract methods only.

**Files Forbidden**

- All PostgreSQL schema/migration/document/internal files; all SQLite/background model/facade paths after prior packages; all scheduler/document/MCP/Council/config/version/test files.

**Public Contracts / Signatures**

- `PostgresStorage.admit_background_receipt(intent, limits, *, now) -> BackgroundAdmissionResultV1`.
- `PostgresStorage.get_background_receipt(operation_id) -> DurableOperationReceiptV1 | None`.
- `PostgresStorage.claim_background_receipt(partition, worker_id, lease_ms, *, now) -> DurableOperationReceiptV1 | None`.
- `PostgresStorage.transition_background_receipt(operation_id, expected_state_version, fencing_token, outcome, *, now) -> DurableOperationReceiptV1`.
- `PostgresStorage.recover_background_receipts(now) -> BackgroundRecoverySnapshotV1`.

**Implementation Constraints**

1. Reuse `PostgresStorage._ensure_pool()` and asyncpg; all SQL is parameterized and schema-qualified by the existing backend rules. Do not create another pool or storage class.
2. Admission runs in one transaction. Acquire deterministic transaction-scoped advisory locks for the global receipt-capacity key and canonical project key, then classify existing idempotency row before capacity. Same digest returns duplicate; different digest returns conflict; otherwise count/sum nonterminal global/project items and bytes and insert only when all four bounds permit.
3. Serializable retry, if needed, is finite and bounded inside the method; no sleep loop is added. Unique races are re-read and classified as duplicate or digest conflict, never surfaced as an untyped integrity failure.
4. Claim uses one `FOR UPDATE SKIP LOCKED` CTE plus `UPDATE ... RETURNING` to select the deterministic oldest eligible row in the partition, including expired leases. Exactly one worker receives it; attempt/version/fence each increment once and lease timestamps derive from the injected `now` plus `lease_ms`.
5. Transition is one conditional `UPDATE ... RETURNING` on operation, expected version, current fence, and legal source state. No-row classification distinguishes not-found/version-conflict/stale-fence without a mutation. Terminal rows are immutable and leave capacity accounting exactly once.
6. Recovery is read-only, ordered, and backend-neutral. It reconstructs the same receipts, nonterminal item/byte totals, and reclaimable expired leases as SQLite for the same seeded rows.
7. Preserve the existing apply-preview receipt behavior and startup/pool semantics. PostgreSQL-specific record/JSON/timestamp coercion must not leak into C-08 return values.

**Required Tests**

- DA-10/Crucible adds `tests/integration/storage/test_postgres_background_receipts.py`: concurrent last-item/byte admission, idempotency/digest race, `SKIP LOCKED` claim exclusivity, worker-death lease recovery, stale-fence/version rejection, terminal release, and fresh-runtime recovery in a throwaway schema.
- DA-10/Crucible adds `tests/integration/storage/test_background_receipt_backend_parity.py`: identical seeded operations produce equal normalized SQLite/PostgreSQL admission, claim, transition, conflict, and recovery outcomes.
- Existing neighbors `tests/integration/storage/test_postgres_apply_preview_receipts.py` and `tests/integration/storage/test_apply_preview_backend_parity.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.postgres import PostgresStorage'`
- `./.venv/bin/pytest -q tests/integration/storage/test_postgres_background_receipts.py tests/integration/storage/test_background_receipt_backend_parity.py` (single repository-saturating PostgreSQL lane; only after DA-04 and DA-10 test ownership land).
- `./.venv/bin/pytest -q tests/integration/storage/test_postgres_apply_preview_receipts.py tests/integration/storage/test_apply_preview_backend_parity.py`.

**Acceptance Criteria**

- [ ] PostgreSQL atomically enforces the same global/per-project item and byte limits as SQLite under concurrent processes.
- [ ] One eligible receipt has at most one active lease; expired leases reclaim with a higher fence and stale completions cannot transition.
- [ ] Normalized admission, receipt, transition, and recovery results are backend-identical for the parity corpus.

**Out of Scope**

- DDL/migration authoring, scheduler/fairness, worker/effect execution, document mutation/replay, MCP/Council/provider behavior, operational deployment, and test-file edits.

**Handoff Notes**

- Forge: touch only the declared symbol block; stop if pool/schema/internal files are needed.
- Crucible: run this as the one held PostgreSQL/process lane and retain raw concurrency counts.
- Sentinel: mandatory review of advisory-lock scope/order, serialization/unique-race handling, project partition isolation, SQL parameterization, stale fences, and stored reference fields.
- Arbiter: mandatory review for C-08 parity, minimality, reuse of the current pool, and absence of backend-specific public behavior.

### Package order and gate

1. Implement `SBR-RECEIPT.1`.
2. Implement `.2` and `.3` in parallel only after `.1`; do not claim behavioral completion until DA-04 has materialized C-06.
3. DA-09 supplies hermetic contract/SQLite proof; DA-10 alone owns the PostgreSQL/process parity lane.
4. Sentinel and Arbiter PASS are mandatory for all three packages because SS-06 is schema-, durability-, concurrency-, and high-blast-radius sensitive.

## DA-02 — Target resolution and typed errors detail
<!-- ID: sbr-target-resolution -->

### APPROACH_SUMMARY

- Goal: make one server-verified caller-session default durable, resolve every later explicit target request-locally without changing that default, and carry one immutable context through a typed MCP boundary.
- Files to modify: exactly the six SS-02 paths, partitioned across `SBR-BIND-RESOLVE.1` through `.4`.
- Files forbidden: every unlisted source/test/config/generated/Council path; especially C-01 storage paths owned by DA-01, schema/bootstrap paths owned by DA-04, hot-path consumers owned by DA-05, and validation files owned by DA-09/DA-10.
- Out of scope: C-01 storage implementation, DDL/migrations, scheduling/background durability, Council seat/admission/Aegis/work-item/provider/projection logic, schema/version/release edits, deployment, and runtime adoption.
- Verification plan: contract/import proof, target-resolution/default-preservation proof, set-project receipt and delayed-second-write proof, then MCP-era/error/adaptor parity. DA-09 owns hermetic behavior and the 32-session × 100-call oracle; DA-10 owns real-adapter/process proof.

Frozen surfaces: C-01 is the only input. C-02 resolves `ProjectTargetV1` by project key, name plus canonical root, unique name, then caller default only when no explicit target exists. C-03 is `BindingReceiptV1`. C-04 is a structured `CallToolResult(isError=true)`. C-11 is one immutable `ResolvedRequestContextV1` per call. C-16 is host-neutral: an external host supplies only a server-verified caller-session key, optional target, and generic attribution; Scribe receives no Council vocabulary.

### Task Package: SBR-BIND-RESOLVE.1 — Immutable request and binding contract types

**Goal**

- Define C-02/C-03/C-11 data contracts and the one builder that keeps agent labels attribution-only. This package does not resolve or persist a project.

**Depends On**

- C-01 remains frozen. No source package dependency.

**Files to Read**

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SS-02 and C-01/C-02/C-03/C-11/C-16.
- `research/RESEARCH_BINDING_RCA.md` F4/F5/F6 and recommendations R1-R4.
- `src/scribe_mcp/shared/execution_context.py` application identity, `ExecutionContext`, and `RouterContextManager.build_execution_context`.
- `tests/security/test_session_provenance.py` and `tests/test_tool_runtime_repo_scope.py` as DA-10/DA-09 consumer contracts.

**Files to Modify**

- `src/scribe_mcp/shared/execution_context.py` — frozen public request/target/receipt/context dataclasses, validation, and the `ExecutionContext.resolved_request_context` slot only.

**Files Forbidden**

- The other five SS-02 files until their packages run; every storage, tool body, schema, Council, config, version, and test file.

**Public Contracts / Signatures**

- `ProjectTargetV1(project_key: str | None = None, project: str | None = None, repo_root: str | None = None)`.
- `ResolvedProjectTargetV1(project_key: str, project_name: str, canonical_repo_root: str, repository_id: str, resolution_source: Literal["project_key", "name_and_root", "unique_name", "caller_default"], default_binding_generation: int)`.
- `AgentAttributionV1(agent: str, agent_id: str | None = None)`; neither field participates in equality/keying for caller identity or target selection.
- `AuthorizationEvidenceV1(source: str, verified: bool, scope_refs: tuple[str, ...])`; values are opaque evidence references, never credentials.
- `BindingReceiptV1(ok: bool, caller_session_key_hash: str, project_key: str, project_name: str, canonical_repo_root: str, binding_generation: int, binding_reused: bool, persistent_write_performed: bool, resolution_source: str, correlation_id: str)`.
- `ResolvedRequestContextV1(caller_session_key_hash: str, resolved_target: ResolvedProjectTargetV1, default_binding_generation: int, agent_attribution: AgentAttributionV1, correlation_id: str, operating_mode: Literal["project", "sentinel"], authorization_evidence: AuthorizationEvidenceV1)`.
- `build_resolved_request_context(*, caller_session_key: str, resolved_target: ResolvedProjectTargetV1, agent_attribution: AgentAttributionV1, correlation_id: str, operating_mode: Literal["project", "sentinel"], authorization_evidence: AuthorizationEvidenceV1) -> ResolvedRequestContextV1`.
- `ExecutionContext.resolved_request_context: ResolvedRequestContextV1 | None`.

**Implementation Constraints**

1. Use `@dataclass(frozen=True, slots=True)` for every V1 value. Normalize roots with the existing path mapping before construction; reject blank identifiers, non-absolute canonical roots, non-positive binding generations, invalid modes/sources, and non-hex 64-character caller hashes.
2. Hash the raw caller-session key once with SHA-256 for public/audit fields. The raw key remains request-local and is never included in receipts, errors, logs, representations, equality, or serialized context.
3. `ProjectTargetV1` accepts zero to three selectors but rejects `repo_root` without `project`; conflicting selectors are resolved only by C-02 precedence, never silently discarded by the model.
4. `build_resolved_request_context` copies/finalizes tuple-backed evidence and attribution once. Downstream code receives the same frozen instance; no helper may reconstruct, mutate, or re-resolve it.
5. Keep `ApplicationIdentity` as the server-owned caller source. `agent`, persona, model, display name, and `agent_id` are metadata only and must not influence application/session keys, project partitions, or authorization.
6. Preserve existing `ExecutionContext` construction for sentinel diagnostics while allowing `resolved_request_context=None` only before target resolution and for explicitly unbound-safe diagnostics.

**Required Tests**

- DA-09/Crucible adds cases in `tests/test_tool_runtime_repo_scope.py` proving frozen values, validation, stable caller hash, attribution-only behavior, and object identity preservation through nested helpers.
- DA-10/Crucible extends `tests/security/test_session_provenance.py` so two same-label callers remain distinct only through server-owned application/session identities; changing only the label cannot create, steal, or recover a binding.
- Regression neighbors `tests/test_execution_context.py` and `tests/shared/test_actor_scoped_session_binding.py` remain green; any expectation that makes the label authoritative must be escalated as stale test ownership, not preserved in production behavior.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.execution_context import AgentAttributionV1, AuthorizationEvidenceV1, BindingReceiptV1, ProjectTargetV1, ResolvedProjectTargetV1, ResolvedRequestContextV1, build_resolved_request_context'`.
- `./.venv/bin/pytest -q tests/test_execution_context.py tests/shared/test_actor_scoped_session_binding.py`.
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/security/test_session_provenance.py` (after DA-09/DA-10 own their additions).

**Acceptance Criteria**

- [ ] C-02/C-03/C-11 names and fields are importable, frozen, validated, and contain no raw caller-session key.
- [ ] Same-label callers cannot collide; changing attribution cannot change caller identity, default, target, or authorization.
- [ ] One `ResolvedRequestContextV1` instance can be passed end to end without mutation or re-resolution.

**Out of Scope**

- Registry lookup, C-01 writes, tool dispatch, error rendering, Council/provider fields, and test-file edits.

**Handoff Notes**

- Forge: stop if another source path or a changed frozen field is needed.
- Crucible: own the named DA-09/DA-10 tests and assert object identity plus label non-authority.
- Sentinel: review raw-key non-disclosure, attribution separation, root validation, and evidence-reference exposure.
- Arbiter: require one canonical model set in `execution_context.py`; reject duplicate DTOs or mutable dict substitutes.

### Task Package: SBR-BIND-RESOLVE.2 — Registered project target resolution and default preservation

**Goal**

- Implement the single C-02 resolver over persisted project identity and C-01 default truth, including authorized cross-repository targets and fail-closed ambiguity.

**Depends On**

- `SBR-BIND-RESOLVE.1`.
- DA-01/C-01 storage methods and `SessionBindingRecordV2` must be importable.

**Files to Read**

- `research/RESEARCH_BINDING_RCA.md` F3-F5 and recommendations R2/R4.
- `research/RESEARCH_BINDING_EFFICIENCY_AND_OWNERSHIP.md` target-resolver and project-key findings.
- `src/scribe_mcp/shared/logging_utils.py::resolve_logging_context` and `ProjectResolutionError`.
- `src/scribe_mcp/state/manager.py::_fetch_project`, `_resolve_current_project`, and `_record_to_project_dict`.

**Files to Modify**

- `src/scribe_mcp/shared/logging_utils.py` — `resolve_project_target`, typed target-resolution failures, and reuse of a current immutable request context.
- `src/scribe_mcp/state/manager.py#registered_target_resolution` — persisted registry lookup/candidate enumeration only.

**Files Forbidden**

- `set_project.py`, `tool_runtime.py`, `mcp_adapter.py`, all C-01 backend implementations, schema, Council, config, version, and test files.

**Public Contracts / Signatures**

- `async resolve_project_target(caller_session_key: str, target: ProjectTargetV1 | None) -> ResolvedProjectTargetV1`.
- `StateManager.resolve_registered_project(*, project_key: str | None = None, project: str | None = None, repo_root: str | None = None) -> tuple[dict[str, Any] | None, tuple[dict[str, str], ...]]`.
- `ProjectResolutionError(message: str, *, error_code: str, target: ProjectTargetV1 | None, candidates: tuple[dict[str, str], ...] = (), remediation: str | None = None, retryable: bool = False)`.
- `resolve_logging_context(..., resolved_request_context: ResolvedRequestContextV1 | None = None, explicit_project: str | None = None, ...) -> LoggingContext`; the compatibility string is converted to `ProjectTargetV1(project=...)` once.

**Implementation Constraints**

1. Apply precedence exactly: explicit `project_key`; explicit `project+repo_root`; explicit unique `project`; C-01 caller default only when `target is None`. Never fall back from an explicit miss/ambiguity/root mismatch to the caller default, recents, global state, agent context, process root, or another repository.
2. Resolve from persisted project records and canonical roots. Name-only lookup succeeds only with one registered match; multiple matches return `SCRIBE_PROJECT_AMBIGUOUS` with stable candidates containing only project key, name, and canonical root.
3. A supplied key with mismatched name/root returns `SCRIBE_PROJECT_ROOT_MISMATCH`; missing keys/names return `SCRIBE_PROJECT_NOT_FOUND`; no default returns `SCRIBE_BINDING_MISSING`. All failure paths perform zero project/default/recent/document/file writes.
4. For `target=None`, read C-01 exactly once using the server-verified caller-session key and carry its generation into the resolved target. An explicit target may read the default only to report its generation; it never calls `set_session_project`, changes caches as authority, or updates recent/global pointers.
5. Replace the current repository-lock and label/agent fallback branches in `resolve_logging_context` with C-02. If `ResolvedRequestContextV1` is already current, consume its `resolved_target` directly and do not call the resolver again.
6. Keep compatibility recovery opt-in and diagnostic-only. No public-release operational authority may come from `current_project`, recent projects, JSON config discovery, `agent_id`, or the ambient repository.
7. Candidate ordering is deterministic by `(canonical_repo_root, project_name, project_key)`; messages and remediation never disclose credentials, raw caller keys, database details, or unrelated projects.

**Required Tests**

- DA-09/Crucible extends `tests/test_tool_runtime_repo_scope.py` with all four precedence cases, duplicate-name ambiguity, root mismatch, missing default, wrong target, stale ambient root, and zero default/recent/cache mutation after explicit same-repo and cross-repo calls.
- DA-09/Crucible adds the resolver cases to `tests/core/test_swarm_binding_reliability.py`: every caller performs five authorized cross-repo explicit operations and negative ambiguous/missing/wrong-target operations while its original default and generation remain unchanged.
- Existing neighbors `tests/test_logging_utils.py`, `tests/test_append_entry_explicit_project_resolution.py`, `tests/test_query_entries_explicit_project_resolution.py`, and `tests/security/test_project_binding_policy.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.logging_utils import ProjectResolutionError, resolve_project_target; from scribe_mcp.state.manager import StateManager'`.
- `./.venv/bin/pytest -q tests/test_logging_utils.py tests/test_append_entry_explicit_project_resolution.py tests/test_query_entries_explicit_project_resolution.py tests/security/test_project_binding_policy.py`.
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py` (after DA-09 owns the additions).

**Acceptance Criteria**

- [ ] Explicit targeting reaches any authorized registered project, including another repository, without `set_project` and without default mutation.
- [ ] Project-key/name-root/unique-name/default precedence is deterministic; ambiguity, missing, root mismatch, and wrong-target requests fail closed with stable candidates and zero effects.
- [ ] Agent/persona labels, recents, process globals, and ambient roots never select an operational target.

**Out of Scope**

- Binding writes/receipts, MCP result construction, Council authorization mapping, mutation execution, and test-file edits.

**Handoff Notes**

- Forge: reuse StateManager/backend registry APIs; do not add a second registry, filesystem scan, or repo-local resolver.
- Crucible: assert both returned target and absence of writes/caches/default-generation changes for every denial/explicit case.
- Sentinel: review cross-repo authorization, candidate minimization, canonical-root comparison, and fail-closed precedence.
- Arbiter: reject duplicated resolution paths or any remaining operational fallback to agent/global/recent state.

### Task Package: SBR-BIND-RESOLVE.3 — One-time default binding and BindingReceiptV1

**Goal**

- Make `set_project` the sole default-selection operation for the exact caller-session key and return C-03 for both changed and unchanged binds.

**Depends On**

- `SBR-BIND-RESOLVE.1` and `SBR-BIND-RESOLVE.2`.
- DA-01/C-01 implements generation-aware `get_session_project` and `set_session_project`.

**Files to Read**

- `src/scribe_mcp/tools/set_project.py::_describe_same_binding_reuse`, `set_project`, and structured/readable response paths.
- `src/scribe_mcp/state/manager.py::set_current_project` and session-project cache handling.
- 05:57 incident call/result refs `aitrace:v1:codex:b4c06068df6e3d5dd0f6e430517eec21`, `aitrace:v1:codex:171ebc79f97bf3301bf8128603182089`, `aitrace:v1:codex:5861b88846ea2e2f018c4f6d77f2b90c`, and `aitrace:v1:codex:8e861f0ca9ec3846527be3ef71a4c0ff`.

**Files to Modify**

- `src/scribe_mcp/tools/set_project.py` — exact-key C-01 bind, receipt construction, response/readable projection, and unchanged-bind fast path.
- `src/scribe_mcp/state/manager.py#session_binding_cache` — consume a completed C-01 record into in-process state without issuing another binding write.

**Files Forbidden**

- C-01 backend/model files, resolver/runtime/adapter files, schema, Council, config, version, and test files.

**Public Contracts / Signatures**

- Preserve the existing public `set_project(..., expected_generation: int | None = None, format: str = "readable", ...) -> dict[str, Any]`; every successful format includes one serialized `binding_receipt: BindingReceiptV1`.
- `StateManager.accept_session_binding(*, caller_session_key: str, record: SessionBindingRecordV2, project_data: dict[str, Any]) -> State`; cache/state projection only, with no C-01 write.
- The successful structured receipt uses `resolution_source="set_project"`; unchanged binds set `binding_reused=True` and `persistent_write_performed=False`; first/changed binds use `False/True`.

**Implementation Constraints**

1. Obtain the exact server-verified caller-session key; missing/unverified identity fails before project/default mutation. Do not derive or namespace it from `agent`, persona, model, display label, process-global state, repo root, or project name.
2. Resolve/upsert the registered project first, then call C-01 with its stable `project_key` and optional `expected_generation`. The returned record is the sole generation/default truth; project name is display compatibility only.
3. Compare the pre-bind record to the returned record to construct C-03. A same-target request still executes C-01 generation validation, but C-01 performs zero persistent writes and preserves `updated_at`; supplied stale generation returns `SCRIBE_BINDING_GENERATION_STALE` even for the same target.
4. After C-01 succeeds, update router/StateManager caches from that record without a second `set_session_project` call. Global and per-agent mirrors are compatibility/readability projections only and never default authority.
5. Emit the identical receipt fields for new, changed, unchanged/readable, structured, and compact responses. Existing project inventory/reminder behavior may remain, but it cannot alter the receipt or default.
6. Correlation ID is generated once per call and shared by C-03, C-11, audit, timing, and any C-04 failure. Hash the caller key via the canonical helper; never return the raw key.
7. The 05:57 regression is normative: after one successful bind and unrelated/idle activity, a later identical explicit-project append in the same caller session must succeed without another `set_project`; the immediate rebind workaround must no longer be necessary.

**Required Tests**

- DA-09/Crucible adds focused cases to `tests/test_tool_runtime_repo_scope.py` for first bind generation 1, changed target +1, unchanged zero-write/same timestamp, stale expected generation zero-write, exact receipt flags, and no label-keyed binding.
- DA-09/Crucible encodes the 05:57 regression in `tests/core/test_swarm_binding_reliability.py`: bind once; perform unrelated calls plus a deterministic barrier; issue the delayed second explicit-project append; assert success, `set_project_count == 1`, same default/generation, correct target, and no extra C-01 write.
- Existing neighbors `tests/test_set_project.py`, `tests/test_set_project_runtime_scope_contract.py`, `tests/test_set_project_integration.py`, and `tests/test_session_project_cache.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.set_project import set_project; from scribe_mcp.shared.execution_context import BindingReceiptV1; from scribe_mcp.state.manager import StateManager'`.
- `./.venv/bin/pytest -q tests/test_set_project.py tests/test_set_project_runtime_scope_contract.py tests/test_set_project_integration.py tests/test_session_project_cache.py`.
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py` (after DA-09 owns the regression).

**Acceptance Criteria**

- [ ] Every successful bind returns a complete C-03 receipt tied to the exact caller-session hash and stable project key.
- [ ] Unchanged bind and stale-generation failure perform zero persistent writes; changed target increments exactly once.
- [ ] The trace-derived delayed second write succeeds after one bind with no rebind/default drift.

**Out of Scope**

- Storage implementation, explicit-target execution, error-result normalization, inventory optimization, Council/provider state, and test-file edits.

**Handoff Notes**

- Forge: preserve all public parameters/formats and stop if C-01 cannot express the frozen generation/no-write contract.
- Crucible: instrument C-01 calls/writes and use deterministic events/barriers, never sleeps.
- Sentinel: review exact-key provenance, raw-key redaction, stale-generation ordering, root authorization, and receipt leakage.
- Arbiter: require one authoritative C-01 mutation and one C-03 projection; reject duplicate binding writes or label/global authority.

### Task Package: SBR-BIND-RESOLVE.4 — One-pass runtime context, typed MCP errors, and generic external adapter

**Goal**

- Resolve once at dispatch, install C-11 for the complete call, and translate every expected binding/project failure into C-04 across modern and legacy MCP adapters.

**Depends On**

- `SBR-BIND-RESOLVE.1`, `.2`, and `.3`.

**Files to Read**

- `src/scribe_mcp/shared/tool_runtime.py::resolve_context_authoritative_session_key` and `execute_tool_call`.
- `src/scribe_mcp/mcp_adapter.py::normalize_tool_result` and `configure_mcp_server.call_tool_bound`.
- `tests/test_mcp_adapter.py`, `tests/test_tool_runtime_repo_scope.py`, `tests/security/test_session_provenance.py`, and `tests/migration/mcp_v2/test_compatibility_matrix.py`.

**Files to Modify**

- `src/scribe_mcp/shared/tool_runtime.py` — exact caller-key selection, single C-02 resolution, C-11 installation, and expected-error raising only.
- `src/scribe_mcp/mcp_adapter.py` — `ScribeErrorV1`, expected-error carrier/normalizer, and modern/legacy `CallToolResult` construction.

**Files Forbidden**

- The other four SS-02 paths after their packages land; all tool bodies, storage/schema, Council, config, version, generated, and test files.

**Public Contracts / Signatures**

- `resolve_context_authoritative_session_key(context: Any) -> str | None` returns only a server-verified application/stable-session key.
- `ScribeErrorV1(ok: Literal[False], error_code: str, message: str, retryable: bool, target: dict[str, str] | None, candidates: tuple[dict[str, str], ...], remediation: str | None, correlation_id: str)`.
- `ScribeExpectedError(error: ScribeErrorV1)` is the only expected-failure exception crossing internal dispatch.
- `normalize_scribe_error(error: ScribeErrorV1, *, runtime: MCPRuntime, era: ProtocolEra) -> CallToolResult`.
- Preserve `execute_tool_call(...) -> Any`, `normalize_tool_result(...)`, and `configure_mcp_server(...)`; `call_tool_bound` catches only `ScribeExpectedError`, returning `isError=true` with identical C-04 `structuredContent` in both eras.

**Implementation Constraints**

1. Derive the exact caller key from `ApplicationIdentity.identity_key` or the verified resolved-scope/stable-session authority chain. Remove `agent` from `_actor_scoped_transport_session_id` authority; legacy compatibility may retain a diagnostic label but cannot key a default, session, cache, or target.
2. Build `ProjectTargetV1` once from `project_key`, `project`, and `repo_root`. For non-`set_project` project tools call C-02 once, create C-11 once, attach that exact frozen object to `ExecutionContext`, and pass it through dispatch/formatting. Helpers consume it without new binding/project lookups.
3. `set_project` uses its C-03 path and does not pre-resolve through caller default. All later ambient/explicit calls use C-02; explicit calls never rebind and never alter the default generation.
4. Map expected failures to the frozen codes: `SCRIBE_BINDING_MISSING`, `SCRIBE_PROJECT_NOT_FOUND`, `SCRIBE_PROJECT_AMBIGUOUS`, `SCRIBE_PROJECT_ROOT_MISMATCH`, `SCRIBE_CALLER_SESSION_UNVERIFIED`, `SCRIBE_BINDING_GENERATION_STALE`, `SCRIBE_DOCUMENT_GENERATION_STALE`, `SCRIBE_BUSY`, `SCRIBE_SHUTTING_DOWN`, and `SCRIBE_STALE_FENCE`. Unknown programmer/runtime defects still propagate to the server error path and are not mislabeled retryable.
5. C-04 text content is a short human rendering of the same structured payload; `structuredContent` is authoritative and always has `ok:false`, `isError=true`, the shared correlation ID, deterministic sanitized target/candidates, and bounded remediation. No raw traceback, database detail, caller key, credential, or unrelated project appears.
6. C-16 is this generic public surface only: verified caller key + optional C-02 target + `AgentAttributionV1`; bind once and retain C-03. Do not add Council imports, fields, tools, schemas, hooks, or adapter branches. External runtime-binding claims require a real C-03 receipt or direct Scribe readback.
7. Reconnect restores only the same server-minted caller identity/default; a new application identity with the same label starts unbound. Across a seeded 100-call schedule, each call observes one C-11, at most one C-01 read and one project-record read, and zero wrong-target/default-drift effects.

**Required Tests**

- DA-09/Crucible extends `tests/test_tool_runtime_repo_scope.py` for one-resolution object identity, ambient/explicit selection, structured missing/ambiguous/root-mismatch/unverified/stale-generation errors, sanitized candidates, and wrong-target zero effect.
- DA-09/Crucible creates `tests/core/test_swarm_binding_reliability.py` using the frozen topology: 32 same-label caller sessions, one `set_project` each, 100 seeded mixed calls each, reconnect/restore, ambiguity, stale generation, wrong target, exact-effects ledger, zero default drift/cross-talk/duplicate effects, and the 05:57 delayed-second-write case.
- DA-10/Crucible extends `tests/security/test_session_provenance.py` for same-label/new-handle denial and same-handle reconnect, and `tests/migration/mcp_v2/test_compatibility_matrix.py` for identical modern/legacy C-04/C-16 envelopes.
- Existing neighbor `tests/test_mcp_adapter.py` remains green and gains DA-10-owned expected-error normalization cases only through the declared DA-10 path; SS-02 Forge does not edit tests.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key; from scribe_mcp.mcp_adapter import ScribeErrorV1, ScribeExpectedError, normalize_scribe_error, normalize_tool_result'`.
- `./.venv/bin/pytest -q tests/test_mcp_adapter.py tests/test_tool_runtime_repo_scope.py`.
- `./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py` (DA-09 hermetic behavioral gate).
- `./.venv/bin/pytest -q tests/security/test_session_provenance.py tests/migration/mcp_v2/test_compatibility_matrix.py` (DA-10 single adapter/process lane).

**Acceptance Criteria**

- [ ] Every project-bound call uses one exact server-verified caller key and one immutable C-11; attribution cannot affect identity or routing.
- [ ] All expected binding/project failures return C-04 `isError=true` with identical structured content across protocol eras; no expected failure escapes as a raw transport exception.
- [ ] The generic C-16 flow supports bind-once, authorized explicit cross-repo calls, reconnect, ambiguity/stale-generation/wrong-target denials, and default preservation without Council logic.
- [ ] The 32-session × 100-call oracle reports zero wrong target, default drift, cross-talk, duplicate effect, or untyped ambiguity.

**Out of Scope**

- Tool-specific mutation semantics, Council admission/projection, C-01 persistence, schema/background/document durability, deployment, runtime restart, and test-file edits.

**Handoff Notes**

- Forge: modify only the two owned paths; stop on any need for a tool-body, Council, storage, or schema edit.
- Crucible: DA-09 owns deterministic core proof; DA-10 alone owns compatibility/process validation. Retain raw oracle counts and exact C-04 payloads.
- Sentinel: mandatory review of caller-key provenance, cross-repo authorization, error/candidate redaction, correlation data, reconnect, and label non-authority.
- Arbiter: mandatory review for one resolver/one context/one error path, modern/legacy parity, and no duplicated host-specific adapter.

### Package order and gate

1. Implement `SBR-BIND-RESOLVE.1`; import/contract proof is required before consumers.
2. Implement `.2`; C-02 behavior must pass before `.3` writes or `.4` dispatch integration.
3. Implement `.3`; require C-03 generation/no-write proof and the trace-derived delayed-second-write regression.
4. Implement `.4`; DA-09 runs the hermetic 32-session × 100-call oracle, then DA-10 runs the held adapter/process lane.
5. Sentinel and Arbiter PASS are mandatory for all packages because SS-02 is an identity, authorization, cross-repository, public-error, and high-blast-radius boundary.

## DA-04 — Schema bootstrap detail
<!-- ID: sbr-schema-bootstrap -->
### APPROACH_SUMMARY

- Goal: materialize frozen C-05/C-06 in one numbered reliability migration plus fresh/legacy baseline parity, then expose frozen C-07 as a bounded PostgreSQL readiness result.
- Files to modify: exactly the six SS-04 paths, partitioned across SBR-SCHEMA.1 through .3.
- Files forbidden: every unlisted source/test/config/generated/Council path; especially binding-store behavior owned by DA-01, receipt-store behavior owned by DA-06, startup orchestration owned by DA-03, and validation files owned by DA-09/DA-10.
- Out of scope: receipt CRUD/state transitions, request routing, queue scheduling, Council/provider semantics, production apply/deploy, release/version surfaces, and test-file edits.
- Verification plan: migration contract and restore compatibility first; PostgreSQL/SQLite/fresh-init parity second; readiness fingerprint/election/deadline proof third. The only schema mutation lane is AgentKit status -> plan -> apply against an approved disposable target, never ad hoc SQL.
- Readiness: all three packages are READY because C-05 and C-06 are frozen. Behavioral completion remains dependent on DA-09/DA-10-owned tests and mandatory Sentinel plus Arbiter review.

Frozen surfaces: C-05 adds project_key and binding_generation to session_projects, preserves project_name for display/compatibility and session_id as the unique caller-session authority, and backfills live bindings to generation 1. C-06 materializes the exact durable receipt columns and unique (canonical_project_key, idempotency_key) identity. C-07 is ensure_schema_ready(deadline_ms: int) -> SchemaReadinessV1 with schema_fingerprint, migration_version, bootstrap_role, wait_ms, ready, error_code, and retryable; one elected bootstrapper may write DDL, peers wait within a bound, and mismatches fail closed.

### Task Package: SBR-SCHEMA.1 — Migration 007 reliability upgrade

**Goal**

- Create the sole numbered PostgreSQL upgrade that materializes C-05, C-06, and the readiness record required by C-07 without changing runtime receipt behavior.

**Depends On**

- SBR-BIND-PERSIST.1 / frozen C-05.
- SBR-RECEIPT.1 / frozen C-06.
- Must land before SBR-SCHEMA.2 and SBR-SCHEMA.3 validation.

**Files to Read**

- SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md SS-04, C-05, C-06, C-07, DA-04.
- PHASE_PLAN SBR-BIND-PERSIST.1 and SBR-RECEIPT.1-.3.
- src/scribe_mcp/db/postgres_migrations/005_apply_preview_receipts.sql and 006_unique_transport_session_index.sql.
- src/scribe_mcp/storage/postgres/schema.py numbered-migration ledger path.

**Files to Modify**

- src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql — new, additive migration only.

**Files Forbidden**

- The other five SS-04 paths until their packages run.
- Every storage behavior, scheduler, server, MCP, Council, config, version, generated, and test path.

**Public Contracts / Signatures**

- Ledger identity is exactly sql:007_reliability_receipts.sql in scribe_migrations.
- session_projects retains session_id PRIMARY KEY and project_name; adds project_key TEXT and binding_generation BIGINT with generation >= 1.
- background_receipts persists exactly: operation_id, canonical_project_key, lane, idempotency_key, payload_digest, payload_bytes, durability_class, state, state_version, attempt_count, next_attempt_at, lease_owner, lease_expires_at, fencing_token, cancel_requested, result_ref, error_code, created_at, updated_at.
- background_receipts has PRIMARY KEY (operation_id) and UNIQUE (canonical_project_key, idempotency_key).
- scribe_schema_readiness is a singleton readiness record with schema_fingerprint, migration_version, and updated_at; it is coordination metadata, never the migration ledger.

**Implementation Constraints**

1. Migration 007 is additive and idempotent. Add C-05 columns in a nullable/backfill/validate/finalize sequence and preserve every legacy row, `project_name`, and `session_id`. Resolve `project_key` only when `session_projects.session_id -> scribe_sessions.repo_root` plus `project_name` identifies exactly one `scribe_projects` row. Zero matches, multiple matches, absent project name, missing session identity, or missing resolved project key remain `binding_state='unresolved'`, retain the stable reason `project_identity_zero_matches`, `project_identity_ambiguous`, `project_name_absent`, `session_missing`, or `project_key_missing`, keep `project_key=NULL`, cannot drive keyed writes, and do not abort migration or server startup.
2. Backfilled bindings receive `binding_generation=1`. The migration-owned classification trigger governs both backfill and later legacy-name writes: resolved rows require a non-empty `project_key` and no reason; unresolved rows require a NULL key and stable reason. Rebinding may resolve or demote a row and advances its generation. Agent/persona labels never participate in keys, uniqueness, or classification.
3. background_receipts uses the closed DA-06 state domain accepted, ready, leased, retry_wait, succeeded, failed_terminal, cancelled; state_version starts >=1, attempt_count/payload_bytes/fencing_token are non-negative, payload_digest is lowercase SHA-256, and lease/result/error nullability matches the state machine.
4. Create claim/recovery/capacity indexes for (canonical_project_key, lane, state, next_attempt_at, created_at), (state, lease_expires_at), and canonical project/state accounting. Do not duplicate apply-preview tables or introduce host/Council fields.
5. The SQL contains no DROP, TRUNCATE, destructive rename, data deletion, direct migration-ledger write, or down migration. The existing numbered runner records completion only after the whole migration succeeds.
6. Rollback is backup restore on an approved disposable target, not reverse DDL. A pre-apply AgentKit backup plus restored ledger/shape readback is required before release approval; inability to restore is a hard stop.
7. Production/live apply is outside Forge authority. The controlled migration gate is exact and ordered: agentkit-schema status, agentkit-schema plan --write-plan, agentkit-schema backup create, agentkit-schema apply, then agentkit-schema status. No psql or direct SQL execution is accepted as proof.

**Required Tests**

- Committed regression `tests/test_database_migration.py::test_migration_007_classifies_unresolved_legacy_bindings_instead_of_refusing_startup` proves exactly-one resolution; preserved, reason-coded, keyless zero/many/absent-name classifications; inability to drive keyed writes; successful ledger advancement; and idempotent 007 SQL replay.
- Committed regression `tests/test_database_migration.py::test_migration_007_keeps_the_legacy_postgres_binding_writer_working` proves later legacy-name writes remain compatible, the trigger owns reclassification, rebind can resolve or demote a binding, and generation advances.
- DA-10/Crucible retains `tests/migration/mcp_v2/test_compatibility_matrix.py::test_migration_007_reliability_receipts_upgrade_and_restore` as the downstream approved-disposable-target release gate proving first apply, preserved row count, C-05/C-06 constraints and indexes, one immutable ledger row with zero drift after second apply, pre-007 reader compatibility through `project_name`, pre-apply backup, and restored shape/ledger.
- Existing neighbors tests/test_bootstrap_postgres_script.py and tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py remain green.

**Verification Commands**

- PYTHONPATH=src ./.venv/bin/python -c 'from pathlib import Path; p=Path("src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql"); assert p.is_file() and p.read_text(encoding="utf-8").strip()'
- PYTHONPATH=src ./.venv/bin/pytest -q tests/test_database_migration.py::test_migration_007_classifies_unresolved_legacy_bindings_instead_of_refusing_startup tests/test_database_migration.py::test_migration_007_keeps_the_legacy_postgres_binding_writer_working
- ./.venv/bin/pytest -q tests/test_bootstrap_postgres_script.py tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py
- git diff --check -- src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql
- DA-10/SBR-SCHEMA.GATE, not this source package, owns the approved disposable-target first/second-apply, row-count, zero-ledger-drift, AgentKit status -> plan -> backup -> apply -> status, and restore receipts.

**Acceptance Criteria**

- [ ] One additive migration source supplies exact C-05/C-06 plus readiness metadata; identity is 007 and only the numbered runner may write the ledger.
- [ ] Migration SQL resolves exactly-one legacy identity while preserving zero/many/absent-name/missing-session/missing-key rows as reason-coded, keyless, unusable unresolved bindings without destructive SQL, startup refusal, or project guessing.
- [ ] Receipt constraints, uniqueness, indexes, and state-nullability encode the frozen C-06 shape.
- [ ] DA-10/SBR-SCHEMA.GATE retains mandatory first/second apply, row-count preservation, zero-ledger-drift, backup, and restore proof before release.

**Out of Scope**

- Baseline schema copies, runtime bootstrap/election, receipt CRUD, live/prod mutation, deployment, and test-file edits.

**Handoff Notes**

- Forge: author only migration 007; stop if any other path or destructive SQL appears necessary.
- Crucible: run the two committed `tests/test_database_migration.py` regressions and own the downstream approved-disposable-target first/second-apply, row-count, zero-ledger-drift, backup, restore-ledger, and schema-shape evidence.
- Sentinel: mandatory review of backfill isolation, digest/idempotency constraints, stored references, denial-of-service indexes, and no-secret redacted receipts.
- Arbiter: mandatory review for one migration authority, additive compatibility, exact C-05/C-06 parity, and zero ledger drift.

### Task Package: SBR-SCHEMA.2 — Fresh and legacy SQLite/PostgreSQL baseline parity

**Goal**

- Make fresh PostgreSQL init and SQLite creation/upgrade materialize the same C-05/C-06 logical schema as migration 007.

**Depends On**

- SBR-SCHEMA.1 is the canonical migration shape; this package mirrors it and must not redefine fields or constraints.

**Files to Read**

- src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql after SBR-SCHEMA.1.
- src/scribe_mcp/storage/sqlite/schema.py create_schema, SESSION_TABLE_STATEMENTS, APPLY_PREVIEW_RECEIPT_TABLE_STATEMENTS, and INDEX_STATEMENTS.
- src/scribe_mcp/db/init.sql session_projects, migration ledger, and apply-preview patterns.
- DA-01 C-05 and DA-06 C-06 contracts.

**Files to Modify**

- src/scribe_mcp/storage/sqlite/schema.py#background_receipt_schema — C-05/C-06 tables, legacy additive upgrade helper, and indexes only.
- src/scribe_mcp/db/init.sql#reliability_receipt_schema — fresh PostgreSQL C-05/C-06/readiness baseline only.

**Files Forbidden**

- Migration 007 after SBR-SCHEMA.1; all PostgreSQL runtime/pool files; all receipt behavior, scheduler, server, MCP, Council, config, version, generated, and test paths.

**Public Contracts / Signatures**

- async def ensure_reliability_schema(execute_fn: ExecuteFn, execute_many_fn: ExecuteManyFn) -> None.
- async def create_background_receipt_tables(execute_many_fn: ExecuteManyFn) -> None.
- create_schema(...) invokes ensure_reliability_schema exactly once before create_all_indexes.
- Fresh init.sql and SQLite schema expose the same C-05/C-06 column names, state domain, uniqueness, and logical defaults; backend-specific types are limited to TIMESTAMPTZ/JSONB/BOOLEAN versus TEXT/INTEGER representations.

**Implementation Constraints**

1. Treat migration 007 as the single schema contract. Do not create a second field list or alternate table name: both backends use session_projects, background_receipts, and the frozen C-05/C-06 names.
2. Fresh PostgreSQL init includes final C-05/C-06 shape and scribe_schema_readiness. Migration 007 remains safe on that fresh shape and the numbered runner still owns its ledger row.
3. SQLite fresh creation includes C-05 fields and the complete background_receipts table/index set. Its legacy upgrade helper adds missing C-05 columns idempotently, backfills project_key from the session repo root plus project name, sets existing bound rows to generation 1, and fails closed before behavior proceeds when identity cannot be resolved uniquely.
4. SQLite enforces lowercase 64-character payload_digest, closed lane/state domains, non-negative sizes/counts/fences, positive state_version/binding_generation, unique project/idempotency identity, and state-dependent lease/result/error nullability using CHECK/UNIQUE/indexes supported by SQLite.
5. PostgreSQL and SQLite timestamp/boolean/JSON storage differences may vary, but normalized values consumed by DA-01/DA-06 must be identical. No backend-specific field enters the public models.
6. Compatibility is additive: preserve project_name and current apply-preview/session tables, triggers, FTS, and indexes. Existing SQLite files reopen without rebuild/data loss; no side database, reset, or table-copy migration is introduced.
7. Importing either schema module performs no I/O. Schema work occurs only through existing storage initialization and the governed AgentKit migration lane.

**Required Tests**

- DA-09/Crucible adds tests/core/test_swarm_binding_reliability.py::test_sqlite_reliability_schema_upgrades_legacy_binding_without_default_drift.
- DA-09/Crucible adds tests/core/test_background_queue_contract.py::test_sqlite_background_receipt_schema_enforces_c06.
- DA-10/Crucible adds tests/migration/mcp_v2/test_compatibility_matrix.py::test_reliability_schema_postgres_sqlite_init_parity, comparing exact logical fields, domains, uniqueness, and indexes against migration 007.
- Existing neighbors tests/storage/test_session_storage_invariants.py, tests/storage/test_sqlite_apply_preview_receipts.py, and tests/test_bootstrap_postgres_script.py remain green.

**Verification Commands**

- PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.sqlite.schema import create_background_receipt_tables, ensure_reliability_schema; from scribe_mcp.storage.postgres.schema import SCHEMA_PATH'
- ./.venv/bin/pytest -q tests/storage/test_session_storage_invariants.py tests/storage/test_sqlite_apply_preview_receipts.py tests/test_bootstrap_postgres_script.py
- ./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py::test_sqlite_reliability_schema_upgrades_legacy_binding_without_default_drift tests/core/test_background_queue_contract.py::test_sqlite_background_receipt_schema_enforces_c06 (after DA-09 owns the tests).
- ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py::test_reliability_schema_postgres_sqlite_init_parity (after DA-10 owns the test).

**Acceptance Criteria**

- [ ] Fresh PostgreSQL, fresh SQLite, and legacy SQLite upgrade expose one logical C-05/C-06 schema.
- [ ] Fresh init plus migration 007 is idempotent; reopening SQLite is non-destructive and preserves existing bindings/receipts.
- [ ] Compatibility project_name remains readable while project_key/generation are authoritative for new binding behavior.
- [ ] Schema modules import without database/filesystem side effects.

**Out of Scope**

- PostgreSQL bootstrap election, pool deadlines, receipt storage methods, state transitions, live migration apply, and test-file edits.

**Handoff Notes**

- Forge: touch only the two declared schema regions and copy no receipt behavior into schema helpers.
- Crucible: own DA-09 hermetic SQLite tests and DA-10 cross-backend parity test; prove reopen and legacy upgrade without sleeps.
- Sentinel: mandatory review of constraints, backfill ambiguity, stored reference exposure, and malicious size/digest inputs.
- Arbiter: mandatory review for one logical schema, minimal backend variance, no duplicate migration path, and unchanged neighboring tables.

### Task Package: SBR-SCHEMA.3 — Fingerprinted elected bootstrap and bounded readiness

**Goal**

- Replace repeated/unbounded startup DDL with one fingerprint fast check, one elected bootstrapper, bounded peer readiness, and the exact frozen C-07 result.

**Depends On**

- SBR-SCHEMA.1 supplies migration 007 and readiness metadata.
- SBR-SCHEMA.2 supplies fresh init parity.
- Runtime consumers DA-03 and release validation DA-10 depend on this package's C-07.

**Files to Read**

- src/scribe_mcp/storage/postgres/schema.py current advisory-lock/bootstrap/ledger functions.
- src/scribe_mcp/storage/postgres/internals.py PostgresPoolConfig and ensure_pool retry path.
- src/scribe_mcp/storage/postgres/__init__.py PostgresStorage.__init__, setup, close, _ensure_pool, and _ensure_schema.
- research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md package P3.
- tests/test_bootstrap_postgres_script.py, tests/test_postgres_project_identity_scoping.py, and tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py.

**Files to Modify**

- src/scribe_mcp/storage/postgres/schema.py — SchemaReadinessV1, fingerprint/ledger fast check, nonblocking election, bounded peer wait, and transactional numbered-migration application.
- src/scribe_mcp/storage/postgres/internals.py — deadline-aware pool connection retries/backoff only.
- src/scribe_mcp/storage/postgres/__init__.py#setup_fast_path — public readiness adapter and setup compatibility only.

**Files Forbidden**

- All schema SQL/baselines after prior packages; all receipt behavior, scheduler, server, MCP, Council, config, version, generated, benchmark, and test paths.

**Public Contracts / Signatures**

- SchemaBootstrapRole = Literal["fast_path", "bootstrapper", "peer"].
- SchemaReadinessErrorCode = Literal["SCHEMA_FINGERPRINT_MISMATCH", "SCHEMA_BOOTSTRAP_TIMEOUT", "SCHEMA_BOOTSTRAP_FAILED", "SCHEMA_STORAGE_UNAVAILABLE"].
- SchemaReadinessV1(schema_fingerprint: str, migration_version: str, bootstrap_role: SchemaBootstrapRole, wait_ms: int, ready: bool, error_code: SchemaReadinessErrorCode | None, retryable: bool).
- async def ensure_schema_ready(*, pool_provider: Callable[..., Awaitable[asyncpg.Pool]], schema_lock: asyncio.Lock, schema_name: str, deadline_ms: int, schema_path: Path = SCHEMA_PATH, migrations_path: Path = MIGRATIONS_PATH) -> SchemaReadinessV1.
- PostgresInternals.ensure_pool(self, *, deadline_ms: int | None = None) -> asyncpg.Pool; no-argument callers remain compatible.
- PostgresStorage.ensure_schema_ready(self, deadline_ms: int) -> SchemaReadinessV1.
- PostgresStorage.setup(self) -> None remains public-compatible, calls ensure_schema_ready(deadline_ms=2500), raises one typed SchemaReadinessError when ready is false, and only then runs existing repo-scoped identity repair.
- Existing ensure_schema(...) -> bool remains a compatibility wrapper over ensure_schema_ready for current bootstrap callers/tests; it must not restore unbounded blocking.

**Implementation Constraints**

1. Compute one deterministic lowercase SHA-256 from the packaged init.sql bytes plus sorted numbered migration filenames and bytes. Expected migration_version is sql:007_reliability_receipts.sql. Cache only immutable packaged-source input; never derive readiness from process-local _schema_ready alone.
2. Warm fast path performs one bounded database read that verifies scribe_schema_readiness fingerprint/version and the migration-007 ledger presence. It performs zero DDL, zero ledger/readiness writes, and returns bootstrap_role="fast_path". Warm storage setup p95 target is <=100 ms.
3. On stale/missing readiness, use pg_try_advisory_lock for the schema-specific key. Exactly one holder is bootstrapper; peers never call init DDL or numbered migrations. The bootstrapper applies schema plus each pending numbered migration transactionally, verifies actual required columns/tables/indexes and immutable ledger state, then publishes the readiness row last.
4. Peers poll/read readiness only within min(remaining caller deadline, 500 ms), with monotonic accounting and bounded backoff. If the elected owner exits before publishing, one peer may acquire the released advisory lock and become the replacement bootstrapper; no two holders execute DDL concurrently.
5. deadline_ms must be positive and bounds the entire pool-connect plus election/bootstrap/wait operation. PostgresInternals caps each connect timeout and retry backoff to remaining time, performs no retry/sleep after expiry, and reports retryable storage-unavailable/timeout truth without leaking DSNs.
6. Fingerprint/version disagreement after bootstrap or against an existing ready row returns ready=false, SCHEMA_FINGERPRINT_MISMATCH, retryable=false, and performs no compatibility overwrite, migration replay, ledger edit, or startup continuation.
7. Timeout/storage failures return ready=false with typed code and retryability; wait_ms is monotonic elapsed whole milliseconds. Success has error_code=None and retryable=false. schema_fingerprint and migration_version are always populated with the expected source values.
8. close() clears only process-local readiness/pool state. It never edits the durable readiness row or migration ledger. setup() preserves existing ordering: schema readiness first, repo-scoped identity repair second.
9. Under 32 simultaneous cold starts, exactly one bootstrap role executes DDL, every successful peer observes the same fingerprint/version, warm peer wait is <=500 ms, and scribe_migrations contains one unchanged row per migration. No raw DSN, SQL payload, or secrets enter readiness/logging.
10. Reuse the existing PostgresStorage, PostgresInternals, schema module, pool, advisory-key helper, and migration ledger. Do not add a daemon, second lock service, alternate migration runner, or process-global authority.

**Required Tests**

- DA-10/Crucible adds tests/integration/test_swarm_concurrency_stress.py::test_schema_bootstrap_32_simultaneous_starts_one_elected_bootstrapper using a disposable schema, 32 simultaneous storage starts, exact bootstrap-role counts, <=500 ms warm peer waits, identical fingerprint/version, and zero ledger drift.
- DA-10/Crucible adds tests/integration/test_swarm_concurrency_stress.py::test_schema_fingerprint_mismatch_fails_closed_without_ledger_write and ::test_schema_peer_deadline_is_bounded_and_retryable.
- Existing tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py, tests/test_bootstrap_postgres_script.py, and tests/test_postgres_project_identity_scoping.py remain green.
- Import smoke must cover SchemaReadinessV1, ensure_schema_ready, PostgresInternals, and PostgresStorage.

**Verification Commands**

- PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.postgres.schema import SchemaReadinessV1, ensure_schema, ensure_schema_ready; from scribe_mcp.storage.postgres.internals import PostgresInternals; from scribe_mcp.storage.postgres import PostgresStorage'
- ./.venv/bin/pytest -q tests/test_bootstrap_postgres_script.py tests/test_postgres_project_identity_scoping.py
- ./.venv/bin/pytest -q tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py
- ./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py::test_schema_bootstrap_32_simultaneous_starts_one_elected_bootstrapper tests/integration/test_swarm_concurrency_stress.py::test_schema_fingerprint_mismatch_fails_closed_without_ledger_write tests/integration/test_swarm_concurrency_stress.py::test_schema_peer_deadline_is_bounded_and_retryable (single repository-saturating PostgreSQL/process lane; only after DA-10 owns the test file).

**Acceptance Criteria**

- [ ] C-07 exact fields and signatures are importable; setup remains compatible and fails closed before identity repair on non-ready results.
- [ ] Warm matching startup performs one fast read, zero writes/DDL, and meets the <=100 ms p95 target.
- [ ] Thirty-two simultaneous starts elect exactly one DDL bootstrapper; peers wait <=500 ms, observe one fingerprint/version, and create zero ledger drift.
- [ ] Fingerprint mismatch, owner failure, connection exhaustion, and deadline expiry return typed bounded truth with no unbounded wait, secret leakage, or compatibility overwrite.
- [ ] Existing setup/bootstrap neighbors and import smoke pass.

**Out of Scope**

- Server lifecycle orchestration, optional-service readiness, queue scheduling, receipt operations, schema field redesign, live/prod adoption, deployment, and test-file edits.

**Handoff Notes**

- Forge: implement only the three declared source regions; stop if another file, new migration, config key, or changed C-07 field is needed.
- Crucible: DA-10 owns the three exact 32-start/mismatch/deadline tests and the held PostgreSQL/process lane; retain raw role counts, timings, fingerprints, and before/after ledger rows.
- Sentinel: mandatory review of advisory-lock election/recovery, deadline exhaustion, fail-closed mismatch, SQL/identifier handling, DSN/log redaction, and resource-exhaustion behavior.
- Arbiter: mandatory review for one pool/one migration runner, compatibility of setup/ensure_schema, no process-local readiness authority, and proof that fast/peer paths never write.

### Package order and gate

1. Implement SBR-SCHEMA.1; inspect the generated AgentKit plan before any apply.
2. Implement SBR-SCHEMA.2 from the accepted migration shape; run hermetic SQLite/init parity before any database mutation.
3. Implement SBR-SCHEMA.3; run import and focused neighbor tests, then DA-10's single held 32-process PostgreSQL lane.
4. On an approved disposable target, execute and retain the ordered AgentKit status -> plan -> backup -> apply -> status receipts, then prove restore compatibility and zero ledger drift. This is validation, not deployment.
5. Sentinel and Arbiter PASS are mandatory for all three packages because SS-04 is schema-, migration-, startup-, concurrency-, and high-blast-radius sensitive.
## DA-05 — Hot path and telemetry detail
<!-- ID: sbr-hot-path -->
### APPROACH_SUMMARY

- **Goal:** Pass one frozen `ResolvedRequestContextV1` through SS-05 tool helpers and response finalization, remove duplicate session/project reads and the formatter's synchronous project fetch, and emit frozen C-12 timing/tripwire evidence without weakening foreground authority, validation, or durability.
- **Files to modify:** exactly the six SS-05 paths named below, partitioned pairwise-disjoint across `SBR-HOTPATH.1` through `.3`.
- **Files forbidden:** every source path outside SS-05; all tests (owned by DA-09/DA-10); storage, schema, background, document, Council, generated, config, packaging, and version surfaces.
- **Out of scope:** target selection, default mutation, C-01/C-02/C-03 implementation, public MCP parameter changes, new queues/caches/registries, deployment/restart, and deferral of authoritative foreground work.
- **Verification plan:** package-local import smoke and focused neighbor tests first; DA-09 then owns deterministic C-11/C-12/read-count/tripwire proof, and DA-10 owns the single reference-profile percentile lane. No SS-05 implementer edits those validation files.
- **Frozen inputs and output:** consume C-04 `ScribeErrorV1` and C-11 `ResolvedRequestContextV1` exactly as accepted; produce C-12 `CallTimingEnvelopeV2` exactly once per completed call.
- **Performance proof:** reads must meet p50 <=75 ms and p95 <=250 ms on the recorded reference profile; durable append/receipt acknowledgement must meet p95 <=500 ms; p99 is always reported as raw evidence because the frozen budget does not invent a p99 cap. Every synchronous class retains the frozen p95 <=500 ms ceiling.
- **Read-count proof:** each call performs at most one durable session-binding read and one project-record read across dispatch plus tool execution; formatter/project/log helpers perform zero additional binding or project-record reads.

### Task Package: SBR-HOTPATH.1 — C-12 timing model and context-aware response finalization

**Goal**

- Define the sole `CallTimingEnvelopeV2` builder/recorder and make `FormatterDispatcher` finalize responses from the already-resolved C-11 context, with honest >=95% accounting and correlated >100 ms stage / >500 ms total evidence.

**Depends On**

- `SBR-BIND-RESOLVE.4` (C-04/C-11 runtime installation) is complete.
- No other SS-05 package.

**Files to Read**

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` C-04, C-11, C-12, and frozen performance budgets.
- `research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` F6 and Package P4.
- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F1/F9 and deterministic timing-probe requirements.
- `src/scribe_mcp/shared/execution_context.py::ResolvedRequestContextV1`.
- `src/scribe_mcp/utils/tool_logger.py::log_tool_call`.
- `tests/test_dispatcher.py`, `tests/test_log_intelligence.py`, and `tests/test_doctor_telemetry.py`.

**Files to Modify**

- `src/scribe_mcp/runtime_timing_envelope.py` — C-12 phase vocabulary, request-local recorder, strict builder, and backwards-compatible V1 projections.
- `src/scribe_mcp/utils/formatters/dispatcher.py` — C-11-aware formatter/audit finalization and slow-call evidence; remove synchronous project lookup.

**Files Forbidden**

- `src/scribe_mcp/shared/tool_runtime.py`, `src/scribe_mcp/shared/execution_context.py`, every tool body, storage backend/model, background service, test, schema, Council, generated, config, packaging, and version file.

**Public Contracts / Signatures**

- `CALL_TIMING_PHASES_V2: tuple[str, ...]` is ordered exactly as `("ingress_decode", "session_binding_read", "project_record_read", "target_resolution", "mode_resolution", "tool_body", "authority_and_validation", "authoritative_durability", "receipt_commit", "hooks", "response_format", "audit_append", "egress_serialize", "unaccounted")`.
- `class CallTimingEnvelopeV2(TypedDict)` has `schema_version: Literal["call-timing-envelope.v2"]`, `correlation_id: str`, `phases_ms: dict[str, float]`, `total_ms: float`, `accounted_ratio: float`, `slow_stages: list[str]`, and `tripwire_exceeded: bool`.
- `CallTimingRecorderV2.start(*, correlation_id: str, started_perf_counter: float | None = None, seed_phases_ms: Mapping[str, float] | None = None) -> CallTimingRecorderV2`.
- `CallTimingRecorderV2.record_phase(phase: str, duration_ms: float) -> None`; repeated recording accumulates only the same named non-overlapping stage.
- `CallTimingRecorderV2.finalize(*, total_ms: float | None = None) -> CallTimingEnvelopeV2`.
- `build_call_timing_envelope_v2(*, correlation_id: str, phases_ms: Mapping[str, float], total_ms: float) -> CallTimingEnvelopeV2`.
- Preserve `build_runtime_efficiency_budget_status(...)`, `build_timing_envelope(...)`, and `build_timing_envelope_from_entries(...)`; their V1 schema/readers remain compatible.
- Extend only the internal formatter interface: `FormatterDispatcher.finalize_tool_response(data: Dict[str, Any], format: str = "readable", tool_name: str = "", telemetry: Optional[Dict[str, Any]] = None, resolved_request_context: ResolvedRequestContextV1 | None = None) -> Union[Dict[str, Any], CallToolResult]`.

**Implementation Constraints**

1. Validate a nonblank C-11 correlation ID, finite nonnegative durations, and only the frozen phase names. Normalize all fourteen phase keys into deterministic order; missing stages are `0.0`, and `unaccounted=max(total_ms-sum(non-unaccounted phases), 0.0)`.
2. Compute `accounted_ratio=min(sum(non-unaccounted phases)/total_ms, 1.0)`; define the zero-total ratio as `1.0`. Never hide missing coverage by counting `unaccounted` as measured time.
3. `slow_stages` contains deterministically ordered non-`unaccounted` stages strictly greater than 100 ms. `tripwire_exceeded` is true only when `slow_stages` is nonempty or `total_ms>500`; exact 100 ms / 500 ms boundaries do not trip.
4. `finalize_tool_response` accepts the same C-11 instance used by the tool. Correlation comes from C-11; telemetry may add durations but may not replace identity, target, authorization, project, or correlation data.
5. Delete the `fetch_project_sync` branch and ambient repo-config fallback from finalization. Resolve `project_name`, canonical `repo_root`, and `progress_log_path` from the supplied resolved/logging context only; absence yields typed C-04/diagnostic omission, never a new lookup.
6. Measure response formatting, the foreground local audit append, and returned-payload serialization separately. Emit one bounded-cardinality slow-call record containing tool, outcome, durability class, error category, permitted hashed/canonical project key, correlation ID, total, accounted ratio, and slow stages. Never label by raw agent string, raw caller key, payload, operation ID, or unbounded error text.
7. Keep the local authoritative JSONL/WAL audit append synchronous and inside `audit_append`. SQL analytics/derived metrics may remain scheduled after local durability; do not move authority, validation, receipt commit, or required local durability behind a background task.
8. Build one C-12 envelope per call and attach it to structured/both responses plus the audit record. Readable-only responses may omit structured content but must still emit the identical correlated audit envelope.
9. A final envelope with `accounted_ratio<0.95` is honest failure evidence, not silently padded or relabeled. DA-09/DA-10 gates reject it.
10. Preserve existing readable, structured, compact, both, MCP fallback, and expected C-04 error rendering behavior.

**Required Tests**

- Existing SS-05 neighbor tests must prove formatter routing, telemetry propagation, backward-compatible V1 timing projections, and no formatter project lookup.
- DA-09/Crucible adds deterministic manual-clock cases in `tests/core/test_swarm_binding_reliability.py` for all fourteen phases, exact ratio math, 100/500 boundary semantics, one envelope/correlation ID, and <95% coverage rejection evidence.
- DA-10/Crucible records raw timing events and p50/p95/p99 on the named reference profile; no hermetic test sleeps or asserts wall-clock completion.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.runtime_timing_envelope import CALL_TIMING_PHASES_V2, CallTimingEnvelopeV2, CallTimingRecorderV2, build_call_timing_envelope_v2, build_timing_envelope; from scribe_mcp.utils.formatters.dispatcher import FormatterDispatcher'`.
- `./.venv/bin/pytest -q tests/test_dispatcher.py tests/test_log_intelligence.py tests/test_doctor_telemetry.py`.
- `./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py` (after DA-09 owns C-12 additions).
- `./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py` (DA-10 held reference-profile lane after DA-10 owns the test).

**Acceptance Criteria**

- [ ] C-12 has the exact frozen phases/fields, honest `unaccounted`, >=0.95 measured coverage in passing calls, and deterministic strict >100/>500 tripwires sharing C-11 correlation.
- [ ] Formatter performs zero session-binding/project-record reads and zero ambient target selection; `fetch_project_sync` is absent from its call path.
- [ ] Local authoritative audit durability remains foreground; only analytics/derived metrics defer.
- [ ] V1 timing consumers and all response formats remain compatible.

**Out of Scope**

- Instrumenting or changing SS-02 dispatch, choosing targets/defaults, storage query behavior, queue creation, test-file edits, client/proxy latency, and production rollout.

**Handoff Notes**

- Forge: implement only the two owned files; stop if a frozen C-04/C-11/C-12 field or another source path must change.
- Crucible: own DA-09/DA-10 test additions, use manual clocks for thresholds, and retain the raw envelopes/percentiles.
- Arbiter: require one timing model, honest coverage math, bounded labels, zero synchronous formatter lookup, and preserved foreground audit durability.

### Task Package: SBR-HOTPATH.2 — Single-context logging helper and get-project read path

**Goal**

- Make `LoggingToolMixin` consume the exact installed C-11 context and make `get_project` reuse its resolved project data without label authority, compatibility re-resolution, or another project-record fetch.

**Depends On**

- `SBR-HOTPATH.1`.
- `SBR-BIND-RESOLVE.4` provides the exact `ExecutionContext.resolved_request_context`.

**Files to Read**

- `src/scribe_mcp/shared/logging_utils.py::LoggingContext`, `resolve_logging_context`, and C-11 reuse branch.
- `src/scribe_mcp/shared/execution_context.py::ResolvedRequestContextV1`.
- `src/scribe_mcp/storage/models.py::ProjectRecord`.
- `src/scribe_mcp/tools/get_project.py::get_project`, `_compute_doc_status`, `_compute_log_counts`, and recent-entry helpers.
- `tests/test_base_logging_tool.py`, `tests/test_get_project_integration.py`, `tests/test_get_project_sitrep.py`, and `tests/test_session_resolution_advisories.py`.

**Files to Modify**

- `src/scribe_mcp/shared/base_logging_tool.py` — current C-11 acquisition/pass-through, canonical project-record projection, and context-aware finalization inputs.
- `src/scribe_mcp/tools/get_project.py` — one-context project/read path and C-12 stage recording.

**Files Forbidden**

- `runtime_timing_envelope.py` and `dispatcher.py` after `SBR-HOTPATH.1`; `read_recent.py` and `query_entries.py` until `SBR-HOTPATH.3`; all other source, test, schema, storage, Council, generated, config, packaging, and version files.

**Public Contracts / Signatures**

- Extend `LoggingToolMixin.prepare_context(..., resolved_request_context: ResolvedRequestContextV1 | None = None, ...) -> LoggingContext`; when omitted, it reads `server_module.get_execution_context().resolved_request_context` once and passes that exact object to `resolve_logging_context`.
- `LoggingToolMixin.project_record_from_context(context: LoggingContext) -> ProjectRecord` projects the already-resolved record only; it never queries storage, loads config, or consults recents/global state.
- `LoggingToolMixin.finalize_tool_response(..., context: LoggingContext, timing: CallTimingRecorderV2) -> Union[Dict[str, Any], CallToolResult]` forwards the same C-11 and recorder to the default formatter.
- Preserve the public `get_project(agent: str = "Codex", project: Optional[str] = None, format: str = "structured", verbose: bool = False, recovery_mode: Optional[str] = None) -> Dict[str, Any]`; `agent` remains attribution only and `recovery_mode` remains explicit diagnostic compatibility only.

**Implementation Constraints**

1. Acquire one C-11 object at tool entry; pass object identity unchanged through `prepare_context`, response helpers, and formatter. Never reconstruct it from `agent`, project text, globals, recents, or response data.
2. A missing C-11 on a project-bound call returns frozen C-04 `SCRIBE_BINDING_MISSING` or `SCRIBE_CALLER_SESSION_UNVERIFIED`; it does not run compatibility discovery. Sentinel/unbound-safe diagnostics retain their explicit C-04-compatible path.
3. `project_record_from_context` uses the authoritative project mapping already produced by C-02. Validate stable key, name, canonical root, and record identity/path fields; incomplete data fails typed before the tool body rather than issuing another fetch.
4. Remove `get_agent_context_manager().get_current_project`, ambient `state_manager.load`, candidate/config project discovery, and the second `backend.fetch_project` from operational project-mode execution. C-11/C-02 selects the target; the public `agent` string never selects or keys it.
5. Preserve explicit-project/default semantics from C-02: an authorized explicit project may differ from the caller default, but the call performs no bind/default/recent/cache mutation and returns data only for `context.resolved_target`.
6. Compute docs status/log counts/project state from the reused context/record; each derived dataset is computed at most once. `verbose=False` does not perform recent-entry rendering reads; `verbose=True` may read entries but cannot re-fetch the project.
7. Record `tool_body`, `authority_and_validation`, and any foreground read work on the `CallTimingRecorderV2`; finalization is delegated once to `SBR-HOTPATH.1`.
8. Preserve C-04 expected errors, structured/readable/compact shapes, planning advisories, docs/log summaries, and explicit diagnostic compatibility responses. No expected resolution failure escapes as a raw exception.
9. Foreground reads still return the requested consistent snapshot. No immediate read becomes a receipt, cached guess, or background-only computation.

**Required Tests**

- Existing tests prove helper reuse, no label authority, unchanged response formats/SITREP/advisories, and no second project fetch.
- DA-09/Crucible instruments binding/project access counts and C-11 object identity in `tests/test_tool_runtime_repo_scope.py` and `tests/core/test_swarm_binding_reliability.py`.
- DA-10/Crucible includes `get_project` in raw read p50/p95/p99 reference-profile evidence.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.base_logging_tool import LoggingToolMixin; from scribe_mcp.tools.get_project import get_project'`.
- `./.venv/bin/pytest -q tests/test_base_logging_tool.py tests/test_get_project_integration.py tests/test_get_project_sitrep.py tests/test_session_resolution_advisories.py`.
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py` (after DA-09 owns access-count/object-identity cases).

**Acceptance Criteria**

- [ ] `get_project` and its helper/formatter chain observe the same C-11 object and C-11 correlation ID.
- [ ] One complete call performs at most one binding read and one project-record read in total; the SS-05 portion performs neither again.
- [ ] Attribution-only `agent`, recents, ambient root, and process/global state cannot select or mutate the operational target/default.
- [ ] Existing get-project content and formats remain correct; non-verbose operation does not add derived recent-entry work.

**Out of Scope**

- C-02 target resolution, C-01/C-03 binding persistence, storage API redesign, new caches, background scheduling, read/query tools, test-file edits, and release/profile execution.

**Handoff Notes**

- Forge: reuse C-11/C-02 results; do not add another registry, cache, config fallback, or compatibility authority path.
- Crucible: count actual resolver/backend calls and assert C-11 object identity plus zero default mutation.
- Arbiter: reject label-keyed selection, repeated resolution/fetch, duplicated project DTO construction, or response regressions hidden as performance work.

### Task Package: SBR-HOTPATH.3 — Read-recent/query single-record execution and timing closure

**Goal**

- Convert `read_recent` and `query_entries` to use the one C-11/LoggingContext/ProjectRecord created for the call, preserve their immediate consistent-snapshot contracts, and close C-12 instrumentation through the formatter.

**Depends On**

- `SBR-HOTPATH.1` and `SBR-HOTPATH.2`.

**Files to Read**

- `src/scribe_mcp/tools/read_recent.py::read_recent`, `_supplement_sparse_db_rows_from_progress_log`, and response finalization branches.
- `src/scribe_mcp/tools/query_entries.py::query_entries`, `_build_search_query`, and `_execute_search_with_fallbacks`.
- `src/scribe_mcp/storage/base.py::fetch_recent_entries_paginated`, `count_entries`, and `query_entries_paginated`.
- `tests/test_consumer_resolution_contract.py`, `tests/test_read_recent_limit.py`, `tests/test_read_recent_supplement_gate.py`, `tests/test_query_entries_db.py`, `tests/test_query_entries_pagination_contract.py`, and `tests/test_query_entries_explicit_project_resolution.py`.

**Files to Modify**

- `src/scribe_mcp/tools/read_recent.py` — C-11/project-record reuse, one finalizer, and named phase recording.
- `src/scribe_mcp/tools/query_entries.py` — carry the same C-11/project record through query building/execution/fallback and one finalizer.

**Files Forbidden**

- The other four SS-05 files after `SBR-HOTPATH.1/.2`; every storage backend/model, resolver/runtime/adapter, background, schema, document, Council, generated, config, packaging, version, and test file.

**Public Contracts / Signatures**

- Preserve public `read_recent(...)` and `query_entries(...)` MCP signatures, pagination/filter semantics, readable/structured/compact behavior, and C-04 results.
- Internal `_build_search_query(final_config: QueryEntriesConfig, context: LoggingContext, project_record: ProjectRecord) -> Dict[str, Any]`.
- Internal `async _execute_search_with_fallbacks(search_query: Dict[str, Any], final_config: QueryEntriesConfig, *, project_record: ProjectRecord, resolved_request_context: ResolvedRequestContextV1, timing: CallTimingRecorderV2) -> Dict[str, Any]`.
- Every formatter call supplies `resolved_request_context=context.resolved_request_context` and the same `CallTimingRecorderV2`.

**Implementation Constraints**

1. Delete the tool-body `state_manager.record_tool`/ambient `state_manager.load` resolution work where C-11 already supplies state/context. Call `prepare_context` once with the installed C-11; preserve only explicit unbound-safe diagnostic handling.
2. Convert the already-resolved LoggingContext project data to one `ProjectRecord` through `LoggingToolMixin.project_record_from_context`. Delete `backend.fetch_project` from `read_recent` and `_execute_search_with_fallbacks`; pass that same record through every DB branch.
3. `query_entries` query construction, DB pagination, Python filtering, flat-file fallback, observed-context option, and final formatting must retain the same C-11 identity/correlation and cannot re-resolve a target from text/global state.
4. Preserve explicit-project fail-closed semantics and C-04 for missing/ambiguous/root-mismatch/unverified/stale cases. Never fall back from an explicit denial to caller default, file discovery, recents, or another repository.
5. Preserve read/query pagination, filters, DB/file parity, supplement gating, and honest error envelopes. File fallback is allowed only for the already-authorized resolved project path and performs no project/default mutation.
6. Record `tool_body`, `authority_and_validation`, `hooks`, and relevant foreground read duration exactly once; call the shared finalizer once per successful response path. Consolidate duplicate readable/structured finalization branches only where behavior stays identical.
7. A synchronous read/query returns its requested consistent snapshot before success. Cache warming, analytics, and derived indexing may defer only after response; project resolution and result data never do.
8. Retain foreground local audit durability and pass C-12 to the finalizer. The complete call must expose >=95% measured accounting, strict correlated >100/>500 evidence, and at most one binding/project-record read.
9. Do not change storage signatures or hide duplicate reads behind a new cache. Reuse the authoritative record already obtained for C-02/C-11.
10. Preserve bounded-cardinality telemetry and redact raw caller/session keys, raw agent labels, payloads, unrestricted project candidates, and free-form exception text.

**Required Tests**

- Existing neighbor tests prove DB/file behavior, supplement gating, explicit-project denials, pagination/filter parity, response formatting, and C-04 honesty after fetch removal.
- DA-09/Crucible extends `tests/test_tool_runtime_repo_scope.py` and `tests/core/test_swarm_binding_reliability.py`: 32 same-label sessions x 100 seeded calls, including `get_project`/`read_recent`/`query_entries`; exact C-11 object identity; <=1 binding read; <=1 project-record read; one C-12; zero wrong target/default drift/cross-talk/duplicate effect.
- DA-09 uses manual stage durations for >=95% coverage and tripwire deltas; DA-10 alone runs real percentile measurements.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.read_recent import read_recent; from scribe_mcp.tools.query_entries import query_entries, _build_search_query, _execute_search_with_fallbacks'`.
- `./.venv/bin/pytest -q tests/test_consumer_resolution_contract.py tests/test_read_recent_limit.py tests/test_read_recent_supplement_gate.py`.
- `./.venv/bin/pytest -q tests/test_query_entries_db.py tests/test_query_entries_pagination_contract.py tests/test_query_entries_explicit_project_resolution.py tests/test_query_entries_dead_engine_honest_envelopes.py`.
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py` (DA-09 hermetic gate).
- `./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py` (DA-10 held reference-profile lane after DA-10 owns the test).

**Acceptance Criteria**

- [ ] Both tools reuse one C-11 and one ProjectRecord end to end; no body/helper/formatter repeats session binding or project-record reads.
- [ ] Immediate read/query snapshots, pagination/filter parity, explicit target/default preservation, and typed C-04 errors remain correct.
- [ ] Every completed call produces one correlated C-12 with >=0.95 accounting and deterministic stage/total tripwire evidence.
- [ ] DA-09's 32 x 100 oracle reports zero wrong target, default drift, cross-talk, duplicate effect, or excess binding/project reads.

**Out of Scope**

- Storage backend/query redesign, new caches or queues, write/receipt behavior, target/default resolution, MCP adapter changes, test-file edits, browser/network validation, deployment, and restart.

**Handoff Notes**

- Forge: modify only these two tools; stop if storage/resolver/formatter files beyond completed dependencies appear necessary.
- Crucible: own all DA-09/DA-10 additions, instrument actual read counts, and retain raw envelopes/percentiles without sleeps in the hermetic lane.
- Arbiter: require one context/record/finalizer path, preserved query semantics, bounded telemetry, and no performance shortcut that weakens synchronous snapshot or durability behavior.

### Package order and gate

1. Implement `SBR-HOTPATH.1`; import and focused formatter/timing tests must pass before any tool consumes C-12.
2. Implement `SBR-HOTPATH.2`; prove C-11 identity and zero helper/get-project rereads before changing the two log-read tools.
3. Implement `SBR-HOTPATH.3`; run both focused read/query lanes and import smoke.
4. DA-09 runs the hermetic 32-session x 100-call oracle, manual timing boundaries, exact one-binding-read/one-project-read counts, one-envelope correlation, >=95% accounting, and zero correctness effects.
5. DA-10 runs the one held reference-profile lane and retains raw p50/p95/p99 evidence: `get_project`/`read_recent`/`query_entries` each p50 <=75 ms and p95 <=250 ms; durable append/receipt acknowledgement p95 <=500 ms; all synchronous classes p95 <=500 ms; p99 reported without an invented cap.
6. Arbiter PASS is mandatory for all three packages because SS-05 is performance-, observability-, and high-blast-radius-sensitive. Reject any duplicate resolver/record lookup, falsified timing coverage, unbounded labels, or deferred authoritative work.
## DA-07 — Scheduler and lifecycle detail
<!-- ID: sbr-background-service -->
### APPROACH_SUMMARY

- Goal: implement frozen C-09 as one host-neutral, bounded, partition-fair background service over frozen C-08, with deterministic scheduling, fenced workers, finite retry/cancellation, restart recovery, metrics, and graceful drain.
- Files to modify: exactly the six SS-07 paths, partitioned across `SBR-BG.1` through `.4`.
- Files forbidden: every unlisted source/test/config/generated/Council path; especially C-08 receipt models/store/backend adapters owned by DA-06, startup-ready semantics owned by DA-03, document mutation execution owned by DA-08, timing-envelope internals owned by DA-05, and validation fixtures/tests owned by DA-09/DA-10.
- Out of scope: receipt persistence or schema changes, document effects, MCP/provider/Council process-count/reuse/idle-reap policy, new metric/result stores, version/release edits, deployment, and runtime adoption.
- Verification plan: scheduler contract and deterministic fairness first; fenced worker/retry/cancellation second; service admission/recovery/API third; server lifecycle/health last. DA-09 owns hermetic and 32-caller correctness proof; DA-10 owns the single PostgreSQL/process lane.
- DAG: layer 2, parallel with DA-05, after DA-06. C-08 is frozen and is the only input; these packages produce frozen C-09.

Frozen surfaces: C-08 supplies `BackgroundReceiptStoreV1.admit/get/claim/transition/recover`, closed receipt states, atomic global/per-project item+byte admission, and monotonic state-version/fencing behavior. C-09 supplies `submit`, `get_status`, `cancel`, `start`, and `stop`; canonical project partitions; control/durable/heavy lanes; bounded admission; global/per-project caps; deficit round robin; finite seeded retry; leases/fencing; and restart-safe recovery. The C-09 short name `BackgroundIntentV1` is an alias of C-08's `BackgroundOperationIntentV1`, never a duplicate DTO.

### Task Package: SBR-BG.1 — Canonical partition and lane-fair scheduler

**Goal**

- Add the deterministic two-level deficit-round-robin scheduler that chooses eligible C-08 partitions without owning persistence, effects, workers, or server lifecycle.

**Depends On**

- DA-06 `SBR-RECEIPT.1` through `.3` and frozen C-08 must be importable and behaviorally usable.

**Files to Read**

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SS-07, C-08, C-09, DA-07, and frozen budgets.
- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F2-F5 and technical-analysis sections C/D.
- `src/scribe_mcp/background/models.py` and `src/scribe_mcp/background/store.py` from DA-06.
- `tests/core/test_background_queue_contract.py` as the DA-09 consumer contract once present.

**Files to Modify**

- `src/scribe_mcp/background/scheduler.py` — scheduler configuration, deterministic DRR state, claim selection, and bounded queue/fairness metrics only.

**Files Forbidden**

- The other five SS-07 paths until their packages run; every receipt backend/model/store, schema, document, MCP, provider, Council, config, version, and test file.

**Public Contracts / Signatures**

- `BackgroundSchedulerConfigV1(global_concurrency: int, max_project_concurrency: int, control_reserved_slots: int, durable_reserved_slots: int, control_quantum: int = 1, durable_quantum: int = 1, heavy_quantum: int = 1, payload_quantum_bytes: int = 65536)`.
- `BackgroundSchedulerMetricsV1(ready: int, retry_wait: int, leased: int, pending_items: int, pending_bytes: int, item_high_water: int, byte_high_water: int, concurrency_high_water: int, starvation_windows_ge_5s: int, project_service_starts: tuple[tuple[str, int], ...], worker_claims: tuple[tuple[str, int], ...])`.
- `BackgroundSchedulerV1.__init__(store: BackgroundReceiptStoreV1, config: BackgroundSchedulerConfigV1, *, clock: Callable[[], datetime]) -> None`.
- `BackgroundSchedulerV1.recover() -> BackgroundRecoverySnapshotV1`.
- `BackgroundSchedulerV1.claim_next(worker_id: str, *, lease_ms: int) -> DurableOperationReceiptV1 | None`.
- `BackgroundSchedulerV1.metrics_snapshot() -> BackgroundSchedulerMetricsV1`.

**Implementation Constraints**

1. Derive partition identity only from `BackgroundPartitionV1(canonical_project_key, lane)`; caller/agent/persona labels, project display names, submission order, and provider metadata never key or order work.
2. Use C-08 `recover(clock())` as durable eligibility/capacity truth. Eligible states are `ready`, due `retry_wait`, and expired `leased`; terminal, future retry, cancelled, and per-project/global-cap-blocked work cannot consume a scheduling turn.
3. Enforce `global_concurrency` and `max_project_concurrency` at every decision. Heavy work may use only capacity remaining after both reserves; durable work may not consume the control reserve; control work may use any free slot. Reserves are strict while their lane has eligible work.
4. Run deterministic DRR over lanes and then canonical project keys. Charge `max(1, ceil(payload_bytes / payload_quantum_bytes))`; persist deficits/cursors only in scheduler memory and reconstruct them deterministically from canonical keys after restart. Skip ineligible partitions without burning a peer's turn.
5. Equal-weight continuously eligible projects differ by at most one unit-cost start per completed round and no project exceeds 50 percent service while a peer remains eligible. A newly eligible control job starts within one scheduler round; no continuously eligible project may accumulate a starvation window of 5 seconds or more.
6. A raced C-08 `claim` returning no receipt advances to the next bounded candidate; it never spins, blocks admission, holds a store transaction, or falls back to global FIFO.
7. Metrics use bounded lane/outcome/canonical-project labels only. Never expose operation IDs, payloads, raw agent labels, unbounded error text, or a second persisted result source.

**Required Tests**

- DA-09/Crucible adds deterministic cases to `tests/core/test_background_queue_contract.py`: three equal-weight projects, 12 unit jobs each, heavy global cap two, per-project cap one, one control reserve, strict item/byte/concurrency high-water bounds, retry-wait/cap skipping, weighted 2:1:1 share within one quantum, and 31 saturated A callers while B/C reach claim/completion before A releases.
- The same suite proves no cross-project HOL, zero starvation windows at least 5 seconds, no project above 50 percent while a peer is eligible, and stable choices for seed/config-independent canonical keys without sleeps.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.scheduler import BackgroundSchedulerConfigV1, BackgroundSchedulerMetricsV1, BackgroundSchedulerV1'`.
- `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py -m "core and regression and not slow and not performance"` (after DA-09 owns the test).
- `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py` (after DA-06/DA-09 land).

**Acceptance Criteria**

- [ ] Control, durable, and heavy lane reserves plus global/per-project caps hold at every scheduler checkpoint.
- [ ] Canonical partitions receive deterministic DRR service with no HOL, no 5-second starvation, at most one unit-job lead, and at most 50 percent share while a peer remains eligible.
- [ ] Item, byte, and concurrency high-water marks never exceed configuration; metrics remain bounded-cardinality and host-neutral.

**Out of Scope**

- Admission persistence, handler execution, retries, cancellation, service lifecycle, server wiring, Council/provider policy, and test-file edits.

**Handoff Notes**

- Forge: implement only `scheduler.py`; stop if C-08 or another source path must change.
- Crucible: own the manual-clock/gated-worker DA-09 tests and assert causal progress, not wall-clock luck.
- Sentinel: review partition-key isolation, byte-cost validation, bound bypasses, starvation/DoS behavior, and metric-label disclosure.
- Arbiter: require one two-level DRR path over C-08; reject global FIFO, duplicate queues, sleeps, or host-specific branching.

### Task Package: SBR-BG.2 — Fenced worker, finite retry, and cancellation protocol

**Goal**

- Execute one claimed receipt through a host-injected idempotent handler, preserving C-08 state-version/fence authority across success, finite seeded retry, permanent failure, cancellation, worker death, and restart.

**Depends On**

- `SBR-BG.1`.
- Frozen C-08 transition and fencing semantics from DA-06.

**Files to Read**

- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F5-F8 and technical-analysis section F.
- `src/scribe_mcp/background/models.py`, `store.py`, and `scheduler.py`.
- `tests/core/test_wal_replay_exactly_once.py` and `tests/core/test_background_queue_contract.py` as DA-09 consumer contracts.

**Files to Modify**

- `src/scribe_mcp/background/worker.py` — worker loop, handler protocol, seeded retry calculation, operation-local cancellation gate, and worker metrics only.

**Files Forbidden**

- `__init__.py`, `service.py`, `server.py`, `health_check.py`, every receipt/storage/schema/document/MCP/provider/Council/config/version/test file, and `scheduler.py` after `SBR-BG.1`.

**Public Contracts / Signatures**

- `BackgroundExecutionKind = Literal["succeeded", "transient_failure", "permanent_failure"]`.
- `BackgroundExecutionOutcomeV1(kind: BackgroundExecutionKind, result_ref: str | None = None, error_code: str | None = None)`.
- `BackgroundCancellationProbeV1.is_cancel_requested() -> bool` and `BackgroundCancellationProbeV1.mark_commit_started() -> None`.
- `BackgroundJobHandlerV1 = Callable[[DurableOperationReceiptV1, BackgroundCancellationProbeV1], Awaitable[BackgroundExecutionOutcomeV1]]`.
- `SeededRetryPolicyV1(max_attempts: int, base_delay_ms: int, max_delay_ms: int, jitter_ms: int, seed: int)`.
- `SeededRetryPolicyV1.next_attempt_at(receipt: DurableOperationReceiptV1, *, now: datetime) -> datetime | None`.
- `BackgroundWorkerStepV1(worker_id: str, operation_id: str | None, outcome: Literal["idle", "succeeded", "retry_wait", "failed_terminal", "cancelled", "stale_fence"])`.
- `BackgroundWorkerV1.__init__(worker_id: str, scheduler: BackgroundSchedulerV1, store: BackgroundReceiptStoreV1, handler: BackgroundJobHandlerV1, retry_policy: SeededRetryPolicyV1, *, lease_ms: int, clock: Callable[[], datetime]) -> None`.
- `BackgroundWorkerV1.run_once() -> BackgroundWorkerStepV1`, `request_cancel(operation_id: str) -> bool`, and `stop_claiming() -> None`.

**Implementation Constraints**

1. Only `scheduler.claim_next` obtains a lease. Every completion/retry/failure/cancel transition supplies the claimed receipt's exact `state_version` and `fencing_token`; stale-fence or CAS rejection produces no effect, retry, capacity release, or success claim.
2. Compute retry delay from a stable hash of configured seed, operation ID, and attempt count. Shared RNG state, wall-clock sleeps, unbounded loops, and host/process identity are forbidden. `max_attempts` is finite; malformed/permanent failures never retry; an exhausted transient failure becomes `failed_terminal`.
3. The handler is injected and host-neutral. It receives the durable operation ID as its idempotency authority and must make any external authoritative effect idempotent. A post-effect/pre-transition crash may re-execute, but the exact-effects oracle permits only one authoritative effect.
4. Cancellation before commit wins atomically: queued/retry work is transitioned by the service; leased work is signalled through the operation-local probe and the worker transitions `cancelled` with its fence. After `mark_commit_started`, cancellation cannot falsely report `cancelled`; the committed result is allowed to finish and become `succeeded`.
5. Worker death leaves the lease durable. Recovery may reclaim only after expiry through a higher C-08 fence; a late worker result is a typed stale-fence outcome and never mutates receipt/effect state.
6. `stop_claiming` prevents new claims but does not blanket-cancel an active authoritative commit. `run_once` is the deterministic test seam; any long-running loop is owned by the service and waits on injected events/deadlines.
7. Worker metrics count bounded outcomes, attempts, retries, lease expiry, cancellation, dead-letter, stale-fence rejection, and claims by stable worker ID; they contain no payload or unbounded error text.

**Required Tests**

- DA-09/Crucible extends `tests/core/test_background_queue_contract.py` with seeded attempt-one transient failure, due retry, finite exhaustion, permanent failure, pre-claim and leased cancellation barriers, non-interruptible commit race, worker death, higher-fence reclaim, stale completion rejection, and equal-capacity worker claim imbalance at most one across 32 unit jobs.
- DA-09/Crucible extends `tests/core/test_wal_replay_exactly_once.py` for post-effect/pre-success crash: the handler/effect sink deduplicates by operation ID and final receipt/effect cardinality is exactly one.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.worker import BackgroundCancellationProbeV1, BackgroundExecutionOutcomeV1, BackgroundWorkerStepV1, BackgroundWorkerV1, SeededRetryPolicyV1'`.
- `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"` (after DA-09 owns the tests).
- `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py` (C-08 transition neighbor).

**Acceptance Criteria**

- [ ] Lease ownership, state version, and fencing token gate every worker transition; zero stale completions are accepted.
- [ ] Retry timing is finite, seeded, deterministic, restart-safe, and terminal on permanent/malformed/exhausted outcomes.
- [ ] Cancellation races yield only enumerated cardinality-clean outcomes; worker death/restart loses no accepted receipt or authoritative effect.

**Out of Scope**

- Handler implementations, document mutation, admission, scheduler policy changes, process management, server wiring, Council/provider behavior, and test-file edits.

**Handoff Notes**

- Forge: implement only `worker.py`; stop on any need to widen C-08 or effect ownership.
- Crucible: use manual time and explicit barriers; prove effect cardinality and stale-fence rejection without sleeps.
- Sentinel: review cancellation/commit races, retry amplification, untrusted handler errors, stale workers, and operation/result reference exposure.
- Arbiter: require one finite state path, deterministic retry, and explicit commit boundary; reject catch-all retries or task cancellation as shutdown.

### Task Package: SBR-BG.3 — BackgroundJobServiceV1 admission, recovery, metrics, and API

**Goal**

- Compose C-08, the scheduler, and workers behind the frozen C-09 API, with typed non-admission, zero-lost restart recovery, bounded metrics, and idempotent start/stop.

**Depends On**

- `SBR-BG.1` and `SBR-BG.2`.
- DA-06 C-08 backend parity must be available for the selected storage backend.

**Files to Read**

- `PHASE_PLAN.md#sbr-receipt-store` exact C-08 models and outcomes.
- `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F1-F3, F6-F9, and Q1-Q3.
- `src/scribe_mcp/background/models.py`, `store.py`, `scheduler.py`, and `worker.py`.
- `tests/core/test_background_queue_contract.py` as the DA-09 consumer contract.

**Files to Modify**

- `src/scribe_mcp/background/service.py` — C-09 service/config/errors/health/shutdown receipt and worker ownership.
- `src/scribe_mcp/background/__init__.py` — explicit C-08/C-09 public exports and the `BackgroundIntentV1` alias only.

**Files Forbidden**

- `server.py`, `health_check.py`, every receipt backend/model/store, schema, document effect, MCP/provider/Council/config/version/test file, and prior scheduler/worker paths after their packages.

**Public Contracts / Signatures**

- `BackgroundIntentV1 = BackgroundOperationIntentV1`; this is an alias, not a subclass or copied dataclass.
- `BackgroundServiceConfigV1(queue_limits: BackgroundQueueLimitsV1, scheduler: BackgroundSchedulerConfigV1, worker_count: int, lease_ms: int, retry_policy: SeededRetryPolicyV1, drain_deadline_ms: int)`.
- `BackgroundQueueEventV1(kind: str, observed_at: datetime, lane: BackgroundLane | None, outcome: str, canonical_project_key_hash: str | None, duration_ms: int | None, value: int | None)`; kind/outcome are validated closed vocabularies and the project label is a non-reversible hash.
- `BackgroundServiceHealthV1(state: Literal["stopped", "starting", "running", "draining", "degraded"], accepting: bool, workers_active: int, metrics: BackgroundSchedulerMetricsV1, accepted_receipts: int, recovered_receipts: int, stale_fence_rejections: int, drain_deadline_exceeded: bool)`.
- `BackgroundShutdownReceiptV1(admission_closed: bool, drain_deadline_ms: int, drained: int, checkpointed: int, cancelled_retryable: int, remaining_recoverable: int, workers_stopped: int, deadline_exceeded: bool, stopped_at: datetime)`.
- `BackgroundDigestConflictError`, `BackgroundQueueBusyError(retry_after_ms: int)`, `BackgroundServiceShuttingDownError`, and `BackgroundOperationNotFoundError` are the only C-09 service errors.
- `BackgroundJobServiceV1.__init__(store: BackgroundReceiptStoreV1, handler: BackgroundJobHandlerV1, config: BackgroundServiceConfigV1, *, clock: Callable[[], datetime], emit: Callable[[BackgroundQueueEventV1], None]) -> None`.
- `submit(intent: BackgroundIntentV1) -> DurableOperationReceiptV1`, `get_status(operation_id: str) -> DurableOperationReceiptV1`, `cancel(operation_id: str, expected_state_version: int) -> DurableOperationReceiptV1`, `start() -> None`, `stop(admission_close: bool = True, drain_deadline_ms: int | None = None) -> BackgroundShutdownReceiptV1`, and `health_snapshot() -> BackgroundServiceHealthV1` are async methods.

**Implementation Constraints**

1. `submit` performs only validation, C-08 atomic admission, durable receipt readback, and bounded event emission. Accepted and duplicate outcomes return the original durable receipt; digest conflict, capacity busy, and admission closed raise the exact typed errors with zero hidden task/effect. It never waits for capacity or a worker.
2. Pass both item and serialized-byte global/per-project bounds through `BackgroundQueueLimitsV1`. Ready, retry-wait, and leased work retain capacity until one terminal transition; terminal/cancel release occurs once in C-08.
3. `start` is idempotent. It calls `recover(clock())` before opening claims/admission, reconstructs every nonterminal receipt and capacity, starts exactly `worker_count` in-process worker loops, and records recovered receipts without manufacturing or discarding work.
4. `get_status` and `cancel` authorize only by the caller's already-resolved service boundary; they never select projects from labels. Cancellation validates `expected_state_version`; queued/retry work transitions terminal immediately, leased work uses the worker's operation-local gate, and terminal/non-interruptible commit outcomes return their durable truth.
5. `stop` closes admission first, lets in-flight foreground receipt commits finish, stops new claims, cooperatively drains to the configured deadline, checkpoints all remaining nonterminal receipts through C-08 truth, cancels only retryable pre-commit work, fences late completions, stops workers, and returns exact counts. A deadline exceedance is typed in the receipt, never silent success.
6. Emit one event stream through the injected sink; do not persist a second metrics/result store. Required measures include receipt acknowledgement, depth/bytes/state counts, high-water marks, queue wait/run time, admission outcomes/retry-after, attempts/retries/dead-letter/cancellation/lease expiry/stale fence, worker claims/concurrency, project share/starvation, and shutdown/recovery counts.
7. Foreground submit/status/cancel and durable receipt acknowledgement target p95 at most 500 ms on the recorded reference profile. Any stage above 100 ms and total above 500 ms carries the existing DA-05 correlation envelope; this service emits queue-specific events but does not duplicate C-12 timing authority.
8. Export only the canonical types through `background/__init__.py`. No provider, Council, seat, work-item, spawn, process-count, process-reuse, or idle-reap field or branch is allowed.

**Required Tests**

- DA-09/Crucible adds admission and lifecycle cases to `tests/core/test_background_queue_contract.py`: exact last item/byte slot under 32 admissions, duplicate/conflict/busy/shutdown outcomes, prompt typed backpressure, start/restart in ready/leased/retry-wait, zero lost accepted receipt, status/cancel CAS, finite drain, deadline checkpoint, and exact metric deltas.
- DA-09 composes the existing `tests/core/test_swarm_binding_reliability.py` 32 same-label sessions × 100 mixed calls with receipt operations; final accepted IDs equal durable receipts, successful IDs equal effects once, and wrong target/default drift/cross-talk/lost accepted work are all zero.
- DA-10 owns the `SCRIBE_SWARM_PROFILE=background-queue` PostgreSQL/process proof in `tests/integration/test_swarm_concurrency_stress.py`; SS-07 Forge does not edit either validation path.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background import BackgroundIntentV1, BackgroundJobServiceV1, BackgroundServiceConfigV1, BackgroundServiceHealthV1, BackgroundShutdownReceiptV1'`.
- `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_swarm_binding_reliability.py tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"` (after DA-09 owns the tests).
- `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py`.

**Acceptance Criteria**

- [ ] Every accepted or duplicate submit returns durable C-08 truth; every conflict/busy/shutdown path is typed, prompt, and effect-free.
- [ ] Fresh service reconstruction finds every accepted nonterminal receipt, rebuilds exact capacity, and loses zero receipts across forced restart.
- [ ] Under 32 callers, foreground control/read and receipt acknowledgement p95 are at most 500 ms, bounds never exceed config, and required metrics agree with receipt history.

**Out of Scope**

- Concrete job handlers/effects, C-08 persistence, server startup/shutdown hooks, external process policy, Council/provider logic, release/deploy work, and test-file edits.

**Handoff Notes**

- Forge: modify only `service.py` and exports in `__init__.py`; stop if persistence, effect, or server ownership is needed.
- Crucible: own DA-09/DA-10 proof and retain raw event counts, receipt/effect ledgers, source revision, bounds, seed, and reference profile.
- Sentinel: review typed overload, receipt authorization/isolation, project-hash labels, event data exposure, restart/cancel/drain races, and resource exhaustion.
- Arbiter: require one C-09 façade over C-08, one event sink, idempotent lifecycle, and no duplicate DTO/store/queue.

### Task Package: SBR-BG.4 — Server lifecycle integration and bounded health projection

**Goal**

- Attach the C-09 service to Scribe startup/shutdown and health without changing core-ready semantics, transport contracts, or host process policy.

**Depends On**

- `SBR-BG.3`.
- DA-03 may later consume C-09 for startup-ready policy, but this package owns only `server.py#background_lifecycle`.

**Files to Read**

- `src/scribe_mcp/server.py::BackgroundServiceStatus`, `get_background_service_status`, `schedule_background_task`, `drain_background_tasks`, `_startup`, and `_shutdown`.
- `src/scribe_mcp/tools/health_check.py::health_check`.
- `research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` P2/P5 and `RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F8/F9/Q3.
- Existing neighbors `tests/test_execution_context.py`, `tests/test_server_invoke_tool_startup_bypass.py`, and `tests/test_health_check.py`.

**Files to Modify**

- `src/scribe_mcp/server.py#background_lifecycle` — C-09 construction/accessor/start/stop integration and legacy task compatibility only.
- `src/scribe_mcp/tools/health_check.py` — bounded `background_job_service` component/metrics projection only.

**Files Forbidden**

- Every other `server.py` anchor, especially DA-03 `startup_ready`; all background scheduler/worker/service files after prior packages; all receipt/storage/schema/object-store/document/MCP/provider/Council/config/version/test files.

**Public Contracts / Signatures**

- Preserve `schedule_background_task(coro, *, service_name: str | None = None, description: str = "", persistent: bool = False) -> asyncio.Task`.
- Preserve `drain_background_tasks(*, timeout: float | None = None) -> list[BaseException]` and `get_background_service_status() -> dict[str, dict[str, Any]]` for legacy process-local services.
- Add `get_background_job_service() -> BackgroundJobServiceV1 | None`.
- Add `get_background_job_service_health() -> BackgroundServiceHealthV1 | None`.
- Preserve `_startup(*, startup_profile: str = "full_server") -> None`, `_shutdown() -> None`, and `health_check(agent: str) -> dict[str, Any]`.
- `health_check` adds `components.background_job_service` and bounded queue/worker metrics while preserving all existing top-level keys.

**Implementation Constraints**

1. Construct one `BackgroundReceiptStoreV1` and one `BackgroundJobServiceV1` from the selected Scribe `storage_backend`; publish the service on server state and start it exactly once after authoritative storage setup. No alternate in-memory fallback is permitted when C-08 is unsupported.
2. Keep `schedule_background_task` only for named, process-local compatibility chores such as initialization/cleanup loops. Receipt-producing accepted work must flow through C-09; no accepted durable job may be represented only by `asyncio.Task` or the legacy `background_tasks` set.
3. Preserve DA-03's core-ready boundary: service recovery is required before new C-09 admission, while optional remote probes/effects remain background/degraded and cannot block core tools or local durable logging.
4. Shutdown order is exact: set transport/admission draining; finish in-flight foreground durable receipt commits; call C-09 `stop(admission_close=True, drain_deadline_ms=configured)`; stop/checkpoint workers and fence late completion; drain/cancel remaining legacy retryable process tasks; close storage/document clients; publish `closed`; emit one terminal lifecycle event.
5. A drain deadline never discards accepted work. Every nonterminal receipt is still queryable/recoverable after fresh startup; shutdown receipt counts and service health expose deadline exceedance, remaining recoverable work, stale-fence rejection, and zero lost accepted receipts.
6. Health output reports only bounded fields from `BackgroundServiceHealthV1`: state/accepting, worker/state counts, item/byte/concurrency high-water marks, stale fences, starvation windows, accepted/recovered counts, and drain status. Do not emit raw operation IDs, payloads, caller labels, unbounded project names, errors, or per-host process policy.
7. Existing background-service status and transport shutdown tests remain compatible. Do not add Council/provider imports or process count/reuse/lease/idle-reap behavior.

**Required Tests**

- DA-09/Crucible extends `tests/test_execution_context.py` for legacy helper compatibility and verifies durable accepted work is absent from the raw `background_tasks` set.
- DA-09/Crucible extends `tests/test_server_invoke_tool_startup_bypass.py` for exactly-once service start, recovery-before-admission, admission-close-before-drain, drain-before backend close, deadline checkpoint, and idempotent repeated shutdown.
- DA-09/Crucible extends `tests/test_health_check.py` for healthy/degraded/draining projections, exact bounded metrics, no raw identifiers, and no regression of existing component/top-level fields.
- DA-09 keeps restart/shutdown causal cases in `tests/core/test_background_queue_contract.py`; DA-10 alone runs the PostgreSQL/process shutdown/restart profile.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp import server; from scribe_mcp.background import BackgroundJobServiceV1; from scribe_mcp.tools.health_check import health_check; assert hasattr(server, "get_background_job_service")'`.
- `./.venv/bin/pytest -q tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_health_check.py`.
- `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"` (after DA-09 owns the tests).

**Acceptance Criteria**

- [ ] Startup reconstructs C-08 truth and starts one bounded worker service without changing core-ready semantics or using legacy task tracking for accepted jobs.
- [ ] Shutdown closes admission before claims, drains/checkpoints before backend close, leaks zero workers/tasks/handles above baseline, and loses zero accepted receipts.
- [ ] Health exposes bounded scheduler/worker/recovery/drain metrics and no raw identifiers or host/provider/Council policy.

**Out of Scope**

- DA-03 startup/import/object-store implementation, C-08 storage/schema, job effects, Council/provider process lifecycle, deployment/adoption, and test-file edits.

**Handoff Notes**

- Forge: modify only the named server lifecycle symbols and health projection; stop if startup-ready or another server anchor must change.
- Crucible: assert event ordering and fresh-runtime recovery with gates/manual time; hold the PostgreSQL/process lane for DA-10.
- Sentinel: review shutdown race safety, fail-closed store support, health redaction/cardinality, and accepted-work durability.
- Arbiter: require legacy compatibility plus one durable path; reject blanket task cancellation, hidden fallback queues, or process-policy leakage.

### Package order and gate

1. Implement `SBR-BG.1`, then `.2`, then `.3`, then `.4`; each package is independently importable before the next begins.
2. DA-09 owns hermetic scheduler/worker/service/lifecycle tests and the 32 same-label caller composition; DA-10 owns the single PostgreSQL/process stress lane. SS-07 implementers do not edit those tests.
3. The release gate requires: 32 callers; foreground control/read and receipt acknowledgement p95 at most 500 ms; zero wrong target/default drift/cross-talk/lost accepted receipts/duplicate effects/stale-fence acceptance; zero continuously eligible starvation windows at least 5 seconds; no project above 50 percent service while a peer remains eligible; equal-capacity worker claims differ by at most one; bounds never exceed configuration; zero post-teardown leaks.
4. Sentinel and Arbiter PASS are mandatory for all four packages because SS-07 is concurrency-, durability-, lifecycle-, resource-exhaustion-, and high-blast-radius sensitive.
## DA-03 — Startup and import readiness detail
<!-- ID: sbr-startup-readiness -->
### APPROACH_SUMMARY

- Goal: make the standalone Scribe process lightweight and core-ready without letting token vocabulary load, metrics-path mutation, optional object-store health, or bridge health gate the MCP ready signal.
- Files to modify: exactly the five SS-03 paths, partitioned pairwise-disjoint across `SBR-STARTUP.1` through `.3`.
- Files forbidden: every unlisted source/test/config/generated/Council path; especially `src/scribe_mcp/object_store/base.py`, `src/scribe_mcp/object_store/__init__.py`, `src/scribe_mcp/tools/health_check.py`, `src/scribe_mcp/background/**`, `src/scribe_mcp/storage/**`, `tests/**`, and all process/provider ownership surfaces.
- Out of scope: schema/bootstrap implementation, background scheduler/worker/service implementation, Council process count/reuse/idle-reap policy, deployment/adoption, versioning, and test-file edits.
- Verification plan: prove import laziness and filesystem purity first; prove nonblocking remote health second; integrate frozen C-07/C-09 into the core-ready boundary third; then let DA-10 own the reference-profile import/RSS/startup/outage gates.
- Readiness: C-07 and C-09 are frozen and their producer packages are explicit predecessors. The three implementation packages are bounded and independently reviewable; release readiness remains dependent on DA-10 performance evidence and Arbiter PASS.

Frozen surfaces: C-07 is `ensure_schema_ready(deadline_ms: int) -> SchemaReadinessV1`; C-09 is `BackgroundJobServiceV1` with recovery-before-admission and bounded start/stop; C-10 is `ServiceStateV1(service, state, required_for_core_ready, last_error_code, last_transition_at, startup_phase_ms)`, where state is exactly `initializing|healthy|degraded|stopped` and optional remote/plugin/bridge services cannot block core-ready.

### Task Package: SBR-STARTUP.1 — Lazy utility exports and token encoder

**Goal**

- Remove the eager `utils -> response -> tokens -> tiktoken encoder` import chain while preserving all existing utility exports, cheap estimation, accurate counting on demand, token metrics, and budget behavior.

**Depends On**

- Frozen SS-03/C-10 scope only; no implementation predecessor.
- May run in parallel with `SBR-STARTUP.2`.

**Files to Read**

- `research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` findings F2 and package P1.
- `src/scribe_mcp/utils/response.py`, `src/scribe_mcp/utils/context_safety.py`, `src/scribe_mcp/utils/estimator.py`, and `src/scribe_mcp/utils/formatters/base.py` for current import/call compatibility.
- `tests/test_estimator.py` and `tests/test_release_startup_probe.py`.

**Files to Modify**

- `src/scribe_mcp/utils/__init__.py` — preserve the public export set but lazily resolve response/token symbols.
- `src/scribe_mcp/utils/tokens.py` — lazy tiktoken import/encoder construction and deferred metrics-directory creation.

**Files Forbidden**

- Every response/formatter/context-safety/estimator caller; all object-store, server, storage, background, config, test, benchmark, Council, version, and generated paths.
- No new utility module, global cache service, or replacement estimator.

**Public Contracts / Signatures**

- Preserve `TokenEstimator.__init__(self, model: str = "gpt-4", daily_limit: int = 100000, operation_limit: int = 8000)`.
- Preserve the one-positional-argument call and add only the backward-compatible selector `TokenEstimator.estimate_tokens(self, data: Union[str, Dict, List, Any], *, exact: bool = True) -> int`.
- Add `TokenEstimator.estimate_tokens_cheap(self, data: Union[str, Dict, List, Any]) -> int`; it must never import tiktoken.
- Preserve `TokenEstimator.estimate_response_tokens`, `record_operation`, `get_usage_stats`, `get_tokenizer_info`, `save_metrics`, and `load_metrics`.
- Preserve `token_estimator: TokenEstimator` and the current `scribe_mcp.utils.__all__` names. Add module `__getattr__(name: str) -> Any` only as the lazy compatibility seam.

**Implementation Constraints**

1. Remove module-level `import tiktoken`. Resolve/import tiktoken and construct the model encoder only inside one private, concurrency-safe first-use helper reached by `estimate_tokens(..., exact=True)` or an exact tokenizer-info request. Unknown models retain the `cl100k_base` fallback.
2. `TokenEstimator()` construction may load environment budget values and allocate in-memory fields only. It must not import tiktoken, load a vocabulary, create `~/.scribe_metrics`, open `token_usage.json`, or write any file.
3. `estimate_tokens_cheap` and `estimate_tokens(..., exact=False)` use the existing deterministic character/JSON approximation. Exact mode lazily loads the encoder; unavailable tiktoken falls back to the same cheap estimator without an import-time warning.
4. Preserve module-level `token_estimator` for direct callers, but make its construction side-effect-free. Create the metrics directory immediately before the first `save_metrics` write; `load_metrics` may read an existing file but must not create a path.
5. Keep `utils.__all__` stable. Existing file/slug/time exports may remain eager; response/token symbols resolve on first attribute access and cache in module globals. Importing `scribe_mcp.utils.sentinel_logs` must not import `response`, `tokens`, or `tiktoken`.
6. Do not change token budget defaults, persisted metrics shape, history bounds, public result dictionaries, or caller behavior outside the additive `exact` selector.

**Required Tests**

- Existing `tests/test_estimator.py::TestTokenEstimator` remains green for strings, dict/list payloads, and response breakdowns.
- DA-10/Crucible extends `tests/test_release_startup_probe.py` with `test_server_import_is_token_lazy_and_filesystem_pure`: a fresh isolated home imports `scribe_mcp.server`, observes no `tiktoken` module/encoder and no metrics path mutation, then proves cheap mode remains lazy and exact mode loads once.
- DA-10/Crucible adds `test_server_import_and_all_tools_loaded_meet_time_and_rss_budgets`: five cold/warm fresh-process samples retain raw elapsed/RSS values and enforce the frozen p95/steady bounds.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'import sys; import scribe_mcp.server; assert "tiktoken" not in sys.modules; from scribe_mcp.utils.tokens import TokenEstimator, token_estimator; assert token_estimator.encoder is None; assert TokenEstimator().estimate_tokens_cheap("abcd") == 1'`
- `./.venv/bin/pytest -q tests/test_estimator.py::TestTokenEstimator`
- `./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_server_import_is_token_lazy_and_filesystem_pure tests/test_release_startup_probe.py::test_server_import_and_all_tools_loaded_meet_time_and_rss_budgets` (after DA-10 owns the tests).
- `for i in 1 2 3 4 5; do /usr/bin/time -f "run=$i elapsed_s=%e maxrss_kb=%M" ./.venv/bin/python -c 'import scribe_mcp.server'; done`

**Acceptance Criteria**

- [ ] Importing `scribe_mcp.server` or `scribe_mcp.utils.tokens` performs zero metrics-path writes and leaves tiktoken/encoder unloaded.
- [ ] Cheap estimation is deterministic and encoder-free; the first exact request initializes one reusable encoder and preserves fallback behavior.
- [ ] The existing `scribe_mcp.utils` export names and token metrics/budget result shapes remain compatible.
- [ ] DA-10 evidence proves warm import p95 at most 1.0 s, cold import p95 at most 1.5 s, pre-tool-ready RSS at most 64 MiB, and all-tools-loaded steady RSS at most 80 MiB.

**Out of Scope**

- Response formatting behavior, token budget redesign, async analytics, caller rewrites, object-store/startup work, dependency removal, and test-file edits.

**Handoff Notes**

- Forge: edit only the two declared utility files; stop if a response/formatter caller change appears necessary.
- Crucible: own DA-10 probe additions and retain per-run elapsed/RSS/module/filesystem evidence, not only aggregate PASS.
- Arbiter: require stable exports, zero import-time I/O, one lazy encoder path, deterministic cheap fallback, and no duplicate estimator/cache module.

### Task Package: SBR-STARTUP.2 — Nonblocking optional object-store health

**Goal**

- Separate remote-client construction from remote availability probing so a configured or unavailable CortaStore cannot delay core readiness, while preserving local-first durability and existing remote operations.

**Depends On**

- Frozen SS-03/C-10 scope only; no implementation predecessor.
- May run in parallel with `SBR-STARTUP.1`; must land before `SBR-STARTUP.3`.

**Files to Read**

- `research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` finding F3 and package P2.
- `src/scribe_mcp/object_store/base.py` lifecycle contracts and `src/scribe_mcp/object_store/__init__.py::create_document_store`.
- `tests/test_object_store_hybrid.py`, `tests/test_object_store_providers.py`, and `tests/test_release_startup_probe.py`.

**Files to Modify**

- `src/scribe_mcp/object_store/hybrid.py` — optional remote-health delegation only.
- `src/scribe_mcp/object_store/providers/corta.py` — separate client setup from bounded health probe.

**Files Forbidden**

- `src/scribe_mcp/object_store/base.py`, the object-store factory/registry, filesystem/S3 providers, server, health tool, storage/background/config/test/benchmark/Council/version/generated paths.
- No second client, retry queue, circuit-breaker service, or remote durability authority.

**Public Contracts / Signatures**

- Preserve `HybridStore.setup(self) -> None`, `close`, and all `DocumentStore` methods.
- Add `HybridStore.probe_remote_health(self, *, timeout_seconds: float = 2.0) -> bool | None`; `None` means the configured provider exposes no probe.
- Preserve `CortaStoreProvider.setup(self) -> None` and `close`.
- Add `CortaStoreProvider.probe_health(self, *, timeout_seconds: float = 2.0) -> bool`.

**Implementation Constraints**

1. `CortaStoreProvider.setup` creates/reuses the `httpx.AsyncClient` only. It performs zero network request, retry, sleep, DNS probe, or health logging.
2. `probe_health` performs exactly one `GET /health` with the supplied timeout capped independently from normal request retry/backoff. It returns true only for HTTP 200, false for other responses or transport failure, propagates cancellation, and never logs keys, signatures, response bodies, or raw credentials.
3. `HybridStore.setup` remains the lifecycle adapter and awaits only the now-local provider setup. `probe_remote_health` delegates once when supported and returns `None` for providers without the optional method; it does not change read/write/delete semantics.
4. Preserve one client per provider. `_ensure_client`, normal operation retry/backoff, signing, content addressing, local-first writes, local cache reads, and close idempotency remain unchanged.
5. Do not schedule work in these files. SBR-STARTUP.3 owns when the optional probe runs and how C-10 records healthy/degraded state.

**Required Tests**

- Existing `tests/test_object_store_hybrid.py` and `tests/test_object_store_providers.py` remain green.
- DA-10/Crucible adds `tests/test_release_startup_probe.py::test_optional_object_store_probe_is_not_in_foreground_startup` proving setup performs zero network request and the explicit probe performs one bounded request.
- DA-10/Crucible adds `test_optional_object_store_outage_adds_at_most_50_ms_and_preserves_local_durability` with a deterministic unavailable remote, raw startup delta, successful core tool listing, and successful local durable append.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.object_store.hybrid import HybridStore; from scribe_mcp.object_store.providers.corta import CortaStoreProvider; assert callable(HybridStore.probe_remote_health); assert callable(CortaStoreProvider.probe_health)'`
- `./.venv/bin/pytest -q tests/test_object_store_hybrid.py`
- `./.venv/bin/pytest -q tests/test_object_store_providers.py`
- `./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_optional_object_store_probe_is_not_in_foreground_startup tests/test_release_startup_probe.py::test_optional_object_store_outage_adds_at_most_50_ms_and_preserves_local_durability` (after DA-10 owns the tests).

**Acceptance Criteria**

- [ ] Provider/store setup performs zero remote health I/O and remains close-idempotent.
- [ ] The explicit health probe is one bounded request with boolean/unsupported truth and cancellation safety.
- [ ] Local-first document persistence and every existing remote operation remain behaviorally compatible.
- [ ] DA-10 evidence proves an optional outage adds at most 50 ms to foreground startup and cannot block core tool listing or local durable logging.

**Out of Scope**

- Server scheduling/service states, S3 health behavior, normal remote-operation retries, write semantics, queueing, circuit breaking, provider registry/config, and test-file edits.

**Handoff Notes**

- Forge: modify only the two declared object-store files; stop if base/factory/provider-registry changes appear necessary.
- Crucible: use deterministic fake transport/manual timing for unit behavior and reserve real reference-profile timing for DA-10.
- Arbiter: require zero network in setup, one client, one explicit probe, unchanged local-first semantics, and no hidden scheduler/retry subsystem.

### Task Package: SBR-STARTUP.3 — C-10 core-ready and optional-service states

**Goal**

- Make `Server ready` mean required C-07 storage/schema readiness plus recovered/running C-09 background service, while object-store and bridge health continue asynchronously through exact C-10 service states.

**Depends On**

- `SBR-STARTUP.1` and `SBR-STARTUP.2`.
- `SBR-SCHEMA.3` produces frozen C-07 through `PostgresStorage.setup -> ensure_schema_ready(deadline_ms=2500)`.
- `SBR-BG.4` produces frozen C-09 server construction/start/stop and health accessors. Do not reimplement or edit its lifecycle symbols.

**Files to Read**

- SEAM_MAP SS-03 and frozen C-07/C-09/C-10.
- PHASE_PLAN `SBR-SCHEMA.3` and `SBR-BG.4`.
- `src/scribe_mcp/server.py::BackgroundServiceStatus`, `get_background_service_status`, `schedule_background_task`, `_init_bridges_background`, `_startup`, and `_shutdown`.
- `src/scribe_mcp/tools/health_check.py`, `tests/test_server_invoke_tool_startup_bypass.py`, `tests/test_health_check.py`, and `tests/test_release_startup_probe.py`.

**Files to Modify**

- `src/scribe_mcp/server.py#startup_ready` only — C-10 type/state helpers, required-service ready assertion, optional probe/wrapper scheduling, startup timing, and the ready transition.

**Files Forbidden**

- `src/scribe_mcp/server.py#background_lifecycle`, including C-09 construction/accessor/start/stop and shutdown ordering owned by `SBR-BG.4`.
- Every other source path, especially health_check, background, storage/schema, object-store after `SBR-STARTUP.2`, bridge implementation, MCP adapter, config, tests, benchmarks, Council, version, and generated files.

**Public Contracts / Signatures**

- Add `ServiceStateNameV1 = Literal["initializing", "healthy", "degraded", "stopped"]`.
- Add frozen `ServiceStateV1(service: str, state: ServiceStateNameV1, required_for_core_ready: bool, last_error_code: str | None, last_transition_at: str, startup_phase_ms: float | None)`.
- Add `get_service_states() -> dict[str, dict[str, Any]]`, returning bounded serializable C-10 snapshots keyed by service.
- Preserve `_startup(*, startup_profile: str = "full_server") -> None`, `_shutdown() -> None`, `get_background_service_status() -> dict[str, dict[str, Any]]`, and DA-07's C-09 accessors unchanged.

**Implementation Constraints**

1. Reuse C-07 by treating successful `storage_backend.setup()` as the required schema/storage ready edge; propagate its typed fail-closed error and never emit core-ready after `SchemaReadinessV1.ready=false`. Record only bounded phase duration and typed error code in C-10.
2. Reuse C-09 from SBR-BG.4. Before core-ready, require its health snapshot to be running and accepting after recovery; do not construct, start, stop, drain, schedule, or persist a second service here.
3. `_startup_complete` means core-ready, not startup-entered: set it only after every `required_for_core_ready=true` state is healthy and immediately before the existing `Server ready` signal. A failed required service leaves startup retryable through the existing lifecycle path and emits no false ready signal.
4. Construct and locally set up the document store, publish it on `app.state`, register `object_store_remote` as optional/initializing, and schedule its explicit SBR-STARTUP.2 health probe through the existing legacy task tracker. Probe completion transitions to healthy; false/exception transitions to degraded with a stable error code. It never delays core-ready.
5. Wrap the already-background bridge initialization only to transition optional `bridge_init` state from initializing to healthy/degraded. Preserve its existing discovery/activation, failure logging, monitor scheduling, and custom-tool registration; do not add suppression policy, persistence, or retry.
6. C-10 outputs contain only the six frozen fields, stable service names/error codes, ISO UTC transition time, and bounded phase milliseconds. Never expose exception text, URLs, credentials, manifest payloads, operation IDs, project labels, host/process policy, or unbounded histories.
7. Preserve startup profiles: `local_only` still skips startup; `storage_only` and `full_server` retain their existing authoritative storage/C-09 policy; optional services may be absent/stopped where the profile does not schedule them. Optional degraded/stopped states never downgrade core tools or local durable logging.
8. Preserve SBR-BG.4 shutdown order exactly. Existing cancellation/drain closes optional tasks before document-store clients; repeated shutdown remains idempotent and leaks zero new tasks/clients.
9. Emit `startup_phase_ms` per service plus total startup timing already stored in `_last_runtime_timing`. Meet warm ready p95 <=1.5 s and cold ready p95 <=2.5 s without weakening C-07/C-09 durability.

**Required Tests**

- Existing `tests/test_server_invoke_tool_startup_bypass.py` and `tests/test_health_check.py` remain green, including SBR-BG.4 lifecycle/health additions when present.
- DA-10/Crucible adds `tests/test_release_startup_probe.py::test_core_ready_requires_c07_and_c09_but_not_optional_services`, covering false-ready denial, C-10 exact fields/states, C-09 recovery-before-ready, and optional degraded readiness.
- DA-10/Crucible adds `test_process_to_ready_meets_warm_and_cold_budgets` and `test_optional_service_shutdown_is_idempotent_and_leak_free`, retaining raw timing/task/client evidence.
- DA-10 composes the object-store outage test from `SBR-STARTUP.2` with local durable append and core tool listing in the same fresh process.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.server import ServiceStateV1, get_service_states, _startup, _shutdown; from scribe_mcp.background import BackgroundJobServiceV1; from scribe_mcp.storage.postgres.schema import SchemaReadinessV1'`
- `./.venv/bin/pytest -q tests/test_server_invoke_tool_startup_bypass.py`
- `./.venv/bin/pytest -q tests/test_health_check.py`
- `./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_core_ready_requires_c07_and_c09_but_not_optional_services tests/test_release_startup_probe.py::test_process_to_ready_meets_warm_and_cold_budgets tests/test_release_startup_probe.py::test_optional_service_shutdown_is_idempotent_and_leak_free` (after DA-10 owns the tests).

**Acceptance Criteria**

- [ ] Core-ready occurs only after C-07 succeeds and C-09 recovery/start reports running+accepting; required failure emits no ready signal.
- [ ] C-10 is importable with exactly six frozen fields and only four frozen states; optional object-store/bridge failure becomes degraded without raw-error leakage.
- [ ] Optional health work is background-only and cannot block core tools/local durable logging; outage foreground delta is at most 50 ms.
- [ ] Warm/cold process-to-ready p95 is at most 1.5/2.5 s, shutdown remains ordered/idempotent, and no new task/client survives teardown.
- [ ] Import/RSS gates from SBR-STARTUP.1 and C-07/C-09 producer regressions all pass on the same source revision.

**Out of Scope**

- C-07 implementation, C-09 scheduler/service/store behavior, background health projection edits, provider process ownership, startup config redesign, bridge suppression/retry, deployment/adoption, and test-file edits.

**Handoff Notes**

- Forge: modify only the declared startup-ready symbols/region; stop if C-09 lifecycle, health_check, config, storage, or another server anchor must change.
- Crucible: DA-10 owns reference-profile timing/RSS/outage tests; validate each required-versus-optional transition and retain raw samples plus teardown counts.
- Arbiter: mandatory high-blast review for truthful ready semantics, exact C-10 shape, strict anchor ownership, preserved C-07/C-09/shutdown contracts, and no Council/process policy.

### Package order and gate

1. Implement `SBR-STARTUP.1` and `SBR-STARTUP.2` independently; each must pass its import smoke and focused neighbor tests before integration.
2. After `SBR-SCHEMA.3` and `SBR-BG.4` land, implement `SBR-STARTUP.3` only inside `server.py#startup_ready`; do not absorb either producer's lifecycle.
3. DA-10/Crucible owns all `tests/test_release_startup_probe.py` additions and records raw five-run import/RSS, warm/cold ready, optional-outage delta, C-10 state, and teardown evidence for one source revision.
4. The gate is exact: warm/cold import p95 <=1.0/1.5 s; pre-tool/all-tools RSS <=64/80 MiB; warm/cold ready p95 <=1.5/2.5 s; optional outage foreground delta <=50 ms; zero false-ready, import-time metrics mutation, optional-service core block, local durability loss, or teardown leak.
5. Arbiter PASS is mandatory for all three packages because SS-03 is startup-, performance-, public-contract-, and high-blast-radius sensitive.
## DA-08 — Document durability detail
<!-- ID: sbr-document-durability -->
### APPROACH_SUMMARY

- Goal: make every managed-document mutation generation-safe, crash-recoverable, and externally auditable through frozen C-13 while reusing the existing apply-preview service, anchor CAS, atomic writes, C-08/C-09 background receipts, and `WriteAheadLog`.
- Files to modify: `src/scribe_mcp/utils/files.py`; `src/scribe_mcp/doc_management/apply_preview.py`; `src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks`; `src/scribe_mcp/tools/manage_docs.py`.
- Files forbidden: every other `src/**` path; all `tests/**` paths in this assignment; schema/migration, storage backend/model, background service/store/scheduler/worker, configuration, version, generated, Council, and release files.
- Out of scope: a second mutation engine, queue, receipt store, registry, indexer, quality engine, database table, provider/Council adapter, deployment, or release operation.
- Verification plan: import smoke for every modified module; focused apply-preview, anchor-CAS, file/WAL, registration, quality, and wrong-target regressions; DA-09 owns the new outage/restart/idempotency oracle; Sentinel and Arbiter PASS all three packages.
- Frozen contract interpretation: C-13 keeps its closed `state` vocabulary. `queued_offline` is an additive boolean readback flag that is legal only with `state="accepted"`; it means the existing WAL durably holds the operation while C-09 admission or post-write convergence remains pending. It is not a second persisted lifecycle state or queue.

### Task Package: SBR-DOC-DUR.1 — Idempotent WAL and atomic document-write substrate

**Goal**

- Extend the existing `WriteAheadLog` and atomic-write primitives so a normalized managed-document intent can be journaled by stable operation ID, inspected after restart, and committed exactly once without changing append-log behavior.

**Depends On**

- `SBR-RECEIPT.1` for the canonical `operation_id`, idempotency-key, payload-digest, and terminal-state semantics consumed later by C-08/C-09.
- No DA-08 source package; this is the first SS-08 package.

**Files to Read**

- `SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` SS-08, C-08, C-09, C-13, and the frozen correctness budgets.
- `src/scribe_mcp/utils/files.py::WriteAheadLog`, `atomic_write`, `async_atomic_write`, `append_line`, and `_write_line_with_wal`.
- `src/scribe_mcp/doc_management/apply_preview.py::ApplyPreviewService` for its existing claim/fence/terminal-replay pattern.
- `tests/test_multi_repo_file_ops.py`, `tests/test_write_barrier_contract.py`, and DA-09-owned `tests/core/test_wal_replay_exactly_once.py`.

**Files to Modify**

- `src/scribe_mcp/utils/files.py` — stable WAL entry identity, conflict-safe uncommitted readback, and compatibility-preserving atomic-write durability only.

**Files Forbidden**

- The other three SS-08 paths until their packages run.
- All storage/background/schema, manager/indexing/quality, MCP adapter, server, config, Council, version, generated, and test files.

**Public Contracts / Signatures**

- Preserve `WriteAheadLog.__init__(log_path: str | Path, repo_root: Path | None = None, context: dict[str, Any] | None = None)`.
- Extend compatibly to `WriteAheadLog.write_entry(entry: Mapping[str, Any], *, entry_id: str | None = None) -> str`; callers that omit `entry_id` keep the existing generated-ID behavior.
- Add `WriteAheadLog.read_uncommitted(*, operation_kind: str | None = None) -> tuple[dict[str, Any], ...]`.
- Add `WriteAheadLog.has_commit(entry_id: str) -> bool`.
- Preserve `WriteAheadLog.commit_entry(entry_id: str) -> None` and `WriteAheadLog.replay_uncommitted() -> int`; the latter remains the legacy append-log replay surface and must not become the document mutation worker.
- Add `WalEntryConflictError(AtomicFileError)` and `WalJournalCorruptError(AtomicFileError)`.
- Preserve `atomic_write(...) -> None`, `async_atomic_write(...) -> None`, `append_line(...) -> None`, and `_write_line_with_wal(...) -> None`.

**Implementation Constraints**

1. Canonicalize a copied mapping before journaling; never mutate the caller's object. A caller-supplied `entry_id` must be a non-empty stable operation ID. Journal rows carry `id`, `op`, `payload_digest`, and timestamp; document rows also carry project/document identity, both generations, both content digests, canonical path, normalized retained intent, and an opaque authorization-evidence reference.
2. For one `entry_id`, byte-identical canonical payload is idempotent and returns the original ID without appending another effect row. The same ID with a different digest raises `WalEntryConflictError` before any write. A commit row is append-only and idempotent.
3. `read_uncommitted` scans under the existing file lock, returns each uncommitted ID at most once in journal order, filters only when `operation_kind` is supplied, and fails closed with `WalJournalCorruptError` for malformed or contradictory non-empty rows. It must not silently skip a document operation.
4. Keep the WAL a crash journal, not a scheduler or receipt store. DA-08 runtime code may use `read_uncommitted` and `commit_entry`; only C-08/C-09 own admission, leasing, retry, cancellation, and terminal lifecycle truth.
5. A document journal is written and `fsync`ed before the target effect. `atomic_write` remains the sole overwrite primitive: same-directory temp file, file `fsync`, atomic replace, then parent-directory `fsync`. A journal commit occurs only after the file effect and package `.3` convergence are proven.
6. Journal files containing retained mutation intent are owner-readable/writable only. Never persist raw caller-session keys, credentials, tokens, full authorization evidence, or unsanitized exception text; persist the C-11 evidence reference and caller-session hash only.
7. Preserve legacy `append_line(use_wal=True)` output and replay semantics exactly. Do not route log appends through the document protocol or make remote object-store sync authoritative.

**Required Tests**

- DA-09/Crucible implements `tests/core/test_wal_replay_exactly_once.py`: crash before effect, crash after atomic replace before commit, repeated restart, duplicate stable ID, conflicting digest, corrupt journal, committed-entry suppression, and exactly one final content effect.
- Existing neighbors `tests/test_multi_repo_file_ops.py` and `tests/test_write_barrier_contract.py` remain green.
- Regression boundary: legacy append WAL replays once and `atomic_write` still rejects non-overwrite mode.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.utils.files import WriteAheadLog, WalEntryConflictError, WalJournalCorruptError, atomic_write, async_atomic_write'`
- `./.venv/bin/pytest -q tests/test_multi_repo_file_ops.py tests/test_write_barrier_contract.py`
- `./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"` (after DA-09 owns the test).

**Acceptance Criteria**

- [ ] Stable same-digest admission is idempotent; same-ID/different-digest admission is effect-free conflict.
- [ ] Every accepted document journal row survives restart, and repeated replay produces exactly one atomic file effect and one commit marker.
- [ ] Legacy append WAL, atomic-write durability, sandbox enforcement, and object-store non-authority are unchanged.
- [ ] No queue, worker, registry, index, quality, or second mutation abstraction exists in `files.py`.

**Out of Scope**

- C-13 modeling, project/binding resolution, background submission, replay scheduling, registration, index updates, quality evaluation, tool response formatting, and test-file edits.

**Handoff Notes**

- Forge: modify only `files.py`; stop if exact-once behavior requires a new store, daemon, schema, or source path.
- Crucible: own the DA-09 test and force deterministic crash boundaries by injected callbacks/events, never sleeps.
- Sentinel: mandatory review of journal permissions, path confinement, retained-payload minimization, digest validation, corrupt-row handling, and secret/session-key exclusion.
- Arbiter: mandatory review for compatibility, one WAL path, one atomic-write path, and no scheduler/state-machine duplication.

### Task Package: SBR-DOC-DUR.2 — C-13 generation-fenced admission and restart replay

**Goal**

- Produce `DocumentMutationReceiptV1` from the existing apply-preview/runtime mutation path and map every foreground, duplicate, offline, conflict, cancellation, and restart-replay outcome onto frozen C-02/C-03/C-04/C-08/C-09/C-11/C-13.

**Depends On**

- `SBR-DOC-DUR.1`.
- `SBR-BIND-RESOLVE.2`, `.3`, and `.4` for C-02, C-03, C-04, and one immutable C-11 per foreground or replay call.
- `SBR-RECEIPT.1` through `.3` for C-08 backend parity and `SBR-BG.3` for C-09 admission/status/cancel/recovery.

**Files to Read**

- `src/scribe_mcp/doc_management/apply_preview.py::ApplyPreviewBinding`, `RetainedIntentExecutor`, and `ApplyPreviewService`.
- `src/scribe_mcp/doc_management/runtime.py::_receipt_scope`, `_RuntimeRetainedIntentExecutor`, `_normalized_manage_docs_intent`, and `handle_manage_docs_request`.
- `PHASE_PLAN.md#sbr-target-resolution`, `#sbr-receipt-store`, and `#sbr-background-service`.
- `tests/test_apply_preview_engine.py`, `tests/test_manage_docs_apply_preview.py`, `tests/integration/test_manage_docs_apply_preview_lifecycle.py`, `tests/integration/storage/test_apply_preview_backend_parity.py`, and `tests/security/test_apply_preview_receipt_security.py`.

**Files to Modify**

- `src/scribe_mcp/doc_management/apply_preview.py` — C-13 frozen model/readback and additional generation/digest preflight on the existing apply service.
- `src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks` — journal/admit/replay helpers adjacent to `_receipt_scope`, `_RuntimeRetainedIntentExecutor`, and retained-intent execution only.

**Files Forbidden**

- `runtime.py` actions unrelated to durable mutation hooks.
- `manager.py`, all storage/background/schema/indexing/quality modules, `server.py`, MCP adapter, config, Council/provider, version, generated, release, and test files.

**Public Contracts / Signatures**

- `DocumentMutationState = Literal["accepted", "applied", "duplicate", "conflict", "terminal_error", "cancelled"]`.
- `DocumentMutationReceiptV1(operation_id: str, project_key: str, caller_session_key_hash: str, binding_generation: int, document_id: str, canonical_path: str, document_generation_before: int, document_generation_after: int | None, content_digest_before: str, content_digest_after: str | None, state: DocumentMutationState, replay_safe: bool, queued_offline: bool, correlation_id: str)`.
- `DocumentMutationReceiptV1.as_public_dict() -> dict[str, object]` emits no raw caller key, authorization evidence, retained content, journal path, lease/fence, or backend detail.
- `ApplyPreviewBinding` gains validated `caller_session_key_hash`, `binding_generation`, `document_id`, `document_generation_before`, `content_digest_before`, and `content_digest_after`; preserve its existing scope/target fields and `storage_payload()`.
- Preserve `ApplyPreviewService.issue(...) -> ApplyPreviewAffordance` and `ApplyPreviewService.apply(...) -> dict[str, object]`; extend their existing preflight/finalization path rather than adding another service.
- Runtime-local `build_document_mutation_receipt(...) -> DocumentMutationReceiptV1`, `admit_document_mutation(...) -> DocumentMutationReceiptV1`, and `replay_document_mutation(...) -> DocumentMutationReceiptV1` stay inside `runtime.py#durable_mutation_hooks`; they are not a new public engine.
- C-13 state remains closed. `queued_offline=True` is legal only for `state="accepted"` and `replay_safe=True`; every other state requires `queued_offline=False`.

**Implementation Constraints**

1. At foreground admission, consume the exact C-11 object already created for the call. Use its resolved C-02 target, C-03/default binding generation, caller-session hash, correlation ID, operating mode, and authorization-evidence reference. Do not read or resolve the binding/project again in the same call.
2. Resolve the canonical registered document once, derive `document_id` from stable project/document identity, and read document generation from the committed WAL lineage: absent lineage is generation 0; an accepted mutation proposes exactly `before + 1`. SHA-256 the full pre- and predicted post-content. Preserve `expected_anchor_sha256` as an additional CAS, never a replacement for generation/digest checks.
3. Compute deterministic `operation_id` and C-08 `idempotency_key` from canonical project key, document ID, binding generation, document generation before, normalized-intent digest, and predicted content digest. The WAL `payload_digest` is SHA-256 of canonical retained-intent JSON.
4. Journal before effect, then call `BackgroundJobServiceV1.submit` with lane `durable` and the same operation/idempotency/digest/byte count. Accepted returns `state="accepted"`. Exact C-08 duplicate returns one `state="duplicate"` C-13 readback tied to the original operation. Digest conflict returns `state="conflict"` and C-04 `SCRIBE_DOCUMENT_GENERATION_STALE` with zero effect.
5. If C-09 is temporarily unavailable, busy, shutting down, or its durable store cannot be reached after the WAL row is `fsync`ed, return `state="accepted", replay_safe=True, queued_offline=True`; startup/recovery scans the existing WAL and resubmits the same C-08 intent. If WAL durability itself fails, return typed retryable C-04 and do not claim acceptance.
6. A replay call creates one fresh C-11 under the background service's durable authorization-evidence reference, explicitly re-resolves C-02 by stable project key, and compares canonical root/project, binding generation, document ID/path, WAL generation, and both content digests before effect. It never selects by project label or ambient default.
7. Under the existing document mutation lock: current before-digest plus matching generations permits one `atomic_write`; current after-digest means the effect already happened and replay proceeds directly to package `.3` convergence; neither digest, wrong project/root/path, stale binding, stale document generation, stale anchor CAS, or changed authorization refuses before effect.
8. Use exact C-04 mappings: stale binding -> `SCRIBE_BINDING_GENERATION_STALE`; document generation/digest/anchor mismatch -> `SCRIBE_DOCUMENT_GENERATION_STALE`; wrong project/root/path or missing authority -> the corresponding project/root/unverified code; queue capacity -> `SCRIBE_BUSY`; closed admission -> `SCRIBE_SHUTTING_DOWN`; stale lease/fence -> `SCRIBE_STALE_FENCE`. Expected failures never escape as raw exceptions.
9. C-09 cancellation before atomic effect returns `state="cancelled"` and commits no document effect. Once atomic replace begins, cancellation cannot manufacture rollback; replay/convergence must report `applied` or `terminal_error` from durable truth. Terminal C-08/C-09 outcomes never re-enter execution.
10. Keep apply-preview receipt issuance, claim fencing, target-locking, terminal replay, and retained-intent execution as the single mutation engine. No second receipt table, queue, worker, lifecycle enum, or in-memory task is permitted.

**Required Tests**

- DA-09/Crucible extends `tests/core/test_wal_replay_exactly_once.py` for outage at admission, restart before/after atomic replace, exact duplicate, digest conflict, stale binding/document generation, anchor drift, cancellation before effect, cancellation after commit boundary, terminal replay, and zero duplicate effect.
- DA-09/Crucible extends `tests/test_manage_docs_anchor_cas.py` and `tests/test_tool_runtime_repo_scope.py` for one C-11 per call/replay, wrong-target refusal, exact C-04 codes, and one binding/project read.
- Existing apply-preview engine, lifecycle, backend-parity, and receipt-security tests remain green; SS-08 Forge does not edit any test path.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewBinding, ApplyPreviewService, DocumentMutationReceiptV1, DocumentMutationState'`
- `./.venv/bin/pytest -q tests/test_apply_preview_engine.py tests/test_manage_docs_apply_preview.py tests/integration/test_manage_docs_apply_preview_lifecycle.py tests/integration/storage/test_apply_preview_backend_parity.py tests/security/test_apply_preview_receipt_security.py`
- `./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py tests/test_manage_docs_anchor_cas.py tests/test_tool_runtime_repo_scope.py -m "core and regression and not slow and not performance"` (after DA-09 owns the cases).

**Acceptance Criteria**

- [ ] Every mutation attempt returns a complete sanitized C-13 receipt or typed C-04; `queued_offline` is true only for WAL-durable accepted work.
- [ ] Repeated client retries, worker retries, and process restarts yield one operation ID, one document generation increment, and at most one file effect.
- [ ] Stale binding, stale document generation/digest/anchor, wrong target/root/path, stale fence, and missing authority all refuse before effect with the exact typed outcome.
- [ ] Duplicate, conflict, terminal, and cancelled outcomes are stable on replay and cannot re-enter the mutation effect.
- [ ] The implementation uses the existing ApplyPreviewService, WAL, C-08/C-09 service, and mutation locks only.

**Out of Scope**

- Registration/index/quality convergence, new actions or MCP parameters, C-08/C-09 implementation changes, storage/schema changes, server lifecycle ownership, deployment, and test-file edits.

**Handoff Notes**

- Forge: stay inside the named symbols/anchor; stop if a new source path, background field, storage method, or contract change is required.
- Crucible: own the deterministic fault matrix in DA-09 and assert receipt/effect/journal/background ledgers agree exactly.
- Sentinel: mandatory review of durable authority references, caller-key/content redaction, wrong-target refusal, journal disclosure, digest/idempotency confusion, cancellation races, and replay authorization.
- Arbiter: mandatory review for one mutation path, frozen C-13/C-04 mapping, compatibility with apply-preview, and zero duplicate state machine.

### Task Package: SBR-DOC-DUR.3 — `manage_docs` readback and registration/index/quality convergence

**Goal**

- Make `manage_docs` expose C-13 consistently and finish each accepted file effect by converging the existing document registry, canonical indexes, and current-generation quality result without rewriting the document twice.

**Depends On**

- `SBR-DOC-DUR.2`.
- `SBR-BG.4` for bounded service start/recovery/stop; package `.3` consumes lifecycle availability but does not edit server hooks.
- Existing `auto_register_document`, index updater, and quality handler behavior in `runtime.py`.

**Files to Read**

- `src/scribe_mcp/tools/manage_docs.py::manage_docs`, `_auto_register_document`, and `_get_index_updater_for_path`.
- `src/scribe_mcp/doc_management/runtime.py::handle_manage_docs_request`, `auto_register_document`, `_handle_quality_check`, and existing post-mutation response paths.
- `tests/test_auto_registration.py`, `tests/test_manage_docs_quality_check.py`, `tests/test_manage_docs_anchor_cas.py`, and `tests/security/test_project_binding_policy.py`.

**Files to Modify**

- `src/scribe_mcp/doc_management/runtime.py#durable_mutation_hooks` — post-effect convergence and WAL commit/readback only.
- `src/scribe_mcp/tools/manage_docs.py` — public result projection/docstring/schema description only; orchestration remains in runtime.

**Files Forbidden**

- All other `runtime.py` behavior, `manager.py`, registry/indexing/quality implementation modules, storage/background/schema/server/MCP adapter/config/Council/version/generated/release files, and all tests.

**Public Contracts / Signatures**

- Preserve the full public `manage_docs(...) -> dict[str, Any]` signature and all existing actions.
- Successful non-dry-run mutation responses add `document_mutation_receipt: dict[str, object]` containing exactly `DocumentMutationReceiptV1.as_public_dict()`.
- Responses with C-13 also add `document_convergence: {"registration": "converged"|"pending"|"not_applicable", "index": "converged"|"pending"|"not_applicable", "quality": "evaluated"|"pending"|"not_applicable"}`; this is response evidence, not another persisted receipt/state machine.
- Dry runs keep the existing apply-preview affordance and do not create a document mutation receipt, WAL row, background receipt, registration, index, or quality side effect.
- No new `manage_docs` action is added. Optional caller `metadata.idempotency_key` is normalized into the existing retained intent; omission uses the deterministic package `.2` key.

**Implementation Constraints**

1. Keep `tools.manage_docs.manage_docs` a thin wrapper over `runtime.handle_manage_docs_request`; it may document/project the receipt but cannot resolve targets, write files, queue jobs, or duplicate convergence logic.
2. After the atomic file effect or an after-digest restart observation, call existing `auto_register_document` for the canonical document key, then the existing path-specific index updater, then the existing quality-check handler against the same canonical path and document generation.
3. Convergence is idempotent: registration resolves one canonical key/path, indexes contain one canonical row, and quality is evaluated for the current post-content digest. Replaying convergence must not append duplicate registry/index rows or rewrite the document.
4. `state="applied"` is emitted and the WAL entry committed only after file digest/generation plus all applicable convergence stages are proven. Quality warnings are returned as current content evidence and do not roll back a correct write; infrastructure failure to evaluate quality remains `accepted + queued_offline` and retryable.
5. If the file already has the predicted after-digest on restart, skip the mutation effect and run only pending convergence. If it has the before-digest, package `.2` may apply once. Any third digest or generation mismatch is `conflict`; no registration/index/quality operation may make the wrong target appear valid.
6. Map exact C-09 status to C-13: accepted/ready/leased/retry_wait -> accepted; succeeded plus convergence -> applied; exact original admission -> duplicate; digest/version/generation conflict -> conflict; failed_terminal -> terminal_error; cancelled -> cancelled.
7. `get_status`/cancel readback must authorize through the already-resolved C-11 target and exact project/operation identity. A same-label caller, different project/root, ambient-default drift, or guessed operation ID receives typed refusal and no cross-project details.
8. Preserve every existing response key, apply-preview terminal replay, auto-registration rule, index skip rule, quality warning code, and frontmatter/edit-trace behavior. Do not hide `SCF_INDEX_*`, `SCF_DOC_UNINDEXED`, scaffold, lifecycle, or topology blockers.
9. Foreground receipt acknowledgement remains p95 at most 500 ms. It waits only for local WAL durability and C-08/C-09 admission; document replay and convergence remain bounded background work when not immediately available.
10. Shutdown respects C-09 truth: close admission, leave every WAL-durable/nonterminal operation recoverable, fence late work, and never commit a journal row merely because the process is stopping.

**Required Tests**

- DA-09/Crucible covers outage/restart/wrong-target/idempotency in `tests/core/test_wal_replay_exactly_once.py`, `tests/test_manage_docs_anchor_cas.py`, and `tests/test_tool_runtime_repo_scope.py`.
- DA-09/Crucible proves registration/index/quality convergence, no duplicate rows, current-generation quality evidence, pending-to-applied replay, terminal/cancelled stability, and wrong-project status/cancel refusal.
- Existing `tests/test_auto_registration.py`, `tests/test_manage_docs_quality_check.py`, `tests/test_manage_docs_apply_preview.py`, `tests/test_manage_docs_anchor_cas.py`, and `tests/security/test_project_binding_policy.py` remain green.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.doc_management import runtime; from scribe_mcp.tools.manage_docs import manage_docs'`
- `./.venv/bin/pytest -q tests/test_auto_registration.py tests/test_manage_docs_quality_check.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_anchor_cas.py tests/security/test_project_binding_policy.py`
- `./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py tests/test_tool_runtime_repo_scope.py -m "core and regression and not slow and not performance"` (after DA-09 owns the cases).

**Acceptance Criteria**

- [ ] Every committed managed-document mutation has one C-13 readback, one WAL lineage generation, the predicted final digest, one canonical registration/index presence, and current-generation quality evidence.
- [ ] Backend or convergence outage returns WAL-durable `accepted + queued_offline`; restart converges it to `applied` exactly once without a second file effect.
- [ ] Duplicate, conflict, terminal, and cancelled outcomes remain stable; wrong-target status/cancel/replay discloses nothing and performs no effect.
- [ ] Existing actions, dry-run/apply-preview behavior, anchor CAS, quality warnings, and response compatibility remain intact.
- [ ] No second mutation engine, queue, registry, indexer, quality engine, or persistence layer is introduced.

**Out of Scope**

- New actions, new background/storage/schema fields, changes to registration/index/quality implementations, server lifecycle edits, Council/provider adapters, deployment/release, and test-file edits.

**Handoff Notes**

- Forge: edit only the thin tool projection plus declared runtime hooks; stop if convergence requires changing registry/index/quality implementations or any fifth SS-08 source path.
- Crucible: validate every acceptance item through DA-09-owned deterministic tests and keep exact operation/receipt/effect/registration/index/quality ledgers.
- Sentinel: mandatory review of status/cancel authorization, cross-project disclosure, stored content/authority references, quality-output sanitization, and outage/backpressure behavior.
- Arbiter: mandatory review for wrapper thinness, convergence idempotency, preserved warnings/contracts, and no duplicate engine.

### Package order and gate

1. Implement `SBR-DOC-DUR.1`; import, legacy append-WAL, corrupt/conflict, and atomic-write proof must pass before runtime integration.
2. Implement `.2` after C-02/C-03/C-04/C-08/C-09/C-11 are importable and current; require deterministic receipt/generation/digest/wrong-target/restart proof before public projection.
3. Implement `.3` after `.2` and C-09 lifecycle integration; require registration/index/quality convergence without duplicate file effect.
4. DA-09 owns all new tests and the hermetic outage/restart/wrong-target/idempotency oracle; DA-10 owns any held PostgreSQL/process stress. SS-08 implementers modify no test path.
5. Release acceptance requires zero wrong-target/default-drift/cross-talk/lost accepted work/duplicate effect/stale-fence acceptance; every WAL-durable accepted operation becomes applied, conflict, terminal_error, or cancelled after restart; receipt acknowledgement p95 is at most 500 ms.
6. Sentinel and Arbiter PASS all three packages because SS-08 is durability-, replay-, document-integrity-, authorization-, and high-blast-radius sensitive.
## DA-09 — Core validation detail
<!-- ID: sbr-core-validation -->
### APPROACH_SUMMARY

- Goal: split frozen SS-09 into five file-disjoint hermetic validation packages proving same-label binding isolation, bounded background execution, exactly-once replay, typed error/document semantics, and the amended Remote C-01 expectation without production edits.
- Files to modify: `tests/fixtures/swarm.py`; `tests/core/test_swarm_binding_reliability.py`; `tests/core/test_background_queue_contract.py`; `tests/core/test_wal_replay_exactly_once.py`; `tests/test_tool_runtime_repo_scope.py`; `tests/test_manage_docs_anchor_cas.py`; `tests/test_remote_backend.py`.
- Files forbidden: every `src/**` path; `pyproject.toml`; all other `tests/**` paths; schema, configuration, version, benchmark, integration, generated, Council, deployment, and release files.
- Out of scope: production repair, live PostgreSQL or Remote calls, provider/Council behavior, reference-profile timing, a second queue/replay/oracle implementation, or any change to C-01/C-02/C-03/C-04/C-08/C-09/C-11/C-12/C-13.
- Verification: compile every modified test module; import-smoke each consumed production contract; run each owned file plus named direct neighbors; then run the seven-path SS-09 lane once. No full-suite lane.
- Frozen-input proof: accepted seam SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61` freezes all nine inputs and marks DA-09 `SPLIT_REQUIRED` at seven paths.
- Test contract: mutable state is function-scoped under `tmp_path`; all 32 callers use canonical `test_agent`; clocks, retries, reconnects, cancellation, shutdown, and crash boundaries use manual clocks and events; no sleeps, external network, live database, or real repository state.
- C-14 rule: `SwarmResultsV1` is the sole structured result source with source revision, seed, topology, set-project count, operation ledger, oracle cardinalities, queue metrics, timing histograms, fault timeline, teardown counts, and verdict; Markdown is derived.

### Task Package: SBR-CORE-VAL.1 — Shared swarm fixture and 32-session binding oracle

**Goal**

- Create the reusable harness and core regression proving 32 same-label sessions retain independent defaults and exact effects through 3,200 mixed calls, explicit targeting, delayed second-write, reconnect, cleanup, and causal cross-repository overlap.

**Depends On**

- `SBR-BIND-PERSIST.1` through `.5`; `SBR-BIND-RESOLVE.1` through `.4`; `SBR-HOTPATH.1` through `.3`; `SBR-SCHEMA.2`.

**Files to Read**

- Accepted seam SS-09, C-01 through C-04, C-11/C-12/C-14, and correctness budgets.
- `research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md` F1-F8 and implementation packages 1-2.
- `tests/conftest.py::test_agent`, `tests/fixtures/projects.py`, `tests/fixtures/storage.py`, and existing set-project/session/MCP tests.

**Files to Modify**

- `tests/fixtures/swarm.py` — topology, manual clock/events, seeded schedule, expected-effects ledger, and C-14 helpers.
- `tests/core/test_swarm_binding_reliability.py` — hermetic core/regression cases using real Scribe code and disposable storage/files.

**Files Forbidden**

- The other five SS-09 paths; every production, configuration, integration, benchmark, Council, generated, and live-state path.

**Public Contracts / Signatures**

- Test-only `ManualClock.now() -> float` and `ManualClock.advance(delta_ms: int) -> None`.
- Test-only `CausalGate.entered: asyncio.Event` and `CausalGate.release: asyncio.Event`.
- `build_swarm_topology(tmp_path: Path, *, agent_label: str, seed: int) -> SwarmTopology` creates four repositories, four projects per repository, and two callers per default project.
- `build_mixed_schedule(caller: SwarmCaller, *, seed: int) -> tuple[SwarmOperation, ...]` returns exactly 100 operations with the frozen 30/20/20/15/5/5/5 mix.
- `reconcile_exact_effects(expected: Sequence[ExpectedEffect], observed: Sequence[ObservedEffect], *, metadata: SwarmRunMetadata) -> SwarmResultsV1`.
- `SwarmResultsV1.as_json_dict() -> dict[str, object]` emits exactly C-14 and is the only structured result source.

**Implementation Constraints**

1. Use one `test_agent` value for all callers. Isolation keys are server-owned application identity and persisted stable session ID, never label/task/object/transport identity.
2. Topology is four disposable repositories × four projects × two callers. Duplicate at least one project name across repositories.
3. Each caller invokes `set_project` once, then 30 ambient appends, 20 reads, 20 managed-doc operations, 15 explicit same-repo operations, five authorized cross-repo operations, five reconnect/restore observations, and five negative/fault/replay operations.
4. Ledger fields include run/operation/caller/application/stable-session identity, default/explicit targets, mutation fingerprint, expected effect, and expected result code; reconcile exact multisets, not success booleans.
5. The delayed second-write binds once, interleaves unrelated calls, waits on an event barrier, issues a second explicit-project append, and proves correct target, unchanged default/generation, `set_project_count == 1`, and no extra C-01 write.
6. Explicit calls never mutate default. Missing, ambiguous, unauthorized, stale-generation, or root-mismatch requests return exact C-04 envelopes and cause zero file/DB/index/recent/cache/binding mutation.
7. Reconnect one caller through a fresh runtime/router after clearing caches; the same handle restores its binding, a new same-label handle does not inherit it, and cleanup leaves 31 peers unchanged.
8. While Repo A is held at a storage/file event, Repo B must reach its checkpoint before A releases; repeat both directions for read/write, log/document, and restore/log.
9. Per call: at most one binding read, one project read, one immutable C-11 object, and one C-12 envelope accounting for at least 95 percent of injected duration with exact tripwire deltas.
10. C-14 cardinalities are zero for wrong target, default drift, cross-talk, missing/duplicate/denied effects, and untyped errors; teardown returns tasks/handles/files/registries to baseline.

**Required Tests**

- `test_32_same_label_sessions_execute_one_bind_and_100_mixed_calls_each`.
- `test_delayed_second_explicit_write_preserves_default_and_generation`.
- `test_reconnect_new_handle_and_single_caller_cleanup_are_isolated`.
- `test_unrelated_repositories_overlap_without_global_head_of_line_blocking`.
- `test_swarm_exact_effects_and_c14_serialization_are_deterministic`.
- Mark new cases `core` and `regression`; no capability, slow, performance, integration, or flaky marker.

**Verification Commands**

- `PYTHONPATH=src:tests ./.venv/bin/python -c 'from fixtures.swarm import ManualClock, CausalGate, SwarmResultsV1, build_swarm_topology, build_mixed_schedule, reconcile_exact_effects'`
- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.set_project import set_project; from scribe_mcp.shared.tool_runtime import execute_tool_call; from scribe_mcp.mcp_adapter import ScribeErrorV1'`
- `./.venv/bin/python -m py_compile tests/fixtures/swarm.py tests/core/test_swarm_binding_reliability.py`
- `./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py -m "core and regression and not integration and not slow and not performance"`
- `./.venv/bin/pytest -q tests/test_set_project.py tests/test_set_project_runtime_scope_contract.py tests/test_session_project_cache.py tests/test_mcp_adapter.py`

**Acceptance Criteria**

- [ ] Exactly 32 authoritative sessions share one label but never a default, generation, ledger, or target.
- [ ] Every caller has one bind and 100 mixed calls; delayed second-write succeeds without rebind/default mutation.
- [ ] Multiple repos/projects, duplicate names, isolated reconnects, new-handle denial, and one-caller cleanup are cardinality-clean.
- [ ] Repo B progresses while Repo A is causally blocked; C-14 is seed-deterministic and all forbidden-effect counts are zero.

**Out of Scope**

- Queue state-machine detail, WAL/document replay, focused runtime/CAS errors, Remote expectations, live adapters/stress, or reference timing.

**Handoff Notes**

- Crucible: implement only these two files with real product code and disposable substrates; keep the oracle immutable.
- Forge/Mantis: repair red production behavior in its owning package; never weaken counts, faults, or timing barriers.
- Witness: verify 32 × 100 arithmetic, operation mix, C-14 fields, markers, and zero live-state access.
- Arbiter: review fixture reuse, deterministic scheduling, exact-effects strength, and absence of label authority or a second runtime.

### Task Package: SBR-CORE-VAL.2 — Bounded queue, fairness, cancellation, and shutdown contract

**Goal**

- Prove C-08/C-09 admission, partitioning, fairness, fencing, cancellation, recovery, shutdown, and metrics stay bounded and independent across projects.

**Depends On**

- `SBR-CORE-VAL.1`; `SBR-RECEIPT.1` through `.3`; `SBR-BG.1` through `.4`.

**Files to Read**

- Seam C-08/C-09/C-12/C-14 and queue budgets; `research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md` F1-F9 and Q1-Q3.
- Existing background receipt, SQLite receipt, execution-context, server lifecycle, and health tests.

**Files to Modify**

- `tests/core/test_background_queue_contract.py` only.

**Files Forbidden**

- All six other SS-09 paths and every production/configuration/integration/Council path.

**Public Contracts / Signatures**

- Consume C-08 `admit/get/claim/transition/recover` and C-09 `submit/get_status/cancel/start/stop` exactly as frozen.
- Reuse package .1 `ManualClock`, `CausalGate`, and C-14 queue fields; do not duplicate them.

**Implementation Constraints**

1. Assert atomic item/serialized-byte bounds across ready, retry-wait, and leased receipts under 32 admissions, including exact transient high-water marks.
2. Same project/key/digest returns the original receipt without capacity; different digest conflicts without effect; overload is `SCRIBE_BUSY`; closed admission is `SCRIBE_SHUTTING_DOWN`.
3. Use repository-plus-project partitions and control/durable/heavy lanes with explicit host-independent caps: global heavy two, per-project heavy one, one control reserve.
4. For three equal-weight projects and 12 unit jobs each, starts differ by at most one per round and none exceeds 50 percent while a peer is eligible; configured 2:1:1 remains within one quantum.
5. Hold Project A by events in ready/running/retry/dead-letter/cancellation/drain; B/C claim and complete before A releases. Repeat 31 callers on A versus one on B and payloads at the byte bound.
6. Manual clock and seeded jitter drive transient retry, due retry, finite exhaustion, permanent failure, worker death, higher-fence reclaim, and stale-completion rejection.
7. Race cancellation before acceptance, queued, leased/cooperative, and non-interruptible commit boundaries; capacity releases exactly once.
8. Shutdown closes admission, stops claims, checkpoints, drains to manual deadline, restores retryable work, rejects stale completions, closes resources, and emits one event; repeated stop is idempotent.
9. Assert exact metric deltas and bounded-cardinality labels; no raw project, caller, operation, payload, or error text label.
10. No sleep, wall-clock fairness, unbounded tasks, sockets, or live DB.

**Required Tests**

- `test_admission_is_atomically_bounded_by_items_and_bytes`.
- `test_duplicate_conflict_busy_and_shutdown_outcomes_are_exact`.
- `test_partition_fairness_caps_and_control_reserve`.
- `test_blocked_project_does_not_head_of_line_block_peers`.
- `test_retry_worker_death_and_stale_fence_are_deterministic`.
- `test_cancellation_races_have_closed_cardinality_clean_outcomes`.
- `test_shutdown_checkpoints_recovers_and_leaks_no_tasks`.
- `test_background_metrics_are_exact_and_bounded_cardinality`.
- Mark all `core` and `regression`.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background import BackgroundIntentV1, BackgroundJobServiceV1, BackgroundServiceConfigV1, BackgroundShutdownReceiptV1; from scribe_mcp.background.scheduler import BackgroundSchedulerV1'`
- `./.venv/bin/python -m py_compile tests/core/test_background_queue_contract.py`
- `./.venv/bin/pytest -q tests/core/test_background_queue_contract.py -m "core and regression and not integration and not slow and not performance"`
- `./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_health_check.py`

**Acceptance Criteria**

- [ ] Item/byte/global/project/lane/worker bounds hold at every checkpoint with exact receipt outcomes.
- [ ] Fairness passes and blocked/retrying/cancelling/draining A never blocks B/C.
- [ ] Retry, reclaim, fencing, cancellation, recovery, and shutdown lose/duplicate no accepted effect or capacity.
- [ ] Metrics and C-14 queue fields are exact and bounded-cardinality.

**Out of Scope**

- WAL/document replay, live throughput/stress, source repair, markers, or a second scheduler/receipt model.

**Handoff Notes**

- Crucible: modify one file and reuse .1 fixtures.
- Forge/Mantis: repair only the upstream C-08/C-09 owner.
- Witness: verify every intermediate bound.
- Arbiter: reject sleep-based fairness, host-dependent expectations, global FIFO/locks, or duplicated queue models.

### Task Package: SBR-CORE-VAL.3 — WAL and document replay exactly-once oracle

**Goal**

- Prove accepted log/background/document work survives every named crash/restart window and converges to one authoritative effect with C-08/C-09/C-13 receipts.

**Depends On**

- `SBR-CORE-VAL.1` and `.2`; `SBR-DOC-DUR.1` through `.3`; `SBR-BG.2` through `.4`.

**Files to Read**

- Seam C-08/C-09/C-13/C-14; swarm research F7/package 2; queue research F6-F8.
- Existing multi-repo file, write-barrier, apply-preview engine/tool/lifecycle tests.

**Files to Modify**

- `tests/core/test_wal_replay_exactly_once.py` only.

**Files Forbidden**

- All six other SS-09 paths and every production/configuration/Council/live-state path.

**Public Contracts / Signatures**

- Consume `WriteAheadLog.write_entry/read_uncommitted/has_commit/commit_entry/replay_uncommitted`, C-08/C-09 receipts, and C-13 `DocumentMutationReceiptV1` unchanged.
- Reuse .1 ledger/clock/gates/reconciler and .2 receipt oracle.

**Implementation Constraints**

1. Cover crash after journal write/before effect, effect/before journal commit, document replace/before receipt success, and receipt success/before response.
2. Race two replay workers, replay twice after success, mix valid rows with malformed/truncated tail, and isolate one project's failure while peers recover.
3. Per accepted operation ID, final effect and terminal receipt cardinality are one; same-digest duplicates return original truth and different-digest conflicts have zero effect.
4. Restore accepted offline/mirror work after recovery and reconstruct ready/leased/retry-wait receipts without process memory.
5. Replay resolves stable project key and compares root, binding generation, document ID/path/generation, content digests, and anchor CAS.
6. Map stale binding/document/anchor/fence, wrong target/root, busy, shutdown, cancellation, and terminal replay to exact C-04/C-13 without raw exceptions.
7. Pre-effect cancellation has zero effect; post-commit cancellation reports durable applied/terminal truth without rollback.
8. Registration/index/quality converge once at current generation; pending-to-applied is monotonic and duplicate/terminal/cancelled outcomes remain stable.
9. Inject callbacks/events at durability boundaries; no sleep/live service/process-global repo/at-least-once weakening.

**Required Tests**

- `test_crash_windows_replay_each_accepted_effect_exactly_once`.
- `test_concurrent_and_repeated_replayers_do_not_duplicate_effects`.
- `test_truncated_tail_and_one_project_failure_are_isolated`.
- `test_offline_admission_and_runtime_reconstruction_preserve_receipts`.
- `test_document_replay_revalidates_target_generations_digests_and_anchor`.
- `test_replay_cancellation_and_terminal_states_are_cardinality_clean`.
- `test_registration_index_and_quality_converge_once_after_replay`.
- Mark all `core` and `regression`.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.utils.files import WriteAheadLog, WalEntryConflictError, WalJournalCorruptError; from scribe_mcp.doc_management.apply_preview import DocumentMutationReceiptV1, DocumentMutationState'`
- `./.venv/bin/python -m py_compile tests/core/test_wal_replay_exactly_once.py`
- `./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py -m "core and regression and not integration and not slow and not performance"`
- `./.venv/bin/pytest -q tests/test_multi_repo_file_ops.py tests/test_write_barrier_contract.py tests/test_apply_preview_engine.py tests/test_manage_docs_apply_preview.py tests/integration/test_manage_docs_apply_preview_lifecycle.py`

**Acceptance Criteria**

- [ ] Every crash/restart/concurrent replay ends with one effect and one terminal truth per accepted operation.
- [ ] Malformed tails, wrong targets, stale generations/digests/anchors/fences, cancellation, and one-project failure cannot contaminate peers.
- [ ] Offline work survives reconstruction; registration/index/quality convergence is current-generation and duplicate-free.
- [ ] Error/state vocabularies remain frozen and all barriers are deterministic.

**Out of Scope**

- Queue fairness, adapter/live stress, new WAL/receipt states, source edits, or unrelated managed-doc behavior.

**Handoff Notes**

- Crucible: make crash points explicit and inspect durable truth after reconstruction.
- Forge/Mantis: production repair stays with SS-06/SS-07/SS-08; never weaken exact-once.
- Witness: verify one effect and terminal receipt per accepted ID across repeated replay.
- Arbiter: reject process-memory proof, swallowed corruption, untyped errors, or duplicate replay engines.

### Task Package: SBR-CORE-VAL.4 — Typed runtime and managed-document refusal regressions

**Goal**

- Extend canonical tests so C-02/C-04/C-11/C-12/C-13 target, identity, generation, CAS, and error semantics are exact and effect-free on refusal.

**Depends On**

- `SBR-BIND-RESOLVE.1` through `.4`; `SBR-HOTPATH.1` through `.3`; `SBR-DOC-DUR.2` and `.3`; `SBR-CORE-VAL.3`.

**Files to Read**

- Existing MCP adapter, logging/explicit resolution, manage-doc apply-preview/quality, and project-binding policy tests.
- Both owned files; extend in place and create no parallel module.

**Files to Modify**

- `tests/test_tool_runtime_repo_scope.py` — caller key, target precedence, immutable context, read counts, and typed MCP errors.
- `tests/test_manage_docs_anchor_cas.py` — generation/digest/anchor/wrong-target refusal and convergence.

**Files Forbidden**

- The other five SS-09 paths, production/config/Council paths, and any new test file.

**Public Contracts / Signatures**

- Preserve C-04 `CallToolResult`: `isError=true` and `structuredContent` keys `ok/error_code/message/retryable/target/candidates/remediation/correlation_id`.
- Consume one immutable C-11 `ResolvedRequestContextV1` and one C-12 envelope per foreground/replay call; helpers never re-resolve.

**Implementation Constraints**

1. Cover ambient default, explicit key, name-plus-root, unique name, duplicate-name ambiguity, root mismatch, missing default, unauthorized target, unverified caller, stale binding/document generation, and stale fence.
2. Assert exact C-04 codes, sanitized deterministic candidates, correlation, retryability, and no raw exception.
3. At most one binding read and project read; nested helpers receive the identical C-11 object.
4. Same/cross-repo explicit calls affect only explicit target and leave default/generation/recent/cache/file/registry/index unchanged.
5. Malformed digest, duplicate/moved anchor, stale generation/digest, wrong project/root/path, write crash, and alias race mutate no bytes/log/registry/index/quality.
6. Post-effect crash reports completed write; registration/index/quality converge once at current generation; duplicate/terminal/cancelled readback is stable.
7. Reuse helpers and `tmp_path`; no live project/network/sleep/Council policy/new error vocabulary.

**Required Tests**

- `test_runtime_resolves_each_target_once_and_preserves_context_identity`.
- `test_runtime_typed_errors_are_exact_sanitized_and_effect_free`.
- `test_explicit_targets_never_mutate_default_or_recent_project`.
- `test_manage_docs_generation_digest_anchor_and_target_refusals_are_effect_free`.
- `test_manage_docs_post_effect_recovery_converges_registration_index_and_quality_once`.
- Mark additions `core` and `regression` without changing unrelated markers.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key; from scribe_mcp.shared.execution_context import ResolvedRequestContextV1; from scribe_mcp.mcp_adapter import ScribeErrorV1, normalize_tool_result; from scribe_mcp.tools.manage_docs import manage_docs'`
- `./.venv/bin/python -m py_compile tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py`
- `./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py -m "core and regression and not integration and not slow and not performance"`
- `./.venv/bin/pytest -q tests/test_mcp_adapter.py tests/test_logging_utils.py tests/test_append_entry_explicit_project_resolution.py tests/test_query_entries_explicit_project_resolution.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_quality_check.py tests/security/test_project_binding_policy.py`

**Acceptance Criteria**

- [ ] Every expected failure returns exact typed MCP/C-04 envelope with zero side effects.
- [ ] Each call has one immutable C-11, at most one binding/project read, and one C-12.
- [ ] Explicit target, CAS, generation, digest, recovery, and convergence preserve defaults and durable truth.
- [ ] Existing canonical-key/fallback, anchor-race, and schema-exposure regressions stay green.

**Out of Scope**

- New resolver/error/CAS behavior, source repair, broad tools, security policy, queue mechanics, or adapter parity.

**Handoff Notes**

- Crucible: extend only these canonical owners.
- Forge/Mantis: route red behavior to SS-02/SS-05/SS-08 without changing the oracle.
- Witness: verify codes, keys, read counts, object identity, and zero-effect snapshots.
- Arbiter: reject duplicated helpers, unit-under-test mocks, or “did not raise” assertions.

### Task Package: SBR-CORE-VAL.5 — Remote C-01 durable binding expectation

**Goal**

- Replace stale all-session in-memory/no-HTTP binding expectations with hermetic proof that only Remote binding set/get uses authenticated authoritative transport and frozen C-01.

**Depends On**

- `SBR-BIND-PERSIST.5` and accepted `SBR-ARCH-AMEND-REMOTE-08`.
- Independent of .2-.4; may run after .1 while preserving whole-file ownership.

**Files to Read**

- `src/scribe_mcp/storage/remote.py#session_binding_transport` read-only; package `SBR-BIND-PERSIST.5`; seam C-01; owned file's session/auth/error fixtures.

**Files to Modify**

- `tests/test_remote_backend.py` only.

**Files Forbidden**

- All other SS-09 paths; production Remote/route/auth/config/Council/live/generated files.

**Public Contracts / Signatures**

- Assert C-01 `set_session_project(session_id: str, project_key: str, expected_generation: int | None = None) -> SessionBindingRecordV2` and `get_session_project(session_id: str) -> SessionBindingRecordV2 | None`.
- Record fields: `caller_session_key_hash`, `project_key`, `project_name`, `canonical_repo_root`, `binding_generation`, `updated_at`.

**Implementation Constraints**

1. Narrow wording so only non-binding compatibility methods remain local; remove the obsolete assertion that binding set/get makes no HTTP.
2. Use existing mocked authenticated client/`_call` only. Assert one delegation with canonical session key, project key, and optional expected generation.
3. Decode all six fields. First change increments generation; unchanged rebind returns same record/zero write; stale expected generation is typed/effect-free.
4. Recreate backend between set/get so empty local cache cannot satisfy authoritative readback.
5. Reject malformed/missing/naive timestamp or generation through existing Remote errors; leak no raw key/credential/backend detail.
6. Preserve local/no-HTTP behavior for unrelated session methods and public-release/auth behavior.
7. No network, sleep, daemon, or integration marker.

**Required Tests**

- Replace `test_session_project_get_set` with `test_session_project_transport_roundtrip_decodes_c01`.
- Add `test_session_project_reconnect_does_not_trust_empty_local_cache`.
- Add `test_session_project_unchanged_and_stale_generation_outcomes`.
- Add `test_session_project_transport_rejects_malformed_record`.
- Rename/narrow `test_session_methods_no_http` to `test_non_binding_session_methods_no_http` and remove only binding calls.
- Mark replacements `core` and `regression`; preserve unrelated behavior.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; from scribe_mcp.storage.base import SessionBindingRecordV2'`
- `./.venv/bin/python -m py_compile tests/test_remote_backend.py`
- `./.venv/bin/pytest -q tests/test_remote_backend.py::TestSessionMethods`
- `./.venv/bin/pytest -q tests/test_remote_backend.py::TestRemoteAuth tests/test_remote_backend.py::TestErrorHandling`

**Acceptance Criteria**

- [ ] Remote binding set/get uses authenticated transport once and strictly decodes C-01.
- [ ] Reconnect proves cache non-authority; unchanged/stale-generation outcomes are durable/effect-free.
- [ ] Malformed responses use existing typed Remote errors without leaks.
- [ ] Unrelated session methods remain local/no-HTTP and no external request occurs.

**Out of Scope**

- Production Remote changes, routes, live parity, unrelated cache/session behavior, adapters/Council, or C-01 redesign.

**Handoff Notes**

- Crucible: modify one file using existing mock-response/auth fixtures.
- Forge/Mantis: defects return to `SBR-BIND-PERSIST.5`; never restore stale binding expectations.
- Witness: verify calls, six fields, generation/CAS/no-write, cache non-authority, and unrelated tests.
- Arbiter: reject live network, broad Remote rewrites, relaxed decoding, or client-local truth.

### DA-09 Dependency, Validation, and Handoff Order

1. Confirm current upstream revisions for all nine frozen inputs; upstream reds return to their owners without weakening SS-09.
2. Implement `SBR-CORE-VAL.1` first; it owns the sole shared fixture/oracle and C-14 serialization.
3. Implement `SBR-CORE-VAL.2` and `.5` independently after .1; they share no modified file.
4. Implement `SBR-CORE-VAL.3` after .2, then `.4` after .3.
5. Run package commands separately, then `./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py tests/test_remote_backend.py -m "core and regression and not integration and not slow and not performance"`.
6. Crucible records behavioral PASS for .1-.5. Witness, when admitted, verifies ownership/imports/signatures/commands/C-14/scope. Arbiter reviews the concurrency/durability oracle after behavioral PASS; Sentinel is required only if a repair changes auth, raw-key handling, retained payloads, or journal permissions.
7. Handoff to DA-10 only at one source revision with all five commands green, zero oracle defects, clean teardown, and C-14 as the sole JSON-equivalent result. DA-10 alone owns live PostgreSQL/process/adapter/reference-budget evidence.
## DA-10 — Stress, adapter, and release evidence detail
<!-- ID: sbr-release-validation -->
### APPROACH_SUMMARY

- Goal: certify SS-10 against frozen C-07/C-10/C-12/C-14 and produce C-15 `ReliabilityReleaseEvidenceV1` for one clean source revision.
- Files to modify: `tests/integration/storage/conftest.py`, `tests/integration/test_swarm_concurrency_stress.py`, `tests/migration/mcp_v2/test_compatibility_matrix.py`, `tests/security/test_session_provenance.py`, `tests/test_release_startup_probe.py`, and `benchmarks/swarm_concurrency.py` only.
- Files forbidden: every `src/**` path; `pyproject.toml`; every other `tests/**` or `benchmarks/**` path; `.council/**`; `.claude/**`; `.codex/**`; Council/provider projections; production configuration, projects, databases, credentials, deploy, publish, and release-version surfaces.
- Out of scope: repairing a failed upstream contract; weakening any frozen budget; creating another swarm/queue oracle; making Council behavior part of Scribe acceptance; persisting secrets or raw DSNs; running the repository-wide suite.
- Verification plan: validate five file-disjoint packages independently, then acquire the single `SBR_REFERENCE_STRESS` repository-saturating lane for one final runner invocation. The lane records the clean Git revision and environment before work, uses disposable repositories/databases/processes only, serializes all smoke/soak/adapter/startup measurements, and emits C-15 only when every required verdict is `PASS` for that revision.
- Frozen-input proof: accepted seam SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`; C-07, C-10, C-12, C-14, and produced C-15 remain frozen. DA-03, DA-04, DA-05, and DA-09 are hard prerequisites.

### Task Package: SBR-REL-VAL.1 — Disposable PostgreSQL reference fixture

**Goal**

Provide an SS-10-only PostgreSQL fixture that creates and drops a uniquely named disposable database, refuses production/shared-state fallbacks, and exposes sanitized environment facts to the reference runner.

**Depends On**

- `SBR-SCHEMA.3` and frozen C-07.

**Files to Read**

- `tests/integration/storage/conftest.py`
- `tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py`
- `tests/fixtures/swarm.py`
- `src/scribe_mcp/storage/postgres/schema.py`

**Files to Modify**

- `tests/integration/storage/conftest.py`

**Files Forbidden**

- The other five SS-10 owned paths; every `src/**` path; all operator/project config; every non-test DSN source.

**Public Contracts / Signatures**

- `validate_disposable_postgres_dsn(dsn: str, *, allow_hosts: Collection[str]) -> SanitizedPostgresTarget`
- `swarm_postgres_backend(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[PostgresReferenceFixture]`
- `PostgresReferenceFixture` exposes the ephemeral DSN only in process memory plus `database_name`, sanitized host/port/database labels, PostgreSQL version, config fingerprint, and async cleanup; it never serializes user, password, query secrets, or the raw DSN.

**Implementation Constraints**

1. Read only `SCRIBE_TEST_POSTGRES_URL` and optional `SCRIBE_TEST_POSTGRES_ADMIN_URL` after `SCRIBE_SWARM_DISPOSABLE=1` is explicit. Reject an identical value from `SCRIBE_POSTGRES_URL`, `DATABASE_URL`, or configured production storage variables.
2. Default accepted hosts are loopback only (`127.0.0.1`, `localhost`, `::1`). Any non-loopback test host requires the explicit comma-separated `SCRIBE_SWARM_TEST_HOST_ALLOWLIST`; record only the sanitized allowlist decision.
3. Create a unique `scribe_swarm_<uuid>` database. For this fixture, insufficient create/drop privilege is a hard failure and shared-database fallback is forbidden. Preserve the existing general `backend` fixture contract outside this new fixture.
4. Register cleanup before setup completes; terminate owned connections, close storage, drop only the exact generated database, and prove no owned database/process remains. Never log credentials or the raw DSN.
5. Capture PostgreSQL server version and a digest of allowlisted non-secret settings. The fixture must not touch an existing Scribe project or operator database.

**Required Tests**

- Add assertions for production-variable collision, missing disposable opt-in, non-allowlisted host, secret-redacted metadata, generated-name enforcement, create/drop success, and cleanup after setup failure.
- Preserve `tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py` and existing SQLite/PostgreSQL conformance behavior.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -m py_compile tests/integration/storage/conftest.py`
- `SCRIBE_SWARM_DISPOSABLE=1 PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py -m postgres`

**Acceptance Criteria**

- [ ] The reference fixture cannot use a production/configured DSN or silently fall back to a shared database.
- [ ] Every run creates and drops one uniquely named disposable database and returns only sanitized environment metadata.
- [ ] Failure and cancellation leave no owned database, connection, or credential-bearing artifact.

**Out of Scope**

Changing PostgreSQL production setup, migration logic, C-07, or existing generic fixture semantics.

**Handoff Notes**

- Forge: STOP if safe disposable setup requires any unlisted source/config file.
- Crucible: run destructive fixture cases only against a disposable test server and inspect teardown.
- Sentinel: review DSN collision checks, redaction, and exact-target cleanup.
- Arbiter: reject shared-state fallback or duplicate PostgreSQL fixture ownership.

### Task Package: SBR-REL-VAL.2 — 32-caller PostgreSQL/process stress and queue proof

**Goal**

Exercise the real provider-neutral swarm, schema readiness, timing envelope, and background queue under disposable PostgreSQL/process profiles while extending C-14 `SwarmResultsV1` rather than creating a second oracle.

**Depends On**

- `SBR-REL-VAL.1`; `SBR-CORE-VAL.1` through `SBR-CORE-VAL.5`; frozen C-07, C-12, and C-14.

**Files to Read**

- `tests/integration/test_swarm_concurrency_stress.py`
- `tests/fixtures/swarm.py`
- `tests/core/test_swarm_binding_reliability.py`
- `tests/core/test_background_queue_contract.py`
- `tests/core/test_wal_replay_exactly_once.py`
- `tests/integration/storage/conftest.py`

**Files to Modify**

- `tests/integration/test_swarm_concurrency_stress.py`

**Files Forbidden**

- Every other SS-10 owned path; `tests/fixtures/swarm.py`; all production and Council files.

**Public Contracts / Signatures**

- `StressProfile.from_env() -> StressProfile` accepts `smoke`, `background-queue`, `release`, and `extended` without separate harnesses.
- `run_reference_stress(profile: StressProfile, *, postgres: PostgresReferenceFixture, source_revision: str, results_dir: Path) -> SwarmResultsV1`
- `swarm-results.json` remains C-14 `scribe-swarm-results.v1`. Its `background_queue` member carries config, foreground/receipt histograms, item/byte/concurrency high-water marks, admission outcomes, queue/run histograms, project shares, worker claims, retry/cancel/lease/fence/shutdown/restart counts; Markdown is derived.

**Implementation Constraints**

1. Reuse `tests/fixtures/swarm.py` and upstream queue/replay oracles. No second scheduler, expected-effects ledger, timing model, or percentile implementation.
2. Smoke is exactly 32 simultaneous same-label `test_agent` sessions across at least four repositories and 16 canonical project partitions, one `set_project` per caller, 100 mixed calls per caller, and at least four worker processes.
3. Include a queue profile with global heavy concurrency 4 and per-project heavy concurrency 1. Rotate overload, retry, cancellation, worker-death, restart, and shutdown faults by project.
4. Hold one project for 10 seconds while peers remain eligible. Prove zero continuously eligible starvation windows ≥5 seconds, no project above 50 percent service while a peer is eligible, unit-job claim imbalance ≤1, and unrelated-project progress before release.
5. Prove item, serialized-byte, global-concurrency, and per-project-concurrency high-water marks never exceed configuration; every forced non-admission is typed; delayed/retry-wait and leased work consume capacity.
6. Prove wrong target, default drift, cross-talk, lost accepted receipt, duplicate effect, accepted stale fence, and unreconciled accepted work after 60 seconds recovery are zero. Teardown returns tasks, handles, sessions, workers, ports, databases, and processes to baseline.
7. Record raw monotonic events and sanitized environment facts; never record credentials, raw DSNs, operator paths, or production identifiers.
8. All smoke, background-queue, and release executions use the one exclusive `SBR_REFERENCE_STRESS` lane; no repository-saturating lane overlaps.

**Required Tests**

- Smoke: 32 callers × 100 calls and exact-effects C-14 oracle.
- Queue: 32 callers/16 partitions/four workers with bounds, fairness, backpressure, no-HOL, death/fence/retry/cancel/restart/shutdown.
- Release: five-minute warmup, 30-minute measurement, five-minute recovery; p50/p95/p99, throughput, RSS, error taxonomy, starvation, recovery, and teardown.
- Budgets: reads p50 ≤75 ms/p95 ≤250 ms; control/read and receipt acknowledgement p95 ≤500 ms; timing accounting ≥95 percent; stages >100 ms and totals >500 ms emit evidence; steady 32-caller throughput ≥50 ops/s and ≥75 percent of four isolated eight-caller runs; peak RSS growth ≤256 MiB, retained ≤64 MiB, final-20-minute slope ≤2 MiB/min; transient non-injected errors ≤0.1 percent.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -m py_compile tests/integration/test_swarm_concurrency_stress.py`
- Exclusive lane smoke: `SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL="$SCRIBE_TEST_POSTGRES_URL" SCRIBE_SWARM_PROFILE=smoke SCRIBE_SWARM_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/swarm-smoke PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py -m "integration and postgres and performance and slow"`

**Acceptance Criteria**

- [ ] 32 same-label callers complete the fixed trace with one bind each and zero correctness defects.
- [ ] Queue fairness, backpressure, worker fencing, restart recovery, and no-HOL verdicts are `PASS`.
- [ ] Measurements share one revision and sanitized environment; teardown returns to baseline.

**Out of Scope**

Hermetic-core oracle changes, queue repair, production load testing, universal hardware promises, or another harness.

**Handoff Notes**

- Forge: consume upstream fixtures/contracts unchanged; STOP on an upstream red.
- Crucible: PASS requires raw-event cardinalities, not only process exit.
- Sentinel: confirm no production credential/state path.
- Arbiter: enforce one oracle family and exclusive heavy lane.

### Task Package: SBR-REL-VAL.3 — Provider-neutral public adapter parity

**Goal**

Run one compact logical trace through each supported public Scribe adapter and prove equivalent target, default, replay, reconnect, and typed-error behavior without Council assumptions.

**Depends On**

- `SBR-CORE-VAL.1`, `SBR-CORE-VAL.3`, `SBR-CORE-VAL.4`, and frozen C-14.

**Files to Read**

- `tests/migration/mcp_v2/test_compatibility_matrix.py`
- `tests/security/test_session_provenance.py`
- `tests/fixtures/swarm.py`
- `tests/core/test_swarm_binding_reliability.py`

**Files to Modify**

- `tests/migration/mcp_v2/test_compatibility_matrix.py`
- `tests/security/test_session_provenance.py`

**Files Forbidden**

- The other four SS-10 owned paths; every production, Council, generated, or provider-host file.

**Public Contracts / Signatures**

- `AdapterParityCase` identifies direct dispatch, modern stdio, modern streamable HTTP, legacy stdio, and supported legacy HTTP/SSE.
- `run_adapter_parity_trace(case: AdapterParityCase, trace: CompactSwarmTrace) -> AdapterParityResult`
- `adapter-parity.json` records source revision, supported/unsupported reason, effective targets, default before/after, replay cardinality, identity/reconnect result, typed error category, and verdict; no secret payloads.

**Implementation Constraints**

1. Reuse one compact upstream trace: bind once, ambient write, explicit authorized write, default readback, reconnect, replay observation, and denial.
2. Compare effective target, unchanged default, exact effect/replay cardinality, server-owned reconnect identity, and typed error category. Formatting may differ only under the existing public compatibility contract.
3. Unsupported legacy paths are explicit `N/A` with a source-backed reason; they never silently pass or enter the PASS denominator.
4. Use disposable repositories and server-minted identities. Denials occur before dispatch and mutate nothing.
5. Emit `adapter-parity.json` only when `SCRIBE_SWARM_RESULTS_DIR` is set; otherwise use `tmp_path`. No `council_mcp` imports or Council acceptance.

**Required Tests**

- Parameterize the compact trace across every supported adapter.
- Cover same-label reconnect, foreign/unknown/revoked/expired denial, explicit-target/default invariance, and replay cardinality.
- Preserve the existing compatibility matrix and session-provenance tests.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -m py_compile tests/migration/mcp_v2/test_compatibility_matrix.py tests/security/test_session_provenance.py`
- `PYTHONPATH=src ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py tests/security/test_session_provenance.py -m "core or regression or mcp_v2" -k "stdio or http or application_handle or reconnect or adapter_parity"`

**Acceptance Criteria**

- [ ] Supported adapters report identical effective target, default invariance, replay cardinality, and typed error category.
- [ ] Reconnect identity is server-owned and cross-session isolation remains exact.
- [ ] Artifact is provider-neutral and secret-free.

**Out of Scope**

Council composition acceptance, public API redesign, or removing supported compatibility paths.

**Handoff Notes**

- Forge: reuse current real-client probes and compact trace.
- Crucible: validate every row, including `N/A` reasons.
- Sentinel: review pre-dispatch denials and redaction.
- Arbiter: reject Council-specific acceptance.

### Task Package: SBR-REL-VAL.4 — Import, RSS, ready, schema, and hot-path budgets

**Goal**

Turn frozen import/RSS/process-ready/schema-ready/hot-path budgets into repeatable release probes whose raw results feed C-15.

**Depends On**

- `SBR-STARTUP.1` through `SBR-STARTUP.3`; `SBR-SCHEMA.3`; `SBR-HOTPATH.1` through `SBR-HOTPATH.3`; frozen C-07, C-10, and C-12.

**Files to Read**

- `tests/test_release_startup_probe.py`
- `src/scribe_mcp/scripts/scribe_probe.py`
- `src/scribe_mcp/server.py`
- `src/scribe_mcp/shared/tool_runtime.py`

**Files to Modify**

- `tests/test_release_startup_probe.py`

**Files Forbidden**

- The other five SS-10 owned paths; every production and configuration file.

**Public Contracts / Signatures**

- `run_release_budget_probe(*, profile: Literal["warm", "cold", "object-store-outage", "schema-32", "hot-path"], source_revision: str, results_dir: Path) -> ReleaseBudgetProbeResult`
- `startup-budget.json` records revision, repetitions, raw samples, percentile method, module count, import-time writes, pre-tool/all-tools RSS, service states, schema roles/waits, C-12 phases/total/accounting/tripwires, environment fingerprint, and verdicts.

**Implementation Constraints**

1. Use fresh subprocesses for import/RSS/ready. Warm/cold cache preparation is explicit; record at least five samples and percentile method.
2. Enforce import warm p95 ≤1.0 s/cold p95 ≤1.5 s; pre-tool ready RSS ≤64 MiB; all-tools-loaded RSS ≤80 MiB; no token encoder or metrics-directory write before token use.
3. Enforce process-to-ready warm p95 ≤1.5 s/cold p95 ≤2.5 s; optional object-store outage adds ≤50 ms and cannot block core tools/local logging; C-10 marks it degraded without blocking core ready.
4. Start 32 simultaneous processes against one stale disposable schema: exactly one C-07 bootstrapper, same fingerprint/version, warm setup p95 ≤100 ms, warm non-bootstrap wait ≤500 ms, and typed fail-closed deadline mismatch.
5. After one bind, enforce reads p50 ≤75 ms/p95 ≤250 ms; durable append/receipt p95 ≤500 ms; every synchronous class p95 ≤500 ms; C-12 accounting ≥95 percent, at most one binding/project read, and tripwires for stage >100 ms or total >500 ms.
6. Record Python executable/version, package versions, platform/kernel/machine, CPU count/model, memory, and sanitized PostgreSQL facts. Use monotonic time, OS/`psutil` RSS, disposable roots/environment.
7. Unit tests may inject probe records; actual measurements run only inside `SBR_REFERENCE_STRESS`.

**Required Tests**

- Preserve current release-bootstrap tests.
- Add PASS/FAIL boundary tests for every budget, missing sample, mixed revision, optional outage, 32-start election, C-12 accounting/read-count/tripwire rules.
- Retain raw samples for each derived verdict.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -m py_compile tests/test_release_startup_probe.py`
- `PYTHONPATH=src ./.venv/bin/pytest -q tests/test_release_startup_probe.py`

**Acceptance Criteria**

- [ ] Every budget emits raw samples and explicit PASS/FAIL.
- [ ] Mixed revisions, missing evidence, excessive reads, unexplained time, and absent tripwires fail.
- [ ] No production contact or teardown leak.

**Out of Scope**

Changing startup, schema, timing, token, object-store, or hot-path implementation.

**Handoff Notes**

- Forge: test frozen records; do not alter production for probe convenience.
- Crucible: verify threshold equality and one-over failures.
- Sentinel: inspect subprocess environment and redaction.
- Arbiter: require raw samples and deterministic derivation.

### Task Package: SBR-REL-VAL.5 — Single-lane release runner and C-15 evidence

**Goal**

Provide the thin operator entrypoint that serializes the complete reference gate and emits the only `ReliabilityReleaseEvidenceV1` from same-revision subordinate evidence.

**Depends On**

- `SBR-REL-VAL.1` through `SBR-REL-VAL.4` and PASS C-14 `SwarmResultsV1`.

**Files to Read**

- `benchmarks/swarm_concurrency.py`
- `tests/fixtures/swarm.py`
- `tests/integration/test_swarm_concurrency_stress.py`
- `tests/migration/mcp_v2/test_compatibility_matrix.py`
- `tests/security/test_session_provenance.py`
- `tests/test_release_startup_probe.py`

**Files to Modify**

- `benchmarks/swarm_concurrency.py`

**Files Forbidden**

- The other five SS-10 owned paths; every production/release/version/Council/generated file.

**Public Contracts / Signatures**

- `main(argv: Sequence[str] | None = None) -> int`
- `build_release_evidence(*, source_revision: str, target_version: str, core: Mapping[str, object], postgres: Mapping[str, object], adapters: Mapping[str, object], startup: Mapping[str, object], queue: Mapping[str, object], artifact_paths: Sequence[Path], exact_commands: Sequence[str], environment_fingerprint: Mapping[str, object]) -> ReliabilityReleaseEvidenceV1`
- `reliability-release-evidence.json` has exactly frozen C-15 top-level fields: `source_revision`, `target_version` (`2.15.0`), `core_verdict`, `postgres_smoke_verdict`, `adapter_parity_verdict`, `import_budget_verdict`, `startup_budget_verdict`, `queue_budget_verdict`, `artifact_paths`, `exact_commands`, `environment_fingerprint`. Verdicts are `PASS` or `FAIL`; detail stays in referenced artifacts.
- `reliability-release-evidence.md` is JSON-derived only.

**Implementation Constraints**

1. Resolve `git rev-parse HEAD`, require no tracked staged/unstaged changes, and record it. Reject missing revision, dirty tracked tree, target version not `2.15.0`, or a subordinate artifact with another revision.
2. Acquire one filesystem lock `SBR_REFERENCE_STRESS` under the results directory; refuse concurrent owners. All PostgreSQL/process smoke, 32-start, queue, adapter, startup, and soak work is sequential inside it.
3. Run/ingest in order: C-14 core proof; 32×100 PostgreSQL smoke; 32-caller queue proof; import/RSS/ready/schema/hot-path probes; adapter parity; release soak; teardown/reconciliation. Infrastructure failure writes a secret-free FAIL diagnostic.
4. Capture exact argv and environment key names, never secret values. Fingerprint Python/Scribe/MCP/asyncpg/psutil versions, OS/platform/kernel/machine, CPU count/model, memory, PostgreSQL versions/config digest, profile/seed/caller/worker/cap settings, and revision.
5. Emit C-15 only after artifact schema, revision equality, raw fields, and every verdict PASS. Any required `FAIL`/`N/A`, missing artifact, cleanup leak, dirty tree, or mixed revision/environment returns nonzero.
6. `core_verdict` is C-14 only; `postgres_smoke_verdict` is 32×100; `adapter_parity_verdict` is provider-neutral matrix; `import_budget_verdict` is import/RSS; `startup_budget_verdict` is ready/outage/C-07/C-12 hot path; `queue_budget_verdict` is bounds/backpressure/fairness/fencing/recovery/no-HOL.
7. Write atomically under gitignored `benchmarks/artifacts/<revision>/`; use repo-relative paths, digest subordinate JSON, redact secrets, and derive Markdown.
8. Runner is orchestration/reporting only; workload/oracle/metrics/adapter logic remains in tests/upstream fixtures.

**Required Tests**

- Unit-test clean/dirty revision, mixed revision/environment, missing field/artifact, digest mismatch, required `N/A`, redaction, lock contention, atomic write, derived Markdown, all-PASS, and any-red nonzero.
- Execute the final lane once and retain JSON/Markdown plus exact command transcript.

**Verification Commands**

- `PYTHONPATH=src ./.venv/bin/python -m py_compile benchmarks/swarm_concurrency.py`
- `PYTHONPATH=src ./.venv/bin/python benchmarks/swarm_concurrency.py --help`
- Exclusive final lane: `SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL="$SCRIBE_TEST_POSTGRES_URL" SCRIBE_SWARM_PROFILE=release SCRIBE_SWARM_CALLERS=64 SCRIBE_SWARM_SMOKE_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_WARMUP_SECONDS=300 SCRIBE_SWARM_DURATION_SECONDS=1800 SCRIBE_SWARM_RECOVERY_SECONDS=300 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/sbr-2.15.0 PYTHONPATH=src ./.venv/bin/python benchmarks/swarm_concurrency.py --profile release --target-version 2.15.0 --postgres-url-env SCRIBE_TEST_POSTGRES_URL --results-dir benchmarks/artifacts/sbr-2.15.0`

**Acceptance Criteria**

- [ ] Exactly one exclusive runner owns every repository-saturating reference action and records exact commands/environment/revision.
- [ ] C-15 is machine-readable, secret-free, same-revision, digest-linked, and every required verdict is `PASS`.
- [ ] Queue fairness/backpressure/no-HOL, adapter parity, import/RSS/ready/hot-path, 32-caller smoke, soak, and teardown are represented.
- [ ] Missing, mixed, dirty, leaked, or failed evidence prevents PASS and returns nonzero.

**Out of Scope**

Version bump, release docs, commit/PR, deploy, publish, Council acceptance, or a second benchmark implementation.

**Handoff Notes**

- Forge: keep runner thin and STOP if a subordinate contract must change.
- Crucible: run package commands separately, then final lane once; every C-15 verdict must PASS.
- Witness: verify signatures, revision, digests, ownership, and no Council/production references.
- Sentinel: review credential non-use/redaction and cleanup.
- Arbiter: required for performance/integration/security risk; reject mixed-revision or independent Markdown evidence.

### DA-10 Dependency and Release Gate

1. Implement `SBR-REL-VAL.1` first.
2. `SBR-REL-VAL.2`, `SBR-REL-VAL.3`, and `SBR-REL-VAL.4` may proceed after upstream packages pass; their files are disjoint.
3. Implement `SBR-REL-VAL.5` after all evidence producers pass.
4. Crucible runs each scoped command separately, then holds `SBR_REFERENCE_STRESS` for one final lane; no repository-saturating lane overlaps.
5. C-15 is READY for DA-11 only when every `SBR-REL-VAL.*` item is complete and every required verdict in `reliability-release-evidence.json` is `PASS` for one clean revision.
## DA-11 — Release surfaces detail
<!-- ID: sbr-release-closure -->
### APPROACH_SUMMARY

- Goal: synchronize the five frozen SS-11 source/public release surfaces to one backward-compatible `2.15.0` MINOR release only after every implementation, validation, and review gate is current for the C-15 source revision.
- Files to modify: `pyproject.toml`, `src/scribe_mcp/__init__.py`, `README.md`, `docs/RELEASE_SURFACE.md`, and `docs/RELEASE_FILE_MAP.md`.
- Files forbidden: every other source, test, schema, generated Council surface, managed workstream document, build artifact, deployment surface, and package-publication surface.
- Out of scope: behavior changes, dependency changes, new tests, schema work, Council-specific logic, generated projection changes, deployment, publication, runtime restart/adoption, and any merge to `main`.
- Verification plan: prove C-15 PASS against the pre-release parent revision; verify the exact five-file diff, import/version parity, public release-note and map consistency, focused neighbor tests, whitespace and secret scans; then hand the validated patch to governed Git custody for one commit, branch push, and PR targeting `dev`.
- Frozen-input proof: accepted seam SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`; C-15 `ReliabilityReleaseEvidenceV1` is frozen and must report `target_version=2.15.0`, the six required `PASS` verdicts, artifact paths, exact commands, environment fingerprint, and the current pre-release source revision.

### Task Package: SBR-RELEASE.1 — Synchronize 2.15.0 release truth and open the governed dev PR

**Goal**

- Apply exactly one additive MINOR bump from the current `2.14.1` package manifest to `2.15.0`, add the runtime package version, and make README release notes plus both public release maps tell the same standalone Scribe truth.
- Preserve the validated implementation revision as the sole parent of the release-truth commit, then use authorized Git custody for one commit, one branch push, and one PR whose base is `dev`.

**Depends On**

- `SBR-REL-VAL.5` and every `SBR-REL-VAL.C15.*` gate are complete; `reliability-release-evidence.json` is secret-free and every required verdict is `PASS` for one clean source revision.
- Every implementation package, package-declared validation/review gate, `SBR-FINAL.CONTRACTS`, `SBR-FINAL.REVISION`, and `SBR-FINAL.REVIEWS` is current for that same revision.
- The accepted SEAM_MAP remains SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`; any contract, target-version, or owned-path drift stops this package for Blueprint amendment.

**Files to Read**

- `.scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md` (`SS-11`, `C-15`, `DA-11` only)
- `.scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/ARCHITECTURE_GUIDE.md` (release boundary and frozen C-15 only)
- `benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json`
- `pyproject.toml`
- `src/scribe_mcp/__init__.py`
- `README.md`
- `docs/RELEASE_SURFACE.md`
- `docs/RELEASE_FILE_MAP.md`

**Files to Modify**

- `pyproject.toml`
- `src/scribe_mcp/__init__.py`
- `README.md`
- `docs/RELEASE_SURFACE.md`
- `docs/RELEASE_FILE_MAP.md`

**Files Forbidden**

- Every path not listed under Files to Modify, including `tests/**`, `benchmarks/**`, `.scribe/**`, `.council/**`, `.claude/**`, `.codex/**`, `.github/**`, `CHANGELOG.md`, `MANIFEST.in`, `docs/COMPATIBILITY_MATRIX.md`, `src/scribe_mcp/__main__.py`, build/dist/egg-info output, deployment files, and any generated projection.
- Do not create a parallel version module, release manifest, changelog, release script, or generated readback.

**Public Contracts / Signatures**

- `pyproject.toml:[project].version = "2.15.0"` is package/build metadata truth.
- `scribe_mcp.__version__: str = "2.15.0"` is additive runtime truth and is exported in `scribe_mcp.__all__`; all existing exports remain unchanged.
- `README.md#Current release highlights` is the SS-11 public release-note/changelog surface and must identify `scribe-mcp 2.15.0`, date `2026-09-27`, the validated binding-reliability scope, and the source-only boundary.
- `docs/RELEASE_SURFACE.md` must identify the `v2.15.0` public release line and distinguish tracked standalone Scribe source/public docs from operator-local, generated, deployed, or published state.
- `docs/RELEASE_FILE_MAP.md` must identify `v2.15.0`, list both version authorities (`pyproject.toml` and `src/scribe_mcp/__init__.py`), identify README release highlights as the public changelog, and state that the PR targets `dev`; promotion/merge to `main` and PyPI publication are later separately authorized actions.

**Implementation Constraints**

1. Before any edit, parse C-15 and require all six verdict fields to be `PASS`, `target_version` to be `2.15.0`, every artifact path to exist, and `source_revision` to equal `git rev-parse HEAD`. Record this revision as the release commit's required parent.
2. Make one coherent five-file patch. Change no executable behavior, dependency specifier, protocol declaration, compatibility rule, license, packaging inclusion, or CLI entry point.
3. Change `pyproject.toml` from `2.14.1` to exactly `2.15.0`. In `src/scribe_mcp/__init__.py`, add the annotated constant `__version__: str = "2.15.0"` and append `"__version__"` to the existing `__all__` without removing or reordering existing public module exports.
4. Rewrite only the current-release claims in README and both release maps. Historical predecessor references may remain when explicitly labeled historical; stale headings or rows that still call `2.14.0`, `2.13.0`, or `v2.7.1` current must not remain.
5. README release highlights must summarize only behavior proven by the accepted workstream and C-15: durable caller-session defaults, explicit targets without default mutation, typed errors, bounded readiness/background work, generation-safe document replay, isolation/stress proof, and the exact source-only boundary. Do not introduce Council/Aegis/work-item/provider-seat/spawn policy.
6. Treat README Current release highlights as the public changelog for this frozen package. Do not create or edit a separate repo `CHANGELOG.md`; managed project changelogs and `.scribe/docs/GLOBAL_CHANGELOG.md` remain operator-local/derived and outside the public release commit.
7. Run every verification command separately. Any failed/missing C-15 field, missing artifact, changed contract, new owned path, stale current-version claim, version mismatch, test failure, secret finding, or diff-scope mismatch blocks Git custody.
8. Forge owns only the five-file source patch and must not stage, commit, push, or open the PR. After Crucible/Witness/Arbiter PASS on the final patch, the chartered coordinator or authorized Git custodian stages exactly these five paths and creates exactly one commit with subject `release: scribe-mcp 2.15.0`.
9. The release commit must have exactly one parent and that parent SHA must equal C-15 `source_revision`. Preserve unrelated dirty paths unstaged; if the designated release checkout cannot prove this parent or exact staged set, stop instead of folding unrelated work into the release commit.
10. The authorized custodian pushes the current non-protected branch to `origin` and opens one PR with base `dev`. The PR must include the C-15 parent SHA, release commit SHA, five-file patch digest, test/diff/secret evidence, and the explicit statement: no publish, deploy, restart/adoption, production credential use, or `main` merge was performed.

**Required Tests**

- Run `tests/test_versioning_behavior.py` and `tests/doc_management/test_version_context.py` to preserve Scribe's pyproject-version observation behavior.
- Run `tests/migration/mcp_v2/test_compatibility_matrix.py::test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree` because README and `docs/RELEASE_FILE_MAP.md` participate in its public compatibility readback.
- Import `scribe_mcp` from `src` and assert the new runtime version without installation or runtime restart.
- Validate exact current-version markers and reject stale current-release headings/rows while allowing explicitly historical predecessor references.
- Failure cases: a non-PASS or mixed-revision C-15 file; a version other than `2.15.0`; an added sixth file; a stale current-release marker; a secret-pattern match; a protected/empty branch; wrong remote; wrong PR base; or a release commit whose parent is not C-15 must fail the corresponding gate.

**Verification Commands — pre-edit C-15 gate**

- `test -s benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json`
- `./.venv/bin/python -c 'import json, pathlib, subprocess; p=pathlib.Path("benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json"); e=json.loads(p.read_text()); verdicts=("core_verdict","postgres_smoke_verdict","adapter_parity_verdict","import_budget_verdict","startup_budget_verdict","queue_budget_verdict"); assert e["target_version"] == "2.15.0"; assert all(e[k] == "PASS" for k in verdicts); assert e["source_revision"] == subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip(); assert e["artifact_paths"] and all(pathlib.Path(x).exists() for x in e["artifact_paths"]); assert e["exact_commands"] and e["environment_fingerprint"]'`

**Verification Commands — source and documentation**

- `PYTHONPATH=src ./.venv/bin/python -c 'import tomllib, scribe_mcp; assert tomllib.load(open("pyproject.toml","rb"))["project"]["version"] == "2.15.0"; assert scribe_mcp.__version__ == "2.15.0"; assert "__version__" in scribe_mcp.__all__'`
- `./.venv/bin/python -c 'from pathlib import Path; r=Path("README.md").read_text(); s=Path("docs/RELEASE_SURFACE.md").read_text(); m=Path("docs/RELEASE_FILE_MAP.md").read_text(); assert "Release contract: `scribe-mcp 2.15.0` · Updated: `2026-09-27`" in r; assert "v2.15.0 public release line" in s; assert "2.15.0" in m and "src/scribe_mcp/__init__.py" in m and "Current release highlights" in m; stale=("Release contract: `scribe-mcp 2.14.0`", "current: 2.13.0", "scribe-mcp==2.13.0", "v2.7.1 public release line"); assert not any(x in r+s+m for x in stale)'`
- `PYTHONPATH=src ./.venv/bin/pytest -q tests/test_versioning_behavior.py tests/doc_management/test_version_context.py`
- `PYTHONPATH=src ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py::test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree`
- `git diff --check -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md`
- `git diff --name-status -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md`

**Verification Commands — governed Git custody**

- `case "$(git branch --show-current)" in ""|main|dev) exit 1;; esac`
- `test "$(git remote get-url origin)" = "https://github.com/CortaLabs/scribe_mcp.git"`
- `git add -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md`
- `diff -u <(printf '%s\n' README.md docs/RELEASE_FILE_MAP.md docs/RELEASE_SURFACE.md pyproject.toml src/scribe_mcp/__init__.py | sort) <(git diff --cached --name-only --diff-filter=ACMRT | sort)`
- `git diff --cached --check`
- `! git diff --cached --unified=0 -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md | rg -q 'AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,255}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'`
- `git diff --cached --binary -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md | sha256sum`
- `git commit -m "release: scribe-mcp 2.15.0"`
- `./.venv/bin/python -c 'import json, pathlib, subprocess; e=json.loads(pathlib.Path("benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json").read_text()); assert subprocess.check_output(["git","rev-parse","HEAD^"], text=True).strip() == e["source_revision"]; assert subprocess.check_output(["git","show","-s","--format=%s","HEAD"], text=True).strip() == "release: scribe-mcp 2.15.0"'`
- `git show --format=fuller --name-status --stat HEAD`
- `git push -u origin HEAD`
- `test "$(git ls-remote --heads origin "$(git branch --show-current)" | cut -f1)" = "$(git rev-parse HEAD)"`
- `gh pr create --base dev --head "$(git branch --show-current)" --title "release: scribe-mcp 2.15.0" --body "Source-only Scribe 2.15.0 release candidate. C-15 PASS for the parent revision. No publish, deploy, runtime adoption, production credential use, or main merge is included."`
- `gh pr view --json url,state,baseRefName,headRefName,commits,files,statusCheckRollup`

**Acceptance Criteria**

- [ ] C-15 is complete, secret-free, same-revision, target `2.15.0`, and all six required verdicts are `PASS`; the eventual release commit parent equals its `source_revision`.
- [ ] Exactly the five frozen SS-11 paths change and are staged; no implementation, test, schema, generated, operator-local, or unrelated file enters the release commit.
- [ ] Package metadata and `scribe_mcp.__version__` both equal `2.15.0`; the additive runtime export preserves all existing exports.
- [ ] README Current release highlights is the synchronized public changelog, and both release maps identify the same version, standalone Scribe contract, owned surfaces, and source-only boundary.
- [ ] Focused tests, import/version checks, stale-marker checks, `git diff --check`, exact staged-path comparison, and the high-confidence secret scan pass.
- [ ] One governed commit has subject `release: scribe-mcp 2.15.0`; its pushed remote SHA equals local HEAD.
- [ ] One PR exists with head equal to the pushed branch and base exactly `dev`; its evidence records the C-15 parent, release commit, patch digest, and explicit no-publish/no-deploy/no-main-merge boundary.

**Out of Scope**

- Any implementation or validation repair; C-15 regeneration; dependency/protocol/schema changes; additional docs/tests; Council-specific behavior; generated surfaces; build artifacts; package upload; tag/release creation; deployment; service restart/adoption; production credentials; branch-protection changes; and any merge to `main`.

**Handoff Notes**

- Forge: edit only the five Files to Modify; stop if another path or a behavior change is needed. Do not stage, commit, push, or create the PR.
- Crucible: run each listed test/command separately and validate every acceptance item, including negative C-15/version/scope cases; do not substitute the full suite.
- Witness: verify accepted seam hash, C-15 parent linkage, exact path ownership, runtime signature, exact staged set, branch/remote/PR-base truth, and absence of forbidden actions.
- Arbiter: required by SS-11 `public_contract`/`arbiter_review`; review release-note accuracy, backward compatibility, boundedness, and evidence completeness.
- Chartered coordinator or authorized Git custodian: only after current PASS gates, perform the listed stage/commit/push/PR actions. Stop before publish, deploy, restart/adoption, tag/release creation, or any merge to `main`.
## Implementation Registry Synthesis
<!-- ID: sbr-implementation-registry-synthesis -->

- Registry receipt: direct Council import accepted 59 total rows with 39 created, 0 updated, 0 orphaned, and 0 validation errors.
- Synthesis hold: the live frontier is intentionally empty while `SBR-PLAN-SYNTH-12` is `in_progress`; completion releases the first implementation wave.
- First wave after synthesis: `SBR-BIND-PERSIST.1` (`c7e2047d-6db1-4841-87da-f3e053662e87`), `SBR-BIND-RESOLVE.1` (`6058f4c6-b437-4304-8dc4-ca7f99aaa194`), `SBR-STARTUP.1` (`2d48d2b5-0e2a-4537-b43e-9d1fe18f5555`), and `SBR-STARTUP.2` (`81007204-ed20-4580-9727-846031ff3a1e`).
- Shared-file serialization: `storage/base.py` is ordered `SBR-BIND-PERSIST.2 -> SBR-RECEIPT.1`; `storage/postgres/__init__.py` is ordered `SBR-SCHEMA.3 -> SBR-BIND-PERSIST.3 -> SBR-RECEIPT.3`; `state/manager.py`, `server.py`, and `doc_management/runtime.py` retain their accepted package order.
- Heavy validation: `SBR-REL-VAL.2` precedes `SBR-REL-VAL.5`; `SBR-REL-VAL.5` remains the only final repository-saturating runner.
- Release hold: `SBR-RELEASE.1` depends directly on `SBR-PLAN-SYNTH-12` plus all 38 preceding executable packages, so every declared same-revision evidence requirement must PASS before release custody.
- Frozen boundary: every new row forbids `council_mcp` files/imports and Council/Aegis/seat/run/work-item/projection semantics; Scribe owns only the generic contracts frozen by the accepted seam SHA-256 `8c0091b53b70ae284b65eff73e674191bd29ec5f9eb3cd40386daa1a3c776f61`.
