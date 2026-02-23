---
id: automation_rng_modular_2026_02_21-research-bizhawk-frame-control
title: "\U0001F52C Research Bizhawk Frame Control \u2014 automation_rng_modular_2026_02_21"
doc_type: RESEARCH_BIZHAWK_FRAME_CONTROL
doc_name: RESEARCH_BIZHAWK_FRAME_CONTROL
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 06:52:44 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Bizhawk Frame Control — automation_rng_modular_2026_02_21
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-21 06:50:13 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** nexus

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** [Describe the finding]
- **Evidence:** [Link to logs, code references, or experiments]
- **Confidence:** Medium

### Finding 2
- **Summary:** [Describe the finding]
- **Evidence:** [Link to supporting material]
- **Confidence:** Medium

### Additional Notes
- Capture supporting observations or open follow-ups.


---
## Technical Analysis
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

<!-- ID: lua_frame_model -->
## Lua Frame Model

BizHawk executes Lua scripts via a single callback registered with `event.onframeend()`. The socket_reader registers `on_frame` at line 1912 of `socket_reader.lua`:

```lua
event.onframeend(on_frame)
```

**Key properties of `on_frame`:**

1. **Called once per emulator frame** — at the end of every frame (after the GBA has processed all inputs and rendered). This gives 59.7275 opportunities per second to execute logic.

2. **`emu.framecount()` is the canonical clock** — returns the current absolute frame number. All timing in `bot/runtime.lua` uses this (`_frame_now()`). Frame comparisons like `now >= _state.next_press_frame` are exact integer comparisons.

3. **Input is first** — the `on_frame` body begins by calling `inp.process()` (line 1775) and `bot_runtime.tick()` (line 1777). This ensures joypad state is set BEFORE any I/O operations that might block.

4. **FAST PATH during input** — while `inp.INPUT_BUSY` is true, ALL socket I/O (send/receive) is completely skipped (lines 1797-1801). This is critical: the Lua script guarantees uninterrupted `joypad.set()` calls during active input sequences with zero network interference.

5. **State sends happen every `SOCKET_STATE_INTERVAL = 30` frames** (~0.5 seconds). Python does NOT receive a state update every frame; it polls on ~30-frame intervals or after input completion.

6. **`bot_runtime.lua` is frame-native** — the bot runtime's `M.tick()` function is called every frame. Stage transitions, countdown checks (`elapsed >= burn_frames`), and press decisions (`now >= _state.next_press_frame`) all operate at single-frame granularity. There is no sub-frame uncertainty in the Lua state machine itself.

**Summary:** Lua has exact, deterministic single-frame control. The frame model is ideal for tick-level operations — if the Lua bot decides to press A on frame N, it can do so reliably.

<!-- ID: ipc_latency -->
## IPC Latency

The communication path from Python to Lua and back is:

```
Python (FastAPI/MCP) → TCP socket → BizHawk socket_reader.lua → response → Python
```

**Architecture:**
- Python side: `src/rom_lab/emulator/socket_reader.py` — async TCP server
- Lua side: `comm.socketServerSend()` and `comm.socketServerResponse()` in `socket_reader.lua`
- The protocol is half-duplex with an explicit ack round-trip. Lua sends state, then reads one command from Python (lines 1864-1888).

**The critical latency breakdown:**

1. **Lua-to-Python delivery**: Lua sends state updates every 30 frames (~500ms). Commands from Python are only read AFTER Lua sends state (line 1864: "Read command from Python (ONLY after sending — avoids blocking deadlock)"). This means Python's command is picked up on the NEXT state send cycle after Python enqueues it.

2. **Socket timeout**: `comm.socketServerSetTimeout(200)` — BizHawk's socket timeout is 200ms. If Python takes >200ms to respond to a state send, Lua returns without waiting. Under normal conditions (fast localhost), actual round-trip is <5ms.

3. **Command processing lag**: When Python sends a command, it is received by Lua on the same frame as the outgoing state send. The Lua response goes out immediately (same frame, line 1879: "Send command response IMMEDIATELY (same frame)").

4. **Input command round-trip**: For an `input` command, Lua processes it on the SAME FRAME as the state send that preceded it. The command is queued to `inp.queue_actions()`, and execution begins the NEXT frame. So the first joypad.set() for the action happens on frame `N+1` where `N` is the frame that processed the command.

5. **30-frame polling constraint**: Python typically waits for Lua to send state (every 30 frames ≈ 502ms) to detect what frame commands get picked up. This is the primary source of timing uncertainty from Python's perspective.

**Key insight**: The 30-frame state interval means Python cannot know exactly which frame a "start" command will be processed on — only that it will be processed within the next 30-frame window after the command is enqueued. This uncertainty cannot be resolved from Python.

**Important**: `POLL_STAGE_INTERVAL_SECONDS = 0.05` (50ms) and `POLL_CANDIDATE_INTERVAL_SECONDS = 0.08` (80ms) — Python polls the bot status at these intervals to check stage transitions. These are Python-side polls; they don't inject anything into Lua's frame loop.

**Summary of latency**: Python→Lua command latency is 1-30 frames (16-502ms), dominated by the state interval window. Once a command is received by Lua, execution begins on the NEXT frame (≤16.7ms). The Lua bot runtime itself has zero latency — it responds on every tick.

<!-- ID: input_precision -->
## Input Precision

**How button presses map to frames** (`lua/common/input.lua`):

The input module is a frame-by-frame queue. Each action in the queue has a `{buttons, frames}` pair. On every call to `M.process()` (called once per frame), the current action's buttons are applied via `joypad.set()` and the frame counter decremented.

```lua
-- Format: "A:2,w:5,Down:8"
-- Results in: hold A for 2 frames, wait 5 frames, hold Down for 8 frames
-- Auto-injects RELEASE_GAP_FRAMES (default 2) gap after each button action
```

**Critical: `joypad.set()` semantics** — BizHawk applies the joypad state submitted during each frame callback for that EXACT frame. There is no queuing by the emulator itself. The Lua callback must call `joypad.set()` with the correct buttons on the exact frame they should be applied.

**The `FAST PATH` guarantee** (lines 1797-1801 of `socket_reader.lua`): When `inp.INPUT_BUSY` is true, the entire socket I/O block is skipped. The only operations are `inp.process()` and `bot_runtime.tick()`. This prevents network latency (even 200ms socket timeout) from causing frame drops mid-sequence.

**Sequence timing example — "A:2" (A press for 2 frames with default 2-frame gap)**:
- Frame 0: queued, INPUT_BUSY = true
- Frame 1: joypad.set({A=true}), frames=2→1
- Frame 2: joypad.set({A=true}), frames=1→0 → advance to gap action
- Frame 3: joypad.set({}), frames=2→1 (gap, no buttons)
- Frame 4: joypad.set({}), frames=1→0 → INPUT_BUSY=false, done

**RNG implications**: `joypad.set()` controls when the player "presses A" from the GBA perspective. If the GBA's main loop checks inputs on a specific frame (e.g., at StartMenu rendering), the Lua input queue must submit `A=true` on that exact frame.

**Can we guarantee "press A on frame N"?** YES, with caveats:
- The Lua bot runtime (`bot_runtime.lua`) already uses `_state.next_press_frame` to hold off actions until a specific frame: `if now >= _state.next_press_frame and can_advance`
- This achieves sub-frame precision from the GBA's perspective
- The uncertainty is in KNOWING which frame to target — see `seed_monitoring` section

**Release gap**: `ROMLAB_INPUT_RELEASE_GAP_FRAMES` defaults to 2. This can be configured via environment variable. Lower values reduce gap between actions; useful for tight timing sequences.

<!-- ID: frame_advance_mode -->
## Frame Advance Mode

BizHawk supports a "pause + frame advance" mode where the emulator runs exactly one frame at a time when manually stepped. This is how human TASers typically work for precise inputs.

**Current system capabilities:**
- `client.pause()` / `client.unpause()` — Lua can pause BizHawk
- `emu.frameadvance()` — advance one frame (valid only when paused)

**Is frame advance mode viable for our use case?**

The `csharp/RomLabStreamer/` C# tool exposes `DoFrameAdvance()` (verified via monodis, `bizhawk-api-discovery.md` rule). The current BizHawk debugger surface (`debug.*` WebSocket commands) also includes `debug.step` for debugger stepping.

**Analysis of frame advance for tick-perfect RNG:**

Frame advance would allow the system to:
1. Pause just before the RNG call frame
2. Step frame by frame, reading gRngValue each step
3. Press A on exactly the right frame

**Problems with frame advance approach:**
1. **Real-time is mandatory for natural timer evolution** — Fire Red's Timer1 seed depends on real-time (timer hardware running at boot). If we pause the emulator, Timer1 stops advancing. This doesn't affect gRngValue after game start (gRngValue is advanced by gameplay actions), but it does mean "waiting in paused mode" is fundamentally different from real-time play.
2. **gRngValue advances during certain callbacks** — On each VBlank interrupt (every frame), `gRngValue = LCRNG(gRngValue)`. If we step one frame at a time, we can observe this increment. This is actually USEFUL — we could step until gRngValue == target.
3. **The current architecture doesn't use frame advance** — The existing Lua bot runs in real-time. There's no mechanism for the bot_runtime to enter stepped mode.
4. **Turbo mode is more practical** — Running at 200-400% speed via `SpeedMode(int)` achieves rapid iteration without the complexity of stepping. The existing reset loop already leverages real-time speed.

**Conclusion**: Frame advance is theoretically capable of tick-perfect targeting but is not implemented and would require significant new infrastructure. Real-time bot with gRngValue monitoring (see `seed_monitoring`) is the current path and is nearly equivalent.

<!-- ID: realtime_vs_stepped -->
## Real-Time vs Stepped Execution

### Real-Time Mode (Current Approach)

**How it works**: BizHawk runs at full speed (or turbo), Lua bot runs in the `event.onframeend` callback. The bot uses gRngValue + seed prediction to target specific frames.

**Pros**:
- Already implemented and working
- Timer1 and other hardware timers advance naturally
- Bot can monitor gRngValue every frame (via `_current_seed()` → `_deps.signals.read_rng_seed()`)
- The RNG state machine in `bot_runtime.lua` already handles frame-level targeting via `_state.next_press_frame`
- Turbo mode achieves rapid iteration

**Cons**:
- Inherent ±0-30 frame uncertainty in WHEN the bot starts (depends on when Python sends the start command in the 30-frame state window)
- Cannot guarantee the A4 press happens on EXACTLY the predicted frame — can only get within ~1-2 frames via timing calibration

### Frame-Stepped Mode (Not Implemented)

**How it would work**: Pause BizHawk, read gRngValue, check if == target, if yes queue A press + unpause for one frame, else just advance one frame.

**Pros**:
- Could guarantee exact frame targeting
- No timing uncertainty once in stepped mode

**Cons**:
- More complex implementation
- Requires pausing before the RNG call window
- gRngValue is still advancing every frame (VBlank), so knowing "the right frame" still requires prediction
- Hardware timers stop during pause, which changes game behavior

### The Hybrid Approach (What Current Code Uses)

The existing system combines both: real-time running with the Lua bot reading gRngValue EVERY FRAME and using `_state.next_press_frame` to delay the press until the right moment.

The key mechanism:
- `rng_pre_a4_hold_frames` — holds off the A4 press for N frames after a3 closes
- `rng_settle_frames_min/max` — adds jitter between presses
- `rng_pre_a1_burn_frames` — waits N frames before first press to hit a specific seed window
- `rng_pre_a1_spin_steps` — extra movements to advance RNG before pressing

**This is functionally equivalent to stepped mode** when the system knows `rng_pre_a4_hold_frames` precisely. The bot waits until `now >= a4_hold_until_frame` then presses. This is a frame-exact wait — it differs from frame advance only in that time (and gRngValue) continues to advance during the wait.

**Key finding**: The current architecture supports tick-perfect targeting via `rng_pre_a4_hold_frames`. The missing piece is KNOWING the correct hold value for a given target seed. That's the calibration/learning problem, not a BizHawk capability limitation.

<!-- ID: seed_monitoring -->
## Seed Monitoring — Can Lua Monitor gRngValue in Real-Time?

**YES. This is already implemented.** The Lua bot runtime reads gRngValue every frame.

**Address**: `ADDR.rng_value = 0x03005000` — this is a fixed IWRAM global in Fire Red. Confirmed in `socket_reader.lua` line 116 and the `ADDR` table.

**Current implementation in `bot_runtime.lua`**:

```lua
local function _current_seed()
    if _deps.signals and _deps.signals.read_rng_seed then
        local ok, seed = pcall(_deps.signals.read_rng_seed)
        if ok and type(seed) == "number" then
            return seed
        end
    end
    return nil
end
```

This is called EVERY FRAME in `M.tick()`:
```lua
_state.seed_current = _current_seed()
```

**What the bot does with gRngValue**:

1. **`rng_unique_wait` mode**: waits until gRngValue changes from its initial value (seed has "diverged"), then proceeds. This waits for RNG to advance away from a known bad seed.

2. **`rng_avoid_seed_starts` / `rng_avoid_seed_candidates`**: blocklist of seed values to skip (up to 8 entries each). If current seed matches a blocked value, the bot skips it.

3. **`rng_expected_seed_start` / `rng_expected_seed_candidate` / `rng_expected_pid`**: expected values for verification — compared against actual observed values in bot status JSON.

4. **Seed logging**: `seed_start`, `seed_after_unique_wait`, `seed_at_candidate`, `seed_current`, `seed_last_press` — all tracked frame-by-frame.

**Can Lua branch on gRngValue?** YES — the `rng_unique_wait` stage already does this: it reads gRngValue, checks if it diverged from the start value, and only then proceeds. This is a live, every-frame seed comparison.

**Key gap**: The current bot does NOT implement "wait until gRngValue == X, then press A". It does "wait N frames (via rng_pre_a4_hold_frames), then press A". The difference: the hold approach relies on the PokeFinder-predicted delay offset being accurate. A direct "match seed then press" approach would be more robust but requires knowing WHICH specific seed value to match just before the generation call.

**Feasibility of direct seed matching**:
- YES: Lua reads gRngValue every frame at 0x03005000
- The Lua bot could easily add a new stage: `rng_target_seed_wait` that monitors gRngValue and presses A when it hits a pre-configured target value
- This would eliminate timing calibration uncertainty entirely
- Requires knowing the exact seed value at the moment before the generation call — computable from PokeFinder-style offset math on the desired target seed

<!-- ID: recommended_approach -->
## Recommended Approach

Based on the research findings, here is the recommended strategy for tick-perfect RNG manipulation:

### Short-Term: Improve `rng_pre_a4_hold_frames` Precision (Already Feasible)

The current system already supports tick-level targeting via `rng_pre_a4_hold_frames`. The main need is accurate hold value prediction from PokeFinder offset data.

**Mechanism:**
1. Python computes target seed (via rng_oracle + PokeFinder offset math)
2. Python predicts the `seed_candidate` value (gRngValue at the moment Lua observes party change)
3. Python calculates how many frames to hold between A3 (YES confirm) and A4 (final press)
4. This hold value is sent to Lua as `rng_pre_a4_hold_frames`
5. Lua executes: waits exactly N frames after A3 closes, then presses A4

**Frame precision**: The Lua bot's `now >= a4_hold_until_frame` check is exact to 1 frame. The remaining uncertainty is in whether Python's predicted hold value is correct.

**Path to improvement**: Better hold value prediction = more hits. This is the calibration/learning layer's job.

### Medium-Term: Add `rng_target_seed_wait` Stage to bot_runtime.lua

**This is the highest-precision option available.** Instead of counting hold frames, the bot watches gRngValue and presses A the moment it hits a specific value.

```lua
-- Proposed new stage in bot_runtime.lua tick():
if _state.stage == "rng_target_seed_wait" then
    local seed = _current_seed()
    if seed == _state.config.rng_target_seed then
        _queue_a_press("a4_acquire")
        _set_stage("a4_acquire", "target seed matched", _state.config.a4_timeout_frames)
        return
    end
    if _stage_timed_out() then
        -- Fallback: seed never appeared, use current seed
        _queue_a_press("a4_acquire")
        _set_stage("a4_acquire", "target seed timeout fallback", _state.config.a4_timeout_frames)
    end
    return
end
```

**Why this is best**: Eliminates timing drift entirely. The press happens on the EXACT frame gRngValue == target. Since gRngValue is LCRNG-deterministic from `seed_candidate`, we can compute exactly what value to watch for using reverse LCRNG by the offset count.

**Remaining uncertainty**: gRngValue advances by LCRNG every VBlank. The question is whether the target seed will actually appear in the polling window (between A3 close and the generation call). If the calibration/timing is roughly correct, this stage would catch it precisely.

### Frame-Advance Mode: Low Priority

Not recommended for the current architecture. Real-time with direct seed matching achieves equivalent precision with less implementation complexity.

### Summary Table

| Approach | Precision | Implementation Cost | Current Status |
|----------|-----------|--------------------:|----------------|
| `rng_pre_a4_hold_frames` | ±1-2 frames | Low | Implemented |
| `rng_target_seed_wait` | ±0 frames | Medium (new Lua stage) | Not implemented |
| Frame advance stepping | ±0 frames | High (new infra) | Not implemented |

**Recommendation**: Implement `rng_target_seed_wait` as the next Lua bot stage. Requires:
1. A new `rng_target_seed` config field in ipc.lua parse_request and bot_runtime config
2. A new stage handler in bot_runtime.lua `M.tick()`
3. Python-side: compute the exact gRngValue to match (= reverse-LCRNG the target seed by offset calls)
4. Pass the value in the bot_control start payload
