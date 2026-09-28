---
id: scribe_binding_reliability_repair_20260927-review-sbr-bind-persist-5
title: 'Quality Review: SBR-BIND-PERSIST.5'
doc_type: custom
doc_name: REVIEW_SBR_BIND_PERSIST_5
category: review
status: ready
version: '0.1'
last_updated: 2026-09-28 00:27:35 UTC
maintained_by: agent-20260928-002054-cadf0952
created_by: arbiter_sbr_bind_persist_5
owners: []
related_docs: []
tags: []
summary: 'FAIL: remote durable binding transport does not preserve ConflictError CAS
  semantics.'
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-09-28 00:25:28 UTC
  created_via: create_doc
  last_edited_at: 2026-09-28 00:27:35 UTC
  last_edited_by: agent-20260928-002054-cadf0952
  last_action: frontmatter_update
  stage: post_implementation
  work_item_id: 398c8030-60a1-4346-bc38-b9b7f535f67e
verdict: FAIL
review_role: arbiter
contract_revision: 34c8b74f546013ea5d3c451110285913a4adbbf1ede78a2d2f094aa5500e7eb4
reviewed_sha256: c3599187d1887e2e2bc00598628aee12752aa007e01776d0a9bbf9bcceabcc9a
---
# Quality Review: SBR-BIND-PERSIST.5

<!-- section: findings -->
## Findings

- **HIGH — CAS conflict semantics are not preserved across the authenticated remote transport.** `StorageBackend.set_session_project` promises `ConflictError` for a stale generation, unknown session, or unknown project (base.py:519-535). `RemoteStorageBackend.set_session_project` delegates directly to `_call` (remote.py:535-549), but `_call` only maps `StaleSession` and `ForbiddenOperation`; every other remote error becomes `RuntimeError` (remote.py:202-216). The server serializes arbitrary backend exceptions with their concrete type and HTTP 500 (server_sse.py:854-862), so a real remote `ConflictError` is not surfaced as the public contract requires. In the HTTP-500 path, `_post_json` calls `raise_for_status()` before decoding the envelope (remote.py:173-184), which can expose `httpx.HTTPStatusError` instead. This breaks backend substitutability and caller conflict handling.

Required repair: preserve the existing authenticated transport, but map the server's `ConflictError` response deterministically to `scribe_mcp.storage.base.ConflictError` before generic HTTP/error handling consumes it. Add a targeted remote-backend regression test for a stale-generation conflict using the real server envelope shape.

- **LOW — module/class documentation is stale.** remote.py:3-5 and 45-48 still state that all session management remains in-memory, while session-project binding is now durable remote state. Update the prose during the repair; this is non-blocking by itself.

<!-- section: evidence -->
## Evidence

Reviewed artifact: `src/scribe_mcp/storage/remote.py`, SHA-256 `c3599187d1887e2e2bc00598628aee12752aa007e01776d0a9bbf9bcceabcc9a`; contract revision `34c8b74f546013ea5d3c451110285913a4adbbf1ede78a2d2f094aa5500e7eb4`.

Prerequisites: Crucible behavioral PASS and Witness truth PASS are current for the same revision/content digest. Paired evidence covers import/compile, 11 auth/error tests, direct transport/reconnect/partition/strict-decoder probe, and diff-check. Reviewer-local shell execution was fenced with `WORK_ITEM_MUTATION_DENIED[BIND_MISSING]`; source was inspected through direct Scribe reads. Neighbor files read: `src/scribe_mcp/storage/base.py`, `src/scribe_mcp/storage/models.py`, `src/scribe_mcp/server_sse.py`, and `tests/test_remote_backend.py`.

Acceptance mapping: strict six-field decoding, aware timestamps, authenticated `_call` reuse, remote-authoritative reads, post-success cache mirroring, session-key partitioning, source-only scope, and explicit downstream ownership of CORE-VAL.1/.5 are supported. The error-mapping defect blocks A1's CAS behavior and API compatibility despite the happy-path evidence. CORE-VAL.1/.5 remain mandatory downstream and are not treated as missing evidence for this source-only package.

<!-- section: verdict -->
## Verdict

**FAIL.** One blocking high-severity defect prevents the remote backend from preserving the public C-01 conflict contract. Return to the implementation owner for the bounded error-mapping repair and targeted regression proof, then re-run behavioral and truth delta gates before Arbiter quality re-review. No runtime activation is claimed.
