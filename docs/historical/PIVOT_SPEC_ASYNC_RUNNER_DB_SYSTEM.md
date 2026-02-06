# Project Pivot Specification: Async Background Task Runner & Database System Refactor

**Date:** 2026-01-05
**Status:** Planning Phase
**Priority:** High - Infrastructure Foundation

---

## 🎯 Executive Summary

The SQL tool logging implementation revealed a fundamental infrastructure gap in Scribe MCP: **lack of systematic async background task management**. While attempting to fix tool logging, we discovered that MCP server context requires proper background task orchestration that current patterns don't provide.

This pivot creates a **NEW PROJECT** focused on:
1. **Async Background Task Runner Service** - Standardized background task execution for MCP
2. **Enhanced scribe_doctor Tool** - Full database observation and live query system
3. **Database System Refactor** - Modularize scattered DB logic into clean services

---

## 🔴 Current Problem: SQL Tool Logging Failure

### The Issue
**Symptom:**
- JSONL tool logging works (130+ entries)
- SQL tool logging fails (0 rows in database)
- Background tasks created but never execute

### Root Cause (98% Confidence)
`asyncio.create_task()` creates **weak references**. When tasks are created inside tool functions (local scope), they are **garbage collected** when the function returns, canceling the task before execution.

**Evidence:**
- Research conducted: 18 web searches, official Python docs analysis
- Pattern identified: Fire-and-forget tasks need strong references
- Attempted Fix 1: `asyncio.create_task(asyncio.to_thread(...))` - Still orphaned
- Attempted Fix 2: `await asyncio.to_thread(...)` - Blocks every tool call (REJECTED)
- Attempted Fix 3: Module-level `background_tasks = set()` pattern - **Implemented but untested**

### Why This Matters
**SQL logging is just the first use case.** Any future background operations in MCP will face this same problem:
- Analytics collection
- Metrics aggregation
- Audit trail writing
- Cache invalidation
- Notification systems
- Health checks

**We need a systematic solution, not one-off hacks.**

---

## 🎯 What We Want: Three-Pillar Solution

### Pillar 1: Async Background Task Runner Service

**Goal:** Standardized, reliable background task execution for MCP server context.

**Requirements:**
- ✅ **Non-blocking** - Tasks execute in background without delaying tool responses
- ✅ **Guaranteed Execution** - Tasks complete before server shutdown
- ✅ **No Garbage Collection** - Strong references prevent premature cancellation
- ✅ **Automatic Cleanup** - Completed tasks removed to prevent memory leaks
- ✅ **Error Handling** - Background failures don't crash the server
- ✅ **Observable** - Can monitor active tasks, completion rates, failures
- ✅ **Thread-Safe** - Supports both async coroutines and sync thread pool execution

**API Design (Proposed):**
```python
# Simple fire-and-forget
background_runner.submit_async(some_coroutine())
background_runner.submit_sync(some_function, arg1, arg2)

# With callbacks
background_runner.submit_async(
    task=some_coroutine(),
    on_success=lambda result: log.info(f"Done: {result}"),
    on_failure=lambda error: log.error(f"Failed: {error}")
)

# Observable state
stats = background_runner.get_stats()
# Returns: {active: 3, completed: 147, failed: 2, avg_duration_ms: 12.5}
```

**Architecture Considerations:**
- Should this be a singleton service or per-component?
- How does it integrate with MCP server lifecycle?
- What happens to pending tasks during graceful shutdown?
- Do we need priority queues for different task types?
- Should we support task cancellation/timeout?

### Pillar 2: Enhanced scribe_doctor Tool

**Goal:** Comprehensive database observation and live query capabilities.

**Current scribe_doctor Capabilities:**
- Basic diagnostics (repo root, config paths)
- Plugin status check
- Vector readiness check

**NEW Capabilities Needed:**

#### 2.1 Full Database Schema Inspection
```python
scribe_doctor --db-schema
# Shows all tables, columns, indexes, constraints
# Validates schema matches expected structure
# Identifies missing tables or migrations
```

#### 2.2 Live Database Queries
```python
scribe_doctor --query "SELECT COUNT(*) FROM tool_calls"
scribe_doctor --query-preset "recent_tool_calls"
scribe_doctor --query-preset "active_sessions"
scribe_doctor --query-preset "db_health"
```

#### 2.3 Database Health Monitoring
```python
scribe_doctor --db-health
# Returns:
# - Table sizes and row counts
# - Index usage statistics
# - WAL file status
# - Locked tables
# - Slow queries (if logging enabled)
# - Integrity check status
```

#### 2.4 Background Task Monitoring
```python
scribe_doctor --tasks
# Returns:
# - Active background tasks
# - Task queue depth
# - Completion rates
# - Failure rates and error types
# - Average execution times
```

#### 2.5 Real-Time Observation Mode
```python
scribe_doctor --watch
# Live-updating dashboard showing:
# - Active tool calls
# - Background task activity
# - Database write rates
# - Error rates
# - Session count
```

### Pillar 3: Database System Refactor

**Goal:** Modularize scattered database logic into clean, maintainable services.

**Current State Issues:**
- Tool logging logic scattered across `utils/response.py`, `utils/tool_logger.py`, `storage/sqlite.py`
- Reminder system DB logic mixed with business logic
- Session management spread across multiple files
- No clear separation between storage layer and business logic
- Hard to test DB operations in isolation

**Refactor Scope:**

#### 3.1 Create Clean Service Layer
```
storage/
├── base.py              # Abstract storage interface (existing)
├── sqlite.py            # SQLite implementation (refactored)
├── postgres.py          # PostgreSQL implementation (existing)
├── services/            # NEW: Service layer
│   ├── tool_logging.py      # Tool call logging service
│   ├── session_mgmt.py      # Session management service
│   ├── reminder_mgmt.py     # Reminder system service
│   ├── project_mgmt.py      # Project CRUD service
│   └── metrics.py           # Analytics/metrics service
└── migrations/          # NEW: Database migrations
    ├── 001_initial.sql
    ├── 002_tool_calls.sql
    └── 003_reminder_history.sql
```

#### 3.2 Separate Concerns
- **Storage Layer** - Low-level database operations (INSERT, UPDATE, SELECT)
- **Service Layer** - Business logic (when to log, what to track, validation)
- **Integration Layer** - How services connect to tools (utils/response.py)

#### 3.3 Make Testing Easier
- Each service should be testable in isolation
- Mock database connections for unit tests
- Integration tests verify end-to-end flow
- Test fixtures for common DB states

---

## 📋 Implementation Phases

### Phase 1: Research & Architecture (NEW PROJECT)
**Estimated Time:** 2-3 hours
**Deliverables:**
- Complete architecture for Async Background Task Runner Service
- scribe_doctor enhancement specification
- Database refactor migration plan
- API design and contracts

### Phase 2: Async Runner Service Implementation
**Estimated Time:** 4-6 hours
**Deliverables:**
- Functional background task runner
- Integration with existing server.py
- Test suite validating non-blocking behavior
- Documentation and usage examples

### Phase 3: scribe_doctor Enhancement
**Estimated Time:** 3-4 hours
**Deliverables:**
- Database schema inspection
- Live query capabilities
- Health monitoring dashboard
- Background task observation

### Phase 4: Database Refactor
**Estimated Time:** 6-8 hours
**Deliverables:**
- Service layer implementation
- Migration from scattered logic to services
- Comprehensive test coverage
- Updated documentation

### Phase 5: Integration & Testing
**Estimated Time:** 2-3 hours
**Deliverables:**
- End-to-end testing of all three pillars
- Performance benchmarking
- Production deployment validation

**Total Estimated Time:** 17-24 hours

---

## 🔬 Success Criteria

### Async Runner Service
- [ ] Can submit 100+ concurrent background tasks without blocking
- [ ] Zero task orphaning (all submitted tasks execute)
- [ ] Memory usage stable (no leaks from completed tasks)
- [ ] Observable via scribe_doctor tool
- [ ] Handles errors gracefully (background failures don't crash server)

### scribe_doctor Enhancement
- [ ] Can inspect full database schema
- [ ] Supports live queries with preset library
- [ ] Health monitoring catches common DB issues
- [ ] Background task monitoring shows real-time stats
- [ ] Watch mode provides live dashboard

### Database Refactor
- [ ] All DB operations go through service layer
- [ ] Each service has 90%+ test coverage
- [ ] No business logic in storage layer
- [ ] Migration system handles schema changes
- [ ] Documentation clear for new contributors

### SQL Tool Logging (Validation)
- [ ] **JSONL and SQL both work** (1:1 entry mapping)
- [ ] SQL writes don't block tool responses
- [ ] Database has matching row count to JSONL
- [ ] Background task runner shows successful executions

---

## 🚨 Critical Decisions Needed

### 1. Service Architecture
- **Question:** Should async runner be a singleton or per-component?
- **Options:**
  - Global singleton (simple, shared queue)
  - Per-service instances (isolated, configurable)
  - Hybrid (global runner, service-specific queues)

### 2. Task Priority
- **Question:** Do different background tasks need priority levels?
- **Options:**
  - FIFO queue (simple, no priorities)
  - Priority queue (complex, better control)
  - Multiple queues by type (medium complexity)

### 3. Shutdown Behavior
- **Question:** How long to wait for background tasks during shutdown?
- **Options:**
  - Wait indefinitely (could hang)
  - Timeout with cancellation (might lose data)
  - Persistent queue (survive restarts)

### 4. Database Migration Strategy
- **Question:** How to handle schema changes without downtime?
- **Options:**
  - Manual SQL scripts (simple but error-prone)
  - Migration framework like Alembic (complex but robust)
  - Version-based migrations (middle ground)

---

## 📊 Current State Summary

**What Works:**
- ✅ JSONL tool logging (synchronous, reliable)
- ✅ Basic SQLite storage layer
- ✅ Session management (partially)
- ✅ Project CRUD operations
- ✅ Reminder system (file-based)

**What's Broken:**
- ❌ SQL tool logging (0 rows despite background task code)
- ❌ Background task execution (garbage collection issue)
- ❌ Lack of observability (can't see what's happening)
- ❌ Scattered DB logic (hard to maintain)

**What's At Risk:**
- ⚠️ Any future background operations will hit same issues
- ⚠️ Database grows but no monitoring
- ⚠️ Refactoring becomes harder as code grows
- ⚠️ Testing becomes harder as coupling increases

---

## 🎯 Next Steps (New Project)

1. **Create New Project:** `scribe_async_runner_db_refactor`
2. **Research Phase:**
   - Study existing MCP server lifecycle hooks
   - Research async task runner patterns (Celery, Dramatiq, custom)
   - Design service layer architecture
   - Plan database migration strategy
3. **Architecture Phase:**
   - Create comprehensive architecture documents
   - Define API contracts for all services
   - Design integration points with existing code
   - Create test strategy
4. **Review Phase:**
   - Validate architecture before implementation
   - Identify risks and mitigation strategies
   - Get approval for breaking changes
5. **Implementation Phase:**
   - Build in incremental phases
   - Test each component in isolation
   - Validate end-to-end integration

---

## 📚 Related Research Documents

**From Current Project:**
- `.scribe/docs/dev_plans/scribe_tool_output_refinement/research/RESEARCH_SQL_REMINDER_FAILURES_20260104_1231.md`
- `.scribe/docs/dev_plans/scribe_tool_output_refinement/research/RESEARCH_ASYNC_BACKGROUND_TASKS_20260104_2327.md`
- `.scribe/docs/dev_plans/scribe_tool_output_refinement/architecture/async_runner/ASYNC_RUNNER_ARCHITECTURE_GUIDE.md`

**Key Findings to Carry Forward:**
- asyncio.create_task() creates weak references
- Module-level set prevents garbage collection
- done_callback pattern for automatic cleanup
- Official Python pattern from docs.python.org/3/library/asyncio-task.html

---

## 💡 Why This Pivot Matters

**Short Term:**
- Fixes SQL tool logging immediately
- Provides foundation for future background operations
- Improves observability and debugging

**Medium Term:**
- Enables analytics and metrics collection
- Supports more sophisticated features (caching, notifications)
- Makes database maintenance easier

**Long Term:**
- Creates reusable infrastructure for all Scribe projects
- Establishes patterns for async operations in MCP
- Provides reference implementation for MCP community

**This is infrastructure work that pays dividends for years.**

---

## 🚀 Ready to Begin

This spec document provides the foundation for the new project. In the new chat session, we'll:
1. Create the project with proper scoping
2. Run full research phase
3. Design comprehensive architecture
4. Implement systematically with full testing

**End of Spec Document**
