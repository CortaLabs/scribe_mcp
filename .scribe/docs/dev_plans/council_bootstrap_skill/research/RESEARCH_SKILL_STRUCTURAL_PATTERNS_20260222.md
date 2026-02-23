---
id: council_bootstrap_skill-research-skill-structural-patterns-20260222
title: "\U0001F52C Research Skill Structural Patterns 20260222 \u2014 council_bootstrap_skill"
doc_type: RESEARCH_SKILL_STRUCTURAL_PATTERNS_20260222
doc_name: RESEARCH_SKILL_STRUCTURAL_PATTERNS_20260222
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 18:50:43 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Skill Structural Patterns 20260222 — council_bootstrap_skill
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 18:48:27 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
<!-- ID: research_scope -->
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->Detail each major finding with evidence and confidence levels.
### Finding 1
- **Summary:** [Describe the finding]
- **Evidence:** [Link to logs, code references, or experiments]
- **Confidence:** Medium

### Finding 2
- **Summary:** [Describe the finding]
- **Evidence:** [Link to supporting material]
- **Confidence:** Medium

### Additional Notes
- Capture supporting observations or open follow-ups.


---
## Technical Analysis
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->Translate research into recommended actions.
### Immediate Next Steps
- [ ] List concrete follow-up tasks for the team.

### Long-Term Opportunities
- Highlight strategic improvements informed by the research.


---
## Appendix
<!-- ID: appendix -->
## Appendix: Detailed Per-Skill Notes

### agent-roster (377 lines, 8 sections)
- **Focus:** Roster.yaml format, agent fields, CLI commands
- **Code examples:** agent definition YAML, field types, custom sections
- **Raw blocks:** 1 (YAML config example with `{}`)
- **Tables:** 1 major (roster fields)
- **Strength:** Clear field catalog with type hints

### scribe-integration (391 lines, 9 sections)
- **Focus:** Logging patterns, file reading, doc management, bug reporting
- **Code examples:** append_entry, manage_docs, open_bug, read_file patterns
- **Raw blocks:** 2 (YAML config examples)
- **Tables:** 1 major (status levels)
- **Strength:** Comprehensive logging reference

### custom-pages-dev (352 lines, 7 sections) [SHORTEST]
- **Focus:** Page templates, frontmatter, static assets, DB migrations
- **Code examples:** Jinja2 template with frontmatter, sidebar layout
- **Raw blocks:** 1 (Jinja2 template code block)
- **Tables:** 3 (fields, blocks, context vars)
- **Strength:** Complete end-to-end custom page workflow

### council-mcp-dev (377 lines, 10 sections)
- **Focus:** Project structure map, patterns reference
- **Code examples:** 12 code blocks covering imports, patterns, auth
- **Raw blocks:** 1 (YAML example)
- **Tables:** 3 (modules, agent selection, schema)
- **Strength:** Comprehensive project overview, highest code density

### mcp-tool-dev (471 lines, 11 sections)
- **Focus:** Step-by-step tool development, policy guards, error handling
- **Code examples:** Tool decorator, signatures, DB patterns, JSON parsing
- **Raw blocks:** 1 (custom YAML fields)
- **Tables:** 3 (modules, patterns, response format)
- **Strength:** Structured 5-step workflow with testing patterns

### web-route-dev (411 lines, 9 sections)
- **Focus:** Web API patterns, council isolation, downstream routes
- **Code examples:** Route structure, Pydantic models, DB queries, ProcessManager
- **Raw blocks:** 1 (YAML config snippet)
- **Tables:** 3 (imports, models, patterns)
- **Strength:** Clear separation of standard vs downstream routes

### agentkit-queries (580 lines, 8 sections) [LONGEST]
- **Focus:** Query cookbook, patterns, SELECT/INSERT/UPDATE/DELETE
- **Code examples:** 7 code blocks covering all query types
- **Raw blocks:** 0 (no conflicting syntax)
- **Tables:** 4 (patterns, operations, fields, anti-patterns)
- **Strength:** Most comprehensive cookbook, no raw blocks needed

### ray-compute (357 lines, 7 sections)
- **Focus:** Ray cluster architecture, CLI commands, worker management
- **Code examples:** Connection patterns, task definitions, fallback patterns
- **Raw blocks:** 0 (no conflicting syntax)
- **Tables:** 3 (architecture, CLI, config)
- **Strength:** CLI-focused reference with GPU/CPU fallback patterns
