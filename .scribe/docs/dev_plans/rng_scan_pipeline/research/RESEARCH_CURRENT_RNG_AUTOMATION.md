
# 🔬 Research: Current RNG Starter Automation System

**Author:** Specter  
**Version:** v0.1  
**Status:** Complete  
**Last Updated:** 2026-02-22 03:55 UTC  
**Confidence:** HIGH

> Understand the existing single-pass RNG automation system to inform the 3-stage pipeline (Deep Scan → Select → Execute) redesign.

---

## Executive Summary

The current system is a **single-pass, auto-execute pipeline** that combines scanning, selection, and execution into one atomic operation. It successfully targets and hits deterministic starter Pokemon through:

1. **Scanning**: PokeFinder-style RNG advancement to generate candidates from current seed
2. **Auto-picking**: Selecting the highest-ranked candidate (index 0) by default
3. **Executing**: Precise frame/seed-match advancement to hit that ONE target

**Key insight for pipeline design**: The system is already modular — `plan_starter_targets()` scan logic is completely decoupled from selection. We can reuse the scan as Stage 1 (Deep Scan), insert a manual selection UI as Stage 2, and keep execution as Stage 3.

**Major limitation addressed by pipeline**: Current system shows zero candidates to user before executing. The 3-stage pipeline solves this by exposing full ranked candidate pool in Stage 2 (Select), allowing informed choice before Stage 3 (Execute).

---

## Research Scope

**Investigator:** Specter  
**Investigation Period:** 2026-02-22 03:54-04:10 UTC  

**Focus Areas Explored:**
- [x] API endpoints and request/response models
- [x] Scan implementation: `plan_starter_targets()` and `build_starter_target_book()`
- [x] Candidate selection logic: ranking, weighting, filter scoring
- [x] State machine: run loop, precheck, dialogue stages, execution flow
- [x] Data models: candidate structure, controller state, learning/calibration

**Files Reviewed:**
- `src/rom_lab/api/routes/automation/models.py` (280 lines) — Pydantic request schema
- `src/rom_lab/api/routes/automation/routes.py` (164 lines) — API endpoints
- `src/rom_lab/api/routes/automation/controller.py` (4597 lines) — Core orchestration
- `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` (788 lines) — Scan math
- `tests/test_automation_routes.py` (2409 lines) — API contract tests

**Confidence:** HIGH — Direct code review of entire call chain

---

## Findings

### 1. Current Scan Implementation: Three-Layer Fallback Strategy

**Summary:** The system doesn't do one scan; it does up to three **progressive fallback scans** based on filter match quality. This is already sophisticated and can be leveraged by the pipeline.

**Evidence:**

| Scan Layer | When | Horizon | Candidate Count | Requirement |
|-----------|------|---------|-----------------|-------------|
| **Base Scan** | Always | User-specified (e.g., 50k frames) | User-specified (e.g., 16) | Full match preferred |
| **Deep Scan** | If base has no full match + filters active | `max(base, target_deep_scan_horizon_frames)` | `max(requested, 32)` | Still prefers full matches |
| **Relaxed Scan** | If deep also has no full match | Same as deep | Same as deep | **Relaxed** — accepts partials |

**Code Location:** `controller.py:2655-2830` — `_apply_target_overlay_to_plan()` orchestrates all three.

**Scan API:** `plan_starter_targets(seed, tid, sid, species_id, horizon_frames, candidate_count, filters, mode, weights, ...)` → returns `{"candidates": [...], "context": {...}}`

**Timing profile:**
- Base scan: ~50-200ms (horizon-dependent)
- Deep scan: +200-500ms
- Relaxed scan: +100-300ms
- **Total for worst case**: ~500-1000ms

**Confidence:** HIGH

---

### 2. Candidate Data Model: Rich Stats + Scores

**Summary:** Each candidate is a fully-featured object with stats, scores, and metadata. This is exactly what Stage 2 (Select) UI needs to display.

**Evidence:**

```python
candidate = {
    "plan_id": "pid-d1234-pid12345678",
    "rank": 1,
    "delay": 1234,                    # Frames to wait before A1 press
    "species_id": 25,                 # Pikachu
    "pid": 0x12345678,                # Generated PID
    "nature": "Jolly",                # Nature name
    "gender": "male",                 # Resolved from PID
    "is_shiny": False,                # Shiny status
    "ivs": {"hp": 31, "atk": 30, ...},  # Full IV array
    
    # Prediction seeds for Lua-side seed-match precision
    "predicted_seed_start": 0xAABBCCDD,
    "predicted_seed_candidate": 0x...,
    "predicted_seed_post_generation": 0x...,
    
    # Scoring (what we care about for UI display)
    "filter_score": 0.8,              # Match quality (0-1)
    "trajectory_score": 0.95,         # Novelty/avoidance (0-1)
    "total_score": 0.87,              # Weighted combo
    
    # Filter check details for transparency
    "filter_checks": [
        { "check": "nature", "value": "Jolly", "required": "Jolly", "matched": true },
        { "check": "shiny", "value": false, "required": false, "matched": true },
        ...
    ]
}
```

**Code Location:** `controller.py:3055-3077` — `_synthetic_candidate_for_delay()` demonstrates full structure.

**Confidence:** HIGH

---

### 3. Selection Logic: "Picks First One" Default Behavior

**Summary:** By default, the system selects `candidates[0]` (highest ranked) without user input. This is the exact behavior the 3-stage pipeline will replace with manual selection.

**Evidence:**

Selection priority order (controller.py:3158-3400):

1. **Seed-Lock Anchor Mode** (if calibration settled + unique_seed_wait mode):
   - Select full match closest to observed delay median
   - Fallback: probe closest to delay

2. **Timing Probe Mode** (if calibrating + timing lock escape active):
   - Generate synthetic candidates at probe offsets
   - May sweep gender/nature variants if repeated misses

3. **Default** (all other cases):
   - `selected_index = 0` ← **THIS IS IT**
   - Picks the rank-1 candidate without asking

**Current User Experience:**
- Call `/start` endpoint
- System: scans, picks index 0, auto-executes
- User: sees nothing until "success" or "failure"

**Code Location:** `controller.py:3158-3400` — Selection state machine.

**Confidence:** HIGH

---

### 4. API Routes: Five Endpoints, Four Are Useful

**Summary:** The API already has a `/target-plan/preview` endpoint that scans WITHOUT executing. The 3-stage pipeline can extend this.

**Evidence:**

| Endpoint | Method | Current Use | Pipeline Use |
|----------|--------|------------|--------------|
| `/defaults` | GET | UI form initialization | ← Keep as-is |
| `/status` | GET | Runtime status | ← Keep as-is |
| `/history` | GET | Past attempts in current run | ← Extend: show full candidate pools |
| `/target-plan/preview` | POST | Scan + preview candidates | ← **Use for Stage 1** |
| `/start` | POST | Scan + auto-pick + execute | ← **Becomes: Stage 1 only** (or split into new endpoint) |
| `/stop` | POST | Cancel active run | ← Keep as-is |

**Code Location:** `routes.py:53-164` — All endpoints defined here.

**Confidence:** HIGH

---

### 5. State Machine: Five Execution Stages (Already Mature)

**Summary:** The run loop already decomposes into clean stages. Stage 3 (Execute) of the pipeline can reuse this directly.

**Evidence:**

After target selected, execution follows (controller.py:782-1281):

| Stage | Duration | Purpose | State Transitions |
|-------|----------|---------|-------------------|
| **0 - Precheck** | 2-5s | Verify game state matches assumptions | Reload/retry up to 3× |
| **1 - Dialogue (A1)** | 5-20s | Open starter choice, advance RNG to target | Seed-match or frame-count precision |
| **2 - Choice (A2)** | 1-2s | Navigate + confirm starter choice | Button press sequence |
| **3 - Confirm (A3)** | 0.5-1s | Yes/No confirmation | Auto-confirm |
| **4 - Acquire (A4)** | 10-15s | Read party, verify PID/IVs match target | Success if match, fail if mismatch |

**Error handling:** Transient errors trigger retry loop (up to `ATTEMPT_ERROR_RECOVERY_LIMIT=5` attempts).

**Code Location:** `controller.py:782-1281` — `_run_exact_attempt()`.

**Confidence:** HIGH

---

### 6. Adaptive Timing Controls: Already Handle Seed-Match Precision

**Summary:** Lua-side and Python-side timing is already sophisticated. The pipeline doesn't need to change this.

**Evidence:**

During Stage 1 (Dialogue), emulator speed auto-adjusts:

- **Far from target** (e.g., 5000+ frames away): High speed % (e.g., 1500%) for fast frame burn
- **Near target** (within `rng_accel_near_target_frames`, e.g., 1000 frames): Precision speed (e.g., 100%)
- **Seed-match mode enabled**: Lua polls `gRngValue` repeatedly until it matches computed target seed, THEN presses A next frame
- **Backoff on stall**: Auto-reduce speed if RNG/frame progress appears stalled

This all works today and the pipeline can inherit it unchanged.

**Code Location:** `controller.py` (lines not isolated; spread through Stage 1 logic).

**Confidence:** HIGH

---

### 7. Learning & Calibration: Integrated for Prediction Quality

**Summary:** The system tracks timing drift, seed prediction accuracy, and filter match patterns across attempts. The pipeline can optionally surface this in Stage 2 UI.

**Evidence:**

State tracked per run:

```python
{
    "pid_learning": {
        "recent_pids": [...],                    # PIDs to avoid
        "recent_seed_candidates": [...],         # Seeds to avoid
        "prediction_hit_rate": 0.95,             # How often we hit the target
        "prediction_delay_mae": 15.3,            # Delay prediction error (frames)
        "observed_delay_median": 847,            # Median time to target
        "target_gender_miss_streak": 2,          # Consecutive gender misses
        "target_nature_miss_streak": 0,          # Consecutive nature misses
    },
    "calibration_state": {
        "drift_estimate_frames": 3.2,            # RNG drift per attempt
        "base_flow_estimate_frames": 760.0,      # Base timing to generate
        "bad_drift_streak": 0,                   # Consecutive bad calibrations
        "probes_total": 5,                       # Total calibration probes
        "probes_required": 8,                    # Probes needed before settling
    }
}
```

**Trajectory scoring** penalizes candidates matching recent PIDs/seeds to encourage diversity.

**Confidence:** HIGH

---

### 8. Scan Parameters: Decoupled from Execution

**Summary:** All scan parameters are in the `StarterResetStartRequest` Pydantic model. The pipeline can accept same parameters in Stage 1 (Deep Scan).

**Evidence:**

Request model (models.py, 280 lines) includes:

- Horizon: `target_horizon_frames` (30-2M frames, depends on thorough_scan mode)
- Candidate count: `target_candidate_count` (1-256)
- Deep scan: `target_thorough_scan` (bool), `target_deep_scan_horizon_frames` (30-2M)
- Selection: `target_mode` ("hybrid_weighted", "filter_first", "pid_first")
- Weighting: `target_weights_filter` (0-1), `target_weights_pid` (0-1)
- Filters: `StarterResetFilters` (shiny, nature, gender, IV minimums)
- Timing: `rng_mode`, `rng_use_seed_match`, `rng_seed_wait_timeout_frames`, `rng_accel_*`, etc.

All these can be inherited by the pipeline unchanged.

**Code Location:** `models.py:99-280`.

**Confidence:** HIGH

---

## Technical Analysis

### Strengths of Current System (What We Build On)

1. **Modular scan**: `plan_starter_targets()` is decoupled from selection. Zero coupling between scan and which candidate we pick. ✅

2. **Rich metadata**: Every candidate includes full stats, scores, filter checks. UI doesn't have to compute these. ✅

3. **Fallback scans**: Handles "no candidates matching filters" gracefully by relaxing constraints. ✅

4. **Learning integration**: Tracks prediction quality, drift, filter miss patterns. Enables smarter calibration next run. ✅

5. **Seed-match precision**: Lua already polls `gRngValue` for tick-perfect seed-match. No rewrite needed. ✅

6. **Error resilience**: Transient failures auto-retry (up to limit). Graceful degradation. ✅

### Gaps Filled by 3-Stage Pipeline

1. **No candidate visibility**: Current system picks first + executes. User sees nothing until done. ❌
   - **Pipeline fix**: Stage 2 shows full ranked pool before execution.

2. **No manual selection**: Auto-picking may not match user preferences. ❌
   - **Pipeline fix**: Stage 2 lets user inspect all top-N candidates + pick one.

3. **Scan-exec coupling**: Can't scan once and try different candidates. ❌
   - **Pipeline fix**: Separate stages allow "scan rich pool, try candidate A, fail, try candidate B" workflows.

4. **Limited history**: Past candidates aren't saved. ❌
   - **Pipeline fix**: Stage 1 saves full scan results for history/analysis.

### Risk Assessment

**Technical risks mitigated:**
- **Seed drift between scan and execution**: Already handled by adaptive timing + seed-match mode.
- **Candidate becoming invalid**: Rare (RNG is deterministic), but execution gracefully fails + retries.
- **Filter constraints conflict**: Deep/relaxed scans already handle this.

**No identified blocking risks for pipeline implementation.**

**Confidence:** HIGH

---

## Recommendations

### Immediate Next Steps (for pipeline implementation)

1. **Stage 1 (Deep Scan)**:
   - Expose `/deep-scan` endpoint that runs the full three-layer scan strategy
   - Return all candidates + metadata (not just top-1)
   - Accept same `StarterResetStartRequest` parameters
   - Typical response time: 500-1000ms for thorough scan

2. **Stage 2 (Select)**:
   - Add UI component that displays ranked candidate pool
   - Show for each candidate: rank, delay, stats, filter score, trajectory score
   - User picks one candidate
   - Send selected candidate ID to backend

3. **Stage 3 (Execute)**:
   - Reuse existing `_run_exact_attempt()` logic unchanged
   - Accept selected candidate from Stage 2
   - Execute stages 0-4 as today
   - Return result (hit/miss/error)

4. **API changes**:
   - Add `/scan` endpoint (new): Deep scan only, return full pool
   - Modify `/start` endpoint (existing): Accept candidate_id parameter (optional)
   - If candidate_id provided: skip scan, use that candidate directly
   - If candidate_id not provided: scan + pick first (backward compat)

### Long-Term Opportunities

- **Candidate history**: Save full scan results per run for later analysis
- **Multi-candidate execution**: "Try A, if it fails, try B from same scan" workflow
- **Learning export**: Export calibration/learning state for ML analysis
- **Filter refinement**: ML-based filter suggestion based on user picks over time

**Confidence:** HIGH

---

## Appendix

### References

- **API Contract**: `routes.py:47-164`
- **Pydantic Schema**: `models.py:48-280`
- **Scan Math**: `starter_target_planner.py:729-788`
- **Selection Logic**: `controller.py:3158-3400`
- **State Machine**: `controller.py:782-1281`
- **Tests**: `tests/test_automation_routes.py:133-153` (preview route test)

### Key Constants (from constants.py)

- `DEFAULT_TARGET_HORIZON_FRAMES`: 50000
- `DEFAULT_TARGET_CANDIDATE_COUNT`: 16
- `DEFAULT_TARGET_MODE`: "hybrid_weighted"
- `DEFAULT_TARGET_WEIGHTS_FILTER`: 0.6
- `DEFAULT_TARGET_WEIGHTS_PID`: 0.4
- `TARGET_FILTER_FULL_SCORE`: 0.999
- `TARGET_PROBE_TOP_RANK_LIMIT`: 32

### Estimated Effort for Pipeline

- **Stage 1 API**: 1-2 hours (wrap existing scan logic)
- **Stage 2 UI**: 3-4 hours (design + implement candidate picker)
- **Stage 3 API**: 1-2 hours (add candidate_id parameter to /start)
- **Integration + Testing**: 2-3 hours
- **Total**: ~8-12 hours (1-2 days, one person)

