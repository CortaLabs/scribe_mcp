# Core Walkthrough

Mission: launch Pocket Mission Control in under ten minutes using the smallest useful Scribe loop.

## Phase 1: Bind Mission Context

```bash
set_project(agent="scribe-doc-writer", name="hello_world_scribe_20260418", root="/path/to/repo")
read_recent(agent="scribe-doc-writer", limit=20)
```

Expected outcome:
- mission context is active
- recent log gives immediate continuity

`read_recent` is the primary history surface in core mode.

## Phase 2: Record First Mission Update

```bash
append_entry(
  agent="scribe-doc-writer",
  status="info",
  message="Pocket Mission Control launched; first core check complete."
)
```

Expected outcome:
- one visible progress entry in project history
- clear proof that logging pipeline is active

Compatibility note:
- `append_event` exists, but treat it as compatibility/support behavior for this moment, not a separate primary lane.

## Phase 3: Make One Governed Doc Move

```bash
manage_docs(
  agent="scribe-doc-writer",
  action="create",
  doc_name="MISSION_NOTES",
  content="# Mission Notes\n\n## Findings\nPlaceholder.\n",
  metadata={
    "doc_type":"research",
    "research_goal":"Capture first-run observations for Pocket Mission Control."
  }
)
manage_docs(
  agent="scribe-doc-writer",
  action="replace_section",
  doc_name="MISSION_NOTES",
  section="findings",
  content="Pocket Mission Control core run completed with project context bound and first update logged."
)
```

Expected outcome:
- one managed document exists
- lifecycle metadata is preserved by tool contract

## Phase 4: Confirm Active Project Snapshot

```bash
get_project(agent="scribe-doc-writer")
```

Expected outcome:
- confirms bound project and current scope

## Core Exit Criteria

1. Bound project context exists.
2. `read_recent` used as primary history view.
3. One mission log entry appended.
4. One managed-doc action completed.
5. No admin/destructive surfaces used.
