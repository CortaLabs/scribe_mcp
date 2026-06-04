---
id: scribe_mcp_bug_log_tooling_20260604-spec-open-bug-manage-docs
title: 'SPEC: open_bug/manage_docs tooling friction'
doc_type: custom
doc_name: SPEC_OPEN_BUG_MANAGE_DOCS
category: engineering
status: scaffolded
version: '0.1'
last_updated: 2026-06-04 01:39:56 UTC
maintained_by: agent-20260604-013722-c24f7d26
created_by: agent-20260604-013722-c24f7d26
owners: []
related_docs: []
tags:
- spec
- open_bug
- open_security
- manage_docs
- case-registry
summary: Problem definition for resolving friction between open_bug/open_security
  report creation and manage_docs follow-up edits.
canonical_doc_type: custom
edit_trace:
  tool: manage_docs
  created_at: 2026-06-04 01:39:29 UTC
  created_via: create_doc
  last_edited_at: 2026-06-04 01:39:56 UTC
  last_edited_by: agent-20260604-013722-c24f7d26
  last_action: append
---

# SPEC: open_bug/manage_docs tooling friction

## Problem Statement
open_bug/open_security can create governed case reports under repo-root docs/bugs or docs/security paths, but follow-up manage_docs edits currently resolve ordinary dev-plan document names. Agents then cannot easily fill required bug/security report sections through managed tooling and may be tempted toward shell edits or fragile path guessing.

## Goals
- Determine from current source truth whether bug/security reports are intended to be repo-root docs, Scribe project docs, registry cases, or a combination.
- Make follow-up editing smooth for agents using manage_docs after open_bug/open_security.
- Preserve coherent link_fix and list_open_cases behavior.
- Return obvious identifiers and paths from open_bug/open_security for follow-up work.
- Add focused regression tests for bug and security report parity.

## Non-Goals
- No PowerShell, path-environment, or client-surface repair work.
- No shell-edit workaround for managed bug/security reports.
- No generated AGENTS.md, CLAUDE.md, .claude, or .codex hand edits.
- No mirror-vs-resolution decision by preference; decide from source evidence and operator ergonomics.

## Constraints And Assumptions
- Use direct mcp__scribe__* tools and keep the active project scribe_mcp_bug_log_tooling_20260604.
- Follow research before Blueprint before implementation.
- If template or contract source changes are needed, consult template-authoring and edit source templates only.
- Existing infrastructure must be extended or refined, not bypassed or replaced.

## Research Questions
- How do open_bug and open_security create reports, assign case IDs, choose paths, register metadata, and return identifiers?
- How does manage_docs resolve doc_name, doc, target_dir, doc_type/category metadata, and paths for edit actions?
- How do case registry, list_open_cases, and link_fix model authority and report paths?
- What do BUG_REPORT and SECURITY_REPORT templates require, including section IDs and metadata?
- What tests currently assert sentinel case IDs, registry contract, manage_docs target resolution, bug management regression behavior, and list_open_cases behavior?
- Which solution best matches source truth: first-class manage_docs resolution for case reports, explicit mirroring with authority rules, or another model?

## Acceptance Criteria
- Research artifacts answer the questions above with file-level evidence.
- Blueprint produces a bounded implementation plan and verification story.
- Implementation makes open_bug/open_security follow-up manage_docs edits straightforward using obvious identifiers such as case_id, slug, returned path, or doc_type/category metadata if source-backed.
- Focused tests reproduce the exact bug/security friction and pass.
- Affected sentinel/manage_docs tests pass.
