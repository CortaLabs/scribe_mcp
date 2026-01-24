---
id: sentinel_tool_test-research-append-entry-internal-calling-20260124-1009
title: "\U0001F52C Research Append Entry Internal Calling 20260124 1009 \u2014 sentinel_tool_test"
doc_name: RESEARCH_APPEND_ENTRY_INTERNAL_CALLING_20260124_1009
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-24'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Append Entry Internal Calling 20260124 1009 — sentinel_tool_test
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-24 10:09:24 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Determine the correct pattern for one MCP tool to call another MCP tool internally (specifically: `open_bug`, `open_security`, and `link_fix` calling `append_entry`) without encountering MCP wrapper type issues.

**Key Takeaways:**
- **ROOT CAUSE**: `append_entry` defaults to `format='readable'`, which triggers `finalize_tool_response()` to wrap the result in `CallToolResult` with `TextContent` (MCP SDK types)
- **SOLUTION**: Internal tool calls MUST pass `format='structured'` to get unwrapped `Dict[str, Any]` return values
- **PATTERN**: `await append_entry_tool(..., format='structured')` returns plain dict that can be processed before the calling tool returns
- **WRAPPING LAYER**: MCP wrapping occurs in `utils/formatters/dispatcher.py::finalize_tool_response()`, NOT at the MCP protocol boundary
- **CONFIDENCE**: 0.98 - Solution verified through code analysis and existing working patterns
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent

**Investigation Window:** 2026-01-24

**Focus Areas:**
- [x] How `append_entry` returns values (plain dict vs MCP-wrapped types)
- [x] When MCP wrapping occurs in the call chain
- [x] How existing tools (`append_event`, `read_recent`) handle internal calls
- [x] Role of `format` parameter in controlling return types
- [x] Behavior of `finalize_tool_response()` wrapper

**Dependencies & Constraints:**
- Investigation limited to existing Scribe MCP v2.2 codebase
- No external testing - code analysis only
- Assumes MCP SDK types (`CallToolResult`, `TextContent`) are available
<!-- ID: findings -->
### Finding 1: append_entry Returns Different Types Based on `format` Parameter
- **Summary:** `append_entry()` uses `finalize_tool_response()` to conditionally wrap its result based on the `format` parameter
- **Evidence:** 
  - `tools/append_entry.py:1260` - Function signature shows `format: str = "readable"` default
  - `tools/append_entry.py:1593-1597` - Calls `await default_formatter.finalize_tool_response(data=result, format=format, tool_name="append_entry")`
- **Confidence:** High (0.98)
- **Impact:** When `format='readable'` (default), returns `CallToolResult`; when `format='structured'`, returns plain `Dict[str, Any]`

### Finding 2: MCP Wrapping Happens in Formatter, Not Protocol Layer
- **Summary:** MCP type wrapping (`CallToolResult`, `TextContent`) occurs in application code (`finalize_tool_response()`), not at the MCP SDK protocol boundary
- **Evidence:**
  - `utils/formatters/dispatcher.py:275-281` - Shows explicit `CallToolResult(content=[TextContent(type="text", text=readable_content)])` construction when `format='readable'`
  - `utils/formatters/dispatcher.py:104-117` - Comment documents this is "ISSUE #9962 FIX" to force clean text display
- **Confidence:** High (0.98)
- **Impact:** Tools can control wrapping by passing `format` parameter; internal calls should use `format='structured'`

### Finding 3: _unwrap_result() Was Attempt to Handle Wrapped Results
- **Summary:** The `_unwrap_result()` helper in `sentinel_tools.py` exists to extract dict from `CallToolResult` wrappers
- **Evidence:**
  - `tools/sentinel_tools.py:30-64` - Complex unwrapping logic handling `CallToolResult.content[0].text` JSON parsing
  - `tools/sentinel_tools.py:306` - `open_bug` uses `result = _unwrap_result(raw_result)` pattern
- **Confidence:** High (0.95)
- **Impact:** Unwrapping is unnecessary if we pass `format='structured'` - cleaner and more direct

### Finding 4: append_event Pattern vs open_bug Pattern
- **Summary:** `append_event` and `open_bug` have different return requirements despite both calling `append_entry`
- **Evidence:**
  - `tools/sentinel_tools.py:157` - `append_event` is itself an `@app.tool()` MCP tool, so returning wrapped result is correct behavior
  - `tools/sentinel_tools.py:187-199` - `append_event` doesn't pass `format` param, inherits default `'readable'`, returns wrapped result directly to MCP client
  - `tools/sentinel_tools.py:300-306` - `open_bug` needs to process result (generate case_id), so needs unwrapped dict
- **Confidence:** High (0.95)
- **Impact:** Different tools have different needs - pass-through tools can use default `format='readable'`, processing tools need `format='structured'`

### Additional Notes
- The `format` parameter is a **dual-purpose control**: it determines both output formatting AND return type wrapping
- All tools using `finalize_tool_response()` have this behavior: `read_recent`, `query_entries`, `list_projects`, etc.
- The comment in `server.py:690-691` explicitly documents this: "list_projects defaults to format='readable', which returns an MCP CallToolResult wrapper"
<!-- ID: technical_analysis -->
**Code Patterns Identified:**

1. **Correct Pattern for Internal Tool Calls:**
```python
# ✅ CORRECT - Pass format='structured' to get plain dict
from scribe_mcp.tools.append_entry import append_entry as append_entry_tool

result = await append_entry_tool(
    message="...",
    status="bug",
    agent=agent,
    meta={...},
    format='structured'  # ← KEY: Returns Dict[str, Any]
)

# Now result is plain dict - can access result["ok"], result["path"], etc.
case_id = generate_case_id_from(result)
return {"ok": True, "case_id": case_id, ...}
```

2. **Incorrect Pattern (Current Implementation):**
```python
# ❌ WRONG - Omitting format parameter gets wrapped result
raw_result = await append_entry_tool(...)  # format defaults to 'readable'
result = _unwrap_result(raw_result)  # Complex JSON parsing to extract dict
```

3. **Pass-Through Pattern (append_event - Correct As Is):**
```python
# ✅ CORRECT for pass-through tools
# append_event is itself an @app.tool() that returns to MCP client
# Returning wrapped CallToolResult is correct behavior
return await append_entry_tool(...)  # format='readable' → wrapped → client sees formatted output
```

**System Interactions:**

- **Tool Layer** (`tools/*.py`) → calls `append_entry()` with parameters
- **Format Layer** (`utils/formatters/dispatcher.py`) → `finalize_tool_response()` wraps based on `format` param
- **MCP SDK Layer** → Receives either `CallToolResult` (readable) or plain dict (structured) from tool
- **Client Layer** → Sees formatted text (readable) or structured JSON (structured)

**Call Chain:**
```
MCP Client
  ↓
MCP SDK (server.py::_call_tool)
  ↓
Tool Function (e.g., open_bug)
  ↓
append_entry(..., format='structured')  ← Pass format here
  ↓
finalize_tool_response(data, format, tool_name)  ← Wrapping decision made here
  ↓
Returns: Dict[str, Any] if format='structured', CallToolResult if format='readable'
```

**Risk Assessment:**
- **Low Risk**: Solution is simple parameter change, no architectural modifications needed
- **High Confidence**: Pattern already used internally (`server.py:693` uses `format="structured"` for internal `list_projects` calls)
- **No Breaking Changes**: External MCP clients unaffected - they always call with default `format='readable'`
- **Cleanup Opportunity**: `_unwrap_result()` helper can be removed after migration to `format='structured'` pattern
<!-- ID: recommendations -->
### Immediate Next Steps

1. **Update `open_bug()` in `tools/sentinel_tools.py`:**
   ```python
   # Line 300 - Add format='structured' parameter
   result = await append_entry_tool(
       message=message,
       status="bug",
       agent=agent,
       meta=meta,
       format='structured'  # ← ADD THIS
   )
   # Line 306 - Remove _unwrap_result() call
   # OLD: result = _unwrap_result(raw_result)
   # NEW: result is already unwrapped dict
   ```

2. **Update `open_security()` in `tools/sentinel_tools.py`:**
   ```python
   # Same pattern - add format='structured' to append_entry_tool call
   # Remove _unwrap_result() call
   ```

3. **Update `link_fix()` in `tools/sentinel_tools.py`:**
   ```python
   # Same pattern - add format='structured' to append_entry_tool call
   # Remove _unwrap_result() call
   ```

4. **Optional Cleanup:**
   - Remove `_unwrap_result()` helper function (lines 30-64) after confirming all uses are migrated
   - Add docstring comment explaining why `format='structured'` is used for internal calls

5. **Testing:**
   - Test `open_bug()`, `open_security()`, `link_fix()` in project mode
   - Verify they correctly generate case IDs and return expected response format
   - Verify `append_event()` still works (should - it doesn't change)

### Long-Term Opportunities

1. **Documentation:**
   - Add pattern to `docs/Scribe_Usage.md` or `CLAUDE.md`:
     > "When one MCP tool calls another internally, always pass `format='structured'` to get unwrapped dict results for processing."

2. **Code Review Guideline:**
   - Add to review checklist: "Internal tool calls must use `format='structured'`"

3. **Type Safety:**
   - Consider adding type hints to make return type explicit:
     ```python
     def append_entry(..., format: Literal['readable', 'structured', 'compact'] = 'readable') -> Union[CallToolResult, Dict[str, Any]]:
     ```

4. **Consistency:**
   - Audit other tools for similar patterns where internal calls might benefit from `format='structured'`
<!-- ID: appendix -->
**References:**
- `tools/append_entry.py:1241-1262` - Function signature with `format='readable'` default
- `tools/append_entry.py:1593-1597` - `finalize_tool_response()` call site
- `tools/sentinel_tools.py:30-64` - `_unwrap_result()` helper function
- `tools/sentinel_tools.py:157-199` - `append_event()` implementation (pass-through pattern)
- `tools/sentinel_tools.py:278-335` - `open_bug()` implementation (processing pattern)
- `utils/formatters/dispatcher.py:89-397` - `ResponseFormatter.finalize_tool_response()` implementation
- `utils/formatters/dispatcher.py:275-281` - MCP wrapping logic for `format='readable'`
- `server.py:690-698` - Internal use of `format="structured"` for `list_projects()`
- `tools/read_recent.py:501-503` - Example of `finalize_tool_response()` usage pattern

**Key Code Locations:**
- **Wrapping happens:** `utils/formatters/dispatcher.py::finalize_tool_response()`
- **Default format defined:** `tools/append_entry.py:1260`
- **Internal call example:** `server.py:693` (startup journal replay)
- **Problem manifestation:** `tools/sentinel_tools.py:306` (_unwrap_result usage)

**Investigation Artifacts:**
- Progress log entries documenting discovery process (10+ entries logged during investigation)
- This research document created via `manage_docs(action="create", metadata={"doc_type": "research"})`

---

**Document Status:** ✅ Complete
**Next Steps:** Hand off to Architect Agent or Coder Agent for implementation
