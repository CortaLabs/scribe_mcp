---
id: heatseeker-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 heatseeker"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 12:33:24 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — heatseeker
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 05:17:47 UTC

> Execution roadmap for heatseeker.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 1 -- C# RNG Math | Pure LCRNG + Method 1 computation in C# with zero BizHawk deps | `RngScanner.cs`, `CandidateResult.cs`, unit-testable math | 0.95 |
| Phase 2 -- Command Integration | Wire HeatSeeker into CommandHandler + Protocol | `HeatSeeker.cs`, Protocol constants, 4 command dispatch cases, capabilities | 0.90 |
| Phase 3 -- Precision Warp | Frame-perfect seed targeting via warp mode integration | Warp tick in OnCommandTimerTick, seed comparison loop, progress/completion responses | 0.85 |
| Phase 4 -- Python Integration | Python-side routing, capability gateway, candidate normalization, warp routing | frame_receiver constants, ws_endpoint routing, capability gateway, normalizer, warp decision tree, tests | 0.90 |
| Phase 5 -- Seed Monitor + Polish | Per-frame seed reporting, status endpoint, end-to-end validation | Monitor tick in UpdateAfter, heatseeker.status, cross-stack validation | 0.85 |

**Dependency chain:** Phase 1 -> Phase 2 -> Phase 3 (C# stack, sequential). Phase 4 can start after Phase 2. Phase 5 requires Phase 3 + Phase 4.

**Total estimated new code:** ~921 lines new, ~25 lines modified across 11 files.
**Build pipeline:** Unchanged -- `scripts/build-streamer.sh` builds the same .csproj.
<!-- ID: phase_0 -->
## Phase 1 -- C# RNG Math (Pure Computation)

**Objective:** Implement the Gen 3 LCRNG engine and Method 1 generation algorithm as pure C# static methods with zero BizHawk dependencies. This is the mathematical foundation that all other phases build on.

**Dependency:** None (first phase).

---

### Task Package 1.1: CandidateResult.cs -- Data Structure

**Scope:** Create the readonly struct that carries Method 1 generation results.
**Files to Create:** `csharp/RomLabStreamer/CandidateResult.cs`
**Dependencies:** None

**Specifications:**
1. Create `CandidateResult` as a `public readonly struct` in namespace `RomLabStreamer`
2. Fields (all readonly):
   - `int Delay` -- frame offset from base seed
   - `uint PreGenSeed` -- LCRNG seed input to the Method 1 call chain
   - `uint PostGenSeed` -- seed state after 4 LCRNG calls
   - `uint Pid` -- 32-bit Pokemon ID (PID_hi << 16 | PID_lo)
   - `byte NatureId` -- (byte)(Pid % 25)
   - `byte Hp, Atk, Def, Spe, SpA, SpD` -- IVs, each 0-31
   - `int IvSum` -- sum of all 6 IVs
   - `bool IsShiny` -- (TID ^ SID ^ PID_hi ^ PID_lo) < 8
   - `bool IsFemale` -- (Pid & 0xFF) < genderThreshold
3. Constructor takes all values as parameters, assigns to readonly fields
4. Add `public string ToJson()` method that returns a JSON object string using **oracle-compatible keys** (see ARCHITECTURE_GUIDE.md Data Contract section, Gap G9/G10):
   ```json
   {"delay":N,"pid":UINT,"nature":"Name","nature_id":N,"ivs":{"hp":N,"attack":N,"defense":N,"speed":N,"sp_attack":N,"sp_defense":N},"iv_sum":N,"shiny":bool,"female":bool,"pre_gen_seed":UINT,"post_gen_seed":UINT}
   ```
   **CRITICAL data contract rules (G9/G10):**
   - IV keys MUST use long-form names: `hp`, `attack`, `defense`, `speed`, `sp_attack`, `sp_defense` -- these match Python's `_IV_KEY_MAP` source keys in controller.py:125 which remaps them to short-form (hp, atk, def, spe, spa, spd)
   - `pid`, `pre_gen_seed`, `post_gen_seed` MUST be raw unsigned integers (NOT hex strings) -- Python `_enrich_candidates()` at controller.py:451 formats PID to hex via `f"0x{pid:08X}"`
   - `nature` MUST be title-case English name (e.g., "Adamant") matching RngScanner.NatureNames
   - Boolean fields use JSON `true`/`false`
5. Do NOT format uint fields as hex strings in JSON -- output raw integers. Python handles hex formatting in `_enrich_candidates()`.

**Verification:**
- [ ] File compiles with `dotnet build` (zero errors, zero warnings)
- [ ] `ToJson()` produces valid JSON when called with test values
- [ ] **Data contract (G9):** IV keys are long-form (`attack` not `atk`, `sp_attack` not `spa`, etc.)
- [ ] **Data contract (G10):** `pid` and seed fields are raw integers, not hex strings
- [ ] **Data contract (G9):** JSON output parseable by Python's `json.loads()` and compatible with `_IV_KEY_MAP` remapping

**Out of Scope (DO NOT TOUCH):**
- RngScanner.cs (separate task)
- Any existing files

**Estimated lines:** ~80

---

### Task Package 1.2: RngScanner.cs -- LCRNG Engine + Method 1

**Scope:** Create the pure math engine for LCRNG stepping and Method 1 Pokemon generation.
**Files to Create:** `csharp/RomLabStreamer/RngScanner.cs`
**Dependencies:** Task 1.1 (CandidateResult.cs must exist)

**Specifications:**
1. Create `RngScanner` as a `public static class` in namespace `RomLabStreamer`
2. Constants:
   - `public const uint LCRNG_A = 0x41C64E6D;`
   - `public const uint LCRNG_C = 0x00006073;`
   - `public const uint LCRNG_A_INV = 0xEEB9EB65;`
3. Nature table:
   - `public static readonly string[] NatureNames` -- 25 entries (Hardy through Quirky), indexed by `PID % 25`
4. Core methods:
   - `public static uint NextSeed(uint seed)` => `unchecked(seed * LCRNG_A + LCRNG_C)`
   - `public static uint PrevSeed(uint seed)` => `unchecked((seed - LCRNG_C) * LCRNG_A_INV)`
   - `public static uint Advance(uint seed, int steps)` -- loop calling NextSeed
   - `public static uint Reverse(uint seed, int steps)` -- loop calling PrevSeed
5. Method 1 generation:
   - `public static CandidateResult Method1Generate(uint preGenSeed, int delay, uint tid, uint sid, byte genderThreshold)`
   - Algorithm: seed0=preGenSeed, seed1=Next(seed0), seed2=Next(seed1), seed3=Next(seed2), seed4=Next(seed3)
   - PID_lo = (seed1 >> 16) & 0xFFFF, PID_hi = (seed2 >> 16) & 0xFFFF
   - PID = (PID_hi << 16) | PID_lo
   - IV_word1 = (seed3 >> 16) & 0xFFFF: HP=bits[0:4], ATK=bits[5:9], DEF=bits[10:14]
   - IV_word2 = (seed4 >> 16) & 0xFFFF: SPE=bits[0:4], SPA=bits[5:9], SPD=bits[10:14]
   - Shiny check: (tid ^ sid ^ PID_hi ^ PID_lo) < 8
   - Nature: (byte)(PID % 25)
   - Gender: (PID & 0xFF) < genderThreshold
   - PostGenSeed = seed4
6. Scan method:
   - `public static List<CandidateResult> ScanForward(uint baseSeed, int horizon, uint tid, uint sid, byte genderThreshold, byte? targetNature = null, bool shinyOnly = false, int minIvSum = 0)`
   - Iterates `horizon` frames, calls Method1Generate per frame, filters inline
7. Filter method (private):
   - `private static bool PassesFilter(CandidateResult c, byte? targetNature, bool shinyOnly, int minIvSum)`
   - Returns false if shinyOnly and not shiny, if targetNature set and mismatch, if IvSum < minIvSum

**Verification:**
- [x] `dotnet build` compiles with zero errors (0 warnings, 0 errors via `scripts/build-streamer.sh deploy`)
- [x] Known test vector: seed=0x00000001, Next => 0x41C6AEE0 (verified; original vector 0x41C70DB6 was incorrect)
- [x] Known test vector: PrevSeed(NextSeed(X)) == X for any X (round-trip verified for 5 test values)
- [ ] ScanForward with horizon=10 returns correct count for a known seed (deferred to integration test)

**Out of Scope (DO NOT TOUCH):**
- HeatSeeker.cs (Phase 2)
- CommandHandler.cs (Phase 2)
- Any existing .cs files

**Estimated lines:** ~180

---

**Phase 1 Acceptance Criteria:**
- [ ] Both new .cs files compile cleanly via `dotnet build` in `csharp/RomLabStreamer/`
- [ ] No existing files modified
- [ ] LCRNG forward/reverse round-trip verified
- [ ] Method 1 generation matches known Pokemon RNG reference values
<!-- ID: phase_1 -->
## Phase 2 -- Command Integration (HeatSeeker + Protocol + CommandHandler)

**Objective:** Create the HeatSeeker orchestrator class and wire it into the existing command dispatch pipeline. After this phase, `heatseeker.scan` and `heatseeker.status` commands work end-to-end within C#.

**Dependency:** Phase 1 complete (RngScanner.cs and CandidateResult.cs exist and compile).

---

### Task Package 2.1: Protocol.cs -- SubCommand Constants

**Scope:** Add 4 HeatSeeker SubCommand byte constants to Protocol.cs.
**Files to Modify:** `csharp/RomLabStreamer/Protocol.cs`
**Dependencies:** None (can start immediately once Phase 1 compiles)

**Specifications:**
1. Add to the `SubCommand` class (after existing constants, before the closing brace):
   ```csharp
   // HeatSeeker commands (0x50-0x5F reserved)
   public const byte HeatSeekerScan    = 0x50;
   public const byte HeatSeekerWarp    = 0x51;
   public const byte HeatSeekerMonitor = 0x52;
   public const byte HeatSeekerStatus  = 0x53;
   ```
2. Verify no byte collision with existing constants (existing range is 0x01-0x4A, Response=0x30)

**Verification:**
- [x] `dotnet build` compiles with zero errors (proof: Build succeeded, 0 errors)
- [x] `grep -c "0x50\|0x51\|0x52\|0x53" csharp/RomLabStreamer/Protocol.cs` returns 4 (proof: grep confirms all 4 at lines 79-82)

**Out of Scope (DO NOT TOUCH):**
- CommandHandler.cs (separate task)
- MessageType, CommandStatus, or other Protocol classes

**Estimated lines:** 6 added

---

### Task Package 2.2: HeatSeeker.cs -- Orchestrator Class

**Scope:** Create the HeatSeeker orchestrator that owns state, reads memory, and delegates math to RngScanner.
**Files to Create:** `csharp/RomLabStreamer/HeatSeeker.cs`
**Dependencies:** Task 1.1, Task 1.2, Task 2.1

**Specifications:**
1. Create `HeatSeeker` as `public class` in namespace `RomLabStreamer`
2. Constructor: `public HeatSeeker(ApiContainer apis, Action<CommandMessage> sendResponse, Action<bool> setWarpModeActive)`
   - Store all three as private readonly fields
3. Constants:
   - `private const long GRngValueAddr = 0x03005000;`
   - `private const long GSaveBlock2PtrAddr = 0x0300500C;`
   - `private const string MemDomain = "System Bus";`
4. TID/SID cache:
   - `private uint _tid, _sid; private bool _tidSidValid;`
   - `public void Initialize()` -- calls ReadTidSid(), resets warp/monitor state
   - `private void ReadTidSid()` -- dereference gSaveBlock2Ptr, read TID at ptr+0x00A (u16), SID at ptr+0x00C (u16)
   - If ptr is 0, set `_tidSidValid = false` and return (save block not loaded yet)
5. Scan method:
   - `public string Scan(int horizon, byte genderThreshold, byte? targetNature, bool shinyOnly, int minIvSum)`
   - Read current seed: `uint seed = _apis.Memory.ReadU32(GRngValueAddr, MemDomain);`
   - If !_tidSidValid, call ReadTidSid() once more (lazy init)
   - Call `RngScanner.ScanForward(seed, horizon, _tid, _sid, genderThreshold, targetNature, shinyOnly, minIvSum)`
   - Build JSON response: `{"seed":"0xHEX","tid":N,"sid":N,"horizon":N,"candidates":[...candidate.ToJson()...],"count":N}`
   - Cache `_lastScanSeed` and `_lastScanCandidateCount`
   - Return the JSON string
6. Status method:
   - `public string GetStatus()`
   - Read current seed from memory
   - Return JSON: `{"state":"idle|scanning|warping|monitoring","current_seed":"0xHEX","tid":N,"sid":N,"tid_sid_valid":bool,"warp_active":bool,"monitor_active":bool,"last_scan_seed":"0xHEX","last_scan_candidates":N}`
7. Warp fields (declare but leave method bodies as stubs for Phase 3):
   - `private bool _warpActive; private uint _warpTargetSeed; private int _warpMaxFrames, _warpFramesAdvanced; private ushort _warpRequestId; private bool _warpCancelled;`
   - `public bool IsWarpActive => _warpActive;`
   - `public void StartWarpToSeed(uint targetSeed, int maxFrames, ushort requestId)` -- stub, throws NotImplementedException with message "Phase 3"
   - `public bool TickWarp(int batchSize)` -- stub, returns false
   - `public void CancelWarp()` -- `_warpCancelled = true;`
8. Monitor fields (declare but leave method bodies as stubs for Phase 5):
   - `private bool _monitorActive; private int _monitorIntervalFrames; private uint _monitorLastSeed; private int _monitorFrameCounter;`
   - `public void SetMonitor(bool enable, int intervalFrames)` -- stub
   - `public void TickMonitor()` -- stub (empty body, no-op)

**Verification:**
- [ ] `dotnet build` compiles with zero errors
- [ ] Scan() method reads gRngValue address (0x03005000)
- [ ] TID/SID pointer dereference chain verified: ReadU32(0x0300500C) -> ReadU16(ptr+0x00A), ReadU16(ptr+0x00C)
- [ ] GetStatus() returns valid JSON structure

**Out of Scope (DO NOT TOUCH):**
- Warp implementation (Phase 3)
- Monitor implementation (Phase 5)
- CommandHandler.cs (separate task)
- StreamerForm.cs (separate task)

**Estimated lines:** ~250

---

**Verification:**
- [x] `dotnet build` compiles with zero errors (proof: 0 errors, 0 warnings)
- [x] Scan() method reads gRngValue address (0x03005000) (proof: HeatSeeker.cs line 161)
- [x] TID/SID pointer dereference chain verified: ReadU32(0x0300500C) -> ReadU16(ptr+0x00A), ReadU16(ptr+0x00C) (proof: HeatSeeker.cs lines 129-137)
- [x] GetStatus() returns valid JSON structure (proof: HeatSeeker.cs lines 216-241, StringBuilder JSON)

**Specifications:**
1. Constructor modification:
   - Accept `HeatSeeker heatSeeker` as a new parameter (add after existing params)
   - Store as `private readonly HeatSeeker _heatSeeker;`
2. HandleCommand() -- add async handler BEFORE the switch expression (same pattern as AdvanceFrames):
   ```csharp
   if (cmd.SubCommand == SubCommand.HeatSeekerWarp)
   {
       return DoHeatSeekerWarp(cmd);  // returns null (async)
   }
   ```
3. HandleCommand() -- add 3 sync cases to the switch expression:
   ```csharp
   SubCommand.HeatSeekerScan    => DoHeatSeekerScan(cmd),
   SubCommand.HeatSeekerStatus  => DoHeatSeekerStatus(cmd),
   SubCommand.HeatSeekerMonitor => DoHeatSeekerMonitor(cmd),
   ```
4. Implement 4 Do*() methods:
   - `DoHeatSeekerScan(cmd)`: Parse JSON payload for {horizon, gender_threshold, target_nature, shiny_only, min_iv_sum}. Call `_heatSeeker.Scan(...)`. Return success response with result JSON as payload.
   - `DoHeatSeekerStatus(cmd)`: Call `_heatSeeker.GetStatus()`. Return success with JSON.
   - `DoHeatSeekerMonitor(cmd)`: Parse JSON for {enable, interval_frames}. Call `_heatSeeker.SetMonitor(...)`. Return success.
   - `DoHeatSeekerWarp(cmd)`: Parse JSON for {target_seed, max_frames}. Call `_heatSeeker.StartWarpToSeed(...)`. Return null (async pattern).
5. DoHello() -- add 4 capabilities **conditionally gated on HeatSeeker initialization** (Gap G14, G2):
   ```csharp
   // HeatSeeker capabilities -- only advertise when initialized
   // (mirrors the existing pattern for debug.* capabilities which are
   // conditional on debugger availability -- see CommandHandler.cs:266-340)
   if (_heatSeeker != null && _heatSeeker.IsInitialized)
   {
       capabilities.Add("heatseeker.scan");
       capabilities.Add("heatseeker.warp_to_seed");
       capabilities.Add("heatseeker.monitor");
       capabilities.Add("heatseeker.status");
   }
   ```
   **Rationale (G14):** HeatSeeker requires TID/SID from save block. Before a save is loaded, gSaveBlock2Ptr is null. Advertising capabilities before initialization would cause Python to route scans to C# that will fail. Conditional capabilities tell Python "use fallback" until HeatSeeker is ready.
6. Add `public bool IsInitialized` property to HeatSeeker.cs (Task 2.2 addendum):
   - Returns `_tidSidValid` -- true once ReadTidSid() succeeds
   - CommandHandler reads this in DoHello() for capability gating
7. JSON parsing: Use the same System.Text.Json approach as existing Do*() methods. Parse payload bytes as UTF-8 string, then JsonDocument.Parse().
8. **Data contract compliance (G9/G10):** DoHeatSeekerScan returns CandidateResult.ToJson() output directly. The JSON format uses oracle-compatible keys per Task 1.1 specification. No transformation needed in CommandHandler -- the data contract is enforced at the CandidateResult level.

**Verification:**
- [ ] `dotnet build` compiles with zero errors
- [ ] DoHello() capabilities list includes all 4 heatseeker.* strings **when IsInitialized is true**
- [ ] DoHello() capabilities list **omits** heatseeker.* strings when IsInitialized is false (G14)
- [ ] HandleCommand switch has 3 new sync cases + 1 async pre-switch case
- [ ] DoHeatSeekerScan parses JSON and calls HeatSeeker.Scan()
- [ ] **Data contract (G9/G10):** Scan response JSON uses oracle-compatible keys (long-form IVs, integer seeds/PIDs)

**Out of Scope (DO NOT TOUCH):**
- Existing command handlers
- StreamerForm.cs
- TcpBridge.cs, FrameCapture.cs

**Estimated lines:** ~130 added, ~10 modified

---

### Task Package 2.4: StreamerForm.cs -- HeatSeeker Construction

**Scope:** Create HeatSeeker instance in StreamerForm and pass it to CommandHandler. Add stub hooks for warp/monitor ticks (actual implementation in Phase 3/5).
**Files to Modify:** `csharp/RomLabStreamer/StreamerForm.cs`
**Dependencies:** Task 2.2 (HeatSeeker class), Task 2.3 (CommandHandler accepts HeatSeeker)

**Specifications:**
1. Add private field: `private HeatSeeker _heatSeeker;`
2. In `Restart()` method, after CommandHandler creation:
   ```csharp
   _heatSeeker = new HeatSeeker(APIs, _bridge.SendResponse, SetWarpModeActive);
   _heatSeeker.Initialize();
   ```
3. Pass `_heatSeeker` to the CommandHandler constructor (add as new argument)
4. In `OnCommandTimerTick()`, add before the existing tight loop:
   ```csharp
   // HeatSeeker warp tick (Phase 3 will implement TickWarp body)
   if (_heatSeeker != null && _heatSeeker.IsWarpActive)
   {
       bool complete = _heatSeeker.TickWarp(TightLoopBatchSize);
       if (complete) { /* warp finished */ }
       return;
   }
   ```
5. In `UpdateAfter()`, add at the end:
   ```csharp
   _heatSeeker?.TickMonitor();
   ```
6. Verify SetWarpModeActive delegate exists (it should from warp mode implementation)

**Verification:**
- [ ] `dotnet build` compiles with zero errors
- [ ] HeatSeeker initialized in Restart()
- [ ] OnCommandTimerTick has HeatSeeker warp check before existing tight loop
- [ ] UpdateAfter calls TickMonitor

**Out of Scope (DO NOT TOUCH):**
- Warp mode entry/exit logic (Phase 3)
- Tight loop batch mechanics
- Frame capture, audio capture, TCP bridge

**Estimated lines:** ~30 added, ~5 modified

---

**Phase 2 Acceptance Criteria:**
- [ ] Full `dotnet build` succeeds with zero errors
- [ ] `scripts/build-streamer.sh` builds and deploys DLL to `~/.romlab/bizhawk/ExternalTools/`
- [ ] BizHawk loads the External Tool without crash
- [ ] `get_capabilities` response includes all 4 heatseeker.* strings **only after save is loaded** (G14: conditional on IsInitialized)
- [ ] `get_capabilities` response **omits** heatseeker.* strings before save is loaded (G14)
- [ ] `heatseeker.scan` command returns JSON with candidates array
- [ ] `heatseeker.status` command returns current state JSON
- [ ] **Data contract (G9/G10):** Scan response JSON IV keys are oracle-format (`attack`, `defense`, `speed`, `sp_attack`, `sp_defense`), PID and seeds are integers
<!-- ID: milestone_tracking -->
## Phase 3 -- Precision Warp (Frame-Perfect Seed Targeting)

**Objective:** Implement the warp-to-seed mechanism: enter warp mode, advance frames at maximum speed, compare gRngValue each batch, stop precisely when target seed is reached. This is the performance-critical phase.

**Dependency:** Phase 2 complete (HeatSeeker.cs exists with warp stubs, StreamerForm has tick hooks).

---

### Task Package 3.1: HeatSeeker.cs -- Warp Implementation

**Scope:** Replace the warp stub methods in HeatSeeker.cs with full frame-advance + seed-compare logic.
**Files to Modify:** `csharp/RomLabStreamer/HeatSeeker.cs`
**Dependencies:** Phase 2 complete

**Specifications:**
1. `StartWarpToSeed(uint targetSeed, int maxFrames, ushort requestId)`:
   - Store parameters in warp state fields
   - Set `_warpActive = true`, `_warpCancelled = false`, `_warpFramesAdvanced = 0`
   - Call `_setWarpModeActive(true)` -- this activates existing warp bypass (sound off, invisible, rewind off, speed max)
   - Send initial progress response: `{"status":"started","target_seed":"0xHEX","max_frames":N}`
2. `TickWarp(int batchSize)` -- called from OnCommandTimerTick:
   - Execute tight loop: `for (int i = 0; i < batchSize && _warpFramesAdvanced < _warpMaxFrames; i++)`
   - Each iteration: `_apis.EmuClient.DoFrameAdvance(); _warpFramesAdvanced++;`
   - After batch, read current seed: `uint currentSeed = _apis.Memory.ReadU32(GRngValueAddr, MemDomain);`
   - **Seed match check:** If `currentSeed == _warpTargetSeed`:
     - Call `_setWarpModeActive(false)` -- exit warp bypass
     - Send completion response via `_sendResponse`: `{"status":"complete","target_seed":"0xHEX","current_seed":"0xHEX","frames_advanced":N}`
     - Set `_warpActive = false`
     - Return true (complete)
   - **Max frames check:** If `_warpFramesAdvanced >= _warpMaxFrames`:
     - Exit warp mode, send failure response: `{"status":"max_frames_exceeded","current_seed":"0xHEX","frames_advanced":N}`
     - Return true (complete, but failed)
   - **Cancel check:** If `_warpCancelled`:
     - Exit warp mode, send cancelled response: `{"status":"cancelled","current_seed":"0xHEX","frames_advanced":N}`
     - Return true (complete)
   - **Progress reporting:** Every 10000 frames (configurable), send progress: `{"status":"progress","current_seed":"0xHEX","frames_advanced":N,"frames_remaining":N}`
   - Return false (still running)
3. Response format: All warp responses use the async pattern -- `_sendResponse(Protocol.MakeResponse(cmd, CommandStatus.Success, payloadBytes))`
4. The request ID (`_warpRequestId`) must be included in all async responses so Python can correlate them

**Verification:**
- [ ] `dotnet build` compiles with zero errors
- [ ] StartWarpToSeed activates warp mode via delegate
- [ ] TickWarp advances frames in batches and checks seed after each batch
- [ ] Warp exits cleanly on seed match, max frames, or cancel
- [ ] Progress responses sent at regular intervals

**Out of Scope (DO NOT TOUCH):**
- SetWarpModeActive implementation (existing)
- Existing tight loop / AdvanceFrames handler
- Python-side warp routing (Phase 4)

**Estimated lines:** ~80 modified (replacing stubs)

---

**Phase 3 Acceptance Criteria:**
- [ ] `dotnet build` succeeds
- [ ] `scripts/build-streamer.sh` builds successfully
- [ ] `heatseeker.warp_to_seed` command accepted by C# (no NotImplementedException)
- [ ] Warp enters warp mode (sound off, max speed)
- [ ] Warp stops when target seed is reached (verified by reading gRngValue after stop)
- [ ] Warp respects max_frames limit
- [ ] Progress messages sent during warp
- [ ] Warp exits cleanly and restores normal emulation state

---

## Phase 4 -- Python Integration (WebSocket Routing + Controller)

**Objective:** Add Python-side support for all 4 HeatSeeker commands: constants in frame_receiver, routing in ws_endpoint, capability-aware scan in controller, and automated tests.

**Dependency:** Phase 2 complete (C# commands work). Can run in parallel with Phase 3.

---

### Task Package 4.1: frame_receiver.py -- SubCommand Constants

**Scope:** Add 4 HeatSeeker SubCommand byte constants to frame_receiver.py.
**Files to Modify:** `src/rom_lab/streaming/frame_receiver.py`
**Dependencies:** Phase 2 complete (Protocol.cs has the byte values)

**Specifications:**
1. Add after existing SUB_* constants (e.g., after SUB_ADVANCE_FRAMES):
   ```python
   # HeatSeeker commands (0x50-0x5F reserved)
   SUB_HEATSEEKER_SCAN: int = 0x50
   SUB_HEATSEEKER_WARP: int = 0x51
   SUB_HEATSEEKER_MONITOR: int = 0x52
   SUB_HEATSEEKER_STATUS: int = 0x53
   ```
2. Values MUST match Protocol.cs exactly (0x50, 0x51, 0x52, 0x53)

**Verification:**
- [ ] `python -c "from rom_lab.streaming.frame_receiver import SUB_HEATSEEKER_SCAN; print(SUB_HEATSEEKER_SCAN)"` prints 80
- [ ] All 4 constants importable

**Out of Scope (DO NOT TOUCH):**
- Existing SUB_* constants
- send_command() or other frame_receiver methods

**Estimated lines:** 5 added

---

### Task Package 4.2: ws_endpoint.py -- Capability Routing

**Scope:** Add HeatSeeker command routing to the WebSocket endpoint.
**Files to Modify:** `src/rom_lab/streaming/ws_endpoint.py`
**Dependencies:** Task 4.1

**Specifications:**
1. Add to COMMAND_CAPABILITIES dict:
   ```python
   "heatseeker.scan": "heatseeker.scan",
   "heatseeker.warp_to_seed": "heatseeker.warp_to_seed",
   "heatseeker.monitor": "heatseeker.monitor",
   "heatseeker.status": "heatseeker.status",
   ```
2. Add elif branches in `_handle_command()` for each command:
   - `heatseeker.scan`: Encode JSON payload `{"horizon": N, "gender_threshold": N, "target_nature": N|null, "shiny_only": bool, "min_iv_sum": N}`, send via `SUB_HEATSEEKER_SCAN`
   - `heatseeker.warp_to_seed`: Encode `{"target_seed": "0xHEX", "max_frames": N}`, send via `SUB_HEATSEEKER_WARP`
   - `heatseeker.monitor`: Encode `{"enable": bool, "interval_frames": N}`, send via `SUB_HEATSEEKER_MONITOR`
   - `heatseeker.status`: No payload needed, send via `SUB_HEATSEEKER_STATUS`
3. Parse the target_seed string "0xHEX" to integer for the JSON payload
4. Default values: horizon=120000, gender_threshold=127, min_iv_sum=0, max_frames=500000, interval_frames=60

**Verification:**
- [ ] `heatseeker.scan` appears in COMMAND_CAPABILITIES
- [ ] Each command routes to correct SUB_* constant
- [ ] Default parameter values applied when not specified

**Out of Scope (DO NOT TOUCH):**
- Existing command handlers
- WebSocket connection logic
- Frame capture/streaming

**Estimated lines:** ~30 added

---

### Task Package 4.3: controller.py -- Capability Gateway + Candidate Normalization + Warp Routing

**Scope:** Add the capability gateway method, candidate normalizer, and warp routing decision tree to the automation controller. This is the Python-side integration hub that bridges C# HeatSeeker results into the existing automation pipeline.
**Files to Modify:** `src/rom_lab/api/routes/automation/controller.py`
**Dependencies:** Task 4.1, Task 4.2

**Specifications:**

#### 4.3a: Capability Gateway -- _scan_rng_candidates() (G1, G5, G11)

1. Add method `async def _scan_rng_candidates(self, horizon: int, gender_threshold: int = 127, target_nature: int | None = None, shiny_only: bool = False, min_iv_sum: int = 0) -> dict`:
   - Check cached capabilities from HELLO handshake (stored in `self._frame_receiver._capabilities` or equivalent)
   - If `"heatseeker.scan"` in capabilities:
     - Build JSON payload: `{"horizon": horizon, "gender_threshold": gender_threshold, "target_nature": target_nature, "shiny_only": shiny_only, "min_iv_sum": min_iv_sum}`
     - Send via `self._frame_receiver.send_command(SUB_HEATSEEKER_SCAN, payload)`
     - Parse response JSON
     - Normalize each candidate via `_normalize_heatseeker_candidate()` (see 4.3b below)
     - Feed normalized candidates into existing `_enrich_candidates()` pipeline (controller.py:451)
     - Return enriched result dict
   - Else (Python fallback):
     - Log warning "HeatSeeker not available, using Python scan fallback"
     - Call existing Python RNG scan if available, or return error dict
2. This method is the **single entry point** -- callers (scan(), existing routes, frontend) never need to know which backend is used
3. The existing `scan()` method at controller.py:~line 400 should call `_scan_rng_candidates()` instead of directly invoking the Python oracle when HeatSeeker is available

#### 4.3b: Candidate Normalizer -- _normalize_heatseeker_candidate() (G9, G10)

4. Add private method `def _normalize_heatseeker_candidate(self, raw: dict, plan_id: str, rank: int) -> dict`:
   - **Purpose:** Transform C# CandidateResult.ToJson() output into the format expected by `_enrich_candidates()` at controller.py:451
   - **Field mappings (C# -> Python):**
     - `raw["delay"]` -> `"delay_frames"` (rename only)
     - `raw["pid"]` -> kept as integer (Python `_enrich_candidates` formats to hex: `f"0x{pid:08X}"`)
     - `raw["nature"]` -> `"nature"` (passthrough, already title-case string)
     - `raw["ivs"]` -> passthrough dict with oracle-format long keys (`attack`, `defense`, `speed`, `sp_attack`, `sp_defense`)
       - `_enrich_candidates()` will remap via `_IV_KEY_MAP` at controller.py:125: `{"hp":"hp", "attack":"atk", "defense":"def", "speed":"spe", "sp_attack":"spa", "sp_defense":"spd"}`
     - `raw["pre_gen_seed"]` -> `"predicted_seed_start"` (rename, keep as int)
     - `raw["post_gen_seed"]` -> `"predicted_seed_candidate"` (rename, keep as int)
     - `raw["shiny"]` -> `"is_shiny"` (rename)
     - `raw["female"]` -> `"is_female"` (rename)
   - **Add metadata fields:**
     - `"plan_id"`: passed in as parameter
     - `"rank"`: passed in as parameter (candidate index within scan results)
     - `"species_id"`: from current automation state (starter species being targeted)
   - **Return:** dict compatible with `_enrich_candidates()` input expectations

#### 4.3c: Warp Routing Decision Tree (G6, G7, G13)

5. Add method `async def _route_warp(self, target_seed: int, max_frames: int = 500000) -> dict`:
   - **Decision tree** (check in priority order):
     1. If `"heatseeker.warp_to_seed"` in capabilities:
        - Use **precision warp** (HeatSeeker per-frame DoFrameAdvance + seed compare)
        - Send via `SUB_HEATSEEKER_WARP` with `{"target_seed": target_seed, "max_frames": max_frames}`
        - Await async response (warp completes asynchronously, correlate by request_id)
        - **Lua behavior during precision warp (G7):** Lua scripts continue running full processing each frame. Overhead is bounded because SetWarpModeActive enables InvisibleEmulation + FrameSkip(9). No warp_control signal is sent to Lua -- Lua does not know warp is active. This is acceptable because Lua processing per frame is lightweight relative to emulation time.
     2. Elif chunked warp available (existing `warp.*` capabilities):
        - Use existing chunked warp (5000 frames/batch via SUB_ADVANCE_FRAMES)
        - This is the current automation warp path
     3. Else:
        - Return error: `{"error": "no_warp_capability", "message": "Neither HeatSeeker nor chunked warp available"}`
   - Return warp result dict with `{"status": "complete|failed|cancelled", "frames_advanced": N}`
6. The `execute()` method at controller.py:639 should call `_route_warp()` instead of directly managing warp when a locked target requires frame advancement

#### 4.3d: Dead Code Cleanup Marker (G15)

7. Mark the following for removal once HeatSeeker is validated end-to-end:
   - `_IV_KEY_MAP` at controller.py:125 is NOT dead code -- it remains needed for both Python oracle and HeatSeeker normalization
   - Any Python-only RNG scan code that duplicates HeatSeeker functionality should be marked with `# TODO(heatseeker): remove Python fallback once HeatSeeker validated` comments
   - Do NOT remove fallback code in this phase -- removal happens in Phase 5 validation

**Verification:**
- [ ] `_scan_rng_candidates()` method exists and is callable
- [ ] Capability check routes to C# HeatSeeker when "heatseeker.scan" in capabilities (G1)
- [ ] Fallback path returns appropriate error/result when HeatSeeker unavailable (G11)
- [ ] `_normalize_heatseeker_candidate()` correctly remaps C# field names to Python expectations (G9/G10)
- [ ] Normalized candidates pass through `_enrich_candidates()` without errors (G10)
- [ ] `_route_warp()` uses precision warp when available, falls back to chunked warp (G6/G13)
- [ ] No warp_control signal sent to Lua during precision warp (G7)
- [ ] Frontend scan button (`automation.js:2738`) works transparently via existing `/scan` route (G5)

**Out of Scope (DO NOT TOUCH):**
- `_enrich_candidates()` internals (already handles remapping)
- `_IV_KEY_MAP` (needed as-is)
- Automation state machine core logic
- Route definitions (existing `/scan` route calls into controller, which now routes internally)

**Estimated lines:** ~120 added, ~20 modified

---

### Task Package 4.4: test_heatseeker.py -- Python Protocol Tests (G12)

**Scope:** Create pytest tests for HeatSeeker Python-side routing and protocol encoding. Addresses G12 (existing tests cover Python warp only, no HeatSeeker coverage).
**Files to Create:** `tests/test_heatseeker.py`
**Dependencies:** Tasks 4.1, 4.2, 4.3

**Specifications:**
1. Test SUB_* constant values match expected bytes (0x50-0x53) -- cross-reference with Protocol.cs (G4/G8)
2. Test COMMAND_CAPABILITIES includes all 4 heatseeker.* entries (G3)
3. Test ws_endpoint command routing encodes correct JSON payloads
4. Test controller capability detection (mock frame_receiver with/without heatseeker.scan capability) (G1/G11)
5. Test default parameter values applied correctly
6. Follow existing test patterns from `tests/test_ws_endpoint_commands.py`
7. **Test _normalize_heatseeker_candidate()** (G9/G10):
   - Input: mock C# ToJson() output with oracle-format keys (attack, defense, speed, sp_attack, sp_defense), integer PID/seeds
   - Verify field renames: delay -> delay_frames, pre_gen_seed -> predicted_seed_start, post_gen_seed -> predicted_seed_candidate, shiny -> is_shiny
   - Verify metadata injection: plan_id, rank, species_id added
   - Verify output passes through `_enrich_candidates()` without KeyError
8. **Test _route_warp() decision tree** (G6/G13):
   - Mock capabilities with heatseeker.warp_to_seed -> routes to precision warp
   - Mock capabilities without heatseeker but with warp.* -> routes to chunked warp
   - Mock capabilities with neither -> returns error dict

**Verification:**
- [ ] `pytest tests/test_heatseeker.py -v` passes all tests
- [ ] No imports from C# code (pure Python tests)
- [ ] Data contract normalization tests cover all field mappings (G9/G10)

**Out of Scope (DO NOT TOUCH):**
- Existing test files (except imports if needed)
- C# testing (manual)

**Estimated lines:** ~150

---

### Task Package 4.5: test_ws_endpoint_commands.py -- HeatSeeker Command Tests (G12)

**Scope:** Add HeatSeeker command tests to the existing WebSocket endpoint test suite. Addresses G12 (existing test_ws_endpoint_commands.py has zero HeatSeeker coverage).
**Files to Modify:** `tests/test_ws_endpoint_commands.py`
**Dependencies:** Tasks 4.1, 4.2

**Specifications:**
1. Add test functions for each heatseeker.* command:
   - `test_heatseeker_scan_command` -- verifies command encoding and capability check
   - `test_heatseeker_status_command` -- verifies status command routing
   - `test_heatseeker_warp_command` -- verifies async warp command encoding
   - `test_heatseeker_monitor_command` -- verifies monitor toggle encoding
2. Follow existing test patterns in the file (mock frame_receiver, assert correct SUB_* byte sent)
3. Test that commands fail gracefully when capability not present

**Verification:**
- [ ] `pytest tests/test_ws_endpoint_commands.py -v -k heatseeker` passes
- [ ] Tests follow existing fixture patterns

**Out of Scope (DO NOT TOUCH):**
- Existing test functions
- Test fixtures (use existing ones)

**Estimated lines:** ~30 added

---

**Phase 4 Acceptance Criteria:**
- [ ] All 4 SUB_HEATSEEKER_* constants exist in frame_receiver.py and match Protocol.cs bytes (G4/G8)
- [ ] All 4 heatseeker.* entries in COMMAND_CAPABILITIES (G3)
- [ ] ws_endpoint routes all 4 commands correctly (G3)
- [ ] Controller routes to C# when capable, falls back otherwise (G1/G11)
- [ ] `_normalize_heatseeker_candidate()` maps C# oracle-format to Python pipeline input (G9/G10)
- [ ] `_route_warp()` implements precision > chunked > none decision tree (G6/G13)
- [ ] Precision warp does not send warp_control signal to Lua (G7)
- [ ] Frontend `/scan` button works transparently through capability gateway (G5)
- [ ] `pytest tests/test_heatseeker.py tests/test_ws_endpoint_commands.py -v` all pass
- [ ] **Data contract end-to-end:** C# scan JSON -> Python normalize -> enrich -> CandidateDetail model validates (G9/G10)

---

## Milestone Tracking
<!-- ID: retro_notes -->
## Phase 5 -- Seed Monitor + End-to-End Validation

**Objective:** Implement the per-frame seed monitor, validate the complete HeatSeeker pipeline end-to-end, and polish edge cases.

**Dependency:** Phase 3 + Phase 4 both complete.

---

### Task Package 5.1: HeatSeeker.cs -- Monitor Implementation

**Scope:** Replace monitor stub methods with per-frame seed reporting logic.
**Files to Modify:** `csharp/RomLabStreamer/HeatSeeker.cs`
**Dependencies:** Phase 3 complete

**Specifications:**
1. `SetMonitor(bool enable, int intervalFrames)`:
   - Set `_monitorActive = enable`
   - Set `_monitorIntervalFrames = intervalFrames` (default 60 = once per second at 60fps)
   - Reset `_monitorFrameCounter = 0`
   - If disabling, send final status: `{"monitor":"stopped"}`
   - If enabling, send confirmation: `{"monitor":"started","interval_frames":N}`
2. `TickMonitor()` -- called from UpdateAfter() every frame:
   - Early return if `!_monitorActive`
   - Increment `_monitorFrameCounter`
   - If `_monitorFrameCounter >= _monitorIntervalFrames`:
     - Read seed: `uint seed = _apis.Memory.ReadU32(GRngValueAddr, MemDomain);`
     - If seed differs from `_monitorLastSeed`:
       - Send seed update via `_sendResponse`: `{"seed":"0xHEX","frame_counter":N,"changed":true}`
       - Update `_monitorLastSeed = seed`
     - Reset `_monitorFrameCounter = 0`
3. Monitor is lightweight: only a ReadU32 every N frames, plus a comparison

**Verification:**
- [ ] `dotnet build` compiles
- [ ] SetMonitor toggles monitoring on/off
- [ ] TickMonitor reads seed at configured interval
- [ ] Only reports when seed changes (deduplication)

**Out of Scope (DO NOT TOUCH):**
- Warp logic (complete)
- Scan logic (complete)

**Estimated lines:** ~40 modified (replacing stubs)

---

### Task Package 5.2: End-to-End Cross-Stack Validation

**Scope:** Validate the complete pipeline from Python command -> WebSocket -> TCP -> C# -> response -> Python.
**Files to Modify:** None (validation only, may update test files if issues found)
**Dependencies:** All prior phases complete

**Specifications:**
1. Manual validation sequence (with BizHawk running Fire Red):
   a. Boot: `rom-lab boot pokemon_fire_red`
   b. Start server: `rom-lab serve`
   c. Connect to `/bizhawk/stream` WebSocket
   d. Send `get_capabilities` -- verify heatseeker.* capabilities present
   e. Send `heatseeker.status` -- verify JSON response with current seed
   f. Send `heatseeker.scan` with `{"horizon": 1000}` -- verify candidates array
   g. Pick a candidate from scan results, send `heatseeker.warp_to_seed` with that seed
   h. Verify warp completes with `status: complete`
   i. Send `heatseeker.status` -- verify current_seed matches target
   j. Send `heatseeker.monitor` with `{"enable": true, "interval_frames": 30}`
   k. Verify seed update messages arrive
   l. Send `heatseeker.monitor` with `{"enable": false}`
2. Cross-validate scan results against Python `rng_oracle.py`:
   - For the same base seed, run both C# scan and Python RNG scan
   - Verify candidate lists match (same PIDs, natures, IVs, shiny status)
3. Document any discrepancies as bugs

**Verification:**
- [ ] All 4 commands work through full WebSocket pipeline
- [ ] Scan results match Python rng_oracle.py for same seed
- [ ] Warp reaches exact target seed
- [ ] Monitor reports seed changes
- [ ] No error responses or crashes during validation

**Out of Scope:**
- Performance benchmarking (future)
- GUI/overlay integration (future)

---

**Phase 5 Acceptance Criteria:**
- [ ] Monitor implementation compiles and runs
- [ ] Full pipeline validated end-to-end
- [ ] C# scan results match Python rng_oracle.py reference
- [ ] All pytest tests pass: `pytest tests/test_heatseeker.py tests/test_ws_endpoint_commands.py -v`
- [ ] BizHawk stable after extended warp operations (no crashes, no memory leaks)

---

## Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Phase 1: RNG Math | Week 1 | Coder | Planned | dotnet build, LCRNG verification |
| Phase 2: Command Integration | Week 1-2 | Coder | Planned | get_capabilities, heatseeker.scan works |
| Phase 3: Precision Warp | Week 2 | Coder | Planned | Warp reaches target seed |
| Phase 4: Python Integration | Week 2 (parallel with P3) | Coder | Planned | pytest passes |
| Phase 5: Monitor + Validation | Week 3 | Coder | Planned | End-to-end cross-validation |

---

## Dependency Graph

```
Phase 1 (RNG Math)
    |
    v
Phase 2 (Command Integration)
    |         \
    v          v
Phase 3       Phase 4
(Warp)      (Python)
    \          /
     v        v
    Phase 5
  (Monitor + E2E)
```

**Parallelism opportunity:** Phase 3 and Phase 4 can execute simultaneously after Phase 2 completes. This is the natural team split point if using multiple Coder agents.

---

## Retro Notes & Adjustments

- Summarize lessons learned after each phase completes.
- Document any scope changes or re-planning decisions here.
