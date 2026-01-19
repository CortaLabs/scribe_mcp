# BUG-FORMAT-004: rotate_log Has NO Readable Mode

**Discovered**: 2026-01-05 (Phase 5 Team A1 testing)
**Severity**: HIGH
**Type**: Format Parameter Implementation Gap
**Scope**: Single tool (rotate_log)

---

## Summary

The `rotate_log` tool **ignores the `format` parameter entirely** and returns raw JSON for ALL format modes (readable, structured, compact). This violates the format parameter contract and prevents human-readable output.

---

## Affected Tool

**rotate_log** (1 tool confirmed, others may have same issue)

---

## Reproduction Steps

```python
# Test all 3 format modes
result_readable = await mcp__scribe__rotate_log(dry_run=True, format="readable")
result_structured = await mcp__scribe__rotate_log(dry_run=True, format="structured")
result_compact = await mcp__scribe__rotate_log(dry_run=True, format="compact")

# ALL return identical JSON:
# {"ok":true,"rotation_executed":false,"dry_run":true,...}
# (429 characters)

assert result_readable == result_structured == result_compact  # PASSES (should FAIL)
```

**All 3 modes return**:
```json
{
  "ok": true,
  "rotation_executed": false,
  "dry_run": true,
  "dry_run_mode": "estimate",
  "processed_log_types": ["progress"],
  "results": [{
    "log_type": "progress",
    "status": "dry_run_complete",
    "dry_run": true,
    "entry_count": 173,
    "estimated_size": 13891,
    "would_rotate": true
  }],
  "summary": {
    "total_operations": 1,
    "successful": 1,
    "failed": 0,
    "skipped": 0
  },
  ...
}
```

---

## Expected Behavior (Readable Mode)

**rotate_log should return human-friendly box output** like other tools:

```
╔══════════════════════════════════════════════════════════╗
║ 🔄 LOG ROTATION (DRY RUN)                                ║
╚══════════════════════════════════════════════════════════╝

📊 Summary:
  Total operations: 1
  ✅ Successful: 1
  ❌ Failed: 0
  ⏭️  Skipped: 0

📁 Processed Logs:
  • progress log
    ├─ Status: dry_run_complete
    ├─ Entries: 173 (~13.9 KB)
    └─ Would rotate: YES

⚠️  This was a DRY RUN - no files were modified
💡 Tip: Remove dry_run=True to perform actual rotation
```

**Character count**: ~350 chars (vs current 429 JSON chars = **18% smaller**)

---

## Actual Behavior

**All format modes return raw JSON** (429 chars):
- `format="readable"` → JSON
- `format="structured"` → JSON
- `format="compact"` → JSON

No human-readable output available.

---

## Root Cause Analysis

**Hypothesis**: Tool doesn't implement `_format_readable()` method
- Check: `scribe_mcp/tools/rotate_log.py`
- Likely: Missing format dispatch logic, returns raw dict

**Code Location**:
```python
# scribe_mcp/tools/rotate_log.py
# Likely missing:
def _format_readable(self, data: dict) -> str:
    """Human-friendly rotation summary"""
    # Implementation needed
```

**Related Code**:
```
scribe_mcp/tools/rotate_log.py  # Main tool file
scribe_mcp/utils/response.py  # Format dispatch
scribe_mcp/tools/base/base_tool.py  # Base class
```

---

## Impact Assessment

**Severity**: HIGH

**User Impact**:
- rotate_log is frequently used for log maintenance
- JSON output is difficult to read for quick status checks
- Users must parse JSON manually to understand rotation results
- Violates principle of least surprise (other tools have readable mode)

**Developer Impact**:
- Inconsistent behavior across tools
- rotate_log is unique exception to format parameter contract
- Sets bad precedent if left unfixed

**Token Impact**:
- Current JSON: 429 chars
- Expected readable: ~350 chars (**18% reduction**)
- Not as critical as high-frequency tools (list_projects, get_project)
- But still contributes to overall token bloat

---

## Comparison with Other Tools

**Tools with proper readable mode**:
- `set_project`: 380 chars readable vs 1100 structured (**65% smaller**)
- `read_file`: 290 chars readable vs 440 structured (**34% smaller**)
- `list_projects`: 450 chars readable vs 666 structured (**32% smaller**)
- `query_entries`: 1400 chars readable vs 4500 structured (**69% smaller**)

**Average reduction**: 52% token savings

**rotate_log** is the ONLY tested tool without readable mode.

---

## Recommended Fix

### Implementation Plan

1. **Add `_format_readable()` method** to `rotate_log.py`:
   ```python
   def _format_readable(self, data: dict) -> str:
       """Format rotation results as human-readable summary"""
       if data.get("dry_run"):
           header = "🔄 LOG ROTATION (DRY RUN)"
           footer = "⚠️  This was a DRY RUN - no files were modified"
       else:
           header = "🔄 LOG ROTATION COMPLETE"
           footer = "✅ Rotation completed successfully"

       # Build box-formatted output
       summary = data.get("summary", {})
       results = data.get("results", [])

       output = f"""
╔══════════════════════════════════════════════════════════╗
║ {header}                                ║
╚══════════════════════════════════════════════════════════╝

📊 Summary:
  Total operations: {summary.get('total_operations', 0)}
  ✅ Successful: {summary.get('successful', 0)}
  ❌ Failed: {summary.get('failed', 0)}
  ⏭️  Skipped: {summary.get('skipped', 0)}

📁 Processed Logs:
"""
       for result in results:
           log_type = result.get('log_type', 'unknown')
           status = result.get('status', 'unknown')
           entry_count = result.get('entry_count', 0)
           size = result.get('estimated_size', 0) / 1024  # KB

           output += f"""  • {log_type} log
    ├─ Status: {status}
    ├─ Entries: {entry_count} (~{size:.1f} KB)
    └─ {'Would rotate' if data.get('dry_run') else 'Rotated'}: YES

"""

       output += footer
       return output
   ```

2. **Test format parameter dispatch** works correctly

3. **Add tests** for all 3 format modes

---

## Workarounds (Current)

**For users**:
- Parse JSON manually
- Use `jq` or similar tool to extract key fields:
  ```bash
  scribe rotate_log --dry-run | jq -r '.summary'
  ```

**For developers**:
- Accept that rotate_log only returns JSON
- Plan fix for Phase 6 implementation

---

## Testing Evidence

Output sample saved to:
```
.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/tool_outputs/rotate_log/
├── readable.txt (429 chars JSON) ← SHOULD BE READABLE
├── structured.txt (429 chars JSON) ← CORRECT
└── compact.txt (429 chars JSON) ← BUG-FORMAT-003
```

All 3 files contain identical JSON.

---

## Related Bugs

- **BUG-FORMAT-003**: Compact mode not implemented (systemic issue)
- **SPEC-ROTATE-001**: rotate_log verification system (Phase 1)

---

## Acceptance Criteria (Fix Verification)

✅ `format="readable"` returns box-formatted text output
✅ `format="structured"` returns JSON (unchanged)
✅ `format="compact"` returns compact JSON (when BUG-FORMAT-003 fixed)
✅ Readable output is ≤ structured output in character count
✅ All 3 modes return DIFFERENT outputs
✅ Tests added for format parameter compliance

---

**Status**: CONFIRMED
**Priority**: P2 (lower than systemic compact bug, but still important)
**Assigned**: Team B for verification, Implementation team for fix
**Estimated Fix**: 2-3 hours (single tool implementation)

---

**Discovered By**: ResearchAgent-Phase5-OutputRecorder-A1
**Reported**: 2026-01-05 14:44 UTC
**Next Steps**: Team B to check if other tools have same issue
