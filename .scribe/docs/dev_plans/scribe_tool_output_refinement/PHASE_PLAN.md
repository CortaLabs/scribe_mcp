# ⚙️ Phase Plan — scribe_tool_output_refinement
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** ready_for_implementation
**Last Updated:** 2026-01-02 14:04:00 UTC

> Sequential execution roadmap for implementing readable output formats across all Scribe MCP tools.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Duration | Key Deliverables | Dependencies | Confidence |
|-------|------|----------|------------------|--------------|------------|
| Phase 0 - Foundation | Extend ResponseFormatter with readable format core | 3 days | ResponseFormatter methods, helper functions, unit tests | None | 0.95 |
| Phase 1 - read_file | Implement readable format for priority tool | 1 week | read_file with format parameter, integration tests | Phase 0 | 0.95 |
| Phase 2 - append_entry | Implement readable format for log writing | 1 week | append_entry with format parameter, bulk mode support | Phase 0 | 0.95 |
| Phase 3 - Log Tools | Implement readable format for log query tools | 1 week | read_recent, query_entries with format parameter | Phase 0 | 0.95 |
| Phase 4 - Remaining Tools | Complete format parameter rollout | 2 weeks | All 14 tools with format parameter | Phase 0-3 | 0.9 |
| Phase 5 - Documentation & Polish | Final testing, docs, and release | 1 week | Documentation, visual validation, release | Phase 4 | 0.9 |

**Total Estimated Duration:** 6 weeks
**Critical Path:** Phase 0 → Phase 1 (read_file is highest priority)

---
## Phase 0 — Foundation (ResponseFormatter Extension)
<!-- ID: phase_0 -->

**Objective:** Extend utils/response.py with readable format infrastructure that all tools will use.

**Duration:** 3 days

### Key Tasks

1. **Add Format Constants** (2 hours)
   - Add `FORMAT_READABLE`, `FORMAT_STRUCTURED`, `FORMAT_COMPACT` constants
   - Update class docstrings with format documentation

2. **Implement Helper Methods** (1 day)
   - `_add_line_numbers(content, start=1) -> str` - Cat -n style line numbering
   - `_create_header_box(title, metadata) -> str` - ASCII box header generation
   - `_create_footer_box(audit_data, reminders) -> str` - ASCII box footer
   - `_format_table(headers, rows) -> str` - Aligned ASCII table generator

3. **Implement Core Formatting Methods** (1 day)
   - `format_readable_file_content(data) -> str` - For read_file output
   - `format_readable_log_entries(entries, pagination) -> str` - For log tools
   - `format_readable_projects(projects, active) -> str` - For list_projects
   - `format_readable_confirmation(operation, data) -> str` - For operation confirmations
   - `format_readable_error(error, context) -> str` - Error message formatting

4. **Implement Format Router** (4 hours)
   - `finalize_tool_response(data, format, tool_name) -> Union[Dict, str]`
   - Routes to appropriate formatter based on format + tool_name
   - Handles invalid format gracefully (default to structured + warning)

5. **Unit Tests** (4 hours)
   - `tests/test_response_formatter.py` - Comprehensive unit tests
   - Test line numbering padding and alignment
   - Test ASCII box generation and width calculations
   - Test format routing logic
   - Test error handling

### Deliverables

- [ ] `utils/response.py` extended with ~300 lines of readable format code
- [ ] `tests/test_response_formatter.py` created with 100% coverage of new methods
- [ ] All helper methods tested independently
- [ ] Format router tested with all format values

### Acceptance Criteria

- [ ] All unit tests pass (100% coverage of new code)
- [ ] Line numbering produces correct cat -n format
- [ ] ASCII boxes align correctly at various terminal widths
- [ ] Format router returns correct types (Dict for structured, str for readable)
- [ ] Invalid format values default to structured with warning logged
- [ ] No breaking changes to existing ResponseFormatter functionality

### Dependencies

**None** - This is the foundation phase

### Risks & Mitigations

- **Risk:** ASCII box drawing doesn't align properly
  - **Mitigation:** Comprehensive width calculation tests, manual visual inspection

- **Risk:** Line numbering padding breaks on large line counts
  - **Mitigation:** Test with 1, 10, 100, 1000, 10000 line files

### Notes

This phase blocks all subsequent phases. Must be fully tested and working before proceeding to tool integration.

---
## Phase 1 — read_file Tool (Priority)
<!-- ID: phase_1 -->

**Objective:** Implement readable format for read_file - the highest priority tool with worst current agent experience.

**Duration:** 1 week

### Key Tasks

1. **Add Format Parameter** (2 hours)
   - Add `format: str = "structured"` parameter to read_file signature
   - Update docstring with format parameter documentation
   - Update type hints: `-> Union[Dict[str, Any], str]`

2. **Integrate Format Selection** (1 day)
   - Modify return statements in all 6 modes (scan_only, chunk, line_range, page, full_stream, search)
   - Call `finalize_tool_response(response_data, format, "read_file")` before returning
   - Test each mode with format="readable"

3. **Readable Format Implementation** (2 days)
   - Implement readable output for chunk mode (priority)
   - Implement readable output for line_range mode
   - Implement readable output for page mode
   - Implement readable output for search mode
   - Implement readable output for full_stream mode
   - Implement readable output for scan_only mode

4. **Integration Tests** (1 day)
   - Test read_file(format="readable", mode="chunk")
   - Test read_file(format="readable", mode="line_range", start_line=1, end_line=50)
   - Test read_file(format="readable", mode="search", pattern="def")
   - Test backward compatibility: read_file() without format parameter
   - Test all existing tests pass unchanged

5. **Performance Validation** (1 day)
   - Benchmark readable format overhead vs structured
   - Test large file handling (10K lines)
   - Verify memory usage ≤2x current
   - Verify overhead ≤5ms per call

### Deliverables

- [ ] read_file tool with format parameter fully implemented
- [ ] All 6 output modes support readable format
- [ ] Integration tests for all modes × all formats (18 test cases minimum)
- [ ] Performance benchmarks show acceptable overhead
- [ ] Backward compatibility validated (all existing tests pass)

### Acceptance Criteria

- [ ] read_file(format="readable") produces line-numbered output with header/footer boxes
- [ ] Content has actual line breaks (not escaped `\n`)
- [ ] Metadata in footer section, not mixed with content
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms
- [ ] Memory usage ≤2x for large files

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Performance degradation on large files
  - **Mitigation:** Lazy string building, streaming for full_stream mode, performance tests

- **Risk:** Breaking existing read_file integrations
  - **Mitigation:** Default format=structured, comprehensive backward compat tests

### Notes

read_file is the highest priority tool (worst current agent experience). Success here validates the entire approach.

---
## Phase 2 — append_entry Tool
<!-- ID: phase_2 -->

**Objective:** Implement readable format for append_entry - the primary logging tool used by all agents.

**Duration:** 1 week

### Key Tasks

1. **Add Format Parameter** (2 hours)
   - Add `format: str = "structured"` parameter
   - Update docstring and type hints
   - Handle format in both single entry and bulk modes

2. **Implement Readable Confirmation** (2 days)
   - Readable format for single entry success
   - Readable format for bulk entry success
   - Readable format for partial failures (some entries failed)
   - Readable format for complete failures
   - Display written line, path, metadata in readable format

3. **Integration Tests** (2 days)
   - Test append_entry(format="readable", message="test")
   - Test bulk mode: append_entry(format="readable", items=[...])
   - Test error cases with readable format
   - Test backward compatibility
   - Test existing append_entry tests pass unchanged

4. **Performance Validation** (1 day)
   - Benchmark single entry with readable format
   - Benchmark bulk mode with readable format
   - Verify no degradation in structured format performance

### Deliverables

- [ ] append_entry with format parameter for single and bulk modes
- [ ] Readable confirmation output showing entry details clearly
- [ ] Integration tests for all append_entry modes
- [ ] Performance validation completed

### Acceptance Criteria

- [ ] Readable format shows written line prominently
- [ ] Success/failure status clear with emoji
- [ ] Path, metadata, and audit info in organized sections
- [ ] Bulk mode shows summary + individual entry details
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Bulk mode readable format too verbose
  - **Mitigation:** Summary section + collapsible details, visual testing

### Notes

append_entry is used heavily by all agents. Readable format will significantly improve logging experience.

---
## Phase 3 — Log Query Tools (read_recent & query_entries)
<!-- ID: phase_3 -->

**Objective:** Implement readable format for log retrieval tools.

**Duration:** 1 week

### Key Tasks

1. **read_recent Tool** (3 days)
   - Add format parameter to read_recent
   - Implement readable format with line-numbered log entries
   - Show pagination info clearly
   - Integration tests for all pagination scenarios

2. **query_entries Tool** (3 days)
   - Add format parameter to query_entries
   - Implement readable format for search results
   - Show filters and result count prominently
   - Integration tests for all query scenarios

3. **Shared Implementation** (1 day)
   - Both tools use `format_readable_log_entries()` helper
   - Ensure consistent output format between tools
   - Test pagination consistency

### Deliverables

- [ ] read_recent with format parameter
- [ ] query_entries with format parameter
- [ ] Consistent readable format for log entries across both tools
- [ ] Integration tests for pagination and filtering

### Acceptance Criteria

- [ ] Log entries line-numbered with emoji, timestamp, agent, message visible
- [ ] Pagination info clear (Page X of Y, Total: N entries)
- [ ] Metadata in footer section
- [ ] All existing tests pass without modification
- [ ] Performance overhead ≤5ms per query

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter readable methods

### Risks & Mitigations

- **Risk:** Large result sets produce overwhelming output
  - **Mitigation:** Pagination limits, visual hierarchy, compact metadata

### Notes

These tools are used for reviewing project progress. Readable format will make log analysis much easier.

---
## Phase 4 — Remaining Tools (Complete Rollout)
<!-- ID: phase_4 -->

**Objective:** Add format parameter to all remaining tools to complete the rollout.

**Duration:** 2 weeks

### Tools in Scope (9 tools)

1. **list_projects** (2 days)
   - Implement ASCII table format for project listing
   - Show status, last entry time, activity metrics
   - Use `format_readable_projects()` helper

2. **get_project** (1 day)
   - Readable format showing current project details
   - Use `format_readable_confirmation()` helper

3. **set_project** (1 day)
   - Readable confirmation of project selection
   - Show project details clearly

4. **manage_docs** (2 days)
   - Readable confirmation of document operations
   - Show section updated, diff summary, verification status

5. **rotate_log** (2 days)
   - Readable confirmation of log rotation
   - Show old/new file paths, entry counts, integrity status

6. **doctor** (2 days)
   - Readable diagnostic output with organized sections
   - Show health checks, warnings, recommendations

7. **generate_doc_templates** (1 day)
   - Readable confirmation showing generated files

8. **delete_project** (1 day)
   - Readable confirmation with safety warnings

9. **health_check** (1 day)
   - Readable health status output

### Key Tasks

- Add format parameter to each tool (consistent signature)
- Implement readable format using appropriate ResponseFormatter method
- Write integration tests for each tool × each format
- Validate backward compatibility for each tool
- Performance testing for each tool

### Deliverables

- [ ] All 14 tools support format parameter
- [ ] Comprehensive integration tests (42+ test cases total)
- [ ] All tools use consistent readable format patterns
- [ ] Complete backward compatibility validation

### Acceptance Criteria

- [ ] All tools accept format parameter with default="structured"
- [ ] Readable format consistent across all tools (header/content/footer pattern)
- [ ] All existing tests pass without modification
- [ ] No performance regressions in any tool
- [ ] Visual validation completed for all readable outputs

### Dependencies

**Phase 0 Complete** - Requires ResponseFormatter infrastructure

### Risks & Mitigations

- **Risk:** Inconsistent readable format across tools
  - **Mitigation:** Centralized ResponseFormatter methods, visual validation

- **Risk:** Tool-specific edge cases break readable format
  - **Mitigation:** Comprehensive integration tests, error handling

### Notes

This phase completes the technical implementation. All tools will support all three formats.

---
## Phase 5 — Documentation & Final Release
<!-- ID: phase_5 -->

**Objective:** Complete documentation, visual validation, and prepare for release.

**Duration:** 1 week

### Key Tasks

1. **Create FORMAT_SPECIFICATION.md** (2 days)
   - Document all three formats (readable, structured, compact)
   - Include visual examples for each tool
   - Document format parameter usage
   - Create format selection decision tree

2. **Update CLAUDE.md** (1 day)
   - Add format parameter to tool reference section
   - Include format usage examples
   - Document best practices for agents

3. **Update Tool Docstrings** (1 day)
   - Add format parameter documentation to all 14 tools
   - Include format examples in each docstring
   - Update type hints if needed

4. **Visual Validation** (2 days)
   - Run test_output_visual.py to generate samples
   - Manual review of all tool outputs in readable format
   - Verify alignment, box drawing, emoji rendering
   - Test at 80, 120, 160 character terminal widths

5. **Performance Validation** (1 day)
   - Run full performance test suite
   - Compare against baseline JSON results
   - Verify no regressions in structured format
   - Document readable format overhead

6. **Final Testing** (1 day)
   - Run complete test suite (unit + integration + performance)
   - Verify 100% backward compatibility
   - Code coverage analysis (target ≥90% for new code)

7. **Release Preparation** (1 day)
   - Update CHANGELOG.md with format feature details
   - Version bump (v2.2.0)
   - Create release notes with format examples
   - Update MCP server guide

### Deliverables

- [ ] FORMAT_SPECIFICATION.md created with comprehensive examples
- [ ] CLAUDE.md updated with format usage guidance
- [ ] All tool docstrings updated
- [ ] Visual validation completed and samples reviewed
- [ ] Performance validation passed
- [ ] Release notes and CHANGELOG.md updated
- [ ] v2.2.0 ready for deployment

### Acceptance Criteria

- [ ] All documentation complete and reviewed
- [ ] Visual samples verified at multiple terminal widths
- [ ] Performance tests pass with no regressions
- [ ] Code coverage ≥90% for new code
- [ ] All existing tests pass without modification
- [ ] Release notes include format examples and migration guide

### Dependencies

**Phase 4 Complete** - All tools must have format parameter before final docs

### Risks & Mitigations

- **Risk:** Documentation incomplete or examples unclear
  - **Mitigation:** Peer review, visual examples, step-by-step usage guide

### Notes

This phase is critical for agent adoption. Clear documentation with visual examples will drive format parameter usage.

---
## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 0 - ResponseFormatter Extended | Week 1 | Coder | ⏳ Planned | Phase 0 acceptance criteria |
| Phase 1 - read_file Complete | Week 2 | Coder | ⏳ Planned | Phase 1 acceptance criteria |
| Phase 2 - append_entry Complete | Week 3 | Coder | ⏳ Planned | Phase 2 acceptance criteria |
| Phase 3 - Log Tools Complete | Week 4 | Coder | ⏳ Planned | Phase 3 acceptance criteria |
| Phase 4 - All Tools Complete | Week 6 | Coder | ⏳ Planned | Phase 4 acceptance criteria |
| Phase 5 - Documentation & Release | Week 7 | Coder + Docs | ⏳ Planned | v2.2.0 release |

**Status Legend:**
- ⏳ Planned
- 🚧 In Progress
- ✅ Complete
- ⚠️ Blocked
- ❌ Failed

---
## Cross-Phase Dependencies
<!-- ID: dependencies -->

```
Phase 0 (Foundation)
    ├─> Phase 1 (read_file)
    ├─> Phase 2 (append_entry)
    ├─> Phase 3 (Log Tools)
    └─> Phase 4 (Remaining Tools)
            └─> Phase 5 (Documentation)
```

**Critical Path:** Phase 0 → Phase 1 → Phase 5

**Parallel Opportunities:**
- Phases 1, 2, 3, 4 can proceed in parallel AFTER Phase 0 completes
- However, sequential execution recommended for risk mitigation and learning

---
## Risk Management
<!-- ID: risk_management -->

### High-Risk Items

1. **Phase 0 Foundation Issues**
   - **Impact:** Blocks all subsequent phases
   - **Probability:** Low (0.1)
   - **Mitigation:** Comprehensive unit tests, early implementation
   - **Contingency:** If blocked, reassess architecture with reduced scope

2. **Performance Degradation**
   - **Impact:** Unacceptable overhead for agents
   - **Probability:** Medium (0.3)
   - **Mitigation:** Performance tests in every phase, optimization as needed
   - **Contingency:** Optimize string building, consider caching, reduce metadata in readable format

3. **Backward Compatibility Break**
   - **Impact:** Breaks existing integrations
   - **Probability:** Low (0.1)
   - **Mitigation:** Default format=structured, comprehensive tests
   - **Contingency:** Immediate rollback, hotfix release

### Medium-Risk Items

1. **Inconsistent Readable Format**
   - **Impact:** Poor agent experience, confusion
   - **Probability:** Medium (0.4)
   - **Mitigation:** Centralized ResponseFormatter, visual validation
   - **Contingency:** Refactor to enforce consistency, update specification

2. **Incomplete Documentation**
   - **Impact:** Low adoption of readable format
   - **Probability:** Low (0.2)
   - **Mitigation:** Dedicated documentation phase, visual examples
   - **Contingency:** Extended Phase 5, community feedback integration

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

*This section will be populated during implementation with lessons learned and scope adjustments.*

**Phase Retrospective Template:**
- What went well?
- What could be improved?
- Scope changes made and why?
- Performance/quality metrics achieved?
- Recommendations for next phase?

---

## Phase 6 — Session-Aware Reminder System (DB Integration)
<!-- ID: phase_6_reminder_system -->

**Objective:** Migrate reminder cooldown tracking from file-based to DB-backed with session isolation and failure-triggered priority.

**Duration:** 3 weeks

**Confidence:** 0.94 (High - infrastructure ready, clear migration path)

### Overview

This phase implements the session-aware reminder system architecture defined in Section 9 of ARCHITECTURE_GUIDE.md. The work proceeds through 7 sequential stages with feature flags for safe rollout and rollback capability.

### Stage 1: Schema Migration (Non-Breaking)
**Duration:** 2 days

**Tasks:**
1. Add `reminder_history` table to `storage/sqlite.py` schema (6 hours)
   - Table definition with 10 columns (id, session_id, reminder_hash, project_root, agent_id, tool_name, reminder_key, shown_at, operation_status, context_metadata)
   - Foreign key constraint: `session_id → scribe_sessions.session_id ON DELETE CASCADE`
   - CHECK constraint: `operation_status IN ('success', 'failure', 'neutral')`

2. Add indexes for query performance (2 hours)
   - `idx_reminder_history_session_hash` (session_id, reminder_hash) - Primary cooldown lookup
   - `idx_reminder_history_shown_at` (shown_at) - TTL cleanup queries
   - `idx_reminder_history_session_tool` (session_id, tool_name) - Analytics queries

3. Write schema migration test (4 hours)
   - `tests/storage/test_sqlite.py::test_reminder_history_schema`
   - Verify table creation, column types, constraints, indexes
   - Verify FK cascade delete behavior

4. Run full test suite (2 hours)
   - Ensure no regressions from schema addition
   - All 69 functional tests must pass

**Deliverables:**
- [ ] `storage/sqlite.py` updated with `reminder_history` table definition
- [ ] 3 indexes created
- [ ] Schema test passes
- [ ] No test regressions

**Acceptance Criteria:**
- [ ] Table created successfully on fresh DB init
- [ ] FK constraint prevents orphaned reminders when session deleted
- [ ] Indexes exist and are used by query planner (verify with EXPLAIN)
- [ ] No breaking changes to existing schema

**Dependencies:** None (adds new table only)

**Risks:**
- **Low Risk:** Schema changes isolated to new table, no existing data affected

---

### Stage 2: Storage Methods Implementation
**Duration:** 3 days

**Tasks:**
1. Implement `upsert_reminder_shown()` method (1 day)
   - Accept 8 parameters (session_id, reminder_hash, project_root, agent_id, tool_name, reminder_key, operation_status, context_metadata)
   - INSERT new row with current UTC timestamp
   - Handle JSON serialization for `context_metadata`
   - Use async/await pattern with connection pooling

2. Implement `check_reminder_cooldown()` method (1 day)
   - Query for COUNT(*) with session_id, reminder_hash, and cutoff timestamp
   - Return True if reminder shown within cooldown window, False otherwise
   - Optimize with index usage (verify with EXPLAIN QUERY PLAN)

3. Implement `cleanup_reminder_history()` method (4 hours)
   - DELETE entries older than cutoff_hours (default: 168 = 7 days)
   - Return count of rows deleted
   - Add to periodic cleanup tasks (future work)

4. Write unit tests (1 day)
   - `tests/storage/test_reminder_storage.py` (new file)
   - Test `upsert_reminder_shown()` with various operation_status values
   - Test `check_reminder_cooldown()` with expired/active cooldowns
   - Test `cleanup_reminder_history()` with mixed old/new entries
   - Test JSON metadata serialization/deserialization

5. Add feature flag to config (2 hours)
   - `config/reminder_config.json`: Add `"use_db_cooldown_tracking": false` (disabled by default)
   - Document flag purpose and migration timeline

**Deliverables:**
- [ ] 3 new storage methods in `storage/sqlite.py`
- [ ] `tests/storage/test_reminder_storage.py` created with 100% coverage
- [ ] Feature flag added to config
- [ ] All new tests passing

**Acceptance Criteria:**
- [ ] `upsert_reminder_shown()` inserts row successfully
- [ ] `check_reminder_cooldown()` returns correct boolean based on timestamps
- [ ] `cleanup_reminder_history()` deletes only old entries, returns accurate count
- [ ] Feature flag defaults to False (file mode)
- [ ] All unit tests pass

**Dependencies:** Stage 1 (schema must exist)

**Risks:**
- **Low Risk:** New methods don't affect existing code until feature flag enabled

---

### Stage 3: Hash Refactoring (Backward Compatible)
**Duration:** 3 days

**Tasks:**
1. Update `_get_reminder_hash()` signature (1 day)
   - Add `session_id: Optional[str] = None` parameter
   - Implement conditional logic: if `session_id` and `use_db_cooldown_tracking=True`, include session_id in hash
   - Legacy mode: Return old format (project|agent|tool|reminder) when feature flag disabled
   - DB mode: Return new format (session|project|agent|tool|reminder) when flag enabled

2. Update hash generation call sites (1 day)
   - `utils/reminder_engine.py::_should_show_reminder()` - Pass `session_id` parameter
   - `utils/reminder_engine.py::generate_reminders()` - Accept and forward `session_id`
   - Maintain backward compatibility: `session_id=None` falls back to file mode

3. Write hash generation tests (1 day)
   - `tests/test_reminder_engine.py::test_hash_generation_db_mode`
   - `tests/test_reminder_engine.py::test_hash_generation_file_mode`
   - `tests/test_reminder_engine.py::test_hash_generation_backward_compat`
   - Verify format switching based on feature flag

4. Run existing reminder tests (4 hours)
   - All existing tests must pass with `use_db_cooldown_tracking=False` (file mode)
   - No behavior changes in legacy mode

**Deliverables:**
- [ ] `_get_reminder_hash()` updated with conditional logic
- [ ] Hash generation tests pass in both modes
- [ ] No regressions in existing reminder tests

**Acceptance Criteria:**
- [ ] File mode hash format: `{project}|{agent}|{tool}|{reminder}` (4 parts)
- [ ] DB mode hash format: `{session}|{project}|{agent}|{tool}|{reminder}` (5 parts)
- [ ] Feature flag correctly controls hash format
- [ ] All 69 functional tests pass with file mode

**Dependencies:** Stage 2 (storage methods exist for testing)

**Risks:**
- **Medium Risk:** Hash format change could break cooldown logic if not properly gated by feature flag
- **Mitigation:** Comprehensive tests in both modes, feature flag default=False

---

### Stage 4: Session Integration
**Duration:** 4 days

**Tasks:**
1. Pass `session_id` from execution context to reminder engine (2 days)
   - Update `reminders.py::get_reminders()` to extract `session_id` from state
   - Update `reminder_engine.py::generate_reminders()` to accept `session_id` parameter
   - Update all tool call sites (append_entry, read_file, etc.) to pass state with session_id

2. Implement `should_reset_reminder_cooldowns()` function (1 day)
   - 3 reset triggers: session ID change, 10-minute idle, 24-hour age
   - Integrate with `get_session_metadata()` for idle/age calculation
   - Clear in-memory `ReminderHistory` dict when reset triggered

3. Add session metadata retrieval (1 day)
   - Implement `get_session_metadata(session_id)` in execution context
   - Query `scribe_sessions` table for `started_at` and `last_active_at`
   - Calculate `session_age_minutes` and `idle_minutes`

4. Write session isolation tests (1 day)
   - `tests/test_reminder_session_isolation.py` (new file)
   - Test same reminder appears in different sessions
   - Test cooldown resets on 10-minute idle
   - Test cooldown resets on session ID change
   - Test 24-hour age cleanup trigger

**Deliverables:**
- [ ] Session ID propagated from execution context to reminder engine
- [ ] `should_reset_reminder_cooldowns()` implemented
- [ ] `get_session_metadata()` implemented
- [ ] Session isolation tests passing

**Acceptance Criteria:**
- [ ] Reminder shown in session1 does NOT suppress in session2
- [ ] Cooldown resets after 10-minute idle period
- [ ] Cooldown resets when session_id changes
- [ ] Long-running sessions (>24h) trigger cleanup

**Dependencies:** Stage 3 (hash generation with session_id)

**Risks:**
- **High Risk:** Session ID might not be available in all code paths
- **Mitigation:** Graceful fallback to file mode if session_id=None, extensive integration testing

---

### Stage 5: Failure Context Propagation
**Duration:** 3 days

**Tasks:**
1. Add `operation_status` parameter to tool try/except blocks (2 days)
   - `tools/append_entry.py` - Wrap main logic in try/except, set operation_status
   - `tools/read_file.py` - Wrap main logic in try/except, set operation_status
   - All 14 tools - Add finally block calling `get_reminders()` with operation_status

2. Update `get_reminders()` signature (1 day)
   - Add `operation_status: str = "neutral"` parameter
   - Pass to `reminder_engine.generate_reminders()`
   - Update docstring with behavior: failure=bypass cooldown, success=respect cooldown

3. Implement failure-priority logic in ReminderEngine (1 day)
   - Update `generate_reminders()` to accept `operation_status`
   - Conditional cooldown check: if `operation_status == "failure"`, set `in_cooldown=False`
   - Maintain max 3 reminders limit even for failures

4. Write failure priority tests (1 day)
   - `tests/test_reminder_failure_priority.py` (new file)
   - Test failure-triggered reminders bypass cooldown
   - Test success-triggered reminders respect cooldown
   - Test neutral status maintains default behavior

**Deliverables:**
- [ ] All 14 tools updated with operation_status parameter
- [ ] `get_reminders()` accepts operation_status
- [ ] Failure-priority logic implemented
- [ ] Failure priority tests passing

**Acceptance Criteria:**
- [ ] Reminder shown once, then suppressed on next success call
- [ ] Same reminder shown again immediately on failure call
- [ ] Max 3 reminders enforced even for failures
- [ ] Neutral status (default) maintains backward compatibility

**Dependencies:** Stage 4 (session integration complete)

**Risks:**
- **Medium Risk:** Failure reminders might cause spam if many consecutive failures
- **Mitigation:** Max 3 reminders per call, cooldown still enforced within session

---

### Stage 6: DB Mode Activation (Production Rollout)
**Duration:** 4 days + 48 hours monitoring

**Tasks:**
1. Set feature flag default to True (2 hours)
   - `config/reminder_config.json`: Change `"use_db_cooldown_tracking": true`
   - Commit with detailed changelog explaining migration

2. Archive file-based cooldown cache (1 hour)
   - Copy `data/reminder_cooldowns.json` to `data/reminder_cooldowns.json.archive`
   - Add timestamp to archive filename
   - Document archive purpose in commit message

3. Run full test suite with DB mode (1 day)
   - All 69 functional tests must pass
   - All new reminder tests must pass
   - Performance tests must validate <5ms query SLA

4. Deploy to production (2 hours)
   - Deploy to staging environment first
   - Monitor for 4 hours in staging
   - Deploy to production if staging clean

5. Monitor production for 48 hours (passive)
   - Watch error logs for reminder-related failures
   - Monitor DB query performance (check <5ms SLA)
   - Verify no regression in reminder delivery rate
   - Be ready for immediate rollback if issues detected

**Deliverables:**
- [ ] Feature flag default changed to True
- [ ] File-based cache archived
- [ ] All tests passing in DB mode
- [ ] Production deployment successful
- [ ] 48-hour monitoring complete with no issues

**Acceptance Criteria:**
- [ ] All tests pass with `use_db_cooldown_tracking=True`
- [ ] DB queries meet <5ms p95 SLA
- [ ] No reminder delivery regressions
- [ ] No increase in error rates
- [ ] Session isolation working in production

**Dependencies:** Stage 5 (all features implemented)

**Risks:**
- **High Risk:** Production issues require immediate rollback
- **Mitigation:** Feature flag rollback available, archived file can be restored
- **Rollback Plan:** Set `use_db_cooldown_tracking=false`, restore archived JSON file, redeploy

---

### Stage 7: Cleanup (Post-Validation)
**Duration:** 2 days (after 2-week production validation)

**Tasks:**
1. Remove file-based cooldown code (1 day)
   - Delete `_load_cooldown_cache()`, `_save_cooldown_cache()`, `_cleanup_cooldown_cache()` methods
   - Remove `_cooldown_cache_path` attribute from ReminderEngine
   - Remove legacy hash generation branch (keep only DB mode)
   - Update class docstrings to reflect DB-only mode

2. Remove feature flag (2 hours)
   - Delete `"use_db_cooldown_tracking"` from `config/reminder_config.json`
   - Remove conditional logic from `_get_reminder_hash()`
   - Simplify to single hash format (session-aware only)

3. Update documentation (4 hours)
   - Update ARCHITECTURE_GUIDE.md to remove "migration" language
   - Update tool documentation to reflect DB-backed reminder system
   - Add session isolation behavior to README

4. Final test suite run (2 hours)
   - All tests pass with simplified code
   - No feature flag references remain
   - Code coverage maintained or improved

**Deliverables:**
- [ ] File-based code removed
- [ ] Feature flag removed
- [ ] Documentation updated
- [ ] All tests passing

**Acceptance Criteria:**
- [ ] No file-based cooldown code remains
- [ ] No feature flag references in codebase
- [ ] Documentation reflects DB-only mode
- [ ] All tests pass
- [ ] Code is simpler and more maintainable

**Dependencies:** Stage 6 + 2 weeks production validation

**Risks:**
- **Low Risk:** Code removal is straightforward after validation period
- **Rollback Plan:** Git revert to pre-cleanup commit if issues discovered

---

### Phase 6 Summary

**Total Duration:** 3 weeks implementation + 2 weeks validation = 5 weeks

**Parallelization Opportunities:**
- Stages 1-3 can have tests written in parallel with implementation
- Stages 4-5 are sequential (session integration must precede failure context)

**Success Metrics:**
- [ ] All functional requirements met (session isolation, failure priority)
- [ ] All performance requirements met (p95 <5ms)
- [ ] All test requirements met (100% coverage of new code)
- [ ] Zero production incidents during rollout
- [ ] Clean migration with rollback plan validated

**Critical Path:** Stage 1 → Stage 2 → Stage 3 → Stage 4 → Stage 5 → Stage 6 → (validation) → Stage 7

**Confidence Level:** 0.94
- Infrastructure ready (scribe_sessions table exists)
- Clear migration strategy with feature flags
- Comprehensive test coverage planned
- Rollback plan defined for each stage

---

**End of Phase Plan**