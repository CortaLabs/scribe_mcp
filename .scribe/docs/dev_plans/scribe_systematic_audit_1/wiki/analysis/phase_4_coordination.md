# Phase 4 Coordination Document

**Created**: 2026-01-05
**Purpose**: Define scope boundaries for 5 parallel Phase 4 agents to prevent overlap

---

## Team Scope Assignments

### Team A: Dead Code Detective
**Agent**: `ResearchAgent-Phase4-DeadCode`
**Primary Responsibility**: Identify all unreferenced/unused code across the codebase
**Priority**: CRITICAL (Top 3)

**Scope Boundaries:**
- ✅ OWNS: All unreferenced functions, classes, methods across 204 files
- ✅ OWNS: Static analysis (AST parsing) for import graph vs usage
- ✅ OWNS: Orphaned utility detection
- ✅ OWNS: Coverage analysis integration (pytest --cov reports)
- ❌ DOES NOT: Analyze code similarity (that's Team B)
- ❌ DOES NOT: Validate API documentation (that's Team D)
- ❌ DOES NOT: Audit legacy fallback patterns (that's Team C)

**Cross-References Allowed:**
- MAY reference Team B's duplication findings (dead + duplicated = higher priority removal)
- MAY inform Team E about false positives requiring manual verification

**Deliverables:**
- `wiki/analysis/dead_code_catalog.md` - Complete inventory with file:line references
- `wiki/analysis/orphaned_utilities.md` - Standalone utility analysis
- `SPEC-DEAD-001-removal-plan.yaml` - Prioritized removal strategy
- Coverage gap analysis (functions with 0% coverage)

---

### Team B: Duplication Hunter
**Agent**: `ResearchAgent-Phase4-Duplication`
**Primary Responsibility**: Detect and catalog all code duplication patterns
**Priority**: CRITICAL (Top 3)

**Scope Boundaries:**
- ✅ OWNS: All code similarity detection (≥80% fuzzy match threshold)
- ✅ OWNS: Known duplication tracking (DUPLICATION-002: doc gathering 3x, _count_log_entries 2x)
- ✅ OWNS: Token-level duplication (repeated string literals, regex patterns)
- ✅ OWNS: Consolidation strategy design (what extracts where)
- ❌ DOES NOT: Find dead code (that's Team A)
- ❌ DOES NOT: Validate extracted module contracts (that's Team E)
- ❌ DOES NOT: Audit legacy fallback duplication (coordinate with Team C)

**Cross-References Allowed:**
- MAY reference Team A's dead code findings (dead + duplicated code)
- MAY inform Team C about legacy duplication patterns
- MAY reference Wave 1-3 module bucket proposals for consolidation targets

**Deliverables:**
- `wiki/analysis/code_duplication_catalog.md` - All patterns with similarity scores
- `wiki/analysis/duplication_impact.md` - LOC waste quantification
- `SPEC-DUP-001-consolidation-plan.yaml` - Extraction strategy with [BUCKET:] tags
- Before/After LOC reduction estimates

---

### Team C: Legacy Code Archaeologist
**Agent**: `ResearchAgent-Phase4-LegacyCode`
**Primary Responsibility**: Identify and document all legacy/fallback patterns
**Priority**: STANDARD

**Scope Boundaries:**
- ✅ OWNS: All try/except fallback patterns
- ✅ OWNS: Legacy configuration compatibility code
- ✅ OWNS: Deprecated method wrappers still in use
- ✅ OWNS: "TODO: remove after migration" comments
- ✅ OWNS: Old API version compatibility shims
- ❌ DOES NOT: Find dead code (that's Team A)
- ❌ DOES NOT: Validate current API docs (that's Team D)
- ❌ DOES NOT: Measure duplication similarity (that's Team B)

**Cross-References Allowed:**
- MAY reference Team B's duplication findings (legacy duplication)
- MAY inform Team D about outdated API patterns still documented
- MAY reference Phase 3 findings (sys.path legacy patterns)

**Deliverables:**
- `wiki/analysis/legacy_patterns_catalog.md` - All fallback code with justifications
- `wiki/analysis/deprecation_candidates.md` - Safe removal assessment
- `SPEC-LEGACY-001-cleanup-plan.yaml` - Phased removal strategy
- Migration dependency analysis (what blocks legacy removal)

---

### Team D: API Documentation Validator
**Agent**: `ResearchAgent-Phase4-APIValidator`
**Primary Responsibility**: Verify ALL API documentation matches actual code behavior
**Priority**: CRITICAL (Top 3)

**Scope Boundaries:**
- ✅ OWNS: All 28 tool API signature validation (Phases 1-2 wiki pages)
- ✅ OWNS: **DEEP behavior verification** (not just signatures, test actual behavior)
- ✅ OWNS: Return type validation (docs vs actual code)
- ✅ OWNS: Parameter validation (required vs optional, types, defaults)
- ✅ OWNS: Phase 3 YAML spec validation (file structures match reality)
- ✅ OWNS: Error message documentation (actual exceptions vs documented)
- ✅ OWNS: Edge case behavior documentation (null handling, empty inputs)
- ❌ DOES NOT: Find dead code (that's Team A)
- ❌ DOES NOT: Design new APIs (that's Phase 6 Architect work)

**Cross-References Required:**
- MUST verify ALL Phase 1 wiki pages (28 tools)
- MUST verify ALL Phase 2 storage backend docs
- MUST verify Phase 3 YAML specs (import paths, file structures)
- MAY reference Team C's legacy findings (deprecated APIs still documented)

**Special Requirements:**
- **Behavior testing required**: Not just "does signature match?" but "does it DO what docs say?"
- Example: If docs say "returns dict with 'status' key", verify code actually returns that
- Example: If docs say "raises ValueError on empty input", verify exception actually raised
- Track discrepancies as BUG-API-### issues with severity ratings

**Deliverables:**
- `wiki/analysis/api_validation_report.md` - All 28 tools verified with pass/fail
- `wiki/analysis/api_discrepancies.md` - Docs vs reality gaps
- `wiki/bugs/api_bugs/` - Individual bug reports for critical mismatches
- `SPEC-API-001-doc-corrections.yaml` - Documentation fix specifications
- Behavior test results (what was tested, what passed/failed)

---

### Team E: Audit Cross-Validator
**Agent**: `ResearchAgent-Phase4-AuditValidator`
**Primary Responsibility**: Validate consistency across ALL prior phase findings
**Priority**: STANDARD (Goes LAST - depends on Teams A-D)

**Scope Boundaries:**
- ✅ OWNS: Cross-referencing findings from Phases 1-3 + Teams A-D
- ✅ OWNS: Contradiction detection (one phase says X, another says Y)
- ✅ OWNS: Completeness verification (did we cover all 204 files?)
- ✅ OWNS: Module bucket overlap detection (multiple buckets claiming same code)
- ✅ OWNS: Token metric consistency (Phase 1 vs actual measurements)
- ✅ OWNS: Spec feasibility check (can YAML specs actually be implemented?)
- ❌ DOES NOT: Find new dead code (that's Team A)
- ❌ DOES NOT: Find new duplication (that's Team B)
- ❌ DOES NOT: Validate APIs independently (that's Team D)

**Cross-References Required (ALL teams):**
- MUST read ALL Wave 1-3 wiki pages (28+ documents)
- MUST read Phase 2 storage audit (7 documents)
- MUST read Phase 3 import/packaging audit (16+ documents)
- MUST read Teams A-D Phase 4 deliverables
- MUST verify cross_cutting_concerns.md completeness

**Special Requirements:**
- **Goes LAST**: Cannot start until Teams A-D complete
- Flags contradictions for orchestrator resolution
- Proposes wiki structure improvements for Phase 6 Architect
- Identifies gaps requiring additional research

**Deliverables:**
- `wiki/analysis/audit_validation_report.md` - Consistency findings
- `wiki/analysis/contradictions_resolved.md` - Conflicts identified and resolved
- `wiki/analysis/coverage_gaps.md` - What we missed (if anything)
- `SPEC-META-001-wiki-improvements.yaml` - Structure enhancements for Phase 6
- Final audit statistics (files covered, LOC audited, findings count)

---

## Overlap Prevention Rules

1. **If you discover something outside your scope:**
   - LOG it in your Scribe entries with `meta={"handoff_to": "Team X"}`
   - REFERENCE the appropriate team in your deliverables
   - DO NOT fully document it yourself (brief note only)

2. **If you find a gray area:**
   - Document it in THIS file under "Gray Areas Resolved" section below
   - Continue with your primary scope
   - Orchestrator will resolve true overlaps

3. **Required coordination touchpoints:**
   - Team E MUST read ALL Teams A-D deliverables before finalizing
   - Team D MAY reference Team C's legacy findings
   - Team B MAY reference Team A's dead code findings
   - All teams MAY update this file with clarifications

---

## Gray Areas Resolved

*Agents: Document any scope ambiguities you encounter here*

### Team C (Legacy) → Team B (Duplication) - 2026-01-05

**Finding**: Duplicate settings import fallback code in `utils/optimization.py`
- **Location**: Lines 34 and 68 (identical pattern)
- **Pattern**: Same try/except ImportError with hardcoded fallback values
- **Action**: Team B should catalog this as code duplication
- **Logged by**: ResearchAgent-Phase4-LegacyCode

### Team C (Legacy) → Team D (API Validator) - 2026-01-05

**Finding**: Deprecated parameter warning in `utils/files.py:775`
- **Docstring**: "DEPRECATED: Use template_content parameter in rotate_file instead"
- **Question**: Is old parameter still accepted by function signature?
- **Action**: Team D should verify if deprecated parameter exists and if it's still used anywhere
- **Logged by**: ResearchAgent-Phase4-LegacyCode

---

## Progress Tracking

| Team | Agent Name | Status | Deliverables Complete | Priority |
|------|-----------|--------|----------------------|----------|
| A | ResearchAgent-Phase4-DeadCode | **PENDING** | 0/4 | CRITICAL |
| B | ResearchAgent-Phase4-Duplication | **IN PROGRESS** | 0/4 | CRITICAL |
| C | ResearchAgent-Phase4-LegacyCode | **✅ COMPLETE** | 4/4 | STANDARD |
| D | ResearchAgent-Phase4-APIValidator | **PENDING** | 0/4 | CRITICAL |
| E | ResearchAgent-Phase4-AuditValidator | **PENDING** | 0/5 | STANDARD (Last) |

*Agents: Update your status here when you begin work*

---

## Known Scope Overlaps (Expected)

These are EXPECTED overlaps that require coordination:

1. **Team A may find duplicated dead code**
   - Action: Log it and inform Team B
   - Team B will quantify the duplication overlap

2. **Team B may find legacy duplication patterns**
   - Action: Log it and inform Team C
   - Team C will assess if legacy code is safe to remove

3. **Team C may find undocumented legacy APIs**
   - Action: Log it and inform Team D
   - Team D will verify if docs need updates or removal

4. **Team D may discover APIs that are actually dead code**
   - Action: Log it and inform Team A
   - Team A will confirm if code is unreferenced

5. **Team E validates everything from Teams A-D**
   - Action: Team E reads ALL deliverables and cross-validates
   - Team E goes LAST to catch any inconsistencies

---

## Communication Protocol

1. **Before starting work:**
   - Read this entire coordination file
   - Update "Progress Tracking" table with your status
   - Log your scope boundaries in your first Scribe entry
   - Review relevant prior phase deliverables

2. **During work:**
   - If you discover overlap, document in "Gray Areas Resolved"
   - Cross-reference other teams when relevant with `meta={"related_team": "X"}`
   - Update progress table as deliverables complete
   - Use Scribe entries to coordinate handoffs

3. **After completing work:**
   - Final Scribe entry summarizing your scope coverage
   - Note any handoffs to other teams in your deliverables
   - Mark status as "Complete" in progress table
   - Update any relevant sections in this coordination file

---

## Execution Order

**Critical Path:**
1. **Teams A, B, C, D** - Can run in TRUE PARALLEL (no dependencies)
2. **Team E** - MUST wait for Teams A-D to complete (depends on all findings)

**Priority Order for Orchestrator:**
1. Deploy Teams A, B, D first (all CRITICAL)
2. Deploy Team C (STANDARD, can run alongside)
3. Deploy Team E LAST (after A-D complete)

---

## Success Criteria (All Teams)

**Individual Team Success:**
- [ ] All deliverables created with proper file:line references
- [ ] ≥10 Scribe log entries with reasoning chains (why/what/how)
- [ ] At least 1 machine-readable YAML spec per team
- [ ] Cross-references to other teams are clear and helpful
- [ ] Coordination file updated with any gray areas encountered

**Phase 4 Overall Success:**
- [ ] All 204 Python files checked for dead code (Team A)
- [ ] All duplication patterns cataloged with ≥80% similarity (Team B)
- [ ] All legacy/fallback patterns documented (Team C)
- [ ] All 28 tool APIs validated with behavior tests (Team D)
- [ ] All prior phase findings cross-validated (Team E)
- [ ] No contradictions between teams (or resolved by orchestrator)
- [ ] Clear handoff documentation for Phase 6 implementation

---

## Special Notes

**For Team D (API Validator):**
- **This is the most critical validation team**
- User quote: "API depth should be deep, I want it to verify behavior too. this team is crucial"
- **Not just signature matching** - must test actual behavior matches documentation
- Example validations required:
  - If docs say "returns dict", verify actual return is dict
  - If docs say "raises ValueError on empty", verify exception is raised
  - If docs say "default is 10", verify code default is 10
  - If docs say "modifies file atomically", verify atomicity in code
- Create test cases to verify behavior, don't just read signatures
- Track severity: CRITICAL (breaks functionality), HIGH (misleading), MEDIUM (incomplete), LOW (minor)

**For Team E (Audit Validator):**
- **Goes absolutely LAST** - cannot start until Teams A-D finish
- Primary job is **consistency validation**, not new research
- If you find contradictions, flag for orchestrator (don't resolve yourself)
- Your deliverables prepare Phase 6 Architect for synthesis work

**For All Teams:**
- **READ-ONLY mode** - document findings, don't fix code
- **Evidence required** - every claim needs file:line reference
- **Token measurements** - if claiming token bloat, measure with tiktoken
- **YAML specs** - all implementation plans must be machine-readable

---

**Last Updated**: 2026-01-05 (Initial creation)
