---
id: documentation_update-checklist
title: "\u2705 Acceptance Checklist \u2014 documentation_update"
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-23'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — documentation_update
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-01-23 09:36:41 UTC

> Acceptance checklist for documentation_update.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [ ] Architecture guide updated with v2.2 documentation strategy (proof: ARCHITECTURE_GUIDE.md)
- [ ] Phase plan updated with 10 task packages (proof: PHASE_PLAN.md)
- [ ] Source of truth identified (proof: scribe_codebase_audit/ARCHITECTURE_GUIDE.md)
<!-- ID: phase_0 -->
### Task 1.1: README.md
- [ ] Version badge updated to v2.2 (proof: line 6 shows v2.2)
- [ ] New "Update v2.2" section added (proof: section exists after line 16)
- [ ] v2.1.1 section marked as "History" (proof: section title updated)
- [ ] SCRIBE_STATE_PATH marked deprecated (proof: line 298 has deprecation notice)

### Task 1.2: AGENTS_EXTENDED.md
- [ ] Header updated to v2.2 with current date (proof: lines 1-6)
- [ ] v2.2 Architecture Components section added (proof: new section exists)
- [ ] ResponseFormatter decomposition documented (proof: table with 6 modules)
- [ ] Connection pooling documented (proof: section describes pool.py)
- [ ] Session isolation documented (proof: agent parameter explained)
- [ ] Database schema updated (proof: status, docs_json, archive table)

### Task 1.3: CLAUDE.md
- [ ] Line 3 version updated to v2.2 (proof: shows "Scribe MCP v2.2")
- [ ] Section header updated ~line 628 (proof: shows "v2.2 Enhanced Tools")
- [ ] Footer version updated ~line 711 (proof: shows v2.2)
- [ ] v2.2 Architecture Components section added (proof: new section exists)

### Phase 1 Verification
- [ ] `grep "v2\.2" README.md AGENTS_EXTENDED.md CLAUDE.md` returns all 3 files
- [ ] `grep "v2\.1\.1" README.md CLAUDE.md | grep -v History` returns no results
<!-- ID: final_verification -->
### Task 2.1: docs/Scribe_Usage.md
- [ ] Version reference updated to v2.2 (proof: header shows v2.2)
- [ ] v2.2 Architecture section added (proof: new section exists)
- [ ] Connection pooling documented (proof: configuration options listed)
- [ ] Data retention documented (proof: cleanup_old_entries described)

### Task 2.2: Whitepaper
- [ ] Title updated to v2.2 (proof: shows "Scribe MCP Whitepaper v2.2")
- [ ] State Manager section updated (proof: no active state.json references)
- [ ] Connection Pool section added (proof: new subsection exists)
- [ ] Architecture diagrams accurate (proof: no state.json in diagrams)

### Task 2.3: quickstart.md
- [ ] set_project examples have agent param (proof: grep confirms)
- [ ] read_recent examples have agent param (proof: grep confirms)
- [ ] All other tool examples have agent param (proof: grep confirms)

### Phase 2 Verification
- [ ] `grep -l "v2\.2" docs/Scribe_Usage.md docs/whitepapers/*.md` returns both files
- [ ] `grep "set_project\|read_recent" .codex/skills/*/references/quickstart.md | grep -v "agent="` returns no results

---

## Phase 3 - LOW Priority Documents

### Task 3.1: Subagent Docs
- [ ] architect.md - agent params fixed (proof: grep confirms)
- [ ] bug_hunter.md - agent params fixed (proof: grep confirms)
- [ ] coder.md - agent params fixed (proof: grep confirms)
- [ ] research.md - agent params fixed (proof: grep confirms)
- [ ] review.md - agent params fixed (proof: grep confirms)

### Task 3.2: AGENTS.md
- [ ] v2.1.1 references updated to v2.2 (proof: grep confirms no active v2.1.1)

### Phase 3 Verification
- [ ] All subagent docs have consistent agent parameter usage
- [ ] No v2.1.1 references in AGENTS.md (except clearly marked historical)

---

## Phase 4 - Final Audit

### Task 4.1: Version Consistency
- [ ] No unexpected v2.1.1 references (proof: grep audit clean)
- [ ] v2.2 present in all key documents (proof: grep returns all expected files)

### Task 4.2: Agent Parameter Consistency
- [ ] No tool examples missing agent param (proof: audit grep clean)
- [ ] All examples follow canonical format (proof: manual review)

### Task 4.3: Cross-Document Consistency
- [ ] Connection pool specs match (min=1, max=3, 50-80%) across docs
- [ ] Formatter module list consistent (6 modules) across docs
- [ ] Deprecation language consistent across docs
- [ ] Agent parameter format consistent across docs

---

## Final Sign-Off

- [ ] All phase checklists complete with proofs
- [ ] Documentation health score: 95%+ (audit verification)
- [ ] Review Agent final approval (name + date)
- [ ] Stakeholder sign-off (name + date)
