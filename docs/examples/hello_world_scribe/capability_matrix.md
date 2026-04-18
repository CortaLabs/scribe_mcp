# Capability Matrix

This matrix maps the full registered feature surface to story treatment lanes.

## Lane Definitions

- Core: first-run launch flow.
- Advanced: expansion + ops + incident coverage.
- Appendix/Admin: support or destructive surfaces intentionally outside the opening story.

## Tool Mapping

| Tool | Lane | Treatment | Notes |
|---|---|---|---|
| `set_project` | Core | Primary | Required startup bind |
| `read_recent` | Core | Primary | Primary history surface |
| `append_entry` | Core | Primary | Main logging action |
| `append_event` | Appendix/Admin | Compatibility note | Alias/support path; not a main lane |
| `manage_docs` | Core | Primary | Governed docs action |
| `get_project` | Core | Primary | Context verification |
| `list_projects` | Advanced | Direct demo | Discovery expansion |
| `read_file` | Advanced | Direct demo | Non-destructive repo inspection |
| `search` | Advanced | Direct demo | Cross-file discovery |
| `query_entries` | Advanced | Direct demo | Filtered/advanced history query |
| `query_reminders` | Advanced | Direct demo | Reminder observation |
| `scribe_doctor` | Advanced | Direct demo | Runtime diagnostics |
| `open_bug` | Advanced | Direct demo | Incident lane: bug |
| `open_security` | Advanced | Direct demo | Incident lane: security |
| `link_fix` | Advanced | Direct demo | Case-to-fix evidence chain |
| `configure_reminders` | Appendix/Admin | Referenced only | Policy mutation kept out of core |
| `reset_reminders` | Appendix/Admin | Referenced only | Reset operation kept out of core |
| `list_open_cases` | Appendix/Admin | Referenced only | Case admin/support listing |
| `generate_doc_templates` | Appendix/Admin | Referenced only | Scaffolding/support utility |
| `authorize_repo_root` | Appendix/Admin | Referenced only | Authorization support surface |
| `rotate_log` | Appendix/Admin | Referenced only | Log maintenance surface |
| `delete_project` | Appendix/Admin | Referenced only | Destructive admin operation |
| `edit_file` | Appendix/Admin | Referenced only | Requires read-before-edit contract |

## Coverage Check

- Core lane emphasizes safe first value.
- Advanced lane demonstrates discovery, operations, and incident handling.
- Appendix/admin lane captures all remaining registered surfaces explicitly.
- No registered tool remains unmapped.
