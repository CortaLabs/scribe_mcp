---
id: manage_docs_agent_ux-research-custom-doc-naming-bug-20260119
title: "\U0001F52C Research Custom Doc Naming Bug 20260119 \u2014 manage_docs_agent_ux"
doc_name: RESEARCH_CUSTOM_DOC_NAMING_BUG_20260119
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-20'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Custom Doc Naming Bug 20260119 — manage_docs_agent_ux
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 04:10:33 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Bug Title:** Custom Document Naming Bug - Files saved with doc_type instead of doc_name

**Severity:** High

**Root Cause:** The `_resolve_create_doc_path()` function in `doc_management/manager.py` (line 828) falls through to using the `doc_type` metadata value as the filename when the `doc_name` top-level parameter is provided alongside `doc_type` in metadata.

**Impact:** Users cannot create multiple custom documents because all custom docs get saved as "custom.md", causing file collisions and data loss.

**Example:**
```python
# User expects this to create COORDINATION_PROTOCOL.md:
manage_docs(
    action="create",
    doc_name="COORDINATION_PROTOCOL",
    metadata={"doc_type": "custom", "body": "..."}
)

# But it actually creates:
# File saved as: custom.md (WRONG - uses doc_type value)
# Expected:      COORDINATION_PROTOCOL.md (uses doc_name parameter)
```

**Root Cause Code Path:**
1. `manage_docs` tool (line 1375-1380) routes `action="create"` with `doc_type="custom"` to internal `action="create_doc"`
2. `apply_doc_change` function (line 159) calls `_resolve_create_doc_path(project, metadata, doc_name)`
3. **BUG:** `_resolve_create_doc_path` line 828 checks metadata fallback chain BEFORE doc_name parameter:
   ```python
   resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
   # Order is wrong: doc_type evaluated before doc_name parameter
   ```
<!-- ID: research_scope -->
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### Finding 1: Parameter Resolution Order Bug in _resolve_create_doc_path
**Severity:** Critical  
**Confidence:** 0.98  
**File:** `/home/austin/projects/MCP_SPINE/scribe_mcp/doc_management/manager.py`  
**Lines:** 810-861, specifically line 828

**Evidence:**
```python
# Line 828 - BUGGY ORDER:
resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
```

**Problem:** When a user provides both a top-level `doc_name` parameter AND a metadata dict with `doc_type`, the function incorrectly checks the metadata fallback chain before considering the actual `doc_name` parameter. 

**Execution Flow:**
1. `metadata.get("doc_name")` returns None (not in metadata, it's a top-level param)
2. `metadata.get("register_as")` returns None (not provided)
3. `metadata.get("doc_type")` returns "custom" ← **STOPS HERE, uses this as filename**
4. `doc_name` parameter never gets evaluated

**Fix Required:** Reorder to check the function parameter `doc_name` BEFORE metadata fallbacks:
```python
# CORRECT ORDER:
resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
```

### Finding 2: Test Coverage Gap
**Severity:** Medium  
**Confidence:** 0.95  
**File:** `/home/austin/projects/MCP_SPINE/scribe_mcp/tests/test_manage_docs_create_doc.py`

**Evidence:**
All existing tests pass `doc_name` WITHIN the metadata dictionary (lines 58, 91, 120, 150), not as a top-level parameter. The test that should catch this bug is missing.

**Missing Test Case:**
```python
@pytest.mark.asyncio
async def test_create_custom_doc_respects_doc_name_parameter():
    """Test that doc_name parameter is respected over metadata.doc_type"""
    project = await _setup_project(tmp_path)
    
    result = await manage_docs(
        action="create",
        doc_name="COORDINATION_PROTOCOL",  # Top-level parameter
        metadata={"doc_type": "custom", "body": "# Protocol\n..."}
    )
    
    # Should create COORDINATION_PROTOCOL.md, NOT custom.md
    assert result["ok"]
    path = Path(result["path"])
    assert path.name == "COORDINATION_PROTOCOL.md"
    assert "custom.md" not in str(path)
```

### Finding 3: Real-world Impact
**Severity:** High  
**Confidence:** 0.90  
**Evidence:** User report from progress log entry at 04:07 UTC documenting this exact bug

**Symptom:**
- User tries: `manage_docs(action="create", doc_name="COORDINATION_PROTOCOL", metadata={"doc_type": "custom", "body": "..."})`
- Expects file: `COORDINATION_PROTOCOL.md`
- Gets file: `custom.md`
- Cannot create multiple custom documents (all collide on same filename)
- "Errant custom.md file from manage_docs misbehavior remains in project directory" (architecture log)

### Finding 4: Code Path Verification
**Severity:** Info  
**Confidence:** 0.99  
**Files Traced:**
1. `tools/manage_docs.py` line 1375-1380: Routes `create` action with `doc_type="custom"` to `create_doc` handler
2. `tools/manage_docs.py` line 1769-1785: Passes `doc_name` parameter to `apply_doc_change()`
3. `doc_management/manager.py` line 159: Calls `_resolve_create_doc_path(project, metadata, doc_name)`
4. `doc_management/manager.py` line 828: **BUG LOCATION** - parameter resolution order incorrect

**Full Flow:**
```
manage_docs(action="create", doc_name="X", metadata={"doc_type": "custom", ...})
↓
Line 1378-1380: Changes action to "create_doc", falls through
↓
Line 1769: await apply_doc_change(..., doc_name="X", metadata={...})
↓
Line 159: doc_path = _resolve_create_doc_path(project, metadata, "X")
↓
Line 828: resolved_name = metadata.get("doc_name") or ... or metadata.get("doc_type") or "X"
         → evaluates to "custom" ← BUG
```
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
## Recommendations

### Priority 1 (CRITICAL - FIX IMMEDIATELY)

**Recommendation 1.1: Fix Parameter Resolution Order**
- **Action:** Modify `doc_management/manager.py` line 828
- **Change:**
  ```python
  # BEFORE (BUGGY):
  resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
  
  # AFTER (FIXED):
  resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
  ```
- **Rationale:** The function parameter `doc_name` should have highest priority in the fallback chain. If a user explicitly passes `doc_name` as a parameter, that MUST be respected. Metadata fallbacks should only be used if `doc_name` parameter is not provided.
- **Risk Level:** Low - This is a pure bug fix that restores intended behavior
- **Affected Code Paths:** Any call to `_resolve_create_doc_path()` with doc_name parameter
- **Testing:** Must add test case (see Finding 2)

### Priority 2 (HIGH - ADD TEST COVERAGE)

**Recommendation 2.1: Add Missing Test Case**
- **File:** `tests/test_manage_docs_create_doc.py`
- **Action:** Add test function (see Finding 2 for full test code)
- **Test Name:** `test_create_custom_doc_respects_doc_name_parameter`
- **Coverage:** Validates that top-level `doc_name` parameter takes precedence over metadata values
- **Prevents Regression:** Ensures this bug cannot resurface

### Priority 3 (MEDIUM - DOCUMENTATION)

**Recommendation 3.1: Clarify API Parameter Priority**
- **Location:** Tool documentation or docstring for `manage_docs`
- **Addition:** Document the parameter resolution order when both top-level and metadata parameters are provided:
  ```
  Parameter Resolution Order (for create action):
  1. doc_name parameter (highest priority)
  2. metadata.get("doc_name")
  3. metadata.get("register_as")
  4. metadata.get("doc_type") (lowest priority, fallback only)
  ```

**Recommendation 3.2: API Consistency Review**
- **Action:** Review all similar parameter resolution patterns in codebase
- **Search For:** Other instances of fallback chains that might have incorrect priority
- **Files to Check:** Any place using `or` chains for parameter resolution
- **Pattern to Find:** Places where metadata dict is checked before function parameters
<!-- ID: appendix -->
## Handoff Notes for Architect & Coder

### For Architect Agent
1. **Scope:** This is a straightforward bug fix, not an architectural issue
2. **Task Package:** Create a single implementation task for the Coder:
   - Fix parameter resolution order in line 828
   - Add test case to prevent regression
   - Verify no other similar bugs exist in codebase
3. **Key Decision:** The fix is unambiguous - doc_name parameter MUST take precedence
4. **Risk Assessment:** Very low risk - this is correcting obviously buggy behavior
5. **Integration Points:** No other systems affected; purely internal to manage_docs

### For Coder Agent
1. **Files to Modify:**
   - `doc_management/manager.py` (1 line change at line 828)
   - `tests/test_manage_docs_create_doc.py` (1 test function addition)
2. **Exact Code Change:**
   ```python
   # File: doc_management/manager.py, Line 828
   # CHANGE FROM:
   resolved_name = metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type") or doc_name
   
   # CHANGE TO:
   resolved_name = doc_name or metadata.get("doc_name") or metadata.get("register_as") or metadata.get("doc_type")
   ```
3. **Test to Add:** Use the test case from Finding 2 in this document
4. **Verification:** Run pytest on test_manage_docs_create_doc.py to verify all tests pass
5. **Expected Outcome:** Users can now create multiple custom docs with unique names

### For Review Agent
1. **Verification Points:**
   - [ ] Parameter order changed correctly
   - [ ] New test added and passes
   - [ ] All existing tests still pass
   - [ ] No similar bugs found in codebase review
2. **Confidence Threshold:** This fix should achieve 100% confidence - it's correcting an obvious bug
3. **Test Coverage Requirement:** New test must fail with old code, pass with new code
4. **Code Review:** Verify no other parameter resolution chains have same issue

## References & Evidence

- **Bug Report:** Logged at progress log timestamp 2026-01-20 04:07 UTC
- **Code Location:** `/home/austin/projects/MCP_SPINE/scribe_mcp/doc_management/manager.py` lines 810-861
- **Related Files:** 
  - `tools/manage_docs.py` (lines 1375-1380, 1769-1785)
  - `tests/test_manage_docs_create_doc.py`
- **Test Files:** `/home/austin/projects/MCP_SPINE/scribe_mcp/tests/test_manage_docs_create_doc.py`

## Research Metadata

- **Research Date:** 2026-01-20
- **Research Agent:** ResearchAgent
- **Investigation Duration:** Traced 4 files, 8 code locations, 4 detailed findings
- **Bug Severity:** HIGH (users cannot create multiple custom documents)
- **Fix Complexity:** LOW (1-line code change + 1 test function)
- **Overall Confidence:** 0.98 (root cause identified with high certainty)
