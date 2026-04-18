# Discovery And Search

Pocket Mission Control now shifts from launch mode to discovery mode.

## Step 1: See Available Project Contexts

```bash
list_projects(agent="scribe-doc-writer")
```

Use this to find mission workspaces without changing anything.

## Step 2: Inspect Repo Artifacts Safely

```bash
read_file(agent="scribe-doc-writer", path="README.md", mode="scan_only")
search(agent="scribe-doc-writer", pattern="set_project", path="src", glob="**/*.py")
```

Use inspection tools to understand structure and call paths before mutations.

## Step 3: Use Advanced History Search

```bash
query_entries(
  agent="scribe-doc-writer",
  project="hello_world_scribe_20260418",
  message="mission",
  message_mode="substring",
  limit=20
)
```

`query_entries` is the advanced, filterable history surface.

## `read_recent` vs `query_entries`

- `read_recent`: primary startup timeline and quick continuity.
- `query_entries`: deeper filtered retrieval by message/status/time/metadata.

This split keeps core usage simple while still exposing full search power later.
