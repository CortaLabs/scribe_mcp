# Research Report: MCP Tool Output Rendering Issue

**Project:** scribe_tool_output_refinement
**Date:** 2026-01-03
**Author:** Orchestrator + User Research
**Status:** VERIFIED (Web Search Backed)

---

## Executive Summary

Claude Code has an **undocumented breaking change** (Issue #9962) that causes MCP tool responses to display as escaped JSON instead of rendered text. This directly impacts our goal of making Scribe's `read_file` output more readable than Claude's native `Read()` tool.

**Root Cause:** Claude Code prioritizes `structuredContent` over `TextContent` when both are present, displaying JSON with escaped `\n` instead of rendered newlines.

**Solution:** Return `CallToolResult` directly with conditional format selection - default to TextContent-only for clean display, offer structured mode when explicitly requested.

---

## Problem Statement

### Observed Behavior

| Aspect | Claude Native Read | Scribe read_file (MCP) |
|--------|-------------------|------------------------|
| Line breaks | Actual newlines render | Shows escaped `\n` |
| Wrapper | None - clean output | JSON `{"ok":true, "content":"..."}` |
| Line numbers | `     1→` | ` 1→` |
| Metadata | None | Header/footer boxes |
| Audit trail | None | Full sha256, provenance |

### Root Cause: Issue #9962

**GitHub Issue:** Claude Code #9962 - MCP TextContent vs structuredContent display priority

Between Claude Code versions `2.0.10` and `2.0.22`, Anthropic made an undocumented change:

| Before (~2.0.9) | After (~2.0.22+) |
|-----------------|------------------|
| `TextContent` displayed cleanly | `structuredContent` prioritized |
| `\n` → actual newlines | `\n` → escaped in JSON display |

**MCP Spec Contradiction:**
> "For backwards compatibility, a tool that returns structured content SHOULD also return the serialized JSON in a TextContent block."

This implies TextContent should be primary for human readability. Claude Code now does the opposite.

---

## Solution Options

### Option 1: Kill Structured Output

```python
@mcp.tool(structured_output=False)
def read_file(path: str, ...) -> str:
    return pretty_formatted_string
```

**Pros:** Forces TextContent only, clean display
**Cons:** Loses structured data for programmatic consumers

### Option 2: Return CallToolResult Directly (RECOMMENDED)

```python
from mcp.types import CallToolResult, TextContent

@mcp.tool()
def read_file(path: str, format: str = "readable", ...) -> CallToolResult:
    pretty = build_pretty_output(...)
    structured = build_structured_output(...)

    if format == "readable":
        # Clean display - NO structuredContent
        return CallToolResult(
            content=[TextContent(type="text", text=pretty)]
        )
    elif format == "structured":
        # Programmatic use
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(structured))],
            structuredContent=structured
        )
    else:  # "both"
        # Future-proof for when bug is fixed
        return CallToolResult(
            content=[TextContent(type="text", text=pretty)],
            structuredContent=structured
        )
```

**Pros:**
- Full control over both formats
- Default to readable for agent experience
- Structured available on demand
- Future-proof for when #9962 is fixed

**Cons:**
- Requires CallToolResult import and manual construction
- Bypasses FastMCP's automatic conversion

### Option 3: Accept JSON, Make Content Beautiful

Keep current approach but optimize the content inside the JSON wrapper.

**Pros:** Simple, works now
**Cons:** Still shows escaped `\n`, JSON noise

---

## Recommended Implementation

### Strategy: Conditional CallToolResult

1. **Default to `format="readable"`** - TextContent only, no structuredContent
2. **Offer `format="structured"`** for programmatic chaining
3. **Support `format="both"`** for future when Claude Code fixes display
4. **Always log to tool_logs** regardless of display format (audit trail)

### Key Code Changes Required

1. **Import MCP types:**
```python
from mcp.types import CallToolResult, TextContent
```

2. **Modify read_file return type:**
```python
def read_file(...) -> CallToolResult:  # Not Dict[str, Any]
```

3. **Conditional return logic:**
```python
if format == "readable":
    return CallToolResult(
        content=[TextContent(type="text", text=pretty_output)]
        # NO structuredContent field
    )
```

### Pretty Output Format (Refined)

Based on Claude's native Read style, recommended format:

```
     1→#!/usr/bin/env python3
     2→"""
     3→Response optimization utilities.
     4→"""
    ...
    40→    "timestamp": "t",

───────────────────────────────────────────────────────────────
path: utils/response.py | lines: 818 | size: 30150
sha256: 2aa1e9e95b3091a8...
```

**Key refinements:**
- Line numbers match Claude style (5-char width, right-aligned)
- Metadata at END, not top (content first)
- Minimal separator (single line, not boxes)
- No JSON wrapper visible to agent

---

## Trade-Off Matrix

| Approach | TextContent Display | Structured Available | Claude Code Shows |
|----------|---------------------|----------------------|-------------------|
| `structured_output=False` | Clean | None | Text properly |
| `CallToolResult` with both | Included | Included | JSON (bug) |
| `CallToolResult` text only | Clean | None | Text properly |
| **Conditional (recommended)** | Clean by default | On demand | Text by default |

---

## Constraints We Cannot Change

1. **MCP Protocol** - Must return valid MCP responses
2. **Claude Code Rendering** - No hooks to modify display behavior
3. **Issue #9962 Status** - Open, no fix announced

## What We CAN Control

1. **Return type** - CallToolResult vs automatic conversion
2. **Fields included** - structuredContent presence triggers JSON display
3. **Default format** - readable vs structured
4. **Output styling** - Line numbers, separators, metadata placement

---

## Action Items

1. [ ] Modify `tools/read_file.py` to return `CallToolResult`
2. [ ] Add conditional logic based on `format` parameter
3. [ ] Update `ResponseFormatter` to build TextContent-compatible strings
4. [ ] Test with Claude Code to verify clean display
5. [ ] Update tests for new return type
6. [ ] Document format parameter in tool docstring

---

## References

- GitHub Issue #9962: Claude Code MCP TextContent display priority
- MCP Protocol Specification: Content types and backwards compatibility
- FastMCP Documentation: structured_output parameter
- Claude Code Changelog: Versions 2.0.10 through 2.0.22

---

## Appendix: Full CallToolResult Example

```python
from mcp.types import CallToolResult, TextContent
import hashlib

@mcp.tool()
def read_file(
    path: str,
    mode: str = "chunk",
    format: str = "readable",  # "readable" | "structured" | "both"
    chunk_index: list = None,
    ...
) -> CallToolResult:
    """Read file with rich formatting and audit trail."""

    # Read and process file
    content, metadata = read_and_process(path, mode, chunk_index)

    # Build pretty output (for readable format)
    pretty = format_readable_output(content, metadata)

    # Build structured output (for programmatic use)
    structured = {
        "ok": True,
        "path": path,
        "mode": mode,
        "content": content,
        "sha256": metadata["sha256"],
        "lines": metadata["lines"],
        "size": metadata["size"],
        "encoding": "utf-8"
    }

    # Always log to tool_logs for audit (regardless of format)
    await log_to_tool_logs(structured)

    # Return based on format preference
    if format == "readable":
        return CallToolResult(
            content=[TextContent(type="text", text=pretty)]
        )
    elif format == "structured":
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(structured, indent=2))],
            structuredContent=structured
        )
    else:  # "both" - future-proof
        return CallToolResult(
            content=[TextContent(type="text", text=pretty)],
            structuredContent=structured
        )
```

---

*Research verified via web search. Issue #9962 confirmed as open on Claude Code GitHub.*
