---
id: warp_mode_frame_advance-implementation-report-20260222-0108
title: "Implementation Report \u2014 Phase 2: Lua Warp Gate"
doc_type: custom
doc_name: IMPLEMENTATION_REPORT_20260222_0108
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 01:08:58 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Implementation Report — Phase 2: Lua Warp Gate

**Date:** 2026-02-22 01:08 UTC
**Agent:** CoderAgent-lua (Forge)
**Project:** warp_mode_frame_advance
**Confidence:** 0.95

## Summary

Implemented Lua warp gate layer across 3 files for the warp mode frame advance feature. All changes are additive gates that default to false/inactive, ensuring zero regression risk. The warp gate skips expensive per-frame work (103+ RAM reads, JSON assembly, socket sends) during warp mode, reducing per-frame cost to a single gRngValue read.

## Files Changed

| File | Changes |
|------|--------|
| `lua/common/bot/runtime.lua` | Added `_warp_active` flag, `M.set_warp_active()`/`M.is_warp_active()` accessors, warp gate in `M.tick()` |
| `src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` | Added `WARP_MODE` flag, warp gate in `on_frame()`, `warp_control` command handler in `execute_command()` |
| `src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua` | Added `WARP_MODE` flag, warp gate in `on_frame()`, `warp_control` no-op stub in `_handle_bot_control()` |

## Implementation Details

### Task 2.1: Runtime Warp Gate (runtime.lua)
- Module-level `_warp_active = false` flag
- `M.set_warp_active(active)` and `M.is_warp_active()` accessors
- `_warp_active` reset to false in `M.init()`
- Warp gate in `M.tick()` after INPUT_BUSY check, before `read_context_signals()`:
  - Activates when `_warp_active AND stage == "rng_seed_wait"`
  - Reads seed via `_current_seed()` (reuses existing signals dependency)
  - On target match: clears `_warp_active`, falls through to normal tick
  - On no match: returns early (skips all signal reads + stage processing)

### Task 2.2: Socket Reader Warp Gate (socket_reader.lua)
- Module-level `WARP_MODE = false` and `warp_heartbeat_interval = 30`
- Warp gate in `on_frame()` after INPUT_BUSY fast path:
  - Increments frame_counter
  - Every `warp_heartbeat_interval` frames: reads ADDR.rng_value, sends JSON heartbeat via socket
  - Checks for incoming `warp_stop` command during heartbeat
  - Returns early (skips event detection, full state assembly, socket state sends)
- `warp_control` command in `execute_command()`:
  - `start`: sets WARP_MODE=true, propagates to bot_runtime
  - `stop`: sets WARP_MODE=false, propagates to bot_runtime
  - `status`: returns current WARP_MODE, rng value, frame counter

### Task 2.3: File Reader Mirror (reader.lua)
- Module-level `WARP_MODE = false` and `warp_heartbeat_interval = 30` (structural parity)
- Warp gate in `on_frame()` after INPUT_BUSY fast path (still runs IPC check for stop command)
- `warp_control` handler returns `{warp_mode=false, note="file_mode_unsupported"}`

## Key Design Decisions

1. **Used `_current_seed()` in runtime.lua** instead of raw `memory.read_u32_le()` — reuses the existing tested code path through `_deps.signals.read_rng_seed`
2. **Warp gate condition includes stage check** (`stage == "rng_seed_wait"`) — gate only activates during the specific stage that needs fast-forwarding, not during other bot stages
3. **File mode gets structural parity** but returns unsupported — warp is fundamentally a socket-mode feature since it requires bidirectional communication for start/stop commands

## Adaptation Notes

- Architecture guide used path `plugins/pokemon_fire_red/lua/` but actual paths are `src/rom_lab/plugins/pokemon_fire_red/lua/`
- Architecture guide suggested raw `memory.read_u32_le(0x03005000, "System Bus")` in runtime.lua but `_current_seed()` already exists and handles the read through the signals dependency — used that instead
- reader.lua has no `execute_command()` function — uses `ipc.check_requests()` -> custom handler pattern, so warp_control was added to `_handle_bot_control()`

## Tests

- [x] `luac -p lua/common/bot/runtime.lua` — passes
- [x] `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` — passes
- [x] `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua` — passes

## Checklist Items Updated

- [x] 2.1 Runtime Warp Gate (p2_runtime)
- [x] 2.2 Socket Reader Warp Gate (p2_socket)
- [x] 2.3 File Reader Mirror (p2_file)
