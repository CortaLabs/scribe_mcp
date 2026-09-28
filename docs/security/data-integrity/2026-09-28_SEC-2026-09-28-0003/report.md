---
visibility: internal
owner_principal_id: sentinel_sbr_schema_2_review_1
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 6b9dd972ede7f29f3ef33029670c3542c28e57847504e7e5378d8537e343df8e
title: "\U0001F512 SQLite rebuild rollback is not connection-affine \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-28 09:42:15 UTC
created_by: agent-20260928-093241-4ef716bd
maintained_by: agent-20260928-093241-4ef716bd
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 09:41:20 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 09:42:15 UTC
  last_edited_by: agent-20260928-093241-4ef716bd
  last_action: frontmatter_update
  stage: security_review
  work_item_id: 769f4ed9-3c46-4b50-84a5-002d2eda02f7
summary: 'High-severity blocking data-integrity finding: rebuild rollback is not connection-affine
  across the SQLite pool.'
owners:
- Sentinel
tags:
- SBR-SCHEMA.2
- security-review
- data-integrity
- high
- open
- fail
verdict: fail
verified_revision: 3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0
---


# 🔒 SQLite rebuild rollback is not connection-affine — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** INVESTIGATING
**Last Updated:** 2026-09-28 09:39:20 UTC

> Summarise why this document exists and what decisions it captures.

---
## Security Overview
<!-- ID: security_overview -->
**Case ID:** SEC-2026-09-28-0003

**Reported By:** Sentinel (`sentinel_sbr_schema_2_review_1`)

**Date Reported:** 2026-09-28

**Severity:** HIGH

**Status:** OPEN — blocks SBR-SCHEMA.2 security PASS

**Component:** SQLite reliability rebuild transaction

**Environment:** Source review at contract revision `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0`

**Customer Impact:** A failed legacy rebuild can leave a pooled SQLite connection inside an unrolled-back transaction after destructive table replacement stages. Later reuse can expose partial DDL, retain locks, commit unintended state, or deny further writes. No production incident was observed; the risk is present in the source transaction boundary.

**CVE ID:** N/A — internal pre-release finding

**CVSS Score:** N/A — deployment concurrency and attacker prerequisites are not yet established.


---
## Description
<!-- ID: description -->
### Threat Analysis

Assets are authoritative legacy rows, exact timestamps/values, table and trigger integrity, SQLite availability, and the guarantee that rebuild failure is atomic. The trust edge is malformed legacy data or any injected/organic SQLite failure during copy, rename, index, trigger, or validation stages. Concurrent storage use can expand the connection pool beyond one connection.

### Vulnerability

`_execute_rebuild` runs the transactional statement list through one `execute_many_fn` call. On error, `SQLiteInternals._run_with_connection` releases the failed, still-valid connection in `finally`. Only afterward does `_execute_rebuild` invoke a second `execute_many_fn(["ROLLBACK;"])`.

The pool is FIFO. Release appends the failed connection to the right, while the next acquire pops from the left. If another idle connection already exists, `ROLLBACK` runs there, reports no active transaction, and that error is explicitly ignored. The original connection can remain `in_transaction` with partial DDL/temp state.

### Safe Reproduction Path

1. Warm `SQLiteConnectionPool` to at least two idle connections.
2. Start the bounded rebuild and raise an SQLite error after `BEGIN IMMEDIATE` and after at least one partial replacement operation.
3. The transaction-owning connection is released to the pool without rollback.
4. The follow-up rollback can acquire a different idle connection.
5. `no transaction is active` is ignored, while the original connection remains reusable and transactional.

The dispatched in-memory command lane could not run an additional custom probe because the hook denied it before launch with `WORK_ITEM_MUTATION_DENIED[BIND_MISSING]`. The earlier supplied persistent-executor proof demonstrates only same-connection behavior and does not cover the actual multi-connection pool boundary.



---
## Affected Systems
<!-- ID: affected_systems -->
**Affected Areas**

- `src/scribe_mcp/storage/sqlite/schema.py:786` — rollback is issued as a separate callback invocation.
- `src/scribe_mcp/storage/sqlite/internals.py:119` — pooled connection is acquired/released around each execute-many call.
- `src/scribe_mcp/storage/sqlite/internals.py:164` — release occurs in `finally` even when the transaction is active.
- `src/scribe_mcp/storage/pool.py:210` — FIFO acquire.
- `src/scribe_mcp/storage/pool.py:300` — valid failed connection is appended without transaction cleanup.
- `src/scribe_mcp/storage/pool.py:186` — validation runs only `SELECT 1`.

**Trust Boundary Violations**

The schema layer assumes callback-level transaction affinity that the storage/pool abstraction does not promise. A successful rollback result on one connection is treated as proof that a different connection's failed transaction was cleaned up.

**Attack Vector**

Local or adjacent failure induction through malformed legacy rows, disk/constraint errors, or timing with an expanded pool. Exploitation need not inject SQL; it relies on legitimate failure paths and pool ordering.

**Unaffected Controls**

Rebuild table names and dynamic SQL fragments are fixed module constants; no attacker-controlled SQL identifier or injection path was found. Copy/value/FK/index/trigger validation logic is otherwise comprehensive when executed on one connection.


---
## Investigation
<!-- ID: investigation -->
### Root Cause

Atomicity is divided across two independent pooled operations. `_execute_many_writes` does not rollback in its own exception path. `_run_with_connection` releases regardless of `conn.in_transaction`. Pool validation considers an active-transaction connection healthy. The schema helper then suppresses a no-active-transaction result from a potentially unrelated connection.

### Evidence

- `schema.py:791-808`: rebuild and rollback use separate `execute_many_fn` calls.
- `internals.py:119-126`: each call independently enters `_run_with_connection`.
- `internals.py:164-176`: connection release/close occurs in `finally`.
- `internals.py:187-190`: no exception-local rollback.
- `pool.py:242-250`: acquire uses `popleft`.
- `pool.py:321-327`: release validates and `append`s.
- `pool.py:195-198`: validation does not inspect or clean `in_transaction`.
- Admitted review-exec index 2: 24 tests passed but no multi-connection rollback-affinity regression is included.
- Prior supplied persistent-executor proof is not sufficient for pooled runtime parity.

### Security Properties at Risk

Integrity: partial replacement state may survive. Availability: an active writer transaction may retain locks. Isolation: later unrelated callers can inherit transactional state. Auditability: a reported explicit rollback may have occurred on the wrong connection.

### Confidence

High from the explicit pool ordering and callback boundaries. Executable multi-connection confirmation remains required as the first repair regression.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Remediation

- Make rollback connection-affine. Preferred minimal control: `SQLiteInternals._execute_many_writes` catches any failure and rolls back the same `conn` before `_run_with_connection` can release it.
- Alternatively, introduce a dedicated transactional callback that owns acquire, statement execution, validation, commit, rollback, and release as one operation.
- Reject or quarantine any pooled connection that is still `in_transaction` at release unless the caller explicitly owns a continuing transaction.
- Do not rely on a second pooled `ROLLBACK` call as the primary safety control.

### Mitigation Status

Not started. Repair likely requires a contract-scope amendment because `internals.py` and `pool.py` are outside the current owned-file boundary.

### Verification Required

- Multi-connection pool regression with at least two idle connections.
- Inject failures at copy, rename, index, trigger, and validation.
- Assert every pooled connection has `in_transaction == False`.
- Assert original authoritative rows/table remain, replacement/temp objects are absent, and later writes succeed.
- Confirm rollback failure is surfaced rather than suppressed.
- Re-run existing 25 weakened-schema probes, persistent failure probes, and registered scoped lane.

### Long-Term Control

All storage transaction APIs should make connection ownership explicit and guarantee rollback-before-release on exceptions.


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Investigation | Sentinel | Complete | Source-level pool/transaction trace |
| Contract scope decision | Coordinator / Blueprint | Required | Current package owns only schema.py and init.sql |
| Fix development | Forge | Not started | Connection-affine rollback |
| Behavioral regression | Crucible | Pending | Multi-connection injected-failure lane |
| Security verification | Sentinel | Pending | Old failure path no longer leaves active transaction |
| Fix linkage | Sentinel | Pending | `link_fix` after verified landing |


---
## Appendix
<!-- ID: appendix -->
### Evidence References

- Work item: `769f4ed9-3c46-4b50-84a5-002d2eda02f7`
- Reviewed revision: `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0`
- `schema.py` SHA-256: `b1fbd401a8bc53018adc0783a36a33fd2347b594171010d18080c98273823f6a`
- Admitted scoped lane: 24 passed with one read-only cache warning.
- Admitted diff check: exit 0.
- Additional supplied probe: denied before launch; no runtime result asserted.

### Fix References

None. `link_fix` is pending verified remediation.

### Open Questions

- Whether the narrow repair should live in the generic pooled execute-many primitive or a rebuild-specific transactional primitive.
- Whether release should always rollback an unexpected active transaction as a defense-in-depth invariant.


---