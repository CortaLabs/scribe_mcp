---
id: scribe_codebase_audit-checklist
title: "\u2705 Acceptance Checklist \u2014 scribe_codebase_audit"
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — scribe_codebase_audit
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-23 05:07:16 UTC

> Acceptance checklist for scribe_codebase_audit.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
### Documentation Status
- [x] ARCHITECTURE_GUIDE.md updated with cleanup design (proof: manage_docs updates)
- [x] PHASE_PLAN.md created with 6 phases, 17 task packages (proof: manage_docs updates)
- [x] CHECKLIST.md created with acceptance criteria (proof: this document)
- [x] Research documents reviewed and claims verified (proof: PROGRESS_LOG entries)

### Research Verification
- [x] Connection pooling gap verified (proof: storage/sqlite.py:1568-1622)
- [x] state.json dual-write verified (proof: state/manager.py:115-156)
- [x] ResponseFormatter size verified (proof: utils/response.py:57-2990, 2934 lines)
- [x] Reminder system confirmed production-ready - NO CHANGES (proof: RESEARCH_REMINDER_SYSTEM.md)
<!-- ID: phase_0 -->
**Effort:** 1-2 hours | **Priority:** HIGH | **Risk:** Low

### Task 1.1: Add Agent Index
- [ ] Add `idx_entries_agent_ts` index to _initialise() (proof: code diff)
- [ ] Server starts without errors (proof: manual test)
- [ ] EXPLAIN shows index usage for agent queries (proof: query plan)

### Task 1.2: Add Emoji Index  
- [ ] Add `idx_entries_emoji_ts` index (proof: code diff)
- [ ] EXPLAIN shows index usage for emoji queries (proof: query plan)

### Task 1.3: Add Log Type and Repo Indexes
- [ ] Add `idx_entries_logtype_ts` index (proof: code diff)
- [ ] Add `idx_projects_repo` index (proof: code diff)
- [ ] All 4 indexes visible in PRAGMA output (proof: query output)
- [ ] All existing tests pass (proof: pytest output)

### Phase 1 Complete
- [ ] All 4 indexes created
- [ ] No test regressions
- [ ] Query performance improved for filtered queries

---

## Phase 2: Connection Pooling
<!-- ID: phase_2 -->

**Effort:** 1-2 weeks | **Priority:** CRITICAL | **Risk:** Medium

### Task 2.1: Create Connection Pool Module
- [ ] Create `storage/pool.py` with SQLiteConnectionPool class (proof: file exists)
- [ ] Pool respects min/max size configuration (proof: unit test)
- [ ] Thread-safe acquire/release (proof: concurrency test)
- [ ] close_all() properly cleans up (proof: unit test)

### Task 2.2: Integrate Pool with SQLiteStorage
- [ ] Replace _connect() with pool.acquire() in 4 sync methods (proof: code diff)
- [ ] Add pool initialization in setup() (proof: code diff)
- [ ] All existing tests pass (proof: pytest output)

### Task 2.3: Add Pool Lifecycle to Server
- [ ] Add close() method to SQLiteStorage (proof: code diff)
- [ ] Register shutdown handler in server.py (proof: code diff)
- [ ] Clean shutdown with no warnings (proof: manual test)

### Task 2.4: Benchmark and Validate
- [ ] Create benchmark script (proof: tests/benchmark_connection_pool.py)
- [ ] Document baseline latency (proof: benchmark output)
- [ ] Document improvement (50-80% target) (proof: benchmark output)

### Phase 2 Complete
- [ ] SQLiteConnectionPool module complete
- [ ] All tests pass
- [ ] 50-80% latency improvement documented

---

## Phase 3: state.json Elimination
<!-- ID: phase_3 -->

**Effort:** 1 week | **Priority:** HIGH | **Risk:** Medium

### Task 3.1: Add Database Columns
- [ ] Add recent_tools column to agent_sessions (proof: PRAGMA output)
- [ ] Add session_started_at column (proof: PRAGMA output)
- [ ] Add last_activity_at column (proof: PRAGMA output)

### Task 3.2: Add Storage Methods
- [ ] Add update_session_activity() to StorageBackend (proof: code diff)
- [ ] Implement in SQLiteStorage (proof: code diff)
- [ ] Unit tests for new method (proof: pytest output)

### Task 3.3: Dual-Write Transition
- [ ] record_tool() writes to database (proof: code diff)
- [ ] Deprecation warning logged on state.json access (proof: log output)
- [ ] All functionality preserved (proof: integration tests)

### Task 3.4: Database-Only Mode
- [ ] Remove state.json writes from record_tool() (proof: code diff)
- [ ] Read-only fallback for old data (proof: code diff)
- [ ] Zero file I/O on hot path (proof: profiling)

### Phase 3 Complete
- [ ] All state.json fields in database
- [ ] No state.json writes on record_tool()
- [ ] Backward compatibility maintained

---

## Phase 4: Data Retention
<!-- ID: phase_4 -->

**Effort:** 3-4 days | **Priority:** MEDIUM | **Risk:** Low

### Task 4.1: Create Archive Table
- [ ] Create scribe_entries_archive table (proof: PRAGMA output)
- [ ] Schema matches entries table + archived_at (proof: schema compare)

### Task 4.2: Implement Cleanup Method
- [ ] Add cleanup_old_entries() to StorageBackend (proof: code diff)
- [ ] Implement archive-then-delete pattern (proof: code diff)
- [ ] Unit tests for cleanup (proof: pytest output)
- [ ] Works with project_id filter (proof: unit test)

### Task 4.3: Add Scheduled Cleanup
- [ ] Call cleanup on server startup (proof: code diff)
- [ ] Configurable retention period (proof: config schema)
- [ ] Cleanup logged (proof: server logs)

### Phase 4 Complete
- [ ] Archive table functional
- [ ] Cleanup runs on startup
- [ ] 90-day default retention

---

## Phase 5: ResponseFormatter Decomposition
<!-- ID: phase_5 -->

**Effort:** 2-3 weeks | **Priority:** LOW | **Risk:** Medium

### Task 5.1: Create Base Formatter Module
- [ ] Create utils/formatters/ directory (proof: directory exists)
- [ ] Create base.py with BaseFormatter (proof: file exists)
- [ ] Extract color utilities (proof: code diff)

### Task 5.2: Create UI Formatter Module
- [ ] Create ui.py with UIFormatter (proof: file exists)
- [ ] Extract header/footer box methods (proof: code diff)
- [ ] Unit tests for UI formatter (proof: pytest output)

### Task 5.3: Create Domain Formatters
- [ ] Create entry.py with EntryFormatter (proof: file exists)
- [ ] Create file.py with FileFormatter (proof: file exists)
- [ ] Create project.py with ProjectFormatter (proof: file exists)
- [ ] Create query.py with QueryFormatter (proof: file exists)
- [ ] Unit tests for each formatter (proof: pytest output)

### Task 5.4: Create Dispatcher and Facade
- [ ] Create dispatcher.py with FormatterDispatcher (proof: file exists)
- [ ] Update response.py as facade (proof: code diff)
- [ ] ResponseFormatter API unchanged (proof: integration tests)
- [ ] ResponseFormatter slimmed to ~200 lines (proof: wc -l)

### Phase 5 Complete
- [ ] 7 new formatter modules created
- [ ] response.py is thin facade
- [ ] Zero API breaking changes
- [ ] All tests pass

---

## Phase 6: Startup Optimization
<!-- ID: phase_6 -->

**Effort:** 1 week | **Priority:** LOW | **Risk:** Low

### Task 6.1: Lazy Journal Replay
- [ ] Move journal replay to background task (proof: code diff)
- [ ] Server responds immediately after startup (proof: timing)
- [ ] Journals still replayed (proof: verification)

### Task 6.2: Skip Completed Migrations
- [ ] Create scribe_migrations table (proof: PRAGMA output)
- [ ] Migrations tracked (proof: table contents)
- [ ] Migrations skip when complete (proof: logs)

### Task 6.3: Lazy Config Loading
- [ ] Config loaded on first access (proof: code diff)
- [ ] No import-time loading (proof: profiling)

### Phase 6 Complete
- [ ] Background journal replay
- [ ] Migrations tracked
- [ ] Startup time measurably improved
<!-- ID: final_verification -->
### Overall Completion
- [ ] All 6 phases completed
- [ ] All 17 task packages executed
- [ ] All tests passing (proof: full pytest output)
- [ ] Performance improvements documented

### Performance Metrics
- [ ] Database query latency reduced 50-80% (proof: benchmark)
- [ ] Zero file I/O on record_tool hot path (proof: profiling)
- [ ] Startup time improved (proof: timing)

### Code Quality
- [ ] ResponseFormatter reduced from 2,934 to ~200 lines (proof: wc -l)
- [ ] No breaking changes to public API (proof: integration tests)
- [ ] New code follows existing patterns (proof: code review)

### Documentation
- [ ] All phases documented in PROGRESS_LOG.md
- [ ] Architecture decisions recorded
- [ ] Lessons learned captured in retro notes

### Sign-off
- [ ] Review Agent grade >= 93% (proof: review report)
- [ ] Stakeholder sign-off recorded (name + date)
- [ ] All blockers resolved

---

## Explicitly Out of Scope
<!-- ID: out_of_scope -->

The following items are EXPLICITLY NOT part of this cleanup:

- **Reminder System** - Confirmed production-ready, zero technical debt (RESEARCH_REMINDER_SYSTEM.md)
- **PostgreSQL completion** - Recommend deprecation, focus on SQLite optimization
- **New features** - This is cleanup only
- **read_file security changes** - Intentional design for external access (standardize, not restrict)
- **Breaking API changes** - All changes must be backward compatible
