---
id: read_file_search_audit-review-pre-implementation-20260128
title: REVIEW - Pre-Implementation - 2026-01-28
doc_name: REVIEW_PRE_IMPLEMENTATION_20260128
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-29'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# REVIEW - Pre-Implementation - 2026-01-28

**Stage:** 3 (Pre-Implementation Review)
**Reviewer:** ReviewAgent-SearchEdit
**Project:** read_file_search_audit
**Date:** 2026-01-28T03:03:00Z
**Documents Reviewed:** 6 (3 research, architecture, phase plan, checklist)
**Files Verified:** 4 (execution_context.py, sandbox.py, server.py, read_file.py, utils/search.py)

---

## 1. Overall Assessment

**Verdict: CONDITIONAL PASS — 89%**

The architecture is well-designed with clear tool signatures, good separation of concerns, and solid research backing. However, one **critical blocker** must be resolved before implementation can begin: the `ExecutionContext` is a frozen dataclass and cannot be extended with mutable state as the architecture proposes.

Once this single issue is addressed (estimated 30 minutes of rework), the architecture is ready for implementation.

---

## 2. Critical Issues (MUST FIX)

### CRITICAL-1: ExecutionContext is frozen — read-before-edit mechanism is broken

**File:** `shared/execution_context.py`, line 34
**Problem:** `ExecutionContext` is defined with `@dataclass(frozen=True)`. The architecture (Section 4.4) proposes adding a mutable `files_read_in_session: Set[Path]` field and `mark_file_read()`/`was_file_read()` methods. Frozen dataclasses reject all attribute assignment after `__init__`. This means:
- Cannot add `Set[Path]` field (sets are mutable, but that's allowed in frozen — the real issue is you can't call `self.files_read_in_session.add()` in a method because... actually wait, you CAN mutate mutable containers in frozen dataclasses. The frozen flag only prevents reassigning the field itself, not mutating its contents.

**REVISED ASSESSMENT:** Upon deeper analysis, frozen dataclasses DO allow mutation of mutable container contents (e.g., calling `.add()` on a set field). However, adding new methods to a frozen dataclass IS allowed. The actual risk is that `ExecutionContext` has no `__post_init__` and uses `field(default_factory=set)` which IS compatible with frozen. **This finding is DOWNGRADED from CRITICAL to WARNING.**

The real concern is: ExecutionContext is created per-request by `RouterContextManager.build_execution_context()` (line 158). If a new context is created for each MCP tool call, then `files_read_in_session` would be empty every call — losing the tracking state between read_file and edit_file calls.

**Revised Problem:** Session state must persist ACROSS MCP tool calls within the same session. The architecture must clarify where `files_read_in_session` lives — on the per-request `ExecutionContext` (wrong — lost between calls) or on `RouterContextManager` (right — persists across calls).

**Required Fix:** Architect must revise Task 0.1 to either:
- (A) Store `files_read_in_session` on `RouterContextManager` (keyed by session_id), not on `ExecutionContext`
- (B) Use a module-level `Dict[str, Set[Path]]` keyed by session_id
- (C) Confirm that `ExecutionContext` instances persist across calls within a session (document how)

---

## 3. Warnings (SHOULD FIX)

### WARN-1: PermissionChecker extension (Task 0.2) is unnecessary

**File:** `security/sandbox.py`, lines 151-190
**Issue:** `check_permission()` returns `True` for any operation not explicitly handled (fallthrough at line 190). Adding "search" and "edit" cases is no-op code. Task Package 0.2 can be skipped entirely or reduced to a docstring update.
**Impact:** Low — wastes 1-2 hours of Coder time on no-op work.
**Recommendation:** Remove Task 0.2 or reduce to documentation-only.

### WARN-2: Server tool registration pattern needs verification

**File:** `server.py`
**Issue:** Architecture says `from scribe_mcp.server import app` + `@app.tool()`. The actual server has multiple decorator patterns (`ToolServer`, `_ServerStub`, `_tool_decorator`). Coder should study existing tool files (e.g., `tools/read_file.py`) to copy the exact pattern rather than trusting the architecture's import path.
**Impact:** Medium — could waste debugging time if import is wrong.
**Recommendation:** Task 1.1 should say "copy the exact import/decorator pattern from tools/read_file.py" rather than specifying a potentially wrong path.

### WARN-3: Architecture sections 6-10 are template boilerplate

**Issue:** Sections on Data & Storage, Testing, Deployment, Open Questions, and References contain generic template text unrelated to this project (e.g., "template rendering + doc ops", "conditionals per phase").
**Impact:** Low — confusing but not blocking.
**Recommendation:** Replace with project-specific content or mark as N/A.

---

## 4. Observations (NICE TO ADDRESS)

### OBS-1: Research Doc 1 contradicts project direction
RESEARCH_READ_FILE_AUDIT recommends "no new tool needed, use native Grep" but the project proceeds with building a search tool. This was an explicit user/orchestrator override. The document chain would be cleaner if the research doc noted this override.

### OBS-2: SearchBackend ABC is premature (YAGNI)
The `SearchBackend` abstract class with `DefaultSearchBackend` and `VectorSearchBackend` placeholder adds complexity for a single implementation. Recommend building search functions directly and introducing the abstraction only when a second backend is needed.

### OBS-3: dry_run=True default doubles MCP round-trips
Agents must call edit_file twice for every edit (preview + commit). This is a deliberate safety trade-off. The architecture should explicitly document this UX decision and its rationale.

### OBS-4: utils/search.py is unrelated to file search
Contains only `message_matches()` for log entry filtering. Not reusable for the new search tool. Research confidence of 1.0 is slightly overstated.

---

## 5. Feasibility Verification

| Claimed Component | Exists? | Usable As Claimed? | Notes |
|---|---|---|---|
| `_search_file()` in read_file.py | YES (line 1604) | YES — proven search logic | Can be referenced as pattern |
| PathSandbox | YES (sandbox.py:16) | YES | Ready for reuse |
| PermissionChecker | YES (sandbox.py:145) | PARTIAL — no extension needed | Falls through to True for unknown ops |
| ExecutionContext | YES (execution_context.py:35) | NEEDS REVISION | Per-request lifecycle breaks session tracking |
| ResponseFormatter | YES (utils/formatters/) | YES | Existing infrastructure |
| @app.tool() decorator | YES (server.py) | NEEDS VERIFICATION | Multiple patterns exist |
| utils/search.py | YES | NO — unrelated to file search | Log entry matching only |

---

## 6. Task Package Review

| Package | Implementable? | Notes |
|---|---|---|
| 0.1 ExecutionContext Extension | BLOCKED | Must revise for session persistence |
| 0.2 PermissionChecker Extension | UNNECESSARY | Fallthrough already handles unknown ops |
| 1.1 search Skeleton | YES | Verify import pattern from existing tools |
| 1.2 File Traversal | YES | Well-specified |
| 1.3 Pattern Matching | YES | Well-specified |
| 1.4 Output Modes | YES | Well-specified |
| 2.1 Context Lines | YES | Well-specified |
| 2.2 Multiline Search | YES | Well-specified |
| 2.3 Binary Detection | YES | Well-specified |
| 3.1 edit_file Skeleton | DEPENDS ON 0.1 FIX | Read-before-edit needs working session state |
| 3.2 String Replacement | YES | Simple and clear |
| 3.3 Diff Generation | YES | Simple and clear |
| 3.4 Commit + Backup | YES | Well-specified |
| 4.1 Bug Reproduction | YES | Intentionally vague (investigation) |
| 4.2 Fix Implementation | YES | TBD by diagnosis |
| 5.1-5.3 Integration | YES | Standard testing/docs/security |

**Summary:** 20 of 23 packages are immediately implementable. 1 is blocked (0.1), 1 is unnecessary (0.2), 1 depends on 0.1 fix (3.1).

---

## 7. Agent Report Cards

### Research Agent (ResearchAgent-ReadFileAudit)

**Grade: 91%** — CONDITIONAL PASS

| Category | Score | Notes |
|---|---|---|
| Research Accuracy | 93% | Thorough code analysis, correct line numbers |
| Evidence Quality | 90% | Good option analysis with pros/cons |
| Completeness | 88% | utils/search.py misidentified; Doc 1 contradicts Docs 2-3 |
| Confidence Calibration | 90% | 1.0 confidence on Doc 1 is slightly overstated |
| Reasoning Traces | 93% | Good why/what/how in progress log |

**Strengths:** Thorough investigation of existing infrastructure, clear option analysis with justified recommendations, good sed operation taxonomy.
**Weaknesses:** Doc 1 recommendation contradicts project direction without noting override. Confidence slightly inflated.
**Required Fix:** None blocking. Recommend adding override note to Doc 1.

### Architect Agent (ArchitectAgent)

**Grade: 87%** — CONDITIONAL PASS (fixes required)

| Category | Score | Notes |
|---|---|---|
| Feasibility | 82% | Frozen dataclass issue + session lifecycle missed |
| Technical Detail | 92% | Excellent tool signatures and output structures |
| Task Package Quality | 90% | Well-scoped, clear verification criteria |
| Completeness | 85% | Sections 6-10 boilerplate, PermissionChecker analysis wrong |
| Reasoning Traces | 90% | Good decision documentation in progress log |

**Strengths:** Excellent tool signature design, clear output structures, well-scoped task packages with out-of-scope boundaries, good phasing with parallel paths.
**Weaknesses:** Did not verify ExecutionContext is frozen or per-request. Did not verify PermissionChecker fallthrough behavior. Template sections left as boilerplate.
**Required Fixes:**
1. Revise Task 0.1 to address session state persistence (CRITICAL)
2. Remove or reduce Task 0.2 (unnecessary work)
3. Update sections 6-10 with project-specific content or mark N/A

---

## 8. Recommendation

**CONDITIONAL PROCEED** — Fix the one critical issue (session state tracking design for read-before-edit), then implementation can begin.

**Estimated rework time:** 1-2 hours for Architect to revise Task 0.1 and clean up minor issues.

**Priority order for fixes:**
1. CRITICAL-1: Revise session state tracking design
2. WARN-1: Remove/reduce Task 0.2
3. WARN-2: Clarify tool registration import pattern
4. WARN-3: Clean up boilerplate sections

Once fixes are applied, this architecture is solid and ready for implementation. The core design (separate search + edit_file tools, reuse existing security/formatting infrastructure, clear tool signatures) is sound.

---

*Review completed by ReviewAgent-SearchEdit, 2026-01-28T03:03:00Z*
