# WORK_ITEMS

```json
{
  "v": 1,
  "project": "scribe_binding_reliability_repair_20260927",
  "generated_by": "work_sync.render_manifest_projection",
  "generated_at": "2026-09-27T10:13:19.561404+00:00",
  "projection_digest": "42fe555edf269c54aecaa91acaf7db159730d26925daa7faba3b82848c4d4a48",
  "items": [
    {
      "package_id": "SBR-BIND-PERSIST.1",
      "title": "SBR BIND PERSIST.1",
      "goal": "Add the single shared binding record and freeze migration 007's SS-01 input.",
      "owned_files": [
        "src/scribe_mcp/storage/models.py",
        "tests/storage/test_session_storage_invariants.py"
      ],
      "verification": [
        "./.venv/bin/python -c 'from scribe_mcp.storage.models import SessionBindingRecordV2; print(SessionBindingRecordV2.__name__)'",
        "./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_sqlite_session_linkage_invariants -q"
      ],
      "acceptance": [
        "Exact six fields/types; invalid generation/naive timestamp fail.",
        "C-05 input is sufficient for SS-04 without DDL authority here.",
        "No Council/persona/agent authority field.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-PLAN-SYNTH-12"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-PERSIST.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 1,
      "suggested_specialist": "forge",
      "contracts": [
        "`SessionBindingRecordV2(caller_session_key_hash: str, project_key: str, project_name: str, canonical_repo_root: str, binding_generation: int, updated_at: datetime)`.",
        "First generation is `1`; generation is at least 1; timestamp is timezone-aware."
      ],
      "status": "in_progress"
    },
    {
      "package_id": "SBR-BIND-RESOLVE.1",
      "title": "SBR BIND RESOLVE.1",
      "goal": "Define C-02/C-03/C-11 data contracts and the one builder that keeps agent labels attribution-only. This package does not resolve or persist a project.",
      "owned_files": [
        "src/scribe_mcp/shared/execution_context.py",
        "tests/test_execution_context.py",
        "tests/shared/test_actor_scoped_session_binding.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.execution_context import AgentAttributionV1, AuthorizationEvidenceV1, BindingReceiptV1, ProjectTargetV1, ResolvedProjectTargetV1, ResolvedRequestContextV1, build_resolved_request_context'",
        "./.venv/bin/pytest -q tests/test_execution_context.py tests/shared/test_actor_scoped_session_binding.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/security/test_session_provenance.py"
      ],
      "acceptance": [
        "C-02/C-03/C-11 names and fields are importable, frozen, validated, and contain no raw caller-session key.",
        "Same-label callers cannot collide; changing attribution cannot change caller identity, default, target, or authorization.",
        "One `ResolvedRequestContextV1` instance can be passed end to end without mutation or re-resolution.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-PLAN-SYNTH-12"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-RESOLVE.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 1,
      "suggested_specialist": "forge",
      "contracts": [
        "`ProjectTargetV1(project_key: str | None = None, project: str | None = None, repo_root: str | None = None)`.",
        "`ResolvedProjectTargetV1(project_key: str, project_name: str, canonical_repo_root: str, repository_id: str, resolution_source: Literal[\"project_key\", \"name_and_root\", \"unique_name\", \"caller_default\"], default_binding_generation: int)`.",
        "`AgentAttributionV1(agent: str, agent_id: str | None = None)`; neither field participates in equality/keying for caller identity or target selection.",
        "`AuthorizationEvidenceV1(source: str, verified: bool, scope_refs: tuple[str, ...])`; values are opaque evidence references, never credentials.",
        "`BindingReceiptV1(ok: bool, caller_session_key_hash: str, project_key: str, project_name: str, canonical_repo_root: str, binding_generation: int, binding_reused: bool, persistent_write_performed: bool, resolution_source: str, correlation_id: str)`.",
        "`ResolvedRequestContextV1(caller_session_key_hash: str, resolved_target: ResolvedProjectTargetV1, default_binding_generation: int, agent_attribution: AgentAttributionV1, correlation_id: str, operating_mode: Literal[\"project\", \"sentinel\"], authorization_evidence: AuthorizationEvidenceV1)`.",
        "`build_resolved_request_context(*, caller_session_key: str, resolved_target: ResolvedProjectTargetV1, agent_attribution: AgentAttributionV1, correlation_id: str, operating_mode: Literal[\"project\", \"sentinel\"], authorization_evidence: AuthorizationEvidenceV1) -> ResolvedRequestContextV1`.",
        "`ExecutionContext.resolved_request_context: ResolvedRequestContextV1 | None`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-STARTUP.1",
      "title": "SBR STARTUP.1",
      "goal": "Remove the eager `utils -> response -> tokens -> tiktoken encoder` import chain while preserving all existing utility exports, cheap estimation, accurate counting on demand, token metrics, and budget behavior.",
      "owned_files": [
        "src/scribe_mcp/utils/__init__.py",
        "src/scribe_mcp/utils/tokens.py",
        "tests/test_estimator.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'import sys; import scribe_mcp.server; assert \"tiktoken\" not in sys.modules; from scribe_mcp.utils.tokens import TokenEstimator, token_estimator; assert token_estimator.encoder is None; assert TokenEstimator().estimate_tokens_cheap(\"abcd\") == 1'",
        "./.venv/bin/pytest -q tests/test_estimator.py::TestTokenEstimator",
        "./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_server_import_is_token_lazy_and_filesystem_pure tests/test_release_startup_probe.py::test_server_import_and_all_tools_loaded_meet_time_and_rss_budgets",
        "for i in 1 2 3 4 5; do /usr/bin/time -f \"run=$i elapsed_s=%e maxrss_kb=%M\" ./.venv/bin/python -c 'import scribe_mcp.server'; done"
      ],
      "acceptance": [
        "Importing `scribe_mcp.server` or `scribe_mcp.utils.tokens` performs zero metrics-path writes and leaves tiktoken/encoder unloaded.",
        "Cheap estimation is deterministic and encoder-free; the first exact request initializes one reusable encoder and preserves fallback behavior.",
        "The existing `scribe_mcp.utils` export names and token metrics/budget result shapes remain compatible.",
        "DA-10 evidence proves warm import p95 at most 1.0 s, cold import p95 at most 1.5 s, pre-tool-ready RSS at most 64 MiB, and all-tools-loaded steady RSS at most 80 MiB.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-PLAN-SYNTH-12"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-STARTUP.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 1,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve `TokenEstimator.__init__(self, model: str = \"gpt-4\", daily_limit: int = 100000, operation_limit: int = 8000)`.",
        "Preserve the one-positional-argument call and add only the backward-compatible selector `TokenEstimator.estimate_tokens(self, data: Union[str, Dict, List, Any], *, exact: bool = True) -> int`.",
        "Add `TokenEstimator.estimate_tokens_cheap(self, data: Union[str, Dict, List, Any]) -> int`; it must never import tiktoken.",
        "Preserve `TokenEstimator.estimate_response_tokens`, `record_operation`, `get_usage_stats`, `get_tokenizer_info`, `save_metrics`, and `load_metrics`.",
        "Preserve `token_estimator: TokenEstimator` and the current `scribe_mcp.utils.__all__` names. Add module `__getattr__(name: str) -> Any` only as the lazy compatibility seam."
      ],
      "status": "in_progress"
    },
    {
      "package_id": "SBR-STARTUP.2",
      "title": "SBR STARTUP.2",
      "goal": "Separate remote-client construction from remote availability probing so a configured or unavailable CortaStore cannot delay core readiness, while preserving local-first durability and existing remote operations.",
      "owned_files": [
        "src/scribe_mcp/object_store/hybrid.py",
        "src/scribe_mcp/object_store/providers/corta.py",
        "tests/test_object_store_hybrid.py",
        "tests/test_object_store_providers.py",
        "tests/test_release_startup_probe.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.object_store.hybrid import HybridStore; from scribe_mcp.object_store.providers.corta import CortaStoreProvider; assert callable(HybridStore.probe_remote_health); assert callable(CortaStoreProvider.probe_health)'",
        "./.venv/bin/pytest -q tests/test_object_store_hybrid.py",
        "./.venv/bin/pytest -q tests/test_object_store_providers.py",
        "./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_optional_object_store_probe_is_not_in_foreground_startup tests/test_release_startup_probe.py::test_optional_object_store_outage_adds_at_most_50_ms_and_preserves_local_durability"
      ],
      "acceptance": [
        "Provider/store setup performs zero remote health I/O and remains close-idempotent.",
        "The explicit health probe is one bounded request with boolean/unsupported truth and cancellation safety.",
        "Local-first document persistence and every existing remote operation remain behaviorally compatible.",
        "DA-10 evidence proves an optional outage adds at most 50 ms to foreground startup and cannot block core tool listing or local durable logging.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-PLAN-SYNTH-12"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-STARTUP.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "src/scribe_mcp/object_store/base.py"
      ],
      "wave": 1,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve `HybridStore.setup(self) -> None`, `close`, and all `DocumentStore` methods.",
        "Add `HybridStore.probe_remote_health(self, *, timeout_seconds: float = 2.0) -> bool | None`; `None` means the configured provider exposes no probe.",
        "Preserve `CortaStoreProvider.setup(self) -> None` and `close`.",
        "Add `CortaStoreProvider.probe_health(self, *, timeout_seconds: float = 2.0) -> bool`."
      ],
      "status": "in_progress"
    },
    {
      "package_id": "SBR-BIND-PERSIST.2",
      "title": "Abstract generation/CAS contract",
      "goal": "Replace the name-only abstract methods with frozen C-01 idempotency and CAS semantics.",
      "owned_files": [
        "src/scribe_mcp/storage/base.py"
      ],
      "verification": [
        "./.venv/bin/python -c 'from scribe_mcp.storage.base import StorageBackend; from scribe_mcp.storage.models import SessionBindingRecordV2; print(StorageBackend.set_session_project.__name__)'"
      ],
      "acceptance": [
        "Exact C-01 signatures and backend-neutral first/change/no-op/stale behavior.",
        "Expected failures remain storage conflicts, not MCP envelopes.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-PERSIST.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 2,
      "suggested_specialist": "forge",
      "contracts": [
        "`async set_session_project(self, session_id: str, project_key: str, expected_generation: int | None = None) -> SessionBindingRecordV2`.",
        "`async get_session_project(self, session_id: str) -> SessionBindingRecordV2 | None`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-PERSIST.5",
      "title": "Remote durable transport parity",
      "goal": "Use existing authenticated backend transport for C-01; local process map is never authoritative binding truth.",
      "owned_files": [
        "src/scribe_mcp/storage/remote.py"
      ],
      "verification": [
        "./.venv/bin/python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; print(RemoteStorageBackend.set_session_project.__name__)'",
        "./.venv/bin/pytest -s tests/test_remote_backend.py::TestSessionMethods::test_session_project_get_set -q",
        "./.venv/bin/pytest -s tests/core/test_swarm_binding_reliability.py -q"
      ],
      "acceptance": [
        "Exact record and backend generation/CAS/no-write outcomes.",
        "Restart/reconnect cannot replace durable truth with empty cache.",
        "Same-label sessions partition only by session key.",
        "Test ownership conflict resolved before Forge starts.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1",
        "SBR-BIND-PERSIST.2",
        "SBR-ARCH-AMEND-REMOTE-08"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-PERSIST.5",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 3,
      "suggested_specialist": "forge",
      "contracts": [
        "Exact C-01 methods; payload/response uses the six record field names."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-RECEIPT.1",
      "title": "Host-neutral receipt models and storage contract",
      "goal": "Define the closed receipt state machine, typed outcomes, façade, and backend contract once. This package owns no persistence SQL.",
      "owned_files": [
        "src/scribe_mcp/background/models.py",
        "src/scribe_mcp/background/store.py",
        "src/scribe_mcp/storage/base.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.models import BackgroundAdmissionResultV1, BackgroundOperationIntentV1, BackgroundQueueLimitsV1, BackgroundRecoverySnapshotV1, BackgroundTransitionOutcomeV1, DurableOperationReceiptV1; from scribe_mcp.background.store import BackgroundReceiptStoreV1; from scribe_mcp.storage.base import StorageBackend'",
        "./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py",
        "./.venv/bin/pytest -q tests/storage/test_apply_preview_receipt_contract.py tests/test_storage_factory_backends.py"
      ],
      "acceptance": [
        "C-08 public names and signatures are importable and host-neutral.",
        "Closed states, version/fence invariants, terminal immutability, and recovery accounting are enforced by models plus façade/backend contract.",
        "Unsupported backends fail closed; no fallback to memory or apply-preview storage exists.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-RECEIPT.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "src/scribe_mcp/storage/models.py"
      ],
      "wave": 3,
      "suggested_specialist": "forge",
      "contracts": [
        "`BackgroundReceiptState = Literal[\"accepted\", \"ready\", \"leased\", \"retry_wait\", \"succeeded\", \"failed_terminal\", \"cancelled\"]`.",
        "`BackgroundLane = Literal[\"control\", \"durable\", \"heavy\"]`.",
        "`BackgroundOperationIntentV1(operation_id: str, canonical_project_key: str, lane: BackgroundLane, idempotency_key: str, payload_digest: str, payload_bytes: int, durability_class: str, created_at: datetime)`.",
        "`BackgroundQueueLimitsV1(max_pending_items: int, max_pending_bytes: int, max_project_pending_items: int, max_project_pending_bytes: int, retry_after_ms: int, accepting: bool = True)`.",
        "`DurableOperationReceiptV1(operation_id: str, canonical_project_key: str, lane: BackgroundLane, idempotency_key: str, payload_digest: str, payload_bytes: int, durability_class: str, state: BackgroundReceiptState, state_version: int, attempt_count: int, next_attempt_at: datetime | None, lease_owner: str | None, lease_expires_at: datetime | None, fencing_token: int, cancel_requested: bool, result_ref: str | None, error_code: str | None, created_at: datetime, updated_at: datetime)`.",
        "`BackgroundAdmissionResultV1(status: Literal[\"accepted\", \"duplicate\", \"digest_conflict\", \"busy\", \"shutting_down\"], receipt: DurableOperationReceiptV1 | None, retry_after_ms: int | None)`.",
        "`BackgroundPartitionV1(canonical_project_key: str, lane: BackgroundLane)`.",
        "`BackgroundTransitionOutcomeV1(state: BackgroundReceiptState, next_attempt_at: datetime | None = None, cancel_requested: bool = False, result_ref: str | None = None, error_code: str | None = None)`.",
        "`BackgroundRecoverySnapshotV1(receipts: tuple[DurableOperationReceiptV1, ...], pending_items: int, pending_bytes: int, reclaimable_operation_ids: tuple[str, ...])`.",
        "`BackgroundReceiptNotFoundError`, `BackgroundStateVersionConflictError`, and `BackgroundStaleFenceError` are the only transition exceptions; admission uses `BackgroundAdmissionResultV1`, never exceptions for duplicate/conflict/busy/shutdown.",
        "`BackgroundReceiptStoreV1.__init__(backend: StorageBackend, *, clock: Callable[[], datetime]) -> None`.",
        "`BackgroundReceiptStoreV1.admit(intent: BackgroundOperationIntentV1, limits: BackgroundQueueLimitsV1) -> BackgroundAdmissionResultV1`.",
        "`BackgroundReceiptStoreV1.get(operation_id: str) -> DurableOperationReceiptV1 | None`.",
        "`BackgroundReceiptStoreV1.claim(partition: BackgroundPartitionV1, worker_id: str, lease_ms: int) -> DurableOperationReceiptV1 | None`.",
        "`BackgroundReceiptStoreV1.transition(operation_id: str, expected_state_version: int, fencing_token: int, outcome: BackgroundTransitionOutcomeV1) -> DurableOperationReceiptV1`.",
        "`BackgroundReceiptStoreV1.recover(now: datetime) -> BackgroundRecoverySnapshotV1`.",
        "`StorageBackend` adds matching `admit_background_receipt(..., now)`, `get_background_receipt(...)`, `claim_background_receipt(..., now)`, `transition_background_receipt(..., now)`, and `recover_background_receipts(now)` async methods; defaults raise `NotImplementedError` exactly as apply-preview storage does."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-DOC-DUR.1",
      "title": "Idempotent WAL and atomic document-write substrate",
      "goal": "Extend the existing `WriteAheadLog` and atomic-write primitives so a normalized managed-document intent can be journaled by stable operation ID, inspected after restart, and committed exactly once without changing append-log behavior.",
      "owned_files": [
        "src/scribe_mcp/utils/files.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.utils.files import WriteAheadLog, WalEntryConflictError, WalJournalCorruptError, atomic_write, async_atomic_write'",
        "./.venv/bin/pytest -q tests/test_multi_repo_file_ops.py tests/test_write_barrier_contract.py",
        "./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py -m \"core and regression and not slow and not performance\""
      ],
      "acceptance": [
        "Stable same-digest admission is idempotent; same-ID/different-digest admission is effect-free conflict.",
        "Every accepted document journal row survives restart, and repeated replay produces exactly one atomic file effect and one commit marker.",
        "Legacy append WAL, atomic-write durability, sandbox enforcement, and object-store non-authority are unchanged.",
        "No queue, worker, registry, index, quality, or second mutation abstraction exists in `files.py`.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-RECEIPT.1"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DOC-DUR.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 4,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve `WriteAheadLog.__init__(log_path: str | Path, repo_root: Path | None = None, context: dict[str, Any] | None = None)`.",
        "Extend compatibly to `WriteAheadLog.write_entry(entry: Mapping[str, Any], *, entry_id: str | None = None) -> str`; callers that omit `entry_id` keep the existing generated-ID behavior.",
        "Add `WriteAheadLog.read_uncommitted(*, operation_kind: str | None = None) -> tuple[dict[str, Any], ...]`.",
        "Add `WriteAheadLog.has_commit(entry_id: str) -> bool`.",
        "Preserve `WriteAheadLog.commit_entry(entry_id: str) -> None` and `WriteAheadLog.replay_uncommitted() -> int`; the latter remains the legacy append-log replay surface and must not become the document mutation worker.",
        "Add `WalEntryConflictError(AtomicFileError)` and `WalJournalCorruptError(AtomicFileError)`.",
        "Preserve `atomic_write(...) -> None`, `async_atomic_write(...) -> None`, `append_line(...) -> None`, and `_write_line_with_wal(...) -> None`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-SCHEMA.1",
      "title": "Migration 007 reliability upgrade",
      "goal": "Create the sole numbered PostgreSQL upgrade that materializes C-05, C-06, and the readiness record required by C-07 without changing runtime receipt behavior.",
      "owned_files": [
        "src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from pathlib import Path; p=Path(\"src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql\"); assert p.is_file() and p.read_text(encoding=\"utf-8\").strip()'",
        "./.venv/bin/pytest -q tests/test_bootstrap_postgres_script.py tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py",
        "./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py::test_migration_007_reliability_receipts_upgrade_and_restore tests/migration/mcp_v2/test_compatibility_matrix.py::test_migration_007_refuses_ambiguous_binding_backfill_without_ledger_write (after DA-10 owns the tests)",
        "On an approved disposable target only, run separately and retain redacted receipts:",
        "agentkit-schema status --redacted-json",
        "agentkit-schema plan --write-plan --backup-profile auto --redacted-json",
        "agentkit-schema backup create --label sbr-007-preapply",
        "agentkit-schema apply --backup-profile auto --redacted-json"
      ],
      "acceptance": [
        "One migration file supplies C-05/C-06 plus readiness metadata; migration identity is 007 and ledger records exactly once.",
        "Legacy bindings backfill to canonical project_key/generation 1 or fail atomically on missing/ambiguous identity.",
        "Receipt constraints, uniqueness, indexes, and state-nullability enforce the frozen C-06 shape.",
        "Second apply is a no-op with zero ledger drift; backup restore proves rollback compatibility without destructive down SQL.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1",
        "SBR-RECEIPT.1"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-SCHEMA.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 4,
      "suggested_specialist": "forge",
      "contracts": [
        "Ledger identity is exactly sql:007_reliability_receipts.sql in scribe_migrations.",
        "session_projects retains session_id PRIMARY KEY and project_name; adds project_key TEXT and binding_generation BIGINT with generation >= 1.",
        "background_receipts persists exactly: operation_id, canonical_project_key, lane, idempotency_key, payload_digest, payload_bytes, durability_class, state, state_version, attempt_count, next_attempt_at, lease_owner, lease_expires_at, fencing_token, cancel_requested, result_ref, error_code, created_at, updated_at.",
        "background_receipts has PRIMARY KEY (operation_id) and UNIQUE (canonical_project_key, idempotency_key).",
        "scribe_schema_readiness is a singleton readiness record with schema_fingerprint, migration_version, and updated_at; it is coordination metadata, never the migration ledger."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-SCHEMA.2",
      "title": "Fresh and legacy SQLite/PostgreSQL baseline parity",
      "goal": "Make fresh PostgreSQL init and SQLite creation/upgrade materialize the same C-05/C-06 logical schema as migration 007.",
      "owned_files": [
        "src/scribe_mcp/storage/sqlite/schema.py",
        "src/scribe_mcp/db/init.sql"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.sqlite.schema import create_background_receipt_tables, ensure_reliability_schema; from scribe_mcp.storage.postgres.schema import SCHEMA_PATH'",
        "./.venv/bin/pytest -q tests/storage/test_session_storage_invariants.py tests/storage/test_sqlite_apply_preview_receipts.py tests/test_bootstrap_postgres_script.py",
        "./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py::test_sqlite_reliability_schema_upgrades_legacy_binding_without_default_drift tests/core/test_background_queue_contract.py::test_sqlite_background_receipt_schema_enforces_c06 (after DA-09 owns the tests)",
        "./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py::test_reliability_schema_postgres_sqlite_init_parity (after DA-10 owns the test)"
      ],
      "acceptance": [
        "Fresh PostgreSQL, fresh SQLite, and legacy SQLite upgrade expose one logical C-05/C-06 schema.",
        "Fresh init plus migration 007 is idempotent; reopening SQLite is non-destructive and preserves existing bindings/receipts.",
        "Compatibility project_name remains readable while project_key/generation are authoritative for new binding behavior.",
        "Schema modules import without database/filesystem side effects.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-SCHEMA.1"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-SCHEMA.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 5,
      "suggested_specialist": "forge",
      "contracts": [
        "async def ensure_reliability_schema(execute_fn: ExecuteFn, execute_many_fn: ExecuteManyFn) -> None.",
        "async def create_background_receipt_tables(execute_many_fn: ExecuteManyFn) -> None.",
        "create_schema(...) invokes ensure_reliability_schema exactly once before create_all_indexes.",
        "Fresh init.sql and SQLite schema expose the same C-05/C-06 column names, state domain, uniqueness, and logical defaults; backend-specific types are limited to TIMESTAMPTZ/JSONB/BOOLEAN versus TEXT/INTEGER representations."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-PERSIST.4",
      "title": "SQLite parity and facade",
      "goal": "Match PostgreSQL behavior while preserving SQLite's write lock and session guard.",
      "owned_files": [
        "src/scribe_mcp/storage/sqlite/sessions.py",
        "src/scribe_mcp/storage/sqlite/domain_facade.py"
      ],
      "verification": [
        "./.venv/bin/python -c 'from scribe_mcp.storage.sqlite.domain_facade import SQLiteDomainFacadeMixin; from scribe_mcp.storage.sqlite import sessions; print(SQLiteDomainFacadeMixin.set_session_project.__name__, sessions.set_session_project.__name__)'",
        "./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_sqlite_session_linkage_invariants -q",
        "./.venv/bin/pytest -s tests/integration/storage/test_storage_backend_shared_contract.py::test_session_transport_mode_project_and_scoped_reuse_contract -q"
      ],
      "acceptance": [
        "Record, generation, no-op, conflict, and same-label isolation equal PostgreSQL.",
        "Unchanged bind calls no writer; unknown-session conflict remains.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1",
        "SBR-BIND-PERSIST.2",
        "SBR-SCHEMA.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-PERSIST.4",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 6,
      "suggested_specialist": "forge",
      "contracts": [
        "Facade exposes exact C-01; helpers keep injected initialize/read/write collaborators and return typed records."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-RECEIPT.2",
      "title": "SQLite atomic receipt persistence",
      "goal": "Implement SQLite admission, lookup, fenced claim/transition, and restart reconstruction behind the shared contract, using the existing SQLite locking/WAL helpers.",
      "owned_files": [
        "src/scribe_mcp/storage/sqlite/background_receipts.py",
        "src/scribe_mcp/storage/sqlite/__init__.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.sqlite.background_receipts import admit_background_receipt, claim_background_receipt, get_background_receipt, recover_background_receipts, transition_background_receipt'",
        "./.venv/bin/pytest -q tests/storage/test_sqlite_background_receipts.py",
        "./.venv/bin/pytest -q tests/storage/test_sqlite_apply_preview_receipts.py tests/integration/storage/test_storage_backend_shared_contract.py"
      ],
      "acceptance": [
        "SQLite never exceeds configured global/per-project item or byte limits, including under 32 concurrent admissions.",
        "Duplicate, digest-conflict, busy, and shutdown outcomes create no hidden row or capacity drift.",
        "State versions and fencing reject stale writers; fresh reopen reconstructs every accepted nonterminal receipt and exact capacity.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-RECEIPT.1",
        "SBR-SCHEMA.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-RECEIPT.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "src/scribe_mcp/storage/sqlite/internals.py"
      ],
      "wave": 6,
      "suggested_specialist": "forge",
      "contracts": [
        "`SQLiteStorage.admit_background_receipt(intent, limits, *, now) -> BackgroundAdmissionResultV1`.",
        "`SQLiteStorage.get_background_receipt(operation_id) -> DurableOperationReceiptV1 | None`.",
        "`SQLiteStorage.claim_background_receipt(partition, worker_id, lease_ms, *, now) -> DurableOperationReceiptV1 | None`.",
        "`SQLiteStorage.transition_background_receipt(operation_id, expected_state_version, fencing_token, outcome, *, now) -> DurableOperationReceiptV1`.",
        "`SQLiteStorage.recover_background_receipts(now) -> BackgroundRecoverySnapshotV1`.",
        "Module functions in `background_receipts.py` use keyword-only injected `initialise_fn`, existing SQLite query callbacks/lock, the same contract arguments, and the same return types; no second backend class."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-SCHEMA.3",
      "title": "Fingerprinted elected bootstrap and bounded readiness",
      "goal": "Replace repeated/unbounded startup DDL with one fingerprint fast check, one elected bootstrapper, bounded peer readiness, and the exact frozen C-07 result.",
      "owned_files": [
        "src/scribe_mcp/storage/postgres/schema.py",
        "src/scribe_mcp/storage/postgres/internals.py",
        "src/scribe_mcp/storage/postgres/__init__.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.postgres.schema import SchemaReadinessV1, ensure_schema, ensure_schema_ready; from scribe_mcp.storage.postgres.internals import PostgresInternals; from scribe_mcp.storage.postgres import PostgresStorage'",
        "./.venv/bin/pytest -q tests/test_bootstrap_postgres_script.py tests/test_postgres_project_identity_scoping.py",
        "./.venv/bin/pytest -q tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py",
        "./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py::test_schema_bootstrap_32_simultaneous_starts_one_elected_bootstrapper tests/integration/test_swarm_concurrency_stress.py::test_schema_fingerprint_mismatch_fails_closed_without_ledger_write tests/integration/test_swarm_concurrency_stress.py::test_schema_peer_deadline_is_bounded_and_retryable (single repository-saturating PostgreSQL/process lane; only after DA-10 owns the test file)"
      ],
      "acceptance": [
        "C-07 exact fields and signatures are importable; setup remains compatible and fails closed before identity repair on non-ready results.",
        "Warm matching startup performs one fast read, zero writes/DDL, and meets the <=100 ms p95 target.",
        "Thirty-two simultaneous starts elect exactly one DDL bootstrapper; peers wait <=500 ms, observe one fingerprint/version, and create zero ledger drift.",
        "Fingerprint mismatch, owner failure, connection exhaustion, and deadline expiry return typed bounded truth with no unbounded wait, secret leakage, or compatibility overwrite.",
        "Existing setup/bootstrap neighbors and import smoke pass.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-SCHEMA.1",
        "SBR-SCHEMA.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-SCHEMA.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 6,
      "suggested_specialist": "forge",
      "contracts": [
        "SchemaBootstrapRole = Literal[\"fast_path\", \"bootstrapper\", \"peer\"].",
        "SchemaReadinessErrorCode = Literal[\"SCHEMA_FINGERPRINT_MISMATCH\", \"SCHEMA_BOOTSTRAP_TIMEOUT\", \"SCHEMA_BOOTSTRAP_FAILED\", \"SCHEMA_STORAGE_UNAVAILABLE\"].",
        "SchemaReadinessV1(schema_fingerprint: str, migration_version: str, bootstrap_role: SchemaBootstrapRole, wait_ms: int, ready: bool, error_code: SchemaReadinessErrorCode | None, retryable: bool).",
        "async def ensure_schema_ready(*, pool_provider: Callable[..., Awaitable[asyncpg.Pool]], schema_lock: asyncio.Lock, schema_name: str, deadline_ms: int, schema_path: Path = SCHEMA_PATH, migrations_path: Path = MIGRATIONS_PATH) -> SchemaReadinessV1.",
        "PostgresInternals.ensure_pool(self, *, deadline_ms: int | None = None) -> asyncpg.Pool; no-argument callers remain compatible.",
        "PostgresStorage.ensure_schema_ready(self, deadline_ms: int) -> SchemaReadinessV1.",
        "PostgresStorage.setup(self) -> None remains public-compatible, calls ensure_schema_ready(deadline_ms=2500), raises one typed SchemaReadinessError when ready is false, and only then runs existing repo-scoped identity repair.",
        "Existing ensure_schema(...) -> bool remains a compatibility wrapper over ensure_schema_ready for current bootstrap callers/tests; it must not restore unbounded blocking."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-PERSIST.3",
      "title": "PostgreSQL atomic persistence",
      "goal": "Implement atomic PostgreSQL generation, CAS, and zero-write no-op behavior.",
      "owned_files": [
        "src/scribe_mcp/storage/postgres/__init__.py"
      ],
      "verification": [
        "./.venv/bin/python -c 'from scribe_mcp.storage.postgres import PostgresStorage; print(PostgresStorage.set_session_project.__name__)'",
        "./.venv/bin/pytest -s tests/storage/test_session_storage_invariants.py::test_postgres_session_linkage_invariants -q",
        "./.venv/bin/pytest -s tests/integration/storage/test_storage_backend_shared_contract.py::test_session_transport_mode_project_and_scoped_reuse_contract -q"
      ],
      "acceptance": [
        "First/change/no-op/stale outcomes match C-01.",
        "No-op has zero write and stable timestamp.",
        "Session ID alone isolates same-label callers.",
        "Record identity comes from persisted project.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1",
        "SBR-BIND-PERSIST.2",
        "SBR-SCHEMA.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-PERSIST.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "tests/paths"
      ],
      "wave": 7,
      "suggested_specialist": "forge",
      "contracts": [
        "Implement both package-2 C-01 methods exactly."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-REL-VAL.1",
      "title": "Disposable PostgreSQL reference fixture",
      "goal": "Provide an SS-10-only PostgreSQL fixture that creates and drops a uniquely named disposable database, refuses production/shared-state fallbacks, and exposes sanitized environment facts to the reference runner.",
      "owned_files": [
        "tests/integration/storage/conftest.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -m py_compile tests/integration/storage/conftest.py",
        "SCRIBE_SWARM_DISPOSABLE=1 PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/storage/test_postgres_schema_bootstrap_concurrency.py -m postgres"
      ],
      "acceptance": [
        "The reference fixture cannot use a production/configured DSN or silently fall back to a shared database.",
        "Every run creates and drops one uniquely named disposable database and returns only sanitized environment metadata.",
        "Failure and cancellation leave no owned database, connection, or credential-bearing artifact.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-SCHEMA.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-REL-VAL.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 7,
      "suggested_specialist": "crucible",
      "contracts": [
        "`validate_disposable_postgres_dsn(dsn: str, *, allow_hosts: Collection[str]) -> SanitizedPostgresTarget`",
        "`swarm_postgres_backend(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[PostgresReferenceFixture]`",
        "`PostgresReferenceFixture` exposes the ephemeral DSN only in process memory plus `database_name`, sanitized host/port/database labels, PostgreSQL version, config fingerprint, and async cleanup; it never serializes user, password, query secrets, or the raw DSN."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-RESOLVE.2",
      "title": "Registered project target resolution and default preservation",
      "goal": "Implement the single C-02 resolver over persisted project identity and C-01 default truth, including authorized cross-repository targets and fail-closed ambiguity.",
      "owned_files": [
        "src/scribe_mcp/shared/logging_utils.py",
        "src/scribe_mcp/state/manager.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.logging_utils import ProjectResolutionError, resolve_project_target; from scribe_mcp.state.manager import StateManager'",
        "./.venv/bin/pytest -q tests/test_logging_utils.py tests/test_append_entry_explicit_project_resolution.py tests/test_query_entries_explicit_project_resolution.py tests/security/test_project_binding_policy.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py"
      ],
      "acceptance": [
        "Explicit targeting reaches any authorized registered project, including another repository, without `set_project` and without default mutation.",
        "Project-key/name-root/unique-name/default precedence is deterministic; ambiguity, missing, root mismatch, and wrong-target requests fail closed with stable candidates and zero effects.",
        "Agent/persona labels, recents, process globals, and ambient roots never select an operational target.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-PERSIST.3",
        "SBR-BIND-PERSIST.4",
        "SBR-BIND-PERSIST.5"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-RESOLVE.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 8,
      "suggested_specialist": "forge",
      "contracts": [
        "`async resolve_project_target(caller_session_key: str, target: ProjectTargetV1 | None) -> ResolvedProjectTargetV1`.",
        "`StateManager.resolve_registered_project(*, project_key: str | None = None, project: str | None = None, repo_root: str | None = None) -> tuple[dict[str, Any] | None, tuple[dict[str, str], ...]]`.",
        "`ProjectResolutionError(message: str, *, error_code: str, target: ProjectTargetV1 | None, candidates: tuple[dict[str, str], ...] = (), remediation: str | None = None, retryable: bool = False)`.",
        "`resolve_logging_context(..., resolved_request_context: ResolvedRequestContextV1 | None = None, explicit_project: str | None = None, ...) -> LoggingContext`; the compatibility string is converted to `ProjectTargetV1(project=...)` once."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-RECEIPT.3",
      "title": "PostgreSQL atomic persistence and backend parity",
      "goal": "Implement the same receipt semantics on PostgreSQL with transaction-safe capacity admission and multi-worker fenced claiming.",
      "owned_files": [
        "src/scribe_mcp/storage/postgres/__init__.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.postgres import PostgresStorage'",
        "./.venv/bin/pytest -q tests/integration/storage/test_postgres_background_receipts.py tests/integration/storage/test_background_receipt_backend_parity.py",
        "./.venv/bin/pytest -q tests/integration/storage/test_postgres_apply_preview_receipts.py tests/integration/storage/test_apply_preview_backend_parity.py"
      ],
      "acceptance": [
        "PostgreSQL atomically enforces the same global/per-project item and byte limits as SQLite under concurrent processes.",
        "One eligible receipt has at most one active lease; expired leases reclaim with a higher fence and stale completions cannot transition.",
        "Normalized admission, receipt, transition, and recovery results are backend-identical for the parity corpus.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-RECEIPT.1",
        "SBR-RECEIPT.2",
        "SBR-SCHEMA.2",
        "SBR-BIND-PERSIST.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-RECEIPT.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 8,
      "suggested_specialist": "forge",
      "contracts": [
        "`PostgresStorage.admit_background_receipt(intent, limits, *, now) -> BackgroundAdmissionResultV1`.",
        "`PostgresStorage.get_background_receipt(operation_id) -> DurableOperationReceiptV1 | None`.",
        "`PostgresStorage.claim_background_receipt(partition, worker_id, lease_ms, *, now) -> DurableOperationReceiptV1 | None`.",
        "`PostgresStorage.transition_background_receipt(operation_id, expected_state_version, fencing_token, outcome, *, now) -> DurableOperationReceiptV1`.",
        "`PostgresStorage.recover_background_receipts(now) -> BackgroundRecoverySnapshotV1`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BG.1",
      "title": "Canonical partition and lane-fair scheduler",
      "goal": "Add the deterministic two-level deficit-round-robin scheduler that chooses eligible C-08 partitions without owning persistence, effects, workers, or server lifecycle.",
      "owned_files": [
        "src/scribe_mcp/background/scheduler.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.scheduler import BackgroundSchedulerConfigV1, BackgroundSchedulerMetricsV1, BackgroundSchedulerV1'",
        "./.venv/bin/pytest -q tests/core/test_background_queue_contract.py -m \"core and regression and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py"
      ],
      "acceptance": [
        "Control, durable, and heavy lane reserves plus global/per-project caps hold at every scheduler checkpoint.",
        "Canonical partitions receive deterministic DRR service with no HOL, no 5-second starvation, at most one unit-job lead, and at most 50 percent share while a peer remains eligible.",
        "Item, byte, and concurrency high-water marks never exceed configuration; metrics remain bounded-cardinality and host-neutral.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-RECEIPT.1",
        "SBR-RECEIPT.2",
        "SBR-RECEIPT.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BG.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 9,
      "suggested_specialist": "forge",
      "contracts": [
        "`BackgroundSchedulerConfigV1(global_concurrency: int, max_project_concurrency: int, control_reserved_slots: int, durable_reserved_slots: int, control_quantum: int = 1, durable_quantum: int = 1, heavy_quantum: int = 1, payload_quantum_bytes: int = 65536)`.",
        "`BackgroundSchedulerMetricsV1(ready: int, retry_wait: int, leased: int, pending_items: int, pending_bytes: int, item_high_water: int, byte_high_water: int, concurrency_high_water: int, starvation_windows_ge_5s: int, project_service_starts: tuple[tuple[str, int], ...], worker_claims: tuple[tuple[str, int], ...])`.",
        "`BackgroundSchedulerV1.__init__(store: BackgroundReceiptStoreV1, config: BackgroundSchedulerConfigV1, *, clock: Callable[[], datetime]) -> None`.",
        "`BackgroundSchedulerV1.recover() -> BackgroundRecoverySnapshotV1`.",
        "`BackgroundSchedulerV1.claim_next(worker_id: str, *, lease_ms: int) -> DurableOperationReceiptV1 | None`.",
        "`BackgroundSchedulerV1.metrics_snapshot() -> BackgroundSchedulerMetricsV1`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-RESOLVE.3",
      "title": "One-time default binding and BindingReceiptV1",
      "goal": "Make `set_project` the sole default-selection operation for the exact caller-session key and return C-03 for both changed and unchanged binds.",
      "owned_files": [
        "src/scribe_mcp/tools/set_project.py",
        "src/scribe_mcp/state/manager.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.set_project import set_project; from scribe_mcp.shared.execution_context import BindingReceiptV1; from scribe_mcp.state.manager import StateManager'",
        "./.venv/bin/pytest -q tests/test_set_project.py tests/test_set_project_runtime_scope_contract.py tests/test_set_project_integration.py tests/test_session_project_cache.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py"
      ],
      "acceptance": [
        "Every successful bind returns a complete C-03 receipt tied to the exact caller-session hash and stable project key.",
        "Unchanged bind and stale-generation failure perform zero persistent writes; changed target increments exactly once.",
        "The trace-derived delayed second write succeeds after one bind with no rebind/default drift.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-RESOLVE.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-RESOLVE.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 9,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve the existing public `set_project(..., expected_generation: int | None = None, format: str = \"readable\", ...) -> dict[str, Any]`; every successful format includes one serialized `binding_receipt: BindingReceiptV1`.",
        "`StateManager.accept_session_binding(*, caller_session_key: str, record: SessionBindingRecordV2, project_data: dict[str, Any]) -> State`; cache/state projection only, with no C-01 write.",
        "The successful structured receipt uses `resolution_source=\"set_project\"`; unchanged binds set `binding_reused=True` and `persistent_write_performed=False`; first/changed binds use `False/True`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BG.2",
      "title": "Fenced worker, finite retry, and cancellation protocol",
      "goal": "Execute one claimed receipt through a host-injected idempotent handler, preserving C-08 state-version/fence authority across success, finite seeded retry, permanent failure, cancellation, worker death, and restart.",
      "owned_files": [
        "src/scribe_mcp/background/worker.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background.worker import BackgroundCancellationProbeV1, BackgroundExecutionOutcomeV1, BackgroundWorkerStepV1, BackgroundWorkerV1, SeededRetryPolicyV1'",
        "./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m \"core and regression and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py"
      ],
      "acceptance": [
        "Lease ownership, state version, and fencing token gate every worker transition; zero stale completions are accepted.",
        "Retry timing is finite, seeded, deterministic, restart-safe, and terminal on permanent/malformed/exhausted outcomes.",
        "Cancellation races yield only enumerated cardinality-clean outcomes; worker death/restart loses no accepted receipt or authoritative effect.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BG.1"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BG.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 10,
      "suggested_specialist": "forge",
      "contracts": [
        "`BackgroundExecutionKind = Literal[\"succeeded\", \"transient_failure\", \"permanent_failure\"]`.",
        "`BackgroundExecutionOutcomeV1(kind: BackgroundExecutionKind, result_ref: str | None = None, error_code: str | None = None)`.",
        "`BackgroundCancellationProbeV1.is_cancel_requested() -> bool` and `BackgroundCancellationProbeV1.mark_commit_started() -> None`.",
        "`BackgroundJobHandlerV1 = Callable[[DurableOperationReceiptV1, BackgroundCancellationProbeV1], Awaitable[BackgroundExecutionOutcomeV1]]`.",
        "`SeededRetryPolicyV1(max_attempts: int, base_delay_ms: int, max_delay_ms: int, jitter_ms: int, seed: int)`.",
        "`SeededRetryPolicyV1.next_attempt_at(receipt: DurableOperationReceiptV1, *, now: datetime) -> datetime | None`.",
        "`BackgroundWorkerStepV1(worker_id: str, operation_id: str | None, outcome: Literal[\"idle\", \"succeeded\", \"retry_wait\", \"failed_terminal\", \"cancelled\", \"stale_fence\"])`.",
        "`BackgroundWorkerV1.__init__(worker_id: str, scheduler: BackgroundSchedulerV1, store: BackgroundReceiptStoreV1, handler: BackgroundJobHandlerV1, retry_policy: SeededRetryPolicyV1, *, lease_ms: int, clock: Callable[[], datetime]) -> None`.",
        "`BackgroundWorkerV1.run_once() -> BackgroundWorkerStepV1`, `request_cancel(operation_id: str) -> bool`, and `stop_claiming() -> None`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BIND-RESOLVE.4",
      "title": "One-pass runtime context, typed MCP errors, and generic external adapter",
      "goal": "Resolve once at dispatch, install C-11 for the complete call, and translate every expected binding/project failure into C-04 across modern and legacy MCP adapters.",
      "owned_files": [
        "src/scribe_mcp/shared/tool_runtime.py",
        "src/scribe_mcp/mcp_adapter.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key; from scribe_mcp.mcp_adapter import ScribeErrorV1, ScribeExpectedError, normalize_scribe_error, normalize_tool_result'",
        "./.venv/bin/pytest -q tests/test_mcp_adapter.py tests/test_tool_runtime_repo_scope.py",
        "./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py",
        "./.venv/bin/pytest -q tests/security/test_session_provenance.py tests/migration/mcp_v2/test_compatibility_matrix.py"
      ],
      "acceptance": [
        "Every project-bound call uses one exact server-verified caller key and one immutable C-11; attribution cannot affect identity or routing.",
        "All expected binding/project failures return C-04 `isError=true` with identical structured content across protocol eras; no expected failure escapes as a raw transport exception.",
        "The generic C-16 flow supports bind-once, authorized explicit cross-repo calls, reconnect, ambiguity/stale-generation/wrong-target denials, and default preservation without Council logic.",
        "The 32-session × 100-call oracle reports zero wrong target, default drift, cross-talk, duplicate effect, or untyped ambiguity.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-RESOLVE.2",
        "SBR-BIND-RESOLVE.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BIND-RESOLVE.4",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 10,
      "suggested_specialist": "forge",
      "contracts": [
        "`resolve_context_authoritative_session_key(context: Any) -> str | None` returns only a server-verified application/stable-session key.",
        "`ScribeErrorV1(ok: Literal[False], error_code: str, message: str, retryable: bool, target: dict[str, str] | None, candidates: tuple[dict[str, str], ...], remediation: str | None, correlation_id: str)`.",
        "`ScribeExpectedError(error: ScribeErrorV1)` is the only expected-failure exception crossing internal dispatch.",
        "`normalize_scribe_error(error: ScribeErrorV1, *, runtime: MCPRuntime, era: ProtocolEra) -> CallToolResult`.",
        "Preserve `execute_tool_call(...) -> Any`, `normalize_tool_result(...)`, and `configure_mcp_server(...)`; `call_tool_bound` catches only `ScribeExpectedError`, returning `isError=true` with identical C-04 `structuredContent` in both eras."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BG.3",
      "title": "BackgroundJobServiceV1 admission, recovery, metrics, and API",
      "goal": "Compose C-08, the scheduler, and workers behind the frozen C-09 API, with typed non-admission, zero-lost restart recovery, bounded metrics, and idempotent start/stop.",
      "owned_files": [
        "src/scribe_mcp/background/service.py",
        "src/scribe_mcp/background/__init__.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background import BackgroundIntentV1, BackgroundJobServiceV1, BackgroundServiceConfigV1, BackgroundServiceHealthV1, BackgroundShutdownReceiptV1'",
        "./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_swarm_binding_reliability.py tests/core/test_wal_replay_exactly_once.py -m \"core and regression and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py"
      ],
      "acceptance": [
        "Every accepted or duplicate submit returns durable C-08 truth; every conflict/busy/shutdown path is typed, prompt, and effect-free.",
        "Fresh service reconstruction finds every accepted nonterminal receipt, rebuilds exact capacity, and loses zero receipts across forced restart.",
        "Under 32 callers, foreground control/read and receipt acknowledgement p95 are at most 500 ms, bounds never exceed config, and required metrics agree with receipt history.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BG.1",
        "SBR-BG.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BG.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 11,
      "suggested_specialist": "forge",
      "contracts": [
        "`BackgroundIntentV1 = BackgroundOperationIntentV1`; this is an alias, not a subclass or copied dataclass.",
        "`BackgroundServiceConfigV1(queue_limits: BackgroundQueueLimitsV1, scheduler: BackgroundSchedulerConfigV1, worker_count: int, lease_ms: int, retry_policy: SeededRetryPolicyV1, drain_deadline_ms: int)`.",
        "`BackgroundQueueEventV1(kind: str, observed_at: datetime, lane: BackgroundLane | None, outcome: str, canonical_project_key_hash: str | None, duration_ms: int | None, value: int | None)`; kind/outcome are validated closed vocabularies and the project label is a non-reversible hash.",
        "`BackgroundServiceHealthV1(state: Literal[\"stopped\", \"starting\", \"running\", \"draining\", \"degraded\"], accepting: bool, workers_active: int, metrics: BackgroundSchedulerMetricsV1, accepted_receipts: int, recovered_receipts: int, stale_fence_rejections: int, drain_deadline_exceeded: bool)`.",
        "`BackgroundShutdownReceiptV1(admission_closed: bool, drain_deadline_ms: int, drained: int, checkpointed: int, cancelled_retryable: int, remaining_recoverable: int, workers_stopped: int, deadline_exceeded: bool, stopped_at: datetime)`.",
        "`BackgroundDigestConflictError`, `BackgroundQueueBusyError(retry_after_ms: int)`, `BackgroundServiceShuttingDownError`, and `BackgroundOperationNotFoundError` are the only C-09 service errors.",
        "`BackgroundJobServiceV1.__init__(store: BackgroundReceiptStoreV1, handler: BackgroundJobHandlerV1, config: BackgroundServiceConfigV1, *, clock: Callable[[], datetime], emit: Callable[[BackgroundQueueEventV1], None]) -> None`.",
        "`submit(intent: BackgroundIntentV1) -> DurableOperationReceiptV1`, `get_status(operation_id: str) -> DurableOperationReceiptV1`, `cancel(operation_id: str, expected_state_version: int) -> DurableOperationReceiptV1`, `start() -> None`, `stop(admission_close: bool = True, drain_deadline_ms: int | None = None) -> BackgroundShutdownReceiptV1`, and `health_snapshot() -> BackgroundServiceHealthV1` are async methods."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-HOTPATH.1",
      "title": "C-12 timing model and context-aware response finalization",
      "goal": "Define the sole `CallTimingEnvelopeV2` builder/recorder and make `FormatterDispatcher` finalize responses from the already-resolved C-11 context, with honest >=95% accounting and correlated >100 ms stage / >500 ms total evidence.",
      "owned_files": [
        "src/scribe_mcp/runtime_timing_envelope.py",
        "src/scribe_mcp/utils/formatters/dispatcher.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.runtime_timing_envelope import CALL_TIMING_PHASES_V2, CallTimingEnvelopeV2, CallTimingRecorderV2, build_call_timing_envelope_v2, build_timing_envelope; from scribe_mcp.utils.formatters.dispatcher import FormatterDispatcher'",
        "./.venv/bin/pytest -q tests/test_dispatcher.py tests/test_log_intelligence.py tests/test_doctor_telemetry.py",
        "./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py",
        "./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py"
      ],
      "acceptance": [
        "C-12 has the exact frozen phases/fields, honest `unaccounted`, >=0.95 measured coverage in passing calls, and deterministic strict >100/>500 tripwires sharing C-11 correlation.",
        "Formatter performs zero session-binding/project-record reads and zero ambient target selection; `fetch_project_sync` is absent from its call path.",
        "Local authoritative audit durability remains foreground; only analytics/derived metrics defer.",
        "V1 timing consumers and all response formats remain compatible.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-RESOLVE.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-HOTPATH.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "src/scribe_mcp/shared/tool_runtime.py",
        "src/scribe_mcp/shared/execution_context.py"
      ],
      "wave": 11,
      "suggested_specialist": "forge",
      "contracts": [
        "`CALL_TIMING_PHASES_V2: tuple[str, ...]` is ordered exactly as `(\"ingress_decode\", \"session_binding_read\", \"project_record_read\", \"target_resolution\", \"mode_resolution\", \"tool_body\", \"authority_and_validation\", \"authoritative_durability\", \"receipt_commit\", \"hooks\", \"response_format\", \"audit_append\", \"egress_serialize\", \"unaccounted\")`.",
        "`class CallTimingEnvelopeV2(TypedDict)` has `schema_version: Literal[\"call-timing-envelope.v2\"]`, `correlation_id: str`, `phases_ms: dict[str, float]`, `total_ms: float`, `accounted_ratio: float`, `slow_stages: list[str]`, and `tripwire_exceeded: bool`.",
        "`CallTimingRecorderV2.start(*, correlation_id: str, started_perf_counter: float | None = None, seed_phases_ms: Mapping[str, float] | None = None) -> CallTimingRecorderV2`.",
        "`CallTimingRecorderV2.record_phase(phase: str, duration_ms: float) -> None`; repeated recording accumulates only the same named non-overlapping stage.",
        "`CallTimingRecorderV2.finalize(*, total_ms: float | None = None) -> CallTimingEnvelopeV2`.",
        "`build_call_timing_envelope_v2(*, correlation_id: str, phases_ms: Mapping[str, float], total_ms: float) -> CallTimingEnvelopeV2`.",
        "Preserve `build_runtime_efficiency_budget_status(...)`, `build_timing_envelope(...)`, and `build_timing_envelope_from_entries(...)`; their V1 schema/readers remain compatible.",
        "Extend only the internal formatter interface: `FormatterDispatcher.finalize_tool_response(data: Dict[str, Any], format: str = \"readable\", tool_name: str = \"\", telemetry: Optional[Dict[str, Any]] = None, resolved_request_context: ResolvedRequestContextV1 | None = None) -> Union[Dict[str, Any], CallToolResult]`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-BG.4",
      "title": "Server lifecycle integration and bounded health projection",
      "goal": "Attach the C-09 service to Scribe startup/shutdown and health without changing core-ready semantics, transport contracts, or host process policy.",
      "owned_files": [
        "src/scribe_mcp/server.py",
        "src/scribe_mcp/tools/health_check.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp import server; from scribe_mcp.background import BackgroundJobServiceV1; from scribe_mcp.tools.health_check import health_check; assert hasattr(server, \"get_background_job_service\")'",
        "./.venv/bin/pytest -q tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_health_check.py",
        "./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m \"core and regression and not slow and not performance\""
      ],
      "acceptance": [
        "Startup reconstructs C-08 truth and starts one bounded worker service without changing core-ready semantics or using legacy task tracking for accepted jobs.",
        "Shutdown closes admission before claims, drains/checkpoints before backend close, leaks zero workers/tasks/handles above baseline, and loses zero accepted receipts.",
        "Health exposes bounded scheduler/worker/recovery/drain metrics and no raw identifiers or host/provider/Council policy.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BG.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-BG.4",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 12,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve `schedule_background_task(coro, *, service_name: str | None = None, description: str = \"\", persistent: bool = False) -> asyncio.Task`.",
        "Preserve `drain_background_tasks(*, timeout: float | None = None) -> list[BaseException]` and `get_background_service_status() -> dict[str, dict[str, Any]]` for legacy process-local services.",
        "Add `get_background_job_service() -> BackgroundJobServiceV1 | None`.",
        "Add `get_background_job_service_health() -> BackgroundServiceHealthV1 | None`.",
        "Preserve `_startup(*, startup_profile: str = \"full_server\") -> None`, `_shutdown() -> None`, and `health_check(agent: str) -> dict[str, Any]`.",
        "`health_check` adds `components.background_job_service` and bounded queue/worker metrics while preserving all existing top-level keys."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-DOC-DUR.2",
      "title": "C-13 generation-fenced admission and restart replay",
      "goal": "Produce `DocumentMutationReceiptV1` from the existing apply-preview/runtime mutation path and map every foreground, duplicate, offline, conflict, cancellation, and restart-replay outcome onto frozen C-02/C-03/C-04/C-08/C-09/C-11/C-13.",
      "owned_files": [
        "src/scribe_mcp/doc_management/apply_preview.py",
        "src/scribe_mcp/doc_management/runtime.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewBinding, ApplyPreviewService, DocumentMutationReceiptV1, DocumentMutationState'",
        "./.venv/bin/pytest -q tests/test_apply_preview_engine.py tests/test_manage_docs_apply_preview.py tests/integration/test_manage_docs_apply_preview_lifecycle.py tests/integration/storage/test_apply_preview_backend_parity.py tests/security/test_apply_preview_receipt_security.py",
        "./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py tests/test_manage_docs_anchor_cas.py tests/test_tool_runtime_repo_scope.py -m \"core and regression and not slow and not performance\""
      ],
      "acceptance": [
        "Every mutation attempt returns a complete sanitized C-13 receipt or typed C-04; `queued_offline` is true only for WAL-durable accepted work.",
        "Repeated client retries, worker retries, and process restarts yield one operation ID, one document generation increment, and at most one file effect.",
        "Stale binding, stale document generation/digest/anchor, wrong target/root/path, stale fence, and missing authority all refuse before effect with the exact typed outcome.",
        "Duplicate, conflict, terminal, and cancelled outcomes are stable on replay and cannot re-enter the mutation effect.",
        "The implementation uses the existing ApplyPreviewService, WAL, C-08/C-09 service, and mutation locks only.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-DOC-DUR.1",
        "SBR-BIND-RESOLVE.2",
        "SBR-BIND-RESOLVE.3",
        "SBR-BIND-RESOLVE.4",
        "SBR-RECEIPT.1",
        "SBR-RECEIPT.2",
        "SBR-RECEIPT.3",
        "SBR-BG.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DOC-DUR.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 12,
      "suggested_specialist": "forge",
      "contracts": [
        "`DocumentMutationState = Literal[\"accepted\", \"applied\", \"duplicate\", \"conflict\", \"terminal_error\", \"cancelled\"]`.",
        "`DocumentMutationReceiptV1(operation_id: str, project_key: str, caller_session_key_hash: str, binding_generation: int, document_id: str, canonical_path: str, document_generation_before: int, document_generation_after: int | None, content_digest_before: str, content_digest_after: str | None, state: DocumentMutationState, replay_safe: bool, queued_offline: bool, correlation_id: str)`.",
        "`DocumentMutationReceiptV1.as_public_dict() -> dict[str, object]` emits no raw caller key, authorization evidence, retained content, journal path, lease/fence, or backend detail.",
        "`ApplyPreviewBinding` gains validated `caller_session_key_hash`, `binding_generation`, `document_id`, `document_generation_before`, `content_digest_before`, and `content_digest_after`; preserve its existing scope/target fields and `storage_payload()`.",
        "Preserve `ApplyPreviewService.issue(...) -> ApplyPreviewAffordance` and `ApplyPreviewService.apply(...) -> dict[str, object]`; extend their existing preflight/finalization path rather than adding another service.",
        "Runtime-local `build_document_mutation_receipt(...) -> DocumentMutationReceiptV1`, `admit_document_mutation(...) -> DocumentMutationReceiptV1`, and `replay_document_mutation(...) -> DocumentMutationReceiptV1` stay inside `runtime.py#durable_mutation_hooks`; they are not a new public engine.",
        "C-13 state remains closed. `queued_offline=True` is legal only for `state=\"accepted\"` and `replay_safe=True`; every other state requires `queued_offline=False`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-HOTPATH.2",
      "title": "Single-context logging helper and get-project read path",
      "goal": "Make `LoggingToolMixin` consume the exact installed C-11 context and make `get_project` reuse its resolved project data without label authority, compatibility re-resolution, or another project-record fetch.",
      "owned_files": [
        "src/scribe_mcp/shared/base_logging_tool.py",
        "src/scribe_mcp/tools/get_project.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.base_logging_tool import LoggingToolMixin; from scribe_mcp.tools.get_project import get_project'",
        "./.venv/bin/pytest -q tests/test_base_logging_tool.py tests/test_get_project_integration.py tests/test_get_project_sitrep.py tests/test_session_resolution_advisories.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py"
      ],
      "acceptance": [
        "`get_project` and its helper/formatter chain observe the same C-11 object and C-11 correlation ID.",
        "One complete call performs at most one binding read and one project-record read in total; the SS-05 portion performs neither again.",
        "Attribution-only `agent`, recents, ambient root, and process/global state cannot select or mutate the operational target/default.",
        "Existing get-project content and formats remain correct; non-verbose operation does not add derived recent-entry work.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-HOTPATH.1",
        "SBR-BIND-RESOLVE.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-HOTPATH.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 12,
      "suggested_specialist": "forge",
      "contracts": [
        "Extend `LoggingToolMixin.prepare_context(..., resolved_request_context: ResolvedRequestContextV1 | None = None, ...) -> LoggingContext`; when omitted, it reads `server_module.get_execution_context().resolved_request_context` once and passes that exact object to `resolve_logging_context`.",
        "`LoggingToolMixin.project_record_from_context(context: LoggingContext) -> ProjectRecord` projects the already-resolved record only; it never queries storage, loads config, or consults recents/global state.",
        "`LoggingToolMixin.finalize_tool_response(..., context: LoggingContext, timing: CallTimingRecorderV2) -> Union[Dict[str, Any], CallToolResult]` forwards the same C-11 and recorder to the default formatter.",
        "Preserve the public `get_project(agent: str = \"Codex\", project: Optional[str] = None, format: str = \"structured\", verbose: bool = False, recovery_mode: Optional[str] = None) -> Dict[str, Any]`; `agent` remains attribution only and `recovery_mode` remains explicit diagnostic compatibility only."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-DOC-DUR.3",
      "title": "`manage_docs` readback and registration/index/quality convergence",
      "goal": "Make `manage_docs` expose C-13 consistently and finish each accepted file effect by converging the existing document registry, canonical indexes, and current-generation quality result without rewriting the document twice.",
      "owned_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/tools/manage_docs.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.doc_management import runtime; from scribe_mcp.tools.manage_docs import manage_docs'",
        "./.venv/bin/pytest -q tests/test_auto_registration.py tests/test_manage_docs_quality_check.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_anchor_cas.py tests/security/test_project_binding_policy.py",
        "./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py tests/test_tool_runtime_repo_scope.py -m \"core and regression and not slow and not performance\""
      ],
      "acceptance": [
        "Every committed managed-document mutation has one C-13 readback, one WAL lineage generation, the predicted final digest, one canonical registration/index presence, and current-generation quality evidence.",
        "Backend or convergence outage returns WAL-durable `accepted + queued_offline`; restart converges it to `applied` exactly once without a second file effect.",
        "Duplicate, conflict, terminal, and cancelled outcomes remain stable; wrong-target status/cancel/replay discloses nothing and performs no effect.",
        "Existing actions, dry-run/apply-preview behavior, anchor CAS, quality warnings, and response compatibility remain intact.",
        "No second mutation engine, queue, registry, indexer, quality engine, or persistence layer is introduced.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-DOC-DUR.2",
        "SBR-BG.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DOC-DUR.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 13,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve the full public `manage_docs(...) -> dict[str, Any]` signature and all existing actions.",
        "Successful non-dry-run mutation responses add `document_mutation_receipt: dict[str, object]` containing exactly `DocumentMutationReceiptV1.as_public_dict()`.",
        "Responses with C-13 also add `document_convergence: {\"registration\": \"converged\"|\"pending\"|\"not_applicable\", \"index\": \"converged\"|\"pending\"|\"not_applicable\", \"quality\": \"evaluated\"|\"pending\"|\"not_applicable\"}`; this is response evidence, not another persisted receipt/state machine.",
        "Dry runs keep the existing apply-preview affordance and do not create a document mutation receipt, WAL row, background receipt, registration, index, or quality side effect.",
        "No new `manage_docs` action is added. Optional caller `metadata.idempotency_key` is normalized into the existing retained intent; omission uses the deterministic package `.2` key."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-HOTPATH.3",
      "title": "Read-recent/query single-record execution and timing closure",
      "goal": "Convert `read_recent` and `query_entries` to use the one C-11/LoggingContext/ProjectRecord created for the call, preserve their immediate consistent-snapshot contracts, and close C-12 instrumentation through the formatter.",
      "owned_files": [
        "src/scribe_mcp/tools/read_recent.py",
        "src/scribe_mcp/tools/query_entries.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.read_recent import read_recent; from scribe_mcp.tools.query_entries import query_entries, _build_search_query, _execute_search_with_fallbacks'",
        "./.venv/bin/pytest -q tests/test_consumer_resolution_contract.py tests/test_read_recent_limit.py tests/test_read_recent_supplement_gate.py",
        "./.venv/bin/pytest -q tests/test_query_entries_db.py tests/test_query_entries_pagination_contract.py tests/test_query_entries_explicit_project_resolution.py tests/test_query_entries_dead_engine_honest_envelopes.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/core/test_swarm_binding_reliability.py",
        "./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py"
      ],
      "acceptance": [
        "Both tools reuse one C-11 and one ProjectRecord end to end; no body/helper/formatter repeats session binding or project-record reads.",
        "Immediate read/query snapshots, pagination/filter parity, explicit target/default preservation, and typed C-04 errors remain correct.",
        "Every completed call produces one correlated C-12 with >=0.95 accounting and deterministic stage/total tripwire evidence.",
        "DA-09's 32 x 100 oracle reports zero wrong target, default drift, cross-talk, duplicate effect, or excess binding/project reads.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-HOTPATH.1",
        "SBR-HOTPATH.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-HOTPATH.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 13,
      "suggested_specialist": "forge",
      "contracts": [
        "Preserve public `read_recent(...)` and `query_entries(...)` MCP signatures, pagination/filter semantics, readable/structured/compact behavior, and C-04 results.",
        "Internal `_build_search_query(final_config: QueryEntriesConfig, context: LoggingContext, project_record: ProjectRecord) -> Dict[str, Any]`.",
        "Internal `async _execute_search_with_fallbacks(search_query: Dict[str, Any], final_config: QueryEntriesConfig, *, project_record: ProjectRecord, resolved_request_context: ResolvedRequestContextV1, timing: CallTimingRecorderV2) -> Dict[str, Any]`.",
        "Every formatter call supplies `resolved_request_context=context.resolved_request_context` and the same `CallTimingRecorderV2`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-STARTUP.3",
      "title": "C-10 core-ready and optional-service states",
      "goal": "Make `Server ready` mean required C-07 storage/schema readiness plus recovered/running C-09 background service, while object-store and bridge health continue asynchronously through exact C-10 service states.",
      "owned_files": [
        "src/scribe_mcp/server.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.server import ServiceStateV1, get_service_states, _startup, _shutdown; from scribe_mcp.background import BackgroundJobServiceV1; from scribe_mcp.storage.postgres.schema import SchemaReadinessV1'",
        "./.venv/bin/pytest -q tests/test_server_invoke_tool_startup_bypass.py",
        "./.venv/bin/pytest -q tests/test_health_check.py",
        "./.venv/bin/pytest -q tests/test_release_startup_probe.py::test_core_ready_requires_c07_and_c09_but_not_optional_services tests/test_release_startup_probe.py::test_process_to_ready_meets_warm_and_cold_budgets tests/test_release_startup_probe.py::test_optional_service_shutdown_is_idempotent_and_leak_free"
      ],
      "acceptance": [
        "Core-ready occurs only after C-07 succeeds and C-09 recovery/start reports running+accepting; required failure emits no ready signal.",
        "C-10 is importable with exactly six frozen fields and only four frozen states; optional object-store/bridge failure becomes degraded without raw-error leakage.",
        "Optional health work is background-only and cannot block core tools/local durable logging; outage foreground delta is at most 50 ms.",
        "Warm/cold process-to-ready p95 is at most 1.5/2.5 s, shutdown remains ordered/idempotent, and no new task/client survives teardown.",
        "Import/RSS gates from SBR-STARTUP.1 and C-07/C-09 producer regressions all pass on the same source revision.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-STARTUP.1",
        "SBR-STARTUP.2",
        "SBR-SCHEMA.3",
        "SBR-BG.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-STARTUP.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "src/scribe_mcp/server.py"
      ],
      "wave": 13,
      "suggested_specialist": "forge",
      "contracts": [
        "Add `ServiceStateNameV1 = Literal[\"initializing\", \"healthy\", \"degraded\", \"stopped\"]`.",
        "Add frozen `ServiceStateV1(service: str, state: ServiceStateNameV1, required_for_core_ready: bool, last_error_code: str | None, last_transition_at: str, startup_phase_ms: float | None)`.",
        "Add `get_service_states() -> dict[str, dict[str, Any]]`, returning bounded serializable C-10 snapshots keyed by service.",
        "Preserve `_startup(*, startup_profile: str = \"full_server\") -> None`, `_shutdown() -> None`, `get_background_service_status() -> dict[str, dict[str, Any]]`, and DA-07's C-09 accessors unchanged."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-CORE-VAL.1",
      "title": "Shared swarm fixture and 32-session binding oracle",
      "goal": "Create the reusable harness and core regression proving 32 same-label sessions retain independent defaults and exact effects through 3,200 mixed calls, explicit targeting, delayed second-write, reconnect, cleanup, and causal cross-repository overlap.",
      "owned_files": [
        "tests/fixtures/swarm.py",
        "tests/core/test_swarm_binding_reliability.py"
      ],
      "verification": [
        "PYTHONPATH=src:tests ./.venv/bin/python -c 'from fixtures.swarm import ManualClock, CausalGate, SwarmResultsV1, build_swarm_topology, build_mixed_schedule, reconcile_exact_effects'",
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.tools.set_project import set_project; from scribe_mcp.shared.tool_runtime import execute_tool_call; from scribe_mcp.mcp_adapter import ScribeErrorV1'",
        "./.venv/bin/python -m py_compile tests/fixtures/swarm.py tests/core/test_swarm_binding_reliability.py",
        "./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py -m \"core and regression and not integration and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/test_set_project.py tests/test_set_project_runtime_scope_contract.py tests/test_session_project_cache.py tests/test_mcp_adapter.py"
      ],
      "acceptance": [
        "Exactly 32 authoritative sessions share one label but never a default, generation, ledger, or target.",
        "Every caller has one bind and 100 mixed calls; delayed second-write succeeds without rebind/default mutation.",
        "Multiple repos/projects, duplicate names, isolated reconnects, new-handle denial, and one-caller cleanup are cardinality-clean.",
        "Repo B progresses while Repo A is causally blocked; C-14 is seed-deterministic and all forbidden-effect counts are zero.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.1",
        "SBR-BIND-PERSIST.2",
        "SBR-BIND-PERSIST.3",
        "SBR-BIND-PERSIST.4",
        "SBR-BIND-PERSIST.5",
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-RESOLVE.2",
        "SBR-BIND-RESOLVE.3",
        "SBR-BIND-RESOLVE.4",
        "SBR-HOTPATH.1",
        "SBR-HOTPATH.2",
        "SBR-HOTPATH.3",
        "SBR-SCHEMA.2"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-CORE-VAL.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 14,
      "suggested_specialist": "crucible",
      "contracts": [
        "Test-only `ManualClock.now() -> float` and `ManualClock.advance(delta_ms: int) -> None`.",
        "Test-only `CausalGate.entered: asyncio.Event` and `CausalGate.release: asyncio.Event`.",
        "`build_swarm_topology(tmp_path: Path, *, agent_label: str, seed: int) -> SwarmTopology` creates four repositories, four projects per repository, and two callers per default project.",
        "`build_mixed_schedule(caller: SwarmCaller, *, seed: int) -> tuple[SwarmOperation, ...]` returns exactly 100 operations with the frozen 30/20/20/15/5/5/5 mix.",
        "`reconcile_exact_effects(expected: Sequence[ExpectedEffect], observed: Sequence[ObservedEffect], *, metadata: SwarmRunMetadata) -> SwarmResultsV1`.",
        "`SwarmResultsV1.as_json_dict() -> dict[str, object]` emits exactly C-14 and is the only structured result source."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-REL-VAL.4",
      "title": "Import, RSS, ready, schema, and hot-path budgets",
      "goal": "Turn frozen import/RSS/process-ready/schema-ready/hot-path budgets into repeatable release probes whose raw results feed C-15.",
      "owned_files": [
        "tests/test_release_startup_probe.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -m py_compile tests/test_release_startup_probe.py",
        "PYTHONPATH=src ./.venv/bin/pytest -q tests/test_release_startup_probe.py"
      ],
      "acceptance": [
        "Every budget emits raw samples and explicit PASS/FAIL.",
        "Mixed revisions, missing evidence, excessive reads, unexplained time, and absent tripwires fail.",
        "No production contact or teardown leak.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-STARTUP.1",
        "SBR-STARTUP.2",
        "SBR-STARTUP.3",
        "SBR-SCHEMA.3",
        "SBR-HOTPATH.1",
        "SBR-HOTPATH.2",
        "SBR-HOTPATH.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-REL-VAL.4",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 14,
      "suggested_specialist": "crucible",
      "contracts": [
        "`run_release_budget_probe(*, profile: Literal[\"warm\", \"cold\", \"object-store-outage\", \"schema-32\", \"hot-path\"], source_revision: str, results_dir: Path) -> ReleaseBudgetProbeResult`",
        "`startup-budget.json` records revision, repetitions, raw samples, percentile method, module count, import-time writes, pre-tool/all-tools RSS, service states, schema roles/waits, C-12 phases/total/accounting/tripwires, environment fingerprint, and verdicts."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-CORE-VAL.2",
      "title": "Bounded queue, fairness, cancellation, and shutdown contract",
      "goal": "Prove C-08/C-09 admission, partitioning, fairness, fencing, cancellation, recovery, shutdown, and metrics stay bounded and independent across projects.",
      "owned_files": [
        "tests/core/test_background_queue_contract.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.background import BackgroundIntentV1, BackgroundJobServiceV1, BackgroundServiceConfigV1, BackgroundShutdownReceiptV1; from scribe_mcp.background.scheduler import BackgroundSchedulerV1'",
        "./.venv/bin/python -m py_compile tests/core/test_background_queue_contract.py",
        "./.venv/bin/pytest -q tests/core/test_background_queue_contract.py -m \"core and regression and not integration and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/storage/test_background_receipt_contract.py tests/storage/test_sqlite_background_receipts.py tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_health_check.py"
      ],
      "acceptance": [
        "Item/byte/global/project/lane/worker bounds hold at every checkpoint with exact receipt outcomes.",
        "Fairness passes and blocked/retrying/cancelling/draining A never blocks B/C.",
        "Retry, reclaim, fencing, cancellation, recovery, and shutdown lose/duplicate no accepted effect or capacity.",
        "Metrics and C-14 queue fields are exact and bounded-cardinality.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-CORE-VAL.1",
        "SBR-RECEIPT.1",
        "SBR-RECEIPT.2",
        "SBR-RECEIPT.3",
        "SBR-BG.1",
        "SBR-BG.2",
        "SBR-BG.3",
        "SBR-BG.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-CORE-VAL.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 15,
      "suggested_specialist": "crucible",
      "contracts": [
        "Consume C-08 `admit/get/claim/transition/recover` and C-09 `submit/get_status/cancel/start/stop` exactly as frozen.",
        "Reuse package .1 `ManualClock`, `CausalGate`, and C-14 queue fields; do not duplicate them."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-CORE-VAL.5",
      "title": "Remote C-01 durable binding expectation",
      "goal": "Replace stale all-session in-memory/no-HTTP binding expectations with hermetic proof that only Remote binding set/get uses authenticated authoritative transport and frozen C-01.",
      "owned_files": [
        "tests/test_remote_backend.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; from scribe_mcp.storage.base import SessionBindingRecordV2'",
        "./.venv/bin/python -m py_compile tests/test_remote_backend.py",
        "./.venv/bin/pytest -q tests/test_remote_backend.py::TestSessionMethods",
        "./.venv/bin/pytest -q tests/test_remote_backend.py::TestRemoteAuth tests/test_remote_backend.py::TestErrorHandling"
      ],
      "acceptance": [
        "Remote binding set/get uses authenticated transport once and strictly decodes C-01.",
        "Reconnect proves cache non-authority; unchanged/stale-generation outcomes are durable/effect-free.",
        "Malformed responses use existing typed Remote errors without leaks.",
        "Unrelated session methods remain local/no-HTTP and no external request occurs.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-PERSIST.5",
        "SBR-CORE-VAL.1",
        "SBR-ARCH-AMEND-REMOTE-08"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-CORE-VAL.5",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 15,
      "suggested_specialist": "crucible",
      "contracts": [
        "Assert C-01 `set_session_project(session_id: str, project_key: str, expected_generation: int | None = None) -> SessionBindingRecordV2` and `get_session_project(session_id: str) -> SessionBindingRecordV2 | None`.",
        "Record fields: `caller_session_key_hash`, `project_key`, `project_name`, `canonical_repo_root`, `binding_generation`, `updated_at`."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-CORE-VAL.3",
      "title": "WAL and document replay exactly-once oracle",
      "goal": "Prove accepted log/background/document work survives every named crash/restart window and converges to one authoritative effect with C-08/C-09/C-13 receipts.",
      "owned_files": [
        "tests/core/test_wal_replay_exactly_once.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.utils.files import WriteAheadLog, WalEntryConflictError, WalJournalCorruptError; from scribe_mcp.doc_management.apply_preview import DocumentMutationReceiptV1, DocumentMutationState'",
        "./.venv/bin/python -m py_compile tests/core/test_wal_replay_exactly_once.py",
        "./.venv/bin/pytest -q tests/core/test_wal_replay_exactly_once.py -m \"core and regression and not integration and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/test_multi_repo_file_ops.py tests/test_write_barrier_contract.py tests/test_apply_preview_engine.py tests/test_manage_docs_apply_preview.py tests/integration/test_manage_docs_apply_preview_lifecycle.py"
      ],
      "acceptance": [
        "Every crash/restart/concurrent replay ends with one effect and one terminal truth per accepted operation.",
        "Malformed tails, wrong targets, stale generations/digests/anchors/fences, cancellation, and one-project failure cannot contaminate peers.",
        "Offline work survives reconstruction; registration/index/quality convergence is current-generation and duplicate-free.",
        "Error/state vocabularies remain frozen and all barriers are deterministic.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-CORE-VAL.1",
        "SBR-CORE-VAL.2",
        "SBR-DOC-DUR.1",
        "SBR-DOC-DUR.2",
        "SBR-DOC-DUR.3",
        "SBR-BG.2",
        "SBR-BG.3",
        "SBR-BG.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-CORE-VAL.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 16,
      "suggested_specialist": "crucible",
      "contracts": [
        "Consume `WriteAheadLog.write_entry/read_uncommitted/has_commit/commit_entry/replay_uncommitted`, C-08/C-09 receipts, and C-13 `DocumentMutationReceiptV1` unchanged.",
        "Reuse .1 ledger/clock/gates/reconciler and .2 receipt oracle."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-CORE-VAL.4",
      "title": "Typed runtime and managed-document refusal regressions",
      "goal": "Extend canonical tests so C-02/C-04/C-11/C-12/C-13 target, identity, generation, CAS, and error semantics are exact and effect-free on refusal.",
      "owned_files": [
        "tests/test_tool_runtime_repo_scope.py",
        "tests/test_manage_docs_anchor_cas.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key; from scribe_mcp.shared.execution_context import ResolvedRequestContextV1; from scribe_mcp.mcp_adapter import ScribeErrorV1, normalize_tool_result; from scribe_mcp.tools.manage_docs import manage_docs'",
        "./.venv/bin/python -m py_compile tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py",
        "./.venv/bin/pytest -q tests/test_tool_runtime_repo_scope.py tests/test_manage_docs_anchor_cas.py -m \"core and regression and not integration and not slow and not performance\"",
        "./.venv/bin/pytest -q tests/test_mcp_adapter.py tests/test_logging_utils.py tests/test_append_entry_explicit_project_resolution.py tests/test_query_entries_explicit_project_resolution.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_quality_check.py tests/security/test_project_binding_policy.py"
      ],
      "acceptance": [
        "Every expected failure returns exact typed MCP/C-04 envelope with zero side effects.",
        "Each call has one immutable C-11, at most one binding/project read, and one C-12.",
        "Explicit target, CAS, generation, digest, recovery, and convergence preserve defaults and durable truth.",
        "Existing canonical-key/fallback, anchor-race, and schema-exposure regressions stay green.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-RESOLVE.2",
        "SBR-BIND-RESOLVE.3",
        "SBR-BIND-RESOLVE.4",
        "SBR-HOTPATH.1",
        "SBR-HOTPATH.2",
        "SBR-HOTPATH.3",
        "SBR-DOC-DUR.2",
        "SBR-DOC-DUR.3",
        "SBR-CORE-VAL.3"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-CORE-VAL.4",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 17,
      "suggested_specialist": "crucible",
      "contracts": [
        "Preserve C-04 `CallToolResult`: `isError=true` and `structuredContent` keys `ok/error_code/message/retryable/target/candidates/remediation/correlation_id`.",
        "Consume one immutable C-11 `ResolvedRequestContextV1` and one C-12 envelope per foreground/replay call; helpers never re-resolve."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-REL-VAL.2",
      "title": "32-caller PostgreSQL/process stress and queue proof",
      "goal": "Exercise the real provider-neutral swarm, schema readiness, timing envelope, and background queue under disposable PostgreSQL/process profiles while extending C-14 `SwarmResultsV1` rather than creating a second oracle.",
      "owned_files": [
        "tests/integration/test_swarm_concurrency_stress.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -m py_compile tests/integration/test_swarm_concurrency_stress.py",
        "SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL=\"$SCRIBE_TEST_POSTGRES_URL\" SCRIBE_SWARM_PROFILE=smoke SCRIBE_SWARM_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/swarm-smoke PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py -m \"integration and postgres and performance and slow\""
      ],
      "acceptance": [
        "32 same-label callers complete the fixed trace with one bind each and zero correctness defects.",
        "Queue fairness, backpressure, worker fencing, restart recovery, and no-HOL verdicts are `PASS`.",
        "Measurements share one revision and sanitized environment; teardown returns to baseline.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-REL-VAL.1",
        "SBR-CORE-VAL.1",
        "SBR-CORE-VAL.2",
        "SBR-CORE-VAL.3",
        "SBR-CORE-VAL.4",
        "SBR-CORE-VAL.5"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-REL-VAL.2",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**",
        "tests/fixtures/swarm.py"
      ],
      "wave": 18,
      "suggested_specialist": "crucible",
      "contracts": [
        "`StressProfile.from_env() -> StressProfile` accepts `smoke`, `background-queue`, `release`, and `extended` without separate harnesses.",
        "`run_reference_stress(profile: StressProfile, *, postgres: PostgresReferenceFixture, source_revision: str, results_dir: Path) -> SwarmResultsV1`",
        "`swarm-results.json` remains C-14 `scribe-swarm-results.v1`. Its `background_queue` member carries config, foreground/receipt histograms, item/byte/concurrency high-water marks, admission outcomes, queue/run histograms, project shares, worker claims, retry/cancel/lease/fence/shutdown/restart counts; Markdown is derived."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-REL-VAL.3",
      "title": "Provider-neutral public adapter parity",
      "goal": "Run one compact logical trace through each supported public Scribe adapter and prove equivalent target, default, replay, reconnect, and typed-error behavior without Council assumptions.",
      "owned_files": [
        "tests/migration/mcp_v2/test_compatibility_matrix.py",
        "tests/security/test_session_provenance.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -m py_compile tests/migration/mcp_v2/test_compatibility_matrix.py tests/security/test_session_provenance.py",
        "PYTHONPATH=src ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py tests/security/test_session_provenance.py -m \"core or regression or mcp_v2\" -k \"stdio or http or application_handle or reconnect or adapter_parity\""
      ],
      "acceptance": [
        "Supported adapters report identical effective target, default invariance, replay cardinality, and typed error category.",
        "Reconnect identity is server-owned and cross-session isolation remains exact.",
        "Artifact is provider-neutral and secret-free.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-CORE-VAL.1",
        "SBR-CORE-VAL.3",
        "SBR-CORE-VAL.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-REL-VAL.3",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "benchmarks/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 18,
      "suggested_specialist": "crucible",
      "contracts": [
        "`AdapterParityCase` identifies direct dispatch, modern stdio, modern streamable HTTP, legacy stdio, and supported legacy HTTP/SSE.",
        "`run_adapter_parity_trace(case: AdapterParityCase, trace: CompactSwarmTrace) -> AdapterParityResult`",
        "`adapter-parity.json` records source revision, supported/unsupported reason, effective targets, default before/after, replay cardinality, identity/reconnect result, typed error category, and verdict; no secret payloads."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-REL-VAL.5",
      "title": "Single-lane release runner and C-15 evidence",
      "goal": "Provide the thin operator entrypoint that serializes the complete reference gate and emits the only `ReliabilityReleaseEvidenceV1` from same-revision subordinate evidence.",
      "owned_files": [
        "benchmarks/swarm_concurrency.py"
      ],
      "verification": [
        "PYTHONPATH=src ./.venv/bin/python -m py_compile benchmarks/swarm_concurrency.py",
        "PYTHONPATH=src ./.venv/bin/python benchmarks/swarm_concurrency.py --help",
        "SCRIBE_SWARM_DISPOSABLE=1 SCRIBE_TEST_POSTGRES_URL=\"$SCRIBE_TEST_POSTGRES_URL\" SCRIBE_SWARM_PROFILE=release SCRIBE_SWARM_CALLERS=64 SCRIBE_SWARM_SMOKE_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_WARMUP_SECONDS=300 SCRIBE_SWARM_DURATION_SECONDS=1800 SCRIBE_SWARM_RECOVERY_SECONDS=300 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/sbr-2.15.0 PYTHONPATH=src ./.venv/bin/python benchmarks/swarm_concurrency.py --profile release --target-version 2.15.0 --postgres-url-env SCRIBE_TEST_POSTGRES_URL --results-dir benchmarks/artifacts/sbr-2.15.0"
      ],
      "acceptance": [
        "Exactly one exclusive runner owns every repository-saturating reference action and records exact commands/environment/revision.",
        "C-15 is machine-readable, secret-free, same-revision, digest-linked, and every required verdict is `PASS`.",
        "Queue fairness/backpressure/no-HOL, adapter parity, import/RSS/ready/hot-path, 32-caller smoke, soak, and teardown are represented.",
        "Missing, mixed, dirty, leaked, or failed evidence prevents PASS and returns nonzero.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-REL-VAL.1",
        "SBR-REL-VAL.2",
        "SBR-REL-VAL.3",
        "SBR-REL-VAL.4"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-REL-VAL.5",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality",
        "security"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter",
        "sentinel"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "src/**",
        "tests/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "wave": 19,
      "suggested_specialist": "crucible",
      "contracts": [
        "`main(argv: Sequence[str] | None = None) -> int`",
        "`build_release_evidence(*, source_revision: str, target_version: str, core: Mapping[str, object], postgres: Mapping[str, object], adapters: Mapping[str, object], startup: Mapping[str, object], queue: Mapping[str, object], artifact_paths: Sequence[Path], exact_commands: Sequence[str], environment_fingerprint: Mapping[str, object]) -> ReliabilityReleaseEvidenceV1`",
        "`reliability-release-evidence.json` has exactly frozen C-15 top-level fields: `source_revision`, `target_version` (`2.15.0`), `core_verdict`, `postgres_smoke_verdict`, `adapter_parity_verdict`, `import_budget_verdict`, `startup_budget_verdict`, `queue_budget_verdict`, `artifact_paths`, `exact_commands`, `environment_fingerprint`. Verdicts are `PASS` or `FAIL`; detail stays in referenced artifacts.",
        "`reliability-release-evidence.md` is JSON-derived only."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-RELEASE.1",
      "title": "Synchronize 2.15.0 release truth and open the governed dev PR",
      "goal": "Apply exactly one additive MINOR bump from the current `2.14.1` package manifest to `2.15.0`, add the runtime package version, and make README release notes plus both public release maps tell the same standalone Scribe truth. Preserve the validated implementation revision as the sole parent of the release-truth commit, then use authorized Git custody for one commit, one branch push, and one PR whose base is `dev`.",
      "owned_files": [
        "pyproject.toml",
        "src/scribe_mcp/__init__.py",
        "README.md",
        "docs/RELEASE_SURFACE.md",
        "docs/RELEASE_FILE_MAP.md"
      ],
      "verification": [
        "test -s benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json",
        "./.venv/bin/python -c 'import json, pathlib, subprocess; p=pathlib.Path(\"benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json\"); e=json.loads(p.read_text()); verdicts=(\"core_verdict\",\"postgres_smoke_verdict\",\"adapter_parity_verdict\",\"import_budget_verdict\",\"startup_budget_verdict\",\"queue_budget_verdict\"); assert e[\"target_version\"] == \"2.15.0\"; assert all(e[k] == \"PASS\" for k in verdicts); assert e[\"source_revision\"] == subprocess.check_output([\"git\",\"rev-parse\",\"HEAD\"], text=True).strip(); assert e[\"artifact_paths\"] and all(pathlib.Path(x).exists() for x in e[\"artifact_paths\"]); assert e[\"exact_commands\"] and e[\"environment_fingerprint\"]'",
        "PYTHONPATH=src ./.venv/bin/python -c 'import tomllib, scribe_mcp; assert tomllib.load(open(\"pyproject.toml\",\"rb\"))[\"project\"][\"version\"] == \"2.15.0\"; assert scribe_mcp.__version__ == \"2.15.0\"; assert \"__version__\" in scribe_mcp.__all__'",
        "./.venv/bin/python -c 'from pathlib import Path; r=Path(\"README.md\").read_text(); s=Path(\"docs/RELEASE_SURFACE.md\").read_text(); m=Path(\"docs/RELEASE_FILE_MAP.md\").read_text(); assert \"Release contract: ",
        "PYTHONPATH=src ./.venv/bin/pytest -q tests/test_versioning_behavior.py tests/doc_management/test_version_context.py",
        "PYTHONPATH=src ./.venv/bin/pytest -q tests/migration/mcp_v2/test_compatibility_matrix.py::test_source_rollback_shadow_restores_prior_dependency_without_mutating_worktree",
        "git diff --check -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md",
        "git diff --name-status -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md",
        "case \"$(git branch --show-current)\" in \"\"|main|dev) exit 1;; esac",
        "test \"$(git remote get-url origin)\" = \"https://github.com/CortaLabs/scribe_mcp.git\"",
        "git add -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md",
        "diff -u <(printf '%s\\n' README.md docs/RELEASE_FILE_MAP.md docs/RELEASE_SURFACE.md pyproject.toml src/scribe_mcp/__init__.py | sort) <(git diff --cached --name-only --diff-filter=ACMRT | sort)",
        "git diff --cached --check",
        "! git diff --cached --unified=0 -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md | rg -q 'AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,255}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'",
        "git diff --cached --binary -- pyproject.toml src/scribe_mcp/__init__.py README.md docs/RELEASE_SURFACE.md docs/RELEASE_FILE_MAP.md | sha256sum",
        "git commit -m \"release: scribe-mcp 2.15.0\"",
        "./.venv/bin/python -c 'import json, pathlib, subprocess; e=json.loads(pathlib.Path(\"benchmarks/artifacts/sbr-2.15.0/reliability-release-evidence.json\").read_text()); assert subprocess.check_output([\"git\",\"rev-parse\",\"HEAD^\"], text=True).strip() == e[\"source_revision\"]; assert subprocess.check_output([\"git\",\"show\",\"-s\",\"--format=%s\",\"HEAD\"], text=True).strip() == \"release: scribe-mcp 2.15.0\"'",
        "git show --format=fuller --name-status --stat HEAD",
        "git push -u origin HEAD",
        "test \"$(git ls-remote --heads origin \"$(git branch --show-current)\" | cut -f1)\" = \"$(git rev-parse HEAD)\"",
        "gh pr create --base dev --head \"$(git branch --show-current)\" --title \"release: scribe-mcp 2.15.0\" --body \"Source-only Scribe 2.15.0 release candidate. C-15 PASS for the parent revision. No publish, deploy, runtime adoption, production credential use, or main merge is included.\"",
        "gh pr view --json url,state,baseRefName,headRefName,commits,files,statusCheckRollup"
      ],
      "acceptance": [
        "C-15 is complete, secret-free, same-revision, target `2.15.0`, and all six required verdicts are `PASS`; the eventual release commit parent equals its `source_revision`.",
        "Exactly the five frozen SS-11 paths change and are staged; no implementation, test, schema, generated, operator-local, or unrelated file enters the release commit.",
        "Package metadata and `scribe_mcp.__version__` both equal `2.15.0`; the additive runtime export preserves all existing exports.",
        "README Current release highlights is the synchronized public changelog, and both release maps identify the same version, standalone Scribe contract, owned surfaces, and source-only boundary.",
        "Focused tests, import/version checks, stale-marker checks, `git diff --check`, exact staged-path comparison, and the high-confidence secret scan pass.",
        "One governed commit has subject `release: scribe-mcp 2.15.0`; its pushed remote SHA equals local HEAD.",
        "One PR exists with head equal to the pushed branch and base exactly `dev`; its evidence records the C-15 parent, release commit, patch digest, and explicit no-publish/no-deploy/no-main-merge boundary.",
        "The package changes only generic Scribe behavior: no council_mcp file or import, Council/Aegis/seat/run/work-item/projection authority, Council schema column, or Council execution replay is introduced."
      ],
      "depends_on": [
        "SBR-PLAN-SYNTH-12",
        "SBR-BIND-PERSIST.1",
        "SBR-BIND-PERSIST.2",
        "SBR-BIND-PERSIST.3",
        "SBR-BIND-PERSIST.4",
        "SBR-BIND-PERSIST.5",
        "SBR-RECEIPT.1",
        "SBR-RECEIPT.2",
        "SBR-RECEIPT.3",
        "SBR-BIND-RESOLVE.1",
        "SBR-BIND-RESOLVE.2",
        "SBR-BIND-RESOLVE.3",
        "SBR-BIND-RESOLVE.4",
        "SBR-SCHEMA.1",
        "SBR-SCHEMA.2",
        "SBR-SCHEMA.3",
        "SBR-HOTPATH.1",
        "SBR-HOTPATH.2",
        "SBR-HOTPATH.3",
        "SBR-BG.1",
        "SBR-BG.2",
        "SBR-BG.3",
        "SBR-BG.4",
        "SBR-STARTUP.1",
        "SBR-STARTUP.2",
        "SBR-STARTUP.3",
        "SBR-DOC-DUR.1",
        "SBR-DOC-DUR.2",
        "SBR-DOC-DUR.3",
        "SBR-CORE-VAL.1",
        "SBR-CORE-VAL.2",
        "SBR-CORE-VAL.3",
        "SBR-CORE-VAL.4",
        "SBR-CORE-VAL.5",
        "SBR-REL-VAL.1",
        "SBR-REL-VAL.2",
        "SBR-REL-VAL.3",
        "SBR-REL-VAL.4",
        "SBR-REL-VAL.5"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-RELEASE.1",
      "evidence_requirements": [
        "behavioral",
        "truth",
        "quality"
      ],
      "gates": [
        "crucible",
        "witness",
        "arbiter"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "tests/**",
        "benchmarks/**",
        ".scribe/**",
        ".github/**",
        "CHANGELOG.md",
        "MANIFEST.in",
        "docs/COMPATIBILITY_MATRIX.md",
        "src/scribe_mcp/__main__.py"
      ],
      "wave": 20,
      "suggested_specialist": "forge",
      "contracts": [
        "`pyproject.toml:[project].version = \"2.15.0\"` is package/build metadata truth.",
        "`scribe_mcp.__version__: str = \"2.15.0\"` is additive runtime truth and is exported in `scribe_mcp.__all__`; all existing exports remain unchanged.",
        "`README.md#Current release highlights` is the SS-11 public release-note/changelog surface and must identify `scribe-mcp 2.15.0`, date `2026-09-27`, the validated binding-reliability scope, and the source-only boundary.",
        "`docs/RELEASE_SURFACE.md` must identify the `v2.15.0` public release line and distinguish tracked standalone Scribe source/public docs from operator-local, generated, deployed, or published state.",
        "`docs/RELEASE_FILE_MAP.md` must identify `v2.15.0`, list both version authorities (`pyproject.toml` and `src/scribe_mcp/__init__.py`), identify README release highlights as the public changelog, and state that the PR targets `dev`; promotion/merge to `main` and PyPI publication are later separately authorized actions."
      ],
      "status": "planned"
    },
    {
      "package_id": "SBR-ARCH-06",
      "title": "Scribe Reliability Release Seam Map",
      "goal": "Synthesize the verified binding, efficiency, server-weight, swarm, and background-queue research into one invariant-valid architecture seam map for a single standalone Scribe reliability and performance release, while defining but not owning the upstream Council integration contract.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md"
      ],
      "acceptance": [
        "SEAM_MAP records Q2 decomposition arithmetic and a fan_out or collapse verdict, and validates I1-I6 with pairwise-disjoint owned paths, an acyclic DAG, one producer per concrete contract, bounded assignments, and complete scope coverage.",
        "Subsystems cover generic durable caller-session defaults and explicit cross-repository targeting, typed MCP failures, server import/startup/schema weight, single-context hot paths and telemetry, bounded background execution and managed-document offline replay, concurrency validation, and release/version surfaces.",
        "The map enforces the 500 ms foreground tripwire, startup/RSS/call budgets, at least 32 concurrent callers, no global or persona-keyed interference, no cross-project head-of-line blocking, and one set_project followed by 100 mixed calls.",
        "Scribe subsystems contain no Council/Aegis/work-item/provider-seat/projection logic; the concrete Council adapter contract is documented as an upstream consumer boundary for council_mcp Atlas without assigning council_mcp files to Scribe implementers.",
        "Design assignments are ready for fresh Blueprint detail passes with no shared whole-file ownership and converge on one SemVer release, one governed release commit boundary, and one PR."
      ],
      "depends_on": [
        "SBR-RCA-01",
        "SBR-EFF-02",
        "SBR-PERF-03",
        "SBR-CONC-A5-05"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-ARCH-06",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "pyproject.toml"
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-ARCH-AMEND-REMOTE-08",
      "title": "Remote Binding Test Ownership Amendment",
      "goal": "Resolve the DA-01-discovered source contract conflict by assigning the existing Remote backend no-HTTP expectation to the validation subsystem and updating the accepted seam map without changing production contracts.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/ARCHITECTURE_GUIDE.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/SEAM_MAP_SCRIBE_RELIABILITY_RELEASE.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/ARCHITECTURE_GUIDE.md"
      ],
      "acceptance": [
        "SS-09 and DA-09 own tests/test_remote_backend.py in addition to the existing validation paths, while SS-01 retains remote.py#session_binding_transport and C-01 remains unchanged.",
        "SS-09 and DA-09 are marked seven-path SPLIT_REQUIRED, with detail planning required to separate the Remote expectation from other validation packages.",
        "Q2 arithmetic, I1, I4, and I6 are updated consistently; all other subsystem ownership, contracts, DAG edges, budgets, and Council boundary remain frozen.",
        "ARCHITECTURE_GUIDE records the ownership amendment and removes the DA-01 execution blocker without editing PHASE_PLAN or CHECKLIST."
      ],
      "depends_on": [
        "SBR-DETAIL-DA01"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-ARCH-AMEND-REMOTE-08",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-CONC-04",
      "title": "Scribe Swarm Concurrency Validation Research",
      "goal": "Design a meaningful regression and load matrix for dozens of concurrent seats using shared personas, multiple repositories and projects, explicit cross-project writes, independent reconnects, offline replay, and mixed Scribe operations without cross-talk or global serialization.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md"
      ],
      "acceptance": [
        "Report specifies deterministic correctness tests for at least 32 concurrent caller sessions across multiple repositories and projects, including same agent labels and independent reconnects.",
        "Report specifies performance and soak tests for mixed reads, logs, managed-document writes, explicit project targeting, binding restore, and offline replay with measurable p50, p95, throughput, memory, and error budgets.",
        "Tests prove no seat can clear or mutate another default, explicit target writes land only in the requested project, operations on one repository do not serialize unrelated repositories, and idempotent replay occurs exactly once.",
        "Report identifies the lightest meaningful CI lane plus an operator stress lane that can scale beyond 32 seats without hard-coded Council assumptions in Scribe.",
        "Validation treats 500 ms as the foreground hot-path tripwire and proves background queues are bounded, load balanced, fair across projects, backpressured, observable, and free of cross-project head-of-line blocking."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SBR-CONC-04",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**"
      ],
      "suggested_specialist": "crucible",
      "status": "in_progress"
    },
    {
      "package_id": "SBR-CONC-A5-05",
      "title": "Scribe Background Queue Validation Delta",
      "goal": "Complete the operator-added concurrency validation delta for the 500 ms foreground tripwire and bounded, load-balanced background execution without modifying the completed A1-A4 research artifact or waiting on its stranded terminal claim.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md"
      ],
      "acceptance": [
        "Report defines which generic Scribe operations must remain foreground and which may move behind durable receipts when expected or observed latency exceeds 500 ms.",
        "Report specifies deterministic tests proving background queues are bounded, partitioned or fairly scheduled across projects, backpressured, observable, idempotent, restart-safe, and free of cross-project head-of-line blocking.",
        "Report defines load-balancing, concurrency-limit, retry, overload, cancellation, and shutdown acceptance under at least 32 simultaneous caller sessions without Council-specific logic in Scribe.",
        "Report supplies exact candidate test files, fixtures, metrics, and commands that compose with RESEARCH_SWARM_CONCURRENCY_VALIDATION.md A1-A4."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SBR-CONC-A5-05",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_SWARM_CONCURRENCY_VALIDATION.md"
      ],
      "suggested_specialist": "crucible",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA01",
      "title": "Binding Persistence Detail Plan",
      "goal": "Detail SS-01 only: durable caller-session defaults, binding generations, and cross-backend SessionBindingStoreV2 task packages.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-01 sections contain bounded task packages only for SS-01 owned paths and frozen C-01/C-05 surfaces, with schema-safe ordering and no Council identity.",
        "Each package names exact files or symbol anchors, dependencies, acceptance, tests, verification, out-of-scope, and implementation/validation handoffs.",
        "Checklist ids use SBR-BIND-PERSIST.* and cover generation, unchanged-rebind zero-write, all backends, migration input, and concurrency."
      ],
      "depends_on": [
        "SBR-PLAN-SCAFFOLD-07"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA01",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 41,
          "end_line": 49,
          "anchor_digest": "849f98069ff5f138fbd07303c00770aca68f6a7dc83616fd45bc0f51f2148ff4"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 41,
          "end_line": 45,
          "anchor_digest": "8eb1011f6e4867a4bf58898a671ea81a597ae8c3b4baff6d42261e7a7c630075"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA02",
      "title": "Target Resolution And Typed Errors Detail Plan",
      "goal": "Detail SS-02 only: one-time defaults, request-local cross-repository targets, immutable context, binding receipts, and typed MCP errors.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-02 sections detail only SS-02 and frozen C-01/C-02/C-03/C-04/C-11/C-16, including delayed second-write and explicit cross-repo behavior.",
        "Packages keep persona labels attribution-only, preserve default state, return structured isError failures, and expose the generic Council adapter boundary without Council logic.",
        "Checklist ids use SBR-BIND-RESOLVE.* and include 100-call, ambiguity, stale generation, reconnect, and wrong-target cases."
      ],
      "depends_on": [
        "SBR-DETAIL-DA01"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA02",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 59,
          "end_line": 67,
          "anchor_digest": "95ef42af133b2ea82aa60f3b2d4c8bff67f04bfe0d1c92ff8fdf0db0b9b36b94"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 51,
          "end_line": 55,
          "anchor_digest": "a5e6f96fb4351d13389063d3956e3dc4ca631b993fe44486be02392fc7364793"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA03",
      "title": "Startup And Import Readiness Detail Plan",
      "goal": "Detail SS-03 only: lazy imports/token estimation, core ready semantics, optional service health, and startup status.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-03 details only SS-03 and frozen C-07/C-09/C-10 without scheduler or Council process ownership.",
        "Packages remove eager token weight/import filesystem mutation and defer optional object-store/bridge health behind service states or durable background work.",
        "Checklist ids use SBR-STARTUP.* and enforce import/RSS/ready/outage budgets with safe shutdown."
      ],
      "depends_on": [
        "SBR-DETAIL-DA04",
        "SBR-DETAIL-DA07"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA03",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 95,
          "end_line": 103,
          "anchor_digest": "1e498e4138498198708bfe8f3b11af1ec42cbd6b39f1a16f25eaf4b344543750"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 71,
          "end_line": 75,
          "anchor_digest": "5196add9c56d35551fb7b1b4df817dfb401fb04b01c30a7dab16f4d1abaac55c"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA04",
      "title": "Schema Bootstrap Detail Plan",
      "goal": "Detail SS-04 only: fingerprint fast checks, elected bootstrap, bounded readiness, and migration 007.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-04 details only SS-04, consumes C-05/C-06, and preserves AgentKit migration authority and zero ledger drift.",
        "Packages cover one elected bootstrapper, bounded peer waits, fingerprint mismatch, PostgreSQL/SQLite/init parity, and 32 simultaneous starts.",
        "Checklist ids use SBR-SCHEMA.* and name migration/status/plan/apply plus rollback and import smoke."
      ],
      "depends_on": [
        "SBR-DETAIL-DA01",
        "SBR-DETAIL-DA06"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA04",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 68,
          "end_line": 76,
          "anchor_digest": "577ad08f1d90cc0f3b1478cdb17a0893b5cc6c99a4eb28f514a180cea5e77e9d"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 56,
          "end_line": 60,
          "anchor_digest": "5c4bef63303bb5d4c57169a68b080ce87dc557f57a1054aeaf3e0cc315bc43e9"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA05",
      "title": "Hot Path And Telemetry Detail Plan",
      "goal": "Detail SS-05 only: immutable single-context tool helpers, duplicate-read removal, and correlated timing envelopes.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-05 details only SS-05 and frozen C-04/C-11/C-12, retaining authoritative foreground durability.",
        "Packages eliminate repeated session/project resolution, reuse immutable context in formatters, instrument at least 95 percent of server time, and emit 100/500 ms tripwires.",
        "Checklist ids use SBR-HOTPATH.* and carry p50/p95/p99 plus one-binding-read/one-project-read proof."
      ],
      "depends_on": [
        "SBR-DETAIL-DA02"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA05",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 77,
          "end_line": 85,
          "anchor_digest": "dc2e74a662e26042d4fb00dbb38475fc9084b23db50b976e6f8b567e9145d262"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 61,
          "end_line": 65,
          "anchor_digest": "6c8779e624183ebcabe33bf74f857142ef8b1e1836ff9b812e7e8009a220d88a"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA06",
      "title": "Durable Receipt Store Detail Plan",
      "goal": "Detail SS-06 only: host-neutral durable receipt models, atomic admission/accounting, idempotency, leases/fencing, and storage task packages.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-06 sections contain bounded task packages only for SS-06 owned paths and frozen C-06/C-08 surfaces.",
        "Packages specify atomic item/byte admission, digest conflicts, state versions, leases, fencing, recovery, backend parity, and exact tests.",
        "Checklist ids use SBR-RECEIPT.* and preserve standalone host-neutral Scribe ownership."
      ],
      "depends_on": [
        "SBR-PLAN-SCAFFOLD-07"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA06",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 50,
          "end_line": 58,
          "anchor_digest": "24ad062ef4baff016784b42c980f1dca54bfd28ddbf401397a06f2f55d0b675d"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 46,
          "end_line": 50,
          "anchor_digest": "6e7221145bfae4c7fdc9ebd27cd27a73ac69dbfe07c53070d8568d1337de6534"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA07",
      "title": "Background Scheduler And Lifecycle Detail Plan",
      "goal": "Detail SS-07 only: bounded fair scheduling, lane reserves, workers, retry/cancellation, restart recovery, and shutdown.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-07 details only SS-07 and frozen C-08/C-09 with no provider or Council process policy.",
        "Packages specify item/byte bounds, DRR fairness, global/per-project caps, typed backpressure, leases/fences, finite retry, cancellation, recovery, telemetry, and drain/shutdown.",
        "Checklist ids use SBR-BG.* and include 32-caller no-HOL and zero-lost-receipt acceptance."
      ],
      "depends_on": [
        "SBR-DETAIL-DA06"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA07",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 86,
          "end_line": 94,
          "anchor_digest": "c3c8c890f7cbdf5f4a8b2a47ede4a191f87c4d6073cb34db52f8631bc6f2fe0d"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 66,
          "end_line": 70,
          "anchor_digest": "cef78b544d2884bc45f00cde9af7968292dc7c583c795e46f245ccf7efcee03c"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA08",
      "title": "Managed Document Durability Detail Plan",
      "goal": "Detail SS-08 only: generation-safe managed-document mutation receipts and offline replay using existing apply-preview, CAS, WAL, and atomic-write primitives.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-08 details only SS-08 and frozen C-02/C-03/C-04/C-08/C-09/C-11/C-13, reusing existing mutation primitives.",
        "Packages define queued_offline, generation checks, exactly-once replay, registration/index/quality convergence, conflicts, cancellation, and typed terminal states without a second document engine.",
        "Checklist ids use SBR-DOC-DUR.* and include outage/restart/wrong-target/idempotency tests."
      ],
      "depends_on": [
        "SBR-DETAIL-DA02",
        "SBR-DETAIL-DA06",
        "SBR-DETAIL-DA07"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA08",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 104,
          "end_line": 112,
          "anchor_digest": "1108cf2bb9240068ac566269d4c4ee3a8bdc7333bd24abbaa1b789a826d5ab35"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 76,
          "end_line": 80,
          "anchor_digest": "d0cb64537e6ce3461237386aff42f0bc2814c9b6e6f12253e49921d910d1b223"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA09",
      "title": "Core Reliability Validation Detail Plan",
      "goal": "Detail amended SS-09 only: deterministic 32-session swarm, exact-effects oracle, binding/error/queue/replay/cancellation/shutdown regressions, and the existing Remote backend session-method expectation.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-09 details only amended SS-09 tests, including tests/test_remote_backend.py, and consumes frozen production contracts without changing them; the seven-path assignment must be split into bounded packages.",
        "Packages specify one set_project plus 100 mixed calls per session, delayed second-write, same labels, multiple repos/projects, reconnects, no-HOL, queue bounds, exact replay, typed errors, and the C-01 Remote transport expectation using manual clocks/events.",
        "Checklist ids use SBR-CORE-VAL.* and include exact commands and neighboring/import-smoke gates."
      ],
      "depends_on": [
        "SBR-DETAIL-DA01",
        "SBR-DETAIL-DA02",
        "SBR-DETAIL-DA05",
        "SBR-DETAIL-DA06",
        "SBR-DETAIL-DA07",
        "SBR-DETAIL-DA08"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA09",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 113,
          "end_line": 121,
          "anchor_digest": "b83dba2d74f733be228eb5c7655c06853fc200fcf0898e92397ef49487de4bbd"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 81,
          "end_line": 85,
          "anchor_digest": "b8dba2184520517055b736fa2053591ffc6b1a190546f4abd6ac03647c90d4fb"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA10",
      "title": "Reference Stress And Release Evidence Detail Plan",
      "goal": "Detail SS-10 only: PostgreSQL/process stress, public adapter parity, import/RSS/startup/queue budgets, and ReliabilityReleaseEvidenceV1.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-10 details only SS-10 and frozen C-07/C-10/C-12/C-14/C-15 using disposable reference profiles and no production credentials.",
        "Packages define one repository-saturating lane, exact environment/source revision, 32-caller stress, import/RSS/ready/hot-path budgets, adapter parity, and machine-readable evidence.",
        "Checklist ids use SBR-REL-VAL.* and require every verdict PASS for one revision."
      ],
      "depends_on": [
        "SBR-DETAIL-DA03",
        "SBR-DETAIL-DA04",
        "SBR-DETAIL-DA05",
        "SBR-DETAIL-DA09"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA10",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 122,
          "end_line": 130,
          "anchor_digest": "0805834775953c5ca856f3a05935034c904c12b6ddcddc39e7d8b4bfd85507dd"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 86,
          "end_line": 90,
          "anchor_digest": "612041a1324ea5bad8a066bd52b4bb82c20a86346f35a3d49d64835492c2daaf"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-DETAIL-DA11",
      "title": "Release Surfaces Detail Plan",
      "goal": "Detail SS-11 only: version 2.15.0 and public standalone Scribe release truth after all validation passes.",
      "owned_files": [],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "DA-11 details only SS-11 and frozen C-15 after all gates, with one backward-compatible MINOR bump to 2.15.0.",
        "Packages update pyproject, runtime version, README and release maps together and specify one governed release commit, push, and PR without deploy/publish/main merge.",
        "Checklist ids use SBR-RELEASE.* and include diff, secret, version, changelog/docs, branch, remote, and PR evidence."
      ],
      "depends_on": [
        "SBR-DETAIL-DA10"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-DETAIL-DA11",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "owned_regions": [
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
          "kind": "line_span",
          "start_line": 131,
          "end_line": 138,
          "anchor_digest": "ad1c1cf2e8807328dccd60c4b41b53bf7b98a16dfb1aa0c4da32187ab67a320d"
        },
        {
          "path": ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md",
          "kind": "line_span",
          "start_line": 91,
          "end_line": 95,
          "anchor_digest": "0544f9c829e223b537d217d03040f045bb717ca167e35482e025b122a56634d5"
        }
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-EFF-02",
      "title": "Scribe Binding Efficiency And Ownership Research",
      "goal": "Measure Scribe binding and steady-state call costs, identify redundant database, filesystem, inventory, and transport work, and map a clean generic Scribe versus Council-owned integration boundary that supports swarm engineering across projects and repositories.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BINDING_EFFICIENCY_AND_OWNERSHIP.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BINDING_EFFICIENCY_AND_OWNERSHIP.md"
      ],
      "acceptance": [
        "Report measures or derives current cold set_project, warm rebind, inventory rendering, explicit-project resolution, and repeated-call costs with exact source paths.",
        "Report identifies redundant database, filesystem, formatting, and transport work and proposes measurable warm-path budgets plus a 100-call no-rebind throughput test.",
        "Report defines swarm semantics: one stable caller session and default project, explicit targeting of any registered project on the workstation across repositories, no default mutation, exact audit attribution, and disambiguation by project id or root rather than another set_project.",
        "Report draws a strict source-authority boundary: generic public Scribe mechanisms in scribe_mcp; Council identities, Aegis admission, work-item lifecycle, spawned-seat handoff, and completion projection in council_mcp. No Council-specific schema or logic is proposed for Scribe.",
        "Report includes concurrency-aware cache and storage recommendations that avoid global invalidation, agent-label collisions, connection-local loss, and serialized hot paths under dozens of simultaneous seats."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SBR-EFF-02",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**"
      ],
      "suggested_specialist": "lens",
      "status": "completed"
    },
    {
      "package_id": "SBR-PERF-03",
      "title": "Scribe Server Weight And Latency RCA",
      "goal": "Measure and localize scribe-server startup time, resident memory, import weight, process multiplicity, transport overhead, and hot tool paths so the standalone public server becomes materially lighter and faster without weakening durability.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md"
      ],
      "acceptance": [
        "Report provides reproducible cold and warm startup timing, resident-memory and process-count measurements, and phase attribution for every material cost.",
        "Report maps heavyweight imports, eager initialization, database/bootstrap work, inventory rendering, transport setup, and per-call hot paths to exact Scribe files and symbols.",
        "Report proposes bounded implementation packages and measurable latency, memory, startup, and concurrency budgets while keeping Scribe standalone and free of Council-specific logic.",
        "Report distinguishes generic scribe-server lifecycle and performance from Council-owned spawning, admission, proxying, and process orchestration.",
        "Report classifies every observed or expected foreground call above 500 ms as hot-path excess unless the API is explicitly asynchronous, and identifies which work can move behind durable receipts into bounded background execution.",
        "Background recommendations include partitioning, concurrency limits, backpressure, fairness, retry/idempotency, observability, and load balancing so one project or expensive operation cannot starve unrelated callers."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SBR-PERF-03",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**"
      ],
      "suggested_specialist": "mantis",
      "status": "completed"
    },
    {
      "package_id": "SBR-PLAN-SCAFFOLD-07",
      "title": "Scribe Reliability Detail Planning Scaffold",
      "goal": "Project the accepted SEAM_MAP into the canonical architecture, phase-plan, and checklist documents and create one stable managed section for each DA-01 through DA-11 so fresh detail planners can own disjoint regions safely.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/ARCHITECTURE_GUIDE.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/ARCHITECTURE_GUIDE.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "ARCHITECTURE_GUIDE replaces template residue with the accepted SEAM_MAP decisions, C-01 through C-16, frozen budgets, standalone Scribe source boundary, and external Council consumer boundary.",
        "PHASE_PLAN contains one stable section and anchor for every DA-01 through DA-11, ordered by the seven DAG layers and populated with the accepted subsystem, inputs, owned paths, and detail-pass handoff without inventing implementation decisions.",
        "CHECKLIST contains matching DA-01 through DA-11 sections and stable ids/prefixes for later detail packages, plus final release and joint acceptance gates.",
        "The three managed docs pass quality and handoff checks with no scaffold residue or conflicting ownership, enabling digest-scoped region custody for parallel detail batches."
      ],
      "depends_on": [
        "SBR-ARCH-06"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-PLAN-SCAFFOLD-07",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "pyproject.toml",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md"
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-PLAN-SYNTH-12",
      "title": "Implementation Registry Synthesis",
      "goal": "Synthesize the accepted SS-01 through SS-11 detail packages into registered, dependency-ordered, file-disjoint implementation work items without changing the frozen architecture or crossing the Council-owned seam.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/WORK_ITEMS.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/CHECKLIST.md"
      ],
      "acceptance": [
        "Every executable PHASE_PLAN package has one manifest work item with exact owned files, forbidden files, dependencies, specialist, verification commands, and checkable acceptance criteria.",
        "Implementation work items preserve the frozen provider-neutral Scribe contracts and explicitly forbid council_mcp files and Council/Aegis/seat/work-item semantics.",
        "The implementation frontier is safe for parallel dispatch, repository-saturating validation remains serialized, and the 2.15.0 release package depends on all same-revision PASS gates."
      ],
      "depends_on": [
        "SBR-DETAIL-DA11"
      ],
      "doc_ref": "PHASE_PLAN.md#SBR-PLAN-SYNTH-12",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/**",
        "tests/**",
        "pyproject.toml",
        ".council/**",
        ".claude/**",
        ".codex/**"
      ],
      "suggested_specialist": "blueprint",
      "status": "completed"
    },
    {
      "package_id": "SBR-RCA-01",
      "title": "SBR RCA 01",
      "goal": "Reproduce and localize reported Scribe binding loss and typed-error defects; inspect Council integration read-only and identify exact repair boundaries.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BINDING_RCA.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_binding_reliability_repair_20260927/research/RESEARCH_BINDING_RCA.md"
      ],
      "acceptance": [
        "Report contains verified incident traces, causal source paths, existing regression coverage, and bounded repair recommendations; no source mutations.",
        "Report models set_project or bind_project as a one-time caller-session default selection rather than a repository lock; later explicit project arguments may target any registered Scribe project, including projects in other repositories, without repeated set_project and without changing the default project.",
        "Cross-repository explicit targeting resolves the target project's own persisted project identity and canonical root, disambiguates same-name projects by stable project id or explicit root with typed candidates, and never chooses by a shared agent or persona label.",
        "Report identifies exact source and regression boundaries for default binding durability, explicit cross-project and cross-repository operations, concurrent-seat isolation, and unchanged ambient state.",
        "Report preserves repository source authority: Scribe contains only generic public project, caller-session, targeting, durability, error, and performance contracts; all Council, Aegis, work-item, provider-seat, and projection orchestration logic remains upstream in council_mcp.",
        "Report treats 10-plus concurrent agents across repositories as the normal operating case and identifies every global, agent-name keyed, connection-local, or mutable-default state that can cause interference."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SBR-RCA-01",
      "evidence_requirements": [],
      "gates": [],
      "suggested_specialist": "mantis",
      "status": "completed"
    },
    {
      "package_id": "SBR-OBJKEY-BUG-13",
      "title": "Restore Scribe backup sync policy",
      "goal": "Diagnose and repair the pre-existing should_sync regression where .scribe/backups/*.bak is rejected despite the repository contract requiring backup artifacts to sync.",
      "wave": 1,
      "depends_on": [],
      "owned_files": [
        "src/scribe_mcp/object_store/keys.py",
        "tests/test_object_store.py"
      ],
      "forbidden_files": [
        "src/council_mcp/**",
        "council_mcp/**",
        ".council/**",
        ".claude/**",
        ".codex/**",
        "pyproject.toml",
        "README.md",
        "docs/**"
      ],
      "verification": [
        "./.venv/bin/pytest -q tests/test_object_store.py",
        "PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp.object_store.keys import should_sync'"
      ],
      "acceptance": [
        "A repository-local .scribe/backups/file.bak is accepted by should_sync while unrelated .bak files remain rejected unless already promised by the existing contract.",
        "The full tests/test_object_store.py module exits zero without weakening existing inclusion or exclusion cases.",
        "The change is isolated from the SBR-STARTUP.2 setup/probe implementation and adds no Council-specific behavior."
      ],
      "evidence_requirements": ["behavioral", "truth"],
      "gates": ["crucible", "witness"],
      "suggested_specialist": "mantis"
    }
  ]
}
```
