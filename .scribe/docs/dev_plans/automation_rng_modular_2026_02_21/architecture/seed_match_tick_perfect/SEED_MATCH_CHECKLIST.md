# Checklist: Seed-Match Tick-Perfect Execution

**Sub-plan of:** automation_rng_modular_2026_02_21
**Author:** ArchitectAgent
**Status:** Draft
**Last Updated:** 2026-02-21

---

<!-- ID: wave_1_lua -->
## Wave 1: Lua Seed Monitor (Task 1.1)

- [ ] **1.1.1**: New state fields added to `_state` in runtime.lua <!-- ID: w1_lua_state_fields -->
  - **Acceptance**: `seed_wait_start_frame`, `seed_at_match`, `frame_at_seed_match`, `frame_at_a2_complete`, `frame_at_a3_complete` all present in _state init and _reset_state
  - **Verification**: `grep -c 'seed_at_match' lua/common/bot/runtime.lua` returns >= 3

- [ ] **1.1.2**: New config fields with defaults in runtime.lua <!-- ID: w1_lua_config_fields -->
  - **Acceptance**: `rng_target_seed = nil`, `rng_seed_wait_timeout_frames = 36000`, `rng_use_seed_match = false` in config defaults
  - **Verification**: `grep 'rng_target_seed' lua/common/bot/runtime.lua` returns >= 2

- [ ] **1.1.3**: `rng_seed_wait` stage handler implemented <!-- ID: w1_seed_wait_stage -->
  - **Acceptance**: Stage reads _current_seed() every frame, compares to config.rng_target_seed, presses A on match, has timeout fallback
  - **Verification**: `grep -c 'rng_seed_wait' lua/common/bot/runtime.lua` returns >= 3

- [ ] **1.1.4**: `a2_yesno_auto` stage handler implemented <!-- ID: w1_a2_auto_stage -->
  - **Acceptance**: Stage presses A to advance dialogue, detects choice via is_choice_open(), transitions to a3_confirm_auto
  - **Verification**: `grep -c 'a2_yesno_auto' lua/common/bot/runtime.lua` returns >= 3

- [ ] **1.1.5**: `a3_confirm_auto` stage handler implemented <!-- ID: w1_a3_auto_stage -->
  - **Acceptance**: Stage presses A to confirm YES, detects choice close, transitions to rng_seed_wait or a4 hold fallback
  - **Verification**: `grep -c 'a3_confirm_auto' lua/common/bot/runtime.lua` returns >= 3

- [ ] **1.1.6**: Bot status JSON includes new fields <!-- ID: w1_status_json -->
  - **Acceptance**: `seed_at_match`, `frame_at_seed_match`, `seed_wait_frames`, `rng_target_seed`, `rng_use_seed_match` in status output
  - **Verification**: `grep 'seed_at_match' lua/common/bot/runtime.lua` appears in status builder

- [ ] **1.1.7**: Stage transition wiring correct <!-- ID: w1_stage_transitions -->
  - **Acceptance**: When rng_use_seed_match=true, flow is: a1_press -> a2_yesno_auto -> a3_confirm_auto -> rng_seed_wait -> a4_acquire. When false, flow is unchanged from current behavior.
  - **Verification**: Manual trace of stage transitions in code

- [ ] **1.1.8**: Lua syntax valid <!-- ID: w1_lua_syntax -->
  - **Acceptance**: `luac -p lua/common/bot/runtime.lua` exits 0
  - **Verification**: `luac -p lua/common/bot/runtime.lua`

---

<!-- ID: wave_1_ipc -->
## Wave 1: IPC Protocol (Task 1.1)

- [ ] **1.1.9**: IPC parses rng_target_seed <!-- ID: w1_ipc_target_seed -->
  - **Acceptance**: `parse_number_field("rng_target_seed")` added to ipc.lua parse_request
  - **Verification**: `grep 'rng_target_seed' lua/common/ipc.lua` returns >= 1

- [ ] **1.1.10**: IPC parses rng_seed_wait_timeout_frames <!-- ID: w1_ipc_timeout -->
  - **Acceptance**: `parse_number_field("rng_seed_wait_timeout_frames")` added
  - **Verification**: `grep 'rng_seed_wait_timeout_frames' lua/common/ipc.lua` returns >= 1

- [ ] **1.1.11**: IPC parses rng_use_seed_match <!-- ID: w1_ipc_use_seed_match -->
  - **Acceptance**: Boolean parsing for rng_use_seed_match field added
  - **Verification**: `grep 'rng_use_seed_match' lua/common/ipc.lua` returns >= 1

- [ ] **1.1.12**: IPC syntax valid <!-- ID: w1_ipc_syntax -->
  - **Acceptance**: `luac -p lua/common/ipc.lua` exits 0
  - **Verification**: `luac -p lua/common/ipc.lua`

---

<!-- ID: wave_1_reader_sync -->
## Wave 1: Lua Reader Sync (Task 1.1b)

- [ ] **1.1b.1**: socket_reader.lua syntax valid <!-- ID: w1_reader_socket -->
  - **Acceptance**: `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua` exits 0
  - **Verification**: `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/socket_reader.lua`

- [ ] **1.1b.2**: reader.lua syntax valid <!-- ID: w1_reader_file -->
  - **Acceptance**: `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua` exits 0
  - **Verification**: `luac -p src/rom_lab/plugins/pokemon_fire_red/lua/reader.lua`

---

<!-- ID: wave_1_oracle -->
## Wave 1: Target Seed Computation (Task 1.2)

- [ ] **1.2.1**: `compute_target_seed()` function added to rng_oracle.py <!-- ID: w1_compute_fn -->
  - **Acceptance**: Function exists, handles offset=0 and offset>0 cases
  - **Verification**: `grep 'def compute_target_seed' src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py`

- [ ] **1.2.2**: `find_offset_for_pid()` function added to rng_oracle.py <!-- ID: w1_find_offset_fn -->
  - **Acceptance**: Function exists, searches configurable range, returns int or None
  - **Verification**: `grep 'def find_offset_for_pid' src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py`

- [ ] **1.2.3**: Both functions in __all__ exports <!-- ID: w1_exports -->
  - **Acceptance**: `"compute_target_seed"` and `"find_offset_for_pid"` in __all__
  - **Verification**: `grep 'compute_target_seed' src/rom_lab/plugins/pokemon_fire_red/rng_oracle.py` in __all__ block

- [ ] **1.2.4**: Existing tests pass <!-- ID: w1_existing_tests -->
  - **Acceptance**: `pytest tests/test_rng_oracle_pokefinder_parity.py` exits 0
  - **Verification**: `pytest tests/test_rng_oracle_pokefinder_parity.py -v`

---

<!-- ID: wave_1_unit_tests -->
## Wave 1: Unit Tests (Task 1.3)

- [x] **1.3.1**: test_seed_match_computation.py created <!-- ID: w1_test_file -->
  - **Acceptance**: File exists in tests/ with at least 6 test functions
  - **Verification**: `pytest tests/test_seed_match_computation.py -v`
  - **Proof**: 15 test functions, 51 total tests, all passing (0.17s)

- [x] **1.3.2**: Round-trip test passes <!-- ID: w1_round_trip -->
  - **Acceptance**: advance(seed, N) then reverse by N returns original seed
  - **Verification**: Test passes
  - **Proof**: test_advance_reverse_round_trip (7 parametrized cases) + test_method1_round_trip (8 seeds x 5 offsets)

- [x] **1.3.3**: Target seed identity test passes <!-- ID: w1_identity -->
  - **Acceptance**: compute_target_seed(seed, offset=0) == seed
  - **Verification**: Test passes
  - **Proof**: test_compute_target_seed_zero_offset (8 seeds parametrized)

- [x] **1.3.4**: Full-chain test passes <!-- ID: w1_full_chain -->
  - **Acceptance**: search -> select -> compute_target -> advance by offset -> method1_generate -> PID matches
  - **Verification**: Test passes
  - **Proof**: test_target_seed_produces_expected_pokemon + test_target_seed_with_offset_produces_expected_pokemon + test_multiple_seeds_all_verify (5 seeds)

---

<!-- ID: wave_2_controller -->
## Wave 2: Controller Integration (Task 2.1)

- [ ] **2.1.1**: _press_to_generation_offset instance variable added <!-- ID: w2_offset_var -->
  - **Acceptance**: `self._press_to_generation_offset: int = 0` in __init__
  - **Verification**: `grep '_press_to_generation_offset' src/rom_lab/api/routes/automation/controller.py`

- [ ] **2.1.2**: _bot_start_fields includes new fields <!-- ID: w2_bot_fields -->
  - **Acceptance**: rng_target_seed, rng_seed_wait_timeout_frames, rng_use_seed_match in bot start payload
  - **Verification**: `grep 'rng_target_seed' src/rom_lab/api/routes/automation/controller.py` returns >= 3

- [ ] **2.1.3**: Target seed computed in overlay <!-- ID: w2_overlay -->
  - **Acceptance**: compute_target_seed called with candidate start_seed and offset
  - **Verification**: `grep 'compute_target_seed' src/rom_lab/api/routes/automation/controller.py`

- [ ] **2.1.4**: Python A2/A3 skipped in seed-match mode <!-- ID: w2_skip_a2a3 -->
  - **Acceptance**: When rng_use_seed_match=True, Python does not poll for A2 choice or A3 confirm
  - **Verification**: Code inspection shows conditional skip of A2/A3 polling

- [ ] **2.1.5**: _calibrate_press_offset method added <!-- ID: w2_calibrate -->
  - **Acceptance**: Method exists, calls find_offset_for_pid, updates offset, logs result
  - **Verification**: `grep '_calibrate_press_offset' src/rom_lab/api/routes/automation/controller.py`

- [ ] **2.1.6**: New bot status fields extracted <!-- ID: w2_extract -->
  - **Acceptance**: seed_at_match, frame_at_seed_match, seed_wait_frames extracted from bot status
  - **Verification**: `grep 'seed_at_match' src/rom_lab/api/routes/automation/controller.py` returns >= 2

- [ ] **2.1.7**: Existing automation tests pass <!-- ID: w2_existing_tests -->
  - **Acceptance**: `pytest tests/test_automation_routes.py` exits 0
  - **Verification**: `pytest tests/test_automation_routes.py -v`

---

<!-- ID: wave_2_planner -->
## Wave 2: Planner Upgrades (Task 2.2)

- [ ] **2.2.1**: target_seed in candidate return data <!-- ID: w2_planner_target -->
  - **Acceptance**: plan_starter_targets returns candidates with target_seed field
  - **Verification**: `grep 'target_seed' src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py`

- [ ] **2.2.2**: Scan horizon raised <!-- ID: w2_planner_horizon -->
  - **Acceptance**: Default horizon >= 100000 when seed_match_mode=True
  - **Verification**: Test or code inspection

- [ ] **2.2.3**: Delay cap removed for seed-match mode <!-- ID: w2_planner_cap -->
  - **Acceptance**: LEARNER_MAX_PRE_A4_HOLD_FRAMES no longer constrains candidate selection in seed_match mode
  - **Verification**: Code inspection

- [ ] **2.2.4**: Existing planner tests pass <!-- ID: w2_planner_tests -->
  - **Acceptance**: `pytest tests/test_starter_target_planner.py` exits 0
  - **Verification**: `pytest tests/test_starter_target_planner.py -v`

---

<!-- ID: wave_3_verification -->
## Wave 3: Verification Pipeline (Task 3.1)

- [ ] **3.1.1**: Verification outcome in attempt result <!-- ID: w3_outcome -->
  - **Acceptance**: verification_result field (exact_hit/seed_hit_pid_miss/etc.) in attempt JSON
  - **Verification**: Code inspection

- [ ] **3.1.2**: Integration tests created <!-- ID: w3_integration_tests -->
  - **Acceptance**: tests/test_seed_match_integration.py exists with >= 5 test functions
  - **Verification**: `pytest tests/test_seed_match_integration.py -v`

- [ ] **3.1.3**: No regressions in test suite <!-- ID: w3_no_regressions -->
  - **Acceptance**: `pytest tests/test_automation_routes.py tests/test_starter_target_planner.py` exits 0
  - **Verification**: `pytest` full suite

---

<!-- ID: wave_3_cleanup -->
## Wave 3: Cleanup (Task 3.2)

- [ ] **3.2.1**: Learner simplified for seed-match mode <!-- ID: w3_learner -->
  - **Acceptance**: timing_lock and phase_cycle_probe strategies skipped when seed_match_mode
  - **Verification**: Code inspection

- [ ] **3.2.2**: Calibration guarded for seed-match mode <!-- ID: w3_calibration -->
  - **Acceptance**: Drift EWMA updates skipped when seed_match_mode
  - **Verification**: Code inspection

- [ ] **3.2.3**: New constants added <!-- ID: w3_constants -->
  - **Acceptance**: SEED_MATCH_DEFAULT_SCAN_HORIZON, SEED_MATCH_DEFAULT_TIMEOUT_FRAMES, SEED_MATCH_OFFSET_SEARCH_RANGE in constants.py
  - **Verification**: `grep 'SEED_MATCH' src/rom_lab/api/routes/automation/constants.py`

- [ ] **3.2.4**: Full test suite passes <!-- ID: w3_full_suite -->
  - **Acceptance**: `pytest tests/` exits 0
  - **Verification**: `pytest tests/ -v`

---

<!-- ID: final_proof -->
## Final Proof: Tick-Perfect Execution

- [ ] **PROOF.1**: First seed match hit achieved <!-- ID: proof_first_hit -->
  - **Acceptance**: seed_at_match == rng_target_seed in at least 1 live attempt
  - **Verification**: Bot run log

- [ ] **PROOF.2**: Offset calibrated and stable <!-- ID: proof_offset -->
  - **Acceptance**: press_to_generation_offset consistent across 3+ attempts
  - **Verification**: Bot run log shows same offset

- [ ] **PROOF.3**: PID prediction matches actual <!-- ID: proof_pid -->
  - **Acceptance**: predicted_pid == actual_pid in at least 5 consecutive attempts
  - **Verification**: Bot run log

- [ ] **PROOF.4**: 10 consecutive exact hits <!-- ID: proof_10_hits -->
  - **Acceptance**: 10 attempts in a row where seed_match=true AND pid_match=true AND nature_match=true
  - **Verification**: Bot run history showing 10 consecutive exact_hit results
