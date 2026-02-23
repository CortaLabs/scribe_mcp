---
id: automation_rng_modular_2026_02_21-implementation-report-20260221-0735
title: "Implementation Report: Task 2.1 \u2014 Controller Integration"
doc_type: custom
doc_name: IMPLEMENTATION_REPORT_20260221_0735
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 07:35:46 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Implementation Report: Task 2.1 — Controller Integration

**Date**: 2026-02-21 07:35 UTC
**Agent**: CoderAgent
**Project**: automation_rng_modular_2026_02_21
**Task**: 2.1 — Wire seed-match mode into StarterResetController

## Summary

Implemented seed-match tick-perfect execution support in the StarterResetController. When `rng_use_seed_match=True`, the controller computes a target seed via `rng_oracle.compute_target_seed()` and sends it to Lua, which waits for `gRngValue` to match before pressing A. This replaces frame-counted hold delays with tick-perfect seed matching.

## Files Changed

| File | Changes |
|------|---------|
| `src/rom_lab/api/routes/automation/controller.py` | Added `_press_to_generation_offset` instance var, 3 new fields in `_bot_start_fields`, target_seed computation in overlay, bot status extraction for seed-match fields, `_calibrate_press_offset()` method, calibration call in `_run_loop` |
| `src/rom_lab/api/routes/automation/learner.py` | Added seed-match verification fields to `_build_prediction_metrics` (target_seed, seed_at_match, verification_outcome) |
| `src/rom_lab/api/routes/automation/models.py` | Added `rng_use_seed_match` (bool) and `rng_seed_wait_timeout_frames` (int) to `StarterResetStartRequest` |
| `src/rom_lab/api/routes/automation/constants.py` | Added `DEFAULT_RNG_USE_SEED_MATCH=False` and `DEFAULT_RNG_SEED_WAIT_TIMEOUT_FRAMES=600` |

## Checklist Items Completed

- [x] 2.1.1: `_press_to_generation_offset` instance variable (7 grep hits)
- [x] 2.1.2: 3 new bot_start_fields (rng_target_seed: 5 hits)
- [x] 2.1.3: Target seed computed in overlay via compute_target_seed (1 hit)
- [x] 2.1.4: Python A2/A3 naturally skipped (exact path has no Python A2/A3 polling)
- [x] 2.1.5: `_calibrate_press_offset` method added (2 hits: definition + call)
- [x] 2.1.6: Bot status fields extracted (seed_at_match: 4 hits)
- [x] 2.1.7: All 172 tests pass (71+10+51+40)

## Tests

- [x] test_automation_routes: 71 passed
- [x] test_starter_target_planner: 10 passed
- [x] test_seed_match_computation: 51 passed
- [x] test_perception_fixes: 40 passed
- [x] Total: 172 passed, 0 failed

## Key Design Decisions

1. **Backward compatible**: `rng_use_seed_match` defaults to `False` — old flow unchanged
2. **Natural A2/A3 skip**: The exact path already delegates to Lua for A2/A3 — no conditional skip needed
3. **Combined PID+IV calibration**: `_calibrate_press_offset` uses `find_offset_for_pokemon` (combined search) rather than separate PID/IV searches
4. **Calibration gated on seed-match mode**: Only runs when `rng_use_seed_match=True` in the rng_plan
5. **Verification outcome taxonomy**: exact_hit / seed_hit_pid_miss / total_miss / timeout

## Confidence: 0.95

High confidence — all checklist items verified with grep/test proof. Only remaining unknowns are live runtime behavior (Lua seed reporting fields need Wave 1 Lua changes to be active).
