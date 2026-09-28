---
visibility: internal
owner_principal_id: witness_sbr_schema_2_review_1
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: c2514659167d440d70d975f2de6f368768022bd4fd47f4dca3410ca6fbb26f98
title: 'Review Report: Truth Check Stage'
related_docs: []
last_updated: 2026-09-28 07:37:17 UTC
created_by: agent-20260928-072141-2f864ee9
maintained_by: agent-20260928-072141-2f864ee9
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 07:36:31 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 07:37:17 UTC
  last_edited_by: agent-20260928-072141-2f864ee9
  last_action: frontmatter_update
  stage: truth_check
  work_item_id: 769f4ed9-3c46-4b50-84a5-002d2eda02f7
summary: 'Witness FAIL for SBR-SCHEMA.2: current SQLite canonical rebuild contradicts
  the active no-rebuild/no-table-copy plan constraint; required neighbor test is also
  mislabeled for live PostgreSQL.'
owners:
- Witness
tags:
- SBR-SCHEMA.2
- truth-review
- witness
- fail
- not-ready-for-sentinel
verdict: fail
verified_revision: f96e7c46312370438388453e23d90cbd3eff6013275490f47437be3f5332c521
---

# Review Report: Truth Check Stage

**Review Date:** 2026-09-28 07:35:20 UTC
**Reviewer:** witness_sbr_schema_2_review_1
**Project:** scribe_binding_reliability_repair_20260927
**Stage:** truth_check
**Review Type:** Post-Implementation

---

<!-- ID: executive_summary -->
## Witness Verification Summary

**Overall: FAIL**
**Review boundary:** active SBR-SCHEMA.2 package scope at contract revision `f96e7c46312370438388453e23d90cbd3eff6013275490f47437be3f5332c521`.

The source/API/parity behavior is largely substantiated, but the implementation violates an explicit sovereign implementation constraint: the active plan forbids SQLite reopen rebuilds and table-copy migrations, while the current implementation unconditionally performs copy/drop/rename rebuilds for both reliability tables on every ensure/reopen. One required neighbor test is also mislabeled and can mutate a live PostgreSQL database without the registered `postgres` marker or cleanup.

A green probe cannot authorize plan divergence. This revision is **NOT READY for Sentinel**.

---

<!-- ID: phase_review_results -->
## Rubric

| Required check | Result | Evidence |
|---|---|---|
| Plan intent / authority | **FAIL** | PHASE_PLAN.md:1010 forbids rebuild/table-copy migration; schema.py:613-651 and 936-937 implement and always execute it. |
| Deterministic intent | PASS | Goal, owned files, forbidden files, signatures, constraints, commands, and A1-A5 are explicit in PHASE_PLAN.md:970-1043 and current work-item readback. |
| Import resolution | PASS | Required symbols exist; exact import smoke exited 0 and resolved SCHEMA_PATH to this checkout. |
| Symbol existence / signatures | PASS | `ensure_reliability_schema(execute_fn: ExecuteFn, execute_many_fn: ExecuteManyFn) -> None` at schema.py:808-811; `create_background_receipt_tables(execute_many_fn: ExecuteManyFn) -> None` at 806-807. |
| Explicit callable contract | PASS | `create_schema` calls `ensure_reliability_schema` exactly once at line 960 and before `create_all_indexes` at 961. |
| C-05/C-06 logical parity | PASS | Current SQLite, init.sql, and migration 007 expose matching logical field/state/uniqueness/default behavior with documented backend type representations. |
| Reopen preservation/idempotence | PASS behaviorally | Supplied recovery probes preserve bindings, receipts, timestamps, foreign keys, triggers, indexes, and second-run state; this does not cure the plan violation. |
| Boundary / scope | PASS with WARN | Current work-item content basis and reviewed artifacts are the two owned files; forbidden-authority scan is clean. Shared unrelated worktree state is non-gating. |
| Command execution | PASS with infrastructure WARN | Registered command index 1 passed 24/1 skip. Exact import smoke was previously executed successfully; this Witness admission's index 0 was denied `REVIEW_COMMAND_EFFECTFUL`. Conditional DA-09/DA-10 nodes are absent/not yet owned. |
| Testing Standard | **FAIL** | Required `tests/storage/test_session_storage_invariants.py` conditionally uses a live `SCRIBE_TEST_POSTGRES_URL` and writes rows, but the PostgreSQL test has neither `@pytest.mark.postgres` nor disposable cleanup. |
| Plan/checklist/Scribe hygiene | **FAIL** | CHECKLIST marks SBR-SCHEMA.2 complete while the implementation contradicts PHASE_PLAN.md:1010. |
| Acceptance completion | **FAIL overall** | Behavioral A1-A5 evidence is green, but required in-scope plan execution is not complete because the implementation mechanism is unauthorized. |

---

<!-- ID: detailed_analysis -->
## Evidence

### Gating mismatch: unauthorized SQLite table rebuild

The sovereign plan states at PHASE_PLAN.md:1010:

- existing SQLite files reopen **without rebuild/data loss**;
- **no table-copy migration is introduced**.

Current source does the opposite:

- schema.py:613-635 builds replacement-table statements using `INSERT ... SELECT`, `DROP TABLE`, and `ALTER TABLE ... RENAME`;
- schema.py:638-651 applies that mechanism to `session_projects` and `background_receipts`;
- schema.py:936-937 creates the receipt table then unconditionally executes the rebuild sequence;
- schema.py:960 runs `ensure_reliability_schema` on every `create_schema`/reopen.

The Crucible repair request called for a canonical rebuild, but the work item remained at the unchanged contract revision and no plan amendment exists. Review-repair prose cannot replace sovereign plan intent.

### Source/interface facts that passed

- Current source hash authority:
  - `schema.py`: `4d541f6e9ca849c6aac05a19147acf274dc47387cdf46402733117fe3b28d0c4`
  - `init.sql`: `7b58753777c5e19552683cf4884a4bab602a5dc5dc93d2dd20a9481a75f9ee49`
  - migration 007: `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`
- Scribe current-byte scans match those hash prefixes and current sizes. Exact implementation hashes were produced by the bound Forge seat: `aitrace:v1:codex:4a1d354095a63d68fcfe936c01cc5cd1` / `aitrace:v1:codex:74cb09c98d878fe5235ce35501cf2edd`.
- Exact import smoke call/result: `aitrace:v1:codex:362a24947e716cee52ac112d962892ac` / `aitrace:v1:codex:48205d0dda0af976130fc60f177e884d`.
- Current Crucible reviewer-exec call/result for the required three-file lane: `aitrace:v1:codex:86df9410d5d952107b767b1c83cbf202` / `aitrace:v1:codex:71a6b0d66088043af0d56bdef57f4c18`.
- Supplied legacy/reopen probe call/result: `aitrace:v1:codex:7d92b134fe9767c94268d0fa3d2d4b7c` / `aitrace:v1:codex:069d02e09634b2553056b3f589363779`.
- Supplied full reopen result: `aitrace:v1:codex:112bf549b989f54cf2e86a34e1a251ec`.
- Diff hygiene call/result: `aitrace:v1:codex:6d0a443b99919466379d6fae05a6922a` / `aitrace:v1:codex:371f3375ae388f64f609d776fb79e9b0`.
- Forbidden-authority scan call/result: `aitrace:v1:codex:42c341d99bea1f6b3d088f31eb0bfcb1` / `aitrace:v1:codex:d24b8fcc3aa5a2971db0fd8f48ecf036`.

### Testing Standard failure

The required neighbor file `tests/storage/test_session_storage_invariants.py` places the SQLite case on `tmp_path`, but its PostgreSQL fixture reads `SCRIBE_TEST_POSTGRES_URL`, opens the configured database, and the test inserts/deletes shared rows without a `postgres` marker or teardown. `pytest.ini` registers `postgres` specifically for tests that require PostgreSQL. The current read-only run skipped this path because the environment variable was absent, so no live state was touched in this review; the test source remains mislabeled/non-hermetic.

---

<!-- ID: recommendations -->
## Required Recovery

This is a discovered contract conflict, not an ordinary source bug.

The coordinator must choose one of two authorized recovery paths:

1. route the affected boundary through Blueprint to amend the plan and task revision to authorize canonical rebuild/table-copy semantics, then re-run implementation validation and Witness; or
2. return to Forge for a plan-compliant legacy enforcement mechanism that does not rebuild/copy tables on reopen.

Separately, the validation package must either mark and clean up the live PostgreSQL neighbor test under its proper test owner or replace it with a disposable PostgreSQL fixture. Witness does not repair either issue.

---

<!-- ID: agent_performance_assessment -->
## Scope and Provenance Assessment

The recovery work was operationally bounded and its behavioral evidence was honest: the bound Forge seat labeled recovery probes, the Crucible seat labeled supplied versus fresh evidence, and current Council truth records the exact revision and hashes. The defect is not evidence fabrication; it is failure to reconcile the requested repair mechanism with the unchanged sovereign plan.

Current shared-worktree noise outside the active package boundary is WARN-only and did not affect this verdict.

---

<!-- ID: compliance_verification -->
## Acceptance and Command Verification

- A1 logical C-05/C-06 schema behavior: supported by current source and scoped test/probe evidence.
- A2 preservation/idempotence behavior: supported by supplied disposable SQLite probes, but implemented through a forbidden rebuild mechanism.
- A3 `project_name` compatibility and authoritative key/generation preservation: supported.
- A4 imports: required symbols resolve; import smoke exited 0 with no observed database/filesystem write side effects.
- A5 no Council/Aegis/seat/work-item/projection authority coupling: source/diff scan found no forbidden vocabulary or `council_mcp` import.

Fresh Witness reviewer-exec command index 1: **24 passed, 1 skipped, 1 read-only cache warning** in 1.98s. The skip is the environment-gated live PostgreSQL invariant. Index 0 was denied by review infrastructure as `REVIEW_COMMAND_EFFECTFUL`; prior exact import execution remains proven by paired ai-trace evidence. Conditional DA-09/DA-10 test nodes are absent from this checkout and remain downstream-owned per the plan.

---

<!-- ID: final_decision -->
## Handoff

**FAIL — NOT READY FOR SENTINEL.**

Return the affected boundary to the coordinator for Blueprint plan repair or a plan-compliant Forge implementation. The formal truth gate must remain failed until:

- the rebuild/table-copy conflict with PHASE_PLAN.md:1010 is resolved under an authorized revision;
- the implementation and checklist agree with that revision;
- required validation tests satisfy the repository Testing Standard; and
- Witness re-verifies the delta at the new exact revision.
