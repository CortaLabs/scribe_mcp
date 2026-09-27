---
visibility: internal
owner_principal_id: crucible_sbr_swarm_validation
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: 511d2aa18fb35e29ec10e9784eef53d1dc1333f8550d351557162a7642f91284
title: "\U0001F52C Swarm Concurrency Validation \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-27 20:15:28 UTC
created_by: agent-20260927-051300-81d63b66
maintained_by: agent-20260927-200633-2018bd79
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:21:59 UTC
  created_via: replace_section
  last_edited_at: 2026-09-27 20:15:28 UTC
  last_edited_by: agent-20260927-200633-2018bd79
  last_action: replace_text
  work_item_id: 20641dc9-386f-453b-80bf-30597d035db4
summary: Implementation-ready generic Scribe regression, stress, fault, replay, and
  adapter validation matrix for 32+ concurrent callers.
owners:
- Crucible
tags:
- scribe
- concurrency
- regression
- load
- fault-injection
---


# 🔬 Swarm Concurrency Validation — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-09-27 05:15:00 UTC

> Implementation-ready Scribe concurrency validation matrix covering default isolation, explicit targeting, reconnect, managed docs, offline replay, performance, and provider boundaries.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary objective:** define an implementation-ready, provider-neutral validation system for Scribe binding reliability under dozens of concurrent callers, multiple repositories and projects, identical caller labels, explicit target overrides, reconnects, managed-document mutations, outage recovery, and mixed read/write traffic.

**Verdict:** READY for Blueprint decomposition. The required behavior can be covered by two deliberately separate lanes:

1. A fast hermetic regression lane with **32 independent application sessions**, all using the canonical `test_agent == "test-agent"` label. Every session calls `set_project` exactly once and then performs **100 mixed calls** (3,200 calls total) through the real Scribe dispatch/context path against disposable repositories and storage.
2. An opt-in PostgreSQL/process stress lane that scales to 32/64/128 callers, injects reconnects and faults, runs a sustained soak, and emits percentile, throughput, RSS, isolation, replay, and error-budget artifacts.

Correctness is cardinality-based, not inferred from green responses: every operation has a deterministic `operation_id`, expected default project, expected effective target, caller/session key, repository key, and mutation fingerprint. Post-run reconciliation must prove zero wrong-target writes, zero lost accepted writes, zero duplicates, zero default-binding drift, zero cross-session reconnect theft, and exactly-once replay.

The current suite already contains useful narrow contracts for two-actor binding, same-label application identities, explicit project resolution, managed-anchor CAS, timing payloads, and live PostgreSQL races. It does not currently contain the required 32-session mixed-operation matrix, deterministic unrelated-repository non-serialization proof, or crash-window WAL exactly-once coverage. Those are the principal validation gaps this report packages.

**Boundary:** this report tests generic public Scribe contracts. Codex/Claude naming, Council work items, Aegis admission, spawn/bind hooks, roster projections, and provider-specific lifecycle behavior are downstream `council_mcp` acceptance concerns and must not be imported into Scribe tests.


---
## Research Scope
<!-- ID: research_scope -->
**Research lead:** Crucible
**Investigation window:** 2026-09-27
**Work item:** `SBR-CONC-04` / `20641dc9-386f-453b-80bf-30597d035db4`

### Included public contracts

- `set_project` establishes one session/application-scoped ambient default and is invoked once per caller in the principal matrix.
- A later explicit `project=` target selects only that call's authorized destination and never mutates the caller's ambient default.
- Multiple callers with the same human label remain isolated by server-owned application/session identity.
- Projects in multiple canonical repositories remain isolated; repeated project labels either resolve by persisted repo/project authority or fail closed with typed ambiguity.
- A reconnect restores only the reconnecting application's persisted session/default and cannot clear, steal, or reuse another caller's binding.
- Reads, audit-log appends, managed-document reads/writes, explicit targeting, runtime restore, and offline/WAL replay can execute concurrently without cross-talk.
- Accepted replayable mutations take effect exactly once despite retry, duplicate replay invocation, or crash at each durability boundary.
- Unrelated repositories are not forced through a repository-global or process-global serialization point.
- Modern and legacy Scribe adapters preserve the same behavior and observable error contract.

### Excluded / separately owned

- Council seat admission, Aegis, work-item claims, provider spawn identity, hook projections, Engineering Team labels, and Codex/Claude host integration are not Scribe source contracts.
- Public deployment, production credentials, real operator projects, and shared live databases are out of scope.
- Performance numbers are release budgets for a named reference profile, not universal promises across arbitrary hardware.

### Evidence inspected

- Session/application identity and context: `src/scribe_mcp/shared/execution_context.py`, `src/scribe_mcp/shared/tool_runtime.py`.
- Project resolution and ambient/default behavior: `src/scribe_mcp/shared/logging_utils.py`, `src/scribe_mcp/state/manager.py`.
- Mutation paths: `src/scribe_mcp/tools/append_entry.py`, `src/scribe_mcp/tools/manage_docs.py`.
- Recovery path: `src/scribe_mcp/utils/files.py::WriteAheadLog`, `src/scribe_mcp/server.py::_replay_journals_background`.
- Existing test owners: `tests/shared/test_actor_scoped_session_binding.py`, `tests/shared/test_multi_project_global_pointer_isolation.py`, `tests/shared/test_session_repo_root_poisoning.py`, `tests/test_manage_docs_anchor_cas.py`, `tests/test_tools.py`, and PostgreSQL integration tests under `tests/integration/storage/`.
- Provider-neutral adapter coverage: `tests/test_mcp_adapter.py`, `tests/security/test_session_provenance.py`, and `tests/migration/mcp_v2/test_compatibility_matrix.py`.

RI test routing was attempted but could not resolve an active repo-intel project/version scope. Structural claims therefore use direct source/test inspection; the failed RI response is not treated as absence evidence.


---
## Findings
<!-- ID: findings -->
### F1 — Identity isolation must be tested independently of the caller label

- **Finding:** `agent` is display/audit metadata, not a sufficient concurrency key. The regression swarm must give all 32 callers the same `test_agent` value while distinguishing them through server-owned application identity and persisted session keys.
- **Evidence:** `ApplicationIdentity` and `RouterContextManager` are the source-level isolation surfaces. Existing tests prove only small cases: two actors, two modern application handles, and one reconnect.
- **Required assertion:** 32 distinct authoritative session keys and 32 stable default bindings survive interleaving, reconnect, and cleanup of a single caller.
- **Confidence:** High.

### F2 — The principal regression must be one bind plus 100 mixed calls per caller

- **Finding:** A loop of only `append_entry` calls would miss resolution changes introduced by read, document, restore, and explicit-target paths.
- **Required topology:** four disposable repositories × four projects per repository × two callers per default project = 32 sessions. Every caller uses the same label. Each session calls `set_project` once, then executes a seeded 100-operation schedule (3,200 calls total).
- **Operation mix per caller:** 30 ambient log appends, 20 reads (`get_project`, `read_recent`, `query_entries`), 20 managed-doc operations (create/read/replace/quality against caller-owned anchors), 15 explicit same-repo project operations, 5 authorized cross-repo explicit operations, 5 reconnect/restore observations, and 5 negative/fault/replay operations.
- **Required assertion:** `set_project_count[session] == 1`; after every explicit target and at final reconciliation, the ambient default remains the original project.
- **Confidence:** High.

### F3 — Success responses are insufficient; use an expected-effects ledger

Every scheduled operation receives immutable fields:

```text
run_id | operation_id | logical_caller | application_identity_key
stable_session_id | agent_label | default_repo | default_project
explicit_target_repo? | explicit_target_project? | expected_effect
mutation_fingerprint | expected_result_code
```

The post-run oracle reads session bindings, persisted log entries, document bodies/registrations, and replay journals. It compares exact multisets of operation IDs and fingerprints. The release gate is:

- wrong-target effects = 0;
- accepted-but-missing effects = 0;
- duplicate effects = 0;
- unexpected effects after denied calls = 0;
- default-binding changes outside `set_project` = 0;
- untyped/ambiguous resolution = 0.

This prevents a routing bug from hiding behind `{"ok": true}` or behind a read that accidentally sees another project.

**Confidence:** High.

### F4 — Explicit targeting needs four independent cases

1. Ambient call: resolves to the caller's bound default.
2. Authorized same-repository explicit target: lands only in that target and leaves ambient default unchanged.
3. Authorized cross-repository explicit target: lands only in the persisted authorized target and leaves ambient default unchanged.
4. Missing, ambiguous, or unauthorized target: returns a typed denial/candidate set and causes zero file, DB, document-index, session-binding, or recent-project mutation.

The matrix should deliberately reuse the same project slug in more than one repository. If duplicate names are not supported by the public registry contract, the expected result is typed ambiguity rather than last-writer or process-global selection.

**Confidence:** High.

### F5 — Reconnect and cleanup are separate fault domains

- Reconnect the same server-minted application handle through a new transport connection and a fresh `RouterContextManager`; it must recover exactly its persisted stable session/default.
- Create a new application handle with the same principal and same `test_agent` label; it must not inherit the prior caller's session/default.
- Cleanup/revoke one caller; all other callers' bindings and reads must remain unchanged.
- Clear process caches/recreate the runtime before restore assertions so the test proves persistence, not an in-memory dictionary.

Existing reconnect tests establish the narrow mechanism, but do not combine it with 32 concurrent callers or mixed mutations.

**Confidence:** High.

### F6 — “No global serialization” needs a deterministic overlap test

Wall-clock speed alone cannot prove absence of a process-global lock. Inject a storage/file-operation probe with per-repository `entered` and `release` events:

1. Repo A enters a blocked write.
2. While A remains blocked, start Repo B's unrelated write.
3. Require B to reach its own backend/file checkpoint before A is released.
4. Repeat with A/B reversed and for read-vs-write, log-vs-doc, and restore-vs-log pairs.

The assertion is causal overlap, not “finished under N ms.” A short `asyncio.wait_for` is only the deadlock bound. The stress artifact additionally reports per-repo active-operation overlap and starvation.

**Confidence:** High.

### F7 — WAL/offline replay has uncovered exactly-once crash windows

`WriteAheadLog.replay_uncommitted()` currently scans uncommitted records, applies each append, then writes a commit record. Required regression cases are:

- crash after journal write, before main-log apply;
- crash after main-log apply, before journal commit;
- two replay workers racing the same journal;
- replay invoked twice after success;
- malformed/truncated journal tail beside valid records;
- one project's replay failure while unrelated projects recover;
- accepted DB-mirror/offline work restored after backend recovery.

For every accepted `operation_id`, final file/DB cardinality must be exactly one. The “apply succeeded but commit was not durable” and concurrent-replayer cases are especially important; current tests do not prove them and the present append-then-commit shape is a high-risk duplicate window. This report does not claim current implementation passes.

**Confidence:** High.

### F8 — Performance must be separated from correctness

The hermetic lane asserts deterministic state and bounded completion only. Release performance is measured in an opt-in reference environment after warmup, with per-operation-type histograms and RSS samples. A single blended latency number would hide slow managed-doc or replay paths.

**Confidence:** High.

### F9 — Cross-provider acceptance is a downstream composition gate

Scribe should parameterize its provider-neutral trace across public adapter modes: modern stdio, modern streamable HTTP, legacy stdio, and legacy HTTP/SSE where supported. The same logical oracle must produce the same targets and typed failures.

A separate `council_mcp` gate must certify Codex and Claude host projections, spawn/bind behavior, Aegis/work-item admission, and hook identity. Passing that downstream gate must not be required to run or understand Scribe's core suite.

**Confidence:** High.


---
## Technical Analysis
<!-- ID: technical_analysis -->
### A. Test architecture

Build one reusable provider-neutral swarm harness in `tests/fixtures/swarm.py`:

- `SwarmTopology`: creates only `tmp_path` repositories, `.git` markers, projects, progress logs, managed docs, and disposable storage.
- `CallerSpec`: logical caller number, shared `test_agent` label, server-minted application identity, stable session ID, default repo/project, permitted explicit targets, and reconnect material.
- `OperationSpec`: deterministic operation ID, operation kind, explicit target (optional), mutation fingerprint, expected result code, and expected effect.
- `SwarmOracle`: records expected effects before dispatch and reconciles session rows, project rows, log entries, document registrations/bodies, journal records, and result codes after dispatch.
- `GateBackend`: delegates to the real ephemeral backend while exposing event checkpoints for deterministic overlap and fault injection; it must not mock the routing/context unit under test.
- `MetricSink`: monotonic start/end timestamps, operation type, target repo/project, caller/session, result code, RSS sample, retry/replay flag, and fault phase.

All tests receive the canonical `test_agent` fixture. The caller label is intentionally identical; unique persona slugs are forbidden. Mutable fixtures are function-scoped and tear down files, sessions, databases, processes, ports, and environment changes.

### B. Light CI regression matrix

**Topology:** 4 repos × 4 projects × 2 sessions = 32 callers. Use duplicate caller and project labels deliberately. Generate all application identities first, then concurrently issue one `set_project` per caller. Freeze the resulting default-binding map.

**Schedule:** each caller receives exactly 100 operations from a fixed seed. Run operations in 100 barriers: at barrier `n`, all 32 callers issue their `n`th operation concurrently, but the caller ordering is deterministically permuted. This gives 3,200 calls with repeatable interleavings and avoids a scheduler-dependent random test.

| Calls per caller | Operation family | Required checks |
|---:|---|---|
| 30 | Ambient `append_entry` | Effect exists once in default target; response timing schema present |
| 20 | `get_project`, `read_recent`, `query_entries` | Reads expose only authorized/default target data and never mutate state |
| 20 | Managed docs: create/read/replace/quality | Registration and bytes remain in effective target; disjoint anchors both succeed; same-anchor stale writer is typed |
| 15 | Explicit same-repo target | Effect exists once only in target; default remains frozen |
| 5 | Explicit authorized cross-repo target | Persisted authority selects exact repo/project; default remains frozen |
| 5 | Reconnect/restore observations | Same application identity restores same stable session; peer bindings unchanged |
| 5 | Denial/fault/replay probes | Typed denial or exactly-once effect; no collateral mutation |

At operations 25, 50, 75, and 100, every caller performs a bare default read after any explicit call. At operation 50, rebuild the runtime/router from persisted storage for eight callers. At operation 75, clean up one selected caller and prove the other 31 remain unchanged.

**Core assertions:**

- exactly 32 `set_project` calls and exactly one per caller;
- 32 distinct authoritative session identities despite one shared label;
- each caller's post-run default equals its frozen initial default;
- explicit writes appear only in their target;
- denied writes appear nowhere;
- actual mutation fingerprints equal the expected multiset;
- every read result is a subset of its authorized visibility;
- expected CAS conflicts are typed and cause no partial write;
- no pending tasks, open handles, temp repositories, or modified process globals after teardown.

The core test uses real dispatch/context/resolution and real temporary files/storage. It may fake only external infrastructure. It carries `core` + `regression` and must remain offline.

### C. Deterministic non-serialization gate

Add a focused causal test independent of the 3,200-call matrix. `GateBackend` blocks Repo A after it enters the actual persistence/file boundary. Repo B must reach its own corresponding boundary before A is released. Parameterize:

- log write A vs log write B;
- managed-doc write A vs log write B;
- slow read A vs write B;
- reconnect/restore A vs write B;
- replay A vs ambient write B.

Run each pair in both directions. Record span intervals and require overlap. This proves unrelated repositories can progress concurrently even if one repository is stalled. It does not prohibit short critical sections for process-local caches; it prohibits holding a shared lock across repository I/O or a complete tool call.

### D. Fault and replay matrix

| Fault point | Injection | Required result |
|---|---|---|
| Before dispatch | malformed/missing/ambiguous explicit target | Typed fail-closed result; zero mutation |
| After context creation | cancel one caller | ContextVar reset; peers unaffected |
| During DB lookup/write | pause or transient exception for Repo A only | Repo B progresses; accepted operations recover or fail explicitly |
| After journal write / before apply | synthetic crash | One effect after replay |
| After apply / before commit | synthetic crash | No duplicate after replay |
| Concurrent replay | two fresh runtime instances replay same journal | One effect, one terminal/observed replay result |
| Truncated journal tail | append partial JSON after valid records | Valid records recover once; corruption is surfaced/contained |
| Managed-doc CAS | same anchor, same precondition | One winner; typed stale loser; valid document |
| Runtime restart | discard all in-memory caches | Persisted identity/default restored independently |
| Transport reconnect | reconnect one application handle; mint another same-label handle | Reconnected caller reuses only its session; new handle gets no stolen default |
| Cleanup/revoke | close one caller during peer activity | Only that caller loses access/cache; peers continue |
| DB mirror outage | file/WAL accepts or tool explicitly rejects according to contract | No silent success; recovered accepted effects exactly once |

If the implementation does not durably accept offline work, the expected outcome is an explicit unavailable result and zero effect. “Exactly once” applies only to operations the API reported as accepted/durable.

### E. Scalable PostgreSQL/process stress and soak

The operator lane runs against a throwaway PostgreSQL database/schema and disposable repository roots. It must never use configured operator projects or production credentials.

**Profiles:**

- smoke: 32 callers × 100 calls; approximately 3,200 operations;
- release: 64 callers, 5-minute warmup + 30-minute measured soak + 5-minute recovery;
- extended: 128 callers, 10-minute warmup + 120-minute soak + 10-minute recovery.

**Measured mix:** 30% log appends, 25% reads/queries, 15% managed-doc mutations/quality reads, 10% explicit targeting, 10% reconnect/runtime restore, and 10% injected outage/offline replay. Each repo gets an equal offered load. Faults rotate across repos so one degraded repo cannot hide starvation elsewhere.

**Reference release budgets** (record hardware, Python, Scribe revision, PostgreSQL version/config, caller count, and seed with every result):

| Metric | Budget |
|---|---:|
| Wrong-target, cross-talk, lost accepted, duplicate, or default-drift count | **0** |
| Unexpected permanent errors outside injected faults | **0** |
| Transient operation error rate outside injected faults | **≤ 0.1%** |
| Accepted operations unreconciled 60 s after recovery | **0** |
| Read/query p50 / p95 | **≤ 75 ms / 250 ms** |
| Log append p50 / p95 | **≤ 150 ms / 600 ms** |
| Managed-doc mutation p50 / p95 | **≤ 300 ms / 1,500 ms** |
| Reconnect/restore p50 / p95 | **≤ 250 ms / 1,000 ms** |
| Replay per accepted operation p50 / p95 | **≤ 200 ms / 750 ms** |
| Aggregate steady-state throughput at 32 callers | **≥ 50 completed ops/s** |
| 32-caller throughput vs four isolated 8-caller repo runs | **≥ 75% of summed isolated throughput** |
| Repo starvation | **No repo with a 10 s zero-completion window outside its injected fault** |
| RSS growth from post-warmup baseline | **≤ 256 MiB peak; ≤ 64 MiB retained after recovery/GC** |
| RSS slope over final 20 measured minutes | **≤ 2 MiB/min** |
| Open tasks/handles/sessions after teardown | **0 above recorded baseline** |

Absolute latency/throughput budgets are for the named reference runner. Other machines still enforce zero correctness errors and compare performance to a stored same-profile baseline: p95 regression ≤20%, throughput regression ≤15%, retained-RSS regression ≤64 MiB.

Emit machine-readable JSON plus a concise Markdown summary under the gitignored `benchmarks/artifacts/` path. Required raw fields are operation type, start/end monotonic time, caller/session, target repo/project, status/result code, retry/replay flag, fault phase, and RSS sample. Derived fields include p50/p95/p99, throughput per 10-second bucket, max concurrent operations, overlap ratio, per-repo starvation windows, error taxonomy, and final oracle cardinalities.

### F. Adapter and provider boundaries

Run the same compact logical trace (bind, ambient write, explicit write, default readback, reconnect, denial) through:

- direct in-process public tool dispatch for the fast core;
- modern stdio real client;
- modern streamable HTTP with server-minted application handles;
- legacy stdio;
- legacy HTTP/SSE where still a supported public transport.

Adapter parity means identical effective targets, ambient default invariance, replay cardinality, and typed error categories; response formatting may differ only where the public compatibility contract permits it.

Downstream `council_mcp` acceptance is separate and should consume a published Scribe candidate. It must validate at least Codex and Claude adapter/projection paths, Council spawn/bind, Aegis/work-item admission, and hook identity. A Scribe failure is reproduced against its provider-neutral trace before assigning it to Scribe; Council-only behavior stays upstream.


---
## Recommendations
<!-- ID: recommendations -->
### Implementation package 1 — Hermetic swarm harness and core contract

**Candidate files**

- create `tests/fixtures/swarm.py`;
- create `tests/core/test_swarm_binding_reliability.py`;
- extend narrow existing owners only where their helper is reused: `tests/shared/test_actor_scoped_session_binding.py`, `tests/shared/test_session_repo_root_poisoning.py`, and `tests/test_manage_docs_anchor_cas.py`.

**Acceptance**

- 32 same-label application sessions across four repos/four projects execute one `set_project` plus 100 mixed calls each;
- exact-effects reconciliation is clean;
- deterministic unrelated-repo overlap passes in both directions;
- runtime/cache rebuild and single-caller cleanup preserve all other defaults;
- test uses `test_agent`, `tmp_path`, function-scoped mutable fixtures, no network, and `core` + `regression` markers.

### Implementation package 2 — Replay durability and crash-window regression

**Candidate file**

- create `tests/core/test_wal_replay_exactly_once.py` rather than mixing crash recovery into generic tool tests.

**Acceptance**

- covers both sides of every durability boundary, concurrent replayers, repeated replay, truncated tail, and one-project failure isolation;
- final cardinality is exactly one per accepted operation ID;
- no test mutates a real project or uses a live database;
- failures found here return to the production owner; Crucible does not weaken the oracle.

### Implementation package 3 — PostgreSQL stress/soak runner

**Candidate files**

- create `tests/integration/test_swarm_concurrency_stress.py`;
- extend `tests/integration/storage/conftest.py` only if its throwaway database fixture cannot safely supply the runner;
- create `benchmarks/swarm_concurrency.py` only as a thin operator/reporting entrypoint over the same harness, not a second implementation.

**Acceptance**

- smoke/release/extended profiles are selected by environment, not hardcoded forks;
- `integration`, `postgres`, `performance`, and `slow` markers keep it out of default CI;
- emits JSON and Markdown metrics under `benchmarks/artifacts/`;
- enforces zero correctness defects and the named reference budgets;
- tears down database/schema, temp repos, journals, processes, ports, sessions, and artifacts-on-failure bookkeeping.

### Implementation package 4 — Public adapter parity

**Candidate files**

- extend `tests/migration/mcp_v2/test_compatibility_matrix.py`;
- extend `tests/security/test_session_provenance.py` for same-label reconnect/identity denial if the core harness exposes a reusable compact trace.

**Acceptance**

- compact bind/write/explicit-target/readback/reconnect/deny trace passes for each supported public adapter;
- target/default/error semantics match across adapters;
- no Council imports, Aegis state, work-item state, roster labels, or generated projection assumptions appear in Scribe tests.

### Implementation package 5 — Foreground tripwire and bounded background-queue proof

This package composes the 32-caller exact-effects oracle with `RESEARCH_BACKGROUND_QUEUE_VALIDATION_DELTA.md`; the requirements below are part of this report's release gate, not an optional follow-up.

**Foreground rule and 500 ms tripwire**

- Foreground completion means the public call returns its synchronous result or a durable receipt only after canonical identity/target resolution, authorization, validation, idempotency reservation, capacity admission, and the required durability commit.
- Any foreground total above **500 ms** emits a correlated slow-call event and fails the named reference-profile budget unless the public contract is explicitly asynchronous and returns a receipt that survives fresh-runtime readback. The hermetic lane crosses the 100 ms stage and 500 ms total boundaries with a manual clock; it never uses wall-clock sleeps.
- The operator lane reports synchronous control/read latency and durable-receipt acknowledgement separately from queue wait and job run time. Both foreground control/read p95 and receipt-acknowledgement p95 are **<= 500 ms**; every individual >500 ms occurrence remains visible in the tripwire count and trace.
- Expensive work is not made asynchronous merely to satisfy latency. Synchronous reads still return data, and authoritative writes complete their declared durability obligation before success.

**Deterministic boundedness, load balance, fairness, and backpressure**

- Configure `max_pending_items=8`, `max_pending_bytes=1024`, per-project pending items `=4`, global heavy concurrency `=2`, per-project heavy concurrency `=1`, and one reserved control slot. Ready, retry-delayed, and leased/running receipts all consume capacity.
- Race 32 same-label callers against one remaining item slot and one remaining byte slot. Exactly one new receipt may be accepted; every other call returns the typed busy/deduplicated/conflict outcome immediately. Item, byte, and concurrency high-water marks must equal or remain below their configured bounds at every checkpoint. No caller waits for a worker or for queue space to appear.
- Drive three continuously eligible, equal-weight project partitions with 12 unit jobs each one scheduler decision at a time. The maximum start-count lead is one, no project receives more than 50% of starts/service while a peer is eligible, a saturated or retry-delayed partition is skipped, and a control job starts within one round despite a full heavy backlog. A 2:1:1 weighted run must match 50%:25%:25% within one quantum.
- Four equal-capacity workers claiming 32 unit jobs differ by at most one claim. Global and per-project caps hold continuously, each receipt has at most one active lease, expired workers are fenced, and replacement workers restore capacity without oversubscription.

**Causal no-head-of-line and recovery proof**

Block Project A after claim, then require Project B and Project C to reach claim and completion before A is released. Repeat while A is ready, running, retry-delayed, cancelling, dead-lettering, draining, and at its item/byte/per-project bounds; repeat with 31 callers targeting A and one caller targeting B. Event ordering is the assertion; a timeout is only a deadlock guard. The gate fails on a global FIFO head, repository-spanning lock, held transaction, or scheduler scan that prevents B/C progress.

Worker death, stale completion, retry, cancellation, shutdown, and fresh-runtime restart reuse the same durable receipt and mutation-fingerprint oracle. Every accepted receipt remains queryable after restart, every authoritative effect occurs exactly once, stale-fence completion is rejected, capacity is released exactly once, and non-admitted work creates no receipt or effect.

**Observable operator budget and lanes**

The light CI lane extends the shared `tests/fixtures/swarm.py` harness and adds `tests/core/test_background_queue_contract.py`, using `test_agent`, `tmp_path`, a manual clock, a disposable durable-receipt store, gated real workers, and no live network or database. It is `core` + `regression` and reuses `tests/core/test_wal_replay_exactly_once.py` rather than creating a second replay oracle.

The capability-gated `background-queue` profile extends `tests/integration/test_swarm_concurrency_stress.py` and runs at least 32 sessions, 16 canonical project partitions, four workers, global heavy concurrency four, and per-project heavy concurrency one against disposable PostgreSQL and repository roots. In addition to the base p50/p95/throughput/RSS/error budgets, it records queue depth/bytes, ready/delayed/leased counts, oldest eligible age, admission outcomes, queue-wait/run histograms, per-project service share, worker claims, retry/cancel/lease/fence events, and shutdown/restart reconciliation.

The operator gate permits zero queue item/byte/concurrency-bound violations, zero accepted stale-fence completions, no continuously eligible project starvation window >=5 seconds, no equal-weight project above 50% service while a peer is eligible, no unit-job worker imbalance above one claim, and zero open tasks/handles/workers above teardown baseline. The same `swarm-results.json` source of truth carries foreground/receipt histograms, high-water marks, service shares, worker claims, starvation windows, and restart reconciliation; the Markdown summary is derived from it.

### Downstream package — council_mcp composition acceptance

Create a separate `council_mcp` work item after a Scribe candidate exists. It should run Codex and Claude host paths against the candidate and verify spawn/bind, Aegis/work-item admission, hooks, and generated projections. Its failures are not automatically Scribe defects; reduce any suspected Scribe issue to the provider-neutral trace first.

### Gate decision

Blueprint may turn these into implementation packages immediately. Release remains BLOCKED until packages 1–5 pass for the same source revision, the operator stress artifact meets correctness, error, foreground, queue, and resource budgets, and any replay or queue red tests are repaired without weakening exactly-once semantics.


---
## Appendix
<!-- ID: appendix -->
### Exact candidate locations

| Purpose | Candidate location | Reuse/placement rationale |
|---|---|---|
| Shared scenario/ledger/gate/metrics fixtures | `tests/fixtures/swarm.py` | One fixture owner for core and integration lanes; no duplicated harness |
| 32×100 hermetic contract + non-serialization | `tests/core/test_swarm_binding_reliability.py` | Auto-marked `core`; add `regression`; shipped binding contract |
| WAL/offline crash windows | `tests/core/test_wal_replay_exactly_once.py` | Fast `tmp_path` durability contract, separate from unrelated tool tests |
| Live PostgreSQL stress/soak | `tests/integration/test_swarm_concurrency_stress.py` | Auto-marked `integration`; explicitly mark `postgres`, `performance`, `slow` |
| Disposable Postgres support, only if needed | `tests/integration/storage/conftest.py` | Existing throwaway DB owner |
| Real-client adapter parity | `tests/migration/mcp_v2/test_compatibility_matrix.py` | Existing modern/legacy stdio/HTTP owner |
| Application identity/reconnect security | `tests/security/test_session_provenance.py` | Existing minted-handle and pre-dispatch-denial owner |
| Optional operator entrypoint | `benchmarks/swarm_concurrency.py` | Thin wrapper over `tests/fixtures/swarm.py`; writes only gitignored artifacts |

### Fixture contracts

- `test_agent`: mandatory canonical label for every simulated caller.
- `swarm_topology(tmp_path)`: returns four canonical repo roots, registered projects, and owned log/doc paths.
- `swarm_backend`: function-scoped SQLite/in-memory implementation for core; no live state.
- `swarm_postgres_backend`: disposable database/schema based on existing integration fixture behavior.
- `swarm_callers(test_agent, swarm_topology)`: 32 server-owned application identities with one shared label.
- `swarm_schedule(seed=20260927)`: exact 100-operation schedule per caller.
- `swarm_oracle`: expected-effects ledger and final cardinality/isolation assertions.
- `gate_backend`: actual-backend decorator exposing event checkpoints without mocking the routing unit.
- `metric_sink`: JSON-safe raw metrics and percentile/RSS derivation.
- `fault_controller`: scoped one-shot faults keyed by repo, operation ID, and durability phase.

### Targeted commands

Light CI contract:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q   tests/core/test_swarm_binding_reliability.py   tests/core/test_wal_replay_exactly_once.py   -m "core and regression and not slow and not performance"
```

Direct neighboring contracts:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q   tests/shared/test_actor_scoped_session_binding.py   tests/shared/test_multi_project_global_pointer_isolation.py   tests/shared/test_session_repo_root_poisoning.py   tests/test_manage_docs_anchor_cas.py   tests/test_append_entry_explicit_project_resolution.py   tests/test_query_entries_explicit_project_resolution.py
```

Provider-neutral real-client adapter gate:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q   tests/migration/mcp_v2/test_compatibility_matrix.py   tests/security/test_session_provenance.py   -m "core or regression"   -k "stdio or http or application_handle or reconnect"
```

Operator smoke stress:

```bash
SCRIBE_TEST_POSTGRES_URL=<disposable-admin-dsn> SCRIBE_SWARM_PROFILE=smoke SCRIBE_SWARM_CALLERS=32 SCRIBE_SWARM_CALLS_PER_CALLER=100 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/swarm-smoke PYTHONPATH=src ./.venv/bin/pytest -q   tests/integration/test_swarm_concurrency_stress.py   -m "integration and postgres and performance and slow"
```

Operator release soak:

```bash
SCRIBE_TEST_POSTGRES_URL=<disposable-admin-dsn> SCRIBE_SWARM_PROFILE=release SCRIBE_SWARM_CALLERS=64 SCRIBE_SWARM_WARMUP_SECONDS=300 SCRIBE_SWARM_DURATION_SECONDS=1800 SCRIBE_SWARM_RECOVERY_SECONDS=300 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/swarm-release PYTHONPATH=src ./.venv/bin/pytest -q   tests/integration/test_swarm_concurrency_stress.py   -m "integration and postgres and performance and slow"
```

Do not run the repository-wide suite for this package. Implementation verification must additionally run import smoke for every production module actually modified, plus direct neighbor tests importing those modules.

### Required stress artifact

`swarm-results.json` should contain:

```json
{
  "schema_version": "scribe-swarm-results.v1",
  "source_revision": "...",
  "profile": "release",
  "seed": 20260927,
  "environment": {},
  "topology": {},
  "budgets": {},
  "operation_histograms": {},
  "throughput_buckets": [],
  "rss_samples": [],
  "fault_timeline": [],
  "oracle": {
    "wrong_target": 0,
    "missing_accepted": 0,
    "duplicates": 0,
    "default_drift": 0,
    "reconnect_theft": 0,
    "unreconciled_after_recovery": 0
  },
  "verdict": "PASS"
}
```

The Markdown summary must be generated from this JSON, never maintained as an independent result source.

### Readiness checklist for Blueprint

- [x] At least 32 concurrent same-label sessions specified.
- [x] One `set_project` then 100 mixed calls per session specified.
- [x] Multiple repositories/projects and duplicate labels covered.
- [x] Ambient default invariance and explicit targeting have exact oracles.
- [x] Reconnect, cleanup, restore, fault, and offline/WAL replay covered.
- [x] No-global-serialization has a causal overlap test.
- [x] p50/p95, throughput, RSS, error, starvation, and replay budgets specified.
- [x] The >500 ms foreground tripwire and bounded, load-balanced, fair, backpressured, observable background queue have deterministic and operator proof.
- [x] Causal no-cross-project-head-of-line coverage includes blocked, retrying, saturated, cancelling, draining, and restart states.
- [x] Light CI and scalable operator lanes separated.
- [x] Exact candidate files, fixtures, markers, commands, and artifact schema specified.
- [x] Scribe public contract separated from Council/provider-specific downstream acceptance.


---