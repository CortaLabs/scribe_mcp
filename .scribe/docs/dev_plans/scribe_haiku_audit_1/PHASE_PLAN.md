---
id: scribe_haiku_audit_1-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 scribe-haiku-audit-1"
doc_name: phase_plan
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

# ⚙️ Phase Plan — scribe-haiku-audit-1
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-01-08 08:13:40 UTC

> Execution roadmap for scribe-haiku-audit-1.

---
## Phase Overview
<!-- ID: phase_overview -->
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Key Deliverables | Est. LOC Impact | Confidence |
|-------|------|------------------|-----------------|------------|
| Phase 1 | Critical God Object Decomposition | storage/query_builder.py, doc_management/patch_engine.py | -500 LOC duplication | 0.95 |
| Phase 2 | High-Impact Shared Utilities | utils/logging_parameter_validator.py, manage_docs_special_creation.py, text_replacements.py | -1,260 LOC | 0.91 |
| Phase 3 | Session Manager Extraction | storage/session_manager.py | -370 LOC from sqlite.py | 0.90 |
| Phase 4 | Medium-Priority Extractions | markdown_tools.py, checklist_manager.py, config_merger.py | -380 LOC | 0.88 |

**Total Impact**: ~3,600 LOC reduction (29% of target files)

**Sequencing Rationale**: 
- Phase 1 extractions have NO dependencies and can run in parallel
- Phase 2 depends on Phase 1 patterns being validated
- Phase 3 depends on QueryBuilder for optional integration
- Phase 4 is lower priority and can be deferred
<!-- ID: phase_0 -->
## Phase 1 - Critical God Object Decomposition
<!-- ID: phase_0 -->

**Objective:** Extract the highest-impact, lowest-risk modules to decompose god objects.

### Task Package 1.1: storage/query_builder.py
**Source:** sqlite.py lines 354-681 (pattern in 4 methods)
**Est. LOC:** ~80 new, ~150 removed from sqlite.py

**Specifications:**
1. Create `storage/query_builder.py` with `QueryBuilder` class
2. Implement fluent builder pattern with methods:
   - `add_agent_filter()`, `add_agents_filter()`
   - `add_emoji_filter()`, `add_emojis_filter()`
   - `add_priority_filter()`, `add_category_filter()`
   - `add_confidence_filter()`, `add_log_type_filter()`
   - `add_time_range()`, `add_meta_filters()`
   - `build()` returning (where_clause, params)
   - `build_with_order()` for priority sorting
3. Update sqlite.py methods to delegate to QueryBuilder:
   - `fetch_recent_entries()` - lines 354-454
   - `query_entries()` - lines 456-535
   - `count_entries()` - lines 537-598
   - `count_query_entries()` - lines 600-681

**Verification:**
- [ ] `pytest tests/test_storage.py` passes
- [ ] Create `tests/storage/test_query_builder.py` with filter tests
- [ ] All 4 sqlite.py methods use QueryBuilder
- [ ] No raw WHERE clause construction in sqlite.py query methods

**Out of Scope:** Session management, migrations, metrics

---

### Task Package 1.2: doc_management/patch_engine.py
**Source:** manager.py lines 1121-1511
**Est. LOC:** ~350 extracted

**Specifications:**
1. Create `doc_management/patch_engine.py` with functions:
   - `parse_patch_hunks(patch_text: str) -> List[Dict]`
   - `apply_unified_patch(original: str, patch: str) -> Tuple[str, int]`
   - `rebase_patch_to_current_context(patch, original, current) -> str`
   - `build_patch_failure_diagnostics(error, patch, content) -> Dict`
   - Helper functions: `_find_sequence_indices()`, `_line_matches()`, etc.
2. Move `DocumentOperationError` exception to `doc_management/exceptions.py` (or reuse existing)
3. Update manager.py to import and call patch_engine functions

**Verification:**
- [ ] `pytest tests/test_doc_management.py` passes (if exists)
- [ ] Create `tests/doc_management/test_patch_engine.py` with:
  - Hunk parsing tests
  - Context matching tests
  - One-line-gap tolerance tests
  - Error diagnostic tests
- [ ] manager.py patch logic reduced to import + delegation

**Out of Scope:** Text replacements, markdown tools, checklist management

---

### Phase 1 Acceptance Criteria
- [ ] Both extractions complete and tested
- [ ] sqlite.py reduced by ~150 LOC
- [ ] manager.py reduced by ~350 LOC
- [ ] All existing tests pass (`pytest`)
- [ ] No circular imports introduced
<!-- ID: phase_1 -->
## Phase 2 - High-Impact Shared Utilities
<!-- ID: phase_1 -->

**Objective:** Extract shared utilities to eliminate cross-tool duplication.

### Task Package 2.1: utils/logging_parameter_validator.py
**Source:** append_entry.py lines 170-415, query_entries.py lines 61-403
**Est. LOC:** ~200 new, ~450 duplication removed

**Specifications:**
1. Create generic `validate_and_prepare_config()` function
2. Support both `AppendEntryConfig` and `QueryEntriesConfig` via protocol/base class
3. Implement shared patterns:
   - BulletproofParameterCorrector integration
   - ExceptionHealer recovery
   - BulletproofFallbackManager emergency fallback
   - Config object creation via `from_legacy_params()`
4. Update both tools to use new validator

**Verification:**
- [ ] `pytest tests/test_append_entry.py` passes
- [ ] `pytest tests/test_query_entries.py` passes
- [ ] Create `tests/utils/test_logging_parameter_validator.py`
- [ ] Duplication in both tools reduced

---

### Task Package 2.2: tools/manage_docs_special_creation.py
**Source:** manage_docs.py lines 758-1000, 2337-2944
**Est. LOC:** ~600 extracted

**Specifications:**
1. Create module with functions:
   - `handle_special_document_creation()` - main dispatcher
   - `build_special_metadata()`
   - `render_special_template()`
   - `record_special_doc_change()`
   - `auto_register_document()`
   - Index update functions: research, bug, review, agent card
2. Move template rendering for review/agent cards
3. Update manage_docs.py to import and delegate

**Verification:**
- [ ] All `create_*` actions in manage_docs still work
- [ ] Research, bug, review, agent card documents create correctly
- [ ] Index files update correctly
- [ ] manage_docs.py reduced by ~600 LOC

---

### Task Package 2.3: doc_management/text_replacements.py
**Source:** manager.py lines 963-1050
**Est. LOC:** ~210 extracted

**Specifications:**
1. Create module with functions:
   - `replace_text_literal(text, find, replace, all) -> (str, int)`
   - `replace_text_regex(text, pattern, replace) -> (str, int)`
   - `replace_text_with_scope()` - scope-limited replacement
   - `replace_section()` - section-based replacement
   - `replace_range_text()` - line range replacement
   - `replace_block_text()` - block replacement
   - `replace_section_by_header()` - header-based replacement
2. Update manager.py to delegate

**Verification:**
- [ ] All replacement modes in manage_docs work
- [ ] Create `tests/doc_management/test_text_replacements.py`
- [ ] manager.py reduced by ~210 LOC

---

### Phase 2 Acceptance Criteria
- [ ] All three extractions complete and tested
- [ ] Logging tools reduced by ~450 LOC combined
- [ ] manage_docs.py reduced by ~600 LOC
- [ ] manager.py reduced by ~210 LOC
- [ ] All existing tests pass (`pytest`)
<!-- ID: milestone_tracking -->
## Phase 3 - Session Manager Extraction
<!-- ID: milestone_tracking -->

**Objective:** Extract session management from sqlite.py to enable backend reuse.

### Task Package 3.1: storage/session_manager.py
**Source:** sqlite.py lines 1717-2083
**Est. LOC:** ~370 extracted

**Specifications:**
1. Create `SessionManager` class that receives storage_backend instance
2. Move methods:
   - `upsert_agent_session()`, `upsert_session()`
   - `set_session_mode()`, `get_session_mode()`
   - `set_session_project()`, `get_session_project()`
   - `get_session_by_transport()`
   - `upsert_agent_recent_project()`
   - `heartbeat_session()`, `end_session()`
   - `get_agent_project()`, `set_agent_project()`
   - `get_or_create_agent_session()`
   - `cleanup_expired_sessions()`
   - `record_reminder_shown()`, `check_reminder_cooldown()`, `cleanup_reminder_history()`
3. Update sqlite.py to delegate session calls to SessionManager
4. SessionManager receives write_lock from backend for thread safety

**Verification:**
- [ ] All session-related functionality works
- [ ] Create `tests/storage/test_session_manager.py`
- [ ] sqlite.py reduced by ~370 LOC
- [ ] Agent context tracking still works end-to-end

**Risk Mitigation:**
- SessionManager MUST receive storage_backend instance, not import SQLiteStorage
- Test session lifecycle thoroughly: create -> heartbeat -> expire -> cleanup

---

## Phase 4 - Medium-Priority Extractions (Optional/Deferred)

**Objective:** Complete remaining extractions for consistency.

### Task Package 4.1: doc_management/markdown_tools.py
**Source:** manager.py lines 1705-1873
**Est. LOC:** ~160 extracted
- `normalize_headers_text()`
- `generate_toc_text()`
- `_build_github_anchor()`

### Task Package 4.2: doc_management/checklist_manager.py
**Source:** manager.py lines 1912-2001
**Est. LOC:** ~120 extracted
- `toggle_checklist_status()`
- Checklist state resolution

### Task Package 4.3: utils/config_merger.py
**Source:** append_entry.py, query_entries.py
**Est. LOC:** ~50 new
- Generic config merge logic

### Task Package 4.4: doc_management/constants.py
**Est. LOC:** ~20
- `SECTION_MARKER`
- Other shared constants

---

## Milestone Tracking

| Milestone | Target | Owner | Status | Evidence |
|-----------|--------|-------|--------|----------|
| Phase 1 Complete | Week 1 | Coder | Pending | CHECKLIST.md |
| Phase 2 Complete | Week 2 | Coder | Pending | CHECKLIST.md |
| Phase 3 Complete | Week 3 | Coder | Pending | CHECKLIST.md |
| Phase 4 Complete | Week 4 | Coder | Deferred | Optional |
| Full Regression Pass | After Each Phase | Coder | - | pytest output |
<!-- ID: retro_notes -->
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

### Architecture Decisions Made

1. **Storage Layer Recalibration**: B1 haiku research was too gentle - sqlite.py upgraded to CRITICAL priority due to 65-method god object pattern

2. **State Layer Exclusion**: C1 research confirmed state/ layer is already well-modularized (1,105 LOC, 3 files, clear separation) - zero extractions needed

3. **rotate_log API Smell**: A3 correctly identified 454 LOC of parameter healing as API design problem, NOT extraction target. Recommend config object collapse in future.

4. **Session Manager DI Pattern**: Decided to pass storage_backend instance to SessionManager rather than import, avoiding circular dependency risk

5. **QueryBuilder Backend Agnostic**: Must use `?` placeholders that work on both SQLite and PostgreSQL

### Scope Changes
- None yet - document any changes here

### Lessons Learned
- To be filled after each phase completes

---
*Phase Plan consolidated by ArchitectAgent-Opus on 2026-01-08*
*Based on haiku swarm research with Opus-level recalibration*
