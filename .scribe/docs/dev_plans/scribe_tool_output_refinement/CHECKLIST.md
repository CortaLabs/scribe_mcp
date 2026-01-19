# ✅ Acceptance Checklist — scribe_tool_output_refinement
**Author:** ArchitectAgent
**Version:** v1.0
**Status:** ready_for_implementation
**Last Updated:** 2026-01-02 14:09:00 UTC

> Comprehensive verification checklist for readable output format implementation across all Scribe MCP tools.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->

- [x] ARCHITECTURE_GUIDE.md complete with all 10 sections (proof: 1000+ lines, 10/10 sections)
- [x] PHASE_PLAN.md complete with 6 phases detailed (proof: 543 lines, phase 0-5)
- [x] CHECKLIST.md created with all phases (proof: this document)
- [ ] Research findings documented (proof: RESEARCH_TOOL_OUTPUT_ANALYSIS_20260102_0853.md)
- [ ] PROGRESS_LOG.md maintained with all design decisions

---
## Phase 0 — Foundation (ResponseFormatter Extension)
<!-- ID: phase_0 -->

### Code Implementation
- [ ] Format constants added to ResponseFormatter (FORMAT_READABLE, FORMAT_STRUCTURED, FORMAT_COMPACT)
- [ ] Helper method: `_add_line_numbers(content, start=1)` implemented
- [ ] Helper method: `_create_header_box(title, metadata)` implemented
- [ ] Helper method: `_create_footer_box(audit_data, reminders)` implemented
- [ ] Helper method: `_format_table(headers, rows)` implemented
- [ ] Core method: `format_readable_file_content(data)` implemented
- [ ] Core method: `format_readable_log_entries(entries, pagination)` implemented
- [ ] Core method: `format_readable_projects(projects, active)` implemented
- [ ] Core method: `format_readable_confirmation(operation, data)` implemented
- [ ] Core method: `format_readable_error(error, context)` implemented
- [ ] Format router: `finalize_tool_response(data, format, tool_name)` implemented

### Testing
- [ ] Unit test file `tests/test_response_formatter.py` created
- [ ] Line numbering tests pass (1, 10, 100, 1000 line files)
- [ ] ASCII box alignment tests pass (80, 120, 160 char widths)
- [ ] Format router tests pass (all format values)
- [ ] Error handling tests pass (invalid format defaults to structured)
- [ ] 100% code coverage achieved for new methods

### Acceptance
- [ ] All unit tests passing (proof: pytest output)
- [ ] No breaking changes to existing ResponseFormatter (proof: existing tests pass)
- [ ] Code review completed and approved
- [ ] Merged to main branch (proof: commit SHA)

---
## Phase 1 — read_file Tool
<!-- ID: phase_1 -->

### Code Implementation
- [ ] Format parameter added: `format: str = "structured"`
- [ ] Type hint updated: `-> Union[Dict[str, Any], str]`
- [ ] Docstring updated with format parameter documentation
- [ ] All 6 modes integrated with format selection:
  - [ ] scan_only mode
  - [ ] chunk mode
  - [ ] line_range mode
  - [ ] page mode
  - [ ] full_stream mode
  - [ ] search mode

### Testing
- [ ] Integration test: `test_read_file_readable_chunk_mode` passing
- [ ] Integration test: `test_read_file_readable_line_range` passing
- [ ] Integration test: `test_read_file_readable_page` passing
- [ ] Integration test: `test_read_file_readable_search` passing
- [ ] Integration test: `test_read_file_readable_full_stream` passing
- [ ] Integration test: `test_read_file_readable_scan_only` passing
- [ ] Backward compatibility: all existing read_file tests pass unchanged
- [ ] Performance benchmark: overhead ≤5ms (proof: test_performance.py results)
- [ ] Memory usage: ≤2x for 10K line file (proof: memory profiler)

### Visual Validation
- [ ] Readable output inspected manually for chunk mode
- [ ] Line numbers right-aligned with arrow separator (→)
- [ ] Header box shows file path, line range, SHA256
- [ ] Content has actual line breaks (not escaped)
- [ ] Footer box shows audit trail and reminders
- [ ] Output looks good at 80 character terminal width

### Acceptance
- [ ] All integration tests passing (proof: pytest output)
- [ ] Performance benchmarks passing (proof: JSON results)
- [ ] Visual validation completed and approved
- [ ] Code review completed and approved
- [ ] Merged to main branch (proof: commit SHA)

---
## Phase 2 — append_entry Tool
<!-- ID: phase_2 -->

### Code Implementation
- [ ] Format parameter added to append_entry signature
- [ ] Single entry mode supports readable format
- [ ] Bulk entry mode supports readable format
- [ ] Error cases formatted readably (partial/complete failures)
- [ ] Type hints updated

### Testing
- [ ] Integration test: `test_append_entry_readable_single` passing
- [ ] Integration test: `test_append_entry_readable_bulk` passing
- [ ] Integration test: `test_append_entry_readable_errors` passing
- [ ] Backward compatibility: existing append_entry tests pass unchanged
- [ ] Performance benchmark: overhead ≤5ms

### Visual Validation
- [ ] Success confirmation shows entry clearly (emoji, timestamp, agent, message)
- [ ] Path and metadata visible in details section
- [ ] Audit trail in footer
- [ ] Bulk mode shows summary + individual entries

### Acceptance
- [ ] All integration tests passing
- [ ] Performance benchmarks passing
- [ ] Visual validation completed
- [ ] Code review approved
- [ ] Merged to main branch

---
## Phase 3 — Log Query Tools
<!-- ID: phase_3 -->

### read_recent Tool
- [ ] Format parameter added
- [ ] Readable format shows line-numbered log entries
- [ ] Pagination info displayed clearly (Page X of Y, Total: N)
- [ ] Integration tests passing
- [ ] Backward compatibility validated

### query_entries Tool
- [ ] Format parameter added
- [ ] Readable format shows search results with line numbers
- [ ] Filters and result count displayed prominently
- [ ] Integration tests passing
- [ ] Backward compatibility validated

### Consistency
- [ ] Both tools use same `format_readable_log_entries()` helper
- [ ] Output format consistent between read_recent and query_entries
- [ ] Pagination format identical

### Acceptance
- [ ] All integration tests passing for both tools
- [ ] Visual validation shows consistency
- [ ] Performance benchmarks passing
- [ ] Code review approved
- [ ] Merged to main branch

---
## Phase 4 — Remaining Tools
<!-- ID: phase_4 -->

### list_projects Tool
- [ ] Format parameter added
- [ ] ASCII table format implemented (headers + rows)
- [ ] Status, last entry time, activity metrics visible
- [ ] Active project highlighted
- [ ] Tests passing

### get_project Tool
- [ ] Format parameter added
- [ ] Readable format shows project details
- [ ] Tests passing

### set_project Tool
- [ ] Format parameter added
- [ ] Readable confirmation of project selection
- [ ] Tests passing

### manage_docs Tool
- [ ] Format parameter added
- [ ] Readable confirmation shows section updated, diff summary
- [ ] Tests passing

### rotate_log Tool
- [ ] Format parameter added
- [ ] Readable confirmation shows old/new paths, entry counts, integrity
- [ ] Tests passing

### doctor Tool
- [ ] Format parameter added
- [ ] Readable diagnostic output with organized sections
- [ ] Tests passing

### generate_doc_templates Tool
- [ ] Format parameter added
- [ ] Readable confirmation shows generated files
- [ ] Tests passing

### delete_project Tool
- [ ] Format parameter added
- [ ] Readable confirmation with safety warnings
- [ ] Tests passing

### health_check Tool
- [ ] Format parameter added
- [ ] Readable health status output
- [ ] Tests passing

### Comprehensive Validation
- [ ] All 14 tools support format parameter
- [ ] All tools accept default format="structured"
- [ ] All tools return correct type (Dict for structured, str for readable)
- [ ] Integration tests: 42+ test cases (14 tools × 3 formats minimum)
- [ ] All existing tests pass without modification
- [ ] Visual validation completed for all tools
- [ ] Performance benchmarks passing for all tools

### Acceptance
- [ ] All integration tests passing (42+ test cases)
- [ ] All existing tests passing (100% backward compatibility)
- [ ] Visual validation approved for all tools
- [ ] Performance benchmarks passing
- [ ] Code review approved
- [ ] Merged to main branch

---
## Phase 5 — Documentation & Final Release
<!-- ID: phase_5 -->

### Documentation
- [ ] FORMAT_SPECIFICATION.md created with:
  - [ ] All three formats documented (readable, structured, compact)
  - [ ] Visual examples for each tool
  - [ ] Format parameter usage guide
  - [ ] Format selection decision tree
- [ ] CLAUDE.md updated with:
  - [ ] Format parameter in tool reference section
  - [ ] Format usage examples
  - [ ] Best practices for agents
- [ ] Tool docstrings updated:
  - [ ] All 14 tools have format parameter documented
  - [ ] Format examples in each docstring
  - [ ] Type hints correct

### Visual Validation
- [ ] `test_output_visual.py` executed to generate samples
- [ ] Manual review completed for all tool outputs:
  - [ ] read_file readable sample
  - [ ] append_entry readable sample
  - [ ] read_recent readable sample
  - [ ] list_projects readable sample
  - [ ] All remaining tools
- [ ] Alignment verified at 80, 120, 160 character widths
- [ ] Box drawing characters form continuous borders
- [ ] Emoji render correctly
- [ ] No text wrapping issues

### Performance Validation
- [ ] Full performance test suite executed
- [ ] Results compared against baseline JSON files
- [ ] No regressions in structured format performance
- [ ] Readable format overhead documented:
  - [ ] read_file: ≤5ms overhead
  - [ ] append_entry: ≤5ms overhead
  - [ ] read_recent: ≤5ms overhead
  - [ ] All other tools: ≤5ms overhead

### Final Testing
- [ ] Complete test suite executed (unit + integration + performance)
- [ ] All tests passing:
  - [ ] Unit tests: 100% for new code
  - [ ] Integration tests: 42+ test cases
  - [ ] Performance tests: all benchmarks passing
  - [ ] Backward compatibility: 100% existing tests passing
- [ ] Code coverage analysis: ≥90% for new code (proof: coverage report)

### Release Preparation
- [ ] CHANGELOG.md updated with:
  - [ ] v2.2.0 entry
  - [ ] Format feature description
  - [ ] Usage examples
  - [ ] Migration guide (none needed - backward compatible)
- [ ] Release notes created with:
  - [ ] Feature summary
  - [ ] Format examples
  - [ ] Performance impact documentation
  - [ ] Links to FORMAT_SPECIFICATION.md
- [ ] Version bump to v2.2.0 (proof: version file updated)
- [ ] MCP server guide updated (if needed)

### Acceptance
- [ ] All documentation reviewed and approved
- [ ] All visual samples verified and approved
- [ ] All performance tests passing
- [ ] All test suites passing (100% backward compatibility)
- [ ] Code coverage ≥90%
- [ ] Release notes approved
- [ ] v2.2.0 ready for deployment

---
## Final Verification
<!-- ID: final_verification -->

### Quality Gates
- [ ] All 6 phases completed with acceptance criteria met
- [ ] All checklist items above checked with proofs attached
- [ ] Zero breaking changes introduced (verified by test suite)
- [ ] Performance targets met (≤5ms overhead, ≤2x memory)
- [ ] Documentation complete and reviewed
- [ ] Code review approved by team
- [ ] Stakeholder sign-off recorded (name + date)

### Deployment Readiness
- [ ] All tests passing in CI/CD pipeline
- [ ] No critical or high-severity bugs open
- [ ] Rollback plan documented and tested
- [ ] Monitoring dashboards ready for format usage tracking
- [ ] Support team trained on new format parameter

### Post-Deployment
- [ ] Format usage metrics being tracked
- [ ] Agent feedback being collected
- [ ] Performance monitoring active
- [ ] No critical issues reported in first week
- [ ] Retro completed and lessons learned documented

---
## Proof Requirements

Each checklist item must have verifiable proof:

- **Code items:** Commit SHA or file reference
- **Test items:** pytest output or CI build number
- **Performance items:** Benchmark JSON results file
- **Visual items:** Screenshots or sample output files
- **Documentation items:** File reference or PR number
- **Review items:** PR approval or review comment link
- **Deployment items:** Release tag or deployment log

Example proof format:
```
- [x] Unit tests passing (proof: pytest run 2026-01-02, all 150 tests passed, commit abc123)
```

---
## Success Criteria Summary

**Project is complete when:**

1. ✅ All 14 tools support format parameter with default="structured"
2. ✅ All tools produce readable output with format="readable"
3. ✅ All existing tests pass without modification (100% backward compatibility)
4. ✅ Performance overhead ≤5ms for readable format
5. ✅ Memory usage ≤2x for large files
6. ✅ Code coverage ≥90% for new code
7. ✅ Documentation complete (ARCHITECTURE, PHASE_PLAN, FORMAT_SPECIFICATION)
8. ✅ Visual validation passed for all tools
9. ✅ Release v2.2.0 deployed successfully
10. ✅ No critical bugs reported in first week of production use
11. ✅ Session-aware reminder system deployed (Phase 6 complete)

---

## Phase 6 — Session-Aware Reminder System (DB Integration)
<!-- ID: phase_6 -->

### Stage 1: Schema Migration (Non-Breaking)

#### Code Implementation
- [ ] `reminder_history` table added to `storage/sqlite.py` schema
- [ ] Table has 10 columns: id, session_id, reminder_hash, project_root, agent_id, tool_name, reminder_key, shown_at, operation_status, context_metadata
- [ ] Foreign key constraint: `session_id → scribe_sessions.session_id ON DELETE CASCADE`
- [ ] CHECK constraint: `operation_status IN ('success', 'failure', 'neutral')`
- [ ] Index created: `idx_reminder_history_session_hash` (session_id, reminder_hash)
- [ ] Index created: `idx_reminder_history_shown_at` (shown_at)
- [ ] Index created: `idx_reminder_history_session_tool` (session_id, tool_name)

#### Testing
- [ ] Schema test: `tests/storage/test_sqlite.py::test_reminder_history_schema` passing
- [ ] Table creation verified on fresh DB init
- [ ] FK cascade delete verified (delete session → reminders deleted)
- [ ] Indexes verified with `EXPLAIN QUERY PLAN` (proof: query plan output)
- [ ] All 69 existing functional tests pass unchanged

#### Acceptance
- [ ] Schema migration complete (proof: pytest output)
- [ ] No regressions in existing tests (proof: full test suite passes)
- [ ] Code review approved (proof: PR approval)
- [ ] Merged to main (proof: commit SHA)

---

### Stage 2: Storage Methods Implementation

#### Code Implementation
- [ ] Method implemented: `SQLiteStorage.upsert_reminder_shown(session_id, reminder_hash, project_root, agent_id, tool_name, reminder_key, operation_status, context_metadata)`
- [ ] Method implemented: `SQLiteStorage.check_reminder_cooldown(session_id, reminder_hash, cooldown_minutes) -> bool`
- [ ] Method implemented: `SQLiteStorage.cleanup_reminder_history(cutoff_hours) -> int`
- [ ] JSON serialization for context_metadata handled correctly
- [ ] Async/await pattern with connection pooling used
- [ ] Feature flag added: `config/reminder_config.json` → `"use_db_cooldown_tracking": false`

#### Testing
- [ ] Test file created: `tests/storage/test_reminder_storage.py`
- [ ] Test: `test_upsert_reminder_shown_success` passing
- [ ] Test: `test_upsert_reminder_shown_with_metadata` passing
- [ ] Test: `test_check_reminder_cooldown_active` passing
- [ ] Test: `test_check_reminder_cooldown_expired` passing
- [ ] Test: `test_cleanup_reminder_history` passing
- [ ] Test: `test_cleanup_preserves_recent_entries` passing
- [ ] 100% code coverage for new storage methods

#### Acceptance
- [ ] All storage method tests passing (proof: pytest output)
- [ ] Feature flag defaults to False (proof: config file content)
- [ ] Code review approved (proof: PR approval)
- [ ] Merged to main (proof: commit SHA)

---

### Stage 3: Hash Refactoring (Backward Compatible)

#### Code Implementation
- [ ] `_get_reminder_hash()` signature updated: `session_id: Optional[str] = None` parameter added
- [ ] Conditional logic implemented: DB mode (5-part hash) vs File mode (4-part hash)
- [ ] DB mode hash format: `{session_id}|{project_root}|{agent_id}|{tool_name}|{reminder_key}`
- [ ] File mode hash format: `{project_root}|{agent_id}|{tool_name}|{reminder_key}` (legacy)
- [ ] Hash generation call sites updated to pass `session_id`
- [ ] `generate_reminders()` accepts and forwards `session_id` parameter

#### Testing
- [ ] Test: `test_hash_generation_db_mode` passing (5-part hash with session_id)
- [ ] Test: `test_hash_generation_file_mode` passing (4-part hash without session_id)
- [ ] Test: `test_hash_generation_backward_compat` passing (session_id=None → file mode)
- [ ] Test: `test_hash_format_switches_with_feature_flag` passing
- [ ] All existing reminder tests pass with `use_db_cooldown_tracking=False`

#### Acceptance
- [ ] Hash generation tests all passing (proof: pytest output)
- [ ] No regressions in existing tests (proof: all 69 tests pass)
- [ ] Code review approved (proof: PR approval)
- [ ] Merged to main (proof: commit SHA)

---

### Stage 4: Session Integration

#### Code Implementation
- [ ] `reminders.py::get_reminders()` extracts `session_id` from state
- [ ] `reminder_engine.py::generate_reminders()` accepts `session_id` parameter
- [ ] All tool call sites updated to pass state with session_id
- [ ] Function implemented: `should_reset_reminder_cooldowns(current_session_id, last_session_id, session_age_minutes, idle_minutes) -> bool`
- [ ] 3 reset triggers implemented: session ID change, 10-minute idle, 24-hour age
- [ ] Function implemented: `get_session_metadata(session_id) -> Dict[str, Any]`
- [ ] Session metadata queries `scribe_sessions` table for timestamps
- [ ] In-memory `ReminderHistory` dict cleared on reset

#### Testing
- [ ] Test file created: `tests/test_reminder_session_isolation.py`
- [ ] Test: `test_reminder_appears_in_different_sessions` passing
- [ ] Test: `test_cooldown_resets_on_10min_idle` passing
- [ ] Test: `test_cooldown_resets_on_session_change` passing
- [ ] Test: `test_cooldown_resets_on_24hour_age` passing
- [ ] Test: `test_session_metadata_calculation` passing

#### Acceptance
- [ ] Session isolation tests all passing (proof: pytest output)
- [ ] Same reminder appears in session1 and session2 (proof: test output)
- [ ] Cooldowns reset properly on idle/session change (proof: test output)
- [ ] Code review approved (proof: PR approval)
- [ ] Merged to main (proof: commit SHA)

---

### Stage 5: Failure Context Propagation

#### Code Implementation
- [ ] Tool updated: `tools/append_entry.py` - try/except/finally with operation_status
- [ ] Tool updated: `tools/read_file.py` - try/except/finally with operation_status
- [ ] All 14 tools updated with operation_status tracking
- [ ] `get_reminders()` signature updated: `operation_status: str = "neutral"` parameter
- [ ] `reminder_engine.generate_reminders()` accepts operation_status parameter
- [ ] Failure-priority logic implemented: `if operation_status == "failure": in_cooldown = False`
- [ ] Max 3 reminders limit enforced even for failures

#### Testing
- [ ] Test file created: `tests/test_reminder_failure_priority.py`
- [ ] Test: `test_failure_bypasses_cooldown` passing
- [ ] Test: `test_success_respects_cooldown` passing
- [ ] Test: `test_neutral_maintains_default_behavior` passing
- [ ] Test: `test_max_3_reminders_even_on_failure` passing
- [ ] Test: `test_operation_status_propagation` passing

#### Acceptance
- [ ] Failure priority tests all passing (proof: pytest output)
- [ ] Failure reminders bypass cooldown (proof: test output)
- [ ] Success reminders respect cooldown (proof: test output)
- [ ] Code review approved (proof: PR approval)
- [ ] Merged to main (proof: commit SHA)

---

### Stage 6: DB Mode Activation (Production Rollout)

#### Pre-Deployment
- [ ] Feature flag changed: `config/reminder_config.json` → `"use_db_cooldown_tracking": true`
- [ ] File archived: `data/reminder_cooldowns.json` → `data/reminder_cooldowns.json.archive-{timestamp}`
- [ ] All 69 functional tests pass with DB mode enabled
- [ ] All new reminder tests pass with DB mode enabled
- [ ] Performance test: cooldown check <5ms p95 (proof: perf test results)
- [ ] Performance test: reminder insert <3ms p95 (proof: perf test results)

#### Deployment
- [ ] Deployed to staging environment (proof: deployment log)
- [ ] Staging monitored for 4 hours (proof: monitoring dashboard)
- [ ] No errors in staging (proof: error log review)
- [ ] Deployed to production (proof: deployment log, timestamp)

#### Post-Deployment Monitoring (48 hours)
- [ ] Error logs reviewed - no reminder-related failures (proof: log analysis)
- [ ] DB query performance monitored - <5ms p95 maintained (proof: metrics dashboard)
- [ ] Reminder delivery rate stable - no regressions (proof: analytics)
- [ ] Session isolation verified in production (proof: DB query showing different sessions)

#### Acceptance
- [ ] Production deployment successful (proof: deployment log)
- [ ] 48-hour monitoring complete with no issues (proof: monitoring report)
- [ ] Performance SLAs met (proof: metrics dashboard)
- [ ] No rollback required (proof: deployment remains active)

---

### Stage 7: Cleanup (Post-Validation)

**Note:** This stage occurs 2 weeks after Stage 6 deployment

#### Code Cleanup
- [ ] Method removed: `ReminderEngine._load_cooldown_cache()`
- [ ] Method removed: `ReminderEngine._save_cooldown_cache()`
- [ ] Method removed: `ReminderEngine._cleanup_cooldown_cache()`
- [ ] Attribute removed: `ReminderEngine._cooldown_cache_path`
- [ ] Feature flag removed: `config/reminder_config.json` → `use_db_cooldown_tracking` deleted
- [ ] Conditional logic removed: `_get_reminder_hash()` simplified to DB mode only
- [ ] Docstrings updated to reflect DB-only mode

#### Documentation
- [ ] ARCHITECTURE_GUIDE.md updated - migration language removed
- [ ] Tool documentation updated - DB-backed reminder system documented
- [ ] README updated - session isolation behavior added
- [ ] Migration complete announcement published

#### Testing
- [ ] All tests pass with simplified code (proof: pytest output)
- [ ] No feature flag references remain in codebase (proof: grep search)
- [ ] Code coverage maintained or improved (proof: coverage report)

#### Acceptance
- [ ] File-based code fully removed (proof: code review)
- [ ] Feature flag fully removed (proof: config file review)
- [ ] Documentation complete (proof: doc review)
- [ ] All tests passing (proof: pytest output)
- [ ] Code is simpler and more maintainable (proof: LOC reduction, cyclomatic complexity)

---

## Phase 6 Success Criteria

**Functional Requirements:**
- [ ] Reminders reset when `session_id` changes
- [ ] Reminders reset after 10-minute idle period
- [ ] Same reminder can appear in different sessions for same project+agent+tool
- [ ] Failure-triggered reminders bypass cooldown within session
- [ ] Success-triggered reminders respect standard cooldown
- [ ] Session isolation working in production

**Performance Requirements:**
- [ ] Cooldown check queries: <5ms (p95) (proof: performance test results)
- [ ] Reminder insert operations: <3ms (p95) (proof: performance test results)
- [ ] TTL cleanup: <100ms for 10k rows (proof: cleanup test results)
- [ ] No memory leaks: stable after 24-hour run (proof: memory profiler)

**Testing Requirements:**
- [ ] All existing reminder tests pass unchanged (proof: pytest output)
- [ ] Session isolation tests verify cross-session behavior (proof: test output)
- [ ] Failure priority tests confirm cooldown bypass (proof: test output)
- [ ] Performance tests validate query SLAs (proof: perf test JSON results)
- [ ] Integration tests cover all tool integration points (proof: test coverage report)

**Documentation Requirements:**
- [ ] ARCHITECTURE_GUIDE.md Section 9 complete (proof: 612 lines added)
- [ ] PHASE_PLAN.md Phase 6 complete (proof: 7 stages documented)
- [ ] CHECKLIST.md Phase 6 complete (proof: this section)
- [ ] All architectural decisions logged (proof: PROGRESS_LOG.md entries)

**Deployment Requirements:**
- [ ] Zero production incidents during rollout (proof: incident log)
- [ ] Clean migration with rollback plan validated (proof: rollback test in staging)
- [ ] 2-week production validation complete (proof: monitoring report)
- [ ] File-based code removed after validation (proof: git log)

---

**End of Checklist**