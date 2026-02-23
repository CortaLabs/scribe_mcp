---
id: warp_mode_frame_advance-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 warp_mode_frame_advance"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 00:57:51 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — warp_mode_frame_advance
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 00:17:37 UTC

> Execution roadmap for warp_mode_frame_advance.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

### Summary

Warp mode implementation is divided into 6 phases, each self-contained and independently testable. Phases 1-5 are implementation; Phase 6 is empirical verification of 3 unverified BizHawk behaviors.

### Phase Dependency Chain

```
Phase 1: C# Foundation ──┐
                          ├── Phase 4: Controller Integration ── Phase 5: UI Extension
Phase 2: Lua Warp Gate ───┤
                          │
Phase 3: Python Plumbing ─┘

Phase 6: Empirical Verification (independent — can run after Phase 1)
```

**Parallelizable**: Phases 1, 2, 3 have no inter-dependencies and can be implemented in parallel.
**Sequential**: Phase 4 depends on Phases 1+2+3. Phase 5 depends on Phase 4.
**Independent**: Phase 6 only needs Phase 1 (C# commands available).

### Phase Summary Table

| Phase | Name | Files Modified | Estimated Changes | Dependencies |
|-------|------|---------------|-------------------|-------------|
| 1 | C# Foundation | Protocol.cs, CommandHandler.cs, StreamerForm.cs | ~200 lines added | None |
| 2 | Lua Warp Gate | runtime.lua, socket_reader.lua, reader.lua | ~120 lines added | None |
| 3 | Python Plumbing | frame_receiver.py, ws_endpoint.py | ~40 lines added | None |
| 4 | Controller Integration | controller.py, constants.py, models.py | ~150 lines added | 1, 2, 3 |
| 5 | UI Extension | automation.js | ~30 lines added | 4 |
| 6 | Empirical Verification | None (testing only) | 0 lines | 1 |

### Total Estimated Impact

- **~540 lines of new code** across 12 files
- **Zero lines of deleted code** (all changes additive)
- **Zero new files** (all modifications to existing files)
- **1 new test file**: `tests/test_warp_mode.py`
<!-- ID: phase_0 -->
## Phase 1 — C# Foundation

**Objective:** Add warp mode state machine and two new SubCommands to the C# streamer DLL.

**Dependencies:** None (first phase, no prior work required)

**Files Modified:** `Protocol.cs`, `CommandHandler.cs`, `StreamerForm.cs`

### Task Package 1.1: Protocol Constants

**Scope:** Add two SubCommand constants to Protocol.cs

**File:** `csharp/RomLabStreamer/Protocol.cs`

**Specifications:**
1. Add `public const byte WarpMode = 0x09;` after existing SubCommand constants (line ~75)
2. Add `public const byte AdvanceFrames = 0x0A;` immediately after WarpMode

**Verification:**
- [ ] `dotnet build` succeeds with zero warnings
- [ ] Constants do not collide with existing 0x01-0x08 range

**Out of Scope:** Do NOT modify any other constants or enums.

---

### Task Package 1.2: StreamerForm Warp State Machine

**Scope:** Add warp state fields, warp gate in UpdateAfter(), and two new methods to StreamerForm.cs

**File:** `csharp/RomLabStreamer/StreamerForm.cs`

**Specifications:**

1. Add private fields after existing fields (~line 30):
```csharp
private bool _warpModeActive = false;
private int _pendingAdvanceFrames = 0;
private bool _savedVideoStreamingEnabled;
private bool _savedSoundOn;
```

2. Add warp gate at TOP of `UpdateAfter()` method, BEFORE existing work items (~line 211):
```csharp
// Warp gate: process pending frame advances before normal work
if (_pendingAdvanceFrames > 0)
{
    _pendingAdvanceFrames--;
    if (_pendingAdvanceFrames == 0)
    {
        // Warp batch complete — restore normal state
        _videoStreamingEnabled = _savedVideoStreamingEnabled;
        _apis.EmuClient.SetSoundOn(_savedSoundOn);
        // Speed remains at warp speed; Python controller manages speed transitions
    }
    return; // Skip ALL normal UpdateAfter work during warp
}
```

3. Add `SetWarpModeActive(bool active)` method:
```csharp
public void SetWarpModeActive(bool active)
{
    _warpModeActive = active;
    if (active)
    {
        _savedVideoStreamingEnabled = _videoStreamingEnabled;
        _savedSoundOn = _apis.EmuClient.GetSoundOn();
        _videoStreamingEnabled = false;
        _apis.EmuClient.SetSoundOn(false);
        _apis.EmuClient.SpeedMode(6400); // Max warp speed
    }
    else
    {
        _videoStreamingEnabled = _savedVideoStreamingEnabled;
        _apis.EmuClient.SetSoundOn(_savedSoundOn);
        _apis.EmuClient.SpeedMode(100); // Restore normal speed
    }
}
```

4. Add `StartAdvanceFrames(int count)` method:
```csharp
public void StartAdvanceFrames(int count)
{
    if (count <= 0) return;
    if (!_warpModeActive)
    {
        // Auto-enable warp for duration of advance
        SetWarpModeActive(true);
    }
    _pendingAdvanceFrames = count;
    // Frames will be consumed one-per-UpdateAfter via the warp gate
}
```

5. Add two delegate lambdas to constructor (~line 178, after existing delegates):
```csharp
_handler = new CommandHandler(
    // ... existing 6 delegates ...
    (active) => SetWarpModeActive(active),        // setWarpModeActive
    () => _warpModeActive,                         // getWarpModeActive
    (count) => StartAdvanceFrames(count)           // startAdvanceFrames
);
```

**Verification:**
- [ ] `dotnet build` succeeds
- [ ] UpdateAfter warp gate is the FIRST code in the method (before frame count check)
- [ ] SetWarpModeActive saves/restores video and sound state
- [ ] Constructor passes 9 delegates (was 6)

**Out of Scope:** Do NOT modify FastUpdateAfter(). Do NOT change existing video gating logic.

---

### Task Package 1.3: CommandHandler Warp Handlers

**Scope:** Add DoWarpMode and DoAdvanceFrames handlers, new delegate fields, raise MaxSpeedPercent

**File:** `csharp/RomLabStreamer/CommandHandler.cs`

**Specifications:**

1. Raise `MaxSpeedPercent` from 5000 to 6400 (line 47):
```csharp
private const int MaxSpeedPercent = 6400;
```

2. Add three new delegate fields after existing delegates (~line 40):
```csharp
private readonly Action<bool> _setWarpModeActive;
private readonly Func<bool> _getWarpModeActive;
private readonly Action<int> _startAdvanceFrames;
```

3. Update constructor to accept 3 additional parameters and assign to fields.

4. Add `DoWarpMode` handler after existing `DoSetSpeed` method:
```csharp
private void DoWarpMode(byte[] data)
{
    bool enable = data.Length > 0 && data[0] != 0;
    _setWarpModeActive(enable);
    var response = new { warp_mode = _getWarpModeActive(), status = "ok" };
    SendJsonResponse(SubCommand.WarpMode, response);
}
```

5. Add `DoAdvanceFrames` handler:
```csharp
private void DoAdvanceFrames(byte[] data)
{
    int frameCount = 0;
    if (data.Length >= 4)
    {
        frameCount = BitConverter.ToInt32(data, 0);
    }
    if (frameCount <= 0 || frameCount > 100000)
    {
        SendJsonResponse(SubCommand.AdvanceFrames, new { error = "invalid_frame_count", requested = frameCount });
        return;
    }
    _startAdvanceFrames(frameCount);
    SendJsonResponse(SubCommand.AdvanceFrames, new { frames_queued = frameCount, status = "ok" });
}
```

6. Add case statements in the command dispatch switch (~HandleCommand method):
```csharp
case SubCommand.WarpMode:
    DoWarpMode(payload);
    break;
case SubCommand.AdvanceFrames:
    DoAdvanceFrames(payload);
    break;
```

**Verification:**
- [ ] `dotnet build` succeeds
- [ ] MaxSpeedPercent is 6400
- [ ] Constructor accepts 9 parameters (was 6)
- [ ] DoWarpMode sends JSON response with `warp_mode` field
- [ ] DoAdvanceFrames validates frame count range [1, 100000]
- [ ] Both new SubCommands are in the dispatch switch

**Out of Scope:** Do NOT modify existing DoFrameAdvance, DoSetSpeed, or any other handler.

---

## Phase 2 — Lua Warp Gate

**Objective:** Add warp-aware gating to Lua runtime and both reader scripts to skip expensive per-frame reads during warp.

**Dependencies:** None (independent of Phase 1)

**Files Modified:** `lua/common/bot/runtime.lua`, `plugins/pokemon_fire_red/lua/socket_reader.lua`, `plugins/pokemon_fire_red/lua/reader.lua`

### Task Package 2.1: Runtime Warp Gate

**Scope:** Add warp flag and warp gate to runtime.lua M.tick()

**File:** `lua/common/bot/runtime.lua`

**Specifications:**

1. Add module-level warp flag (~after line 10):
```lua
local _warp_active = false
```

2. Add accessor functions to M table:
```lua
function M.set_warp_active(active)
    _warp_active = active
end

function M.is_warp_active()
    return _warp_active
end
```

3. Add warp gate in `M.tick()` at line ~924, AFTER the `INPUT_BUSY` check but BEFORE `read_context_signals()`:
```lua
-- Warp gate: skip signal reading during warp, only check seed
if _warp_active then
    -- Single RAM read: gRngValue at 0x03005000
    local rng = memory.read_u32_le(0x03005000, "System Bus")
    -- Check if seed matches target (if target is set)
    if _target_seed and rng == _target_seed then
        _warp_active = false
        -- Fall through to normal tick to process the match
    else
        return  -- Skip all other processing during warp
    end
end
```

**Note:** The exact target_seed mechanism depends on how the bot runtime stores the target. The coder should inspect the existing `_current_seed()` function and target comparison logic to wire this correctly.

**Verification:**
- [ ] `luac -p lua/common/bot/runtime.lua` passes
- [ ] Warp gate is AFTER INPUT_BUSY check and BEFORE read_context_signals()
- [ ] Only 1 RAM read during warp (vs 103+ normally)
- [ ] Seed match exits warp and falls through to normal processing

**Out of Scope:** Do NOT modify read_context_signals() itself. Do NOT change any existing logic paths.

---

### Task Package 2.2: Socket Reader Warp Gate

**Scope:** Add WARP_MODE flag, warp gate in on_frame(), and warp_control command handler to socket_reader.lua

**File:** `plugins/pokemon_fire_red/lua/socket_reader.lua`

**Specifications:**

1. Add module-level warp flag near top of file:
```lua
local WARP_MODE = false
```

2. Add warp gate at top of `on_frame()` function, BEFORE full state assembly:
```lua
if WARP_MODE then
    _frame_count = _frame_count + 1
    -- Heartbeat every 30 frames
    if _frame_count % 30 == 0 then
        local rng = memory.read_u32_le(0x03005000, "System Bus")
        local heartbeat = json.encode({
            warp = true,
            frame = emu.framecount(),
            rng = string.format("0x%08X", rng)
        })
        comm.socketServerSend(heartbeat)
    end
    return  -- Skip full state assembly
end
```

3. Add `warp_control` case in `execute_command()` function:
```lua
elseif cmd_type == "warp_control" then
    local enable = cmd.enable
    WARP_MODE = (enable == true)
    -- Also propagate to runtime if available
    if runtime and runtime.set_warp_active then
        runtime.set_warp_active(WARP_MODE)
    end
    local response = json.encode({
        type = "warp_control_response",
        warp_mode = WARP_MODE,
        status = "ok"
    })
    comm.socketServerSend(response)
```

**Verification:**
- [ ] `luac -p plugins/pokemon_fire_red/lua/socket_reader.lua` passes
- [ ] Warp gate skips full state assembly
- [ ] Heartbeat sends every 30 frames with rng value
- [ ] warp_control command toggles WARP_MODE flag

**Out of Scope:** Do NOT modify existing command handlers. Do NOT change state assembly logic.

---

### Task Package 2.3: File Reader Warp Gate (Mirror)

**Scope:** Mirror warp changes from socket_reader.lua to reader.lua per lua-reader-sync rule

**File:** `plugins/pokemon_fire_red/lua/reader.lua`

**Specifications:**

1. Add identical `WARP_MODE` flag
2. Add identical warp gate in the file-mode equivalent of on_frame()
3. Add identical warp_control command handler (using file-based command mechanism instead of socket)
4. Heartbeat writes to a file instead of socket send

**CRITICAL: lua-reader-sync rule** — Both files MUST be updated together. The warp gate logic must be functionally identical.

**Verification:**
- [ ] `luac -p plugins/pokemon_fire_red/lua/reader.lua` passes
- [ ] WARP_MODE flag exists and defaults to false
- [ ] Warp gate logic matches socket_reader.lua (same heartbeat interval, same skip behavior)

**Out of Scope:** Do NOT modify any non-warp logic in reader.lua.

---

## Phase 3 — Python Plumbing

**Objective:** Add SubCommand constants and WebSocket command routing for warp mode.

**Dependencies:** None (independent of Phases 1-2)

**Files Modified:** `src/rom_lab/streaming/frame_receiver.py`, `src/rom_lab/streaming/ws_endpoint.py`

### Task Package 3.1: Frame Receiver Constants

**Scope:** Add two SubCommand constants to frame_receiver.py

**File:** `src/rom_lab/streaming/frame_receiver.py`

**Specifications:**

1. Add after existing SUB constants (line ~34):
```python
SUB_WARP_MODE: int = 0x09
SUB_ADVANCE_FRAMES: int = 0x0A
```

**Verification:**
- [ ] `pytest -q tests/test_frame_receiver.py` passes (existing tests unaffected)
- [ ] Constants match Protocol.cs values exactly (0x09, 0x0A)

**Out of Scope:** Do NOT modify any existing constants or methods.

---

### Task Package 3.2: WebSocket Command Routing

**Scope:** Add warp_mode and advance_frames command handling to ws_endpoint.py

**File:** `src/rom_lab/streaming/ws_endpoint.py`

**Specifications:**

1. Import new constants:
```python
from .frame_receiver import SUB_WARP_MODE, SUB_ADVANCE_FRAMES
```

2. Add command routing in the WebSocket message handler (same pattern as existing commands):
```python
elif command == "warp_mode":
    enable = data.get("enable", False)
    payload = bytes([1 if enable else 0])
    response = await self._send_command(SUB_WARP_MODE, payload)
    await websocket.send_json(response)

elif command == "advance_frames":
    count = data.get("count", 0)
    payload = count.to_bytes(4, byteorder="little")
    response = await self._send_command(SUB_ADVANCE_FRAMES, payload)
    await websocket.send_json(response)
```

**Verification:**
- [ ] `pytest -q tests/test_ws_endpoint_commands.py` passes (existing tests unaffected)
- [ ] New commands follow same pattern as existing command handlers
- [ ] Payload encoding matches C# expectations (byte for warp, int32LE for frames)

**Out of Scope:** Do NOT modify existing command handlers. Do NOT add tests yet (tests in Phase 4).
<!-- ID: phase_1 -->
## Phase 4 — Controller Integration

**Objective:** Wire warp mode into the Python automation controller, adding the orchestration logic that decides when to warp and when to land.

**Dependencies:** Phases 1, 2, 3 (C# commands, Lua gates, Python plumbing all required)

**Files Modified:** `controller.py`, `constants.py`, `models.py`, optionally `state_factories.py`

### Task Package 4.1: Warp Constants

**Scope:** Add warp-related configuration constants

**File:** `src/rom_lab/api/routes/automation/constants.py`

**Specifications:**

1. Add after existing accel constants (~line 44):
```python
# Warp mode defaults
DEFAULT_WARP_MODE_ENABLED: bool = False
DEFAULT_WARP_THRESHOLD_FRAMES: int = 5000
DEFAULT_WARP_LANDING_BUFFER_FRAMES: int = 1200  # Must match accel_near_target_frames
WARP_MAX_FRAMES_PER_CALL: int = 50000
```

**Verification:**
- [ ] `DEFAULT_WARP_MODE_ENABLED` is False (zero regression)
- [ ] `DEFAULT_WARP_LANDING_BUFFER_FRAMES` matches existing `accel_near_target_frames` default (1200)
- [ ] `WARP_MAX_FRAMES_PER_CALL` is 50000 (safe upper bound)

**Out of Scope:** Do NOT modify existing constants.

---

### Task Package 4.2: Model Fields

**Scope:** Add optional warp configuration fields to StarterResetStartRequest

**File:** `src/rom_lab/api/routes/automation/models.py`

**Specifications:**

1. Add fields to `StarterResetStartRequest` class:
```python
warp_mode_enabled: bool = Field(
    default=False,
    description="Enable warp mode for bulk frame advancement during seed targeting"
)
warp_threshold_frames: int = Field(
    default=5000,
    ge=1000,
    description="Minimum frames-to-target to activate warp mode"
)
warp_landing_buffer_frames: int = Field(
    default=1200,
    ge=100,
    description="Frames before target where warp exits and precision landing begins"
)
```

**Verification:**
- [ ] Existing tests pass (fields have defaults, so no breaking changes)
- [ ] `StarterResetStartRequest()` with no warp fields still works
- [ ] `StarterResetStartRequest(warp_mode_enabled=True)` accepted

**Out of Scope:** Do NOT modify existing fields. Do NOT add validation beyond what's specified.

---

### Task Package 4.3: Controller Warp Methods

**Scope:** Add warp control methods and integrate warp into the seed-targeting loop

**File:** `src/rom_lab/api/routes/automation/controller.py`

**Specifications:**

1. Add imports at top (~line 117):
```python
from ..streaming.frame_receiver import SUB_WARP_MODE, SUB_ADVANCE_FRAMES
```

2. Add `_set_warp_mode(self, enable: bool) -> dict` method (pattern from `_set_emu_speed_percent`):
```python
async def _set_warp_mode(self, enable: bool) -> dict:
    """Enable/disable warp mode on C# streamer."""
    payload = bytes([1 if enable else 0])
    return await self._send_sub_command(SUB_WARP_MODE, payload)
```

3. Add `_advance_frames_bulk(self, count: int) -> dict` method:
```python
async def _advance_frames_bulk(self, count: int) -> dict:
    """Request C# to advance count frames in warp mode."""
    clamped = min(count, WARP_MAX_FRAMES_PER_CALL)
    payload = clamped.to_bytes(4, byteorder="little")
    return await self._send_sub_command(SUB_ADVANCE_FRAMES, payload)
```

4. Add `_send_lua_warp_control(self, enable: bool) -> None` method:
```python
async def _send_lua_warp_control(self, enable: bool) -> None:
    """Send warp_control command to Lua via MCP."""
    await self._send_mcp_command({
        "type": "warp_control",
        "enable": enable
    })
```

5. Integrate warp into `_wait_for_lua_bot_candidate()` at the warp insertion point (~line 2042):

Before the existing speed control logic (`if frames_to_target > ...`), add:

```python
# Warp mode: bulk advance when far from target
if (self._warp_mode_enabled
    and frames_to_target > self._warp_landing_buffer_frames
    and frames_to_target > self._warp_threshold_frames):
    
    warp_frames = frames_to_target - self._warp_landing_buffer_frames
    logger.info(f"Warp: advancing {warp_frames} frames (target in {frames_to_target})")
    
    # Enable warp on both C# and Lua sides
    await self._set_warp_mode(True)
    await self._send_lua_warp_control(True)
    
    # Advance in bulk
    await self._advance_frames_bulk(warp_frames)
    
    # Wait for advance to complete (poll frame count or use response)
    # Implementation detail: coder determines best polling mechanism
    
    # Disable warp, resume normal speed control
    await self._send_lua_warp_control(False)
    await self._set_warp_mode(False)
    
    # Continue to existing speed control for precision landing
```

6. Store warp config from request model in controller instance:
```python
self._warp_mode_enabled = getattr(request, 'warp_mode_enabled', False)
self._warp_threshold_frames = getattr(request, 'warp_threshold_frames', DEFAULT_WARP_THRESHOLD_FRAMES)
self._warp_landing_buffer_frames = getattr(request, 'warp_landing_buffer_frames', DEFAULT_WARP_LANDING_BUFFER_FRAMES)
```

**Verification:**
- [ ] `pytest -q tests/test_automation_routes.py` passes (warp disabled by default)
- [ ] `_set_warp_mode` follows same pattern as `_set_emu_speed_percent`
- [ ] `_advance_frames_bulk` clamps to WARP_MAX_FRAMES_PER_CALL
- [ ] Warp branch only executes when `_warp_mode_enabled=True` AND `frames_to_target > threshold`
- [ ] Both C# and Lua warp are enabled before advance and disabled after

**Out of Scope:** Do NOT modify existing speed control logic. The warp branch executes BEFORE existing speed logic and falls through to it for precision landing.

---

### Task Package 4.4: Warp Mode Tests

**Scope:** Create test file for warp mode constants and model validation

**File:** `tests/test_warp_mode.py` (NEW FILE)

**Specifications:**

Create tests as specified in ARCHITECTURE_GUIDE testing_strategy section:

1. `test_warp_constants_no_collision` — All SUB_* constants are unique
2. `test_warp_default_disabled` — DEFAULT_WARP_MODE_ENABLED is False
3. `test_warp_model_fields_optional` — StarterResetStartRequest works without warp fields
4. `test_warp_model_fields_explicit` — StarterResetStartRequest accepts warp_mode_enabled=True
5. `test_warp_threshold_positive` — DEFAULT_WARP_THRESHOLD_FRAMES > 0
6. `test_warp_landing_buffer_matches_accel` — Landing buffer matches accel_near_target_frames

**Verification:**
- [ ] `pytest -q tests/test_warp_mode.py` passes
- [ ] No new test fixtures required (pure unit tests)

**Out of Scope:** Do NOT add integration tests (require emulator). Do NOT modify existing test files.

---

## Phase 5 — UI Extension

**Objective:** Extend the automation.js warp display to show warp status to the user.

**Dependencies:** Phase 4 (controller integration must be complete)

**Files Modified:** `.council/web/static/js/automation.js`

### Task Package 5.1: Warp Status Display

**Scope:** Add visual warp indicator and extend existing _setWarpMode() function

**File:** `.council/web/static/js/automation.js`

**Specifications:**

1. Add `_updateWarpStatusDisplay()` function that shows/hides a "WARP" badge in the automation UI when warp mode is active.

2. Extend the existing `_setWarpMode()` function (~line 1088) to call `_updateWarpStatusDisplay()` after toggling warp state.

3. The warp indicator should:
   - Show "WARP" text with a distinctive color (e.g., cyan glow matching the existing UI theme)
   - Be visible in the automation status area
   - Disappear when warp mode is disabled

**Note:** The exact visual design is left to the coder. The existing `_warpModeActive` flag at line 114 is already present and should be reused.

**Verification:**
- [ ] No JavaScript errors in browser console
- [ ] Warp indicator appears when `_warpModeActive` is true
- [ ] Warp indicator disappears when `_warpModeActive` is false
- [ ] Existing warp logic (video stream management) unchanged

**Out of Scope:** Do NOT modify backend code. Do NOT add new WebSocket commands.

---

## Phase 6 — Empirical Verification

**Objective:** Test 3 unverified BizHawk behaviors that cannot be confirmed from source code alone.

**Dependencies:** Phase 1 (C# commands must be available for testing)

**Files Modified:** None (testing only — results may inform future optimizations)

### Task Package 6.1: InvisibleEmulation Test

**Scope:** Determine if InvisibleEmulation(true) suppresses video buffer writes

**Procedure:**
1. Boot BizHawk with streamer tool loaded
2. Start video streaming, confirm frames arriving
3. Call `InvisibleEmulation(true)` via C# handler
4. Monitor GetVideoBuffer() output — does it still return new frame data?
5. Document findings

**Pass Criteria:** Document whether InvisibleEmulation affects video buffer (yes/no) and by how much

**Outcome:** If InvisibleEmulation does suppress buffer writes, add it to SetWarpModeActive() enter sequence. If not, remove the reference from architecture.

---

### Task Package 6.2: SetSoundOn Overhead Test

**Scope:** Determine if SetSoundOn(false) reduces CPU usage during warp

**Procedure:**
1. Measure frame advance rate with sound on
2. Measure frame advance rate with sound off
3. Compare throughput

**Pass Criteria:** Document percentage improvement (if any) from disabling sound

**Outcome:** If no measurable improvement, simplify warp enter/exit by removing sound toggling.

---

### Task Package 6.3: Maximum SpeedMode Test

**Scope:** Determine highest stable SpeedMode percentage

**Procedure:**
1. Test SpeedMode(1000) — stable for 60 seconds?
2. Test SpeedMode(2000) — stable?
3. Test SpeedMode(4000) — stable?
4. Test SpeedMode(6400) — stable?
5. If 6400 fails, binary search for maximum stable value

**Pass Criteria:** Identify the highest SpeedMode value that runs stably for 60+ seconds

**Outcome:** Set MAX_WARP_SPEED_PERCENT in C# to the verified maximum.
<!-- ID: milestone_tracking -->
## Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| M1: C# warp commands build clean | Phase 1 | Forge | Pending | `dotnet build` output |
| M2: Lua syntax passes all 3 files | Phase 2 | Forge | Pending | `luac -p` output |
| M3: Python constants added, tests pass | Phase 3 | Forge | Pending | `pytest` output |
| M4: Controller warp methods + new tests pass | Phase 4 | Forge | Pending | `pytest tests/test_warp_mode.py` |
| M5: UI warp indicator visible | Phase 5 | Forge | Pending | Browser screenshot |
| M6: All 3 BizHawk behaviors documented | Phase 6 | Forge | Pending | Test log entries |
| M7: Full regression suite passes | Post-all | Forge | Pending | Full `pytest` + `dotnet build` |
| M8: Live warp test — seed acquired faster than non-warp | Post-all | Manual | Pending | Timing comparison |

### Implementation Wave Plan

For team orchestration, phases can be grouped into waves:

**Wave 1 (Parallel):** Phases 1, 2, 3 — no dependencies between them
- 3 Forge agents can work simultaneously
- Each has bounded scope (1-3 files, clear verification)

**Wave 2 (Sequential):** Phase 4 — depends on Wave 1 completion
- Single Forge agent
- Largest phase (~150 lines)
- Requires all Wave 1 artifacts

**Wave 3 (Sequential):** Phase 5 — depends on Phase 4
- Single Forge agent
- Smallest phase (~30 lines)
- UI only, no backend changes

**Wave 4 (Independent):** Phase 6 — only needs Phase 1
- Can run any time after Wave 1
- Manual testing, no code changes
- Documents findings for future optimization
<!-- ID: retro_notes -->
## Retro Notes and Adjustments

### Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BizHawk crashes at SpeedMode(6400) | Medium | High | Phase 6 tests first; fall back to lower value |
| Re-entrant DoFrameAdvance crashes | Low | Critical | State machine pattern prevents this by design |
| Lua warp gate misses seed match | Low | High | Single RAM read per frame guarantees check |
| Video stream doesn't resume after warp | Medium | Medium | Explicit restore in SetWarpModeActive(false) |
| Two-channel race condition | Low | Medium | Sequenced by Python controller, different state |

### Architecture Decisions Log

| Decision | Alternatives Considered | Rationale |
|----------|------------------------|-----------|
| State machine in C# | Inline loop, async task | Prevents re-entrant emulator calls |
| Two-phase warp | Single-speed approach | Precision landing requires normal speed control |
| Boolean flag gating | Config file toggle | Simpler, no I/O, defaults to off |
| 1200-frame landing buffer | 600, 2400 | Matches existing accel_near_target_frames |
| Heartbeat every 30 frames | 10, 60, event-driven | Balances visibility with minimal overhead |
| SubCommand 0x09/0x0A | Higher values | Next available in sequential order |

### Post-Implementation Review Criteria

After all phases complete, Arbiter should verify:

1. **Zero regression**: All pre-existing tests pass without modification
2. **Default off**: System behaves identically to pre-warp when warp_mode_enabled=False
3. **Clean separation**: Warp code is cleanly gated, not interleaved with existing logic
4. **Lua sync**: Both reader files have identical warp logic
5. **No new files**: All changes are modifications to existing files (except test_warp_mode.py)
6. **Protocol alignment**: C# SubCommand values match Python SUB_* constants exactly
