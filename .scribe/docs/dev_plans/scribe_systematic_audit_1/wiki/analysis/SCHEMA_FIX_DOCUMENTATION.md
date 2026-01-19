# Schema Fix Documentation: MCP Tool Parameter Exposure

**Date:** 2026-01-07
**Author:** CoderAgent-Wiki
**Project:** scribe_systematic_audit_1
**Category:** Infrastructure Fix

---

## Problem Statement

### Symptom
MCP tool schemas were not exposing parameter types properly, resulting in parameter definitions appearing as empty objects `{}` instead of typed JSON Schema definitions.

### Root Cause
The `from __future__ import annotations` import at the top of `tools/manage_docs.py` (and potentially other tool modules) causes all type annotations to be stored as **string literals** rather than actual type objects.

When `inspect.signature()` reads parameter annotations from functions using `from __future__ import annotations`, it returns string representations like `"str"`, `"Optional[str]"`, `"Dict[str, Any]"` instead of actual type objects.

### Impact
- MCP clients (Claude Code, etc.) couldn't see what parameters tools accepted
- Parameter validation was impaired
- Tool discovery and usage became difficult
- Schema introspection failed for all affected tools

---

## Solution Implementation

### Fix Location
**File:** `server.py`
**Lines:** 142-210
**Function:** `_build_schema_from_signature(func: Callable) -> Dict[str, Any]`

### Technical Approach

#### Key Change
Use `typing.get_type_hints(func)` instead of relying solely on `param.annotation`:

```python
# Before (broken with __future__ annotations):
annotation = param.annotation  # Returns string "str" instead of <class 'str'>

# After (working):
type_hints = typing.get_type_hints(func)  # Resolves string annotations to actual types
annotation = type_hints.get(param_name, param.annotation)
```

#### Implementation Details

**Step 1: Resolve String Annotations (Lines 149-153)**
```python
try:
    type_hints = typing.get_type_hints(func)
except Exception:
    type_hints = {}
```
- `get_type_hints()` evaluates string annotations into actual type objects
- Gracefully handles errors with empty dict fallback
- Works with both `from __future__ import annotations` and normal annotations

**Step 2: Use Resolved Types (Line 171)**
```python
annotation = type_hints.get(param_name, param.annotation)
```
- Prefer resolved type from `get_type_hints()`
- Fall back to raw annotation if resolution failed
- Ensures backward compatibility

**Step 3: Type Mapping (Lines 186-204)**
```python
if annotation is str or annotation == str:
    param_schema = {"type": "string"}
elif annotation is int or annotation == int:
    param_schema = {"type": "integer"}
# ... etc
```
- Maps Python type objects to JSON Schema types
- Handles both identity (`is`) and equality (`==`) checks
- Supports `str`, `int`, `float`, `bool`, `list`, `dict`, `Optional`, `Union`

**Step 4: Optional/Union Handling (Lines 177-183)**
```python
if origin is Union:
    non_none_types = [t for t in args if t is not type(None)]
    if non_none_types:
        annotation = non_none_types[0]
```
- Unwraps `Optional[X]` (which is `Union[X, None]`)
- Extracts underlying type for schema generation
- Maintains type safety while handling nullable parameters

---

## Results

### Before Fix
```json
{
  "name": "manage_docs",
  "inputSchema": {
    "type": "object",
    "properties": {
      "action": {},
      "doc": {},
      "section": {},
      "content": {}
    }
  }
}
```
All parameters showed empty `{}` schemas.

### After Fix
```json
{
  "name": "manage_docs",
  "inputSchema": {
    "type": "object",
    "properties": {
      "action": {"type": "string"},
      "doc": {"type": "string"},
      "section": {"type": "string"},
      "content": {"type": "string"},
      "dry_run": {"type": "boolean"},
      "metadata": {"type": "object"}
    },
    "required": ["action"]
  }
}
```
All parameters now have proper JSON Schema types.

---

## Files Modified

| File | Lines | Description |
|------|-------|-------------|
| `server.py` | 142-210 | Added `typing.get_type_hints()` resolution in `_build_schema_from_signature()` |

---

## Testing Verification

**Manual Verification:**
```bash
# Start MCP server
python -m server

# Inspect tool schemas (via MCP client)
# Verify all manage_docs parameters show proper types
```

**Expected Output:**
- All tool parameters show JSON Schema types (`string`, `integer`, `boolean`, `object`, `array`)
- No empty `{}` parameter schemas
- `required` arrays correctly populated

---

## Lessons Learned

### Python Annotations Gotcha
`from __future__ import annotations` is a **breaking change** for runtime introspection:
- Enables forward references and reduces import overhead
- But stores all annotations as strings
- Requires `typing.get_type_hints()` for runtime type resolution

### Best Practice
When using `from __future__ import annotations`:
1. **Always** use `typing.get_type_hints(func)` for runtime introspection
2. **Never** rely on `param.annotation` directly
3. **Wrap** in try/except to handle edge cases gracefully
4. **Test** schema generation for all affected tools

### Broader Impact
This pattern should be verified across all MCP tool modules:
- Any tool using `from __future__ import annotations`
- Any schema generation or parameter introspection code
- Any validation logic reading type annotations

---

## Related Documentation

- **Python PEP 563:** Postponed Evaluation of Annotations
- **typing.get_type_hints():** Official documentation
- **MCP Tool Schema Spec:** Tool parameter schema requirements

---

## Confidence Score

**0.95** - High confidence in fix correctness
- Root cause clearly identified
- Solution directly addresses the problem
- Implementation follows Python best practices
- Manual testing verified schema exposure

**Uncertainty:**
- Other tools may have same issue (not yet audited)
- Edge cases with complex type annotations (nested generics, custom types)

---

*Documentation created as part of scribe_systematic_audit_1 Phase 5.5 manage_docs audit*
