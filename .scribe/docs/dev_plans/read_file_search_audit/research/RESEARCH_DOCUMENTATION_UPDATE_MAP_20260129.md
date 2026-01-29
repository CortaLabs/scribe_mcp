
# Research: Documentation Update Map for search and edit_file Tools
**Author:** ResearchAgent-DocsAudit
**Version:** v1.0
**Status:** Complete
**Last Updated:** 2026-01-29 04:50 UTC
**Project:** read_file_search_audit

> Maps every document requiring updates to reference the new `search` and `edit_file` MCP tools.

---
## Executive Summary
<!-- ID: executive_summary -->

Two new MCP tools (`search` for multi-file codebase grep, `edit_file` for safe file editing) were implemented and registered in `tools/__init__.py`. However, **zero documentation files** reference these tools. This report maps every file that needs updating, organized by priority.

**Total files requiring updates: 22**
- CRITICAL (agents cannot discover tools): 8
- IMPORTANT (incomplete docs): 10
- NICE-TO-HAVE (minor references): 4

---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-DocsAudit
**Investigation Window:** 2026-01-29
**Focus Areas:**
- [x] Skill files (.claude/skills, .codex/skills)
- [x] CLAUDE.md files (root, scribe_mcp, config)
- [x] Agent definitions (.claude/agents/, docs/claude_code_subagents/)
- [x] Usage documentation (docs/Scribe_Usage.md)
- [x] Codex skill references
- [x] README.md
- [x] Whitepapers and guides
- [x] Tool registration verification

**Verification:** Tools confirmed registered in `tools/__init__.py` (lines 18-19, 37-38).

---
## Findings
<!-- ID: findings -->

### PRIORITY 1: CRITICAL (Agents will not discover tools)

#### 1. `docs/Scribe_Usage.md` — Canonical Tool Reference
- **What:** No `search()` or `edit_file()` tool sections exist. This is THE reference agents use for parameter discovery.
- **Needs:** Full tool documentation sections for both tools (params, examples, edge cases). Pattern: follow existing `read_file` section (line 869+) and `query_entries` section (line 805+).
- **Scope:** ~100 lines per tool (200 total new content)
- **Confidence:** 0.99

#### 2. `CLAUDE.md` (scribe_mcp root) — Orchestrator Reference
- **What:** "Essential Tools Quick Reference" section (line 611+) missing both tools. File Reading Policy (line 148) doesn't mention `search` as grep alternative or `edit_file` as sed alternative.
- **Needs:** Add `search` and `edit_file` entries to tool table. Update file reading/editing policy to reference new tools.
- **Scope:** ~15 lines additions + policy update
- **Confidence:** 0.98

#### 3. `AGENTS.md` — Agent Governance
- **What:** Tool listing (line 254+) mentions `read_file` but not `search` or `edit_file`. File reading policy (line 37) doesn't mention search/edit alternatives.
- **Needs:** Add tools to tool listing. Update read-file policy to include search/edit_file.
- **Scope:** ~10 lines
- **Confidence:** 0.98

#### 4. `.codex/skills/scribe-mcp-usage/SKILL.md` — Codex Skill Entry Point
- **What:** Non-negotiables section says "Use `read_file` for file contents" but doesn't mention `search` or `edit_file`.
- **Needs:** Add references to new tools in non-negotiables and navigation sections.
- **Scope:** ~5 lines
- **Confidence:** 0.98

#### 5. `.codex/skills/scribe-mcp-usage/references/Operational_Contract.md` — Codex Contract
- **What:** Tool list (line 3 description, tool schemas) doesn't include `search` or `edit_file`. File reading rules (line 98) only mention `read_file`.
- **Needs:** Add tool schemas for both tools. Update file reading rules to include `search` for multi-file grep and `edit_file` for editing.
- **Scope:** ~40 lines per tool (80 total)
- **Confidence:** 0.99

#### 6. `.codex/skills/scribe-mcp-usage/references/files.md` — File Access Reference
- **What:** Only documents `read_file`. Needs companion entries for `search` (multi-file) and `edit_file`.
- **Needs:** New sections or new companion files (search.md, edit_file.md) in references/
- **Scope:** ~60 lines per tool (120 total) OR create 2 new files
- **Confidence:** 0.99

#### 7. `.codex/skills/scribe-mcp-usage/references/Scribe_Usage.md` — Codex Usage Copy
- **What:** Mirror of docs/Scribe_Usage.md. Also missing search/edit_file tool sections.
- **Needs:** Same updates as docs/Scribe_Usage.md (keep in sync)
- **Scope:** ~200 lines (mirror)
- **Confidence:** 0.99

#### 8. `config/CLAUDE.md` — Config-specific Agent Reference
- **What:** Tools Architecture listing (lines 280-297) lists all tools but omits `search.py` and `edit_file.py`.
- **Needs:** Add `- search.py - Multi-file codebase search (grep/rg replacement)` and `- edit_file.py - Safe file editing with exact string replacement`
- **Scope:** 2 lines
- **Confidence:** 0.98

### PRIORITY 2: IMPORTANT (Incomplete docs, agents can work around)

#### 9-13. `.claude/agents/` (5 files)
- `scribe-research-analyst.md`
- `scribe-coder.md`
- `scribe-architect.md`
- `scribe-review-agent.md`
- `scribe-bug-hunter.md`
- **What:** All have File Reading Policy saying "use scribe.read_file" and tool tables. None mention `search` (multi-file grep replacement) or `edit_file` (safe editing).
- **Needs:** Update File Reading Policy to add `search` and `edit_file`. Add to tool usage tables.
- **Scope:** ~5 lines each (25 total)
- **Confidence:** 0.95

#### 14-18. `docs/claude_code_subagents/` (5 files, mirrors of .claude/agents/)
- Same 5 agent files as above.
- **What:** These are the upstream source copies. Same gaps.
- **Needs:** Same updates as .claude/agents/ counterparts (keep in sync).
- **Scope:** ~5 lines each (25 total)
- **Confidence:** 0.95

#### 19. `README.md` — Public Documentation
- **What:** Has detailed read_file features section but no sections for search or edit_file.
- **Needs:** New feature sections for both tools.
- **Scope:** ~30 lines per tool (60 total)
- **Confidence:** 0.95

### PRIORITY 3: NICE-TO-HAVE (Minor references, low impact)

#### 20. `docs/whitepapers/scribe_mcp_whitepaper.md`
- **What:** Directory tree (line 135) lists `search.py` but not `edit_file.py`. Tool Suite section (line 386+) describes search.py (line 607) but not edit_file.
- **Needs:** Add edit_file.py to directory tree and tool suite section.
- **Scope:** ~5 lines
- **Confidence:** 0.92

#### 21. `.codex/skills/scribe-mcp-usage/references/INDEX.md` — Codex Reference Index
- **What:** Lists reference files. Will need entries for new search.md and edit_file.md if those are created.
- **Needs:** Add index entries for new reference files.
- **Scope:** 2 lines
- **Confidence:** 0.90

#### 22. `.codex/skills/scribe-mcp-usage/references/quickstart.md` — Codex Quickstart
- **What:** No mention of search or edit_file.
- **Needs:** Add brief mention in tool overview if one exists.
- **Scope:** ~3 lines
- **Confidence:** 0.85

---
## Technical Analysis
<!-- ID: technical_analysis -->

**Tool Registration Status (VERIFIED):**
- `tools/__init__.py` lines 18-19: `from . import search` and `from . import edit_file` present
- `tools/__init__.py` lines 37-38: Both in `__all__` list
- `server.py`: No explicit imports needed (auto-registered via `@app.tool()` decorators)

**Sync Considerations:**
- `.codex/skills/` files are copies of `.claude/skills/` — must stay in sync
- `docs/claude_code_subagents/` files are source copies of `.claude/agents/` — must stay in sync
- `docs/Scribe_Usage.md` and `.codex/.../references/Scribe_Usage.md` must stay in sync

**Risk Assessment:**
- HIGH RISK: Without docs/Scribe_Usage.md updates, agents using `read_file(mode="search", query="search tool")` to discover parameters will find nothing
- MEDIUM RISK: Without CLAUDE.md/AGENTS.md updates, orchestrator won't guide agents to use new tools
- LOW RISK: Whitepaper/README gaps are cosmetic

---
## Recommendations
<!-- ID: recommendations -->

### Immediate Next Steps (Phase 5 of current project)
1. Update `docs/Scribe_Usage.md` with full tool documentation for `search` and `edit_file`
2. Update `CLAUDE.md` Essential Tools section and File Reading Policy
3. Update `AGENTS.md` tool listing and file reading policy
4. Update `config/CLAUDE.md` tools listing
5. Update `.codex/skills/scribe-mcp-usage/references/Operational_Contract.md`
6. Create `.codex/skills/scribe-mcp-usage/references/search.md` and `edit_file.md`
7. Update `.codex/skills/scribe-mcp-usage/SKILL.md`

### Second Pass
8. Update all 10 agent definition files (.claude/agents/ + docs/claude_code_subagents/)
9. Update `README.md`
10. Update `.codex/skills/scribe-mcp-usage/references/files.md`

### Third Pass (Nice-to-have)
11. Update whitepaper directory tree and tool suite section
12. Update codex reference INDEX.md and quickstart.md

### Estimated Total Scope
- ~600 lines of new/modified documentation
- 22 files to touch
- Recommend batching: governance docs first (items 1-7), then agent files (8-10), then minor (11-12)

---
## Appendix
<!-- ID: appendix -->

### Files Verified as NOT Needing Updates
- `tools/__init__.py` — Already has search and edit_file registered
- `server.py` — Tools auto-register via decorators, no changes needed
- `docs/mcp_server_guide.md` — No tool-specific content
- `docs/guides/manage_docs_agent_guide.md` — Only covers manage_docs
- `docs/guides/manage_docs_troubleshooting.md` — Only covers manage_docs
- `.scribe/docs/dev_plans/` — Project-specific docs, no updates needed

### Search Methodology
- `Glob **/*.md` across repo for all markdown files
- `Grep` for `grep|sed|rg|ripgrep` in all .md files
- `Grep` for `search.*tool|edit_file|scribe.search|scribe.edit` in all .md files
- `Grep` for `Essential Tools|Tool Usage|Available Tools` for tool table locations
- `Grep` for `tools/` listings in config and whitepaper docs
- Manual verification of tool registration in `tools/__init__.py` and `server.py`

---
