---
id: council_bootstrap_skill-architecture
title: "\U0001F3D7\uFE0F Architecture Guide \u2014 council_bootstrap_skill"
doc_type: architecture
doc_name: architecture
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 19:08:18 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🏗️ Architecture Guide — council_bootstrap_skill
**Author:** Scribe
**Version:** Draft v0.1
**Status:** Draft
**Last Updated:** 2026-02-22 18:46:32 UTC

> Architecture guide for council_bootstrap_skill.

---
## 1. Problem Statement
<!-- ID: problem_statement -->
- **Context:** New users initializing a council (`council init`) get either an empty roster or a standard preset of 8 generic agents. There is no guided process to customize the roster for their specific project — they must read docs, understand all fields, and write YAML by hand.

- **Goals:**
  - Create an interactive, checkpoint-gated workflow skill that guides users from zero to a fully configured, project-specific agent roster
  - Deploy Lens research swarm to analyze the target codebase before designing agents
  - Produce complete, field-populated YAML templates the user can customize (not fill-in-the-blank)
  - End with a validated, imported, and verified roster via `council roster import && council update`

- **Non-Goals:**
  - Runtime automation (this is a guide document, not executable code)
  - Web UI integration (CLI-only workflow)
  - Modifying the skill generation pipeline itself

- **Success Metrics:**
  - Skill renders via `council update --dry-run` without errors
  - Frontmatter uses the standard 4-field format (name, description, user-invocable, context)
  - All YAML examples pass `validate_roster()` validation
  - Template uses `{?% raw %}` blocks correctly for all Jinja2 syntax in YAML examples
<!-- ID: requirements_constraints -->
- **Functional Requirements:**
  - 5-phase interactive workflow with user checkpoints between each phase
  - Phase 1 deploys parallel Lens research swarm (3-5 agents via Teams)
  - Phase 2 produces complete YAML agent definitions for all 5 mandatory archetypes + coordinator
  - Phase 3 proposes additional project-specific agents based on research findings
  - Phase 4 assembles final roster.yaml, runs embedded validation, writes file
  - Phase 5 applies via CLI commands and verifies round-trip integrity

- **Non-Functional Requirements:**
  - ~800 lines total (matching density of existing skills: code block every 31-89 lines)
  - All YAML containing `{{` or `{%` wrapped in `{% raw %}...{% endraw %}`
  - Standard 4-field frontmatter only (name, description, user-invocable, context)
  - Template variables used: `{{ repo_root }}` for path references

- **Assumptions:**
  - User has already run `council init` (`.council/` directory exists)
  - User is running as Atlas or has coordinator-level access
  - Lens agents are available for research (haiku model accessible)

- **Risks & Mitigations:**
  - **Risk:** YAML examples with Jinja2 syntax break template rendering → **Mitigation:** Every YAML block with `{{`/`{%` gets `{% raw %}` wrapping; verified in acceptance tests
  - **Risk:** Skill is too long, exceeds context limits → **Mitigation:** Target 800 lines with dense formatting; appendix tables compress reference material
  - **Risk:** Users skip checkpoints → **Mitigation:** Each phase ends with explicit "CHECKPOINT: [instruction]" markers
<!-- ID: architecture_overview -->
### Single-File Deliverable

The entire skill is ONE file: `.council/templates/skills/bootstrap-council/SKILL.md.j2`

This file renders to `.claude/skills/bootstrap-council/SKILL.md` and `.codex/skills/bootstrap-council/SKILL.md` via `council update`.

### Document Structure (Section-by-Section Blueprint)

| Section | Lines (est.) | Purpose | Code Blocks |
|---------|-------------|---------|-------------|
| **Frontmatter** | 1-6 | Standard 4-field YAML frontmatter | 0 |
| **Title + Overview** | 7-25 | What this skill does, when to use it, prerequisites | 0 |
| **Phase 0: Pre-Flight** | 26-65 | Verify `.council/` exists, check existing roster, confirm with user | 2 (bash checks) |
| **Phase 1: Research Swarm** | 66-195 | Deploy 3-5 Lens agents in parallel, template prompts for each area | 5 (team deploy, Lens prompts) |
| **Phase 2: Orchestrator Design** | 196-290 | Design coordinator agent with complete YAML template | 1 (full YAML block in raw) |
| **Phase 3: Core Archetypes** | 291-530 | 5 mandatory agent types with complete YAML templates | 5 (one per archetype in raw) |
| **Phase 4: Project-Specific Agents** | 531-600 | Propose extra agents based on research, YAML template | 1 (generic template in raw) |
| **Phase 5: Assembly & Validation** | 601-700 | Assemble roster.yaml, run validation checklist, write file | 3 (assembly, validation, CLI) |
| **Phase 6: Apply & Verify** | 701-760 | CLI commands, round-trip verification, Scribe logging | 2 (CLI, verification) |
| **Appendix A: Field Reference** | 761-800 | Required fields, valid enums, model selection guide | 2 (tables) |
| **TOTAL** | **~800** | | **~21 code blocks** |

### Checkpoint Design Pattern

Every phase ends with a checkpoint block:

```
> **CHECKPOINT**: [Action required from user]
> Present [summary] and ask the user to confirm before proceeding.
> If the user wants changes, iterate on [specific aspect] before moving on.
```

This is the FIRST workflow/interactive skill. All 8 existing skills are reference docs. The checkpoint pattern is the key differentiator.

### Raw Block Strategy

YAML examples containing Jinja2 syntax MUST use raw blocks. The pattern:

```
{actual template syntax}
{% raw %}
```yaml
agents:
  - name: {{ agent_name }}
    identity_prompt: |
      You are {{ agent_display_name }}...
```
{% endraw %}
{resume template syntax}
```

Note: Standard YAML examples WITHOUT `{{`/`{%` do NOT need raw blocks.

### Template Variable Usage

From `generate_skills()` lines 2243-2249, these variables are available:
- `orchestrator` — coordinator agent object (has `.name`, `.display_name`, `.title`)
- `agents` — list of all agents  
- `repo_root` — repository root path string
- `timestamp` — generation timestamp
- `skill_slug` — "bootstrap-council"
- `skill_template_path` — source template relative path

The skill should use `{{ repo_root }}` for file path references (e.g., "Edit `{{ repo_root }}/.council/roster.yaml`").
<!-- ID: detailed_design -->
### Phase 0: Pre-Flight Check (~40 lines)

**Content:**
1. Bash command to verify `.council/` exists and has `council.yaml`
2. Bash command to count existing agents in `roster.yaml` (if any)
3. Decision tree: if roster has >1 agent, warn user this will replace their roster
4. CHECKPOINT: Confirm user wants to proceed

**Key code blocks:**
```bash
# Check prerequisites
ls -la .council/council.yaml
# Count existing agents (0 = fresh init, >1 = existing roster)
grep -c "^  - name:" .council/roster.yaml 2>/dev/null || echo "0"
```

### Phase 1: Codebase Research Swarm (~130 lines)

**Content:**
1. Explanation of why research comes first (agents are designed FOR the codebase)
2. Team deployment instructions using Claude Code Teams
3. 5 research area templates with specific prompts:

| Research Area | Lens Prompt Focus | Why It Matters |
|---------------|-------------------|----------------|
| **Project Structure** | Directory layout, entry points, build system | Determines which agents need file access |
| **Tech Stack** | Languages, frameworks, dependencies, DB | Informs domain selection and tool restrictions |
| **Testing** | Test framework, coverage, patterns | Determines if dedicated test agent needed |
| **API/Integration** | External APIs, protocols, auth patterns | Informs security/integration agent needs |
| **Domain Concepts** | Business logic, key abstractions | Shapes agent identity prompts and expertise |

4. Template for each Lens deployment prompt (reusable pattern)
5. CHECKPOINT: Review research findings summary before designing agents

**Key pattern for Lens prompts:**
```
Research Area: [area]
Scope: [what to investigate]
Output: Summary of findings relevant to agent design
Focus on: What capabilities an agent would need to work in this area
```

### Phase 2: Orchestrator Design (~95 lines)

**Content:**
1. Guidance on naming the coordinator (project-themed vs generic)
2. What makes a good coordinator identity_prompt
3. COMPLETE starter YAML for coordinator agent with ALL fields populated

**The coordinator YAML template (inside {% raw %} block):**
- name: user-chosen-name
- display_name, title, description: filled with guidance comments
- model: inherit
- council_role: coordinator
- can_delegate: true
- domains: orchestration, coordination, planning + project-specific
- identity_prompt: 6-line template with project context slots
- expertise_prompt: 5-item bullet list of coordinator skills
- behavioral_guidelines: 7 items covering delegation, logging, protocol
- No disallowed_tools (coordinator needs everything)

4. CHECKPOINT: User reviews and customizes coordinator before proceeding

### Phase 3: Core Archetypes (~240 lines, ~48 lines each)

**Content for each of the 5 mandatory archetypes:**

Each archetype section includes:
1. One-paragraph role description and when to deploy
2. COMPLETE starter YAML with ALL fields populated (inside {% raw %} block)
3. Key customization guidance (what to change for their project)

**Archetype 1: Researcher (Lens analog)**
- model: haiku (cost-effective for high-volume research)
- disallowed_tools: [Write, Edit] (read-only by design)
- domains: research, investigation, documentation + project-specific
- identity_prompt: focused on investigation, evidence gathering
- expertise_prompt: codebase exploration, documentation, cross-referencing

**Archetype 2: Architect (Blueprint analog)**
- model: opus (deep reasoning for design decisions)
- disallowed_tools: [Edit] (designs, doesn't implement)
- domains: architecture, system-design, phase-planning + project-specific
- identity_prompt: focused on system design, trade-off analysis
- expertise_prompt: architecture, API design, task packaging

**Archetype 3: Implementer (Forge analog)**
- model: sonnet (standard implementation)
- No disallowed_tools (needs full access)
- domains: implementation, coding, refactoring + project-specific
- identity_prompt: focused on executing task packages precisely
- expertise_prompt: code quality, test writing, incremental delivery

**Archetype 4: Reviewer (Arbiter analog)**
- model: sonnet
- council_role: auditor
- disallowed_tools: [Write, Edit] (review-only)
- domains: code-review, quality-gates, standards-enforcement + project-specific
- identity_prompt: adversarial review, quality gatekeeper
- expertise_prompt: code review, security audit, standards compliance

**Archetype 5: Debugger (Mantis analog)**
- model: sonnet
- No disallowed_tools (needs full access for investigation)
- domains: debugging, bug-hunting, root-cause-analysis + project-specific
- identity_prompt: root cause analysis, minimal surgical fixes
- expertise_prompt: debugging, log analysis, reproduction, fix verification

Each archetype YAML is complete and validated — user customizes FROM a working base.

### Phase 4: Project-Specific Agents (~70 lines)

**Content:**
1. Decision framework for additional agents based on research findings:

| Research Signal | Suggested Agent | Example |
|-----------------|-----------------|---------|
| Complex security/auth | Security Analyst | Sentinel |
| Extensive test suite | Test Engineer | Crucible |
| Multiple external APIs | Integration Specialist | — |
| Domain-specific logic | Domain Expert | — |
| ML/AI components | ML Engineer | — |
| Documentation gaps | Technical Writer | — |

2. Generic agent YAML template (inside {% raw %} block) with placeholder comments
3. Guidance: most projects need 6-8 agents total. More than 10 is usually too many.
4. CHECKPOINT: User confirms final agent list

### Phase 5: Assembly & Validation (~100 lines)

**Content:**
1. Complete roster.yaml structure with defaults section:
```yaml
defaults:
  model: sonnet
  council_role: specialist
  memory_config:
    visibility: private
    default_strength: 0.5

agents:
  # [all agent definitions assembled here]
```

2. Embedded validation checklist (mirrors validate_roster() logic):
- [ ] Every agent has `name` (string, unique, lowercase-with-hyphens)
- [ ] Every agent has `domains` (list, at least one entry)
- [ ] At least one agent has `council_role: coordinator`
- [ ] All `model` values are valid: haiku, sonnet, opus, inherit
- [ ] All `council_role` values are valid: coordinator, specialist, auditor, omniscient
- [ ] No duplicate agent names
- [ ] Every agent has `identity_prompt` (warning-level, but strongly recommended)
- [ ] Every agent has `expertise_prompt` (warning-level, but strongly recommended)

3. Write command:
```bash
# Write the assembled roster to disk
# (Atlas writes the file, user confirms)
```

4. Dry-run verification:
```bash
council update --dry-run
```

5. CHECKPOINT: User reviews dry-run output and confirms

### Phase 6: Apply & Verify (~60 lines)

**Content:**
1. Import to database:
```bash
council roster import
```

2. Generate agent cards:
```bash
council update
```

3. Verify generated files:
```bash
ls -la .claude/agents/
council roster list
```

4. Round-trip integrity check:
```bash
council roster export --force
council roster status
```

5. Scribe logging (if in a project context):
```python
append_entry(agent="atlas", message="Council roster bootstrapped with N agents",
    status="success", meta={"agents": ["list", "of", "slugs"]})
```

6. CHECKPOINT: Final verification — user confirms everything looks correct

### Appendix A: Field Reference (~40 lines)

Compressed reference tables:

**Required Fields:**
| Field | Type | Validation |
|-------|------|-----------|
| `name` | string | Non-empty, unique, lowercase with hyphens |
| `domains` | list[string] | At least one entry |

**Recommended Fields:**
| Field | Type | Notes |
|-------|------|-------|
| `title` | string | One-line role description |
| `description` | string | When to use this agent |
| `model` | enum | haiku/sonnet/opus/inherit |
| `council_role` | enum | coordinator/specialist/auditor/omniscient |
| `identity_prompt` | markdown | First-person agent identity |
| `expertise_prompt` | markdown | Bullet list of skills |

**Model Selection Guide:**
| Model | Cost | Use For | Example Agents |
|-------|------|---------|----------------|
| haiku | Low | High-volume research, scanning | Researcher |
| sonnet | Medium | Implementation, review, testing | Implementer, Reviewer, Debugger |
| opus | High | Architecture, complex reasoning | Architect |
| inherit | Parent | Coordinator (uses caller's model) | Orchestrator |
<!-- ID: directory_structure -->
```
.council/templates/skills/bootstrap-council/
  SKILL.md.j2              # THE deliverable — single Jinja2 template

Renders to (via `council update`):
  .claude/skills/bootstrap-council/SKILL.md
  .codex/skills/bootstrap-council/SKILL.md
```

**Key source files referenced by the skill:**
```
.council/roster.yaml                          # Target output file
.council/council.yaml                         # Verified in pre-flight
src/council_mcp/agents/generate.py            # validate_roster() at lines 799-890
src/council_mcp/agents/roster_templates/      # standard.yaml preset for reference
src/council_mcp/templates/claude/council_member.md.j2  # How agents get rendered
```
<!-- ID: data_storage -->
- **Datastores:** ['Filesystem markdown', 'SQLite mirror']
- **Indexes & Performance:** FTS for sections
- **Migrations:** Sequential migrations tracked in storage layer


---
## 7. Testing & Validation Strategy
<!-- ID: testing_strategy -->
- **Template Rendering Test:** `council update --dry-run` must succeed with the new skill template present
- **Raw Block Verification:** Rendered output must contain literal `{` characters (not interpreted as Jinja2)
- **Frontmatter Validation:** Generated SKILL.md must start with valid YAML frontmatter (4 fields)
- **Existing Test Compatibility:** `pytest tests/test_skill_packages.py -v` must still pass (if exists)
- **Manual QA:** Invoke `/bootstrap-council` in a Claude Code session to verify the workflow renders correctly
<!-- ID: deployment_operations -->
- **Environments:** Local development
- **Release Process:** Git commits drive deployment
- **Configuration Management:** Project-specific .scribe settings
- **Maintenance & Ownership:** Doc management team


---
## 9. Open Questions & Follow-Ups
<!-- ID: open_questions -->
| Item | Owner | Status | Notes |
|------|-------|--------|-------|
| Should templates support conditionals per phase? | Docs Lead | TODO | Evaluate after initial rollout. |
Close each question once answered and reference the relevant section above.


---
## 10. References & Appendix
<!-- ID: references_appendix -->
- PROGRESS_LOG.md
- ARCHITECTURE_GUIDE.md

Generated via generate_doc_templates.


---