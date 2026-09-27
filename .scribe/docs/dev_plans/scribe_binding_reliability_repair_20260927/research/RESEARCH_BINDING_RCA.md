---
visibility: internal
owner_principal_id: mantis_sbr_binding_rca
council_id: ''
project_id: scribe_binding_reliability_repair_20260927
required_grants: []
revoked_at: null
policy_digest: dc2c419a489cabeab7120aaebdc708b98f4defc257eb2ea74d8eeee577701af5
title: "\U0001F52C Scribe Binding Reliability Root-Cause Analysis \u2014 scribe_binding_reliability_repair_20260927"
related_docs: []
last_updated: 2026-09-27 21:31:04 UTC
created_by: agent-20260927-050444-8c5cc6e2
maintained_by: agent-20260927-045601-3badc02f
status: ready
canonical_doc_type: other
edit_trace:
  tool: manage_docs
  created_at: 2026-09-27 05:17:42 UTC
  created_via: replace_section
  last_edited_at: 2026-09-27 21:31:04 UTC
  last_edited_by: agent-20260927-045601-3badc02f
  last_action: replace_text
  work_item_id: d88b1a97-d9bd-4737-9d88-8c8302c61e45
summary: Attach fresh same-session direct MCP binding-drop evidence to F1 root cause.
owners:
- Mantis
tags:
- binding
- session-isolation
- cross-repository
- typed-errors
- reliability
---


# 🔬 Scribe Binding Reliability Root-Cause Analysis — scribe_binding_reliability_repair_20260927
**Author:** Scribe
**Version:** v0.1
**Status:** ready
**Last Updated:** 2026-09-27 05:16:03 UTC

> Verified RCA for recurring caller-session binding loss, explicit cross-repository targeting, typed MCP errors, concurrency isolation, and Council integration boundaries.

---
## Executive Summary
<!-- ID: executive_summary -->
The recurring failure is real and reproducible. Three independent `append_entry` calls from the same long-running Atlas transcript returned the same transport-visible text, “ExecutionContext repo scope unresolved: no verified project binding for this request/session was available,” at [incident 1](aitrace:v1:codex:14e63e5e65f815c23a9a9d00021bd4a5), [incident 2](aitrace:v1:codex:b8e876ff62f3b59161e76c52334d2503), and [incident 3](aitrace:v1:codex:39ca43511b805df2f32f531e25580b75). The paired calls explicitly supplied the intended project, but the generic runtime rejected them before `append_entry` ran. An immediate `set_project` call then succeeded and restored operation ([call](aitrace:v1:codex:a0b7006ad03c0a25bcde82cb0bc7c024), [result](aitrace:v1:codex:9789fccd8c2d02f7fc9edd660986b257)).

The direct cause is `execute_tool_call()` in `src/scribe_mcp/shared/tool_runtime.py:927-1043`. It requires a verified repository root before dispatch, resolves the explicit project only when the ambient root is absent or unverified, and otherwise raises a plain `ValueError`. `src/scribe_mcp/server.py:697-715` forwards that exception, while `src/scribe_mcp/mcp_adapter.py:457-473` only normalizes successful return values. The caller therefore receives an untyped text error with no stable code, candidate list, retry classification, or structured MCP payload.

The architectural defect is broader than one missing lookup. Scribe conflates three different concepts: (a) caller-session default selection, (b) per-operation explicit target, and (c) repository authority. `set_project` must establish (a) once. A later explicit target must resolve (b) from the persisted project record—using `project_key` or the tuple of name plus canonical root—and must not mutate (a). Current code often makes the ambient repository and session-bound project an authorization fence, which blocks valid cross-repository explicit operations and encourages repeated rebinding.

Concurrency is also under-specified for the normal 10-plus-agent case. The durable `session_projects` seam is correctly keyed by a canonical caller session, but auxiliary identity and fallback paths still use the caller-supplied `agent` label, a single mutable `agent_projects` pointer, process-local caches, and legacy global state. Same-persona seats can therefore interfere when the exact transport/caller-session axis is absent or changes.

READY: the Scribe repair boundary is now source-localized and separable from Council. Scribe should own generic caller-session defaults, explicit project targeting, durable binding/error/document contracts, and latency. Council must retain Aegis, work-item, provider-seat, spawned-seat, terminal-completion, and hook-projection orchestration.


---
## Research Scope
<!-- ID: research_scope -->
This was a read-only RCA across `scribe_mcp` and `council_mcp`. Product source, tests, configuration, and generated projections were not modified. The only authored artifact is this report.

Evidence used:

- Five durable ai-trace call/result references, including all three failures and the immediate recovery pair.
- Direct Scribe `read_file` scans and targeted line reads for runtime dispatch, binding persistence, project resolution, state caches, managed-document operations, and MCP result normalization.
- Read-only Council inspection for session admission, local Scribe projection, Aegis startup binding, same-persona axes, and completion/projection ownership.
- Focused regression execution: `8 passed in 3.74s` for current unresolved-scope behavior, explicit-project append behavior, adapter result normalization, manage-doc runtime errors, canonical binding-key recovery, and parallel-agent isolation.
- Repo Intelligence was attempted first for the two primary Scribe anchors, but returned an honest unresolved active-project/version envelope. Structural claims below therefore rely on direct source reads and focused tests, not the degraded RI result.

Contract interpreted:

1. `set_project` or a future `bind_project` selects one durable default for the exact caller session.
2. Explicit project arguments target any registered Scribe project, including another repository, without rebinding or changing the default.
3. Resolution uses persisted project identity and canonical root. Same-name ambiguity requires a stable `project_key` or explicit root and returns typed candidates.
4. No resolution may select by shared agent/persona label.
5. Scribe remains generic. Council-specific admission, Aegis, work-item, seat, provider, and projection logic stays in `council_mcp`.


---
## Findings
<!-- ID: findings -->
### F1 — Verified recurring loss is rejected before the requested tool runs (P0)

`server._call_tool()` delegates at `src/scribe_mcp/server.py:697-715`. `execute_tool_call()` reconstructs request context, attempts a session binding lookup under `stable_session_id or session_id` at `shared/tool_runtime.py:966-1007`, and raises at `1028-1043` if no verified root is recovered. Because the failure occurs before function dispatch, the explicit `project` on `append_entry` cannot self-heal inside `append_entry.resolve_logging_context()`.

The incident proves the exact sequence: established long-running caller → three explicit-project append failures → one explicit-root `set_project` → success. Current tests intentionally assert the raw raise (`tests/test_set_project_runtime_scope_contract.py:91-119`, `tests/test_tool_runtime_repo_scope.py:156,232,266,300`) but do not prove a structured error or explicit-target recovery.

#### Fresh direct MCP reproduction — 2026-09-27 13:32 UTC

Council Atlas session `01a0b9bb-f8e0-7881-adfa-436da1df3635` produced a tighter causal sequence in one live turn:

1. `append_entry` succeeded for the already-bound project (`aitrace:v1:codex:a26ff28ee048475631baff53f4d97d65` → `aitrace:v1:codex:fc8b3cef9777e644eee2c1b162a739e2`).
2. Five seconds later, with no intervening `set_project` or project switch, the next `append_entry` failed (`aitrace:v1:codex:3ebf5a1a5d15094de3559d64f39669dd` → `aitrace:v1:codex:33bc576e5268ebbb4780df7773d3bae9`). The result was `isError:true` and exactly `ExecutionContext repo scope unresolved: no verified project binding for this request/session was available.`
3. Repeating the identical project/root bind succeeded (`aitrace:v1:codex:84a72d5f53fa0b0cb430b5f43abc3ca1` → `aitrace:v1:codex:af4098d56c2a2585b320940e8c97a946`).
4. The immediate retry of `append_entry` then succeeded (`aitrace:v1:codex:ebffe3313ea5c95a1e5ef674abfeda1c` → `aitrace:v1:codex:26d09e10c2fee45713152e104e0c6103`).

This rules out a caller project switch and demonstrates loss of previously usable binding state between ordinary calls inside one provider session. Repeating `set_project` is recovery evidence only, not the operator contract or intended procedure.

#### Second same-session recurrence — 2026-09-27 13:58 UTC

The same Council Atlas session later reproduced the defect again after the prior recovery and successful append, with no operator project switch:

1. A later explicit-project `append_entry` for the runtime-adoption incident returned no semantic success (`false`) despite the outer wrapper completing normally (`aitrace:v1:codex:e9dbbf537143f30ec8decaa2114435c9` → `aitrace:v1:codex:c9c17309b3b8a294c95a066bab39933a`). The operator identified the direct MCP response as the same verified-repository-scope loss.
2. The immediately following recovery used the identical agent, project name, and canonical repository root, then retried the append in the same call (`aitrace:v1:codex:0c0db199807049fe6cc3d60735317204` → `aitrace:v1:codex:09da56926ddb3470feab3f727122a518`).
3. That recovery result was `{"set_project_error":false,"append_ok":true}`.

This recurrence strengthens the persistence diagnosis: a previously restored binding can disappear again later in the same stable provider session. It also independently demonstrates the misleading-success boundary—the outer execution completed normally while the operation reported only `false`. Repeated `set_project` remains an emergency preservation workaround and must not be normalized as procedure.

#### Third same-session recurrence — 2026-09-27 14:57 UTC

The same Council Atlas session reproduced the defect a third time while recording the live Cortalabs deployment incident, again after earlier recovery and successful writes and with no operator project switch:

1. The explicit-project `append_entry` failed at the MCP boundary with `{"ok":false,"error":true}` (`aitrace:v1:codex:5a410b29ab1a9ae38702d2012832c16e` → `aitrace:v1:codex:3c0e9e51412af129dba75da0d7e2acf6`). The traced operation is classified `semantic_status:"error"`.
2. The immediately following recovery used the identical Atlas agent, Scribe project, and canonical Council repository root, then retried the append (`aitrace:v1:codex:ed9a6195197617556e56d742578e35d8` → `aitrace:v1:codex:89399b507bc8bffaeee4fbc1508c0672`).
3. The recovery result was `{"set_project_error":false,"append_ok":true}`.

This third recurrence shows that successful recovery does not make the binding durable: it can be lost repeatedly within one unchanged provider session. Repeating `set_project` is evidence that the current path can be temporarily repaired, not an accepted recovery contract or intended operator procedure.

#### Fourth same-session recurrence — 2026-09-27 15:28 UTC

The same Council Atlas session then lost binding scope on a read path, after successful project activation, reads, and writes and with no operator project switch:

1. An explicit-project `read_recent(agent="Atlas", project="cortalabs_public_deployment_infrastructure_20260912")` returned `isError:true` with the exact message `ExecutionContext repo scope unresolved: no verified project binding for this request/session was available.` (`aitrace:v1:codex:c7bfb077acf7849b2096358d973d4036` → `aitrace:v1:codex:27b57588f72220c2694bee6ebf1f0849`).
2. A simultaneous Council `list_messages` call succeeded, isolating the failure to Scribe's binding/context path rather than the outer execution wrapper.
3. The immediately following recovery repeated the identical Atlas agent, project name, and canonical Council repository root, then retried `read_recent` (`aitrace:v1:codex:e11a8d683a14187ad7977751a3a32836` → `aitrace:v1:codex:3561bc2b8a1d44f984e3abb8f74faf6c`). Both `set_project` and `read_recent` returned `isError:false`.

This recurrence proves the disappearing binding affects ordinary reads as well as writes. Repeating `set_project` remains recovery evidence only; it is neither resolution nor intended procedure.

#### Fifth same-session recurrence — 2026-09-27 15:48 UTC

The unchanged Council Atlas session lost the read binding again less than six minutes after a successful mirrored write:

1. At 15:42:10 UTC, explicit-project `append_entry` succeeded with `ok:true` and Postgres mirror status `ok` (`aitrace:v1:codex:668cbcc20404eb92513ea7c753acb949` → `aitrace:v1:codex:f154a38cb7981deda2c6239c38a3f43f`).
2. At 15:48:00 UTC, explicit-project `read_recent` returned `isError:true` and the exact unresolved verified-repository-scope message (`aitrace:v1:codex:6cfc14db91d231c066b3581d4f1099c7` → `aitrace:v1:codex:43bc3969980c125523bcd42a708da8a7`).
3. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried `read_recent` (`aitrace:v1:codex:cc20b0ac2475956093212d574ac7c0a5` → `aitrace:v1:codex:dfe8fdf51a27320cc8a4949fd69d9357`). The result reported `set_ok:true` and `read_recent.isError:false`.

The short success-to-loss interval further rules out ordinary inactivity as the cause. The binding remains ephemeral despite successful read/write use and repeated recovery. Repeating `set_project` is recovery evidence only, never resolution or intended procedure.

#### Sixth same-session recurrence — 2026-09-27 16:09 UTC

The unchanged Council Atlas session lost the read binding for a sixth documented time after both a successful write and a later successful read:

1. At 15:56:58 UTC, explicit-project `append_entry` succeeded with `ok:true` and Postgres mirror status `ok` (`aitrace:v1:codex:cdc52b7ef886c133cb7501e018b0f783` → `aitrace:v1:codex:23f96bc63bf99a0ea9df677c628569d3`).
2. At 16:05:24 UTC, explicit-project `read_recent` still succeeded (`aitrace:v1:codex:6e467ea76e497246c7355a769b151739` → `aitrace:v1:codex:288cccb424708c2eea6798b08b81c64d`).
3. At 16:09:50 UTC, the same explicit-project `read_recent` returned `isError:true` and the exact unresolved verified-repository-scope message (`aitrace:v1:codex:20e983498095dac5ab9d915c211aec4d` → `aitrace:v1:codex:aa9c71eafa7dc72160641ec5e2e0bcc3`).
4. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried `read_recent` (`aitrace:v1:codex:162fee12ebb4e2ca319316efcbf883a0` → `aitrace:v1:codex:4ce4e1e7fc62814e9d810242da3a21ef`). The result reported `set_ok:true` and `read_recent.isError:false`.

This sequence proves binding loss can occur within minutes of a successful read, not merely after an idle interval or write boundary. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Seventh same-session recurrence — 2026-09-27 16:31 UTC

The same Council Atlas session lost the read binding again after the successful 16:09 recovery read and without any operator project change:

1. The preceding recovery had returned `set_ok:true` and `read_recent.isError:false` for the identical Atlas/project/root axes (`aitrace:v1:codex:162fee12ebb4e2ca319316efcbf883a0` → `aitrace:v1:codex:4ce4e1e7fc62814e9d810242da3a21ef`).
2. At 16:31:14 UTC, explicit-project `read_recent` again returned `isError:true` and the exact unresolved verified-repository-scope message (`aitrace:v1:codex:8e4402a5f4ec0cf9fd6adeff7ec4776c` → `aitrace:v1:codex:21db1f2f36b16045cfe502feab2d8eb3`).
3. Five seconds later, the immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried `read_recent` (`aitrace:v1:codex:71b4385cb62261697f0002f37397ac85` → `aitrace:v1:codex:e4737f47dbbd5c41a48fd139b457e203`). The result reported `set_ok:true` and `read_recent.isError:false`.

This seventh recurrence confirms the same binding repeatedly disappears after verified recovery in one unchanged provider session. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Eighth same-session recurrence — 2026-09-27 16:47 UTC

The unchanged Council Atlas session lost the read binding again after the successful 16:31 recovery and with no operator project change:

1. The prior recovery had returned `set_ok:true` and `read_recent.isError:false` for the identical Atlas/project/root axes (`aitrace:v1:codex:71b4385cb62261697f0002f37397ac85` → `aitrace:v1:codex:e4737f47dbbd5c41a48fd139b457e203`).
2. At 16:47:25 UTC, explicit-project `read_recent` again returned `isError:true` and the exact unresolved verified-repository-scope message (`aitrace:v1:codex:b7b2d5f6b87c179d83201b259f3116dd` → `aitrace:v1:codex:4ef88a384bebcd8e52f1cffec8f9b316`).
3. Seven seconds later, the immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried `read_recent` (`aitrace:v1:codex:6a77702c112195267ab47df39fce5024` → `aitrace:v1:codex:dec82d975b67180ef0be1645d8d56148`). The result reported `set_ok:true` and `read_recent.isError:false`.

This eighth recurrence demonstrates continuing periodic loss after repeated verified recovery in one stable provider session. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Ninth same-session recurrence — 2026-09-27 17:42 UTC

The unchanged Council Atlas session later lost binding scope on an explicit-project write after prior successful activation, reads, and logging:

1. At 17:42:46 UTC, `append_entry(agent="atlas", project="cortalabs_public_deployment_infrastructure_20260912")` returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:c9b4c6bf40e7d80cb5258374d3362bb9` → `aitrace:v1:codex:d6dfb49c6ae0794f47e7ecfa8dac46f9`).
2. The outer execution completed normally, again demonstrating that callers must inspect the MCP semantic result rather than wrapper success alone.
3. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried the same append (`aitrace:v1:codex:c72e9929441d98f1886a1c9a55ae570a` → `aitrace:v1:codex:f44bdae69cd6abf38f8ab206b9f704f8`). The retry returned `ok:true` with Postgres mirror status `ok`.

This ninth recurrence reconfirms that both read and write bindings periodically disappear inside one stable session. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Tenth same-session recurrence — 2026-09-27 19:13 UTC

The unchanged Council Atlas session lost binding scope again after many successful Scribe operations and, per the operator handoff, after runtime 2.172.0 adoption:

1. At 19:13:13 UTC, an explicit-project `append_entry` for a completed 2.172.2 migration-transport checkpoint returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:ee4a2555f1024ba0f9115974864cbada` → `aitrace:v1:codex:2e15f32358bd8f3dacabc0ca42f0eb61`).
2. The outer execution completed normally, preserving the misleading-success boundary already observed in earlier write-path recurrences.
3. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried the same append (`aitrace:v1:codex:5291c528248b4ee8d5e064aeac620321` → `aitrace:v1:codex:e767e7517f78ec374588df9d3f70b878`).
4. The recovery wrote the checkpoint at 19:13:30 UTC with `ok:true` and Postgres mirror status `ok`.

This post-adoption recurrence shows that Council/runtime generation progress does not stabilize Scribe's session binding. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Eleventh same-session recurrence — 2026-09-27 19:33 UTC

The unchanged Council Atlas session lost binding scope again on an explicit-project write about twenty minutes after recurrence ten:

1. At 19:33:58 UTC, `append_entry(agent="atlas", project="cortalabs_public_deployment_infrastructure_20260912")` for a Hoshin dependency checkpoint returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:fb1a26baa3d9e9f1f7193d392f750d45` → `aitrace:v1:codex:976db49e744d2ed3375890ef521cd71a`).
2. The outer execution completed normally, preserving the semantic-failure/transport-success defect.
3. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root (`aitrace:v1:codex:27143c2539866bfe6bba248d4fce8292` → `aitrace:v1:codex:8ada45723dc20f4756fff276c21e5fd6`).
4. Retrying the identical append then succeeded at 19:34:17 UTC with `ok:true`, Postgres mirror status `ok`, and log ID `422383218180b47502446a00b9a11215` (`aitrace:v1:codex:310570876dac68d15369f75aa767cf59` → `aitrace:v1:codex:ba77947be6f880ccdc68b8888c736bbb`).

This eleventh recurrence confirms that binding loss persists repeatedly within one stable provider session and across unrelated Council activity. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Twelfth same-session recurrence — 2026-09-27 19:53 UTC

The unchanged Council Atlas session lost binding scope again after Council 2.173.0 adoption and a supervised Web reload:

1. At 19:53:46 UTC, an explicit-project `append_entry` for a runtime/recovery checkpoint returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:9581383b44d551eccb4242a0f9ee977c` → `aitrace:v1:codex:d82d0f0179580dd01ade483a748d2c30`).
2. The outer execution completed normally, preserving the semantic-failure/transport-success defect.
3. The recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root (`aitrace:v1:codex:f70dfc31de2dc38681a5453999d4003e` → `aitrace:v1:codex:b9c0e91258f64272724ec5ca0082e752`).
4. Retrying the identical append succeeded with `ok:true`, Postgres mirror status `ok`, and log ID `362f0b3508bba67d4a88a693bcbeddcd` (`aitrace:v1:codex:745a8085d1795e1f6e6c5442e34dd19c` → `aitrace:v1:codex:b3bff2c69d6d4205c10754f79f261b2d`).

This twelfth recurrence shows that Council daemon adoption and Web process replacement do not restore Scribe binding durability. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Thirteenth same-session recurrence — 2026-09-27 20:11 UTC

The unchanged Council Atlas session lost binding scope again after 2.173.0 live convergence while the upstream per-seat identity repair was active:

1. At 20:11:49 UTC, an explicit-project `append_entry` for a communications/migration checkpoint returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:b4356a9ba494cf74a0b77a20fd93c463` → `aitrace:v1:codex:ae3871f79780750962122e0521155702`).
2. The outer execution completed normally, preserving the semantic-failure/transport-success defect.
3. The recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root (`aitrace:v1:codex:758cac1caea2405acc8120df75159b7b` → `aitrace:v1:codex:7581a1b80bd06fe359f625c263a180b8`).
4. Retrying the identical append succeeded with `ok:true`, Postgres mirror status `ok`, and log ID `9c771c1f65beee2ba982909723198b36` (`aitrace:v1:codex:0c71da9fd1d2684b0214a5047029d7bf` → `aitrace:v1:codex:87f4b726adc79d3588a5c006115583c1`).

This thirteenth recurrence confirms that live Council convergence and active upstream repair do not mask or cure the independent Scribe binding loss. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Fourteenth same-session recurrence — 2026-09-27 20:42 UTC

The unchanged Council Atlas session lost binding scope again immediately after governed Council 2.173.4 adoption:

1. At 20:42:02 UTC, an explicit-project `append_entry` for the adoption/authority incident returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:aaf97447ef86df680ff24791073451e5` → `aitrace:v1:codex:b30db05e3a5d2f7c1abae5c3c3ddb7ae`).
2. The outer execution completed normally, preserving the semantic-failure/transport-success defect.
3. One combined recovery call repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried the append (`aitrace:v1:codex:0448a0eaa2dec12e0af7d3d884031e49` → `aitrace:v1:codex:daa2f006415317ac8001fab9725b32f5`).
4. The retry succeeded with `ok:true`, Postgres mirror status `ok`, and log ID `55c6dbdf24d40bb7e058c1060be67558`.
5. The same incident checkpoint records concurrent Council authority re-adoption failure for Council session `91fc8ca7-2e52-4295-8464-f894b1516f24`: `binding_missing` followed by `local_binding_cas_lost.foreign_connection` at transport epoch 52. That is Council-owned evidence, while the Scribe append failure remains independently verified by the paired calls above.

This fourteenth recurrence shows a single process-generation change can expose both systems' distinct ephemeral-identity failures at once. Neither Council re-adoption nor Scribe `set_project` repetition is an acceptable steady-state procedure.

#### Fifteenth same-session recurrence — 2026-09-27 21:04 UTC

The unchanged Council Atlas session lost binding scope again immediately after a successful governed commit and push:

1. At 21:04:40 UTC, an explicit-project `append_entry(agent="atlas", project="cortalabs_public_deployment_infrastructure_20260912")` returned the exact unresolved verified-repository-scope message (`aitrace:v1:codex:3f04721fe0c91ea5b4cbb12789c32aed` → `aitrace:v1:codex:3b1d736ea65a82796a8dedf471b95fce`).
2. The outer execution completed normally, preserving the semantic-failure/transport-success defect.
3. The immediately following recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root, then retried the same append in one combined call (`aitrace:v1:codex:3b2018cde6ada52b0eec65cddcd07d5d` → `aitrace:v1:codex:18996405cd2ff829bdbcddbc8cbb5b1e`).
4. The retry succeeded with `ok:true`, Postgres mirror status `ok`, log ID `99ebaa9e73f28bf28a0ed75b6b34cceb`, and 138.934 ms Scribe timing.

This fifteenth recurrence proves that Git activity is merely adjacent timing: a successful commit/push does not itself preserve or restore Scribe binding scope. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

#### Sixteenth same-session recurrence and projection split-brain — 2026-09-27 21:24–21:26 UTC

The unchanged Council Atlas session exposed the same lost binding on both Council-owned projection reconciliation and a later direct append:

1. At 21:24:30 UTC, Atlas ran `council work reconcile-projection 9da446dc-a1c1-45da-a86e-0c4a0a6c04a1` (`aitrace:v1:codex:d7c7b51dd247957b238a12cf0753ffc7` → `aitrace:v1:codex:e48cda4b38560c26d46fed3757033515`).
2. The command's Scribe subprocess logged `Tool 'manage_docs' raised an unexpected exception` and the exact unresolved verified-repository-scope `ValueError` from `tool_runtime.py`. In the same outer result, Council nevertheless reported `Projection: projected` and receipt `prj-818c517e5752d9e0fe9c408f` as `reconciled`. This is direct evidence that the current projection receipt can claim convergence while its managed-document call failed.
3. At 21:26:00 UTC, a separate explicit-project `append_entry` returned the same unresolved verified-repository-scope message (`aitrace:v1:codex:c26756bf523a4482c558e4e2d999f46b` → `aitrace:v1:codex:659fcdd6a8ac3402bd8b8d0b828c0868`).
4. The immediately following combined recovery repeated the identical Atlas agent, Scribe project, and canonical Council repository root and retried the append (`aitrace:v1:codex:f980b1841d0dc5daf0c878f8570375e7` → `aitrace:v1:codex:d6cd88456f06d0eb7f7431f9c37587cd`).
5. The retry succeeded with `ok:true`, Postgres mirror status `ok`, log ID `136036cb532aca9ad543b32e3191eb19`, and 103.009 ms Scribe timing.

This sixteenth recurrence broadens the verified blast radius: the disappearing binding affects direct logging and the Council → Scribe managed-document projection path, while Council receipt status can conceal the Scribe-side exception. Repeating `set_project` remains recovery evidence only, never resolution or intended procedure.

### F2 — Read and write keys were historically asymmetric; current source repairs only that narrow case

`shared/tool_runtime.py:966-986` documents the known stable/session-key mismatch and now reads the same canonical key used by `set_project`. `tests/test_tool_runtime_repo_scope.py:461-535` guards this. This is necessary but not sufficient: if the transport/caller-session identity changes, is absent, or is reconstructed under a different actor-scoped key, there is still no durable binding to read. The default binding contract needs an explicit, observable caller-session key and generation rather than inference from mutable request context.

### F3 — Explicit targeting is coupled to ambient repository/default state (P0 contract conflict)

`shared/tool_runtime.py:927-965` adopts an explicit project record’s root only when the current root is missing or not verified. A correctly verified ambient root therefore prevents the runtime from establishing a different explicit target before dispatch.

`shared/logging_utils.py:339-461` resolves explicit names globally but then:
- authorizes ordinary writes only when the name matches the session binding or the target root equals the verified ambient root (`420-447`);
- permits `read_recent` as a special cross-project read but explicitly rejects a different root (`455-461`);
- exposes no typed ambiguity/authorization payload because `ProjectResolutionError` carries only message and recent names (`83-89`).

This is the repository-lock behavior prohibited by the current work-item contract. The target project’s own persisted identity/root must govern the operation while the ambient default remains unchanged.

### F4 — The persisted project model already has the right identity, but callers do not use it end to end

`storage/models.py:172-193` defines deterministic `project_key` and `ProjectRecord.project_key`. Storage `fetch_project` accepts `repo_root` and `project_key` (`storage/base.py:81-108`), and SQLite/PostgreSQL enforce unique project-key indexes. However, `set_session_project` stores only `session_id -> project_name` (`storage/base.py:453`; PostgreSQL `storage/postgres/__init__.py:1837-1860`; SQLite `storage/sqlite/sessions.py:122-159`). Explicit tool schemas generally accept only a project name. This discards the stable identity needed to survive same-name projects across repositories.

### F5 — Same-persona isolation is not an exact-seat contract in Scribe

`_derive_session_identity_preview()` hashes `repo_root:mode:project:agent` at `shared/tool_runtime.py:413-455`. The `agent` value is caller-supplied and commonly a persona/spawn label, not a server-verified seat/session identifier. `AgentContextManager.set_current_project()` persists one mutable pointer per `agent_id` at `state/agent_manager.py:109-213`. Two live seats that share that label can overwrite the pointer even though durable session bindings are separate.

The in-memory router caches `transport_session_id -> session_id` and `session_id -> project_name` (`shared/execution_context.py:256-257,283-349`), while `StateManager` also retains session, recent-project, and compatibility global caches (`state/manager.py:237-289,459-526`). These are safe only when every request carries the exact stable session. The current `tests/test_session_isolation.py` proves different agent names and different synthetic runs, not two same-persona seats with distinct server-verified caller sessions across repositories.

### F6 — MCP error typing exists for returned mappings but not for runtime exceptions

`mcp_adapter.normalize_tool_result()` correctly preserves `structuredContent` and `isError` for returned mappings (`mcp_adapter.py:318-380`; guarded by `tests/test_mcp_adapter.py:161-182`). But `call_tool_bound()` validates, awaits, and normalizes without an exception translation boundary (`457-473`). Thus the scope `ValueError` escapes as transport text. Tool-local structured errors such as `MANAGE_DOCS_RUNTIME_EXCEPTION` (`tools/manage_docs.py:300-321`, `tests/test_manage_docs_reminders.py:114-133`) do not cover pre-dispatch failures.

### F7 — `set_project` mixes a cheap bind with expensive inventory/bootstrap

The tool’s default readable path blocks the same-binding reuse fast path via `readable_sitrep_requested` (`tools/set_project.py:903-925`). A non-reused bind performs downstream asset bootstrap and document generation before the authoritative session binding write (`1047-1058` versus binding persistence at `1268-1383`), then counts entries and scans inventory (`1422-1510`). The incident recovery took 8.8 seconds. Binding availability should not wait for document generation or a human-readable inventory.

### F8 — Managed-document durability has atomic file tools, but no offline operation spool

Scribe has progress-log WAL replay only: `server._replay_journals_background()` scans progress-log `.journal` files at `842-962`. Managed-doc edits have atomic writes, hashes, anchor CAS, change records, and apply-preview receipts, but no durable queue that records a typed requested mutation while the database/runtime is offline and later replays it under the same project/session/document generation. Consequently “offline spool” is a missing capability, not an existing broken retry.

### F9 — Binding and document generations are incomplete

Agent project pointers have an optimistic `version`, and managed sections support `expected_anchor_sha256`. Session bindings store only project name plus timestamp; no monotonic binding generation or project key is returned/required. Documents expose content/anchor hashes but no uniform document-generation field across all managed-doc operations. Without both generations, a queued/retried operation cannot prove “same default binding, same target document state.”

### F10 — Council’s Scribe state is projection, not actual Scribe runtime binding

Council `open_session` persists its admission and a local projection (`council_mcp/tools/sessions.py:7755-7880`) but does not call Scribe. The heartbeat’s `ensure_scribe_selection()` reads only `read_session_scribe_project_projection()` and explicitly treats Scribe as an audit association (`sessions.py:1635-1671`). Therefore `scribe_binding_state=current` can mean “Council projection matches” while the next direct Scribe call still has no verified Scribe binding. This explains projection state noise and must be repaired upstream in Council without importing Council semantics into Scribe.

### F11 — Council child proxies can collide on one project/client registry row

`council_mcp/storage/council_models.py:1012-1089` upserts `council.client_registry` on conflict by `(project_id, client_id)` and stores one mutable `session_id` forward pointer. A sibling child process that inherits or reuses the same parent-derived `client_id` therefore addresses the same registry row: reconnect, exit, clear, or re-registration can repoint or end the association another exact seat still needs. The live Seshat recovery path reproduced the resulting split: read-only Council MCP worked, while governed recovery returned `CLIENT_BOUND_SESSION_MISMATCH` / `open_session_not_found`; a mission reopen then failed `MISSION_SCRIBE_PROJECT_UNRESOLVED`.

This is Council-owned client/session admission state, not a Scribe binding key. The upstream repair must partition registry/admission authority by exact child seat/run/connection axes and preserve project association across reconnect. Scribe should receive only the resulting verified generic caller-session identity.


---
## Technical Analysis
<!-- ID: technical_analysis -->
### Required defect matrix

| Defect / contract | Current causal boundary | Existing coverage | Required package boundary |
|---|---|---|---|
| Persistence / exact-seat identity | `set_project.py:1268-1383` writes the canonical session binding, but `tool_runtime.py:413-455` derives auxiliary identity from repo/project/`agent`; `agent_manager.py:109-213` is agent-label keyed. | Canonical stable-key lookup is covered; same-persona exact-session multi-repo concurrency is not. | Scribe: caller-session-keyed default binding and no persona-based resolution. Council: inject/retain verified provider/seat session axes upstream. |
| Explicit-project self-heal | Pre-dispatch explicit resolution is conditional on missing/unverified ambient root (`tool_runtime.py:927-965`), so a valid ambient default can block a different target. | Sentinel explicit append and missing-name fail-closed tests only. | Scribe: resolve `ProjectTargetV1` before repo-scope rejection; never mutate default. |
| Structured MCP errors | Plain exceptions cross `server.py:697-715` / `mcp_adapter.py:457-473`. | Mapping normalization and tool-local manage-doc error tests. | Scribe: one runtime exception-to-`CallToolResult(isError=true)` translator with stable codes, fields, retryability, candidates, and remediation. |
| Spawned-seat exposure / admission | Council `open_session` records admission and projections; Scribe has no seat concept. | Extensive Council session lifecycle tests; no joint direct-Scribe bind proof. | Council only: expose a verified caller-session binding input/receipt to Scribe and run real direct-Scribe acceptance. |
| Same-persona isolation | Scribe agent pointer is keyed by caller `agent`, while Council distinguishes sibling seats with raw requested spelling and provider/run/hook axes (`council_mcp/tools/sessions.py:6832-6847`). | Scribe different-agent/different-run tests; Council same-persona tests separately. | Joint acceptance, but source stays split: generic caller-session identity in Scribe; seat admission in Council. |
| Terminal completion projection | Council completion attestations live in `services/hook_identity.py:141-440,4187+`. | Council completion/projection tests. | Council only. Scribe may emit generic immutable operation receipts, never work-item terminal logic. |
| Projection state noise | Council heartbeat calls local `read_session_scribe_project_projection` and may report `current` without a Scribe RPC (`sessions.py:1635-1671`). | Council projection state tests assert local state. | Council: label projection truth distinctly from Scribe runtime/default-binding truth; only claim live binding after a Scribe receipt/readback. |
| Structured artifacts | Scribe responses are mostly dict/TextContent; Council owns completion attestations and work evidence. | Adapter structure tests exist, but no generic artifact envelope for bind/doc mutations. | Scribe: generic `BindingReceiptV1`, `ProjectResolutionErrorV1`, `DocumentMutationReceiptV1`. Council composes them into its own artifacts. |
| Managed-doc offline spool | Only progress-log WAL is replayed (`server.py:842-962`); managed-doc requests have no spool. | Atomic-write/apply-preview tests, not outage/replay tests. | Scribe: optional local durable spool keyed by operation id + project key + binding generation + document generation; explicit queued/applied/conflict terminal states. |
| Cheap bind vs inventory | Default readable call disables reuse and performs doc bootstrap/inventory before binding (`set_project.py:903-925,1047-1058,1268-1510`). | Timing envelope tests observe phases but do not require bind-first latency. | Scribe: split `bind_project` (or fast `set_project`) from `project_inventory`; commit binding before optional enrichment. |
| Binding / document generations | Agent pointer has version; session binding has name/timestamp only; documents have hashes/anchor CAS but no uniform generation. | Isolated version/hash tests. | Scribe: monotonic binding generation per caller session and document generation/content digest on every mutation/readback. |
| End-to-end matrix | Current tests are component-local; Council projection and Scribe runtime are tested separately. | No single 10-plus-agent, multi-repo, same-persona, outage/reconnect matrix. | Joint acceptance suite with source-owned tests in each repo plus a Council integration lane. |
| Aegis startup binding | `council_mcp/config/__init__.py:3533-3650` probes activated sockets and collapses non-typed failures to `AEGIS_STARTUP_BINDING_UNAVAILABLE`. The live 19:42 Codex CLI renewal was subsequently classified upstream as sandbox-denied AF_UNIX `EPERM`, while the direct MCP path remained reachable (`aitrace:v1:codex:6aae21fe66d805f17df639b707d59a45`). | Council Aegis activation tests do not yet prove the sandbox-denied/remedy distinction. | Council only: return a distinct non-transient transport-denied code and truthful remedy; do not prescribe reload for sandbox policy and do not add Aegis behavior to Scribe. |
| Child proxy client collision | `council_mcp/storage/council_models.py:1012-1089` stores one session pointer per `(project_id, client_id)`; sibling proxies sharing a parent-derived client ID can overwrite the same row. | Session tests cover client binding, but live sibling exit/reconnect caused `CLIENT_BOUND_SESSION_MISMATCH` and missing project-bound mission authority. | Council only: exact child seat/run/connection partitioning and reconnect-safe ownership; pass Scribe only the verified generic caller-session key. |

### Desired state and invariants

1. **Default selection:** `bind_project(caller_session_key, project_key)` is idempotent. It returns `binding_generation`, selected `project_key`, canonical root, and resolution evidence.
2. **Explicit target:** each target-capable tool accepts a common target object: `{project?: name, project_key?: stable id, repo_root?: canonical root}`. Name-only lookup succeeds only when unique. Ambiguity returns typed candidates containing safe identifiers and roots.
3. **Ambient state invariant:** explicit targeting is request-local. Before and after values of the caller-session default binding are identical.
4. **Authority invariant:** target resolution derives root/repo identity from the persisted project record. The current working directory, daemon root, caller persona, and another session’s default never select the target.
5. **Concurrency invariant:** 10-plus simultaneous callers—including siblings sharing the same persona label—remain isolated by a server-verified caller-session key. `agent` is attribution only.
6. **Error invariant:** expected failures are data, not thrown transport text. Stable codes include at least `SCRIBE_BINDING_MISSING`, `SCRIBE_PROJECT_NOT_FOUND`, `SCRIBE_PROJECT_AMBIGUOUS`, `SCRIBE_PROJECT_ROOT_MISMATCH`, `SCRIBE_CALLER_SESSION_UNVERIFIED`, `SCRIBE_BINDING_GENERATION_STALE`, and `SCRIBE_DOCUMENT_GENERATION_STALE`.
7. **Durability invariant:** queued/retried document work cannot apply to a different project, caller binding generation, or document generation.
8. **Performance invariant:** a warm/default bind does not enumerate inventory or regenerate documents. Inventory is an explicit read operation.

### Normal 10-plus-agent interference inventory

- **Global/process state:** `server.storage_backend`, `state_manager`, `router_context_manager`, `agent_context_manager`, `agent_identity`, and legacy `app.state.execution_context`. Most are service singletons by design; correctness must come from request ContextVars and durable keys, never mutable singleton selection.
- **Caller-label keyed:** `agent_projects`, AgentContextManager leases, activity, and recent-project rows use `agent_id`. They are unsafe as binding authority when multiple seats share a label.
- **Connection/transport keyed:** router `_transport_sessions` is correct only if the host provides a stable, unique transport identity across calls and reconnects. Process fallback or actor-scoped reconstruction can create a new key after a prior bind.
- **Session keyed:** `session_projects` is the preferred authority seam but currently stores only a name, not stable project id/root/generation.
- **Mutable defaults:** `State.current_project`, global-agent fallback, and recent-project lists remain compatibility/UI surfaces. They must never select a target for an identified caller.
- **Project-scoped identity:** current agent-session reuse hashes the explicit project and root. That turns a request-local explicit target into a different identity and conflicts with unchanged ambient default state.
- **Council-local projection:** provider/session/work-item projection stores are upstream hints/authorities for Council, not proof of Scribe’s live default binding.

### Reproducer model

Minimal failure:
1. Establish a caller session and bind project A.
2. Issue a later target-capable tool call with explicit project A (or B) from a request where the verified transport/caller-session key is absent or differs.
3. `execute_tool_call` fails at `tool_runtime.py:1040` before the target tool.
4. Observe untyped text.
5. Re-run `set_project(name=A, root=A.root)`; it creates/updates the missing session/root mapping.
6. Retry succeeds.

Contract-conflict reproducer to add:
1. Bind project A in repository A.
2. Call `append_entry(project=B.name, project_key=B.key)` where B is in repository B.
3. Assert write lands only in B, A remains the caller default, and the same caller-session/binding generation remains current.
4. Run concurrently for at least 12 callers, including two pairs sharing the same `agent` label.


---
## Recommendations
<!-- ID: recommendations -->
### Scribe package SBR-S1 — Generic binding and target resolver (highest priority)

Owned source boundary:
- `shared/tool_runtime.py`
- `shared/logging_utils.py`
- `shared/execution_context.py`
- `tools/set_project.py` or a thin `bind_project` endpoint reusing its authorization primitives
- storage session-project models/backends

Implement one resolver shared by every tool:

`resolve_project_target(caller_session_key, explicit_target | default_binding) -> ResolvedProjectTarget`

The returned value must include `project_key`, project name, canonical root, repository id, resolution source, and binding generation. Resolution precedence: explicit `project_key`; name + explicit root; unique name; caller default when no explicit target. Ambiguous name-only queries return typed candidates. Remove agent/persona matching and ambient-root equality as target authorization rules. Preserve actual filesystem/root policy at mutation time using the resolved target’s own persisted authority.

Persist session defaults by `caller_session_key -> project_key`, not name. Retain name only as display/compatibility data. Keep explicit targeting request-local and assert default readback is unchanged.

### Scribe package SBR-S2 — Typed MCP failure boundary

Add a generic public exception/envelope type and translate expected runtime failures inside `mcp_adapter.call_tool_bound()` or immediately around `server._call_tool()`. Return `CallToolResult` with:
- `isError: true`;
- text summary;
- `structuredContent: {ok:false, error_code, message, retryable, target, candidates, remediation, correlation_id}`.

Do not make tools individually catch the same pre-dispatch errors. Preserve unexpected exceptions as a distinct internal-runtime code with safe details and server logging.

### Scribe package SBR-S3 — Exact caller-session isolation and generation

Make the server-verified transport/caller-session identity the sole binding key. Treat `agent` as attribution. Add monotonic `binding_generation` and return it from bind/readback operations. Remove identified-caller fallback to `agent_projects` or global current-project state. Cache entries must carry project key and generation and validate against durable state after reconnect.

Regression cases:
- 12 concurrent callers across at least 3 repositories;
- two same-persona/same-agent-label sibling pairs;
- reconnect with the same verified caller session;
- a new caller session with the same persona does not inherit the old default;
- explicit B operation does not alter default A;
- name collision across repos requires project key/root;
- stale binding generation fails typed.

### Scribe package SBR-S4 — Split bind from inventory

Make the binding commit the first small durable action after target validation. Return a structured receipt immediately. Move document scaffolding, counts, reminders, and SITREP inventory behind explicit enrichment/inventory calls or an optional post-bind phase that cannot invalidate an already committed bind. The default readable format must not disable the warm-bind fast path.

Acceptance budgets should distinguish bind latency from inventory latency. The incident’s 8.8-second recovery is the baseline to improve, not an acceptable bind SLA.

### Scribe package SBR-S5 — Document generations and offline spool

Standardize `DocumentMutationReceiptV1` with operation id, project key, caller-session key hash, binding generation, document id/path, document generation/content digest before and after, status, and replay safety.

Only then add an offline spool. Spool immutable normalized intents; never raw transient context. Replay must re-resolve project key and compare both generations. Outcomes are `applied`, `duplicate`, `conflict`, or `terminal_error`; no silent retargeting. Reuse apply-preview receipt and atomic-write primitives rather than creating a parallel mutation engine.

### Council package SBR-C1 — Real Scribe bind activation/readback

Keep this entirely in `council_mcp`. `open_session`/spawn admission should provide the exact caller-session axis and intended Scribe project to the Scribe client, perform or request the generic bind once, and retain the returned generic receipt. Do not claim `scribe_binding_state=current` from hook projection alone. Expose separate fields for `scribe_projection_state` and `scribe_runtime_binding_state`.

### Council package SBR-C2 — Admission, same-persona, completion, and projection cleanup

Continue using Council’s provider/session/run/hook/spawn axes. Bind spawned seats before first work, preserve same-persona sibling isolation, retire terminal completion projections, and reduce local projection rows/noise. Consume Scribe’s generic receipts as evidence; do not move Council work-item, Aegis, provider, seat, completion-attestation, or hook-projection concepts into Scribe.

### Council package SBR-C3 — Aegis typed startup errors

Preserve the current Aegis reason-code family in `config/__init__.py:3611-3650`, but stop collapsing all non-`RuntimeError` causes to the generic unavailable code where a safe typed cause is known. This package is independent of Scribe binding semantics.

### Required end-to-end acceptance matrix

Run a joint integration lane covering:
- cold open → bind → direct Scribe log;
- reconnect → default readback without rebinding;
- explicit same-repo target and explicit cross-repo target;
- same-name collision with typed candidates;
- 12 concurrent callers, same-persona siblings, and different providers;
- spawned-seat admission before first Scribe operation;
- Scribe restart/cache loss with durable default recovery;
- Council restart/projection loss with no false live-binding claim;
- structured errors at each failure boundary;
- managed-doc DB outage → queued receipt → restart → generation-safe replay;
- terminal Council completion and projection retirement;
- latency assertions for cheap bind independently of inventory.

No package should be declared complete from unit tests alone; the final proof is direct tool behavior with unchanged ambient state.


---
## Appendix
<!-- ID: appendix -->
### Durable transcript evidence

- Failure 1 call/result pair: `aitrace:v1:codex:563d7dbb46585ffe9610b017ebd70121` → `aitrace:v1:codex:14e63e5e65f815c23a9a9d00021bd4a5`.
- Failure 2 call/result context: `aitrace:v1:codex:a4cf9941820cae6aa612daf4db9a2b03` → `aitrace:v1:codex:b8e876ff62f3b59161e76c52334d2503`.
- Failure 3 call/result pair: `aitrace:v1:codex:e74c62636ef63f1fc4ff777e913b2020` → `aitrace:v1:codex:39ca43511b805df2f32f531e25580b75`.
- Recovery call/result pair: `aitrace:v1:codex:a0b7006ad03c0a25bcde82cb0bc7c024` → `aitrace:v1:codex:9789fccd8c2d02f7fc9edd660986b257`.

The second reference was refreshed and reconstructed with `trace_context`; freshness was current and complete.

### Focused verification run

Command:

`./.venv/bin/pytest -q tests/test_set_project_runtime_scope_contract.py::test_execute_tool_call_set_project_root_omitted_fails_without_verified_binding tests/test_append_entry_explicit_project_resolution.py::test_append_entry_passes_explicit_project_to_context_in_sentinel_mode tests/test_append_entry_explicit_project_resolution.py::test_append_entry_missing_explicit_project_in_sentinel_mode_does_not_fallback_to_sentinel tests/test_mcp_adapter.py::test_result_normalization_preserves_structured_text_and_error_semantics tests/test_manage_docs_reminders.py::test_manage_docs_returns_structured_error_when_runtime_raises tests/test_session_isolation.py::test_parallel_agent_isolation tests/test_tool_runtime_repo_scope.py::test_session_binding_read_uses_canonical_stable_session_key`

Result: `8 passed in 3.74s`.

### Coverage gaps that must become regressions

- Runtime scope failure returns typed MCP data instead of raising.
- Explicit target resolution occurs before ambient repo-scope rejection.
- Cross-repository explicit read and write succeed without rebinding.
- Default binding remains byte-for-byte/generation-identical after explicit operations.
- Same-name projects return typed candidate records; project key/root disambiguates.
- Session binding persists project key/root/generation, not name alone.
- Same-persona sibling sessions remain isolated under 12-way concurrency.
- Reconnect recovers the same default by verified caller-session identity.
- Process fallback and agent label never acquire another caller’s default.
- Warm bind omits inventory/scaffold work and meets a separate latency budget.
- All expected pre-dispatch failures carry stable codes and `isError=true`.
- Managed-document spool replay checks binding and document generations.
- Council projection truth cannot be presented as live Scribe-binding truth.
- Spawned-seat first direct Scribe call succeeds without a manual rebind.
- Council completion/projection cleanup does not alter Scribe generic state.

### Risks and facts not yet proven

- The exact host-side reason the long-running incident request lost or changed its verified transport/caller-session key is not encoded in the returned Scribe error. Current evidence proves the missing binding at dispatch and the successful immediate repair, but not whether the upstream trigger was reconnect, proxy identity loss, cache eviction, or a host context omission. The repair must make those cases observationally distinct.
- RI could not resolve an active indexed project/version for this checkout during the query. No structural claim relies on that failed lookup.
- No product fix was made in this package.
- The existing project architecture/phase/checklist documents are generic scaffolds and should be replaced by Blueprint after this RCA; this report is the implementation-ready evidence source.

### Handoff status

READY for Blueprint/Seshat. Every required defect has a causal source boundary, current coverage statement, and bounded Scribe-versus-Council repair package. The one unresolved trigger detail is explicitly converted into required typed observability and does not block repair architecture.


---