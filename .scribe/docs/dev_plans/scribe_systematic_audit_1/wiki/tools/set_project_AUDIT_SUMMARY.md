# set_project.py Forensic Audit - Executive Summary

**Agent**: ResearchAgent-E-SetProject
**Tool**: `tools/set_project.py`
**LOC**: 807 lines
**Date**: 2026-01-05
**Status**: ✅ COMPLETE

---

## Audit Scope

Systematic forensic analysis of `set_project.py` covering:
- Sub-system decomposition and boundary identification
- Bug discovery with reproduction steps and fix specifications
- Token consumption analysis with optimization recommendations
- Cross-tool pattern detection for modularization
- Implicit contract documentation
- Error handling architecture analysis

---

## Key Findings

### 🐞 Bugs Confirmed

**BUG-001: Empty Log Treated as New Project**
- **File**: `tools/set_project.py`
- **Line**: 461
- **Severity**: Medium
- **Impact**: Misleading SITREP output, hidden inventory data
- **Fix**: Change `is_new = not exists() or count == 0` → `is_new = not exists()`
- **Evidence**: Full reproduction steps in `wiki/bugs/BUG-001-set-project-empty-log.md`
- **Spec**: YAML implementation spec in `wiki/specs/SPEC-SET-001-bug-fix.yaml`

### 🔄 Duplication Confirmed

**DUPLICATION-002: Doc Inventory Gathering**
- **Affected Files**:
  - `set_project.py` (lines 91-125)
  - `list_projects.py` (lines 88-125)
  - `get_project.py` (lines 146-164)
- **Pattern**: Identical doc checking logic with `_get_doc_line_count()` and `_detect_custom_content()`
- **Proposal**: Extract `DocInventoryGatherer` module [BUCKET:metadata]
- **Effort**: ~7 hours

### 📊 Token Analysis

**SITREP Output Metrics** (5 samples analyzed):
- **Average**: 283 tokens (range 198-390)
- **Structural overhead**: 82 tokens (28.8%) - boxes, headers
- **Duplication**: 36 tokens (12.7%) - repeated Location block
- **Reminders**: Up to 71 additional tokens
- **Compact format**: 17 tokens (94% reduction possible)

**Optimization Targets**:
1. Make structural boxes optional in compact mode (-82 tokens)
2. Template shared Location block (-36 tokens)
3. Separate reminders as optional concern (-71 tokens)
4. Target: <200 tokens for standard SITREP (30% reduction)

### 🧩 Sub-Systems Identified

1. **Parameter Normalization** (lines 131-233) - [BUCKET:parameter_healing]
2. **Path Resolution** (lines 219-243, 548-591) - Internal (keep)
3. **Doc Creation & Inventory** (lines 61-127, 624-688) - [BUCKET:metadata]
4. **Database Mirroring** (lines 286-346, 408-440) - [BUCKET:error_handling]
5. **Agent Session Binding** (lines 349-402) - Internal (monitor)
6. **SITREP Formatting** (lines 454-531) - [BUCKET:formatting]

### 🎯 Extractable Modules

| Module | Bucket | Priority | Effort | Tools Affected |
|--------|--------|----------|--------|----------------|
| DocInventoryGatherer | metadata | HIGH | 7h | 3 (set_project, list_projects, get_project) |
| ParameterHealer | parameter_healing | HIGH | 11h | 5+ (all monster tools) |
| SITREP Optimization | formatting | MED | 12h | 3+ (set_project, list_projects, get_project) |
| ErrorPolicy | error_handling | MED | 13h | 5+ (all DB-mirroring tools) |

**Total Estimated Effort**: 43 hours (High priority: 18 hours)

---

## Deliverables

### ✅ Documentation
- **Wiki Page**: `wiki/tools/set_project.md` (8 sections, comprehensive)
- **Bug Report**: `wiki/bugs/BUG-001-set-project-empty-log.md` (reproduction + fix)
- **Fix Spec**: `wiki/specs/SPEC-SET-001-bug-fix.yaml` (YAML implementation guide)
- **Cross-Cutting**: `wiki/cross_cutting_concerns.md` (6 buckets, 4 modules)

### ✅ Analysis Artifacts
- **Token Analysis**: `wiki/tools/token_analysis_results.json` (5 samples)
- **Token Script**: `wiki/tools/token_analysis_manual.py` (reproducible analysis)

### ✅ Scribe Logging
- **Total Logs**: 8 entries with full reasoning traces
- **All logs include**: why/what/how reasoning framework
- **Evidence level**: High (code analysis + token measurement + bug reproduction)

---

## Gate Requirements

- [x] Wiki stub created (8 sections complete)
- [x] ≥3 Scribe logs (8 logs with reasoning traces)
- [x] ≥3 token samples (5 samples analyzed)
- [x] BUG-001 confirmed with evidence

**Status**: ALL GATES PASSED ✅

---

## Architecture Insights

### Implicit Contracts Documented

1. **Session Binding**: stable_session_id preferred over UUID (line 411)
2. **Silent DB Failures**: Database mirroring errors are non-fatal (lines 305, 333, 345)
3. **Doc Inventory Completeness**: Only checks 4 standard docs, custom content is best-effort
4. **Project Registry Touch**: Failures silently ignored (lines 304, 344)

### Error Handling Architecture

**Policy**: Graceful degradation with structured fallbacks
- Database failures → print() + continue (state.json is source of truth)
- Agent context failures → legacy global state fallback
- Parameter normalization failures → safe defaults (empty dict/list)

**Tag**: [BUCKET:error_handling] - Needs unification for observability

### Configuration Gravity

`set_project` has 20+ parameters with complex normalization:
- Multiple parameter sources (direct, defaults dict, convenience params)
- Priority resolution (emoji_param > defaults.emoji > default_emoji)
- Validation scattered across helpers

**Decision**: Keep as internal (set_project-specific), not a candidate module

---

## Modularization Roadmap

### Phase 6 Priorities (from this audit)

**High Priority** (Immediate value):
1. **DocInventoryGatherer** (7h)
   - Unifies doc checking across 3 tools
   - Single source of truth for inventory logic
   - Enables consistent detection of research files, bugs, custom logs

2. **ParameterHealer** (11h)
   - Fixes MCP framework JSON string quirks consistently
   - Prevents user-facing parameter bugs
   - Used by all monster tools

**Medium Priority** (Optimization):
3. **SITREP Optimization** (12h)
   - Reduces token consumption 30-50%
   - Improves compact mode usability
   - Benefits set_project, list_projects, get_project

4. **ErrorPolicy** (13h)
   - Structured error logging instead of print()
   - Failure metrics and observability
   - Consistent fallback behavior

### Coordination with Wave 1 Agents

**Watch for patterns in**:
- Agent A (append_entry): ParameterHealer usage, error handling
- Agent B (manage_docs): Doc inventory needs, SITREP-style formatting
- Agent C (query_entries): ParameterHealer usage, formatting patterns
- Agent D (rotate_log): Error handling, doc inventory checks

**Aggregate in**: Phase 2 (post-Wave 1 completion)

---

## Before/After Mental Models

### DocInventoryGatherer
- **Before**: 3 tools each implement "check ARCH + PHASE + CHECKLIST + count lines + detect custom"
- **After**: Single `DocInventoryGatherer.gather()` returns standardized inventory, tools adapt to needs
- **Win**: "Get doc status" is now a named, testable operation

### ParameterHealer
- **Before**: Each tool tries JSON parsing with different fallback strategies
- **After**: `ParameterHealer.heal(param, type, fallback)` with consistent behavior
- **Win**: Parameter healing is policy, not scattered try/except blocks

### SITREP Formatting
- **Before**: 283 tokens avg with 28.8% structural overhead, 12.7% duplication
- **After**: Optional components, template fragments, separate reminders → <200 tokens
- **Win**: Compact mode viable for high-frequency calls

---

## Testing Recommendations

### BUG-001 Regression Tests
```python
# Test 1: Empty log after rotation shows existing SITREP
# Test 2: Manually cleared log shows existing SITREP
# Test 3: Genuinely new project still works
# Test 4: Inventory gathering works for empty logs
```

### Module Extraction Tests
```python
# For each extracted module:
# 1. Unit tests for module in isolation
# 2. Integration tests with all consuming tools
# 3. Regression tests for existing behavior
# 4. Performance tests (token usage, execution time)
```

---

## Risk Assessment

### BUG-001 Fix
- **Risk**: Low (single boolean expression)
- **Impact**: Medium (affects SITREP selection)
- **Testing**: 4 regression tests required
- **Rollback**: Trivial (revert line 461)

### DocInventoryGatherer Extraction
- **Risk**: Medium (changes 3 tools)
- **Impact**: High (affects all doc-aware operations)
- **Testing**: Comprehensive (unit + integration for 3 tools)
- **Rollback**: Moderate (revert 3 tool integrations)

### ParameterHealer Extraction
- **Risk**: Medium (affects 5+ tools)
- **Impact**: High (user-facing parameter handling)
- **Testing**: Critical (all monster tools must be tested)
- **Rollback**: Complex (5+ tool reversions)

---

## Success Metrics

### Phase 6 Modularization Success
- [ ] DocInventoryGatherer used by all 3 tools without regression
- [ ] ParameterHealer eliminates parameter normalization duplication
- [ ] Token consumption reduced by 30% in readable mode
- [ ] Error Policy provides queryable failure metrics
- [ ] All existing tests pass
- [ ] New modules have >90% test coverage

### Audit Quality Metrics
- [x] All sub-systems identified with clear boundaries
- [x] All bugs have reproduction steps + fix specs
- [x] All extractable modules have effort estimates
- [x] All implicit contracts documented
- [x] Token analysis provides actionable optimization targets
- [x] Cross-tool patterns flagged for coordination

---

## Files Created

```
.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/
├── tools/
│   ├── set_project.md                    (Main wiki page, 8 sections)
│   ├── token_analysis_manual.py          (Token measurement script)
│   ├── token_analysis_results.json       (5 sample results)
│   └── set_project_AUDIT_SUMMARY.md      (This file)
├── bugs/
│   └── BUG-001-set-project-empty-log.md  (Bug report + reproduction)
├── specs/
│   └── SPEC-SET-001-bug-fix.yaml         (Implementation spec)
└── cross_cutting_concerns.md              (6 buckets, 4 modules)
```

---

## Next Steps

1. **Human Review**: Review findings, approve module extraction priorities
2. **Wave 1 Coordination**: Await agents A-D findings for pattern confirmation
3. **Phase 2 Planning**: Aggregate cross-cutting concerns from all 5 agents
4. **Phase 6 Execution**: Implement high-priority modules (DocInventoryGatherer, ParameterHealer)
5. **BUG-001 Fix**: Implement single-line fix with regression tests

---

## Sign-Off

**Audit Completed By**: ResearchAgent-E-SetProject
**Completion Date**: 2026-01-05 02:42 UTC
**Evidence Level**: High (code analysis + token measurement + cross-tool validation)
**Gate Status**: ALL PASSED ✅
**Ready for Review**: YES ✅

**Deliverables**: 6 documentation files, 8 Scribe logs, 5 token samples, 1 bug confirmed, 4 modules proposed

---

**Study like an architect. Report like a forensic analyst. Leave clean seams for the future.**

✅ Mission accomplished.
