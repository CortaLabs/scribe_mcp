---
id: automation_rng_modular_2026_02_21-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 automation_rng_modular_2026_02_21"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 08:26:55 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — automation_rng_modular_2026_02_21
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-21 05:10:19 UTC

> Execution roadmap for automation_rng_modular_2026_02_21.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Parallel Packages | Confidence |
|-------|------|------------------|-------------------|------------|
| Phase 1 -- Module Extraction | Split 6,857-line automation.py into 12-file package | Package structure, __init__.py re-exports, all modules extracted | 4 parallel packages | 0.95 |
| Phase 2 -- RNG Engine Enhancement | Add initial_seed_from_timer1() and LCRNG test vectors | rng_oracle.py enhancement, PokeFinder parity fixtures | 2 parallel packages (runs parallel with Phase 1) | 0.95 |
| Phase 3 -- Testing Infrastructure | Create new test files for modular codebase | 3 new test files, emulator integration patterns | 3 parallel packages | 0.90 |
| Phase 4 -- Strategy Pattern Foundation | Add AutomationStrategy ABC for future multi-strategy support | ABC definition, registration hook on GamePlugin | 2 parallel packages | 0.85 |
| Phase 5 -- Integration and Verification | End-to-end validation, regression verification | Full test suite green, import compatibility confirmed | 2 sequential packages | 0.90 |

**Parallel Execution Model:** Phases 1 and 2 run concurrently (no file overlap). Phase 3 begins after Phase 1 completes (tests import from new package). Phase 4 can begin after Phase 1 completes. Phase 5 is the final gate.

**Dependency Graph:**
```
Phase 1 (Module Extraction) ----+---> Phase 3 (Testing) ----+
                                |                            |
                                +---> Phase 4 (Strategy) ----+---> Phase 5 (Integration)
                                                             |
Phase 2 (RNG Engine) -------------------------------------->-+
```
<!-- ID: phase_0 -->
### Phase 1 -- Module Extraction (Wave 1A)

**Objective:** Convert `src/rom_lab/api/routes/automation.py` (6,857 lines) into a 12-file Python package at `src/rom_lab/api/routes/automation/` with backward-compatible `__init__.py` re-exports.

**Prerequisites:** None (first phase).
**Estimated Effort:** 4 parallel task packages, each completable in one agent session.

---

#### Task Package 1.1: Package Scaffold and Constants/Models Extraction

**Agent Type:** Forge (sonnet)
**Scope:** Create the package directory, extract constants and Pydantic models into their own modules.
**Files to Create:**
- `src/rom_lab/api/routes/automation/__init__.py` (empty initially, populated in Task 1.4)
- `src/rom_lab/api/routes/automation/constants.py`
- `src/rom_lab/api/routes/automation/models.py`

**Specifications:**
1. Create `automation/` directory under `src/rom_lab/api/routes/`
2. Extract lines 1-212 from `automation.py` (all constants: `STARTER_*`, `CALIBRATION_*`, enums, type aliases) into `constants.py`. Include all imports these constants need.
3. Extract `StarterResetFilters` (lines 559-603), `StarterResetStartRequest` (lines 606-756), and all other Pydantic model classes into `models.py`. `models.py` imports from `constants.py`.
4. Create empty `__init__.py` with a comment: `# Re-exports populated after all modules are extracted (Task 1.4)`

**Parallel With:** Task 1.2, Task 1.3 (no file overlap)
**Dependencies:** None
**Acceptance Criteria:**
- `python -c "from rom_lab.api.routes.automation.constants import STARTER_CANDIDATE_CAPTURE_RNG_OFFSET_CALLS"` succeeds
- `python -c "from rom_lab.api.routes.automation.models import StarterResetFilters"` succeeds
- `luac -p` not applicable (Python only)

**Out of Scope:** Do NOT delete original `automation.py` yet. Do NOT modify `__init__.py` re-exports yet.

---

#### Task Package 1.2: History Store and State Factories Extraction

**Agent Type:** Forge (sonnet)
**Scope:** Extract `StarterHistoryStore` and state factory functions into their own modules.
**Files to Create:**
- `src/rom_lab/api/routes/automation/history_store.py`
- `src/rom_lab/api/routes/automation/state_factories.py`

**Specifications:**
1. Extract `StarterHistoryStore` class (lines 353-553) into `history_store.py`. Include its SQLite imports, `_DB_PATH`, and initialization logic. Import constants from `constants.py`.
2. Extract all state snapshot factory functions (functions that create/manipulate state dicts for API responses -- approximately 8-10 functions like `_build_state_snapshot`, `_format_timing_info`, etc.) into `state_factories.py`. Import from `constants.py` and `models.py` as needed.

**Parallel With:** Task 1.1, Task 1.3 (no file overlap)
**Dependencies:** None (can reference constants.py by convention even before Task 1.1 creates it -- both execute in same phase, merged at end)
**Acceptance Criteria:**
- `python -c "from rom_lab.api.routes.automation.history_store import StarterHistoryStore"` succeeds
- `python -c "from rom_lab.api.routes.automation.state_factories import _build_state_snapshot"` succeeds (or equivalent top-level factory function)

**Out of Scope:** Do NOT modify original `automation.py`. Do NOT extract controller logic.

---

#### Task Package 1.3: Dialogue Detection, Filter Engine, and Spin Timing Extraction

**Agent Type:** Forge (sonnet)
**Scope:** Extract the three pure-function modules: dialogue detection, filter/validation engine, and spin timing.
**Files to Create:**
- `src/rom_lab/api/routes/automation/dialogue_detection.py`
- `src/rom_lab/api/routes/automation/filter_engine.py`
- `src/rom_lab/api/routes/automation/spin_timing.py`

**Specifications:**
1. Extract dialogue detection functions (screen text parsing, dialogue state machine helpers -- functions like `_detect_dialogue_state`, `_parse_screen_text`, `_is_starter_screen`) into `dialogue_detection.py`. These are pure functions taking state dicts and returning detection results.
2. Extract filter/validation functions (IV matching, nature filtering, shiny checks -- functions like `_validate_exact_precheck`, `_check_filters_match`, `_ivs_match_thresholds`) into `filter_engine.py`. Import from `constants.py` and `models.py`.
3. Extract spin timing functions (frame counting, timing calibration helpers -- functions like `_compute_spin_frames`, `_calculate_timing_offset`) into `spin_timing.py`. Import from `constants.py`.

**Parallel With:** Task 1.1, Task 1.2 (no file overlap)
**Dependencies:** None
**Acceptance Criteria:**
- Each new module imports cleanly: `python -c "from rom_lab.api.routes.automation.filter_engine import _validate_exact_precheck"` (or equivalent)
- No circular imports between the three new modules

**Out of Scope:** Do NOT extract the learner, calibration, or controller. Do NOT modify original `automation.py`.

---

#### Task Package 1.4: Controller, Routes, __init__.py Re-exports, and File Swap

**Agent Type:** Forge (sonnet)
**Scope:** Extract the remaining large modules (controller, learner, calibration, target overlay, routes), wire up `__init__.py` re-exports, and perform the file-to-package swap.
**Files to Create:**
- `src/rom_lab/api/routes/automation/learner.py`
- `src/rom_lab/api/routes/automation/calibration.py`
- `src/rom_lab/api/routes/automation/target_overlay.py`
- `src/rom_lab/api/routes/automation/controller.py`
- `src/rom_lab/api/routes/automation/routes.py`

**Files to Modify:**
- `src/rom_lab/api/routes/automation/__init__.py` (add all re-exports)

**Files to Delete:**
- `src/rom_lab/api/routes/automation.py` (the original monolith -- Python cannot have both file and package with same name)

**Specifications:**
1. Extract `StarterResetController` class (lines 759-4475, 3717 lines, ~50 methods) into `controller.py`. This is the largest module. It imports from all other modules in the package.
2. Extract learner functions into `learner.py`, calibration functions into `calibration.py`, target overlay functions into `target_overlay.py`.
3. Extract FastAPI route handlers (lines 4481-4583) into `routes.py`. Include the `router = APIRouter()` definition and all `@router.*` decorated functions. Include module-level singletons: `_history_store = StarterHistoryStore(...)` and `_controller = StarterResetController(...)`. Include the lazy MCP import pattern (lines 4586-4592).
4. Update `__init__.py` with comprehensive re-exports so that ALL existing `from rom_lab.api.routes.automation import X` statements continue to work. This includes: `StarterResetController`, `StarterResetFilters`, `StarterResetStartRequest`, `StarterHistoryStore`, `_history_store`, `_controller`, `_validate_exact_precheck`, `router`, and every other name currently accessed by `tests/test_automation_routes.py`.
5. Delete original `automation.py` (CRITICAL: Python cannot have both `automation.py` and `automation/` at the same path level).

**Parallel With:** NONE -- this is the merge task. Runs AFTER Tasks 1.1, 1.2, 1.3 are complete.
**Dependencies:** Task 1.1, Task 1.2, Task 1.3
**Acceptance Criteria:**
- `python -c "from rom_lab.api.routes.automation import StarterResetController, StarterResetFilters, _controller, router"` succeeds
- `pytest tests/test_automation_routes.py -x --tb=short` passes (ALL existing tests)
- `python -c "from rom_lab.api.routes.automation import _validate_exact_precheck"` succeeds
- No `automation.py` file exists alongside the `automation/` directory
- `grep -r "from rom_lab.api.routes.automation import" src/ tests/ | grep -v __pycache__` shows no broken imports

**Out of Scope:** Do NOT modify any test files. Do NOT change any API behavior.

---

### Phase 1 Milestone Table

| Task Package | Agent | Files | Parallel? | Acceptance Criteria | Status |
|-------------|-------|-------|-----------|---------------------|--------|
| 1.1 Scaffold + Constants/Models | Forge | `__init__.py`, `constants.py`, `models.py` | Yes (with 1.2, 1.3) | Import constants and models from new modules | Planned |
| 1.2 History + State Factories | Forge | `history_store.py`, `state_factories.py` | Yes (with 1.1, 1.3) | Import StarterHistoryStore from new module | Planned |
| 1.3 Dialogue + Filter + Timing | Forge | `dialogue_detection.py`, `filter_engine.py`, `spin_timing.py` | Yes (with 1.1, 1.2) | Import filter_engine functions from new module | Planned |
| 1.4 Controller + Routes + Swap | Forge | `controller.py`, `learner.py`, `calibration.py`, `target_overlay.py`, `routes.py`, `__init__.py` (update) | No (after 1.1-1.3) | `pytest tests/test_automation_routes.py -x` passes | Planned |
<!-- ID: phase_1 -->
### Phase 2 -- RNG Engine Enhancement (Wave 1B -- runs parallel with Phase 1)

**Objective:** Enhance `rng_oracle.py` with `initial_seed_from_timer1()` function and create comprehensive PokeFinder parity test fixtures.

**Prerequisites:** None (rng_oracle.py is a separate file from automation.py -- no conflict with Phase 1).
**Estimated Effort:** 2 parallel task packages.

**CRITICAL NOTE:** Phase 2 runs concurrently with Phase 1. There is ZERO file overlap -- Phase 1 works on `automation.py` and creates files in `automation/`, while Phase 2 works on `rng_oracle.py` and creates files in `tests/`.

---

#### Task Package 2.1: initial_seed_from_timer1() and LCRNG Enhancement

**Agent Type:** Forge (sonnet)
**Scope:** Add the `initial_seed_from_timer1()` function to `rng_oracle.py` and verify LCRNG constants.
**Files to Modify:**
- `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py`

**Specifications:**
1. Add `initial_seed_from_timer1(timer1_value: int) -> int` function:
   ```python
   def initial_seed_from_timer1(timer1_value: int) -> int:
       """Compute initial gRngValue from Timer1 counter (REG_TM1CNT_L).
       FRLG: SeedRng(REG_TM1CNT_L) stores the 16-bit Timer1 value
       directly as gRngValue (zero-extended to 32 bits).
       Per decomp: decomps/pokefirered/src/main.c:SeedRngAndSetTrainerId()
       """
       return timer1_value & 0xFFFF
   ```
2. Add module-level docstring reference to PokeFinder equivalence: our `next_seed()` matches PokeFinder `LCRNG::next()`, our `method1_generate()` matches `StaticGenerator3::generate()`.
3. Verify existing constants: `A = 0x41C64E6D`, `C = 0x6073` (Gen 3 LCRNG). These should already be present -- do not change if correct.
4. Add `__all__` export list if not present.

**Parallel With:** Task 2.2, all Phase 1 tasks
**Dependencies:** None
**Acceptance Criteria:**
- `python -c "from rom_lab.plugins.pokemon_fire_red.rng_oracle import initial_seed_from_timer1; assert initial_seed_from_timer1(0x1234) == 0x1234"` succeeds
- `python -c "from rom_lab.plugins.pokemon_fire_red.rng_oracle import initial_seed_from_timer1; assert initial_seed_from_timer1(0x1FFFF) == 0xFFFF"` succeeds (mask to 16-bit)
- Existing `pytest tests/test_rng_oracle_pokefinder_parity.py -x` still passes

**Out of Scope:** Do NOT modify any other file. Do NOT change existing function signatures.

---

#### Task Package 2.2: PokeFinder Parity Test Fixtures

**Agent Type:** Forge (sonnet)
**Scope:** Create comprehensive test fixture files for LCRNG and Method 1 validation.
**Files to Create:**
- `tests/fixtures/rng/lcrng_vectors.json`
- `tests/fixtures/rng/method1_pokemon.json`
- `tests/fixtures/rng/pokefinder_reference.json`

**Specifications:**
1. Create `lcrng_vectors.json` with 20+ LCRNG chain test vectors:
   ```json
   [
     {"seed": "0x00000000", "advances": 1, "expected": "0x00006073"},
     {"seed": "0x00000000", "advances": 10, "expected": "<compute>"},
     {"seed": "0x00000001", "advances": 1, "expected": "<compute>"},
     ...
   ]
   ```
   Generate values using the known LCRNG formula: `seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF`.

2. Create `method1_pokemon.json` with 10+ Method 1 generation results from known seeds:
   ```json
   [
     {
       "seed": "0x00000000",
       "pid": "<computed_pid>",
       "ivs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
       "nature": "<computed>",
       "ability_bit": 0,
       "shiny_for_tid_sid": null
     },
     ...
   ]
   ```

3. Create `pokefinder_reference.json` with cross-reference data confirming our engine matches PokeFinder output for the same seeds.

4. Ensure `tests/fixtures/rng/` directory exists (create if needed).

**Parallel With:** Task 2.1, all Phase 1 tasks
**Dependencies:** None
**Acceptance Criteria:**
- All JSON files are valid: `python -c "import json; json.load(open('tests/fixtures/rng/lcrng_vectors.json'))"` succeeds for each
- At least 20 LCRNG vectors, 10 Method 1 vectors
- Values are mathematically correct (verifiable against LCRNG formula)

**Out of Scope:** Do NOT write test Python files yet (that is Phase 3). Do NOT modify rng_oracle.py (that is Task 2.1).

---

### Phase 2 Milestone Table

| Task Package | Agent | Files | Parallel? | Acceptance Criteria | Status |
|-------------|-------|-------|-----------|---------------------|--------|
| 2.1 initial_seed_from_timer1 | Forge | `rng_oracle.py` | Yes (with 2.2 and all Phase 1) | New function importable, existing tests pass | Planned |
| 2.2 PokeFinder Fixtures | Forge | `tests/fixtures/rng/*.json` | Yes (with 2.1 and all Phase 1) | Valid JSON, 20+ LCRNG + 10+ Method 1 vectors | Planned |
<!-- ID: milestone_tracking -->
### Phase 3 -- Testing Infrastructure (Wave 2A)

**Objective:** Create new test files that exercise the modularized codebase and RNG engine enhancements.

**Prerequisites:** Phase 1 complete (modules must be importable from `automation/` package). Phase 2 complete (fixtures and `initial_seed_from_timer1` must exist).
**Estimated Effort:** 3 parallel task packages.

---

#### Task Package 3.1: LCRNG Pure Math Tests

**Agent Type:** Forge (sonnet)
**Scope:** Create test file for LCRNG chain validation using fixture data.
**Files to Create:**
- `tests/test_rng_engine_lcrng.py`

**Specifications:**
1. Create `test_rng_engine_lcrng.py` that:
   - Loads `tests/fixtures/rng/lcrng_vectors.json`
   - Tests `next_seed()` against all vectors
   - Tests `prev_seed()` as inverse of `next_seed()` (round-trip property)
   - Tests `advance(seed, n)` for multi-step chains
   - Tests `initial_seed_from_timer1()` with edge cases (0, 0xFFFF, values > 16 bits)
   - Tests seed wraparound at 32-bit boundary
2. All tests are pure math -- no emulator dependency. Must run in CI.
3. Use `pytest.mark.parametrize` with fixture data for vector tests.

**Parallel With:** Task 3.2, Task 3.3
**Dependencies:** Phase 1 (Task 1.4 complete), Phase 2 (Tasks 2.1 and 2.2 complete)
**Acceptance Criteria:**
- `pytest tests/test_rng_engine_lcrng.py -v` passes
- At least 20 test cases from fixture data
- No emulator dependency (runs in bare CI environment)

**Out of Scope:** Do NOT modify rng_oracle.py. Do NOT modify existing test files.

---

#### Task Package 3.2: Method 1 Generation Tests

**Agent Type:** Forge (sonnet)
**Scope:** Create test file for Method 1 Pokemon generation validation.
**Files to Create:**
- `tests/test_rng_engine_method1.py`

**Specifications:**
1. Create `test_rng_engine_method1.py` that:
   - Loads `tests/fixtures/rng/method1_pokemon.json`
   - Tests `method1_generate(seed)` against all fixture vectors
   - Verifies PID computation (two RNG calls via Random32)
   - Verifies IV extraction (two RNG calls via Random, bit packing)
   - Verifies nature derivation from PID (`pid % 25`)
   - Verifies ability bit derivation from PID (`pid & 1`)
   - Tests shiny detection with known TID/SID pairs
2. All tests are pure math -- no emulator dependency.
3. Cross-reference with `tests/fixtures/rng/pokefinder_reference.json` for parity confirmation.

**Parallel With:** Task 3.1, Task 3.3
**Dependencies:** Phase 1 (Task 1.4 complete), Phase 2 (Tasks 2.1 and 2.2 complete)
**Acceptance Criteria:**
- `pytest tests/test_rng_engine_method1.py -v` passes
- At least 10 test cases from fixture data
- PokeFinder parity confirmed for all vectors

**Out of Scope:** Do NOT modify rng_oracle.py. Do NOT modify existing parity tests.

---

#### Task Package 3.3: Emulator Integration Test Patterns

**Agent Type:** Forge (sonnet)
**Scope:** Create test file with emulator integration test patterns (skip-gated).
**Files to Create:**
- `tests/test_rng_emulator_integration.py`

**Specifications:**
1. Create `test_rng_emulator_integration.py` with skip-gating:
   ```python
   import pytest
   _BIZHAWK_RUNNING = False  # Set True when emulator is active
   pytestmark = pytest.mark.skipif(not _BIZHAWK_RUNNING, reason="BizHawk not running")
   ```
2. Add test stubs (not full implementations -- those need live emulator):
   - `test_read_grng_value_matches_oracle()` -- read gRngValue from RAM 0x03005000, advance oracle, compare
   - `test_initial_seed_matches_timer1()` -- capture Timer1 at boot, verify initial seed
   - `test_method1_prediction_matches_generated_pokemon()` -- predict starter from pre-generation seed, compare with actual generated Pokemon
3. Each test stub should have a clear docstring explaining what the live test validates.
4. Include `STARTER_CANDIDATE_CAPTURE_RNG_OFFSET_CALLS = 6` reference for the offset constant.

**Parallel With:** Task 3.1, Task 3.2
**Dependencies:** Phase 2 (Task 2.1 complete -- imports `initial_seed_from_timer1`)
**Acceptance Criteria:**
- `pytest tests/test_rng_emulator_integration.py -v` shows all tests SKIPPED (not erroring)
- File imports cleanly without emulator present
- At least 3 test stubs with clear docstrings

**Out of Scope:** Do NOT implement live emulator logic (that requires BizHawk running). Stubs only.

---

### Phase 3 Milestone Table

| Task Package | Agent | Files | Parallel? | Acceptance Criteria | Status |
|-------------|-------|-------|-----------|---------------------|--------|
| 3.1 LCRNG Tests | Forge | `test_rng_engine_lcrng.py` | Yes (with 3.2, 3.3) | pytest passes, 20+ test cases | Planned |
| 3.2 Method 1 Tests | Forge | `test_rng_engine_method1.py` | Yes (with 3.1, 3.3) | pytest passes, PokeFinder parity | Planned |
| 3.3 Emulator Integration Stubs | Forge | `test_rng_emulator_integration.py` | Yes (with 3.1, 3.2) | All tests skip cleanly | Planned |

---

### Phase 4 -- Strategy Pattern Foundation (Wave 2B -- can parallel with Phase 3)

**Objective:** Add `AutomationStrategy` ABC to enable future multi-strategy support without modifying existing automation code.

**Prerequisites:** Phase 1 complete (modularized package must exist).
**Estimated Effort:** 2 parallel task packages.

**DESIGN NOTE:** This phase is intentionally lightweight. It creates the ABC and registration hook but does NOT refactor existing code to use it. The existing `StarterResetController` continues to work as-is. The strategy pattern is scaffolding for FUTURE strategy additions.

---

#### Task Package 4.1: AutomationStrategy ABC

**Agent Type:** Forge (sonnet)
**Scope:** Define the abstract base class for automation strategies.
**Files to Create:**
- `src/rom_lab/api/routes/automation/strategy.py`

**Specifications:**
1. Create `strategy.py` with:
   ```python
   from abc import ABC, abstractmethod
   from typing import Any

   class AutomationStrategy(ABC):
       """Abstract base class for game automation strategies.
       
       Each strategy encapsulates a complete automation workflow
       (e.g., starter reset, shiny hunting, EV training).
       
       Strategies are registered via GamePlugin.get_automations()
       and exposed through the API router.
       """
       
       @property
       @abstractmethod
       def name(self) -> str:
           """Unique strategy identifier (e.g., 'starter_reset')."""
           ...
       
       @property
       @abstractmethod
       def display_name(self) -> str:
           """Human-readable name for UI display."""
           ...
       
       @abstractmethod
       async def start(self, config: dict[str, Any]) -> dict[str, Any]:
           """Begin the automation with given configuration."""
           ...
       
       @abstractmethod
       async def stop(self) -> dict[str, Any]:
           """Stop the automation gracefully."""
           ...
       
       @abstractmethod
       async def get_state(self) -> dict[str, Any]:
           """Return current automation state for API/UI."""
           ...
   ```
2. Add `AutomationStrategy` to `__init__.py` re-exports.
3. Include docstring noting this is scaffolding -- existing `StarterResetController` is NOT refactored to use it in this project.

**Parallel With:** Task 4.2
**Dependencies:** Phase 1 (Task 1.4 complete -- package must exist for __init__.py update)
**Acceptance Criteria:**
- `python -c "from rom_lab.api.routes.automation.strategy import AutomationStrategy"` succeeds
- `python -c "from rom_lab.api.routes.automation import AutomationStrategy"` succeeds (re-export)
- ABC cannot be instantiated directly

**Out of Scope:** Do NOT refactor StarterResetController to inherit from AutomationStrategy. Do NOT modify routes.py.

---

#### Task Package 4.2: GamePlugin Registration Hook

**Agent Type:** Forge (sonnet)
**Scope:** Add `get_automations()` method to `GamePlugin` ABC for future strategy registration.
**Files to Modify:**
- `src/rom_lab/plugins/base.py`

**Specifications:**
1. Add method to `GamePlugin` class:
   ```python
   def get_automations(self) -> dict[str, type]:
       """Return available automation strategies for this game.
       
       Returns:
           Dictionary mapping strategy name to strategy class.
           Default: empty dict (no automations registered).
           
       Example override:
           def get_automations(self):
               from rom_lab.api.routes.automation.strategy import AutomationStrategy
               return {"starter_reset": StarterResetStrategy}
       """
       return {}
   ```
2. This is a NON-ABSTRACT method with a default empty return. Existing plugins do not need to override it.
3. Add type annotation using `TYPE_CHECKING` guard to avoid circular import:
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING
   if TYPE_CHECKING:
       from rom_lab.api.routes.automation.strategy import AutomationStrategy
   ```

**Parallel With:** Task 4.1
**Dependencies:** Phase 1 (Task 1.4 complete -- strategy.py must exist for type reference)
**Acceptance Criteria:**
- `python -c "from rom_lab.plugins.base import GamePlugin; assert GamePlugin.get_automations"` succeeds
- Existing plugin imports still work: `python -c "from rom_lab.plugins.pokemon_fire_red import FireRedPlugin"`
- No circular import errors

**Out of Scope:** Do NOT implement get_automations() on FireRedPlugin yet. Do NOT modify any other plugin files.

---

### Phase 4 Milestone Table

| Task Package | Agent | Files | Parallel? | Acceptance Criteria | Status |
|-------------|-------|-------|-----------|---------------------|--------|
| 4.1 AutomationStrategy ABC | Forge | `strategy.py`, `__init__.py` (update) | Yes (with 4.2) | ABC importable from package | Planned |
| 4.2 GamePlugin Hook | Forge | `base.py` | Yes (with 4.1) | get_automations() exists, no circular imports | Planned |

---

### Phase 5 -- Integration and Verification (Wave 3 -- Final Gate)

**Objective:** End-to-end verification that ALL existing tests pass, ALL new modules work together, and backward compatibility is confirmed.

**Prerequisites:** Phases 1-4 complete.
**Estimated Effort:** 2 sequential task packages (order matters for verification).

---

#### Task Package 5.1: Full Regression Test Suite

**Agent Type:** Forge (sonnet)
**Scope:** Run the complete test suite and fix any integration issues.
**Files to Modify:** Any file as needed for bug fixes (should be minimal if Phases 1-4 executed correctly).

**Specifications:**
1. Run full test suite: `pytest tests/ -x --tb=short -q`
2. Specifically verify:
   - `pytest tests/test_automation_routes.py -v` -- ALL existing tests pass
   - `pytest tests/test_rng_oracle_pokefinder_parity.py -v` -- existing parity tests pass
   - `pytest tests/test_rng_engine_lcrng.py -v` -- new LCRNG tests pass
   - `pytest tests/test_rng_engine_method1.py -v` -- new Method 1 tests pass
   - `pytest tests/test_rng_emulator_integration.py -v` -- emulator tests skip cleanly
   - `pytest tests/test_starter_target_planner.py -v` -- planner tests pass
   - `pytest tests/test_perception_fixes.py -v` -- perception tests pass
3. Fix any import errors, missing re-exports, or integration bugs discovered.
4. Verify no `automation.py` file exists alongside `automation/` directory.

**Parallel With:** NONE -- must run first in Phase 5
**Dependencies:** All of Phases 1-4
**Acceptance Criteria:**
- `pytest tests/ -x --tb=short -q` exits with code 0
- Zero test failures
- Zero import errors

**Out of Scope:** Do NOT add new test cases. Focus on making existing + Phase 3 tests pass.

---

#### Task Package 5.2: Import Compatibility Audit and Documentation

**Agent Type:** Forge (sonnet)
**Scope:** Verify all import paths work and create a migration summary.
**Files to Modify:** `src/rom_lab/api/routes/automation/__init__.py` (if missing re-exports found)

**Specifications:**
1. Run comprehensive import audit:
   ```bash
   grep -rn "from rom_lab.api.routes.automation" src/ tests/ --include="*.py" | grep -v __pycache__
   grep -rn "import automation" src/ tests/ --include="*.py" | grep -v __pycache__
   ```
2. For EVERY import found, verify it resolves correctly.
3. Add any missing names to `__init__.py` re-exports.
4. Verify the FastAPI router is correctly mounted:
   ```python
   python -c "from rom_lab.api.routes.automation import router; print(router.routes)"
   ```
5. Log the final module structure and any re-exports added.

**Parallel With:** NONE -- runs after Task 5.1
**Dependencies:** Task 5.1
**Acceptance Criteria:**
- All `grep`-found imports resolve without error
- `__init__.py` re-exports cover 100% of externally-used names
- FastAPI router has all expected routes

**Out of Scope:** Do NOT refactor any working code. Only fix broken imports.

---

### Phase 5 Milestone Table

| Task Package | Agent | Files | Parallel? | Acceptance Criteria | Status |
|-------------|-------|-------|-----------|---------------------|--------|
| 5.1 Full Regression Suite | Forge | Any (bug fixes) | No (first) | `pytest tests/ -x` passes | Planned |
| 5.2 Import Audit | Forge | `__init__.py` (if needed) | No (after 5.1) | All imports resolve, router mounted | Planned |

---

## Overall Milestone Tracking

| Milestone | Wave | Depends On | Owner | Status | Evidence |
|-----------|------|------------|-------|--------|----------|
| Phase 1 Tasks 1.1-1.3 Complete | Wave 1A | None | Forge x3 | Planned | Module imports succeed |
| Phase 2 Tasks 2.1-2.2 Complete | Wave 1B | None | Forge x2 | Planned | initial_seed_from_timer1 importable, fixtures valid |
| Phase 1 Task 1.4 Complete | Wave 1A (merge) | Tasks 1.1-1.3 | Forge | Planned | `pytest test_automation_routes.py` passes |
| Phase 3 Tasks 3.1-3.3 Complete | Wave 2A | Phases 1, 2 | Forge x3 | Planned | All new test files pass/skip |
| Phase 4 Tasks 4.1-4.2 Complete | Wave 2B | Phase 1 | Forge x2 | Planned | ABC importable, hook exists |
| Phase 5 Tasks 5.1-5.2 Complete | Wave 3 (gate) | Phases 1-4 | Forge | Planned | Full `pytest tests/` green |
| PROJECT COMPLETE | -- | All phases | Nexus | Planned | All milestones green |

**Wave Execution Schedule:**
- **Wave 1 (5 parallel agents):** Tasks 1.1, 1.2, 1.3 + Tasks 2.1, 2.2
- **Wave 1 merge (1 agent):** Task 1.4 (after Wave 1 parallel completes)
- **Wave 2 (up to 5 parallel agents):** Tasks 3.1, 3.2, 3.3 + Tasks 4.1, 4.2
- **Wave 3 (sequential, 1 agent):** Tasks 5.1, then 5.2
<!-- ID: retro_notes -->
## Retro Notes (Phases 1-5)

_(Phases 1-5 completed. See PROGRESS_LOG for retrospective.)_

---

# UX Overhaul Phase Plan (Phases 6-9)
<!-- ID: ux_overhaul_phases -->

**Date**: 2026-02-21
**Author**: ArchitectAgent
**Depends on**: Phases 1-5 (all complete)
**Research**: RESEARCH_UI_SURFACE_20260221_0809.md, RESEARCH_BROKEN_CODE_AUDIT.md, RESEARCH_SEED_MATCH_UX.md

---

## Phase Overview (UX Overhaul)

| Phase | Name | Scope | Est. Task Packages | Dependencies |
|-------|------|-------|--------------------|--------------|
| 6 | Backend Cleanup | Delete dead code, fix bugs, fix defaults | 4 | Phases 1-5 complete |
| 7 | Core UI Overhaul | Remove dead controls, add Advanced section, fix payload | 3 | Phase 6 complete |
| 8 | Data Display Components | Seed diagnostics, history IVs+Result, Pokemon card, learning tables | 4 | Phase 7 complete |
| 9 | Profiles and Polish | Setting profiles, enhanced copy, premium CSS | 3 | Phase 8 complete |

**Wave structure**:
- **Wave A**: Phase 6 (backend only, no UI changes)
- **Wave B**: Phase 7 (UI structural changes, depends on Wave A)
- **Wave C**: Phase 8 (new display components, depends on Wave B)
- **Wave D**: Phase 9 (polish layer, depends on Wave C)

All waves are sequential. Within each wave, task packages may run in parallel where no file conflicts exist.

---

## Phase 6 -- Backend Cleanup
<!-- ID: phase_6 -->

**Goal**: Delete all dead code from the delay-based timing system, fix critical bugs, correct defaults. The backend must be clean before the UI can be simplified.

**Acceptance**: All remaining tests pass after deletions. No dead code remains. Seed-match is the only execution path.

### Task Package 6.1: Model and Constants Cleanup
<!-- ID: tp_6_1 -->

**Scope**: Delete dead model fields from StarterResetStartRequest, fix validator bug, delete dead constants, fix default values.

**Files to Modify**:
- `src/rom_lab/api/routes/automation/models.py`
- `src/rom_lab/api/routes/automation/constants.py`

**Specifications**:

1. In `models.py`, DELETE these fields from `StarterResetStartRequest`:
   - `execution_profile` (line 183-189)
   - `execution_max_delay_frames` (line 190-198)
   - `calibration_policy` (line 227-230)
   - `calibration_probe_count` (line 231-234)
   - `calibration_recheck_every_attempts` (line 235-240)
   - `drift_threshold_frames` (line 241-248)
   - `rng_pre_a4_hold_frames` (line 163-168)
   - `rng_settle_frames_min` (line 142-147)
   - `rng_settle_frames_max` (line 148-153)
   - Also delete the `rng_settle_frames_max` field_validator (line 250-255)

2. In `models.py`, FIX `rng_seed_wait_timeout_frames` validator: change `le=3600` to `le=216000` (line 180)

3. In `constants.py`, CHANGE:
   - `DEFAULT_RNG_USE_SEED_MATCH = False` -> `True` (line 39)
   - `DEFAULT_RNG_SEED_WAIT_TIMEOUT_FRAMES = 600` -> `36000` (line 40)

4. In `constants.py`, DELETE all constants listed in RESEARCH_BROKEN_CODE_AUDIT.md "DELETE" section (~50 constants). This includes:
   - All `TIMING_LOCK_*` constants (lines 169-199)
   - All `TIMING_PROBE_*` constants (lines 189-231)
   - All `FAST_PROBE_*` constants (lines 131-134)
   - All `CALIBRATION_*` constants (lines 139-142)
   - All `PREDICTION_*` constants except `PREDICTION_CANDIDATE_CAPTURE_OFFSET_CALLS` (lines 143-155)
   - `SETTLE_PHASE_CYCLE`, `WAIT_PHASE_CYCLE` (lines 95-96)
   - `LEARNER_GLOBAL_JUMP_*` constants (lines 101-104)
   - `LEARNER_TARGET_LADDER_MAX`, `LEARNER_TARGET_SINGLE_HIT_STREAK_TRIGGER`, `LEARNER_STRONG_SEED_START_FORCE_JUMP` (lines 105-107)
   - `LEARNER_MAX_SETTLE_FRAMES`, `LEARNER_MAX_WAIT_MIN_FRAMES`, `LEARNER_MAX_PRE_A4_HOLD_FRAMES` (lines 79-85)
   - `SEGMENT_JITTER_*` constants (lines 259-260)
   - `DEFAULT_CALIBRATION_*`, `DEFAULT_DRIFT_THRESHOLD_FRAMES`, `DEFAULT_EXECUTION_PROFILE` (lines 28, 35-38)
   - `DEFAULT_RNG_SETTLE_FRAMES_MIN/MAX`, `DEFAULT_RNG_PRE_A4_HOLD_FRAMES` (lines 24-27)
   - `TARGET_DELAY_FLOOR_MARGIN_FRAMES`, `TARGET_DELAY_CEILING_MARGIN_FRAMES` (lines 161-162)
   - `FULL_ONLY_PHASE_COMPENSATION_CLAMP_FRAMES` (line 155)

**Verification**:
- [ ] `python -c "from rom_lab.api.routes.automation.models import StarterResetStartRequest; print('OK')"` succeeds
- [ ] `python -c "from rom_lab.api.routes.automation.constants import DEFAULT_RNG_USE_SEED_MATCH; assert DEFAULT_RNG_USE_SEED_MATCH == True"` succeeds
- [ ] `StarterResetStartRequest(rng_seed_wait_timeout_frames=36000)` does NOT raise ValidationError

**Out of Scope**: Do NOT modify learner.py, calibration.py, controller.py, or tests in this package. Those will break with ImportError on deleted constants -- that is expected and fixed in subsequent packages.

---

### Task Package 6.2: Learner and Calibration Cleanup
<!-- ID: tp_6_2 -->

**Scope**: Delete dead strategy code from learner.py, simplify calibration.py, fix all ImportErrors from deleted constants.

**Files to Modify**:
- `src/rom_lab/api/routes/automation/learner.py`
- `src/rom_lab/api/routes/automation/calibration.py`

**Dependencies**: Task Package 6.1 must be complete first (deleted constants will cause ImportErrors).

**Specifications**:

1. In `learner.py`:
   - DELETE the entire body of `_derive_adaptive_rng_plan()` from line 657 to line 1165 (all dead strategies after the seed-match short-circuit). The seed-match path (lines 634-657) stays.
   - DELETE `_apply_execution_profile_overrides()` function (lines 699-728)
   - DELETE `_cycle_pick()` function (lines 591-595)
   - SIMPLIFY `_base_rng_plan()` (lines 467-555): remove fields for calibration_*, execution_profile, rng_pre_a4_hold_frames, rng_settle_frames_min/max from the returned dict
   - FIX all import statements that reference deleted constants -- remove those imports
   - DELETE all dead local variables computed before the seed-match short-circuit that are only used by deleted strategies (prediction_low_accuracy, execution_low_accuracy, timing_lock_ready, timing_lock_escape, phase_index, settle_phase_frames, wait_phase_frames, timing_lock_spin_steps, etc.)

2. In `calibration.py`:
   - DELETE `_segment_delta()` (lines 27-34)
   - DELETE `_update_segment_ema()` (lines 37-58)
   - DELETE `_update_calibration_segments()` (lines 61-97)
   - SIMPLIFY `_update_calibration_state()` to approximately 10 lines: record infer_status and track target_miss_streak only. Remove all drift EWMA, probes_total, segment tracking, recalibration_due logic.
   - FIX all imports referencing deleted constants

**Verification**:
- [ ] `python -c "from rom_lab.api.routes.automation.learner import _derive_adaptive_rng_plan; print('OK')"` succeeds
- [ ] `python -c "from rom_lab.api.routes.automation.calibration import _update_calibration_state; print('OK')"` succeeds
- [ ] No ImportError when importing the full automation package

**Out of Scope**: Do NOT modify controller.py or tests. Controller fixes are in 6.3.

---

### Task Package 6.3: Controller and Routes Cleanup
<!-- ID: tp_6_3 -->

**Scope**: Fix the critical calibration bug, prune dead fields from controller methods, update routes/defaults endpoint.

**Files to Modify**:
- `src/rom_lab/api/routes/automation/controller.py`
- `src/rom_lab/api/routes/automation/routes.py`

**Dependencies**: Task Packages 6.1 and 6.2 must be complete.

**Specifications**:

1. In `controller.py`:
   - FIX line 3829: The `_update_calibration_state()` call must either (a) pass `seed_match_mode=True` unconditionally since seed-match is now the only path, or (b) be simplified since calibration.py is now trivial. Match whatever the simplified calibration function signature expects.
   - PRUNE `_bot_start_fields` method: remove fields sent to Lua that no longer exist: `rng_settle_frames_min`, `rng_settle_frames_max`, `rng_pre_a4_hold_frames`. Keep: `rng_use_seed_match`, `rng_target_seed`, `rng_seed_wait_timeout_frames`, `rng_mode`, `rng_unique_seed_window`, `rng_avoid_seed_*`, `rng_expected_*`.
   - PRUNE dead timing_lock/timing_probe logic in `_apply_target_overlay_to_plan` if any exists (verify first).
   - FIX all imports referencing deleted constants or removed model fields.

2. In `routes.py`:
   - ADD to `/defaults` response dict (around line 51-72):
     ```python
     "rng_use_seed_match": DEFAULT_RNG_USE_SEED_MATCH,
     "rng_seed_wait_timeout_frames": DEFAULT_RNG_SEED_WAIT_TIMEOUT_FRAMES,
     ```
   - REMOVE dead entries from `/defaults` response: `execution_profile`, `calibration_policy`, `calibration_probe_count`, `calibration_recheck_every_attempts`, `drift_threshold_frames`, `rng_settle_frames_min`, `rng_settle_frames_max`, `rng_pre_a4_hold_frames`, `execution_max_delay_frames`.
   - REMOVE dead entries from `options` dict: `execution_profile` choices, `calibration_policy` choices.
   - ADD to `options`: `rng_mode` stays (deterministic, unique_seed_wait).
   - FIX all imports referencing deleted constants.

**Verification**:
- [ ] `python -c "from rom_lab.api.routes.automation.controller import StarterResetController; print('OK')"` succeeds
- [ ] `curl localhost:8100/api/automation/starter-reset/defaults | python -m json.tool` shows `rng_use_seed_match: true` and `rng_seed_wait_timeout_frames: 36000`
- [ ] Defaults response does NOT contain `execution_profile`, `calibration_policy`, or other dead fields

**Out of Scope**: Do NOT modify test files. Tests are cleaned in 6.4.

---

### Task Package 6.4: Dead Test Cleanup
<!-- ID: tp_6_4 -->

**Scope**: Delete all test functions that exercise dead strategies and dead model fields.

**Files to Modify**:
- `tests/test_automation_routes.py`
- `tests/test_starter_target_planner.py` (audit only -- delete dead refs if found)

**Dependencies**: Task Packages 6.1-6.3 must be complete.

**Specifications**:

1. In `test_automation_routes.py`, DELETE all test functions that:
   - Assert `plan["strategy"]` equals any of: `timing_lock_calibration`, `timing_lock_escape_jump`, `phase_cycle_probe`, `global_seed_jump`, `target_seek_jump`, `target_seek_hard_jump`, `exact_lock`, `baseline` (when testing delay-based baseline)
   - Test `execution_profile` field behavior (fast_probe, exact_lock profiles)
   - Test `calibration_policy` field behavior
   - Reference deleted constants (TIMING_LOCK_*, CALIBRATION_*, etc.)

2. In `test_starter_target_planner.py`, AUDIT for references to deleted model fields or constants. Delete any dead test logic found.

3. Do NOT delete tests for:
   - Seed-match strategy behavior
   - Filter evaluation
   - History/observability
   - PID learning state
   - Bot start/stop flow
   - Any test in `tests/test_seed_match*.py`

**Verification**:
- [ ] `pytest tests/test_automation_routes.py -v --tb=short` passes (all remaining tests green)
- [ ] `pytest tests/test_starter_target_planner.py -v --tb=short` passes
- [ ] `pytest tests/ -v --tb=short -x` passes (full suite)

**Out of Scope**: Do NOT modify application code. Only test files.

---

### Phase 6 Milestone Table
<!-- ID: phase_6_milestones -->

| Milestone | Task Package | Status | Evidence |
|-----------|-------------|--------|----------|
| Dead model fields deleted | 6.1 | Pending | StarterResetStartRequest imports clean |
| Validator bug fixed | 6.1 | Pending | le=216000 accepts 36000 |
| Defaults corrected | 6.1 | Pending | DEFAULT_RNG_USE_SEED_MATCH=True |
| Dead constants deleted | 6.1 | Pending | ~50 constants removed |
| Dead strategies deleted | 6.2 | Pending | learner.py ~500 lines removed |
| Calibration simplified | 6.2 | Pending | calibration.py reduced to ~10 lines |
| Controller bug fixed | 6.3 | Pending | seed_match_mode passed correctly |
| Defaults endpoint updated | 6.3 | Pending | /defaults returns seed-match fields |
| Dead tests deleted | 6.4 | Pending | ~30 test functions removed |
| Full test suite passes | 6.4 | Pending | pytest green |

---

## Phase 7 -- Core UI Overhaul
<!-- ID: phase_7 -->

**Goal**: Remove dead controls from the automation panel, add collapsible Advanced section with surfaced settings, update the payload builder, add profile controls UI.

**Acceptance**: Panel main view shows only filters + save slot. Advanced section has all power-user settings. _buildStartPayload() sends rng_use_seed_match: true. All settings loaded from /defaults.

### Task Package 7.1: Remove Dead Controls and Add Advanced Section (HTML + CSS)
<!-- ID: tp_7_1 -->

**Scope**: Modify the HTML template to remove 7 dead control blocks and add the Advanced collapsible section. Add CSS for new components.

**Files to Modify**:
- `.council/web/pages/bizhawk.html.j2` (lines 305-504 automation panel)
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. In `bizhawk.html.j2`, DELETE the 7 `<label class="automation__field">` blocks for:
   - `automationRngMode` (RNG Mode select)
   - `automationExecutionProfile` (Execution Profile select)
   - `automationUniqueSeedWindow` (Unique Seed Window input)
   - `automationExecutionMaxDelayFrames` (Execution Max Delay input)
   - `automationSettleMinFrames` (Settle Min input)
   - `automationSettleMaxFrames` (Settle Max input)
   - `automationPreA4HoldFrames` (Pre-Final-A Hold input)

2. In `bizhawk.html.j2`, ADD after the IV filter grid and BEFORE the action buttons:
   ```html
   <!-- Advanced toggle -->
   <div class="automation__advanced-toggle" id="automationAdvancedToggle">
     <svg width="8" height="8" viewBox="0 0 8 8" fill="currentColor"><path d="M2 1l4 3-4 3z"/></svg>
     <span>Advanced</span>
   </div>
   <div class="automation__advanced-options" id="automationAdvancedOptions">
     <p class="automation__advanced-info">Seed-match monitors gRngValue every frame. When the target seed appears, A4 fires automatically. Offset calibrates from verification outcomes.</p>
     <div class="automation__grid automation__grid--advanced">
       <label class="automation__field">
         <span class="automation__label">Seed Wait Timeout (frames)</span>
         <input class="automation__input automation__input--mono" id="automationSeedWaitTimeout"
                type="number" min="60" max="216000" step="3600" placeholder="36000">
       </label>
       <label class="automation__field">
         <span class="automation__label">RNG Mode</span>
         <select class="automation__select" id="automationRngMode">
           <option value="deterministic">Deterministic</option>
           <option value="unique_seed_wait">Unique Seed Wait</option>
         </select>
       </label>
       <label class="automation__field">
         <span class="automation__label">Unique Seed Window (frames)</span>
         <input class="automation__input automation__input--mono" id="automationUniqueSeedWindow"
                type="number" min="0" max="7200" step="1" placeholder="180">
       </label>
       <label class="automation__field">
         <span class="automation__label">Candidate Timeout (sec)</span>
         <input class="automation__input automation__input--mono" id="automationCandidateTimeout"
                type="number" min="0.25" max="20" step="0.25" placeholder="6.0">
       </label>
       <label class="automation__field">
         <span class="automation__label">Pre-A1 Spin Steps</span>
         <input class="automation__input automation__input--mono" id="automationPreA1SpinSteps"
                type="number" min="0" max="240" step="1" placeholder="0">
       </label>
       <label class="automation__field">
         <span class="automation__label">Target Horizon (frames)</span>
         <input class="automation__input automation__input--mono" id="automationTargetHorizon"
                type="number" min="30" max="20000" step="100" placeholder="1800">
       </label>
       <label class="automation__field">
         <span class="automation__label">Target Candidate Count</span>
         <input class="automation__input automation__input--mono" id="automationTargetCandidateCount"
                type="number" min="1" max="256" step="1" placeholder="64">
       </label>
     </div>
   </div>
   ```

3. In `bizhawk.html.j2`, ADD profile controls row before Start/Stop buttons:
   ```html
   <div class="automation__profiles" id="automationProfiles">
     <select class="automation__select automation__select--profile" id="automationProfileSelect">
       <option value="">-- Profile --</option>
     </select>
     <button class="automation__btn automation__btn--sm" id="automationProfileLoadBtn" title="Load">Load</button>
     <button class="automation__btn automation__btn--sm" id="automationProfileSaveBtn" title="Save">Save</button>
     <button class="automation__btn automation__btn--sm automation__btn--danger-sm" id="automationProfileDeleteBtn" title="Delete">Del</button>
   </div>
   ```

4. In `bizhawk.css`, ADD:
   - `.automation__advanced-toggle` styles (flex, align-items, gap, cursor, color, font, letter-spacing, user-select)
   - `.automation__advanced-toggle svg` transition
   - `.automation__advanced-toggle.open svg` transform rotate(90deg)
   - `.automation__advanced-options` display:none
   - `.automation__advanced-options.open` display:block
   - `.automation__advanced-info` paragraph style (dim color, small font, margin)
   - `.automation__grid--advanced` layout variant
   - `.automation__profiles` row style
   - `.automation__btn--sm` compact button style
   - `.automation__select--profile` compact select style

**Verification**:
- [ ] Page loads without JS errors
- [ ] Main view shows only: Save Slot, Shiny, Nature, Gender, IV filters
- [ ] "Advanced" toggle expands to show 7 controls
- [ ] Profile controls row visible between Advanced and Start/Stop

**Out of Scope**: Do NOT modify automation.js. JS changes in 7.2.

---

### Task Package 7.2: JavaScript Module Overhaul
<!-- ID: tp_7_2 -->

**Scope**: Update automation.js to match the new HTML structure: remove dead variable references, add new DOM bindings, update _loadDefaults, update _buildStartPayload, add Advanced section toggle logic.

**Files to Modify**:
- `.council/web/static/js/automation.js`

**Dependencies**: Task Package 7.1 must be complete (HTML structure changes).

**Specifications**:

1. REMOVE module-scope variable declarations for dead controls:
   - `_executionProfile`, `_executionMaxDelayFrames`, `_settleMinFrames`, `_settleMaxFrames`, `_preA4HoldFrames`
   Note: `_rngMode` and `_uniqueSeedWindow` STAY because they moved to Advanced section (same IDs).

2. ADD new module-scope variables:
   - `_seedWaitTimeout`, `_candidateTimeout`, `_preA1SpinSteps`, `_targetHorizon`, `_targetCandidateCount`
   - `_advancedToggle`, `_advancedOptions`
   - `_profileSelect`, `_profileLoadBtn`, `_profileSaveBtn`, `_profileDeleteBtn`

3. UPDATE `init()`:
   - Remove getElementById for dead controls
   - Add getElementById for new controls
   - Add Advanced toggle click handler: `_advancedToggle.addEventListener('click', () => { _advancedToggle.classList.toggle('open'); _advancedOptions.classList.toggle('open'); })`

4. UPDATE `_loadDefaults(data)`:
   - Remove lines reading dead fields (execution_profile, settle_min/max, pre_a4_hold, execution_max_delay)
   - ADD: read `rng_use_seed_match` (informational -- always true)
   - ADD: read `rng_seed_wait_timeout_frames` -> `_seedWaitTimeout.value`
   - ADD: read `candidate_timeout_seconds` -> `_candidateTimeout.value`
   - ADD: read `rng_pre_a1_spin_steps` -> `_preA1SpinSteps.value`
   - ADD: read `target_horizon_frames` -> `_targetHorizon.value`
   - ADD: read `target_candidate_count` -> `_targetCandidateCount.value`

5. UPDATE `_buildStartPayload()`:
   - REMOVE: `execution_profile`, `execution_max_delay_frames`, `rng_settle_frames_min`, `rng_settle_frames_max`, `rng_pre_a4_hold_frames`
   - ADD: `rng_use_seed_match: true` (hardcoded -- always on)
   - ADD: `rng_seed_wait_timeout_frames: _parseOptionalInteger(_seedWaitTimeout) || 36000`
   - ADD: `candidate_timeout_seconds: parseFloat(_candidateTimeout.value) || 6.0`
   - ADD: `rng_pre_a1_spin_steps: _parseOptionalInteger(_preA1SpinSteps) || 0`
   - ADD: `target_horizon_frames: _parseOptionalInteger(_targetHorizon) || 1800`
   - ADD: `target_candidate_count: _parseOptionalInteger(_targetCandidateCount) || 64`
   - KEEP: `rng_mode`, `rng_unique_seed_window` (now read from Advanced section inputs)

**Verification**:
- [ ] No JS console errors on page load
- [ ] "Defaults" button populates all controls including Advanced section
- [ ] Start button sends correct payload with `rng_use_seed_match: true` and all Advanced fields
- [ ] Payload does NOT contain deleted fields (execution_profile, calibration_*, settle_*, pre_a4_hold)

**Out of Scope**: Profile save/load logic (Phase 9). History rendering (Phase 8). Seed diagnostics rendering (Phase 8).

---

### Task Package 7.3: Integration Test for Phase 7
<!-- ID: tp_7_3 -->

**Scope**: Verify the full round-trip: defaults endpoint returns correct values, payload builder sends correct fields, API accepts the payload.

**Files to Modify**:
- `tests/test_automation_routes.py` (add new tests if needed)

**Dependencies**: Task Packages 7.1 and 7.2 complete.

**Specifications**:

1. Verify GET /defaults returns `rng_use_seed_match: true`, `rng_seed_wait_timeout_frames: 36000`, and does NOT return dead fields.
2. Verify POST /start accepts payload with `rng_use_seed_match: true`, `rng_seed_wait_timeout_frames: 36000`.
3. Verify POST /start REJECTS payload with deleted fields (execution_profile, calibration_policy, etc.) -- should get 422 or ignore.
4. Run full test suite: `pytest tests/ -v --tb=short -x`

**Verification**:
- [ ] All new tests pass
- [ ] Full test suite passes
- [ ] No regressions from Phase 6 or 7

**Out of Scope**: Do NOT add display component tests -- those are Phase 8.

---

### Phase 7 Milestone Table
<!-- ID: phase_7_milestones -->

| Milestone | Task Package | Status | Evidence |
|-----------|-------------|--------|----------|
| Dead controls removed from HTML | 7.1 | Pending | 7 label blocks deleted |
| Advanced section added | 7.1 | Pending | Toggle + 7 controls |
| Profile controls added | 7.1 | Pending | Select + Load/Save/Del |
| CSS for new components | 7.1 | Pending | Advanced + profile styles |
| JS dead refs removed | 7.2 | Pending | No console errors |
| JS payload updated | 7.2 | Pending | rng_use_seed_match: true sent |
| JS defaults loader updated | 7.2 | Pending | All advanced fields populated |
| Integration test passes | 7.3 | Pending | Full suite green |

---

## Phase 8 -- Data Display Components
<!-- ID: phase_8 -->

**Goal**: Add rich data display components: seed-match diagnostics, history table IVs + Result columns, Pokemon detail card with IV bars, learning data tables.

**Acceptance**: All new display components render correctly from live polling data. History table shows IVs and seed-match results. Pokemon card shows IV stat bars with nature effects. Learning data shows structured tables instead of codeblock.

### Task Package 8.1: Seed-Match Diagnostics Block
<!-- ID: tp_8_1 -->

**Scope**: Add seed-match diagnostics to the status section, showing target seed, matched seed, wait frames, result, and offset.

**Files to Modify**:
- `.council/web/pages/bizhawk.html.j2`
- `.council/web/static/js/automation.js`
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. In `bizhawk.html.j2`, ADD after the metrics bar (State/Attempts/Matches/Elapsed) and BEFORE the meta line:
   - Section sublabel "Seed-Match"
   - 5 metric divs: Target (mono hex), Matched (mono hex), Wait (frames), Result (colored pill), Offset (integer)
   - Use IDs: `automationSeedTarget`, `automationSeedMatched`, `automationSeedWaitFrames`, `automationSeedResult`, `automationSeedOffset`

2. In `automation.js`, ADD function `_renderSeedDiagnostics(status)`:
   - Read `status.active_rng_plan?.rng_target_seed` -> hex format `0xHHHHHHHH`
   - Read `status.last_candidate?.rng_seed_at_match` -> hex format
   - Read `status.last_candidate?.rng_seed_wait_frames` -> integer + " frames"
   - Read `status.last_candidate?.candidate?.seed_match_verification_outcome` -> result pill with semantic class
   - Read `status.calibration_state?.press_to_generation_offset` -> integer
   - Call from `_renderStatus()`
   - Map result values to CSS classes: exact_hit -> --good, seed_hit_pid_miss -> --warn, timeout -> --error, total_miss -> --error

3. In `bizhawk.css`, ADD:
   - `.automation__seed-diagnostics` container (flex, gap, matching metrics bar style)
   - `.automation__metric-v--good` (color: #4ade80)
   - `.automation__metric-v--warn` (color: #facc15)
   - `.automation__metric-v--error` (color: #f87171)
   - `.automation__metric-v--mono` (font-family: monospace, font-size: 0.85em)
   - `.automation__section-sublabel` (small, dim, uppercase, tracking)

**Verification**:
- [ ] Diagnostics block renders with placeholder "--" values when no run active
- [ ] During active run, target seed, matched seed, wait, result, offset update on each poll
- [ ] Result pill colors: green for exact_hit, yellow for seed_hit_pid_miss, red for timeout/miss

**Out of Scope**: Do NOT modify history table or candidate card.

---

### Task Package 8.2: History Table IVs and Result Columns
<!-- ID: tp_8_2 -->

**Scope**: Add IVs column and Result column to history table. Remove Ability column.

**Files to Modify**:
- `.council/web/pages/bizhawk.html.j2`
- `.council/web/static/js/automation.js`
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. In `bizhawk.html.j2`, UPDATE history table `<thead>`:
   - Remove `<th>Ability</th>`
   - Add `<th>IVs</th>` after Gender
   - Add `<th>Result</th>` after Seed
   - Update total columns from 11 to 12
   - Update any `colspan="11"` to `colspan="12"` in empty state rows

2. In `automation.js`, UPDATE `_renderHistory()`:
   - Remove Ability cell rendering
   - ADD IVs cell: format `row.ivs` as `HP/Atk/Def/SpA/SpD/Spe` (e.g., `31/25/18/30/28/20`). Show `--` when null.
   - ADD Result cell: read `row.candidate?.seed_match_verification_outcome`. Render as colored pill:
     - `exact_hit` -> `<span class="automation__history-pill automation__history-pill--hit">HIT</span>`
     - `seed_hit_pid_miss` -> `<span class="automation__history-pill automation__history-pill--pid-miss">PID?</span>`
     - `timeout` -> `<span class="automation__history-pill automation__history-pill--timeout">TIMEOUT</span>`
     - `total_miss` -> `<span class="automation__history-pill automation__history-pill--miss">MISS</span>`
     - null -> `--`

3. UPDATE `_buildHistoryCopyText()` to match new column order (remove Ability, add IVs, add Result).

4. In `bizhawk.css`, ADD:
   - `.automation__history-pill` base (display: inline-block, padding, border-radius, font-size, font-weight)
   - `.automation__history-pill--hit` (background: rgba(74,222,128,0.15), color: #4ade80)
   - `.automation__history-pill--pid-miss` (background: rgba(250,204,21,0.15), color: #facc15)
   - `.automation__history-pill--timeout` (background: rgba(248,113,113,0.15), color: #f87171)
   - `.automation__history-pill--miss` (background: rgba(248,113,113,0.15), color: #f87171)

**Verification**:
- [ ] History table renders with 12 columns
- [ ] IVs column shows `31/25/18/30/28/20` format for rows with IV data
- [ ] IVs column shows `--` for rows without IV data
- [ ] Result column shows colored pills (HIT green, PID? yellow, TIMEOUT/MISS red)
- [ ] Copy History button produces correct TSV with new columns

**Out of Scope**: Do NOT modify seed diagnostics or Pokemon card.

---

### Task Package 8.3: Pokemon Detail Card
<!-- ID: tp_8_3 -->

**Scope**: Replace the simple candidate card with a premium Pokemon detail card featuring IV stat bars, nature effects, and enhanced layout.

**Files to Modify**:
- `.council/web/pages/bizhawk.html.j2`
- `.council/web/static/js/automation.js`
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. In `bizhawk.html.j2`, REPLACE the `automationCandidate` section content with a new Pokemon card structure:
   - Container: `.automation__pokemon-card`
   - Header: Species name + level + shiny badge + match pill
   - IV bars section: 6 horizontal bars (HP/Atk/Def/SpA/SpD/Spe), each bar scaled 0-31, with numeric value label
   - Nature effect indicators on the bar labels: green (+) for boosted stat, red (-) for reduced stat
   - Details grid: Nature, Gender, Ability, PID (hex), Seeds (start -> candidate hex)
   - Moves list with compact layout

2. In `automation.js`, ADD function `_renderPokemonCard(lastCandidate)`:
   - Extract IVs from `lastCandidate.candidate.ivs` (object with hp, attack, defense, sp_attack, sp_defense, speed)
   - Determine nature effects: map nature name to +10%/-10% stat using standard Pokemon nature table (hardcode the 25-nature lookup table in JS -- small, static data)
   - Render IV bars: `<div class="automation__iv-bar" style="--iv-val: ${iv}; --iv-pct: ${(iv/31)*100}%">`
   - Color-code bars: 0-10 red tier, 11-20 yellow tier, 21-30 green tier, 31 gold tier
   - Call from `_renderStatus()` when `status.last_candidate` exists

3. In `bizhawk.css`, ADD:
   - `.automation__pokemon-card` container (background, border, border-radius, padding)
   - `.automation__pokemon-card__header` (flex, align-items, gap)
   - `.automation__iv-bars` container (display: grid, row-gap)
   - `.automation__iv-bar` (height, background track, colored fill using var(--iv-pct))
   - `.automation__iv-bar--red/--yellow/--green/--gold` tier colors
   - `.automation__iv-label` (name + value + nature indicator)
   - `.automation__nature-boost` (color: #4ade80) and `.automation__nature-reduce` (color: #f87171)
   - `.automation__pokemon-details` grid (2-column layout for stats)
   - `.automation__pokemon-moves` (flex-wrap, gap, compact pills)

**Verification**:
- [ ] Pokemon card renders when a candidate exists
- [ ] IV bars display 6 stats with correct proportional widths (0-31 scale)
- [ ] Nature effects show +/- indicators on correct stats
- [ ] PID and Seeds display in hex format
- [ ] Card shows "--" placeholder when no candidate

**Out of Scope**: Species sprite/art (requires asset pipeline -- defer to future enhancement). Use species name + ID text for now.

---

### Task Package 8.4: Learning Data Tables
<!-- ID: tp_8_4 -->

**Scope**: Replace the raw observability codeblock with structured tables and metrics.

**Files to Modify**:
- `.council/web/pages/bizhawk.html.j2`
- `.council/web/static/js/automation.js`
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. In `bizhawk.html.j2`, ADD new learning data container (replaces or supplements `automationObservability`):
   - Distribution mini-tables: Nature (top 5), Gender, Ability, Seed Start frequency
   - Targeting metrics row: Target level, last score, avg score
   - Strategy info: Current strategy, phase, dup streak
   - Each section is a compact card with label + data

2. In `automation.js`, ADD function `_renderLearningData(status)`:
   - Parse `status.observability` object (already structured with fields like candidates_total, shiny_count, nature_hist, gender_hist, etc.)
   - Render distribution data as mini-tables (2-column: name | count)
   - Render targeting metrics as metric cards
   - Replace or supplement the existing `_pre.textContent = ...` pattern with DOM-built tables
   - Call from `_renderStatus()`

3. In `bizhawk.css`, ADD:
   - `.automation__learning` container (grid or flex layout)
   - `.automation__learning-card` (background, border, padding, compact)
   - `.automation__learning-table` (compact table, no borders, small font)
   - `.automation__learning-metric` (label + value pair)

**Verification**:
- [ ] Learning data section shows structured tables instead of raw text
- [ ] Distribution tables show Nature/Gender/Ability top entries
- [ ] Targeting metrics display correctly
- [ ] Falls back to "--" or empty state when no data

**Out of Scope**: Do NOT remove the Copy Learning button (it still copies the raw text format).

---

### Phase 8 Milestone Table
<!-- ID: phase_8_milestones -->

| Milestone | Task Package | Status | Evidence |
|-----------|-------------|--------|----------|
| Seed diagnostics block | 8.1 | Pending | 5 metrics render from status |
| History IVs column | 8.2 | Pending | IV spread format renders |
| History Result column | 8.2 | Pending | Colored pills render |
| Pokemon detail card | 8.3 | Pending | IV bars + nature effects |
| Learning data tables | 8.4 | Pending | Structured tables replace codeblock |

---

## Phase 9 -- Profiles and Polish
<!-- ID: phase_9 -->

**Goal**: Add setting profiles (save/load), enhance copy snapshot, apply premium CSS polish across all automation panel components.

**Acceptance**: Users can save/load named profiles. Copy snapshot includes IVs and seed-match data. Panel looks professionally polished.

### Task Package 9.1: Setting Profiles
<!-- ID: tp_9_1 -->

**Scope**: Implement save/load/delete of automation setting profiles using localStorage.

**Files to Modify**:
- `.council/web/static/js/automation.js`

**Specifications**:

1. ADD storage key constant: `const PROFILES_KEY = 'romlab_automation_profiles';`

2. ADD function `_saveProfile()`:
   - Prompt for profile name
   - Read all form control values (main + advanced) into a JSON object
   - Save to localStorage under `PROFILES_KEY`
   - Refresh profile dropdown

3. ADD function `_loadProfile(name)`:
   - Read profile from localStorage
   - Populate all form controls from saved values
   - If profile contains non-default advanced values, auto-open Advanced section

4. ADD function `_deleteProfile(name)`:
   - Confirm deletion
   - Remove from localStorage
   - Refresh profile dropdown

5. ADD function `_refreshProfiles()`:
   - Read all profiles from localStorage
   - Populate `_profileSelect` dropdown with profile names

6. Wire up event listeners in `init()`:
   - `_profileSaveBtn.addEventListener('click', _saveProfile)`
   - `_profileLoadBtn.addEventListener('click', () => _loadProfile(_profileSelect.value))`
   - `_profileDeleteBtn.addEventListener('click', () => _deleteProfile(_profileSelect.value))`
   - Call `_refreshProfiles()` on init

**Verification**:
- [ ] Save button prompts for name and persists profile
- [ ] Load button populates all controls from profile
- [ ] Delete button removes profile and updates dropdown
- [ ] Profiles persist across page reloads (localStorage)
- [ ] Advanced section auto-opens when loading profile with non-default advanced values

**Out of Scope**: Do NOT implement server-side profile storage.

---

### Task Package 9.2: Enhanced Copy Snapshot
<!-- ID: tp_9_2 -->

**Scope**: Rewrite _buildSnapshotCopyText() to include IVs, seed-match diagnostics, and improved formatting.

**Files to Modify**:
- `.council/web/static/js/automation.js`

**Specifications**:

1. REWRITE `_buildSnapshotCopyText()` to include:
   - **Section 1 -- Run Overview**: state, run_id, attempts/matches/elapsed, filters (expanded), save_slot
   - **Section 2 -- Seed-Match Status**: target seed, matched seed, wait frames, result, offset, mode
   - **Section 3 -- Last Candidate**: name/species/level/nature/gender/ability/shiny, PID, seeds
   - **Section 4 -- IVs**: Full stat spread with nature effects annotated (e.g., `Atk: 31 (+10% Adamant)`)
   - **Section 5 -- Prediction Health**: hit rates, error metrics
   - **Section 6 -- Active Plan**: strategy, target, delay config
   - **Section 7 -- Distribution Summary**: top natures, genders, seeds
   - **Section 8 -- Recent History**: last 12 rows with IVs and Result

2. Use consistent formatting: aligned colons, hex values prefixed with 0x, section dividers.

**Verification**:
- [ ] Copy Snapshot button produces enriched markdown
- [ ] IVs section present with nature effect annotations
- [ ] Seed-match diagnostics section present
- [ ] History section includes IVs and Result columns

**Out of Scope**: Do NOT change Copy Learning or Copy Debug buttons.

---

### Task Package 9.3: Premium CSS Polish
<!-- ID: tp_9_3 -->

**Scope**: Apply premium visual polish across all automation panel components. This uses the frontend-design skill.

**Files to Modify**:
- `.council/web/static/css/bizhawk.css`

**Specifications**:

1. **Typography**: Refine font sizes, weights, and letter-spacing for all automation elements. Ensure mono fonts for all hex/numeric values.

2. **Spacing**: Audit and refine padding, margins, and gaps throughout the automation panel for visual breathing room.

3. **Color system**: Define CSS custom properties for automation panel colors:
   - `--automation-bg` (card/section backgrounds)
   - `--automation-border` (borders, dividers)
   - `--automation-text-primary` / `--automation-text-dim` / `--automation-text-accent`
   - `--automation-success` / `--automation-warn` / `--automation-error`

4. **Card treatments**: Subtle background differentiation for different card types (diagnostics, candidate, learning). Consistent border-radius and border-color.

5. **Transitions**: Smooth transitions on toggle open/close (Advanced section), hover states on buttons and table rows, active states on controls.

6. **Focus states**: Visible focus rings on all interactive elements (accessibility).

7. **Responsive**: Ensure automation panel works at narrow widths (Advanced section stacks, history table horizontal scrolls).

**Verification**:
- [ ] All automation panel components use CSS custom properties
- [ ] Consistent visual treatment across all cards and sections
- [ ] Smooth transitions on toggles and hovers
- [ ] Panel works at 768px and 480px widths
- [ ] Focus states visible on all interactive elements

**Out of Scope**: Do NOT change functionality. CSS only.

---

### Phase 9 Milestone Table
<!-- ID: phase_9_milestones -->

| Milestone | Task Package | Status | Evidence |
|-----------|-------------|--------|----------|
| Profiles save/load/delete | 9.1 | Pending | localStorage round-trip |
| Enhanced copy snapshot | 9.2 | Pending | IVs + seed-match in clipboard |
| Premium CSS polish | 9.3 | Pending | Custom properties + transitions |
