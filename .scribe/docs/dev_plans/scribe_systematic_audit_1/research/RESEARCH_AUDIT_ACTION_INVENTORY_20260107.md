# 🔬 Research Audit Action Inventory 20260107 — scribe_systematic_audit_1
**Author:** ResearchAgent-WikiAnalysis
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-07 21:44:11 UTC

> Comprehensive inventory of all actions, specs, bugs, and cleanup tasks identified in the scribe_systematic_audit_1 wiki. This document provides orchestrator-ready prioritized task lists extracted from 94 wiki documents across 12 directories.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Create comprehensive action inventory from audit wiki to enable orchestrator planning and implementation prioritization.

**Key Takeaways:**
- **CRITICAL BLOCKER:** BUG-MANAGE-DOCS-001 prevents 10+ manage_docs actions from functioning
- **17 manage_docs actions** inventoried: 2 tested working, 1 tested blocked, 14 untested (10 likely blocked)
- **13 implementation specs** identified across 5 categories (bug fixes, token optimization, format improvements, infrastructure, code quality)
- **4 documented bugs** requiring fixes
- **Major cleanup opportunities:** 238 unused imports, 18 dead functions (150-200 LOC reduction), 1,893 LOC duplication waste (52% reduction potential)
- **Test coverage:** Only 17.6% of manage_docs actions tested - comprehensive validation blocked by database bug


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-WikiAnalysis

**Investigation Window:** 2026-01-07 (wiki analysis) | Audit created: 2026-01-04 to 2026-01-05

**Focus Areas:**
- [x] Complete inventory of 17 manage_docs actions with test status
- [x] Enumeration of all SPEC-* implementation specifications
- [x] Catalog of documented bugs and blockers
- [x] Identification of cleanup tasks (dead code, duplication)
- [x] Priority classification (P0/P1/P2/P3)

**Dependencies & Constraints:**
- Wiki created by scribe_systematic_audit_1 project over 7-day period
- Phase 5.5 manage_docs audit incomplete due to critical blocker
- Some SPEC files in two directories: wiki/specs/ (11 files) and wiki/implementation_specs/ (2 files)
- Migration playbook exists but src/ migration not yet executed


---
## Findings
<!-- ID: findings -->

### Finding 1: manage_docs Critical Blocker
- **Summary:** BUG-MANAGE-DOCS-001 prevents 80%+ of manage_docs functionality. Database missing `docs_json` column causes DOC_NOT_FOUND errors for all registered document operations.
- **Evidence:**
  - `wiki/PHASE_5_5_MANAGE_DOCS_AUDIT_SUMMARY.md` (lines 19-30, 189-224)
  - `wiki/analysis/manage_docs_action_matrix.md` (complete action compatibility matrix)
  - `wiki/specs/SPEC-MANAGE-DOCS-001-database-docs-field.yaml` (implementation spec)
- **Impact:** Blocks 10+ actions: list_sections, list_checklist_items, replace_section, apply_patch, replace_range, replace_text, append, status_update, normalize_headers, generate_toc
- **Confidence:** 0.95 (High)

### Finding 2: Test Coverage Gap
- **Summary:** Only 3 of 17 manage_docs actions have been tested (17.6% coverage). 2 pass (create_bug_report, create_research_doc), 1 blocked (list_sections).
- **Evidence:** `wiki/analysis/manage_docs_action_matrix.md` (lines 11-29)
- **Status:** Testing blocked - remaining 14 actions likely fail with same DOC_NOT_FOUND error
- **Confidence:** 0.90 (High)

### Finding 3: Implementation Specs Ready
- **Summary:** 13 YAML implementation specs created across 5 categories, ready for Coder Agent deployment
- **Evidence:** `wiki/specs/*.yaml` (11 files) + `wiki/implementation_specs/*.yaml` (2 files)
- **Categories:** Bug fixes (2), Token optimization (3), Format improvements (2), Infrastructure (2), Code quality (2)
- **Confidence:** 0.95 (High)

### Finding 4: Significant Cleanup Opportunities
- **Summary:** Dead code and duplication analysis found substantial reduction opportunities
- **Evidence:**
  - `wiki/analysis/DEAD_CODE_SUMMARY.md`: 238 unused imports, 18 dead functions
  - `wiki/analysis/code_duplication_catalog.md`: 1,893 LOC waste across 4 patterns
- **Reduction Potential:** 150-200 LOC (dead code) + 800-900 LOC (duplication) = ~1,000 LOC total
- **Confidence:** 0.93 (High)

### Finding 5: Orchestration Guidance Complete
- **Summary:** Comprehensive implementation guidance created for post-audit work
- **Evidence:**
  - `wiki/MIGRATION_PLAYBOOK.md`: 30KB, 1,315 lines, 8-phase src/ migration guide
  - `wiki/ORCHESTRATION_RULES.md`: Quality enforcement policy
- **Confidence:** 0.90 (High)


---
## Technical Analysis
<!-- ID: technical_analysis -->

### manage_docs Action Breakdown

**Category A: Working Actions (Auto-Path Generation)** ✅
1. **create_bug_report** - TESTED ✅ PASS
   - Auto-generates path: `docs/bugs/<category>/<date>_<slug>/report.md`
   - Requires: `metadata.category` (REQUIRED)
   - Test date: 2026-01-05

2. **create_research_doc** - TESTED ✅ PASS
   - Auto-generates path: `docs/dev_plans/<project>/research/<doc_name>.md`
   - Requires: `doc_name` (REQUIRED)
   - Test date: 2026-01-05

3. **create_review_report** - UNTESTED ⚠️ (Likely works)
   - Expected path: `docs/dev_plans/<project>/REVIEW_REPORT_<stage>_<timestamp>.md`
   - Requires: `metadata.stage`

4. **create_agent_report_card** - UNTESTED ⚠️ (Likely works)
   - Expected path: `docs/dev_plans/<project>/AGENT_REPORT_CARD_<agent>_<stage>_<timestamp>.md`
   - Requires: `metadata.agent_name`, `metadata.stage`

**Category B: Blocked Actions (Requires docs Field)** ❌
5. **list_sections** - TESTED ❌ BLOCKED
   - Error: DOC_NOT_FOUND (database missing docs_json column)
   - Test date: 2026-01-05

6. **list_checklist_items** - UNTESTED ⚠️ (Likely blocked)
7. **replace_section** - UNTESTED ⚠️ (Likely blocked)
8. **apply_patch** - UNTESTED ⚠️ (Likely blocked)
9. **replace_range** - UNTESTED ⚠️ (Likely blocked)
10. **replace_text** - UNTESTED ⚠️ (Likely blocked)
11. **append** - UNTESTED ⚠️ (Likely blocked)
12. **status_update** - UNTESTED ⚠️ (Likely blocked)
13. **normalize_headers** - UNTESTED ⚠️ (Likely blocked)
14. **generate_toc** - UNTESTED ⚠️ (Likely blocked)

**Category C: Unknown Status (Complex Dependencies)** ⚠️
15. **search** - UNTESTED ⚠️ (Partial dependency)
    - Exact/fuzzy modes: Likely blocked
    - Semantic mode: Unknown (may bypass docs lookup)

16. **batch** - UNTESTED ⚠️ (Meta-action)
    - Status depends on delegated actions

17. **validate_crosslinks** - UNTESTED ⚠️ (Likely blocked)

### Implementation Specifications Inventory

**P0 - CRITICAL (Blockers)**
1. **SPEC-MANAGE-DOCS-001** - Database docs_json column
   - Priority: CRITICAL
   - Effort: 4-6 hours
   - Blocks: 10+ manage_docs actions
   - Status: DRAFT
   - Location: `wiki/specs/SPEC-MANAGE-DOCS-001-database-docs-field.yaml`

2. **SPEC-SET-001** - set_project empty log bug
   - Priority: HIGH
   - Bug: BUG-001 (line 459 marking issue)
   - Location: `wiki/specs/SPEC-SET-001-bug-fix.yaml`

**P1 - HIGH (Token Optimization)**
3. **SPEC-TOKEN-001** - list_projects optimization (40% reduction target)
4. **SPEC-TOKEN-002** - append_entry optimization (35% reduction target)
5. **SPEC-TOKEN-003** - Global output refinement (30-40% reduction)

**P2 - MEDIUM (Format Improvements)**
6. **SPEC-FORMAT-001** - Format parameter standardization
7. **SPEC-FORMAT-002** - Readable mode enhancement

**P2 - MEDIUM (Code Quality)**
8. **SPEC-DUP-001** - Consolidation plan (1,893 LOC duplication)
9. **SPEC-META-001** - Wiki improvements

**P2 - MEDIUM (Infrastructure)**
10. **SPEC-GEN-001** - Registry integration
11. **SPEC-PKG-001** - src/ migration (6-9 hour effort)
12. **SPEC-STORAGE-001** - Enforce abstraction (from implementation_specs/)
13. **SPEC-PG-001** - PostgreSQL parity (from implementation_specs/)

### Bug Catalog

**Critical Bugs:**
1. **BUG-MANAGE-DOCS-001** - Database missing docs_json column
   - Location: Implicit (discovered during Phase 5.5 audit)
   - Impact: Blocks 10+ manage_docs actions
   - Fix: SPEC-MANAGE-DOCS-001
   - Status: BLOCKER

**High Severity Bugs:**
2. **BUG-001** - set_project empty log marking
   - Location: `wiki/bugs/BUG-001-set-project-empty-log.md`
   - File: `tools/set_project.py:459`
   - Fix: SPEC-SET-001
   - Status: Documented

3. **BUG-STORAGE-001** - Storage abstraction bypass
   - Location: `wiki/bugs/BUG-STORAGE-001-abstraction-bypass.md`
   - File: `shared/project_registry.py` (direct sqlite3.connect())
   - Impact: 11 direct violations, PostgreSQL incompatibility
   - Fix: SPEC-STORAGE-001
   - Status: Documented

**Medium Severity Bugs:**
4. **BUG-FORMAT-003** - Compact mode not implemented
   - Location: `wiki/bugs/phase_5_bugs/BUG-FORMAT-003-compact-mode-not-implemented.md`
   - Status: Documented

5. **BUG-FORMAT-004** - rotate_log no readable mode
   - Location: `wiki/bugs/phase_5_bugs/BUG-FORMAT-004-rotate-log-no-readable-mode.md`
   - Status: Documented

### Cleanup Task Inventory

**Dead Code Removal (SPEC-DEAD-001 pending)**
- **Unused imports:** 238 (verified by AST analysis)
- **Dead functions:** 18 (production code only, grep-verified)
- **LOC reduction:** 150-200 lines
- **Confidence:** 95%
- **Evidence:** `wiki/analysis/dead_code_refined.md`, `wiki/analysis/orphaned_utilities.md`

**Code Duplication Consolidation (SPEC-DUP-001)**
- **Pattern 1:** `_count_log_entries` (2 implementations, 23 LOC waste)
- **Pattern 2:** Doc gathering logic (3 implementations, 196 LOC waste)
- **Pattern 3:** Config class infrastructure (3 implementations, 1,674 LOC waste)
- **Pattern 4:** Formatter coupling (11 call sites)
- **Total waste:** 1,893 LOC
- **Consolidation target:** 800-900 LOC reduction (52%)
- **Evidence:** `wiki/analysis/code_duplication_catalog.md`


---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps (P0 - CRITICAL)

**DECISION REQUIRED: Fix BUG-MANAGE-DOCS-001 First**

The orchestrator faces a critical decision point documented in Phase 5.5 summary:

**Option 1: Fix Bug First (RECOMMENDED)** ⭐
- Deploy Coder Agent with SPEC-MANAGE-DOCS-001
- Estimated effort: 4-6 hours
- Unblocks: 10+ manage_docs actions immediately
- Value: HIGH - enables Phase 5.5 wiki copying and full manage_docs validation
- Risk: Low - detailed spec provided, rollback available

**Option 2: Continue Testing (NOT RECOMMENDED)**
- Test remaining 14 actions to document failure modes
- Estimated effort: 2-3 hours
- Value: LOW - confirms what we already know (all will fail)
- Wastes time without fixing the problem

**Option 3: Quick Workaround (ACCEPTABLE)**
- Implement merge fallback in logging_utils.py
- Estimated effort: 1-2 hours
- Value: MEDIUM - unblocks work but maintains technical debt
- Risk: Medium - band-aid solution

**Orchestrator Action:** Choose Option 1, 2, or 3 before proceeding with any manage_docs-dependent work.

### High Priority Implementation (P1)

**After BUG-MANAGE-DOCS-001 is fixed:**

1. **Complete manage_docs Testing**
   - Test remaining 14 actions (1.5 hours per SPEC-MANAGE-DOCS-001 Phase 5)
   - Verify all 17 actions work correctly
   - Create comprehensive usage documentation

2. **Fix BUG-001 (set_project)**
   - Deploy SPEC-SET-001
   - Fix empty log marking issue at line 459
   - Estimated effort: 1-2 hours

3. **Token Optimization Wave**
   - SPEC-TOKEN-001: list_projects (40% reduction)
   - SPEC-TOKEN-002: append_entry (35% reduction)
   - SPEC-TOKEN-003: Global output (30-40% reduction)
   - Combined estimated effort: 6-8 hours
   - Impact: Significant token savings on high-frequency tools

### Medium Priority Cleanup (P2)

4. **Code Quality Improvements**
   - Dead code removal (SPEC-DEAD-001): 150-200 LOC reduction
   - Duplication consolidation (SPEC-DUP-001): 800-900 LOC reduction
   - Combined impact: ~1,000 LOC cleaner codebase
   - Estimated effort: 8-12 hours

5. **Format Standardization**
   - SPEC-FORMAT-001: Format parameter standardization
   - SPEC-FORMAT-002: Readable mode enhancement
   - Estimated effort: 4-6 hours

6. **Storage Abstraction Fix**
   - SPEC-STORAGE-001: Enforce abstraction layer
   - Fix BUG-STORAGE-001 (11 violations in project_registry.py)
   - Enable PostgreSQL compatibility
   - Estimated effort: 6-8 hours

### Long-Term Strategic (P3)

7. **Infrastructure Modernization**
   - SPEC-PKG-001: src/ migration (6-9 hours)
   - Use MIGRATION_PLAYBOOK.md (8-phase guide)
   - SPEC-PG-001: PostgreSQL parity (7 tables, 40+ columns)
   - Combined effort: 15-24 hours

8. **Registry Integration**
   - SPEC-GEN-001: Registry integration
   - Wiki improvements (SPEC-META-001)

### Quality Gates

**Before considering audit complete:**
- [ ] BUG-MANAGE-DOCS-001 fixed and verified
- [ ] All 17 manage_docs actions tested (100% coverage)
- [ ] P0/P1 bugs fixed (BUG-001, BUG-STORAGE-001)
- [ ] Token optimization wave deployed (30-40% reduction achieved)
- [ ] Dead code removed (150-200 LOC)
- [ ] Duplication consolidated (800-900 LOC)
- [ ] Review Agent validation (≥93% grade)


---
## Appendix
<!-- ID: appendix -->

### Wiki Structure
- **Total files:** 94 markdown documents
- **Directories:** 12 (analysis/, specs/, bugs/, tools/, storage/, infrastructure/, review/, architecture/, implementation_specs/, reviews/, tool_outputs/)
- **Size:** ~42KB documentation
- **Created:** 2026-01-04 to 2026-01-05 (Phase 0-5.5)

### Key References
- **Action Matrix:** `wiki/analysis/manage_docs_action_matrix.md` (553 lines)
- **Phase 5.5 Summary:** `wiki/PHASE_5_5_MANAGE_DOCS_AUDIT_SUMMARY.md` (384 lines)
- **INDEX:** `wiki/INDEX.md` (comprehensive navigation)
- **Migration Guide:** `wiki/MIGRATION_PLAYBOOK.md` (1,315 lines)
- **Orchestration Rules:** `wiki/ORCHESTRATION_RULES.md` (170 lines)

### Confidence Assessment
- **manage_docs action status:** 0.95 (tested 3, code analysis for 14)
- **SPEC file enumeration:** 0.98 (complete directory scan)
- **Bug catalog:** 0.92 (wiki-documented bugs only)
- **Cleanup opportunities:** 0.93 (AST-based static analysis)
- **Overall inventory:** 0.92 (high confidence, comprehensive)

### Data Sources
All findings derived from:
- 94 wiki markdown files (scanned 2026-01-07)
- 13 YAML SPEC files
- 4 bug reports
- Action matrix with test results
- Dead code and duplication analysis reports

### Quick Stats
- **17** manage_docs actions inventoried
- **13** implementation specs ready
- **4** bugs documented
- **238** unused imports identified
- **18** dead functions found
- **1,893** LOC duplication waste
- **~1,000** LOC reduction potential
- **17.6%** manage_docs test coverage (3/17)
- **10+** actions blocked by BUG-MANAGE-DOCS-001


---

**Research Complete:** 2026-01-07 21:44 UTC
**Agent:** ResearchAgent-WikiAnalysis
**Project:** scribe_systematic_audit_1
**Deliverable Status:** ✅ COMPLETE
**Next Action:** Orchestrator decision on BUG-MANAGE-DOCS-001 (Option 1/2/3)
