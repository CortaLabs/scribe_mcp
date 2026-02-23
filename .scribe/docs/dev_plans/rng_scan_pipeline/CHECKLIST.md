---
id: rng_scan_pipeline-checklist
title: "\u2705 Acceptance Checklist \u2014 rng_scan_pipeline"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 04:12:05 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — rng_scan_pipeline
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 03:52:59 UTC

> Acceptance checklist for rng_scan_pipeline.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Phase 1: Foundation (Models + Hidden Power)

- [ ] **Task 1.1**: `compute_hidden_power()` added to `starter_target_planner.py` <!-- ID: phase1_task1 -->
  - **Acceptance**: Function returns correct (type, power) tuple for known IV spreads
  - **Verification**: `compute_hidden_power({"hp":31,"atk":31,"def":31,"spa":31,"spd":31,"spe":31})` returns `("Dark", 70)`

- [ ] **Task 1.2**: 7 new Pydantic models added to `models.py` <!-- ID: phase1_task2 -->
  - **Acceptance**: `CandidateDetail`, `ScanMeta`, `ScanResponse`, `SelectRequest`, `SelectResponse`, `ExecuteRequest`, `ExecuteResponse` all importable
  - **Verification**: `from rom_lab.api.routes.automation.models import CandidateDetail, ScanResponse` succeeds

- [ ] **Task 1.3**: Hidden power unit tests created <!-- ID: phase1_task3 -->
  - **Acceptance**: All HP types reachable, power range [30,70], known spreads correct
  - **Verification**: `pytest tests/test_hidden_power.py -v` passes

- [ ] **Task 1.4**: Scan cache constants added to `constants.py` <!-- ID: phase1_task4 -->
  - **Acceptance**: `SCAN_CACHE_MAX_RESULTS`, `SCAN_CACHE_TTL_SECONDS`, `SCAN_PIPELINE_DEFAULT_CANDIDATE_COUNT` importable
  - **Verification**: No import errors

## Phase 2: Backend API

- [ ] **Task 2.1**: `scan()` + `_enrich_candidates()` + `_evict_expired_scans()` added to controller <!-- ID: phase2_task1 -->
  - **Acceptance**: `scan()` returns dict with scan_id, candidates list with hidden power fields, scan_meta
  - **Verification**: Candidates have `hidden_power_type` and `hidden_power_power` fields

- [ ] **Task 2.2**: `select()` and `execute()` added to controller <!-- ID: phase2_task2 -->
  - **Acceptance**: `select()` locks candidate by scan_id + plan_id; `execute()` starts run loop with locked target
  - **Verification**: Invalid scan_id/plan_id raises RuntimeError; execute without selection raises RuntimeError

- [ ] **Task 2.3**: 3 route handlers added to `routes.py` <!-- ID: phase2_task3 -->
  - **Acceptance**: `POST /scan`, `POST /select`, `POST /execute` return correct response shapes and error codes
  - **Verification**: Error cases return 404, 409, 503 as specified

- [ ] **Task 2.4**: Backend tests added to `test_automation_routes.py` <!-- ID: phase2_task4 -->
  - **Acceptance**: 8+ new test cases covering scan/select/execute and edge cases
  - **Verification**: `pytest tests/test_automation_routes.py -v -k "scan or select or execute"` passes; all existing tests still pass

## Phase 3: Frontend UI

- [ ] **Task 3.1**: HTML structure added to `bizhawk.html.j2` <!-- ID: phase3_task1 -->
  - **Acceptance**: Scan pipeline section visible with controls, table container, locked target panel
  - **Verification**: Page loads without errors; all `id` attributes present

- [ ] **Task 3.2**: JavaScript scan module added to `automation.js` <!-- ID: phase3_task2 -->
  - **Acceptance**: Deep Scan triggers API call, table renders candidates, selection locks target, execute fires
  - **Verification**: Full scan -> select -> execute flow works in browser

- [ ] **Task 3.3**: CSS styles added to `bizhawk.css` <!-- ID: phase3_task3 -->
  - **Acceptance**: Scan table matches tactical HUD aesthetic (dark, cyan, matte)
  - **Verification**: Selected row distinguished, shiny rows have gold accent, no purple

## Phase 4: Integration

- [ ] **Task 4.1**: End-to-end integration verified <!-- ID: phase4_task1 -->
  - **Acceptance**: Full pipeline works with live BizHawk; existing `/start` backward-compatible
  - **Verification**: `pytest tests/test_automation_routes.py tests/test_hidden_power.py -v` all pass; manual E2E test
<!-- ID: phase_0 -->
*(No Phase 0 prerequisites -- this project extends existing, verified infrastructure.)*
<!-- ID: final_verification -->
## Final Verification

- [ ] All Phase 1-4 checklist items checked with proof evidence attached
- [ ] `pytest tests/test_automation_routes.py tests/test_hidden_power.py -v` passes (0 failures)
- [ ] Existing `/start` endpoint still works identically (backward compatibility)
- [ ] No regressions in `pytest tests/` full suite
- [ ] Architecture documents updated with any deviations discovered during implementation
