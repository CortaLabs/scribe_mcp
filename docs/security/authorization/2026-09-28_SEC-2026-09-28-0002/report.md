---
visibility: internal
owner_principal_id: sentinel_sbr_schema_2_review_1
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 6b9dd972ede7f29f3ef33029670c3542c28e57847504e7e5378d8537e343df8e
title: "\U0001F512 SQLite session binding authority can remain forged or stale \u2014\
  \ scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-28 09:42:08 UTC
created_by: agent-20260928-093241-4ef716bd
maintained_by: agent-20260928-093241-4ef716bd
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 09:40:14 UTC
  created_via: replace_section
  last_edited_at: 2026-09-28 09:42:08 UTC
  last_edited_by: agent-20260928-093241-4ef716bd
  last_action: frontmatter_update
  stage: security_review
  work_item_id: 769f4ed9-3c46-4b50-84a5-002d2eda02f7
summary: 'High-severity blocking C-05 authority-integrity finding: forged or stale
  project_key and downgraded generation survive SQLite fresh/rebind/reopen paths.'
owners:
- Sentinel
tags:
- SBR-SCHEMA.2
- security-review
- authorization
- high
- open
- fail
verdict: fail
verified_revision: 3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0
---


# 🔒 SQLite session binding authority can remain forged or stale — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** INVESTIGATING
**Last Updated:** 2026-09-28 09:37:54 UTC

> Summarise why this document exists and what decisions it captures.

---
## Security Overview
<!-- ID: security_overview -->
**Case ID:** SEC-2026-09-28-0002

**Reported By:** Sentinel (`sentinel_sbr_schema_2_review_1`)

**Date Reported:** 2026-09-28

**Severity:** HIGH

**Status:** OPEN — blocks SBR-SCHEMA.2 security PASS

**Component:** Scribe C-05 session binding authority

**Environment:** Source review at contract revision `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0`

**Customer Impact:** A forged or stale canonical project key can misattribute a session to the wrong project authority. Downstream C-05 consumers could perform project-keyed reads or writes under an identity that does not correspond to the session repository and compatibility project name. No exploitation or production exposure was observed; this is a pre-release source-level integrity finding.

**CVE ID:** N/A — internal pre-release finding

**CVSS Score:** N/A — deployment reachability and attacker prerequisites are not yet established.


---
## Description
<!-- ID: description -->
### Threat Analysis

Assets are canonical project identity, binding generation/fencing, session-to-project isolation, and compatibility-name continuity. The untrusted input edge is any caller that can invoke the compatibility binding writer or otherwise supply a `session_projects` row. The trust boundary is crossed when later code treats `project_key` and `binding_generation` as authoritative.

### Vulnerability

The SQLite C-05 table checks only that a resolved key is nonempty, generation is positive, state is in the closed domain, and reason/nullability agree. Its two triggers validate only that the session exists. They do not prove that `project_key` equals the unique project selected by `(scribe_sessions.repo_root, project_name)`, nor do they enforce monotonic generation.

The compatibility writer in `src/scribe_mcp/storage/sqlite/sessions.py:122` updates `project_name` and `updated_at` only. The reopen repair predicate in `schema.py:1175` revisits only syntactically invalid authority tuples, so a mismatched nonempty key and any positive generation remain accepted. Fresh PostgreSQL `init.sql:229` has the same shape-only checks but omits migration 007's classification trigger/function, creating a weaker window until 007 executes.

### Safe Reproduction Path

1. Create two projects in one repository: `alpha/pk-alpha` and `beta/pk-beta`, plus a live session.
2. Insert `project_name='alpha'`, `project_key='pk-forged'`, `binding_generation=99`, `binding_state='resolved'`, `binding_state_reason=NULL`.
3. Current SQLite constraints and triggers accept the row.
4. Re-run `ensure_reliability_schema`; canonical shape is a no-op and the row repair predicate skips this syntactically valid tuple.
5. Rebind with the compatibility writer to `beta`; the stale key and generation remain.
6. Any positive generation, including a downgrade, remains accepted on reopen.

A supplied in-memory probe was attempted but denied before child launch with `WORK_ITEM_MUTATION_DENIED[BIND_MISSING]`; this report does not claim that command executed. The exploit path is established directly by the cited source predicates and write statement.



---
## Affected Systems
<!-- ID: affected_systems -->
**Affected Areas**

- `src/scribe_mcp/storage/sqlite/schema.py:107` — shape-only C-05 constraints and session-existence triggers.
- `src/scribe_mcp/storage/sqlite/schema.py:1073` — legacy repair and reopen predicate.
- `src/scribe_mcp/storage/sqlite/sessions.py:122` — compatibility rebind updates name only.
- `src/scribe_mcp/db/init.sql:229` — fresh PostgreSQL shape without 007 classification trigger.
- `src/scribe_mcp/db/postgres_migrations/007_reliability_receipts.sql:17` — authoritative comparison control.

**Trust Boundary Violations**

A compatibility project name crosses into canonical project-key authority without an identity-correspondence check. Generation is stored as authority/fencing state but can be set to any positive integer or decreased.

**Attack Vector**

Local or adjacent application caller with access to the binding write path; direct database access is not required for the stale-key path because the public compatibility writer changes only `project_name`.

**Not Affected by This Finding**

C-06 receipt state-domain, digest, lease-pair, fencing equality, uniqueness, and state-nullability constraints are fully fingerprinted in the reviewed SQLite canonical body. Dynamic table/trigger names in the rebuild are fixed module constants, and SQL string inputs are not attacker-controlled.


---
## Investigation
<!-- ID: investigation -->
### Root Cause

C-05 schema equivalence is defined as exact equality to a canonical table body whose authority rules are incomplete. Fingerprinting therefore proves that all deployments share the same weakness; it does not prove project identity correctness. The repair predicate checks internal tuple consistency but not correspondence with `scribe_projects` and does not detect generation regression.

### Evidence

- `schema.py:107-150`: no project-key classification or generation transition trigger.
- `schema.py:698-719`: canonical predicate fingerprints only those two session-existence triggers.
- `schema.py:1175-1192`: resolved rows are revisited only for empty key or non-null reason.
- `sessions.py:135-139`: conflict update changes `project_name` and timestamp only.
- `init.sql:229-251`: no migration 007 classification function/trigger.
- `007_reliability_receipts.sql:17-106`: authoritative PostgreSQL migration validates supplied key and owns generation increments.
- Admitted review-exec index 2: 24 tests passed; none exercise forged/mismatched C-05 authority.
- Admitted review-exec index 5: scoped diff check passed.

### Confidence and Scope

Confidence is high from direct control-flow and SQL-constraint inspection. The denied runtime probe limits executable demonstration, not the source-level conclusion. No Council-specific column, authority, or schema leakage was found in the owned files.


---
## Resolution Plan
<!-- ID: resolution_plan -->
### Immediate Remediation

- Add SQLite insert/update classification or guard logic equivalent to migration 007: derive the unique canonical key from session repository plus project name; reject or classify mismatches without guessing.
- Make `binding_generation` monotonic and system-owned for rebinding; callers must not be able to decrease or arbitrarily set it.
- Expand `SESSION_PROJECTS_CANONICAL_PREDICATE` to fingerprint the authority triggers/controls, so a weakened schema cannot be accepted as canonical.
- Ensure legacy/reopen repair detects a resolved tuple whose key disagrees with the unique canonical project and fails closed or reclassifies deterministically.
- Make fresh PostgreSQL bootstrap install equivalent classification enforcement or prove structurally that no binding write can occur before migration 007 completes.

### Mitigation Status

Not started. The current work item must receive a security FAIL and return to an authorized repair owner.

### Verification Required

- Negative SQLite test: forged nonempty key cannot become or remain resolved.
- Compatibility rebind test: changing `project_name` derives the new key and increments generation exactly once.
- Downgrade test: decreasing generation is rejected.
- Legacy/reopen test: mismatched resolved rows fail closed without data loss.
- Fresh PostgreSQL bootstrap test: no pre-007 weaker authority window.
- Re-run the registered scoped lane and exact-hash review after repair.

### Long-Term Control

Treat project key and generation as owned authority fields at every backend boundary; compatibility names are inputs to classification, never parallel authority.


---
## Timeline & Ownership
<!-- ID: timeline -->
| Phase | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Investigation | Sentinel | Complete | Source review and admitted review-exec receipts |
| Repair design/scope | Coordinator / Blueprint if contract scope changes | Required | Current owned-file boundary may be insufficient |
| Fix development | Forge | Not started | Add authority guards and regressions |
| Security verification | Sentinel | Pending | Prove old exploit path closed |
| Fix linkage | Sentinel | Pending | `link_fix` only after verified landed remediation |


---
## Appendix
<!-- ID: appendix -->
### Evidence References

- Work item: `769f4ed9-3c46-4b50-84a5-002d2eda02f7`
- Reviewed revision: `3c4626483a7e192cdfc8955e249baa3ae754137bb8c702be7f326b7e9fe24bd0`
- `schema.py` SHA-256: `b1fbd401a8bc53018adc0783a36a33fd2347b594171010d18080c98273823f6a`
- `init.sql` SHA-256: `7b58753777c5e19552683cf4884a4bab602a5dc5dc93d2dd20a9481a75f9ee49`
- Behavioral PASS event: `bec7aa97-4cec-4249-806f-185353618260`
- Truth PASS event: `31d8011f-65ad-4f92-b68b-c68a4ee87acb`
- Supplied probe status: denied before launch; no runtime result asserted.

### Fix References

None. `link_fix` is pending verified remediation and must not be called yet.

### Open Questions

- Whether fresh PostgreSQL bootstrap is reachable by any binding writer before migration 007 is guaranteed complete.
- Whether the repair belongs entirely in the two owned schema files or requires a contract amendment for the SQLite binding writer.


---