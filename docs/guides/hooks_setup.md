# Scribe Hooks Setup Guide

Scribe ships a Claude Code hook that **blocks direct Write/Edit operations** on managed documentation paths (`.scribe/docs/dev_plans/`). This forces all agents to use `manage_docs()` instead of bypassing the managed document system.

---

## Why This Exists

Managed docs (architecture guides, phase plans, checklists, research docs) have YAML frontmatter, section IDs, and versioning metadata. When agents use `Write` or `Edit` directly on these files, they corrupt metadata, lose section tracking, and break the audit trail.

The hook enforces at the **tool level** — agents cannot bypass it regardless of what their prompts say.

---

## What Gets Blocked

Any `Write` or `Edit` tool call where `file_path` contains `.scribe/docs/dev_plans/`.

**Blocked:**
- `Write(file_path=".scribe/docs/dev_plans/my_project/research/RESEARCH_TOPIC.md", ...)`
- `Edit(file_path="/full/path/.scribe/docs/dev_plans/my_project/ARCHITECTURE_GUIDE.md", ...)`

**Allowed:**
- `Write(file_path="src/app.py", ...)` — not a managed doc path
- `manage_docs(action="create", ...)` — correct tool for managed docs
- `manage_docs(action="replace_section", ...)` — correct tool for edits

---

## Installation

### Step 1: Install the hook script

Copy the hook script to your global Claude hooks directory:

```bash
mkdir -p ~/.claude/hooks
cp .claude/hooks/protect-managed-docs.sh ~/.claude/hooks/protect-managed-docs.sh
chmod +x ~/.claude/hooks/protect-managed-docs.sh
```

If you're setting up a project that doesn't have the Scribe repo cloned, create the script manually:

```bash
mkdir -p ~/.claude/hooks
cat > ~/.claude/hooks/protect-managed-docs.sh << 'SCRIPT'
#!/bin/bash
# Scribe Managed Docs Protection Hook
# Blocks Write/Edit on .scribe/docs/dev_plans/ paths.
# Exit 0 = allow, Exit 2 = block (stderr shown to agent)

set -euo pipefail

hook_input=$(cat)

file_path=$(echo "$hook_input" | jq -r '.tool_input.file_path // .tool_input.filePath // ""')
tool_name=$(echo "$hook_input" | jq -r '.tool_name // ""')

if [[ -z "$file_path" ]]; then
    exit 0
fi

if [[ "$file_path" != /* ]]; then
    cwd=$(echo "$hook_input" | jq -r '.cwd // ""')
    if [[ -n "$cwd" ]]; then
        file_path="$cwd/$file_path"
    fi
fi

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
SCRIPT
chmod +x ~/.claude/hooks/protect-managed-docs.sh
```

### Step 2: Add the hook to your project settings

Add this to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$HOME/.claude/hooks/protect-managed-docs.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

If you already have a `settings.json`, merge the `hooks` key into it.

### Step 3: Reboot Claude Code

Hooks are loaded on session start. Restart Claude Code for the hook to take effect.

### Step 4: Verify

Ask Claude to write a test file in the protected path:

```
Write a file at .scribe/docs/dev_plans/test.md with content "test"
```

You should see the block message. Then verify normal writes still work:

```
Write a file at /tmp/scribe-hook-test.md with content "test"
```

---

## Requirements

- `jq` must be installed (`sudo apt install jq` or `brew install jq`)
- Bash shell available at `/bin/bash`
- Claude Code with hooks support

---

## Troubleshooting

**Hook not firing:** Restart Claude Code. Hooks load at session start.

**`jq: command not found`:** Install jq. The hook parses JSON input from Claude Code.

**Legitimate Write needed:** If you genuinely need to bypass the hook (e.g., fixing a corrupted file), temporarily remove the hook from settings.json, restart, make the fix, then re-add.

---

## For Other Projects Using Scribe

Any project that uses Scribe MCP should install this hook. The two things you need:

1. **The script** at `~/.claude/hooks/protect-managed-docs.sh` (install once, works for all projects)
2. **The settings.json hook block** in each project's `.claude/settings.json`

Once the global script is installed, each new project only needs the settings.json entry.
