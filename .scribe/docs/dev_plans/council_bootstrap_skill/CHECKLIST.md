---
id: council_bootstrap_skill-checklist
title: "\u2705 Acceptance Checklist \u2014 council_bootstrap_skill"
doc_type: checklist
doc_name: checklist
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 19:25:03 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ✅ Acceptance Checklist — council_bootstrap_skill
**Author:** Scribe
**Version:** v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 18:46:32 UTC

> Acceptance checklist for council_bootstrap_skill.

---
## Documentation Hygiene
<!-- ID: documentation_hygiene -->
- [x] Architecture guide updated (proof: ARCHITECTURE_GUIDE.md — Blueprint session 2026-02-22)
- [x] Phase plan current (proof: PHASE_PLAN.md — single task package defined)
- [x] Research complete (proof: RESEARCH_ROSTER_YAML_CATALOG_20260222.md, RESEARCH_SKILL_STRUCTURAL_PATTERNS_20260222.md)
<!-- ID: phase_0 -->
### Implementation (Forge)
- [x] File created: `.council/templates/skills/bootstrap-council/SKILL.md.j2` | proof=All implementation gates verified — file exists, dry-run passes, {{ in output, 4-field frontmatter, 846 lines, 7 phases, 7 checkpoints, 8 raw blocks, council_identity in 11 places, both output files exist, 44 tests pass
- [ ] Frontmatter: exactly 4 fields (name, description, user-invocable, context)
- [ ] Line count: 750-850 lines
- [ ] Phases: 7 sections (Phase 0-6) plus Appendix
- [ ] Checkpoints: every phase ends with CHECKPOINT blockquote
- [ ] Raw blocks: all YAML with `{{`/`{%` wrapped in `{% raw %}`
- [ ] Template vars: `{{ repo_root }}` used for file paths
- [ ] YAML quality: all archetype YAMLs are complete and would pass validate_roster()

### Verification
- [ ] `council update --dry-run` succeeds
- [ ] `.claude/skills/bootstrap-council/SKILL.md` exists after `council update`
- [ ] `.codex/skills/bootstrap-council/SKILL.md` exists after `council update`
- [ ] Rendered output contains literal `{{` (raw blocks working)
- [ ] `pytest tests/test_council_update.py -v` passes
<!-- ID: final_verification -->
- [ ] All checklist items checked with proofs attached.  
- [ ] Stakeholder sign-off recorded (name + date).  
- [ ] Retro completed and lessons learned documented.


---