---
visibility: internal
owner_principal_id: crucible_sbr_schema_2_review_1
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: ee52bb27e0ac2baf3a54b15ac0c8fa9fc05359a85f9a8690ea5577896c9cc5de
title: 'Review Report: Behavioral Review Stage'
related_docs: []
last_updated: 2026-09-28 06:11:25 UTC
created_by: agent-20260928-055757-77509262
maintained_by: agent-20260928-055757-77509262
status: complete
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 06:10:33 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 06:11:25 UTC
  last_edited_by: agent-20260928-055757-77509262
  last_action: frontmatter_update
summary: 'Crucible behavioral FAIL for SBR-SCHEMA.2: legacy SQLite C-05 checks and
  C-06 operation-id nullability do not match fresh/PostgreSQL semantics.'
owners:
- Crucible
tags:
- SBR-SCHEMA.2
- behavioral-review
- fail
- sqlite
- postgresql
---

# Review Report: Behavioral Review Stage

**Review Date:** 2026-09-28 06:09:39 UTC
**Reviewer:** crucible_sbr_schema_2_review_1
**Project:** scribe_binding_reliability_repair_20260927
**Stage:** behavioral_review
**Review Type:** Post-Implementation

---

<!-- ID: executive_summary -->
## Executive Summary

**Verdict: FAIL.** SBR-SCHEMA.2 revision `f96e7c46312370438388453e23d90cbd3eff6013275490f47437be3f5332c521` is not behaviorally adequate for A1-A5.

The admitted scoped suite is green (24 passed, 1 skipped), PostgreSQL `init.sql` statically mirrors migration 007's C-05/C-06 fields and domains, and the Forge probe proves fresh/legacy backfill plus reopen preservation on valid rows. Those results do not cover the decisive negative behaviors. Current SQLite source leaves upgraded legacy `session_projects` without the C-05 checks present on fresh SQLite/PostgreSQL, and SQLite C-06 leaves `operation_id` nullable despite PostgreSQL primary-key nullability. A1 therefore fails and A3 is not reliably enforced after legacy upgrade.

DA-09/DA-10 named tests remain later gates; their absence is not the reason for this FAIL. The blocker is a current source-level contract mismatch.

---

<!-- ID: phase_review_results -->
## Acceptance Review Results

| Criterion | Result | Evidence |
|---|---|---|
| A1 one logical C-05/C-06 schema | **FAIL** | Fresh SQLite has positive generation, state domain, nonempty-key, and state-consistency checks at `schema.py:107-131`; legacy ALTER at `schema.py:742-758` adds columns/defaults only. C-06 `operation_id TEXT PRIMARY KEY` lacks explicit `NOT NULL`, unlike PostgreSQL PK semantics. |
| A2 idempotent/preserving reopen | Partial pass | Forge's recorded in-memory probe passed valid-row fresh/legacy/reopen preservation; admitted suite passed. It did not assert upgraded-row negative constraints. PostgreSQL was inspected statically, not freshly executed in this review. |
| A3 project_name compatibility; key/generation authoritative | **FAIL** | Backfill preserves `project_name` and does not recompute already-resolved rows, but an upgraded legacy table can accept `binding_generation <= 0`, arbitrary `binding_state`, blank keys, and inconsistent resolved/unresolved tuples. |
| A4 import side-effect free | Pass with supplied-plus-static evidence | Forge's exact import command ran successfully twice in ai-trace. Reviewer-exec index 0 was denied `REVIEW_COMMAND_EFFECTFUL`, so it was not retried. Current module contains declarations/functions only at import boundary. |
| A5 generic Scribe only | Pass | Current owned files contain generic Scribe schema only; no Council authority surface was identified. |

Overall package result follows A1/A3: **FAIL**.

---

<!-- ID: detailed_analysis -->
## Detailed Analysis

### Blocking finding 1 — legacy SQLite C-05 is weaker

The canonical fresh SQLite table declares:

- `project_key` nonempty when non-null;
- `binding_generation >= 1`;
- `binding_state IN ('resolved', 'unresolved')`;
- resolved/unresolved key-and-reason consistency.

The upgrade function adds `project_key TEXT`, `binding_generation INTEGER NOT NULL DEFAULT 1`, `binding_state TEXT NOT NULL DEFAULT 'unresolved'`, and `binding_state_reason TEXT`, then normalizes only currently inconsistent rows. SQLite cannot gain the missing table checks from those ALTER statements. Reopen is therefore non-destructive for valid rows but does not materialize the same enforced schema: later writes can persist values rejected by fresh SQLite and PostgreSQL.

### Blocking finding 2 — C-06 operation ID nullability differs

SQLite declares `operation_id TEXT PRIMARY KEY CHECK (trim(operation_id) <> '')` without explicit `NOT NULL`. The check evaluates to NULL for a NULL value and therefore does not reject it. SQLite's official CREATE TABLE contract states that ordinary non-integer primary keys permit NULL unless the column is explicitly `NOT NULL`, or the table is `STRICT`/`WITHOUT ROWID`. PostgreSQL primary keys are non-null. This violates requested nullability parity.

Reference: https://www.sqlite.org/lang_createtable.html

### Evidence provenance

- Current Scribe reads: `schema.py` SHA prefix `19aab133a4a5a7e1`, `init.sql` prefix `7b58753777c5e195`, migration 007 prefix `9eda9e27741c18e3`; sizes and current work-item revision match the submitted package.
- Full hashes reproduced in the Forge tool result: `19aab133a4a5a7e1cd09967373bbbaddaeeedd60eebdcba9c8ce086cab8cfe75`, `7b58753777c5e19552683cf4884a4bab602a5dc5dc93d2dd20a9481a75f9ee49`, `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`.
- Completion receipt is reconciled: event `da920625-1ff3-4604-a18c-312db635eac7`, receipt `prj-9aa96df2fb5e899d45855786`.
- ai-trace proves Forge's probe and test execution: `aitrace:v1:codex:d2b97c0512f967c11a2c13820196f75e` / `aitrace:v1:codex:fed0a474b3d153efa0b15930c06650bc`; targeted pytest `aitrace:v1:codex:918f7d7ba2d93aaee5176e72c6438f40` / `aitrace:v1:codex:b633063f3f7d488bed45de41de1cfc94`.
- Fresh reviewer-exec index 1: 24 passed, 1 skipped, exit 0, read-only bubblewrap. The skip is the environment-gated PostgreSQL invariant.
- Direct custom probe/hash commands were denied by the work-item hook because reviewer seats have no implementation claim. No retry or bypass was attempted; the registered review-exec lane was used where allowed.

---

<!-- ID: recommendations -->
## Recommendations

Shortest path back to PASS:

1. Rebuild upgraded legacy `session_projects` into the canonical fresh table shape inside a transaction, copying the normalized rows and preserving `project_name`, `updated_at`, and authoritative key/generation data. Column-only ALTER is insufficient for the required checks.
2. Declare SQLite C-06 `operation_id TEXT NOT NULL PRIMARY KEY`. Ensure reopen/upgrade repairs any database created by the current candidate so `CREATE TABLE IF NOT EXISTS` does not leave the nullable form in place.
3. Re-run an admitted probe that proves both positive preservation and negative rejection after legacy upgrade:
   - generation 0/negative rejected;
   - arbitrary state rejected;
   - resolved-without-key and unresolved-without-reason rejected;
   - NULL operation ID rejected;
   - all 19 C-06 columns, uniqueness, and three indexes present;
   - metadata drift does not rewrite an authoritative binding;
   - binding and receipt rows survive reopen.
4. Preserve the current valid-row/idempotency checks. DA-09/DA-10 may later encode the permanent regression tests, but the repaired revision still needs current behavioral review evidence.

---

<!-- ID: agent_performance_assessment -->
## Test and Evidence Assessment

The supplied tests are real, hermetic, and meaningful for their existing contracts, and the admitted command passed. Under the keep/cut/merge/mark rubric they should be kept.

They are not sufficient for this package's new parity contract:

- `test_session_storage_invariants.py` covers the binding record model and session linkage, not legacy SQLite DDL constraints.
- `test_sqlite_apply_preview_receipts.py` covers apply-preview receipts, not C-06 background receipts.
- `test_bootstrap_postgres_script.py` checks older init/bootstrap behavior and does not compare migration 007 against SQLite.
- Forge's ad hoc probe checks valid-row behavior and two C-06 domain failures, but not legacy C-05 constraint enforcement or NULL primary-key rejection.

The evidence is therefore green but incomplete for A1/A3; a green neighboring suite cannot override the demonstrated schema mismatch.

---

<!-- ID: compliance_verification -->
## Compliance Verification

- Owned implementation files were read only; Crucible made no source, test, plan, config, or generated-file edits.
- Managed output only: this review report plus Scribe audit entries and the formal Council review.
- No full suite, deployment, commit, push, merge, or production action was performed.
- Current work-item truth was read before review; exact revision and reconciled completion receipt were confirmed.
- ai-trace was used to verify the claimed Forge commands and results rather than accepting narration.
- Admitted command executed: `./.venv/bin/pytest -q tests/storage/test_session_storage_invariants.py tests/storage/test_sqlite_apply_preview_receipts.py tests/test_bootstrap_postgres_script.py` → **24 passed, 1 skipped**.
- Reviewer-exec index 0 returned `REVIEW_COMMAND_EFFECTFUL`; per contract it was not retried or bypassed.
- PostgreSQL `init.sql` and migration 007 were inspected for structural parity/idempotency. No fresh live PostgreSQL execution was claimed.

---

<!-- ID: final_decision -->
## Final Decision

**FAIL — NOT READY for Witness.**

Blocking assertions:

1. Legacy SQLite upgrade does not enforce the C-05 constraints that fresh SQLite and PostgreSQL enforce.
2. SQLite C-06 permits NULL `operation_id` because its ordinary TEXT primary key is not explicitly `NOT NULL`.

Formal review must be recorded as `role=crucible`, `evidence_type=behavioral`, `status=fail`, exact revision `f96e7c46312370438388453e23d90cbd3eff6013275490f47437be3f5332c521`.
