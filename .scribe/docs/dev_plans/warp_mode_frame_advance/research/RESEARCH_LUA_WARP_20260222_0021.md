---
id: warp_mode_frame_advance-research-lua-warp-20260222-0021
title: "\U0001F52C Research Lua Warp 20260222 0021 \u2014 warp_mode_frame_advance"
doc_type: RESEARCH_LUA_WARP_20260222_0021
doc_name: RESEARCH_LUA_WARP_20260222_0021
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 00:23:20 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Lua Warp 20260222 0021 — warp_mode_frame_advance
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 00:21:30 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

This research analyzes the Lua runtime and socket reader for warp mode design. Three files were fully reviewed:

- `lua/common/bot/runtime.lua` (1699 lines) — Bot tick loop, stage machine
- `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` (1922 lines) — Main frame loop, socket communication
- `lua/common/bot/signals_fr.lua` (328 lines) — RAM signal readers

**Key Finding**: During `rng_seed_wait` stage, the bot executes ~104 RAM reads per frame (mostly reading 32 text printers) plus a full `read_game_state()` + socket send every 30 frames. Warp mode can reduce this to **1-2 RAM reads per frame** by introducing a `WARP_MODE` flag that gates all non-essential work.

**Existing Fast Path**: The socket reader already has a fast path for `INPUT_BUSY` — when input is executing, only `inp.process()`, `bot_runtime.tick()`, and frame counter run. The warp mode flag should mirror this pattern.

**RNG Address**: `gRngValue` is at `0x03005000` (IWRAM) — a single 4-byte read. This is the ONLY read needed during warp wait.
<!-- ID: research_scope -->
**Research Lead:** nexus

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Per-Frame Work Inventory

#### socket_reader.lua `on_frame()` — Main Frame Callback

The `event.onframeend(on_frame)` is called every emulated frame. The work is structured in two paths:

**FAST PATH** (when `inp.INPUT_BUSY == true`):
```
inp.process()              -- LIGHT: processes queued input sequence, calls joypad.set()
bot_runtime.tick()         -- MEDIUM: see below
frame_counter increment    -- TRIVIAL
```
All socket I/O, file I/O, game state reads are SKIPPED. This is already optimized.

**NORMAL PATH** (when not input-busy, every frame):

| Step | Cost | Description |
|------|------|-------------|
| `inp.process()` | LIGHT | Joypad state management |
| `bot_runtime.tick()` | MEDIUM | ~104 RAM reads via `read_context_signals()` |
| Input transition detection | TRIVIAL | Boolean comparison |
| `ipc.check_requests()` | LIGHT | File existence check for debug commands |
| Event detection block | LIGHT | 10 RAM reads (printer, battle flags, script mode) |
| `read_game_state()` every 30 frames | HEAVY | Full state: party decrypt + bag + 225 tiles + NPCs + text |
| `comm.socketServerSend()` | HEAVY | Blocking socket send (up to 200ms timeout) |
| `comm.socketServerResponse()` | HEAVY | Blocking socket receive (up to 200ms timeout) |
| `write_state()` every 60 frames | MEDIUM | Full state + disk write |

**Total per-frame RAM reads (normal path, non-send frame)**: ~104 reads (bot tick)
**Total per-frame RAM reads (send frame, every 30)**: ~104 + ~400+ reads (bot tick + full game state)

#### `bot_runtime.tick()` — Called Every Frame When Active

```lua
-- From runtime.lua:923-940
local signals = _deps.signals.read_context_signals()   -- ~104 RAM reads
_state.last_signals = signals
_state.seed_current = _current_seed()                  -- 1 RAM read (gRngValue)
_state.updated_frame = now
```

Then dispatches to stage handler.

#### `read_context_signals()` — Called Every Frame by Bot Tick

From `signals_fr.lua:156-191`:
1. `obj_base` flags byte (1 read)
2. `battle_type_flags` (1 read: 4 bytes)
3. `battle_outcome` (1 read)
4. `_scan_text_printers()` — **96 reads**: loops all 32 text printers, 3 reads each (active + ptr + state)
5. `script_mode` (1 read)
6. `special_var_result` (1 read)
7. `yes_no_window_id` (1 read)

**Total: ~103 RAM reads per bot tick frame**

#### `_current_seed()` — Called Every Frame by Bot Tick

Single call: `mem.read_u32_le(ADDR.rng_value, DOM)` — reads `gRngValue` at `0x03005000`. **1 RAM read, 4 bytes.**

---

### 2. RNG Monitoring — gRngValue

- **Address**: `0x03005000` (IWRAM, absolute System Bus address)
- **Size**: 4 bytes (u32 LE)
- **Access in runtime.lua**: `_current_seed()` (line 244-252), called via `_deps.signals.read_rng_seed()`
- **Access in signals_fr.lua**: `M.read_rng_seed()` (line 230-233) — single `mem.read_u32_le(c.addr.rng_value, c.dom)` call
- **BizHawk access cost**: Extremely cheap — IWRAM is on-chip, no pointer dereference needed

**Conclusion**: Reading gRngValue is the cheapest possible per-frame operation. An ultra-lightweight warp mode that reads ONLY this value would be ~0.01% of the current per-frame cost.

---

### 3. Bot Stage Machine During Seed Wait

The `rng_seed_wait` stage (lines 1337-1427) is the critical warp target:

```lua
if _state.stage == "rng_seed_wait" then
    local seed = _current_seed()           -- 1 read: gRngValue
    if seed == nil then return end

    local target_seed = tonumber(_state.config.rng_target_seed)

    -- Check exact seed match
    if target_seed and seed == target_seed then
        -- IMMEDIATELY queue A press and transition to a4_acquire
        ...queue_a_press("a4_acquire")
        _set_stage("a4_acquire", ...)
        return
    end

    -- Timeout check (arithmetic only)
    local wait_frames = now - (_state.seed_wait_start_frame or now)
    if wait_frames >= timeout then
        -- Fallback: queue A press anyway
        ...
        return
    end

    -- Unexpected candidate check (reads party)
    local candidate = _deps.signals.find_new_party_candidate(baseline_signatures)
    ...
    return
end
```

**Per-frame work in `rng_seed_wait` (currently)**:
1. `read_context_signals()` called by tick() BEFORE stage dispatch: ~103 reads (WASTED)
2. `_current_seed()`: 1 read (NEEDED)
3. Seed comparison: arithmetic only
4. Timeout check: arithmetic only
5. `find_new_party_candidate()`: 2-14 reads (party count + personalities)

**With warp mode gating**: Only steps 2-5 needed = **1-16 RAM reads total**.

---

### 4. Socket Command Flow (How Commands Arrive)

The socket protocol (lines 1868-1891 of socket_reader.lua):
```
1. Lua sends state JSON via comm.socketServerSend()  -- every 30 frames
2. Lua reads command from Python via comm.socketServerResponse()
3. If command present: execute_command(req) -> encode_response() -> send response
4. Python sends ack -> Lua reads ack (keeps lockstep)
```

**Command types supported** (`execute_command`, lines 1618-1676):
- `"read"` — read RAM addresses
- `"dump"` — dump RAM region
- `"write"` — write RAM value
- `"screenshot"` — capture screenshot
- `"input"` — queue input actions
- `"scene_probe"` — optional screenshot + probe
- `"bot_control"` — send command to bot runtime (start/stop/update/status)

**Adding a new command type for warp control** is straightforward: add an `elseif req.type == "warp_control"` branch in `execute_command()`.

The command flows through `ipc.parse_request()` which handles JSON parsing. The `bot_control` command type routes to `_handle_bot_control()` → `bot_runtime.handle_command()`.

For warp mode, a new `"warp_control"` command type would set a module-level `WARP_MODE` boolean in socket_reader.lua.

---

### 5. Warp Mode Flag Design

**Where to add the flag**: Module-level in `socket_reader.lua` (lines 1715-1725 area):

```lua
-- WARP MODE: When true, skip all expensive per-frame work
-- Only reads gRngValue + queues seed-match A press
local WARP_MODE = false
local warp_mode_rng_interval = 1  -- read RNG every N frames (default: every frame)
```

**What MUST still run during warp**:
- `inp.process()` — MUST run to drain any queued input
- `bot_runtime.tick()` — MUST run for seed-match detection (but can be made lighter)
- `frame_counter` increment

**What CAN be skipped during warp**:
- `ipc.check_requests()` — debug file IPC (not needed during warp)
- Event detection block (10 reads for text/battle/menu events)
- `read_game_state()` — ALL of it: party, items, tiles, NPCs, text, RNG state
- `comm.socketServerSend()` — full state sends
- `comm.socketServerResponse()` — command polling (except warp-exit command)
- `write_state()` — file fallback writes

**Modified `on_frame()` structure with warp mode**:
```lua
local function on_frame()
    errlog.protected_call(function()
        -- Always: process input (MUST be first)
        inp.process()
        
        -- Always: bot tick (handles seed-match detection)
        -- BUT: bot tick can be made warp-aware to skip read_context_signals()
        if bot_runtime and bot_runtime.tick then
            bot_runtime.tick()
        end
        
        frame_counter = frame_counter + 1
        
        -- WARP MODE: Skip all expensive work
        if WARP_MODE then
            -- Only send periodic lightweight RNG heartbeat (optional, every N frames)
            if frame_counter % warp_mode_heartbeat_interval == 0 then
                -- Send minimal {type:"warp_heartbeat", rng: X, frame: N}
                local rng = mem.read_u32_le(ADDR.rng_value, DOM)
                local msg = '{"type":"warp_heartbeat","rng":' .. rng .. ',"frame":' .. frame_counter .. '}\n'
                pcall(function() comm.socketServerSend(msg) end)
                -- Check for warp_stop command
                local ok, cmd = pcall(comm.socketServerResponse)
                if ok and cmd and cmd ~= "{}" and cmd ~= "{}\n" then
                    local req = ipc.parse_request(cmd)
                    if req and req.type == "warp_control" and req.action == "stop" then
                        WARP_MODE = false
                        -- Force immediate full state send after warp exit
                    end
                end
            end
            return  -- Skip ALL other work
        end
        
        -- ... normal path continues
    end)
end
```

---

### 6. Bot Tick During Warp — Making tick() Warp-Aware

The issue: `bot_runtime.tick()` always calls `read_context_signals()` (~103 reads) before checking the stage. During `rng_seed_wait`, those reads are 100% wasted.

**Option A: Warp-aware tick() in runtime.lua**

Add a `M.tick_warp()` function that skips `read_context_signals()` and only does minimal work:

```lua
-- In runtime.lua: new warp-mode tick
function M.tick_warp()
    if not _state.active then return end
    if _deps.input and _deps.input.INPUT_BUSY then return end
    
    -- Only valid during rng_seed_wait stage
    if _state.stage ~= "rng_seed_wait" then
        -- Fall back to normal tick for other stages
        return M.tick()
    end
    
    local now = _frame_now()
    _state.seed_current = _current_seed()  -- 1 RAM read
    _state.updated_frame = now
    
    -- Minimal seed-match check
    local seed = _state.seed_current
    if seed == nil then return end
    local target_seed = tonumber(_state.config.rng_target_seed)
    if target_seed and seed == target_seed then
        -- Match! Queue A press and transition
        _state.a4_presses = 0
        _state.a4_last_progress_frame = now
        _state.a4_prev_signal_key = nil
        _state.a4_hold_until_frame = 0
        _state.a4_hold_complete_logged = true
        _state.next_press_frame = now
        local queued = _queue_a_press("a4_acquire")
        if queued then
            _state.seed_at_match = seed
            _state.frame_at_seed_match = now
            _set_stage("a4_acquire", "target seed matched (warp)", _state.config.a4_timeout_frames)
            _append_event("rng_seed_match", {target_seed = target_seed, matched_seed = seed})
        end
        return
    end
    
    -- Timeout check
    local wait_frames = now - (_state.seed_wait_start_frame or now)
    if wait_frames >= (_state.config.rng_seed_wait_timeout_frames or 36000) then
        -- Timeout fallback
        ...
    end
end
```

**Option B: WARP_MODE flag in runtime.lua itself**

Add `_state.warp_mode = false` to the state and check it in `M.tick()`:

```lua
function M.tick()
    if not _state.active then return end
    if _deps.input and _deps.input.INPUT_BUSY then return end
    
    local now = _frame_now()
    _state.seed_current = _current_seed()  -- Always: 1 read
    _state.updated_frame = now
    
    -- In warp mode during rng_seed_wait: skip read_context_signals()
    local signals = nil
    if not (_state.warp_mode and _state.stage == "rng_seed_wait") then
        signals = _deps.signals.read_context_signals()  -- 103 reads
        _state.last_signals = signals
    end
    
    -- ... rest of tick
```

**Recommendation**: Option B is simpler and safer. A single boolean guard before the expensive `read_context_signals()` call.

---

### 7. Warp Exit Coordination

**When warp ends** (seed matched OR warp_stop command received):

1. Python sends `{"type":"warp_control","action":"stop"}` via socket
2. Lua sets `WARP_MODE = false`
3. The next normal frame tick will:
   - Run full `read_context_signals()` (signals are fresh from hardware)
   - Run `read_game_state()` (gets current state post-warp)
   - Send full state to Python via socket

**Risk: State desync after warp**
- Lua's `frame_counter` continues during warp (correct)
- `_state.seed_current` is updated every frame during warp (correct)
- `_state.last_signals` is STALE during warp — but it's only used by `_status_json()` for reporting, not for logic
- On warp exit, the very next normal tick refreshes `last_signals` — no desync risk

**Force full state read on warp exit** (recommended):
```lua
if WARP_MODE == false and was_warp_mode then
    -- Force immediate full state send
    force_send = true
end
```

---

### 8. Ultra-Lightweight RNG Monitor

The minimal implementation for warp mode heartbeat:

```lua
-- Ultra-lightweight: single RAM read
local rng = mem.read_u32_le(ADDR.rng_value, DOM)
-- ADDR.rng_value = 0x03005000
```

No pointer dereference, no decryption, no party reads. This is all that's needed for seed-match polling during warp.

**Suggested heartbeat interval**: Every 30-60 frames during warp. At 60fps, that's 1-2 reads/second reported to Python.

But the **local seed-match check in Lua** (Option B above) checks EVERY frame — this catches the seed on the exact frame it occurs, which is critical for timing. The Python heartbeat is just for monitoring/debugging, not for the match itself.

---

### 9. Socket Command Integration (New `warp_control` Command)

Add to `execute_command()` in socket_reader.lua (after the `bot_control` branch, line ~1673):

```lua
elseif req.type == "warp_control" then
    local action = tostring(req.action or "")
    if action == "start" then
        WARP_MODE = true
        warp_mode_heartbeat_interval = tonumber(req.heartbeat_interval) or 30
        return {type = "response", values = {warp_mode = 1, active = 1}}
    elseif action == "stop" then
        WARP_MODE = false
        return {type = "response", values = {warp_mode = 0, active = 0}}
    elseif action == "status" then
        local rng = mem.read_u32_le(ADDR.rng_value, DOM)
        return {type = "response", values = {warp_mode = WARP_MODE and 1 or 0, rng = rng, frame = frame_counter}}
    end
    return {type = "response", error = "unknown warp_control action"}
```

From Python (automation controller), this translates to:
```python
# Send warp_control command via existing socket protocol
sock.send(json.dumps({"type": "warp_control", "action": "start"}) + "\n")
```

---

### 10. Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|------------|
| Seed match happens on frame where warp_stop is also received | LOW | Lua checks seed first in warp tick, queues A press before checking commands |
| ipc.check_requests() skipped means debug commands don't work during warp | ACCEPTABLE | Debug mode and warp mode are mutually exclusive |
| Bot runtime `_state.last_signals` stale during warp | LOW | Only used for status reporting; refreshed on warp exit |
| Socket command polling skipped during warp (except heartbeat) | DESIGN CHOICE | Python can't issue other commands during warp; use warp_stop first |
| Warp mode engaged while bot is NOT in rng_seed_wait | MEDIUM | Either guard against this in Lua (only allow warp in rng_seed_wait stage), or fall through to normal tick |
| find_new_party_candidate() still runs during warp tick | ACCEPTABLE | Only 2-14 reads, needed for unexpected candidate detection |
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---