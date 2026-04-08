# Scribe MCP Handoff: Codex Approval Alignment

Last updated: 2026-03-30 UTC

## Why This Exists

`scribe_mcp` is being used from Codex clients that now apply a separate host-side safety reviewer to MCP tool calls with side effects.

The immediate symptom is approval prompts on normal Scribe operations such as `set_project`, even when the surrounding Codex config explicitly allowlists the tool.

This handoff documents what Scribe needs in order to present a cleaner trust surface to Codex-class hosts.

## Verified Findings

### 1. Scribe currently exports 22 MCP tools

Tool count by module:

- `sentinel_tools.py`: 4
- `reminder_tools.py`: 3
- 15 single-tool modules

Daily-use tools include:

- `set_project`
- `append_entry`
- `read_file`
- `read_recent`
- `query_entries`
- `search`
- `list_projects`
- `get_project`

### 2. Tool descriptions and schemas exist, but annotations do not

The server builds `mcp.types.Tool(...)` objects manually in:

- [server.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/server.py:430)

Current behavior in the custom `_tool_decorator`:

- accepts `name`, `description`, `input_schema`, and `output_schema`
- stores the tool in `Server._scribe_tool_defs`
- returns `mcp_types.Tool(name=..., description=..., inputSchema=..., outputSchema=...)`

What is missing from the emitted `Tool` definitions:

- `annotations`
- `meta`
- `icons`
- `execution`

So today Scribe has no first-class path to expose:

- `readOnlyHint`
- `destructiveHint`
- `idempotentHint`
- `openWorldHint`
- task/execution metadata for long-running tools

### 3. This is a server-layer gap, not just a per-tool authoring omission

Scribe is not on `FastMCP`. It uses `mcp.server.Server` and a custom compatibility layer in `server.py`.

That means adding annotations is not just a matter of changing:

```python
@app.tool()
```

to:

```python
@app.tool(annotations=...)
```

The custom decorator itself must first be extended to accept and persist those fields into `mcp_types.Tool(...)`.

### 4. One tool is also missing a docstring

Audit result:

- 22 tools total
- 21 with docstrings
- `read_file` is the only tool currently missing a tool-level docstring

This is minor compared to the annotations gap, but it is still worth fixing because the current server uses function docstrings when an explicit description is not supplied.

## Why Codex Still Prompts

Codex appears to reason across at least three layers:

1. local instructions and prompts
2. Codex runtime approval and safety review
3. MCP tool metadata and config

Scribe can only directly influence layer 3.

Right now, side-effecting tools like `set_project` are legible as "tools with input schema and descriptions," but not as "closed-world local state tools that are non-destructive."

That leaves Codex to infer more than it should.

## Required Work In Scribe

### Phase 1: Extend the custom tool decorator

Update the custom `_tool_decorator` in [server.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/server.py:430) so it can accept and emit:

- `title`
- `annotations`
- `icons`
- `meta`
- `execution`

Target contract should mirror the available fields on `mcp.types.Tool`.

### Phase 2: Classify the existing 22 tools

At minimum, assign a risk class to every tool:

- read-only local
- additive local write
- stateful local write
- destructive/admin
- open-world or externally connected

### Phase 3: Add annotations to the daily-safe set first

Suggested first batch:

- `read_file`
- `read_recent`
- `query_entries`
- `search`
- `get_project`
- `list_projects`
- `set_project`
- `append_entry`
- `append_event`
- `link_fix`
- `open_bug`
- `open_security`

Suggested classification:

- read-only tools:
  - `readOnlyHint = true`
  - `openWorldHint = false`
- additive or stateful local tools:
  - `readOnlyHint = false`
  - `destructiveHint = false`
  - `openWorldHint = false`
- destructive tools such as `delete_project`:
  - `destructiveHint = true`

Do not mark tools idempotent unless repeated identical calls truly have no additional effect.

### Phase 4: Add tests for tool metadata, not just execution

Add tests that verify `list_tools()` returns the expected metadata for representative tools:

- one read-only tool
- one additive local write tool
- one stateful local write tool
- one destructive tool

## Suggested Implementation Shape

### Decorator signature

Extend `_tool_decorator(...)` to accept optional fields such as:

- `title: str | None = None`
- `annotations: mcp_types.ToolAnnotations | None = None`
- `icons: list[mcp_types.Icon] | None = None`
- `meta: dict[str, Any] | None = None`
- `execution: mcp_types.ToolExecution | None = None`

Then persist them when building `mcp_types.Tool(...)`.

### Example target usage

Representative target shape after server support exists:

```python
@app.tool(
    title="Set Scribe Project",
    annotations=mcp_types.ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def set_project(...):
    ...
```

## Recommended Acceptance Criteria

- `server.py` custom decorator accepts and persists tool metadata fields beyond name/description/schema
- `list_tools()` includes annotations for classified tools
- `delete_project` is explicitly marked destructive
- read-only daily-use tools are explicitly marked read-only and closed-world
- `read_file` has a proper tool docstring or explicit description
- representative metadata tests pass

## Files To Touch

Primary:

- [server.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/server.py)

Likely next:

- [set_project.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/set_project.py)
- [append_entry.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/append_entry.py)
- [sentinel_tools.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/sentinel_tools.py)
- [read_file.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/read_file.py)
- [query_entries.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/query_entries.py)
- [read_recent.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/read_recent.py)
- [search.py](/home/austin/projects/MCP_SPINE/scribe_mcp/src/scribe_mcp/tools/search.py)

## Notes

- This handoff is about Codex compatibility, not generic MCP correctness alone.
- Annotations will help, but they will not guarantee that Codex never prompts.
- The immediate missing piece in Scribe is the ability to emit annotations at all.
