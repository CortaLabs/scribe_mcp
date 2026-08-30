---
id: scribe_rehome_resolution_fix_20260830-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe_rehome_resolution_fix_20260830"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: ready
version: '1.0'
last_updated: 2026-08-30 19:39:52 UTC
maintained_by: agent-20260830-191342-81801aff
created_by: agent-20260830-191342-81801aff
owners:
- Blueprint
related_docs: []
tags:
- dry-run
- apply-preview
- rehome
- security
summary: Dependency-ordered executable packages for apply-preview implementation,
  validation, and 2.14.0 release.
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-08-30 19:39:52 UTC
  created_via: frontmatter_update
  last_edited_at: 2026-08-30 19:39:52 UTC
  last_edited_by: agent-20260830-191342-81801aff
  last_action: frontmatter_update
  work_item_id: 253998c7-c9d2-4379-925d-ea3ee4c146dc
---

# ⚙️ Phase Plan — scribe_rehome_resolution_fix_20260830
**Author:** Blueprint
**Version:** v1.0
**Status:** Ready
**Last Updated:** 2026-08-30 UTC

> Execution roadmap for scribe_rehome_resolution_fix_20260830.

---
## Phase Overview
<!-- ID: phase_overview -->
| Wave | Packages | Outcome |
|---|---|---|
| Baseline | SCRIBE-REHOME-B1, SCRIBE-DRY-APPLY-R1, SCRIBE-DRY-APPLY-R2, SCRIBE-DRY-APPLY-P1 | Existing rehome fix, research, security contract, and this executable plan |
| 1 | SCRIBE-DRY-APPLY-I1 | Frozen typed storage contract |
| 2 | SCRIBE-DRY-APPLY-I2, SCRIBE-DRY-APPLY-I3, SCRIBE-DRY-APPLY-I4 | SQLite, PostgreSQL, and Remote parity |
| 3 | SCRIBE-DRY-APPLY-I5 | Receipt engine, fencing, replay, and multi-locks |
| 4 | SCRIBE-REHOME-B3 | Preserve dirty rehome repair and integrate public apply runtime |
| 5 | SCRIBE-DRY-APPLY-V1 | Cross-backend behavioral and security evidence |
| 6 | SCRIBE-REHOME-B2 | 2.14.0 version and release truth |

Dependency order: `I1 -> {I2,I3,I4} -> I5 -> B3 -> V1 -> B2`. The first implementation dispatch after import is `SCRIBE-DRY-APPLY-I1`.

### SCRIBE-REHOME-B1

Completed baseline package. Its current dirty rehome/create-preview changes must be preserved.

### SCRIBE-DRY-APPLY-R1

Completed source-reuse research in `research/RESEARCH_DRY_RUN_APPLY_REUSE.md`.

### SCRIBE-DRY-APPLY-R2

Security artifact is complete; review custody was force-closed after two identical findings. The two findings are mandatory requirements in every downstream package.

### SCRIBE-DRY-APPLY-P1

This Blueprint package authors the architecture, plan, checklist, and executable manifest only. It owns no source, test, release, Git, or runtime mutation.


---
## Phase 0 — Define First Implementation Slice
<!-- ID: phase_0 -->
### SCRIBE-DRY-APPLY-I1

**Title:** Define durable apply-preview receipt records and StorageBackend contract

**Goal**

Introduce the single typed persistence contract every backend must implement, with fail-closed capability semantics and no runtime behavior yet.

**Depends On**

None.

**Files to Read**

- `src/scribe_mcp/storage/base.py`
- `src/scribe_mcp/storage/models.py`
- `tests/test_storage_models_compatibility.py`
- `tests/integration/storage/test_storage_backend_shared_contract.py`

**Files to Modify**

- `src/scribe_mcp/storage/base.py`
- `src/scribe_mcp/storage/models.py`
- `tests/storage/test_apply_preview_receipt_contract.py`

**Files Forbidden**

- `src/scribe_mcp/doc_management/**`
- `src/scribe_mcp/storage/sqlite/**`
- `src/scribe_mcp/storage/postgres/**`
- `src/scribe_mcp/storage/remote.py`
- `src/scribe_mcp/server_sse.py`
- `pyproject.toml`, `README.md`

**Public Contracts / Signatures**

- `ApplyPreviewReceiptRecord` contains the immutable binding, retained intent, lifecycle/fence, terminal result, expiry, and audit fields defined in `ARCHITECTURE_GUIDE.md#c-receipt-storage-typed-durable-lifecycle`.
- `ApplyPreviewClaimResult.status` is one of `claimed|recovery|terminal|busy|expired|not_found`.
- `StorageBackend.issue_apply_preview_receipt(record: ApplyPreviewReceiptRecord) -> ApplyPreviewReceiptRecord`
- `StorageBackend.fetch_apply_preview_receipt(token_sha256: str) -> ApplyPreviewReceiptRecord | None`
- `StorageBackend.claim_apply_preview_receipt(token_sha256: str, *, lease_seconds: int) -> ApplyPreviewClaimResult`
- `StorageBackend.finalize_apply_preview_receipt(token_sha256: str, *, fence: int, terminal_state: str, result_code: str, result_json: str) -> ApplyPreviewReceiptRecord`
- `StorageBackend.cleanup_apply_preview_receipts() -> int`

**Implementation Constraints**

1. Token plaintext is not a model field; only a validated 64-character SHA-256 hex lookup key is retained.
2. Base methods raise `NotImplementedError`; callers must translate missing support to storage-unavailable rather than succeed.
3. Lifecycle, result-code, and claim-status vocabularies are closed and validated at construction/decoding boundaries.
4. Records serialize through the existing dataclass/JSON transport path without `Any`-shaped public ambiguity.

**Required Tests**

- New contract tests prove field validation, closed states, redacted representation, terminal immutability semantics, and missing-backend fail-closed behavior.
- Preserve storage-model compatibility tests.

**Verification Commands**

- `uv run pytest -q tests/storage/test_apply_preview_receipt_contract.py tests/test_storage_models_compatibility.py`
- `uv run python -c 'from scribe_mcp.storage.base import StorageBackend; from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord'`

**Acceptance Criteria**

- [ ] One typed record/claim contract exists and contains no plaintext token field.
- [ ] Every backend method signature is exact and fail-closed by default.
- [ ] Closed lifecycle/claim vocabularies reject malformed values.
- [ ] Focused tests and both import smokes pass.

**Out of Scope**

Backend SQL, Remote operations, runtime action wiring, rehome changes, versioning.

**Handoff Notes**

- Sia: stop if a backend-specific file is needed.
- Crucible: verify record validation and default fail-closed behavior.
- Sentinel: final security evidence is centralized in `SCRIBE-DRY-APPLY-V1`.


---
## Phase 1 — Next Bounded Slice
<!-- ID: phase_1 -->
### SCRIBE-DRY-APPLY-I2

**Title:** Implement SQLite atomic receipt lifecycle

**Goal**

Add the receipt table and single-statement issue/fetch/claim/finalize/cleanup behavior to SQLite.

**Depends On**

- `SCRIBE-DRY-APPLY-I1`

**Files to Read**

- `src/scribe_mcp/storage/sqlite/internals.py`
- `tests/test_sqlite_internals.py`

**Files to Modify**

- `src/scribe_mcp/storage/sqlite/schema.py`
- `src/scribe_mcp/storage/sqlite/apply_preview_receipts.py`
- `src/scribe_mcp/storage/sqlite/__init__.py`
- `tests/storage/test_sqlite_apply_preview_receipts.py`

**Files Forbidden**

PostgreSQL, Remote, runtime, manager, release files.

**Public Contracts / Signatures**

Implement all five `StorageBackend` receipt methods from I1 without signature drift.

**Implementation Constraints**

1. Add `apply_preview_receipts` plus expiry and state/lease indexes through the existing schema initializer.
2. Claim is one guarded `UPDATE ... RETURNING` under SQLite's write gate; it claims unexpired issued rows or an expired applying lease and increments the fence.
3. Finalize is one conditional update requiring applying state and the exact fence.
4. Terminal fetch returns stored result; cleanup cannot remove non-expired or applying rows.

**Required Tests**

Concurrent claims produce one owner; stale fence finalize fails; expired applying lease yields recovery with a larger fence; terminal rows replay; cleanup is bounded.

**Verification Commands**

- `uv run pytest -q tests/storage/test_sqlite_apply_preview_receipts.py tests/test_sqlite_internals.py tests/integration/storage/test_storage_backend_shared_contract.py`
- `uv run python -c 'from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.sqlite.apply_preview_receipts import claim_apply_preview_receipt'`

**Acceptance Criteria**

- [ ] SQLite persists no plaintext bearer.
- [ ] Atomic claim/fence/recovery/replay tests pass.
- [ ] Storage errors surface; no in-memory fallback exists.
- [ ] Import smokes pass.

**Out of Scope**

Other backends, public runtime, rehome executor.

**Handoff Notes**

Sia owns the four files. Crucible validates concurrency with real SQLite connections.

### SCRIBE-DRY-APPLY-I3

**Title:** Implement PostgreSQL receipt schema, migration, and atomic lifecycle

**Goal**

Provide fresh-install and upgrade-safe PostgreSQL parity using server-side atomic conditional statements.

**Depends On**

- `SCRIBE-DRY-APPLY-I1`

**Files to Read**

- `src/scribe_mcp/storage/postgres/schema.py`
- `src/scribe_mcp/storage/postgres/internals.py`
- `src/scribe_mcp/db/postgres_migrations/004_tool_call_correlation_metadata.sql`

**Files to Modify**

- `src/scribe_mcp/storage/postgres/__init__.py`
- `src/scribe_mcp/db/init.sql`
- `src/scribe_mcp/db/postgres_migrations/005_apply_preview_receipts.sql`
- `tests/integration/storage/test_postgres_apply_preview_receipts.py`

**Files Forbidden**

SQLite, Remote, runtime, manager, release files.

**Public Contracts / Signatures**

Implement the five I1 methods exactly.

**Implementation Constraints**

1. Fresh schema and numbered migration define byte-equivalent receipt columns, constraints, and indexes.
2. Migration is additive/idempotent and uses the existing Scribe PostgreSQL migration loader; no AgentKit or council-local migration command is introduced.
3. Claim and finalize use database `NOW()` and atomic `UPDATE ... RETURNING`; no read-then-write claim.
4. JSON fields remain JSONB and returned records use the I1 dataclass decoder.

**Required Tests**

Fresh schema, migration idempotency, concurrent claim, recovery fence, stale finalize, replay, cleanup, and schema scoping.

**Verification Commands**

- `uv run pytest -q tests/integration/storage/test_postgres_apply_preview_receipts.py tests/test_postgres_project_identity_scoping.py tests/integration/storage/test_storage_backend_shared_contract.py`
- `uv run python -c 'from scribe_mcp.storage.postgres import PostgresStorage'`

**Acceptance Criteria**

- [ ] Fresh and migrated PostgreSQL schemas match.
- [ ] Atomic lifecycle behavior matches SQLite.
- [ ] Database time and fence predicates are enforced.
- [ ] Focused tests and import smoke pass.

**Out of Scope**

Production migration apply, Remote transport, runtime behavior.

**Handoff Notes**

Sia owns the four files. This package is schema-sensitive; stop if destructive DDL appears.

### SCRIBE-DRY-APPLY-I4

**Title:** Implement Remote backend parity and fail-closed transport

**Goal**

Expose the five backend operations as authenticated internal RPCs while preserving server-side atomicity and public-release denial.

**Depends On**

- `SCRIBE-DRY-APPLY-I1`

**Files to Read**

- `src/scribe_mcp/storage/remote.py`
- `src/scribe_mcp/server_sse.py`
- `tests/security/test_remote_fail_closed.py`

**Files to Modify**

- `src/scribe_mcp/storage/remote.py`
- `src/scribe_mcp/server_sse.py`
- `tests/test_remote_backend.py`
- `tests/security/test_apply_preview_remote_fail_closed.py`

**Files Forbidden**

SQLite, PostgreSQL, runtime, manager, release files.

**Public Contracts / Signatures**

Implement the five I1 methods exactly. Each operation maps to one `_call` and returns decoded I1 records.

**Implementation Constraints**

1. Add operations only to the authenticated legacy/internal allowlist; public-release transport continues to deny them.
2. Claim/finalize are one RPC each. The client cannot emulate CAS with fetch plus update.
3. Connection, timeout, forbidden-operation, malformed-payload, or missing-method outcomes fail closed.
4. Token hashes and retained intent never enter logs or exception messages.

**Required Tests**

One-call delegation, dataclass decoding, public deny, auth failure, timeout, malformed response, and no fallback.

**Verification Commands**

- `uv run pytest -q tests/test_remote_backend.py tests/security/test_apply_preview_remote_fail_closed.py tests/security/test_remote_fail_closed.py`
- `uv run python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; from scribe_mcp.server_sse import _LEGACY_OPERATION_ALLOWLIST'`

**Acceptance Criteria**

- [ ] All five methods delegate once and decode safely.
- [ ] Public-release transport denies every receipt mutation operation.
- [ ] Remote failures never create local receipt state or success.
- [ ] Focused tests and import smokes pass.

**Out of Scope**

Public REST API expansion, runtime action wiring, deployment.

**Handoff Notes**

Sia owns the four files. Sentinel evidence is deferred to V1 after end-to-end integration.


---
## Milestone Tracking
<!-- ID: milestone_tracking -->
### SCRIBE-DRY-APPLY-I5

**Title:** Build receipt service, fenced replay, and deterministic multi-path locks

**Goal**

Implement server-only receipt issuance/apply orchestration independent of the public runtime router.

**Depends On**

- `SCRIBE-DRY-APPLY-I1`
- `SCRIBE-DRY-APPLY-I2`
- `SCRIBE-DRY-APPLY-I3`
- `SCRIBE-DRY-APPLY-I4`

**Files to Read**

- `src/scribe_mcp/doc_management/manager.py`
- `src/scribe_mcp/shared/write_barrier.py`
- `src/scribe_mcp/shared/tool_runtime.py`
- `tests/test_manage_docs_anchor_cas.py`
- `tests/security/test_project_binding_policy.py`

**Files to Modify**

- `src/scribe_mcp/doc_management/apply_preview.py`
- `src/scribe_mcp/doc_management/manager.py`
- `tests/test_apply_preview_engine.py`
- `tests/security/test_apply_preview_receipt_security.py`

**Files Forbidden**

Runtime router, backend implementations, server transport, dirty rehome tests, release files.

**Public Contracts / Signatures**

- `ApplyPreviewService.__init__(storage: StorageBackend, *, ttl_seconds: int = 600, max_ttl_seconds: int = 1800, claim_lease_seconds: int = 60)`
- `ApplyPreviewService.issue(*, action: str, normalized_intent: Mapping[str, object], binding: ApplyPreviewBinding, precondition: Mapping[str, object], predicted_after: Mapping[str, object]) -> ApplyPreviewAffordance`
- `ApplyPreviewService.apply(*, receipt: str, execution_context: object, executor: RetainedIntentExecutor) -> dict[str, object]`
- `document_mutation_locks(targets: Sequence[MutationLockTarget]) -> AsyncContextManager[None]`

**Implementation Constraints**

1. Generate 32 random bytes; hash with SHA-256; retain plaintext only long enough to build the issuance response.
2. Enforce 600-second default and 1800-second hard cap.
3. Receipt-only apply rejects companion mutation fields before lookup.
4. Compare verified scope before executor invocation; public agent text is attribution only.
5. Acquire canonical lock identities in lexical order and release in reverse order.
6. Terminal replay returns stored safe result with `replayed: true`; busy/recovery/storage outcomes are stable and non-mutating.
7. Redact tokens, hashes used for lookup, retained intent, and internal authority details from repr/log/error paths.

**Required Tests**

Token opacity, no plaintext persistence/logging, TTL cap, wrong scope, concurrent apply, busy, stale fence, terminal replay, crash claim recovery, storage unavailable, executor-not-called failure cases, lock-order determinism.

**Verification Commands**

- `uv run pytest -q tests/test_apply_preview_engine.py tests/security/test_apply_preview_receipt_security.py tests/test_manage_docs_anchor_cas.py tests/test_manage_docs_actor_identity.py tests/test_manage_docs_session_binding.py tests/security/test_project_binding_policy.py`
- `uv run python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewService; from scribe_mcp.doc_management.manager import document_mutation_locks'`

**Acceptance Criteria**

- [ ] Exact retained intent is the only executable payload.
- [ ] Two concurrent applies can invoke the executor at most once.
- [ ] Terminal and crash-recovery retries never duplicate mutation.
- [ ] Tokens/intent remain absent from persistence readback, logs, and errors.
- [ ] Focused tests and import smokes pass.

**Out of Scope**

Action routing, rehome side effects, backend SQL, versioning.

**Handoff Notes**

Forge owns the four files. Stop if runtime or backend files are required.

### SCRIBE-REHOME-B3

**Title:** Preserve rehome durability and integrate automatic apply-preview runtime

**Goal**

Complete the existing dirty rehome repair, route direct and receipt rehome through one composite executor, and expose the minimal public apply contract.

**Depends On**

- `SCRIBE-REHOME-B1`
- `SCRIBE-DRY-APPLY-I5`

**Files to Read**

- `src/scribe_mcp/doc_management/runtime.py`
- `src/scribe_mcp/doc_management/apply_preview.py`
- `src/scribe_mcp/tools/manage_docs.py`
- `tests/test_manage_docs_create_intent.py`
- `tests/test_manage_docs_session_binding.py`
- `tests/test_manage_docs_runtime_action_classification.py`
- `tests/test_manage_docs_schema_keystone.py`
- `tests/test_mcp_adapter.py`

**Files to Modify**

- `src/scribe_mcp/doc_management/runtime.py`
- `src/scribe_mcp/doc_management/rehome_transaction.py`
- `tests/test_manage_docs_cleanup_support.py`
- `tests/test_manage_docs_target_resolution.py`
- `tests/test_manage_docs_index_updates.py`
- `tests/test_manage_docs_apply_preview.py`

**Files Forbidden**

- `src/scribe_mcp/tools/manage_docs.py`
- all storage implementation files
- `tests/test_manage_docs_create_intent.py`
- `pyproject.toml`, `src/scribe_mcp/__main__.py`, `README.md`
- prompt, roster, skill, generated-agent, or deployment surfaces

**Public Contracts / Signatures**

- Successful eligible preview: `apply: {action: "apply_preview", receipt: str, expires_at: str}`.
- Follow-up: `manage_docs(action="apply_preview", metadata={"receipt": str})`.
- `capture_rehome_binding(...) -> RehomeCompositeBinding`
- `execute_rehome_transaction(..., receipt_fence: int | None) -> dict[str, object]`
- `recover_rehome_transaction(...) -> dict[str, object]`

**Implementation Constraints**

1. Preserve every current dirty hunk in runtime and cleanup/create-preview regression behavior; integrate surgically.
2. Add `apply_preview` through existing `VALID_ACTIONS`/manifest authority. Do not edit the host schema or client arguments.
3. Call one issuer before both the create early return and common final return; exclude failed, read-only, quality, and apply-preview responses.
4. Use one composite rehome executor for direct and retained execution.
5. Bind/recheck both authorities, paths, files, registry mappings, indexes, preimage/predicted-after state, mode, overwrite, and all deterministic locks.
6. Recognized partial crash states may complete only verified idempotent steps; OTHER returns recovery-required without mutation.
7. Current policy, write barrier, canonical path resolution, and manager CAS remain authoritative.

**Required Tests**

Existing dirty rehome/rebind/review-index and create-preview shape remain green. New tests cover automatic exposure, no-affordance actions, receipt-only input, apply once/replay, changed preimage, composite rehome scope, deterministic locks, partial recovery, and MCP host-valid result shape.

**Verification Commands**

- `uv run pytest -q tests/test_manage_docs_cleanup_support.py tests/test_manage_docs_target_resolution.py tests/test_manage_docs_index_updates.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_create_intent.py tests/test_manage_docs_session_binding.py tests/test_manage_docs_runtime_action_classification.py tests/test_manage_docs_schema_keystone.py tests/test_mcp_adapter.py tests/test_response_formatter_helpers.py`
- `uv run python -c 'from scribe_mcp.doc_management.runtime import _handle_rehome_doc, handle_manage_docs_request; from scribe_mcp.doc_management.rehome_transaction import execute_rehome_transaction'`

**Acceptance Criteria**

- [ ] Existing dirty rehome/create-preview behavior is preserved.
- [ ] Eligible previews automatically expose the exact three-field affordance.
- [ ] Apply accepts only the opaque receipt and executes once.
- [ ] Direct and receipt rehome share one composite executor.
- [ ] Source/destination file, registry, index, lock, and recovery semantics pass.
- [ ] Neighbor tests and import smokes pass.

**Out of Scope**

Storage SQL/transport, release files, prompts/skills/rosters, deployment.

**Handoff Notes**

Mantis owns the six files because this package preserves and extends the active rehome bug repair. Stop on any need to reset dirty files.

### SCRIBE-DRY-APPLY-V1

**Title:** Validate backend parity, end-to-end behavior, and mandatory security risks

**Goal**

Provide independent cross-backend and end-to-end proof for the two force-closed findings before release.

**Depends On**

- `SCRIBE-DRY-APPLY-I2`
- `SCRIBE-DRY-APPLY-I3`
- `SCRIBE-DRY-APPLY-I4`
- `SCRIBE-DRY-APPLY-I5`
- `SCRIBE-REHOME-B3`

**Files to Read**

All modified implementation files and their package tests.

**Files to Modify**

- `tests/integration/storage/test_apply_preview_backend_parity.py`
- `tests/integration/test_manage_docs_apply_preview_lifecycle.py`

**Files Forbidden**

All source, release, prompt, roster, skill, generated, Git, and deployment files.

**Public Contracts / Signatures**

No new source contract. Tests consume C-RECEIPT-STORAGE, C-APPLY-ENGINE, C-PUBLIC-APPLY, and C-REHOME-COMPOSITE unchanged.

**Implementation Constraints**

1. Run the same lifecycle assertions against SQLite and PostgreSQL; Remote must prove server-side delegation/failure parity.
2. Use real concurrency and injected crash boundaries, not mocked success-only paths.
3. Prove exactly-once mutation, terminal replay, stale-fence denial, storage fail-closed, and composite partial-crash recovery.
4. Prove tokens and retained intent absent from persistence/log/error/host content.
5. Do not modify implementation to make tests pass; return defects to the owning package.

**Required Tests**

The two owned tests plus all package-local commands listed above.

**Verification Commands**

- `uv run pytest -q tests/integration/storage/test_apply_preview_backend_parity.py tests/integration/test_manage_docs_apply_preview_lifecycle.py tests/storage/test_apply_preview_receipt_contract.py tests/storage/test_sqlite_apply_preview_receipts.py tests/integration/storage/test_postgres_apply_preview_receipts.py tests/test_remote_backend.py tests/security/test_apply_preview_remote_fail_closed.py tests/test_apply_preview_engine.py tests/security/test_apply_preview_receipt_security.py tests/test_manage_docs_apply_preview.py`
- `uv run python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewService; from scribe_mcp.doc_management.runtime import handle_manage_docs_request; from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.postgres import PostgresStorage; from scribe_mcp.storage.remote import RemoteStorageBackend'`

**Acceptance Criteria**

- [ ] One-write concurrency and terminal replay parity pass on supported backends.
- [ ] Remote fails closed and never client-emulates atomic operations.
- [ ] Composite rehome recovery passes recognized states and blocks unknown states.
- [ ] No receipt/intent leakage is observed.
- [ ] Behavioral and security evidence receipts are PASS for the current revision.

**Out of Scope**

Source fixes, release edits, full suite, deployment.

**Handoff Notes**

Crucible owns the two files and produces behavioral evidence; Sentinel produces security evidence against the same revision. No additional planning/review pass is required.

### SCRIBE-REHOME-B2

**Title:** Publish 2.14.0 source-level release truth

**Goal**

Amend the existing version package in place so the additive public action/response feature and preserved rehome fixes ship as SemVer minor 2.14.0.

**Depends On**

- `SCRIBE-REHOME-B3`
- `SCRIBE-DRY-APPLY-V1`

**Files to Read**

- `pyproject.toml`
- `src/scribe_mcp/__main__.py`
- `README.md`

**Files to Modify**

- `pyproject.toml`
- `src/scribe_mcp/__main__.py`
- `README.md`

**Files Forbidden**

All runtime, storage, tests, prompts, generated surfaces, Git remote, and deployment files.

**Public Contracts / Signatures**

`python -m scribe_mcp --version` prints `scribe-mcp 2.14.0`; package metadata and README release contract match.

**Implementation Constraints**

1. Preserve the current dirty 2.13.2 wording/history while advancing the final target to 2.14.0.
2. README names the automatic apply affordance, durable cross-backend receipt lifecycle, composite rehome recovery, and source-only status.
3. Do not claim deployment, restart, PR closeout, merge, or production activation.

**Required Tests**

Version parity and CLI output.

**Verification Commands**

- `uv run python -m scribe_mcp --version`
- `uv run python -c 'import pathlib, tomllib; data=tomllib.loads(pathlib.Path("pyproject.toml").read_text()); assert data["project"]["version"] == "2.14.0"'`
- `rg -n '2\.14\.0|apply_preview|receipt|rehome' README.md pyproject.toml src/scribe_mcp/__main__.py`

**Acceptance Criteria**

- [ ] All three version surfaces report 2.14.0.
- [ ] README accurately separates source proof from activation.
- [ ] Existing dirty release edits are preserved, not discarded.
- [ ] Verification commands pass.

**Out of Scope**

Commit, push, PR changes, merge, deployment, restart.

**Handoff Notes**

Forge owns the three files. This is the final package only after V1 passes.


---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->
### Planning decisions and operational handoff

- Repo intelligence was unavailable because active project/version scope could not be resolved; exact source reads and literal searches were used and the limitation is logged.
- The absent fresh-process RI probe was not replaced by a guessed path.
- `SCRIBE-REHOME-B3` and `SCRIBE-REHOME-B2` are existing queued registry rows. Their contracts are amended in place to prevent duplicate runtime/release ownership. The orchestrator must use current lifecycle diagnostics and the sanctioned queued-row repair before dispatch.
- No new package owns `runtime.py` or the release trio in parallel with B3/B2.
- First clean frontier package after manifest import is `SCRIBE-DRY-APPLY-I1`, routed to Sia.
- Planning is complete in one pass; implementation begins through the imported manifest, not another Blueprint or reviewer cycle.


---