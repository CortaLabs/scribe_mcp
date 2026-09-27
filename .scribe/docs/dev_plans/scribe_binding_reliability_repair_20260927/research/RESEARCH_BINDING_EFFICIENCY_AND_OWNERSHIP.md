---
visibility: internal
owner_principal_id: lens_sbr_efficiency_ownership
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 3df95c22d9d11cd3507a2ccccb7730fea1ccf3bd1b4795474085d6fd9f2bbeac
title: "\U0001F52C Binding Efficiency and Ownership \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-27 05:24:15 UTC
created_by: agent-20260927-051100-0431cda5
maintained_by: agent-20260927-051100-0431cda5
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:23:03 UTC
  created_via: replace_section
  last_edited_at: 2026-09-27 05:24:15 UTC
  last_edited_by: agent-20260927-051100-0431cda5
  last_action: frontmatter_update
---


# 🔬 Binding Efficiency and Ownership — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-09-27 05:21:11 UTC

> Measured Scribe binding/steady-state costs and generic-versus-Council ownership map

---
## Executive Summary
<!-- ID: executive_summary -->
Objective: measure binding/steady-state Scribe costs and define a generic Scribe versus Council integration boundary for swarm callers.

Verified (high confidence): first bound set_project(format=structured) returned 1,270.256 ms: resolve_paths 244.016 ms, targeted_refresh_after 509.829 ms, record_tool 161.235 ms, check_slug_collision 88.831 ms, ensure_documents 81.917 ms. Same-session/root warm rebind returned 291.607 ms and reused binding, skipping persistent writes: resolve_paths 136.769 ms, same_binding_reuse_probe 58.361 ms, targeted_refresh_reused 54.860 ms, record_tool 10.472 ms, update_agent_activity 31.126 ms. Warm is 4.36x faster but still spends heavily before reuse detection and on reminders.

Product contract: one stable caller session with one default project selected once; later calls explicitly target authorized registered projects across repositories without mutating ambient default. Identity uses project key/id and canonical root, never another binding call or persona label.

Handoff: Blueprint should design cached default plus explicit immutable target resolution; preserve DB-backed audit and fail-closed authorization; verify no-rebind throughput, cross-repository targeting, concurrent-seat isolation, and exact attribution.

Confidence: high for source and captured timings; medium for unmeasured cold transport startup and 100-call sequential throughput.


---
## Research Scope
<!-- ID: research_scope -->
Scope is generic public Scribe mechanisms in scribe_mcp: project/session/default selection, explicit target resolution, durable storage, filesystem durability, typed errors, offline-safe writes, and performance. Council identity, Aegis admission, work-item lifecycle, spawned-seat handoff, provider orchestration, and completion projection remain upstream in /home/austin/projects/MCP_SPINE/council_mcp; no Council schema or lifecycle logic belongs in Scribe.

Evidence: direct Scribe MCP source inspection began with read_file(scan_only), then targeted reads/search. Runtime samples were direct Scribe calls on 2026-09-27. Only the owned report was mutated.

UNKNOWN: cold process/transport startup was not reproduced. A sequential 100-call run was not completed after a long-running probe; the required reproducible measurement is specified in Recommendations, not claimed as result.


---
## Findings
<!-- ID: findings -->
System Surface Map (all confidence high unless noted)

1. Binding entrypoint: src/scribe_mcp/tools/set_project.py:659-760, set_project; records tool/activity, resolves root, binds session, and emits timing.
2. Warm binding: set_project.py:478-658, _describe_same_binding_reuse and _targeted_post_bind_refresh; router cache/session proof, DB fetch_project, root equality, reminder refresh.
3. Filesystem inventory: set_project.py:118-230, _count_log_entries and _gather_project_inventory; repeated document existence/line checks, full progress-log read/count, custom-content scan.
4. Activity/formatting: set_project.py:233-316 and 1400-1510; DB counts/recent fetches plus SITREP formatter. Readable mode blocks warm reuse.
5. Session/default state: src/scribe_mcp/state/manager.py:350-435, 430-540, 237-300; TTL project cache, per-session cache, backend reads, session/global pointers, lock-protected persistence.
6. Explicit target resolution: src/scribe_mcp/shared/logging_utils.py:91-190, 300-480; session binding, explicit DB fetch by root/name/alias, authorization, resolution metadata.
7. Durable identity: src/scribe_mcp/storage/postgres/__init__.py:2999-3139; project_key/root lookup; duplicate unscoped names fail closed; aliases can issue multiple queries.
8. Budget envelope: src/scribe_mcp/runtime_timing_envelope.py:7-66, 69-151; thresholds and phase serialization.

UI → component → state → data source → validation: no UI is in scope (UNKNOWN browser surface). Caller/tool request → set_project or LoggingToolMixin.prepare_context → router/session and StateManager caches → Postgres/SQLite rows plus repo files → root authorization, project-key disambiguation, typed errors. Confidence high.


---
## Technical Analysis
<!-- ID: technical_analysis -->
Core seams and redundant work (confidence high)

Cold/full bind (set_project.py:659-1550) records tool, updates activity, prepares context, computes authority/root, maps paths, resolves aliases, validates paths, may create directories, ensures assets/docs, hashes generated docs, checks slug collisions, upserts project/docs JSON, updates registry/state/session/recent, gathers inventory/activity, refreshes reminders, and formats output. Mutation, inventory, and human SITREP are coupled.

Warm bind skips assets/docs/upsert/registry/state/session writes and agent-recent updates (set_project.py:931-1039) but still pays record_tool, root/path resolution, router-cache plus fetch_project/binding proof, and reminder refresh.

Filesystem duplication: four doc checks, full progress-log count, and custom scan (set_project.py:118-230); DB activity separately does four count_entries plus one recent-entry fetch (233-316); formatter serializes another response.

DB duplication: explicit resolution may do scoped fetch, unscoped fallback, alias list, canonical and denormalized probes (logging_utils.py:342-480; postgres/__init__.py:2999-3139). set_project independently alias-fetches, slug-check fetches/lists, and upserts (set_project.py:398-437, 1040-1180).

Transport/audit: every tool enters StateManager.record_tool. Captured append_entry log timing is 87.737 ms (DB fetch 52.974, DB insert 9.045, WAL 20.205, formatting 0.059); generic read phase timing is UNKNOWN and should be instrumented.

Existing caches: StateManager project TTL cache and per-session cache, router current-project cache, and asyncpg pool max 20 (storage/postgres/__init__.py:147-180). Invalidation is local/manual; do not introduce global flush.

Invariants: session/actor default is authoritative; global fallback is actor-less legacy only (state/manager.py:464-527). Names alone are insufficient across repos; project_key combines normalized root and name; duplicate unscoped names fail closed (postgres/__init__.py:2999-3050). Root authorization is fail-closed (set_project.py:760-850, 1550-1640). Audit retains stable session, actor, project key/root, and correlation.

Risks: warm rebind 291.607 ms remains dominated by root resolution and reminder refresh; StateManager lock can serialize dozens of seats; inventory is O(files + log bytes); alias ambiguity must return typed candidates/reasons, never guess.


---
## Recommendations
<!-- ID: recommendations -->
Implementation-ready generic Scribe packages

1. Session/default selector (scribe_mcp): reuse state/manager.py:237-300, 430-527 and router context. Persist stable session→default, actor-scoped attribution, idempotent rebind. Target warm default p95 ≤150 ms, p99 ≤300 ms; zero writes for unchanged binding; no global invalidation.
2. Explicit target resolver (scribe_mcp): integrate logging_utils.py:342-480 and postgres/__init__.py:2999-3139. Resolve once by project key/id or canonical root+name; typed ambiguity/authorization candidates; leave default untouched. Target p95 ≤200 ms local DB; cross-repo authorized target succeeds without set_project.
3. Inventory/format separation (scribe_mcp): integrate set_project.py:118-316, 1400-1510. Machine bind must not read files; cache metadata by path+mtime/size and DB activity by project key, invalidating only changed project/stream. Inventory p95 ≤250 ms unchanged.
4. Durability/offline writer (scribe_mcp): preserve DB-first plus append/WAL; retry connection-local failure idempotently using correlation IDs and durable queue. No Council fields. No acknowledged write may be dropped; replay deduplicates.
5. Transport telemetry (scribe_mcp): extend runtime_timing_envelope.py:7-151 to generic resolution/backend/filesystem/serialization/transport-visible phases and p50/p95/p99.

Swarm contract: one caller session selects one default once. Any registered Scribe project, including another repo, is explicitly targetable by stable id/key or canonical root+name when authorized; explicit calls do not mutate default or require set_project. Audit includes stable session, actor, project id/key, canonical root/repo id, tool, correlation id, status. Separate actor-scoped cache keys; pooled connection-safe operations; no global flush and no persona identity.

Required 100-call no-rebind test: bind once; invoke a machine-readable read tool 100 times with same session and no set_project; record wall/per-call durations. Assert same default, no default mutation, no repeated bind, no cross-seat attribution. Report p50/p95/p99 and calls/sec. Proposed local warm budgets: p95 ≤150 ms, p99 ≤300 ms, total ≤15 s (≥6.7 calls/sec). Readable inventory separate p95 ≤250 ms. Confidence medium: targets proposed.


---
## Appendix
<!-- ID: appendix -->
Existing verification surfaces

Direct evidence: cold structured set_project 1,270.256 ms; warm same-session/root 291.607 ms with binding_reused=true and skipped-write list.

Current source thresholds runtime_timing_envelope.py:7-11: cold warn/fail 5,800/7,000 ms; warm-bound warn/fail 600/1,200 ms; set_project warn/fail 17,292/22,000 ms. These do not enforce no-rebind machine-call budgets.

Five parallel read_recent(n=1, compact) calls completed in 8,971 ms wall (~1.79 s/call equivalent under this MCP dispatch; not a sequential throughput claim). The sequential 100-call probe was not completed; use the harness above.

Targeted verification should cover set_project, StateManager, resolve_logging_context, Postgres project lookup, and timing envelope, plus import smoke. Report QA: non-empty, every finding has confidence, paths/line anchors, explicit UNKNOWNs, and quality_check without blocking scaffold/frontmatter warnings.

Handoff READY: keep generic Scribe session/default/target/durability/performance in scribe_mcp; Council identity, Aegis, work-item/spawn lifecycle, orchestration, and completion projection as council_mcp adapters. Preserve project-key/root/session audit invariants and verify cross-repo targeting plus concurrent-seat matrix.


---