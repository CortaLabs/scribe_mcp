---
id: rng_scan_pipeline-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 rng_scan_pipeline"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 04:09:26 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — rng_scan_pipeline
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 03:52:59 UTC

> Execution roadmap for rng_scan_pipeline.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview

| Phase | Name | Scope | Verification | Est. Effort |
|-------|------|-------|-------------|-------------|
| **1** | Foundation: Models + Hidden Power | Pydantic models, `compute_hidden_power()`, HP unit tests | `pytest tests/test_hidden_power.py` passes | 1-2 hours |
| **2** | Backend: Scan/Select/Execute API | Controller methods, route handlers, scan cache | `pytest tests/test_automation_routes.py` passes (new + existing) | 3-4 hours |
| **3** | Frontend: Scan Pipeline UI | HTML container, JS scan module, CSS styles, candidate table | Manual: scan button works, table renders, select + execute flow | 3-4 hours |
| **4** | Integration + Polish | End-to-end testing, edge cases, backward compat verification | Full pipeline test with BizHawk, existing `/start` still works | 1-2 hours |

**Total estimated effort: 8-12 hours (1-2 days, one person)**

**Dependency chain:** Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 (strictly sequential; each builds on the previous)
<!-- ID: phase_0 -->
## Phase 1 -- Foundation: Models + Hidden Power

**Objective:** Create all new Pydantic models and the hidden power computation utility. This phase has zero dependencies on controller changes and can be unit-tested in isolation.

---

### Task Package 1.1: Hidden Power Computation

**Scope:** Add `compute_hidden_power()` function to starter_target_planner.py
**Files to Modify:** `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py`
**Dependencies:** None (first task)

#### Specifications
1. Add `HP_TYPES` constant list (16 types in Gen 3 order: Fighting, Flying, Poison, Ground, Rock, Bug, Ghost, Steel, Fire, Water, Grass, Electric, Psychic, Ice, Dragon, Dark)
2. Add function `compute_hidden_power(ivs: dict[str, int]) -> tuple[str, int]` that:
   - Accepts dict with keys: "hp", "atk", "def", "spa", "spd", "spe" (all int 0-31)
   - Computes type using bit 0 of each IV: `type_val = (hp&1) | ((atk&1)<<1) | ((def&1)<<2) | ((spe&1)<<3) | ((spa&1)<<4) | ((spd&1)<<5)`, then `type_index = type_val * 15 // 63`
   - Computes power using bit 1 of each IV: `power_val = ((hp>>1)&1) | (((atk>>1)&1)<<1) | (((def>>1)&1)<<2) | (((spe>>1)&1)<<3) | (((spa>>1)&1)<<4) | (((spd>>1)&1)<<5)`, then `power = power_val * 40 // 63 + 30`
   - Returns `(type_name, power)`
3. Place the function AFTER `plan_starter_targets()` (after line 788)

#### Verification
- [ ] `compute_hidden_power({"hp":31,"atk":31,"def":31,"spa":31,"spd":31,"spe":31})` returns `("Dark", 70)`
- [ ] `compute_hidden_power({"hp":31,"atk":30,"def":30,"spa":31,"spd":31,"spe":31})` returns `("Ice", 70)`
- [ ] `compute_hidden_power({"hp":0,"atk":0,"def":0,"spa":0,"spd":0,"spe":0})` returns `("Fighting", 30)`
- [ ] Function is importable from `rom_lab.plugins.pokemon_fire_red.starter_target_planner`

#### Out of Scope
- Do NOT modify any existing functions in starter_target_planner.py
- Do NOT add imports (only uses built-in int operations)

---

### Task Package 1.2: New Pydantic Models

**Scope:** Add pipeline response models to models.py
**Files to Modify:** `src/rom_lab/api/routes/automation/models.py`
**Dependencies:** None (can run in parallel with 1.1)

#### Specifications
1. Add `CandidateDetail(BaseModel)` with fields:
   - `plan_id: str`, `rank: int`, `delay_frames: int`
   - `species_id: int`, `species_name: str`
   - `nature: str`, `gender: str`, `is_shiny: bool`
   - `pid: str` (hex string)
   - `ability: str`
   - `ivs: dict[str, int]` (keys: hp, atk, def, spa, spd, spe)
   - `iv_total: int`
   - `hidden_power_type: str`, `hidden_power_power: int`
   - `stats_at_level_5: dict[str, int] | None = None`
   - `filter_score: float`, `trajectory_score: float`, `total_score: float`
   - `filter_checks: list[dict[str, Any]]`
   - `predicted_seed_start: str`, `predicted_seed_candidate: str`

2. Add `ScanMeta(BaseModel)` with fields:
   - `seed_at_scan: str`, `tid: int`, `sid: int`, `species_id: int`
   - `scan_elapsed_ms: int`, `scan_mode: str`
   - `base_scan_elapsed_ms: int`
   - `deep_scan_used: bool`, `deep_scan_elapsed_ms: int`
   - `relaxed_scan_used: bool`, `relaxed_scan_elapsed_ms: int`
   - `horizon_frames: int`, `total_candidates_generated: int`, `filters_active: bool`

3. Add `ScanResponse(BaseModel)` with fields:
   - `scan_id: str`, `created_at: str`, `expires_at: str`
   - `candidates: list[CandidateDetail]`, `candidate_count: int`
   - `scan_meta: ScanMeta`

4. Add `SelectRequest(BaseModel)` with fields: `scan_id: str`, `plan_id: str`

5. Add `SelectResponse(BaseModel)` with fields: `scan_id: str`, `plan_id: str`, `locked: bool`, `candidate: CandidateDetail`, `message: str`

6. Add `ExecuteRequest(BaseModel)` with fields: `scan_id: str`

7. Add `ExecuteResponse(BaseModel)` with fields: `status: str`, `scan_id: str`, `plan_id: str`, `run_id: str | None`, `message: str`

8. Place all new models AFTER the existing `StarterResetStartRequest` class (after line 280)

#### Verification
- [ ] All 7 new model classes importable from `rom_lab.api.routes.automation.models`
- [ ] `CandidateDetail` can be instantiated with all required fields
- [ ] `ScanResponse` validates correctly with nested `CandidateDetail` list
- [ ] No import errors when loading the module

#### Out of Scope
- Do NOT modify `StarterResetStartRequest` or `StarterResetFilters`
- Do NOT add validators yet (keep models simple)

---

### Task Package 1.3: Hidden Power Unit Tests

**Scope:** Create comprehensive test file for compute_hidden_power
**Files to Modify:** `tests/test_hidden_power.py` (NEW file)
**Dependencies:** Task 1.1 (compute_hidden_power must exist)

#### Specifications
1. Create `tests/test_hidden_power.py` with the following tests:
   - `test_all_max_ivs`: IVs all 31 -> Dark, 70
   - `test_all_zero_ivs`: IVs all 0 -> Fighting, 30
   - `test_ice_70`: {hp:31, atk:30, def:30, spa:31, spd:31, spe:31} -> Ice, 70
   - `test_fire_70`: {hp:31, atk:30, def:31, spa:30, spd:31, spe:30} -> Fire, 70
   - `test_grass_70`: {hp:31, atk:30, def:31, spa:30, spd:31, spe:31} -> Grass, 70
   - `test_all_types_reachable`: Verify all 16 HP types can be produced by at least one IV spread
   - `test_power_range`: Verify power is always in [30, 70]
2. Import from `rom_lab.plugins.pokemon_fire_red.starter_target_planner import compute_hidden_power`

#### Verification
- [ ] `pytest tests/test_hidden_power.py -v` passes all tests
- [ ] All 16 HP types verified reachable

#### Out of Scope
- Do NOT test scan or controller logic (Phase 2)
- Do NOT add conftest fixtures (pure math tests need none)

---

### Task Package 1.4: Scan Cache Constants

**Scope:** Add new constants for scan cache configuration
**Files to Modify:** `src/rom_lab/api/routes/automation/constants.py`
**Dependencies:** None

#### Specifications
1. Add after existing constants (after last line):
   ```python
   # --- Scan Pipeline Cache ---
   SCAN_CACHE_MAX_RESULTS = 5
   SCAN_CACHE_TTL_SECONDS = 600  # 10 minutes
   SCAN_PIPELINE_DEFAULT_CANDIDATE_COUNT = 128
   ```

#### Verification
- [ ] Constants importable from `rom_lab.api.routes.automation.constants`
- [ ] No import errors

#### Out of Scope
- Do NOT modify existing constants

---

## Phase 2 -- Backend: Scan/Select/Execute API

**Objective:** Implement the 3 new controller methods and route handlers. This is the core backend work.

---

### Task Package 2.1: Controller scan() Method

**Scope:** Add `scan()`, `_enrich_candidates()`, and `_evict_expired_scans()` to StarterResetController
**Files to Modify:** `src/rom_lab/api/routes/automation/controller.py`
**Dependencies:** Phase 1 complete (models + compute_hidden_power + constants)

#### Specifications
1. Add to `__init__` (around line 250):
   ```python
   self._scan_results: dict[str, dict[str, Any]] = {}
   self._locked_target: dict[str, Any] | None = None
   ```

2. Add method `_evict_expired_scans(self) -> None`:
   - Iterate `_scan_results`, delete entries where `expires_at < datetime.utcnow().isoformat()`
   - Call under `self._lock`

3. Add method `_enrich_candidates(self, candidates: list[dict], species_id: int) -> list[dict]`:
   - For each candidate:
     - Call `compute_hidden_power()` on candidate's IVs
     - Add `hidden_power_type`, `hidden_power_power`
     - Add `iv_total` = sum of all IVs
     - Format `pid` as hex string `f"0x{pid:08X}"`
     - Format seed values as hex strings
     - Add `species_name` (resolve from species_id using existing lookup)
     - Add `ability` (resolve from PID bit 0 + species data)
   - Return enriched list

4. Add method `async def scan(self, request: StarterResetStartRequest) -> dict`:
   - Call `_ensure_socket_connected()` + `_read_enriched_state()`
   - Run precheck: `_validate_exact_precheck(state)`
   - Build learning/calibration state (same pattern as `preview_target_plan`)
   - Override `request.target_candidate_count` to `max(request.target_candidate_count, SCAN_PIPELINE_DEFAULT_CANDIDATE_COUNT)`
   - Call `_apply_target_overlay_to_plan_async()` to get candidates
   - Extract candidate list from `target_preview`
   - Call `_enrich_candidates()` on result
   - Generate `scan_id = str(uuid.uuid4())`
   - Under `self._lock`: evict expired, evict oldest if at max, store in `_scan_results`
   - Return dict matching `ScanResponse` shape

#### Verification
- [ ] `scan()` returns dict with `scan_id`, `candidates`, `scan_meta` keys
- [ ] Candidates have `hidden_power_type` and `hidden_power_power` fields
- [ ] Cache stores result under scan_id
- [ ] Oldest eviction works when cache is full

#### Out of Scope
- Do NOT modify `_apply_target_overlay_to_plan` internals
- Do NOT modify `preview_target_plan` method
- Do NOT touch execution logic

---

### Task Package 2.2: Controller select() and execute() Methods

**Scope:** Add `select()` and `execute()` methods to StarterResetController
**Files to Modify:** `src/rom_lab/api/routes/automation/controller.py`
**Dependencies:** Task 2.1 (scan cache must exist)

#### Specifications
1. Add method `async def select(self, scan_id: str, plan_id: str) -> dict`:
   - Under `self._lock`: call `_evict_expired_scans()`
   - Validate `scan_id` exists in `_scan_results`, raise RuntimeError if not found or expired
   - Find candidate with matching `plan_id` in cached candidates list
   - Raise RuntimeError if plan_id not found
   - Set `_scan_results[scan_id]["locked_plan_id"] = plan_id`
   - Set `self._locked_target = {"scan_id": scan_id, "plan_id": plan_id, "candidate": candidate}`
   - Return dict matching `SelectResponse` shape

2. Add method `async def execute(self, scan_id: str) -> dict`:
   - Under `self._lock`: validate `_locked_target` is not None and matches `scan_id`
   - Raise RuntimeError if no locked target or scan_id mismatch
   - Raise RuntimeError if automation already running (`self._state.get("active")`)
   - Extract the locked candidate
   - Build a `merged_plan` dict from the candidate that `_run_loop` expects:
     - Copy relevant fields: `target_plan_id`, `target_plan_score`, `target_selected_delay`, prediction seeds, etc.
   - Set `self._state["pipeline_locked_target"] = deepcopy(self._locked_target)`
   - Retrieve the original `request` from `_scan_results[scan_id]["request_snapshot"]`
   - Start `_run_loop` as background task (same pattern as `start()` method)
   - Return dict matching `ExecuteResponse` shape

#### Verification
- [ ] `select()` returns locked candidate details
- [ ] `select()` rejects invalid scan_id with RuntimeError
- [ ] `select()` rejects invalid plan_id with RuntimeError
- [ ] `execute()` starts the run loop
- [ ] `execute()` rejects if no target locked
- [ ] `execute()` rejects if automation already running

#### Out of Scope
- Do NOT modify `_run_exact_attempt` or `_run_loop` internals
- Do NOT modify the `start()` method (backward compat preserved)

---

### Task Package 2.3: Route Handlers

**Scope:** Add 3 new FastAPI route handlers
**Files to Modify:** `src/rom_lab/api/routes/automation/routes.py`
**Dependencies:** Tasks 2.1, 2.2 (controller methods must exist)

#### Specifications
1. Add `@router.post("/scan")` handler:
   ```python
   @router.post("/scan")
   async def starter_reset_scan(body: StarterResetStartRequest) -> dict[str, Any]:
       try:
           return await _controller.scan(body)
       except RuntimeError as exc:
           detail = str(exc)
           status_code = 503
           if "precheck" in detail.lower():
               status_code = 409
           raise HTTPException(status_code=status_code, detail=detail) from exc
   ```

2. Add `@router.post("/select")` handler:
   ```python
   @router.post("/select")
   async def starter_reset_select(body: SelectRequest) -> dict[str, Any]:
       try:
           return await _controller.select(body.scan_id, body.plan_id)
       except RuntimeError as exc:
           raise HTTPException(status_code=404, detail=str(exc)) from exc
   ```

3. Add `@router.post("/execute")` handler:
   ```python
   @router.post("/execute")
   async def starter_reset_execute(body: ExecuteRequest) -> dict[str, Any]:
       try:
           return await _controller.execute(body.scan_id)
       except RuntimeError as exc:
           detail = str(exc)
           status_code = 409 if "already running" in detail.lower() else 400
           raise HTTPException(status_code=status_code, detail=detail) from exc
   ```

4. Add import for `SelectRequest`, `ExecuteRequest` from models

#### Verification
- [ ] `POST /scan` returns 200 with ScanResponse shape
- [ ] `POST /select` returns 200 with SelectResponse shape
- [ ] `POST /execute` returns 200 with ExecuteResponse shape
- [ ] Error cases return proper HTTP status codes (404, 409, 503)

#### Out of Scope
- Do NOT modify existing route handlers
- Do NOT change the router prefix

---

### Task Package 2.4: Backend Tests

**Scope:** Add scan/select/execute endpoint tests
**Files to Modify:** `tests/test_automation_routes.py`
**Dependencies:** Tasks 2.1-2.3 (all backend endpoints must exist)

#### Specifications
1. Add test class or section for scan pipeline tests, following existing test patterns in the file
2. Tests to add:
   - `test_scan_returns_candidates`: POST /scan with valid request, verify response has scan_id + candidates list
   - `test_scan_candidates_have_hidden_power`: Verify candidates include hidden_power_type and hidden_power_power
   - `test_select_valid_candidate`: POST /select with valid scan_id + plan_id, verify locked response
   - `test_select_invalid_scan_id`: POST /select with bad scan_id, verify 404
   - `test_select_invalid_plan_id`: POST /select with valid scan_id but bad plan_id, verify 404
   - `test_execute_without_selection`: POST /execute without prior select, verify 400
   - `test_execute_with_locked_target`: POST /execute after valid select, verify 200 + started
   - `test_scan_cache_eviction`: Run 6 scans, verify oldest is evicted (max 5)
3. Use same mocking patterns as existing tests (mock `_read_enriched_state`, `plan_starter_targets`)

#### Verification
- [ ] `pytest tests/test_automation_routes.py -v -k scan` passes
- [ ] `pytest tests/test_automation_routes.py -v -k select` passes
- [ ] `pytest tests/test_automation_routes.py -v -k execute` passes (new tests only)
- [ ] All existing tests still pass

#### Out of Scope
- Do NOT modify existing tests
- Do NOT test UI (Phase 3)

---

## Phase 3 -- Frontend: Scan Pipeline UI

**Objective:** Build the candidate browser UI on the BizHawk page.

---

### Task Package 3.1: HTML Structure

**Scope:** Add scan pipeline HTML container to bizhawk.html.j2
**Files to Modify:** `.council/web/pages/bizhawk.html.j2`
**Dependencies:** Phase 2 complete (endpoints exist to call)

#### Specifications
1. Add new section within the existing automation panel area:
   - Scan controls: "Deep Scan" button, scan status indicator, candidate count badge
   - Candidate table container: `<div id="scanCandidateTable">` with table headers
   - Locked target panel: `<div id="scanLockedTarget">` (hidden until selection)
   - Action buttons: "Execute", "Clear Selection", "Re-scan"
2. Table columns: Rank, Nature, IVs (HP/Atk/Def/SpA/SpD/Spe), IV Total, HP Type/Power, Score, Shiny, Select button
3. Use BEM class naming: `scan-pipeline__*`
4. Add `id` attributes for JS binding: `scanBtn`, `scanStatus`, `scanCandidateTable`, `scanLockedTarget`, `scanExecuteBtn`, `scanClearBtn`, `scanRescanBtn`

#### Verification
- [ ] HTML renders without errors on page load
- [ ] All `id` attributes present for JS binding
- [ ] Scan pipeline section visible within automation panel

#### Out of Scope
- Do NOT modify existing automation panel HTML
- Do NOT add JS behavior yet (Task 3.2)

---

### Task Package 3.2: JavaScript Scan Module

**Scope:** Add scan pipeline logic to automation.js
**Files to Modify:** `.council/web/static/js/automation.js`
**Dependencies:** Task 3.1 (HTML elements must exist)

#### Specifications
1. Add new section within the existing IIFE for scan pipeline:
   - `_scanState = { scanId: null, candidates: [], lockedPlanId: null, sortColumn: 'rank', sortAsc: true }`
   - `async function _onDeepScan()`: POST to /scan with current form params, store result, render table
   - `function _renderCandidateTable(candidates)`: Build table rows from candidate data, attach click handlers
   - `function _sortCandidates(column)`: Client-side sort, re-render
   - `function _onSelectCandidate(planId)`: POST to /select, update locked target panel
   - `async function _onExecuteTarget()`: POST to /execute, show status
   - `function _onClearSelection()`: Clear locked state, re-enable table selection
   - `function _onRescan()`: Re-run scan with current params
2. Nature color mapping: object mapping nature names to CSS classes (boosted/reduced stat indicators)
3. IV bar rendering: For each IV, render as colored bar (0-31 scale, cyan for 31, dim for 0)
4. Shiny indicator: star icon for shiny candidates
5. Pagination: Show first 50 candidates, "Load More" button adds next 50

#### Verification
- [ ] Deep Scan button triggers API call and table renders
- [ ] Table is sortable by clicking column headers
- [ ] Candidate selection highlights row and shows locked panel
- [ ] Execute button fires execution
- [ ] Clear button resets selection state

#### Out of Scope
- Do NOT modify existing automation JS functions
- Do NOT add WebSocket streaming (HTTP polling is sufficient)

---

### Task Package 3.3: CSS Styles

**Scope:** Add scan pipeline styles
**Files to Modify:** `.council/web/static/css/bizhawk.css`
**Dependencies:** Task 3.1 (HTML classes must exist)

#### Specifications
1. Add `.scan-pipeline` block styles following existing BizHawk page aesthetic:
   - Container: dark matte background (`var(--ac-bg-base)` or `#0d1117`)
   - Borders: `var(--ac-border)` or `#1e2a38`
   - Text: `var(--ac-text-primary)` or `#c8d6e5`
   - Accent: `var(--ac-cyan)` or `#00d4ff`
   - Font: SF Mono stack (matches existing)
2. Table styles:
   - `.scan-pipeline__table`: full width, compact row height
   - `.scan-pipeline__row`: hover highlight, pointer cursor
   - `.scan-pipeline__row--selected`: cyan left border, slight glow
   - `.scan-pipeline__row--shiny`: subtle gold accent
   - `.scan-pipeline__table-header`: sortable headers with arrow indicators
3. IV bar: `.scan-pipeline__stat-bar`: thin bar with fill proportional to IV/31
4. Locked target panel: `.scan-pipeline__locked`: bordered card with confirmed target details
5. Responsive: table scrolls horizontally on narrow screens

#### Verification
- [ ] Styles load without errors
- [ ] Table matches tactical HUD aesthetic (dark, cyan, matte)
- [ ] Selected row clearly distinguished
- [ ] Shiny rows have gold accent

#### Out of Scope
- Do NOT modify existing BizHawk CSS styles
- Do NOT use purple (zero purple rule from agent-chat system)

---

## Phase 4 -- Integration and Polish

**Objective:** End-to-end testing, edge cases, and final polish.

---

### Task Package 4.1: Integration Testing

**Scope:** Verify full pipeline works end-to-end
**Files to Modify:** None (testing only)
**Dependencies:** Phases 1-3 complete

#### Specifications
1. Boot BizHawk with Fire Red, navigate to starter selection screen
2. Open BizHawk web page, locate scan pipeline section
3. Test flow: Deep Scan -> inspect candidates -> select one -> execute -> verify result
4. Test edge cases:
   - Scan when not at starter selection screen (should return precheck error)
   - Select expired scan (should return 404)
   - Execute without selection (should return 400)
   - Run existing `/start` endpoint (backward compat - should still work)
5. Test UI:
   - Sort by each column
   - Pagination (load more)
   - Re-scan after execution
   - Clear selection

#### Verification
- [ ] Full scan -> select -> execute flow completes
- [ ] Existing `/start` auto-execute still works
- [ ] Error cases return appropriate messages
- [ ] `pytest tests/test_automation_routes.py tests/test_hidden_power.py -v` all pass

#### Out of Scope
- Do NOT add new features in this phase
- Bug fixes only
<!-- ID: phase_1 -->
<!-- Phase 1 template content removed - replaced by Phase 1-4 task packages above -->
<!-- ID: milestone_tracking -->
## Milestone Tracking

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 1: Models + HP function + tests | TBD | Coder | Pending | `pytest tests/test_hidden_power.py` |
| Phase 2: Backend API (scan/select/execute) | TBD | Coder | Pending | `pytest tests/test_automation_routes.py -k scan` |
| Phase 3: Frontend UI | TBD | Coder | Pending | Manual: scan pipeline visible on BizHawk page |
| Phase 4: Integration pass | TBD | Coder | Pending | Full E2E test with BizHawk |
<!-- ID: retro_notes -->
## Retro Notes and Adjustments

- Architecture designed 2026-02-22 by ArchitectAgent
- Research verified against 7 source files with HIGH confidence
- One gap found: hidden power computation not in existing planner (added as Task 1.1)
- Task packages scoped for Coder execution: 11 task packages across 4 phases
- Backward compatibility preserved: existing `/start` endpoint unchanged
