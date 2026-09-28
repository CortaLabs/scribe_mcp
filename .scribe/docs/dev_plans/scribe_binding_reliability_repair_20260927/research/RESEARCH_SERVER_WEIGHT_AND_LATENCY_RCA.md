---
visibility: internal
owner_principal_id: mantis_sbr_server_perf
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: c6e01023acdd10feb53e0a604becdeb22e98552324af105a6ad89002c0d49342
title: "\U0001F52C Scribe Server Weight and Latency Root Cause Analysis \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-27 05:33:03 UTC
created_by: agent-20260927-051258-c78bacde
maintained_by: agent-20260927-051258-c78bacde
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:30:53 UTC
  created_via: replace_section
  last_edited_at: 2026-09-27 05:33:03 UTC
  last_edited_by: agent-20260927-051258-c78bacde
  last_action: frontmatter_update
summary: Measurement-led RCA proving the import, startup, memory, process-multiplicity,
  transport, and hot-call causes of Scribe server overhead, with bounded repair packages
  and concurrency budgets.
owners:
- Mantis
tags:
- performance
- startup
- memory
- latency
- concurrency
- SBR-PERF-03
---


# 🔬 Scribe Server Weight and Latency Root Cause Analysis — scribe_binding_reliability_repair_20260927
**Author:** Mantis
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-09-27 05:29:20 UTC

> Measurement-led RCA of standalone Scribe startup, memory, process multiplicity, transport overhead, and hot tool paths.

---
## Executive Summary
<!-- ID: executive_summary -->
Scribe server weight and latency are not caused by one database query. They are the product of four stacked costs:

1. Import-time eager construction loads the token-estimation and response-formatting graph before any tool is requested. A fresh interpreter that imports scribe_mcp.server reaches about 122 MB RSS and imports 884 modules; importing scribe_mcp.tools alone stays near 13 MB. The largest avoidable cause is src/scribe_mcp/utils/__init__.py importing response and tokens, which instantiates TokenEstimator at src/scribe_mcp/utils/tokens.py:359-360 and eagerly loads a GPT-4 tiktoken encoder at lines 80-86.
2. Ready-to-handshake startup synchronously waits on Postgres setup and remote object-store health. A representative warm run spent 189.7 ms in storage.setup and 1,474.0 ms in document_store.setup, producing 1,674.5 ms inside _startup and 4.12 s process wall time. The object-store probe is described as non-blocking in src/scribe_mcp/object_store/providers/corta.py:51-52, but setup awaits the HTTP GET at line 54.
3. Process-per-client multiplication turns a large process into a host-level resource problem. The read-only host snapshot found 37 scribe-server processes using 6,356,040 KB aggregate RSS (171,785 KB average) plus 60 Council wrapper layers using 3,147,588 KB. A proportional-memory sample of 35 servers found 5,153,417 KB PSS and 5,135,000 KB private memory, so this is not merely shared-page RSS double counting.
4. Hot calls pay duplicated context/session/project work before the tool body and synchronous audit work during response finalization. Five direct MCP round trips per tool averaged 3.73-4.80 s. In-process bodies for get_project and read_recent averaged 296.9 ms and 292.4 ms. The residual 3.6-4.5 s lies in the shared runtime, MCP transport/proxy, scheduling contention, and uninstrumented boundaries. Every measured foreground direct call exceeds the amended 500 ms excess threshold.

The repair should first remove eager token/formatter initialization and the synchronous remote health probe, then collapse and instrument the per-call session/project queries. Scribe should own a light standalone server, bounded internal background execution, durable receipts, and clean shutdown. Council must own how many server processes it spawns, whether they are reused, and when provider/seat processes are terminated.


---
## Research Scope
<!-- ID: research_scope -->
### Scope

This RCA covers standalone/public Scribe concerns:

- Python import graph and eager initialization
- stdio server startup and ready signal
- Postgres pool/schema/bootstrap work
- object-store and bridge/plugin startup
- tool inventory construction
- shared per-call runtime and representative hot tools
- Scribe-side shutdown and background-task behavior
- per-process memory and concurrency budgets

Council-specific spawning, Aegis admission, work-item routing, proxy ownership, provider process trees, and cross-agent server reuse are integration boundaries only. They are not implementation work for scribe_mcp.

### Measurement definitions

- Cold import: first fresh interpreter run in the measurement series, without privileged host page-cache eviction.
- Warm import/startup: subsequent fresh interpreters with filesystem and database caches naturally warm. Each run is still a new Python process.
- Ready wall time: process invocation through clean stdin EOF, including import, _startup, MCP stdio setup, and shutdown.
- Tool body: direct invocation after one storage_only startup, excluding shared execute_tool_call and MCP transport.
- Client round trip: direct mcp__scribe__ tool call observed from the active client, including the server runtime and external transport/proxy path.
- Memory: Linux RSS from ps/time; host totals supplemented with smaps_rollup PSS/private memory.

Measurements were taken 2026-09-27 from /home/austin/projects/MCP_SPINE/scribe_mcp using Python 3.12.3. Network-backed startup probes were rerun outside the socket-blocked diagnostic sandbox against the existing local Scribe runtime substrate. No production source or test files were changed.

### Interpretation limits

The import "cold" result is not a hardware-cold page-cache result because dropping host caches would be destructive and was not authorized. Client round-trip residual cannot yet be split exactly between execute_tool_call, MCP serialization, host proxying, and scheduler wait because those boundaries lack a common correlation timing envelope. The report therefore treats the residual as a proven combined boundary and proposes instrumentation before optimization claims.


---
## Findings
<!-- ID: findings -->
### F1 — Process multiplicity is the dominant host-level cost

Host snapshot:

| Metric | Evidence |
|---|---:|
| Live scribe-server processes | 37 |
| Aggregate server RSS | 6,356,040 KB |
| Average server RSS | 171,784.9 KB |
| RSS range | 133,384-259,468 KB |
| Older than 1 hour | 12 |
| Older than 1 day | 8 |
| Wrapper layers matching council env run | 60 |
| Aggregate wrapper RSS | 3,147,588 KB |
| Server PSS sample | 35 processes, 5,153,417 KB total |
| Private-memory sample | 5,135,000 KB total |
| Threads | 7.3 average, 18 maximum |

Representative ancestry is Codex/Claude session → council env run wrapper → Python CLI wrapper → scribe-server. None of the sampled servers was reparented to PID 1. They linger because their owning provider sessions and stdio chains remain alive, not because Scribe detached itself. Scribe still magnifies the cost because every client process loads the same 120-170 MB runtime and starts its own pools, document-store client, background tasks, and schema checks.

### F2 — The nominal lazy tool registry is defeated by eager utility imports

Measured fresh-process states:

| Import state | Modules | RSS |
|---|---:|---:|
| Python + psutil baseline | 86 | 13,008 KB |
| scribe_mcp package | 87 | 13,008 KB |
| scribe_mcp.tools registry | 96 | 13,384 KB |
| scribe_mcp.server | 884 | 123,164 KB |
| server + all 35 tools | 997 | 131,044 KB |

Five server-import runs were 1.85, 1.92, 1.93, 2.05, and 3.13 s with about 122 MB maximum RSS.

The causal chain is:

- server.py imports scribe_mcp.utils.sentinel_logs at line 54.
- Python executes scribe_mcp/utils/__init__.py first.
- utils/__init__.py imports ResponseFormatter and token symbols at lines 6-7.
- response.py imports token_estimator at line 18.
- tokens.py constructs the global TokenEstimator at lines 359-360.
- TokenEstimator.__init__ calls tiktoken.encoding_for_model at lines 80-86 and creates ~/.scribe_metrics at lines 90-93.

Importing tiktoken alone was about 13.9 MB RSS; importing scribe_mcp.utils.tokens reached about 108.2 MB because encoder construction loads the vocabulary. This is the single clearest memory root cause.

### F3 — Synchronous remote health dominates server readiness

Three network-capable stdio runs completed in 5.11, 4.30, and 3.52 s at about 128 MB maximum RSS. An INFO run attributed:

- storage.setup: 189.7 ms
- document_store.setup: 1,474.0 ms
- _startup total: 1,674.5 ms
- full process wall time: 4.12 s
- import/transport/shutdown outside _startup: about 2.45 s by subtraction

server._startup at src/scribe_mcp/server.py:1104-1235 correctly defers cleanup, plugin initialization, legacy migration, and journal replay, but it awaits document_store.setup at lines 1195-1208. HybridStore.setup awaits its remote provider, and CortaStoreProvider.setup awaits GET /health with a 2.0 s timeout. A nonessential availability probe therefore gates "Server ready."

Bridge initialization starts concurrently but currently attempts the configured council_mcp manifest and logs a failure because it defines no runtime plugin. This did not dominate readiness in the sample, but it is repeated noise and work in every process.

### F4 — Every server repeats schema verification

PostgresStorage.setup at src/scribe_mcp/storage/postgres/__init__.py:222-224 calls _ensure_schema. src/scribe_mcp/storage/postgres/schema.py:113-180 then:

- acquires a cross-process advisory lock
- creates/sets the schema
- reads and splits the full init SQL
- executes every idempotent statement
- ensures the migration table
- enumerates every numbered migration and queries its ledger row

The measured warm cost was only 189.7 ms, but 37 concurrent processes serialize on the same advisory lock and repeat unchanged DDL/ledger checks. During socket denial, four connection attempts with 1+2+4 second backoff produced 8.78-9.28 s failed startups, proving the retry path directly delays readiness.

### F5 — Tool inventory has a bounded but real cold spike

server.py:693-695 calls tools.ensure_all_tools_loaded for tools/list. Cold inventory:

- 35 tools
- 216.6-232.4 ms
- RSS growth from about 123 MB to about 131 MB
- warm list: 0.35 ms

One-shot scribe tools --json still took 2.66-3.48 s and about 130.5-130.9 MB because process import dominates. Inventory is not the primary resident-memory cause, but clients that request tools immediately add a cold-start burst.

### F6 — Foreground call latency exceeds the 500 ms contract

Five direct MCP round trips:

| Tool | Samples (ms) | Average | Classification |
|---|---|---:|---|
| get_project | 3527, 3717, 5144, 4497, 4663 | 4309.6 | excess |
| read_recent | 4501, 3724, 3405, 4041, 3792 | 3892.6 | excess |
| query_entries | 4433, 4827, 4267, 4241, 5383 | 4430.2 | excess |
| read_file scan | 4910, 6174, 5836, 3643, 3415 | 4795.6 | excess |
| search literal | 4102, 4270, 4099, 2862, 3312 | 3729.0 | excess |

In-process, PostgreSQL-backed tool bodies after startup:

- get_project: 542.9, 265.9, 254.8, 208.6, 212.4 ms; average 296.9 ms
- read_recent: 248.7, 255.3, 432.0, 235.0, 291.2 ms; average 292.4 ms

Scribe tool logs recorded read_recent tool-only samples from 191.4 to 2,445.5 ms, average 603.7 ms over 40 recent entries. Thus even the body sometimes exceeds 500 ms, and every end-to-end call does.

The shared path at src/scribe_mcp/shared/tool_runtime.py:637-1244 can perform get_session_by_transport, session allocation, project lookup, mode resolution, upsert_session, agent-session allocation/readback, execution-context construction, cached-project lookup, and read-hook dispatch before invoking the tool. Tool bodies then call state_manager.record_tool and prepare_context again. Response finalization at src/scribe_mcp/utils/formatters/dispatcher.py:139-286 performs JSON serialization, synchronous project lookup, synchronous JSONL logging, and schedules SQL analytics. This duplication is the Scribe-owned hot-path target. The remaining unmeasured client residual also includes Council/provider proxying and process scheduling, which must be instrumented and repaired in council_mcp.


---
## Technical Analysis
<!-- ID: technical_analysis -->
### Startup and import symbols

- src/scribe_mcp/server.py:17-18 — logging configuration at import.
- server.py:32-35 — MCP runtime/version type load.
- server.py:37-42 — bridge tools imported at module load.
- server.py:85-94 — MCP server, storage backend, state manager, and router context constructed at import.
- server.py:1104-1235 — synchronous startup and ready signal.
- server.py:1504-1513 — stdio lifecycle.
- src/scribe_mcp/utils/__init__.py:3-7 — eager convenience exports.
- src/scribe_mcp/utils/tokens.py:74-93, 359-360 — eager encoder, metrics-directory side effect, and global singleton.
- src/scribe_mcp/tools/__init__.py:13-115 — correct lazy tool-module registry.
- server.py:693-695 and 1342-1374 — eager all-tool loading only when inventory/description is requested.

### Storage and remote setup symbols

- src/scribe_mcp/storage/postgres/__init__.py:222-224 — setup always calls schema ensure.
- src/scribe_mcp/storage/postgres/schema.py:113-180 — advisory-locked full DDL and migration scan.
- src/scribe_mcp/storage/postgres/internals.py: ensure_pool — connection retry/backoff observed on failure.
- src/scribe_mcp/object_store/__init__.py:43-89 — store construction.
- src/scribe_mcp/object_store/hybrid.py:28-29 — setup delegates directly to remote.
- src/scribe_mcp/object_store/providers/corta.py:45-68 — awaited health request.
- server.py:1016-1078 — bridge discovery/activation and monitor creation.
- server.py:842-962 — journal replay scans configured projects plus recursive journal patterns.

### Per-call symbols

- src/scribe_mcp/shared/tool_runtime.py:877-1007 — transport/session/project resolution queries.
- tool_runtime.py:1047-1180 — mode resolution, session upsert, agent-session allocation/readback, execution-context build.
- tool_runtime.py:1198-1244 — cached project injection, type coercion, read hooks, dispatch.
- src/scribe_mcp/tools/get_project.py:417-477 — record_tool, agent binding read, and prepare_context.
- src/scribe_mcp/tools/read_recent.py:273-380 — record_tool, parameter healing, state/context resolution.
- read_recent.py:430-516 — DB read, entry limiting, token metrics, response finalization.
- src/scribe_mcp/utils/formatters/dispatcher.py:173-240 — sync project resolution, response serialization, JSONL audit.
- dispatcher.py:242-280 — analytics write scheduling.

### Lifecycle ownership

Scribe-owned:

- reduce import and per-process resident memory
- expose one clean standalone server lifecycle
- make nonessential startup work asynchronous
- bound internal background tasks and queues
- cancel/drain tasks and close pools/clients on EOF or signal
- emit ready, queue, call-stage, and shutdown telemetry

Council-owned:

- process-per-agent versus shared/reused server policy
- council env run wrapper multiplicity
- Aegis admission and provider session ownership
- work-item/caller routing and proxy latency
- process caps, reuse keys, idle reap, and seat/session teardown

No Council-specific admission, work-item, provider, or process-reuse logic belongs in Scribe.


---
## Recommendations
<!-- ID: recommendations -->
### Package P1 — Remove eager utility and token weight

Owned Scribe boundary: src/scribe_mcp/utils/__init__.py, utils/tokens.py, response/formatter callers.

- Replace eager convenience imports with leaf imports or lazy __getattr__ exports.
- Make TokenEstimator encoder construction lazy on first accurate token-count request.
- Do not create ~/.scribe_metrics during module import; create it only on persistence.
- Keep a cheap character-based estimator available without loading tiktoken.
- Add an import regression probe for module count, import time, RSS, and import-time filesystem writes.

Acceptance budget:

- fresh scribe_mcp.server import: warm p95 <= 1.0 s, cold p95 <= 1.5 s
- pre-tool ready RSS <= 64 MB
- no token encoder and no metrics-directory mutation before a token-count operation
- all-tools-loaded steady RSS <= 80 MB

### Package P2 — Decouple readiness from optional remote services

Owned Scribe boundary: server._startup, object_store providers, bridge/plugin startup.

- Ready should require MCP transport plus the configured authoritative storage needed for the requested durability mode.
- Construct the document store synchronously but move remote health probing behind a bounded background service or lazy first-use circuit breaker.
- Publish service state as initializing/healthy/degraded with a durable local readiness record.
- Ensure bridge/plugin/journal services cannot delay ready and suppress invalid optional manifests after one typed failure until configuration changes.

Acceptance budget:

- warm process-to-ready p95 <= 1.5 s
- cold process-to-ready p95 <= 2.5 s
- optional object-store outage adds <= 50 ms to foreground startup
- failed optional service never prevents core tool listing or local durable logging

### Package P3 — Fast-path schema/bootstrap

Owned Scribe boundary: PostgresStorage.setup and storage/postgres/schema.py.

- Separate pool readiness from schema migration authority.
- Introduce a schema version/fingerprint fast check; only one elected bootstrapper runs DDL when the fingerprint is stale.
- Other processes wait on a bounded readiness row/advisory notification, not a full repeated DDL loop.
- Preserve fail-closed behavior when required schema is absent or mismatched.
- Bound connection retry by a startup deadline and emit attempt/backoff phases.

Acceptance budget:

- warm storage setup p95 <= 100 ms
- 32 simultaneous starts perform one DDL/bootstrap execution
- non-bootstrap callers wait <= 500 ms warm and receive a typed timeout when the bootstrap deadline expires
- no migration ledger drift and no weakened durability

### Package P4 — Collapse and instrument the per-call path

Owned Scribe boundary: shared/tool_runtime.py, state/router context, logging mixins, response dispatcher.

- Add a correlation timing envelope covering ingress decode, session lookup, project lookup, mode resolution, agent-session allocation, tool body, hooks, response formatting, audit append, and egress serialization.
- Resolve one immutable request context once. Pass it to tool helpers instead of repeating state_manager.record_tool/prepare_context/project loads.
- Cache immutable project metadata and session bindings by version with explicit invalidation on set_project/rebind.
- Remove synchronous fetch_project_sync from response finalization; use the already-resolved context.
- Keep local JSONL/WAL durability in the foreground for writes; analytics and derived rendering may run asynchronously.

Acceptance budget:

- foreground read p50 <= 150 ms, p95 <= 500 ms, p99 <= 750 ms
- durable append acknowledgement p95 <= 500 ms
- no call performs more than one session-binding read and one project-record read
- stage timings account for >= 95% of client-observed server time
- any stage > 100 ms and any total > 500 ms emits a correlated slow-call event

### Package P5 — Durable bounded background execution

Eligible work: optional remote health/sync, analytics mirrors, index regeneration, quality/topology scans requested asynchronously, journal reconciliation, cleanup, plugin/model initialization, and expensive bulk operations after a durable foreground receipt. Project binding, authorization, authoritative log WAL append, and required write validation remain foreground.

Contract:

- Receipt: operation_id, project_id, idempotency_key, enqueue timestamp, payload digest, durability class, status, attempt count, result/error reference.
- Partitioning: queue key is canonical project/repository identity; control/readiness, durable writes, and heavy maintenance use separate lanes.
- Concurrency: configurable global cap plus per-project cap; default heavy concurrency 1 per project and at most min(4, CPU count) globally.
- Backpressure: bounded queue depth and bytes; reject with typed busy/retry-after before accepting work that cannot be durably queued.
- Fairness: weighted or deficit round-robin across project partitions; reserve capacity for small control/read operations so one bulk project cannot starve others.
- Retry/idempotency: deduplicate by project + idempotency key + payload digest; exponential backoff with jitter; finite attempts; terminal dead-letter state; replay is safe after crash.
- Observability: queue wait, run time, attempts, depth, oldest age, per-project share, rejection count, completion status, and cancellation/drain outcomes.
- Load balancing: multiple standalone workers may claim receipts with leases and fencing tokens. Council may choose how many Scribe workers/processes exist, but Scribe's queue contract must remain host-neutral and standalone.
- Shutdown: stop admission, drain foreground durable commits, checkpoint queued receipts, cancel only retryable work, close pools/clients, and emit a terminal lifecycle event.

Acceptance budget under 32 concurrent callers:

- control/read lane p95 <= 500 ms
- durable receipt acknowledgement p95 <= 500 ms
- no project receives > 50% worker time while another project has queued eligible work, except explicit priority policy
- queue depth remains bounded and overload is typed, not timeout-based
- zero lost accepted receipts across forced worker restart

### Package P6 — Council integration follow-up, not Scribe code

Route to council_mcp:

- reuse one healthy Scribe server per safe runtime/repository authority scope where isolation permits
- enforce process caps and single-flight startup
- terminate wrapper/server chains when provider seats end
- reap idle servers with explicit leases and preserve active-call fencing
- measure proxy/admission/queue wait separately from Scribe server time

Target host budget for 10 simultaneous agents:

- <= 2 Scribe server processes per safe authority scope, unless isolation policy explicitly requires more
- <= 200 MB aggregate Scribe PSS per scope after P1
- no inactive server older than its lease/idle TTL
- wrapper count is O(server processes), not O(tool calls)


---
## Appendix
<!-- ID: appendix -->
Run from /home/austin/projects/MCP_SPINE/scribe_mcp.

### Import and memory

    for i in 1 2 3 4 5; do
      /usr/bin/time -f "import_run=$i elapsed_s=%e user_s=%U sys_s=%S maxrss_kb=%M"         ./.venv/bin/python -c 'import scribe_mcp.server' >/dev/null
    done

    ./.venv/bin/python -X importtime -c 'import scribe_mcp.server' 2>&1       | sort -nr -k2 | head -n 80

    ./.venv/bin/python -c 'import sys,psutil; p=psutil.Process();       print("baseline",len(sys.modules),p.memory_info().rss//1024);       import scribe_mcp.tools; print("tools",len(sys.modules),p.memory_info().rss//1024);       import scribe_mcp.server; print("server",len(sys.modules),p.memory_info().rss//1024)'

### Startup attribution

    SCRIBE_LOG_LEVEL=INFO /usr/bin/time       -f 'elapsed_s=%e user_s=%U sys_s=%S maxrss_kb=%M exit=%x'       ./.venv/bin/scribe-server </dev/null >/dev/null

The socket-blocked sandbox variant reproducibly failed after retries at about 8.8-9.3 s. The network-capable run is the valid readiness result; the blocked run is retained only as retry/backoff evidence.

### Inventory

    ./.venv/bin/python -c 'import asyncio,time,psutil,scribe_mcp.server as s;       p=psutil.Process(); a=time.perf_counter(); r=asyncio.run(s.app.list_tools());       print((time.perf_counter()-a)*1000,len(r),p.memory_info().rss//1024)'

### Host process snapshot

    ps -eo pid,ppid,rss,vsz,etimes,stat,lstart,args --sort=-rss       | grep -E '[s]cribe-server|[s]cribe_mcp.server'

    pstree -aps <scribe-server-pid>

    awk '/^Pss:/ {sum+=$2} /^Private_Clean:/ {priv+=$2}       /^Private_Dirty:/ {priv+=$2} END {print sum,priv}'       /proc/<scribe-server-pid>/smaps_rollup

### Tool timing

Client samples were collected by timing five sequential direct mcp__scribe__ calls for each tool in one session. Tool-body samples were collected in one fresh process after await server._startup(startup_profile="storage_only") by calling get_project and read_recent directly five times.

Scribe's .scribe/logs/TOOL_LOG.jsonl shows that existing duration fields are not comparable across all tools: read_recent passes a start timestamp and records the body, while read_file/search/query_entries often record only the finalization boundary (sub-millisecond values). Package P4 must normalize this before automated budget enforcement.

### Confidence

High confidence:

- eager token encoder causes most import RSS
- object-store health probe blocks ready
- schema ensure repeats per process
- 35-37 live processes consume multi-gigabyte private memory
- end-to-end foreground calls exceed 500 ms

Medium confidence:

- exact division of the 3.6-4.5 s residual between Scribe shared runtime and Council/provider transport, because no end-to-end correlated phase envelope exists yet
- steady-state target values under 32 callers, pending the Crucible concurrency package

No source implementation is included in this research package.


---