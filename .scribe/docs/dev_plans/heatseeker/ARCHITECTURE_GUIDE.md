---
id: heatseeker-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 heatseeker"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 06:17:16 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — heatseeker
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 05:17:47 UTC

> Architecture guide for heatseeker.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## Problem Statement

**Context:** The ROM Lab automation system currently performs RNG seed scanning and precision warp targeting through a multi-layer Python-Lua-C# pipeline. The scanning computation (LCRNG forward walk + Method 1 generation + filtering) runs in Python, while warp mode execution traverses 4 process boundaries (Python -> TCP -> C# -> Lua) with per-chunk granularity of 10,000 frames. This creates two performance bottlenecks:

1. **Scan latency**: Python scans 120K candidates in ~50-100ms. C# can do it in ~2.4ms -- a 20-40x improvement.
2. **Warp overshoot**: The tight loop advances 5,000 frames per batch without checking gRngValue mid-batch, causing up to 4,999 frames of overshoot per chunk. The Lua warp gate adds per-frame interpreter overhead even for a single RAM read.

**Goals:**
- Implement a C#-native RNG scanner (`RngScanner`) that runs LCRNG + Method 1 + shiny/nature/IV computation entirely inside BizHawk's process
- Add a precision warp command (`heatseeker.warp_to_seed`) that checks gRngValue after EVERY `DoFrameAdvance()` call, achieving frame-perfect seed targeting with zero overshoot
- Integrate into the existing RomLabStreamer as new `heatseeker.*` commands, reusing the TCP bridge, capability handshake, and build pipeline
- Maintain full backward compatibility -- existing warp mode and Python scan continue to work unmodified

**Non-Goals (Out of Scope):**
- Replacing the existing warp mode (it remains as a fallback)
- IMemoryEventsApi write callbacks (deferred to future phase)
- Multi-game support (Fire Red only in v1)
- GUI overlay/HUD (deferred to Phase 5)
- Removing Lua warp gate (deprecation path only, no removal)
<!-- ID: requirements_constraints -->
## Requirements and Constraints

### Functional Requirements
1. **heatseeker.scan**: Read gRngValue + TID/SID, run LCRNG forward N frames, produce enriched candidate pool (PID, nature, IVs, shiny, gender) -- all in C#
2. **heatseeker.warp_to_seed**: Enter warp mode, advance frames with per-frame gRngValue check, stop on exact target seed, exit warp -- zero overshoot
3. **heatseeker.monitor**: Toggle per-frame seed monitoring in UpdateAfter(), reporting seed + advance count via TCP
4. **heatseeker.status**: Query current HeatSeeker state (idle/scanning/warping/monitoring, cached TID/SID, last scan result)
5. **Capability handshake**: Register `heatseeker.*` capabilities in DoHello(), enabling Python to detect HeatSeeker availability
6. **Graceful fallback**: Python scan pipeline detects HeatSeeker via capabilities; falls back to Python-only scan when unavailable

### Non-Functional Requirements
- Scan of 120K candidates must complete in less than 16.7ms (one frame budget)
- Warp-to-seed must have zero overshoot (stop on exact frame where gRngValue matches target)
- No regression to existing streamer functionality (frame capture, audio, warp mode, debug commands)
- Same build pipeline: `scripts/build-streamer.sh` builds and deploys the updated DLL

### Constraints
- **.NET Framework 4.8** -- BizHawk External Tools target net48, not .NET 8+
- **C# 12.0** -- Language version set in .csproj
- **Emulator thread only** -- All BizHawk API calls (IMemoryApi, IEmuClientApi) must execute on the emulator thread. HandleCommand() runs on this thread. No worker thread API calls.
- **Single TCP client** -- TcpBridge supports one connection (frame_receiver.py). HeatSeeker shares this connection.
- **Fire Red / mGBA core** -- "System Bus" is the validated memory domain. gRngValue at 0x03005000.
- **Backward compatible** -- Existing SubCommand bytes (0x01-0x4A) must not change. HeatSeeker uses 0x50-0x5F.
<!-- ID: architecture_overview -->
## Architecture Overview

### Solution Summary

HeatSeeker is a C#-native RNG scanning and precision warp engine that runs inside the existing RomLabStreamer BizHawk External Tool. It adds four new commands to the `heatseeker.*` namespace (SubCommand bytes 0x50-0x53), three new C# source files, and minimal Python-side routing changes.

### System Architecture

```
Browser / MCP Tool
    |
    | JSON WebSocket
    v
ws_endpoint.py  ---  routes heatseeker.* commands
    |
    | Binary TCP (existing frame_receiver)
    v
TcpBridge.cs  ---  existing, unchanged
    |
    | CommandMessage dispatch
    v
CommandHandler.cs  ---  adds 4 new switch cases for 0x50-0x53
    |
    | delegates to
    v
+---------------------------+
| HeatSeeker.cs (NEW)       |  Orchestrator: owns scan/warp state,
|                           |  reads gRngValue via IMemoryApi,
|                           |  delegates math to RngScanner
+---------------------------+
    |
    | pure math (no BizHawk API)
    v
+---------------------------+
| RngScanner.cs (NEW)       |  Pure computation: LCRNG step,
|                           |  Method 1 generation, shiny check,
|                           |  IV extraction, candidate scoring
+---------------------------+
    |
    | data structure
    v
+---------------------------+
| CandidateResult.cs (NEW)  |  readonly struct: PID, nature,
|                           |  IVs, shiny, gender, delay, seed
+---------------------------+
```

### Data Flow: heatseeker.scan

```
1. Python sends SUB_HEATSEEKER_SCAN (0x50) with JSON payload:
   { "horizon": 120000, "species_id": 1, "gender_threshold": 31 }

2. CommandHandler.HandleCommand() dispatches to DoHeatSeekerScan(cmd)

3. DoHeatSeekerScan() calls _heatSeeker.Scan(horizon, speciesId, genderThreshold):
   a. Read gRngValue via APIs.Memory.ReadU32(0x03005000, "System Bus")
   b. Read cached TID/SID (populated at Restart())
   c. Call RngScanner.ScanForward(baseSeed, horizon, tid, sid, speciesId, genderThreshold)
   d. RngScanner runs LCRNG forward loop:
      - For each delay 0..horizon:
        - Method 1 generate: 4 LCRNG steps -> PID + IVs
        - Compute nature, shiny, gender, IV totals
        - Build CandidateResult
        - If passes minimum filter: add to results list
   e. Serialize results as JSON array
   f. Return as CommandMessage response

4. Response flows back: CommandHandler -> TcpBridge -> frame_receiver -> ws_endpoint -> browser/MCP
```

### Data Flow: heatseeker.warp_to_seed

```
1. Python sends SUB_HEATSEEKER_WARP (0x51) with payload:
   { "target_seed": 0xABCD1234, "max_frames": 600000 }

2. CommandHandler.HandleCommand() dispatches to DoHeatSeekerWarp(cmd)
   - Returns null (async command, like AdvanceFrames)

3. DoHeatSeekerWarp() calls _heatSeeker.StartWarpToSeed(targetSeed, maxFrames, requestId):
   a. StreamerForm enters warp mode (SetWarpModeActive(true) -- same bypass stack)
   b. Stores target seed, max frames, request ID
   c. Sets _heatseekerWarpActive = true

4. StreamerForm.OnCommandTimerTick() -- modified to check HeatSeeker warp:
   a. If _heatseekerWarpActive:
      - Batch loop (TightLoopBatchSize frames per tick):
        for (int i = 0; i < batch; i++) {
            APIs.EmuClient.DoFrameAdvance();
            uint rng = APIs.Memory.ReadU32(0x03005000, "System Bus");
            _heatseekerFramesAdvanced++;
            if (rng == targetSeed) {
                // EXACT HIT -- stop immediately
                _heatseekerWarpActive = false;
                SetWarpModeActive(false);
                Send success response with frames_advanced
                return;
            }
        }
      - If max_frames exceeded: abort, send failure response
      - Send progress response every batch

5. On completion/abort: exit warp, send final response with result
```

### Component Inventory

| Component | File | Type | Responsibility |
|-----------|------|------|---------------|
| `HeatSeeker` | `csharp/RomLabStreamer/HeatSeeker.cs` | NEW class | Orchestrator. Owns state (idle/scanning/warping/monitoring), cached TID/SID, scan results. Bridges between CommandHandler and RngScanner. Reads memory via IMemoryApi. |
| `RngScanner` | `csharp/RomLabStreamer/RngScanner.cs` | NEW static class | Pure math. LCRNG forward/reverse, Method 1 generation, shiny check, IV extraction, candidate filtering. Zero BizHawk dependencies. Unit-testable. |
| `CandidateResult` | `csharp/RomLabStreamer/CandidateResult.cs` | NEW readonly struct | Data carrier. PID, nature ID, nature name, IVs (6 bytes), shiny bool, gender, delay (frame offset from base seed), pre-generation seed, post-generation seed. JSON serialization. |
| `Protocol.cs` | `csharp/RomLabStreamer/Protocol.cs` | MODIFIED | Add SubCommand constants: HeatSeekerScan=0x50, HeatSeekerWarp=0x51, HeatSeekerMonitor=0x52, HeatSeekerStatus=0x53 |
| `CommandHandler.cs` | `csharp/RomLabStreamer/CommandHandler.cs` | MODIFIED | Add 4 switch cases + 4 Do*() methods. Add HeatSeeker construction in constructor. Add heatseeker.* capabilities to DoHello(). |
| `StreamerForm.cs` | `csharp/RomLabStreamer/StreamerForm.cs` | MODIFIED | Add HeatSeeker warp tick in OnCommandTimerTick(). Add HeatSeeker monitor tick in UpdateAfter(). Pass warp delegates to HeatSeeker. |
| `frame_receiver.py` | `src/rom_lab/streaming/frame_receiver.py` | MODIFIED | Add SUB_HEATSEEKER_SCAN=0x50, SUB_HEATSEEKER_WARP=0x51, SUB_HEATSEEKER_MONITOR=0x52, SUB_HEATSEEKER_STATUS=0x53 constants. |
| `ws_endpoint.py` | `src/rom_lab/streaming/ws_endpoint.py` | MODIFIED | Add heatseeker.* entries to COMMAND_CAPABILITIES dict. Add elif branches in _handle_command(). |
| `controller.py` | `src/rom_lab/api/routes/automation/controller.py` | MODIFIED | Add HeatSeeker-aware scan method that checks capabilities and routes to C# or Python fallback. |

### RAM Address Reference (Verified)

| Symbol | Address (System Bus) | Type | Access Pattern |
|--------|---------------------|------|----------------|
| `gRngValue` | `0x03005000` | u32 | `ReadU32(0x03005000, "System Bus")` -- read every frame during warp/monitor |
| `gSaveBlock2Ptr` | `0x0300500C` | u32 ptr | `ReadU32(0x0300500C, "System Bus")` -- read once at Restart() |
| TID | `*gSaveBlock2Ptr + 0x00A` | u16 | `ReadU16(ptr + 0x00A, "System Bus")` -- read once at Restart() |
| SID | `*gSaveBlock2Ptr + 0x00C` | u16 | `ReadU16(ptr + 0x00C, "System Bus")` -- read once at Restart() |

### Command Protocol Extension

| SubCommand Byte | Name | Capability String | Sync/Async | Description |
|----------------|------|-------------------|------------|-------------|
| `0x50` | HeatSeekerScan | `heatseeker.scan` | Sync | Run LCRNG scan from current seed, return candidate JSON |
| `0x51` | HeatSeekerWarp | `heatseeker.warp_to_seed` | **Async** | Enter warp, advance to target seed, send progress + completion |
| `0x52` | HeatSeekerMonitor | `heatseeker.monitor` | Sync | Toggle per-frame seed reporting (enable/disable) |
| `0x53` | HeatSeekerStatus | `heatseeker.status` | Sync | Query current HeatSeeker state |

### Request/Response Formats

**heatseeker.scan (0x50)**
```
Request payload (JSON UTF-8):
{
  "horizon": 120000,          // max frames to scan forward
  "species_id": 1,            // for gender threshold lookup
  "gender_threshold": 31,     // PID & 0xFF < threshold = female
  "min_iv_sum": 0,            // minimum HP+ATK+DEF+SPA+SPD+SPE
  "target_nature": null,      // null = any, or nature ID 0-24
  "shiny_only": false         // if true, only return shiny candidates
}

Response payload (JSON UTF-8):
{
  "base_seed": "0xABCD1234",
  "tid": 12345,
  "sid": 54321,
  "horizon": 120000,
  "scan_time_ms": 2.4,
  "candidate_count": 847,
  "candidates": [
    {
      "delay": 1523,
      "pre_gen_seed": 2882400018,
      "post_gen_seed": 1547823641,
      "pid": 2732849561,
      "nature_id": 3,
      "ivs": { "hp": 31, "attack": 31, "defense": 20, "speed": 28, "sp_attack": 15, "sp_defense": 22 },
      "iv_sum": 147,
      "shiny": false,
      "female": false
    },
    ...
  ]
}
```

**heatseeker.warp_to_seed (0x51)**
```
Request payload (JSON UTF-8):
{
  "target_seed": "0xABCD1234",  // exact gRngValue to stop on
  "max_frames": 600000          // safety cap
}

Progress responses (periodic, same request ID):
{
  "status": "warping",
  "frames_advanced": 45000,
  "max_frames": 600000,
  "current_seed": "0x..."
}

Final response:
{
  "status": "hit" | "miss" | "cancelled",
  "frames_advanced": 152300,
  "final_seed": "0x...",
  "target_seed": "0xABCD1234"
}
```

**heatseeker.monitor (0x52)**
```
Request: { "enable": true, "interval_frames": 1 }
Response: { "monitoring": true }

While monitoring, periodic unsolicited messages via TCP:
{
  "type": "heatseeker_monitor",
  "seed": "0x...",
  "frame": 123456,
  "advances_since_last": 1
}
```

**heatseeker.status (0x53)**
```
Request: (empty or {})
Response:
{
  "state": "idle" | "scanning" | "warping" | "monitoring",
  "tid": 12345,
  "sid": 54321,
  "tid_sid_valid": true,
  "last_scan_seed": "0x...",
  "last_scan_candidates": 847,
  "warp_target": null,
  "warp_frames_advanced": 0,
  "monitor_active": false
}
```
<!-- ID: detailed_design -->
## Detailed Design

### 1. RngScanner.cs -- Pure Computation Engine

This is the mathematical core. It has ZERO BizHawk dependencies -- pure integer arithmetic. This makes it unit-testable outside BizHawk.

```csharp
namespace RomLabStreamer
{
    /// <summary>
    /// Pure Gen 3 LCRNG computation engine.
    /// No BizHawk API dependencies -- unit-testable standalone.
    /// </summary>
    public static class RngScanner
    {
        // LCRNG constants (verified from decomp random.h + rng_oracle.py)
        public const uint LCRNG_A     = 0x41C64E6D;
        public const uint LCRNG_C     = 0x00006073;
        public const uint LCRNG_A_INV = 0xEEB9EB65;

        // Nature names (index = PID % 25)
        public static readonly string[] NatureNames = {
            "Hardy","Lonely","Brave","Adamant","Naughty",
            "Bold","Docile","Relaxed","Impish","Lax",
            "Timid","Hasty","Serious","Jolly","Naive",
            "Modest","Mild","Quiet","Bashful","Rash",
            "Calm","Gentle","Sassy","Careful","Quirky"
        };

        public static uint NextSeed(uint seed)
            => unchecked(seed * LCRNG_A + LCRNG_C);

        public static uint PrevSeed(uint seed)
            => unchecked((seed - LCRNG_C) * LCRNG_A_INV);

        public static uint Advance(uint seed, int steps) { ... }
        public static uint Reverse(uint seed, int steps) { ... }

        public static CandidateResult Method1Generate(
            uint preGenSeed, int delay, uint tid, uint sid,
            byte genderThreshold)
        { ... }

        /// <summary>
        /// Scan forward from baseSeed for `horizon` frames.
        /// Returns all candidates matching the filter criteria.
        /// </summary>
        public static List<CandidateResult> ScanForward(
            uint baseSeed, int horizon, uint tid, uint sid,
            byte genderThreshold,
            byte? targetNature = null,
            bool shinyOnly = false,
            int minIvSum = 0)
        {
            var results = new List<CandidateResult>();
            uint seed = baseSeed;
            for (int delay = 0; delay < horizon; delay++)
            {
                var candidate = Method1Generate(seed, delay, tid, sid, genderThreshold);
                if (PassesFilter(candidate, targetNature, shinyOnly, minIvSum))
                    results.Add(candidate);
                seed = NextSeed(seed);
            }
            return results;
        }

        private static bool PassesFilter(CandidateResult c,
            byte? targetNature, bool shinyOnly, int minIvSum)
        {
            if (shinyOnly && !c.IsShiny) return false;
            if (targetNature.HasValue && c.NatureId != targetNature.Value) return false;
            if (c.IvSum < minIvSum) return false;
            return true;
        }
    }
}
```

**Key design choices:**
- Static class: no instance state, no allocation overhead between scans
- `unchecked` arithmetic: required for uint overflow behavior matching the GBA's 32-bit wrapping
- List<CandidateResult> return: caller can sort/rank/truncate as needed
- Filter in the scan loop: avoids building a 120K-element list when only a few hundred pass

### 2. CandidateResult.cs -- Data Structure

```csharp
namespace RomLabStreamer
{
    /// <summary>
    /// One Method 1 generation result. Immutable value type.
    /// </summary>
    public readonly struct CandidateResult
    {
        public readonly int Delay;           // frame offset from base seed
        public readonly uint PreGenSeed;     // seed input to Method 1
        public readonly uint PostGenSeed;    // seed after 4 LCRNG calls
        public readonly uint Pid;
        public readonly byte NatureId;       // PID % 25
        public readonly byte Hp, Atk, Def, Spe, SpA, SpD;  // IVs 0-31
        public readonly int IvSum;
        public readonly bool IsShiny;
        public readonly bool IsFemale;

        // Constructor populates all fields from Method 1 math
        // ToJson() method for serialization -- MUST use oracle-compatible keys
        // See "Data Contract: C# CandidateResult to Python CandidateDetail" section
        // for exact field mapping. Key requirement: IVs use oracle long-form keys
        // (attack, defense, speed, sp_attack, sp_defense), NOT short keys.
        // PID output as integer, NOT hex string.
    }
}
```

**Why readonly struct:** Zero heap allocation. Candidates are value types stored contiguously in the List<T> backing array. For 120K candidates, this avoids 120K GC-tracked objects.

### 3. HeatSeeker.cs -- Orchestrator

```csharp
namespace RomLabStreamer
{
    /// <summary>
    /// HeatSeeker orchestrator. Owns scan/warp state, TID/SID cache,
    /// and bridges between CommandHandler and RngScanner.
    /// </summary>
    public class HeatSeeker
    {
        private readonly ApiContainer _apis;
        private readonly Action<CommandMessage> _sendResponse;
        private readonly Action<bool> _setWarpModeActive;

        // Cached trainer IDs (read once at Initialize())
        private uint _tid;
        private uint _sid;
        private bool _tidSidValid;

        // Warp state
        private bool _warpActive;
        private uint _warpTargetSeed;
        private int _warpMaxFrames;
        private int _warpFramesAdvanced;
        private ushort _warpRequestId;
        private bool _warpCancelled;

        // Monitor state
        private bool _monitorActive;
        private int _monitorIntervalFrames;
        private uint _monitorLastSeed;
        private int _monitorFrameCounter;

        // Last scan cache
        private uint _lastScanSeed;
        private int _lastScanCandidateCount;

        // Constants
        private const long GRngValueAddr = 0x03005000;
        private const long GSaveBlock2PtrAddr = 0x0300500C;
        private const string MemDomain = "System Bus";

        public HeatSeeker(ApiContainer apis,
            Action<CommandMessage> sendResponse,
            Action<bool> setWarpModeActive)
        { ... }

        /// <summary>Called from StreamerForm.Restart().</summary>
        public void Initialize()
        {
            ReadTidSid();
            _warpActive = false;
            _monitorActive = false;
        }

        private void ReadTidSid()
        {
            uint sb2Ptr = _apis.Memory.ReadU32(GSaveBlock2PtrAddr, MemDomain);
            if (sb2Ptr == 0) { _tidSidValid = false; return; }
            _tid = _apis.Memory.ReadU16((long)sb2Ptr + 0x00A, MemDomain);
            _sid = _apis.Memory.ReadU16((long)sb2Ptr + 0x00C, MemDomain);
            _tidSidValid = true;
        }

        /// <summary>Synchronous scan. Called from HandleCommand thread.</summary>
        public string Scan(int horizon, byte genderThreshold,
            byte? targetNature, bool shinyOnly, int minIvSum) { ... }

        /// <summary>Start async warp. Called from HandleCommand.</summary>
        public void StartWarpToSeed(uint targetSeed, int maxFrames,
            ushort requestId) { ... }

        /// <summary>Called from OnCommandTimerTick() each timer tick.</summary>
        public bool TickWarp(int batchSize) { ... }

        /// <summary>Called from UpdateAfter() each frame.</summary>
        public void TickMonitor() { ... }

        public void CancelWarp() { _warpCancelled = true; }
        public string GetStatus() { ... }
        public void SetMonitor(bool enable, int intervalFrames) { ... }
    }
}
```

**Key design choices:**
- Separate `Initialize()` from constructor: APIs are not available in constructor (BizHawk lifecycle)
- `TickWarp()` returns bool: true when warp is complete, false when still running. StreamerForm calls this in its timer tick.
- `TickMonitor()` runs in UpdateAfter(): per-frame, lightweight ReadU32 only when monitor is active
- TID/SID cached: re-read on Initialize() (ROM load/state load)

### 4. CommandHandler Integration

Add to HandleCommand switch expression (after existing debug cases):

```csharp
// HeatSeeker (heatseeker namespace)
SubCommand.HeatSeekerScan    => DoHeatSeekerScan(cmd),
SubCommand.HeatSeekerStatus  => DoHeatSeekerStatus(cmd),
SubCommand.HeatSeekerMonitor => DoHeatSeekerMonitor(cmd),
```

HeatSeekerWarp is async (like AdvanceFrames), handled before the switch:

```csharp
if (cmd.SubCommand == SubCommand.HeatSeekerWarp)
{
    return DoHeatSeekerWarp(cmd);  // returns null = async
}
```

Add to DoHello() capabilities list (conditional on HeatSeeker initialization success -- G14):

```csharp
// HeatSeeker capabilities (conditional -- only if Initialize() succeeded)
if (_heatSeeker != null && _heatSeeker.IsInitialized)
{
    capabilities.Add("heatseeker.scan");
    capabilities.Add("heatseeker.warp_to_seed");
    capabilities.Add("heatseeker.monitor");
    capabilities.Add("heatseeker.status");
}
```

**G14 compliance:** Capabilities are conditional on `_heatSeeker.IsInitialized` (true after successful TID/SID read). If save block is not loaded (e.g., before title screen), HeatSeeker capabilities are omitted and Python fallback is used automatically.

### 5. StreamerForm Integration

**OnCommandTimerTick() modification:**

```csharp
// At the top of OnCommandTimerTick(), BEFORE the existing tight loop:
if (_heatSeeker != null && _heatSeeker.IsWarpActive)
{
    bool complete = _heatSeeker.TickWarp(TightLoopBatchSize);
    if (complete)
    {
        // Warp finished, resume normal command processing
    }
    return;  // Skip normal commands during HeatSeeker warp
}

// Existing tight loop code follows...
if (_tightLoopActive && _tightLoopRemaining > 0) { ... }
```

**UpdateAfter() modification:**

```csharp
// At the end of UpdateAfter(), after frame capture:
_heatSeeker?.TickMonitor();
```

**Restart() modification:**

```csharp
// After CommandHandler creation:
_heatSeeker = new HeatSeeker(APIs, _bridge.SendResponse, SetWarpModeActive);
_heatSeeker.Initialize();
```

### 6. Python-Side Changes

**frame_receiver.py**: Add constants
```python
# HeatSeeker (Phase: heatseeker)
SUB_HEATSEEKER_SCAN: int = 0x50
SUB_HEATSEEKER_WARP: int = 0x51
SUB_HEATSEEKER_MONITOR: int = 0x52
SUB_HEATSEEKER_STATUS: int = 0x53
```

**ws_endpoint.py**: Add to COMMAND_CAPABILITIES dict
```python
"heatseeker.scan": "heatseeker.scan",
"heatseeker.warp_to_seed": "heatseeker.warp_to_seed",
"heatseeker.monitor": "heatseeker.monitor",
"heatseeker.status": "heatseeker.status",
```

Add elif branches in `_handle_command()` to encode JSON payloads and route to the correct SUB_* constant.

**controller.py**: Add capability-aware scan routing
```python
async def _scan_rng_candidates(self, horizon: int, ...) -> dict:
    """Route scan to HeatSeeker (C#) if available, else Python fallback."""
    caps = await self._frame_receiver.ensure_handshake()
    if "heatseeker.scan" in caps.get("capabilities", []):
        # Route through C# HeatSeeker
        payload = json.dumps({"horizon": horizon, ...}).encode()
        resp = await self._frame_receiver.send_command(SUB_HEATSEEKER_SCAN, payload)
        return json.loads(resp)
    else:
        # Fallback to Python scan
        return self._python_scan_fallback(horizon, ...)
```
<!-- ID: data_contract -->
## Data Contract: C# CandidateResult to Python CandidateDetail

> **Addresses: G9 (CRITICAL), G10 (HIGH) -- Blocker 1**
> Without this contract, `_enrich_candidates()` receives mismatched field names and `execute()` silently gets None for target_expected_pid/delay.

### The Problem

C# `CandidateResult` (readonly struct) uses PascalCase fields and a flat IV byte array:
```csharp
public readonly int Delay;
public readonly uint Pid;
public readonly byte NatureId;
public readonly byte Hp, Atk, Def, Spe, SpA, SpD;  // IVs 0-31
public readonly bool IsShiny;
public readonly bool IsFemale;
```

Python `_enrich_candidates()` (controller.py:451-498) expects oracle-format keys with `_IV_KEY_MAP` remapping:
```python
_IV_KEY_MAP = {"hp": "hp", "attack": "atk", "defense": "def", "speed": "spe", "sp_attack": "spa", "sp_defense": "spd"}
```

Python `execute()` (controller.py:809-821) reads from rng_plan:
```python
summary["target_expected_pid"] = rng_plan.get("target_expected_pid")
summary["target_expected_delay"] = rng_plan.get("target_expected_delay")
```

### Solution: Two-Layer Normalization

**Layer 1 -- C# `ToJson()` outputs oracle-compatible keys:**

CandidateResult.ToJson() MUST serialize using these EXACT key names:

```json
{
  "delay": 1523,
  "pid": 2732849561,
  "nature_id": 3,
  "ivs": {
    "hp": 31,
    "attack": 31,
    "defense": 20,
    "speed": 28,
    "sp_attack": 15,
    "sp_defense": 22
  },
  "iv_sum": 147,
  "shiny": false,
  "female": false,
  "pre_gen_seed": 2882400018,
  "post_gen_seed": 1547823641
}
```

**Key mapping from C# struct fields to JSON keys:**

| C# Field | JSON Key | Notes |
|-----------|----------|-------|
| `Delay` | `delay` | int, frame offset from base seed |
| `Pid` | `pid` | uint as integer (NOT hex string -- Python formats later) |
| `NatureId` | `nature_id` | byte as int |
| `Hp` | `ivs.hp` | Nested under `ivs` dict, using oracle long-form keys |
| `Atk` | `ivs.attack` | NOT "atk" -- oracle uses "attack" |
| `Def` | `ivs.defense` | NOT "def" -- oracle uses "defense" |
| `Spe` | `ivs.speed` | NOT "spe" -- oracle uses "speed" |
| `SpA` | `ivs.sp_attack` | NOT "spa" -- oracle uses "sp_attack" |
| `SpD` | `ivs.sp_defense` | NOT "spd" -- oracle uses "sp_defense" |
| `IvSum` | `iv_sum` | int, sum of all 6 IVs |
| `IsShiny` | `shiny` | bool |
| `IsFemale` | `female` | bool |
| `PreGenSeed` | `pre_gen_seed` | uint as integer |
| `PostGenSeed` | `post_gen_seed` | uint as integer |

**Why oracle-format IV keys:** `_enrich_candidates()` applies `_IV_KEY_MAP` which maps `{attack -> atk, defense -> def, speed -> spe, sp_attack -> spa, sp_defense -> spd}`. If C# already outputs the short keys, the mapping produces empty results. C# MUST output the long-form oracle keys so the existing remapping works unchanged.

**Layer 2 -- Python `_normalize_heatseeker_candidate()` adds enrichment context:**

After C# returns candidates, Python wraps each one for the enrichment pipeline:

```python
def _normalize_heatseeker_candidate(raw: dict, rank: int, plan_id: str, species_id: int) -> dict:
    """Convert HeatSeeker C# candidate dict to _enrich_candidates() input format."""
    candidate = dict(raw)
    candidate["plan_id"] = plan_id
    candidate["rank"] = rank
    candidate["species_id"] = species_id
    # C# returns pid as int; _enrich_candidates expects int (formats to hex later)
    # C# returns ivs in oracle-format keys; _enrich_candidates expects oracle keys
    # C# returns pre_gen_seed/post_gen_seed as int; _enrich expects these names
    # Map C# seed field names to Python expected names
    candidate["predicted_seed_start"] = candidate.pop("pre_gen_seed", 0)
    candidate["predicted_seed_candidate"] = candidate.pop("post_gen_seed", 0)
    return candidate
```

This normalization is **minimal** because C# ToJson() already outputs oracle-compatible keys. The normalizer only adds metadata fields (plan_id, rank, species_id) and renames seed fields.

### Data Flow Through Pipeline

```
C# RngScanner.ScanForward()
  -> List<CandidateResult>
  -> Each CandidateResult.ToJson() (oracle-compatible keys)
  -> JSON array in scan response

Python controller._scan_rng_candidates()
  -> Parse C# JSON response
  -> For each candidate: _normalize_heatseeker_candidate(raw, rank, plan_id, species_id)
  -> Pass list to _enrich_candidates(normalized, species_id)
  -> _enrich_candidates applies _IV_KEY_MAP, computes hidden power, formats hex PIDs
  -> Cache in _scan_results (same as Python scan path)

Python execute()
  -> Reads from _scan_results cache (same format regardless of scan source)
  -> locked_target["candidate"] has all enriched fields
  -> rng_plan fields (target_expected_pid, target_expected_delay) populated by scan
```

### Contract Verification Criteria

- [ ] C# `CandidateResult.ToJson()` outputs keys matching the table above EXACTLY
- [ ] `ivs` dict uses oracle long-form keys: `hp`, `attack`, `defense`, `speed`, `sp_attack`, `sp_defense`
- [ ] `pid` is output as integer, NOT hex string
- [ ] Python `_normalize_heatseeker_candidate()` adds `plan_id`, `rank`, `species_id`, renames seed fields
- [ ] `_enrich_candidates()` processes normalized HeatSeeker candidates identically to Python oracle candidates
- [ ] `execute()` can read `target_expected_pid` and `target_expected_delay` from HeatSeeker-sourced locked_target
- [ ] Round-trip test: C# scan -> normalize -> enrich -> select -> execute works without None field errors

<!-- ID: capability_gateway -->
## Capability Gateway Pattern

> **Addresses: G1 (HIGH), G5 (HIGH), G11 (HIGH), G14 (MEDIUM)**
> Provides a reusable pattern for "check if HeatSeeker is available, use it, else fallback to Python."

### Gateway Method: `_scan_rng_candidates()`

A single method on `AutomationController` that encapsulates all capability detection and routing logic:

```python
async def _scan_rng_candidates(
    self,
    horizon: int,
    species_id: int,
    gender_threshold: int = 127,
    target_nature: int | None = None,
    shiny_only: bool = False,
    min_iv_sum: int = 0,
) -> dict[str, Any]:
    """Route scan to HeatSeeker (C#) if available, else Python fallback.

    Returns dict with keys: base_seed, tid, sid, candidates (list[dict]), scan_time_ms.
    Caller does NOT need to know which backend was used.
    """
    caps = self._cached_capabilities  # populated by ensure_handshake
    if caps and "heatseeker.scan" in caps:
        return await self._scan_via_heatseeker(horizon, species_id, gender_threshold,
                                                target_nature, shiny_only, min_iv_sum)
    else:
        return await self._scan_via_python(horizon, species_id, gender_threshold,
                                            target_nature, shiny_only, min_iv_sum)
```

### Capability Cache

Capabilities are fetched once per WebSocket connection (from the HELLO handshake response) and cached on the controller:

```python
# In controller __init__ or connection setup:
self._cached_capabilities: set[str] | None = None

async def _refresh_capabilities(self) -> set[str]:
    """Fetch capabilities from streamer via HELLO handshake."""
    resp = await self._frame_receiver.ensure_handshake()
    caps = set(resp.get("capabilities", []))
    self._cached_capabilities = caps
    return caps
```

**Invalidation:** Capabilities are refreshed when:
- WebSocket reconnects (new HELLO handshake)
- Explicit `_refresh_capabilities()` call
- Never mid-session (capabilities are static per streamer session -- G14 is acceptable)

### Integration Point: scan()

The existing `scan()` method (controller.py:500+) is modified to call `_scan_rng_candidates()` instead of directly invoking the Python scan pipeline:

```python
async def scan(self, request: StarterResetStartRequest) -> dict[str, Any]:
    # ... existing precheck and setup ...
    # CHANGED: Use capability gateway instead of direct Python scan
    raw_scan = await self._scan_rng_candidates(
        horizon=horizon,
        species_id=species_id,
        gender_threshold=gender_threshold,
    )
    raw_candidates = raw_scan.get("candidates", [])
    enriched = self._enrich_candidates(raw_candidates, species_id)
    # ... existing cache and response assembly ...
```

### Frontend Transparency (G5)

The frontend (`automation.js`) continues calling `POST /scan` to the Python API. The capability gateway is ENTIRELY server-side. No frontend changes required for basic HeatSeeker integration.

```
Frontend: POST /scan -> Python scan() -> _scan_rng_candidates()
                                              |
                              HeatSeeker available? ----YES----> C# scan via WS
                                              |
                                              NO
                                              |
                                              v
                                    Python scan (existing)
```

### Warp Capability Gateway

Same pattern applies to warp routing (see Warp Mode Routing section). The controller checks for `heatseeker.warp_to_seed` capability before choosing warp strategy.

<!-- ID: warp_mode_routing -->
## Warp Mode Routing

> **Addresses: G6 (HIGH), G7 (MEDIUM), G13 (HIGH), G15 (LOW)**
> Defines when to use each warp strategy and how they coexist.

### Four Warp Layers (Verified)

| Layer | Mechanism | Speed | Precision | When Used |
|-------|-----------|-------|-----------|-----------|
| **1. No warp** | Per-frame polling from Python | 60fps | Exact | frames_to_target < warp_threshold |
| **2. HeatSeeker precision warp** | C# per-frame `DoFrameAdvance()` + `ReadU32(gRngValue)` | ~5000fps | Zero overshoot | `heatseeker.warp_to_seed` available AND frames_to_target > 0 |
| **3. Chunked warp** | C# tight loop (5000 frames/batch) via `SUB_ADVANCE_FRAMES` | ~50000fps | Up to 4999 frames overshoot | HeatSeeker unavailable AND warp_enabled AND frames_to_target > warp_threshold |
| **4. Lua warp gate** | Lua `WARP_MODE` skips expensive processing | N/A (passive) | N/A | Active during Layer 3 only (via `_send_lua_warp_control`) |

### Decision Tree

```
_wait_for_lua_bot_candidate() needs to advance N frames:

  1. Is heatseeker.warp_to_seed available? (capability check)
     YES -> Use precision warp (Layer 2)
       - Send SUB_HEATSEEKER_WARP with target_seed
       - C# handles everything: enters warp, per-frame advance + check, exits warp
       - Python waits for completion response
       - Zero overshoot guaranteed
       - Lua NOT notified (see below)

     NO -> Is warp_enabled and N > warp_threshold?
       YES -> Use chunked warp (Layer 3)
         - _send_lua_warp_control("start") -- activates Lua warp gate
         - _set_warp_mode(True) -- C# enters warp mode
         - Loop: _advance_frames_bulk(chunk=10K) until within threshold
         - Cleanup: _send_lua_warp_control("stop"), restore
         - Possible overshoot up to chunk_size

       NO -> Per-frame polling (Layer 1)
         - Normal automation loop
         - Check seed each frame via Lua/Python pipeline
```

### Lua Behavior During Precision Warp (G7)

**Decision: HeatSeeker precision warp does NOT send `warp_control` to Lua.**

Rationale:
- Precision warp runs in C# via `DoFrameAdvance()` in a tight loop
- C# uses `InvisibleEmulation(true)` + `FrameSkip(9)` during warp mode, which drastically reduces the frames Lua actually processes
- Lua runs its normal frame processing loop, but the overhead is bounded:
  - With FrameSkip(9), Lua sees ~1/10th of the frames
  - InvisibleEmulation skips rendering, which is the expensive part
  - Lua's per-frame work (state assembly, socket send) is ~1-2ms
  - At 5000fps effective warp speed, Lua overhead is ~0.5ms per Lua frame = negligible
- Sending `warp_control` would require:
  - Adding a new `warp_control` channel to precision warp (extra complexity)
  - Coordinating start/stop signals between C# warp and Lua state
  - Risk of Lua state desync if precision warp completes mid-Lua-frame

**Acceptable tradeoff:** ~5-10% overhead from Lua processing during precision warp, in exchange for simpler implementation and no Lua coordination risk. If profiling shows >20% overhead, a future phase can add `warp_control` signaling.

### Dead Code Cleanup (G15)

**Phase 3 task:** Remove `_pendingAdvanceFrames` field (StreamerForm.cs:60-61) and the `UpdateAfter()` warp gate that checks it (StreamerForm.cs:262-297). This code is already dead -- `StartAdvanceFrames` sets `_pendingAdvanceFrames = 0` and uses the tight loop instead. The gate can never fire.

### Lua Warp Gate Deprecation Path

| Phase | Lua Warp Gate Status | Notes |
|-------|---------------------|-------|
| Current | Active during chunked warp | `_send_lua_warp_control("start"/"stop")` |
| HeatSeeker v1 | Active during chunked warp only | Not used during precision warp |
| Future | Config toggle to disable | Once precision warp validated for all cases |
| Long-term | Removed entirely | After deprecation period, remove from socket_reader.lua |

<!-- ID: constants_duplication -->
## Constants Duplication (G8)

The LCRNG constants (LCRNG_A, LCRNG_C, LCRNG_A_INV) are duplicated in:
- C# `RngScanner.cs` (new)
- Python `rng_oracle.py` (existing)

**Decision: Accept duplication.** These are mathematical constants that will never change (defined by the GBA hardware). Cross-language shared constants add build complexity (code generation, shared config files) for zero practical benefit. Both implementations are verified against the same Pokemon decomp source (`random.h`).

**Separately:** The duplicated automation constants in `state_factories.py:15-18` (DEFAULT_RNG_MODE, etc.) are pre-existing tech debt from incomplete Task 1.4. This is out of scope for HeatSeeker but should be cleaned up in a future maintenance pass.

<!-- ID: directory_structure -->
## Directory Structure

```
csharp/RomLabStreamer/
  ├── RomLabStreamer.csproj    # EXISTING -- no changes needed
  ├── StreamerForm.cs          # MODIFIED -- add HeatSeeker warp/monitor ticks
  ├── CommandHandler.cs        # MODIFIED -- add 4 heatseeker.* dispatch cases
  ├── Protocol.cs              # MODIFIED -- add 4 SubCommand constants
  ├── TcpBridge.cs             # EXISTING -- unchanged
  ├── FrameCapture.cs          # EXISTING -- unchanged
  ├── AudioCapture.cs          # EXISTING -- unchanged
  ├── HeatSeeker.cs            # NEW -- orchestrator (state, memory reads, warp control)
  ├── RngScanner.cs            # NEW -- pure math (LCRNG, Method 1, filtering)
  └── CandidateResult.cs       # NEW -- readonly struct data carrier

src/rom_lab/streaming/
  ├── frame_receiver.py        # MODIFIED -- add SUB_HEATSEEKER_* constants
  └── ws_endpoint.py           # MODIFIED -- add heatseeker.* capabilities + routing

src/rom_lab/api/routes/automation/
  └── controller.py            # MODIFIED -- add capability-aware scan routing

scripts/
  ├── build-streamer.sh        # EXISTING -- unchanged (builds same .csproj)
  └── update_ext_tool_trust.py # EXISTING -- unchanged

tests/
  ├── test_ws_endpoint_commands.py  # MODIFIED -- add heatseeker.* command tests
  └── test_heatseeker.py            # NEW -- Python-side routing + protocol tests
```

### File Change Summary

| File | Change Type | Lines Added (est.) | Lines Modified (est.) |
|------|-------------|-------------------|---------------------|
| `HeatSeeker.cs` | NEW | ~250 | 0 |
| `RngScanner.cs` | NEW | ~180 | 0 |
| `CandidateResult.cs` | NEW | ~80 | 0 |
| `Protocol.cs` | MODIFIED | 6 | 0 |
| `CommandHandler.cs` | MODIFIED | ~120 | ~10 |
| `StreamerForm.cs` | MODIFIED | ~30 | ~5 |
| `frame_receiver.py` | MODIFIED | 5 | 0 |
| `ws_endpoint.py` | MODIFIED | ~30 | 0 |
| `controller.py` | MODIFIED | ~40 | ~10 |
| `test_heatseeker.py` | NEW | ~150 | 0 |
| `test_ws_endpoint_commands.py` | MODIFIED | ~30 | 0 |
| **TOTAL** | | **~921** | **~25** |
<!-- ID: data_storage -->
## Data and State Management

### In-Process State (C# -- HeatSeeker instance)

| State | Scope | Persistence | Notes |
|-------|-------|-------------|-------|
| TID/SID cache | Per-ROM-load | Until Restart() | Re-read when ROM loads or savestate loaded |
| Warp state | Per-warp-command | Transient | Reset on warp completion/abort |
| Monitor state | Per-toggle | Transient | Cleared on Restart() |
| Last scan cache | Per-scan | Transient | Overwritten each scan |

### Cross-Process State (Binary TCP Protocol)

- Request/response correlation via `RequestID` (2-byte LE) -- same as existing commands
- Async warp progress uses same request ID for all progress + completion messages
- Monitor updates are unsolicited (no request ID) -- identified by `type` field in JSON

### No Persistent Storage

HeatSeeker does not write to disk. All state is in-memory within the BizHawk process. Scan results flow through TCP to Python/browser for display and persistence. The Python automation controller already handles scan result logging.
<!-- ID: testing_strategy -->
## Testing and Validation Strategy

### C# Testing (Manual -- BizHawk Required)

C# External Tools cannot be unit-tested in isolation without the BizHawk runtime. Validation strategy:

1. **RngScanner correctness**: Cross-validate C# scan results against existing Python `rng_oracle.py` output for identical seeds. Run both with same (seed, TID, SID, horizon) and compare candidate lists.
2. **Build verification**: `scripts/build-streamer.sh` must succeed with zero errors/warnings
3. **Runtime smoke test**: Deploy DLL, boot BizHawk, verify `heatseeker.*` capabilities appear in HELLO response
4. **Scan accuracy**: Run scan from known seed, verify PID/nature/IVs match Python oracle output
5. **Warp precision**: Warp to known target seed, verify gRngValue matches exactly on landing frame

### Python Testing (Automated -- pytest)

| Test File | What It Tests | How |
|-----------|--------------|-----|
| `tests/test_heatseeker.py` | Protocol constants, capability routing, JSON payload encoding/decoding | Mock frame_receiver, verify correct SUB_* bytes sent |
| `tests/test_ws_endpoint_commands.py` | heatseeker.* WebSocket command routing | Existing test pattern -- add heatseeker command dispatch tests |

### Validation Sequence (Per Phase)

```
Phase 1 (RNG Math):
  1. Write RngScanner.cs + CandidateResult.cs
  2. dotnet build -- must succeed
  3. Deploy and boot BizHawk
  4. Run heatseeker.scan from Python with known seed
  5. Compare output against rng_oracle.py for same seed/TID/SID

Phase 2 (Command Integration):
  1. Verify heatseeker.* in HELLO capabilities
  2. Run heatseeker.scan via WebSocket from browser
  3. Run heatseeker.status -- verify state reporting
  4. pytest tests/test_ws_endpoint_commands.py -- all pass

Phase 3 (Precision Warp):
  1. Save state at known seed
  2. heatseeker.warp_to_seed with target 50,000 frames ahead
  3. Verify landing seed matches target EXACTLY
  4. Verify frames_advanced in response
  5. Test abort: start warp, cancel before completion

Phase 4 (Python Integration):
  1. pytest tests/test_heatseeker.py -- all pass
  2. Verify controller scan routing: with HeatSeeker -> C#, without -> Python
  3. End-to-end: automation run uses HeatSeeker scan when available

Phase 5 (Monitor):
  1. Enable monitor, verify seed reports arrive at expected interval
  2. Disable monitor, verify reports stop
  3. Monitor during normal gameplay -- verify advance tracking
```

### Cross-Validation Against Python Oracle

The most critical test is mathematical correctness. The C# `RngScanner` must produce identical results to the Python `rng_oracle.py` for every candidate at every delay. Test procedure:

```python
# Python side: generate reference data
from rom_lab.plugins.pokemon_fire_red.rng_oracle import method1_generate, next_seed

seed = 0x12345678
tid, sid = 12345, 54321
results = []
s = seed
for delay in range(1000):
    result = method1_generate(s)
    results.append((delay, hex(result.pid), result.nature_id, result.ivs))
    s = next_seed(s)

# C# side: run heatseeker.scan with same seed/TID/SID/horizon=1000
# Compare every candidate field: delay, PID, nature_id, IVs
# ANY mismatch = FAIL
```
<!-- ID: deployment_operations -->
## Build, Deploy, and Operations

### Build Pipeline (Unchanged)

```bash
# Build only
scripts/build-streamer.sh

# Build + deploy to BizHawk ExternalTools/ + update trust hash
scripts/build-streamer.sh deploy
```

The existing build script compiles `csharp/RomLabStreamer/RomLabStreamer.csproj` targeting net48. New C# files (HeatSeeker.cs, RngScanner.cs, CandidateResult.cs) are automatically included by the `<Compile Include="**/*.cs" />` wildcard in the .csproj. No build script changes needed.

### Deployment Sequence

1. `scripts/build-streamer.sh deploy` -- builds DLL, copies to `~/.romlab/bizhawk/ExternalTools/`, updates SHA512 trust hash in `config.ini`
2. Restart BizHawk to load updated DLL (External Tools are loaded at startup)
3. Restart `rom-lab serve` (picks up Python-side changes)
4. Verify: connect to `/bizhawk/stream` WebSocket, send `get_capabilities`, confirm `heatseeker.*` capabilities present

### Rollback

If HeatSeeker causes issues, revert the C# changes and rebuild. The existing warp mode and Python scan continue to work -- HeatSeeker is purely additive.

### Monitoring

- `heatseeker.status` command provides runtime state inspection
- C# `System.Diagnostics.Debug.WriteLine()` for BizHawk debug console logging
- Python-side logging via existing `ws_endpoint.py` audit log pattern
<!-- ID: open_questions -->
## Open Questions and Future Work

| Item | Priority | Status | Notes |
|------|----------|--------|-------|
| IMemoryEventsApi write callbacks for zero-poll monitoring | Medium | Deferred | Per-frame overhead needs benchmarking. Start with polling. |
| IGuiApi overlay HUD for on-screen seed display | Low | Deferred to Phase 5 | DrawText/PixelText confirmed available via monodis |
| Multi-target seed scanning (stop on any of N seeds) | Low | Future | Useful for flexible target selection |
| Predictive warp (calculate exact frame count via LCRNG) | Medium | Future | Can replace chunked warp entirely -- single advance call |
| Lua warp gate deprecation | Low | Future | Phase 1: coexist. Phase 2: config toggle. Phase 3: remove. |
| ReadU32 overhead per DoFrameAdvance in warp tight loop | Medium | Measure in Phase 3 | Expected <1us. If >100us, batch N frames then check. |
| SaveBlock2 pointer validity during boot sequence | Low | Known risk | Pointer may be 0 before save loads. Initialize() handles this with null check. |
| BizHawk External Tool crash on first load | Low | Pre-existing | Known issue with RomLabStreamer. Defensive null checks in Restart(). |
<!-- ID: references_appendix -->
## References and Appendix

### Research Documents
- `RESEARCH_STREAMER_INFRASTRUCTURE.md` -- Full C# RomLabStreamer architecture, command system, TCP bridge, build pipeline
- `RESEARCH_BIZHAWK_RNG_API.md` -- IMemoryApi/IGuiApi verified via monodis, gRngValue address (triple-verified), LCRNG formula, Method 1 algorithm, TID/SID access pattern
- `RESEARCH_WARP_MODE.md` -- 4-layer warp architecture, tight loop mechanism, adaptive acceleration, Lua warp gate, HeatSeeker integration opportunities

### Key Source Files Referenced
| File | Lines | Reference For |
|------|-------|---------------|
| `csharp/RomLabStreamer/Protocol.cs` | 27-80 | SubCommand byte codes, 0x50+ available |
| `csharp/RomLabStreamer/CommandHandler.cs` | 183-260, 266-340 | HandleCommand dispatch, DoHello capabilities |
| `csharp/RomLabStreamer/StreamerForm.cs` | 490-588 | Tight loop, OnCommandTimerTick, StartAdvanceFrames |
| `src/rom_lab/streaming/frame_receiver.py` | 26-42 | SUB_* constant definitions |
| `src/rom_lab/streaming/ws_endpoint.py` | 223-260 | COMMAND_CAPABILITIES dict |
| `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` | 40-161 | LCRNG constants, Method 1 implementation |

### LCRNG Constants (Canonical)
```
LCRNG_A     = 0x41C64E6D  (multiplier)
LCRNG_C     = 0x00006073  (increment)
LCRNG_A_INV = 0xEEB9EB65  (multiplicative inverse)

next_seed = (seed * LCRNG_A + LCRNG_C) & 0xFFFFFFFF
prev_seed = ((seed - LCRNG_C) * LCRNG_A_INV) & 0xFFFFFFFF
output    = seed >> 16  (upper 16 bits)
```

### SubCommand Byte Allocation (Updated)
```
0x01-0x0B  Emulation + Warp (existing)
0x10-0x14  Save States (existing)
0x20-0x27  Memory Access (existing)
0x30-0x32  Protocol (existing)
0x40-0x4A  Debug Surface (existing)
0x50       HeatSeekerScan      (NEW)
0x51       HeatSeekerWarp      (NEW)
0x52       HeatSeekerMonitor   (NEW)
0x53       HeatSeekerStatus    (NEW)
0x54-0x5F  Reserved for HeatSeeker expansion
```
