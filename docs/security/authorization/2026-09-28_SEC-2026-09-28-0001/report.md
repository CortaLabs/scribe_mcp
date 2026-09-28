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
last_updated: 2026-09-28 04:21:51 UTC
created_by: agent-20260928-032945-0d10794a
maintained_by: agent-20260928-035855-dd245099
status: ready
canonical_doc_type: security
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 03:37:26 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 04:21:51 UTC
  last_edited_by: agent-20260928-035855-dd245099
  last_action: replace_section
  work_item_id: 5309eca6-4d91-477e-b0c8-7087b6d65338
id: SEC-2026-09-28-0001
doc_type: security
summary: 'High-severity SBR-SCHEMA.1 security FAIL: migration 007 accepts unvalidated
  supplied project keys and caller-controlled generations.'
owners:
- Sentinel
tags:
- security
- authorization
- postgresql
- migration-007
- SBR-SCHEMA.1
category: security
---


# 🔒 Migration 007 accepts forged resolved project keys — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** OPEN — REPORT READY; REMEDIATION REQUIRED
**Last Updated:** 2026-09-28 03:35:06 UTC

> This report records the blocking security finding, source-level proof, remediation contract, and verification requirements for SBR-SCHEMA.1.

---
## Security Overview
<!-- ID: security_overview -->
**Case ID:** SEC-2026-09-28-0001

**Reported By:** Sentinel (`sentinel_sbr_schema_007_review_1`)

**Date Reported:** 2026-09-28 UTC

**Severity:** HIGH

**Status:** OPEN — SBR-SCHEMA.1 security gate FAIL

**Component:** PostgreSQL migration 007 session-binding isolation

**Reviewed Boundary:** Work item `5309eca6-4d91-477e-b0c8-7087b6d65338`, contract revision `40a626417efbf62903bb4a9cc759bf20cbb98579f823ad43bca01316cb88d4c8`, SQL SHA-256 `53e4af21e29c4930b96e4bd2e7a020de633997da7b9433f7030da35015e76bce`.

**Customer Impact:** A database writer able to update `session_projects` can bind a session to another or nonexistent project key and can choose a non-monotonic generation. That defeats the schema-level isolation/CAS invariant and can misroute later project-keyed operations. The current legacy writer supplies only `project_name`, which reduces immediate exposure but does not close the enforced-boundary defect.

**CVE / CVSS:** No CVE assigned. Internal high-severity authorization-boundary defect; no numeric CVSS assigned because the externally reachable write path is not established in this source package.


---
## Description
<!-- ID: description -->
### Threat Analysis

Assets at risk are canonical project identity, per-session binding integrity, receipt isolation, and generation-based stale-writer fencing. The trust edge is a write into `session_projects`: legacy-name writes are untrusted classification input, while a supplied `project_key` is currently treated as authority without database proof. The attacker/precondition is any compromised, buggy, or future application path running under the Scribe database role with write permission on this table. The security outcome is cross-project or nonexistent-project binding plus generation rollback/selection.

### Vulnerability

At `007_reliability_receipts.sql:34-43`, any non-empty supplied `NEW.project_key` enters the resolved branch. The trigger does not prove that the key exists in `scribe_projects`, matches the session repository, or agrees with the project name. At lines 133-154, the CHECK validates only tuple shape: resolved + non-NULL key + NULL reason. Therefore a coherent forged binding passes both trigger and constraint.

At lines 28-32 and 81-86, a caller may also provide any positive `binding_generation`. The trigger increments only when the supplied generation equals the old one; a different positive value skips the increment and passes the `>= 1` CHECK. This breaks monotonic rebind generation.

### Proof Path

Given unresolved session `s-zero` and a key belonging to another project:

```sql
UPDATE session_projects
SET project_key = 'key-normal',
    binding_state = 'resolved',
    binding_state_reason = NULL
WHERE session_id = 's-zero';
```

The BEFORE trigger sees a changed, non-empty key and forces `resolved` with no reason. No key-ownership lookup runs. The consistency CHECK then accepts the row. Supplying `binding_generation = 1` or another positive value different from the old generation similarly bypasses the increment branch.

The committed negative test at `tests/test_database_migration.py:517-529` disables the trigger but changes only `project_key` while leaving `binding_state='unresolved'`; that proves incoherent tuples fail, not that coherent forged tuples fail.

### Evidence Boundary

This is a deterministic source-level proof from the exact reviewed SQL and committed tests. Local shell/test execution was not available to this reviewer because the repository hook returned `WORK_ITEM_MUTATION_DENIED[BIND_MISSING]`; the denial was not retried. The supplied ai-trace pair `aitrace:v1:codex:70d9b558b9cf6f800cd8ef079da8b806` / `aitrace:v1:codex:198aa77b7127cc62046fc5843cdea616` is a work-item-show call/result containing historical RED, 10+10 GREEN, initialize, and 25,895-row census claims. It is useful provenance but is not the raw execution call/result for those commands. Those historical claims demonstrate startup availability and legacy classification, not resistance to the forged-key path above.



---
## Affected Systems
<!-- ID: affected_systems -->
**Affected Areas**

- `src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17-157`
- `tests/test_database_migration.py:463-608`
- Downstream consumers that treat a resolved `session_projects.project_key` and `binding_generation` as authoritative

**Trust Boundary Violation**

The migration collapses “caller supplied an opaque key” into “database proved canonical project identity.” This crosses the session-to-project authorization boundary without validating the key against `scribe_projects` and the session repository.

**Attack Vector**

Local/application-database write path. No public HTTP/MCP parameter reaching `project_key` was established in this package; the currently reviewed PostgreSQL `set_session_project` method writes `project_name` only. Risk becomes directly exploitable if any current or future database-role path accepts or derives `project_key` without an independent canonical lookup.

**Unaffected / Positive Controls**

- Legacy zero, many, absent-name, missing-session, and missing-key rows are startup-safe and remain reason-coded/keyless during migration backfill.
- Stable reason codes contain no secret values.
- Receipt rows persist digests, byte counts, opaque refs, and error codes rather than raw payload/error bodies.
- The SQL is generic Scribe-only and contains no Council/Aegis/seat/work-item/projection authority.
- The three receipt indexes cover the declared claim, lease recovery, and project/state accounting access patterns.


---
## Investigation
<!-- ID: investigation -->
### Root Cause

The function comment says “a writer that supplies the key owns the identity,” and the implementation encodes that trust decision directly. The table constraints only enforce representation consistency, not referential or repository-scoped validity. Generation is likewise treated as caller input before a conditional increment rather than as trigger-owned state.

### Security Classification

- **CWE-639 / authorization by user-controlled key (analogous):** a supplied project identifier can select another authorization domain.
- **CWE-284:** schema-level access-control invariant is incomplete.
- **CWE-367-style stale-state risk (analogous):** caller-controlled/non-monotonic generation weakens stale-writer fencing.

### Review of Requested Properties

- No guessed project during legacy backfill: PASS.
- Unresolved rows stay keyless/reason-coded on legacy writes: PASS.
- Resolved key validity: FAIL.
- Trigger/CHECK bypass resistance: FAIL.
- Rebind generation monotonicity: FAIL for explicit-key/generation writes; PASS only for tested legacy-name rebinds.
- Replay idempotency: source appears idempotent for the current valid schema; historical disposable execution is supplied but not independently replayed by this reviewer.
- Secret/error leakage: PASS in this migration.
- Availability / indexes: PASS for the reviewed 25,895-row historical deployment claim and declared indexes; no new unbounded error payload is stored.
- Generic Scribe-only boundary: PASS.

### Related Evidence

Exact source reads were obtained through direct Scribe and reported SHA-256 prefixes matching the registered full hashes. Historical runtime claims are retained as provenance only; this FAIL is based on the current source path and missing negative coverage.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Remediation

1. Keep startup-safe legacy classification unchanged.
2. Remove the unconditional trust in caller-supplied `project_key`. Either:
   - always derive the key from `session_id -> repo_root + project_name`; or
   - validate a supplied key by requiring exactly one `scribe_projects` row whose key matches and whose `repo_root` matches the session repository.
3. Make generation trigger-owned and monotonic. A key-changing resolve or demotion must set `OLD.binding_generation + 1`; callers must not select or reduce it.
4. Decide the explicit-key public/schema contract with Blueprint because changing whether a writer may supply a key is a load-bearing schema/interface decision.

### Required Regression Proof

Run against a uniquely named disposable PostgreSQL database:

- reject a nonexistent supplied key;
- reject a key belonging to another repository/project;
- reject a coherent forged tuple when the trigger is disabled, or document/implement the database privilege model that makes trigger disabling impossible for the application role;
- reject caller-controlled generation rollback/jump and prove exact +1 on rebind;
- preserve zero/many/absent-name/missing-session/missing-key startup-safe classification;
- preserve legacy writer compatibility;
- replay migration 007 twice with unchanged row counts, keys, generations, and ledger;
- retain fresh stdio initialize and live/disposable census proof.

### Mitigation Status

Not started. No source fix was authorized or implemented by this review seat.

### Verification Status

Open. A future Sentinel re-gate must inspect the repair delta and run/inspect the negative-path PostgreSQL proof. `link_fix` must be called only after that remediation is verified and landed.

### Fix Landed
Fix landed with status: **validated**

### Fix Details
- Artifact: src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17; tests/test_database_migration.py:477
- Execution ID: 9927bdcd-8d3c-4cf4-ae58-9b56c00ffdb3


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Date | Notes |
| --- | --- | --- | --- |
| Security source review | Sentinel | 2026-09-28 | Found forged-key and generation-control bypass at exact revision. |
| Contract decision | Blueprint / coordinator | Pending | Decide whether explicit keys are forbidden or validated canonically. |
| Fix development | Forge or Mantis per coordinator routing | Pending | Migration and regression changes only within amended ownership. |
| Security verification | Sentinel | Pending | Delta review plus disposable PostgreSQL negative-path proof. |
| Fix linkage | Sentinel | Pending | Call `link_fix` after verified landing. |


---
## Appendix
<!-- ID: appendix -->
### Evidence References

- Work item: `5309eca6-4d91-477e-b0c8-7087b6d65338`
- Contract revision: `40a626417efbf62903bb4a9cc759bf20cbb98579f823ad43bca01316cb88d4c8`
- SQL SHA-256: `53e4af21e29c4930b96e4bd2e7a020de633997da7b9433f7030da35015e76bce`
- Test SHA-256: `85e390bd68eb377f74b4581c5f65b1835683d5ee3b94b290a8c8f9a272f18005`
- Plan SHA-256: `8935a7940ea40a792b43102622bc963dc75285cc17329ff7cd3b15b67f4d5287`
- Historical evidence readback pair: `aitrace:v1:codex:70d9b558b9cf6f800cd8ef079da8b806`, `aitrace:v1:codex:198aa77b7127cc62046fc5843cdea616`
- Reviewer execution limitation: `WORK_ITEM_MUTATION_DENIED[BIND_MISSING]`

### Open Questions

- Which planned runtime writer is authorized to supply `project_key` directly?
- Is the application database role prevented from disabling triggers? If not, the coherent-tuple invariant also needs a non-trigger enforcement strategy.
- Should `session_projects.project_key` gain a foreign key once the unique project-key index is guaranteed, or should trigger validation remain the compatibility mechanism?
- What exact generation/CAS contract must reject caller-selected values?

### Fix References

None yet. Case remains open; no `link_fix` is valid until remediation is verified.

- **Fix Reference:** src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17; tests/test_database_migration.py:477 (execution: 9927bdcd-8d3c-4cf4-ae58-9b56c00ffdb3)
- **Landing Status:** validated
- **Fix Linked By:** mantis_sbr_schema_007_security_repair_2


---