
# HeatSeeker Integration Gap Audit
**Author:** Gauge (Council Auditor)
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-02-22 UTC
**Grade:** 78/100 -- SEND BACK for specific fixes before implementation begins.

> Comprehensive audit of every integration point between the planned HeatSeeker C# RNG scanner and the existing Python automation infrastructure: scan pipeline, warp mode, execution flow, frontend UI, and binary protocol.

---
## Executive Summary
<!-- ID: executive_summary -->

**Primary Objective:** Map every integration gap, orphaned code path, disconnected wiring, and dead code risk in the HeatSeeker project before implementation begins.

**Key Takeaways:**
- 15 integration gaps identified (3 CRITICAL, 6 HIGH, 4 MEDIUM, 2 LOW)
- Architecture is fundamentally sound -- capability-based routing with fallback is the right pattern
- Critical missing piece: **data contract** between C# CandidateResult and Python enrichment/execution
- 3 CRITICAL gaps are protocol-layer -- no HeatSeeker constants, capabilities, or routing exist yet (expected pre-implementation)
- Existing Python scan becomes fallback, NOT dead code -- but must be cleanly gated
- Existing warp and HeatSeeker precision warp serve different purposes and must coexist
- Lua warp gate behavior during HeatSeeker precision warp is undocumented


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** Gauge (auditor)

**Investigation Window:** 2026-02-22

**Focus Areas:**
- [x] A: Scan Pipeline to HeatSeeker Migration
- [x] B: Warp Mode Integration (old chunked warp + new precision warp)
- [x] C: Execution Flow (scan -> select -> execute with HeatSeeker candidates)
- [x] D: Dead Code Risk Assessment
- [x] E: Build/Deploy and Protocol Layer

**Files Audited (20+ files):**
- controller.py (~4906 lines), routes.py, models.py, constants.py, state_factories.py, learner.py
- ws_endpoint.py (1812 lines), frame_receiver.py
- Protocol.cs, CommandHandler.cs, StreamerForm.cs
- socket_reader.lua, automation.js
- test_warp_mode.py, test_automation_routes.py
- ARCHITECTURE_GUIDE.md, PHASE_PLAN.md


---
## Findings
<!-- ID: findings -->

### Gap Summary Table

| # | Gap | Severity | Category | Files Affected | Phase |
|---|-----|----------|----------|----------------|-------|
| G1 | Python scan pipeline becomes fallback after HeatSeeker | HIGH | Migration | controller.py:500-611 | P4 |
| G2 | No heatseeker.* capabilities in DoHello | CRITICAL | Protocol | CommandHandler.cs:266-384 | P2 |
| G3 | No heatseeker.* routing in ws_endpoint.py | CRITICAL | Protocol | ws_endpoint.py | P4 |
| G4 | No SUB_HEATSEEKER_* constants in Protocol.cs/frame_receiver.py | CRITICAL | Protocol | Protocol.cs, frame_receiver.py | P2 |
| G5 | Frontend hardcoded to Python /scan endpoint | HIGH | Frontend | automation.js:2718-2750 | P4 |
| G6 | Three-layer warp becomes four-layer with precision warp | HIGH | Warp | controller.py:2452-2531, StreamerForm.cs:460-511 | P3 |
| G7 | Lua warp gate orphaned by HeatSeeker precision warp | MEDIUM | Dead Code | socket_reader.lua:1669-1689 | P3 |
| G8 | state_factories.py duplicated constants | LOW | Code Health | state_factories.py:15-18 | N/A |
| G9 | _enrich_candidates tied to Python-only format | HIGH | Integration | controller.py:440-498 | P4 |
| G10 | execute() stores locked_target from Python scan only | HIGH | Integration | controller.py:639-726 | P4 |
| G11 | No capability check gateway in controller | HIGH | Integration | controller.py (missing) | P4 |
| G12 | Tests cover Python warp only | MEDIUM | Testing | test_warp_mode.py | P5 |
| G13 | _advance_frames_bulk vs per-frame advance are different mechanisms | HIGH | Warp | controller.py:2141, StreamerForm.cs:494 | P3 |
| G14 | DoHello capabilities static, not feature-detected | MEDIUM | Protocol | CommandHandler.cs:273-333 | P2 |
| G15 | _pendingAdvanceFrames UpdateAfter gate is dead code | LOW | Dead Code | StreamerForm.cs:60-61, 262-297 | P3 |

### G1: Python Scan Pipeline Becomes Fallback (HIGH)

controller.py:500-611 `scan()` calls `_derive_adaptive_rng_plan()` and `_apply_target_overlay_to_plan_async()` for Python-side scanning. Architecture Guide Section 4.3 specifies capability-based routing to C# HeatSeeker. No `_scan_rng_candidates()` gateway exists yet. Python scan pipeline must be preserved as gated fallback.

### G2: No heatseeker.* Capabilities in DoHello (CRITICAL)

CommandHandler.cs:273-333 `DoHello()` lists emu.*, warp.*, savestate.*, memory.*, protocol.*, telemetry.*, debug.* capabilities. Zero heatseeker.* entries. Python capability checks will never route to HeatSeeker until Phase 2 adds: `heatseeker.scan`, `heatseeker.status`, `heatseeker.cancel`, `heatseeker.warp_to_target`.

### G3: No heatseeker.* Routing in ws_endpoint.py (CRITICAL)

ws_endpoint.py COMMAND_CAPABILITIES dict (29 entries) and _handle_command() elif chain have no heatseeker.* branches. Phase 4 TP 4.1 must add entries, binary payload construction, and C#-to-JSON response parsing.

### G4: No SUB_HEATSEEKER_* Constants (CRITICAL)

Protocol.cs SubCommand bytes 0x01-0x4A allocated. frame_receiver.py mirrors. 0x50+ range available. Phase 2 must add 0x50-0x53 for scan/status/cancel/warp. Clean: no collision risk.

### G5: Frontend Hardcoded to Python /scan (HIGH)

automation.js:2738 POSTs to API_BASE + '/scan'. Response parsed as Python format. Architecture favors transparent routing (Python delegates to C# internally, frontend unchanged). But C# response format differs -- field mapping required (see G9).

### G6: Three-Layer Warp + HeatSeeker = Four Layers (HIGH)

Current: (1) Python controller calculates warp_count, loops _advance_frames_bulk in 10K chunks; (2) C# StreamerForm tight loop 5000 DoFrameAdvance/tick; (3) Lua WARP_MODE skips expensive work. HeatSeeker adds: (4) Per-frame DoFrameAdvance + gRngValue check for zero-overshoot targeting. These serve different purposes and must coexist. Chunked warp = fallback when HeatSeeker absent.

### G7: Lua Warp Gate Orphaned (MEDIUM)

socket_reader.lua:1828-1851 WARP_MODE gate skips event detection during warp. HeatSeeker precision warp does NOT send warp_control to Lua. Lua runs full frame processing during precision warp. Overhead bounded by C# InvisibleEmulation + FrameSkip(9). Architecture Guide does not address this tradeoff.

### G8: state_factories.py Duplicate Constants (LOW)

state_factories.py:15-18 local copies of DEFAULT_RNG_MODE, DEFAULT_CALIBRATION_POLICY, etc. Comment: "defined locally until Task 1.4 wires up imports." Task 1.4 never completed.

### G9: _enrich_candidates Format Mismatch (HIGH)

controller.py:440-498 expects Python field names: delay, pid, nature_id, iv_hp, iv_attack, etc. HeatSeeker CandidateResult: Seed, Delay, Pid, Ivs[6], NatureId, AbilitySlot, GenderValue, IsShiny. Different casing, different IV structure (array vs named fields). **A normalization layer or dual-format enricher is required.** This is the highest-risk gap.

### G10: execute() Field Dependencies (HIGH)

controller.py:639-726 execute() stores locked_target from select(). _run_exact_attempt():1110+ reads target_expected_delay, target_expected_pid from rng_plan. If HeatSeeker candidates use different field names, execution loop gets None values and fails silently. Field normalization is critical for scan-to-execute pipeline.

### G11: No Capability Gateway (HIGH)

Architecture Guide Section 4.3 specifies _scan_rng_candidates() that checks get_capabilities for heatseeker.scan. Method does not exist. scan() goes directly to Python. Phase 4 TP 4.1 must add: gateway method, capability cache, C# routing, Python fallback.

### G12: Tests Cover Python Warp Only (MEDIUM)

test_warp_mode.py verifies Python+C# chunked warp: constants, WS drain, chunked loop, cancel, cleanup. No HeatSeeker tests. Phase 5 must add: command routing, capability detection, candidate normalization, execute integration, precision warp tests.

### G13: Bulk vs Per-Frame Advance (HIGH)

_advance_frames_bulk (SUB_ADVANCE_FRAMES=0x0A): "advance N frames fast." HeatSeeker warp (SUB_HEATSEEKER_WARP=0x53): "advance one frame, check gRngValue, repeat." Different SubCommands, different dispatch. Python must choose correctly based on capability.

### G14: Static Capabilities (MEDIUM)

CommandHandler.cs capabilities are static List. Debug capabilities are conditional via BuildDebugCapabilities(). HeatSeeker capabilities should be conditional on initialization success.

### G15: Dead _pendingAdvanceFrames (LOW)

StreamerForm.cs:60-61 _pendingAdvanceFrames declared. UpdateAfter:262-297 warp gate checks it. StartAdvanceFrames:503 sets it to 0, uses tight loop instead. UpdateAfter gate can never fire.


---
## Technical Analysis
<!-- ID: technical_analysis -->

### Wiring Diagram: Current vs HeatSeeker

**Current Flow (Python Scan + Chunked Warp):**
```
Frontend automation.js
  | POST /scan (JSON)
  v
routes.py -> controller.scan()
  | Python: _derive_adaptive_rng_plan() -> _apply_target_overlay_to_plan_async()
  | -> plan_starter_targets() (rng_oracle)
  v
controller._enrich_candidates() -> cache in _scan_results
  v
Frontend: display -> POST /select -> POST /execute -> _run_loop
  v
_run_exact_attempt -> _wait_for_lua_bot_candidate()
  | If warp_enabled and frames_to_target > threshold:
  |   _send_lua_warp_control("start") -> Lua WARP_MODE=true
  |   _set_warp_mode(True) -> C# SUB_WARP_MODE
  |   _set_ws_warp_state(True) -> ws drain
  |   Loop: _advance_frames_bulk(chunk=10K) -> C# tight loop
  |   Cleanup: stop warp, restore all
  v
Bot acquires starter -> validate -> match
```

**HeatSeeker Flow (C# Scan + Precision Warp):**
```
Frontend automation.js
  | POST /scan (same endpoint)
  v
routes.py -> controller.scan()
  | NEW: _scan_rng_candidates() capability gateway
  |   get_capabilities -> "heatseeker.scan" present?
  |   YES: binary cmd -> ws_endpoint -> frame_receiver
  |     -> C# CommandHandler -> HeatSeeker.StartScan()
  |     -> RngScanner LCRNG math -> CandidateResult[]
  |     -> Binary response -> Python JSON + normalization
  |     -> _enrich_candidates() (updated for dual format)
  |   NO: fallback to existing Python scan
  v
Same cache -> same /select -> same /execute
  v
_wait_for_lua_bot_candidate()
  | NEW: If heatseeker.warp_to_target available:
  |   Binary cmd -> C# HeatSeeker.WarpToTarget()
  |   Per-frame DoFrameAdvance() + gRngValue check
  |   Zero overshoot, exact seed match
  | FALLBACK: existing chunked warp
  v
Bot acquires starter (same from here)
```

### Dead Code Risk Assessment

| Code | Status After HeatSeeker | Action |
|------|------------------------|--------|
| controller.scan() Python scanning | Fallback | Preserve gated |
| _derive_adaptive_rng_plan() | Fallback | Preserve |
| _apply_target_overlay_to_plan() | Fallback | Preserve |
| _advance_frames_bulk() | Fallback | Preserve |
| _send_lua_warp_control() | Likely orphaned | Deprecate post-validation |
| socket_reader.lua warp_control | Likely orphaned | Deprecate post-validation |
| socket_reader.lua WARP_MODE gate | Likely orphaned | Deprecate post-validation |
| StreamerForm._pendingAdvanceFrames | Already dead | Remove |
| StreamerForm.UpdateAfter() warp gate | Already dead | Remove |
| state_factories.py duplicate constants | Technical debt | Fix imports |

### Risk Assessment

- **Highest risk (G9/G10):** CandidateResult field mapping. No spec exists. Silent runtime failures if mismatched.
- **Moderate risk (G6/G13):** Warp coexistence. Clean protocol separation, but Python controller must choose correctly.
- **Low risk (G2/G3/G4):** Protocol gaps are expected pre-implementation. Clean 0x50+ range, no collisions.


---
## Recommendations
<!-- ID: recommendations -->

### Required Before Implementation Begins (Blockers)

These MUST be resolved before Phase 2 code is written:

1. **Define CandidateResult data contract (G9/G10 — HIGHEST RISK)**
   - [ ] Publish a shared schema document specifying exact field names, types, and units for C# `CandidateResult` and Python enrichment input
   - [ ] Decide: normalize in Python (adapter layer) or normalize in C# (serialize to Python-compatible JSON)
   - [ ] Write a `_normalize_heatseeker_candidate()` function spec with field mapping: `Ivs[0]->iv_hp`, `Ivs[1]->iv_attack`, `NatureId->nature_id`, `Pid->pid`, `Delay->delay`, `IsShiny->shiny`, `GenderValue->gender_value`, `AbilitySlot->ability_slot`
   - [ ] Ensure `_enrich_candidates()` (controller.py:440-498) can accept both formats via duck-typing or explicit format flag

2. **Reserve SubCommand byte range for HeatSeeker (G4)**
   - [ ] Allocate 0x50-0x53 in Protocol.cs: `SUB_HEATSEEKER_SCAN=0x50`, `SUB_HEATSEEKER_STATUS=0x51`, `SUB_HEATSEEKER_CANCEL=0x52`, `SUB_HEATSEEKER_WARP=0x53`
   - [ ] Mirror in frame_receiver.py with identical constant names and values
   - [ ] Document the binary payload format for each SubCommand (request and response)

3. **Document Lua warp gate behavior during precision warp (G7)**
   - [ ] Architecture Guide must specify: Does precision warp send `warp_control` to Lua, or does Lua run full frame processing?
   - [ ] If Lua runs full processing: quantify overhead (event detection, state assembly, socket sends per frame)
   - [ ] If Lua gets warp_control: specify when start/stop signals are sent relative to HeatSeeker warp lifecycle

### Phase-Gated Implementation Checklist

**Phase 2 (Command Integration)**
- [ ] Add `heatseeker.scan`, `heatseeker.status`, `heatseeker.cancel`, `heatseeker.warp_to_target` to `DoHello()` capabilities (G2)
- [ ] Make HeatSeeker capabilities conditional on initialization success (G14)
- [ ] Add SUB_HEATSEEKER_* constants to Protocol.cs and frame_receiver.py (G4)

**Phase 3 (Precision Warp)**
- [ ] Implement per-frame `DoFrameAdvance()` + `gRngValue` check loop in C# (G6/G13)
- [ ] Ensure chunked warp (`_advance_frames_bulk`) remains functional as fallback (G6)
- [ ] Remove dead `_pendingAdvanceFrames` field and `UpdateAfter` warp gate (G15)
- [ ] Resolve Lua warp gate coexistence question (G7)

**Phase 4 (Python Integration)**
- [ ] Add `heatseeker.*` entries to `COMMAND_CAPABILITIES` dict in ws_endpoint.py (G3)
- [ ] Add `_handle_command()` elif branches for all 4 HeatSeeker commands (G3)
- [ ] Implement `_scan_rng_candidates()` gateway with capability check (G11)
- [ ] Gate Python scan as fallback behind `heatseeker.scan not in capabilities` (G1)
- [ ] Implement `_normalize_heatseeker_candidate()` for CandidateResult -> Python format (G9)
- [ ] Ensure `execute()` field reads (`target_expected_delay`, `target_expected_pid`) work with normalized candidates (G10)
- [ ] Frontend: transparent routing — `/scan` endpoint unchanged, Python handles C# delegation internally (G5)

**Phase 5 (Testing & E2E)**
- [ ] Add HeatSeeker command routing tests to test_ws_endpoint_commands.py (G12)
- [ ] Add capability detection tests (G12)
- [ ] Add candidate normalization round-trip tests (G9/G10)
- [ ] Add precision warp integration tests (G6/G13)
- [ ] Add scan-to-execute pipeline test with HeatSeeker candidates (G10)

### Long-Term Opportunities

- **Retire Lua warp gate entirely**: Once HeatSeeker precision warp is validated, the Lua WARP_MODE gate (socket_reader.lua:1828-1851) and `_send_lua_warp_control()` can be deprecated. This eliminates a full layer from the warp stack.
- **Unify constants**: Fix state_factories.py duplicated constants (G8) — wire imports from constants.py as originally intended by Task 1.4.
- **Single scan path**: Once HeatSeeker is stable and validated against Python scan results, the Python scan can be removed entirely (not just gated). This simplifies the scan pipeline from two paths to one.
- **Binary response optimization**: Consider returning HeatSeeker candidates as packed binary (not JSON) for lower latency. The existing binary protocol already supports this pattern.


---
## Appendix
<!-- ID: appendix -->

### References

| Document | Location | Relevance |
|----------|----------|-----------|
| ARCHITECTURE_GUIDE.md | `.scribe/docs/dev_plans/heatseeker/ARCHITECTURE_GUIDE.md` | Defines capability-based routing, fallback patterns, HeatSeeker component design |
| PHASE_PLAN.md | `.scribe/docs/dev_plans/heatseeker/PHASE_PLAN.md` | 5-phase implementation plan with task packages and acceptance criteria |
| CHECKLIST.md | `.scribe/docs/dev_plans/heatseeker/CHECKLIST.md` | Implementation checklist tracking per-phase deliverables |
| Protocol.cs | `csharp/RomLabStreamer/Protocol.cs` | Binary protocol SubCommand definitions (0x01-0x4A allocated) |
| CommandHandler.cs | `csharp/RomLabStreamer/CommandHandler.cs` | Command dispatch, DoHello capabilities, handler registration |
| StreamerForm.cs | `csharp/RomLabStreamer/StreamerForm.cs` | Warp state machine, tight loop, InvisibleEmulation |
| controller.py | `src/rom_lab/api/routes/automation/controller.py` | Scan/select/execute pipeline, warp loop, candidate enrichment |
| ws_endpoint.py | `src/rom_lab/streaming/ws_endpoint.py` | WebSocket command routing, COMMAND_CAPABILITIES dict |
| frame_receiver.py | `src/rom_lab/streaming/frame_receiver.py` | Python-side SUB_* constants, binary frame parsing |
| socket_reader.lua | `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` | Lua warp gate, warp_control handler, heartbeat |

### Audit Methodology

- **Files audited**: 20+ across C#, Python, Lua, JavaScript, and test suites
- **Approach**: Structural scan (imports, class/method signatures) followed by targeted line-range reads of integration boundaries
- **Gap identification**: Cross-referenced Architecture Guide section numbers against actual code to find missing implementations, mismatched contracts, and dead code
- **Severity classification**: CRITICAL = blocks entire feature path; HIGH = causes runtime failure without fix; MEDIUM = technical debt or incomplete coverage; LOW = cleanup only
- **Grade calculation**: 78/100 based on: sound architecture (+20), clean protocol separation (+15), working fallback design (+15), missing data contract (-10), undocumented warp coexistence (-7), no capability gateway (-5), dead code not cleaned (-3), test gaps (-5), duplicated constants (-2)

---