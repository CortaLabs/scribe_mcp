# Wave 1 Mindset Brief: Study Like an Architect, Report Like a Forensic Analyst

**For Agents**: A-AppendEntry, B-ManageDocs, C-QueryEntries, D-RotateLog, E-SetProject

---

## Your Mission

You are **not** debugging a tool. You are **mapping a system**.

Monster files (>1,000 LOC) are **bundles of concerns** that evolved organically. Your job is to:

1. **Identify distinct responsibilities** inside the file
2. **Name them clearly** (parsing vs validation vs execution, formatting vs persistence vs indexing)
3. **Document where boundaries should exist** (but don't code them)
4. **Map seams for future modularization** (Phase 6 uses your work)

---

## Think in Sub-Systems, Not Functions

**Bad audit**: "append_entry is 2,357 LOC, very complex"

**Good audit**: "append_entry contains 5 distinct sub-systems:
- Parameter validation & healing (lines 50-200)
- Bulk vs single mode routing (lines 201-400)
- Database mirroring (lines 401-600)
- Vector indexing (lines 601-750)
- Response formatting (lines 751-900)

**Boundary violations**: Formatting logic calls DB directly (line 820), vector indexing mutates parameters (line 650)"

---

## Flag Extractable Modules (No Coding)

When you see logic that:
- Appears in 2+ tools
- Has clear inputs/outputs
- Could be reused elsewhere

Create **candidate module note** in `cross_cutting_concerns.md`:

```markdown
### Candidate Module: LogEntryFormatter [BUCKET:formatting]
- Origin: append_entry.py:751-900, list_projects.py:200-350
- Responsibilities: Convert internal data to readable/structured/compact formats
- Used by: append_entry, list_projects, get_project, read_recent
- Why it should be shared: All tools need 3-way format routing
- Risks if extracted: Tools may have subtle format differences
- Before/After: Before = formatting mixed with business logic in each tool. After = single source of truth for output formatting, tools focus on data preparation only.
```

**You Are Allowed to Say NO**:

Sometimes the right answer is:

```markdown
### NOT a Candidate Module: <LogicName>
- Why it should NOT be modularized: Tightly coupled to tool-specific invariants, extraction would break contracts
- Evidence of coupling: [specific examples]
```

**Modularity is about clarity, not purity.** Honest coupling documentation is more valuable than forced extraction.

---

## Unification > De-Duplication

**Not this**: "Found duplicate code in 3 files, should delete 2 copies"

**This**: "Found 3 variants of doc gathering logic:
- set_project: Checks ARCHITECTURE_GUIDE + PHASE_PLAN + CHECKLIST + counts lines + detects custom content
- list_projects: Same checks but different return shape (dict vs object)
- get_project: Same checks + adds doc hash tracking

**Unification opportunity**: Extract base contract `DocInventoryGatherer` [BUCKET:metadata] that all 3 can use. Variants exist because each tool evolved separately, not because they need different logic.

**Before/After Mental Model**:
- Before: 3 responsibilities mixed (doc checking + line counting + hash tracking) in each tool
- After: Single `DocInventoryGatherer` handles invariant checks, tools adapt results to their needs
- Conceptual win: Tools reason about 'get doc status' not 'check files + count lines + hash content'"

---

## Be Ruthless About Implicit Contracts

Document assumptions that aren't enforced by code:

- "Assumes set_project has already run" (no check, silent failure if not)
- "Silently mutates session state" (side effect not visible in signature)
- "Only works if logs exist" (no guard, throws cryptic error)
- "This branch is never hit unless X flag is passed" (dead code?)

**Implicit contracts are where modularization breaks.**

**Watch for Configuration Gravity**:

Monster files love to absorb config logic. Flag when you see:
- Config objects passed everywhere [BUCKET:config]
- Defaults that mutate behavior implicitly
- Validation mixed with execution
- "If this flag, then this completely different code path"
- We have a config system! Do not bypass it .scribe/config

These are **prime module boundaries** - config handling wants to be separate from business logic.

---

## Token Output = Design Smell

When measuring tokens, categorize verbosity:

**Structural** (tables, headers, boxes):
- Example: list_projects table header consumes 50 tokens
- Action: Could be optional in compact mode

**Metadata** (IDs, timestamps, reminders):
- Example: Every response includes full project path + 3 reminder checks
- Action: Reminder system could be factored out

**Duplication** (repeated blocks):
- Example: Same "📁 Location:" block in 5 different responses
- Action: Shared template fragment

**Safety padding** ("just in case" messages):
- Example: 200-token explanation of what empty state means
- Action: Move to docs, keep response minimal

**Call out which parts**:
- Belong in "compact" (essential data only)
- Belong in "structured" (full metadata)
- Should maybe not exist at all (redundant warnings)

---

## Error Handling = Architecture

Error paths are **contract surfaces**, not just exception handlers.

If an error path:
- Logs something
- Mutates state
- Retries operation
- Swallows exception
- Rewrites parameters

...it is **not just an error handler**, it's a **policy decision**.

Find and document:

**Silent failures** [BUCKET:error_handling]:
- `except Exception: pass` (no logging)
- Fallback values without warnings
- State corruption on partial failure

**Escalation patterns**:
- Which errors bubble up?
- Which get swallowed?
- Which mutate state then fail?

**Heal and continue logic**:
- Parameter healing (auto-corrects bad inputs)
- Default value insertion
- Partial success handling

These are **architectural decisions**, not bugs. Document:
- What fails quietly (and why that's allowed)
- What escalates (and what the caller is expected to do)
- What mutates state after partial failure (and whether that's safe)

**Policy decisions often deserve their own module** - error recovery logic is reusable.

---

## Stay Read-Only, But Think Forward

**You are NOT implementing.**

**You ARE laying out**:
- What should be separate (sub-system boundaries)
- What should be shared (candidate modules)
- What should be optional (feature flags, modes)
- What should be core (invariants, contracts)

Every insight should end in:

> "This would be easier to reason about if X were isolated."

---

## Required Wiki Sections

Every monster tool wiki page must include:

1. **Overview** (purpose, LOC, complexity)
2. **Sub-System Breakdown** (distinct responsibilities with line ranges)
3. **Modularization Notes** (extractable modules, unification opportunities)
4. **Implicit Contracts** (assumptions not enforced by code)
5. **Token Analysis** (avg/p95/max + verbosity categorization)
6. **Error Handling Architecture** (silent failures, escalation, heal-continue)
7. **Known Issues** (bugs with evidence)
8. **Implementation Specs** (YAML format, exact file/line references)

---

## Success Criteria

**You succeed when**:
- Phase 6 Architect can design refactoring without re-reading your tool
- Your wiki page explains not just "what is" but "what should be"
- Your modularization notes have clear boundaries (inputs/outputs/responsibilities)
- Your token analysis reveals **why** output is large, not just that it is
- Your implicit contracts list would make a good test suite

**You fail when**:
- Your wiki is just a function catalog
- You propose code changes instead of describing seams
- You skim instead of studying
- You miss the extractable modules that agents B/C/D also find

---

## Mindset

**Study like an architect.**
- See systems, not functions
- See boundaries, not just lines of code
- See contracts, not just parameters

**Report like a forensic analyst.**
- Evidence required (file:line, repro call, expected vs actual)
- No "seems like" language
- Verifiable claims only

**Leave clean seams for the future.**
- Every finding should enable Phase 6
- Every module candidate should have clear inputs/outputs
- Every implicit contract should be nameable

---

**Don't code. Don't skim. Map the architecture.**

This is how good audits become great refactorings.
