# 🔬 Research: Existing Infrastructure for Sitrep Feature
**Author:** ResearchAgent-Infrastructure
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-06 12:46:00 UTC

> This research documents existing infrastructure that MUST be reused for the sitrep (project status report) feature. User corrected orchestrator for asking about infrastructure that already exists - this document provides definitive code references.

---
## Executive Summary
<!-- ID: executive_summary -->

**Primary Objective:** Document existing implementations for entry counting, document architecture, docs_json integration, pagination, recent entries display, and timestamps to prevent reinventing the wheel.

**Key Takeaways:**
- Entry counting mechanism already exists: `backend.count_entries()` with filter support
- Base 4 docs are hardcoded constants; custom docs created via `manage_docs`
- `docs_json` column exists in DB but NOT exposed in ProjectRecord model (integration gap)
- Pagination infrastructure fully implemented via `PaginationInfo` dataclass
- Recent entries display format already exists in `format_readable_log_entries()`
- Timestamps tracked in `scribe_projects` table with `created_at`/`updated_at`
- `get_project` already has `_read_recent_progress_entries()` helper for reading last N entries

**Critical Finding:** User wants sitrep to REUSE these existing patterns, not create new ones.

---
## Research Scope
<!-- ID: research_scope -->

**Research Lead:** ResearchAgent-Infrastructure

**Investigation Window:** 2026-01-06

**Focus Areas:**
- [x] Entry counting mechanism (existing implementation)
- [x] Base 4 docs vs custom docs architecture
- [x] docs_json ↔ ProjectRegistry integration
- [x] Pagination patterns (existing implementations)
- [x] Recent entries display format
- [x] Timestamp/date tracking

**Dependencies & Constraints:**
- Must use existing infrastructure - NO parallel implementations
- User explicitly stated "we already have a proper way to count entries"
- User specified "the 4 base docs are ALWAYS present, but manage_docs can create custom docs"

---
## Findings
<!-- ID: findings -->

### Finding 1: Entry Counting Mechanism
**Summary:** Entry counting already implemented in SQLite backend with full filter support.

**Evidence:**
- **File:** `storage/sqlite.py:505-555`
- **Method:** `async def count_entries(self, project: ProjectRecord, filters: Optional[Dict]) -> int`
- **Implementation:** SQL `COUNT(*)` query on `scribe_entries` table
- **Filters:** agent, emoji, priority (IN), category (IN), min_confidence (>=)
- **Usage:** `tools/read_recent.py:320-323` - called for pagination total_count

**Confidence:** 1.0 (definitive implementation exists)

---

### Finding 2: Base 4 Docs Architecture
**Summary:** The 4 base docs are hardcoded; custom docs created via `manage_docs`.

**Base Docs (set_project.py:250-255):**
```python
docs = {
    "architecture": "ARCHITECTURE_GUIDE.md",
    "phase_plan": "PHASE_PLAN.md",
    "checklist": "CHECKLIST.md",
    "progress_log": "PROGRESS_LOG.md",
}
```

**Custom Docs (manage_docs.py:2175-2234):**
- Research: `docs/research/{name}.md` (create_research_doc)
- Bugs: `docs/bugs/{category}/{date}_{slug}/report.md` (create_bug_report)
- Reviews: `REVIEW_REPORT_{stage}_{date}_{time}.md` (create_review_report)

**Confidence:** 1.0 (definitive separation)

---

### Finding 3: docs_json Integration Gap
**Summary:** `docs_json` column exists in DB but NOT in ProjectRecord model.

**Database (sqlite.py:659):** `docs_json TEXT` column in `scribe_projects`
**Model Gap (models.py:9-15):** ProjectRecord does NOT include `docs_json` field
**Result:** docs_json exists but not retrievable via `fetch_project()`

**Confidence:** 0.9 (column exists, integration incomplete)

---

### Finding 4: Pagination Infrastructure
**Summary:** Complete pagination via `PaginationInfo` dataclass.

**PaginationInfo (estimator.py:42-57):**
- Fields: page, page_size, total_count, has_next, has_prev
- Method: `to_dict()` for JSON serialization

**Helper (response.py:2418):**
```python
create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo
```

**Confidence:** 1.0 (fully implemented)

---

### Finding 5: Recent Entries Display
**Summary:** Complete formatting in `format_readable_log_entries()`.

**Method (response.py:604-790):**
- Format: `[emoji] HH:MM | agent | message`
- Features: ANSI colors, reasoning blocks, NO truncation
- Pagination header with page X of Y

**Confidence:** 1.0 (definitive implementation)

---

### Finding 6: Timestamp Tracking
**Summary:** Comprehensive timestamps in `scribe_projects` table.

**Database (sqlite.py:657-658):**
- `created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

**ProjectRecord (models.py:14-15):**
- `created_at: Optional[datetime]`
- `updated_at: Optional[datetime]`

**ProjectInfo (project_registry.py:15-35):**
- created_at, last_entry_at, last_access_at, last_status_change

**list_projects (list_projects.py:236-238):** ISO format conversion via `.isoformat()`

**Confidence:** 1.0 (fully implemented)

---

### Finding 7: Recent Entries Helper
**Summary:** `get_project` already has helper for reading recent entries.

**Method (get_project.py:70-127):**
```python
async def _read_recent_progress_entries(
    progress_log_path: str,
    limit: int = 5
) -> List[Dict[str, Any]]
```

**Returns:** `[{"emoji": str, "timestamp": str, "agent": str, "message": str}]`
**Features:** Parses file, NO truncation, default limit=5

**Confidence:** 1.0 (ready to reuse)

---

## Technical Analysis
<!-- ID: technical_analysis -->

**Entry Counting Pattern:**
```python
total_count = await backend.count_entries(project, filters)
```

**Pagination Pattern:**
```python
rows, total = await backend.fetch_recent_entries_paginated(...)
pagination = create_pagination_info(page, page_size, total)
```

**Recent Entries:**
```python
entries = await _read_recent_progress_entries(log_path, limit=5)
```

**System Interactions:**
```
get_project/list_projects → ProjectRegistry → ProjectInfo → SQLite Backend
                                                                ↓
                                                        count_entries()
                                                        fetch_project()
```

**Risk Assessment:**
- docs_json integration gap (medium severity)
- Entry count duplication between file parsing and SQL (low severity)

---

## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps for Architect

**1. Reuse Entry Counting:**
- Use `backend.count_entries(project, filters)` - NO new implementation
- Signature: `async def count_entries(project: ProjectRecord, filters: Optional[Dict]) -> int`

**2. Reuse Base 4 Docs:**
- Base docs: `["architecture", "phase_plan", "checklist", "progress_log"]`
- Always in `project["docs"]` dict

**3. Reuse Pagination:**
- Use `create_pagination_info(page, page_size, total_count)`

**4. Reuse Recent Entries:**
- Use `_read_recent_progress_entries(log_path, limit=5)` from get_project.py
- OR use `backend.fetch_recent_entries()` for DB-based reads

**5. Reuse Timestamps:**
- `created_at`, `last_entry_at`, `last_access_at` available in ProjectInfo
- Use `.isoformat()` for string conversion

**6. Address docs_json Gap (Future):**
- Add `docs_json` field to ProjectRecord
- Update `fetch_project()` to SELECT docs_json

### Long-Term Opportunities
- Unified entry counting (deprecate file parsing)
- Complete docs_json integration
- Pagination standardization across all tools

---

## Appendix
<!-- ID: appendix -->

### File Reference Index

| Component | File:Lines | Purpose |
|-----------|-----------|---------|
| count_entries | `storage/sqlite.py:505-555` | Entry counting implementation |
| Base 4 docs | `set_project.py:250-255` | Hardcoded docs dict |
| Custom docs | `manage_docs.py:2175-2234` | Research/bug report creation |
| docs_json | `sqlite.py:659` | Database column (not in model) |
| PaginationInfo | `estimator.py:42-57` | Dataclass |
| create_pagination_info | `response.py:2418` | Helper |
| format_readable | `response.py:604-790` | Entry display format |
| Timestamps | `sqlite.py:657-658`, `models.py:14-15` | created_at, updated_at |
| ProjectInfo | `project_registry.py:15-35` | Aggregated view |
| Recent entries | `get_project.py:70-127` | File-based helper |

**Research Complete:** 2026-01-06 12:46:00 UTC
**Confidence:** 0.95 (all findings backed by code references)
**Next Stage:** Architecture Phase (Architect Agent)
---