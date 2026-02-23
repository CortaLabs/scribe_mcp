---
id: scribe_perf_optimization-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe_perf_optimization"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 06:16:14 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — scribe_perf_optimization
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-17 05:57:35 UTC

> Acceptance checklist for scribe_perf_optimization.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
- [ ] Architecture guide complete and reviewed <!-- ID: doc_arch -->
  - **Acceptance**: All 10 sections populated with implementation details
  - **Verification**: `scribe.read_file ARCHITECTURE_GUIDE.md` shows no template placeholder text
- [ ] Phase plan complete with scoped task packages <!-- ID: doc_phase -->
  - **Acceptance**: 9 task packages across 4 phases, each with file:line references
  - **Verification**: `scribe.read_file PHASE_PLAN.md` shows all phases populated
- [ ] Checklist complete with pass/fail criteria <!-- ID: doc_check -->
  - **Acceptance**: Every optimization has testable verification criteria
  - **Verification**: This document is fully populated
<!-- ID: phase_0 -->
---
## Phase 1: persist() Cleanup (Track B)
<!-- ID: phase_1_checklist -->

- [ ] **Task 1.1**: Project upsert loop removed from persist() <!-- ID: p1_task1 -->
  - **Acceptance**: `persist()` method no longer contains `for project_name, payload in state.projects.items():`
  - **Verification**: `grep -c "state.projects.items" src/scribe_mcp/state/manager.py` returns 0 in persist()
- [ ] **Task 1.1b**: Session _upsert_project removed from persist() <!-- ID: p1_task1b -->
  - **Acceptance**: `persist()` session_projects loop no longer calls `_upsert_project`
  - **Verification**: Manual code inspection of persist() method
- [ ] **Task 1.1c**: persist() docstring updated <!-- ID: p1_task1c -->
  - **Acceptance**: Docstring explains why project upserts are not needed
  - **Verification**: `scribe.read_file manager.py` -- docstring on persist()
- [ ] **Task 1.2**: Regression test added <!-- ID: p1_task2 -->
  - **Acceptance**: `tests/test_persist_cleanup.py` exists with 2+ test functions
  - **Verification**: `pytest tests/test_persist_cleanup.py -v` passes
- [ ] **Phase 1 Gate**: All existing tests pass <!-- ID: p1_gate -->
  - **Acceptance**: `pytest tests/ -x --timeout=120` returns 0 exit code
  - **Verification**: CI or manual run

---
## Phase 2: set_project Call Reduction (Track A)
<!-- ID: phase_2_checklist -->

- [ ] **Task 2.1**: Batch upsert_dev_plan implemented (OPT-1) <!-- ID: p2_task1 -->
  - **Acceptance**: set_project.py uses `execute_batch` when available, falls back to sequential otherwise
  - **Verification**: `grep "execute_batch" src/scribe_mcp/tools/set_project.py` returns match
- [ ] **Task 2.2**: Project record cache added (OPT-2) <!-- ID: p2_task2 -->
  - **Acceptance**: `RemoteStorageBackend` has `_project_cache` dict, `fetch_project` checks cache
  - **Verification**: `grep "_project_cache" src/scribe_mcp/storage/remote.py` returns 3+ matches
- [ ] **Task 2.3**: count_entries skipped for new projects (OPT-3) <!-- ID: p2_task3 -->
  - **Acceptance**: `docs_were_generated` computed before count_entries, used to skip call
  - **Verification**: `grep "docs_were_generated" src/scribe_mcp/tools/set_project.py` before count_entries
- [ ] **Phase 2 Gate**: All existing tests pass <!-- ID: p2_gate -->
  - **Acceptance**: `pytest tests/ -x --timeout=120` returns 0 exit code
  - **Verification**: CI or manual run

---
## Phase 3: CortaStore Fixes (Track C)
<!-- ID: phase_3_checklist -->

- [ ] **Task 3.1**: create_storage_backend mode auto-detection (FIX-1) <!-- ID: p3_task1 -->
  - **Acceptance**: `create_storage_backend()` without mode param returns RemoteStorageBackend when settings.mode="client"
  - **Verification**: Unit test passes
- [ ] **Task 3.2**: CortaStore health probe added (FIX-2) <!-- ID: p3_task2 -->
  - **Acceptance**: `CortaStoreProvider.setup()` includes GET /health probe with warning on failure
  - **Verification**: `grep "health" src/scribe_mcp/object_store/providers/corta.py` returns match
- [ ] **Task 3.3**: .env.example updated (FIX-3) <!-- ID: p3_task3 -->
  - **Acceptance**: .env.example documents CLIENT mode config, notes SCRIBE_DB_URL not needed
  - **Verification**: Manual inspection

---
## Phase 4: Deploy and Verify
<!-- ID: phase_4_checklist -->

- [ ] **Task 4.1**: Deployed to Hetzner <!-- ID: p4_task1 -->
  - **Acceptance**: `curl http://localhost:8200/health` returns 200 on council-hub
  - **Verification**: SSH to council-hub, run health check
- [ ] **Task 4.2**: Performance verified <!-- ID: p4_task2 -->
  - **Acceptance**: `set_project` in CLIENT mode completes in < 3 seconds (was ~28s)
  - **Verification**: Timing measurement from local MCP
<!-- ID: final_verification -->
---
## Final Verification
<!-- ID: final_gate -->

- [ ] All phase gates passed <!-- ID: final_all_phases -->
  - **Acceptance**: Phases 1-4 all complete with proofs
  - **Verification**: All checklist items above are checked
- [ ] No behavioral regressions <!-- ID: final_regression -->
  - **Acceptance**: `pytest tests/ -x --timeout=120` passes
  - **Verification**: Full test suite run
- [ ] Performance target met <!-- ID: final_perf -->
  - **Acceptance**: set_project CLIENT mode < 3 seconds (90%+ improvement from ~28s)
  - **Verification**: Timing measurement post-deploy
- [ ] Architecture documents match implementation <!-- ID: final_docs -->
  - **Acceptance**: No drift between ARCHITECTURE_GUIDE.md and actual code
  - **Verification**: Review Agent audit
