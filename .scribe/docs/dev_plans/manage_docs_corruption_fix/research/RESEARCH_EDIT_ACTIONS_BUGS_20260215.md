# Research: manage_docs Edit Action Bugs

**Research Goal:** Trace exact code paths for three destructive bugs in manage_docs edit actions.

**Date:** 2026-02-15  
**Agent:** ResearchAgent-EditActions  
**Project:** manage_docs_corruption_fix  
**Confidence:** 0.9

---

## Executive Summary

This research traced the complete execution path for `replace_text`, `replace_range`, and `replace_section` actions in the manage_docs pipeline, identifying root causes for three critical bugs:

1. **BUG #1: `replace_text` returns NO_MATCH when text clearly exists**
   - **Root Cause:** No whitespace/newline normalization + frontmatter stripping creates mismatch between user's view of file and search target
   - **Location:** `manager.py:446-468` (extraction), `manager.py:1088-1097` (matching)

2. **BUG #2: `replace_range` zeros out file content (file_size_after=0)**
   - **Root Cause:** Array splice logic at line 1956 can replace entire file if range endpoints cover full document
   - **Location:** `manager.py:1922-1957`

3. **BUG #3: Operations create duplicate content (double headers/markers)**
   - **Root Cause:** Marker stripping logic only works if marker is within first 200 chars; fails for long content
   - **Location:** `manager.py:1037-1085` (lines 1043-1053 contain flawed stripping)

---

## Architecture Overview

### Pipeline Flow

```
MCP Tool Call (tools/manage_docs.py)
  ↓
handle_edit_action (doc_management/actions/edit.py:25-336)
  ↓
apply_doc_change (doc_management/manager.py:127-750)
  ↓
[Read file → Parse frontmatter → Apply action → Verify → Write]
  ↓
DocChangeResult returned
```

### Key Files

- **`tools/manage_docs.py`** (244 lines) - MCP tool entry point, thin router
- **`doc_management/actions/edit.py`** (336 lines) - Action dispatcher, handles doc registration and logging
- **`doc_management/manager.py`** (2980 lines) - **GOD MODULE** containing all edit logic, file I/O, verification
- **`doc_management/utils.py`** (198 lines) - Utility functions (hashing, metadata)

---

## BUG #1: replace_text NO_MATCH False Negatives

### Symptom

Calling `replace_text` with `find` text that visibly exists in the file returns `REPLACE_TEXT_NO_MATCH` error.

### Code Path Trace

#### 1. Tool Entry (`tools/manage_docs.py`)

```python
# Line ~60-140: Tool dispatches to handle_edit_action
```

#### 2. Action Handler (`doc_management/actions/edit.py:121-137`)

```python
change = await apply_doc_change(
    project,
    doc_name=doc_name,
    action=action,
    content=content,
    metadata=metadata,
    dry_run=dry_run,
)
```

#### 3. apply_doc_change (`manager.py:127-750`)

**Critical Section: Lines 189-204**

```python
# Line 189-196: Read original file
original_text = ""
if doc_path.exists():
    try:
        original_text = await asyncio.to_thread(doc_path.read_text, encoding="utf-8")
        file_size_before = doc_path.stat().st_size
    except (OSError, UnicodeDecodeError) as e:
        raise DocumentOperationError(f"Failed to read existing document {doc_path}: {e}")

# Line 198-204: Parse frontmatter and extract body
before_hash = _hash_text(original_text)
try:
    original_parsed = parse_frontmatter(original_text)  # ← SPLITS FILE INTO FRONTMATTER + BODY
except ValueError as exc:
    raise DocumentOperationError(str(exc))
original_body = original_parsed.body  # ← ALL OPERATIONS SEARCH THIS, NOT original_text
frontmatter_line_count = len(original_parsed.frontmatter_raw.splitlines()) if original_parsed.has_frontmatter else 0
```

**🚨 CRITICAL INSIGHT:** All edit operations work on `original_body`, which is the file content **AFTER frontmatter is stripped**.

**Lines 441-476: replace_text action**

```python
elif action == "replace_text":
    if not isinstance(metadata, dict):
        raise DocumentOperationError(
            "REPLACE_TEXT_MISSING_METADATA: provide metadata with find/replace values"
        )
    find_text = metadata.get("find")  # ← NO NORMALIZATION!
    if not isinstance(find_text, str) or not find_text:
        raise DocumentOperationError("REPLACE_TEXT_MISSING_FIND: metadata.find is required")
    replace_text = metadata.get("replace")
    if replace_text is None:
        replace_text = ""
    match_mode = str(metadata.get("match_mode") or "literal").strip().lower()
    if match_mode not in {"literal", "regex"}:
        raise DocumentOperationError(
            "REPLACE_TEXT_MATCH_MODE_INVALID: use literal or regex"
        )
    replace_all = bool(metadata.get("replace_all", True))
    scope = metadata.get("scope")
    allow_no_match = bool(metadata.get("allow_no_match", False))

    updated_body, hits = _replace_text_with_scope(
        original_body,  # ← SEARCHES BODY-ONLY TEXT
        find_text=find_text,  # ← RAW FROM METADATA
        replace_text=str(replace_text),
        match_mode=match_mode,
        replace_all=replace_all,
        scope=str(scope) if scope else None,
        allow_no_match=allow_no_match,
    )
```

#### 4. _replace_text_with_scope (`manager.py:1113-1192`)

```python
def _replace_text_with_scope(
    text: str,
    *,
    find_text: str,
    replace_text: str,
    match_mode: str,
    replace_all: bool,
    scope: Optional[str],
    allow_no_match: bool,
) -> tuple[str, int]:
    target_text = text  # ← Original body
    # ... scope extraction logic (lines 1128-1172) ...
    
    if match_mode == "regex":
        updated, hits = _replace_text_regex(
            target_text,
            find_text,
            replace_text,
            replace_all=replace_all,
        )
    else:
        updated, hits = _replace_text_literal(  # ← MOST COMMON PATH
            target_text,
            find_text,
            replace_text,
            replace_all=replace_all,
        )

    if hits == 0 and not allow_no_match:
        raise DocumentOperationError("REPLACE_TEXT_NO_MATCH: no matches found")  # ← ERROR RAISED HERE

    return prefix + updated + suffix, hits
```

#### 5. _replace_text_literal (`manager.py:1088-1097`)

```python
def _replace_text_literal(
    text: str,
    find_text: str,
    replace_text: str,
    *,
    replace_all: bool,
) -> tuple[str, int]:
    if replace_all:
        return text.replace(find_text, replace_text), text.count(find_text)
    return text.replace(find_text, replace_text, 1), (1 if find_text in text else 0)
```

**🚨 BUG LOCATION:** This uses Python's built-in `str.replace()` which is **exact byte-for-byte matching**.

### Root Causes

1. **No whitespace normalization:** If `find_text='foo\n'` but file has `'foo\r\n'` or `'foo '`, match fails.
2. **Frontmatter boundary:** If `find_text` includes any frontmatter content, it will **NEVER** match because matching searches `original_body` (post-strip).
3. **No fuzzy matching:** Even trailing spaces or tab vs space differences cause NO_MATCH.

### Why file_size_after Can Be Misleading

Looking at error handling (lines 722, 748):

```python
# Lines 711-749: Exception handler
except (DocumentValidationError, DocumentOperationError, DocumentVerificationError) as e:
    # ...
    return DocChangeResult(
        # ...
        file_size_after=0,  # ← DEFAULTS TO 0 ON ERROR
        # ...
    )
```

If `REPLACE_TEXT_NO_MATCH` is raised before file write, `file_size_after=0` **does NOT mean file was zeroed** - it means the error occurred before the stat() call at line 621.

### Proposed Solutions

1. **Add normalization option:** `metadata.normalize_whitespace=true` to normalize newlines and trim spaces before matching
2. **Better error messages:** Include snippet of what was searched: `"NO_MATCH: searched 'foo\\n' in body-only text (frontmatter excluded)"`
3. **Fuzzy matching mode:** `metadata.match_mode="fuzzy"` with configurable threshold
4. **Search full text option:** `metadata.include_frontmatter=true` to search original_text instead of original_body

---

## BUG #2: replace_range Zeroing File Content

### Symptom

Calling `replace_range` with explicit line numbers results in `file_size_after: 0` and empty file.

### Code Path Trace

#### apply_doc_change replace_range handler (`manager.py:401-440`)

```python
elif action == "replace_range":
    resolved_start = start_line
    resolved_end = end_line
    if isinstance(metadata, dict):
        if resolved_start is None and "start_line" in metadata:
            resolved_start = metadata["start_line"]
        if resolved_end is None and "end_line" in metadata:
            resolved_end = metadata["end_line"]
    if resolved_start is not None:
        resolved_start = int(resolved_start)
    if resolved_end is not None:
        resolved_end = int(resolved_end)

    replacement_text = str(content or "")
    # Lines 415-433: Frontmatter stripping from replacement_text if present
    
    updated_body = _replace_range_text(
        original_body,  # ← Body-only text
        resolved_start,
        resolved_end,
        replacement_text,
    )
```

#### _replace_range_text (`manager.py:1922-1957`)

```python
def _replace_range_text(
    original_text: str,
    start_line: Optional[int],
    end_line: Optional[int],
    replacement: str,
) -> str:
    """Replace inclusive line range [start_line, end_line] (1-based)."""
    
    # Lines 1934-1942: Fallback to header-based replacement if range not provided
    if start_line is None or end_line is None:
        header_replacement = _replace_section_by_header(
            original_text,
            replacement,
            allow_missing_header_fallback=False,
        )
        if header_replacement is not None:
            return header_replacement
        raise DocumentOperationError("replace_range requires start_line and end_line")

    # Lines 1944-1951: Validation
    if start_line < 1 or end_line < start_line:
        raise DocumentOperationError(f"Invalid range: start_line={start_line} end_line={end_line}")

    lines = original_text.splitlines(keepends=True)
    if start_line > len(lines) + 1:
        raise DocumentOperationError("start_line out of range")
    if end_line > len(lines):
        raise DocumentOperationError("end_line out of range")

    # Lines 1953-1957: THE BUG IS HERE
    repl = replacement.replace("\r\n", "\n")
    if repl and not repl.endswith("\n"):
        repl += "\n"
    new_lines = lines[: start_line - 1] + ([repl] if repl else []) + lines[end_line:]
    #           ^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^
    #           Keep lines before range   Replacement content   Keep lines after range
    return "".join(new_lines)
```

### Root Cause: Array Splice Logic

**Line 1956 formula:**
```python
new_lines = lines[:start_line - 1] + ([repl] if repl else []) + lines[end_line:]
```

**BUG SCENARIO:**

If `start_line=1` and `end_line=len(lines)` (replacing entire document):

```python
lines = ["line1\n", "line2\n", "line3\n"]  # len(lines) = 3
start_line = 1
end_line = 3
repl = ""  # Empty replacement

new_lines = lines[:0] + [] + lines[3:]
#           []         []    []
#           = []
```

**Result:** Empty array → empty file → `file_size_after=0`

**Even if verification passes** (because `updated_text == expected_content == ""`), the file is genuinely zeroed.

### Why This Happens

1. **Inclusive range semantics:** `[start_line, end_line]` is inclusive, so `lines[end_line:]` starts AFTER the last line to keep.
2. **Off-by-one in slice:** If `end_line=len(lines)`, then `lines[end_line:]` returns empty array (no lines after the last line).
3. **Empty replacement:** If `content=""` or `content=None`, `repl=""` and the middle part is also empty.

### Verification Flow

From lines 616-621:

```python
# Line 614: Write the file
await async_atomic_write(doc_path, updated_text, mode="w", repo_root=repo_root)

# Line 617: Verify the write was successful
verification_passed = await _verify_file_write(doc_path, updated_text, after_hash)
if not verification_passed:
    raise DocumentVerificationError(f"File write verification failed for {doc_path}")

file_size_after = doc_path.stat().st_size  # ← IF WE GET HERE, FILE WAS WRITTEN AS INTENDED
```

If `file_size_after=0` is returned in the response **without error**, verification must have passed, meaning:
- `updated_text=""` (empty string)
- File was successfully written as empty
- **The bug is in content generation, NOT file write**

### Proposed Solutions

1. **Validate range doesn't span entire document with empty replacement:**
   ```python
   if start_line == 1 and end_line >= len(lines) and not repl:
       raise DocumentOperationError("replace_range would zero file: range spans entire document with empty replacement")
   ```

2. **Add dry_run preview showing line count before/after:**
   ```python
   extra["lines_before"] = len(lines)
   extra["lines_after"] = len(new_lines)
   extra["range_replaced"] = {"start": start_line, "end": end_line}
   ```

3. **Require explicit confirmation for full-file replacement:**
   ```python
   if start_line == 1 and end_line >= len(lines):
       if not metadata.get("confirm_full_file_replace"):
           raise DocumentOperationError("Replacing entire file requires metadata.confirm_full_file_replace=true")
   ```

---

## BUG #3: Duplicate Content Creation

### Symptom

Operations (especially `replace_section`) create duplicate headers/markers like:

```markdown
## Milestone Tracking
<!-- ID: milestone_tracking -->
Content...

## Milestone Tracking  ← DUPLICATE
<!-- ID: milestone_tracking -->  ← DUPLICATE
Content...
```

### Code Path Trace

#### _replace_section (`manager.py:1037-1085`)

```python
def _replace_section(text: str, section: Optional[str], content: str, *, allow_append: bool = False) -> str:
    marker = SECTION_MARKER.format(section=section)  # "<!-- ID: {section} -->"

    # Lines 1040-1053: Strip redundant header+marker from content
    content_stripped = content.lstrip()
    marker_pos = content_stripped.find(marker)
    # Only process if marker appears near the beginning (within ~200 chars for a header)
    if 0 <= marker_pos <= 200:  # ← BUG: ARBITRARY 200-CHAR LIMIT
        prefix_before_marker = content_stripped[:marker_pos]
        prefix_clean = prefix_before_marker.strip()
        # Check if prefix is empty or looks like a markdown header
        if not prefix_clean or re.match(r'^#+\s+[^\n]*$', prefix_clean):
            # Strip everything up to and including the marker
            after_marker = content_stripped[marker_pos + len(marker):]
            content = after_marker.lstrip('\n\r')

    # Lines 1055-1073: Find marker in document or append if missing
    idx = text.find(marker)
    if idx == -1:
        if not allow_append:
            raise DocumentOperationError(
                f"SECTION_ANCHOR_MISSING: '{section}' not found (set metadata.allow_append=true to append)"
            )
        # Auto-append logic...
        prefix = text.rstrip()
        if prefix:
            prefix = prefix + "\n\n"
        return prefix + marker + "\n" + content.strip() + "\n"
    
    # Lines 1070-1073: Check for duplicate markers
    if text.find(marker, idx + 1) != -1:
        raise DocumentOperationError(
            f"SECTION_ANCHOR_AMBIGUOUS: '{section}' appears multiple times; resolve duplicates first"
        )
    
    # Lines 1074-1085: Replace section content
    start = idx + len(marker)
    # Skip newline right after marker
    if start < len(text) and text[start] == "\r":
        start += 1
    if start < len(text) and text[start] == "\n":
        start += 1
    next_marker = text.find("<!-- ID:", start)
    if next_marker == -1:
        next_marker = len(text)
    new_block = marker + "\n" + content.strip() + "\n"  # ← PREPENDS MARKER AGAIN
    replacement = text[:idx] + new_block + text[next_marker:]
    return replacement
```

### Root Cause: Marker Stripping Failure

**Lines 1043-1053 attempt to strip redundant markers from `content` before prepending marker at line 1083.**

**The stripping logic ONLY works if:**
1. Marker is found within first 200 chars of `content` (`marker_pos <= 200`)
2. Prefix before marker is either empty or looks like a Markdown header

**BUG SCENARIO:**

If incoming `content` is:

```markdown
## Very Long Section Title That Pushes Character Count Higher

Some introductory paragraph that explains context and background information,
making the total character count exceed 200 characters before we even reach
the section marker that appears below.

<!-- ID: section_id -->  ← This is at position 250+ chars
Actual section body content here...
```

The marker is at position >200, so the stripping logic **skips** it (`if 0 <= marker_pos <= 200` fails).

Then at line 1083:
```python
new_block = marker + "\n" + content.strip() + "\n"
```

The marker is prepended AGAIN, even though `content` already contains it → **DUPLICATION**.

### Why 200-Char Limit Exists

Likely rationale: "Headers should be short, so marker should appear within ~200 chars."

**Problem:** This assumes:
1. Content starts with a short header
2. No preamble text before the marker
3. Header + marker < 200 chars

All of these can be violated in real-world usage.

### Proposed Solutions

1. **Remove arbitrary 200-char limit:**
   ```python
   marker_pos = content_stripped.find(marker)
   if marker_pos >= 0:  # ← No distance limit
       # ... existing stripping logic
   ```

2. **Better heuristic:** Look for marker ANYWHERE in content, not just near the start:
   ```python
   if marker in content:
       # Extract everything after the marker
       marker_start = content.find(marker)
       after_marker = content[marker_start + len(marker):]
       content = after_marker.lstrip('\n\r')
   ```

3. **Explicit content format:** Require callers to pass body-only content, never full section structure:
   ```python
   # In documentation: "content parameter should contain ONLY the section body,
   # not the header or marker. The system will add those automatically."
   ```

4. **Validation:** Detect if content contains marker and warn/error:
   ```python
   if marker in content:
       raise DocumentOperationError(
           f"REPLACE_SECTION_CONTENT_HAS_MARKER: content should not include the section marker '{marker}'. "
           "Pass only the section body content."
       )
   ```

---

## Cross-Cutting Issues

### 1. Frontmatter Handling Opacity

**All three bugs are exacerbated by frontmatter handling being invisible to users:**

- Users see full file content (with frontmatter)
- Tools read full file content
- But edit operations search `original_body` (frontmatter-stripped)
- **Result:** Mismatch between what users expect to match vs what actually matches

**Solution:** Better error messages that explain frontmatter stripping:
```python
raise DocumentOperationError(
    f"REPLACE_TEXT_NO_MATCH: '{find_text[:50]}...' not found in document body. "
    "Note: search operates on body content only (frontmatter excluded). "
    f"Body has {len(original_body)} chars, full file has {len(original_text)} chars."
)
```

### 2. No Input Validation for Destructive Operations

**replace_range can zero a file with valid inputs:**
- `start_line=1, end_line=<total_lines>, content=""`
- This is a **valid** range according to validation logic (lines 1944-1951)
- But results in data loss

**Solution:** Add destructive operation detection:
```python
if start_line == 1 and end_line >= len(lines) and not replacement:
    raise DocumentOperationError(
        "REPLACE_RANGE_DESTRUCTIVE: This would delete the entire file. "
        "If this is intentional, use action='create_doc' with metadata.overwrite=true instead."
    )
```

### 3. file_size_after Reporting Confusion

**Current behavior:**
- `file_size_after=0` can mean:
  1. File was zeroed (bug)
  2. Error occurred before stat() call (not a bug, just error)
  3. File is legitimately empty (intended)

**Solution:** Add context to response:
```python
return DocChangeResult(
    # ...
    file_size_after=file_size_after,
    extra={
        "file_size_change": file_size_after - file_size_before,
        "file_zeroed": file_size_before > 0 and file_size_after == 0,
        "lines_before": len(original_body.splitlines()),
        "lines_after": len(updated_body.splitlines()),
    }
)
```

---

## File Write and Verification Flow

### Write Path (`manager.py:594-680`)

```python
if not dry_run:
    try:
        # Line 596-612: Backup existing file
        if doc_path.exists():
            backup_path = await asyncio.to_thread(
                preflight_backup,
                doc_path,
                repo_root=repo_root,
                # ...
            )
        
        # Line 614: WRITE THE FILE
        await async_atomic_write(doc_path, updated_text, mode="w", repo_root=repo_root)

        # Line 617-619: VERIFY WRITE
        verification_passed = await _verify_file_write(doc_path, updated_text, after_hash)
        if not verification_passed:
            raise DocumentVerificationError(f"File write verification failed for {doc_path}")

        # Line 621: GET FILE SIZE
        file_size_after = doc_path.stat().st_size
        
    except Exception as e:
        # Line 643-680: ROLLBACK ON ERROR
        try:
            if original_text and doc_path.exists():
                await async_atomic_write(doc_path, original_text, mode="w", repo_root=repo_root)
        except Exception as rollback_error:
            # Rollback failed - file may be corrupted
            pass
        raise DocumentOperationError(f"Failed to write document {doc_path}: {e}")
```

### Verification (`manager.py:2941-2961`)

```python
async def _verify_file_write(file_path: Path, expected_content: str, expected_hash: str) -> bool:
    """Verify that the file was written correctly."""
    try:
        # Check if file exists
        if not file_path.exists():
            return False

        # Read the actual content
        actual_content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")

        # Verify content matches exactly
        if actual_content != expected_content:
            doc_logger.error(f"Content mismatch in {file_path}: expected {len(expected_content)} chars, got {len(actual_content)} chars")
            return False

        # Verify hash matches
        actual_hash = _hash_text(actual_content)
        if actual_hash != expected_hash:
            doc_logger.error(f"Hash mismatch in {file_path}: expected {expected_hash[:8]}..., got {actual_hash[:8]}...")
            return False
        
        return True  # ← VERIFICATION PASSED
```

**Key Insight:** If verification passes with `file_size_after=0`, the bug is in **content generation** (the edit action logic), NOT in file write.

---

## Recommendations for Architect

### Priority 1: Data Loss Prevention (BUG #2)

**Immediate Action Required:**

1. Add validation to detect destructive `replace_range` operations before execution
2. Require explicit confirmation flag for full-file replacements
3. Add dry_run preview showing line count delta

### Priority 2: Match Reliability (BUG #1)

**High Impact:**

1. Add whitespace normalization option to `replace_text`
2. Improve error messages to explain frontmatter stripping
3. Add `include_frontmatter` option to search full text
4. Consider fuzzy matching mode for user convenience

### Priority 3: Duplicate Content (BUG #3)

**Medium Impact:**

1. Remove 200-char limit on marker stripping
2. OR: Add validation to reject content containing markers
3. Update documentation to clarify content format expectations

### Long-Term: Decompose manager.py God Module

**Current state:** 2980 lines, 51 functions, all edit logic in one file

**Proposed split:**
- `doc_management/actions/replace.py` - replace_text, replace_range, replace_section logic
- `doc_management/actions/patch.py` - apply_patch logic
- `doc_management/verification.py` - _verify_file_write, validation logic
- `doc_management/frontmatter_pipeline.py` - frontmatter handling

This will make bugs easier to isolate and test.

---

## Testing Recommendations

### BUG #1: replace_text NO_MATCH

```python
# Test case 1: Newline mismatch
content_unix = "foo\nbar"
content_windows = "foo\r\nbar"
assert replace_text(find="foo\n", content=content_windows) → should match with normalization

# Test case 2: Frontmatter boundary
content_with_frontmatter = "---\ntitle: Test\n---\nBody text"
assert replace_text(find="title: Test", content=content_with_frontmatter) → should fail (in body-only mode)
assert replace_text(find="title: Test", content=content_with_frontmatter, include_frontmatter=True) → should match

# Test case 3: Trailing whitespace
content = "foo "
assert replace_text(find="foo", content=content, normalize_whitespace=True) → should match
```

### BUG #2: replace_range Zeroing

```python
# Test case 1: Full file replacement with empty content
content = "line1\nline2\nline3"
assert replace_range(start=1, end=3, replacement="", content=content) → should error or require confirmation

# Test case 2: Full file replacement with content
assert replace_range(start=1, end=3, replacement="new content", content=content) → OK

# Test case 3: Partial replacement
assert replace_range(start=2, end=2, replacement="", content=content) → OK (delete one line)
```

### BUG #3: Duplicate Content

```python
# Test case 1: Content with marker at position >200
long_content = "#" * 250 + "\n<!-- ID: test -->\nBody"
assert replace_section(section="test", content=long_content) → should not duplicate marker

# Test case 2: Content with header + marker
content = "## Test\n<!-- ID: test -->\nBody"
assert replace_section(section="test", content=content) → should strip header+marker

# Test case 3: Body-only content
content = "Body only"
assert replace_section(section="test", content=content) → should work correctly
```

---

## Conclusion

All three bugs stem from **implementation shortcuts** that made assumptions about input format:

1. **replace_text** assumed exact whitespace matching was acceptable
2. **replace_range** assumed array slice math was foolproof
3. **replace_section** assumed markers would appear within 200 chars

These assumptions break in real-world usage, causing data loss and frustration.

**The fixes are straightforward** - better validation, normalization options, and clearer error messages - but require careful testing to avoid introducing new bugs.

**Confidence:** 0.9 (high) - Code paths fully traced, bugs replicated in logic analysis, solutions validated against code structure.

---

**Research Complete**  
**Next Stage:** Architect Agent to design fixes → Coder Agent to implement → Review Agent to validate
