# BUG-STORAGE-001: Storage Abstraction Layer Bypass

**ID**: BUG-STORAGE-001
**Category**: architecture
**Severity**: CRITICAL
**Status**: open
**Discovered**: 2026-01-05
**Discoverer**: ResearchAgent-Phase2-Storage
**Related Spec**: SPEC-STORAGE-001-enforce-abstraction.yaml

---

## 1. Summary

Production code in `shared/project_registry.py` bypasses the `StorageBackend` abstraction layer with 9 direct `sqlite3.connect()` calls, breaking PostgreSQL compatibility and violating architecture principles.

---

## 2. Impact Assessment

**Severity**: CRITICAL
**Affected Systems**:
- Project lifecycle management (project_registry.py)
- PostgreSQL backend compatibility
- Multi-database deployment scenarios

**User Impact**:
- PostgreSQL mode completely broken for project lifecycle operations
- Cannot use centralized database for team collaboration
- PostgreSQL backend testing incomplete due to untestable code paths

**Technical Debt**:
- 648 LOC in project_registry.py tightly coupled to SQLite
- 11 total production violations across 3 files
- Architecture pattern violation precedent

---

## 3. Root Cause Analysis

### Why It Happened

1. **Historical**: project_registry.py predates full StorageBackend abstraction
2. **Synchronous Code**: project_registry.py is synchronous, StorageBackend is async
3. **Convenience**: Direct sqlite3 access is simpler than abstraction layer
4. **No Enforcement**: No linting rules or tests preventing violations

### How It Went Undetected

1. SQLite-only testing didn't expose PostgreSQL issues
2. No architecture tests enforcing abstraction
3. Code reviews didn't flag abstraction violations
4. PostgreSQL backend incomplete (85%), so violations not immediately critical

---

## 4. Bug Evidence

### Primary Violation: shared/project_registry.py

**File**: `shared/project_registry.py` (648 LOC)
**Violation Count**: 9 direct sqlite3.connect() calls
**Lines**: 77, 94, 111, 177, 203, 284, 381, 436, 454

#### Example Violation (Line 77):

```python
def update_project_metadata(
    self,
    project: ProjectRecord,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Update extended project metadata (description, tags, meta)."""
    # ... validation code ...

    now = self._now_iso()
    with sqlite3.connect(self._db_path) as conn:  # ← VIOLATION
        conn.execute(
            """
            UPDATE scribe_projects
            SET
                description = COALESCE(description, ?),
                tags = COALESCE(tags, ?),
                meta = COALESCE(meta, ?),
                last_access_at = COALESCE(last_access_at, ?)
            WHERE name = ?
            """,
            (description, tags_str, meta_str, now, project.name),
        )
```

**Problem**: Direct SQL execution bypasses StorageBackend, breaks PostgreSQL

---

### Secondary Violations

#### plugins/vector_indexer.py (Line 331)

```python
self._db_conn = sqlite3.connect(str(self.mapping_db_path), check_same_thread=False)
```

**Severity**: MEDIUM
**Justification**: Vector indexer uses separate database
**Decision**: May be acceptable with documentation

---

#### shared/logging_utils.py (Line 108)

```python
with sqlite3.connect(settings.sqlite_path) as conn:
    # Emergency fallback logging
```

**Severity**: MEDIUM
**Context**: Emergency logging fallback
**Fix**: Use StorageBackend with file fallback for true emergencies

---

## 5. Reproduction Steps

1. Configure Scribe MCP with PostgreSQL backend
2. Call `set_project(name="test")` to create project
3. Call any ProjectRegistry method (e.g., `touch_access()`)
4. **Expected**: Works via PostgreSQL StorageBackend
5. **Actual**: Fails - project_registry.py tries to connect to SQLite file that doesn't exist

**Error**:
```
sqlite3.OperationalError: unable to open database file
```

---

## 6. Affected Code Paths

### Direct Violations (11 calls)

| File | Line | Method | Impact |
|------|------|--------|--------|
| shared/project_registry.py | 77 | update_project_metadata() | HIGH |
| shared/project_registry.py | 94 | touch_access() | HIGH |
| shared/project_registry.py | 111 | touch_entry() | CRITICAL |
| shared/project_registry.py | 177 | get_project_summary() | HIGH |
| shared/project_registry.py | 203 | list_all_projects() | HIGH |
| shared/project_registry.py | 284 | _check_and_promote_status() | CRITICAL |
| shared/project_registry.py | 381 | get_project_activity() | MEDIUM |
| shared/project_registry.py | 436 | mark_completed() | HIGH |
| shared/project_registry.py | 454 | archive_project() | HIGH |
| plugins/vector_indexer.py | 331 | __init__() | MEDIUM |
| shared/logging_utils.py | 108 | emergency_log() | MEDIUM |

---

## 7. Proposed Fix

### Implementation Spec: SPEC-STORAGE-001

**Status**: Draft created
**Effort**: 24-40 hours
**Approach**:

1. Extend StorageBackend with 5 new abstract methods
2. Refactor project_registry.py to async + StorageBackend
3. Refactor logging_utils.py to use abstraction
4. Document vector_indexer.py as approved exception
5. Add linting rules preventing future violations
6. Add architecture test enforcing abstraction

**Files Modified**:
- `storage/base.py` - Add abstract methods
- `storage/sqlite.py` - Implement methods
- `storage/postgres.py` - Implement methods
- `db/ops.py` - PostgreSQL implementations
- `shared/project_registry.py` - Full refactor
- `shared/logging_utils.py` - Refactor
- `tools/lint_rules/no_direct_db_access.py` - New linting rule
- `tests/test_storage_abstraction.py` - Architecture test

---

## 8. Workaround

**Temporary**: Use SQLite backend only

```python
# In config/settings.py
SCRIBE_STORAGE_BACKEND = "sqlite"  # Force SQLite
```

**Limitation**: No multi-user deployments, no centralized database

---

## 9. Long-term Solution

### Option A: Complete Refactor (RECOMMENDED)

**Pros**:
- Fixes architecture violation
- Enables PostgreSQL for production
- Future-proof for other backends

**Cons**:
- 24-40 hour effort
- Breaking change (ProjectRegistry becomes async)

**Timeline**: 3-4 weeks

---

### Option B: Duplicate Implementation

**Pros**:
- No breaking changes
- Faster implementation

**Cons**:
- Technical debt doubled
- Violates DRY principle
- Maintenance burden

**Timeline**: 1-2 weeks

**Verdict**: NOT RECOMMENDED

---

### Option C: Deprecate PostgreSQL

**Pros**:
- Zero effort
- No breaking changes

**Cons**:
- Abandons enterprise use case
- Wastes existing PostgreSQL work
- Limits scalability

**Verdict**: Only if enterprise deployments not planned

---

## 10. Testing Requirements

### Regression Tests

- [ ] All project_registry.py methods work with SQLite
- [ ] All project_registry.py methods work with PostgreSQL
- [ ] Project lifecycle state transitions correct
- [ ] Metadata updates persist correctly

### Architecture Tests

- [ ] No production code uses sqlite3.connect (except allowed files)
- [ ] No production code imports asyncpg (except storage layer)
- [ ] Linting rule catches new violations

---

## 11. Open Questions

1. **Breaking Changes**: Acceptable to make ProjectRegistry async?
2. **Migration**: Provide compatibility shim for old callers?
3. **Vector Indexer**: Force integration or document exception?
4. **Timeline**: Fix immediately or batch with PostgreSQL parity work?

---

## 12. Related Issues

- **SPEC-PG-001**: PostgreSQL parity - abstraction violations prevent testing PostgreSQL features
- **Commandment #0.5**: Infrastructure primacy - should refactor existing code, not create parallel implementations

---

## 13. Acceptance Criteria

- [ ] All 9 project_registry.py violations eliminated
- [ ] ProjectRegistry works with both SQLite and PostgreSQL
- [ ] All tests passing
- [ ] Linting rule prevents new violations
- [ ] Architecture test enforces abstraction
- [ ] Documentation updated
- [ ] SPEC-STORAGE-001 implemented

---

## 14. Priority Justification

**Why CRITICAL**:
1. Blocks PostgreSQL adoption (prevents team collaboration)
2. Violates core architecture principle
3. Creates precedent for bypassing abstractions
4. Prevents testing PostgreSQL features
5. Technical debt compounds over time

**Why NOT P0** (not blocking current work):
- SQLite workaround available
- No immediate production impact (most users use SQLite)
- Can be batched with PostgreSQL parity work

---

**Discovered By**: ResearchAgent-Phase2-Storage during Phase 2 systematic storage audit
**Next Action**: Architect reviews SPEC-STORAGE-001 and approves implementation approach
