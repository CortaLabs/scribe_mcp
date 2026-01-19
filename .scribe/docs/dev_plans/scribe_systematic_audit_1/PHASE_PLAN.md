# ⚙️ Phase Plan — Scribe Systematic Audit #1

**Author:** ArchitectAgent
**Version:** v1.0 (Phase 0 Charter)
**Status:** ACTIVE - Phase 0 Complete
**Last Updated:** 2026-01-05 02:02:00 UTC

> **Timeline:** 7 days (40-50 hours total effort)
> **Objective:** Complete forensic audit of 51,014 LOC across 204 Python files, producing comprehensive wiki documentation, implementation specs, and refactoring roadmap.

---
## Phase Overview
<!-- ID: phase_overview -->

| Phase | Goal | Key Deliverables | Duration | Agent Type | Confidence |
|-------|------|------------------|----------|------------|------------|
| **Phase 0** | Charter & Baseline | ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md, wiki/INDEX.md | 1-2 hrs | Architect | ✅ 1.00 |
| **Phase 1** | Tool-by-Tool Audit (RESCOPED) | 28 tool wiki pages, bug reports, implementation specs | 18-24 hrs | Research (12 parallel) | 0.95 |
| **Phase 2** | Storage & State | Storage layer docs, abstraction violation fixes | 6-8 hrs | Research (sequential) | 0.80 |
| **Phase 3** | Import Graph | Import analysis, packaging recommendations | 5-7 hrs | Research (sequential) | 0.75 |
| **Phase 4** | Dead Code & Redundancy | Duplication report, consolidation specs | 6-8 hrs | Research (sequential) | 0.70 |
| **Phase 5** | Token Bloat Analysis | Token measurements, optimization specs | 5-7 hrs | Research (sequential) | 0.80 |
| **Phase 6** | Architecture Synthesis | System diagrams, refactoring roadmap | 6-8 hrs | Architect | 0.75 |
| **Phase 7** | Final Review | Quality grades, approval recommendations | 3-4 hrs | Review + Human | 0.90 |

**Total Estimated Effort:** 40-52 hours over 7 days

---
## Phase 0 — Charter & Baseline ✅ COMPLETE
<!-- ID: phase_0 -->

**Status:** ✅ COMPLETE (2026-01-05)

**Objective:** Establish comprehensive audit framework with baseline metrics, documentation standards, and wiki structure.

**Key Tasks:**
- ✅ Create project with set_project("scribe_systematic_audit_1")
- ✅ Gather baseline metrics (LOC counts, file counts by layer)
- ✅ Populate ARCHITECTURE_GUIDE.md (all 10 sections)
- ✅ Create PHASE_PLAN.md (this document)
- ✅ Create CHECKLIST.md with verification criteria
- ✅ Scaffold wiki directory structure (7 categories)
- ✅ Create wiki/INDEX.md navigation hub
- ✅ Document wiki page templates and specification formats
- ✅ Log all work to scribe_systematic_audit_1 project

**Deliverables:**
- ✅ ARCHITECTURE_GUIDE.md (768 lines, 10 sections, ~4500 words)
- ✅ PHASE_PLAN.md (this file)
- ✅ CHECKLIST.md (verification items)
- ✅ wiki/INDEX.md (navigation structure)
- ✅ Wiki directories: tools/, storage/, architecture/, analysis/, implementation_specs/, bugs/, review/
- ✅ Baseline metrics logged (204 files, 51,014 LOC)

**Acceptance Criteria:**
- ✅ All required documentation files created
- ✅ Wiki template structures defined (tool page, YAML spec, bug report)
- ✅ Agent assignment strategy documented (4 parallel + sequential phases)
- ✅ Baseline metrics collected and logged
- ✅ Minimum 5 Scribe log entries with reasoning chains

**Dependencies:** None (foundation phase)

**Notes:** Charter approved. Ready for Phase 1 parallel execution with 4 Research Agents.

---
## Phase 1 — Tool-by-Tool Forensic Audit (REVISED SCOPE)
<!-- ID: phase_1 -->

**Status:** 🔄 CRITICAL SCOPE CORRECTION APPLIED

**⚠️ DIRECTIVE**: Monster files (>1,000 LOC) are **systems**, not tools. Each gets a solo agent. Depth over throughput.

**Objective:** Document all 28 MCP tools with forensic precision, identify bugs, create implementation specs for refactoring opportunities.

**Agent Deployment Strategy:** 12 Research Agents in parallel (increased from 4)

**Rationale for Rescope:**
- Files >1,000 LOC contain hidden state transitions, implicit contracts, undocumented coupling
- Splitting attention across monster files guarantees shallow audits with missed edge cases
- Audit prioritizes **depth over throughput** - monster files get **studied**, not skimmed

---

### 🧨 Monster Tools (Solo Agents - ONE TOOL EACH)

#### Agent A: append_entry.py (2,357 LOC)
**Assignment:** Solo only (no other tools)
**Complexity:** Ultra-High
**Agent Name:** `ResearchAgent-A-AppendEntry`

**Focus Areas:**
- Monolithic function with 21 parameters (consolidation analysis)
- Bulk/single modes, DB mirroring, vector indexing
- Silent exception swallowing (`except Exception: pass` patterns)
- Nested error handlers and parameter healing
- Config object usage (AppendEntryConfig)

**Deliverables:**
- Wiki page: `wiki/tools/append_entry.md`
- Token metrics (≥10 samples)
- Parameter reduction spec: `SPEC-APPEND-001-param-consolidation.yaml`
- Error handling spec: `SPEC-APPEND-002-error-logging.yaml`
- ≥10 Scribe log entries with reasoning chains

---

#### Agent B: manage_docs.py (2,663 LOC)
**Assignment:** Solo only (no other tools)
**Complexity:** Ultra-High
**Agent Name:** `ResearchAgent-B-ManageDocs`

**Focus Areas:**
- 20+ action types (create_research_doc, create_bug_report, replace_section, apply_patch, etc.)
- YAML frontmatter handling and validation
- Regex parsing patterns
- Patch application compiler
- Research indexing system

**Deliverables:**
- Wiki page: `wiki/tools/manage_docs.md`
- Token metrics (≥10 samples)
- Action type analysis: `wiki/analysis/manage_docs_actions.md`
- Consolidation spec: `SPEC-MANAGE-001-action-splitting.yaml`
- ≥10 Scribe log entries with reasoning chains

---

#### Agent C: query_entries.py (2,030 LOC)
**Assignment:** Solo only (no other tools)
**Complexity:** Ultra-High
**Agent Name:** `ResearchAgent-C-QueryEntries`

**Focus Areas:**
- 25-parameter signature (reduction analysis)
- Multi-scope search (project, global, all_projects, research, bugs, all)
- Pagination and relevance filtering
- Code reference verification
- Message mode variations (substring, regex, exact)

**Deliverables:**
- Wiki page: `wiki/tools/query_entries.md`
- Token metrics (≥10 samples)
- Search pattern analysis: `wiki/analysis/query_search_patterns.md`
- Parameter spec: `SPEC-QUERY-001-param-reduction.yaml`
- ≥10 Scribe log entries with reasoning chains

---

#### Agent D: rotate_log.py (1,981 LOC)
**Assignment:** Solo only (no other tools)
**Complexity:** Ultra-High
**Agent Name:** `ResearchAgent-D-RotateLog`

**Focus Areas:**
- Log rotation algorithms
- Compression and archive management
- Integrity verification (SHA256, line counts)
- Atomic writes and file locking
- Rotation state management

**Deliverables:**
- Wiki page: `wiki/tools/rotate_log.md`
- Rotation metrics analysis
- Integrity spec: `SPEC-ROTATE-001-verification.yaml`
- Performance analysis: `wiki/analysis/rotate_performance.md`
- ≥10 Scribe log entries with reasoning chains

---

#### Agent E: set_project.py (807 LOC)
**Assignment:** Solo only (no other tools)
**Complexity:** High
**Agent Name:** `ResearchAgent-E-SetProject`

**Focus Areas:**
- **KNOWN BUG-001**: Line 459 - `entry_count == 0` incorrectly marks empty logs as new
- Project lifecycle management
- Doc inventory gathering (`_gather_project_inventory`)
- Session binding
- SITREP formatting (new vs existing projects)

**Deliverables:**
- Wiki page: `wiki/tools/set_project.md`
- Bug report: `wiki/bugs/BUG-001-set-project-empty-log.md`
- Fix spec: `SPEC-SET-001-bug-fix.yaml`
- Token metrics (≥10 samples)
- ≥10 Scribe log entries with reasoning chains

---

### ⚖️ Medium Tools (Conservative Pairing - 4 agents)

#### Agent F: read_file.py (785 LOC)
**Assignment:** Solo (repo-scoped file access system)
**Agent Name:** `ResearchAgent-F-ReadFile`

**Focus Areas:**
- Mode system (scan_only, chunk, line_range, page, search)
- Provenance tracking (SHA256, size, encoding)
- Chunk-aware reading for large files
- Security and sandboxing

**Deliverables:**
- Wiki page: `wiki/tools/read_file.md`
- Token metrics (≥10 samples)
- Security analysis: `wiki/analysis/read_file_security.md`
- ≥10 Scribe log entries

---

#### Agent G: list_projects.py (533 LOC) + get_project.py (352 LOC) = 885 LOC
**Assignment:** Paired (functionally adjacent - project discovery + retrieval)
**Agent Name:** `ResearchAgent-G-ProjectOps`

**Focus Areas:**
- **KNOWN TOKEN-001**: list_projects generates 1000+ tokens for 10 projects
- **KNOWN DUPLICATION-002**: Doc gathering logic repeated with set_project.py (90-100 LOC)
- Project registry integration
- Lifecycle states and activity metrics
- 3-way routing (readable format: no matches / single / multiple)

**Deliverables:**
- 2 wiki pages: `wiki/tools/list_projects.md`, `wiki/tools/get_project.md`
- Token optimization spec: `SPEC-LIST-001-token-reduction.yaml`
- Consolidation spec: `SPEC-PROJECT-001-doc-gathering.yaml`
- ≥10 Scribe log entries

---

#### Agent H: read_recent.py (586 LOC)
**Assignment:** Solo (log entry retrieval)
**Agent Name:** `ResearchAgent-H-ReadRecent`

**Focus Areas:**
- **KNOWN ISSUE**: Parameter type issues (n parameter broken)
- Recent entries retrieval with pagination
- Priority/category filtering (Phase 5 enhanced)
- Format routing (readable/structured/compact)

**Deliverables:**
- Wiki page: `wiki/tools/read_recent.md`
- Bug report: `BUG-RECENT-001-param-type.md`
- Token metrics (≥10 samples)
- ≥10 Scribe log entries

---

#### Agent I: generate_doc_templates.py (544 LOC)
**Assignment:** Solo (template scaffolding)
**Agent Name:** `ResearchAgent-I-GenTemplates`

**Focus Areas:**
- Document template generation
- Jinja integration
- Frontmatter handling
- Overwrite protection

**Deliverables:**
- Wiki page: `wiki/tools/generate_doc_templates.md`
- Template analysis
- Token metrics (≥10 samples)
- ≥10 Scribe log entries

---

### 🧩 Small/Utility Tools (Batched - 3 agents)

#### Agent J: Health & Lifecycle Tools (~830 LOC total)
**Assignment:** 4 utilities (all <300 LOC)
**Agent Name:** `ResearchAgent-J-Utilities`

**Tools:**
1. `health_check.py` (274 LOC)
2. `doctor.py` (113 LOC)
3. `delete_project.py` (216 LOC)
4. `sentinel_tools.py` (227 LOC)

**Deliverables:**
- 4 wiki pages
- Combined utility analysis
- ≥10 Scribe log entries

---

#### Agent K: Advanced Features (~1,152 LOC total)
**Assignment:** 4 tools (vector, agent session, validation, project utils)
**Agent Name:** `ResearchAgent-K-Advanced`

**Tools:**
1. `vector_search.py` (419 LOC)
2. `agent_project_utils.py` (192 LOC)
3. `manage_docs_validation.py` (287 LOC)
4. `project_utils.py` (254 LOC)

**Deliverables:**
- 4 wiki pages
- Plugin architecture analysis
- Session management specs
- ≥10 Scribe log entries

---

#### Agent L: Base Classes & Config (~600 LOC total)
**Assignment:** 7 small files (infrastructure/config)
**Agent Name:** `ResearchAgent-L-Infrastructure`

**Tools:**
1. `base/base_tool.py`
2. `base/tool_metadata.py`
3. `base/normalizer.py`
4. `config/append_entry_config.py`
5. `config/query_entries_config.py`
6. `config/rotate_log_config.py`
7. `constants.py`

**Deliverables:**
- 7 wiki pages
- Inheritance hierarchy analysis
- Config duplication analysis
- ≥10 Scribe log entries

---

### Phase 1 Completion Criteria

**Mandatory Per-Agent Deliverables (ALL must be complete):**
- [ ] Full wiki page (template compliant, all sections filled)
- [ ] Token metrics (≥10 samples, avg + max documented using tiktoken)
- [ ] Explicit dependency map (imports, storage calls, cross-tool interactions)
- [ ] At least one of: bug report, refactor spec, or "no action" justification with evidence
- [ ] ≥10 Scribe log entries with 3-part reasoning chains (why/what/how)

**Quality Gates:**
- [ ] No "skimmed" analysis - all code paths documented
- [ ] Edge cases identified and catalogued
- [ ] Hidden state transitions documented
- [ ] Implicit contracts made explicit
- [ ] Token measurements use tiktoken (not estimates)

**Failure Condition:** Tool marked **INCOMPLETE** if any deliverable missing

**Phase-Level Acceptance:**
- [ ] All 28 tool wiki pages created (100% coverage)
- [ ] All 12 agents marked complete (≥10 log entries each)
- [ ] Token baselines established (avg/max per tool)
- [ ] Known issues confirmed (BUG-001, DUPLICATION-001/002, TOKEN-001)
- [ ] New bugs/duplications identified and catalogued
- [ ] Cross-cutting concerns documented
- [ ] wiki/tools/INDEX.md updated with all 28 tools
- [ ] Implementation specs created for all high-priority issues
- [ ] Review Agent grade ≥93% on all wiki pages

**Dependencies:** Phase 0 complete (charter approved)

**Revised Timeline:**
- **Total Duration**: 18-24 hours agent work (increased from 12-16 hours)
- **Monster agents** (5): 4-5 hours each = 20-25 hours (parallel)
- **Medium agents** (4): 3-4 hours each = 12-16 hours (parallel)
- **Utility agents** (3): 2-3 hours each = 6-9 hours (parallel)
- **Wall Clock**: ~5-6 hours (assuming full parallelism)

**Deployment Strategy: 3-Wave Staggered Launch with Quality Gates**

**⚠️ CRITICAL**: Do NOT deploy all 12 agents concurrently. Stagger deployment across 3 waves to prevent context melt, token budget exhaustion, and half-finished deliverables.

**Wave 1: Monster Tools (5 agents - HIGHEST PRIORITY)**
- Agent A (append_entry), Agent B (manage_docs), Agent C (query_entries), Agent D (rotate_log), Agent E (set_project)
- Deploy together, monitor closely
- **Gate to Wave 2:** Each agent must have:
  - [ ] Tool wiki page stub created
  - [ ] ≥3 Scribe log entries with reasoning chains (why/what/how)
  - [ ] ≥3 token samples recorded (avg + max tracking started)

---

### ⚠️ WAVE 1 CRITICAL CORRECTION: BUG-001 Analysis Flaw

**Date**: 2026-01-05
**Reviewer**: Orchestrator + User
**Agent Affected**: Agent E (set_project.py)

**Finding**: Agent E's BUG-001 fix specification is **fatally flawed** and would permanently break new project detection.

#### Agent E's Proposed Fix (INCORRECT):
```python
is_new = not progress_log_path.exists()
```

#### Why This FAILS:
1. **Execution Order**: `set_project.py` line 246 calls `_ensure_documents()` which runs BEFORE the `is_new` check at line 459
2. **Template Creation**: Line 667 calls `generate_doc_templates()` which **CREATES** `PROGRESS_LOG.md`
3. **Consequence**: After template creation, `progress_log_path.exists()` is **ALWAYS True**
4. **Result**: `is_new` would be **ALWAYS False**, showing every project (including genuinely new ones) as "existing"
5. **Impact**: Complete breakage of new project detection

#### CORRECT Fix: Hash Comparison

**Infrastructure Already Exists**:
- `ProjectRegistry.record_doc_update()` (shared/project_registry.py:227-234)
- Tracks `baseline_hashes` (template state) and `current_hashes` (modified state)

**Problem**: `generate_doc_templates.py` does NOT call `record_doc_update()` when creating templates

**Solution**:
1. **Wire up infrastructure**: Add `record_doc_update()` call in `generate_doc_templates.py:220-224` after template write
2. **Use hash comparison in set_project.py**:
   ```python
   # Check if core docs match baseline hashes (pristine = new)
   docs_meta = registry.get_project(name).meta.get("docs", {})
   baseline = docs_meta.get("baseline_hashes", {})
   current = docs_meta.get("current_hashes", {})

   core_docs = {"architecture", "phase_plan", "checklist"}
   is_new = all(baseline.get(d) == current.get(d) for d in core_docs if d in baseline)
   ```

**Semantic Correctness**:
- ❌ "Does file exist?" → Wrong question (files created immediately)
- ❌ "Are there entries?" → Wrong question (fails after rotation)
- ✅ "Has project been worked on?" → Correct question (hash comparison answers this)

**Documentation Updated**:
- `wiki/bugs/BUG-001-set-project-empty-log.md` - Corrected fix specification
- `wiki/analysis/cross_cutting_concerns.md` - New section "Missing Infrastructure Integrations"

**Wave 2 Status**: Correction documented, proceeding with deployment after user review.

---

**Wave 2: Medium Tools (4 agents - AFTER Wave 1 gates met)**
- Agent F (read_file), Agent G (list_projects + get_project), Agent H (read_recent), Agent I (generate_doc_templates)
- Deploy only after Wave 1 gates satisfied
- **Gate to Wave 3:** Same criteria as Wave 1

**Wave 3: Batched Utilities (3 agents - AFTER Wave 2 gates met)**
- Agent J (health/lifecycle), Agent K (advanced features), Agent L (base/config)
- Deploy only after Wave 2 gates satisfied
- **Gate to Phase 2:** All agents complete with full deliverables

**Coordination Rules:**
- Project name: `scribe_systematic_audit_1` (ALL agents must use this)
- Agent naming per table above (e.g., `ResearchAgent-A-AppendEntry`)
- Wiki coordination via `wiki/tools/INDEX.md` (each updates their section)
- No file conflicts (separate wiki pages per tool)
- **Shared cross-cutting page:** `wiki/analysis/cross_cutting_concerns.md` (created in Wave 1, all agents append findings)

**Critical Orchestrator Rules:**

1. **No Co-Authoring on Monster Tools**
   - Solo ownership is absolute for monsters (A-E)
   - If agent stuck, they ask for help but NO shared wiki page authoring
   - Maintains traceability and accountability

2. **Force Shared Cross-Cutting Concerns Page Early**
   - Create `wiki/analysis/cross_cutting_concerns.md` before Wave 1 launches
   - ALL agents must append when they find:
     - Duplicated helper patterns
     - Shared token bloat sources (formatting/reminders/metadata)
     - Storage abstraction violations
     - Session identity / project routing assumptions
   - Turns individual audits into unified system map

3. **Token Measurement Discipline**
   - All token metrics must use **tiktoken** (same model tokenizer)
   - Record as: **avg / p95 / max** (don't average away outliers)
   - Same sample method across all agents
   - Minimum 10 samples per tool

4. **Evidence or It Didn't Happen**
   - Every issue (known or new) requires:
     - File path + line range (exact)
     - Minimal repro call (inputs shown)
     - Expected vs actual behavior
   - No "seems like" or "appears to" language in wiki pages
   - All claims must be verifiable

5. **Stop-Review Triggers (P0 Escalation)**
   - If ANY agent reports these, Orchestrator flags immediately as P0:
     - Silent exception swallowing in core tool paths
     - Non-atomic writes in rotate/registry operations
     - Storage bypass (direct sqlite3/asyncpg outside abstraction layer)
   - Link to INDEX bug list immediately
   - May pause deployment to address critical findings

**Known Pre-Identified Issues:**
- BUG-001: set_project false positive (Agent E)
- DUPLICATION-001: _count_log_entries (2 implementations)
- DUPLICATION-002: Doc gathering logic (repeated 3x, 90-100 LOC each)
- TOKEN-001: list_projects verbosity (1000+ tokens → target <400)

---
## Phase 2 — Storage & State Audit
<!-- ID: phase_2 -->

**Status:** ⏳ PENDING (Awaits Phase 1 completion)

**Objective:** Document storage abstraction layer, identify PostgreSQL gaps, fix abstraction violations, audit state management.

**Agent:** Research Agent E (sequential execution, 6-8 hours)

**Key Tasks:**

1. **Storage Abstraction Documentation**
   - Document `storage/base.py` StorageBackend interface (286 LOC)
   - Create wiki page: `wiki/storage/base_interface.md`
   - Document all abstract methods with signatures, purposes, expected behaviors

2. **SQLite Backend Audit**
   - Document `storage/sqlite.py` implementation (2,207 LOC)
   - Create wiki page: `wiki/storage/sqlite_backend.md`
   - Catalog 61 CREATE TABLE statements
   - Document all 21 tables (schema, indexes, purpose)
   - Map method implementations to base interface

3. **PostgreSQL Backend Audit**
   - Document `storage/postgres.py` implementation (260 LOC)
   - Create wiki page: `wiki/storage/postgres_backend.md`
   - **GAP ANALYSIS**: Document missing tables (7 identified)
   - **GAP ANALYSIS**: Document missing columns (40+ identified)
   - **GAP ANALYSIS**: Document missing methods (delete_project, reminder_history, tool_calls)
   - Create implementation spec: `SPEC-PG-001-postgres-parity.yaml`

4. **Abstraction Violation Investigation**
   - **CRITICAL**: Audit `shared/project_registry.py` direct sqlite3.connect() usage
   - Grep for all `sqlite3.connect()` calls bypassing abstraction
   - Grep for all `asyncpg` imports bypassing abstraction
   - Create bug report: `BUG-STORAGE-001-abstraction-bypass.md`
   - Create implementation spec: `SPEC-STORAGE-001-enforce-abstraction.yaml`

5. **Data Models Documentation**
   - Document `storage/models.py` (207 LOC)
   - Create wiki page: `wiki/storage/models.md`
   - Catalog all data classes and their relationships

6. **State Management Audit**
   - Document `state/manager.py` (if exists)
   - Analyze `state/state.json` structure
   - Analyze `state/rotation_state.json` usage
   - Document utils/rotation_state.py (528 LOC) integration

**Deliverables:**
- 4 wiki pages (base_interface, sqlite_backend, postgres_backend, models)
- PostgreSQL parity spec: `SPEC-PG-001`
- Storage abstraction enforcement spec: `SPEC-STORAGE-001`
- Bug report: `BUG-STORAGE-001`
- State management documentation

**Acceptance Criteria:**
- [ ] All storage components documented with API references
- [ ] PostgreSQL gaps cataloged with line-by-line comparison
- [ ] All abstraction violations identified with file:line references
- [ ] Implementation specs created for all fixes
- [ ] ≥10 Scribe log entries with reasoning chains
- [ ] Review Agent grade ≥93%

**Dependencies:** Phase 1 complete (tool audit provides context for storage usage)

**Open Questions:**
- Complete PostgreSQL implementation or deprecate support?
- Enforce abstraction layer strictly or allow exceptions?

---
## Phase 3 — Import Graph & Packaging (TEAM APPROACH)
<!-- ID: phase_3 -->

**Status:** 🔄 REVISED SCOPE - 4 Agent Team (Parallel Execution)

**Objective:** Analyze import structure, document packaging approach, evaluate src/ migration, create standardization recommendations.

**⚠️ SCOPE REVISION RATIONALE:**
Original plan (single agent, 5-7 hours) underestimated scope. Import/packaging work affects ALL 204 files and requires VERY thorough documentation for critical foundational changes. Team approach ensures specialist focus and comprehensive coverage.

**Agent Deployment Strategy:** 4 Research Agents in parallel (25-33 hours total, 6-10 hours per agent)

**Coordination:** Shared `wiki/analysis/phase_3_coordination.md` created before deployment with explicit scope boundaries to prevent overlap.

---

### Team A: sys.path Pattern Auditor (6-8 hours)
**Agent Name:** `ResearchAgent-Phase3-SysPath`

**Scope:**
- Grep all 81 `sys.path.insert()` occurrences with exact file:line references
- Categorize by context (tests, internal modules, scripts, utilities)
- Document WHY each one exists (root cause analysis)
- Identify quick wins (sys.path hacks removable without src/ migration)
- Analyze test vs production code patterns

**Deliverables:**
- `wiki/analysis/sys_path_patterns.md` (comprehensive catalog with categories)
- Quick wins list (immediate improvements without migration)
- Pattern frequency analysis (which hacks are most common)

**Acceptance Criteria:**
- [ ] All 81 occurrences documented with file:line
- [ ] Each categorized with justification (why it exists)
- [ ] Quick wins identified with effort estimates
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team B: Import Structure Cartographer (6-8 hours)
**Agent Name:** `ResearchAgent-Phase3-ImportGraph`

**Scope:**
- Catalog all 442 absolute imports (`from scribe_mcp.*`)
- Map import graph (who imports what, dependency chains)
- Identify import hot spots (most imported modules = high coupling)
- Document current package structure (why MCP_SPINE is NOT a Python module)
- Analyze import depth (shallow vs deep import chains)

**Deliverables:**
- `wiki/analysis/import_graph.md` (comprehensive analysis with statistics)
- Dependency graph visualization (ASCII art or graphviz format)
- Hot spot analysis (coupling metrics per module)

**Acceptance Criteria:**
- [ ] All 442 imports cataloged and analyzed
- [ ] Import graph visualization created
- [ ] Hot spots identified with coupling scores
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team C: src/ Migration Architect (8-10 hours)
**Agent Name:** `ResearchAgent-Phase3-SrcMigration`

**Scope:**
- Design src/ directory structure (detailed layout)
- Estimate effort for 204 files (THOROUGH file-by-file impact analysis)
- Document benefits: cleaner imports, standard Python packaging, pip compatibility
- Document risks: breaking changes, test updates, import rewrites
- Create phased migration strategy (can it be incremental? all-at-once?)
- Test compatibility analysis (how many tests break? what rewrites needed?)
- pip packaging requirements (setup.py, pyproject.toml, MANIFEST.in)

**Deliverables:**
- `SPEC-PKG-001-src-migration.yaml` (ultra-detailed implementation spec)
- Migration playbook (step-by-step guide with phases)
- Risk mitigation strategies (rollback plan, testing strategy)
- Effort breakdown by file category (tools, storage, tests, utilities)

**Acceptance Criteria:**
- [ ] src/ structure fully designed with rationale
- [ ] All 204 files impact-assessed
- [ ] Phased migration strategy documented
- [ ] Risks and mitigations identified
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team D: Circular Dependency Detective (5-7 hours)
**Agent Name:** `ResearchAgent-Phase3-CircularDeps`

**Scope:**
- Map tools ↔ server circular dependency (known, document lazy binding)
- Find ALL other circular dependencies (exhaustive search)
- Analyze lazy binding patterns (import-time vs runtime)
- Categorize circularities: acceptable vs problematic
- Recommend decoupling strategies with effort estimates
- Document why some circularities may be intentional

**Deliverables:**
- `wiki/analysis/circular_dependencies.md` (comprehensive mapping)
- `SPEC-PKG-002-import-standards.yaml` (standards to prevent future circularities)
- Decoupling strategy specs (effort estimates per circularity)

**Acceptance Criteria:**
- [ ] All circular dependencies mapped with evidence
- [ ] Each circularity categorized (acceptable vs fix-required)
- [ ] Decoupling strategies documented with effort
- [ ] Import standards defined
- [ ] ≥10 Scribe log entries with reasoning chains

---

**Phase 3 Overall Deliverables:**
- 3 comprehensive analysis documents (sys_path_patterns.md, import_graph.md, circular_dependencies.md)
- 2 implementation specs (SPEC-PKG-001-src-migration.yaml, SPEC-PKG-002-import-standards.yaml)
- 1 dependency graph visualization
- 1 coordination document (phase_3_coordination.md)
- Migration playbook and risk mitigation strategies
- ≥40 Scribe log entries total (10 per agent minimum)

**Phase 3 Acceptance Criteria:**
- [ ] All 4 agent teams complete with deliverables
- [ ] No scope overlap (coordination file prevents duplication)
- [ ] All import patterns (81 sys.path + 442 absolute) documented
- [ ] src/ migration fully scoped with file-by-file analysis
- [ ] All circular dependencies mapped
- [ ] Review Agent grade ≥93%

**Dependencies:** Phase 2 complete ✅ (storage analysis informs import dependencies)

**Coordination Rules:**
1. All agents read `wiki/analysis/phase_3_coordination.md` FIRST
2. Agents must log their scope boundaries in coordination file
3. If agents discover overlap, they coordinate via coordination file updates
4. Cross-references encouraged (Team C references Team A's sys.path findings)

**Open Questions:**
- Prioritize src/ migration immediately or defer to separate project?
- Acceptable level of circular dependencies vs refactor cost?
- Should migration be phased or all-at-once?

---
## Phase 4 — Dead Code & Redundancy (TEAM APPROACH)
<!-- ID: phase_4 -->

**Status:** ✅ COMPLETE (Grade: 91.8/100 - CONDITIONAL PASS)

**Objective:** Identify code duplication, unused functions, consolidation opportunities, legacy code cleanup, API documentation validation, and audit cross-verification. STRICT research mode (no code changes).

**⚠️ SCOPE REVISION RATIONALE:**
Original plan (single agent, 6-8 hours) underestimated scope. User requires comprehensive cleanup analysis examining ALL 204 files, plus API documentation validation to ensure all Phase 1-3 findings remain accurate. Team approach ensures thorough coverage across 5 critical areas.

**Agent Deployment Strategy:** 5 Research Agents in parallel (25-30 hours total, 4-7 hours per agent)

**Coordination:** Shared `wiki/analysis/phase_4_coordination.md` created before deployment with explicit scope boundaries to prevent overlap.

**Priority Order (Critical to Standard):** Dead Code → Duplication → API Validator → Legacy → Audit Validator

---

### Team A: Dead Code Detective (5-6 hours)
**Agent Name:** `ResearchAgent-Phase4-DeadCode`
**Priority:** CRITICAL (Top 3)

**Scope:**
- Find unreferenced functions (defined but never called anywhere)
- Find unused imports (imported but never used in file)
- Find commented-out code (# TODO, # DEPRECATED, # UNUSED, old implementations)
- Find orphaned files (files not imported anywhere in codebase)
- Safety analysis: Which deletions are safe vs require runtime verification?

**Deliverables:**
- `wiki/analysis/dead_code_report.md` (comprehensive catalog)
- `SPEC-DEAD-001-safe-removals.yaml` (safe to delete immediately)
- `SPEC-DEAD-002-careful-removals.yaml` (requires testing/verification)

**Acceptance Criteria:**
- [ ] All unreferenced functions documented with file:line
- [ ] All unused imports cataloged
- [ ] All commented-out code sections identified
- [ ] Safety analysis complete (safe vs risky deletions)
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team B: Duplication Hunter (5-6 hours)
**Agent Name:** `ResearchAgent-Phase4-Duplication`
**Priority:** CRITICAL (Top 3)

**Scope:**
- Find KNOWN duplications: `_count_log_entries` (2 locations), doc gathering logic (3x, 90-100 LOC each)
- Find copy-paste patterns (identical or near-identical code blocks ≥80% similarity)
- Find similar function signatures across files (same params, different names)
- Consolidation opportunities: common utilities scattered across files
- Analyze tool config duplication (append_entry_config, query_entries_config, rotate_log_config)

**Deliverables:**
- `wiki/analysis/duplication_report.md` (all duplicates cataloged)
- `SPEC-DEDUP-001-count-log-entries.yaml` (consolidate duplicate)
- `SPEC-DEDUP-002-doc-gathering.yaml` (extract common function)
- `SPEC-DEDUP-00N-*.yaml` (for each additional duplication found)

**Acceptance Criteria:**
- [ ] All code duplication cataloged with file:line references
- [ ] Similarity scores documented (how similar are duplicates?)
- [ ] Consolidation opportunities prioritized by impact
- [ ] Implementation specs created for all refactoring work
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team C: Legacy Code Archaeologist (4-5 hours)
**Agent Name:** `ResearchAgent-Phase4-Legacy`
**Priority:** STANDARD

**Scope:**
- Find old fallback patterns (try/except with fallback to deprecated methods)
- Find version-gated code (if version < X use old path - still needed?)
- Find deprecated patterns (v1.x code still present in v2.x codebase)
- Find migration artifacts (code from old architectures no longer needed)
- Document WHY each was kept (intentional backward compatibility vs oversight)

**Deliverables:**
- `wiki/analysis/legacy_code_report.md` (catalog with rationale)
- `SPEC-LEGACY-001-safe-modernization.yaml` (safe to update)
- Rationale for keeping vs removing each legacy pattern

**Acceptance Criteria:**
- [ ] All legacy patterns documented with file:line
- [ ] Rationale documented (intentional vs oversight)
- [ ] Modernization opportunities identified
- [ ] Backward compatibility impact assessed
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team D: API Documentation Validator (6-7 hours)
**Agent Name:** `ResearchAgent-Phase4-APIValidator`
**Priority:** CRITICAL (Top 3)

**Scope:**
- Cross-check all 28 tool APIs from Phase 1 wikis against actual code
- Verify function signatures (params match docs? types correct?)
- Verify return types (docs say dict, code returns dict?)
- **DEEP behavior verification**: Test actual behavior matches documentation
- Verify YAML specs from Phase 3 match actual file structures
- Find undocumented APIs (public functions not in wikis)
- Find documentation drift (docs say X, code does Y)

**Deliverables:**
- `wiki/analysis/api_validation_report.md` (comprehensive validation)
- `SPEC-API-001-documentation-fixes.yaml` (corrections needed)
- Discrepancy list (docs vs code mismatches with severity)

**Acceptance Criteria:**
- [ ] All 28 tool APIs cross-checked against code
- [ ] Function signatures verified (params, types, defaults)
- [ ] Return types verified with actual testing
- [ ] Behavior verification complete (not just signatures)
- [ ] Undocumented APIs cataloged
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team E: Audit Cross-Validator (5-6 hours)
**Agent Name:** `ResearchAgent-Phase4-AuditValidator`
**Priority:** STANDARD (Goes last - depends on other teams)

**Scope:**
- Verify Phase 1 findings (28 tool audits - still accurate?)
- Verify Phase 2 findings (storage layer - any changes since audit?)
- Verify Phase 3 findings (import counts - did we miss any?)
- Cross-check extractable module proposals (Phase 1) against actual code
- Verify token analysis samples are representative
- Catch audit drift (code changed since documentation was written)

**Deliverables:**
- `wiki/analysis/audit_cross_validation.md` (verification report)
- Corrections to Phase 1-3 wikis (if needed)
- Confidence assessment (how accurate are our findings?)

**Acceptance Criteria:**
- [ ] All Phase 1-3 findings verified against current code
- [ ] Audit drift documented (what changed since audit?)
- [ ] Confidence scores assigned to all findings
- [ ] Corrections documented for any inaccuracies
- [ ] ≥10 Scribe log entries with reasoning chains

---

**Phase 4 Overall Deliverables:**
- 5 comprehensive analysis documents
- 8+ implementation specs (YAML format)
- 1 coordination document (phase_4_coordination.md)
- Discrepancy lists and correction recommendations
- ≥50 Scribe log entries total (10 per agent minimum)

**Phase 4 Acceptance Criteria:**
- [ ] All 5 agent teams complete with deliverables
- [ ] No scope overlap (coordination file prevents duplication)
- [ ] All dead code and duplication cataloged
- [ ] API documentation validated against actual behavior
- [ ] Phase 1-3 audits cross-validated
- [ ] Review Agent grade ≥93%

**Dependencies:** Phase 3 complete ✅ (import analysis reveals dependency chains)

**Coordination Rules:**
1. All agents read `wiki/analysis/phase_4_coordination.md` FIRST
2. Agents must log their scope boundaries in coordination file
3. Team E (Audit Validator) goes LAST - depends on Teams A-D findings
4. Cross-references encouraged between teams

**Safety Notes:**
- Dead code removal must verify no runtime references (grep + test coverage)
- Consolidation must maintain backward compatibility
- All specs require test coverage verification
- API validation must test actual behavior, not just signatures

---

### Phase 4 Results Summary

**Completion Date:** 2026-01-05
**Review Grade:** 91.8/100 - CONDITIONAL PASS ✅
**Review Report:** `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/reviews/PHASE_4_REVIEW.md`

**Key Achievements:**
- ✅ All 5 teams completed (Teams A, B, C, D, E)
- ✅ 17 deliverables created (4 analysis docs + 3 YAML specs per team + coordination)
- ✅ 356 total findings across 209 files (51,014+ LOC audited)
- ✅ 0 critical contradictions (92% consistency score)
- ✅ 99.5% coverage (near-perfect)
- ✅ LOC reduction potential: 1,143-1,193 lines (2.2-2.3% of codebase)

**Team Results:**
- **Team A (Dead Code)**: 238 unused imports + 18 dead functions (150-200 LOC reduction) - Grade: 88/100
- **Team B (Duplication)**: 4 patterns, 1,893 LOC waste (52% reduction = 947 LOC saved) - Grade: 90/100
- **Team C (Legacy)**: 95 patterns, 68 sys.path hacks, 38-45hr cleanup - Grade: 91/100
- **Team D (API Validator)**: 18 tools, 97% accuracy (100% LOC accuracy) - Grade: 96/100
- **Team E (Cross-Validator)**: 0 contradictions, validation complete - Grade: 94/100

**Critical Issue (Non-Blocking):**
- ⚠️ All teams logged as generic "ResearchAgent" instead of specific agent names (Scribe discipline violation, -10pts)
- Impact: Reduced traceability but research quality exceptional

**Approval Decision:** ✅ Phase 5 CLEARED - Technical quality is exceptional, all findings validated and implementable

---
## Phase 5 — Comprehensive Tool Output & Token Analysis (EXPANDED SCOPE)
<!-- ID: phase_5 -->

**Status:** ⏳ PENDING (Awaits Phase 4 completion)

**Objective:** Test ALL 28 tools exhaustively across ALL modes (readable/structured/compact), measure token output, flag display issues, verify configuration systems, and catch any remaining bugs. This is one of the final major audit phases - finish strong.

**⚠️ SCOPE EXPANSION RATIONALE:**
Original plan (single agent, token analysis only) was insufficient. User requires comprehensive testing of EVERY tool's output modes, customizable display configuration validation, format parameter audit across all tools, and bug detection (e.g., manage_docs not auto-registering docs). This is the final quality gate before architecture synthesis.

**Agent Deployment Strategy:** 3 Research Agents (24-28 hours total, 8-10 hours per agent)

**Coordination:** Shared `wiki/analysis/phase_5_coordination.md` with explicit tool assignments to prevent overlap.

**🚨 CRITICAL: Team A Sandbox Isolation**
**ONLY Team A (Output Recorder)** uses a separate project for TESTING: `scribe_systematic_audit_1_phase5_tool_output`

**Rationale:** Testing all 28 tools includes DESTRUCTIVE actions (delete_project, rotate_log, etc.). Sandbox prevents corruption of main audit documentation.

**Setup:** Before Team A deployment, create isolated sandbox project:
```python
await set_project(name="scribe_systematic_audit_1_phase5_tool_output")
```

**How It Works:**
- **Team A**: Tests tools in SANDBOX, writes deliverables to MAIN audit wiki, logs to MAIN audit project
- **Teams B & C**: Work entirely on MAIN audit project (no sandbox needed - they analyze, not test)

---

### Team A: Tool Output Recorder & Bug Hunter (10-12 hours)
**Agent Name:** `ResearchAgent-Phase5-OutputRecorder`
**Priority:** CRITICAL (Top 1)

**🚨 Project Split:**
- **Testing environment:** `scribe_systematic_audit_1_phase5_tool_output` (SANDBOX - call tools here safely)
- **Deliverables & Scribe logs:** `scribe_systematic_audit_1` (MAIN audit project)

**Scope:**
- Test ALL 28 tools in SANDBOX project (safe to call delete_project, rotate_log, etc.)
- For EACH tool, record outputs for ALL modes:
  - `format="readable"` (human-readable, default)
  - `format="structured"` (JSON/dict output)
  - `format="compact"` (condensed output)
- Test with various parameters (empty, minimal, maximal inputs)
- Save raw outputs to MAIN audit project `wiki/tool_outputs/<tool_name>/` directory
- Create output comparison matrices (readable vs structured vs compact)
- **Bug hunting during testing**:
  - Catch any bugs encountered while testing tools
  - Test manage_docs auto-registration (does `generate_doc_templates` call `ProjectRegistry.record_doc_update()`?)
  - Edge case testing: empty inputs, null values, Unicode, large files
  - Error handling: Do tools fail gracefully with readable messages?
  - Format parameter errors: What happens with `format="invalid"`?

**Deliverables (ALL written to MAIN audit project):**
- `wiki/tool_outputs/` directory with subdirectories for each tool
- `wiki/analysis/tool_output_catalog.md` - Complete inventory with token counts
- Output samples for all 28 tools × 3 modes = 84+ recordings
- Comparison spreadsheet: tool × mode × token_count × issues
- `wiki/bugs/phase_5_bugs/` - New bug reports (BUG-FORMAT-###, BUG-TOOL-###)
- `wiki/analysis/edge_case_testing_report.md` - Edge case results
- Bug reproduction scripts for any issues found

**Acceptance Criteria:**
- [ ] ALL 28 tools tested in SANDBOX (no exceptions)
- [ ] ALL 3 modes recorded per tool (readable, structured, compact)
- [ ] Raw outputs saved to MAIN audit wiki/tool_outputs/ for reference
- [ ] Token counts measured with tiktoken for each output
- [ ] manage_docs auto-registration bug verified
- [ ] Edge cases tested, bugs documented with reproduction steps
- [ ] ≥10 Scribe log entries with reasoning chains (logged to MAIN project)

---

### Team B: Format & Display Validator (8-10 hours)
**Agent Name:** `ResearchAgent-Phase5-FormatValidator`
**Priority:** CRITICAL (Top 2)
**Project Context:** `scribe_systematic_audit_1` (MAIN audit project - analyzes Team A's recordings)

**Scope:**
- **Format parameter audit**: Verify all 28 tools support `format` parameter
- **Mode completeness**: Flag tools WITHOUT readable/compact modes
- **Compact mode verification**: Ensure compact mode ACTUALLY reduces tokens (not just renamed)
- **Default behavior**: Document default format for each tool (should be readable)
- **Customizable display config**: Test `use_ansi_colors`, box drawing toggles, metadata verbosity
- **Config system deep dive**: Analyze `.scribe/config/scribe.yaml` customization options
- **Box drawing**: Can users disable box characters? (╔═══╗ vs plain text)
- **ANSI colors**: Can users disable color codes? (config-driven)
- **Metadata depth**: Can users control what metadata is shown?

**Deliverables:**
- `wiki/analysis/format_parameter_audit.md` - All 28 tools format support
- `wiki/analysis/display_configuration_guide.md` - Complete customization options
- `SPEC-FORMAT-001-missing-modes.yaml` - Tools lacking readable/compact modes
- `SPEC-FORMAT-002-config-system.yaml` - Display configuration enhancements
- Bug reports for tools with broken format parameters

**Acceptance Criteria:**
- [ ] All 28 tools format parameter support verified
- [ ] Tools without readable mode flagged (BUG-FORMAT-###)
- [ ] Tools without compact mode flagged
- [ ] Compact mode token reduction verified (must be <80% of readable)
- [ ] Default format documented for all tools
- [ ] Display configuration options cataloged
- [ ] ≥10 Scribe log entries with reasoning chains

---

### Team C: Token Bloat Analyzer (8-10 hours)
**Agent Name:** `ResearchAgent-Phase5-TokenAnalyzer`
**Priority:** CRITICAL (Top 3)
**Project Context:** `scribe_systematic_audit_1` (MAIN audit project - analyzes Team A's recordings)

**Scope:**
- **Token measurement**: Measure token output for ALL 28 tools (using Team A's recordings)
- **Bloat categorization**: Structural (boxes), Metadata (IDs, timestamps), Duplication, Safety padding
- **30-40% reduction targets**: Identify tools exceeding acceptable token budgets
- **Output refinement**: NOT truncating/deleting fields - refine HOW we display
- **Depth configuration**: Can users control output depth? (verbose vs minimal)
- **High-frequency tool focus**: `list_projects` (1000+ tokens), `set_project` (400-800), `get_project`, `read_recent`
- **Compare utils/response.py patterns**: Token-heavy templates in response formatter

**Deliverables:**
- `wiki/analysis/token_analysis_comprehensive.md` - All 28 tools measured
- `wiki/analysis/token_bloat_hotspots.md` - Tools exceeding budgets
- `SPEC-TOKEN-001` through `SPEC-TOKEN-00N` - Per-tool optimization specs (30-40% reduction targets)
- Before/after examples showing refined displays (not truncated content)
- Token budget recommendations (acceptable ranges per tool category)

**Acceptance Criteria:**
- [ ] All 28 tools token counts measured (readable, structured, compact)
- [ ] Token bloat categorized (structural/metadata/duplication/safety)
- [ ] High-frequency tools analyzed in depth
- [ ] Optimization specs target 30-40% reduction (no content loss)
- [ ] Before/after examples show refinement (not truncation)
- [ ] ≥10 Scribe log entries with reasoning chains

---

**Phase 5 Overall Deliverables:**
- 3 comprehensive analysis documents (output catalog, format audit, token analysis)
- 84+ tool output recordings (28 tools × 3 modes)
- 10+ implementation specs (SPEC-TOKEN-###, SPEC-FORMAT-###)
- Bug reports for any issues found (from Team A's bug hunting)
- Display configuration guide (customization options)
- ≥30 Scribe log entries total (10 per agent minimum)

**Phase 5 Acceptance Criteria:**
- [ ] ALL 28 tools tested across ALL 3 modes (84+ recordings)
- [ ] Token analysis complete with 30-40% reduction targets
- [ ] Format parameter support verified for all tools
- [ ] Display configuration options documented
- [ ] Compact mode verified (actually reduces tokens)
- [ ] Default format verified (should be readable)
- [ ] manage_docs auto-registration bug investigated
- [ ] Edge cases tested, error handling audited
- [ ] Review Agent grade ≥93%

**Dependencies:** Phase 4 complete ✅ (API validation confirms tool behavior)

**Coordination Rules:**
1. Team A records outputs FIRST (also does bug hunting during testing)
2. Team B and C can run in parallel after Team A completes initial recordings
3. Team B and C depend on Team A's output recordings
4. All teams cross-reference findings

**Safety Notes:**
- **Team A ONLY**: Test tools in SANDBOX project `scribe_systematic_audit_1_phase5_tool_output`
- **All Teams**: Write deliverables to MAIN audit project wiki
- **All Teams**: Log Scribe entries to MAIN audit project
- Record outputs to files (don't paste 1000+ token outputs into logs)
- Use tiktoken for consistent token measurement
- Save raw outputs for Phase 6 reference

---
## Phase 5.5 — Wiki Structure & Documentation Integration
<!-- ID: phase_5_5 -->

**Status:** ⏳ PENDING (Awaits Phase 5 completion)

**Objective:** Finalize audit documentation structure, create master INDEX.md, ensure all documents are properly linked and searchable, update agent instructions to reference wikis, and deep dive manage_docs to ensure it can properly edit all documentation.

**Agent:** Research Agent (sequential execution, 6-8 hours)

**Key Tasks:**

1. **Master INDEX.md Creation**
   - Create comprehensive `wiki/INDEX.md` as central navigation hub
   - Organize by phase (Phase 0 → Phase 5)
   - Link ALL documents (tools, analysis, specs, bugs, reviews)
   - Add table of contents with anchors
   - Include quick links to critical findings (BUG-001, TOKEN-001, etc.)
   - Add search keywords for each section

2. **Document Linking & Cross-References**
   - Verify every wiki page links to related pages
   - Add "See also" sections to analysis documents
   - Cross-reference specs to their source analysis documents
   - Link bug reports to affected tools
   - Create bidirectional links (A → B and B → A)
   - Verify no orphaned documents (every doc reachable from INDEX.md)

3. **Searchability Enhancement**
   - Add keyword metadata to document frontmatter
   - Create topic index (alphabetical A-Z guide)
   - Add tag cloud (most common topics/concepts)
   - Document naming conventions for future wikis
   - Create search guide (how to find specific info)

4. **Agent Instruction Updates**
   - Update `.claude/agents/scribe-research-analyst.md` to reference wikis
   - Update `.claude/agents/scribe-architect.md` to use wiki findings
   - Update `.claude/agents/scribe-coder.md` to check wiki before coding
   - Update `.claude/agents/scribe-review-agent.md` to validate against wikis
   - Update `.claude/agents/scribe-bug-hunter.md` to reference bug wiki
   - Add wiki references to CLAUDE.md instructions
   - Document wiki maintenance protocol (update wikis with every change)

5. **manage_docs Deep Dive**
   - **Critical investigation**: Can manage_docs edit ALL documentation types?
   - Test manage_docs with:
     - ARCHITECTURE_GUIDE.md (section replacement with anchors)
     - PHASE_PLAN.md (status updates, section additions)
     - CHECKLIST.md (status toggles)
     - Research documents (RESEARCH_*.md)
     - Analysis documents (wiki/analysis/*.md)
     - Bug reports (wiki/bugs/*)
   - Document limitations (what can't it edit?)
   - Create SPEC-MANAGE-DOCS-001 for any missing capabilities
   - Verify auto-registration: Does `generate_doc_templates` properly call `ProjectRegistry.record_doc_update()`?
   - Test all 11 actions (replace_section, append, status_update, create_research_doc, etc.)

**Deliverables:**
- `wiki/INDEX.md` - Master navigation document (comprehensive, all-linking)
- `wiki/SEARCH_GUIDE.md` - How to find information in audit
- `wiki/TOPIC_INDEX.md` - Alphabetical topic guide
- Updated `.claude/agents/*.md` files (5 agent instruction updates)
- `wiki/analysis/manage_docs_capability_audit.md` - What manage_docs can/can't do
- `SPEC-MANAGE-DOCS-001-enhancements.yaml` - Missing manage_docs capabilities
- Wiki maintenance protocol document

**Acceptance Criteria:**
- [ ] INDEX.md created with links to ALL documents (100% coverage)
- [ ] All wiki pages have cross-references to related pages
- [ ] No orphaned documents (all reachable from INDEX.md)
- [ ] All 5 agent instructions updated with wiki references
- [ ] manage_docs capabilities fully tested and documented
- [ ] manage_docs auto-registration bug status confirmed
- [ ] SPEC-MANAGE-DOCS-001 created if limitations found
- [ ] Search guide enables easy information discovery
- [ ] ≥10 Scribe log entries with reasoning chains
- [ ] Review Agent grade ≥93%

**Dependencies:** Phase 5 complete (all tool outputs and analysis documents exist)

**Post-Phase 5.5 Wiki Migration Plan:**
- After approval, ALL wikis will be **COPIED** (not moved) from:
  - **SOURCE**: `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/`
  - **DESTINATION**: `/home/austin/projects/MCP_SPINE/scribe_mcp/docs/wiki/`
- **Original audit wikis remain intact** in project directory (permanent audit documentation)
- **Working wikis** at `/docs/wiki/` will be updated as part of Scribe Protocol
- Agent instructions will reference permanent wiki location at `/docs/wiki/`
- Future development will maintain working wikis with every code change (per Scribe Protocol)

**Critical Questions to Answer:**
1. Can manage_docs edit analysis documents in wiki/analysis/?
2. Can manage_docs create/update bug reports in wiki/bugs/?
3. Does manage_docs support all document types (not just the 4 core docs)?
4. Is ProjectRegistry.record_doc_update() called correctly by generate_doc_templates?
5. What are the limitations preventing full doc automation?

---
## Phase 6 — Architecture Synthesis
<!-- ID: phase_6 -->

**Status:** ⏳ PENDING (Awaits Phases 1-5.5 completion)

**Objective:** Synthesize all audit findings into system architecture documentation, refactoring roadmap, and implementation prioritization.

**Agent:** Architect Agent (6-8 hours)

**Key Tasks:**

1. **System Architecture Documentation**
   - Create `wiki/architecture/system_overview.md`
     - High-level component diagram (text/ASCII art)
     - Layer breakdown (tools, storage, utils, state)
     - External integrations (MCP protocol, databases, filesystem)
   - Create `wiki/architecture/component_interactions.md`
     - Tool → Storage → Database flow
     - Config object usage patterns
     - Reminder system integration
   - Create `wiki/architecture/data_flow.md`
     - Request/response cycles
     - Logging flows
     - State management flows

2. **Refactoring Roadmap Creation**
   - Consolidate all implementation specs (SPEC-001 through SPEC-NNN)
   - Prioritize by: Impact (high/medium/low) × Effort (hours)
   - Create priority tiers:
     - **P0 (Critical)**: Bugs, abstraction violations, security issues
     - **P1 (High Impact)**: Token bloat (30-40% savings), major duplication
     - **P2 (Medium Impact)**: Dead code removal, import standardization
     - **P3 (Nice to Have)**: Config consolidation, src/ migration
   - Create dependency ordering (what must be fixed first)
   - Map specs to phases (which can be done in parallel)

3. **Risk Assessment**
   - For each spec, document:
     - Breaking change risk (high/medium/low/none)
     - Test coverage requirements
     - Backward compatibility strategy
     - Rollback plan if issues arise

4. **Token Optimization Strategy**
   - Aggregate token savings across all specs
   - Create tool-by-tool optimization plan
   - Define output verbosity guidelines
   - Document format parameter best practices

5. **Implementation Guidance**
   - Create execution plan for post-audit implementation
   - Define quality gates for each spec
   - Document testing requirements
   - Create monitoring plan (how to verify improvements)

**Deliverables:**
- `wiki/architecture/system_overview.md`
- `wiki/architecture/component_interactions.md`
- `wiki/architecture/data_flow.md`
- `wiki/architecture/refactoring_roadmap.md` (prioritized specs)
- `wiki/architecture/token_optimization_strategy.md`
- `wiki/architecture/implementation_guidance.md`

**Acceptance Criteria:**
- [ ] Complete system architecture documented
- [ ] All specs prioritized into P0/P1/P2/P3 tiers
- [ ] Dependency ordering established (implementation sequence)
- [ ] Risk assessment complete for all specs
- [ ] Token optimization strategy aggregates 30-40% savings
- [ ] ≥10 Scribe log entries with reasoning chains
- [ ] Human review and approval of roadmap

**Dependencies:** Phases 1-5 complete (all audit data gathered)

**Outputs to Human:**
- Request prioritization feedback on P1/P2 specs
- Request go/no-go decision on PostgreSQL parity
- Request approval for src/ migration timing

---
## Phase 7 — Final Review
<!-- ID: phase_7 -->

**Status:** ⏳ PENDING (Awaits Phase 6 completion)

**Objective:** Quality assurance on all audit deliverables, grading, approval/rejection recommendations, handoff preparation.

**Agents:** Review Agent + Human (3-4 hours)

**Review Agent Tasks:**

1. **Wiki Page Quality Assessment**
   - Grade all 28 tool wiki pages (completeness, accuracy, clarity)
   - Validate cross-references (all links work, no orphaned pages)
   - Check adherence to template structure
   - Verify all sections populated with real content (no placeholders)

2. **Implementation Spec Validation**
   - Review all SPEC-XXX files for:
     - Testability (can we verify the fix works?)
     - Safety (breaking change risk assessment accurate?)
     - Clarity (can Coder Agent implement from spec alone?)
   - Verify YAML format correctness
   - Check before/after code examples present

3. **Bug Report Verification**
   - Review all BUG-XXX reports for:
     - Reproduction steps (clear and actionable?)
     - Root cause analysis (reasoning chain present?)
     - Fix viability (proposed solution sound?)
   - Verify severity ratings appropriate

4. **Analysis Report Quality**
   - Review duplication_report.md (all duplicates found?)
   - Review dead_code_report.md (safety analysis thorough?)
   - Review token_analysis.md (measurements valid?)
   - Review import_graph.md (all patterns cataloged?)

5. **Architecture Documentation Review**
   - Review system_overview.md (accurate and complete?)
   - Review refactoring_roadmap.md (prioritization sound?)
   - Review token_optimization_strategy.md (achieves 30-40% target?)

6. **Grading**
   - Grade each phase (Research Agents A-H, Architect Agent)
   - Overall audit quality score
   - **Quality Gate**: ≥93% required for approval

**Human Review Tasks:**

1. **Strategic Decisions**
   - Approve/reject PostgreSQL parity work (go/no-go)
   - Approve/reject src/ migration timing (now vs later)
   - Prioritize P1/P2 implementation specs (which to do first)

2. **Roadmap Approval**
   - Review refactoring roadmap (prioritization makes sense?)
   - Approve token optimization strategy (acceptable trade-offs?)
   - Sign-off on implementation guidance (ready to execute?)

3. **Final Audit Sign-Off**
   - Approve audit completion (deliverables meet objectives?)
   - Approve handoff to future implementation phases

**Deliverables:**
- `wiki/review/final_review.md` (Review Agent assessment)
- Agent grades (all phases graded ≥93%)
- Human approval document (strategic decisions recorded)
- Handoff document (how to use audit artifacts)

**Acceptance Criteria:**
- [ ] Review Agent grades all phases ≥93%
- [ ] All wiki cross-references validated
- [ ] All implementation specs reviewed and approved
- [ ] Human sign-off on refactoring roadmap
- [ ] Human decisions recorded for PostgreSQL and src/ migration
- [ ] Audit completion logged to global log

**Dependencies:** Phase 6 complete (all deliverables ready for review)

**Final Log Entry:**
```python
append_entry(
    message="Scribe Systematic Audit #1 COMPLETE: 28 tools documented, XX bugs found, YY specs created, ZZ% token reduction potential",
    status="success",
    agent="Orchestrator",
    log_type="global",
    meta={
        "project": "scribe_systematic_audit_1",
        "entry_type": "audit_complete",
        "tools_documented": 28,
        "bugs_found": "XX",
        "specs_created": "YY",
        "token_reduction_potential": "ZZ%",
        "wiki_pages": "NN"
    }
)
```

---
## Milestone Tracking
<!-- ID: milestone_tracking -->

| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Phase 0 Complete | 2026-01-05 | ArchitectAgent | ✅ DONE | ARCHITECTURE_GUIDE.md created |
| Phase 1 Start | 2026-01-06 | Orchestrator | 🔜 READY | 4 Research Agents assigned |
| Phase 1 Complete | 2026-01-07 | ResearchAgents A-D | ⏳ PENDING | 28 tool wiki pages |
| Phase 2 Complete | 2026-01-08 | ResearchAgent-E | ⏳ PENDING | Storage docs + specs |
| Phase 3 Complete | 2026-01-08 | ResearchAgent-F | ⏳ PENDING | Import analysis |
| Phase 4 Complete | 2026-01-09 | ResearchAgent-G | ⏳ PENDING | Duplication report |
| Phase 5 Complete | 2026-01-09 | ResearchAgent-H | ⏳ PENDING | Token analysis |
| Phase 6 Complete | 2026-01-10 | ArchitectAgent | ⏳ PENDING | Refactoring roadmap |
| Phase 7 Complete | 2026-01-11 | ReviewAgent + Human | ⏳ PENDING | Final approval |
| **AUDIT COMPLETE** | **2026-01-11** | **Orchestrator** | ⏳ PENDING | **Global log entry** |

---
## Retro Notes & Adjustments
<!-- ID: retro_notes -->

### Phase 0 Retro (2026-01-05)

**What Went Well:**
- Comprehensive charter created in ~1.5 hours
- Baseline metrics gathered efficiently
- Wiki structure well-defined for agent consumption
- YAML spec and bug report formats provide clear standards

**What Could Be Improved:**
- Initial attempt to use manage_docs failed (doc key issue)
- Fell back to Edit tool - manage_docs integration needs Phase 1 validation

**Adjustments:**
- None required - proceeding to Phase 1 as planned

**Lessons Learned:**
- manage_docs requires correct document key registration
- Edit tool reliable fallback for architecture documents
- Scribe logging with reasoning chains takes ~10-15% additional time but critical for audit trail

---

**Document Control:**
- **Version**: 1.0 (Phase 0 Complete)
- **Author**: ArchitectAgent
- **Last Updated**: 2026-01-05 02:02:00 UTC
- **Status**: ACTIVE - Phase 1 Ready
- **Next Review**: After Phase 1 completion (parallel tool audits)
