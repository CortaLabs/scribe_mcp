---
name: scribe-mcp-usage
description: Operate the local Scribe MCP tools for logging, project setup, manage_docs workflows, read_file usage, bridge integrations, and sentinel/project mode discipline. Use whenever you need to follow Scribe tool contracts, document management rules, or bridge development.
---

# Scribe MCP Usage

## Navigation (progressive disclosure)
Start here, then open only what you need:

### Core Workflow
- `references/quickstart.md` — minimal correct workflow for any session.
- `references/INDEX.md` — how to search fast across references.
- `references/Operational_Contract.md` — full rules, tool signatures, manage_docs schemas.
- `references/Scribe_Usage.md` — canonical tool usage and examples.

### Tools
- `references/manage_docs.md` — manage_docs details and examples.
- `references/read_file.md` — read_file modes, scope rules, and examples.
- `references/logging.md` — logging discipline and reasoning block.

### Modes & Rules
- `references/modes.md` — project vs sentinel mode rules.
- `references/doc_naming.md` — doc_name vs doc_category rules.

### Bridge System (External MCP Integration)
- `references/bridges/INDEX.md` — bridge system overview and navigation.
- `references/bridges/quickstart.md` — get a bridge running in 5 minutes.
- `references/bridges/manifest.md` — YAML manifest schema reference.
- `references/bridges/plugin.md` — BridgePlugin API reference.
- `references/bridges/hooks.md` — hook lifecycle and execution.
- `references/bridges/permissions.md` — permission system and access control.
- `references/bridges/tools.md` — tool wrapping and custom tools.
- `references/bridges/admin_cli.md` — admin CLI commands.

### Templates
- `assets/templates/` — managed doc templates (research/bug/review/agent card/logs).
- `assets/templates/bridge/` — bridge manifest and plugin templates.

## Non-negotiables (short)
- Use MCP tools directly; no manual substitutes.
- Log after meaningful actions with a reasoning block.
- Use `read_file` for file contents; avoid shell reads.
- Bridges must implement `on_activate()`, `on_deactivate()`, `health_check()`.
