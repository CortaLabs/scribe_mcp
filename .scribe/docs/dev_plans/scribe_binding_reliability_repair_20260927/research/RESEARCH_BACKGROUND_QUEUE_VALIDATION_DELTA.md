---
visibility: internal
owner_principal_id: crucible_sbr_queue_delta
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: f05c7c5795d87e6d711d12ac51b0b6617d9d086a39afaad5fef3dc2b31ff0b87
title: "\U0001F52C Background Queue Validation Delta \u2014 scribe_binding_reliability_repair_20260927"
related_docs:
- RESEARCH_SWARM_CONCURRENCY_VALIDATION
- RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA
last_updated: 2026-09-27 05:40:11 UTC
created_by: agent-20260927-053052-9aa2bfcd
maintained_by: agent-20260927-053052-9aa2bfcd
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:38:49 UTC
  created_via: replace_section
  last_edited_at: 2026-09-27 05:40:11 UTC
  last_edited_by: agent-20260927-053052-9aa2bfcd
  last_action: frontmatter_update
  work_item_id: 0981594c-b6d8-49e8-bf74-02bb7d3bc0fe
summary: Implementation-ready validation contract for Scribe's 500 ms foreground tripwire
  and bounded, project-fair durable background execution.
owners:
- Crucible
---


# 🔬 Background Queue Validation Delta — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-09-27 05:35:47 UTC

> Validation contract for Scribe's 500 ms foreground tripwire and bounded, project-fair durable background execution.

---
## Executive Summary
<!-- ID: executive_summary -->
This delta converts the operator-added **500 ms foreground tripwire** and Package P5 from `RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md` into an executable validation contract. It composes with `RESEARCH_SWARM_CONCURRENCY_VALIDATION.md` A1–A4; it does not alter that artifact or repeat its identity, targeting, reconnect, and exact-effects oracles.

**Decision:** READY for Blueprint decomposition. A Scribe implementation may move work out of the request path only after the foreground path has completed every authority, validation, and durability obligation and returned a durable receipt. The 500 ms rule is a tripwire, not permission to make every slow operation asynchronous: a foreground call above 500 ms is presumed to contain excessive hot-path work unless its public contract explicitly returns an asynchronous receipt.

The validation gate has two coupled lanes:

1. **Hermetic deterministic lane:** a manual clock, bounded in-memory scheduler backed by a disposable durable receipt store, gated workers, and the existing 32-caller swarm prove capacity, partitioning, fairness, backpressure, idempotency, restart recovery, cancellation, shutdown, and causal absence of cross-project head-of-line blocking without sleeps or live infrastructure.
2. **Opt-in PostgreSQL/process lane:** at least 32 simultaneous caller sessions exercise multiple workers, lease/fencing claims, forced worker death, overload, and graceful shutdown against a throwaway schema. It reports foreground and receipt latency separately from queue wait and run time.

A passing implementation must preserve all A1–A4 correctness invariants, keep control/read and durable-receipt acknowledgement p95 at or below 500 ms on the named reference profile, admit no work beyond configured item/byte bounds, lose no accepted receipt across restart, execute each accepted logical operation at most once, and let an eligible project progress while another project is saturated or blocked.

**Release posture:** research is READY; implementation release remains BLOCKED until the candidate tests and metrics in this delta pass for the same source revision as A1–A4.


---
## Research Scope
<!-- ID: research_scope -->
### Included generic Scribe boundary

- Foreground request classification for project binding, target resolution, authorization, reads, authoritative mutations, idempotency reservation, durable receipt creation, backpressure, and receipt/status queries.
- Background eligibility for optional remote health/sync, analytics mirrors, index regeneration, explicitly asynchronous quality/topology work, journal reconciliation, retention cleanup, plugin/model initialization, and expensive bulk work accepted through a durable receipt.
- Queue capacity by item count and payload bytes; separate ready, delayed-retry, leased/running, terminal, and dead-letter accounting.
- Canonical repository/project partitioning, lane separation, weighted or deficit round-robin fairness, per-project and global concurrency caps, worker leases, fencing tokens, retries, cancellation, shutdown, and restart recovery.
- Observable queue and receipt metrics under a minimum of 32 simultaneous caller sessions.
- Composition with the existing `SwarmTopology`, `CallerSpec`, `OperationSpec`, `SwarmOracle`, `GateBackend`, `MetricSink`, and `fault_controller` contracts proposed by A1–A4.

### Explicit exclusions

- Council seats, work items, Aegis admission, spawn/bind hooks, Codex or Claude projection behavior, provider process policy, and any `council_mcp` imports.
- Production projects, operator databases, production credentials, or shared live queues.
- Treating 500 ms as a universal hardware-independent benchmark. Absolute latency budgets apply to a recorded reference profile; correctness, boundedness, isolation, and causal progress are universal.
- A second queue implementation in tests. Tests exercise the real scheduler/receipt interfaces with disposable storage; fakes control time, worker release, and external services only.

### Definitions

- **Foreground completion:** the public call returns its result or a durable receipt after all required authority checks and minimum durability commits succeed.
- **Durable receipt:** a persisted record containing `operation_id`, canonical repo/project key, lane, idempotency key, payload digest, durability class, enqueue timestamp, status, attempt count, and result/error reference. A receipt is not “accepted” until it survives a fresh runtime read.
- **Eligible job:** an admitted nonterminal receipt whose dependency, retry time, cancellation, lease, and lane conditions permit a worker claim.
- **Queue bound:** a configured maximum over admitted nonterminal work, enforced atomically for both item count and serialized payload bytes. Delayed retries still consume capacity; terminal records do not.
- **Cross-project head-of-line blocking:** Project B cannot reach a claim/start/completion checkpoint while Project A is blocked, saturated, retry-delayed, or holding its per-project concurrency.
- **Tripwire:** any foreground total above 500 ms emits a correlated slow-call event and fails the reference-profile budget unless the API contract is explicitly asynchronous and the foreground segment only performs required validation/durability.

### Evidence basis

- A1–A4 validation artifact: `RESEARCH_SWARM_CONCURRENCY_VALIDATION.md`, especially its 32×100 schedule, exact-effects ledger, causal overlap gate, replay oracle, fixture contracts, and commands.
- Performance/RCA artifact: `RESEARCH_SERVER_WEIGHT_AND_LATENCY_RCA.md`, Package P4 foreground budgets and Package P5 receipt/queue contract.
- Current source seams: `src/scribe_mcp/server.py::schedule_background_task`, `drain_background_tasks`, background journal replay/startup services, `src/scribe_mcp/object_store/hybrid.py`, and response-finalization background analytics.
- Existing neighboring tests: `tests/test_execution_context.py`, `tests/test_server_invoke_tool_startup_bypass.py`, `tests/test_health_check.py`, `tests/test_object_store_hybrid.py`, and `tests/test_tools.py`.

Repo Intelligence could not resolve an active project/version scope for this repository. Candidate placement therefore uses direct source/test inspection and the already-approved A1–A4 placement map; the failed RI lookup is not absence evidence.


---
## Findings
<!-- ID: findings -->
### F1 — The 500 ms rule separates a synchronous contract from deferred implementation work

A slow foreground operation is not automatically backgroundable. The public contract decides whether a call must return data now, commit authoritative state now, or may return a receipt.

| Operation boundary | Foreground obligation | Background-eligible remainder |
|---|---|---|
| Application/session/project binding | Resolve canonical identity, repository, project, and authorization; persist binding before success | Derived analytics only |
| Read/query | Resolve authority and return the requested consistent snapshot | Cache warming or derived indexing after the response |
| Authoritative append/write | Validate payload and preconditions; reserve idempotency; commit local authoritative file/WAL or configured authoritative DB state | Analytics mirror, optional remote replication, derived rendering/indexing |
| Explicit async quality/topology/index request | Validate scope and inputs; atomically reserve capacity; persist receipt and payload digest | Scan, rendering, index generation, artifact publication |
| Bulk maintenance/reconciliation | Validate target and policy; persist receipt if accepted | Enumerate and process bounded batches |
| Optional service initialization/health | Establish only the minimum core readiness required by configured durability | Remote probe, plugin/model load, bridge discovery, cleanup |
| Receipt status/cancel | Authorize, read or transition receipt atomically, and return current state | Worker response to a cancellation request |

The foreground segment must retain authority resolution, required validation, local durability, idempotency reservation, capacity admission, and the accepted receipt commit. Returning a task ID held only in memory is a failure. Reads that promise immediate data remain foreground; changing them to receipt-returning APIs is a public-contract change, not a latency optimization.

### F2 — Capacity must be reserved before acceptance and must include delayed work

A bounded scheduler needs two simultaneous limits: `max_pending_items` and `max_pending_bytes`. Capacity covers ready, retry-delayed, and leased nonterminal receipts; otherwise a retry storm can bypass the bound. A per-project limit prevents one project from consuming the global backlog.

Admission is one atomic outcome:

- new eligible work with capacity: reserve capacity, persist receipt/payload, return `accepted`;
- duplicate same project + idempotency key + payload digest: return the original receipt without consuming capacity;
- same idempotency key with a different digest: typed conflict and zero mutation;
- insufficient item or byte capacity: typed `busy` with bounded `retry_after_ms`, no accepted receipt, no hidden task;
- shutdown admission closed: typed `shutting_down`, zero mutation.

Tests must assert the maximum observed depth and bytes never exceed configuration, even transiently under 32 concurrent admission attempts.

### F3 — Project partitioning and lane separation are correctness properties

The queue key is canonical repository identity plus project identity, not display name or caller label. Control/readiness work, durable replication/writes, and heavy maintenance use distinct lanes. Global capacity and worker count may be shared, but per-project concurrency defaults to one for heavy work and cannot be consumed by another project.

A deterministic deficit-round-robin oracle should assign unit-cost jobs and fixed quantum/weights. While two equal-weight partitions remain eligible:

- their started-job counts may differ by at most one at each completed scheduling round;
- neither may exceed 50% of starts or worker service time across the shared eligible interval;
- a blocked, retry-delayed, empty, cancelled, or per-project-saturated partition is skipped without burning another partition's turn;
- a newly eligible control job starts within one scheduler round even when heavy queues are full, using reserved control capacity.

Weighted policies are allowed only when the configured weight is recorded in the artifact; observed service share must match normalized weight within one quantum.

### F4 — No cross-project head-of-line blocking needs causal checkpoints

Latency alone cannot prove progress independence. Reuse `GateBackend`/gated workers:

1. Admit enough Project A jobs to fill its per-project allowance and block A after claim.
2. Admit Project B and Project C jobs through independent sessions.
3. Require B and C to reach claim and completion checkpoints before A is released.
4. Repeat with A in ready, running, retry-delayed, dead-letter transition, cancellation, and shutdown-drain states.
5. Repeat with Project A payloads at the byte bound and with 31 callers targeting A while one caller targets B.

The gate fails if a global FIFO head, shared lock, single project scan, or held transaction prevents B/C progress. A short `asyncio.wait_for` is only the deadlock guard; event ordering is the assertion.

### F5 — Concurrency limits and worker load balancing need one shared receipt oracle

At every scheduler checkpoint:

- running total is at most `global_concurrency`;
- running jobs for each project/lane are at most their configured cap;
- one receipt has at most one active lease;
- worker claims are balanced within one claim among healthy equal-capacity workers over unit-cost jobs;
- a stale worker cannot complete after its lease expires because the fencing token no longer matches;
- replacing a killed worker restores capacity without exceeding caps.

The reference default for heavy work is one running job per project and `min(4, CPU count)` globally. Tests set explicit caps, avoiding host-CPU-dependent expectations.

### F6 — Retry, idempotency, and restart safety share the same state machine

Required durable states are `accepted`, `ready`, `leased`, `retry_wait`, `succeeded`, `failed_terminal`, and `cancelled`. Each transition records version/fencing information and is atomic.

Deterministic failure schedule:

- attempt 1 fails transiently; retry time is computed from a seeded jitter source and manual clock;
- duplicate submission before retry returns the same receipt;
- runtime restarts during `ready`, `leased`, and `retry_wait`;
- expired lease is reclaimed once with a higher fencing token;
- stale worker completion is rejected;
- success persists once and releases capacity once;
- finite final attempt enters terminal/dead-letter state and is never auto-run again;
- malformed payload or permanent error never retries.

Exactly-once means one externally authoritative effect per accepted logical operation. Execution may be at-least-once around a crash, so the effect sink and receipt transition must use the operation/idempotency key to reject duplicates. The A1–A4 exact-effects multiset remains the final oracle.

### F7 — Cancellation has pre-accept, queued, and running semantics

- Caller cancellation before durable acceptance creates no receipt/effect.
- Cancellation after acceptance but before lease atomically marks `cancelled`, releases capacity once, and never runs.
- Cancellation during a retryable/cooperative job sets `cancel_requested`; the worker checkpoints safely and records `cancelled`.
- A non-interruptible authoritative commit is allowed to finish; the receipt reports the committed result rather than falsely claiming cancellation.
- Cancelling one caller or project changes no peer bindings, queue order, or receipt states.

Tests must race cancel against claim and completion at controlled barriers and accept only the explicitly enumerated terminal outcomes; both paths must be cardinality-clean.

### F8 — Shutdown is a protocol, not a blanket task cancellation

Shutdown order is:

1. atomically close admission;
2. allow in-progress foreground durable commits to finish;
3. stop new worker claims;
4. persist/checkpoint ready, delayed, and leased receipt state;
5. cooperatively drain within a configured deadline;
6. cancel only retryable work after the deadline and return it to a recoverable state;
7. reject stale completions by fencing token;
8. close workers, pools, clients, and metrics exporters;
9. emit one terminal lifecycle event.

After restart, every accepted nonterminal receipt is either completed once or remains queryable/retryable. The process must expose zero leaked tasks/handles above baseline. A shutdown timeout is typed and observable, not silent success.

### F9 — Metrics must make boundedness and the 500 ms tripwire auditable

Required labels are generic and bounded-cardinality: lane, outcome, durability class, error category, and hashed/canonical project key where policy permits. Do not label by payload, raw agent string, operation ID, or unbounded error text.

Required measures:

- foreground total and phase histogram; slow-call count for stage >100 ms and total >500 ms;
- receipt acknowledgement histogram;
- queue depth and bytes, ready/delayed/leased counts, oldest eligible age;
- admission accepted/deduplicated/rejected counts and retry-after;
- queue-wait and run-time histograms by lane;
- attempts, retry, dead-letter, cancellation, lease-expiry, stale-fence rejection;
- active workers, global/project concurrency high-water marks, worker claim counts;
- per-project eligible service share and starvation-window count;
- shutdown admitted/drained/checkpointed/cancelled/recovered counts.

The hermetic lane asserts exact metric deltas. The operator lane emits time series and derives p50/p95/p99, maxima, shares, and starvation windows from raw events.


---
## Technical Analysis
<!-- ID: technical_analysis -->
### A. Reuse-first test architecture

Extend the A1–A4 fixture owner `tests/fixtures/swarm.py`; do not create a second swarm harness.

Add fixture contracts:

- `manual_clock`: monotonic time and deterministic advance; no `time.sleep`.
- `queue_config`: explicit global/per-project item, byte, concurrency, lane-reserve, lease, retry, and shutdown bounds.
- `durable_receipt_store(tmp_path)`: disposable persisted receipts/payloads/leases; supports fresh-runtime reopen.
- `background_queue_harness`: the real scheduler/receipt interfaces wired to disposable storage.
- `gated_worker_pool`: real worker loop with per-operation entered/release events and stable worker IDs.
- `queue_fault_controller`: one-shot failure/crash points at pre-receipt, post-receipt, post-claim, post-effect/pre-complete, and shutdown checkpoint.
- `receipt_oracle`: exact receipt transitions, capacity accounting, lease/fence monotonicity, and effect cardinality.
- `queue_metric_sink`: raw foreground/receipt/queue/worker/shutdown events merged with the existing `MetricSink`.
- `queue_schedule(seed=20260927)`: deterministic admissions, costs, faults, cancels, and worker deaths for 32 same-label callers.

All callers use `test_agent`; mutable fixtures are function-scoped. Queue files, schemas, tasks, clocks, environment, and workers must be torn down. The real scheduler/receipt code remains unmocked.

### B. Foreground classification contract tests

Create `tests/core/test_background_queue_contract.py` and parameterize the public operation classes in F1.

For each operation, inject a gated optional/heavy collaborator:

- required foreground steps must complete before the response;
- optional/heavy work must not begin before receipt durability;
- a receipt response is readable after reconstructing the runtime from storage;
- foreground cancellation before receipt produces no accepted work;
- synchronous public reads return data, never a misleading receipt;
- stage timing covers at least 95% of server-observed duration and emits the >500 ms tripwire event.

Use a manual stage-duration probe to deterministically cross 100 ms and 500 ms boundaries. Do not assert wall-clock completion in the hermetic lane.

### C. Bounded admission and backpressure matrix

With `max_pending_items=8`, `max_pending_bytes=1024`, per-project items `=4`, and workers gated:

1. fill each boundary exactly and prove the last in-bound admission succeeds;
2. race 32 admissions against one remaining item slot and one remaining byte slot;
3. require exactly one new accepted receipt and 31 typed busy/deduplicated outcomes as appropriate;
4. assert high-water marks equal, never exceed, configured limits;
5. move work through retry-wait and prove capacity is retained;
6. cancel/complete terminal work and prove capacity is released once;
7. resubmit duplicates and digest conflicts without changing capacity;
8. reopen storage and recalculate capacity from durable nonterminal receipts.

Backpressure must return promptly from a deterministic atomic admission path; it must not wait for a worker or for queue space to appear.

### D. Deterministic scheduler/fairness matrix

Run three equal-weight projects with 12 unit-cost jobs each, heavy global cap 2, per-project cap 1, and one reserved control slot. Drive the scheduler one decision at a time.

Assertions:

- stable round order from canonical partition keys plus seed;
- max start-count lead between continuously eligible equal-weight projects is one;
- no project exceeds 50% of starts/service while a peer remains eligible;
- a partition in retry-wait or at its project cap is skipped;
- one control job starts within one round despite full heavy backlog;
- changing weights to 2:1:1 yields service shares within one quantum of 50%:25%:25%;
- caller labels, submission order, and duplicate project display names do not affect partition identity.

### E. 32-session queue composition schedule

Layer queue operations into the A1–A4 topology: four repositories × four projects × two sessions, all with the same `test_agent` label. Keep the original 100-call schedule and exact-effects ledger. Replace a deterministic subset of heavy/derived calls with receipt-producing operations:

- 10 asynchronous quality/topology/index/bulk submissions per caller;
- two duplicate submissions and one digest-conflict submission per caller;
- two cancellation races per caller;
- two transient retry paths per caller;
- forced worker restart for eight partitions;
- one overload barrier where all 32 callers compete for bounded remaining capacity.

At operations 25, 50, 75, and 100, preserve the A1–A4 ambient-default readback. Queue receipts carry canonical targets from the already-resolved immutable request context. Final reconciliation adds:

- accepted receipt IDs equal durable receipt rows;
- terminal success IDs equal effect fingerprints exactly once;
- busy/conflict/pre-accept-cancel IDs have no effect;
- per-project queue/worker metrics agree with receipt history;
- no binding drift, wrong-target effect, duplicate effect, or peer-session theft.

### F. Load balance, crash, cancellation, and shutdown matrix

| Scenario | Controlled event | Required result |
|---|---|---|
| Worker balance | 4 workers claim 32 unit jobs | Claim counts differ by at most one; caps never exceeded |
| Worker death | kill after lease, before effect | Lease expires; new worker claims with higher fence |
| Stale completion | dead worker reports after reassignment | Typed stale-fence rejection; one effect |
| Post-effect crash | kill after idempotent effect, before receipt success | Replay observes/deduplicates effect; terminal success once |
| Retry overload | all A jobs enter retry-wait | B/C eligible jobs progress; delayed A retains bounded capacity |
| Queued cancel | cancel before claim | Cancelled once; no run/effect; capacity released |
| Running cancel | cancel at worker checkpoint | Allowed terminal outcome is explicit; no duplicate/retry leak |
| Shutdown admission | race 32 submits with admission close | Each request is either durably accepted or typed shutdown; no limbo |
| Shutdown deadline | hold one retryable job past drain | Checkpoint/recover after restart; stale worker fenced |
| Restart | reopen fresh scheduler/store | All accepted receipts queryable; no loss; correct capacity rebuilt |

### G. Operator PostgreSQL/process profile

Extend `tests/integration/test_swarm_concurrency_stress.py` with `SCRIBE_SWARM_PROFILE=background-queue`. Minimum topology is 32 simultaneous sessions, 16 canonical project partitions, four worker processes, global heavy concurrency four, and per-project heavy concurrency one.

Workload mix:

- 40% foreground control/read and durable receipt submissions;
- 25% heavy receipt jobs;
- 10% duplicates/conflicts;
- 10% transient retries;
- 5% cancellations;
- 5% overload probes;
- 5% worker restart/shutdown probes.

Faults rotate by project. One project is held for 10 seconds while others remain eligible. Results are invalid unless the artifact records source revision, Python/PostgreSQL versions, CPU count, worker/config bounds, seed, and raw event counts.

Reference-profile acceptance:

| Metric | Budget |
|---|---:|
| Wrong target, binding drift, lost accepted receipt, duplicate effect | 0 |
| Foreground control/read p95 | <= 500 ms |
| Durable receipt acknowledgement p95 | <= 500 ms |
| Queue item/byte/concurrency bound violations | 0 |
| Typed overload outcomes at forced saturation | 100% of non-admitted calls |
| Continuously eligible project starvation window | 0 windows >= 5 s |
| Equal-weight project service share | no project >50% while peer eligible |
| Worker claim imbalance for unit jobs | <= 1 claim |
| Accepted receipts unreconciled 60 s after recovery | 0 |
| Stale-fence completions accepted | 0 |
| Open tasks/handles/workers after teardown | 0 above baseline |

Machine-dependent latency comparisons also require foreground/receipt p95 regression <=20% and queue throughput regression <=15% against a same-profile baseline.

### H. Metrics artifact extension

Extend `swarm-results.json`; do not create an independent source of truth. Add:

```json
{
  "background_queue": {
    "config": {},
    "foreground_histograms": {},
    "receipt_ack_histograms": {},
    "depth_high_water": {},
    "bytes_high_water": {},
    "concurrency_high_water": {},
    "admission": {},
    "queue_wait_histograms": {},
    "run_histograms": {},
    "project_service_share": {},
    "worker_claims": {},
    "retries": {},
    "cancellations": {},
    "lease_expirations": 0,
    "stale_fence_rejections": 0,
    "shutdown": {},
    "restart_reconciliation": {}
  }
}
```

The Markdown summary is generated from the JSON artifact. Raw operation IDs remain in the disposable artifact only and are not metric labels.


---
## Recommendations
<!-- ID: recommendations -->
### Implementation package Q1 — Receipt, admission, and foreground tripwire contract

**Candidate tests**

- create `tests/core/test_background_queue_contract.py`;
- extend `tests/test_tools.py` for correlated foreground/receipt timing envelope assertions;
- extend `tests/test_execution_context.py` only for compatibility behavior of `schedule_background_task`, drain, and service status if those public helpers remain.

**Gate**

- every operation class is explicitly foreground or receipt-returning;
- accepted receipt survives runtime reconstruction;
- capacity is atomically bounded by items and bytes;
- duplicate/conflict/overload/pre-accept-cancel behavior is exact;
- 100 ms stage and 500 ms total tripwires are deterministic and correlated.

### Implementation package Q2 — Partitioned scheduler, fairness, and recovery

**Candidate tests**

- keep reusable fixtures in `tests/fixtures/swarm.py`;
- extend `tests/core/test_background_queue_contract.py` for deterministic scheduling and load balancing;
- extend the A1–A4 candidate `tests/core/test_wal_replay_exactly_once.py` for receipt/effect crash windows rather than creating a second replay oracle.

**Gate**

- canonical project partitions and lanes are independent;
- global/per-project caps and reserved control capacity hold at every checkpoint;
- fairness/share oracles pass;
- blocked/retrying Project A cannot stop B/C;
- lease expiry, fencing, retry, dead-letter, and restart cardinality are clean.

### Implementation package Q3 — Shutdown and neighboring service adapters

**Candidate tests**

- extend `tests/test_server_invoke_tool_startup_bypass.py` for bounded service scheduling and admission-close order;
- extend `tests/test_health_check.py` for queue/service health and bounded-cardinality metrics;
- extend `tests/test_object_store_hybrid.py` when optional remote replication moves behind a durable receipt;
- keep shutdown/restart end-to-end cases in `tests/core/test_background_queue_contract.py`.

**Gate**

- admission closes before worker drain;
- accepted nonterminal receipts survive deadline cancellation and restart;
- stale completions are fenced;
- optional remote failure never corrupts local authoritative success;
- teardown leaks nothing.

### Implementation package Q4 — 32-session PostgreSQL/process proof

**Candidate tests**

- extend the A1–A4 candidate `tests/integration/test_swarm_concurrency_stress.py`;
- extend `tests/integration/storage/conftest.py` only if its disposable schema fixture cannot supply receipt/lease tables;
- keep `benchmarks/swarm_concurrency.py` a thin entrypoint over the shared fixtures.

**Gate**

- background-queue profile runs at least 32 callers and four workers;
- overload, cancellation, retries, worker death, restart, and shutdown are present in raw events;
- reference budgets and exact-effects oracle pass;
- no production state or Council logic is present.

### Verification order

1. Foreground/receipt and bounded admission core tests.
2. Scheduler/fairness/no-HOL core tests.
3. Replay/restart/cancellation/shutdown core tests.
4. Direct neighbors named above.
5. Existing A1–A4 core commands.
6. Operator PostgreSQL background-queue smoke.
7. Adapter parity only after the provider-neutral core is green.

### Gate decision

Blueprint may merge Q1–Q4 into the A1–A4 implementation plan, preserving one fixture/oracle family. Do not release a queue implementation that passes throughput while violating receipt durability, capacity, project fairness, fencing, cancellation, or shutdown. A green suite built on sleeps, unbounded task creation, unique test personas, mocked scheduler code, or live operator state is a BLOCK.


---
## Appendix
<!-- ID: appendix -->
### Acceptance-to-test map

| Work-item criterion | Executable evidence |
|---|---|
| A1 foreground vs durable-receipt boundary | Q1 classification parameterization; timing/tripwire assertions; reconstructed-runtime receipt read |
| A2 bounded, partitioned, fair, backpressured, observable, idempotent, restart-safe, no cross-project HOL | Q1 capacity race; Q2 deterministic scheduler/replay; gated A/B/C causal progress; exact metric deltas |
| A3 load balance, caps, retries, overload, cancellation, shutdown under 32+ sessions | 32-session queue schedule plus Q4 PostgreSQL/process profile |
| A4 exact files, fixtures, metrics, commands composing with A1–A4 | Tables and commands below; shared `tests/fixtures/swarm.py` and `swarm-results.json` |

### Exact candidate locations

| Purpose | Candidate location |
|---|---|
| Shared swarm/queue fixtures and oracles | `tests/fixtures/swarm.py` |
| Hermetic foreground, admission, scheduler, fairness, cancellation, shutdown | `tests/core/test_background_queue_contract.py` |
| WAL/receipt/effect restart cardinality | `tests/core/test_wal_replay_exactly_once.py` |
| A1–A4 32×100 binding composition | `tests/core/test_swarm_binding_reliability.py` |
| Existing task/service-status neighbor | `tests/test_execution_context.py` |
| Startup/shutdown scheduling neighbor | `tests/test_server_invoke_tool_startup_bypass.py` |
| Timing-envelope neighbor | `tests/test_tools.py` |
| Queue/service health neighbor | `tests/test_health_check.py` |
| Optional remote replication neighbor | `tests/test_object_store_hybrid.py` |
| PostgreSQL/process smoke and soak | `tests/integration/test_swarm_concurrency_stress.py` |
| Disposable PostgreSQL fixture, if required | `tests/integration/storage/conftest.py` |
| Thin operator entrypoint | `benchmarks/swarm_concurrency.py` |

### Exact fixture contracts

- existing: `test_agent`, `swarm_topology`, `swarm_backend`, `swarm_postgres_backend`, `swarm_callers`, `swarm_schedule`, `swarm_oracle`, `gate_backend`, `metric_sink`, `fault_controller`;
- delta: `manual_clock`, `queue_config`, `durable_receipt_store`, `background_queue_harness`, `gated_worker_pool`, `queue_fault_controller`, `receipt_oracle`, `queue_metric_sink`, `queue_schedule`.

### Targeted commands

Hermetic queue contract:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"
```

A1–A4 composition:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q tests/core/test_swarm_binding_reliability.py tests/core/test_background_queue_contract.py tests/core/test_wal_replay_exactly_once.py -m "core and regression and not slow and not performance"
```

Direct neighbors:

```bash
PYTHONPATH=src ./.venv/bin/pytest -q tests/test_execution_context.py tests/test_server_invoke_tool_startup_bypass.py tests/test_tools.py tests/test_health_check.py tests/test_object_store_hybrid.py
```

Import smoke for production modules actually modified by the implementation package:

```bash
PYTHONPATH=src ./.venv/bin/python -c 'from scribe_mcp import server; from scribe_mcp.tools import append_entry, manage_docs; print(server.__file__)'
```

Operator PostgreSQL/process smoke, using a disposable DSN supplied by the test environment:

```bash
SCRIBE_TEST_POSTGRES_URL="${SCRIBE_TEST_POSTGRES_URL}" SCRIBE_SWARM_PROFILE=background-queue SCRIBE_SWARM_CALLERS=32 SCRIBE_SWARM_WORKERS=4 SCRIBE_SWARM_GLOBAL_CONCURRENCY=4 SCRIBE_SWARM_PER_PROJECT_CONCURRENCY=1 SCRIBE_SWARM_SEED=20260927 SCRIBE_SWARM_RESULTS_DIR=benchmarks/artifacts/background-queue-smoke PYTHONPATH=src ./.venv/bin/pytest -q tests/integration/test_swarm_concurrency_stress.py -m "integration and postgres and performance and slow"
```

Do not run the repository-wide suite for this package. Each implementation package must additionally run tests for direct neighbor modules that import from or are imported by modified production files.

### Determinism and Testing Standard checklist

- [x] Canonical `test_agent`; no unique persona creation.
- [x] `tmp_path` and disposable schema/store only.
- [x] Manual clock and event gates; no scheduler-dependent sleeps.
- [x] Real scheduler/receipt code; external services only may be faked.
- [x] Core/regression and capability markers are separated.
- [x] One reusable fixture/oracle family composes with A1–A4.
- [x] Every test fails on a named product-contract violation.
- [x] No Council imports or behavior in Scribe tests.
- [x] No full-suite command.

### Final readiness

The delta is implementation-ready when the managed document quality gates pass. It does not claim the current source already satisfies the queue contract; current `schedule_background_task` tracks fire-and-forget tasks but does not by itself prove bounded admission, durable receipts, partition fairness, leases/fencing, or restart recovery.


---