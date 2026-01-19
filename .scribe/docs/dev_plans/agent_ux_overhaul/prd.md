---
id: agent_ux_overhaul-prd-agent-ux-overhaul
title: Agent UX Overhaul - Product Requirements Document
doc_name: PRD_agent_ux_overhaul
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-19'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
<!-- TOC:start -->
- [1 Agent UX Overhaul - Product Requirements Document](#1-agent-ux-overhaul-product-requirements-document)
  - [1.1 Executive Summary](#11-executive-summary)
  - [1.2 Problem Statement](#12-problem-statement)
    - [1.2.1 Problem 1: Slugify Chaos](#121-problem-1-slugify-chaos)
    - [1.2.2 Problem 2: manage_docs Complexity](#122-problem-2-manage-docs-complexity)
  - [1.3 Goals & Non-Goals](#13-goals-non-goals)
    - [1.3.1 Goals](#131-goals)
    - [1.3.2 Non-Goals](#132-non-goals)
  - [1.4 Solution Design](#14-solution-design)
    - [1.4.1 Part 1: Slugify Consolidation](#141-part-1-slugify-consolidation)
    - [1.4.2 Part 2: manage_docs Simplification](#142-part-2-manage-docs-simplification)
      - [1.4.2.1 Actions to KEEP (Core Editing - 6)](#1421-actions-to-keep-core-editing-6)
      - [1.4.2.2 Actions to CONSOLIDATE (Creation - 5 → 1)](#1422-actions-to-consolidate-creation-5-1)
      - [1.4.2.3 Actions to REMOVE from manage_docs](#1423-actions-to-remove-from-manage-docs)
    - [1.4.3 Part 3: Parameter Healing (Conservative)](#143-part-3-parameter-healing-conservative)
  - [1.5 Research Completed](#15-research-completed)
  - [1.6 Migration Strategy](#16-migration-strategy)
    - [1.6.1 Phase 1: Slugify (Low Risk)](#161-phase-1-slugify-low-risk)
    - [1.6.2 Phase 2: manage_docs Consolidation (Medium Risk)](#162-phase-2-manage-docs-consolidation-medium-risk)
    - [1.6.3 Phase 3: Auto-Transform Integration (Pending Research)](#163-phase-3-auto-transform-integration-pending-research)
    - [1.6.4 Phase 4: Documentation Cleanup](#164-phase-4-documentation-cleanup)
  - [1.7 Success Criteria](#17-success-criteria)
  - [1.8 Open Questions](#18-open-questions)
  - [1.9 Appendix: File References](#19-appendix-file-references)
<!-- TOC:end -->

# 1 Agent UX Overhaul - Product Requirements Document

**Project:** agent_ux_overhaul  
**Date:** 2026-01-19  
**Status:** Research Complete, Pending Architecture  
**Owner:** Austin + Orchestrator

---

## 1.1 Executive Summary

This project addresses two interconnected problems that cause agent failures and wasted tokens:

1. **Slugify Inconsistency** - Project names are normalized differently across the codebase (hyphens vs underscores vs raw), causing silent lookup failures
2. **manage_docs Complexity** - 18 actions with confusing parameters cause agents to fail, waste generations, and give up

**Goal:** Make tools "just work" without requiring agents to read documentation or get formatting exactly right.

---

## 1.2 Problem Statement

### 1.2.1 Problem 1: Slugify Chaos

Agents use hyphens and underscores interchangeably. The system should handle this, but currently:

| Component | Format Used | Example |
|-----------|-------------|----------|
| Filesystem | Underscore (canonical) | `my_project` |
| Database | Raw (as entered) | `My-Project` |
| State Dict | Raw (as entered) | `My-Project` |
| Vector DB | Hyphenated (inline) | `my-project` |

**Impact:** A project created as "my-project" has its files at `my_project/` but DB lookups for `my_project` fail silently.

**Root Cause:** No single normalization point. Each component does its own thing (or nothing).

### 1.2.2 Problem 2: manage_docs Complexity

Current state:
- 18 actions across 4 categories
- Similar names with different semantics (`replace_section` vs `replace_range` vs `replace_text`)
- Overloaded metadata parameter with undocumented keys per action
- Agents don't know which action to use, fail, waste entire generation

**Impact:** Agents give up on manage_docs, try manual file edits, break Scribe protocol.

---

## 1.3 Goals & Non-Goals

### 1.3.1 Goals

1. **Single-source slugify** - Define normalization ONE TIME, use everywhere
2. **Accept any format** - Hyphens, underscores, spaces, mixed case all resolve correctly
3. **Simplify manage_docs** - Reduce from 18 to 7 focused actions
4. **Conservative healing** - Fix format issues, never change semantics
5. **Fail fast with clarity** - When we can't heal, give actionable error immediately
6. **Zero documentation dependency** - Tools work without agents reading docs

### 1.3.2 Non-Goals

- Changing what existing actions DO (behavior preservation)
- Aggressive parameter healing that changes intent
- Breaking existing projects/data
- Rewriting manage_docs from scratch

---

## 1.4 Solution Design

### 1.4.1 Part 1: Slugify Consolidation

**Principle:** Normalize at boundaries, store canonically, match flexibly.

```
INPUT (any format)     →  BOUNDARY           →  INTERNAL (canonical)
"My-Project"           →  normalize_input()  →  "my_project"
"my_project"           →  normalize_input()  →  "my_project"
"MY PROJECT"           →  normalize_input()  →  "my_project"
```

**Implementation:**

1. Create `normalize_project_input(name)` in `utils/slug.py`
   - Wraps existing `slugify_project_name()`
   - Handles None/empty gracefully
   - Single source of truth

2. Add to EVERY tool entry point:
   - `set_project` - already does for filesystem, extend to DB storage
   - `get_project` - normalize before lookup
   - `query_entries` - normalize project filter
   - `read_recent` - normalize project filter
   - `append_entry` - normalize project reference
   - `manage_docs` - normalize project context
   - `rotate_log` - normalize project name
   - `delete_project` - normalize before delete

3. Lazy DB migration:
   - On first access, if raw name != canonical, update DB record
   - No big-bang migration needed
   - Add `display_name` column for pretty output (optional)

4. Collision detection:
   - In `set_project`, check if canonical name already exists
   - Prevent "my-project" and "my_project" from both being created

### 1.4.2 Part 2: manage_docs Simplification

**Current:** 18 actions across 4 categories

**Target:** 7 focused mutation actions

#### 1.4.2.1 Actions to KEEP (Core Editing - 6)

| Action | Purpose | Key Params |
|--------|---------|------------|
| `replace_section` | Section-based editing (scaffolder) | section, content |
| `apply_patch` | Unified diff editing (preferred) | patch, patch_mode="unified" |
| `replace_range` | Line-based editing | start_line, end_line, content |
| `replace_text` | Find/replace | metadata.find, metadata.replace |
| `append` | Add content | content, metadata.position |
| `status_update` | Checklist updates | section, metadata.status |

#### 1.4.2.2 Actions to CONSOLIDATE (Creation - 5 → 1)

**Before:**
- `create_doc`
- `create_research_doc`
- `create_bug_report`
- `create_review_report`
- `create_agent_report_card`

**After:**
```python
create(doc_type="custom|research|bug|review|agent_card", ...)
```

Internal routing based on doc_type, same templates, cleaner interface.

#### 1.4.2.3 Actions to REMOVE from manage_docs

**Category 3 (Transformation) → Automatic:**
- `normalize_headers` → Run automatically after edits (pending research)
- `generate_toc` → Run on finalization (pending research)
- `validate_crosslinks` → Scrap for now, underdeveloped

**Category 4 (Inspection) → Move to read_file:**
- `list_sections` → `read_file(mode="scan_only")` already does this
- `list_checklist_items` → Just read the file
- `search` → Dedicated search tool or enhanced read_file
- `batch` → Power user edge case, low priority

### 1.4.3 Part 3: Parameter Healing (Conservative)

**Principle:** Fix obvious format issues, NEVER change semantics.

**DO heal:**
- Project name format: `my-project` → `my_project`
- Case normalization: `My_Project` → `my_project`
- Typos in enum values: `doc_category="arcitecture"` → `"architecture"`
- Type coercion: `start_line="10"` → `10`

**DON'T heal:**
- Action names (if wrong, fail fast with suggestion)
- Semantic intent (don't guess what they meant)
- Required parameters (don't invent values)

**Error messages must include:**
- What was wrong
- What we expected
- Suggested fix ("Did you mean X?")

---

## 1.5 Research Completed

| Research Doc | Scope | Key Findings |
|--------------|-------|---------------|
| `RESEARCH_slugify_input_boundaries_20260119` | Where names enter system | 6 tools don't normalize, load_project_config gap |
| `RESEARCH_slugify_storage_migration_20260119` | DB/state storage | DB stores raw, filesystem uses slugified, collision risk |
| `RESEARCH_manage_docs_action_taxonomy_20260119` | All 18 actions mapped | 4 categories, consolidation opportunities identified |
| `RESEARCH_manage_docs_error_healing_20260119` | Failure patterns | BulletproofParameterCorrector exists, can extend |
| `RESEARCH_auto_transform_viability_20260119` | Auto normalize/TOC | **PENDING** |

---

## 1.6 Migration Strategy

### 1.6.1 Phase 1: Slugify (Low Risk)
1. Add `normalize_project_input()` to utils/slug.py
2. Add normalization to each tool entry point (small changes)
3. Add collision detection to set_project
4. Implement lazy migration on access

### 1.6.2 Phase 2: manage_docs Consolidation (Medium Risk)
1. Create unified `create` action with doc_type routing
2. Keep old create_* as aliases initially (deprecation period)
3. Remove Category 3+4 actions
4. Update all documentation

### 1.6.3 Phase 3: Auto-Transform Integration (Pending Research)
1. If viable: Hook normalize_headers into edit action post-processing
2. If viable: Hook generate_toc into finalization
3. Add opt-out flags if needed

### 1.6.4 Phase 4: Documentation Cleanup
1. Update SKILL.md
2. Update CLAUDE.md
3. Update Scribe_Usage.md
4. Update any templates/examples

---

## 1.7 Success Criteria

1. **Slugify:** Any reasonable project name format works (hyphens, underscores, spaces, mixed case)
2. **manage_docs:** Agents can use 7 clear actions without reading docs
3. **Healing:** Format issues auto-fixed, semantic errors fail fast with suggestions
4. **Zero regressions:** Existing projects and workflows continue to work
5. **Token savings:** Fewer failed generations from format errors

---

## 1.8 Open Questions

1. **Auto-transform timing:** After every edit or only on explicit finalize? (Opus researching)
2. **Display names:** Store pretty name separately or just use canonical everywhere?
3. **Alias deprecation:** How long to keep old action names as aliases?
4. **search tool:** New dedicated tool or enhance read_file?

---

## 1.9 Appendix: File References

**Core files to modify:**
- `utils/slug.py` - Add normalize_project_input()
- `tools/set_project.py` - Add collision detection
- `tools/get_project.py` - Add input normalization
- `tools/query_entries.py` - Add input normalization
- `tools/read_recent.py` - Add input normalization
- `tools/append_entry.py` - Fix inline hyphen normalization
- `tools/manage_docs.py` - Consolidate creates, remove actions
- `tools/rotate_log.py` - Add input normalization
- `tools/delete_project.py` - Add input normalization
- `storage/sqlite.py` - Lazy migration logic
- `state/manager.py` - Normalize dict keys

**Docs to update:**
- `.codex/skills/scribe-mcp-usage/SKILL.md`
- `CLAUDE.md`
- `docs/Scribe_Usage.md`
- `docs/guides/manage_docs_troubleshooting.md`
