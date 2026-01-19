---
id: agent_ux_overhaul-checklist
title: "\u2705 Acceptance Checklist \u2014 agent_ux_overhaul"
doc_name: checklist
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

# ✅ Acceptance Checklist — agent_ux_overhaul
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-19 06:54:56 UTC

> Acceptance checklist for agent_ux_overhaul.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Architecture guide complete (proof: ARCHITECTURE_GUIDE.md - 27KB, 10 sections)
- [x] Phase plan complete (proof: PHASE_PLAN.md - 22 task packages across 4 phases)
- [x] Research documents reviewed (proof: 5 RESEARCH_*.md files in research/)
- [ ] PRD requirements addressed (proof: All goals from prd.md covered in architecture)
<!-- ID: phase_0 -->
### Task 1.1: normalize_project_input()
- [x] Function added to `utils/slug.py` after line 35 | proof=normalize_project_input() added to utils/slug.py lines 39-68
- [ ] Handles None input -> returns None
- [ ] Handles empty string -> returns None
- [ ] Handles whitespace-only -> returns None
- [ ] Calls slugify_project_name() for valid input
- [ ] Docstring with examples included
- [ ] **Verification:** `pytest tests/test_slugify_normalization.py::test_normalize_project_input_variants`

### Task 1.2: get_project Normalization
- [ ] Import added: `from utils.slug import normalize_project_input`
- [ ] Normalization applied at line ~395 before state.get_project()
- [ ] **Verification:** set_project("My-Project") then get_project("my_project") returns same project

### Task 1.3: query_entries Normalization
- [ ] Import added to `tools/query_entries.py`
- [ ] Normalization applied at line ~1287
- [ ] **Verification:** query_entries(project="My-Project") == query_entries(project="my_project")

### Task 1.4: read_recent Normalization
- [ ] Import added to `tools/read_recent.py`
- [ ] Normalization applied in project resolution (~line 155)
- [ ] **Verification:** read_recent(project="My-Project") works

### Task 1.5: rotate_log Normalization
- [ ] Import added to `tools/rotate_log.py`
- [ ] Normalization applied at line ~1367
- [ ] **Verification:** rotate_log(project="my-project") works

### Task 1.6: delete_project Normalization
- [ ] Import changed to normalize_project_input
- [ ] Normalization applied at line ~23
- [ ] **Verification:** Can delete project using any name variant

### Task 1.7: load_project_config Normalization
- [ ] Import added to `tools/project_utils.py`
- [ ] Normalization applied at line ~86 in filename construction
- [ ] **Verification:** load_project_config("My-Project") finds my_project.json

### Task 1.8: Collision Detection
- [ ] _check_slug_collision() function added to `tools/set_project.py`
- [ ] Called before backend.upsert_project() for new projects
- [ ] Error message includes suggestion to use existing project
- [ ] **Verification:** Create "my_project", then "my-project" -> error

### Task 1.9: State Dict Keys (Optional)
- [ ] Import added to `state/manager.py`
- [ ] Normalization in get_project() method
- [ ] **Verification:** State lookups work with any name format
<!-- ID: final_verification -->
### Task 2.1: Action Registry Constants
- [ ] PRIMARY_ACTIONS set defined (7 actions)
- [ ] DEPRECATED_ALIASES dict defined (5 mappings)
- [ ] HIDDEN_ACTIONS set defined (7 actions)
- [ ] valid_actions combines all three sets
- [ ] **Verification:** All 18 original actions still validate

### Task 2.2: create Action Routing
- [ ] "create" action handled in dispatcher
- [ ] doc_type extracted from metadata (default: "custom")
- [ ] Routes to correct handler based on doc_type
- [ ] **Verification:** create(doc_type="research") creates research doc

### Task 2.3: Deprecation Aliases
- [ ] DEPRECATED_ALIASES checked in dispatcher
- [ ] Deprecation message added to healing_messages
- [ ] Default params applied from alias mapping
- [ ] "deprecated" field included in response
- [ ] **Verification:** create_research_doc() works with warning

### Task 2.4: Auto-Transform Hook
- [ ] Check for auto_normalize_headers in frontmatter
- [ ] Check for auto_generate_toc in frontmatter
- [ ] Apply transforms only when opted-in
- [ ] Add flags to frontmatter_extra when applied
- [ ] **Verification:** Doc with frontmatter flag gets auto-transformed

### Task 2.5: manage_docs Project Normalization
- [ ] Import added to `tools/manage_docs.py`
- [ ] Normalization applied to project parameter
- [ ] **Verification:** manage_docs(project="My-Project") works

---

## Phase 3: Documentation Updates

### Task 3.1: Critical Documentation (6 files)
- [ ] docs/Scribe_Usage.md updated
- [ ] CLAUDE.md updated
- [ ] config/CLAUDE.md updated
- [ ] .codex/skills/scribe-mcp-usage/references/manage_docs.md updated
- [ ] .codex/skills/scribe-mcp-usage/references/Scribe_Usage.md updated
- [ ] .codex/skills/scribe-mcp-usage/SKILL.md updated

### Task 3.2: Agent Definitions (3 files)
- [ ] AGENTS.md updated
- [ ] docs/guides/manage_docs_agent_guide.md updated
- [ ] .codex/skills/.../sections/documentation_management.md updated

### Task 3.3: Agent Instructions (8 files)
- [ ] .claude/agents/scribe-architect.md updated
- [ ] .claude/agents/scribe-research-analyst.md updated
- [ ] .claude/agents/scribe-coder.md updated
- [ ] .claude/agents/scribe-review-agent.md updated
- [ ] .claude/agents/scribe-bug-hunter.md updated
- [ ] docs/guides/manage_docs_troubleshooting.md updated
- [ ] PROJECT_NAMING.md updated
- [ ] README.md updated

### Task 3.4: Supporting Documentation (6 files)
- [ ] .codex/skills/.../sections/document_editing_manage_docs.md updated
- [ ] docs/whitepapers/scribe_mcp_whitepaper.md updated
- [ ] Other .codex reference files updated as needed
- [ ] **Verification:** grep for deprecated actions returns only deprecation docs

---

## Phase 4: Testing & Validation

### Task 4.1: Slugify Tests
- [ ] tests/test_slugify_normalization.py created
- [ ] test_normalize_project_input_variants() passes
- [ ] test_collision_detection() passes
- [ ] test_cross_tool_consistency() passes

### Task 4.2: manage_docs Tests
- [ ] tests/test_manage_docs_consolidation.py created
- [ ] test_create_action_routing() passes
- [ ] test_deprecated_alias_warning() passes
- [ ] test_hidden_actions_still_work() passes
- [ ] test_auto_transform_optin() passes

### Task 4.3: Full Test Suite
- [ ] `pytest tests/` passes with 0 failures
- [ ] No unexpected warnings
- [ ] All existing tests unchanged

### Task 4.4: Manual QA
- [ ] Create project with hyphens, access with underscores - PASS
- [ ] Query with mixed case - PASS
- [ ] Deprecated action emits warning - PASS
- [ ] New create action works - PASS
- [ ] Auto-transform with frontmatter flag - PASS
- [ ] Collision detection works - PASS

---

## Final Sign-off

- [ ] All Phase 1 items checked with proofs
- [ ] All Phase 2 items checked with proofs
- [ ] All Phase 3 items checked with proofs
- [ ] All Phase 4 items checked with proofs
- [ ] Review Agent approval (>=93%)
- [ ] Stakeholder sign-off recorded (name + date)
- [ ] Retro completed and lessons documented

---
*Checklist v1.0 - Agent UX Overhaul*
*Generated: 2026-01-19 by ArchitectAgent*
