
# 🏗️ Architecture Guide — Scribe Systematic Audit #1

**Author:** ArchitectAgent
**Version:** v1.0 (Phase 0 Charter)
**Status:** Active - Charter Approved
**Last Updated:** 2026-01-05 01:57:00 UTC

> **Mission:** Forensic audit of entire Scribe MCP codebase (204 Python files, 51,014 LOC) to document all components, eliminate technical debt, reduce token overhead by 30-40%, and establish comprehensive wiki-based knowledge base for AI agent consumption.

---
## 1. Problem Statement
<!-- ID: problem_statement -->

**Context:** The Scribe MCP codebase has grown organically to 51,014 LOC across 204 Python files without systematic code review or architecture documentation. This has resulted in:

- **Ultra-complex tool implementations**: 4 tools exceed 1,900 LOC (append_entry: 2,357, manage_docs: 2,663, query_entries: 2,030, rotate_log: 1,981)
- **Storage abstraction violations**: `shared/project_registry.py` bypasses the StorageBackend interface with direct `sqlite3.connect()` calls
- **Incomplete PostgreSQL migration**: 7 tables missing, 40+ columns missing, 3 tools not implemented (delete_project, reminder_history, tool_calls)
- **Import structure chaos**: 81 files use `sys.path` manipulation with inconsistent patterns
- **Code duplication**: `_count_log_entries` exists in 2 files, document gathering repeated 3x (~90-100 LOC each)
- **Parameter overload**: append_entry (21 params), query_entries (25 params) causing cognitive complexity
- **Token bloat**: list_projects returns 1000+ tokens, set_project returns 400-800 tokens
- **Documented bugs**: set_project line 459 incorrectly marks empty logs as new (entry_count == 0 logic)

**Impact:**
- AI agents receive excessive token overhead (30-40% reduction potential)
- Code maintenance requires deep context across multiple files
- Storage backend switching is unreliable due to abstraction violations
- PostgreSQL users face incomplete feature parity
- No centralized documentation for understanding system behavior

**Goals:**
1. **100% Wiki Coverage**: Document every tool, storage method, utility function with machine-readable specifications
2. **Token Reduction**: Achieve 30-40% reduction in tool output through strategic refactoring
3. **Storage Parity**: Complete PostgreSQL implementation to match SQLite feature set
4. **Import Standardization**: Eliminate sys.path manipulation, establish consistent patterns
5. **Bug Elimination**: Fix all documented issues with verified tests
6. **Architecture Clarity**: Create comprehensive component interaction maps
7. **Dead Code Removal**: Identify and eliminate unused functions, redundant logic

**Non-Goals:**
- Complete rewrite of existing systems (maintain backward compatibility)
- Optimization without measurement (all changes must be data-driven)
- UI/UX changes (focus is internal architecture and documentation)

**Success Metrics:**
- 100% of 28 tools documented in wiki with implementation specs
- Token output reduced by 30-40% on high-frequency tools (list_projects, set_project, read_recent)
- All 69 functional tests passing with 0 regressions
- PostgreSQL backend achieves 100% feature parity with SQLite
- Zero direct database access bypassing StorageBackend interface
- Wiki navigation achieves <30 seconds to find any component documentation


---
## 2. Requirements & Constraints
<!-- ID: requirements_constraints -->

**Functional Requirements:**

1. **Wiki Documentation System**
   - Every tool must have dedicated wiki page: `wiki/tools/<tool_name>.md`
   - Every storage method documented: `wiki/storage/<method_name>.md`
   - Machine-readable YAML implementation specs for all refactoring work
   - Cross-referenced navigation via INDEX.md files
   - Exact file paths and line numbers in all references

2. **Implementation Specification Format**
   - YAML-based specs with before/after code blocks
   - Precise line number references for all changes
   - Test coverage requirements defined upfront
   - Verification criteria (how to confirm fix works)
   - Approval gates: Review Agent ≥93% + Human sign-off

3. **Bug Reporting Format**
   - File path, line number, symptom description
   - Root cause analysis with reasoning chain
   - Impact assessment (severity, affected features)
   - Proposed fix with alternative approaches considered
   - Test reproduction case

**Non-Functional Requirements:**

1. **Zero Breaking Changes**: All refactoring must maintain backward compatibility
2. **Test Coverage**: No regression in 69 functional tests, new tests for bug fixes
3. **Storage Abstraction**: All database access via StorageBackend interface (no direct sqlite3/asyncpg)
4. **Documentation-First**: Implementation specs created BEFORE code changes
5. **Token Efficiency**: All tool outputs measured before/after optimization
6. **AI Agent Optimized**: All documentation written for LLM consumption with clear hierarchies

**Constraints:**

1. **Resource Limits**
   - 7-day audit timeline (40-50 hours total effort)
   - 4 parallel Research Agents maximum (Phase 1 only)
   - Sequential execution for Phases 2-7

2. **Technical Constraints**
   - MCP protocol compliance (tool signatures immutable)
   - Python 3.8+ compatibility required
   - SQLite 3.35+ and PostgreSQL 12+ support
   - Existing configuration files must remain valid

3. **Scope Boundaries**
   - Production code only (tests excluded from wiki)
   - No UI/UX changes (terminal output format only)
   - No protocol changes (client compatibility maintained)

**Assumptions:**

- Codebase remains stable during audit (no major feature development)
- Access to full git history for tracing design decisions
- Ability to test both SQLite and PostgreSQL backends
- Review Agent available for quality gates

**Risks & Mitigations:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Scope creep beyond 7 days | High | High | Strict phase gating, Review Agent enforcement |
| Breaking changes during refactoring | Medium | Critical | Comprehensive test suite run before/after all changes |
| PostgreSQL testing environment unavailable | Medium | Medium | Mock-based testing, defer Postgres completion to Phase 2.5 |
| Wiki becomes outdated immediately | High | Medium | Automated doc generation from code annotations (future) |
| Agent coordination failures | Medium | High | Clear project names, mandatory Scribe logging, explicit handoffs |


---
## 3. Architecture Overview
<!-- ID: architecture_overview -->

**Solution Summary:** Multi-phase forensic audit producing comprehensive wiki-based documentation system, targeted refactoring via implementation specs, and systematic technical debt elimination.

**Audit Phases (8 Total):**

```
Phase 0: Charter & Baseline (1-2 hours) ← CURRENT PHASE
  ↓
Phase 1: Tool-by-Tool Audit (12-16 hours, 4 parallel agents)
  ↓
Phase 2: Storage & State Audit (6-8 hours, sequential)
  ↓
Phase 3: Import Graph & Packaging (5-7 hours, sequential)
  ↓
Phase 4: Dead Code & Redundancy (6-8 hours, sequential)
  ↓
Phase 5: Token Bloat Analysis (5-7 hours, sequential)
  ↓
Phase 6: Architecture Synthesis (6-8 hours, Architect Agent)
  ↓
Phase 7: Final Review (3-4 hours, Review Agent + Human)
```

**Component Breakdown:**

1. **Wiki Documentation System**
   - **Location**: `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/`
   - **Structure**:
     - `INDEX.md` - Central navigation hub
     - `tools/` - 28 tool pages (one per MCP tool)
     - `storage/` - Storage backend documentation
     - `architecture/` - System design documents
     - `analysis/` - Investigation findings
     - `implementation_specs/` - YAML-based refactoring specs
     - `bugs/` - Bug reports with reproduction cases
     - `review/` - Review Agent assessments

2. **Research Agent Pool (Phase 1)**
   - **Agent A**: Tools 1-7 (append_entry, manage_docs, query_entries, rotate_log, set_project, read_file, generate_doc_templates)
   - **Agent B**: Tools 8-14 (list_projects, get_project, read_recent, health_check, vector_search, project_utils, sentinel_tools)
   - **Agent C**: Tools 15-21 (Tool configs, base classes, validation modules)
   - **Agent D**: Tools 22-28 (Remaining utilities and edge case tools)
   - Each agent produces: Tool wiki pages, bug reports, implementation specs

3. **Implementation Spec Format** (YAML)
   ```yaml
   spec_id: "SPEC-001-append-entry-param-reduction"
   title: "Reduce append_entry parameter count from 21 to 12"
   file: "tools/append_entry.py"
   lines: [145, 189]
   severity: "medium"
   impact: "Improved maintainability, reduced cognitive load"

   changes:
     - type: "parameter_consolidation"
       before: |
         async def append_entry(message, status, emoji, agent, meta,
                              timestamp_utc, items, items_list, ...)
       after: |
         async def append_entry(message, status=None, config=None, **kwargs)
       reasoning: "Consolidate into AppendEntryConfig object"

   tests:
     - "test_append_entry_backward_compat"
     - "test_append_entry_config_mode"

   verification:
     - "All existing tests pass"
     - "Token output reduced by 15-20%"
   ```

4. **Bug Report Format** (Markdown)
   ```markdown
   # BUG-001: set_project incorrectly marks empty logs as new

   **File**: tools/set_project.py
   **Line**: 459
   **Severity**: Medium
   **Impact**: Misleading status messages for projects with no entries

   ## Symptom
   Projects with entry_count == 0 show as "NEW PROJECT CREATED" even if docs exist.

   ## Root Cause
   Logic at line 459 uses `entry_count == 0` as proxy for "new project"
   instead of checking if docs were just created.

   ## Reproduction
   1. Create project with set_project()
   2. Delete PROGRESS_LOG.md manually
   3. Call set_project() again
   4. Observe incorrect "NEW PROJECT" message

   ## Proposed Fix
   Check `created_docs` flag instead of entry_count.
   ```

**Data Flow:**

```
Research Agent Investigation
  ↓
Wiki Page Creation (tools/<name>.md)
  ↓
Bug Discovery → Bug Report (bugs/<id>.md)
  ↓
Implementation Spec Creation (implementation_specs/<id>.yaml)
  ↓
Review Agent Validation (≥93% required)
  ↓
Human Approval
  ↓
Coder Agent Implementation (if approved)
  ↓
Final Review Agent Verification
```

**External Integrations:**

- Git history analysis for design decision tracing
- Scribe MCP logging for all agent actions
- pytest integration for test verification
- SQLite + PostgreSQL for baseline comparisons


---
## 4. Detailed Design
<!-- ID: detailed_design -->

### 4.1 Wiki Page Template Structure

Every tool wiki page must follow this structure:

```markdown
# Tool: <tool_name>

**File**: `tools/<tool_name>.py`
**LOC**: <line_count>
**Complexity**: <low|medium|high|ultra-high>
**Last Audited**: <YYYY-MM-DD>

## Purpose
<1-2 sentence description>

## Signature
```python
async def <tool_name>(<params>):
    """<docstring>"""
```

## Parameters
| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| param1 | str | Yes | N/A | ... |

## Return Value
<description of return type and structure>

## Token Output
- **Current**: <XXX tokens average>
- **Target**: <XXX tokens (XX% reduction)>
- **Measurement**: <sample calls used>

## Known Issues
- BUG-XXX: <description with link>

## Dependencies
- Storage: <methods called>
- Utils: <modules imported>
- Tools: <other tools called>

## Implementation Specs
- SPEC-XXX: <title with link>

## Code Analysis
### Complexity Hotspots
- Lines XXX-YYY: <description>

### Duplication Detected
- Pattern: <description>
- Also in: <file_path:line>

### Refactoring Opportunities
1. <opportunity with reasoning>
```

### 4.2 Phase 1: Tool-by-Tool Audit (Parallel Execution)

**Agent A - Ultra-High Complexity Tools (Estimated 14-16 hours)**
- append_entry.py (2,357 LOC)
  - Document 21-parameter signature
  - Analyze bulk mode implementation
  - Identify AppendEntryConfig consolidation opportunities
  - Map token output patterns (current vs target)
- manage_docs.py (2,663 LOC)
  - Document 11 action types
  - Analyze section anchor system
  - Identify apply_patch vs replace_section usage
  - Map YAML frontmatter handling
- query_entries.py (2,030 LOC)
  - Document 25-parameter signature
  - Analyze QueryEntriesConfig usage
  - Identify pagination logic
  - Map Phase 4 enhanced search implementation
- rotate_log.py (1,981 LOC)
  - Document rotation state management
  - Analyze integrity verification
  - Identify RotateLogConfig usage
  - Map auto-threshold logic

**Agent B - High Complexity Tools (Estimated 10-12 hours)**
- set_project.py (807 LOC)
  - **BUG-001**: Document line 459 empty log issue
  - Analyze project bootstrapping
  - Map lifecycle state transitions
  - Identify doc hygiene flag logic
- read_file.py (785 LOC)
  - Document mode system (scan_only, chunk, line_range, page, search)
  - Analyze chunk management
  - Map provenance metadata
- list_projects.py (533 LOC)
  - **TOKEN BLOAT**: 1000+ token output analysis
  - Document filtering/pagination
  - Analyze lifecycle metadata
  - Identify format parameter behavior
- get_project.py (352 LOC)
  - **TOKEN BLOAT**: 400-800 token output analysis
  - Document context retrieval
  - Analyze reminder integration
- read_recent.py (586 LOC)
  - Document pagination system
  - Analyze filter capabilities
  - Map format parameter options

**Agent C - Configuration & Base Classes (Estimated 8-10 hours)**
- config/query_entries_config.py (590 LOC)
- config/append_entry_config.py (590 LOC)
- config/rotate_log_config.py (494 LOC)
- base/tool_metadata.py (481 LOC)
- manage_docs_validation.py (287 LOC)

**Agent D - Utilities & Edge Case Tools (Estimated 8-10 hours)**
- health_check.py (274 LOC)
- vector_search.py (419 LOC)
- sentinel_tools.py (227 LOC)
- project_utils.py (254 LOC)
- generate_doc_templates.py (544 LOC)

### 4.3 Phase 2: Storage & State Audit (Sequential, 6-8 hours)

**Research Agent E Mission:**

1. **Storage Abstraction Analysis**
   - Document base.py StorageBackend interface (286 LOC)
   - Audit sqlite.py implementation (2,207 LOC)
     - 61 CREATE TABLE statements
     - 21 tables documented
   - Audit postgres.py implementation (260 LOC)
     - **GAP**: Missing delete_project method
     - **GAP**: Missing reminder_history table support
     - **GAP**: Missing tool_calls table support
     - **GAP**: 7 tables total missing
     - **GAP**: 40+ columns missing
   - Document models.py data structures (207 LOC)

2. **Abstraction Violation Investigation**
   - **CRITICAL**: shared/project_registry.py direct sqlite3.connect()
   - Grep for all `sqlite3.connect()` calls bypassing abstraction
   - Grep for all `asyncpg` calls bypassing abstraction
   - Create implementation specs for abstraction fixes

3. **State Management**
   - Document state/manager.py (location TBD)
   - Analyze state.json structure
   - Map rotation_state.json usage (utils/rotation_state.py - 528 LOC)

### 4.4 Phase 3: Import Graph & Packaging (Sequential, 5-7 hours)

**Research Agent F Mission:**

1. **Import Pattern Analysis**
   - Grep for all `sys.path.insert` occurrences (81 files documented)
   - Categorize patterns:
     - Tests adding parent to path
     - Internal modules using absolute imports
     - Inconsistent patterns
   - Create import standardization spec

2. **Packaging Structure**
   - Document current: MCP_SPINE is NOT a Python module
   - Analyze src/ migration feasibility (6-9 hour effort estimated)
   - Document 442 absolute imports (scribe_mcp.*)
   - Map circular dependency: tools ↔ server (lazy binding)

3. **Module Dependency Graph**
   - Create visual map of all imports
   - Identify tight coupling points
   - Document lazy import patterns

### 4.5 Phase 4: Dead Code & Redundancy (Sequential, 6-8 hours)

**Research Agent G Mission:**

1. **Duplication Detection**
   - **KNOWN**: _count_log_entries in 2 files
   - **KNOWN**: Document gathering repeated 3x (~90-100 LOC each)
   - Grep for similar function signatures
   - Analyze copy-paste patterns

2. **Dead Code Analysis**
   - Find unreferenced functions (grep + cross-reference)
   - Find unused imports
   - Find deprecated code paths (comments, version checks)

3. **Consolidation Opportunities**
   - Identify common utilities scattered across files
   - Map candidates for utils/ consolidation
   - Create refactoring specs

### 4.6 Phase 5: Token Bloat Analysis (Sequential, 5-7 hours)

**Research Agent H Mission:**

1. **High-Frequency Tool Measurement**
   - Sample 20 calls each: list_projects, set_project, get_project, read_recent
   - Measure token output (current baseline)
   - Identify verbose output patterns:
     - Repetitive metadata
     - Unnecessary formatting
     - Verbose error messages
     - Redundant reminders

2. **Format Parameter Audit**
   - Document `format="readable"` vs `format="structured"` behavior
   - Measure token differences
   - Identify ANSI color overhead (config-driven in v2.1.1)

3. **Optimization Targets**
   - Create token reduction specs for 30-40% improvement
   - Prioritize by tool call frequency
   - Define measurement verification criteria

### 4.7 Phase 6: Architecture Synthesis (Architect Agent, 6-8 hours)

**Deliverables:**
1. **System Architecture Map**
   - Complete component interaction diagram
   - Data flow visualization
   - Storage abstraction layer diagram

2. **Refactoring Roadmap**
   - Prioritized implementation specs (by impact × effort)
   - Dependency ordering (what must be fixed first)
   - Risk assessment per spec

3. **Token Optimization Strategy**
   - Tool-by-tool optimization plan
   - Format parameter strategy
   - Output verbosity guidelines

### 4.8 Phase 7: Final Review (Review Agent + Human, 3-4 hours)

**Review Agent Mission:**
- Grade all wiki pages (completeness, accuracy, clarity)
- Validate all implementation specs (testability, safety)
- Verify bug reports (reproduction steps, fix viability)
- Check cross-references (links work, no orphaned pages)
- **Quality Gate**: ≥93% required for approval

**Human Review:**
- Approve/reject refactoring roadmap
- Prioritize implementation specs
- Sign-off on architectural recommendations


---
## 5. Directory Structure (Keep Updated)
<!-- ID: directory_structure -->

```
/home/austin/projects/MCP_SPINE/scribe_mcp/
├── .scribe/
│   └── docs/
│       └── dev_plans/
│           └── scribe_systematic_audit_1/
│               ├── ARCHITECTURE_GUIDE.md (this file)
│               ├── PHASE_PLAN.md
│               ├── CHECKLIST.md
│               ├── PROGRESS_LOG.md
│               ├── BUG_LOG.md
│               ├── DOC_LOG.md
│               ├── SECURITY_LOG.md
│               └── wiki/
│                   ├── INDEX.md (navigation hub)
│                   ├── tools/ (28 tool pages)
│                   │   ├── append_entry.md
│                   │   ├── manage_docs.md
│                   │   ├── query_entries.md
│                   │   ├── rotate_log.md
│                   │   └── ... (24 more)
│                   ├── storage/
│                   │   ├── sqlite_backend.md
│                   │   ├── postgres_backend.md
│                   │   ├── base_interface.md
│                   │   └── models.md
│                   ├── architecture/
│                   │   ├── system_overview.md
│                   │   ├── component_interactions.md
│                   │   └── data_flow.md
│                   ├── analysis/
│                   │   ├── import_graph.md
│                   │   ├── duplication_report.md
│                   │   ├── dead_code_report.md
│                   │   └── token_analysis.md
│                   ├── implementation_specs/
│                   │   ├── SPEC-001-append-entry-params.yaml
│                   │   ├── SPEC-002-storage-abstraction.yaml
│                   │   ├── SPEC-003-token-optimization.yaml
│                   │   └── ... (more as discovered)
│                   ├── bugs/
│                   │   ├── BUG-001-set-project-empty-log.md
│                   │   └── ... (more as discovered)
│                   └── review/
│                       ├── phase1_review.md
│                       ├── phase2_review.md
│                       └── final_review.md
│
├── tools/ (17,253 LOC total)
│   ├── append_entry.py (2,357 LOC)
│   ├── manage_docs.py (2,663 LOC)
│   ├── query_entries.py (2,030 LOC)
│   ├── rotate_log.py (1,981 LOC)
│   └── ... (24 more tools)
│
├── storage/ (2,983 LOC total)
│   ├── sqlite.py (2,207 LOC)
│   ├── base.py (286 LOC)
│   ├── postgres.py (260 LOC)
│   └── models.py (207 LOC)
│
├── utils/ (13,307 LOC total)
│   ├── response.py (2,423 LOC)
│   ├── parameter_validator.py (1,538 LOC)
│   ├── error_handler.py (1,517 LOC)
│   ├── config_manager.py (1,504 LOC)
│   └── ... (20 more utilities)
│
├── state/
│   ├── manager.py
│   ├── state.json
│   └── rotation_state.json
│
├── shared/
│   └── project_registry.py (CRITICAL: abstraction violation)
│
└── server.py (MCP server entry point)
```

> **Note**: Agents must update this tree as wiki pages are created during audit phases.


---
## 6. Data & Storage
<!-- ID: data_storage -->

**Primary Datastores:**

1. **SQLite Database** (default backend)
   - Location: `data/scribe_projects.db`
   - 21 tables documented in audit
   - 61 CREATE TABLE statements in sqlite.py
   - Used for: Project registry, progress logs, doc metadata, reminder history, tool call logging

2. **PostgreSQL Database** (optional backend)
   - Connection via `SCRIBE_DB_URL` environment variable
   - **INCOMPLETE**: 7 tables missing, 40+ columns missing
   - **INCOMPLETE**: 3 tool methods not implemented (delete_project, reminder_history, tool_calls)
   - Target: 100% feature parity with SQLite by Phase 2 completion

3. **Filesystem Storage**
   - Markdown documents: `.scribe/docs/dev_plans/<project>/`
   - Configuration: `config/projects/<project>.json`
   - State files: `state/state.json`, `state/rotation_state.json`
   - Wiki output: `.scribe/docs/dev_plans/<project>/wiki/`

**Storage Abstraction Layer:**

- **Interface**: `storage/base.py` (286 LOC) defines StorageBackend protocol
- **SQLite Impl**: `storage/sqlite.py` (2,207 LOC) - complete implementation
- **Postgres Impl**: `storage/postgres.py` (260 LOC) - partial implementation
- **VIOLATION**: `shared/project_registry.py` bypasses abstraction with direct `sqlite3.connect()`

**Performance Considerations:**

- FTS (Full Text Search) for log queries in SQLite
- Pagination required for large log files (>1000 entries)
- Rotation triggers when logs exceed configurable thresholds
- Vector search (FAISS) for semantic query_entries (Phase 4 feature)


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->

**Existing Test Suite:**

- **69 Functional Tests**: Must pass with 0 regressions
- **Performance Tests**: Rotation benchmarks (0.5MB, 1MB, 2MB files)
- **Location**: `tests/` directory (excluded from audit scope)
- **Command**: `pytest` (functional), `pytest -m performance` (benchmarks)

**Audit Testing Requirements:**

1. **Bug Reproduction Tests**
   - Every bug report must include reproduction test case
   - Test must fail before fix, pass after fix
   - Example: `test_set_project_empty_log_marking()` for BUG-001

2. **Implementation Spec Verification**
   - Every SPEC must define test coverage requirements
   - Backward compatibility tests for all refactoring
   - Token output measurements (before/after)

3. **Storage Backend Parity**
   - Identical test suite run against SQLite and PostgreSQL
   - Feature matrix comparison
   - Performance benchmarks for both backends

4. **Integration Testing**
   - Wiki generation validation (all pages render correctly)
   - Cross-reference link checking
   - YAML spec parsing and validation

**Quality Gates:**

- All tests pass before Review Agent evaluation
- Review Agent grade ≥93% required for phase approval
- Human sign-off on implementation specs before coding


---
## 8. Deployment & Operations
<!-- ID: deployment_operations -->

**This is an Audit Project - No Deployment**

This audit does not deploy code changes. It produces documentation and implementation specifications for future deployment.

**Deliverables for Future Deployment:**

1. **Wiki Documentation**: Used immediately by AI agents for context
2. **Implementation Specs**: Queued for prioritized execution
3. **Bug Reports**: Triaged for severity and fix urgency
4. **Refactoring Roadmap**: Guides future development cycles

**Operational Impact:**

- Wiki provides instant knowledge base for all future Scribe development
- Implementation specs reduce planning overhead for future work
- Token optimization specs directly improve AI agent efficiency
- Storage parity specs enable PostgreSQL production use

**Maintenance:**

- Wiki pages updated whenever tools are modified
- Implementation specs marked "COMPLETED" when implemented
- Bug reports moved to "FIXED" with PR references
- Periodic re-audit (suggested: quarterly) to prevent drift


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->

| Item | Owner | Status | Phase | Notes |
|------|-------|--------|-------|-------|
| Complete PostgreSQL implementation or deprecate? | Architect | OPEN | 2 | Evaluate user demand vs effort |
| Migrate to src/ packaging structure? | Architect | OPEN | 3 | 6-9 hours effort, improves imports |
| Implement automated wiki generation from code? | Research | OPEN | 6 | Prevents documentation drift |
| Consolidate config classes into unified system? | Research | OPEN | 4 | Reduces duplication in tools/config/ |
| Should token optimization be aggressive or conservative? | Human | OPEN | 5 | Balance verbosity vs usability |
| Deprecate sqlite3.connect() usage entirely? | Architect | OPEN | 2 | Enforce abstraction layer strictly |
| Create implementation priority tiers (P0/P1/P2)? | Human | OPEN | 7 | Guides post-audit execution |

> **Note**: Update this table as questions are answered during audit phases. Reference decisions in relevant sections above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->

**Project Documentation:**
- PHASE_PLAN.md - Detailed phase execution plan
- CHECKLIST.md - Verification and completion criteria
- PROGRESS_LOG.md - Audit activity trail
- BUG_LOG.md - Discovered issues
- DOC_LOG.md - Documentation change log

**Codebase Context:**
- `/home/austin/projects/MCP_SPINE/scribe_mcp/` - Repository root
- `CLAUDE.md` (repo root) - Main development guidelines
- `.claude/agents/` - Subagent definitions
- `docs/Scribe_Usage.md` - Tool usage reference

**Baseline Metrics:**
- Total Files: 204 Python files
- Total LOC: 51,014 LOC (production code only)
- Tools: 28 tools, 17,253 LOC
- Storage: 4 files, 2,983 LOC
- Utils: 24 files, 13,307 LOC

**Known Issues Inventory (Pre-Audit):**
- BUG-001: set_project.py line 459 (empty log marking)
- VIOLATION: shared/project_registry.py (abstraction bypass)
- GAP: PostgreSQL missing 7 tables, 40+ columns, 3 methods
- DUPLICATION: _count_log_entries in 2 files
- DUPLICATION: Document gathering repeated 3x (~90-100 LOC each)
- BLOAT: list_projects (1000+ tokens)
- BLOAT: set_project (400-800 tokens)
- COMPLEXITY: append_entry (2,357 LOC, 21 params)
- COMPLEXITY: manage_docs (2,663 LOC, 11 action types)
- COMPLEXITY: query_entries (2,030 LOC, 25 params)
- COMPLEXITY: rotate_log (1,981 LOC)

**Generated Artifacts:**
- Wiki pages: `wiki/INDEX.md` and subdirectories
- Implementation specs: `wiki/implementation_specs/*.yaml`
- Bug reports: `wiki/bugs/BUG-*.md`
- Analysis reports: `wiki/analysis/*.md`

---

**Document Control:**
- **Version**: 1.0 (Phase 0 Charter)
- **Author**: ArchitectAgent
- **Last Updated**: 2026-01-05 01:57:00 UTC
- **Status**: ACTIVE - Charter Approved
- **Next Review**: After Phase 1 completion (parallel tool audits)