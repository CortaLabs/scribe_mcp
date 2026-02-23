---
id: heatseeker-checklist
title: "\u2705 Acceptance Checklist \u2014 heatseeker"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 12:32:30 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — heatseeker
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 05:17:47 UTC

> Acceptance checklist for heatseeker.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [ ] Architecture guide complete with 14 sections including data contract, capability gateway, warp routing, constants duplication (proof: ARCHITECTURE_GUIDE.md)
- [ ] Phase plan current with all 5 phases and 13 task packages, gap-specific requirements in Tasks 1.1, 2.3, 4.3, 4.4 (proof: PHASE_PLAN.md)
- [ ] Checklist mirrors phase plan acceptance criteria with gap IDs for traceability (proof: this document)
- [ ] All research documents referenced in architecture (proof: RESEARCH_STREAMER_INFRASTRUCTURE.md, RESEARCH_BIZHAWK_RNG_API.md, RESEARCH_WARP_MODE.md, RESEARCH_INTEGRATION_GAPS.md)
- [ ] All 15 integration gaps (G1-G15) from RESEARCH_INTEGRATION_GAPS.md addressed in architecture, phase plan, and checklist (proof: gap ID annotations throughout all three documents)

---

## Phase 1: C# RNG Math
<!-- ID: phase_1_checklist -->
### Task 1.1: CandidateResult.cs
- [x] File exists at `csharp/RomLabStreamer/CandidateResult.cs` (proof: file on disk, 129 lines)
- [x] Declared as `public readonly struct CandidateResult` (proof: line 13)
- [x] All 15 fields present: Delay, PreGenSeed, PostGenSeed, Pid, NatureId, NatureName, Hp, Atk, Def, Spe, SpA, SpD, IvSum, IsShiny, IsFemale (proof: lines 16-48)
- [x] `ToJson()` method produces valid JSON with **oracle-compatible format** (proof: lines 92-127):
  - IV keys are long-form: `attack`, `defense`, `speed`, `sp_attack`, `sp_defense` (NOT `atk`, `def`, etc.) [G9]
  - `pid`, `pre_gen_seed`, `post_gen_seed` are raw integers (NOT hex strings) [G10]
  - `nature` is title-case English name via NatureName field [G9]
- [x] `dotnet build` compiles with zero errors, zero warnings (proof: Build succeeded. 0 Warning(s) 0 Error(s))

### Task 1.2: RngScanner.cs
- [x] File exists at `csharp/RomLabStreamer/RngScanner.cs` (proof: file on disk, 161 lines)
- [x] Declared as `public static class RngScanner` (proof: line 13)
- [x] LCRNG constants correct: A=0x41C64E6D, C=0x6073, A_INV=0xEEB9EB65 (proof: lines 16-18, A*A_INV mod 2^32 = 1 verified via Python)
- [x] `NextSeed(0x00000001)` returns `0x41C6AEE0` (proof: Python manual calc 1*A+C=0x41C6AEE0; NOTE: task package vector 0x41C70DB6 was incorrect)
- [x] `PrevSeed(NextSeed(X)) == X` round-trip verified for X in {0x1, 0xDEADBEEF, 0x12345678, 0xFFFFFFFF, 0x0} (proof: Python verification)
- [x] Method1Generate implements correct IV bit extraction: HP=bits[0:4], ATK=bits[5:9], DEF=bits[10:14] from word1; SPE=bits[0:4], SPA=bits[5:9], SPD=bits[10:14] from word2 (proof: lines 89-98, bitmask (val >> shift) & 0x1F)
- [x] ScanForward filters inline (shiny, nature, IV sum) (proof: lines 136-142 call PassesFilter per candidate)
- [x] 25 nature names present in correct order (Hardy through Quirky) (proof: lines 22-28, Python verification of key indices 0=Hardy, 3=Adamant, 10=Timid, 15=Modest, 24=Quirky)
- [x] `dotnet build` compiles with zero errors (proof: `scripts/build-streamer.sh deploy` -- 0 warnings, 0 errors, DLL deployed to ExternalTools)

### Phase 1 Gate
- [ ] Both new .cs files compile cleanly (proof: `dotnet build` output with 0 errors)
- [ ] No existing files modified (proof: `git diff --name-only` shows only new files)
<!-- ID: phase_2_checklist -->

### Task 2.1: Protocol.cs Constants
- [x] 4 SubCommand constants added: HeatSeekerScan=0x50, HeatSeekerWarp=0x51, HeatSeekerMonitor=0x52, HeatSeekerStatus=0x53 (proof: grep shows all 4 at Protocol.cs lines 79-82)
- [x] No byte collisions with existing constants (proof: grep '0x5[0-9a-fA-F]' returns only the 4 new constants, existing range 0x01-0x4A untouched)
- [x] `dotnet build` succeeds (proof: Build succeeded, 0 errors, 8 warnings all from HeatSeeker.cs stubs not Protocol.cs)

### Task 2.2: HeatSeeker.cs
- [ ] File exists at `csharp/RomLabStreamer/HeatSeeker.cs` (proof: file on disk)
- [ ] Constructor accepts ApiContainer, Action&lt;CommandMessage&gt;, Action&lt;bool&gt; (proof: code review)
- [ ] Initialize() calls ReadTidSid() (proof: code review)
- [ ] ReadTidSid() dereferences gSaveBlock2Ptr (0x0300500C) then reads TID at ptr+0x00A, SID at ptr+0x00C (proof: code review)
- [ ] Scan() reads gRngValue from 0x03005000 and calls RngScanner.ScanForward (proof: code review)
- [ ] Scan() returns JSON with seed, tid, sid, horizon, candidates array, count (proof: code review)
- [ ] GetStatus() returns JSON with state, current_seed, tid, sid, warp/monitor status (proof: code review)
- [ ] `IsInitialized` public property exists and returns `_tidSidValid` [G14] (proof: code review)
- [ ] Warp methods are stubs (StartWarpToSeed throws NotImplementedException) (proof: code review)
- [ ] Monitor methods are no-op stubs (proof: code review)
- [ ] `dotnet build` succeeds (proof: build output)

### Task 2.3: CommandHandler.cs Integration
- [ ] HeatSeeker parameter added to CommandHandler constructor (proof: code diff)
- [ ] HeatSeekerWarp handled as async before switch (returns null) (proof: code review)
### Task 2.2: HeatSeeker.cs
- [x] File exists at `csharp/RomLabStreamer/HeatSeeker.cs` (proof: 298 lines on disk)
- [x] Constructor accepts ApiContainer, Action&lt;CommandMessage&gt;, Action&lt;bool&gt; (proof: lines 86-90, stores as private readonly fields)
- [x] Initialize() calls ReadTidSid() (proof: line 120, also resets warp/monitor state)
- [x] ReadTidSid() dereferences gSaveBlock2Ptr (0x0300500C) then reads TID at ptr+0x00A, SID at ptr+0x00C (proof: lines 129-137)
- [x] Scan() reads gRngValue from 0x03005000 and calls RngScanner.ScanForward (proof: lines 161, 174)
- [x] Scan() returns JSON with seed, tid, sid, horizon, candidates array, count (proof: lines 180-195 StringBuilder)
- [x] GetStatus() returns JSON with state, current_seed, tid, sid, warp/monitor status (proof: lines 216-241)
- [x] `IsInitialized` public property exists and returns `_tidSidValid` [G14] (proof: line 46)
- [x] Warp methods are stubs (StartWarpToSeed throws NotImplementedException) (proof: line 260)
- [x] Monitor methods are no-op stubs (proof: lines 274-285, empty bodies)
- [x] `dotnet build` succeeds (proof: 0 errors, 0 warnings)

### Task 2.3: CommandHandler.cs Integration
- [ ] HeatSeeker parameter added to CommandHandler constructor (proof: code diff)
- [ ] HeatSeekerWarp handled as async before switch (returns null) (proof: code review)
- [ ] 3 sync cases added to switch: Scan, Status, Monitor (proof: code review)
- [ ] 4 Do*() methods implemented with JSON parsing (proof: code review)
- [ ] DoHello() capabilities **conditionally** include heatseeker.* strings gated on `_heatSeeker.IsInitialized` [G14/G2] (proof: code review showing `if` guard)
- [ ] DoHello() **omits** heatseeker.* capabilities when IsInitialized is false [G14] (proof: test with unloaded save)
- [ ] DoHeatSeekerScan returns oracle-compatible JSON per data contract [G9/G10] (proof: response inspection)
- [ ] `dotnet build` succeeds (proof: build output)

### Task 2.4: StreamerForm.cs Integration
- [ ] `_heatSeeker` field added (proof: code diff)
- [ ] HeatSeeker created in Restart() with correct delegate arguments (proof: code review)
- [ ] HeatSeeker passed to CommandHandler constructor (proof: code review)
- [ ] OnCommandTimerTick has HeatSeeker warp check before existing tight loop (proof: code review)
- [ ] UpdateAfter calls `_heatSeeker?.TickMonitor()` (proof: code review)
- [ ] `dotnet build` succeeds (proof: build output)
- [ ] StartWarpToSeed no longer throws NotImplementedException (proof: code review)
- [ ] StartWarpToSeed calls _setWarpModeActive(true) (proof: code review)
- [ ] TickWarp executes DoFrameAdvance in batches (proof: code review)
- [ ] Seed comparison after each batch via ReadU32(0x03005000) (proof: code review)
- [ ] Warp exits on seed match with "complete" status (proof: code review)
- [ ] Warp exits on max_frames with "max_frames_exceeded" status (proof: code review)
- [ ] Warp exits on cancel with "cancelled" status (proof: code review)
- [ ] Progress messages sent every 10000 frames (proof: code review)
- [ ] All async responses include request ID for correlation (proof: code review)

### Phase 3 Gate
- [ ] `dotnet build` succeeds (proof: build output)
- [ ] `scripts/build-streamer.sh` builds successfully (proof: build script output)
- [ ] Warp enters and exits warp mode correctly (proof: manual BizHawk test)
- [ ] Warp reaches target seed (proof: `heatseeker.status` shows matching seed after warp)
- [ ] `dotnet build` succeeds (proof: build output)

### Phase 2 Gate
- [ ] `scripts/build-streamer.sh` builds and deploys DLL (proof: build script output)
- [ ] BizHawk loads External Tool without crash (proof: manual test)
- [ ] `get_capabilities` includes heatseeker.* **only after save is loaded** (IsInitialized=true) [G14] (proof: WebSocket response comparison before/after save load)
- [ ] `get_capabilities` **omits** heatseeker.* before save is loaded [G14] (proof: WebSocket response before save)
- [ ] `heatseeker.scan` returns JSON with candidates using oracle-compatible keys [G9/G10] (proof: WebSocket response)
- [ ] `heatseeker.status` returns current state (proof: WebSocket response)
- [ ] **Data contract:** Scan response IV keys are `attack`/`defense`/`speed`/`sp_attack`/`sp_defense`, PID and seeds are integers [G9/G10] (proof: JSON response inspection)

---

## Phase 3: Precision Warp
<!-- ID: phase_3_checklist -->

### Task 3.1: Warp Implementation
- [ ] StartWarpToSeed no longer throws NotImplementedException (proof: code review)

## Phase 4: Python Integration
<!-- ID: phase_4_checklist -->

### Task 4.1: frame_receiver.py Constants
- [ ] SUB_HEATSEEKER_SCAN = 0x50 (proof: import check)
- [ ] SUB_HEATSEEKER_WARP = 0x51 (proof: import check)
- [ ] SUB_HEATSEEKER_MONITOR = 0x52 (proof: import check)
- [ ] SUB_HEATSEEKER_STATUS = 0x53 (proof: import check)

### Task 4.2: ws_endpoint.py Routing
- [ ] All 4 heatseeker.* entries in COMMAND_CAPABILITIES (proof: grep output)
- [ ] _handle_command() has elif branches for all 4 commands (proof: code review)
- [ ] Default parameter values applied: horizon=120000, gender_threshold=127, min_iv_sum=0, max_frames=500000, interval_frames=60 (proof: code review)

### Task 4.3: controller.py -- Capability Gateway + Normalizer + Warp Routing

#### 4.3a: Capability Gateway [G1/G5/G11]
- [ ] `_scan_rng_candidates()` method exists (proof: grep output)
- [ ] Checks cached capabilities for "heatseeker.scan" (proof: code review)
- [ ] Routes to C# HeatSeeker when capability present [G1] (proof: code review)
- [ ] Falls back to Python when HeatSeeker unavailable [G11] (proof: code review)
- [ ] Frontend `/scan` button works transparently (no frontend changes needed) [G5] (proof: manual test via automation.js)

#### 4.3b: Candidate Normalizer [G9/G10]
- [ ] `_normalize_heatseeker_candidate()` method exists (proof: grep output)
- [ ] Renames `delay` -> `delay_frames` (proof: code review)
- [ ] Renames `pre_gen_seed` -> `predicted_seed_start` (proof: code review)
- [ ] Renames `post_gen_seed` -> `predicted_seed_candidate` (proof: code review)
- [ ] Renames `shiny` -> `is_shiny`, `female` -> `is_female` (proof: code review)
- [ ] Adds metadata: `plan_id`, `rank`, `species_id` (proof: code review)
- [ ] IV dict passes through with oracle-format keys (long-form) for `_IV_KEY_MAP` remapping [G9] (proof: code review)
- [ ] PID kept as integer for `_enrich_candidates()` hex formatting [G10] (proof: code review)
- [ ] Normalized output successfully passes through `_enrich_candidates()` without KeyError (proof: test output)

#### 4.3c: Warp Routing Decision Tree [G6/G7/G13]
- [ ] `_route_warp()` method exists (proof: grep output)
- [ ] Priority 1: precision warp via heatseeker.warp_to_seed when capable [G6] (proof: code review)
- [ ] Priority 2: chunked warp via existing warp.* when precision unavailable [G13] (proof: code review)
- [ ] Priority 3: error dict returned when neither available (proof: code review)
- [ ] No warp_control signal sent to Lua during precision warp [G7] (proof: code review)
- [ ] Precision warp note: Lua continues full processing, bounded by InvisibleEmulation+FrameSkip(9) [G7] (proof: architecture doc reference)

#### 4.3d: Dead Code Markers [G15]
- [ ] Python fallback scan code marked with `# TODO(heatseeker): remove once validated` [G15] (proof: grep output)
- [ ] `_IV_KEY_MAP` confirmed NOT dead code -- still needed (proof: code review)

### Task 4.4: test_heatseeker.py [G12]
- [ ] File exists at `tests/test_heatseeker.py` (proof: file on disk)
- [ ] Tests SUB_* constant values match 0x50-0x53 [G4/G8] (proof: test output)
- [ ] Tests COMMAND_CAPABILITIES inclusion [G3] (proof: test output)
- [ ] Tests capability-aware routing [G1/G11] (proof: test output)
- [ ] Tests `_normalize_heatseeker_candidate()` field mappings [G9/G10] (proof: test output)
- [ ] Tests normalized output passes through `_enrich_candidates()` [G10] (proof: test output)
- [ ] Tests `_route_warp()` decision tree: precision > chunked > error [G6/G13] (proof: test output)
- [ ] Tests cover HeatSeeker-specific paths, not just Python warp [G12] (proof: test names include "heatseeker")
- [ ] `pytest tests/test_heatseeker.py -v` passes (proof: pytest output)

### Task 4.5: test_ws_endpoint_commands.py Updates [G12]
- [ ] HeatSeeker command routing tests added [G12] (proof: code diff)
- [ ] Tests cover heatseeker.scan, heatseeker.status, heatseeker.warp_to_seed, heatseeker.monitor commands [G12] (proof: test output)
- [ ] `pytest tests/test_ws_endpoint_commands.py -v -k heatseeker` passes (proof: pytest output)

### Phase 4 Gate
- [ ] All Python tests pass: `pytest tests/test_heatseeker.py tests/test_ws_endpoint_commands.py -v` (proof: pytest output)
- [ ] No regressions in existing tests: `pytest tests/test_ws_endpoint_commands.py -v` (proof: pytest output)
- [ ] **Data contract end-to-end:** C# scan JSON -> Python normalize -> enrich -> CandidateDetail model validates [G9/G10] (proof: integration test output)
- [ ] **Capability gateway:** scan routes to C# when available, Python fallback when not [G1/G11] (proof: test output with mocked capabilities)
- [ ] **Warp routing:** precision warp preferred, chunked warp fallback [G6/G13] (proof: test output)
- [ ] **Frontend transparency:** automation.js /scan button unchanged, works via capability gateway [G5] (proof: manual test or no-change verification)

---

## Phase 5: Seed Monitor + End-to-End Validation
<!-- ID: phase_5_checklist -->

### Task 5.1: Monitor Implementation
- [ ] SetMonitor toggles _monitorActive (proof: code review)
- [ ] TickMonitor reads seed at configured interval (proof: code review)
- [ ] Only reports when seed changes (deduplication) (proof: code review)
- [ ] `dotnet build` succeeds (proof: build output)

### Task 5.2: End-to-End Validation
- [ ] get_capabilities returns heatseeker.* capabilities (proof: WebSocket test)
- [ ] heatseeker.scan returns valid candidates (proof: WebSocket test)
- [ ] heatseeker.warp_to_seed reaches target seed (proof: WebSocket test + status check)
- [ ] heatseeker.monitor reports seed changes (proof: WebSocket test)
- [ ] heatseeker.status reports accurate state (proof: WebSocket test)
- [ ] C# scan results match Python rng_oracle.py for same seed (proof: cross-validation output)
- [ ] No crashes or memory leaks after extended warp (proof: BizHawk stability test)
<!-- ID: phase_0 -->
## Cross-Cutting Requirements

### Build & Test
- [ ] All C# code compiles with zero errors AND zero warnings (proof: `dotnet build` output)
- [ ] All Python tests pass with zero failures (proof: `pytest` output)
- [ ] No existing tests broken by HeatSeeker changes (proof: full test suite run)

### Constants Synchronization [G4/G8]
- [ ] SubCommand bytes (0x50-0x53) match between Protocol.cs and frame_receiver.py (proof: grep both files)
- [ ] Capability strings match between DoHello(), COMMAND_CAPABILITIES, and ws_endpoint routing (proof: grep all three)
- [ ] No byte collisions between HeatSeeker constants (0x50-0x53) and existing ranges (0x01-0x4A) (proof: grep Protocol.cs)

### Data Contract Compliance [G9/G10]
- [ ] C# CandidateResult.ToJson() outputs oracle-compatible IV keys: `attack`, `defense`, `speed`, `sp_attack`, `sp_defense` (proof: C# code review)
- [ ] C# outputs PID and seed fields as raw integers, NOT hex strings (proof: C# code review)
- [ ] Python `_normalize_heatseeker_candidate()` correctly maps C# field names to pipeline expectations (proof: Python test output)
- [ ] Normalized candidates pass through `_enrich_candidates()` and produce valid `CandidateDetail` Pydantic models (proof: test output)
- [ ] JSON response formats consistent between C# output and Python parsing expectations (proof: integration test)

### Capability Gateway [G1/G2/G5/G11/G14]
- [ ] DoHello() advertises heatseeker.* capabilities ONLY when IsInitialized is true [G14] (proof: before/after save load test)
- [ ] Python _scan_rng_candidates() checks capabilities before routing [G1] (proof: code review)
- [ ] Python falls back gracefully when HeatSeeker not available [G11] (proof: test with mock capabilities)
- [ ] Frontend automation.js requires zero changes for HeatSeeker integration [G5] (proof: no-change diff)

### Warp Mode Coexistence [G6/G7/G13]
- [ ] Precision warp (HeatSeeker) and chunked warp coexist without conflict [G6] (proof: code review of _route_warp)
- [ ] No warp_control signal sent to Lua during HeatSeeker precision warp [G7] (proof: code review)
- [ ] Warp routing decision tree correctly prioritizes: precision > chunked > error [G13] (proof: test output)
<!-- ID: final_verification -->
## Final Verification
- [ ] All phase gate criteria met (Phases 1-5)
- [ ] All cross-cutting requirements satisfied (constants sync, data contract, capability gateway, warp coexistence)
- [ ] Full `dotnet build` clean (zero errors, zero warnings)
- [ ] Full `pytest` clean (zero failures)
- [ ] `scripts/build-streamer.sh` produces deployable DLL
- [ ] BizHawk loads tool without crash
- [ ] All 4 heatseeker.* commands work end-to-end through WebSocket pipeline
- [ ] Scan results cross-validated against Python rng_oracle.py
- [ ] **Data contract verified end-to-end:** C# ToJson() -> TCP -> Python normalize -> enrich -> CandidateDetail validates [G9/G10]
- [ ] **Capability gateway verified:** conditional capabilities, scan routing, fallback all work [G1/G2/G5/G11/G14]
- [ ] **Warp routing verified:** precision warp, chunked warp fallback, Lua coexistence [G6/G7/G13]
- [ ] All 15 integration gaps (G1-G15) resolved with evidence (proof: gap coverage matrix)
- [ ] ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md all current
- [ ] All checklist items checked with proofs attached
- [ ] Retro notes documented in PHASE_PLAN.md
