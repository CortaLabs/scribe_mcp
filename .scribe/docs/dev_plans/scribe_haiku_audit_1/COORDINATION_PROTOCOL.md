---
id: scribe_haiku_audit_1-coordination-protocol
title: Haiku Audit Swarm - Coordination Protocol
doc_name: COORDINATION_PROTOCOL
category: engineering
status: draft
version: '0.1'
last_updated: '2026-01-08'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Haiku Audit Swarm - Coordination Protocol

**Project:** `scribe-haiku-audit-1`
**Purpose:** Identify modularization opportunities in scribe_mcp core files
**Orchestrator:** Opus | **Researchers:** Haiku (all)

---

## 🎯 Mission Statement

Find large files that should be split into smaller, focused modules. We are **identifying and proposing** - NOT implementing. Each researcher produces a structured analysis that feeds into a unified refactoring plan.

---

## 📏 Core Principles (NON-NEGOTIABLE)

### 1. Code Sharing Over Duplication
- If two modules need similar functionality, propose a **shared utility**
- Never recommend creating parallel implementations
- Reference existing utilities in `utils/` before proposing new ones

### 2. Clean Codebase Structure
- No random file proliferation
- Every proposed module must have a clear home in the existing directory structure
- If a new directory is needed, justify it explicitly

### 3. Consistent Naming Conventions
All proposed extractions MUST follow these patterns:

```
# For extracted modules from tools/:
tools/<original>_<purpose>.py
  Examples:
  - manage_docs_actions.py (action handlers)
  - manage_docs_validation.py (validators) ← already exists!
  - append_entry_formatters.py (output formatting)

# For extracted utilities:
utils/<domain>_<function>.py
  Examples:
  - utils/entry_builder.py
  - utils/doc_parser.py

# For shared infrastructure:
shared/<concept>.py
  Examples:
  - shared/pagination.py
  - shared/filtering.py
```

### 4. Logical Cohesion
Each proposed module must have:
- **Single responsibility** - one clear purpose
- **Minimal interface** - few entry points
- **Clear dependencies** - explicit imports, no circular refs

---

## 🔬 Research Methodology

### Required Tool Usage
```python
# ALWAYS start with structure scan
read_file(path="<file>", mode="scan_only", format="readable")

# For large files, paginate structure
read_file(path="<file>", mode="scan_only", structure_page=1, structure_page_size=20)

# Check existing wiki for prior analysis
read_file(path=".scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/tools/<tool>.md", mode="scan_only")
```

### Analysis Questions (Answer for each file)
1. What are the logical clusters of functionality?
2. Which functions are only used internally vs exported?
3. What shared patterns exist that could be extracted?
4. Are there existing utilities that should be used instead of inline code?
5. What's the minimum viable extraction that reduces complexity?

---

## 📋 Deliverable Format (MANDATORY)

Every researcher produces findings in this EXACT structure:

```markdown
# Modularization Analysis: <filename>

## Summary
- **Lines:** <count>
- **Classes:** <count>
- **Functions:** <count>
- **Complexity Rating:** Low/Medium/High/Critical

## Logical Clusters Identified

### Cluster 1: <name>
- **Lines:** ~<estimate>
- **Functions:** <list>
- **Purpose:** <one sentence>
- **Extraction Candidate:** Yes/No
- **Proposed Module:** `<path/name.py>`
- **Dependencies:** <what it needs>
- **Dependents:** <what needs it>

### Cluster 2: <name>
...

## Shared Code Opportunities
- <pattern> appears in <files> → propose `utils/<name>.py`

## Existing Utilities to Leverage
- `utils/<existing>.py` could replace inline code at lines <X-Y>

## Recommended Extractions (Priority Order)
1. **<module_name>** - <reason> - Est. <lines> lines
2. **<module_name>** - <reason> - Est. <lines> lines

## Risks & Considerations
- <any concerns about extraction>

## Questions for Architect
- <anything unclear that needs higher-level decision>
```

---

## 👥 Agent Assignments

### Tools Division (3 Agents)

| Agent ID | Scope | Focus |
|----------|-------|-------|
| `ResearcherA1-Haiku` | `tools/manage_docs.py` (3,079 lines) | Action handlers, validation, doc operations |
| `ResearcherA2-Haiku` | `tools/append_entry.py` + `tools/query_entries.py` | Logging cluster - entry creation, querying, filtering |
| `ResearcherA3-Haiku` | `tools/read_file.py` + `tools/rotate_log.py` | File operations cluster - reading, rotation, archival |

### Infrastructure Division (2 Agents)

| Agent ID | Scope | Focus |
|----------|-------|-------|
| `ResearcherB1-Haiku` | `storage/sqlite.py` + `storage/base.py` | Storage abstraction, query patterns |
| `ResearcherB2-Haiku` | `doc_management/manager.py` + `doc_management/*.py` | Doc management subsystem |

### State Division (1 Agent)

| Agent ID | Scope | Focus |
|----------|-------|-------|
| `ResearcherC1-Haiku` | `state/agent_manager.py` + `state/manager.py` | State management patterns |

---

## 📁 Output Location

All research docs go to:
```
.scribe/docs/dev_plans/scribe_haiku_audit_1/research/
```

Naming convention:
```
RESEARCH_<SCOPE>_MODULARIZATION_<YYYYMMDD>.md

Examples:
- RESEARCH_MANAGE_DOCS_MODULARIZATION_20260108.md
- RESEARCH_LOGGING_CLUSTER_MODULARIZATION_20260108.md
- RESEARCH_STORAGE_MODULARIZATION_20260108.md
```

---

## ✅ Completion Criteria

A research doc is COMPLETE when it has:
- [ ] All sections from the template filled
- [ ] At least 2 extraction candidates identified (or explicit "none needed" justification)
- [ ] Shared code opportunities documented
- [ ] Existing utilities checked and referenced
- [ ] Questions for Architect listed (even if empty)

---

## 🔗 Reference Materials

Existing wiki docs to consult:
- `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/CANDIDATE_MODULE_BUCKETS.md`
- `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/tools/<tool_name>.md`
- `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/cross_cutting_concerns.md`

---

## ⚠️ Anti-Patterns (DO NOT)

- ❌ Propose extraction without checking if utility already exists
- ❌ Create new directories without explicit justification
- ❌ Suggest names that don't follow conventions above
- ❌ Recommend changes without considering dependents
- ❌ Skip the deliverable template sections
- ❌ Propose more than 5 extractions per file (focus on high-impact)

---

*This protocol governs all research agents. Deviations require Orchestrator approval.*
