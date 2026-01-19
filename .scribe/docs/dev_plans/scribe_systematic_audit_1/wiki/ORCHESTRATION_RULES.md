# Orchestration Rules - Post Wave 1 Enforcement

**Date**: 2026-01-05
**Authority**: User + Orchestrator
**Context**: Lessons from Wave 1 corrections and architectural insights

---

## Mission Statement

You are no longer "auditing Scribe." You are **reverse-engineering its operating system**.

By Phase 6, the Architect agent must answer these questions **without opening a single .py file**:
- Where project truth lives
- How parameters enter the system
- How errors are classified
- How tokens are produced
- Which subsystems are reusable
- Which are intentionally coupled

---

## 1. Lock the Mental Model: "Module = Contract, Not Folder"

**Rule for all future agents (Waves 2/3):**

> A module is only real if you can describe:
> - **Inputs**: What data enters
> - **Outputs**: What data exits
> - **Failure policy**: What happens on error
> - **Who owns state**: Mutability boundaries

If an agent proposes "extract X" without answering those four, the finding is **INCOMPLETE**.

**Why This Works**: `ParameterHealer`, `DocInventoryGatherer`, and `ErrorPolicy` proposals from Wave 1 define *policy*, not just helpers. That's the standard.

---

## 2. Force "Before/After" at the System Level (Not Per Function)

**Bad (REJECT)**:
> "This removes ~90 LOC duplication."

**Good (ACCEPT)**:
> "Before: three tools independently decide what 'project state' means.
> After: a single inventory contract defines project truth; tools only render it."

**Example**: Wave 1's BUG-001 correction only worked because someone stepped back and asked *what the system thinks "new project" means* instead of patching a condition.

**That's the bar now.**

---

## 3. Modularization Is Optional — Truth Is Mandatory

**Agents are allowed to say "NO, this should stay coupled."**

**But if an agent says NO, they MUST document**:
- What invariant would break if extracted
- What state leaks across boundaries
- Why config adapters wouldn't fix it

**Example**: `set_project` config normalization is correct non-modularization. That's not failure—that's architectural honesty.

---

## 4. Treat Token Bloat as a Cross-Cutting System, Not Tool Bugs

**Directive**: No future agent is allowed to say "this tool is verbose" without tagging:
- **Structural** (tables, headers, boxes)
- **Metadata** (IDs, timestamps, reminders)
- **Duplication** (repeated blocks)
- **Safety padding** ("just in case" messages)

Those categories already exist and are working. Phase 6 should be able to design:
- One formatter system
- One reminder emission policy
- One compact/structured/readable router

**If token findings aren't aggregatable, they're noise.**

---

## 5. Storage & Error Handling Are Policy Layers — Keep Them Unified

**Two Critical Truths from Wave 1**:
1. Silent DB failure is **intentional policy** (best-effort registry updates)
2. Atomicity failures are **system bugs**, not edge cases (rotate_log P0)

**Directive to agents**:
- If an error is swallowed → document *why* (policy decision)
- If partial failure corrupts state → escalate P0 immediately (system bug)

**Phase 6 Should End With**:
- One `AtomicFileWriter`
- One `ErrorPolicy` contract
- One persistence coordinator contract

Anything else is regression.

---

## 6. Enforce Bucket Discipline Ruthlessly

The bucket system is working. Don't let it degrade.

**Rules**:
- Every proposed module **MUST** map to exactly one primary bucket
- Secondary buckets allowed, but one owner
- If two agents propose the same bucketed module independently → **priority extraction**

**This prevents**: Ad-hoc utils sprawl
**This enables**: Intentional subsystems instead of a junk drawer

---

## 7. Orchestrator-Specific Enforcement Rules

**Non-Negotiable**:

1. **No concurrency between architectural synthesis and research**
   - Let Wave 2 finish before anyone starts "planning fixes"

2. **Stop waves immediately on P0**
   - rotate_log atomicity violation proved why

3. **Cross-cutting concerns > tool docs**
   - If agents aren't appending to cross_cutting_concerns.md, they're failing the phase

4. **Do not normalize bad findings**
   - Agent E's initial BUG-001 analysis was wrong; correction was the right call
   - Keep that standard

---

## 8. Phase 6 Success Criteria

By the time Phase 6 starts, the Architect agent should be able to answer **without opening a single `.py` file**:

- ✅ Where project truth lives
- ✅ How parameters enter the system
- ✅ How errors are classified
- ✅ How tokens are produced
- ✅ Which subsystems are reusable
- ✅ Which are intentionally coupled

**Wave 1 already set this up beautifully. Don't let later waves dilute it.**

---

## Agent Mindset Enforcement

If future agents:
- ✅ Think in contracts
- ✅ Respect policy vs bug boundaries
- ✅ Aggregate findings across tools
- ✅ Resist premature modularization

Then Phase 6 will be **design, not archaeology**.

---

## Next Steps

**Options for Orchestrator**:
1. Draft **Wave 2 agent briefing** tuned to medium tools
2. Outline **Phase 6 extraction order** based on impact vs risk
3. Sanity-check whether any Wave 1 module proposals should be **merged** before extraction

**Current Status**: Wave 1 correction documented, ready for Wave 2 deployment with enhanced guidance.
