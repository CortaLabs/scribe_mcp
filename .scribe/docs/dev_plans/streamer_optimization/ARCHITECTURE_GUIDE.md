---
id: streamer_optimization-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 streamer_optimization"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 03:43:29 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — streamer_optimization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 03:19:07 UTC

> Architecture guide for streamer_optimization.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** The starter automation bot in ROM Lab targets specific RNG seeds to snipe Pokemon with desired IVs/natures in Pokemon Fire Red. A warp mode infrastructure was implemented (warp_mode_frame_advance project) that uses a C# state machine, Lua warp guards, and Python orchestration to bulk-advance frames. However, the current implementation achieves only ~143fps (~2.4x realtime) instead of the theoretical 5000-50000% ceiling identified by research.

**Root Cause (Verified):** The existing warp mode correctly disables video capture and sound in C#, but misses several critical BizHawk bypass settings and has Python-side limitations:

1. **Missing BizHawk bypasses (C#):**
   - `EnableRewind(false)` — BizHawk saves rewind state every frame (significant overhead)
   - `FrameSkip(9)` — render cadence still at default (renders every frame to display pipeline)
   - `RunLuaDuringTurbo` — Lua callbacks still fire every frame (~103 RAM reads from socket_reader.lua normal path; the bot runtime warp gate reduces this to 1 read but the socket_reader still runs its full on_frame when not in WARP_MODE)
   - No warp cancellation mechanism in the C# state machine

2. **Python-side limitations:**
   - `_advance_frames_bulk()` is a single blocking TCP request-response — no progress, no cancellation
   - `_send_frames()` in ws_endpoint.py has no warp awareness — blocks on queue.get() with stale frames
   - One-shot `warp_engaged` flag prevents re-warping if first batch hits WARP_MAX_FRAMES_PER_CALL
   - No telemetry (GetApproxFramerate()) for adaptive batch sizing

**Goal:** Optimize the EXISTING warp mode infrastructure to achieve 3000+ fps during warp on standard hardware, with progress reporting, cancellation support, and multi-batch capability.

**Research Base:** 3 research documents + 1 prior architecture:
- RESEARCH_CSHARP_STREAMER.md: C# plugin audit, 22 API methods, DoFrameAdvance bottleneck analysis
- RESEARCH_PYTHON_PIPELINE.md: Python pipeline audit, 6 bottlenecks, 5 optimization paths
- RESEARCH_BIZHAWK_SPEED.md: BizHawk speed capabilities, 55 IEmuClientApi methods, theoretical ceiling analysis
- warp_mode_frame_advance ARCHITECTURE_GUIDE.md: Prior 992-line design (fully implemented, serves as baseline)
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Functional Requirements:**
1. Add `EnableRewind(false)` to C# warp entry, restore on exit
2. Add `FrameSkip(9)` to C# warp entry, restore on exit
3. Add warp cancellation: Python can abort an in-progress warp via new SUB_CANCEL_ADVANCE command
4. Chunked frame advancement: Python breaks large warps into configurable chunks (default 10,000 frames)
5. Progress reporting: Python emits warp progress events during chunked advancement
6. Multi-shot warp: Remove one-shot `warp_engaged` flag, allow re-warping when frames_to_target re-exceeds threshold
7. ws_endpoint `_send_frames` warp drain mode: drain queue without encoding/sending during warp
8. GetApproxFramerate() telemetry after each warp batch for speed reporting

**Non-Functional Requirements:**
1. Zero regression: all existing tests pass, normal streaming unaffected when warp is off
2. Target 3000+ fps during warp on standard hardware (currently ~143fps)
3. Warp cancellation response time < 1 second
4. Clean BizHawk state restoration on ALL exit paths (normal, cancel, error, tool unload)

**Constraints:**
- All BizHawk API method names MUST be verified via monodis before use (bizhawk-api-discovery rule)
- C# External Tool runs on emulator thread — no background threading for frame advance
- RunLuaDuringTurbo is on Config class, not IEmuClientApi — may need reflection to access; treat as exploratory
- Both Lua readers must be updated together (lua-reader-sync rule)
- Existing warp infrastructure must not be replaced — only enhanced
<!-- ID: architecture_overview -->
## 3. Architecture Overview

### Current State (Baseline)

The existing warp infrastructure works end-to-end:

```
Python controller._wait_for_lua_bot_candidate()
  -> _send_lua_warp_control("start")     # Lua: _warp_active=true, WARP_MODE=true
  -> _set_warp_mode(True)                # C#: InvisibleEmulation, SetSoundOn(false), SpeedMode(6400), _videoStreamingEnabled=false
  -> _advance_frames_bulk(N)             # C#: state machine decrements _pendingAdvanceFrames in UpdateAfter
  -> _set_warp_mode(False)               # C#: restore all settings
  -> _send_lua_warp_control("stop")      # Lua: restore full tick
```

C# warp gate (StreamerForm.cs:232-263): On each frame, decrements counter, sends progress every 500 frames, returns early (skips all normal work). FastUpdateAfter delegates to UpdateAfter every frame during warp.

### Optimization Targets

```
CURRENT WARP BYPASS STACK:
  [x] InvisibleEmulation(true)        -- render bypass
  [x] SetSoundOn(false)               -- audio bypass
  [x] SpeedMode(6400)                 -- max throttle
  [x] _videoStreamingEnabled=false    -- frame capture bypass
  [x] Lua _warp_active guard          -- 1 RAM read instead of 103+
  [x] Lua WARP_MODE guard             -- skip state.json + socket I/O
  [ ] EnableRewind(false)             -- MISSING: rewind state save overhead
  [ ] FrameSkip(9)                    -- MISSING: render cadence overhead
  [ ] RunLuaDuringTurbo=false         -- MISSING: eliminate ALL Lua callbacks (exploratory)
  [ ] Warp cancellation               -- MISSING: no way to abort mid-warp
  [ ] Chunked advancement             -- MISSING: single blocking call
  [ ] Progress reporting (Python)     -- MISSING: Python blocks, no status
  [ ] Multi-shot warp                 -- MISSING: one-shot flag
  [ ] _send_frames drain mode         -- MISSING: WebSocket still processes during warp
  [ ] GetApproxFramerate() telemetry  -- MISSING: no speed measurement
```

### Change Architecture

All changes are additive enhancements to existing code. No new files, no new services. Changes grouped by layer:

**C# Layer (StreamerForm.cs + CommandHandler.cs):**
- Add `EnableRewind(false)` and `FrameSkip(9)` to `SetWarpModeActive(true)`, restore on exit
- Save/restore rewind and frameskip state (new fields: `_warpSavedRewindEnabled`, `_warpSavedFrameSkip`)
- Add `DoCancel` handler for new `SUB_CANCEL_ADVANCE = 0x0B` — sets `_pendingAdvanceFrames = 0`
- Add `GetApproxFramerate()` call after warp completion, include in completion response
- Protocol.cs: Add `CancelAdvance = 0x0B` constant

**Python Controller Layer (controller.py):**
- Replace single `_advance_frames_bulk(N)` with chunked loop: chunks of WARP_CHUNK_SIZE (default 10,000 frames)
- Between chunks: check `_stop_event`, re-read bot state, emit progress, check if seed already hit
- Remove `warp_engaged` one-shot flag — allow re-warping when distance re-exceeds threshold
- Add `_cancel_advance()` method using new SUB_CANCEL_ADVANCE
- Log GetApproxFramerate from warp completion response

**Python WebSocket Layer (ws_endpoint.py):**
- Add `warp_active` flag to shared `stream_config` dict
- In `_send_frames`: when `warp_active`, drain queue without encoding/sending (prevent stale frame blockage)
- Set flag via `set_warp_state` exposed on the streaming endpoint handler

**Python Constants/Models (constants.py, models.py):**
- Add `WARP_CHUNK_SIZE = 10_000` constant
- Add `warp_chunk_size` field to StarterResetStartRequest model

### Component Interaction (Post-Optimization)

```
Python controller._wait_for_lua_bot_candidate()
  LOOP while frames_to_target > warp_threshold:
    -> _send_lua_warp_control("start")          # Once, first iteration
    -> _set_warp_mode(True)                     # Once, first iteration
    -> set_warp_state(True) on ws_endpoint      # Signal _send_frames to drain
    -> CHUNK LOOP:
       -> _advance_frames_bulk(min(chunk_size, remaining))
       -> Check _stop_event (cancellation)
       -> Re-read bot state (seed match check)
       -> Emit progress event
       -> If seed matched or cancelled: break
    -> _set_warp_mode(False)                    # Restore C#
    -> set_warp_state(False) on ws_endpoint     # Resume streaming
    -> _send_lua_warp_control("stop")           # Restore Lua
    -> Re-read state, re-compute frames_to_target
    -> If still > threshold: loop (multi-shot)
```
<!-- ID: detailed_design -->
## 4. Detailed Design

### 4.1 C# Enhancements (StreamerForm.cs + CommandHandler.cs + Protocol.cs)

#### 4.1.1 Additional Bypass Settings in SetWarpModeActive

Add new save/restore fields after existing warp fields (StreamerForm.cs ~line 66):

```csharp
private bool _warpSavedRewindEnabled = true;   // EnableRewind state before warp
private int _warpSavedFrameSkip = 0;           // FrameSkip state before warp (0 = render every frame)
```

Modify `SetWarpModeActive(bool active)` (StreamerForm.cs:426-445):

```csharp
private void SetWarpModeActive(bool active)
{
    if (active == _warpModeActive) return;
    _warpModeActive = active;
    if (active)
    {
        // Save current state
        _warpSavedSoundOn = APIs.EmuClient.GetSoundOn();
        _warpSavedVideoEnabled = _videoStreamingEnabled;
        // Note: BizHawk has no GetRewindEnabled() or GetFrameSkip() — track internally

        // Apply all bypasses
        APIs.EmuClient.SetSoundOn(false);
        APIs.EmuClient.InvisibleEmulation(true);
        APIs.EmuClient.EnableRewind(false);     // NEW: eliminate rewind state save overhead
        APIs.EmuClient.FrameSkip(9);            // NEW: minimize render cadence
        _videoStreamingEnabled = false;
        APIs.EmuClient.SpeedMode(6400);
    }
    else
    {
        // Restore all settings
        APIs.EmuClient.SetSoundOn(_warpSavedSoundOn);
        APIs.EmuClient.InvisibleEmulation(false);
        APIs.EmuClient.EnableRewind(true);      // NEW: restore rewind
        APIs.EmuClient.FrameSkip(0);            // NEW: restore render-every-frame
        _videoStreamingEnabled = _warpSavedVideoEnabled;
        APIs.EmuClient.SpeedMode(100);
    }
}
```

**IMPORTANT**: `EnableRewind(bool)` and `FrameSkip(int)` are monodis-verified on IEmuClientApi (RESEARCH_BIZHAWK_SPEED.md Finding 12, lines 531/559). Safe to call.

#### 4.1.2 Warp Cancellation — CancelAdvance Command

Protocol.cs — add after AdvanceFrames constant:

```csharp
public const byte CancelAdvance = 0x0B;  // Cancel in-progress advance: [] -> [Status:1][Cancelled:1]
```

CommandHandler.cs — add dispatch case and handler:

```csharp
SubCommand.CancelAdvance => DoCancelAdvance(cmd),
```

```csharp
private CommandMessage DoCancelAdvance(CommandMessage cmd)
{
    bool wasCancelled = _pendingAdvanceFrames > 0;  // Need access via delegate
    _cancelAdvance?.Invoke();
    byte[] data = new byte[] { (byte)(wasCancelled ? 1 : 0) };
    return Protocol.MakeResponse(cmd, CommandStatus.Success, data);
}
```

StreamerForm.cs — add cancel delegate and method:

```csharp
// New delegate in constructor:
(Action)(() => CancelAdvanceFrames())

private void CancelAdvanceFrames()
{
    _pendingAdvanceFrames = 0;
    // Warp mode cleanup is handled by the Python controller calling _set_warp_mode(False)
}
```

#### 4.1.3 Telemetry in Completion Response

Modify warp completion in UpdateAfter (StreamerForm.cs:253-261) to include FPS:

```csharp
if (_pendingAdvanceFrames == 0)
{
    int fps = APIs.EmuClient.GetApproxFramerate();
    byte[] result = new byte[8];  // 4 bytes frames + 4 bytes fps
    BitConverter.GetBytes(advanced).CopyTo(result, 0);
    BitConverter.GetBytes(fps).CopyTo(result, 4);
    var completionMsg = new CommandMessage(
        SubCommand.Response, _pendingAdvanceRequestId,
        new byte[] { CommandStatus.Success,
            result[0], result[1], result[2], result[3],
            result[4], result[5], result[6], result[7] });
    _bridge?.SendResponse(completionMsg);
}
```

#### 4.1.4 Safety: Cleanup on Tool Unload

The existing `Cleanup()` method (StreamerForm.cs:544-560) already restores warp state — verified. No changes needed. It correctly calls `InvisibleEmulation(false)` and restores sound on any exit path.

Add `EnableRewind(true)` and `FrameSkip(0)` to the cleanup path to match the new bypasses:

```csharp
if (_warpModeActive)
{
    try
    {
        APIs.EmuClient.InvisibleEmulation(false);
        APIs.EmuClient.SetSoundOn(_warpSavedSoundOn);
        APIs.EmuClient.EnableRewind(true);   // NEW
        APIs.EmuClient.FrameSkip(0);         // NEW
    }
    catch { }
}
```

### 4.2 Python Controller Enhancements (controller.py)

#### 4.2.1 Chunked Advancement with Progress

Replace the single-call warp block (controller.py:2105-2133) with a chunked loop:

```python
# === Warp mode: chunked bulk advance with progress ===
warp_chunk_size = int(config_payload.get("warp_chunk_size") or WARP_CHUNK_SIZE)

if (
    warp_enabled
    and frames_to_target is not None
    and int(frames_to_target) > warp_threshold
):
    warp_count = int(frames_to_target) - warp_landing_buffer
    if warp_count > 0:
        await self._append_debug_event(
            run_id, "warp_start",
            frames_to_target=int(frames_to_target),
            warp_count=warp_count,
            landing_buffer=warp_landing_buffer,
            chunk_size=warp_chunk_size,
        )
        # Enter warp mode once
        await self._send_lua_warp_control("start")
        await self._set_warp_mode(True)
        self._set_ws_warp_state(True)  # Signal ws_endpoint to drain frames

        remaining = warp_count
        total_advanced = 0
        warp_cancelled = False

        while remaining > 0:
            chunk = min(warp_chunk_size, remaining)
            success = await self._advance_frames_bulk(chunk)
            if not success:
                break
            total_advanced += chunk
            remaining -= chunk

            # Check cancellation
            if self._stop_event.is_set():
                await self._cancel_advance()
                warp_cancelled = True
                break

            # Check if seed was hit during this chunk (re-read bot state)
            if remaining > 0:
                try:
                    raw = await self._read_raw_state(run_id)
                    bot = (raw or {}).get("bot", {})
                    if bot.get("stage") != "rng_seed_wait":
                        break  # Seed hit or stage changed
                except Exception:
                    pass

            # Progress event
            await self._append_debug_event(
                run_id, "warp_progress",
                advanced=total_advanced, remaining=remaining, total=warp_count,
            )

        # Exit warp mode
        self._set_ws_warp_state(False)
        await self._set_warp_mode(False)
        await self._send_lua_warp_control("stop")

        await self._append_debug_event(
            run_id, "warp_complete",
            success=not warp_cancelled,
            total_advanced=total_advanced,
            warp_count=warp_count,
        )
        continue  # Re-read state after warp
# === END warp mode branch ===
```

**Key changes from current code:**
1. `warp_engaged` one-shot flag REMOVED — the outer loop naturally re-evaluates `frames_to_target` after each warp
2. Chunked `while remaining > 0` loop replaces single blocking call
3. Between-chunk seed check prevents overshooting
4. `_stop_event` checked between chunks for cancellation
5. Progress events emitted

#### 4.2.2 New Methods

```python
async def _cancel_advance(self) -> bool:
    """Cancel an in-progress C# frame advance."""
    receiver = self._frame_receiver
    if receiver is None:
        return False
    send_command = getattr(receiver, "send_command", None)
    if not callable(send_command):
        return False
    try:
        result = await send_command(SUB_CANCEL_ADVANCE, b"", 2.0)
    except Exception:
        return False
    return isinstance(result, dict) and int(result.get("status", -1)) == CMD_STATUS_SUCCESS

def _set_ws_warp_state(self, active: bool) -> None:
    """Signal ws_endpoint _send_frames to drain/resume."""
    # Access the shared stream_config via the FrameReceiver's subscriber system
    # Implementation: set a module-level flag on ws_endpoint that _send_frames checks
    from rom_lab.streaming import ws_endpoint
    ws_endpoint.set_warp_active(active)
```

#### 4.2.3 Constants Addition (constants.py)

```python
# Warp optimization
WARP_CHUNK_SIZE: int = 10_000  # Frames per advance_frames_bulk call during chunked warp
```

Add `SUB_CANCEL_ADVANCE: int = 0x0B` to frame_receiver.py constants.

#### 4.2.4 Model Addition (models.py)

Add to `StarterResetStartRequest`:

```python
warp_chunk_size: int = Field(
    default=WARP_CHUNK_SIZE,
    ge=1_000, le=600_000,
    description="Frames per warp chunk (controls progress granularity and cancellation responsiveness)",
)
```

### 4.3 WebSocket Layer Enhancement (ws_endpoint.py)

#### 4.3.1 Module-Level Warp State

Add near top of ws_endpoint.py:

```python
_warp_active: bool = False

def set_warp_active(active: bool) -> None:
    global _warp_active
    _warp_active = active
```

#### 4.3.2 _send_frames Warp Drain Mode

Modify _send_frames (ws_endpoint.py:370-434) to check warp state:

```python
async def _send_frames(ws, queue, stream_config=None):
    if stream_config is None:
        stream_config = _new_stream_config()
    encoder = MjpegEncoder()
    last_sent_monotonic = 0.0

    while True:
        frame = await queue.get()
        frame = _coalesce_latest_frame(queue, frame)

        # WARP DRAIN MODE: consume frames without encoding/sending
        if _warp_active:
            continue  # Drain queue, prevent blocking, skip all work

        # Normal streaming continues unchanged below...
        try:
            max_fps = float(stream_config.get("max_fps", DEFAULT_STREAM_MAX_FPS))
        except (TypeError, ValueError):
            max_fps = DEFAULT_STREAM_MAX_FPS
        # ... rest unchanged
```

This is a minimal change with maximum impact: during warp, frames are consumed from the queue (preventing backpressure) but not encoded or sent. When warp ends, normal streaming resumes immediately.

### 4.4 Error Handling and State Restoration

**Invariant:** BizHawk must NEVER be left in InvisibleEmulation(true) or EnableRewind(false) state after any exit path.

**Protection layers (defense in depth):**
1. Python controller: try/finally around warp block — always calls `_set_warp_mode(False)` and `_set_ws_warp_state(False)`
2. C# StreamerForm.Cleanup(): already restores InvisibleEmulation on tool unload — add EnableRewind/FrameSkip
3. C# StreamerForm constructor: already calls `InvisibleEmulation(false)` on restart — add EnableRewind/FrameSkip
4. Python `_set_warp_mode` timeout: if C# doesn't respond within 2s, Python proceeds (prevents infinite hang)
<!-- ID: directory_structure -->
## Directory Structure

All changes target existing files. No new files are created.

```
csharp/RomLabStreamer/
  StreamerForm.cs          # Warp entry/exit enhancements (EnableRewind, FrameSkip, cancel)
  CommandHandler.cs        # New DoCancelAdvance handler + _cancelAdvance delegate
  Protocol.cs              # Add SUB_CANCEL_ADVANCE = 0x0B constant

src/rom_lab/
  streaming/
    frame_receiver.py      # Add SUB_CANCEL_ADVANCE constant
    ws_endpoint.py         # Add _warp_active flag + set_warp_active() + drain mode
  api/routes/automation/
    controller.py          # Chunked warp loop, _cancel_advance(), _set_ws_warp_state()
    constants.py           # Add WARP_CHUNK_SIZE = 10_000
    models.py              # Add warp_chunk_size field to StarterResetStartRequest

lua/common/bot/runtime.lua              # NO CHANGES (already optimized)
src/rom_lab/plugins/pokemon_fire_red/
  lua/socket_reader.lua                 # NO CHANGES (already optimized)
  lua/reader.lua                        # NO CHANGES (already optimized)
```

### Files NOT Modified (Verified Correct)

| File | Why No Changes |
|------|----------------|
| `runtime.lua` | `_warp_active` gate already skips 103+ RAM reads per frame |
| `socket_reader.lua` | `WARP_MODE` flag already skips state JSON + socket I/O |
| `reader.lua` | File-mode equivalent of socket_reader warp gate |
| `encoder.py` | MJPEG encoder is correct; ws_endpoint drain prevents calls during warp |
<!-- ID: data_storage -->
## Data Storage & State Management

No persistent storage changes. All state is in-memory.

### C# State Fields (StreamerForm.cs)

| Field | Type | Purpose | Lifecycle |
|-------|------|---------|----------|
| `_warpModeActive` | bool | Master warp flag | Existing, unchanged |
| `_pendingAdvanceFrames` | int | Frame countdown | Existing, unchanged |
| `_warpSavedSoundOn` | bool | Saved sound state | Existing, unchanged |
| `_warpSavedVideoEnabled` | bool | Saved video state | Existing, unchanged |
| `_warpSavedRewindEnabled` | bool | Saved rewind state | **NEW** |
| `_warpSavedFrameSkip` | int | Saved frame skip | **NEW** |
| `_cancelAdvance` | Action? | Cancel callback | **NEW** |

All new fields follow the existing save/restore pattern: saved on warp entry, restored on warp exit or cleanup.

### Python State (controller.py)

| State | Type | Purpose |
|-------|------|---------|
| `warp_engaged` | bool | **REMOVED** — one-shot flag replaced by chunked loop |
| `_warp_cancelled` | bool | **NEW** — cancellation flag checked between chunks |

### Python State (ws_endpoint.py)

| State | Type | Purpose |
|-------|------|---------|
| `_warp_active` | bool | **NEW** — module-level flag, gates frame encoding |

### Binary Protocol Additions

| SubCommand | ID | Direction | Payload |
|------------|----|-----------|---------| 
| `CancelAdvance` | `0x0B` | Python -> C# | Empty (just header) |

Response to CancelAdvance reuses existing AdvanceFrames response format with `frames_remaining > 0` indicating early cancellation.
<!-- ID: testing_strategy -->
## Testing Strategy

### Existing Tests (Must Not Regress)

| Test File | Coverage | Gate |
|-----------|----------|------|
| `tests/test_ws_endpoint_commands.py` | WebSocket command routing, warp mode commands | All pass |
| `tests/test_warp_mode.py` | Warp state transitions, advance_frames_bulk | All pass |
| `tests/test_automation_routes.py` | Automation API endpoints, starter reset flow | All pass |

### New Tests Required

#### Phase 1 (C# — verified via manual BizHawk testing)

C# changes are validated through the existing build + deploy + manual probe cycle:
1. `scripts/build-streamer.sh` compiles without error
2. `scripts/build-streamer.sh deploy` copies DLL to BizHawk
3. Manual probe: send `warp_mode on` via WebSocket, verify `GetApproxFramerate()` in response
4. Manual probe: send `cancel_advance` during active warp, verify early termination

No new pytest files for C# — BizHawk integration tests require live emulator.

#### Phase 2 (Python — automated pytest)

**test_ws_endpoint_commands.py additions:**
- `test_warp_active_flag_set_on_warp_mode_on` — verify `set_warp_active(True)` called
- `test_warp_active_flag_cleared_on_warp_mode_off` — verify `set_warp_active(False)` called
- `test_send_frames_drains_during_warp` — mock queue, verify no encode calls when warp active

**test_warp_mode.py additions:**
- `test_chunked_advancement_splits_large_warp` — 25,000 frames -> 3 chunks (10k, 10k, 5k)
- `test_cancel_advance_stops_between_chunks` — set cancel flag, verify early exit
- `test_warp_state_restored_on_error` — raise during chunk, verify cleanup runs
- `test_multi_shot_warp` — verify warp re-engages on subsequent loops (no one-shot)

**test_automation_routes.py additions:**
- `test_starter_reset_warp_chunk_size_param` — verify model accepts warp_chunk_size

#### Phase 3 (Integration — end-to-end with BizHawk)

Manual integration test protocol:
1. Start BizHawk + RomLabStreamer + `rom-lab serve`
2. Start starter reset automation via API
3. Observe warp engage/disengage cycle in logs
4. Verify WebSocket clients see frame freeze during warp (drain mode)
5. Verify WebSocket clients resume frames after warp exit
6. Send cancel during warp, verify graceful termination
7. Run 10 consecutive starter resets without state leaks

### Regression Gate

All existing tests must pass before AND after each phase:
```bash
pytest -q tests/test_ws_endpoint_commands.py tests/test_warp_mode.py tests/test_automation_routes.py
```
<!-- ID: deployment_operations -->
## Deployment & Operations

### Build & Deploy Pipeline

**C# (Phase 1):**
```bash
# 1. Build
scripts/build-streamer.sh

# 2. Deploy to BizHawk
scripts/build-streamer.sh deploy

# 3. Restart BizHawk to load new DLL
# (BizHawk caches external tools — must restart)
```

**Python (Phase 2):**
```bash
# No build step — restart FastAPI server
rom-lab serve

# Or if already running, just restart the process
```

### Validation Sequence (After Each Phase)

```bash
# 1. Run regression tests
pytest -q tests/test_ws_endpoint_commands.py tests/test_warp_mode.py tests/test_automation_routes.py

# 2. Build C# (Phase 1 only)
scripts/build-streamer.sh
scripts/build-streamer.sh deploy

# 3. Restart services
# Restart BizHawk (if C# changed)
# Restart rom-lab serve (if Python changed)

# 4. Manual smoke test
# Send warp_mode on/off via WebSocket
# Verify frame rate telemetry in response
# Run one starter reset cycle
```

### Rollback

All changes are to existing files — standard `git revert` or `git checkout` of specific files.
No database migrations, no config file changes, no new infrastructure.
<!-- ID: open_questions -->
## Open Questions & Risks

### Resolved Through Verification

| Question | Resolution |
|----------|-----------|
| Does C# stream frames during warp? | **NO** — `_videoStreamingEnabled=false` + warp gate returns before CaptureFrame (R2 claim was incorrect) |
| Are Lua scripts already optimized? | **YES** — Both `runtime.lua` and `socket_reader.lua` have warp gates verified in code |
| Is the warp state machine implemented? | **YES** — Full implementation in StreamerForm.cs lines 232-263, 415, 426-445, 544-560 |
| Does InvisibleEmulation exist? | **YES** — Verified via monodis on BizHawk DLLs |

### Open Questions

| # | Question | Impact | Mitigation |
|---|----------|--------|-----------|
| 1 | Does `EnableRewind(false)` measurably improve warp fps? | Low — additive optimization | Benchmark before/after; skip if <5% improvement |
| 2 | Does `FrameSkip(9)` work correctly with `InvisibleEmulation(true)`? | Medium — could cause frame desync | Test empirically; remove if instabilities observed |
| 3 | Is `GetApproxFramerate()` reliable during InvisibleEmulation? | Low — telemetry only | If unreliable, fall back to timing-based fps calculation in Python |
| 4 | Can Config class properties be accessed without reflection? | Low — reflection works | Use reflection as designed; if blocked, skip Config tweaks |
| 5 | What is the optimal WARP_CHUNK_SIZE? | Medium — too small = overhead, too large = unresponsive cancel | Start with 10,000; tune based on measured chunk latency |

### Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| BizHawk API crash on new call combination | Low | High | Save/restore pattern ensures recovery; test incrementally |
| Warp mode leaves BizHawk in bad state | Low | High | 4-layer defense-in-depth restoration (see detailed_design) |
| Performance regression in non-warp path | Very Low | Medium | No non-warp code paths are modified; regression tests gate |
| Cancel command arrives after warp completes | Low | Low | CancelAdvance is a no-op when no advance is pending |
<!-- ID: references_appendix -->
## References & Appendix

### Research Documents

| Document | Key Findings |
|----------|-------------|
| `RESEARCH_CSHARP_STREAMER.md` | Full C# plugin architecture, binary protocol, 55 IEmuClientApi methods via monodis |
| `RESEARCH_PYTHON_PIPELINE.md` | Python warp orchestration, controller flow, ws_endpoint gap (no warp drain) |
| `RESEARCH_BIZHAWK_SPEED.md` | InvisibleEmulation, FrameSkip, EnableRewind, RunLuaDuringTurbo, Config reflection |

### Prior Architecture

| Document | Relevance |
|----------|-----------|
| `warp_mode_frame_advance/ARCHITECTURE_GUIDE.md` | Baseline design — FULLY IMPLEMENTED, this blueprint optimizes it |

### Verified API Methods (monodis-confirmed)

```
IEmuClientApi:
  DoFrameAdvance()
  InvisibleEmulation(bool)
  SpeedMode(int percent)
  GetSoundOn() -> bool
  SetSoundOn(bool)
  EnableRewind(bool)
  FrameSkip(int)
  GetApproxFramerate() -> int
  SaveState(string)
  LoadState(string)

Config (reflection-only):
  RunLuaDuringTurbo -> bool
  MuteFrameAdvance -> bool
  SoundThrottle -> bool
  Unthrottled -> bool
```

### Verified Code Locations

| Component | File | Key Lines |
|-----------|------|-----------|
| Warp state machine | StreamerForm.cs | 232-263 (UpdateAfter gate), 415 (FastUpdateAfter), 426-445 (SetWarpModeActive) |
| Warp cleanup | StreamerForm.cs | 544-560 (Unload handler) |
| Protocol constants | Protocol.cs | SubCommand enum (WarpMode=0x09, AdvanceFrames=0x0A) |
| Python warp commands | frame_receiver.py | SUB_WARP_MODE=0x09, SUB_ADVANCE_FRAMES=0x0A |
| Controller warp block | controller.py | ~2105-2133 (warp engage block) |
| Lua warp gate | runtime.lua | 922 (set_warp_active), 938-953 (tick gate) |
| Socket warp gate | socket_reader.lua | 1735 (WARP_MODE flag), 1830-1850 (heartbeat) |

### Research Discrepancy Log

| Claim (Research) | Reality (Code) | Impact |
|-----------------|----------------|--------|
| R2: "C# keeps sending 60fps ARGB during warp" | C# correctly disables video with `_videoStreamingEnabled=false` + warp gate | Architecture focuses on Python-side drain, not C# video fix |
| R2: "Python ws_endpoint encode/send during warp" | Partially correct — C# sends no frames, but ws_endpoint has no drain logic for queue | Architecture adds drain mode as defense-in-depth |
