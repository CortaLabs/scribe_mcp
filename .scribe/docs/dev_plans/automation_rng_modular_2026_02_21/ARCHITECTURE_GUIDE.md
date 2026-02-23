---
id: automation_rng_modular_2026_02_21-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 automation_rng_modular_2026_02_21"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 08:23:27 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — automation_rng_modular_2026_02_21
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-21 05:10:19 UTC

> Architecture guide for automation_rng_modular_2026_02_21.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement

**Context:** `src/rom_lab/api/routes/automation.py` is a 6,857-line monolith containing the entire Fire Red starter reset automation subsystem: state machine, learning engine, calibration engine, target planner integration, filter evaluator, RNG math helpers, dialogue detection, and HTTP routes -- all in a single file. This makes the codebase hard to navigate, test in isolation, and extend with new automation strategies (wild encounter, breeding, etc.).

Additionally, the RNG engine (`rng_oracle.py`) is mathematically correct and achieves PokeFinder parity for Method 1 generation, but lacks a few convenience functions needed for full Searcher parity (initial seed from Timer1). The test infrastructure covers the monolith well but lacks dedicated LCRNG parity tests against PokeFinder reference data.

**Goals:**
- Split automation.py into a well-organized 12-file package with zero behavior changes
- Preserve backward compatibility via `__init__.py` re-exports (existing tests and imports unchanged)
- Enhance rng_oracle.py with initial_seed_from_timer1() for PokeFinder Searcher parity
- Create dedicated RNG engine parity test files using PokeFinder fixture data
- Lay groundwork for AutomationStrategy ABC (future multi-strategy support)

**Non-Goals:**
- No new automation strategies implemented in this project (wild encounter, breeding are future)
- No frontend changes (automation.js, bizhawk.html.j2 remain untouched)
- No Lua runtime changes (runtime.lua stays as-is)
- No generic dispatch router yet (Phase 4 design only, implementation deferred)

**Success Metrics:**
- All 3,756 lines of existing tests pass unchanged after modularization
- Each extracted module is independently importable and testable
- New PokeFinder parity tests pass with fixture data
- No circular dependencies in the new package DAG

**Research References:**
- RESEARCH_AUTOMATION_MODULARIZATION.md -- 10-module split analysis, dependency DAG, re-export strategy
- RESEARCH_POKEFINDER_RNG_ENGINE.md -- PokeFinder C++ parity verification, Method 1 confirmed correct
- RESEARCH_TESTING_INFRASTRUCTURE.md -- Two-layer test architecture, fixture strategy
- RESEARCH_DECOMP_RNG_TIMING.md -- Fire Red RNG chain, initial seed from Timer1, Method 1 = 4 calls
- RESEARCH_ARCHITECTURE_PATTERNS.md -- Synthesized 5-layer architecture, strategy pattern, phased plan
<!-- ID: requirements_constraints -->
## 2. Requirements and Constraints

**Functional Requirements:**
- Split automation.py into 12 files within `src/rom_lab/api/routes/automation/` package
- `__init__.py` must re-export all public names so existing imports continue working
- Preserve all module-level singletons (`_history_store`, `_controller`) initialization behavior
- Preserve lazy MCP import pattern (`rom_lab_mcp` only imported at runtime, never at module level)
- Add `initial_seed_from_timer1(timer1_value: int) -> int` to `rng_oracle.py`
- Create test fixtures from PokeFinder reference data (static3.json, lcrng.json)
- Create `test_rng_engine_lcrng.py` and `test_rng_engine_method1.py` test files

**Non-Functional Requirements:**
- Zero behavior changes -- pure structural refactor for Phase 1
- All existing 3,756 lines of test_automation_routes.py pass without modification
- No circular dependencies in the module DAG
- Each module independently importable (no import-time side effects except singletons in controller.py)
- Python typing standards: lowercase generics, `X | None`, `-> None`

**Assumptions:**
- automation.py is the ONLY file being split (rng_oracle.py and starter_target_planner.py remain untouched)
- The `init_automation(session_manager, frame_receiver)` entry point remains the app startup hook
- BizHawk socket reader is NOT required for any CI test (emulator tests skip-gated)

**Constraints:**
- Two module-level singletons (`_history_store` at line 556, `_controller` at line 4478) must maintain their initialization semantics
- `_detect_choice_prompt_via_mcp()` must keep its lazy import of `rom_lab_mcp.tools`
- `_mcp_runtime_handles()` must keep its lazy import pattern
- Tests reference `automation._controller`, `automation.StarterResetFilters`, etc. -- `__init__.py` must re-export these
- No two parallel agents may edit the same file (task package constraint for team execution)

**Risks and Mitigations:**
- **HIGH -- target_overlay extraction**: `_apply_target_overlay_to_plan` is 1,551 lines inside StarterResetController. Must verify zero `self.` references in the core logic. Mitigation: extract as pure function receiving all state as parameters; keep async wrapper in controller.py
- **MEDIUM -- lazy MCP imports**: If `dialogue_detection.py` imports `rom_lab_mcp` at module level, all tests fail. Mitigation: preserve exact lazy-import pattern from current code
- **MEDIUM -- test import paths**: Existing tests reference `automation.*` attributes. Mitigation: comprehensive `__init__.py` re-exports
- **LOW -- singleton init order**: `_history_store` needs `STARTER_HISTORY_DB_PATH` from constants. Mitigation: explicit import of constants in history_store.py
- **LOW -- spin_timing dependency**: calibration.py needs spin timing estimators. Mitigation: extract `spin_timing.py` as shared utility
<!-- ID: architecture_overview -->
## 3. Architecture Overview

**Solution Summary:** Transform the 6,857-line automation.py monolith into a 12-file Python package at `src/rom_lab/api/routes/automation/`, with a strict DAG dependency structure, `__init__.py` re-exports for backward compatibility, and enhanced RNG test coverage using PokeFinder reference data.

**System Architecture (5 Layers):**

```
Layer 5: API Routes
  routes.py ---- FastAPI router, 7 HTTP handlers, init_automation()
       |
Layer 4: Controller (State Machine)
  controller.py ---- StarterResetController, _controller singleton, run loop
       |         \
       |          \--- _history_store singleton (from history_store.py)
       |
Layer 3: Strategy Components (Pure Logic)
  target_overlay.py ---- _apply_target_overlay_to_plan() extracted as pure function
  learner.py ----------- _derive_adaptive_rng_plan(), _update_pid_learning_state()
  calibration.py ------- _update_calibration_state(), segment EMA tracking
  filter_engine.py ----- _evaluate_filter_checks(), _pokemon_matches_filters()
  dialogue_detection.py - _extract_context_signals(), _is_dialogue_engaged()
  spin_timing.py ------- _estimate_pre_a1_spin_timing_frames()
       |
Layer 2: Data Models and State
  models.py ----------- StarterResetFilters, StarterResetStartRequest (Pydantic)
  history_store.py ---- StarterHistoryStore (SQLite persistence)
  state_factories.py -- _empty_observability(), _empty_pid_learning_state(), _empty_calibration_state()
       |
Layer 1: Constants
  constants.py -------- ~170 module-level constants (all primitive values)
       |
External Dependencies (UNCHANGED):
  rng_oracle.py -------------- LCRNG engine, Method 1 generation (pure math)
  starter_target_planner.py -- Target book building, ranking (pure math)
```

**Dependency DAG (No Circular Dependencies):**

```
rng_oracle.py (external, pure)
starter_target_planner.py (external, imports rng_oracle)
  |
constants.py (no imports)
  |
state_factories.py (no imports)
models.py (imports: constants, pydantic)
history_store.py (imports: constants, sqlite3)
  |
filter_engine.py (imports: models)
spin_timing.py (imports: constants)
dialogue_detection.py (imports: constants; lazy: rom_lab_mcp.tools)
  |
learner.py (imports: constants, models)
calibration.py (imports: constants, spin_timing)
  |
target_overlay.py (imports: constants, models, rng_oracle, starter_target_planner, learner, calibration, spin_timing)
  |
controller.py (imports: ALL above + history_store + dialogue_detection + filter_engine + MCP lazy)
  |
routes.py (imports: controller, models, state_factories + MCP lazy)
```

**Data Flow (User Starts Automation):**

```
User clicks "Start" in BizHawk UI
  -> POST /api/automation/starter-reset/start (routes.py)
  -> StarterResetController.start(request) (controller.py)
  -> Creates asyncio task for _run_loop()
  -> _run_loop() iterates attempts:
      1. _wait_for_exact_precheck() -- verifies game state via MCP
      2. _apply_target_overlay_for_attempt() -- calls target_overlay.py
         -> plan_starter_targets() from starter_target_planner.py
         -> Uses rng_oracle.method1_generate() for seed prediction
         -> Applies calibration drift from calibration.py
         -> Applies learner strategy from learner.py
      3. _send_bot_control() -- sends IPC command to Lua bot
      4. _wait_for_lua_bot_candidate() -- polls for completion
      5. _record_candidate() -- evaluates filters via filter_engine.py
      6. _update_pid_learning() -- updates learner.py + calibration.py state
      7. _complete_attempt() -- stores in history_store.py
      8. Loop back or finish
  -> GET /api/automation/starter-reset/status polled every 800ms
```

**External Integrations (UNCHANGED):**
- `rng_oracle.py` at `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` (254 lines, pure math)
- `starter_target_planner.py` at `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` (754 lines, pure math)
- `rom_lab_mcp` tools (lazy-imported at runtime for emulator IPC)
- BizHawk Lua bot runtime (`lua/common/bot/runtime.lua`) for frame-tick state machine
<!-- ID: detailed_design -->
## 4. Module Specifications

### 4.1 constants.py (~215 lines)
**Purpose:** All module-level constants extracted from lines 1-212 of automation.py
**Public Interface:** ~170 named constants (all primitive values: int, float, str, tuple, dict)
**Key Constants Groups:**
- `DEFAULT_AUTOMATION_MODE`, `GBA_FRAME_RATE`, `STARTER_HISTORY_DB_PATH`
- `LEARNER_*` (22 thresholds), `TIMING_LOCK_*` (12 params), `TIMING_PROBE_*` (8 params)
- `CALIBRATION_*` (10 params), `TARGET_*` (12 params), `PREDICTION_*` (8 params)
- `SEGMENT_*` (3 jitter params), `SETTLE_PHASE_CYCLE`, `WAIT_PHASE_CYCLE` tuples
- `STARTER_BALL_SCRIPT_NAMES`, `FACING_DELTAS`, `NICKNAME_TEXT_HINTS`
- `DEFAULT_RNG_*` (8 RNG defaults)
**Dependencies:** None (all primitive values)
**File Path:** `src/rom_lab/api/routes/automation/constants.py`

### 4.2 models.py (~200 lines)
**Purpose:** Pydantic models for automation configuration and filters
**Public Interface:**
- `StarterResetFilters(BaseModel)` -- shiny/nature/gender/IV filters with validators
- `StarterResetStartRequest(BaseModel)` -- full automation start parameters (mode, save_slot, filters, rng_mode, timing, etc.)
**Dependencies:** `constants.py`, `pydantic`
**File Path:** `src/rom_lab/api/routes/automation/models.py`

### 4.3 history_store.py (~205 lines)
**Purpose:** SQLite-backed persistence for starter candidate history
**Public Interface:**
- `StarterHistoryStore` class: `__init__(db_path)`, `append_candidate(summary_dict)`, `list_candidates(page, page_size)`
- `_history_store` singleton (initialized at module import time)
**Dependencies:** `constants.py` (for `STARTER_HISTORY_DB_PATH`), `sqlite3`, `threading.Lock`
**File Path:** `src/rom_lab/api/routes/automation/history_store.py`

### 4.4 state_factories.py (~120 lines)
**Purpose:** Factory functions that create clean state dictionaries
**Public Interface:**
- `_empty_observability() -> dict[str, Any]` -- 20-key observability state
- `_empty_pid_learning_state() -> dict[str, Any]` -- 37-key learning state
- `_empty_calibration_state() -> dict[str, Any]` -- 30-key calibration state
**Dependencies:** None (pure dict factories)
**File Path:** `src/rom_lab/api/routes/automation/state_factories.py`

### 4.5 dialogue_detection.py (~180 lines)
**Purpose:** Context signal extraction and dialogue state helpers
**Public Interface:**
- `_extract_context_signals(context_dict) -> dict`
- `_is_dialogue_engaged(signals) -> bool`
- `_is_input_advance_ready(signals) -> bool`
- `_is_choice_open(signals) -> bool`, `_is_choice_closed(signals) -> bool`
- `_is_nickname_stage(state_dict, *, nickname_hints) -> bool`
- `_detect_choice_prompt_via_mcp(state_dict) -> bool` -- LAZY import of rom_lab_mcp.tools
- `_extract_post_input(state_dict) -> dict`
- `_post_input_has_choice(post_input) -> bool`
- `_post_input_signals(post_input) -> dict`
- `_validate_exact_precheck(state) -> dict` -- precheck validation helper
**Dependencies:** `constants.py`; LAZY: `rom_lab_mcp.tools` (runtime only)
**CRITICAL:** `_detect_choice_prompt_via_mcp` MUST preserve the late-import pattern:
```python
def _detect_choice_prompt_via_mcp(state_dict):
    from rom_lab_mcp.tools import detect_choice_prompt_from_state  # lazy!
    ...
```
**File Path:** `src/rom_lab/api/routes/automation/dialogue_detection.py`

### 4.6 filter_engine.py (~200 lines)
**Purpose:** Filter evaluation and IV normalization helpers
**Public Interface:**
- Constants: `_IV_STAT_KEYS`, `_IV_FILTER_SPEC`, `_IV_KEY_ALIASES`
- `_normalize_token(s) -> str | None`
- `_normalize_gender(s) -> str | None`
- `_normalize_ivs(raw) -> dict`
- `_evaluate_filter_checks(mon_dict, filters) -> list[dict]`
- `_filter_checks_passed(filter_checks) -> bool`
- `_candidate_filter_check_match(candidate, filter_checks) -> bool`
- `_pokemon_matches_filters(mon_dict, filters) -> bool`
- `_party_signature(party_list) -> str`
- `_find_new_party_candidate(party_list, old_sigs) -> dict | None`
- `_collect_party_signatures(party_list) -> set[str]`
**Dependencies:** `models.py` (for `StarterResetFilters` type hints)
**File Path:** `src/rom_lab/api/routes/automation/filter_engine.py`

### 4.7 spin_timing.py (~80 lines)
**Purpose:** Spin timing estimators shared by calibration and target_overlay
**Public Interface:**
- `_estimate_pre_a1_spin_timing_frames(spin_steps, ...) -> float`
- `_estimate_pre_a1_reface_frames(...) -> float`
- `_estimate_pre_a1_spin_total_timing_frames(...) -> float`
- `_max_spin_steps_for_budget_frames(...) -> int`
**Dependencies:** `constants.py`
**File Path:** `src/rom_lab/api/routes/automation/spin_timing.py`

### 4.8 learner.py (~430 lines)
**Purpose:** PID learning state management and adaptive RNG plan derivation
**Public Interface:**
- `_base_rng_plan(request) -> dict` -- builds baseline plan from request
- `_increment_bounded_hist(hist_dict, key, max_keys) -> None`
- `_top_seed_hist_keys(hist_dict, min_count) -> list[int]`
- `_cycle_pick(cycle_tuple, attempt_index, minimum) -> int`
- `_recent_top_frequency(recent_list, window) -> tuple[Any, float]`
- `_derive_adaptive_rng_plan(request, learning, attempt_index) -> dict` (~500 lines) -- full strategy selection state machine
- `_update_pid_learning_state(learning, *, summary, filter_checks, matched) -> None` (~320 lines)
**Dependencies:** `constants.py`, `models.py`
**File Path:** `src/rom_lab/api/routes/automation/learner.py`

### 4.9 calibration.py (~215 lines)
**Purpose:** Timing calibration, drift estimation, and EMA segment tracking
**Public Interface:**
- `_segment_delta(start, end) -> float | None`
- `_update_segment_ema(calibration, *, segment_key, observed) -> tuple[float, float]`
- `_update_calibration_segments(calibration, *, summary) -> None`
- `_update_calibration_state(calibration, *, summary, rng_plan) -> None` (~140 lines)
**Dependencies:** `constants.py`, `spin_timing.py`
**File Path:** `src/rom_lab/api/routes/automation/calibration.py`

### 4.10 target_overlay.py (~1,560 lines)
**Purpose:** Extracted `_apply_target_overlay_to_plan()` as a standalone pure function
**Public Interface:**
- `_apply_target_overlay_to_plan(request, *, learning, calibration, rng_plan, ...) -> dict`
- Helper functions: `_infer_delta()`, `_build_prediction_metrics()`, `_find_rng_delay()`, `_seed_candidate_observed_from_pre_generation()`, `_bounded_seed_step_delta()`
- `_is_shiny()`, `_build_candidate_summary()`
- Observability: `_update_observability()`, `_normalize_observability_key()`, `_increment_hist()`
- Type helpers: `_as_int_bool()`, `_to_int()`, `_frames_to_seconds()`
**Dependencies:** `constants.py`, `models.py`, `rng_oracle`, `starter_target_planner`, `learner`, `calibration`, `spin_timing`
**Extraction Note:** Currently a 1,551-line method inside StarterResetController. Must be extracted as a pure function that receives all state as parameters. The controller keeps only the async wrapper (`_apply_target_overlay_for_attempt`) that snapshots state under lock, calls `run_in_threadpool()`, and writes back results.
**File Path:** `src/rom_lab/api/routes/automation/target_overlay.py`

### 4.11 controller.py (~900 lines)
**Purpose:** `StarterResetController` class (state machine lifecycle) and module singletons
**Public Interface:**
- `StarterResetController` class: `__init__`, `configure()`, `start()`, `stop()`, `status()`, `history()`, `preview_target_plan()`, `_run_loop()`, `_run_single_attempt()`, `_run_exact_attempt()`, etc.
- `_controller` singleton (initialized at module level)
- MCP runtime handle helpers (lazy imports)
**Dependencies:** ALL other modules + `history_store.py` + `dialogue_detection.py` + `filter_engine.py` + `rom_lab_mcp` (lazy)
**File Path:** `src/rom_lab/api/routes/automation/controller.py`

### 4.12 routes.py (~110 lines)
**Purpose:** FastAPI route handlers and app startup hook
**Public Interface:**
- `router = APIRouter(prefix="/api/automation")`
- `init_automation(session_manager, frame_receiver)` -- app startup hook
- 7 HTTP route handlers (defaults, status, history, preview, start, stop, etc.)
**Dependencies:** `controller.py`, `models.py`, `state_factories.py`
**File Path:** `src/rom_lab/api/routes/automation/routes.py`

### 4.13 __init__.py (Re-export Hub)
**Purpose:** Backward compatibility -- re-exports all public names so `from rom_lab.api.routes.automation import X` continues working
**Critical Re-exports:**
```python
from .routes import router, init_automation
from .controller import _controller, StarterResetController
from .models import StarterResetFilters, StarterResetStartRequest
from .state_factories import _empty_pid_learning_state, _empty_calibration_state, _empty_observability
from .filter_engine import _evaluate_filter_checks, _filter_checks_passed, _pokemon_matches_filters
from .filter_engine import _party_signature, _find_new_party_candidate, _collect_party_signatures
from .learner import _derive_adaptive_rng_plan, _update_pid_learning_state
from .dialogue_detection import _validate_exact_precheck
from .calibration import _update_calibration_state
from .history_store import _history_store
```

### 4.14 RNG Engine Enhancement (rng_oracle.py -- extend in place)
**Purpose:** Add `initial_seed_from_timer1()` for PokeFinder Searcher parity
**New Function:**
```python
def initial_seed_from_timer1(timer1_value: int) -> int:
    """Compute initial gRngValue from Timer1 counter (REG_TM1CNT_L).
    
    FRLG: SeedRng(REG_TM1CNT_L) stores the 16-bit Timer1 value
    directly as gRngValue (zero-extended to 32 bits).
    Per decomp: decomps/pokefirered/src/main.c:SeedRngAndSetTrainerId()
    """
    return timer1_value & 0xFFFF
```
**File Path:** `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` (EDIT, not replace)
<!-- ID: directory_structure -->
## 5. Directory Structure

```
src/rom_lab/api/routes/automation/    # NEW PACKAGE (replaces automation.py single file)
    __init__.py            # Re-exports for backward compatibility
    constants.py           # ~215 lines -- all module-level constants
    models.py              # ~200 lines -- StarterResetFilters, StarterResetStartRequest
    history_store.py       # ~205 lines -- StarterHistoryStore + _history_store singleton
    state_factories.py     # ~120 lines -- _empty_observability/learning/calibration
    dialogue_detection.py  # ~180 lines -- context signals, dialogue helpers, precheck
    filter_engine.py       # ~200 lines -- filter evaluation, IV normalization
    spin_timing.py         # ~80 lines  -- spin timing estimators (shared)
    learner.py             # ~430 lines -- adaptive RNG plan, PID learning state
    calibration.py         # ~215 lines -- timing calibration, EMA tracking
    target_overlay.py      # ~1,560 lines -- extracted target overlay pure function
    controller.py          # ~900 lines -- StarterResetController + _controller singleton
    routes.py              # ~110 lines -- FastAPI handlers + init_automation

src/rom_lab/plugins/pokemon_fire_red/
    rng_oracle.py          # 254 lines -- ENHANCED with initial_seed_from_timer1()
    starter_target_planner.py  # 754 lines -- UNCHANGED

tests/
    test_automation_routes.py              # 3,756 lines -- UNCHANGED (backward compat)
    test_fire_red_rng_oracle.py            # existing -- UNCHANGED
    test_rng_oracle_pokefinder_parity.py   # existing -- UNCHANGED
    test_rng_engine_lcrng.py               # NEW -- LCRNG parity vs PokeFinder
    test_rng_engine_method1.py             # NEW -- Method 1 multi-seed parity
    test_rng_emulator_integration.py       # NEW -- savestate-based integration (skip-gated)
    test_starter_target_planner.py         # existing -- UNCHANGED
    fixtures/rng/
        pokefinder_method1/
            firered_lugia_method1_seed_AAAAAAAA.json  # existing
            emerald_totodile_method1_seed_55555555.json  # NEW
        pokefinder_lcrng/                  # NEW
            advance_vectors.json
            next_vectors.json

scripts/
    generate_rng_fixtures.py              # NEW -- fixture generation from PokeFinder data
```
<!-- ID: data_storage -->
## 6. Data and Storage

**StarterHistoryStore (SQLite):**
- Database path: configured via `STARTER_HISTORY_DB_PATH` constant (default: `~/.romlab/starter_history.db`)
- Table: `starter_history` with columns for candidate summaries, timestamps, filter results
- Thread-safe: `threading.Lock` for all SQLite operations
- No schema changes in this project -- purely structural extraction

**RNG State (In-Memory):**
- `_state["learning"]` -- 37-key dict managed by `learner.py`, tracks PID frequency, seed history, prediction accuracy
- `_state["calibration"]` -- 30-key dict managed by `calibration.py`, tracks timing drift, EMA segments
- `_state["observability"]` -- 20-key dict managed by `target_overlay.py`, tracks histogram and event counts
- All state dicts are initialized by `state_factories.py` factory functions
- State is ephemeral (lost on controller restart) -- only candidate history persists to SQLite

**Test Fixtures (JSON):**
- Located at `tests/fixtures/rng/` -- checked into git
- Generated from PokeFinder reference data via `scripts/generate_rng_fixtures.py`
- Source data at `.local_refs/rng_sources/admiral_fish_pokefinder/Test/` (gitignored)
<!-- ID: testing_strategy -->
## 7. Testing and Validation Strategy

**Layer 1 -- Pure Math Tests (CI, always run):**
- `test_fire_red_rng_oracle.py` -- existing LCRNG unit tests (unchanged)
- `test_rng_oracle_pokefinder_parity.py` -- existing Method 1 parity (unchanged)
- `test_rng_engine_lcrng.py` -- NEW: LCRNG advance/reverse parity vs PokeFinder lcrng.json
- `test_rng_engine_method1.py` -- NEW: Method 1 multi-seed coverage from static3.json (FireRed Lugia + Emerald Totodile)
- `test_starter_target_planner.py` -- existing planner tests (unchanged)

**Layer 2 -- Controller and Route Tests (CI, always run, monkeypatched):**
- `test_automation_routes.py` -- existing 3,756-line test suite (MUST pass unchanged after modularization)
- Uses `FastAPI TestClient` + `monkeypatch` for controller mocking
- No emulator required

**Layer 3 -- Emulator Integration Tests (skip-gated, manual):**
- `test_rng_emulator_integration.py` -- NEW: savestate-based deterministic replay tests
- Gate: `_BIZHAWK_RUNNING = _check_bizhawk_socket()` at module load time
- Uses `@pytest.mark.skipif(not _BIZHAWK_RUNNING, reason="requires live BizHawk")`
- Workflow: load savestate -> read RNG seed -> predict PID/IVs -> verify against RAM
- Reserved savestate slots: 8-9 (for integration tests only)

**Fixture Strategy:**
- JSON fixtures in `tests/fixtures/rng/` generated from PokeFinder Test/ data
- `scripts/generate_rng_fixtures.py` automates extraction and formatting
- Fixture format: `{source, dataset, seed, lcrng_constants, rows: [{delay, pid, nature_id, ivs}]}`

**Validation Commands:**
```bash
# CI (all pure math + controller tests)
pytest tests/ -q

# After modularization (verify backward compat)
pytest tests/test_automation_routes.py -v

# RNG parity only
pytest tests/test_rng_engine_lcrng.py tests/test_rng_engine_method1.py -v

# Emulator integration (requires BizHawk)
pytest tests/test_rng_emulator_integration.py -v
```
<!-- ID: deployment_operations -->
## 8. Deployment and Operations

**No deployment changes required.** This is a pure structural refactor:
- The FastAPI router import path (`from rom_lab.api.routes.automation import router, init_automation`) remains unchanged via `__init__.py` re-exports
- The app startup hook (`init_automation()`) remains at the same import path
- SQLite database path for history is unchanged
- No new environment variables, config keys, or runtime dependencies

**Migration Path (for the monolith split):**
1. Create `src/rom_lab/api/routes/automation/` directory
2. Move automation.py content into 12 module files
3. Delete the original `src/rom_lab/api/routes/automation.py` file (it becomes the `__init__.py` of the package)
4. Verify: `pytest tests/test_automation_routes.py -v` passes with zero changes
5. The old import path `from rom_lab.api.routes import automation` now resolves to the package `__init__.py`

**IMPORTANT:** Python treats `automation.py` (file) and `automation/` (package) as the same module path. When converting from file to package, the file MUST be deleted -- Python cannot have both a file and a directory with the same name. The `__init__.py` inside the package takes over the role of the former file.
<!-- ID: open_questions -->
## Open Questions (Phases 1-5)

_(Phases 1-5 open questions resolved during implementation. See PROGRESS_LOG for resolution details.)_

---

# UX Overhaul Architecture (Phases 6-9)
<!-- ID: ux_overhaul_architecture -->

**Date**: 2026-02-21
**Author**: ArchitectAgent
**Research Inputs**: RESEARCH_UI_SURFACE_20260221_0809.md, RESEARCH_BROKEN_CODE_AUDIT.md, RESEARCH_SEED_MATCH_UX.md
**Status**: Approved for implementation

---

## UX Overhaul -- Executive Summary

The starter reset automation panel requires a comprehensive UX overhaul to align the user interface with the seed-match execution model that replaced the delay-based timing system. The current panel exposes 18 controls, of which 7 target dead code paths, while the seed-match feature (the only working execution method) has zero UI presence. Additionally, approximately 830 lines of dead backend code, 50+ dead constants, 8 dead model fields, and 30+ dead tests must be deleted.

**User constraints driving this architecture** (non-negotiable):
1. Surface every setting with sensible defaults (nothing hidden behind code defaults)
2. Clean main view + collapsed Advanced section (not "remove everything" but organized hierarchy)
3. DELETE broken code (not deprecate, not keep)
4. Setting profiles (save/load configurations as presets)
5. Learning data displayed as proper UI components (not codeblocks)
6. Pokemon detail card with IV stat bars, nature effects, ability, moves, species art
7. History table with IVs and seed-match result columns
8. Enhanced copy snapshot (richer clipboard export)
9. Premium feel (professional UI polish)
10. Frontend-design skill on Opus for implementation agents

---

## UX Overhaul -- System Architecture

### Frontend Component Hierarchy

```
automation-panel (id="panel-automation")
+-- automation__grid (MAIN CONTROLS)
|   +-- Save Slot select
|   +-- Shiny filter select
|   +-- Nature filter text input
|   +-- Gender filter select
|   +-- IV filters (HP/Atk/Def/SpA/SpD/Spe/Total) number inputs
|   +-- Advanced toggle (collapsed by default)
|       +-- Seed Wait Timeout number input
|       +-- RNG Mode select (deterministic / unique_seed_wait)
|       +-- Unique Seed Window number input (shown when RNG Mode = unique_seed_wait)
|       +-- Candidate Timeout number input
|       +-- Pre-A1 Spin Steps number input
|       +-- Target Horizon number input
|       +-- Target Candidate Count number input
|   +-- Profile controls (Save / Load / Delete)
|   +-- Start / Stop / Defaults buttons
|
+-- automation__status (STATUS SECTION)
|   +-- State chip + Attempts + Matches + Elapsed (metrics bar)
|   +-- Seed-Match Diagnostics block (NEW)
|   |   +-- Target seed hex, Matched seed hex, Wait frames, Result pill, Offset
|   +-- Meta line (run_id, stage, reason)
|   +-- Target Board (selected target + top candidates)
|   +-- Learning Data display (NEW -- tables/metrics, not codeblock)
|   +-- Observability summary
|   +-- Debug events
|
+-- automation__candidate (LAST CANDIDATE)
|   +-- Pokemon Detail Card (NEW -- redesigned)
|       +-- Species art/sprite, Name, Level
|       +-- IV stat bars (radar or bar chart) with nature effects (+/-)
|       +-- Nature, Gender, Ability, Shiny status
|       +-- Moves list
|       +-- PID hex, Seeds hex
|
+-- automation__history (HISTORY TABLE)
|   +-- Updated columns: #, Time, Species, Nature, Gender, Shiny, IVs, PID, Seed, Result, Moves, Match
|   +-- Pagination controls
|   +-- Copy History button (updated for new columns)
|
+-- automation__actions (COPY BUTTONS)
    +-- Enhanced Copy Snapshot (richer markdown export)
    +-- Copy Learning Data
    +-- Copy Debug Report
```

### Data Flow: API to Visual Components

```
GET /defaults  ------>  _loadDefaults()  ------>  Populate all form controls
                        (includes seed-match fields now)

_buildStartPayload()  <------  Read all form controls
        |                      (includes rng_use_seed_match: true,
        |                       rng_seed_wait_timeout_frames, advanced fields)
        v
POST /start  ------>  controller.start()  ------>  Lua bot loop

GET /status  ------>  _renderStatus()  ------>  Metrics bar
(every 800ms)         _renderSeedDiagnostics()  ------>  Seed-Match block
                      _renderTargetBoard()  ------>  Target cards
                      _renderLearningData()  ------>  Learning tables (NEW)
                      _renderCandidate()  ------>  Pokemon Detail Card (NEW)

GET /history  ------>  _renderHistory()  ------>  Table with IVs + Result columns
(every 800ms)
```

### Backend Changes Overview

| Layer | Change Type | Scope |
|-------|-------------|-------|
| **models.py** | DELETE 8 fields, fix 1 validator | execution_profile, execution_max_delay_frames, calibration_policy, calibration_probe_count, calibration_recheck_every_attempts, drift_threshold_frames, rng_pre_a4_hold_frames, rng_settle_frames_min/max. Fix le=3600 to le=216000. |
| **constants.py** | DELETE ~50 constants, FIX 2 defaults | All TIMING_LOCK_*, CALIBRATION_*, FAST_PROBE_*, dead LEARNER_* constants. Fix DEFAULT_RNG_USE_SEED_MATCH=True, DEFAULT_RNG_SEED_WAIT_TIMEOUT_FRAMES=36000. |
| **learner.py** | DELETE ~500 lines | Delete _derive_adaptive_rng_plan lines 657-1165 (10 dead strategies), delete _cycle_pick, delete _apply_execution_profile_overrides. Simplify _base_rng_plan. |
| **calibration.py** | DELETE 3 functions, SIMPLIFY 1 | Delete _segment_delta, _update_segment_ema, _update_calibration_segments. Reduce _update_calibration_state to ~10 lines (infer_status + target_miss_streak only). |
| **controller.py** | FIX 1 bug, PRUNE 2 methods | Fix line 3829: pass seed_match_mode=True. Prune _bot_start_fields to remove dead Lua fields. Prune dead timing_lock/timing_probe logic in _apply_target_overlay_to_plan. |
| **routes.py** | UPDATE 1 endpoint, UPDATE 1 options map | Add rng_use_seed_match + rng_seed_wait_timeout_frames to /defaults. Remove dead options (execution_profile choices, calibration_policy choices). |
| **tests** | DELETE ~30 test functions | All tests for dead strategies (timing_lock_*, phase_cycle_probe, global_seed_jump, exact_lock, fast_probe). |

---

## UX Overhaul -- Component Specifications

### Component 1: Main Controls Grid (Phase 7)

**What changes**: Remove 7 dead controls, keep 11 live controls.

**Controls to REMOVE from HTML + JS**:
| Control | Element ID | Why Dead |
|---------|-----------|----------|
| RNG Mode | `automationRngMode` | Seed-match is always deterministic; unique_seed_wait moves to Advanced |
| Execution Profile | `automationExecutionProfile` | All 3 profiles dead under seed-match |
| Unique Seed Window | `automationUniqueSeedWindow` | Moves to Advanced section |
| Execution Max Delay | `automationExecutionMaxDelayFrames` | Delay-based cap, dead |
| Settle Min Frames | `automationSettleMinFrames` | Per-press jitter, dead |
| Settle Max Frames | `automationSettleMaxFrames` | Per-press jitter, dead |
| Pre-Final-A Hold | `automationPreA4HoldFrames` | Replaced by seed-match |

**Controls that REMAIN in main view**:
Save Slot, Shiny, Nature, Gender, IV HP/Atk/Def/SpA/SpD/Spe/Total Min.

**Files modified**: bizhawk.html.j2 (lines 305-504), automation.js (init, _loadDefaults, _buildStartPayload).

### Component 2: Advanced Section (Phase 7)

**What it is**: A collapsible disclosure section between the filter grid and action buttons.

**UI pattern**: Mirrors `agent-chat__advanced-toggle` / `agent-chat__advanced-options` pattern already in bizhawk.html.j2. Toggle with `.open` class, chevron SVG rotates 90 degrees.

**Advanced controls**:
| Control | ID | Type | Default | Range | Notes |
|---------|-----|------|---------|-------|-------|
| Seed Wait Timeout (frames) | `automationSeedWaitTimeout` | number | 36000 | 60-216000, step=3600 | How long Lua polls before giving up |
| RNG Mode | `automationRngMode` | select | deterministic | deterministic, unique_seed_wait | Moved from main view |
| Unique Seed Window (frames) | `automationUniqueSeedWindow` | number | 180 | 0-7200, step=1 | Only relevant when RNG Mode = unique_seed_wait |
| Candidate Timeout (sec) | `automationCandidateTimeout` | number | 6.0 | 0.25-20.0, step=0.25 | NEW: was silently defaulted |
| Pre-A1 Spin Steps | `automationPreA1SpinSteps` | number | 0 | 0-240, step=1 | NEW: was silently defaulted |
| Target Horizon (frames) | `automationTargetHorizon` | number | 1800 | 30-20000 | NEW: was silently defaulted |
| Target Candidate Count | `automationTargetCandidateCount` | number | 64 | 1-256 | NEW: was silently defaulted |

**Informational text**: Brief explanation of seed-match behavior at top of Advanced section.

**Payload changes**: `_buildStartPayload()` always sends `rng_use_seed_match: true`. Advanced fields are read from their inputs with fallback to defaults.

### Component 3: Seed-Match Diagnostics (Phase 8)

**Location**: Status section, after metrics bar, before meta line.

**Data sources** (from GET /status polling response):
- `status.active_rng_plan.rng_target_seed` -- hex display
- `status.last_candidate.rng_seed_at_match` -- hex display
- `status.last_candidate.rng_seed_wait_frames` -- integer frames
- `status.last_candidate.candidate.seed_match_verification_outcome` -- result pill
- `status.calibration_state.press_to_generation_offset` -- offset integer

**Display**: 5-metric horizontal row matching existing metrics bar style. Result values use semantic coloring: exact_hit=green, seed_hit_pid_miss=yellow, timeout/total_miss=red.

**New HTML elements**: `automationSeedDiagnostics` container with 5 metric divs.
**New JS function**: `_renderSeedDiagnostics(status)` called from `_renderStatus()`.
**New CSS classes**: `.automation__seed-diagnostics`, `.automation__metric-v--good/--warn/--error/--mono`.

### Component 4: History Table (Phase 8)

**Column changes**: Remove Ability column (saves space, starters have obvious abilities). Add IVs column. Add Result column.

**Updated columns (12)**: #, Time, Species, Nature, Gender, Shiny, IVs, PID, Seed, Result, Moves, Match.

**IVs column**: Format `31/25/18/30/28/20` (HP/Atk/Def/SpA/SpD/Spe). Data from `row.ivs` (already returned by history_store.py:240). Display `--` when null.

**Result column**: Render from `row.candidate.seed_match_verification_outcome`. Colored pills: `HIT` (green), `PID?` (yellow), `TIMEOUT` (red), `MISS` (red), `--` (grey/absent).

**Files**: bizhawk.html.j2 (thead), automation.js (_renderHistory, _buildHistoryCopyText). colspan changes from 11 to 12.

### Component 5: Pokemon Detail Card (Phase 8)

**Replaces**: Current `automationCandidate` section (simple card with display_name, species_id, match chip, moves list).

**New design**:
- Species sprite/art (from PokeAPI or local asset if available; fallback to species_id text)
- IV stat bars: 6 horizontal bars (HP/Atk/Def/SpA/SpD/Spe) scaled 0-31, color-coded by tier (0-10 red, 11-20 yellow, 21-30 green, 31 gold)
- Nature effect indicators: +10% stat highlighted green, -10% stat highlighted red
- Stats: Nature, Gender, Ability, Shiny status, Level
- Moves: list with type colors if available
- IDs: PID (hex), Seeds (start -> candidate in hex)
- Match status: prominent pill

**Data sources**: All from `status.last_candidate` and `status.last_candidate.candidate`.

**Files**: bizhawk.html.j2 (new HTML structure), automation.js (new `_renderPokemonCard(candidate)` function), bizhawk.css (new `.automation__pokemon-card` component).

### Component 6: Learning Data Display (Phase 8)

**Replaces**: Current `automationObservability` pre block (raw multi-line text).

**New design**: Structured tables/metrics instead of codeblock.
- **Distribution table**: Nature distribution (top 5), Gender distribution, Ability distribution, Seed start frequency
- **Targeting metrics**: Target level, last score, avg score, scan mode
- **Strategy info**: Current strategy, phase, jump config
- **Pressure indicators**: Dup streak, dominance ratios

**Data source**: `status.observability` fields already returned by the API.

**Files**: bizhawk.html.j2, automation.js (new `_renderLearningData(status)` function), bizhawk.css.

### Component 7: Setting Profiles (Phase 9)

**What it is**: Save/load named configurations of all form control values.

**Storage**: localStorage under key `romlab_automation_profiles`. JSON object mapping profile name to settings snapshot.

**UI**: Small row above or beside Start/Stop buttons.
- Save button (opens name prompt)
- Load dropdown (lists saved profiles)
- Delete button (removes selected profile)

**Snapshot captures**: All form control values (main + advanced), serialized as JSON object.

**Load behavior**: Populates all form controls from snapshot. Advanced section auto-opens if snapshot contains non-default advanced values.

**Files**: automation.js (new `_saveProfile()`, `_loadProfile()`, `_deleteProfile()`, `_listProfiles()` functions), bizhawk.html.j2 (profile controls row).

### Component 8: Enhanced Copy Snapshot (Phase 9)

**Replaces**: Current `_buildSnapshotCopyText()` which produces a 7-section markdown report.

**Enhancements**:
- Add IVs section with full stat spread and nature effect annotation
- Add seed-match diagnostics section (target seed, matched seed, wait frames, result, offset)
- Add learning summary in structured format (not raw observability text)
- Improve formatting: aligned columns, consistent hex formatting, section headers

**Files**: automation.js (`_buildSnapshotCopyText()` rewrite).

---

## UX Overhaul -- File Change Map

### Phase 6 (Backend Cleanup) -- Files Modified

| File | Action | Lines Affected |
|------|--------|----------------|
| `src/rom_lab/api/routes/automation/models.py` | DELETE 8 fields, FIX validator | ~40 lines removed, 1 line fixed |
| `src/rom_lab/api/routes/automation/constants.py` | DELETE ~50 constants, FIX 2 defaults | ~150 lines removed, 2 lines changed |
| `src/rom_lab/api/routes/automation/learner.py` | DELETE ~500 lines (dead strategies) | Lines 657-1165 deleted, _cycle_pick and _apply_execution_profile_overrides deleted |
| `src/rom_lab/api/routes/automation/calibration.py` | DELETE 3 functions, SIMPLIFY 1 | ~200 lines removed |
| `src/rom_lab/api/routes/automation/controller.py` | FIX bug, PRUNE 2 methods | ~20 lines changed |
| `src/rom_lab/api/routes/automation/routes.py` | UPDATE defaults + options | ~10 lines changed |
| `tests/test_automation_routes.py` | DELETE ~30 dead test functions | ~800 lines removed |
| `tests/test_starter_target_planner.py` | AUDIT for dead refs | Minimal |

### Phase 7 (Core UI Overhaul) -- Files Modified

| File | Action | Lines Affected |
|------|--------|----------------|
| `.council/web/pages/bizhawk.html.j2` | REMOVE 7 controls, ADD Advanced section, ADD profile row | ~50 lines removed, ~40 lines added |
| `.council/web/static/js/automation.js` | REMOVE 7 vars/inits/defaults/payload, ADD Advanced section JS, ADD profile JS, UPDATE payload builder | ~60 lines removed, ~80 lines added |
| `.council/web/static/css/bizhawk.css` | ADD advanced toggle + options CSS | ~30 lines added |

### Phase 8 (Data Display Components) -- Files Modified

| File | Action | Lines Affected |
|------|--------|----------------|
| `.council/web/pages/bizhawk.html.j2` | ADD seed diagnostics block, UPDATE history thead, ADD Pokemon card HTML, ADD learning tables HTML | ~80 lines added |
| `.council/web/static/js/automation.js` | ADD _renderSeedDiagnostics, UPDATE _renderHistory (IVs+Result), ADD _renderPokemonCard, ADD _renderLearningData | ~200 lines added |
| `.council/web/static/css/bizhawk.css` | ADD seed diagnostics CSS, ADD history pill CSS, ADD Pokemon card CSS, ADD learning data CSS | ~120 lines added |

### Phase 9 (Profiles and Polish) -- Files Modified

| File | Action | Lines Affected |
|------|--------|----------------|
| `.council/web/pages/bizhawk.html.j2` | ADD profile controls row | ~10 lines added |
| `.council/web/static/js/automation.js` | ADD profile functions, REWRITE _buildSnapshotCopyText | ~100 lines added/changed |
| `.council/web/static/css/bizhawk.css` | ADD profile CSS, PREMIUM polish pass (spacing, shadows, transitions, typography) | ~80 lines added |
<!-- ID: references_appendix -->
## 10. References and Appendix

**Research Documents:**
- `RESEARCH_AUTOMATION_MODULARIZATION.md` -- auto-analyst, complete module boundary analysis
- `RESEARCH_POKEFINDER_RNG_ENGINE.md` -- rng-researcher, PokeFinder C++ parity verification
- `RESEARCH_TESTING_INFRASTRUCTURE.md` -- test-architect, two-layer test design
- `RESEARCH_DECOMP_RNG_TIMING.md` -- decomp-specialist, Fire Red RNG chain analysis
- `RESEARCH_ARCHITECTURE_PATTERNS.md` -- synthesis-lead, unified architecture vision

**Key Source Files:**
- `src/rom_lab/api/routes/automation.py` (6,857 lines) -- the monolith being split
- `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` (254 lines) -- LCRNG engine
- `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` (754 lines) -- target planner
- `src/rom_lab/plugins/base.py` (245 lines) -- GamePlugin ABC
- `tests/test_automation_routes.py` (3,756 lines) -- existing test suite
- `tests/test_rng_oracle_pokefinder_parity.py` -- existing PokeFinder parity tests

**External References:**
- PokeFinder: `admiral_fish/pokefinder` -- authoritative Gen 3 RNG tool
- Fire Red decomp: `decomps/pokefirered/` -- game source (local, gitignored)
- PokeFinder fixtures: `.local_refs/rng_sources/admiral_fish_pokefinder/Test/` (gitignored)
