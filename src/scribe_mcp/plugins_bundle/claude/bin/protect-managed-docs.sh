#!/bin/bash
# ============================================================
# Scribe Managed Docs Protection Hook
# ============================================================
# Blocks Write and Edit tool calls targeting .scribe/docs/dev_plans/
# Forces all managed doc changes through manage_docs MCP tool.
#
# Exit codes:
#   0 = allow tool call
#   2 = block tool call (stderr shown to agent)
#
# Install: Add PreToolUse hook in .claude/settings.json
# ============================================================

set -euo pipefail

hook_input=$(cat)

file_path=$(echo "$hook_input" | jq -r '.tool_input.file_path // .tool_input.filePath // ""')
tool_name=$(echo "$hook_input" | jq -r '.tool_name // ""')

# No file path = not a file operation, allow
if [[ -z "$file_path" ]]; then
    exit 0
fi

# Normalize: resolve relative paths against cwd
if [[ "$file_path" != /* ]]; then
    cwd=$(echo "$hook_input" | jq -r '.cwd // ""')
    if [[ -n "$cwd" ]]; then
        file_path="$cwd/$file_path"
    fi
fi

# Check if path is inside .scribe/docs/dev_plans/
if [[ "$file_path" == *".scribe/docs/dev_plans/"* ]]; then
    cat >&2 <<EOF
BLOCKED: $tool_name on managed documentation path.

  Path: $file_path

Managed docs under .scribe/docs/dev_plans/ MUST be modified through Scribe tools:

  manage_docs(action="create", ...)           - Create new docs (research, bug, custom)
  manage_docs(action="replace_section", ...)   - Update a section by ID
  manage_docs(action="replace_range", ...)     - Update by line range
  manage_docs(action="apply_patch", ...)       - Precision edits
  manage_docs(action="status_update", ...)     - Update checklist items
  append_entry(...)                            - Log progress

Direct Write/Edit is FORBIDDEN. This is tool-enforced, not optional.
EOF
    exit 2
fi

exit 0
