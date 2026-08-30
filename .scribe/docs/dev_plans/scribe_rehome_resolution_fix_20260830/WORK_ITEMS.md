# WORK_ITEMS

```json
{
  "v": 1,
  "project": "scribe_rehome_resolution_fix_20260830",
  "generated_by": "blueprint",
  "items": [
    {
      "package_id": "SCRIBE-REHOME-B1",
      "title": "Repair rehome canonical path resolution and review create dry-run shape",
      "goal": "Restore the governed create -> same-project rehome -> populate workflow by making the canonical doc key resolve the nested target immediately and after rebind, and make special review create dry-runs return a valid non-mutating MCP result.",
      "owned_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "tests/test_manage_docs_cleanup_support.py",
        "tests/test_manage_docs_create_intent.py",
        "tests/test_manage_docs_target_resolution.py"
      ],
      "verification": [
        "uv run pytest -q tests/test_manage_docs_cleanup_support.py tests/test_manage_docs_create_intent.py tests/test_manage_docs_target_resolution.py",
        "uv run python -c 'from scribe_mcp.doc_management.runtime import _handle_rehome_doc, handle_manage_docs_request'"
      ],
      "acceptance": [
        "After a same-project rehome into contracts/REVIEW_CI_RUNNER_01.md, replace_section by doc_name REVIEW_CI_RUNNER_01 resolves and edits the nested target without attempting the removed project-root path.",
        "The canonical nested target mapping survives a fresh project/runtime rebind equivalent used by the test harness.",
        "The source is absent after the move, the nested target exists, and registry/cache state contains no stale canonical mapping that wins resolution.",
        "Special review manage_docs create with dry_run=True creates no file or registration and returns a host-valid MCP content/result shape.",
        "All declared focused tests and runtime import smoke pass."
      ],
      "depends_on": [],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-REHOME-B1",
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "pyproject.toml",
        "src/scribe_mcp/doc_management/manager.py",
        "src/scribe_mcp/server.py",
        "AGENTS.md",
        "CLAUDE.md"
      ],
      "wave": 1,
      "suggested_specialist": "mantis",
      "contracts": [
        "rehome_doc success atomically persists canonical doc-name to nested target-path resolution",
        "dry-run create is non-mutating and host-serializable"
      ],
      "status": "queued"
    },
    {
      "package_id": "SCRIBE-REHOME-B2",
      "title": "Publish 2.14.0 source-level release truth",
      "goal": "Amend the existing version package in place so the additive public action and response feature plus preserved rehome fixes ship as SemVer minor 2.14.0.",
      "owned_files": [
        "pyproject.toml",
        "src/scribe_mcp/__main__.py",
        "README.md"
      ],
      "verification": [
        "uv run python -m scribe_mcp --version",
        "uv run python -c 'import pathlib, tomllib; data=tomllib.loads(pathlib.Path(\"pyproject.toml\").read_text()); assert data[\"project\"][\"version\"] == \"2.14.0\"'",
        "rg -n '2\\.14\\.0|apply_preview|receipt|rehome' README.md pyproject.toml src/scribe_mcp/__main__.py"
      ],
      "acceptance": [
        "pyproject.toml, the CLI version, and README report 2.14.0.",
        "README names automatic apply, durable cross-backend receipt lifecycle, composite rehome recovery, and source-only status.",
        "The current dirty 2.13.2 release edits are preserved while advancing the final minor target."
      ],
      "depends_on": [
        "SCRIBE-REHOME-B3",
        "SCRIBE-DRY-APPLY-V1"
      ],
      "evidence_requirements": [],
      "forbidden_files": [
        "src/scribe_mcp/doc_management",
        "src/scribe_mcp/storage",
        "tests",
        ".claude",
        ".codex"
      ],
      "suggested_specialist": "forge",
      "wave": 8,
      "doc_ref": "PHASE_PLAN.md#SCRIBE-REHOME-B2",
      "contracts": [
        "C-RELEASE-2.14.0"
      ]
    },
    {
      "package_id": "SCRIBE-REHOME-B3",
      "title": "Preserve rehome durability and integrate automatic apply-preview runtime",
      "goal": "Complete the existing dirty rehome repair, route direct and receipt rehome through one composite executor, and expose the minimal public apply contract.",
      "owned_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/doc_management/rehome_transaction.py",
        "tests/test_manage_docs_cleanup_support.py",
        "tests/test_manage_docs_target_resolution.py",
        "tests/test_manage_docs_index_updates.py",
        "tests/test_manage_docs_apply_preview.py"
      ],
      "verification": [
        "uv run pytest -q tests/test_manage_docs_cleanup_support.py tests/test_manage_docs_target_resolution.py tests/test_manage_docs_index_updates.py tests/test_manage_docs_apply_preview.py tests/test_manage_docs_create_intent.py tests/test_manage_docs_session_binding.py tests/test_manage_docs_runtime_action_classification.py tests/test_manage_docs_schema_keystone.py tests/test_mcp_adapter.py tests/test_response_formatter_helpers.py",
        "uv run python -c 'from scribe_mcp.doc_management.runtime import _handle_rehome_doc, handle_manage_docs_request; from scribe_mcp.doc_management.rehome_transaction import execute_rehome_transaction'"
      ],
      "acceptance": [
        "Existing dirty rehome and create-preview behavior is preserved and all named neighbor tests remain green.",
        "Eligible previews automatically expose apply action, opaque receipt, and expiry; apply accepts only the receipt and executes once.",
        "Direct and receipt rehome share one composite executor binding both authorities, paths, files, registries, indexes, preimages, locks, and recovery states."
      ],
      "depends_on": [
        "SCRIBE-REHOME-B1",
        "SCRIBE-DRY-APPLY-I5"
      ],
      "evidence_requirements": [],
      "forbidden_files": [
        "src/scribe_mcp/tools/manage_docs.py",
        "src/scribe_mcp/storage",
        "tests/test_manage_docs_create_intent.py",
        "pyproject.toml",
        "src/scribe_mcp/__main__.py",
        "README.md",
        ".claude",
        ".codex"
      ],
      "suggested_specialist": "mantis",
      "wave": 6,
      "doc_ref": "PHASE_PLAN.md#SCRIBE-REHOME-B3",
      "contracts": [
        "C-PUBLIC-APPLY",
        "C-REHOME-COMPOSITE"
      ]
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-R1",
      "title": "SCRIBE DRY APPLY R1",
      "goal": "Map the narrowest reusable implementation seam for automatic manage_docs dry-run apply receipts and verify current MCP SDK v2 branch/release truth without editing source.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/research/RESEARCH_DRY_RUN_APPLY_REUSE.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/research/RESEARCH_DRY_RUN_APPLY_REUSE.md"
      ],
      "acceptance": [
        "Artifact cites exact source paths and symbols for the shared dry-run response seam, action/schema authority, identity/project/CAS/audit primitives, and representative tests.",
        "Artifact distinguishes mutating from read-only dry runs and recommends the smallest additive invocation contract with compatibility risks.",
        "Artifact records evidence-backed local and remote Git/PR status for the MCP SDK v2 migration and current maintenance branch."
      ],
      "depends_on": [],
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/tools/manage_docs.py",
        "tests"
      ],
      "wave": 1,
      "suggested_specialist": "lens",
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-R1"
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-R2",
      "title": "SCRIBE DRY APPLY R2",
      "goal": "Define the minimum safe receipt security contract for applying an exact successful manage_docs mutation preview without client argument reconstruction.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/research/RESEARCH_DRY_RUN_APPLY_SECURITY.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/research/RESEARCH_DRY_RUN_APPLY_SECURITY.md"
      ],
      "acceptance": [
        "Artifact specifies binding, TTL, single-use or idempotent replay, drift, authorization/path recheck, redaction, storage, and audit requirements with stable failure outcomes.",
        "Artifact identifies reusable existing security/session/CAS primitives and rejects any design that trusts client-replayed normalized arguments or leaks internal state.",
        "Artifact gives a PASS or BLOCK decision for the smallest additive public contract described by the SPEC."
      ],
      "depends_on": [],
      "evidence_requirements": [
        "security"
      ],
      "gates": [],
      "forbidden_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/tools/manage_docs.py",
        "tests"
      ],
      "wave": 1,
      "suggested_specialist": "sentinel",
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-R2"
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-P1",
      "title": "SCRIBE DRY APPLY P1",
      "goal": "Synthesize the completed dry-run apply research into one minimal additive architecture and bounded executable implementation packages, carrying the two force-closed security findings as mandatory requirements.",
      "owned_files": [
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/ARCHITECTURE_GUIDE.md",
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/PHASE_PLAN.md",
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/CHECKLIST.md",
        ".scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/WORK_ITEMS.md"
      ],
      "verification": [
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/ARCHITECTURE_GUIDE.md",
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/PHASE_PLAN.md",
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/CHECKLIST.md",
        "test -s .scribe/docs/dev_plans/scribe_rehome_resolution_fix_20260830/WORK_ITEMS.md"
      ],
      "acceptance": [
        "Architecture defines automatic successful-mutation preview exposure and an opaque apply_preview follow-up without prompt/roster/skill edits or client argument reconstruction.",
        "Architecture defines durable fail-closed atomic receipt claim/consume/replay parity across SQLite, PostgreSQL, and Remote backends.",
        "Architecture defines composite rehome source/destination authority, path, file, registry, index, preimage, locking, and recovery semantics.",
        "PHASE_PLAN, CHECKLIST, and WORK_ITEMS contain bounded implementation plus validation/version packages with disjoint ownership and exact commands, preserving existing rehome dirty changes."
      ],
      "depends_on": [],
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src",
        "tests",
        "README.md",
        "pyproject.toml"
      ],
      "wave": 2,
      "suggested_specialist": "blueprint",
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-P1"
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I1",
      "title": "Define durable receipt records and StorageBackend contract",
      "goal": "Introduce the single typed persistence contract every backend must implement, with fail-closed capability semantics and no runtime behavior yet.",
      "wave": 3,
      "depends_on": [],
      "owned_files": [
        "src/scribe_mcp/storage/base.py",
        "src/scribe_mcp/storage/models.py",
        "tests/storage/test_apply_preview_receipt_contract.py"
      ],
      "forbidden_files": [
        "src/scribe_mcp/doc_management",
        "src/scribe_mcp/storage/sqlite",
        "src/scribe_mcp/storage/postgres",
        "src/scribe_mcp/storage/remote.py",
        "src/scribe_mcp/server_sse.py",
        "pyproject.toml",
        "README.md"
      ],
      "verification": [
        "uv run pytest -q tests/storage/test_apply_preview_receipt_contract.py tests/test_storage_models_compatibility.py",
        "uv run python -c 'from scribe_mcp.storage.base import StorageBackend; from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord'"
      ],
      "acceptance": [
        "One typed record and claim contract exists with no plaintext token field and closed lifecycle and claim vocabularies.",
        "Every backend method signature is exact, missing capability fails closed, and focused tests and import smokes pass."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-I1",
      "suggested_specialist": "sia",
      "contracts": [
        "C-RECEIPT-STORAGE"
      ],
      "evidence_requirements": []
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I2",
      "title": "Implement SQLite atomic receipt lifecycle",
      "goal": "Add the receipt table and single-statement issue, fetch, claim, finalize, and cleanup behavior to SQLite.",
      "wave": 4,
      "depends_on": [
        "SCRIBE-DRY-APPLY-I1"
      ],
      "owned_files": [
        "src/scribe_mcp/storage/sqlite/schema.py",
        "src/scribe_mcp/storage/sqlite/apply_preview_receipts.py",
        "src/scribe_mcp/storage/sqlite/__init__.py",
        "tests/storage/test_sqlite_apply_preview_receipts.py"
      ],
      "forbidden_files": [
        "src/scribe_mcp/storage/postgres",
        "src/scribe_mcp/storage/remote.py",
        "src/scribe_mcp/doc_management",
        "pyproject.toml"
      ],
      "verification": [
        "uv run pytest -q tests/storage/test_sqlite_apply_preview_receipts.py tests/test_sqlite_internals.py tests/integration/storage/test_storage_backend_shared_contract.py",
        "uv run python -c 'from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.sqlite.apply_preview_receipts import claim_apply_preview_receipt'"
      ],
      "acceptance": [
        "SQLite persists no plaintext bearer and enforces one atomic claim with monotonic fencing.",
        "Recovery, terminal replay, stale finalize, storage failure, cleanup, tests, and import smokes pass."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-I2",
      "suggested_specialist": "sia",
      "contracts": [
        "C-SQLITE-PARITY"
      ],
      "evidence_requirements": []
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I3",
      "title": "Implement PostgreSQL receipt schema, migration, and atomic lifecycle",
      "goal": "Provide fresh-install and upgrade-safe PostgreSQL parity using server-side atomic conditional statements.",
      "wave": 4,
      "depends_on": [
        "SCRIBE-DRY-APPLY-I1"
      ],
      "owned_files": [
        "src/scribe_mcp/storage/postgres/__init__.py",
        "src/scribe_mcp/db/init.sql",
        "src/scribe_mcp/db/postgres_migrations/005_apply_preview_receipts.sql",
        "tests/integration/storage/test_postgres_apply_preview_receipts.py"
      ],
      "forbidden_files": [
        "src/scribe_mcp/storage/sqlite",
        "src/scribe_mcp/storage/remote.py",
        "src/scribe_mcp/doc_management",
        "pyproject.toml"
      ],
      "verification": [
        "uv run pytest -q tests/integration/storage/test_postgres_apply_preview_receipts.py tests/test_postgres_project_identity_scoping.py tests/integration/storage/test_storage_backend_shared_contract.py",
        "uv run python -c 'from scribe_mcp.storage.postgres import PostgresStorage'"
      ],
      "acceptance": [
        "Fresh and migrated PostgreSQL schemas match and migration 005 is additive and idempotent.",
        "Atomic claim, recovery fence, stale finalize, replay, cleanup, tests, and import smoke pass."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-I3",
      "suggested_specialist": "sia",
      "contracts": [
        "C-POSTGRES-PARITY"
      ],
      "evidence_requirements": []
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I4",
      "title": "Implement Remote backend parity and fail-closed transport",
      "goal": "Expose the five backend operations as authenticated internal RPCs while preserving server-side atomicity and public-release denial.",
      "wave": 4,
      "depends_on": [
        "SCRIBE-DRY-APPLY-I1"
      ],
      "owned_files": [
        "src/scribe_mcp/storage/remote.py",
        "src/scribe_mcp/server_sse.py",
        "tests/test_remote_backend.py",
        "tests/security/test_apply_preview_remote_fail_closed.py"
      ],
      "forbidden_files": [
        "src/scribe_mcp/storage/sqlite",
        "src/scribe_mcp/storage/postgres",
        "src/scribe_mcp/doc_management",
        "pyproject.toml"
      ],
      "verification": [
        "uv run pytest -q tests/test_remote_backend.py tests/security/test_apply_preview_remote_fail_closed.py tests/security/test_remote_fail_closed.py",
        "uv run python -c 'from scribe_mcp.storage.remote import RemoteStorageBackend; from scribe_mcp.server_sse import _LEGACY_OPERATION_ALLOWLIST'"
      ],
      "acceptance": [
        "All five methods delegate once and decode safely without client-side CAS emulation.",
        "Public-release transport and connection, auth, timeout, malformed-response, and missing-method failures fail closed."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-I4",
      "suggested_specialist": "sia",
      "contracts": [
        "C-REMOTE-PARITY"
      ],
      "evidence_requirements": []
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I5",
      "title": "Build receipt service, fenced replay, and deterministic multi-path locks",
      "goal": "Implement server-only receipt issuance and apply orchestration independent of the public runtime router.",
      "wave": 5,
      "depends_on": [
        "SCRIBE-DRY-APPLY-I1",
        "SCRIBE-DRY-APPLY-I2",
        "SCRIBE-DRY-APPLY-I3",
        "SCRIBE-DRY-APPLY-I4"
      ],
      "owned_files": [
        "src/scribe_mcp/doc_management/apply_preview.py",
        "src/scribe_mcp/doc_management/manager.py",
        "tests/test_apply_preview_engine.py",
        "tests/security/test_apply_preview_receipt_security.py"
      ],
      "forbidden_files": [
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/storage",
        "src/scribe_mcp/server_sse.py",
        "pyproject.toml",
        "README.md"
      ],
      "verification": [
        "uv run pytest -q tests/test_apply_preview_engine.py tests/security/test_apply_preview_receipt_security.py tests/test_manage_docs_anchor_cas.py tests/test_manage_docs_actor_identity.py tests/test_manage_docs_session_binding.py tests/security/test_project_binding_policy.py",
        "uv run python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewService; from scribe_mcp.doc_management.manager import document_mutation_locks'"
      ],
      "acceptance": [
        "Only exact retained intent can execute, TTL is capped, scope and policy fail closed, and two concurrent applies invoke the executor at most once.",
        "Terminal replay, crash recovery, stale fence denial, storage unavailable, lock order, redaction, tests, and import smokes pass."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-I5",
      "suggested_specialist": "forge",
      "contracts": [
        "C-APPLY-ENGINE"
      ],
      "evidence_requirements": []
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-V1",
      "title": "Validate backend parity, end-to-end behavior, and mandatory security risks",
      "goal": "Provide independent cross-backend and end-to-end proof for the two force-closed findings before release.",
      "wave": 7,
      "depends_on": [
        "SCRIBE-DRY-APPLY-I2",
        "SCRIBE-DRY-APPLY-I3",
        "SCRIBE-DRY-APPLY-I4",
        "SCRIBE-DRY-APPLY-I5",
        "SCRIBE-REHOME-B3"
      ],
      "owned_files": [
        "tests/integration/storage/test_apply_preview_backend_parity.py",
        "tests/integration/test_manage_docs_apply_preview_lifecycle.py"
      ],
      "forbidden_files": [
        "src",
        "pyproject.toml",
        "README.md",
        ".claude",
        ".codex"
      ],
      "verification": [
        "uv run pytest -q tests/integration/storage/test_apply_preview_backend_parity.py tests/integration/test_manage_docs_apply_preview_lifecycle.py tests/storage/test_apply_preview_receipt_contract.py tests/storage/test_sqlite_apply_preview_receipts.py tests/integration/storage/test_postgres_apply_preview_receipts.py tests/test_remote_backend.py tests/security/test_apply_preview_remote_fail_closed.py tests/test_apply_preview_engine.py tests/security/test_apply_preview_receipt_security.py tests/test_manage_docs_apply_preview.py",
        "uv run python -c 'from scribe_mcp.doc_management.apply_preview import ApplyPreviewService; from scribe_mcp.doc_management.runtime import handle_manage_docs_request; from scribe_mcp.storage.sqlite import SQLiteStorage; from scribe_mcp.storage.postgres import PostgresStorage; from scribe_mcp.storage.remote import RemoteStorageBackend'"
      ],
      "acceptance": [
        "Exactly-once claim and terminal replay parity pass for SQLite and PostgreSQL, and Remote proves server-side delegation and fail-closed behavior.",
        "Composite rehome partial crashes recover or stop safely, leakage is absent, and behavioral plus security evidence pass on one revision."
      ],
      "doc_ref": "PHASE_PLAN.md#SCRIBE-DRY-APPLY-V1",
      "suggested_specialist": "crucible",
      "contracts": [
        "C-BEHAVIORAL-SECURITY-EVIDENCE"
      ],
      "evidence_requirements": [
        "behavioral",
        "security"
      ]
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I6",
      "title": "SCRIBE DRY APPLY I6",
      "goal": "Repair automatic receipt issuance for normal edit previews by consuming the canonical hashes.after prediction already returned by manage_docs.",
      "owned_files": [
        "src/scribe_mcp/doc_management/runtime.py"
      ],
      "verification": [
        "uv run pytest -q tests/integration/test_manage_docs_apply_preview_lifecycle.py::test_replace_text_preview_exposes_apply_receipt tests/test_manage_docs_apply_preview.py tests/test_apply_preview_engine.py",
        "uv run python -c 'from scribe_mcp.doc_management.runtime import handle_manage_docs_request'"
      ],
      "acceptance": [
        "A successful eligible replace_text dry run with response.hashes.after receives the compact apply_preview affordance and durable receipt without changing existing response fields.",
        "Ineligible/read-only previews remain without apply, the Crucible regression passes unchanged, and the prior B3/I5 runtime tests remain green."
      ],
      "depends_on": [
        "SCRIBE-REHOME-B3",
        "SCRIBE-DRY-APPLY-I5"
      ],
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "tests",
        "src/scribe_mcp/storage",
        "src/scribe_mcp/doc_management/apply_preview.py",
        "pyproject.toml",
        "README.md"
      ],
      "wave": 8,
      "suggested_specialist": "mantis"
    },
    {
      "package_id": "SCRIBE-MCP-SDK-V2-TEST-FIX",
      "title": "SCRIBE MCP SDK V2 TEST FIX",
      "goal": "Repair the stale MCP SDK v2 compatibility assertion so the hermetic contract test validates the supported 2.x major instead of pinning the installed distribution to 2.0.0.",
      "owned_files": [
        "tests/test_mcp_adapter.py"
      ],
      "verification": [
        "uv run pytest -q tests/test_mcp_adapter.py"
      ],
      "acceptance": [
        "The runtime-selection test passes with installed MCP SDK 2.1.1 while still asserting major 2 and public SDK v2 surfaces.",
        "Malformed versions and unsupported major versions remain rejected by the unchanged neighboring tests."
      ],
      "depends_on": [
        "SCRIBE-REHOME-B3"
      ],
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src",
        "pyproject.toml",
        "README.md"
      ],
      "wave": 7,
      "suggested_specialist": "mantis"
    },
    {
      "package_id": "SCRIBE-DRY-APPLY-I7-REHOME-BINDING",
      "title": "SCRIBE DRY APPLY I7 REHOME BINDING",
      "goal": "Repair the security defect in receipt-based rehome by persisting and executing against the immutable preview-time composite authority, registry, index, file-preimage, mode, and path binding instead of recapturing current registry state.",
      "owned_files": [
        "src/scribe_mcp/doc_management/rehome_transaction.py",
        "src/scribe_mcp/doc_management/runtime.py",
        "src/scribe_mcp/doc_management/apply_preview.py",
        "tests/integration/test_manage_docs_apply_preview_lifecycle.py",
        "tests/security/test_apply_preview_receipt_security.py",
        "tests/test_manage_docs_apply_preview.py"
      ],
      "verification": [
        "uv run pytest -q tests/integration/test_manage_docs_apply_preview_lifecycle.py tests/security/test_apply_preview_receipt_security.py tests/test_manage_docs_apply_preview.py tests/test_apply_preview_engine.py",
        "uv run python -c \"from scribe_mcp.doc_management.apply_preview import ApplyPreviewService; from scribe_mcp.doc_management.rehome_transaction import RehomeCompositeBinding, execute_rehome_transaction; from scribe_mcp.doc_management.runtime import handle_manage_docs_request\""
      ],
      "acceptance": [
        "Receipt-based rehome rejects registry, index, authority, path, mode, or file-preimage drift as unsafe or unknown before mutation.",
        "Recognized partial crash states recover exactly once against the immutable preview binding and terminal replay remains idempotent.",
        "End-to-end tests cover registry/index drift, contradictory authority, partial-crash completion, exactly-once recovery, and terminal replay."
      ],
      "depends_on": [
        "SCRIBE-REHOME-B3",
        "SCRIBE-DRY-APPLY-I5"
      ],
      "evidence_requirements": [],
      "gates": [],
      "forbidden_files": [
        "src/scribe_mcp/storage",
        "src/scribe_mcp/server_sse.py",
        "pyproject.toml",
        "src/scribe_mcp/__main__.py",
        "README.md"
      ],
      "wave": 8,
      "suggested_specialist": "mantis"
    }
  ]
}
```
