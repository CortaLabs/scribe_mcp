---
id: read_file_search_audit-docs-update-checklist
title: 'Checklist: Documentation Update for search & edit_file Tools'
doc_name: DOCS_UPDATE_CHECKLIST
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-29'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Checklist: Documentation Update for search & edit_file Tools

**Project:** read_file_search_audit
**Sub-plan:** docs_update
**Author:** ArchitectAgent-DocsUpdate
**Date:** 2026-01-29

---

## Batch 0: Recreate `.claude/skills/` (Recovery)
<!-- ID: batch_0_checklist -->

- [ ] **0.1**: `.claude/skills/scribe-mcp-usage/` recreated from `.codex/` copy <!-- ID: task_0_1 -->
  - **Acceptance**: All files from `.codex/skills/scribe-mcp-usage/` present in `.claude/skills/scribe-mcp-usage/`
  - **Verification**: `diff -r .codex/skills/scribe-mcp-usage/ .claude/skills/scribe-mcp-usage/` shows no differences

## Batch 1: Skill Source Update (at `.claude/skills/`)
<!-- ID: batch_1_checklist -->

- [ ] **1.1**: `.claude/skills/.../references/search.md` created <!-- ID: task_1_1 -->
  - **Acceptance**: File exists, 17 params documented, 6+ examples
  - **Verification**: `cat .claude/skills/scribe-mcp-usage/references/search.md | wc -l` >= 100
- [ ] **1.2**: `.claude/skills/.../references/edit_file.md` created <!-- ID: task_1_2 -->
  - **Acceptance**: File exists, 7 params documented, read-before-edit explained, 4+ examples
  - **Verification**: `cat .claude/skills/scribe-mcp-usage/references/edit_file.md | wc -l` >= 80
- [ ] **1.3**: `.claude/skills/.../SKILL.md` updated <!-- ID: task_1_3 -->
  - **Acceptance**: Tools section lists search.md and edit_file.md; Non-negotiables mentions all 3 tools
  - **Verification**: `grep 'search.md' .claude/skills/scribe-mcp-usage/SKILL.md` succeeds

## Batch 4: Codex Skill References (executed before Batch 2)
<!-- ID: batch_4_checklist -->

- [ ] **4.1**: `.claude/skills/.../Operational_Contract.md` updated <!-- ID: task_4_1 -->
  - **Acceptance**: search and edit_file schemas present
  - **Verification**: `grep 'search' .claude/skills/scribe-mcp-usage/references/Operational_Contract.md`
- [ ] **4.2**: `.claude/skills/.../files.md` updated <!-- ID: task_4_2 -->
  - **Acceptance**: Title says "File Operations", search + edit_file sections exist
  - **Verification**: `head -1 .claude/skills/scribe-mcp-usage/references/files.md` contains "File Operations"
- [ ] **4.3**: `.claude/skills/.../INDEX.md` updated <!-- ID: task_4_3 -->
  - **Acceptance**: search.md and edit_file.md entries present
- [ ] **4.4**: `.claude/skills/.../quickstart.md` updated <!-- ID: task_4_4 -->
  - **Acceptance**: Mentions search and edit_file
- [ ] **4.5**: `.claude/skills/.../Scribe_Usage.md` updated <!-- ID: task_4_5 -->
  - **Acceptance**: search and edit_file sections mirror docs/Scribe_Usage.md

## Batch 2: Skill Sync
<!-- ID: batch_2_checklist -->

- [ ] **2.1**: All 8 files synced from `.claude/skills/` (source) to `.codex/skills/` AND `~/.claude/skills/` <!-- ID: task_2_1 -->
  - **Acceptance**: SHA256 match for all synced files across all 3 locations
  - **Verification**: `diff .claude/skills/scribe-mcp-usage/SKILL.md .codex/skills/scribe-mcp-usage/SKILL.md` AND `diff .claude/skills/scribe-mcp-usage/SKILL.md ~/.claude/skills/scribe-mcp-usage/SKILL.md` (no output = match)
  - Files: SKILL.md, references/{search,edit_file,INDEX,Operational_Contract,files,quickstart,Scribe_Usage}.md

## Batch 3: Governance Docs
<!-- ID: batch_3_checklist -->

- [ ] **3.1**: `docs/Scribe_Usage.md` updated <!-- ID: task_3_1 -->
  - **Acceptance**: search section (~100 lines) + edit_file section (~80 lines) with full params and examples
  - **Verification**: `grep '## search' docs/Scribe_Usage.md` and `grep '## edit_file' docs/Scribe_Usage.md`
- [ ] **3.2**: `CLAUDE.md` (scribe_mcp root) updated <!-- ID: task_3_2 -->
  - **Acceptance**: Essential Tools table has search + edit_file; File Policy mentions both
  - **Verification**: `grep 'search' CLAUDE.md` and `grep 'edit_file' CLAUDE.md`
- [ ] **3.3**: `AGENTS.md` updated <!-- ID: task_3_3 -->
  - **Acceptance**: Tool listing and file policy include search + edit_file
- [ ] **3.4**: `config/CLAUDE.md` updated <!-- ID: task_3_4 -->
  - **Acceptance**: search.py and edit_file.py in Tools Architecture listing

## Batch 5: Agent Files
<!-- ID: batch_5_checklist -->

- [ ] **5.1**: All 5 `.claude/agents/` files updated <!-- ID: task_5_1 -->
  - **Acceptance**: File Reading Policy mentions search + edit_file in all 5 files
  - **Verification**: `grep -l 'scribe.search' .claude/agents/*.md | wc -l` = 5
- [ ] **5.2**: All 5 `docs/claude_code_subagents/` mirrors updated <!-- ID: task_5_2 -->
  - **Acceptance**: Mirror files match .claude/agents/ for updated sections
  - **Verification**: `grep -l 'scribe.search' docs/claude_code_subagents/*.md | wc -l` = 5

## Batch 6: Minor Updates
<!-- ID: batch_6_checklist -->

- [ ] **6.1**: `README.md` updated <!-- ID: task_6_1 -->
  - **Acceptance**: Feature sections for search and edit_file exist
- [ ] **6.2**: `docs/whitepapers/scribe_mcp_whitepaper.md` updated <!-- ID: task_6_2 -->
  - **Acceptance**: edit_file.py in directory tree and tool suite section

## Cross-Cutting Verification
<!-- ID: cross_cutting -->

- [ ] **Drop-in snippet**: Architecture Guide Section 4 contains complete, self-contained snippet <!-- ID: verify_snippet -->
- [ ] **Sync integrity**: All .codex and ~/.claude skill files match .claude/ source files <!-- ID: verify_sync -->
- [ ] **No broken references**: All nav links in SKILL.md point to files that exist <!-- ID: verify_links -->
- [ ] **Tool signatures consistent**: All 22 files use the same parameter names/types <!-- ID: verify_consistency -->
