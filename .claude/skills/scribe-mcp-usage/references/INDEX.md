---
id: read_file_search_audit-index
title: Skill Index (How to Search Fast)
doc_name: INDEX
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
# Skill Index (How to Search Fast)

Use `read_file(mode="search")` against skill reference docs. Default `search_mode` is `regex`.

Common searches:
```python
# Doc registration (create/register/auto-register)
read_file(path="references/Scribe_Usage.md", mode="search", query=r"register_doc|register_existing|auto-registration|DOC_NOT_FOUND", context_lines=2)

# manage_docs actions and required params
read_file(path="references/Scribe_Usage.md", mode="search", query=r"### `manage_docs`|#### `create_doc`|#### `apply_patch`|#### `status_update`", context_lines=2)

# doc_name vs doc_category semantics
read_file(path="references/Scribe_Usage.md", mode="search", query=r"doc_name|doc_category", context_lines=2)

# read_file scope rules
read_file(path="references/Scribe_Usage.md", mode="search", query=r"allow_outside_repo|denylist|\\.codex/skills|\\.claude/skills", context_lines=2)

# search tool (multi-file grep replacement)
read_file(path="references/search.md", mode="search", query=r"output_mode|glob|type", context_lines=2)

# edit_file tool (safe file editing)
read_file(path="references/edit_file.md", mode="search", query=r"dry_run|read_before|old_string", context_lines=2)

# tight search within a single top-level section (generated section pack)
read_file(path="references/sections/INDEX.md", mode="search", query=r"Document Editing|Documentation Management|read_file|manage_docs", context_lines=1)
```

## Reference Files

| File | Topic |
|------|-------|
| `quickstart.md` | Minimal correct workflow |
| `Operational_Contract.md` | Full rules and tool signatures |
| `Scribe_Usage.md` | Canonical tool usage and examples |
| `manage_docs.md` | manage_docs details |
| `read_file.md` | read_file modes, scope, dependencies |
| `search.md` | Multi-file codebase search |
| `edit_file.md` | Safe file editing |
| `files.md` | File operations overview (read/search/edit) |
| `logging.md` | Logging discipline |
| `modes.md` | Project vs sentinel mode |
| `doc_naming.md` | doc_name vs doc_category |
| `sentinel_cases.md` | Sentinel mode examples |
