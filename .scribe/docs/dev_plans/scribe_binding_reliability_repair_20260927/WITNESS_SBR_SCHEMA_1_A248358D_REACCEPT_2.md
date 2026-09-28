---
id: scribe_binding_reliability_repair_20260927-witness-sbr-schema-1-a248358d-reaccept-2
title: Witness Sbr Schema 1 A248358D Reaccept 2
doc_type: custom
doc_name: WITNESS_SBR_SCHEMA_1_A248358D_REACCEPT_2
category: verification
status: ready
version: '0.1'
last_updated: 2026-09-28 05:00:57 UTC
maintained_by: agent-20260928-044402-83326ac5
created_by: agent-20260928-044402-83326ac5
owners:
- Witness
related_docs: []
tags:
- witness
- verification
- truth-check
- SBR-SCHEMA.1
summary: PASS truth reacceptance for SBR-SCHEMA.1 at exact revision a248358d; READY
  FOR SENTINEL.
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 04:58:06 UTC
  created_via: create_doc
  last_edited_at: 2026-09-28 05:00:57 UTC
  last_edited_by: agent-20260928-044402-83326ac5
  last_action: frontmatter_update
  stage: truth_check
  work_item_id: 5309eca6-4d91-477e-b0c8-7087b6d65338
verdict: PASS
revision: a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb
evidence_type: truth
---
# Witness Verification Report

<!-- ID: summary -->
## Summary

**Overall: PASS**

**Review boundary:** active SBR-SCHEMA.1 package scope at exact contract revision `a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb`.

The current migration SQL, named PostgreSQL regressions, and aligned PHASE_PLAN bytes match the admitted immutable hashes. The implementation satisfies the frozen C-05/C-06 schema and migration-authority contracts, keeps unresolved legacy rows startup-safe, and introduces no Council authority or schema.

Frontend checks are not applicable.
<!-- ID: rubric -->
## Rubric

- REQUIRED Plan Intent / Authority — **PASS**. Work-item goal, contracts, acceptance criteria, and PHASE_PLAN SBR-SCHEMA.1 are deterministic and authorize only migration 007 plus the two named regressions.
- REQUIRED Import Resolution — **PASS**. No modified production Python module is in boundary. The modified test module's imports/symbols are source-resolved; exact-revision `py_compile` is supplied evidence. Fresh reviewer execution was denied before launch as `REVIEW_COMMAND_EFFECTFUL`, not counted as a fresh pass.
- REQUIRED Symbol Existence — **PASS**. `PostgresStorage`, `set_session_project`, `get_session_project`, `schema.MIGRATIONS_PATH`, and `ensure_schema_on_connection` exist at current source.
- REQUIRED Explicit Contract Match — **PASS**. C-05 binding classification/generation, C-06 receipt shape, readiness metadata, and ledger identity match.
- REQUIRED Boundary Match — **PASS**. Review boundary matches the work-item owned files; PHASE_PLAN explicitly permits the two named test regions and single named trigger replacement.
- REQUIRED Scope Boundary — **PASS**. Current lifecycle attribution names only the owned SQL and test files; no forbidden Council/config/generated paths are attributed to this implementation.
- REQUIRED Command Execution — **PASS with provenance disclosure**. Fresh admitted `git diff --check` passed. PostgreSQL, module, neighbor, compile, and stdio results are supplied exact-revision evidence; denied reviewer commands were not executed or relabeled.
- REQUIRED Plan / Checklist / Scribe Hygiene — **PASS**. PHASE_PLAN is ready and hash-aligned; current Crucible PASS is durable; this report is Scribe-managed.
- REQUIRED Acceptance Criteria — **PASS** for this source package. DA-10/SBR-SCHEMA.GATE retains later backup/apply/restore release proof.
- REQUIRED Testing Standard — **PASS**. Both regressions are marked `postgres` and `regression`; `postgres` is registered as a capability marker; the fixture creates and force-drops a unique database and does not target shared state.
- WARN ONLY — Council's post-review drift disclosure is mtime-attributed, while current full SHA-256 values remain byte-identical to the reviewed artifacts.
- WARN ONLY — Repo-intel could not resolve project/version scope and contributed no proof.
- WARN ONLY — Scribe runtime lacks the prescribed `verification` doc type; this report uses a supported custom scaffold with verification metadata.
<!-- ID: evidence -->
## Evidence

### Exact revision and artifact identity

- Council current contract revision: `a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb`.
- SQL SHA-256: `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`.
- Test SHA-256: `45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055`.
- PHASE_PLAN SHA-256: `7cfee446d5e9f435cfe5562f5cf84cb3a3856458494eca6bd64ecbe5be603db5`.
- Current Crucible behavioral PASS: Council event `9a61ebc4-b6af-40b1-af38-d4c431d179c3`; report SHA-256 `fb01509174dd50e1aaa834f634a643c1ab4882796af51a995df28a8ed9b9cf2d`.
- Transcript reconstruction confirmed the Crucible session and durable formal-review/report actions; session evidence is current. Formal review call: `aitrace:v1:codex:ce022089f6965cdda0252d670eea4d42` with paired result `aitrace:v1:codex:9ebd59b306d66aa7a1e8ba0c59a5eb82`.

### Contract and source truth

- `session_projects_classify_binding` derives `scribe_sessions.repo_root`, matches `scribe_projects` by repository plus project name, accepts a supplied key only on canonical equality, forces inserts to generation 1, preserves stored generation on updates, and increments only when the classified binding tuple changes.
- Stable unresolved reasons are `project_name_absent`, `session_missing`, `project_identity_zero_matches`, `project_identity_ambiguous`, `project_key_missing`, and `project_key_mismatch`. No exception/refusal path exists for unresolved legacy rows.
- `session_projects_binding_state_consistent` enforces resolved = non-null key/no reason and unresolved = null key/nonempty reason.
- `background_receipts` declares exactly 19 ordered columns: operation_id, canonical_project_key, lane, idempotency_key, payload_digest, payload_bytes, durability_class, state, state_version, attempt_count, next_attempt_at, lease_owner, lease_expires_at, fencing_token, cancel_requested, result_ref, error_code, created_at, updated_at.
- Receipt identity is PRIMARY KEY(operation_id) plus UNIQUE(canonical_project_key, idempotency_key). Closed states and state-dependent nullability are enforced. Required claim, lease-recovery, and project-state accounting indexes exist.
- `scribe_schema_readiness` is singleton coordination metadata with schema_fingerprint, migration_version, and updated_at.
- Source search found the numbered migration runner only in `schema.py`; it derives ledger identity as `sql:<filename>` and writes the ledger after SQL succeeds. Migration 007 itself contains no ledger write.
- Destructive-token audit found exactly one allowed statement: `DROP TRIGGER IF EXISTS session_projects_classify_binding ON session_projects`, immediately followed by recreation. No TRUNCATE, DELETE, rename, or other DROP exists.
- Owned-file search found no `council_mcp`, Council, Aegis, work-item, projection, seat, or run authority terms/imports.

### Test and command evidence

Fresh Witness execution:
- `council work review-exec ... --command-index 4 --json` launched once in `bubblewrap-read-only-v1`; `git diff --check -- src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql tests/test_database_migration.py` exited 0.
- Review-exec indices 0-3 were denied before child launch as `REVIEW_COMMAND_EFFECTFUL`; they provide no fresh execution evidence.

Supplied immutable evidence at the exact matching hashes/revision:
- Focused disposable PostgreSQL regressions: 2 passed.
- Full migration module: 10 passed.
- Direct neighbors: 10 passed.
- Capability-free lane: 16 passed, 4 expected skips.
- Test-module `py_compile`: passed.
- Fresh stdio initialize: protocol `2025-11-25`, 35 tools, `sql:007_reliability_receipts.sql` ledger row, and 19 receipt columns.
- Implementer completion/proof action is reconstructed at `aitrace:v1:codex:af1b702d2182f656488fee4ea698515e` with paired result `aitrace:v1:codex:b3d2162cdd8c9998f5678c4824746eb3`. This is accepted as supplied evidence, not a Witness rerun.

No full repository suite was run, as required.
<!-- ID: handoff -->
## Handoff

**PASS — READY FOR SENTINEL.**

The exact-revision truth gate is satisfied. Sentinel should review the same revision and hashes, with emphasis on project-key authorization, unresolved-row isolation, receipt denial-of-service/index behavior, and no-secret receipt fields.

Known non-gating limitations:
- Reviewer-exec permitted only command index 4; indices 0-3 were denied before launch.
- Repo-intel returned unresolved project/version scope and was not used as proof.
- Scribe runtime required a `custom` scaffold because `verification` is not a registered doc type.
