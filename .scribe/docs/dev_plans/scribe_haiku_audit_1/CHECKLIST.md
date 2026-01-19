---
id: scribe_haiku_audit_1-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe-haiku-audit-1"
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-08'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — scribe-haiku-audit-1
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-08 08:13:40 UTC

> Acceptance checklist for scribe-haiku-audit-1.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
## Documentation Hygiene
<!-- ID: documentation_hygiene -->

- [x] Architecture guide updated with priority-ranked extractions (proof: ARCHITECTURE_GUIDE.md)
- [x] Phase plan current with scoped task packages (proof: PHASE_PLAN.md)
- [x] Research documents reviewed and consolidated (proof: 6 research docs in /research/)
- [ ] All extraction modules documented with interfaces
- [ ] Test structure documented per phase
<!-- ID: phase_0 -->
## Phase 1 - Critical God Object Decomposition
<!-- ID: phase_0 -->

### Task 1.1: storage/query_builder.py
- [ ] QueryBuilder class created (proof: storage/query_builder.py exists)
- [ ] All filter methods implemented: agent, emoji, priority, category, confidence, log_type, time_range, meta
- [ ] `build()` method returns (where_clause, params) tuple
- [ ] `build_with_order()` method handles priority sorting
- [ ] `tests/storage/test_query_builder.py` created
- [ ] All filter type tests pass
- [ ] sqlite.py `fetch_recent_entries()` delegates to QueryBuilder
- [ ] sqlite.py `query_entries()` delegates to QueryBuilder
- [ ] sqlite.py `count_entries()` delegates to QueryBuilder
- [ ] sqlite.py `count_query_entries()` delegates to QueryBuilder
- [ ] No raw WHERE clause construction remains in sqlite.py query methods

### Task 1.2: doc_management/patch_engine.py
- [ ] patch_engine.py created (proof: doc_management/patch_engine.py exists)
- [ ] `parse_patch_hunks()` function implemented
- [ ] `apply_unified_patch()` function implemented
- [ ] `rebase_patch_to_current_context()` function implemented
- [ ] `build_patch_failure_diagnostics()` function implemented
- [ ] Helper functions moved: _find_sequence_indices, _line_matches, etc.
- [ ] `tests/doc_management/test_patch_engine.py` created
- [ ] Hunk parsing tests pass
- [ ] Context matching tests pass
- [ ] One-line-gap tolerance tests pass
- [ ] Error diagnostic tests pass
- [ ] manager.py delegates patch operations to patch_engine

### Phase 1 Completion
- [ ] sqlite.py reduced by ~150 LOC (proof: wc -l comparison)
- [ ] manager.py reduced by ~350 LOC (proof: wc -l comparison)
- [ ] `pytest` full suite passes
- [ ] No circular imports (proof: import test)
<!-- ID: final_verification -->
## Phase 2 - High-Impact Shared Utilities
<!-- ID: final_verification -->

### Task 2.1: utils/logging_parameter_validator.py
- [ ] logging_parameter_validator.py created
- [ ] `validate_and_prepare_config()` function implemented
- [ ] Supports AppendEntryConfig
- [ ] Supports QueryEntriesConfig
- [ ] BulletproofParameterCorrector integration tested
- [ ] ExceptionHealer recovery tested
- [ ] `tests/utils/test_logging_parameter_validator.py` created
- [ ] append_entry.py updated to use validator
- [ ] query_entries.py updated to use validator
- [ ] ~450 LOC duplication eliminated

### Task 2.2: tools/manage_docs_special_creation.py
- [ ] manage_docs_special_creation.py created
- [ ] `handle_special_document_creation()` implemented
- [ ] Research doc creation works
- [ ] Bug report creation works
- [ ] Review report creation works
- [ ] Agent report card creation works
- [ ] Index update functions work
- [ ] `tests/tools/test_manage_docs_special_creation.py` created
- [ ] manage_docs.py delegates special creation
- [ ] manage_docs.py reduced by ~600 LOC

### Task 2.3: doc_management/text_replacements.py
- [ ] text_replacements.py created
- [ ] All replacement modes implemented: literal, regex, scope, section, range, block, header
- [ ] `tests/doc_management/test_text_replacements.py` created
- [ ] manager.py delegates text replacement operations
- [ ] manager.py reduced by ~210 LOC

### Phase 2 Completion
- [ ] `pytest` full suite passes
- [ ] No circular imports

---

## Phase 3 - Session Manager Extraction

### Task 3.1: storage/session_manager.py
- [ ] SessionManager class created
- [ ] Receives storage_backend instance (NOT imports SQLiteStorage)
- [ ] All session methods moved from sqlite.py
- [ ] Session lifecycle tested: create -> heartbeat -> expire -> cleanup
- [ ] Project context methods work
- [ ] Reminder cooldown methods work
- [ ] `tests/storage/test_session_manager.py` created
- [ ] sqlite.py delegates session operations
- [ ] sqlite.py reduced by ~370 LOC

### Phase 3 Completion
- [ ] Agent context tracking works end-to-end
- [ ] `pytest` full suite passes

---

## Phase 4 - Medium-Priority Extractions (Optional)

### Task 4.1: doc_management/markdown_tools.py
- [ ] markdown_tools.py created
- [ ] normalize_headers and generate_toc work
- [ ] Tests created

### Task 4.2: doc_management/checklist_manager.py
- [ ] checklist_manager.py created
- [ ] toggle_checklist_status works
- [ ] Tests created

### Task 4.3: utils/config_merger.py
- [ ] config_merger.py created
- [ ] Generic config merge works
- [ ] Tests created

### Task 4.4: doc_management/constants.py
- [ ] constants.py created with SECTION_MARKER and other shared constants

---

## Final Verification

- [ ] All Phase 1-3 checklist items complete with proofs
- [ ] Total LOC reduction achieved: ~3,000+ LOC
- [ ] All existing functionality preserved
- [ ] Stakeholder sign-off recorded (name + date)
- [ ] Retro completed and lessons learned documented

---
*Checklist consolidated by ArchitectAgent-Opus on 2026-01-08*
