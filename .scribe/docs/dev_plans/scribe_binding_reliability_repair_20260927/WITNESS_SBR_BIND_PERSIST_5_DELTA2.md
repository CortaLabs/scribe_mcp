---
id: scribe_binding_reliability_repair_20260927-witness-sbr-bind-persist-5-delta2
title: Witness Sbr Bind Persist 5 Delta2
doc_type: custom
doc_name: WITNESS_SBR_BIND_PERSIST_5_DELTA2
category: verification
status: ready
version: '0.1'
last_updated: 2026-09-28 00:59:21 UTC
maintained_by: agent-20260928-004503-56055a58
created_by: witness_sbr_bind_persist_5_delta2
owners:
- Witness
related_docs: []
tags:
- witness
- truth-check
- SBR-BIND-PERSIST.5
summary: 'PASS: repaired SBR-BIND-PERSIST.5 remote transport matches the active contract
  and preserves non-conflict error behavior.'
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 00:57:08 UTC
  created_via: create_doc
  last_edited_at: 2026-09-28 00:59:21 UTC
  last_edited_by: agent-20260928-004503-56055a58
  last_action: frontmatter_update
  stage: truth_check
  work_item_id: 398c8030-60a1-4346-bc38-b9b7f535f67e
verdict: PASS
review_role: witness
contract_revision: 34c8b74f546013ea5d3c451110285913a4adbbf1ede78a2d2f094aa5500e7eb4
source_sha256: 75b5a92e4168ac01cb3c113463525b2eea172c380224611ba677124c3f668dd4
review_admission_id: 71ac7981-3c07-43b5-b9e8-3d55c627cfd8
---

# Witness Verification Report

<!-- ID: summary -->
## Summary

**Overall: PASS**

**Review Boundary:** active package scope — `src/scribe_mcp/storage/remote.py` only, at contract revision `34c8b74f546013ea5d3c451110285913a4adbbf1ede78a2d2f094aa5500e7eb4`.

Current source SHA-256 is `75b5a92e4168ac01cb3c113463525b2eea172c380224611ba677124c3f668dd4`, exactly matching the repaired completion artifact. The delta restores public `ConflictError` semantics for structured non-2xx and 2xx remote envelopes while preserving all pre-existing auth, network, stale-session, forbidden-operation, malformed-response, and unrelated HTTP failure behavior. A1-A5 pass. `SBR-CORE-VAL.1` and `SBR-CORE-VAL.5` remain mandatory downstream and are not waived.
<!-- ID: rubric -->
## Rubric

- **CHECK — Plan Intent / Authority. EVIDENCE:** current work-item contract authorizes C-01 durable remote parity and the structured error repair in `remote.py` only. **RESULT: PASS.**
- **CHECK — Deterministic Intent. EVIDENCE:** revision declares exact six-field records, authenticated durable transport, A1-A5, owned/forbidden files, and four verification commands. **RESULT: PASS.**
- **CHECK — Import Resolution. EVIDENCE:** paired import command printed `set_session_project` with exit 0; paired `py_compile` exited 0. **RESULT: PASS.**
- **CHECK — Symbol Existence. EVIDENCE:** `ConflictError`, `RemoteUnavailableError`, `StorageBackend`, `SessionBindingRecordV2`, `SessionLeaseExpired`, `RemoteStorageBackend._raise_mapped_remote_error`, `_post_json`, `_call`, `set_session_project`, and `get_session_project` exist in current source. **RESULT: PASS.**
- **CHECK — Explicit Contract Match. EVIDENCE:** remote/base signatures match exactly; decoder accepts exactly six fields and constructs the validated immutable record; set/get delegate through authenticated `_call`; reads never fall back to the local mirror. **RESULT: PASS.**
- **CHECK — Conflict / non-conflict behavior. EVIDENCE:** recognized structured errors are mapped before `raise_for_status()`; the same mapper is invoked by `_call` for successful-status error envelopes. The seven-case probe passes stale-generation, unknown-session, unknown-project, 2xx conflict, stale session with metadata, forbidden operation, and unrelated HTTP 500 preservation. **RESULT: PASS.**
- **CHECK — Boundary Match. EVIDENCE:** review boundary equals the package-owned single file. **RESULT: PASS.**
- **CHECK — Scope Boundary. EVIDENCE:** repair transcript contains one patch targeting only `remote.py`; no test or Council file was edited by the repair. **RESULT: PASS.**
- **CHECK — Command Execution. EVIDENCE:** paired results prove import, compile, 11 targeted tests, 7/7 probe, and scoped diff-check. **RESULT: PASS.**
- **CHECK — Testing Standard. EVIDENCE:** this source-only package modified no tests; required existing tests use mocked `httpx` clients and no live/shared state. Marker/placement changes are outside the owned boundary. **RESULT: PASS / no modified in-scope tests.**
- **CHECK — Acceptance Criteria. EVIDENCE:** A1-A5 individually verified; CORE-VAL.1/.5 remain explicitly deferred and mandatory. **RESULT: PASS.**
- **CHECK — Frontend truth checks. EVIDENCE:** package touches no frontend surface. **RESULT: NOT APPLICABLE.**
- **WARN ONLY:** unrelated dirty worktree paths exist outside the active package boundary; they are non-gating.
- **WARN ONLY:** admitted `review-exec` index 0 returned `REVIEW_COMMAND_EFFECTFUL` without launching a child. It was not counted as evidence; paired ai-trace evidence was used.
- **WARN ONLY:** live Scribe rejected `doc_type=verification`; this report uses a governed `custom` scaffold with verification category/stage metadata.
<!-- ID: evidence -->
## Evidence

### Current bytes and source contract

- Scribe scan: `remote.py` SHA-256 `75b5a92e4168ac01cb3c113463525b2eea172c380224611ba677124c3f668dd4`.
- `remote.py:145-167`: shared mapper preserves `StaleSession -> SessionLeaseExpired`, `ForbiddenOperation -> PermissionError`, and adds `ConflictError -> storage.base.ConflictError`.
- `remote.py:198-206`: structured HTTP error envelopes are decoded and mapped before `resp.raise_for_status()`.
- `remote.py:223-239`: `_call` delegates to authenticated `_post_json` and reuses the same mapper for successful-status error envelopes.
- `remote.py:273-302`: exact six-field decoding and typed record construction.
- `remote.py:557-580`: remote-authoritative set/get; mirror updates occur only after successful decode and never satisfy reads.
- `base.py:519-541`: exact public signatures and CAS/no-write/`ConflictError` contract.
- `models.py:59-85`: immutable six-field record validates hash, non-empty keys/root, positive non-bool generation, and aware timestamp.

### Paired execution proof

- Import call/result: `aitrace:v1:codex:bbb835f0fc59d00b37fcaca2548f402c` / `aitrace:v1:codex:1cf0db224fe02c73f21ecb8608586957` — output `set_session_project`, exit 0.
- Compile call/result: `aitrace:v1:codex:59b7ba887c26707af77156d0a58918cc` / `aitrace:v1:codex:f8522e9ced42d7391ab1f3404432ffa2` — exit 0.
- Targeted tests call/result: `aitrace:v1:codex:e0de45acf007741103d3ed8f3b1c9449` / `aitrace:v1:codex:4097c6072cd34fabece4345b087a00dd` — 11 passed, exit 0.
- Seven-case probe call/result: `aitrace:v1:codex:becc44d277829e22ef844446d537d7ca` / `aitrace:v1:codex:1b0f591e990b1fea15b4ec6e940e4f1c` — 7/7 passed.
- Scoped diff-check call/result: `aitrace:v1:codex:18a93b64bd434261d4f72c740ce22ea4` / `aitrace:v1:codex:f13ef8dfd52daf37f3109ba924413049` — exit 0.
- Repair patch: `aitrace:v1:codex:219eef4234334937109ebd98709e6a0b` — only `src/scribe_mcp/storage/remote.py`.
- Forge handoff: completion event `97c85fcd-0c21-4fed-8c9b-f131dcaa6772`; projection receipt `prj-27c20d0a9303aefa0d3b6af2` is reconciled.
- Reviewer admission `71ac7981-3c07-43b5-b9e8-3d55c627cfd8`: `review-doctor` status healthy, projection active.
<!-- ID: handoff -->
## Handoff

**PASS — READY FOR ARBITER / remaining declared gate work.**

Truth evidence is current for repaired SHA `75b5a92e4168ac01cb3c113463525b2eea172c380224611ba677124c3f668dd4` at contract revision `34c8b74f546013ea5d3c451110285913a4adbbf1ede78a2d2f094aa5500e7eb4`.

This verdict does not claim completion of `SBR-CORE-VAL.1` or `SBR-CORE-VAL.5`; both remain mandatory downstream release gates.
