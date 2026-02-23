---
id: automation_rng_modular_2026_02_21-research-ui-surface-20260221-0809
title: "\U0001F52C Research Ui Surface 20260221 0809 \u2014 automation_rng_modular_2026_02_21"
doc_type: RESEARCH_UI_SURFACE_20260221_0809
doc_name: RESEARCH_UI_SURFACE_20260221_0809
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 08:13:41 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Ui Surface 20260221 0809 — automation_rng_modular_2026_02_21
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-21 08:09:15 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

This report catalogs the complete user-facing surface of the starter reset automation panel. It covers every UI control, every API field, the exact payload sent to POST /start, gaps between API capability and UI exposure, history table columns, status display surfaces, and the /defaults endpoint contract.

**Key finding**: The seed-match feature (rng_use_seed_match, rng_seed_wait_timeout_frames) implemented in the last wave has **zero UI presence**. It cannot be toggled from the panel. Additionally, 10 other API fields (target scoring weights, calibration knobs, horizon, candidate count) are silently server-defaulted with no UI controls.

**Files analyzed**:
- `.council/web/pages/bizhawk.html.j2` (1041 lines) — automation tab: lines 305-504
- `.council/web/static/js/automation.js` (1573 lines) — full file
- `src/rom_lab/api/routes/automation/models.py` (278 lines)
- `src/rom_lab/api/routes/automation/routes.py` (144 lines)
- `src/rom_lab/api/routes/automation/constants.py` (281 lines)

**Confidence**: 0.99 (direct code inspection, no inference required)
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

### 1. UI Controls Inventory (Complete)

The automation panel is at HTML lines 305–504, inside `id="panel-automation"`. All controls are in `class="automation__grid"`.

**Section: Starter Reset (input grid)**

| Element ID | Label | Type | Options / Range |
|---|---|---|---|
| `automationSaveSlot` | Save Slot | `<select>` | Slots 0-9 (JS-populated as "Slot 1"–"Slot 10") |
| `automationShinyFilter` | Shiny | `<select>` | Any / Shiny Only / Not Shiny |
| `automationNatureFilter` | Nature | `<input type="text">` | Free-text, placeholder "Any" |
| `automationGenderFilter` | Gender | `<select>` | Any / Male / Female / Genderless |
| `automationRngMode` | RNG Mode | `<select>` | Deterministic / Unique Seed Wait |
| `automationExecutionProfile` | Execution Profile | `<select>` | Adaptive / Exact Lock / Fast Probe |
| `automationUniqueSeedWindow` | Unique Seed Window (frames) | `<input type="number">` | min=0, step=1, placeholder=180 |
| `automationExecutionMaxDelayFrames` | Execution Max Delay (frames) | `<input type="number">` | min=30, step=1, placeholder="Auto" |
| `automationSettleMinFrames` | Settle Min (frames) | `<input type="number">` | min=0, step=1, placeholder=0 |
| `automationSettleMaxFrames` | Settle Max (frames) | `<input type="number">` | min=0, step=1, placeholder=0 |
| `automationPreA4HoldFrames` | Pre-Final-A Hold (frames) | `<input type="number">` | min=0, step=1, placeholder=0 |
| `automationIvHpMin` | IV HP Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvAtkMin` | IV Atk Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvDefMin` | IV Def Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvSpaMin` | IV SpA Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvSpdMin` | IV SpD Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvSpeMin` | IV Spe Min | `<input type="number">` | min=0, max=31, placeholder="Any" |
| `automationIvTotalMin` | IV Total Min | `<input type="number">` | min=0, max=186, placeholder="Any" |

**Total UI controls in input grid: 18**

**Action buttons:**
- `automationStartBtn` — "Start" (primary)
- `automationStopBtn` — "Stop" (danger)
- `automationDefaultsBtn` — "Defaults"
- `automationStatusLine` — inline status text

---

### 2. API Fields in StarterResetStartRequest (Complete)

**Top-level fields (22 total):**

| Field | Type | Default | UI Control? |
|---|---|---|---|
| `mode` | Literal["starter_exact_v1"] | "starter_exact_v1" | No (hardcoded in payload) |
| `save_slot` | int [0-9] | 0 | Yes — `automationSaveSlot` |
| `filters` | StarterResetFilters | (nested) | Yes (10 filter fields) |
| `candidate_timeout_seconds` | float [0.25-20.0] | 6.0 | **No — not in UI or payload** |
| `rng_mode` | Literal["deterministic","unique_seed_wait"] | "deterministic" | Yes — `automationRngMode` |
| `rng_unique_seed_window` | int [0-7200] | 180 | Yes — `automationUniqueSeedWindow` |
| `rng_settle_frames_min` | int [0-240] | 0 | Yes — `automationSettleMinFrames` |
| `rng_settle_frames_max` | int [0-240] | 0 | Yes — `automationSettleMaxFrames` |
| `rng_pre_a1_spin_steps` | int [0-240] | 0 | **No — not in UI or payload** |
| `rng_pre_a4_hold_frames` | int [0-7200] | 0 | Yes — `automationPreA4HoldFrames` |
| `rng_use_seed_match` | bool | False | **No — ABSENT from UI and payload** |
| `rng_seed_wait_timeout_frames` | int [60-3600] | 600 | **No — ABSENT from UI and payload** |
| `execution_profile` | Literal["adaptive","exact_lock","fast_probe"] | "adaptive" | Yes — `automationExecutionProfile` |
| `execution_max_delay_frames` | int\|None [30-60000] | None | Yes — `automationExecutionMaxDelayFrames` |
| `target_mode` | Literal["hybrid_weighted","filter_first","pid_first"] | "hybrid_weighted" | **No — not in UI or payload** |
| `target_weights_filter` | float [0.0-1.0] | 0.7 | **No — not in UI or payload** |
| `target_weights_pid` | float [0.0-1.0] | 0.3 | **No — not in UI or payload** |
| `target_horizon_frames` | int [30-20000] | 1800 | **No — not in UI or payload** |
| `target_candidate_count` | int [1-256] | 64 | **No — not in UI or payload** |
| `calibration_policy` | Literal["per_run_quick","continuous_micro","none"] | "per_run_quick" | **No — not in UI or payload** |
| `calibration_probe_count` | int [1-20] | 3 | **No — not in UI or payload** |
| `calibration_recheck_every_attempts` | int [1-200] | 20 | **No — not in UI or payload** |
| `drift_threshold_frames` | int [0-120] | 10 | **No — not in UI or payload** |

**StarterResetFilters nested fields (10 total):**

| Field | Type | Default | UI Control? |
|---|---|---|---|
| `shiny` | bool\|None | None | Yes — `automationShinyFilter` |
| `nature` | str\|None | None | Yes — `automationNatureFilter` |
| `gender` | Literal\|None | None | Yes — `automationGenderFilter` |
| `iv_hp_min` | int\|None [0-31] | None | Yes — `automationIvHpMin` |
| `iv_attack_min` | int\|None [0-31] | None | Yes — `automationIvAtkMin` |
| `iv_defense_min` | int\|None [0-31] | None | Yes — `automationIvDefMin` |
| `iv_sp_attack_min` | int\|None [0-31] | None | Yes — `automationIvSpaMin` |
| `iv_sp_defense_min` | int\|None [0-31] | None | Yes — `automationIvSpdMin` |
| `iv_speed_min` | int\|None [0-31] | None | Yes — `automationIvSpeMin` |
| `iv_total_min` | int\|None [0-186] | None | Yes — `automationIvTotalMin` |

---

### 3. The Gap: Fields With No UI Control

**12 API fields are invisible to the user and silently defaulted:**

| Field | Default | Category | Notes |
|---|---|---|---|
| `candidate_timeout_seconds` | 6.0 | Session timing | Not in payload at all |
| `rng_pre_a1_spin_steps` | 0 | RNG timing | Not in payload at all |
| `rng_use_seed_match` | False | **Seed-match** | **Entire feature unreachable from UI** |
| `rng_seed_wait_timeout_frames` | 600 | **Seed-match** | **Entire feature unreachable from UI** |
| `target_mode` | "hybrid_weighted" | Target planning | Not in payload at all |
| `target_weights_filter` | 0.7 | Target planning | Not in payload at all |
| `target_weights_pid` | 0.3 | Target planning | Not in payload at all |
| `target_horizon_frames` | 1800 | Target planning | Not in payload at all |
| `target_candidate_count` | 64 | Target planning | Not in payload at all |
| `calibration_policy` | "per_run_quick" | Calibration | Not in payload at all |
| `calibration_probe_count` | 3 | Calibration | Not in payload at all |
| `calibration_recheck_every_attempts` | 20 | Calibration | Not in payload at all |
| `drift_threshold_frames` | 10 | Calibration | Not in payload at all |

**Note**: `mode` is hardcoded to "starter_exact_v1" in `_buildStartPayload()` without reading from any UI element (no UI control needed — it's the only mode).

---

### 4. _buildStartPayload() — Exact Payload Sent to POST /start

Fields actually sent (js/automation.js lines 341-363):

```javascript
{
  mode: 'starter_exact_v1',                  // hardcoded
  save_slot: Number(_saveSlot.value || 0),   // UI
  rng_mode: rngMode,                         // UI
  execution_profile: executionProfile,       // UI
  execution_max_delay_frames: executionMaxDelay,  // UI (optional int)
  rng_unique_seed_window: uniqueSeedWindow,  // UI
  rng_settle_frames_min: settleMin,          // UI
  rng_settle_frames_max: Math.max(settleMin, settleMax),  // UI (with auto-clamp)
  rng_pre_a4_hold_frames: preA4Hold,         // UI
  filters: {
    shiny: bool|null,                        // UI
    gender: str|null,                        // UI
    nature: str|null,                        // UI
    iv_hp_min: int|null,                     // UI
    iv_attack_min: int|null,                 // UI
    iv_defense_min: int|null,                // UI
    iv_sp_attack_min: int|null,              // UI
    iv_sp_defense_min: int|null,             // UI
    iv_speed_min: int|null,                  // UI
    iv_total_min: int|null,                  // UI
  }
}
```

**Total fields sent: 19 (9 top-level + 10 filter fields).**
No seed-match fields. No target planning fields. No calibration fields. No candidate_timeout_seconds.

---

### 5. /defaults Endpoint — What It Returns vs What JS Uses

**GET /api/automation/starter-reset/defaults** (routes.py lines 47-99)

Returns `defaults` object with 34 keys. JS `_loadDefaults()` reads only these:

| Default Key | JS Uses It? | Maps To Control |
|---|---|---|
| `save_slot` | Yes | `automationSaveSlot` |
| `filters.shiny` | Yes | `automationShinyFilter` |
| `filters.nature` | Yes | `automationNatureFilter` |
| `filters.gender` | Yes | `automationGenderFilter` |
| `rng_mode` | Yes | `automationRngMode` |
| `execution_profile` | Yes | `automationExecutionProfile` |
| `rng_unique_seed_window` | Yes | `automationUniqueSeedWindow` |
| `execution_max_delay_frames` | Yes | `automationExecutionMaxDelayFrames` |
| `rng_settle_frames_min` | Yes | `automationSettleMinFrames` |
| `rng_settle_frames_max` | Yes | `automationSettleMaxFrames` |
| `rng_pre_a4_hold_frames` | Yes | `automationPreA4HoldFrames` |
| `filters.iv_hp_min` | Yes | `automationIvHpMin` |
| `filters.iv_attack_min` | Yes | `automationIvAtkMin` |
| `filters.iv_defense_min` | Yes | `automationIvDefMin` |
| `filters.iv_sp_attack_min` | Yes | `automationIvSpaMin` |
| `filters.iv_sp_defense_min` | Yes | `automationIvSpdMin` |
| `filters.iv_speed_min` | Yes | `automationIvSpeMin` |
| `filters.iv_total_min` | Yes | `automationIvTotalMin` |
| `history_page_size` | Yes | `automationHistoryPageSize` |

**Defaults returned but NOT used by JS (no corresponding UI control):**

| Default Key | Value | Notes |
|---|---|---|
| `mode` | "starter_exact_v1" | Hardcoded in payload |
| `candidate_timeout_seconds` | 6.0 | No UI, not sent |
| `rng_pre_a1_spin_steps` | 0 | No UI, not sent |
| `target_mode` | "hybrid_weighted" | No UI, not sent |
| `target_weights_filter` | 0.7 | No UI, not sent |
| `target_weights_pid` | 0.3 | No UI, not sent |
| `target_horizon_frames` | 1800 | No UI, not sent |
| `target_candidate_count` | 64 | No UI, not sent |
| `calibration_policy` | "per_run_quick" | No UI, not sent |
| `calibration_probe_count` | 3 | No UI, not sent |
| `calibration_recheck_every_attempts` | 20 | No UI, not sent |
| `drift_threshold_frames` | 10 | No UI, not sent |

**MISSING from /defaults entirely (seed-match fields added in last wave):**

| Field | Value in model | Present in /defaults? |
|---|---|---|
| `rng_use_seed_match` | False | **NO — not returned by /defaults** |
| `rng_seed_wait_timeout_frames` | 600 | **NO — not returned by /defaults** |

The /defaults endpoint was not updated when seed-match fields were added to StarterResetStartRequest. Two-way gap: not in defaults response AND not in JS UI AND not in payload.

---

### 6. History Table — What's Shown vs What's Available

**History table columns (HTML lines 481-493):**
`#` | `Time` | `Species` | `Nature` | `Gender` | `Ability` | `Shiny` | `PID` | `Seed` | `Moves` | `Match`

**How columns are populated** (_renderHistory, JS lines 691-726):
- `#` → `A{attempt}` (attempt number)
- `Time` → formatted timestamp
- `Species` → display_name + species_id
- `Nature` → row.nature
- `Gender` → row.gender
- `Ability` → row.ability
- `Shiny` → Shiny/Normal pill
- `PID` → hex32(personality)
- `Seed` → `{rng_seed_start} → {rng_seed_candidate}` (both as hex32)
- `Moves` → comma-joined move names
- `Match` → Match/Miss pill

**Data stored in history records but NOT shown in table:**
- `ivs` — full IV object (HP/Atk/Def/SpA/SpD/Spe) — available in Copy Debug only
- `evs` — full EV object — available in Copy Debug only
- `stats` — computed stats — available in Copy Debug only
- `stage_durations` — per-stage timing breakdown — available in Copy Debug only
- `frame_at_a1_press`, `frame_at_a2_press`, `frame_at_a3_press`, `frame_at_a4_press` — available in Copy Debug only
- `is_shiny` (bool) vs `shiny_value` (int) — shiny_value not shown
- `filter_checks` — per-criterion match breakdown — available in Copy Debug only

**History table pagination controls:**
- `automationHistoryPageSize` — select: 10/20/50/100 (default 20 selected)
- `automationHistoryPrevBtn` / `automationHistoryNextBtn` — prev/next
- `automationHistoryMeta` — "Run {id} • Rows {total} • Page {n}/{total}"
- `automationCopyHistoryBtn` — copies TSV with all 11 columns

---

### 7. Status Display — What the User Sees During a Run

**Metrics bar (HTML lines 416-434):**
- `automationStateChip` — state text: IDLE/RUNNING/ERROR (with CSS class for color)
- `automationAttempts` — attempt count integer
- `automationMatches` — match count integer
- `automationElapsed` — M:SS format

**Meta line (`automationMeta`, JS lines 418-429):**
Dot-separated parts: `Run {run_id}` • `Stage: {current_stage}` • `StageReason: {stage_reason}` • `Reason: {stop_reason}` • `RNG: {config.rng_mode}` • `Adaptive: {active_rng_plan.strategy}` • `Started {timestamp}`

**Target board (`automationTargetBoard`):**
When a candidate is selected: 3-card layout:
1. Selected Target: Reason, Rank/Score/conf, Delay (selected/requested/effective), PID/nature/gender, Seeds (start/cand/obsCand)
2. Prediction Health: Hit rates (full/exec), Error (delayMAE/missStreak), Last delay (observed/err), Last checks (pid/nature/gender/full), Run (attempts/matches)
3. Top Exact Candidates table: Rank | Delay | Score | PID | Nature/Gender | SeedCand (top 6)

When no selected candidate but partial candidates exist: "No Exact Candidate Yet" card + Nearest Partial Diagnostics table.

**Observability block (`automationObservability`):**
Multi-line text (JS lines 1527-1541):
```
Candidates N • shiny N • not_shiny N
RngMode deterministic
Adaptive {strategy} • {dup_streak} dup streak • dom {ratio}
Spread seedStartDom {ratio} • seedDom {ratio} • pidUnique {ratio}
Target lvl {N} • last {score} • avg {avg}
Jump jumps N • last N
Plan {strategy} • {rng_mode} • profile {profile} • maxDelay {N} • win {N} • settle {min}..{max} • wait {N} • phase {N} • target {N} • jump yes/no@{interval}
Nature {top3}
Gender {top3}
Ability {top3}
Moves {top4}
Seed(cand) {top4}
Strategies {top3}
```

**Error display (`automationError`):** Shows `last_error` when non-empty.

**Debug events pre (`automationDebug`):** Last 8 debug events from `status.debug_events[]`. Format per event: `{time} {event_name} | {details...}` Each event can include: stage, reason, error, stop_reason, strategy, pressure, phase, target_level, target_avg, seed_ratio, pid_unique, post_input signals.

**Last Candidate section (`automationCandidate`):**
Card showing: display_name, species_id, slot, shiny chip, match chip, gender/nature/ability, moves list.

**Copy buttons:**
- `automationCopySnapshotBtn` — copies 7-section markdown snapshot (see §8)
- `automationCopyLearningBtn` — copies observability text content
- `automationCopyDebugBtn` — copies full debug report + learning summary

---

### 8. Copy Snapshot — 7-Section Markdown Report

`_buildSnapshotCopyText()` produces:

1. **Run Overview**: state, run_id, attempts/matches/elapsed, stage, stop_reason, last_error, filters, mode/slot, RNG mode/profile/uniqueWin/settle
2. **Prediction + Timing Health**: health label, prediction hit rates (full/exec), delay MAE/miss streak, spread ratios, pressure (strategy/ladder/jumps), calibration drift/recheck
3. **Active Plan**: strategy/phase/settle/wait, reason, jump config, execution profile/maxDelay, target model/weights, selected target (rank/delay/pid/seeds), execution plan (selected/requested/effective/holdA4/source), delay gap, planner stats (scan mode/horizon/candidates/elapsed/cache)
4. **Last Candidate**: name/species/level/nature/gender, PID/shiny/ability, seeds (start→candidate→current), frame timestamps (a1/a2/a3/a4/candidate/sinceStart), filter check summary
5. **Distribution**: total candidates, shiny counts, nature/gender/seed_start/seed_cand/strategy top entries
6. **Signal Event Digest**: last 12 signal events (candidate_*/adaptive_rng_plan/pid_learning_updated/target_plan_selected/attempt_error/run_finished), compact format
7. **History (Compact)**: TSV of last 12 history rows (#/Time/Nature/Gender/PID/Seed/Match)

---

### 9. Poll Behavior

- **Idle**: polls every 2000ms
- **Running**: polls every 800ms
- **Paused** (tab not visible): polling stopped, hint shows "Paused"
- **Offline**: hint shows "Offline"
- Each poll calls GET /status then GET /history

Poll hint element: `automationPollHint` in panel header.

---

### 10. API Routes Summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/automation/starter-reset/defaults` | UI defaults + options |
| GET | `/api/automation/starter-reset/status` | Current run state |
| GET | `/api/automation/starter-reset/history?page=N&page_size=N` | Paginated attempt history |
| POST | `/api/automation/starter-reset/target-plan/preview` | Preview target plan (not wired to UI button) |
| POST | `/api/automation/starter-reset/start` | Start automation |
| POST | `/api/automation/starter-reset/stop` | Stop automation |

**Note**: `POST /target-plan/preview` exists in routes.py but there is no "Preview" button in the UI. It accepts the full StarterResetStartRequest body.
<!-- ID: technical_analysis -->
## Technical Analysis

### Critical Gaps (Architect must address)

**GAP-1: Seed-match completely unreachable from UI.**
- `rng_use_seed_match` (bool, default False) and `rng_seed_wait_timeout_frames` (int, default 600) exist in the model and are wired in the controller, but there is no UI toggle and they are absent from `_buildStartPayload()`.
- The feature was implemented (Waves 1-3) but never connected to the panel.
- The `/defaults` endpoint was also not updated to return these fields.
- **Fix requires**: HTML toggle (checkbox or select), JS variable, `_loadDefaults` read, `_buildStartPayload` inclusion, `/defaults` return value addition.

**GAP-2: /defaults endpoint missing two fields.**
- `rng_use_seed_match` and `rng_seed_wait_timeout_frames` are not in the defaults dict returned by `GET /defaults`. Even if JS were updated, it would get `undefined` from the API.

**GAP-3: 10 API fields silently server-defaulted with no user visibility.**
- `candidate_timeout_seconds`, `rng_pre_a1_spin_steps`, `target_mode`, `target_weights_filter`, `target_weights_pid`, `target_horizon_frames`, `target_candidate_count`, `calibration_policy`, `calibration_probe_count`, `calibration_recheck_every_attempts`, `drift_threshold_frames`
- Decision for Architect: which should get UI controls, which stay intentionally hidden.

### Observability-Only Data (Available but Not Promoted)

- IVs, EVs, stats, and stage_durations are captured per-candidate in the history record and visible in Copy Debug, but do NOT appear in the history table. The UX deliberately hides them from the main view.

### Minor Inconsistencies

- `automationExecutionMaxDelayFrames` has `min=30` in HTML, `_parseOptionalInteger` uses min=30/max=60000. API uses `ge=30, le=TARGET_DEEP_SCAN_HORIZON_FRAMES` (60000). Consistent.
- `rng_pre_a1_spin_steps` is in the model and /defaults (would be 0) but absent from payload and has no UI control.

### Code Patterns Identified

- JS follows a clean DOM-ID pattern: all variables declared at module scope, resolved in `init()`, read in `_buildStartPayload()`.
- `/defaults` is called on load and on "Defaults" button click only — not on each start.
- Payload is fully constructed client-side from DOM state, not computed from defaults at send-time.
- History rendering uses `colspan="11"` on empty row — any new column addition requires updating this span value.

### Open Questions for Architect

1. Should seed-match toggle be a simple checkbox, or a more prominent mode-switch (e.g., replacing the "RNG Mode" select or adding a new select option)?
2. Should `rng_seed_wait_timeout_frames` be user-editable or remain a server constant?
3. Which of the 10 "expert" fields should be exposed (possibly in a collapsible "Advanced" section)?
4. Should the history table get an IV column, or is Copy Debug sufficient for IV data?
5. Should `POST /target-plan/preview` get a UI button?
<!-- ID: recommendations -->
## Recommendations for Architect

### Priority 1 — Critical Gap Closures

**REC-1: Add seed-match UI controls (GAP-1, GAP-2)**
The `rng_use_seed_match` and `rng_seed_wait_timeout_frames` fields have been implemented in the controller but are completely unreachable from the UI. The Architect must:
- Add a checkbox `automationRngUseSeedMatch` to the automation grid
- Add a number input `automationRngSeedWaitTimeout` (min=60, max=3600, placeholder="600") that activates only when seed-match is checked
- Update `_buildStartPayload()` to include both fields
- Update `GET /defaults` handler in routes.py to return both fields

**REC-2: Update /defaults endpoint (GAP-2)**
The `/defaults` route handler in `routes.py` lines 47-99 must be extended. Two constants exist (`DEFAULT_RNG_USE_SEED_MATCH = False`, `DEFAULT_RNG_SEED_WAIT_TIMEOUT_FRAMES = 600`) but are never included in the response dict. This is a one-line-per-field fix.

### Priority 2 — Evaluate for UI Exposure

**REC-3: Assess the 10 silently-defaulted fields (GAP-3)**
The following fields are always server-defaulted and never surfaced. The Architect should decide per-field whether to expose, document, or retain as server-internal:
- `candidate_timeout_seconds` — power user concern, probably worth exposing
- `rng_pre_a1_spin_steps` — advanced RNG tuning, may want to expose
- `target_mode`, `target_weights_filter`, `target_weights_pid` — only relevant for learner/adaptive mode; evaluate if adaptive execution profile needs sub-controls
- `target_horizon_frames`, `target_candidate_count` — RNG scan window controls; possibly expose for advanced users
- `calibration_policy`, `calibration_probe_count`, `calibration_recheck_every_attempts` — calibration management; possibly a separate "Advanced" section
- `drift_threshold_frames` — timing drift control; low priority for UI exposure

**REC-4: Consider /target-plan/preview UI button**
The endpoint `POST /target-plan/preview` is fully implemented but has no UI entry point. It accepts the same payload as `/start` and returns candidate preview data. A "Preview Targets" button would let users validate their filter configuration before committing to a full reset run.

### Priority 3 — History Table Enhancement

**REC-5: Expose per-candidate IV data in history table**
The history endpoint returns IV/stat data per candidate (visible in the `/candidates` debug log), but the 11-column history table does not render IVs. The Architect should consider:
- Adding an expandable row detail panel per history entry
- Or adding abbreviated IV columns (total only, or HP/Atk/Spe) to the table

### Implementation Notes for Architect

- All UI changes are additive — no existing controls need to be moved or removed
- The `_buildStartPayload()` function in `automation.js` lines 318-364 is the single canonical integration point for new fields
- The `_loadDefaults()` function in `automation.js` lines 152-213 must be updated for any new field pulled from `/defaults`
- Validation patterns exist in the JS for number inputs (parseFloat with fallback to null); follow the existing pattern
- The automation grid uses CSS `automation__grid` class with established layout; new controls can be appended without layout changes
- The status section already has `automationObservability` and `automationDebug` display surfaces that render server-provided text — seed-match status could be surfaced through `automationMeta` without new HTML elements
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---