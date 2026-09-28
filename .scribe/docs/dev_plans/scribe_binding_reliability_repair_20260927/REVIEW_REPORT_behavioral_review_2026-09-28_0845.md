---
visibility: internal
owner_principal_id: crucible_sbr_schema_2_review_3
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 3df27cd223f53635940d8edc8bf0fc6e2755566a99a160ee349a0eb0b5d09a8f
title: 'Review Report: Behavioral Review Stage'
related_docs: []
last_updated: 2026-09-28 08:47:24 UTC
created_by: agent-20260928-083622-2d7733b2
maintained_by: agent-20260928-083622-2d7733b2
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 08:46:03 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 08:47:24 UTC
  last_edited_by: agent-20260928-083622-2d7733b2
  last_action: frontmatter_update
summary: 'Crucible FAIL for SBR-SCHEMA.2 revision 3c462648: incomplete C-06 equivalence
  introspection and non-intrinsic rollback on copy constraint failure.'
owners:
- Crucible
tags:
- SBR-SCHEMA.2
- behavioral-review
- crucible
- fail
- not-ready-for-witness
verdict: fail
verified_revision: 3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0
---

# Review Report: Behavioral Review Stage

**Review Date:** 2026-09-28 08:45:05 UTC
**Reviewer:** crucible_sbr_schema_2_review_3
**Project:** scribe_binding_reliability_repair_20260927
**Stage:** behavioral_review
**Review Type:** Post-Implementation

---

<!-- ID: executive_summary -->
## Behavioral Review Summary

**Verdict: FAIL**

Revision `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0` is not behaviorally ready for Witness. The fresh admitted hermetic lane is green, the source hashes match the dispatch, and supplied Forge evidence proves the common fresh/legacy/no-op path. Two amended A2 guarantees remain unproven and contradicted by the source:

1. C-06 equivalence introspection omits material frozen constraints and can classify a weakened table as canonical, skipping rebuild.
2. Copy failure does not intrinsically roll back the opened transaction because the rebuild uses plain `INSERT INTO ... SELECT` after `BEGIN IMMEDIATE`; SQLite constraint failure defaults to statement ABORT, while the generic executor has no rollback-on-exception contract.

A2 therefore fails. A1, A3, A4, and A5 have supporting evidence but cannot yield an overall PASS.

---

<!-- ID: phase_review_results -->
## Acceptance Results

| Criterion | Result | Evidence |
|---|---|---|
| A1 — fresh PostgreSQL / fresh SQLite / legacy SQLite logical C-05/C-06 parity | PASS with risk | Fresh source inspection matches the declared field/state/default shape; supplied disposable legacy probe passed. The A2 introspection defect can leave a weakened pre-existing C-06 table uncorrected. |
| A2 — gated rebuild, exact preservation, no-op reopen, rollback | **FAIL** | `BACKGROUND_RECEIPTS_CANONICAL_PREDICATE` does not cover all frozen checks; plain copy INSERT does not force transaction rollback on constraint failure. |
| A3 — `project_name` compatibility with authoritative key/generation | PASS | Fresh source inspection and supplied probe preserve/read legacy `project_name`, `project_key`, generation, state, reason, and timestamp. |
| A4 — side-effect-free schema imports | PASS from supplied exact-revision evidence | Current source hash matches Forge evidence. Fresh reviewer-exec rejected pycompile/import as `REVIEW_COMMAND_EFFECTFUL`; Forge paired evidence shows both passed at the reviewed hash. |
| A5 — generic Scribe boundary | PASS | Owned source contains no Council import or Council/Aegis/seat/work-item/projection/replay authority. Fresh diff check passed. |
| Testing Standard | **FAIL for required behavior coverage** | Fresh narrowed lane passed 24 tests, but repository search found no committed test or disposable probe that weakens one omitted C-06 constraint and proves introspection rebuilds it, nor a persistent-executor copy-failure rollback probe. DA-09/DA-10 conditional nodes are future-owned and are not themselves failures. |

---

<!-- ID: detailed_analysis -->
## Findings and Evidence

### F1 — C-06 introspection is incomplete

The canonical C-06 table at `schema.py:454-578` and migration 007 at `007_reliability_receipts.sql:169-285` require more than column/default/index shape. The introspection predicate at `schema.py:725-763` checks selected fragments only. It omits, among other frozen rules:

- non-empty `idempotency_key` and `durability_class`;
- explicit non-negative `attempt_count` and `fencing_token`;
- `cancel_requested IN (0, 1)` and timestamp ordering;
- complete accepted/ready/leased/retry_wait/succeeded/failed_terminal/cancelled nullability and counter rules.

A table can therefore retain the exact column signature, unique key, three indexes, state domain, and the searched fragments while weakening or deleting an omitted rule. The predicate evaluates canonical, so `_table_requires_rebuild` returns false and no repair occurs. This violates the amended requirement that absent or non-equivalent frozen constraints trigger the bounded rebuild.

### F2 — copy failure rollback depends on connection disposal

`_rebuild_table_statements` opens `BEGIN IMMEDIATE` and copies with plain `INSERT INTO ... SELECT` at `schema.py:867-880`. A constraint error on that INSERT uses SQLite's default ABORT behavior: the statement fails, but the transaction is not guaranteed to roll back. The generic `ExecuteManyFn` contract carries no rollback-on-exception guarantee. Current `SQLiteInternals._execute_many_writes` iterates statements then commits, and its pooled connection release path does not roll back before reuse.

The supplied invalid-row probe passed because initialization ran before the pool existed and the transient connection was closed after the exception. That demonstrates one concrete caller path, not the public helper's fail-closed transaction contract. Use a rollback conflict action or an explicit executor rollback contract and prove the same persistent connection is no longer in a transaction after failure.

### Evidence provenance

Fresh evidence:
- admitted command index 2: 24 passed in 2.68s, read-only sandbox;
- admitted command index 5: diff check exit 0;
- current `schema.py` hash `aaf74ca1eaf9ec0f10cfe515f79155951c73ea3bf8b8342110329b6fccde2716`;
- current `init.sql` hash `7b58753777c5e19552683cf4884a4bab602a5dc5dc93d2dd20a9481a75f9ee49`;
- fresh source/test search found no coverage for the two failing edge contracts.

Supplied exact-revision evidence verified through ai-trace:
- pytest call/result: `aitrace:v1:codex:2aa21b24757db262dd8c1a160f2ae7d5` / `aitrace:v1:codex:de3e04f11ddc4344d304069810ee7ade`;
- legacy/rollback probe call/result: `aitrace:v1:codex:834999122e6b3638c3ab8fb3568aa8ff` / `aitrace:v1:codex:2a08bb7d403bde14b03144fa224e244e`;
- no-rebuild probe call/result: `aitrace:v1:codex:8b8a04670299fe0ec487d423056a7eca` / `aitrace:v1:codex:0e35fee2a7bd2871c359cb48962dd45f`;
- pycompile call/result: `aitrace:v1:codex:9f7f88809fff4ec282fadc8f00098e8f` / `aitrace:v1:codex:2205c7cf0c39202320cde2860f83af5e`;
- import call/result: `aitrace:v1:codex:25e243808338005eb11221ed46be7914` / `aitrace:v1:codex:746a95b228471d87af3021eb3c4fcf59`.

---

<!-- ID: recommendations -->
## Required Recovery

Shortest path back to PASS:

1. Expand C-06 canonical equivalence detection so every frozen CHECK/UNIQUE/index/column invariant is verified, preferably from one canonical normalized contract rather than a selective fragment list.
2. Make the copy operation transaction-rollback-safe independent of connection disposal, for example by using `INSERT OR ROLLBACK INTO ... SELECT` or an executor contract that explicitly rolls back before re-raising.
3. Add disposable regressions that:
   - create an otherwise canonical C-06 table with one omitted rule weakened (ready/retry_wait/cancelled is sufficient), confirm introspection requests rebuild, then prove the invalid write is rejected;
   - run an invalid legacy copy through a persistent connection/executor and assert `in_transaction == false`, the original table/row remains, no replacement table remains, and a subsequent write is not locked.
4. Re-run pycompile/import, the 24-test lane, the amended disposable probe, and diff check at a new exact revision.

No DA-09/DA-10 future node is required to exist for this package review; the disposable recovery probes are sufficient.

---

<!-- ID: agent_performance_assessment -->
## Scope and Provenance Assessment

Forge stayed within the two owned production files and preserved `init.sql`. The implementation improved the prior unconditional-rebuild design substantially: it added per-table gating, exact operation-id NOT NULL in SQLite, copy/value validation, post-rebuild FK/index/trigger validation, a matching-schema no-op, and supplied honest tool evidence.

The remaining defects are contract-completeness issues, not evidence fabrication. The supplied probes prove the cases they actually exercised but do not cover subtly non-equivalent C-06 tables or persistent-executor copy failure.

---

<!-- ID: compliance_verification -->
## Commands and Coverage

Fresh admitted commands:

- command index 2 — `./.venv/bin/pytest -q tests/storage/test_session_storage_invariants.py::test_session_binding_record_v2_contract tests/storage/test_session_storage_invariants.py::test_sqlite_session_linkage_invariants tests/storage/test_sqlite_apply_preview_receipts.py tests/test_bootstrap_postgres_script.py`: **24 passed**, one read-only cache warning.
- command index 5 — `git diff --check -- src/scribe_mcp/storage/sqlite/schema.py src/scribe_mcp/db/init.sql`: **passed**.
- command indexes 0 and 1 — pycompile/import: reviewer infrastructure returned `REVIEW_COMMAND_EFFECTFUL`; no command launched. Exact-revision supplied evidence is cited above.
- conditional DA-09 and DA-10 commands were not run because their named nodes are future-owned and absent by plan condition.

Testing Standard application: the 24 tests are meaningful and hermetic for their stated behavior, but none protects the new introspection/rollback edge contracts. A green existing lane therefore does not satisfy the amended behavioral gate.

---

<!-- ID: final_decision -->
## Handoff

**FAIL — NOT READY FOR WITNESS.**

Behavioral event must remain failed at revision `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0`.

Repair owner: Forge, limited to `src/scribe_mcp/storage/sqlite/schema.py` plus the separately authorized test owner for a durable regression. Re-review only the delta and the two edge probes after a new revision is registered.
