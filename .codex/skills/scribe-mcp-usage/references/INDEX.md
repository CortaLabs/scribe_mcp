# Skill Index (How to Search Fast)

Use `read_file(mode="search")` against skill reference docs. Default `search_mode` is `regex`.

## Core Scribe Searches

```python
# Doc registration (create/register/auto-register)
read_file(path="references/Scribe_Usage.md", mode="search", query=r"register_doc|register_existing|auto-registration|DOC_NOT_FOUND", context_lines=2)

# manage_docs actions and required params
read_file(path="references/Scribe_Usage.md", mode="search", query=r"### `manage_docs`|#### `create_doc`|#### `apply_patch`|#### `status_update`", context_lines=2)

# doc_name vs doc_category semantics
read_file(path="references/Scribe_Usage.md", mode="search", query=r"doc_name|doc_category", context_lines=2)

# read_file scope rules
read_file(path="references/Scribe_Usage.md", mode="search", query=r"allow_outside_repo|denylist|\\.codex/skills|\\.claude/skills", context_lines=2)

# tight search within a single top-level section (generated section pack)
read_file(path="references/sections/INDEX.md", mode="search", query=r"Document Editing|Documentation Management|read_file|manage_docs", context_lines=1)
```

## Bridge System Searches

```python
# Bridge manifest fields
read_file(path="references/bridges/manifest.md", mode="search", query=r"bridge_id|permissions|hooks|project_config", context_lines=2)

# BridgePlugin API
read_file(path="references/bridges/plugin.md", mode="search", query=r"on_activate|on_deactivate|health_check|pre_append", context_lines=2)

# Hook lifecycle
read_file(path="references/bridges/hooks.md", mode="search", query=r"execute_pre_append|execute_post_append|BridgeHookManager", context_lines=2)

# Permission types
read_file(path="references/bridges/permissions.md", mode="search", query=r"read:|write:|create:|can_modify_project", context_lines=2)

# Tool wrapping
read_file(path="references/bridges/tools.md", mode="search", query=r"BridgeToolWrapper|register_custom_tool|BridgeToolRegistry", context_lines=2)

# Bridge quickstart
read_file(path="references/bridges/quickstart.md", mode="search", query=r"register_bridge|activate_bridge|create_project", context_lines=2)
```

## Quick Reference by Topic

| Topic | Reference File | Search Pattern |
|-------|---------------|----------------|
| manage_docs actions | `Scribe_Usage.md` | `manage_docs\|create_doc\|apply_patch` |
| read_file modes | `read_file.md` | `mode=\|scan_only\|chunk\|search` |
| Project setup | `quickstart.md` | `set_project\|read_recent` |
| Bridge manifest | `bridges/manifest.md` | `bridge_id\|permissions\|hooks` |
| Bridge plugin | `bridges/plugin.md` | `on_activate\|health_check` |
| Bridge hooks | `bridges/hooks.md` | `pre_append\|post_append` |
| Bridge permissions | `bridges/permissions.md` | `can_modify\|can_append` |
