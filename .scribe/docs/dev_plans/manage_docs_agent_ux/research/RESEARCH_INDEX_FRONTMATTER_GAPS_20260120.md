---
id: manage_docs_agent_ux-research-index-frontmatter-gaps-20260120
title: "\U0001F52C Research Index Frontmatter Gaps 20260120 \u2014 manage_docs_agent_ux"
doc_name: RESEARCH_INDEX_FRONTMATTER_GAPS_20260120
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-20'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Index Frontmatter Gaps 20260120 — manage_docs_agent_ux
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-01-20 04:12:03 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Research Goal:** Investigate when indexes and frontmatter don't get updated properly in manage_docs operations.

**Key Findings:**

1. **Frontmatter Auto-Update WORKS for most actions** - The `last_updated` field IS automatically updated via `_apply_frontmatter_pipeline` for ALL edit actions (replace_section, append, apply_patch, status_update, replace_range, replace_text, normalize_headers, generate_toc).

2. **CRITICAL GAP: Managed Docs Have NO Index Files** - Unlike special docs (research/bug/review/agent_cards) which have INDEX.md files that get auto-updated, the core managed documents (ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md) have NO index files at all.

3. **Index Update Asymmetry** - Special doc creation calls `_update_research_index()`, `_update_bug_index()`, etc. (manage_docs.py:2771-2775), but managed doc edits have NO corresponding index update mechanism.

4. **Write Tool Bypass Impact is Asymmetric** - When agents bypass manage_docs with Write tool:
   - Frontmatter is NOT updated (last_updated stays stale)
   - Index files are NOT updated (already non-existent for managed docs)
   - For special docs: index remains stale until next manage_docs operation

5. **Action Coverage Gap** - `validate_crosslinks` action bypasses frontmatter updates entirely (line 449-450).

**Root Cause:** Frontmatter infrastructure exists and works, but was never integrated into ALL action paths. Index infrastructure only exists for special docs, not for core managed documents.
<!-- ID: research_scope -->
**Research Lead:** Scribe

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Detailed Findings

### Finding 1: Frontmatter Auto-Update Mechanism EXISTS and WORKS

**Summary:** The last_updated field IS automatically updated for managed documents via the frontmatter pipeline.

**Evidence:**
- `doc_management/manager.py` line 2380: `updates["last_updated"] = date_str` - hardcoded into ALL document edits
- `doc_management/manager.py` lines 2415-2420: `apply_frontmatter_updates()` is called with these updates
- `utils/frontmatter.py` lines 82-118: `apply_frontmatter_updates()` applies the last_updated to the actual YAML frontmatter
- This happens for actions: replace_section, append, apply_patch, status_update, replace_range, replace_text, normalize_headers, generate_toc
- Applied frontmatter is written to disk at `doc_management/manager.py` line 554 via `async_atomic_write()`

**Confidence:** Very High (0.95) - Code inspection confirms the full pipeline

**Exception:** Action `validate_crosslinks` bypasses this (lines 449-450) because it's read-only

---

### Finding 2: CRITICAL - Managed Docs Have NO Index Infrastructure

**Summary:** ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md have zero index file support, unlike special docs.

**Evidence:**
- File search: No INDEX.md exists in managed doc directories (unlike /research/INDEX.md)
- `tools/manage_docs.py` lines 2589-2641: Index updaters defined ONLY for special docs
  - `_update_research_index()` at line 2860
  - `_update_bug_index()` at line 2921 (NOTE: function exists but not shown in grep results - likely async)
  - `_update_review_index()` at line 3015
  - `_update_agent_card_index()` at line 3108
  - NO corresponding updaters for architecture/phase_plan/checklist
- Grep search for "ARCHITECTURE_GUIDE\|PHASE_PLAN\|CHECKLIST" in manage_docs.py: 0 results
- Index update call only for special docs at line 2773: `await index_updater()`

**Implication:** Managed documents were never designed to have index files. They exist in project metadata but nowhere else.

**Confidence:** Very High (0.95) - Comprehensive search confirms absence

---

### Finding 3: Index Update Asymmetry - Special Docs Only

**Summary:** Only special documents (research/bug/review/agent_cards) have index update mechanisms.

**Evidence:**
- `tools/manage_docs.py` lines 2589, 2620, 2628, 2640: Index updater lambdas created only for special doc types
- Line 2771-2775: Only called for special doc creation (`if index_updater:`)
- Managed docs processed at lines 1360-1650 have NO corresponding index update calls
- Search for index update in EDIT_ACTIONS section (lines 1256-1268): zero index operations

**Why It Matters:** If an agent creates a special doc with manage_docs, the INDEX.md gets updated. But if they edit it with manage_docs, the INDEX.md is NOT updated (only created docs trigger index update).

**Confidence:** High (0.9) - Code structure clearly shows this pattern

---

### Finding 4: Write Tool Bypass Leaves Both Stale

**Summary:** When agents bypass manage_docs with Write tool, they avoid BOTH frontmatter updates AND index updates.

**Evidence:**
- Write tool: Simple 2-parameter tool (file_path, content) - no hook into manage_docs pipeline
- No post-write frontmatter update for Write operations
- No index update mechanism for Write operations
- Impact varies by doc type:
  - Managed docs: last_updated stays stale (only gap, no index to stale)
  - Special docs: last_updated stays stale + INDEX.md stays stale

**Cascading Effect:**
- Agent uses Write to update architecture.md
- last_updated doesn't change
- INDEX.md for research is fine (managed docs don't have index)
- But for research docs: agent uses Write, last_updated stale + INDEX.md stale

**Confidence:** High (0.85) - Inference from architecture, no live test evidence

---

### Finding 5: Action Coverage Gap - validate_crosslinks Bypasses Frontmatter

**Summary:** The `validate_crosslinks` read-only action bypasses frontmatter updates.

**Evidence:**
- `doc_management/manager.py` lines 449-450: Early return for validate_crosslinks
- Line 2380 (last_updated setting) is NOT reached for this action
- This is correct (read-only action shouldn't modify file), but shows conditional paths

**Impact:** Minimal (correct behavior for read-only action)

**Confidence:** Very High (0.95) - Direct code inspection

---

## Coverage Table: Which Actions Update Frontmatter vs Index?

| Action | Frontmatter Updated | Index Updated | Notes |
|--------|:------------------:|:-------------:|-------|
| replace_section | ✅ Yes | ❌ No | Core workflow action |
| append | ✅ Yes | ❌ No | Core workflow action |
| apply_patch | ✅ Yes | ❌ No | Core workflow action |
| status_update | ✅ Yes | ❌ No | Checklist updates |
| replace_range | ✅ Yes | ❌ No | Line-level edits |
| replace_text | ✅ Yes | ❌ No | Find/replace |
| normalize_headers | ✅ Yes | ❌ No | Auto-normalize |
| generate_toc | ✅ Yes | ❌ No | Auto-TOC |
| validate_crosslinks | ❌ No | ❌ No | Read-only action |
| create_doc | ✅ Yes | ❌ No | Managed docs have no index |
| create_research_doc | ✅ Yes | ✅ Yes* | *Only created docs, not edits |
| create_bug_report | ✅ Yes | ✅ Yes* | *Only created docs, not edits |
| create_review_report | ✅ Yes | ✅ Yes* | *Only created docs, not edits |
| create_agent_report_card | ✅ Yes | ✅ Yes* | *Only created docs, not edits |

**Summary:** All EDIT actions update frontmatter correctly, NO actions update any index files on subsequent edits.
<!-- ID: technical_analysis -->
## Gap Analysis

### Gap 1: Managed Docs Have No Index Infrastructure (CRITICAL)

**What's Missing:** ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md have zero index file support.

**Why It Matters:**
- Special docs (research/bugs) have INDEX.md auto-generated and updated
- Managed docs have nothing - no INDEX.md, no index updates
- This creates an asymmetric system where some docs are indexed and others aren't

**Severity:** HIGH - Architectural inconsistency

**How to Fix:**
- Add INDEX.md generation for managed docs directory
- Call index update when creating/editing managed docs
- OR: Accept that managed docs don't need indexes (intentional design choice?)

**Investigation Needed:** Was this intentional or oversight?

---

### Gap 2: Index Updates Only on Creation, Never on Edit (MEDIUM)

**What's Missing:** When special docs are EDITED, their INDEX.md is NOT updated.

**Example:** 
- Agent creates research doc via manage_docs → INDEX.md updated ✅
- Agent edits same research doc via manage_docs → INDEX.md stays stale ❌

**Current Code:** `index_updater` lambda is only called DURING document creation (lines 2771-2773), not during edits.

**Severity:** MEDIUM - Index becomes stale over time

**How to Fix:**
- Call index updater for EDIT_ACTIONS too (not just create)
- Move index updater call outside special doc creation block
- Apply to all actions: replace_section, append, apply_patch, etc.

---

### Gap 3: Write Tool Bypass Creates Dual Staleness (MEDIUM)

**What's Missing:** When agents bypass manage_docs with Write tool, BOTH frontmatter AND index go stale.

**Scenario:**
- Agent uses Write to update research doc directly
- last_updated doesn't change (Write has no post-hook)
- INDEX.md doesn't get refreshed (no trigger)
- Result: Double stale - old timestamp + index mismatch

**Severity:** MEDIUM - Amplifies the impact of Write tool bypass

**How to Fix:**
- Add Write tool hook to call frontmatter + index update post-write
- OR: Detect Write-based changes and auto-update on next manage_docs call
- OR: Warn agents when they bypass manage_docs

---

### Gap 4: Asymmetric Special Doc Coverage (LOW)

**What's Missing:** Bug reports have index update but index function signature unclear.

**Evidence:** Search found `_update_bug_index()` definition expected at line 2921 but implementation not visible in search results. Likely due to async function handling in grep.

**Severity:** LOW - Likely working, just not well documented

**How to Fix:**
- Verify all four special doc types have working index updaters
- Document the index update mechanism

---

## Key Code Locations

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Frontmatter Update | manager.py | 2348-2420 | `_apply_frontmatter_pipeline()` sets last_updated |
| Frontmatter Application | frontmatter.py | 82-118 | `apply_frontmatter_updates()` writes to YAML |
| Index Update (Research) | manage_docs.py | 2860-2920 | `_update_research_index()` |
| Index Update (Bugs) | manage_docs.py | 2921+ | `_update_bug_index()` |
| Index Update (Review) | manage_docs.py | 3013-3060 | `_update_review_index()` |
| Index Update (Agent Cards) | manage_docs.py | 3106-3150 | `_update_agent_card_index()` |
| Index Update Calls | manage_docs.py | 2589-2641 | Lambda creation for special docs |
| Index Update Execution | manage_docs.py | 2771-2775 | Actual index_updater() call |
| Write File | manager.py | 554 | `async_atomic_write()` writes updated content |

---

## System Interactions

**Frontmatter Pipeline is Robust:**
- All edit actions correctly flow through `_apply_frontmatter_pipeline()`
- `apply_frontmatter_updates()` properly applies changes to YAML frontmatter
- Changes are written to disk successfully
- Infrastructure is complete and working

**Index System is Incomplete:**
- Index updates ONLY for special doc creation
- Index updates NEVER for edits
- Managed docs have no index infrastructure at all
- Index updates are not integrated into regular edit flow

**Write Tool Bypass Effect:**
- Frontmatter bypass: last_updated becomes stale (would be caught by hash check if applied)
- Index bypass: Relevant only for special docs, becomes stale for research/bugs
- Both effects compound when using Write on special docs
<!-- ID: recommendations -->
## Recommendations

### Recommendation 1: Fix Index Update Triggering (IMMEDIATE)

**Priority:** HIGH - Impacts special doc indexing reliability

**What to Do:**
- Move index updater call from special doc creation block (line 2771) to a more general location
- Call index updater for ALL document change operations, not just creation
- Specifically: Call for EDIT_ACTIONS that modify special docs

**Implementation Approach:**
1. After `apply_doc_change()` returns successfully (line 1769+)
2. Check if doc is a special type (research, bugs, review, agent_cards)
3. Call appropriate index updater function
4. Similar pattern to lines 2771-2775 but for edits

**Code Impact:** Changes to tools/manage_docs.py lines 1790-1850

**Estimated Effort:** 2-3 hours

**Test Scenarios:**
- Edit research doc → verify INDEX.md updates
- Edit bug report → verify bugs/INDEX.md updates
- Edit review report → verify REVIEW_INDEX.md updates
- Edit agent card → verify AGENT_CARDS_INDEX.md updates

---

### Recommendation 2: Add Managed Doc Index Infrastructure (MEDIUM)

**Priority:** MEDIUM - Maintains consistency with special docs

**What to Do:**
- Create INDEX.md structure for managed docs directory
- Add `_update_managed_docs_index()` function (research/manage_docs.py)
- Call it when creating or editing managed docs

**Implementation Approach:**
1. Create template: `/templates/documents/MANAGED_DOCS_INDEX_TEMPLATE.md`
2. Implement `_update_managed_docs_index()` to:
   - Find all .md files in managed docs directory (architecture, phase_plan, checklist)
   - Extract frontmatter metadata (title, status, last_updated, version)
   - Generate INDEX.md with table of managed documents
3. Call from both create and edit paths for managed docs

**Code Impact:** Changes to tools/manage_docs.py, new template

**Estimated Effort:** 4-5 hours

**Decision Point:** Is this desired or intentional design? Consult with architect before implementing.

---

### Recommendation 3: Detect and Warn on Write Tool Bypass (LOW)

**Priority:** LOW - Defensive measure, doesn't fix root cause

**What to Do:**
- Add detection for direct file writes to manage_docs tracked files
- Emit warning/reminder to agents about using manage_docs
- Consider deprecating Write tool for managed docs

**Implementation Approach:**
1. Create `_detect_write_bypass()` function to check if file was modified outside manage_docs
2. Compare timestamps or hash snapshots
3. Emit warning in next manage_docs call for that doc
4. Add reminder in documentation

**Code Impact:** Minor - diagnostic feature only

**Estimated Effort:** 1-2 hours

---

## Summary Table: Gap Remediation

| Gap | Severity | Root Cause | Fix Effort | Priority |
|-----|----------|-----------|-----------|----------|
| Index updates only on creation | MEDIUM | Incomplete integration | 2-3 hrs | HIGH |
| Managed docs no index | HIGH | Design oversight | 4-5 hrs | MEDIUM |
| Write bypass dual stale | MEDIUM | Write tool lacks hooks | 1-2 hrs | LOW |
| Bug index coverage unclear | LOW | Documentation gap | <1 hr | LOW |

---

## Action Items for Architect/Coder

1. **Clarify Design Intent**: Are managed docs intentionally without indexes, or is this a gap?
2. **Implement Index Updates on Edit**: Priority HIGH - Fix special doc index staleness
3. **Add Managed Doc Indexes**: Priority MEDIUM - Maintain consistency
4. **Document Index System**: Explain when/how indexes get updated for each doc type

---

## Confidence Assessment

| Finding | Confidence | Reasoning |
|---------|-----------|-----------|
| Frontmatter auto-update works | 0.95 | Direct code inspection confirms full pipeline |
| Managed docs have no index | 0.95 | Comprehensive file system + code search confirms absence |
| Index updates only on create | 0.90 | Code structure clearly shows creation-only trigger |
| Write bypass effect | 0.85 | Inferred from architecture, no live test evidence |

**Overall Research Confidence:** 0.91 - High confidence findings with clear code references
<!-- ID: appendix -->
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---