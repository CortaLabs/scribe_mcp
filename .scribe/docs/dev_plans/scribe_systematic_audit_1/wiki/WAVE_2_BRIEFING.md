# Wave 2 Agent Briefing: Medium Tool Forensic Audit

**Date**: 2026-01-05
**Agents**: F (read_file), G (list_projects + get_project), H (read_recent), I (generate_doc_templates)
**Complexity**: Medium (544-885 LOC per assignment)
**Mode**: **READ-ONLY AUDIT** - No implementation, only documentation

---

## Mission Refinement (Post-Wave 1)

You are **reverse-engineering Scribe's operating system**, not cataloging functions.

Wave 1 proved the methodology works. Wave 2 must maintain that standard while covering medium-complexity tools that connect to monster tool infrastructure.

**Critical**: After Waves 2 & 3 complete, there will be a **critical evaluation** of ALL audit work before Phase 6. Your wiki pages are not documentation for users—they are **architecture blueprints for the Architect agent**.

---

## 🚨 NON-NEGOTIABLE: READ-ONLY AUDIT

**YOU ARE NOT FIXING BUGS. YOU ARE NOT IMPLEMENTING SOLUTIONS.**

Your job:
- ✅ Document what IS
- ✅ Document what SHOULD BE
- ✅ Create machine-readable specs for future implementation
- ❌ Write code
- ❌ Fix bugs
- ❌ Implement solutions
- ❌ Create patches

**Example**:
- ✅ "BUG-002: read_file line 234 - Missing hash verification after read (see spec SPEC-READ-002)"
- ❌ "Fixed hash verification by adding SHA256 check"

If you find yourself writing implementation code, **STOP**. Write a spec instead.

**Anti-pattern warning**:
If you find yourself mentally "designing the fix," stop and write a spec instead. Design intent belongs in Phase 6.

---

## Orchestration Rules (Mandatory)

These rules were established post-Wave 1 and are **non-negotiable**:

### 1. Module = Contract, Not Folder

Every proposed extractable module MUST answer:
- **Inputs**: What data enters
- **Outputs**: What data exits
- **Failure policy**: What happens on error
- **Who owns state**: Mutability boundaries

If you can't answer all four, the module proposal is **INCOMPLETE**.

### 2. Before/After at System Level

**Bad**: "This removes ~90 LOC duplication."
**Good**: "Before: three tools independently decide what 'project state' means. After: a single inventory contract defines project truth; tools only render it."

Focus on **conceptual clarity**, not line counts.

### 3. You Can Say "NO" to Modularization

If something should stay coupled, document:
- What invariant would break if extracted
- What state leaks across boundaries
- Why config adapters wouldn't fix it

**Example**: set_project's config normalization should stay coupled (Agent E, Wave 1).

### 4. Token Bloat Categories (Required)

Every verbosity finding MUST be tagged:
- **Structural**: tables, headers, boxes
- **Metadata**: IDs, timestamps, reminders
- **Duplication**: repeated blocks
- **Safety padding**: "just in case" messages

This enables Phase 6 to design **one formatter system** instead of per-tool patches.

### 5. Error Handling = Policy vs Bug

Document clearly:
- **Policy**: Silent failures that are intentional (e.g., best-effort registry updates)
- **Bug**: Partial failures that corrupt state (e.g., rotate_log atomicity violation - P0)

If you're not sure, ask: "Does this failure leave the system in an inconsistent state?"

### 6. Bucket Discipline

Every extractable module gets **ONE primary bucket**:
- `[BUCKET:formatting]`
- `[BUCKET:persistence]`
- `[BUCKET:indexing]`
- `[BUCKET:config]`
- `[BUCKET:state]`
- `[BUCKET:metadata]`
- `[BUCKET:error_handling]`
- `[BUCKET:reminders]`
- `[BUCKET:templating]`
- `[BUCKET:utilities]`

Secondary buckets allowed, but document primary owner.

---

## Wave 2 Tool Assignments

### Agent F: read_file.py (785 LOC, Solo)

**Known Context**:
- New in v2.1.1 (repo-scoped file access with provenance)
- Chunk modes: scan_only, chunk, line_range, page, search
- SHA256 verification, encoding detection
- Integration point with reminders system

**Focus Areas**:
1. **Sub-systems**: Mode routing, chunk handling, provenance tracking, verification
2. **Cross-cutting**: Does this duplicate functionality in manage_docs or other readers?
3. **Token profile**: Multiple read modes = multiple output formats
4. **Contracts**: How does "repo-scoped" get enforced? What fails if path escapes?

**Deliverables**:
- `wiki/tools/read_file.md` (8 sections)
- Token analysis (≥10 samples across all modes)
- Extractable modules with [BUCKET:] tags
- ≥10 Scribe log entries

---

### Agent G: list_projects.py + get_project.py (885 LOC, Paired)

**Known Context** (PRE-IDENTIFIED):
- **TOKEN-001**: list_projects produces 1000+ tokens (target <400 tokens, 60% reduction)
- **DUPLICATION-002**: Doc gathering logic repeated (90-100 LOC, shared with set_project)
- Both tools use ProjectRegistry for lifecycle state
- Both tools format "readable" output with SITREP logic

**Focus Areas**:
1. **Unification opportunity**: What's the contract difference between list vs get?
2. **Token bloat decomposition**: Structural/metadata/duplication/safety in both tools
3. **Registry integration**: How do they use baseline_hashes/current_hashes?
4. **Implicit coupling**: Do these assume set_project has run first?

**Special Directive**:
Your audit will inform BUG-001's correct fix (hash comparison for "new vs existing"). Document exactly how get_project retrieves and uses hash data from ProjectRegistry.

**Deliverables**:
- `wiki/tools/list_projects.md` (8 sections)
- `wiki/tools/get_project.md` (8 sections)
- `wiki/analysis/list_get_unification.md` (comparison analysis)
- Token analysis for BOTH tools (≥10 samples each, 20 total)
- Extractable modules with [BUCKET:] tags
- ≥10 Scribe log entries

---

### Agent H: read_recent.py (586 LOC, Solo)

**Known Context**:
- Filter support (agent, status, emoji)
- Pagination (page, page_size)
- Format routing (readable/structured/compact)
- Current bug: `n` parameter type error (known from prior context)

**Focus Areas**:
1. **Query pattern**: How does this differ from query_entries (Agent C, Wave 1)?
2. **Should these be unified?**: Document boundary between "recent" vs "query"
3. **Filter composition**: Are filters reusable across tools?
4. **Pagination logic**: Duplication with query_entries?

**Deliverables**:
- `wiki/tools/read_recent.md` (8 sections)
- Token analysis (≥10 samples)
- Comparison with query_entries (reference Agent C's work)
- Extractable modules with [BUCKET:] tags
- ≥10 Scribe log entries

---

### Agent I: generate_doc_templates.py (544 LOC, Solo)

**Known Context** (CRITICAL FOR BUG-001):
- **Missing integration**: Does NOT call `ProjectRegistry.record_doc_update()` when creating templates
- **Consequence**: Causes BUG-001 in set_project (can't detect new vs existing via hash comparison)
- Template rendering, Jinja2 integration, YAML frontmatter handling
- Overwrite protection for PROGRESS_LOG.md

**Focus Areas**:
1. **Infrastructure gap**: Document EXACTLY where record_doc_update() SHOULD be called
2. **Template contracts**: What guarantees do templates make to consumers?
3. **Why hash tracking matters**: Explain lifecycle dependency (template → modified → archived)
4. **Jinja vs simple replacement**: When/why is each used?

**Special Directive**:
Your audit completes the BUG-001 analysis. You MUST document:
- Line ranges where hash recording should happen
- What hash should be computed (template content after render)
- Which ProjectRegistry method to call
- What metadata to pass

**Deliverables**:
- `wiki/tools/generate_doc_templates.md` (8 sections)
- `wiki/analysis/template_lifecycle_integration.md` (hash tracking design)
- Token analysis (≥10 samples)
- SPEC-GEN-001: ProjectRegistry integration spec (YAML)
- Extractable modules with [BUCKET:] tags
- ≥10 Scribe log entries

---

## Required Wiki Sections (All Agents)

Every tool wiki page MUST include:

1. **Overview** (purpose, LOC, complexity, relationships to other tools)
2. **Sub-System Breakdown** (distinct responsibilities with line ranges)
3. **Modularization Notes** (extractable modules OR honest coupling assessment)
4. **Implicit Contracts** (assumptions not enforced by code)
5. **Token Analysis** (avg/p95/max + category breakdown)
6. **Error Handling Architecture** (policy vs bug classification)
7. **Known Issues** (bugs with evidence + specs)
8. **Implementation Specs** (YAML format, exact file:line references)

**Template Available**: See Wave 1 examples (append_entry.md, manage_docs.md, query_entries.md)

---

## Cross-Cutting Concerns Discipline

You MUST append to `wiki/analysis/cross_cutting_concerns.md` when you find:

1. **Duplicated patterns** (same logic in 2+ tools)
2. **Token bloat sources** (shared verbosity across tools)
3. **Missing integrations** (infrastructure exists but not wired up)
4. **Implicit assumptions** (contracts not enforced by code)
5. **Parameter proliferation** (20+ param signatures)
6. **Extractable modules** (reusable across tools)

**Gate reminder**:
A Wave 2 agent with zero cross-cutting entries automatically fails gate review unless explicitly justified.

---

## Success Criteria for Wave 2

**You succeed when the Architect agent can answer (without opening .py files)**:

For your tool(s):
- ✅ What contract does this tool expose?
- ✅ What sub-systems does it contain?
- ✅ What's extractable vs intentionally coupled?
- ✅ How does it integrate with monster tools (Wave 1)?
- ✅ What token bloat is structural vs fixable?
- ✅ What errors are policy vs bugs?

For the system:
- ✅ How do medium tools connect to monster tool infrastructure?
- ✅ Where are unification opportunities vs necessary duplication?
- ✅ What module boundaries span multiple complexity tiers?

**You fail when**:
- Your wiki is just a function catalog
- You propose extraction without contract definition
- You skip cross-cutting concerns updates
- You implement fixes instead of documenting architecture

---

## Wave 2 Gates (To Proceed to Wave 3)

Same criteria as Wave 1:
- [ ] All 4 tool wiki pages created (8 sections each)
- [ ] ≥10 Scribe log entries per agent (with reasoning chains)
- [ ] ≥10 token samples per tool (40+ total)
- [ ] All findings tagged with [BUCKET:] identifiers
- [ ] cross_cutting_concerns.md updated by all agents
- [ ] At least 1 YAML implementation spec per agent

---

## Post-Wave 2 Evaluation Plan

After Wave 2 completes, Orchestrator + User will:

1. **Critical review** of ALL Wave 1 + Wave 2 findings
2. **Sanity check** module proposals (merge overlapping buckets?)
3. **Validate** that wiki pages enable Phase 6 work
4. **Decide** whether to adjust Wave 3 strategy based on findings

Your wiki pages are **inputs to that evaluation**. Make them count.

---

## Mindset Enforcement

**Study like an architect**:
- See systems, not functions
- See boundaries, not just lines of code
- See contracts, not just parameters

**Report like a forensic analyst**:
- Evidence required (file:line, repro call, expected vs actual)
- No "seems like" language
- Verifiable claims only

**Leave clean seams for the future**:
- Every finding should enable Phase 6
- Every module candidate should have clear inputs/outputs
- Every implicit contract should be nameable

---

## You Are Building the Operating System Manual

By the time you finish, someone should be able to **redesign Scribe's architecture** using only your wiki pages.

That's the standard. Anything less is archaeology, not architecture.

---

**Green light for Wave 2 deployment when Orchestrator receives user approval.**
