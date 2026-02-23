---
id: automation_rng_modular_2026_02_21-research-architecture-patterns
title: "\U0001F52C Research Architecture Patterns \u2014 automation_rng_modular_2026_02_21"
doc_type: RESEARCH_ARCHITECTURE_PATTERNS
doc_name: RESEARCH_ARCHITECTURE_PATTERNS
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 05:26:48 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Architecture Patterns — automation_rng_modular_2026_02_21
**Author:** synthesis-lead
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-21 05:19:22 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Vision:** Transform the current starter-reset monolith into a modular, plugin-anchored automation framework where the RNG engine, timing engine, strategy layer, emulator interface, and UI are independently composable and testable.

**Current State:** A single 6,857-line `src/rom_lab/api/routes/automation.py` conflates ~170 constants, SQLite history storage, Pydantic models, and a `StarterResetController` class that entangles: RNG planning, calibration/timing, emulator IPC orchestration, PID learning, target planning, candidate filtering, and state machine management. The Lua-side `lua/common/bot/runtime.lua` is a frame-tick state machine with stages hardcoded for starter-reset.

**Target State:** A layered module system:
1. `AutomationStrategy` ABC — per-task lifecycle contract (starter reset, wild, breeding)
2. `RNGEngine` — pure LCRNG prediction, method1 generation, seed search, IV calculation
3. `TimingModel` — calibration, drift estimation, delay prediction (per-strategy)
4. `EmulatorInterface` — wraps Lua IPC for bot commands, state reads
5. `HistoryStore` ABC — pluggable candidate persistence (SQLite now, extensible)
6. `GamePlugin.get_automations()` — registers available strategies per game
7. **Frontend:** strategy-aware panel with dynamic config fields per automation type

**Key Constraints:**
- Starter reset must continue working unchanged (no behavior regressions)
- Frame-precise timing preserved — no Python-side timing disrupts the Lua tick contract
- All tests remain 100% emulator-free for CI (existing monkeypatch pattern preserved)
- Automation capabilities are plugin-registered, not global/singleton
- Frontend keeps the polling pattern (800ms/2000ms) but generalizes API paths

**Key Takeaways:**
- The architecture splits into 5 clean modules: RNGEngine, TimingModel, TargetPlanner, AutomationController, HistoryStore
- Plugin system is the natural anchor for automation capability registration
- Lua runtime.lua needs a data-driven stage config to support new automation types without new files
- Frontend needs a strategy-selector dropdown + dynamic field panels per strategy type
- Test infrastructure should use pytest fixtures for controller state and async IO mocking
<!-- ID: research_scope -->
## Research Scope

**Research Lead:** synthesis-lead
**Investigation Window:** 2026-02-21
**Focus Areas:**
- [x] Frontend analysis: automation.js (1,573 lines), bizhawk.html.j2, bizhawk.css
- [x] Plugin architecture: GamePlugin ABC, PokemonFireRedPlugin, plugin capability model
- [x] Lua IPC architecture: ipc.lua, bot/runtime.lua state machine
- [x] Architecture patterns: PokemonAutomation project, PokeFinder design, clean arch patterns
- [x] Auto-analyst findings: automation.py module boundaries, StarterResetController internals
- [x] Decomp-specialist findings: RNG timing chain, seed source, givemon call chain
- [x] Test-architect findings: existing test patterns, CI requirements, async testing

**Dependencies & Constraints:**
- Must preserve starter-reset behavior (no regressions — existing 3,756-line test suite must pass)
- Lua side uses file-based or socket IPC — no breaking changes to the frame protocol
- FastAPI TestClient + monkeypatch is the established CI test pattern
- GamePlugin ABC is the plugin registration boundary
- Python typing standards: lowercase generics, `X | None`, `-> None`

**FRONTEND ANALYSIS FINDINGS:**
- automation.js: single IIFE (~1,573 lines), zero abstraction, starter-reset specific
- All DOM IDs are starter-specific: `automationSaveSlot`, `automationShinyFilter`, etc.
- API base hardcoded: `/api/romlab/api/automation/starter-reset`
- Start payload: `mode='starter_exact_v1'` hardcoded in `_buildStartPayload()`
- Rich status rendering: target board (RNG prediction), candidate history, learning metrics, debug events
- Polling: 800ms while running, 2000ms idle, adaptive based on `status.running`
- Pattern to generalize: strategy-selector dropdown → dynamic config panel + dynamic API base

**PLUGIN ARCHITECTURE FINDINGS:**
- `GamePlugin` ABC in `src/rom_lab/plugins/base.py` has clean capability registration pattern
- `get_automations()` method does not yet exist — needs to be added
- `PokemonFireRedPlugin.get_observation_extractors()` shows the right capability registry pattern
- `rng_oracle.py` is already pure logic (no side effects) — ideal module boundary
- `starter_target_planner.py` is also pure logic — natural `TargetPlanner` module

**LUA ARCHITECTURE FINDINGS:**
- `lua/common/bot/runtime.lua`: state machine (idle → A1→A2→A3→A4→candidate), starter-specific stages
- Frame-event tracking: `frame_at_a1_press` through `frame_at_a4_press`, RNG seed tracking
- IPC protocol: transport-agnostic (file or socket), `bot` field on start command for bot_type
- Runtime is configurable via JSON config (a2_max_presses, a3_timeout, etc.) — stage config could extend this
- For new automation types: either new Lua files per strategy, OR stage-config extension

**DECOMP-SPECIALIST FINDINGS (from log entries):**
- Starter chain: Player touches Pokéball → ConfirmStarterChoice → YES → ChoseStarter → `givemon` → CreateBoxMon → 4 RNG calls (2 for PID, 2 for IVs)
- RNG seed source: `SeedRngAndSetTrainerId` reads REG_TM1CNT_L (Timer 1 counter) — title screen or naming screen
- gRng address: 0x03005000 (already tracked in socket_reader.lua `read_rng_state()`)
- vblank_counter2 IS the frame counter (increments every VBlank)
- MISSING in current Lua: gRng2Value address and Timer1 counter for seed verification
<!-- ID: findings -->
## Findings

### Finding 1: Module Split for StarterResetController (Confidence: High)

The existing `StarterResetController` (~6,000 lines) can be cleanly split into 5 modules that follow single-responsibility principle:

| New Module | Location | Responsibility | Extracted From |
|---|---|---|---|
| `rng_engine.py` | `plugins/pokemon_fire_red/` | LCRNG advance/reverse, Method1 generation, IV decode | Already in `rng_oracle.py` (pure) |
| `target_planner.py` | `plugins/pokemon_fire_red/` | Seed window search, candidate scoring, delay planning | Already in `starter_target_planner.py` (pure) |
| `timing_model.py` | `plugins/pokemon_fire_red/` | Calibration state, drift estimation, delay prediction, segment timing | Extracted from `StarterResetController` |
| `pid_learner.py` | `plugins/pokemon_fire_red/` | PID frequency tracking, dominant seed detection, strategy selection | Extracted from `StarterResetController` |
| `automation_controller.py` | `plugins/pokemon_fire_red/` | State machine lifecycle, emulator IPC, run loop | Remaining `StarterResetController` |

**10 clean module boundaries** identified by auto-analyst (no circular dependencies): `constants.py`, `models.py`, `history_store.py`, `state_factories.py`, `dialogue_detection.py`, `filter_engine.py`, `learner.py`, `calibration.py`, `target_overlay.py`, `controller.py` + `routes.py`.

**Critical note from auto-analyst:** `_apply_target_overlay_to_plan` (~1,551 lines) must be extracted as a pure function from `StarterResetController` — this is the highest-risk extraction. Two module-level singletons (`_history_store`, `_controller`) are the primary coupling points; resolved via `init_automation()`.

**Evidence:** `rng_oracle.py` already has `next_seed`, `prev_seed`, `advance`, `method1_generate`, `search_static_window` as pure functions. `starter_target_planner.py` has `plan_starter_targets`, `nature_name`, `resolve_gender_from_pid` as pure functions. The constants block (~170 constants) belongs distributed to each module.

### Finding 2: AutomationStrategy ABC Pattern (Confidence: High)

Create `src/rom_lab/automation/base.py` with:

```python
class AutomationStrategy(ABC):
    @property
    @abstractmethod
    def slug(self) -> str: ...  # e.g. "starter_reset"
    
    @property
    @abstractmethod
    def name(self) -> str: ...  # e.g. "Starter Reset"
    
    @abstractmethod
    def get_default_config(self) -> dict[str, Any]: ...
    
    @abstractmethod
    async def start(self, config: dict[str, Any]) -> dict[str, Any]: ...
    
    @abstractmethod
    async def stop(self) -> dict[str, Any]: ...
    
    @abstractmethod
    async def get_status(self) -> dict[str, Any]: ...
    
    @abstractmethod
    async def get_history(self, page: int, page_size: int) -> dict[str, Any]: ...
```

**GamePlugin integration:**
```python
class GamePlugin(ABC):
    def get_automations(self) -> dict[str, AutomationStrategy]:
        """Return available automation strategies for this game. Default: empty."""
        return {}
```

**Evidence:** `get_observation_extractors()` in `base.py` already uses this exact pattern for registering per-plugin capabilities. PokemonAutomation project uses a similar task/operation registry pattern.

### Finding 3: Generic API Router Pattern (Confidence: High)

Replace the hardcoded `/api/automation/starter-reset` router with a dynamic dispatch router:

```
GET  /api/automation/strategies               → list available strategies
GET  /api/automation/{strategy_slug}/defaults
POST /api/automation/{strategy_slug}/start
POST /api/automation/{strategy_slug}/stop
GET  /api/automation/{strategy_slug}/status
GET  /api/automation/{strategy_slug}/history
```

The router resolves `strategy_slug` via `active_plugin.get_automations()[strategy_slug]`.

**Evidence:** The frontend's `API_BASE = '/api/romlab/api/automation/starter-reset'` is the only coupling point between JS and Python. Generalizing this path string unlocks multi-strategy support with no other frontend changes needed for API calls.

### Finding 4: Frontend Strategy Panel Pattern (Confidence: High)

The HTML panel needs a strategy-selector before the config grid:
1. Add `<select id="automationStrategySelect">` populated via `GET /api/automation/strategies`
2. Hide/show config field groups based on selected strategy using CSS classes
3. Keep the status section (target board, candidate history, learning metrics) as shared — already generic enough
4. Rename starter-specific DOM IDs to strategy-namespaced: `automationStarterSaveSlot`, `automationStarterShinyFilter`, etc.
5. `_buildStartPayload()` dispatches to strategy-specific builders: `_buildStarterPayload()`, `_buildWildPayload()`, etc.

**Evidence:** The status rendering in automation.js (target board, observability, debug) uses `status.*` fields that are generic enough to remain shared. Only the config input section is strategy-specific.

### Finding 5: Lua Runtime Generalization (Confidence: Medium)

Two options for supporting new automation types in Lua:
- **Option A (recommended):** New `lua/plugins/pokemon_fire_red/bots/` directory with per-strategy Lua files. Each file implements its own stage state machine. `socket_reader.lua` dispatches bot commands to the right file based on `bot_type` field.
- **Option B:** Extend `runtime.lua` with a data-driven stage configuration table. Stages defined as config → runtime executes generically. More complex but single file.

Option A is simpler, avoids breaking the existing runtime, and follows the plugin separation pattern.

**Evidence:** IPC protocol already has `bot` field in start commands (from ipc.lua parsing). The dispatch hook is already there.

### Finding 6: RNG Engine Completeness Gap (Confidence: High)

From rng-researcher + decomp-specialist cross-analysis:

**Confirmed correct:**
- `rng_oracle.py` LCRNG constants are exact: `LCRNG_A = 0x41C64E6D` = 1103515245 (RAND_MULT), `LCRNG_C = 0x00006073` = 24691 (addend) — confirmed from `decomps/pokefirered/src/random.h`
- Method 1 IV ordering is correct: `w1&0x1F=HP, w1>>5=Atk, w1>>10=Def, w2&0x1F=Spe, w2>>5=SpA, w2>>10=SpD` — PokeFinder uses same bit layout; apparent discrepancy was an index-ordering artifact in PokeFinder's internal storage, not actual difference
- `gRng2Value` (Random2 / ISO_RANDOMIZE2) is declared in `random.h` but unused in Fire Red starter path — only appears in commented-out daycare code. No need to track it for starter reset.
- `method1_generate` correctly models the 4-call chain: `Random32()` x2 for PID (2 calls), `Random()` x2 for IVs (2 calls) — confirmed from `decomps/pokefirered/src/pokemon.c:CreateBoxMon()`

**Still missing (required for PokeFinder Searcher parity):**
- `initial_seed_from_timer1(timer1_value: int) -> int` — the initial seed is the Timer 1 counter value at seeding moment, zero-extended to 32-bits. PokeFinder Searcher needs this to calculate what seed was active at title screen.
- `REG_TM1CNT_L` reading in Lua — Timer 1 runs at ~16 MHz independent of frames. Soft reset does NOT reset Timer 1 (only hard power cycle does). This is the fundamental source of seed entropy.
- Seeding occurs at title screen state machine case 2 (after palette fade) via `SeedRngAndSetTrainerId()` in `src/title_screen.c:731` — confirmed from decomp trace.

**Method taxonomy (from rng-researcher):**
- Starters: **Method 1** (PID_lo, PID_hi, IV_word1, IV_word2) — our implementation is correct
- Wild encounters: **Method H** (Gen 3 wild, FRLG-specific) — needed for future wild bot
- Method 4: inserts extra RNG call between IV1 and IV2 — used for some legendaries

**Lua reader already tracks:** `rng_value` (0x03005000), `vblank_counter2` (frame counter, increments each VBlank), `main_callback1/2` pointers — sufficient for current starter reset. Timer1 reading would be required only for offline seed reconstruction.

**Confidence:** High — confirmed by decomp trace and rng-researcher analysis of PokeFinder StaticGenerator3 source.

### Finding 7: Testing Architecture (Confidence: High)

From test-architect analysis:

**Two-layer testing architecture:**
- **Layer 1 — Pure Math Tests** (always CI): LCRNG engine, Method 1, seed advance/reverse, target planning. Zero external dependencies. Uses `rng_oracle.py` and `starter_target_planner.py` directly.
- **Layer 2 — Emulator Integration Tests** (skip-gated): Load savestate → advance N frames → read RAM → compare prediction. Gate via `_BIZHAWK_RUNNING = _check_bizhawk_socket()` at module load time.

**PokeFinder fixture data available for parity tests:**
- `.local_refs/rng_sources/admiral_fish_pokefinder/Test/RNG/lcrng.json` — LCRNG raw vectors
- `.local_refs/rng_sources/admiral_fish_pokefinder/Test/Gen3/static3.json` — Method 1 reference (3 test cases, 10 advances each, including `firered_lugia_method1`)
- `tests/fixtures/rng/pokefinder_method1/firered_lugia_method1_seed_AAAAAAAA.json` — already extracted in project format

**Open item:** `lcrng.json` "next" vector interpretation needs verification — may be 6 parallel chains from seed=0 rather than sequential chain output.

**New test files proposed:**
1. `tests/test_rng_engine_lcrng.py` — LCRNG parity vs lcrng.json (once vector interpretation confirmed)
2. `tests/test_rng_engine_method1.py` — Method 1 parity vs static3.json (especially firered_lugia)
3. `tests/test_rng_emulator_integration.py` — Savestate-based integration tests (skip-gated)
<!-- ID: technical_analysis -->
## Technical Analysis

### Plugin Integration Pattern

The `AutomationStrategy` sits inside the plugin system, not alongside it:

```
src/rom_lab/
├── plugins/
│   ├── base.py                           # GamePlugin ABC + get_automations()
│   └── pokemon_fire_red/
│       ├── plugin.py                      # PokemonFireRedPlugin (adds get_automations)
│       ├── rng_oracle.py                  # KEEP AS-IS (pure LCRNG logic)
│       ├── starter_target_planner.py      # KEEP AS-IS (pure target planning)
│       └── automation/                    # NEW: plugin-specific automation
│           ├── __init__.py
│           ├── base.py                    # StarterResetStrategy(AutomationStrategy)
│           ├── timing_model.py            # TimingModel — calibration + drift
│           ├── pid_learner.py             # PIDLearner — frequency + strategy
│           └── history_store.py          # StarterHistoryStore (extracted)
├── automation/
│   ├── __init__.py
│   └── base.py                           # AutomationStrategy ABC
└── api/
    └── routes/
        ├── automation.py                  # REFACTOR: generic dispatch router
        └── automation_starter_reset.py   # MOVE: StarterResetController (leaner)
```

### Module Composition Diagram

```
Frontend (automation.js)
    ↕ poll GET /api/automation/{slug}/status
    ↕ POST /api/automation/{slug}/start

AutomationRouter (FastAPI)
    → plugin.get_automations()[slug]
    → strategy.start(config) / strategy.stop() / strategy.get_status()

StarterResetStrategy (AutomationStrategy)
    uses: TimingModel, PIDLearner, TargetPlanner, HistoryStore
    sends: EmulatorBotCommand via IPC

RNGEngine (rng_oracle.py — pure)
    next_seed, prev_seed, advance, method1_generate, search_static_window

TargetPlanner (starter_target_planner.py — pure)
    plan_starter_targets, score_candidate, rank_candidates

TimingModel (NEW — extracted from StarterResetController)
    calibrate, update_drift, predict_delay, segment timing

PIDLearner (NEW — extracted from StarterResetController)
    update, get_dominant_seed, select_strategy, avoid_seeds

HistoryStore (extracted StarterHistoryStore)
    append_candidate, get_page, clear

Lua BotRuntime (runtime.lua — unchanged)
    start/stop/status IPC, frame-tick state machine
    → emits: events with frame numbers, RNG state
```

### Code Patterns Identified

1. **The Controller Monolith Anti-Pattern:** `StarterResetController` is ~6,000 lines. It has too many responsibilities because each learning/calibration/timing/planning concern grew organically inside a single class. Solution: extract each state machine into its own class.

2. **Constants Sprawl:** ~170 module-level constants. After split, each constant belongs to its natural module: `LCRNG_*` in `rng_engine.py`, `CALIBRATION_*` in `timing_model.py`, `LEARNER_*` in `pid_learner.py`, `TARGET_*` in `target_planner.py`.

3. **History Store Isolation:** `StarterHistoryStore` is already well-isolated (SQLite-backed, clean interface). Just needs to be moved to `automation/history_store.py`.

4. **Frontend DOM Coupling:** All 22 DOM element references in automation.js are starter-specific. Solution: group into strategy-namespaced configuration objects: `STARTER_FIELDS = {saveSlot: 'automationStarterSaveSlot', ...}`.

5. **RNG Parity Gap:** `rng_oracle.py` implements forward/reverse LCRNG and Method 1 generation. PokeFinder additionally has: `LCRNG64` (for Gen 4+), `initial_seed_from_timer1`, `tid_sid_from_seed`. The Timer1-to-seed calculation is what enables the "Searcher" function (find seed from current game state). This is the missing piece for full PokeFinder parity.

### System Interactions

| Component | Interacts With | Interface |
|---|---|---|
| AutomationRouter | ActivePlugin | `get_automations()` dict lookup |
| StarterResetStrategy | TimingModel | Method calls (calibrate/predict/update) |
| StarterResetStrategy | PIDLearner | Method calls (update/get_strategy/avoid) |
| StarterResetStrategy | TargetPlanner | `plan_starter_targets()` function call |
| StarterResetStrategy | HistoryStore | `append_candidate()`, `get_page()` |
| StarterResetStrategy | Lua IPC | HTTP/file-based debug request |
| Frontend | AutomationRouter | REST polling + start/stop |
| Lua BotRuntime | Emulator | Frame-tick callbacks |

### Risk Assessment

- [High] **Regression Risk:** The monolith has 3,756 lines of tests. Module split must preserve all existing behavior. Mitigation: split one module at a time, keeping all existing test fixtures working.
- [Medium] **RNG Parity Gap:** Timer1 seed calculation not yet implemented. PokeFinder parity requires this for the "Searcher" function. Mitigation: implement as new method in `rng_engine.py`, test against PokeFinder fixtures.
- [Low] **Lua generalization:** New `lua/plugins/` directory requires build/deploy coordination. Mitigation: use Option A (separate files per strategy) — simpler, no runtime changes.
<!-- ID: recommendations -->
## Recommendations

### Interface Contracts

**`AutomationStrategy` ABC** — `src/rom_lab/automation/base.py`:
```python
from abc import ABC, abstractmethod
from typing import Any

class AutomationStrategy(ABC):
    @property
    @abstractmethod
    def slug(self) -> str: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_default_config(self) -> dict[str, Any]: ...

    @abstractmethod
    async def start(self, config: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    async def stop(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_status(self) -> dict[str, Any]: ...

    @abstractmethod
    async def get_history(self, page: int, page_size: int) -> dict[str, Any]: ...
```

**`GamePlugin.get_automations()`** — `src/rom_lab/plugins/base.py`:
```python
def get_automations(self) -> dict[str, AutomationStrategy]:
    """Return automation strategies keyed by slug. Default: empty."""
    return {}
```

**`TimingModel`** — `src/rom_lab/plugins/pokemon_fire_red/automation/timing_model.py`:
```python
class TimingModel:
    def update_segment(self, segment_name: str, observed_frames: float) -> None: ...
    def predict_delay(self) -> int: ...
    def record_drift(self, expected: int, observed: int) -> None: ...
    def needs_recalibration(self) -> bool: ...
    def get_state(self) -> dict[str, Any]: ...
```

**`PIDLearner`** — `src/rom_lab/plugins/pokemon_fire_red/automation/pid_learner.py`:
```python
class PIDLearner:
    def update(self, pid: int, seed_start: int, seed_candidate: int) -> None: ...
    def get_dominant_seed(self) -> int | None: ...
    def get_strategy(self) -> str: ...
    def should_avoid_seed(self, seed: int) -> bool: ...
    def get_state(self) -> dict[str, Any]: ...
```

**`RNGEngine` additions** — `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` (extend in place):
```python
def initial_seed_from_timer1(timer1_value: int) -> int:
    """Compute initial gRngValue from Timer1 counter (REG_TM1CNT_L).
    
    FRLG: SeedRng(REG_TM1CNT_L) stores the 16-bit Timer1 value
    directly as gRngValue (zero-extended to 32 bits).
    Required for PokeFinder Searcher parity.
    """
    return timer1_value & 0xFFFF
```

### Phased Implementation Plan

**Phase 1 — Internal Split (no API changes):**
- Extract `TimingModel` class from `StarterResetController._calibration_state` + calibration methods
- Extract `PIDLearner` class from `StarterResetController._pid_learning_state` + learning methods
- Extract `_apply_target_overlay_to_plan` (~1,551 lines) as pure function in `target_overlay.py`
- Move `StarterHistoryStore` to `automation/history_store.py`
- Distribute 170 constants to their natural modules
- Move `_empty_*` state factories to `state_factories.py`
- Move dialogue detection helpers to `dialogue_detection.py`
- Move filter engine to `filter_engine.py`
- **Gate:** All existing tests (`tests/test_automation_routes.py` 3,756 lines) still pass unchanged

**Phase 2 — AutomationStrategy ABC + Plugin Registration:**
- Create `src/rom_lab/automation/base.py` with `AutomationStrategy` ABC
- Create `src/rom_lab/plugins/pokemon_fire_red/automation/base.py` with `StarterResetStrategy`
- Add `get_automations()` to `GamePlugin` ABC and `PokemonFireRedPlugin`
- Create `GET /api/automation/strategies` endpoint (list available strategies with config schemas)
- Create generic dispatch router `GET|POST /api/automation/{slug}/*`
- Keep `/api/automation/starter-reset/*` as aliases (backwards compatibility during transition)

**Phase 3 — RNG Engine Completeness (PokeFinder Parity):**
- Add `initial_seed_from_timer1(timer1_value: int) -> int` to `rng_oracle.py`
- Verify `lcrng.json` "next" vector interpretation (parallel chains vs sequential) — then write `test_rng_engine_lcrng.py`
- Write `test_rng_engine_method1.py` using `static3.json` firered_lugia fixture (10 advances, pid/ivs/nature)
- Optionally add Timer1 Lua reading (hardware register, non-trivial) — required only for offline seed reconstruction, not for current automation

**Phase 4 — Frontend Generalization:**
- Add strategy-selector `<select>` to bizhawk.html.j2 automation panel, populated from `/api/automation/strategies`
- Namespace starter-specific DOM IDs: `automationStarterSaveSlot`, `automationStarterShinyFilter`, etc.
- Refactor automation.js: dynamic `API_BASE = /api/automation/${selectedStrategy}`, strategy dispatch for `_buildStartPayload()`
- Keep all existing starter-reset UI behavior intact under new namespacing

**Phase 5 — Wild Encounter Strategy (stretch goal):**
- Define Method H (Gen 3 wild) in `rng_oracle.py`: `method_h_generate(seed: int) -> WildResult`
- Implement `WildEncounterStrategy(AutomationStrategy)` in plugin
- Add `lua/plugins/pokemon_fire_red/bots/wild_bot.lua` (bot_type=wild_encounter)
- Wire into dispatch router
- Add parity tests from `Test/Gen3/wild3.json` PokeFinder fixture

### Immediate Next Steps (Priority Order)

1. **Verify `lcrng.json` vector interpretation** — unblock Phase 3 LCRNG parity tests (test-architect open item)
2. **Extract `TimingModel`** (Phase 1, highest regression risk — most inter-woven with controller)
3. **Extract `PIDLearner`** (Phase 1, second priority)
4. **Extract `_apply_target_overlay_to_plan`** (Phase 1, 1,551 lines — largest pure-function extraction)
5. **Add `AutomationStrategy` ABC** (Phase 2, small interface file — enables all downstream plugin work)
6. **Add `get_automations()` to plugin** (Phase 2, wires automation into plugin system)
7. **Add `initial_seed_from_timer1()`** (Phase 3, 2-line function — completes PokeFinder Searcher parity)
8. **Write Method 1 parity tests** (Phase 3, use existing firered_lugia fixture — high confidence)
9. **Generic automation router** (Phase 2, prerequisite for frontend generalization)

### Long-Term Opportunities

- Wild encounter RNG automation (Method H, same infrastructure, different Lua bot)
- Breeding RNG automation with egg hatching prediction (egg3.json fixture data available)
- Cross-game automation strategies via the plugin system (Fire Red + Leaf Green share ROM layout)
- Automated TID/SID manipulation using Timer1 seed control (id3.json + seedtotime3.json fixture data)
- Method 4 support for legendaries (legendaries using extra RNG call between IV words)
<!-- ID: appendix -->
## Appendix

### Source Files Studied

| File | Lines | Role |
|---|---|---|
| `src/rom_lab/api/routes/automation.py` | 6,857 | Main monolith (target for refactoring) |
| `src/rom_lab/plugins/base.py` | 246 | GamePlugin ABC — plugin registration anchor |
| `src/rom_lab/plugins/pokemon_fire_red/plugin.py` | 370 | Fire Red plugin implementation |
| `src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` | ~200 | Pure LCRNG engine — already extracted |
| `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` | ~600 | Pure target planner — already extracted |
| `lua/common/bot/runtime.lua` | ~900 | Emulator-resident bot state machine |
| `lua/common/ipc.lua` | ~250 | Transport-agnostic IPC protocol |
| `.council/web/static/js/automation.js` | 1,573 | Frontend polling + status rendering |
| `.council/web/pages/bizhawk.html.j2` | 1,042 | HTML template with automation panel |
| `tests/test_automation_routes.py` | 3,756 | Existing test suite (must not regress) |

### Related Research Documents

- `RESEARCH_AUTOMATION_MODULARIZATION.md` — auto-analyst: detailed module boundary analysis
- `RESEARCH_POKEFINDER_RNG_ENGINE.md` — rng-researcher: PokeFinder C++ source analysis
- `RESEARCH_TESTING_INFRASTRUCTURE.md` — test-architect: test patterns and CI requirements
- `RESEARCH_DECOMP_RNG_TIMING.md` — decomp-specialist: Fire Red RNG call chain analysis

### Key External References

- [PokemonAutomation/ComputerControl](https://github.com/PokemonAutomation/ComputerControl) — task/operation registry pattern
- [Admiral-Fish/PokeFinder](https://github.com/Admiral-Fish/PokeFinder) — Searcher+Generator pattern, profile system
- [python-statemachine](https://github.com/fgmacedo/python-statemachine) — FSM library for Python (not needed, but reference)
- [FRLG Starter RNG Guide](https://blisy.net/g3/frlg-starter.html) — community timing documentation
