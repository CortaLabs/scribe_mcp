---
id: streamer_optimization-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 streamer_optimization"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 03:59:34 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — streamer_optimization
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 03:19:07 UTC

> Execution roadmap for streamer_optimization.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 1 — C# Warp Optimization | Maximize BizHawk frame throughput during warp | EnableRewind(false), FrameSkip(9), CancelAdvance command, GetApproxFramerate telemetry | 0.90 |
| Phase 2 — Python Warp Pipeline | Chunked advancement, cancellation, WebSocket drain | Chunked warp loop, _cancel_advance(), ws_endpoint drain mode, multi-shot warp | 0.92 |
| Phase 3 — Integration & Validation | End-to-end warp optimization verified | Full starter reset cycle at >3000fps, all tests green, no state leaks | 0.85 |

**Parallelism:** Phase 1 and Phase 2 can execute in parallel — they modify different codebases (C# vs Python) with no shared dependencies. Phase 3 requires both Phase 1 and Phase 2 complete.

**Target:** >3000fps emulated frame throughput during warp (current baseline: ~1500-2000fps with InvisibleEmulation + SpeedMode(6400) only).
<!-- ID: phase_0 -->
## Phase 1 — C# Warp Optimization

**Objective:** Maximize BizHawk emulator frame throughput by adding all available speed bypass settings and a cancellation command.

**Parallel with:** Phase 2 (no dependencies between them)

---

### Task Package 1.1: Enhanced SetWarpModeActive

**Scope:** Add EnableRewind(false) and FrameSkip(9) to warp entry/exit, with save/restore for both.
**Files to Modify:** `csharp/RomLabStreamer/StreamerForm.cs`
**Dependencies:** None (first task)

**Specifications:**
1. Add two new fields:
   - `private bool _warpSavedRewindEnabled;`
   - `private int _warpSavedFrameSkip;`
2. In `SetWarpModeActive(true)` block (lines 426-445), after existing sound/video/invisible calls:
   - Save: `_warpSavedRewindEnabled = /* no getter — assume true */; _warpSavedFrameSkip = 0;`
   - Set: `APIs.EmuClient.EnableRewind(false);`
   - Set: `APIs.EmuClient.FrameSkip(9);`
3. In `SetWarpModeActive(false)` block:
   - Restore: `APIs.EmuClient.EnableRewind(_warpSavedRewindEnabled);`
   - Restore: `APIs.EmuClient.FrameSkip(_warpSavedFrameSkip);`
4. In unload cleanup (lines 544-560), add same restoration calls

**Verification:**
- [ ] `scripts/build-streamer.sh` compiles without error
- [ ] DLL loads in BizHawk without crash
- [ ] Warp mode on/off cycle completes without BizHawk state corruption

**Out of Scope:** CancelAdvance, GetApproxFramerate, Config reflection (separate tasks)

---

### Task Package 1.2: CancelAdvance Command

**Scope:** Add SUB_CANCEL_ADVANCE (0x0B) protocol command enabling Python to cancel in-progress frame advancement.
**Files to Modify:** `csharp/RomLabStreamer/Protocol.cs`, `csharp/RomLabStreamer/CommandHandler.cs`, `csharp/RomLabStreamer/StreamerForm.cs`
**Dependencies:** None (independent of Task 1.1)

**Specifications:**
1. `Protocol.cs`: Add `CancelAdvance = 0x0B` to SubCommand enum
2. `CommandHandler.cs`:
   - Add field: `private Action? _cancelAdvance;`
   - Add registration method: `public void SetCancelAdvanceCallback(Action callback)`
   - Add handler: `private void DoCancelAdvance(Command cmd)` that invokes `_cancelAdvance?.Invoke()` and sends OK response
   - Wire in dispatch switch: case `SubCommand.CancelAdvance` -> `DoCancelAdvance(cmd)`
3. `StreamerForm.cs`:
   - In `AdvanceFrames` method: register a cancel callback that sets `_pendingAdvanceFrames = 0`
   - After advancement completes: clear callback
   - In response, include `frames_remaining` field (>0 = cancelled early)

**Verification:**
- [ ] `scripts/build-streamer.sh` compiles without error
- [ ] Send `cancel_advance` during active warp via WebSocket — verify early termination
- [ ] Send `cancel_advance` when no warp active — verify no-op response

**Out of Scope:** Python-side cancel logic (Phase 2)

---

### Task Package 1.3: Warp Telemetry (GetApproxFramerate)

**Scope:** Include emulator frame rate in warp mode and advance_frames responses for performance measurement.
**Files to Modify:** `csharp/RomLabStreamer/CommandHandler.cs`
**Dependencies:** Task 1.1 (warp must work correctly first)

**Specifications:**
1. In `DoWarpMode` response JSON, add field: `"approx_framerate": APIs.EmuClient.GetApproxFramerate()`
2. In `DoAdvanceFrames` completion response JSON, add field: `"approx_framerate": APIs.EmuClient.GetApproxFramerate()`
3. Frame rate value is informational only — Python logs it but does not act on it

**Verification:**
- [ ] Warp mode on response includes `approx_framerate` field
- [ ] Advance frames completion response includes `approx_framerate` field
- [ ] Value is a positive integer during active emulation

**Out of Scope:** Config reflection (RunLuaDuringTurbo etc.) — deferred to future work
<!-- ID: phase_1 -->
## Phase 2 — Python Warp Pipeline

**Objective:** Replace the blocking single-call warp advancement with a chunked, cancellable loop, add WebSocket drain mode, and remove the one-shot warp limitation.

**Parallel with:** Phase 1 (no dependencies between them)

---

### Task Package 2.1: WebSocket Warp Drain Mode

**Scope:** Add a module-level warp flag to ws_endpoint.py that makes _send_frames drain the queue without encoding during warp.
**Files to Modify:** `src/rom_lab/streaming/ws_endpoint.py`, `src/rom_lab/streaming/frame_receiver.py`
**Dependencies:** None (first task in Phase 2)

**Specifications:**
1. `ws_endpoint.py`: Add module-level state:
   ```python
   _warp_active: bool = False
   
   def set_warp_active(active: bool) -> None:
       global _warp_active
       _warp_active = active
   ```
2. `ws_endpoint.py`: In `_send_frames()` loop (lines 370-434), after frame dequeue and coalesce:
   ```python
   if _warp_active:
       continue  # Drain queue without encoding
   ```
3. `frame_receiver.py`: Add constant `SUB_CANCEL_ADVANCE: int = 0x0B` (for Task 2.3)

**Verification:**
- [ ] `pytest -q tests/test_ws_endpoint_commands.py` — all existing tests pass
- [ ] New test: `test_send_frames_drains_during_warp` — mock queue, verify no encode calls when warp active
- [ ] New test: `test_warp_active_flag_set_on_warp_mode_on`

**Out of Scope:** Controller changes (Task 2.2), cancel logic (Task 2.3)

---

### Task Package 2.2: Chunked Warp Loop (Controller)

**Scope:** Replace the blocking single-call `_advance_frames_bulk(warp_count)` with a chunked loop that processes frames in WARP_CHUNK_SIZE increments.
**Files to Modify:** `src/rom_lab/api/routes/automation/controller.py`, `src/rom_lab/api/routes/automation/constants.py`, `src/rom_lab/api/routes/automation/models.py`
**Dependencies:** Task 2.1 (ws_endpoint drain must exist for _set_ws_warp_state to call)

**Specifications:**
1. `constants.py`: Add `WARP_CHUNK_SIZE: int = 10_000`
2. `models.py`: Add `warp_chunk_size: int = 10_000` field to `StarterResetStartRequest`
3. `controller.py`: Add method `_set_ws_warp_state(self, active: bool) -> None`:
   ```python
   async def _set_ws_warp_state(self, active: bool) -> None:
       from rom_lab.streaming.ws_endpoint import set_warp_active
       set_warp_active(active)
   ```
4. `controller.py`: Replace warp block (lines ~2105-2133) with chunked loop:
   ```python
   if (warp_enabled and frames_to_target is not None
       and int(frames_to_target) > warp_threshold):
       warp_count = int(frames_to_target) - warp_landing_buffer
       if warp_count > 0:
           await self._send_lua_warp_control("start")
           await self._set_warp_mode(True)
           await self._set_ws_warp_state(True)
           try:
               remaining = warp_count
               while remaining > 0 and not self._warp_cancelled:
                   chunk = min(remaining, chunk_size)
                   success = await self._advance_frames_bulk(chunk)
                   if not success:
                       break
                   remaining -= chunk
           finally:
               await self._set_ws_warp_state(False)
               await self._set_warp_mode(False)
               await self._send_lua_warp_control("stop")
           continue  # Re-check seed after warp (NO one-shot flag)
   ```
5. Remove `warp_engaged` one-shot flag entirely — warp can re-engage on subsequent loops

**Verification:**
- [ ] `pytest -q tests/test_warp_mode.py` — all existing tests pass
- [ ] New test: `test_chunked_advancement_splits_large_warp` — 25k frames -> 3 chunks
- [ ] New test: `test_multi_shot_warp` — verify re-engagement after first warp

**Out of Scope:** Cancel command sending (Task 2.3), telemetry logging

---

### Task Package 2.3: Cancel Advance Support (Python Side)

**Scope:** Add _cancel_advance() method to controller that sends SUB_CANCEL_ADVANCE to C#, and wire cancellation flag into chunked loop.
**Files to Modify:** `src/rom_lab/api/routes/automation/controller.py`
**Dependencies:** Task 2.2 (chunked loop must exist), Phase 1 Task 1.2 (C# CancelAdvance must exist for end-to-end, but Python code can be written independently)

**Specifications:**
1. Add instance variable: `self._warp_cancelled: bool = False`
2. Add method:
   ```python
   async def _cancel_advance(self) -> None:
       self._warp_cancelled = True
       if self._frame_receiver:
           await self._frame_receiver.send_sub_command(SUB_CANCEL_ADVANCE)
   ```
3. Reset `self._warp_cancelled = False` at start of each warp block
4. In chunked loop (Task 2.2), check `self._warp_cancelled` between chunks (already specified in 2.2)
5. Add error handling: if `_advance_frames_bulk` raises during a chunk, ensure warp state is still cleaned up (the try/finally from 2.2 handles this)

**Verification:**
- [ ] `pytest -q tests/test_warp_mode.py` — all existing + new tests pass
- [ ] New test: `test_cancel_advance_stops_between_chunks` — set cancel flag, verify early exit
- [ ] New test: `test_warp_state_restored_on_error` — raise during chunk, verify cleanup

**Out of Scope:** UI cancel button, automation stop endpoint wiring
<!-- ID: milestone_tracking -->
## Phase 3 — Integration & Validation

**Objective:** Verify end-to-end warp optimization with both C# and Python changes deployed together.

**Dependencies:** Phase 1 AND Phase 2 must both be complete.

---

### Task Package 3.1: End-to-End Integration Test

**Scope:** Deploy both C# and Python changes, run full starter reset cycle, verify performance and correctness.
**Files to Modify:** None (validation only)
**Dependencies:** All Phase 1 and Phase 2 tasks complete

**Specifications:**
1. Build and deploy C# DLL: `scripts/build-streamer.sh && scripts/build-streamer.sh deploy`
2. Restart BizHawk with updated DLL
3. Restart `rom-lab serve` with updated Python
4. Run full regression suite:
   ```bash
   pytest -q tests/test_ws_endpoint_commands.py tests/test_warp_mode.py tests/test_automation_routes.py
   ```
5. Start starter reset automation via API
6. Observe and record:
   - Warp engage/disengage cycle in logs
   - `approx_framerate` values in warp mode responses
   - WebSocket client behavior during warp (should see frame freeze then resume)
   - Multiple warp re-engagements (no one-shot limitation)
7. Send cancel during active warp — verify graceful termination
8. Run 10 consecutive starter resets — verify no state leaks
9. Check BizHawk state after full run — sound on, video streaming, rewind enabled, normal speed

**Verification:**
- [ ] All pytest tests pass
- [ ] `approx_framerate` > 3000 during warp (target performance)
- [ ] WebSocket clients see frame freeze during warp, resume after
- [ ] Cancel works end-to-end (Python -> C# -> early termination)
- [ ] 10 consecutive resets complete without state corruption
- [ ] BizHawk returns to normal state after all warps

**Out of Scope:** Performance tuning beyond initial benchmarks (future iteration)

---

## Milestone Tracking

| Milestone | Owner | Status | Evidence/Link |
|-----------|-------|--------|---------------|
| Phase 1 Task 1.1: Enhanced SetWarpModeActive | forge-csharp | Complete | EnableRewind(false), FrameSkip(9), save/restore, cleanup — build succeeds |
| Phase 1 Task 1.2: CancelAdvance Command | forge-csharp | Complete | Protocol 0x0B, handler, dispatch, callback — build succeeds |
| Phase 1 Task 1.3: Warp Telemetry | forge-csharp | Complete | GetApproxFramerate in WarpMode + AdvanceFrames responses — build succeeds |
| Phase 2 Task 2.1: WebSocket Drain Mode | forge-python | Complete | _warp_active flag, set_warp_active(), drain mode in _send_frames |
| Phase 2 Task 2.2: Chunked Warp Loop | forge-python | Complete | WARP_CHUNK_SIZE, chunked loop, warp_engaged removed |
| Phase 2 Task 2.3: Cancel Advance (Python) | forge-python | Complete | _cancel_advance(), stop_event check, try/finally cleanup |
| Phase 3 Task 3.1: Integration Test | Forge/Manual | Planned | — |

Update status and evidence as work progresses. Always link to PROGRESS_LOG entries or commits.
<!-- ID: retro_notes -->
## Dependency Graph

```
Phase 1 (C#)                    Phase 2 (Python)
├─ Task 1.1 (SetWarpMode)      ├─ Task 2.1 (WS Drain)
├─ Task 1.2 (CancelAdvance)    ├─ Task 2.2 (Chunked Loop) ← depends on 2.1
└─ Task 1.3 (Telemetry) ←1.1   └─ Task 2.3 (Cancel Python) ← depends on 2.2
                    \                      /
                     └──── Phase 3 ───────┘
                           Task 3.1 (Integration)
```

**Maximum parallelism:** 2 Forge agents — one on Phase 1, one on Phase 2. Within each phase, tasks are sequential due to dependencies.

## Retro Notes & Adjustments

- Prior warp_mode_frame_advance architecture was FULLY IMPLEMENTED (not just designed). This blueprint optimizes the existing system rather than building from scratch.
- R2 research incorrectly claimed C# streams frames during warp — verified as false. C# already correctly gates video capture. Architecture adjusted to focus on Python-side drain as defense-in-depth.
- Lua scripts (runtime.lua, socket_reader.lua) already have warp gates — no changes needed. Architecture explicitly documents verified-correct components.
