# BUG-FORMAT-003: Compact Mode Not Implemented (Systemic)

**Discovered**: 2026-01-05 (Phase 5 Team A testing)
**Severity**: HIGH
**Type**: Format Parameter Implementation Gap
**Scope**: SYSTEMIC (affects 100% of tested tools)

---

## Summary

The `format="compact"` parameter is accepted by all tools but returns **byte-for-byte identical output** to `format="structured"` mode. This defeats the entire purpose of compact mode, which should reduce token usage by 20%+ through shortened field names and reduced metadata.

---

## Affected Tools (8/8 tested = 100% failure rate)

1. **list_projects** - compact=666 chars, structured=666 chars (100% identical)
2. **get_project** - compact=651 chars, structured=651 chars (100% identical)
3. **read_recent** - compact=10,500 chars, structured=10,500 chars (100% identical)
4. **query_entries** - compact=4,500 chars, structured=4,500 chars (100% identical)
5. **rotate_log** - compact=429 chars, structured=429 chars (100% identical)
6. **set_project** - compact=1,100 chars, structured=1,100 chars (100% identical)
7. **read_file** - compact=440 chars, structured=440 chars (100% identical)
8. **append_entry** - (no JSON modes, N/A)

**Projected**: Likely affects ALL 16 MCP tools (pending Team A2 testing)

---

## Reproduction Steps

### Test Case 1: list_projects

```python
# Structured mode
result_structured = await mcp__scribe__list_projects(format="structured", limit=3)
# Returns: {"ok":true,"projects":[...],"count":3,...} (666 chars)

# Compact mode
result_compact = await mcp__scribe__list_projects(format="compact", limit=3)
# Returns: {"ok":true,"projects":[...],"count":3,...} (666 chars)

# Verification
assert result_structured == result_compact  # PASSES (should FAIL)
```

### Test Case 2: query_entries

```python
result_structured = await mcp__scribe__query_entries(format="structured", message="bug", limit=3)
# Returns: JSON with full field names (4,500 chars)

result_compact = await mcp__scribe__query_entries(format="compact", message="bug", limit=3)
# Returns: IDENTICAL JSON (4,500 chars)

assert result_structured == result_compact  # PASSES (should FAIL)
```

---

## Expected Behavior

**Compact mode should**:
1. Use **short field names**: `n` instead of `name`, `p` instead of `projects`, `ts` instead of `timestamp`
2. **Omit verbose metadata**: `reminders`, `recent_projects`, `context_safety`
3. **Reduce tokens by ≥20%** compared to structured mode
4. **Target <80% of readable mode tokens**

**Example expected compact output**:
```json
{
  "ok": true,
  "p": [
    {"n": "project1", "s": "planning", "e": 5},
    {"n": "project2", "s": "in_progress", "e": 42}
  ],
  "cnt": 2,
  "pg": {"p": 1, "sz": 3, "tot": 109}
}
```

---

## Actual Behavior

**All tools** return full field names and complete metadata in compact mode:
```json
{
  "ok": true,
  "projects": [
    {"name": "project1", "status": "planning", "entries": 5},
    {"name": "project2", "status": "in_progress", "entries": 42}
  ],
  "count": 2,
  "pagination": {"page": 1, "page_size": 3, "total_count": 109},
  "recent_projects": [...],
  "reminders": []
}
```

**Identical to structured mode** (no token savings).

---

## Root Cause Analysis

**Hypothesis 1**: Tools accept `format` parameter but don't implement separate compact logic
- Check: Do tools have `_format_compact()` method?
- Likely: Falls back to `_format_structured()` or returns raw dict

**Hypothesis 2**: Base class missing compact implementation
- Check: `tools/base/base_tool.py` or `utils/response.py`
- May need: Abstract method `_format_compact()` that subclasses override

**Hypothesis 3**: Format parameter handled in middleware, not per-tool
- Check: `utils/response.py` format dispatch logic
- May be: Switch statement missing `compact` case

**Code Locations to Investigate**:
```
scribe_mcp/utils/response.py  # Format dispatch logic
scribe_mcp/tools/base/base_tool.py  # Base tool class
scribe_mcp/tools/list_projects.py  # Example tool implementation
```

---

## Impact Assessment

**Severity**: HIGH

**User Impact**:
- Users expect compact mode to save tokens (documented feature)
- No token savings = wasted API calls in token-constrained environments
- False advertising if feature is documented but non-functional

**Developer Impact**:
- 100% of tools affected = systematic infrastructure issue
- Cannot be fixed per-tool, needs base class or middleware fix
- High-priority P1 issue for token optimization goals

**Business Impact**:
- Phase 5 goal: 30-40% token reduction (cannot achieve without compact mode)
- Compact mode was PRIMARY strategy for token optimization
- Need alternative strategy or systematic fix

---

## Recommended Fix

### Short-term (Quick Win)
1. **Document limitation**: Update user-facing docs to note compact mode not implemented
2. **Focus on readable mode**: Optimize readable output instead (already shows 52% avg reduction)
3. **Disable compact parameter**: Return error if format="compact" (fail fast)

### Long-term (Proper Fix)
1. **Implement `_format_compact()` in base class**:
   ```python
   # utils/response.py or tools/base/base_tool.py
   def _format_compact(self, data: dict) -> dict:
       """Compact mode: short field names, minimal metadata"""
       return {
           "ok": data.get("ok", True),
           # Map long field names to short versions
           **self._compact_field_mapping(data)
       }
   ```

2. **Create field mapping standard**:
   - `name` → `n`
   - `projects` → `p`
   - `timestamp` → `ts`
   - `pagination` → `pg`
   - etc.

3. **Override per tool for custom compact logic**

4. **Add tests**: Format parameter compliance tests for ALL tools

---

## Workarounds (Current)

**For users**:
- Use `format="readable"` instead (average 52% token savings vs structured)
- Avoid `format="compact"` (provides no benefit)
- Use pagination and filtering to reduce output size

**For developers**:
- Focus token optimization on readable mode
- Document compact mode as "planned feature"
- Team C should analyze readable vs structured (not compact)

---

## Testing Evidence

Output samples saved to:
```
.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/tool_outputs/
├── list_projects/
│   ├── readable.txt (450 chars)
│   ├── structured.txt (666 chars)
│   └── compact.txt (666 chars) ← IDENTICAL
├── query_entries/
│   ├── readable.txt (1,400 chars)
│   ├── structured.txt (4,500 chars)
│   └── compact.txt (4,500 chars) ← IDENTICAL
└── [6 more tools with same pattern]
```

---

## Related Bugs

- **BUG-FORMAT-004**: rotate_log has NO readable mode (only JSON)
- **BUG-001**: set_project empty log marking issue
- **SPEC-TOKEN-001 through SPEC-TOKEN-004**: Token optimization specs

---

## Acceptance Criteria (Fix Verification)

✅ Compact mode output is **≠** structured mode output
✅ Compact mode uses short field names (`n`, `p`, `ts`, etc.)
✅ Compact mode token count is **≤80%** of structured mode
✅ Compact mode omits verbose metadata (reminders, context_safety)
✅ All 16 tools implement compact mode consistently
✅ Tests added to prevent regression

---

**Status**: CONFIRMED (8/8 tools tested, 100% failure rate)
**Priority**: P1 (blocks Phase 5 token optimization goals)
**Assigned**: Team B (Format Validator) for verification, Team C for impact analysis
**Estimated Fix**: 4-8 hours (base class implementation + per-tool overrides)

---

**Discovered By**: ResearchAgent-Phase5-OutputRecorder (Team A + A1)
**Reported**: 2026-01-05 14:43 UTC
**Next Steps**: Team B systematic audit of ALL 16 tools, source code investigation
