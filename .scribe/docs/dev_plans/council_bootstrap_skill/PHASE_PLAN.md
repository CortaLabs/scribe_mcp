---
id: council_bootstrap_skill-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_bootstrap_skill"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 19:09:26 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_bootstrap_skill
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-22 18:46:32 UTC

> Execution roadmap for council_bootstrap_skill.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Confidence (0-1) |
|-------|------|------------------|------------------|
| Phase 1 — Write SKILL.md.j2 | Create the complete bootstrap-council skill template | Single file: `.council/templates/skills/bootstrap-council/SKILL.md.j2` (~800 lines) | 0.95 |
| Phase 2 — Verify & Ship | Validate rendering, run tests, confirm dry-run | `council update --dry-run` passes, rendered output correct | 0.95 |

This is a single-task-package project. One Forge session writes the file, one verification pass confirms it.
<!-- ID: phase_0 -->
**Objective:** Write the complete bootstrap-council SKILL.md.j2 template file.

**Scope:** Single file creation at `.council/templates/skills/bootstrap-council/SKILL.md.j2`

**Files to Create:**
- `.council/templates/skills/bootstrap-council/SKILL.md.j2` (NEW — ~800 lines)

**Files to NOT Modify:**
- Any existing skill templates
- `generate.py` (no changes needed — skill auto-discovered)
- `roster.yaml` (not related)
- Any other source code

**Specifications:**

The file MUST follow the architecture in ARCHITECTURE_GUIDE.md section "Detailed Design" exactly. Here is the precise structure:

**1. Frontmatter (lines 1-6)**
```yaml
---
name: bootstrap-council
description: Interactive workflow for bootstrapping a full Council agent roster from codebase research
user-invocable: true
context: full
---
```

**2. Title + Overview (lines 7-25)**
- H1: "Bootstrap Council — Interactive Roster Creation"
- One-paragraph summary: what this skill does
- Prerequisites list: `council init` completed, `.council/` exists
- Note: "This is an interactive workflow. Follow each phase in order."

**3. Phase 0: Pre-Flight Check (lines 26-65)**
- H2: "Phase 0: Pre-Flight Check"
- Bash code block: verify `.council/council.yaml` exists
- Bash code block: count agents in existing roster
- Conditional guidance: fresh vs existing roster
- Checkpoint block (blockquote format)

**4. Phase 1: Codebase Research Swarm (lines 66-195)**
- H2: "Phase 1: Codebase Research"
- Explanation paragraph: why research before agent design
- H3 for each research area (5 total): Project Structure, Tech Stack, Testing Patterns, API & Integration, Domain Concepts
- Each area: 1-2 sentence scope + specific prompt template for Lens
- Team deployment code block showing how to spin up parallel Lens agents
- Checkpoint block: present research summary to user

**5. Phase 2: Design the Orchestrator (lines 196-290)**
- H2: "Phase 2: Design Your Orchestrator"
- Guidance paragraphs on coordinator naming, personality, scope
- COMPLETE coordinator YAML template inside `{% raw %}...{% endraw %}` block — ALL fields populated with sensible defaults and inline YAML comments explaining each field
- Customization notes: what to change based on project
- Checkpoint block

**6. Phase 3: Core Agent Archetypes (lines 291-530)**
- H2: "Phase 3: Core Archetypes"
- Brief intro: every council needs these 5 roles
- H3 for each archetype: Researcher, Architect, Implementer, Reviewer, Debugger
- Each: 2-3 sentence role description + COMPLETE YAML template inside `{% raw %}...{% endraw %}` block + 2-3 customization notes
- Each YAML has: name, display_name, title, description, model, council_role (if non-default), domains, disallowed_tools (if applicable), identity_prompt, expertise_prompt, behavioral_guidelines
- Checkpoint block after all 5

**7. Phase 4: Project-Specific Roles (lines 531-600)**
- H2: "Phase 4: Project-Specific Agents"
- Decision table: research signal → suggested agent type
- Generic agent YAML template inside `{% raw %}...{% endraw %}` block
- Guidance: target 6-8 total agents
- Checkpoint block

**8. Phase 5: Assemble & Validate (lines 601-700)**
- H2: "Phase 5: Assemble & Validate"
- Complete roster.yaml skeleton with defaults section (regular YAML, no raw needed since no `{{`)
- Validation checklist (8 items mirroring validate_roster())
- Write-to-disk instruction
- `council update --dry-run` command
- Checkpoint block

**9. Phase 6: Apply & Verify (lines 701-760)**
- H2: "Phase 6: Apply & Verify"
- Sequential CLI commands: `council roster import` → `council update` → `council roster list` → `council roster export --force` → `council roster status`
- Scribe logging code block
- Final checkpoint

**10. Appendix (lines 761-800)**
- H2: "Appendix: Quick Reference"
- Required Fields table (2 rows)
- Recommended Fields table (8 rows)  
- Model Selection Guide table (4 rows)

**Critical Implementation Rules for Forge:**

1. **{% raw %} blocks**: Every YAML code block that contains `{{` or `{%` MUST be wrapped. Count them: there should be exactly 7-8 raw blocks (coordinator + 5 archetypes + 1 generic template + possibly research prompt templates).

2. **Use `{{ repo_root }}`**: For any file path reference to the repository, use the template variable. Example: "Edit `{{ repo_root }}/.council/roster.yaml`"

3. **Checkpoint format**: Use this exact blockquote pattern:
```
> **CHECKPOINT**: [Brief description of what to review]
>
> [1-2 sentences about what to present to the user and what decisions they need to make]
```

4. **YAML template quality**: Every archetype YAML must be COMPLETE and VALID. A user should be able to copy any single archetype YAML block, paste it into a roster.yaml, and have it pass `validate_roster()`. The identity_prompt and expertise_prompt must be thoughtful, not generic placeholders.

5. **Line count**: Target 780-820 lines. Do NOT pad with empty lines or verbose prose. Dense, actionable content.

6. **No Jinja2 template logic**: The SKILL.md.j2 should be almost entirely static content. The only template variables used should be `{{ repo_root }}` for path references. No loops, no conditionals, no agent iteration. This is a reference document, not a dynamic template.

**Acceptance Criteria:**
- [ ] File exists at `.council/templates/skills/bootstrap-council/SKILL.md.j2`
- [ ] `council update --dry-run` succeeds with the file present
- [ ] Rendered output at `.claude/skills/bootstrap-council/SKILL.md` contains literal `{{` characters in YAML examples (raw blocks working)
- [ ] Frontmatter has exactly 4 fields: name, description, user-invocable, context
- [ ] File is 750-850 lines
- [ ] Contains exactly 7 phase sections (Phase 0 through Phase 6) plus Appendix
- [ ] Each phase ends with a CHECKPOINT blockquote
- [ ] All YAML blocks with Jinja2 syntax are wrapped in raw blocks

**Deliverables:**
- Single file: `.council/templates/skills/bootstrap-council/SKILL.md.j2`

**Dependencies:** None — this is the first and only implementation task.

**Notes:** Do NOT create any other files. Do NOT modify generate.py. The skill is auto-discovered from the templates directory by `generate_skills()`. Do NOT register it anywhere.
<!-- ID: phase_1 -->
**Objective:** Verify the skill renders correctly and passes all checks.

**Verification Steps:**

1. Run template rendering:
```bash
council update --dry-run
```
Expect: no errors, skill listed in generated output

2. Apply and check rendered output:
```bash
council update
cat .claude/skills/bootstrap-council/SKILL.md | head -10
```
Expect: frontmatter intact, content rendered

3. Verify raw blocks worked:
```bash
grep -c '{' .claude/skills/bootstrap-council/SKILL.md
```
Expect: >0 (literal `{` present in YAML examples)

4. Run existing tests:
```bash
pytest tests/test_skill_packages.py -v 2>/dev/null || echo "No skill test file"
pytest tests/test_council_update.py -v
```
Expect: all tests pass

**Acceptance Criteria:**
- [ ] `council update --dry-run` succeeds
- [ ] Rendered SKILL.md exists in both `.claude/skills/` and `.codex/skills/`
- [ ] Raw blocks produce literal `{` in output
- [ ] All existing tests pass
<!-- ID: milestone_tracking -->
| Milestone | Target Date | Owner | Status | Evidence/Link |
|-----------|-------------|-------|--------|---------------|
| Architecture complete | 2026-02-22 | Blueprint | In Progress | ARCHITECTURE_GUIDE.md |
| SKILL.md.j2 written | 2026-02-22 | Forge | Pending | Task #4 |
| Verification passed | 2026-02-22 | Atlas | Pending | Task #5 |
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---