# manage_docs Troubleshooting Guide

Comprehensive troubleshooting reference for `manage_docs` operations in the Scribe MCP system.

## Quick Diagnosis

**Common symptoms and immediate checks:**

| Symptom | First Check | Quick Fix |
|---------|-------------|-----------|
| `DOC_NOT_FOUND` error | Is file on disk? | `generate_doc_templates()` or verify EDIT action |
| Edit succeeds but no changes | Dry run enabled? | Set `dry_run=False` |
| Section not found | Section anchor exists? | Use `list_sections` to find valid IDs |
| Auto-registration fails | File exists? | Create file first with `generate_doc_templates()` |
| Database errors | Backend configured? | Run `scribe_doctor()` |

## Auto-Registration Issues

### Error: `DOC_NOT_FOUND: Document 'X' not registered`

**Symptom:** Edit operation fails with document not found error, even though file exists.

**Possible Causes:**
1. Action is not an EDIT operation (CREATE actions don't auto-register)
2. Auto-registration is somehow disabled (rare in v2.2.0+)
3. Auto-registration attempted but failed silently
4. File doesn't exist at expected path

**Diagnosis Steps:**

```python
# 1. Verify project context
await get_project()
# Check that project name matches

# 2. Check if file exists
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")
# Should succeed if file exists

# 3. Check progress log for auto-registration attempts
await read_recent(n=10)
# Look for auto-registration messages or errors

# 4. Verify you're using an EDIT action
# See docs/guides/manage_docs_agent_guide.md for list
```

**Solutions:**

```python
# Solution 1: Manual registration
await generate_doc_templates(project_name="<project>")

# Solution 2: Verify action type
# Use EDIT actions: replace_section, append, etc.
# Don't use CREATE actions for existing docs

# Solution 3: Check file path
await read_file(path=".scribe/docs/dev_plans/<project>/")
# Verify document files exist in expected location
```

### Error: `Cannot auto-register: file does not exist at path X`

**Symptom:** Auto-registration attempted but file is missing from disk.

**Possible Causes:**
1. Project scaffolding wasn't created
2. Document was deleted
3. Project name mismatch
4. Path resolution error

**Diagnosis Steps:**

```python
# 1. List project directory contents
await read_file(path=".scribe/docs/dev_plans/<project>/", mode="scan_only")

# 2. Verify project name
result = await get_project()
print(result["project"]["name"])

# 3. Check expected path
# architecture → ARCHITECTURE_GUIDE.md
# phase_plan → PHASE_PLAN.md
# checklist → CHECKLIST.md
```

**Solutions:**

```python
# Solution 1: Create initial scaffolding
await generate_doc_templates(project_name="<project>")

# Solution 2: Use CREATE action for new documents
await manage_docs(
    action="create_research_doc",
    doc="research",
    doc_name="RESEARCH_TOPIC_20260106",
    metadata={...}
)

# Solution 3: Verify project exists
await list_projects(filter="<project_name>")
```

### Auto-registration succeeds but edit fails

**Symptom:** Progress log shows successful auto-registration, but edit operation fails.

**Possible Causes:**
1. Section anchor doesn't exist (for `replace_section`)
2. Line numbers out of bounds (for `replace_range`)
3. YAML frontmatter corrupted
4. Document format issues

**Diagnosis Steps:**

```python
# 1. List available sections
sections = await manage_docs(action="list_sections", doc="architecture")
# Check if your section ID exists

# 2. Read document content
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")
# Verify format and anchors

# 3. Check for frontmatter issues
# Look for valid YAML at top of file
```

**Solutions:**

```python
# Solution 1: Use correct section ID
sections = await manage_docs(action="list_sections", doc="architecture")
# Use IDs from this list

# Solution 2: Switch to replace_range for problematic sections
await manage_docs(
    action="replace_range",
    doc="architecture",
    start_line=42,
    end_line=50,
    content="..."
)

# Solution 3: Normalize document first
await manage_docs(action="normalize_headers", doc="architecture")
```

## Document Edit Issues

### Error: `STRUCTURED_EDIT_ANCHOR_NOT_FOUND`

**Symptom:** Section anchor not found in document body.

**Possible Causes:**
1. Anchor ID doesn't exist in document
2. Typo in section parameter
3. Document was modified and anchor removed
4. Case sensitivity mismatch

**Diagnosis Steps:**

```python
# 1. List all available sections
result = await manage_docs(action="list_sections", doc="architecture")
print(result["sections"])  # All valid section IDs

# 2. Search for the section in file content
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")
# Look for <!-- ID: your_section_id -->
```

**Solutions:**

```python
# Solution 1: Use valid section ID
sections = await manage_docs(action="list_sections", doc="architecture")
valid_id = sections["sections"][0]["id"]
await manage_docs(
    action="replace_section",
    doc="architecture",
    section=valid_id,
    content="..."
)

# Solution 2: Add the anchor to document first
await manage_docs(
    action="append",
    doc="architecture",
    content="\n<!-- ID: new_section -->\n## New Section\n..."
)

# Solution 3: Use replace_range instead
await manage_docs(
    action="replace_range",
    doc="architecture",
    start_line=100,
    end_line=120,
    content="..."
)
```

### Error: `STRUCTURED_EDIT_ANCHOR_AMBIGUOUS`

**Symptom:** Multiple lines match the anchor text in `replace_block`.

**Possible Causes:**
1. Duplicate text in document
2. Non-unique anchor pattern
3. Multiple instances of same header text

**Diagnosis Steps:**

```python
# Error message includes line numbers where anchor was found
# Review the error to see all matching locations

# Read document to understand duplicates
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")
```

**Solutions:**

```python
# Solution 1: Use more specific anchor text
await manage_docs(
    action="apply_patch",
    doc="architecture",
    edit={
        "type": "replace_block",
        "anchor": "**Very Specific Unique Text:**",  # More unique
        "new_content": "..."
    }
)

# Solution 2: Use replace_range with exact line numbers
await manage_docs(
    action="replace_range",
    doc="architecture",
    start_line=42,  # Exact line from error message
    end_line=50,
    content="..."
)

# Solution 3: Use replace_section with anchors
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="unique_section_id",
    content="..."
)
```

### Line number issues with `replace_range`

**Symptom:** Wrong lines are replaced or operation fails with out-of-bounds error.

**Possible Causes:**
1. Forgetting that line numbers are body-relative (exclude frontmatter)
2. Document was edited since you determined line numbers
3. Off-by-one errors

**Diagnosis Steps:**

```python
# 1. Read document with line numbers
await read_file(
    path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md",
    mode="line_range",
    start_line=1,
    end_line=100
)
# Note: This shows file lines, not body-relative lines

# 2. List checklist items (includes body-relative line numbers)
await manage_docs(
    action="list_checklist_items",
    doc="checklist",
    metadata={"text": "search term"}
)
# Returns body_line_offset for accurate targeting
```

**Solutions:**

```python
# Solution 1: Account for frontmatter
# If frontmatter is 8 lines, subtract 8 from file line numbers
body_line = file_line - 8

# Solution 2: Use list_checklist_items for checklists
items = await manage_docs(action="list_checklist_items", doc="checklist")
# Use body_line_offset from results

# Solution 3: Use section-based editing
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="section_id",
    content="..."
)
```

## Database Issues

### Error: `Database write failed` or `Connection refused`

**Symptom:** Auto-registration or document updates fail with database errors.

**Possible Causes:**
1. Database backend not configured
2. Connection string invalid
3. Write permissions missing
4. Database file locked
5. PostgreSQL server not running

**Diagnosis Steps:**

```python
# 1. Check system health
await scribe_doctor()
# Returns database backend status and connectivity

# 2. Verify environment variables
import os
print(os.getenv("SCRIBE_STORAGE_BACKEND"))  # Should be "sqlite" or "postgres"
print(os.getenv("SCRIBE_DB_URL"))  # For postgres only

# 3. Check database file permissions (SQLite)
# ls -la .scribe/scribe.db
# Should be writable by current user
```

**Solutions:**

```python
# Solution 1: Configure backend (SQLite - default)
# No configuration needed, auto-created

# Solution 2: Configure PostgreSQL
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL=postgresql://user:pass@host/db

# Solution 3: Fix permissions (SQLite)
chmod 644 .scribe/scribe.db
chmod 755 .scribe/

# Solution 4: Verify PostgreSQL server
psql $SCRIBE_DB_URL -c "SELECT 1;"
```

### Error: `Project not found in database`

**Symptom:** Operations fail because project doesn't exist in registry.

**Possible Causes:**
1. Project never initialized
2. Database was reset
3. Project name mismatch

**Diagnosis Steps:**

```python
# 1. List all projects
await list_projects()

# 2. Check current project context
await get_project()

# 3. Search for project by name
await list_projects(filter="<partial_name>")
```

**Solutions:**

```python
# Solution 1: Initialize project
await set_project(name="<project_name>")

# Solution 2: Verify correct project name
projects = await list_projects()
# Use exact name from this list

# Solution 3: Create new project if lost
await set_project(name="<project_name>")
await generate_doc_templates(project_name="<project_name>")
```

## Performance Issues

### Slow document operations

**Symptom:** `manage_docs` operations take longer than expected.

**Possible Causes:**
1. Large document files
2. Complex YAML frontmatter
3. Semantic search with large vector index
4. Multiple batch operations

**Diagnosis Steps:**

```python
# 1. Check document file size
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md", mode="scan_only")
# Check "Size" in response

# 2. Profile operation
import time
start = time.time()
await manage_docs(action="...", doc="...", ...)
print(f"Operation took {time.time() - start:.2f}s")

# 3. Check vector index size (for semantic search)
await scribe_doctor()
# Shows vector index metrics if enabled
```

**Solutions:**

```python
# Solution 1: Use more specific operations
# Instead of batch, do individual targeted edits
await manage_docs(action="replace_section", doc="architecture", section="specific_section", ...)

# Solution 2: Reduce semantic search scope
await manage_docs(
    action="search",
    doc="*",
    metadata={
        "query": "...",
        "search_mode": "semantic",
        "doc_k": 5,  # Limit results
        "project_slug": "specific_project"  # Narrow scope
    }
)

# Solution 3: Split large documents
# Break monolithic docs into smaller, focused documents
```

### High memory usage

**Symptom:** System memory usage spikes during `manage_docs` operations.

**Possible Causes:**
1. Very large document files
2. Batch operations with many items
3. Semantic search loading large embeddings

**Solutions:**

```python
# Solution 1: Process in smaller chunks
# Instead of one large batch, do multiple small batches

# Solution 2: Use streaming for large files
await read_file(
    path="...",
    mode="chunk",
    chunk_index=[0]  # Process one chunk at a time
)

# Solution 3: Limit search results
await manage_docs(
    action="search",
    metadata={"k": 10, "min_similarity": 0.7}  # Fewer, higher-quality results
)
```

## Workflow Issues

### Changes not appearing in document

**Symptom:** Edit operation succeeds, but file content unchanged.

**Possible Causes:**
1. Dry run mode enabled
2. Wrong document key
3. Edit applied to wrong section
4. Caching issue

**Diagnosis Steps:**

```python
# 1. Check dry_run parameter
# Verify you're not passing dry_run=True

# 2. Re-read document
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")

# 3. Check progress log for edit confirmation
await read_recent(n=5)
# Should show edit operation logged
```

**Solutions:**

```python
# Solution 1: Disable dry run
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="...",
    content="...",
    dry_run=False  # Explicitly disable
)

# Solution 2: Verify correct document
result = await manage_docs(action="list_sections", doc="architecture")
print(result["path"])  # Confirm this is the file you want to edit

# Solution 3: Force refresh
# Re-read the file after a moment
import time
time.sleep(1)
await read_file(path="...")
```

### Batch operations failing partway through

**Symptom:** First few operations succeed, then batch fails.

**Possible Causes:**
1. Later operation has invalid parameters
2. Earlier operation changed document structure
3. Section anchors became invalid mid-batch

**Diagnosis Steps:**

```python
# Check error message - it will indicate which operation failed
# Review progress log for partial completions
await read_recent(n=10)
```

**Solutions:**

```python
# Solution 1: Execute operations individually to isolate failure
for op in operations:
    try:
        await manage_docs(**op)
    except Exception as e:
        print(f"Failed: {op}, Error: {e}")

# Solution 2: Order operations correctly
# Put structural changes (normalize_headers) before content changes
operations = [
    {"action": "normalize_headers", "doc": "architecture"},
    {"action": "replace_section", "doc": "architecture", ...},
    {"action": "generate_toc", "doc": "architecture"}
]

# Solution 3: Use smaller batches
# Break one large batch into multiple smaller ones
```

## Prevention Best Practices

### Before Starting Work

```python
# 1. Verify project context
await get_project()

# 2. Verify documents exist
await list_projects()

# 3. Check document health
await scribe_doctor()
```

### During Development

```python
# 1. Use list_sections before editing
sections = await manage_docs(action="list_sections", doc="architecture")

# 2. Test with dry_run first
await manage_docs(action="...", doc="...", dry_run=True)

# 3. Verify after each major edit
await read_file(path="...")
```

### After Errors

```python
# 1. Check progress log
await read_recent(n=10)

# 2. Read error message carefully - they're actionable

# 3. Use scribe_doctor for system health
await scribe_doctor()
```

## Getting Help

### Information to Gather

When reporting issues, include:

1. **Error message** (full text)
2. **Operation attempted** (action, doc, parameters)
3. **Project context** (`await get_project()`)
4. **System health** (`await scribe_doctor()`)
5. **Recent log entries** (`await read_recent(n=10)`)
6. **File state** (`await read_file(path="...", mode="scan_only")`)

### Common Diagnostic Commands

```python
# Full diagnostic suite
await scribe_doctor()
await get_project()
await list_projects()
await read_recent(n=10)
await manage_docs(action="list_sections", doc="architecture")
```

### Self-Service Debugging

```python
# 1. Isolate the issue
# Try the simplest operation first
await manage_docs(action="list_sections", doc="architecture")

# 2. Verify prerequisites
# Check file exists, project set, database accessible

# 3. Review documentation
# docs/Scribe_Usage.md - Full reference
# docs/guides/manage_docs_agent_guide.md - Quick patterns

# 4. Check error message suggestions
# Error messages include specific solutions
```

## Summary

### Quick Fixes for Common Issues

| Issue | Quick Fix |
|-------|-----------|
| DOC_NOT_FOUND | `await generate_doc_templates(project_name="<project>")` |
| Section not found | `await manage_docs(action="list_sections", doc="<doc>")` |
| Auto-register fails | Verify file exists, check database connectivity |
| Changes not appearing | Disable dry_run, verify document key |
| Database errors | Run `await scribe_doctor()`, check permissions |
| Performance issues | Reduce scope, use targeted operations |

### When All Else Fails

```python
# Nuclear option: Regenerate project scaffolding
await set_project(name="<project>")
await generate_doc_templates(project_name="<project>", overwrite=True)
# WARNING: This overwrites existing documents!
```

### Key Principles

1. **Read error messages** - They contain specific solutions
2. **Use diagnostic tools** - `scribe_doctor()`, `list_sections()`, `read_file()`
3. **Start simple** - Isolate issues with minimal operations
4. **Check prerequisites** - Project set, file exists, database accessible
5. **Log everything** - Use `append_entry` to track your work
