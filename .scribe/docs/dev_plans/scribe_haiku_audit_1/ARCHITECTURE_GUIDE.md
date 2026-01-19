---
id: scribe_haiku_audit_1-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 scribe-haiku-audit-1"
doc_name: architecture
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

# 🏗️ Architecture Guide — scribe-haiku-audit-1
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-01-08 08:13:40 UTC

> Architecture guide for scribe-haiku-audit-1.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
## 1. Problem Statement
<!-- ID: problem_statement -->

### Context
The Scribe MCP codebase has grown organically to ~25,000 LOC across tools/, storage/, doc_management/, and state/ subsystems. A haiku swarm audit identified significant modularization opportunities, with **critical god-object anti-patterns** in:

1. **storage/sqlite.py** (2,400 LOC, 65 methods) - Query building duplicated 4x, session management mixed with schema, metrics collection interleaved
2. **tools/manage_docs.py** (3,079 LOC, 28 functions) - Special document creation, parameter healing, vector indexing all bundled
3. **doc_management/manager.py** (2,465 LOC, 48 functions) - Patch engine, text replacements, markdown tools, checklist management all in one file
4. **Logging cluster** (4,390 LOC combined) - 500-700 LOC of duplication between append_entry.py and query_entries.py

### Goals
- **Primary**: Extract cohesive modules to reduce god-object complexity
- **Secondary**: Eliminate code duplication via shared utilities
- **Tertiary**: Improve testability through single-responsibility modules

### Non-Goals
- No API changes to MCP tool signatures (internal refactoring only)
- No new features during this refactoring phase
- No changes to state/ layer (already well-modularized per C1 research)

### Success Metrics
- sqlite.py reduced from 2,400 to <1,600 LOC
- manage_docs.py reduced from 3,079 to <2,200 LOC
- manager.py reduced from 2,465 to <1,200 LOC
- Logging cluster duplication reduced by 500+ LOC
- All existing tests pass after extraction
<!-- ID: requirements_constraints -->
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->

### Functional Requirements
1. All extractions must be **additive** - no breaking changes to existing module interfaces
2. Extracted modules must be independently testable
3. Circular imports must be prevented through careful dependency ordering
4. Each extraction must have clear single responsibility

### Non-Functional Requirements
1. **Backend Agnostic**: QueryBuilder and SessionManager must work with both SQLite and PostgreSQL
2. **Backwards Compatible**: All existing tool calls must continue to work unchanged
3. **Performance Neutral**: No measurable performance regression from extraction overhead

### Constraints (NON-NEGOTIABLE)
- **COMMANDMENT #0.5**: No parallel/replacement files - extract TO new modules, not REPLACE existing ones
- **COMMANDMENT #3**: Work with existing files through proper delegation, not abandonment
- **Architecture Constraint**: storage/ extractions go to storage/, doc_management/ extractions go to doc_management/
- **Naming Convention**: Per COORDINATION_PROTOCOL - `storage/query_builder.py`, `doc_management/patch_engine.py`, etc.

### Risk Assessment
| Risk | Severity | Mitigation |
|------|----------|------------|
| Circular imports | HIGH | Careful dependency ordering, no cross-module imports between new extractions |
| Session state corruption | HIGH | SessionManager receives storage_backend instance, not imports |
| Migration ordering | MEDIUM | Migration registry with version tracking |
| Test coverage gaps | MEDIUM | Create parallel test structure for each extraction |
| PostgreSQL compatibility | MEDIUM | QueryBuilder is SQL-agnostic; validate on both backends |
<!-- ID: architecture_overview -->
## 3. Architecture Overview - Priority-Ranked Extraction List
<!-- ID: architecture_overview -->

### TIER 1: CRITICAL EXTRACTIONS (God Object Decomposition)

#### 1.1 storage/query_builder.py [HIGHEST PRIORITY]
- **Source**: sqlite.py lines 354-681 (duplicated in 4 methods)
- **LOC Saved**: ~150 lines of duplication eliminated
- **Confidence**: 0.95
- **Risk**: LOW (pure query construction, no state)
- **Rationale**: Same WHERE clause construction logic repeated in fetch_recent_entries, query_entries, count_entries, count_query_entries. Builder pattern consolidates all filter logic.

```python
class QueryBuilder:
    def __init__(self, project_id: int): ...
    def add_agent_filter(self, agent: str) -> 'QueryBuilder': ...
    def add_priority_filter(self, priorities: List[str]) -> 'QueryBuilder': ...
    def add_time_range(self, start: str, end: str) -> 'QueryBuilder': ...
    def build(self) -> Tuple[str, List[Any]]: ...
```

#### 1.2 storage/session_manager.py [CRITICAL]
- **Source**: sqlite.py lines 1717-2083 (20+ session methods)
- **LOC Saved**: ~370 lines extracted
- **Confidence**: 0.90
- **Risk**: MEDIUM (manages session state, requires write_lock injection)
- **Rationale**: Session lifecycle (upsert_agent_session, heartbeat, end_session, cleanup_expired) is separate concern from core storage. Enables PostgreSQL backend reuse.

#### 1.3 doc_management/patch_engine.py [CRITICAL]
- **Source**: manager.py lines 1121-1511
- **LOC Saved**: ~350 lines extracted
- **Confidence**: 0.95
- **Risk**: LOW (pure text operations, no state)
- **Rationale**: Unified diff parsing, context-aware application, one-line-gap tolerance. Most complex and specialized code in doc_management.

### TIER 2: HIGH-IMPACT SHARED UTILITIES

#### 2.1 utils/logging_parameter_validator.py [HIGH PRIORITY]
- **Source**: append_entry.py lines 170-415, query_entries.py lines 61-403
- **LOC Saved**: ~450 lines of duplication
- **Confidence**: 0.92
- **Risk**: LOW (replacing exact duplicates)
- **Rationale**: Both tools implement identical bulletproof parameter healing pattern. Generic validator supports both config types.

#### 2.2 tools/manage_docs_special_creation.py [HIGH PRIORITY]
- **Source**: manage_docs.py lines 758-1000, 2337-2944
- **LOC Saved**: ~600 lines extracted
- **Confidence**: 0.90
- **Risk**: LOW (cohesive subsystem, new module)
- **Rationale**: Complete subsystem for research/bug/review/agent card creation. Includes template rendering, index updates, database integration.

#### 2.3 doc_management/text_replacements.py [HIGH PRIORITY]
- **Source**: manager.py lines 963-1050
- **LOC Saved**: ~210 lines extracted
- **Confidence**: 0.90
- **Risk**: LOW (distinct text manipulation strategies)
- **Rationale**: Multiple replacement modes (literal, regex, section, block, header, range) bundled in one module.

### TIER 3: MEDIUM-IMPACT EXTRACTIONS

#### 3.1 doc_management/markdown_tools.py
- **Source**: manager.py lines 1705-1873
- **LOC Saved**: ~160 lines extracted
- **Confidence**: 0.92
- **Risk**: LOW (self-contained markdown operations)

#### 3.2 doc_management/checklist_manager.py
- **Source**: manager.py lines 1912-2001
- **LOC Saved**: ~120 lines extracted
- **Confidence**: 0.88
- **Risk**: LOW (encapsulated checklist logic)

#### 3.3 utils/config_merger.py
- **Source**: append_entry.py lines 300-348, query_entries.py lines 237-300
- **LOC Saved**: ~100-120 lines
- **Confidence**: 0.90
- **Risk**: LOW (generic pattern)

### TIER 4: LOWER PRIORITY / STRATEGIC

#### 4.1 storage/migrations/ subdirectory
- **Source**: sqlite.py lines 683-1163
- **LOC Reorganized**: ~480 lines across 4-5 files
- **Confidence**: 0.85
- **Risk**: MEDIUM (requires migration registry)

#### 4.2 security/repo_policy.py
- **Source**: read_file.py lines 26-118
- **LOC Saved**: ~92 lines extracted
- **Confidence**: 0.85
- **Risk**: MEDIUM (security boundary)

#### 4.3 utils/code_structure_analyzer.py
- **Source**: read_file.py lines 1384-1583
- **LOC Saved**: ~200 lines extracted
- **Confidence**: 0.80
- **Risk**: MEDIUM (AST complexity)

### NOT RECOMMENDED FOR EXTRACTION

| Component | Why Not Extract |
|-----------|-----------------|
| **state/ layer** | Already well-modularized (1,105 LOC across 3 files). C1 research confirmed zero extraction needed. |
| **rotate_log parameter healing** | 454 LOC of healing is API design smell, not extraction target. Fix: collapse to RotateLogConfig object. |
| **storage/sqlite.py low-level helpers** | _execute/_fetchone/_connect are necessary implementation details. Extraction adds indirection without value. |
<!-- ID: detailed_design -->
## 4. Detailed Design - Dependency Graph & Extraction Order
<!-- ID: detailed_design -->

### Dependency Graph (Extraction Order)

```
PHASE 1 (No Dependencies - Can Start Immediately)
├── storage/query_builder.py ──────┐
│   └─ deps: utils/search.py       │ Both isolated,
├── doc_management/patch_engine.py ┘ parallel extraction OK
│   └─ deps: re module only
│
PHASE 2 (Depends on Phase 1 completion for pattern validation)
├── utils/logging_parameter_validator.py
│   └─ deps: BulletproofParameterCorrector, ExceptionHealer
├── tools/manage_docs_special_creation.py
│   └─ deps: template_engine, append_entry, storage backend
├── doc_management/text_replacements.py
│   └─ deps: re module, header utilities
│
PHASE 3 (Depends on storage/query_builder.py being stable)
├── storage/session_manager.py
│   └─ deps: storage/query_builder.py (optional), models.py
│   └─ receives: storage_backend instance (avoids import)
│
PHASE 4 (Lower Priority - After Core Stabilizes)
├── doc_management/markdown_tools.py
├── doc_management/checklist_manager.py
├── utils/config_merger.py
├── storage/migrations/ (optional restructure)
```

### Module Interface Specifications

#### storage/query_builder.py
```python
from typing import Any, List, Tuple, Optional

class QueryBuilder:
    """Fluent builder for WHERE clauses with parameterized filters."""
    
    def __init__(self, project_id: int) -> None: ...
    def add_agent_filter(self, agent: str) -> 'QueryBuilder': ...
    def add_agents_filter(self, agents: List[str]) -> 'QueryBuilder': ...
    def add_emoji_filter(self, emoji: str) -> 'QueryBuilder': ...
    def add_emojis_filter(self, emojis: List[str]) -> 'QueryBuilder': ...
    def add_priority_filter(self, priorities: List[str]) -> 'QueryBuilder': ...
    def add_category_filter(self, categories: List[str]) -> 'QueryBuilder': ...
    def add_confidence_filter(self, min_confidence: float) -> 'QueryBuilder': ...
    def add_log_type_filter(self, log_type: str | List[str]) -> 'QueryBuilder': ...
    def add_time_range(self, start: Optional[str], end: Optional[str]) -> 'QueryBuilder': ...
    def add_meta_filters(self, meta_filters: dict) -> 'QueryBuilder': ...
    def build(self) -> Tuple[str, Tuple[Any, ...]]: ...
    def build_with_order(self, priority_sort: bool = False) -> Tuple[str, str, Tuple[Any, ...]]: ...
```

#### doc_management/patch_engine.py
```python
from typing import Tuple, List, Dict, Any

def parse_patch_hunks(patch_text: str) -> List[Dict[str, Any]]: ...
def apply_unified_patch(original_text: str, patch_text: str) -> Tuple[str, int]: ...
def rebase_patch_to_current_context(patch: str, original: str, current: str) -> str: ...
def build_patch_failure_diagnostics(error: Exception, patch: str, content: str) -> Dict[str, Any]: ...
```

#### storage/session_manager.py
```python
from typing import Optional, Dict, Any

class SessionManager:
    """Manages agent sessions, project context, and reminders."""
    
    def __init__(self, storage_backend) -> None: ...
    async def upsert_session(self, session_id: str, ...) -> None: ...
    async def heartbeat_session(self, session_id: str) -> None: ...
    async def end_session(self, session_id: str) -> None: ...
    async def get_agent_project(self, agent_id: str) -> Optional[Dict[str, Any]]: ...
    async def set_agent_project(self, agent_id: str, project_name: str, ...) -> Dict[str, Any]: ...
    async def cleanup_expired_sessions(self, batch_size: int = 100) -> int: ...
    async def record_reminder_shown(self, session_id: str, ...) -> None: ...
    async def check_reminder_cooldown(self, session_id: str, ...) -> bool: ...
```

### Integration Pattern (How sqlite.py delegates)

```python
# BEFORE: sqlite.py with inline query building
async def fetch_recent_entries(self, ...):
    clauses = ["project_id = ?"]
    params = [project.id]
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    # ... 50 more lines of filter building

# AFTER: sqlite.py delegating to QueryBuilder
from storage.query_builder import QueryBuilder

async def fetch_recent_entries(self, ...):
    builder = QueryBuilder(project.id)
    if filters.get("agent"):
        builder.add_agent_filter(filters["agent"])
    if filters.get("priority"):
        builder.add_priority_filter(filters["priority"])
    where_clause, params = builder.build()
    # ... execute query
```
<!-- ID: directory_structure -->
## 5. Directory Structure (Target State After Extraction)
<!-- ID: directory_structure -->

```
scribe_mcp/
├── storage/
│   ├── base.py              (unchanged - interface)
│   ├── sqlite.py            (REDUCED: 2400 → ~1600 LOC)
│   ├── models.py            (unchanged)
│   ├── query_builder.py     [NEW - ~80 LOC] ← Phase 1
│   ├── session_manager.py   [NEW - ~370 LOC] ← Phase 3
│   └── migrations/          [OPTIONAL - restructure only]
│
├── doc_management/
│   ├── manager.py           (REDUCED: 2465 → ~1200 LOC)
│   ├── patch_engine.py      [NEW - ~350 LOC] ← Phase 1
│   ├── text_replacements.py [NEW - ~210 LOC] ← Phase 2
│   ├── markdown_tools.py    [NEW - ~160 LOC] ← Phase 4
│   ├── checklist_manager.py [NEW - ~120 LOC] ← Phase 4
│   ├── constants.py         [NEW - ~20 LOC] ← Shared constants
│   └── (existing files unchanged)
│
├── tools/
│   ├── manage_docs.py            (REDUCED: 3079 → ~2200 LOC)
│   ├── manage_docs_special_creation.py [NEW - ~600 LOC] ← Phase 2
│   ├── append_entry.py           (REDUCED: 2360 → ~2000 LOC)
│   ├── query_entries.py          (REDUCED: 2030 → ~1700 LOC)
│   └── (other tools unchanged)
│
├── utils/
│   ├── logging_parameter_validator.py [NEW - ~200 LOC] ← Phase 2
│   ├── config_merger.py               [NEW - ~50 LOC] ← Phase 4
│   └── (existing utils unchanged)
│
├── security/
│   └── repo_policy.py       [FUTURE - ~100 LOC] ← Phase 4+
│
└── state/                   (NO CHANGES - already well-modularized)
    ├── manager.py           (334 LOC)
    ├── agent_manager.py     (512 LOC)
    └── agent_identity.py    (259 LOC)
```

### Line Count Impact Summary

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| storage/sqlite.py | 2,400 | ~1,600 | -800 (33%) |
| doc_management/manager.py | 2,465 | ~1,200 | -1,265 (51%) |
| tools/manage_docs.py | 3,079 | ~2,200 | -879 (29%) |
| tools/append_entry.py | 2,360 | ~2,000 | -360 (15%) |
| tools/query_entries.py | 2,030 | ~1,700 | -330 (16%) |
| **TOTAL** | 12,334 | ~8,700 | **-3,634 (29%)** |

New modules created: **10 files** totaling ~2,160 LOC (extracted, not new code)
<!-- ID: data_storage -->
## 6. Data & Storage Considerations
<!-- ID: data_storage -->

### QueryBuilder Backend Agnosticism
The QueryBuilder must work with both SQLite and PostgreSQL:
- Use parameterized queries with `?` placeholders
- PostgreSQL adapter can translate `?` to `$1, $2, ...` at execution time
- No SQLite-specific functions in query construction

### SessionManager State Isolation
- Session state lives in database, not in-memory
- SessionManager receives storage_backend instance (no import of SQLiteStorage)
- Enables future backend swapping without SessionManager changes

### Migration Strategy
If storage/migrations/ restructure is pursued:
- Keep all migrations idempotent (safe to run multiple times)
- Use migration registry with version tracking
- Call migrations from `_initialise()` in dependency order

### No Schema Changes Required
All extractions are internal code reorganization:
- No new database tables
- No column additions
- No index changes
- Existing schema fully supports extracted modules
<!-- ID: testing_strategy -->
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->

### Test Structure Per Extraction

Each new module requires parallel test file:
```
tests/
├── storage/
│   ├── test_query_builder.py     ← Phase 1
│   └── test_session_manager.py   ← Phase 3
├── doc_management/
│   ├── test_patch_engine.py      ← Phase 1
│   ├── test_text_replacements.py ← Phase 2
│   ├── test_markdown_tools.py    ← Phase 4
│   └── test_checklist_manager.py ← Phase 4
├── tools/
│   └── test_manage_docs_special_creation.py ← Phase 2
└── utils/
    ├── test_logging_parameter_validator.py  ← Phase 2
    └── test_config_merger.py                ← Phase 4
```

### Testing Requirements Per Phase

**Phase 1 (Critical Extractions)**
- QueryBuilder: Test all filter types, empty builder, complex combinations
- patch_engine: Test hunk parsing, context matching, one-line-gap tolerance, error diagnostics

**Phase 2 (Shared Utilities)**
- logging_parameter_validator: Test both AppendEntryConfig and QueryEntriesConfig
- special_creation: Test each document type creation, index updates
- text_replacements: Test each replacement mode

**Phase 3 (Session Manager)**
- Session lifecycle: create, heartbeat, expire, cleanup
- Project context: get, set, concurrency handling
- Reminder cooldown: hash-based deduplication

### Integration Test Requirements
- All existing tests in `tests/` must pass after each phase
- Run `pytest` after each extraction to verify no regressions
- Specific verification: `pytest tests/test_storage.py tests/test_tools.py`

### Observability
- Each extracted module should log entry/exit for debugging
- Use structured logging via existing `shared/logging_utils.py`
<!-- ID: deployment_operations -->
## 8. Deployment & Operations
<!-- ID: deployment_operations -->

### Extraction is Internal Refactoring
- No MCP tool signature changes
- No configuration changes required
- No environment variable changes
- No database migrations

### Rollout Strategy
1. **Per-Phase Commits**: Each phase should be a separate commit/PR
2. **Feature Branch**: Work on `refactor/modularization-phase-N` branches
3. **Review Gate**: Each phase requires code review before merge
4. **Regression Test**: Full `pytest` run before each merge

### Rollback Plan
If extraction introduces bugs:
- Revert the specific commit
- Extracted modules can be deleted without breaking existing code
- Original inline code still exists until delegation is added

### Maintenance Ownership
- Storage layer extractions: Backend maintainer
- Doc management extractions: Documentation team
- Logging utilities: Core tools maintainer
<!-- ID: open_questions -->
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->

| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| rotate_log API redesign | Architect | DECIDED | Recommend RotateLogConfig object collapse, NOT extraction of 454 LOC healing |
| SessionManager DI pattern | Coder | TODO | Pass storage_backend instance vs facade pattern - implement during Phase 3 |
| Migration registry versioning | Coder | DEFERRED | Only if storage/migrations/ restructure is pursued in Phase 4+ |
| QueryBuilder PostgreSQL validation | Coder | TODO | Verify query syntax works on both backends during Phase 1 |
| Shared constants location | Architect | DECIDED | Create doc_management/constants.py for SECTION_MARKER etc. |
| Test coverage baseline | Coder | TODO | Run coverage report before Phase 1 to establish baseline |
<!-- ID: references_appendix -->
## 10. References & Appendix
<!-- ID: references_appendix -->

### Source Research Documents
All findings consolidated from haiku swarm audit:
1. `research/RESEARCH_MANAGE_DOCS_MODULARIZATION_20260108.md` - A1 analysis (tools/manage_docs.py)
2. `research/RESEARCH_LOGGING_CLUSTER_MODULARIZATION_20260108.md` - A2 analysis (append_entry + query_entries)
3. `research/RESEARCH_FILE_OPS_CLUSTER_MODULARIZATION_20260108.md` - A3 analysis (read_file + rotate_log)
4. `research/RESEARCH_STORAGE_MODULARIZATION_20260108.md` - B1 analysis (storage layer) **[RECALIBRATED]**
5. `research/RESEARCH_DOC_MANAGEMENT_MODULARIZATION_20260108.md` - B2 analysis (doc_management subsystem)
6. `research/RESEARCH_STATE_MODULARIZATION_20260108.md` - C1 analysis (state layer - zero extractions)

### Confidence Scores Summary
| Extraction | Confidence | Source |
|------------|------------|--------|
| storage/query_builder.py | 0.95 | B1 verified + Opus calibration |
| doc_management/patch_engine.py | 0.95 | B2 |
| utils/logging_parameter_validator.py | 0.92 | A2 |
| storage/session_manager.py | 0.90 | B1 verified |
| tools/manage_docs_special_creation.py | 0.90 | A1 |
| doc_management/text_replacements.py | 0.90 | B2 |
| doc_management/markdown_tools.py | 0.92 | B2 |
| doc_management/checklist_manager.py | 0.88 | B2 |
| utils/config_merger.py | 0.90 | A2 |
| state/ layer (NO EXTRACTION) | 0.98 | C1 - confirmed clean |

### Opus Architect Recalibration Notes
- B1 haiku was too gentle on sqlite.py - upgraded from HIGH to CRITICAL priority
- A3 parameter healing correctly identified as API smell, not extraction target
- C1 state layer assessment confirmed accurate - zero extractions needed
- Overall extraction roadmap reduces codebase by ~3,600 LOC (29%) through consolidation

---
*Architecture Guide consolidated by ArchitectAgent-Opus on 2026-01-08*
*Based on haiku swarm research with Opus-level recalibration*
