---
visibility: internal
owner_principal_id: sentinel_sbr_schema_007_review_1
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 4b92b66896c39d0cf4072a22968b3a90baa854ef4229398e2f52c8acd04027b5
title: "\U0001F512 Migration 007 accepts forged resolved project keys \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-28 05:32:58 UTC
created_by: agent-20260928-032945-0d10794a
maintained_by: agent-20260928-052402-66746c41
status: ready
canonical_doc_type: security
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 03:37:26 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 05:32:58 UTC
  last_edited_by: agent-20260928-052402-66746c41
  last_action: frontmatter_update
  work_item_id: 5309eca6-4d91-477e-b0c8-7087b6d65338
id: SEC-2026-09-28-0001
doc_type: security
summary: 'Resolved high-severity migration-007 authorization defect: exact-revision
  Sentinel reacceptance confirms canonical repo/project validation and trigger-owned
  monotonic generation.'
owners:
- Sentinel
tags:
- security
- authorization
- postgresql
- migration-007
- SBR-SCHEMA.1
category: security
verdict: PASS
revision: a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb
evidence_type: security
case_status: resolved
---


# 🔒 Migration 007 accepts forged resolved project keys — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** RESOLVED — SECURITY REACCEPTANCE PASS
**Last Updated:** 2026-09-28 UTC

> This report records the blocking security finding, source-level proof, remediation contract, and verification requirements for SBR-SCHEMA.1.

---
## Security Overview
<!-- ID: security_overview -->
**Case ID:** SEC-2026-09-28-0001

**Reported By:** Sentinel (`sentinel_sbr_schema_007_review_1`)

**Verified By:** Sentinel (`sentinel_sbr_schema_007_reaccept_3`)

**Date Reported:** 2026-09-28 UTC

**Severity:** HIGH

**Status:** RESOLVED — exact-revision security reacceptance PASS

**Component:** PostgreSQL migration 007 session-binding isolation

**Reviewed Boundary:** Work item `5309eca6-4d91-477e-b0c8-7087b6d65338`, contract revision `a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb`, SQL SHA-256 `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`, test SHA-256 `45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055`, and plan SHA-256 `7cfee446d5e9f435cfe5562f5cf84cb3a3856458494eca6bd64ecbe5be603db5`.

**Resolution:** Migration 007 now treats caller identity fields as assertions, derives or validates the canonical project key through the session repository plus project name, resets classification fail-closed before resolution, and owns binding generation monotonically from stored OLD state. The current regressions exercise same-repository and cross-repository forged tuples, caller generation jumps, missing/ambiguous identity axes, direct-promotion attempts, replay, receipt constraints, and state nullability.

**Customer Impact After Fix:** The demonstrated forged-key and generation-control paths no longer authorize a resolved binding under the migration trigger. No public HTTP/MCP path supplying `project_key` was identified. PostgreSQL table-owner/superuser DDL such as disabling or dropping enforcement is outside this package's ordinary writer threat boundary and is not claimed as defended by these tests.


---
## Description
<!-- ID: description -->
### Threat Analysis

Assets at risk are canonical project identity, per-session binding integrity, receipt isolation, and generation-based stale-writer fencing. The changed trust edge is a write into `session_projects`: `session_id`, `project_name`, supplied `project_key`, supplied binding state, and supplied generation are untrusted inputs. Canonical authority comes from `scribe_sessions.repo_root` joined to exactly one `scribe_projects` identity with a usable key.

### Vulnerability

The original revision accepted any non-empty supplied `project_key` as a resolved identity and allowed caller-selected positive `binding_generation`. A coherent forged tuple therefore passed the shape CHECK while bypassing repository/project authorization, and a generation jump or rollback weakened stale-writer fencing.

### Remediated Control

At current SQL lines 29-50, the trigger captures a supplied key only for validation, ignores caller generation, and resets every write to keyless unresolved state before classification. Lines 53-84 resolve only when the session exists, `project_name` is present, exactly one same-repository project matches, that project has exactly one usable key, and any supplied key equals the canonical key. Lines 87-96 advance generation only from `OLD.binding_generation` when the stored classification changes.

### Proof Path Closure

The current PostgreSQL regression at `tests/test_database_migration.py:589-652` shows:

- a caller generation update to 999 is ignored;
- a same-repository forged key remains keyless with `project_key_mismatch`;
- a coherent key/name pair from another repository remains keyless with `project_identity_zero_matches`;
- a valid rebind resolves and advances generation by exactly one from OLD truth;
- an INSERT generation of 777 is normalized to 1.

The legacy classification matrix at lines 499-529 preserves missing-name, missing-session, missing-key, zero-match, and ambiguous rows as generation-1 unresolved/keyless rows. Lines 531-565 prove forced promotion is reclassified and an unresolved binding cannot produce a project-keyed receipt. Lines 654-769 verify the frozen receipt columns, nullability, keys, indexes, and representative invalid state tuples.

### Evidence Boundary

Fresh evidence produced by this Sentinel seat is limited to current-byte Scribe reads/hash readback, scoped searches, and admitted `review-exec` command index 4 in `bubblewrap-read-only-v1`: `git diff --check` exited 0 with one child launched and reaped. Disposable PostgreSQL and stdio results are supplied current-revision evidence, not fresh Sentinel execution: focused regressions 2 passed, module 10 passed, neighbors 10 passed, capability-free lane 16 passed with 4 expected skips, and fresh stdio initialize listed 35 tools with migration ledger `sql:007_reliability_receipts.sql` and 19 receipt columns. Crucible PASS event `9a61ebc4-b6af-40b1-af38-d4c431d179c3` and Witness PASS event `91d1fef6-c081-4775-87a4-d43b0dd430a0` cover this exact revision.



---
## Affected Systems
<!-- ID: affected_systems -->
**Affected Areas**

- `src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17-167`
- `src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:169-313`
- `tests/test_database_migration.py:475-829`
- Downstream consumers that treat a resolved `session_projects.project_key` and `binding_generation` as authoritative

**Trust Boundary Result**

The schema no longer collapses “caller supplied an opaque key” into “database proved canonical project identity.” Resolution now requires repository-scoped canonical lookup, and caller generation is discarded.

**Fail-Closed Axes**

Missing project name, missing session, zero project matches, ambiguous project matches, missing canonical key, and supplied-key mismatch all produce `binding_state='unresolved'`, `project_key=NULL`, and a stable non-empty reason. The table CHECK rejects incoherent resolved/unresolved representations when trigger enforcement is bypassed, while the trigger blocks coherent forged tuples during ordinary INSERT/UPDATE execution.

**Receipt and Availability Controls**

`background_receipts` remains exactly 19 columns with operation primary key, project/idempotency uniqueness, closed state values, state-dependent nullability, non-negative counters/fence, digest shape, and claim/recovery/accounting indexes. Stored fields are digests, sizes, opaque references, and error codes rather than payload/error bodies. No secrets or raw DSNs are introduced.

**Generic Scribe Isolation**

Scoped current-byte searches found no Council/Council MCP, Aegis, work-item, seat, projection, or execution-replay authority in either owned file. Migration 007 contains no direct migration-ledger write. Its sole DROP is the allowlisted idempotent replacement of `session_projects_classify_binding`.


---
## Investigation
<!-- ID: investigation -->
### Root Cause

The original trigger treated caller-supplied key and generation fields as authority. Table constraints enforced only tuple shape, not repository-scoped identity. This was an authorization-boundary error analogous to CWE-639/CWE-284, with stale-state fencing weakened by caller-selected generation.

### Remediation Assessment

The repair is minimal and closes the demonstrated path:

1. canonical identity is selected from `NEW.session_id -> scribe_sessions.repo_root` plus `NEW.project_name`;
2. exactly-one project match and exactly-one usable canonical key are required;
3. a supplied key is accepted only if it equals that canonical key;
4. classification begins unresolved/keyless, so every failed axis remains unusable;
5. INSERT generation is always 1;
6. UPDATE generation begins from OLD truth and increments only when canonical classification changes.

### Review of Required Properties

- Same-repository forged key cannot authorize: **PASS**.
- Cross-repository coherent forged tuple remains keyless/unresolved: **PASS**.
- Canonical validation binds session repository and project identity: **PASS**.
- Missing, zero-match, ambiguous, missing-key, and mismatch axes fail closed: **PASS**.
- Caller generation jumps/rollbacks are ignored; valid rebind advances monotonically from OLD truth: **PASS**.
- Direct forced promotion with trigger active cannot make an unresolved row authoritative: **PASS**.
- Binding-state CHECK blocks incoherent tuples if the trigger is disabled: **PASS**.
- Frozen receipt constraints, keys, indexes, and state-nullability expose no demonstrated bypass: **PASS**.
- Startup-safe legacy classification and migration replay/ledger stability: **PASS** on supplied disposable PostgreSQL evidence.
- No Council authority/import/schema leaked into generic Scribe: **PASS**.
- No secret-bearing receipt fields added: **PASS**.

### Residual Boundary

The tests do not claim to resist PostgreSQL table-owner or superuser DDL that disables/drops triggers and rewrites constraints. That actor can dismantle any table-local control and is outside the ordinary application-writer boundary reviewed here. If production credentials are table owners, least-privilege ownership separation remains a deployment-hardening requirement, not a defect proven in this package.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Remediation Implemented

- Replaced supplied-key authority with repository/project canonical derivation and equality validation.
- Made binding generation trigger-owned: 1 on INSERT, OLD-based on UPDATE, exact increment when canonical classification changes.
- Preserved startup-safe unresolved classification for legacy rows and later writes.
- Added PostgreSQL negatives for same-repository forged key, cross-repository coherent tuple, generation jump, generation-on-insert, missing session, missing canonical key, unresolved promotion, replay, ledger stability, exact receipt schema, constraints, indexes, and state nullability.
- Preserved legacy `project_name` writer compatibility and generic Scribe-only scope.

### Verification

Fresh Sentinel evidence:

- Current Scribe readbacks match SQL SHA-256 `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`, tests SHA-256 `45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055`, and plan SHA-256 `7cfee446d5e9f435cfe5562f5cf84cb3a3856458494eca6bd64ecbe5be603db5`.
- Admitted read-only `review-exec` index 4 ran `git diff --check -- src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql tests/test_database_migration.py`; exit 0, one child launched/reaped, no timeout, empty stdout/stderr digests.
- Current-byte source walkthrough and static boundary searches confirm the controls described above.

Supplied current-revision execution evidence:

- focused disposable PostgreSQL regressions: 2 passed;
- migration module: 10 passed;
- direct neighbor lane: 10 passed;
- capability-free lane: 16 passed, 4 expected skips;
- fresh stdio initialize: protocol `2025-11-25`, 35 tools, `sql:007_reliability_receipts.sql` ledger row, 19 receipt columns;
- Crucible behavioral PASS `9a61ebc4-b6af-40b1-af38-d4c431d179c3`;
- Witness truth PASS `91d1fef6-c081-4775-87a4-d43b0dd430a0`.

### Verification Status

**RESOLVED / SECURITY PASS** for contract revision `a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb`. The prior `validated` fix link points to the correct repaired artifacts but preceded Sentinel closure verification. This reacceptance updates the report and records the authoritative Sentinel fix link after verification.

### Fix Landed
Fix landed with status: **resolved**

### Fix Details
- Artifact: src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17#sha256=9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8; tests/test_database_migration.py:477#sha256=45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055
- Execution ID: 4ca97f3b-6503-40b7-b9ce-a5f02d5e02b5


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Date | Notes |
| --- | --- | --- | --- |
| Security discovery | Sentinel | 2026-09-28 | Proved supplied-key authorization and caller-generation bypass at revision `40a626...`; opened SEC-2026-09-28-0001. |
| Contract amendment | Blueprint / coordinator | 2026-09-28 | Required repository-scoped key validation, trigger-owned monotonic generation, negative PostgreSQL proof, and focused owned scope. |
| Repair | Mantis | 2026-09-28 | Implemented the minimal migration/test delta and captured RED-first then GREEN disposable PostgreSQL evidence. |
| Behavioral verification | Crucible | 2026-09-28 | PASS event `9a61ebc4-b6af-40b1-af38-d4c431d179c3` at exact revision `a248358d...`. |
| Truth verification | Witness | 2026-09-28 | PASS event `91d1fef6-c081-4775-87a4-d43b0dd430a0` at exact revision `a248358d...`. |
| Security reacceptance | Sentinel | 2026-09-28 | Current-byte control review, case reconciliation, and admitted read-only review-exec PASS; SEC-2026-09-28-0001 resolved. |
| Fix linkage | Sentinel | 2026-09-28 | Authoritative post-verification link recorded against the repaired SQL and regression artifacts. |


---
## Appendix
<!-- ID: appendix -->
### Current Evidence References

- Work item: `5309eca6-4d91-477e-b0c8-7087b6d65338`
- Security admission: `129a9227-b3bb-4dff-aafb-a20985f2a8a2`
- Contract revision: `a248358d885add846304939eaac56841e35a0a29682e933ad823053d07f7d4bb`
- SQL SHA-256: `9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8`
- Test SHA-256: `45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055`
- Plan SHA-256: `7cfee446d5e9f435cfe5562f5cf84cb3a3856458494eca6bd64ecbe5be603db5`
- Crucible PASS: `9a61ebc4-b6af-40b1-af38-d4c431d179c3`
- Witness PASS: `91d1fef6-c081-4775-87a4-d43b0dd430a0`
- Fresh review-exec: command index 4, command digest `2c5480162cd97d94c893398d8d3a71d8d2a4dc958767edb2092dd9e77fd7cdc3`, exit 0, `bubblewrap-read-only-v1`

### Historical Finding References

- Vulnerable revision: `40a626417efbf62903bb4a9cc759bf20cbb98579f823ad43bca01316cb88d4c8`
- Vulnerable SQL SHA-256: `53e4af21e29c4930b96e4bd2e7a020de633997da7b9433f7030da35015e76bce`
- Original source proof is preserved in Scribe history and the case timeline.

### Fix References

- `src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17`
- `tests/test_database_migration.py:477`
- Prior link status: `validated` by Mantis before Sentinel reacceptance.
- Final link status: `resolved` by Sentinel after exact-revision verification.

### Closure

No open exploit path remains within the reviewed ordinary INSERT/UPDATE and migration-application boundary. The security report is ready, internally consistent, and suitable as the durable closure record for SEC-2026-09-28-0001.

- **Fix Reference:** src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17#sha256=9eda9e27741c18e3400921e3b9cb61a0a086ec429e05d1a08b77c9a9741688a8; tests/test_database_migration.py:477#sha256=45b32d3759d296494e2e9a8e2a04e7a1f046c89a2e66075b58399f2465062055 (execution: 4ca97f3b-6503-40b7-b9ce-a5f02d5e02b5)
- **Landing Status:** resolved
- **Fix Linked By:** sentinel_sbr_schema_007_reaccept_3


---