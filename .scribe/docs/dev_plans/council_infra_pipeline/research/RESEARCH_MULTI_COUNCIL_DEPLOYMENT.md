---
id: council_infra_pipeline-research-multi-council-deployment
title: "\U0001F52C Research Multi Council Deployment \u2014 council_infra_pipeline"
doc_type: RESEARCH_MULTI_COUNCIL_DEPLOYMENT
doc_name: RESEARCH_MULTI_COUNCIL_DEPLOYMENT
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 02:14:28 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Multi Council Deployment — council_infra_pipeline
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 02:13:41 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

The Council web UI serves multiple registered councils, each with custom pages, routes, static assets, and DB migrations. The platform discovers and serves council-specific content by resolving filesystem paths stored in the `council.councils` database table. This research documents the complete discovery chain, inventories all downstream councils, and analyzes the architectural gap that prevents multi-council deployment to production (Hetzner).

**Critical Finding**: The web UI assumes filesystem co-location -- it reads custom pages, routes, and static files directly from `Path(council[\"repo_path\"])`. On dev (WSL2), all repos are local. On prod (Docker containers on Hetzner), downstream repos do not exist inside the container. This is the fundamental deployment gap that must be solved before CI/CD can support multi-council deployments.

**Confidence**: 0.95 (all claims verified via direct code inspection)
<!-- ID: research_scope -->
## Research Scope

**Research Lead:** ResearchAgent
**Date:** 2026-02-17
**Priority:** HIGH -- blocks CI/CD design for multi-council

**Scope:**
1. Discover all downstream councils across ~/projects/
2. Trace council registration and web UI discovery code
3. Map exact filesystem requirements per council
4. Analyze Docker container constraints for multi-council
5. Evaluate deployment architecture options
6. Research industry patterns for multi-tenant deployment
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
- **References:** [Link to diagrams, ADRs, whitepapers, or related documents]
- **Attachments:** [List supporting artifacts or datasets]


---