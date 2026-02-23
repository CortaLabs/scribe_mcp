---
id: automation_rng_modular_2026_02_21-implementation-report-20260221-0731
title: "Implementation Report: Task 2.2 \u2014 Planner Seed-Match Upgrades"
doc_type: custom
doc_name: IMPLEMENTATION_REPORT_20260221_0731
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-21 07:32:04 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Implementation Report: Task 2.2 — Planner Seed-Match Upgrades

**Date:** 2026-02-21 07:31 UTC
**Agent:** CoderAgent (forge-planner)
**Project:** automation_rng_modular_2026_02_21
**Task:** 2.2 — Planner Upgrades

## Summary

Enhanced `starter_target_planner.py` to support seed-match mode with target_seed computation, larger scan horizons, and simplified closest-candidate selection.

## Files Changed

| File | Changes |
|------|--------|
| `src/rom_lab/api/routes/automation/constants.py` | Added 3 new constants: SEED_MATCH_DEFAULT_SCAN_HORIZON (100,000), SEED_MATCH_DEFAULT_TIMEOUT_FRAMES (36,000), SEED_MATCH_OFFSET_SEARCH_RANGE ((-10, 25)) |
| `src/rom_lab/plugins/pokemon_fire_red/starter_target_planner.py` | Added seed_match_mode + press_to_generation_offset params to plan_starter_targets() and rank_starter_target_book(). Added clamp_horizon param to build_starter_target_book(). Compute target_seed per candidate via rng_oracle.compute_target_seed(). Seed-match rank_key prefers lowest delay. Context output includes seed_match_mode and press_to_generation_offset. |

## Key Design Decisions

1. **target_seed computed in rank_starter_target_book**, not build_starter_target_book — because target_seed depends on press_to_generation_offset which is a dynamic calibration value, not a static per-seed property.
2. **clamp_horizon parameter** on build_starter_target_book rather than special-casing seed_match_mode inside it — keeps the book builder generic.
3. **Rank key for seed-match** uses `-float(delay)` to prefer closest candidate, with filter_score as primary discriminator — this means among perfect-filter candidates, the one with shortest wait time is selected.

## Tests

- [x] 10/10 planner tests pass (0.70s)
- [x] 71/71 automation route tests pass (1.32s)
- [x] 81 total tests, 0 regressions

## Checklist Items Completed

- [x] 2.2.1: target_seed in candidate return data (line 635)
- [x] 2.2.2: Scan horizon raised (100,000 default, clamp bypass)
- [x] 2.2.3: Delay cap removed for seed-match mode
- [x] 2.2.4: Existing planner tests pass

## Confidence Score: 0.95

Not 1.0 because: (1) target_seed computation correctness depends on press_to_generation_offset calibration accuracy which is empirical, and (2) the closest-candidate selection strategy may not be optimal for all filter configurations — e.g., if a perfect-filter candidate exists at delay 50,000 but a 90%-match candidate exists at delay 100, the perfect match is still chosen. This is correct per spec but worth noting.

## Follow-ups

- Task 3.1 (Wave 3) will add integration tests proving seed-match execution works end-to-end
- Controller (Task 2.1, parallel) will consume the target_seed field from planner results
