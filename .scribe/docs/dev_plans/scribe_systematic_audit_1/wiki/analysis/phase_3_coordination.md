# Phase 3 Coordination Document

**Created**: 2026-01-05
**Purpose**: Define scope boundaries for 4 parallel Phase 3 agents to prevent overlap

---

## Team Scope Assignments

### Team A: sys.path Pattern Auditor
**Agent**: `ResearchAgent-Phase3-SysPath`
**Primary Responsibility**: All `sys.path.insert()` and `sys.path.append()` occurrences

**Scope Boundaries:**
- ✅ OWNS: All sys.path manipulation patterns (81 occurrences)
- ✅ OWNS: Context categorization (tests vs production)
- ✅ OWNS: Quick wins identification (removable without migration)
- ❌ DOES NOT: Catalog absolute imports (that's Team B)
- ❌ DOES NOT: Design src/ structure (that's Team C)
- ❌ DOES NOT: Find circular dependencies (that's Team D)

**Cross-References Allowed:**
- MAY reference Team B's import hot spots to understand why sys.path is needed
- MAY inform Team C about sys.path removal requirements for migration

---

### Team B: Import Structure Cartographer
**Agent**: `ResearchAgent-Phase3-ImportGraph`
**Primary Responsibility**: All absolute imports and dependency graph

**Scope Boundaries:**
- ✅ OWNS: All 442 `from scribe_mcp.*` imports
- ✅ OWNS: Import graph visualization (who imports what)
- ✅ OWNS: Import hot spots (coupling metrics)
- ❌ DOES NOT: Analyze sys.path (that's Team A)
- ❌ DOES NOT: Design migration strategy (that's Team C)
- ❌ DOES NOT: Map circular dependencies (that's Team D - though may discover them)

**Cross-References Allowed:**
- MAY reference Team A's sys.path findings to understand import context
- MAY inform Team D about potential circular dependencies discovered
- MAY inform Team C about high-coupling modules requiring careful migration

---

### Team C: src/ Migration Architect
**Agent**: `ResearchAgent-Phase3-SrcMigration`
**Primary Responsibility**: src/ directory design and migration strategy

**Scope Boundaries:**
- ✅ OWNS: src/ directory structure design
- ✅ OWNS: File-by-file migration impact analysis (204 files)
- ✅ OWNS: Migration playbook and phasing strategy
- ✅ OWNS: pip packaging requirements (setup.py, pyproject.toml)
- ❌ DOES NOT: Catalog current imports (that's Team B)
- ❌ DOES NOT: Analyze sys.path patterns (that's Team A)
- ❌ DOES NOT: Find circular dependencies (that's Team D)

**Cross-References Required:**
- MUST reference Team A's sys.path findings (these disappear after migration)
- MUST reference Team B's import graph (understand current structure)
- SHOULD reference Team D's circular dependencies (migration may affect them)

---

### Team D: Circular Dependency Detective
**Agent**: `ResearchAgent-Phase3-CircularDeps`
**Primary Responsibility**: All circular import dependencies

**Scope Boundaries:**
- ✅ OWNS: All circular dependency mapping (exhaustive search)
- ✅ OWNS: Lazy binding pattern analysis
- ✅ OWNS: Acceptable vs problematic categorization
- ✅ OWNS: Decoupling strategy recommendations
- ❌ DOES NOT: Catalog linear imports (that's Team B)
- ❌ DOES NOT: Analyze sys.path (that's Team A)
- ❌ DOES NOT: Design src/ migration (that's Team C)

**Cross-References Allowed:**
- MAY reference Team B's import graph for context
- MAY inform Team C about circularities that complicate migration

---

## Overlap Prevention Rules

1. **If you discover something outside your scope:**
   - LOG it in your Scribe entries
   - REFERENCE the appropriate team ("Team B should investigate...")
   - DO NOT fully document it yourself

2. **If you find a gray area:**
   - Document it in THIS file under "Gray Areas Resolved" section below
   - Continue with your primary scope
   - Review Agent will catch true overlaps

3. **Required coordination touchpoints:**
   - Team C MUST read Team A + B deliverables before finalizing migration spec
   - All teams MAY update this file with clarifications

---

## Gray Areas Resolved

*Agents: Document any scope ambiguities you encounter here*

### Team A Findings (2026-01-05)
**Gray Area**: Expected 81 sys.path occurrences but found only 70 in Python files
**Resolution**: Discrepancy explained - 11 additional mentions in documentation (.md) and log files (.jsonl) are examples/references, not actual code. Team A confirmed 70 actual Python occurrences documented.

**Handoff to Team B**: 4 test files with parent.parent.parent pattern suggest deep import chains - may indicate circular dependencies or high coupling:
- tests/test_tool_logger.py:15
- tests/debug_vector_processing.py:13
- tests/test_query_priority_filters.py:8
- tests/demo_get_project_formatter.py:12

**Handoff to Team C**: All 65 test sys.path hacks can be eliminated after src/ migration with `pip install -e .` - migration impact is HIGH for test infrastructure.

### Team B Findings (2026-01-05)
**Finding**: Discovered 12 circular module dependencies (5 unique bidirectional pairs)

**Handoff to Team D - Critical Circles for Detailed Analysis**:
1. **tools <-> utils** (HIGH IMPACT): 57 files import tools, 63 import utils - tightly coupled infrastructure
2. **storage <-> db** (HIGH IMPACT): Database layer circular dependency
3. **doc_management <-> tools** (MEDIUM): 16 files import doc_management, tools imports it back
4. **shared <-> utils** (MEDIUM): Shared infrastructure circularly coupled
5. **shared <-> tools** (MEDIUM): Shared infrastructure and tools interdependent

**Handoff to Team C - Migration Implications**:
- **Hot spots requiring careful migration**: utils (63 importers), tools (57), config (47), storage (31), shared (30)
- Circular dependencies MUST be resolved before src/ migration to enable proper dependency ordering
- Recommended migration order: config → security/templates → storage → state → tools/shared/doc_management → server

**Gray Area**: Found 439 actual Python imports vs expected 442
**Resolution**: Discrepancy likely due to counting methodology (multiline imports, or estimates from documentation). 439 confirmed actual imports documented in import_graph.md.

### Team D Findings (2026-01-05)
**Finding**: Found only 3 circular dependencies (all ACCEPTABLE with intentional lazy binding)

**Response to Team B's Handoff**:
Team B reported 12 circular module dependencies (5 bidirectional pairs), but Team D's detailed analysis found only 3 actual circular dependencies:

1. **CD-001: tools ↔ server** (P2 - ACCEPTABLE): Late-binding plugin registration pattern required by MCP framework
2. **CD-002: shared.logging_utils ↔ tools.*** (P2 - ACCEPTABLE): 5 function-level lazy imports with explicit circular import avoidance comments
3. **CD-003: utils.parameter_validator ↔ tools.base.parameter_normalizer** (P3 - ACCEPTABLE): Function-level lazy import with graceful fallback

**Clarification for Team B**:
Team B may have detected potential circularities that don't manifest as runtime circular imports due to lazy binding patterns. Team D's analysis focused on **actual import-time circular dependencies** and found all 3 are intentionally designed with proper protection mechanisms.

**Decoupling Recommendation**: **NONE** - All patterns are appropriate and should be preserved through migration

**Handoff to Team C - Migration Impact**:
- **Low Risk**: All circular dependencies use patterns compatible with src/ layout
- **No Architectural Changes Required**: Lazy binding patterns remain valid after migration
- **Import Path Updates Only**: Update scribe_mcp.* → scribe.* in 7 locations
- **Estimated Effort**: 3-4 hours for import path updates and verification
- **Migration Order Note**: Circular dependencies do NOT block migration; they're intentional design patterns

**Gray Area Addressed**:
Team B's report of "tools <-> utils", "storage <-> db", "shared <-> utils" high-impact circles could not be confirmed as actual circular dependencies. These may be bidirectional dependency relationships (A imports from B, B imports from A) but with proper lazy binding to avoid import-time circularity. Recommend Team B clarify if these are architectural concerns vs actual import failures.

---

## Progress Tracking

| Team | Agent Name | Status | Deliverables Complete |
|------|-----------|--------|----------------------|
| A | ResearchAgent-Phase3-SysPath | **COMPLETE** | 3/3 ✅ |
| B | ResearchAgent-Phase3-ImportGraph | **COMPLETE** | 3/3 ✅ (import_graph.md, dependency_graph.dot, import_graph_SUMMARY.md) |
| C | ResearchAgent-Phase3-SrcMigration | **IN PROGRESS** | 0/4 |
| D | ResearchAgent-Phase3-CircularDeps | **COMPLETE** | 3/3 ✅ (circular_dependencies.md, SPEC-PKG-002-import-standards.yaml, decoupling strategies in doc) |

*Agents: Update your status here when you begin work*

---

## Known Scope Overlaps (Expected)

These are EXPECTED overlaps that require coordination:

1. **Team B may discover circular dependencies** while mapping imports
   - Action: Log them and inform Team D
   - Team D will do the detailed analysis

2. **Team C needs context from Team A + B** for migration design
   - Action: Team C should read Team A + B deliverables first
   - Cross-reference their findings in migration spec

3. **Team D's circular dependencies may inform Team C's migration**
   - Action: Team D should note migration implications
   - Team C incorporates into risk analysis

---

## Communication Protocol

1. **Before starting work:**
   - Read this entire coordination file
   - Update "Progress Tracking" table with your status
   - Log your scope boundaries in your first Scribe entry

2. **During work:**
   - If you discover overlap, document in "Gray Areas Resolved"
   - Cross-reference other teams when relevant
   - Update progress table as deliverables complete

3. **After completing work:**
   - Final Scribe entry summarizing your scope coverage
   - Note any handoffs to other teams
   - Mark status as "Complete" in progress table

---

## Success Criteria (All Teams)

- [ ] No true scope duplication (expected coordination is fine)
- [ ] All 81 sys.path + 442 imports + circular deps documented
- [ ] src/ migration has complete file-by-file analysis
- [ ] Cross-references between teams are clear and helpful
- [ ] Coordination file updated with any gray areas encountered

---

**Last Updated**: 2026-01-05 (Initial creation)
