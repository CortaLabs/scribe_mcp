---
id: warp_mode_frame_advance-checklist
title: "\u2705 Acceptance Checklist \u2014 warp_mode_frame_advance"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 01:26:11 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — warp_mode_frame_advance
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 00:17:37 UTC

> Acceptance checklist for warp_mode_frame_advance.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene

- [ ] **ARCHITECTURE_GUIDE.md** complete with all 10 sections <!-- ID: doc_arch -->
  - **Acceptance**: All sections populated, code references verified
  - **Verification**: `wc -l ARCHITECTURE_GUIDE.md` shows >500 lines
- [ ] **PHASE_PLAN.md** complete with 6 phases and 14 task packages <!-- ID: doc_phase -->
  - **Acceptance**: Each task package has Scope, Files, Specifications, Verification, Out of Scope
  - **Verification**: All task package headers present
- [ ] **CHECKLIST.md** complete with per-phase items <!-- ID: doc_check -->
  - **Acceptance**: Every task package has at least one verification checkbox
  - **Verification**: This file
- [ ] **Research docs referenced** in architecture <!-- ID: doc_refs -->
  - **Acceptance**: All 4 RESEARCH_*.md files cited in references section
  - **Verification**: Grep ARCHITECTURE_GUIDE.md for "RESEARCH_"
<!-- ID: phase_0 -->
## Phase 1: C# Foundation

- [x] **1.1 Protocol Constants** <!-- ID: p1_protocol -->
  - **Acceptance**: WarpMode=0x09 and AdvanceFrames=0x0A added to Protocol.cs
  - **Verification**: `dotnet build` succeeds; grep Protocol.cs for "0x09" and "0x0A"

- [x] **1.2 StreamerForm Warp State Machine** <!-- ID: p1_streamer -->
  - **Acceptance**: Warp gate in UpdateAfter(), SetWarpModeActive(), StartAdvanceFrames() methods added
  - **Verification**: `dotnet build` succeeds; constructor passes 9 delegates

- [x] **1.3 CommandHandler Warp Handlers** <!-- ID: p1_handler -->
  - **Acceptance**: DoWarpMode(), DoAdvanceFrames() handlers, MaxSpeedPercent=6400, 3 new delegates
  - **Verification**: `dotnet build` succeeds; dispatch switch includes both new SubCommands

## Phase 2: Lua Warp Gate

- [x] **2.1 Runtime Warp Gate** <!-- ID: p2_runtime -->
  - **Acceptance**: _warp_active flag, warp gate in M.tick() after INPUT_BUSY before read_context_signals
  - **Verification**: `luac -p lua/common/bot/runtime.lua` passes

- [x] **2.2 Socket Reader Warp Gate** <!-- ID: p2_socket -->
  - **Acceptance**: WARP_MODE flag, warp gate in on_frame(), warp_control command, heartbeat every 30 frames
  - **Verification**: `luac -p plugins/pokemon_fire_red/lua/socket_reader.lua` passes

- [x] **2.3 File Reader Mirror** <!-- ID: p2_file -->
  - **Acceptance**: Identical warp logic mirrored from socket_reader.lua
  - **Verification**: `luac -p plugins/pokemon_fire_red/lua/reader.lua` passes; diff confirms parity

## Phase 3: Python Plumbing

- [x] **3.1 Frame Receiver Constants** <!-- ID: p3_constants -->
  - **Acceptance**: SUB_WARP_MODE=0x09, SUB_ADVANCE_FRAMES=0x0A added
  - **Verification**: `pytest -q tests/test_frame_receiver.py` passes

- [x] **3.2 WebSocket Command Routing** <!-- ID: p3_ws -->
  - **Acceptance**: warp_mode and advance_frames commands routed in ws_endpoint.py
  - **Verification**: `pytest -q tests/test_ws_endpoint_commands.py` passes

## Phase 4: Controller Integration

- [x] **4.1 Warp Constants** <!-- ID: p4_constants -->
  - **Acceptance**: DEFAULT_WARP_MODE_ENABLED=False, threshold, buffer, max constants added
  - **Verification**: Import from constants.py succeeds

- [x] **4.2 Model Fields** <!-- ID: p4_models -->
  - **Acceptance**: warp_mode_enabled, warp_threshold_frames, warp_landing_buffer_frames on StarterResetStartRequest
  - **Verification**: Model constructs with and without warp fields

- [x] **4.3 Controller Warp Methods** <!-- ID: p4_controller -->
  - **Acceptance**: _set_warp_mode(), _advance_frames_bulk(), _send_lua_warp_control() methods; warp branch in _wait_for_lua_bot_candidate()
  - **Verification**: `pytest -q tests/test_automation_routes.py` passes (warp disabled by default)

- [x] **4.4 Warp Mode Tests** <!-- ID: p4_tests -->
  - **Acceptance**: tests/test_warp_mode.py with 6 test functions
  - **Verification**: `pytest -q tests/test_warp_mode.py` all 6 pass
<!-- ID: final_verification -->
## Phase 5: UI Extension

- [x] **5.1 Warp Status Display** <!-- ID: p5_display -->
  - **Acceptance**: _updateWarpStatusDisplay() function added; _setWarpMode() calls it
  - **Verification**: No JS console errors; warp badge visible when active

## Phase 6: Empirical Verification

- [ ] **6.1 InvisibleEmulation Test** <!-- ID: p6_invisible -->
  - **Acceptance**: Document whether InvisibleEmulation(true) suppresses video buffer writes
  - **Verification**: Test log entry with findings

- [ ] **6.2 SetSoundOn Overhead Test** <!-- ID: p6_sound -->
  - **Acceptance**: Document CPU impact of SetSoundOn(false)
  - **Verification**: Test log entry with throughput comparison

- [ ] **6.3 Maximum SpeedMode Test** <!-- ID: p6_speed -->
  - **Acceptance**: Identify highest stable SpeedMode percentage
  - **Verification**: Test log entry with stability results at each increment

## Final Verification

### Regression Suite

- [ ] **All existing Python tests pass** <!-- ID: final_pytest -->
  - **Command**: `pytest -q tests/test_automation_routes.py tests/test_ws_endpoint_commands.py tests/test_frame_receiver.py`
  - **Acceptance**: All tests pass with zero modifications to existing test files

- [ ] **New warp tests pass** <!-- ID: final_warp_tests -->
  - **Command**: `pytest -q tests/test_warp_mode.py`
  - **Acceptance**: All 6 tests pass

- [ ] **C# builds clean** <!-- ID: final_csharp -->
  - **Command**: `cd csharp/RomLabStreamer && dotnet build`
  - **Acceptance**: Build succeeded, zero warnings

- [ ] **Lua syntax valid** <!-- ID: final_lua -->
  - **Command**: `luac -p lua/common/bot/runtime.lua && luac -p plugins/pokemon_fire_red/lua/socket_reader.lua && luac -p plugins/pokemon_fire_red/lua/reader.lua`
  - **Acceptance**: All three files pass syntax check

### Zero Regression Verification

- [ ] **Default off behavior** <!-- ID: final_default_off -->
  - **Acceptance**: With warp_mode_enabled=False (default), system behavior is identical to pre-warp codebase
  - **Verification**: Run automation without warp, compare output to baseline

- [ ] **Protocol alignment** <!-- ID: final_protocol -->
  - **Acceptance**: C# SubCommand.WarpMode==0x09 matches Python SUB_WARP_MODE==0x09; same for 0x0A
  - **Verification**: Grep both files, confirm values match

- [ ] **Lua reader sync** <!-- ID: final_lua_sync -->
  - **Acceptance**: Both socket_reader.lua and reader.lua have identical warp gate logic
  - **Verification**: Diff warp-related sections of both files

### Sign-off

- [ ] **Arbiter review >= 93%** <!-- ID: final_review -->
  - **Acceptance**: Post-implementation review passes with confidence >= 0.93
  - **Verification**: Arbiter Scribe log entry with score
