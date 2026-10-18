---
id: scribe_rehome_resolution_fix_20260830-research-dry-run-apply-security
title: "Research \u2014 Dry-Run Apply Receipt Security Contract"
doc_type: custom
doc_name: RESEARCH_DRY_RUN_APPLY_SECURITY
category: research
status: ready
version: '0.1'
last_updated: 2026-08-30 18:21:50 UTC
maintained_by: agent-20260830-181619-2e32078b
created_by: agent-20260830-181619-2e32078b
owners:
- Sentinel
related_docs: []
tags:
- security
- manage_docs
- apply_preview
- receipt
summary: Minimum safe receipt contract for applying an exact successful manage_docs
  mutation preview
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-08-30 18:20:13 UTC
  created_via: create_doc
  last_edited_at: 2026-08-30 18:21:50 UTC
  last_edited_by: agent-20260830-181619-2e32078b
  last_action: frontmatter_update
  work_item_id: 90cf6903-5d6b-49c5-9543-f6b843561030
---
# Research — Dry-Run Apply Receipt Security Contract

## Decision
<!-- ID: decision -->

**PASS, with mandatory controls.** The smallest acceptable additive public contract is an `apply` affordance on each successful mutation preview:

```json
{
  "apply": {
    "action": "apply_preview",
    "receipt": "<opaque-server-token>",
    "expires_at": "<RFC3339 timestamp>"
  }
}
```

The follow-up is `manage_docs(action="apply_preview", metadata={"receipt": "<opaque-server-token>"})`. The caller sends no normalized arguments, target path, action payload, diff, preimage, or after-state. Existing dry-run fields remain unchanged and read-only or unsuccessful dry runs receive no affordance.

This is a conditional PASS for the public shape, not approval of every implementation. BLOCK any implementation that trusts client-replayed normalized arguments, uses a self-contained serialized receipt, stores plaintext bearer tokens, relies on process-local state, skips apply-time controls, or can execute a mutation twice.

## Threat Analysis
<!-- ID: threat_analysis -->

Assets are document integrity, project/repository isolation, authenticated mutation authority, canonical path confinement, audit truth, and the confidentiality of document bodies, diffs, normalized arguments, session identifiers, and internal storage state.

The new trust edge is a compact bearer capability crossing from a successful preview response back into the server. Adversaries include another agent or session that obtains a receipt, a caller replaying or altering preview data, a stale authorized caller applying after target drift, and concurrent workers racing the same receipt.

Primary abuse cases:

1. Receipt theft causes a cross-actor, cross-session, cross-project, or cross-repository write.
2. A caller reconstructs or substitutes normalized arguments so the apply differs from the reviewed preview.
3. A stale receipt overwrites a changed target or reuses a path that now resolves elsewhere.
4. Concurrent or crash-retried calls apply the mutation twice.
5. Responses, logs, telemetry, or storage expose receipt material, normalized payloads, paths, document contents, or internal authority state.
6. A public `agent` string is mistaken for authenticated authority.
7. A read-only, failed, or otherwise inapplicable dry run incorrectly advertises Apply.

## Minimum Binding Contract
<!-- ID: binding_contract -->

Generate at least 256 bits of cryptographically secure random token entropy. Return only the opaque token. Store only a server-side SHA-256 token hash for lookup; never persist or log the plaintext token.

Each receipt row is immutable after issue except for lifecycle state and audit timestamps. It MUST bind:

- verified principal identity and the verified session/run identity;
- active Scribe project identity and canonical repository-root identity;
- canonical target identity, including action-specific source/destination identity where rehome or create requires more than one path assertion;
- the exact action and server-retained normalized mutation intent;
- an action-specific precondition digest, including the preimage hash or an explicit nonexistence/registry-generation assertion;
- the predicted after-state hash;
- issue time, expiry time, receipt version, lifecycle state, and audit correlation ID.

The public `agent` string is attribution only. It MUST NOT authorize issue or apply, and changing it MUST NOT let a caller satisfy the principal/session binding.

The server-retained normalized intent is the only executable mutation payload. The client MUST NOT resend it and the apply endpoint MUST reject mutation fields accompanying `receipt`.

## TTL, Storage, and Lifecycle
<!-- ID: ttl_storage -->

Default TTL is 10 minutes. Configurable TTL MUST be capped at 30 minutes. Expiry is checked against trusted server time both before claiming and again within the atomic apply transaction.

Use the existing durable project storage boundary, not an in-memory dictionary or a parallel unmanaged store. Receipt lookup is by unique token hash. Persist only the minimum normalized intent needed to execute the reviewed mutation. Sensitive retained fields require the same at-rest protection and access controls as managed document content. Cleanup may delete expired rows only after retaining the non-sensitive audit record required by policy.

Required state machine:

`issued -> applying -> applied`

or

`issued -> applying -> failed_terminal`.

Claiming `issued` MUST be an atomic compare-and-set operation with a fencing value. Exactly one worker can enter `applying`. The mutation and terminal receipt result SHOULD commit atomically where the storage boundary permits. If the process crashes after the document write but before terminal-state persistence, recovery compares the bound preimage and predicted after-state hashes: observed after-state finalizes the stored success without rewriting; observed preimage may safely resume under the same fencing protocol; any third state fails closed as drift.

A completed retry returns the stored terminal result with `replayed: true`; it never runs the mutation again. An in-flight retry returns a stable busy/retry outcome and cannot acquire a second execution lease.

## Apply-Time Rechecks
<!-- ID: apply_rechecks -->

Receipt possession is necessary but insufficient. Immediately before execution, the server MUST:

1. validate token syntax, lookup hash, TTL, receipt version, and applicability;
2. compare verified principal, session/run, project, and repository identities to the immutable binding;
3. re-run current authorization, Scribe write-barrier, project write-safety, and path-sandbox policy;
4. re-resolve the canonical target and require it to match the bound target identity;
5. compare the action-specific precondition digest/preimage against current state;
6. atomically claim the receipt;
7. execute only the retained normalized intent through the normal mutation path, preserving existing lock/CAS/atomic-write controls;
8. verify the resulting after-state hash, persist the terminal result, and append linked audit events.

Changing authorization, path resolution, project binding, write-barrier state, or target content after preview invalidates apply. No policy result from preview is cached as apply-time authority.

## Stable Public Outcomes
<!-- ID: failure_outcomes -->

All outcomes use the normal host-valid MCP result shape and expose no internal stack, retained intent, existence oracle, or authority details.

- `APPLY_RECEIPT_APPLIED`: mutation applied once; include safe result fields and `replayed: false`.
- `APPLY_RECEIPT_REPLAYED`: terminal result returned without mutation; include `replayed: true`.
- `APPLY_RECEIPT_INVALID`: malformed, unknown, revoked, or unsupported-version receipt.
- `APPLY_RECEIPT_EXPIRED`: trusted server time is beyond expiry.
- `APPLY_RECEIPT_SCOPE_MISMATCH`: verified principal/session/project/repository does not match; do not identify which dimension failed.
- `APPLY_RECEIPT_INAPPLICABLE`: no successful mutation preview or the action is not eligible.
- `APPLY_RECEIPT_POLICY_DENIED`: current authorization, write barrier, or path policy denies the write.
- `APPLY_RECEIPT_TARGET_DRIFT`: canonical target or bound precondition/preimage differs.
- `APPLY_RECEIPT_BUSY`: another fenced worker is applying; safe to retry after server guidance.
- `APPLY_RECEIPT_RECOVERY_REQUIRED`: state is indeterminate and automated hash reconciliation cannot prove preimage or after-state; no mutation retry occurs.
- `APPLY_RECEIPT_STORAGE_UNAVAILABLE`: durable claim/result storage is unavailable; fail closed.

Malformed/unknown and scope-mismatch responses SHOULD be timing- and detail-normalized enough to avoid turning receipt lookup into an oracle.

## Redaction and Audit
<!-- ID: redaction_audit -->

The receipt token is secret bearer material. Redact it from logs, errors, traces, telemetry, Scribe entries, exception context, and analytics. Public responses MUST NOT include normalized intent, document bodies, unredacted diffs, absolute internal paths, session secrets, storage keys, or serialized internal state. A short non-secret audit correlation derived separately from the bearer token may be exposed.

Append linked `preview_receipt_issued` and `preview_receipt_apply_result` audit events. Record correlation ID, receipt version, verified principal/session identifiers in the protected audit plane, project/repository identity, action, canonical target identifier, issue/expiry/apply timestamps, preimage and after-state hashes, lifecycle transition, stable result code, replay flag, and policy/CAS decision. Do not record the bearer token or retained normalized payload.

Audit linkage MUST prove that one applied result corresponds to one issued successful mutation preview and must preserve crash-recovery transitions.

## Reusable Existing Primitives
<!-- ID: reusable_primitives -->

Reuse rather than fork these existing controls:

- Shared response enrichment and dry-run/action context in `src/scribe_mcp/doc_management/runtime.py:3190-3224`, with the create early-return twin at `runtime.py:3094-3100`.
- Action authority and write-intent classification in `runtime.py:39-166,281-282`; only successful write-intent previews may advertise Apply.
- Required project context and write fallback rejection in `runtime.py:2611-2642,2780-2798`.
- Apply-time write barrier at `runtime.py:2697-2702`; it must run again for receipt apply.
- Existing manager operation logging, cross-process lock, before/after hashes, anchor digest, and CAS inputs in `src/scribe_mcp/doc_management/manager.py:61-101,154-231,1332-1375`.
- Existing edit dry-run result hashes and preview semantics in `src/scribe_mcp/doc_management/actions/edit.py:460-504`.
- JSON-safe host result normalization in `src/scribe_mcp/tools/manage_docs.py:311-322` and MCP adapter validation in `src/scribe_mcp/mcp_adapter.py:182-296`.

The existing security/session/project resolution used by `manage_docs` remains authoritative. Receipt code consumes its verified identity result; it does not infer authority from caller text.

## Missing Primitives Required Before Implementation Can Pass
<!-- ID: missing_primitives -->

Current source does not provide a complete receipt lifecycle. The implementation needs a narrowly scoped durable receipt repository with token-hash lookup, TTL, atomic compare-and-set claim, fencing, terminal-result persistence, cleanup, and crash reconciliation. It also needs:

- one shared issuer used by both the normal response finalizer and create early return;
- a server-only executor for retained normalized intent;
- action-specific precondition capture for create, edit, and rehome;
- explicit preview/apply audit linkage and token redaction tests;
- a stable result-code mapper and host-valid response tests;
- negative tests for wrong principal/session/project/repository, expiry, drift, replay, concurrent claim, storage failure, and crash recovery.

A generic session lease is not a substitute: the existing short-lived session TTL pattern lacks receipt-specific binding, durable atomic consume, terminal-result replay, and recovery semantics.

## Rejected Designs
<!-- ID: rejected_designs -->

- Client resubmits normalized arguments, target, action, diff, or hashes alongside a receipt.
- Self-contained signed/encrypted receipt carries executable internal state to the client.
- Plaintext receipt stored in the database, logs, or response metadata beyond the one issuance response.
- Process-local dictionary, cache-only state, or best-effort consumed flag.
- Preview-time authorization reused without apply-time principal, policy, barrier, path, and CAS checks.
- Delete-on-consume semantics that cannot return a deterministic result after timeout or crash.
- Trusting the public `agent` string, document metadata, or client-provided project/path as authority.
- Logging normalized intent or document content for audit/debugging.
- Advertising Apply for read-only, failed, or non-mutating dry runs.

## Verification Contract
<!-- ID: verification -->

Implementation is not security-PASS until tests prove: exact retained intent is executed; original mutation fields are rejected; the token is opaque and absent from persistence/logs; default and maximum TTL are enforced; wrong scope fails closed; policy/path/write-barrier changes are rechecked; target drift blocks; two concurrent applies produce one write; post-success retry returns the stored result; crash recovery reconciles preimage/after-state without double write; storage failure fails closed; and all responses remain MCP-host-valid.

## Evidence and Confidence
<!-- ID: evidence -->

This contract materializes the already-completed Sentinel decision recorded in the active Scribe trail and the reuse map in `research/RESEARCH_DRY_RUN_APPLY_REUSE.md`. It is consistent with `SPEC_DRY_RUN_APPLY_RECEIPT.md:30-74`. Source mappings above are high confidence where cited by the reuse artifact. Durable receipt repository shape, action-specific precondition encoding, and transaction placement remain implementation/design work; the security requirements for those gaps are fixed here.

Decision confidence: high for the public trust boundary and mandatory controls; medium-high for precise storage placement until architecture selects the existing durable backend seam.

## Handoff
<!-- ID: handoff -->
**READY for Blueprint/Forge planning only under this contract.** PASS the additive `apply: {action, receipt, expires_at}` response and `apply_preview` follow-up. BLOCK implementation or release if any mandatory binding, TTL, replay, drift, reauthorization/path, redaction, durable storage, audit, or stable-outcome requirement is absent.
