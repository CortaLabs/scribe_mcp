# manage_docs Usage Guide for AI Agents

Quick reference for AI agents using `manage_docs` in the Scribe MCP system.

## Auto-Registration (v2.2.0+)

**You don't need to worry about registration for EDIT operations.**

```python
# Just call manage_docs directly:
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="Updated content..."
)
# Auto-registration happens automatically if needed
```

The system will:
1. Check if "architecture" is registered
2. If not, auto-register it (file must exist)
3. Proceed with your edit operation
4. Log the auto-registration event

## Action Categories

### EDIT Actions (Auto-Register)

These actions automatically register unregistered documents before performing the operation:

| Action | Description | Use Case |
|--------|-------------|----------|
| `list_sections` | List all section anchors | Find valid section IDs before editing |
| `replace_section` | Replace content by section anchor | Update specific architecture sections |
| `apply_patch` | Apply structured/unified diffs | Precision edits with compiler-generated patches |
| `replace_range` | Replace explicit line ranges | Direct line-based editing |
| `append` | Append content to document/section | Add new content to existing docs |
| `status_update` | Update checklist item status | Mark tasks done with proof links |
| `normalize_headers` | Normalize headers to ATX format | Clean up markdown formatting |
| `generate_toc` | Generate table of contents | Auto-generate doc navigation |
| `search` | Semantic search across documents | Find related content |
| `replace_text` | Replace text patterns | Global text replacements |
| `validate_crosslinks` | Validate cross-references | Check document link integrity |

### CREATE Actions (Explicit Registration)

These actions handle document creation and registration internally:

| Action | Description | Use Case |
|--------|-------------|----------|
| `create_research_doc` | Create structured research documents | Document investigation findings |
| `create_bug_report` | Create structured bug reports | Track bugs with automatic indexing |
| `create_review_report` | Create review reports | Document code review outcomes |
| `create_agent_report_card` | Create agent performance reports | Track agent quality scores |
| `create_doc` | Create custom documents | Generate custom doc types |

## Common Patterns

### Pattern 1: Edit Existing Document

**Scenario:** Update architecture section after investigation

```python
# No pre-registration needed - just edit
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",
    content="## Problem Statement\n\n**Updated findings:** ..."
)
```

### Pattern 2: Create New Research Doc

**Scenario:** Document research findings

```python
await manage_docs(
    action="create_research_doc",
    doc="research",  # REQUIRED - always use "research"
    doc_name="RESEARCH_CONTEXT_HYDRATION_20260106",  # REQUIRED
    metadata={
        "research_goal": "Design context hydration for tools",
        "confidence_areas": ["tool_behavior", "output_formats"],
        "priority": "high"
    }
)
```

### Pattern 3: Multiple Sequential Edits

**Scenario:** Update multiple sections in one document

```python
# First edit auto-registers (if needed)
await manage_docs(
    action="append",
    doc="phase_plan",
    content="## Phase 6: Performance Optimization\n..."
)

# Subsequent edits use existing registration
await manage_docs(
    action="normalize_headers",
    doc="phase_plan"
)

await manage_docs(
    action="generate_toc",
    doc="phase_plan"
)
```

### Pattern 4: Checklist Updates

**Scenario:** Mark checklist items complete with proof

```python
await manage_docs(
    action="status_update",
    doc="checklist",
    section="phase_4_implementation",
    metadata={
        "status": "done",
        "proof": "PROGRESS_LOG#2026-01-06"
    }
)
```

### Pattern 5: Find Valid Sections

**Scenario:** Discover available section anchors before editing

```python
# List all sections first
result = await manage_docs(
    action="list_sections",
    doc="architecture"
)
# Returns: {"sections": [{"id": "problem_statement", "line": 42, ...}, ...]}

# Then edit specific section
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="problem_statement",  # Use ID from list_sections
    content="..."
)
```

### Pattern 6: Batch Operations

**Scenario:** Perform multiple edits atomically

```python
await manage_docs(
    action="batch",
    doc="architecture",
    metadata={
        "operations": [
            {
                "action": "append",
                "doc": "architecture",
                "section": "requirements_constraints",
                "content": "Added performance requirements",
                "metadata": {"position": "after"}
            },
            {
                "action": "status_update",
                "doc": "checklist",
                "section": "documentation_complete",
                "metadata": {"status": "done", "proof": "all_docs_updated"}
            }
        ]
    }
)
```

## Error Handling

### Common Errors and Solutions

**Error: `DOC_NOT_FOUND: Document 'X' not registered`**

*Cause:* Auto-registration failed or action is not an EDIT operation.

*Solution:*
```python
# 1. Verify you're using an EDIT action (see table above)
# 2. Check file exists:
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")
# 3. Manual registration fallback:
await generate_doc_templates(project_name="<project>")
```

**Error: `Cannot auto-register: file does not exist`**

*Cause:* Document file missing from disk.

*Solution:*
```python
# Create file first using generate_doc_templates
await generate_doc_templates(project_name="<project>")
# OR use CREATE action for new custom docs
await manage_docs(action="create_doc", ...)
```

**Error: `STRUCTURED_EDIT_ANCHOR_NOT_FOUND`**

*Cause:* Section anchor doesn't exist in document.

*Solution:*
```python
# List valid sections first
sections = await manage_docs(action="list_sections", doc="architecture")
# Use an existing section ID from the list
```

**Error: `STRUCTURED_EDIT_ANCHOR_AMBIGUOUS`**

*Cause:* Multiple lines match the anchor text.

*Solution:*
```python
# Use more specific anchor text or switch to replace_range
await manage_docs(
    action="replace_range",
    doc="architecture",
    start_line=42,
    end_line=45,
    content="..."
)
```

## Best Practices

### For All Agents

1. **Use EDIT actions for existing docs** - Auto-registration handles the rest
2. **Use CREATE actions for new docs** - They handle registration internally
3. **Check error messages** - They provide actionable guidance
4. **Log your work** - Use `append_entry` after significant edits
5. **Verify changes** - Use `read_file` to confirm edits succeeded

### For Research Agents

```python
# Always use create_research_doc for new research
await manage_docs(
    action="create_research_doc",
    doc="research",
    doc_name="RESEARCH_<TOPIC>_<YYYYMMDD>",
    metadata={
        "research_goal": "...",
        "confidence_areas": ["area1", "area2"]
    }
)
```

### For Architect Agents

```python
# Use replace_section for architecture updates
await manage_docs(
    action="replace_section",
    doc="architecture",
    section="system_overview",
    content="## System Overview\n..."
)

# Update checklist after architecture changes
await manage_docs(
    action="status_update",
    doc="checklist",
    section="architecture_complete",
    metadata={"status": "done", "proof": "architecture_updated"}
)
```

### For Coder Agents

```python
# Append implementation notes to phase plan
await manage_docs(
    action="append",
    doc="phase_plan",
    content="## Implementation Notes\n- Completed Phase 4\n- All tests passing"
)

# Create bug reports when issues found
await manage_docs(
    action="create_bug_report",
    metadata={
        "category": "logic",
        "slug": "off_by_one_error",
        "severity": "medium",
        "title": "Off-by-one error in pagination",
        "component": "query_entries"
    }
)
```

### For Review Agents

```python
# Create review reports
await manage_docs(
    action="create_review_report",
    metadata={
        "review_type": "pre_implementation",
        "overall_grade": 95,
        "recommendations": [...]
    }
)

# Validate document cross-references
await manage_docs(
    action="validate_crosslinks",
    doc="architecture",
    metadata={"check_anchors": true}
)
```

## Quick Reference

### Most Common Operations

```python
# Update architecture section
manage_docs(action="replace_section", doc="architecture", section="<id>", content="...")

# Mark checklist item done
manage_docs(action="status_update", doc="checklist", section="<id>", metadata={"status": "done", "proof": "..."})

# Create research doc
manage_docs(action="create_research_doc", doc="research", doc_name="RESEARCH_<TOPIC>_<DATE>", metadata={...})

# Create bug report
manage_docs(action="create_bug_report", metadata={"category": "...", "slug": "...", "severity": "...", ...})

# Append to document
manage_docs(action="append", doc="phase_plan", content="...")

# List available sections
manage_docs(action="list_sections", doc="architecture")
```

### Debugging Workflow

```python
# 1. Check current project context
await get_project()

# 2. List available sections
await manage_docs(action="list_sections", doc="architecture")

# 3. Read current content
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")

# 4. Make edit
await manage_docs(action="replace_section", doc="architecture", ...)

# 5. Verify change
await read_file(path=".scribe/docs/dev_plans/<project>/ARCHITECTURE_GUIDE.md")

# 6. Log the work
await append_entry(message="Updated architecture", agent="YourAgent", meta={"doc": "architecture"})
```

## Summary

**Key Takeaways:**
- Auto-registration is automatic for EDIT operations (no pre-work needed)
- CREATE operations handle their own registration
- Error messages are actionable - read them carefully
- Always log your work with `append_entry`
- Use `list_sections` to discover valid anchors before editing

**Common Mistakes to Avoid:**
- Don't manually call `generate_doc_templates` before every edit
- Don't ignore error messages - they tell you exactly what to fix
- Don't forget to log significant changes
- Don't use CREATE actions when you mean to edit existing docs

**When in Doubt:**
1. Check if file exists with `read_file`
2. Use `list_sections` to see valid anchors
3. Read error messages carefully
4. Consult `docs/Scribe_Usage.md` for full details
