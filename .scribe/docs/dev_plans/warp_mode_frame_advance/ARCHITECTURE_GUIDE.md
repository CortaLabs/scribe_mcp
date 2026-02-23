---
id: warp_mode_frame_advance-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 warp_mode_frame_advance"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 00:54:26 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — warp_mode_frame_advance
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 00:17:37 UTC

> Architecture guide for warp_mode_frame_advance.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** The starter automation bot targets specific RNG seeds to snipe Pokemon with desired IVs/natures in Pokemon Fire Red. During the `rng_seed_wait` stage, it must advance thousands of frames (often 50,000-300,000+) from the current RNG state to the target seed. The current approach uses `SpeedMode` (speed throttle up to 3000-5000%) but hits an effective throughput ceiling of approximately 260% real-time speed.

**Root Cause:** Per-frame overhead dominates at high speed settings, nullifying the speed multiplier:
- **Lua:** ~104 RAM reads per frame from `read_context_signals()` (96 of which scan text printers), plus full game state serialization (~400+ reads) and blocking socket I/O every 30 frames.
- **C#:** `UpdateAfter()` runs every frame with video capture, audio capture, TCP queue push, command drain, and UI label updates.
- **BizHawk:** `DoFrameAdvance()` includes throttle (`StepRunLoop_Throttle`) and render (`Render()`) on every call.

**Goal:** Implement a warp mode that bypasses all non-essential per-frame work during bulk frame advancement, then seamlessly transitions to precise speed control for the final approach to the target seed. Target: 10-50x throughput improvement over current speed-throttle approach.

**Critical Constraint:** Warp mode MUST NOT break regular stream mode. The existing BizHawk streaming pipeline (C# External Tool -> TCP -> Python -> WebSocket -> Browser) that shows live video, handles commands, and supports the AI agent console must work exactly as before when warp is off. Zero regression.

**Research Base:** 4 research documents (RESEARCH_BIZHAWK_API, RESEARCH_CSHARP_STREAMER_20260222, RESEARCH_LUA_WARP_20260222_0021, RESEARCH_CONTROLLER_WARP) totaling ~1,500 lines. All claims verified against source code with 0 discrepancies.
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Functional Requirements:**
1. Bulk frame advancement: advance N frames with minimal per-frame overhead (target: 1 RAM read/frame vs current ~104).
2. Seamless mode transition: warp -> precision speed control within the same attempt cycle.
3. Warp progress reporting: periodic heartbeat during warp with RNG state and frame count.
4. Warp cancellation: ability to abort a warp in progress from Python or browser.
5. Seed-match detection during warp: Lua must still check `gRngValue` every frame and trigger immediately on match.
6. Safe warp exit: full state refresh after warp completes (signals, game state, socket sync).
7. Configurable: warp on/off, threshold frames, landing buffer — all as API request parameters.

**Non-Functional Requirements:**
1. Zero regression: when warp is off, every existing feature works identically.
2. No re-entrant emulator calls: C# must use state machine pattern, not inline loops.
3. Lua reader sync: both `socket_reader.lua` and `reader.lua` updated (per `lua-reader-sync` rule).
4. BizHawk API methods: only monodis-verified method names used (per `bizhawk-api-discovery` rule).

**Constraints:**
- BizHawk has no native bulk frame advance API. `DoFrameAdvance()` must be called N times individually.
- `DoFrameAdvance()` includes `Render()` + `StepRunLoop_Throttle()` — `InvisibleEmulation(true)` bypasses render, `SpeedMode(6400)` minimizes throttle.
- Lua `event.onframeend` fires on every `DoFrameAdvance()` call — cannot be suppressed. Must gate expensive work in Lua with a boolean flag.
- C# External Tool runs on emulator thread — no background threading allowed for frame advance.
- TCP bridge must not overflow during warp (video/audio streaming disabled).
- 3 BizHawk API behaviors are UNVERIFIED and require empirical testing:
  - Does `InvisibleEmulation(true)` suppress `UpdateAfter()` calls in External Tool?
  - Does `DoFrameAdvanceAndUnpause()` include Render+Throttle like `DoFrameAdvance()`?
  - Is it safe to loop `DoFrameAdvance()` N times within a single `UpdateAfter()` call?
<!-- ID: architecture_overview -->
## 3. Architecture Overview

### System Data Flow — Normal Mode vs Warp Mode

```
NORMAL MODE (current — default, always active when warp is off):
  BizHawk DoFrameAdvance()
    -> Lua event.onframeend -> socket_reader.on_frame()
       -> bot_runtime.tick()        [~104 RAM reads: signals + seed]
       -> read_game_state()         [~400+ reads every 30 frames]
       -> comm.socketServerSend()   [blocking socket I/O]
    -> C# UpdateAfter()
       -> DrainCommands()           [command processing]
       -> FrameCapture.CaptureFrame [video buffer copy]
       -> AudioCapture.CaptureSamples [audio samples]
       -> TcpBridge.QueueFrame      [TCP send queue]

WARP MODE (new — engaged only during rng_seed_wait with frames_to_target > threshold):
  BizHawk DoFrameAdvance() [with InvisibleEmulation(true), SetSoundOn(false), SpeedMode(6400)]
    -> Lua event.onframeend -> socket_reader.on_frame()
       -> inp.process()             [input drain — always runs]
       -> bot_runtime.tick()        [1 RAM read: gRngValue only]
       -> SKIP: read_game_state, socket I/O, event detection
       -> Heartbeat every 30 frames [3-field JSON: warp, frame, rng]
    -> C# UpdateAfter()
       -> _pendingAdvanceFrames > 0: decrement, skip ALL normal work
       -> DrainCommandsOnly()       [check for cancel command only]
       -> Progress event every 500 frames [TCP response to Python]
       -> return early              [no video, no audio, no UI update]
```

### Component Interaction Diagram

```
                    Python Controller
                    controller.py:_wait_for_lua_bot_candidate()
                           |
           +-----------+---+-----------+
           |                           |
    Channel 1: TCP              Channel 2: MCP Socket
    frame_receiver ->           mcp_manager ->
    C# CommandHandler           Lua socket_reader
           |                           |
    [SUB_WARP_MODE 0x09]        [warp_control cmd]
    [SUB_ADVANCE_FRAMES 0x0A]   [bot_control cmd]
           |                           |
    StreamerForm.UpdateAfter    runtime.lua M.tick()
    _pendingAdvanceFrames       _warp_active guard
    state machine               1 RAM read/frame
```

### Two-Phase Warp Approach

**Phase A — Bulk Warp** (frames_to_target > warp_threshold):
1. Python sends `warp_control:start` to Lua (sets `_warp_active=true`, skips signals)
2. Python sends `SUB_WARP_MODE:enable` to C# (disables video/audio, enables InvisibleEmulation)
3. Python sends `SUB_ADVANCE_FRAMES:N` to C# (N = frames_to_target - landing_buffer)
4. C# state machine advances N frames, one per UpdateAfter tick, minimal work per frame
5. C# sends progress events every 500 frames
6. C# sends completion response when done

**Phase B — Precision Landing** (frames_to_target <= landing_buffer):
1. Python sends `SUB_WARP_MODE:disable` to C# (restores video/audio/render)
2. Python sends `warp_control:stop` to Lua (restores full tick with signals)
3. Existing speed control takes over: `accel_precision_speed_percent` (400%)
4. Lua detects exact seed match on the frame it occurs, queues A press immediately

### Seamless Coexistence Guarantee

Every warp change is gated by a boolean flag that defaults to `false`:
- C#: `_warpModeActive` in StreamerForm — `false` means UpdateAfter runs exactly as today
- Lua: `_warp_active` in runtime.lua — `false` means `read_context_signals()` runs every tick
- Lua: `WARP_MODE` in socket_reader.lua — `false` means full state reads + socket I/O continue
- Python: `warp_mode_enabled` in request config — `false` means speed-only acceleration (current behavior)
- JS: `_warpModeActive` already exists — currently manages video stream, extended for warp status display

When ALL flags are `false` (default): the system behaves identically to the pre-warp codebase.
<!-- ID: detailed_design -->
## 4. Detailed Design — Layer by Layer

### 4.1 C# Streamer Layer (Protocol + CommandHandler + StreamerForm)

#### 4.1.1 Protocol Extensions (`Protocol.cs`)

Add two new SubCommand constants after `GetStreamState = 0x08` (line 37):

```csharp
// Warp Mode (Phase: warp_mode_frame_advance)
public const byte WarpMode       = 0x09;  // Toggle warp state: [Enabled:1] -> [Status:1][Enabled:1]
public const byte AdvanceFrames  = 0x0A;  // Bulk advance: [Count:4 LE] -> [Status:1][Advanced:4 LE]
```

Wire format:
- `WarpMode (0x09)`: Request data = `[enabled:1byte]` (0=off, 1=on). Response = `[status:1][enabled:1]`.
- `AdvanceFrames (0x0A)`: Request data = `[count:4byte LE uint32]`. Response = `[status:1][frames_advanced:4byte LE uint32]`. Progress events sent as unsolicited responses during execution: `[status:1][advanced:4 LE][total:4 LE]`.

#### 4.1.2 StreamerForm State Machine (`StreamerForm.cs`)

Add new fields (after `_videoStreamingEnabled`, around line 55):

```csharp
// Warp mode state machine
private bool _warpModeActive = false;
private int _pendingAdvanceFrames = 0;
private int _pendingAdvanceTotalFrames = 0;
private ushort _pendingAdvanceRequestId = 0;
private const int WarpProgressInterval = 500;  // Send progress every N frames
private bool _warpSavedSoundOn = true;
private bool _warpSavedVideoEnabled = true;
```

Modify `UpdateAfter()` — insert warp gate at TOP (line 211, after `_frameCount++`):

```csharp
protected override void UpdateAfter()
{
    _frameCount++;

    // === WARP GATE: skip all normal work during bulk advance ===
    if (_pendingAdvanceFrames > 0)
    {
        _pendingAdvanceFrames--;
        int advanced = _pendingAdvanceTotalFrames - _pendingAdvanceFrames;

        // Drain commands only (check for cancel/abort)
        if (_commandHandler != null)
            _commandHandler.DrainCommandsLightweight();

        // Progress event every WarpProgressInterval frames
        if (advanced % WarpProgressInterval == 0 && _bridge != null)
        {
            byte[] progress = new byte[8];
            BitConverter.GetBytes(advanced).CopyTo(progress, 0);
            BitConverter.GetBytes(_pendingAdvanceTotalFrames).CopyTo(progress, 4);
            _bridge.SendResponse(Protocol.MakeUnsolicited(
                SubCommand.AdvanceFrames, CommandStatus.Success, progress));
        }

        // Completion
        if (_pendingAdvanceFrames == 0)
        {
            byte[] result = BitConverter.GetBytes(advanced);
            // Send final response using stored request ID
            _bridge?.SendResponse(Protocol.MakeResponseById(
                _pendingAdvanceRequestId,
                SubCommand.AdvanceFrames, CommandStatus.Success, result));
        }
        return;  // Skip ALL normal UpdateAfter work
    }

    // === Normal UpdateAfter continues unchanged below ===
    // FPS calculation ...
    // Input drain ...
    // DrainCommands() ...
    // FrameCapture ...
    // etc.
}
```

`FastUpdateAfter()` also needs the warp gate (line 361):

```csharp
protected override void FastUpdateAfter()
{
    _frameCount++;
    if (_pendingAdvanceFrames > 0)
    {
        // During warp, run the warp gate on EVERY frame (not every 4th)
        UpdateAfter();
        return;
    }
    if (_frameCount % 4 == 0) UpdateAfter();
}
```

New delegate callbacks for CommandHandler constructor (extend the existing 6-delegate pattern at line 174):

```csharp
_commandHandler = new CommandHandler(
    APIs,
    () => _lastFrame,
    (resp) => _bridge?.SendResponse(resp),
    BuildTelemetryJson,
    () => _sessionId,
    (enabled) => _videoStreamingEnabled = enabled,
    () => _videoStreamingEnabled,
    // NEW: Warp mode delegates
    (active) => SetWarpModeActive(active),
    () => _warpModeActive,
    (count, reqId) => StartAdvanceFrames(count, reqId)
);
```

New methods in StreamerForm:

```csharp
private void SetWarpModeActive(bool active)
{
    if (active == _warpModeActive) return;
    _warpModeActive = active;
    if (active)
    {
        _warpSavedSoundOn = _apis.EmuClient.GetSoundOn();
        _warpSavedVideoEnabled = _videoStreamingEnabled;
        _apis.EmuClient.SetSoundOn(false);
        _apis.EmuClient.InvisibleEmulation(true);
        _videoStreamingEnabled = false;
        _apis.EmuClient.SpeedMode(6400);
    }
    else
    {
        _apis.EmuClient.SetSoundOn(_warpSavedSoundOn);
        _apis.EmuClient.InvisibleEmulation(false);
        _videoStreamingEnabled = _warpSavedVideoEnabled;
        _apis.EmuClient.SpeedMode(100);
    }
}

private void StartAdvanceFrames(int count, ushort requestId)
{
    _pendingAdvanceFrames = Math.Max(0, Math.Min(600_000, count));
    _pendingAdvanceTotalFrames = _pendingAdvanceFrames;
    _pendingAdvanceRequestId = requestId;
}
```

#### 4.1.3 CommandHandler Dispatch (`CommandHandler.cs`)

Add to dispatch switch (after line 165 `SubCommand.GetStreamState`):

```csharp
SubCommand.WarpMode      => DoWarpMode(cmd),
SubCommand.AdvanceFrames => DoAdvanceFrames(cmd),
```

New handler methods:

```csharp
private CommandMessage DoWarpMode(CommandMessage cmd)
{
    if (cmd.Data.Length < 1)
        return Protocol.MakeResponse(cmd, CommandStatus.Error, "WarpMode requires 1 byte");
    bool enabled = cmd.Data[0] != 0;
    _setWarpModeActive?.Invoke(enabled);
    byte[] data = new byte[] { (byte)(enabled ? 1 : 0) };
    return Protocol.MakeResponse(cmd, CommandStatus.Success, data);
}

private CommandMessage DoAdvanceFrames(CommandMessage cmd)
{
    if (cmd.Data.Length < 4)
        return Protocol.MakeResponse(cmd, CommandStatus.Error, "AdvanceFrames requires 4 bytes (uint32 LE)");
    int count = BitConverter.ToInt32(cmd.Data, 0);
    if (count <= 0)
        return Protocol.MakeResponse(cmd, CommandStatus.Error, "Count must be > 0");
    _startAdvanceFrames?.Invoke(count, cmd.RequestId);
    // Response will be sent by StreamerForm when advance completes
    return null;  // No immediate response — async completion
}
```

Add new delegate fields (following existing pattern at lines 39-41):

```csharp
private readonly Action<bool>? _setWarpModeActive;
private readonly Func<bool>? _getWarpModeActive;
private readonly Action<int, ushort>? _startAdvanceFrames;
```

Add `WarpMode` and `AdvanceFrames` to `IsAuditedSubCommand()` list at line 2409.

Raise `MaxSpeedPercent` from 5000 to 6400 (line 47):

```csharp
private const int MaxSpeedPercent = 6400;  // BizHawk API supports up to 6400
```

#### 4.1.4 Important C# Design Decision: State Machine vs Inline Loop

**Decision: State machine (decrement counter in UpdateAfter).**

Rationale:
- Inline loop (`for (int i = 0; i < N; i++) DoFrameAdvance()` inside `HandleCommand()`) is re-entrant: `DoFrameAdvance()` triggers `UpdateAfter()` which calls `DrainCommands()` which may call `HandleCommand()` again. Stack overflow risk.
- State machine is safe: `_pendingAdvanceFrames` is set once, then each natural UpdateAfter tick decrements it. BizHawk drives the frame loop. No re-entrancy.
- State machine allows cancel: commands are still drained during warp, so Python can send a cancel.

### 4.2 Lua Runtime Layer

#### 4.2.1 Bot Runtime Warp Guard (`lua/common/bot/runtime.lua`)

Add module-level flag (after existing state vars, around line 60):

```lua
local _warp_active = false   -- True during rng_seed_wait warp window
```

Add warp guard at top of `M.tick()` (line 919, after INPUT_BUSY check at line 923):

```lua
function M.tick()
    if not _state.active then return end
    if _deps.input and _deps.input.INPUT_BUSY then return end

    -- WARP GATE: skip signal scanning during warp window
    if _warp_active and _state.stage == "rng_seed_wait" then
        local now = _frame_now()
        _state.seed_current = _current_seed()   -- 1 RAM read only
        _state.updated_frame = now
        if tonumber(_state.run_started_frame or 0) > 0 then
            _state.frame_since_attempt_start = math.max(0, now - tonumber(_state.run_started_frame))
        end
        -- Seed match check (critical — must fire immediately)
        local target = tonumber(_state.config.rng_target_seed)
        if target and _state.seed_current == target then
            _warp_active = false   -- Exit warp before acquiring
            -- Fall through to normal tick for seed match handling
        else
            return   -- Skip read_context_signals and everything else
        end
    end

    -- Existing code continues unchanged from here...
    local now = _frame_now()
    local signals = _deps.signals.read_context_signals()
    -- ...
```

Add accessor functions (for external control):

```lua
function M.set_warp_active(active)
    _warp_active = (active == true)
end

function M.is_warp_active()
    return _warp_active
end
```

#### 4.2.2 Socket Reader Warp Mode (`plugins/pokemon_fire_red/lua/socket_reader.lua`)

Add module-level flag (around line 1715):

```lua
local WARP_MODE = false
local warp_heartbeat_interval = 30  -- frames between heartbeats during warp
```

Add warp gate in `on_frame()` (after `bot_runtime.tick()`, before event detection block):

```lua
local function on_frame()
    errlog.protected_call(function()
        inp.process()  -- Always runs

        if bot_runtime and bot_runtime.tick then
            bot_runtime.tick()
        end

        frame_counter = frame_counter + 1

        -- WARP MODE: skip all expensive work
        if WARP_MODE then
            if frame_counter % warp_heartbeat_interval == 0 then
                local rng = mem.read_u32_le(ADDR.rng_value, DOM)
                local msg = string.format(
                    '{"type":"warp_heartbeat","rng":%u,"frame":%d}\n', rng, frame_counter)
                pcall(function() comm.socketServerSend(msg) end)
                -- Check for warp_stop command
                local ok, cmd = pcall(comm.socketServerResponse)
                if ok and cmd and cmd ~= "" and cmd ~= "{}" and cmd ~= "{}\n" then
                    local req = ipc.parse_request(cmd)
                    if req and req.type == "warp_control" and req.action == "stop" then
                        WARP_MODE = false
                        if bot_runtime then bot_runtime.set_warp_active(false) end
                    end
                end
            end
            return  -- Skip ALL other work
        end

        -- Normal path continues unchanged...
```

Add `warp_control` command to `execute_command()` (after `bot_control` branch, around line 1673):

```lua
elseif req.type == "warp_control" then
    local action = tostring(req.action or "")
    if action == "start" then
        WARP_MODE = true
        warp_heartbeat_interval = tonumber(req.heartbeat_interval) or 30
        if bot_runtime then bot_runtime.set_warp_active(true) end
        return {type = "response", values = {warp_mode = true}}
    elseif action == "stop" then
        WARP_MODE = false
        if bot_runtime then bot_runtime.set_warp_active(false) end
        return {type = "response", values = {warp_mode = false}}
    elseif action == "status" then
        local rng = mem.read_u32_le(ADDR.rng_value, DOM)
        return {type = "response", values = {warp_mode = WARP_MODE, rng = rng, frame = frame_counter}}
    end
    return {type = "response", error = "unknown warp_control action: " .. action}
```

#### 4.2.3 File Reader Sync (`plugins/pokemon_fire_red/lua/reader.lua`)

Per `lua-reader-sync` rule: add no-op stub for `warp_control` in `execute_command()`:

```lua
elseif req.type == "warp_control" then
    -- File mode does not support warp mode (socket-only feature)
    return {type = "response", values = {warp_mode = false, note = "file_mode_unsupported"}}
```

### 4.3 Python Streaming Layer (frame_receiver + ws_endpoint)

#### 4.3.1 Protocol Constants (`frame_receiver.py`)

Add after `SUB_GET_STREAM_STATE = 0x08` (line 33):

```python
# Warp mode sub-command IDs (warp_mode_frame_advance)
SUB_WARP_MODE: int = 0x09        # Toggle warp: data=[enabled:1byte]
SUB_ADVANCE_FRAMES: int = 0x0A   # Bulk advance: data=[count:4byte LE uint32]
```

#### 4.3.2 WebSocket Command Capabilities (`ws_endpoint.py`)

Add to `COMMAND_CAPABILITIES` dict (around line 208-242):

```python
"warp_mode": "warp_mode",           # Requires C# capability advertisement
"advance_frames": "advance_frames", # Requires C# capability advertisement
```

Add handler cases in the command dispatch (around line 887):

```python
elif cmd == "warp_mode":
    enabled = bool(params.get("enabled", False))
    result = await receiver.send_command(
        SUB_WARP_MODE, struct.pack("B", 1 if enabled else 0))
elif cmd == "advance_frames":
    count = int(params.get("count", 0))
    if count <= 0:
        result = {"error": "count must be > 0"}
    else:
        timeout = max(5.0, count / 59.7275 * 2.0)
        result = await receiver.send_command(
            SUB_ADVANCE_FRAMES, struct.pack("<I", count), timeout)
```

### 4.4 Python Controller Layer (automation/controller.py)

#### 4.4.1 Imports

Add `SUB_ADVANCE_FRAMES` and `SUB_WARP_MODE` to imports (line 117):

```python
from rom_lab.streaming.frame_receiver import (
    CMD_STATUS_SUCCESS,
    SUB_ADVANCE_FRAMES,
    SUB_GET_EMU_STATE,
    SUB_SET_SPEED,
    SUB_WARP_MODE,
)
```

#### 4.4.2 New Method: `_advance_frames_bulk()`

Add after `_set_emu_speed_percent` (line 1798), following the same pattern:

```python
async def _advance_frames_bulk(self, count: int) -> bool:
    """Advance emulator N frames atomically via C# warp state machine."""
    receiver = self._frame_receiver
    if receiver is None or not bool(getattr(receiver, "is_connected", False)):
        return False
    send_command = getattr(receiver, "send_command", None)
    if not callable(send_command):
        return False
    clamped = max(1, min(600_000, int(count)))
    timeout = max(5.0, clamped / GBA_FRAME_RATE * 2.0)
    try:
        result = await send_command(
            SUB_ADVANCE_FRAMES, struct.pack("<I", clamped), timeout)
    except Exception:
        return False
    return isinstance(result, dict) and int(result.get("status", -1)) == CMD_STATUS_SUCCESS
```

#### 4.4.3 New Method: `_set_warp_mode()`

```python
async def _set_warp_mode(self, enabled: bool) -> bool:
    """Toggle C# warp mode (InvisibleEmulation, sound, video)."""
    receiver = self._frame_receiver
    if receiver is None or not bool(getattr(receiver, "is_connected", False)):
        return False
    send_command = getattr(receiver, "send_command", None)
    if not callable(send_command):
        return False
    try:
        result = await send_command(
            SUB_WARP_MODE, struct.pack("B", 1 if enabled else 0), 2.0)
    except Exception:
        return False
    return isinstance(result, dict) and int(result.get("status", -1)) == CMD_STATUS_SUCCESS
```

#### 4.4.4 New Method: `_send_lua_warp_control()`

```python
async def _send_lua_warp_control(self, action: str) -> bool:
    """Send warp_control command to Lua via MCP channel."""
    try:
        resp = await run_in_threadpool(
            self._mcp_manager.send_command,
            {"type": "warp_control", "action": action},
            3.0,
        )
        return resp is not None and not resp.get("error")
    except Exception:
        return False
```

#### 4.4.5 Warp Integration in `_wait_for_lua_bot_candidate()`

Insert warp branch inside the `rng_seed_wait` block (before the speed control at line 2046):

```python
# Inside _wait_for_lua_bot_candidate, when stage == "rng_seed_wait"
# After frames_to_target is computed (line 2044):

frames_to_target = int(accel_target_effective_delay) - int(frame_since_attempt)

# === NEW: Warp mode branch ===
warp_threshold = int(config_payload.get("warp_threshold_frames") or 5000)
warp_landing_buffer = int(config_payload.get("warp_landing_buffer_frames") or 1200)
warp_enabled = bool(config_payload.get("warp_mode_enabled", False))

if (
    warp_enabled
    and frames_to_target is not None
    and int(frames_to_target) > warp_threshold
    and not warp_engaged  # local flag, prevent re-entry
):
    warp_count = int(frames_to_target) - warp_landing_buffer
    if warp_count > 0:
        await self._append_debug_event(
            run_id, "warp_start",
            frames_to_target=frames_to_target,
            warp_count=warp_count,
            landing_buffer=warp_landing_buffer,
        )
        # Step 1: Tell Lua to enter lightweight warp mode
        await self._send_lua_warp_control("start")
        # Step 2: Tell C# to enter warp mode (disable video/audio/render)
        await self._set_warp_mode(True)
        # Step 3: Execute bulk frame advance
        success = await self._advance_frames_bulk(warp_count)
        # Step 4: Exit warp mode
        await self._set_warp_mode(False)
        await self._send_lua_warp_control("stop")
        warp_engaged = True  # Only warp once per attempt
        await self._append_debug_event(
            run_id, "warp_complete",
            success=success,
            warp_count=warp_count,
        )
        continue  # Re-read state immediately after warp
# === END warp mode branch ===

# Existing speed control continues unchanged below...
desired_speed = int(accel_speed_percent)
```

### 4.5 JavaScript UI Layer (automation.js)

#### 4.5.1 Extend `_setWarpMode()`

The existing `_setWarpMode()` at line 1088 manages video stream disable/enable. Extend it to also display warp status in the UI:

```javascript
// After _warpModeActive = true (line 1102):
_updateWarpStatusDisplay(true, 0, 0);  // Show "WARP" indicator

// After _warpModeActive = false (line 1119):
_updateWarpStatusDisplay(false, 0, 0);  // Hide "WARP" indicator
```

Add new function for warp status display:

```javascript
function _updateWarpStatusDisplay(active, advanced, total) {
    const el = document.getElementById('warp-status');
    if (!el) return;
    if (active) {
        const pct = total > 0 ? Math.round(advanced / total * 100) : 0;
        el.textContent = `WARP ${pct}%`;
        el.style.display = 'inline-block';
    } else {
        el.style.display = 'none';
    }
}
```

The `_syncWarpMode()` function at line 1123 already correctly activates warp when `targetRemaining > nearTargetFrames * 2` — this logic remains unchanged. The Python controller is the primary warp executor; the JS layer is for status display only.

### 4.6 Constants and Models

#### 4.6.1 `constants.py` Additions

Add after `RNG_ACCEL_MAX_NEAR_TARGET_FRAMES` (line 45):

```python
# Warp mode constants
DEFAULT_WARP_MODE_ENABLED: bool = False
DEFAULT_WARP_THRESHOLD_FRAMES: int = 5000
DEFAULT_WARP_LANDING_BUFFER_FRAMES: int = 1200
WARP_MAX_FRAMES_PER_CALL: int = 600_000
```

#### 4.6.2 `models.py` Additions

Add to `StarterResetStartRequest` (around line 230):

```python
warp_mode_enabled: bool = Field(
    default=DEFAULT_WARP_MODE_ENABLED,
    description="Enable bulk frame advancement during seed-wait phase",
)
warp_threshold_frames: int = Field(
    default=DEFAULT_WARP_THRESHOLD_FRAMES,
    ge=100, le=1_000_000,
    description="Minimum frames-to-target before triggering warp mode",
)
warp_landing_buffer_frames: int = Field(
    default=DEFAULT_WARP_LANDING_BUFFER_FRAMES,
    ge=100, le=100_000,
    description="Frames before target where warp stops and precision mode begins",
)
```
<!-- ID: directory_structure -->
## Directory Structure

### Files Modified by Warp Mode

```
csharp/RomLabStreamer/
├── Protocol.cs                    # +2 SubCommand constants (0x09, 0x0A)
├── CommandHandler.cs              # +2 handlers (DoWarpMode, DoAdvanceFrames)
│                                  #   +3 delegate fields, MaxSpeedPercent 5000→6400
└── StreamerForm.cs                # +warp state machine fields
                                   #   +warp gate in UpdateAfter()
                                   #   +SetWarpModeActive(), StartAdvanceFrames()
                                   #   +2 delegate lambdas in constructor

lua/common/bot/
└── runtime.lua                    # +_warp_active flag
                                   #   +warp gate in M.tick() (skip signals, read RNG only)
                                   #   +M.set_warp_active(), M.is_warp_active()

plugins/pokemon_fire_red/lua/
├── socket_reader.lua              # +WARP_MODE flag
│                                  #   +warp gate in on_frame() (skip reads, heartbeat only)
│                                  #   +warp_control command handler
└── reader.lua                     # MIRROR of socket_reader.lua warp changes
                                   #   (lua-reader-sync rule: both files always updated together)

src/rom_lab/streaming/
├── frame_receiver.py              # +SUB_WARP_MODE=0x09, SUB_ADVANCE_FRAMES=0x0A
└── ws_endpoint.py                 # +warp_mode, advance_frames command routing

src/rom_lab/api/routes/automation/
├── constants.py                   # +DEFAULT_WARP_MODE_ENABLED, threshold/buffer/max constants
├── models.py                      # +warp fields on StarterResetStartRequest
├── controller.py                  # +_advance_frames_bulk(), _set_warp_mode()
│                                  #   +_send_lua_warp_control()
│                                  #   +warp branch in _wait_for_lua_bot_candidate()
└── state_factories.py             # +warp fields in state construction (if needed)

.council/web/static/js/
└── automation.js                  # +_updateWarpStatusDisplay()
                                   #   +extend _setWarpMode() for warp indicator
```

### Files NOT Modified (Explicit Boundary)

These files are intentionally out of scope:

- `src/rom_lab/schema/` — No schema changes; warp is operational, not perceptual
- `src/rom_lab/bridge/` — No bridge changes; warp does not alter game state format
- `src/rom_lab/emulator/` — No emulator layer changes; warp operates above this layer
- `lua/common/memory.lua` — Shared memory module unchanged
- `lua/common/ipc.lua` — IPC module unchanged
- `tests/` — New test files only, no modification to existing tests
<!-- ID: data_storage -->
## Data Storage

### No New Persistent Storage

Warp mode introduces **zero new persistent storage**. All warp state is ephemeral and lives in-memory:

| State | Location | Lifetime | Reset On |
|-------|----------|----------|----------|
| `_pendingAdvanceFrames` | C# StreamerForm | Per-warp-call | Warp complete or warp-off |
| `_warpModeActive` | C# StreamerForm | Per-session | Warp-off command or tool unload |
| `_warp_active` | Lua runtime.lua | Per-session | `M.set_warp_active(false)` |
| `WARP_MODE` | Lua socket_reader.lua | Per-session | `warp_control` command |
| `warp_mode_enabled` | Python controller | Per-run config | Run ends or new run starts |

### Wire Protocol Data

Warp commands use the existing TCP binary protocol with no new storage:

- **Request**: 4-byte header + payload (same as all SubCommands)
- **Response**: 4-byte header + JSON payload (same as all SubCommands)
- **Heartbeat**: JSON `{warp: true, frame: N, rng: "0xHHHHHHHH"}` via existing socket send

### Existing Storage Unchanged

- `lua/output/state.json` — Not written during warp (Lua warp gate skips full state assembly)
- `lua/output/debug_request.json` — Unchanged (file-mode only)
- No database tables added or modified
- No new configuration files
<!-- ID: testing_strategy -->
## Testing and Validation Strategy

### Unit Tests (Automated)

#### C# Layer — Build Verification
- **Build gate**: `dotnet build` must succeed with zero warnings on modified files
- **Protocol constants**: Static assertion that WarpMode=0x09 and AdvanceFrames=0x0A do not collide with existing SubCommand values
- **No C# unit test framework currently in use** — validation is build + manual integration

#### Python Layer — pytest

**New test file: `tests/test_warp_mode.py`**

| Test | Validates | Method |
|------|-----------|--------|
| `test_warp_constants_no_collision` | SUB_WARP_MODE and SUB_ADVANCE_FRAMES don't collide with existing SUB_* | Import constants, assert uniqueness |
| `test_warp_default_disabled` | DEFAULT_WARP_MODE_ENABLED is False | Import from constants |
| `test_warp_model_fields_optional` | StarterResetStartRequest accepts without warp fields | Construct model without warp fields |
| `test_warp_model_fields_explicit` | StarterResetStartRequest accepts warp fields | Construct with warp_mode_enabled=True |
| `test_warp_threshold_positive` | DEFAULT_WARP_THRESHOLD_FRAMES > 0 | Import and assert |
| `test_warp_landing_buffer_matches_accel` | Landing buffer == accel_near_target_frames default | Cross-check constants |

**Existing test files — regression gates:**

- `tests/test_automation_routes.py` — Must pass unchanged (warp defaults to off)
- `tests/test_ws_endpoint_commands.py` — Must pass unchanged (new commands additive)
- `tests/test_frame_receiver.py` — Must pass unchanged (new SUB_* constants additive)

### Integration Tests (Manual — Emulator Required)

These require a running BizHawk instance and cannot be automated in CI:

| Test | Procedure | Pass Criteria |
|------|-----------|---------------|
| Normal mode unaffected | Boot with warp disabled, run automation | Identical behavior to pre-warp codebase |
| Warp on/off toggle | Send warp_mode enable/disable via WS | C# enters/exits warp state cleanly |
| Bulk advance | Send advance_frames(5000) | Frames advance, response returns actual count |
| Video gate during warp | Enable warp, check stream | No video frames emitted during warp |
| Video restore after warp | Disable warp, check stream | Video resumes within 1 second |
| Lua heartbeat | Enable warp, observe Lua output | Heartbeat every 30 frames with rng value |
| Seed match during warp | Set target seed, enable warp | Lua detects match, breaks out of warp |
| Landing precision | Run full automation with warp | Bot lands within landing buffer of target |

### Regression Test Protocol

Before merging any warp phase:

```bash
# 1. All existing tests must pass
pytest -q tests/test_automation_routes.py tests/test_ws_endpoint_commands.py tests/test_frame_receiver.py

# 2. New warp tests must pass
pytest -q tests/test_warp_mode.py

# 3. C# must build clean
cd csharp/RomLabStreamer && dotnet build

# 4. Lua syntax check
luac -p lua/common/bot/runtime.lua
luac -p plugins/pokemon_fire_red/lua/socket_reader.lua
luac -p plugins/pokemon_fire_red/lua/reader.lua
```
<!-- ID: deployment_operations -->
## Deployment and Operations

### Build and Deploy Sequence

Warp mode changes span 4 languages. The deploy sequence is:

```bash
# 1. Build C# streamer DLL
cd csharp/RomLabStreamer && dotnet build
# DLL auto-copies to ~/.romlab/bizhawk/ExternalTools/

# 2. Lua files — no build step, but verify syntax
luac -p lua/common/bot/runtime.lua
luac -p plugins/pokemon_fire_red/lua/socket_reader.lua
luac -p plugins/pokemon_fire_red/lua/reader.lua

# 3. Python — restart API server to pick up new constants/controller code
# rom-lab serve (restart)

# 4. JavaScript — static files served directly, no build step
# Browser hard-refresh to pick up automation.js changes

# 5. Restart BizHawk to load updated Lua scripts and new DLL
rom-lab boot pokemon_fire_red
```

### Operational Monitoring

During warp operation, the following signals indicate health:

| Signal | Source | Healthy Value |
|--------|--------|---------------|
| Heartbeat | Lua → socket → Python logs | Every ~0.5s (30 frames at max speed) |
| Frame counter | Heartbeat JSON `frame` field | Monotonically increasing |
| RNG value | Heartbeat JSON `rng` field | Changing each heartbeat |
| Warp status | automation.js UI indicator | "WARP" badge visible during warp |
| Video stream | Browser canvas | Frozen during warp, resumes after |

### Rollback

Warp mode is entirely gated by boolean flags. To disable without code revert:

1. **Runtime**: Set `warp_mode_enabled: false` in run config (or omit field — defaults to false)
2. **Emergency**: Send `warp_mode` disable command via WebSocket
3. **Code revert**: All changes are additive — removing warp code paths leaves existing behavior intact

### No Infrastructure Changes

- No new services or processes
- No database migrations
- No configuration file changes (constants are in Python source)
- No CI/CD pipeline changes needed
- No deployment environment changes
<!-- ID: open_questions -->
## Open Questions and Follow-Ups

### Unverified BizHawk Behaviors (Phase 6 — Empirical)

These three behaviors are referenced in research but cannot be verified from source code alone. They require empirical testing with a running BizHawk instance:

| # | Question | Risk if Wrong | Mitigation | Phase |
|---|----------|---------------|------------|-------|
| OQ-1 | Does `InvisibleEmulation(true)` suppress video buffer writes, or does it only hide the form window? | If it only hides the window, video frames still flow to GetVideoBuffer() and waste CPU during warp | Test empirically; if no effect on buffer, rely solely on C# `_warpModeActive` flag to gate `captureVideoFrame` | Phase 6 |
| OQ-2 | Does `SetSoundOn(false)` actually reduce CPU overhead, or does the audio subsystem still process internally? | If audio still processes, we lose potential warp speedup | Test empirically; if no effect, remove from warp enter/exit sequence | Phase 6 |
| OQ-3 | What is the maximum stable `SpeedMode(percent)` value? Research suggests 6400, but BizHawk may have internal limits or instability above certain thresholds | If unstable at 6400, warp fails or crashes BizHawk | Test empirically with increments (1000, 2000, 4000, 6400); use highest stable value as MAX_WARP_SPEED_PERCENT | Phase 6 |

### Design Decisions Deferred to Implementation

| # | Decision | Context | Resolution Timing |
|---|----------|---------|-------------------|
| DD-1 | Exact heartbeat JSON shape | Research proposes `{warp, frame, rng}` but Python may need additional fields for monitoring | Coder decides during Lua implementation (Phase 2) |
| DD-2 | Whether `state_factories.py` needs warp fields | Depends on how StarterResetStartRequest flows to controller | Coder inspects call chain during Phase 4 |
| DD-3 | Warp indicator UI design in automation.js | Research shows existing `_warpModeActive` flag; exact visual treatment TBD | Coder decides during Phase 5 |

### Questions That Do NOT Block Architecture

These were raised during research but are resolved or irrelevant:

- **Q: Can Lua runtime.lua import from socket_reader.lua?** — No, and not needed. Each has its own warp flag.
- **Q: Does the two-command-channel design create race conditions?** — No. TCP commands (warp) and MCP commands (bot lifecycle) operate on different state and are sequenced by the Python controller.
- **Q: Can we use FrameSkip instead of DoFrameAdvance loop?** — Investigated and rejected. FrameSkip still renders every Nth frame, which means Lua and C# overhead persists. DoFrameAdvance in a state machine with full overhead gating is strictly faster.
<!-- ID: references_appendix -->
## References and Appendix

### Research Documents

| Document | Key Findings |
|----------|-------------|
| `RESEARCH_BIZHAWK_API.md` | BizHawk API surface (DoFrameAdvance, InvisibleEmulation, SpeedMode, SetSoundOn); verified via monodis |
| `RESEARCH_CSHARP_STREAMER_20260222.md` | C# StreamerForm architecture, delegate injection pattern, UpdateAfter() work items, video gating logic |
| `RESEARCH_LUA_WARP_20260222_0021.md` | Lua runtime.lua tick loop, 103-read overhead, socket_reader on_frame(), warp gate insertion points |
| `RESEARCH_CONTROLLER_WARP.md` | Python controller flow, _wait_for_lua_bot_candidate(), speed control, frame_receiver SUB constants |

### Source Files Verified

All architecture decisions were verified against actual source code. Zero discrepancies found between research claims and code reality.

| File | Lines Verified | Key Finding |
|------|---------------|-------------|
| `Protocol.cs` | 27-75 | SubCommand 0x09-0x0F available |
| `CommandHandler.cs` | 39, 47, 148, 410-458, 525 | Delegate pattern, MaxSpeedPercent=5000, DoFrameAdvance single-shot |
| `StreamerForm.cs` | 174-181, 210-358, 361-364 | Constructor delegates, UpdateAfter 7 items, FastUpdateAfter modulo 4 |
| `frame_receiver.py` | 26-34 | SUB constants 0x01-0x08 |
| `controller.py` | 117-121, 1786-1798, 2042-2062 | Imports, _set_emu_speed_percent pattern, warp insertion point |
| `runtime.lua` | 919-935 | M.tick() with read_context_signals at line 928 |
| `automation.js` | 1088-1152 | Existing warp infrastructure |
| `constants.py` | full file | GBA_FRAME_RATE, accel defaults |

### Architectural Principles Applied

1. **Zero Regression**: Every change behind boolean flag defaulting to false
2. **State Machine over Loop**: Prevent re-entrant emulator calls in C#
3. **Two-Phase Warp**: Bulk advance then precision landing
4. **Minimal Overhead**: 1 RAM read per frame during warp (vs 103+ normally)
5. **Existing Infrastructure**: All changes modify existing files, no new services
6. **Dual Reader Sync**: Both Lua readers updated together per lua-reader-sync rule
7. **Additive Protocol**: New SubCommand IDs, no changes to existing command handling

### Glossary

| Term | Definition |
|------|-----------|
| **Warp Mode** | Operational mode where BizHawk advances frames at maximum speed with minimal per-frame overhead |
| **Bulk Advance** | Phase A of warp: advance N frames via DoFrameAdvance() loop with video/audio/Lua overhead suppressed |
| **Precision Landing** | Phase B of warp: slow to 400% speed within landing buffer for frame-accurate seed targeting |
| **Landing Buffer** | Number of frames before target where warp exits and normal speed control resumes (default: 1200) |
| **Heartbeat** | Lightweight JSON sent by Lua every 30 frames during warp containing frame count and RNG value |
| **SubCommand** | Binary protocol command ID in the TCP stream between Python frame_receiver and C# CommandHandler |
| **State Machine Pattern** | C# implementation where DoFrameAdvance() is called from UpdateAfter() (event loop) rather than inline in HandleCommand() |
| **Warp Gate** | Conditional branch at top of a function that skips normal processing when warp is active |
