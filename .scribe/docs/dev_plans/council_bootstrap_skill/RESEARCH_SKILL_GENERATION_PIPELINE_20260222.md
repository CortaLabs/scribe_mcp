---
id: council_bootstrap_skill-research-skill-generation-pipeline-20260222
title: "\U0001F52C Research: Skill Generation Pipeline End-to-End"
doc_type: RESEARCH_SKILL_GENERATION_PIPELINE_20260222
doc_name: RESEARCH_SKILL_GENERATION_PIPELINE_20260222
category: research
status: draft
version: '0.1'
last_updated: 2026-02-22 18:51:44 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# 🔬 Research: Skill Generation Pipeline End-to-End

**Author:** Lens  
**Project:** council_bootstrap_skill  
**Date:** 2026-02-22  
**Scope:** Comprehensive pipeline from discovery to DB sync

---

## Executive Summary

The skill generation pipeline is a **manifest-managed, two-target system** that discovers `.j2` templates in `.council/templates/skills/`, renders them to both `.claude/skills/` and `.codex/skills/`, and then syncs the generated SKILL.md files to the database. The system uses YAML frontmatter for metadata, maintains a manifest for safe stale-file pruning, and includes automatic schema normalization.

**Key Finding:** Skill sync is non-blocking (non-fatal errors are silently logged) and occurs AFTER file generation during the `council update` CLI flow.

---

## 1. Skill Template Discovery

**Location:** `.council/templates/skills/` directory structure

**Pattern:**
```
.council/templates/skills/
└── <skill-slug>/
    ├── SKILL.md.j2      (required - main skill template)
    └── ... (optional companion files like examples, configs, etc.)
```

**Discovery Process** (lines 2218-2237 in generate.py):
- `generate_skills()` calls `templates_root.rglob("*")` to recursively find ALL files
- Filters to `.is_file()` only
- Files are sorted for deterministic output
- **File naming rule:** `.j2` extension indicates Jinja2 template; non-`.j2` files are copied as-is

**Code Reference:**
```python
# generate.py:2218
source_files = [path for path in sorted(templates_root.rglob("*")) if path.is_file()]

# generate.py:2233-2235
output_rel = (
    Path(str(rel_source)[:-3]) if source_path.name.endswith(".j2") else rel_source
)
```

**Confidence:** High (source code verified)

---

## 2. Skill Template Rendering

**Jinja2 Environment Setup** (lines 2350-2400 in generate.py):
- Uses `StrictUndefined` mode (all vars must be defined)
- Trim blocks and lstrip enabled for clean output
- Multi-path loader checks: `.council/templates/claude/` → `.council/templates/` → package templates

**Rendering Context Variables** (lines 2243-2250 in generate.py):
```python
template.render(
    orchestrator=orchestrator,           # Coordinator agent object
    agents=agents,                        # Full roster with defaults applied
    repo_root=str(repo_root),            # Repository root path
    timestamp=timestamp,                  # ISO datetime UTC
    skill_slug=output_rel.parts[0],      # Skill directory name
    skill_template_path=rel_source.as_posix(),  # Relative template path
)
```

**Two-Target Materialization** (lines 2266-2337 in generate.py):
- Rendered once (stored in `rendered_by_source`)
- Materialized to BOTH targets:
  - `.claude/skills/<slug>/SKILL.md`
  - `.codex/skills/<slug>/SKILL.md`

**Confidence:** High (source code verified)

---

## 3. Manifest Management

**Manifest File Locations:**
- `.claude/skills/.skills_manifest.json`
- `.codex/skills/.skills_manifest.json`

**Manifest Schema** (lines 2146-2154 in generate.py):
```python
{
    "version": 1,
    "generator": "council update",
    "generated_files": ["sorted", "relative", "paths"],
    "updated_at": "ISO8601_UTC_timestamp"
}
```

**Manifest Constant** (referenced throughout):
```
_SKILLS_MANIFEST_FILENAME = ".skills_manifest.json"  # (approximate, implicit)
```

**Stale File Pruning** (lines 2312-2333 in generate.py):
1. Load previous manifest via `_load_skills_manifest()` → `set[str]`
2. Collect current generated files → `set[str]`
3. Compute diff: `stale = previous - current`
4. For each stale file:
   - Unlink file
   - Call `_prune_empty_parents()` to remove empty directories
5. Write new manifest via `_write_skills_manifest()`

**Confidence:** High (source code verified)

---

## 4. Frontmatter Format & Parsing

**Location:** `src/council_mcp/services/skills.py` lines 47-139

**Frontmatter Location in SKILL.md:**
```markdown
---
name: bootstrap-council
description: Short description
user-invocable: true
context: full
allowed-tools: [Read, Edit, Write]
disable-model-invocation: false
argument-hint: "Optional hint"
---

# Markdown content below...
```

**Supported Fields (Hyphenated or Underscore):**

| Field Name | DB Column | Type | Example | Required |
|-----------|-----------|------|---------|----------|
| `name` | `name` | string | "bootstrap-council" | No (fallback to dir name) |
| `description` | `description` | string | "Master dev guide" | No (empty string default) |
| `agent` | `agent` | string | "atlas" | No |
| `allowed-tools` / `allowed_tools` | `allowed_tools` | list[string] | `[Read, Edit, Write]` | No |
| `user-invocable` / `user_invocable` | `user_invocable` | boolean | true | No (default true) |
| `disable-model-invocation` / `disable_model_invocation` | `disable_model_invocation` | boolean | false | No (default false) |
| `argument-hint` / `argument_hint` | `argument_hint` | string | "Optional hint" | No |
| `context` / `context_mode` | `context_mode` | string | "full" | No |

**Parser Details** (lines 47-139 in skills.py):

1. **Tokenization** (lines 54-97):
   - Strips leading/trailing `---` markers
   - Splits on first `:` in each line
   - Handles quoted strings (removes outer quotes)
   - Attempts to parse as YAML list (`[a,b,c]` → list)
   - Attempts to parse as boolean (`true/false/yes/no`)
   - Falls back to string for unrecognized values

2. **Field Mapping** (lines 99-137):
   - Hyphenated names (`user-invocable`) map to underscored columns (`user_invocable`)
   - Both forms accepted (hyphen checked first)
   - Raw frontmatter stored as `_raw_frontmatter` for reference

3. **Return Structure:**
```python
{
    "name": "...",
    "description": "...",
    "allowed_tools": [...],
    "user_invocable": bool,
    "context_mode": "...",
    # ... other fields ...
    "_raw_frontmatter": {...}  # Original parsed dict
}
```

**Confidence:** High (source code verified)

---

## 5. Skill Sync to Database

**Entry Point:** `SkillsService.discover_skills()` async function (lines 315-495 in skills.py)

**Called From:** `_sync_generated_project_skills()` in CLI (update_cmd.py lines 319-330)

**Workflow:**

1. **Scan Paths** (lines 331-334):
   - Scans: `.claude/skills/`, `.codex/skills/`
   - Uses `Path.rglob("SKILL.md")` to find all skill files recursively

2. **For Each SKILL.md** (lines 337-481):
   - Read content, compute SHA256 hash (first 32 chars)
   - Parse frontmatter via `SkillsService.parse_skill_frontmatter()`
   - Extract name (fallback to parent directory name)
   - Generate slug: `re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")`
   - Detect source type from path:
     - `.claude/skills/` or `.codex/skills/` → "project" or "personal" (if in home dir)
     - `/plugins/` → "plugin"
   - Extract fields: description, allowed_tools, disable_model_invocation, user_invocable, argument_hint, context_mode

3. **Frontmatter Normalization** (lines 384-392):
   - Calls `_normalize_skill_frontmatter()` to convert raw YAML to canonical format
   - Tracks if conversion occurred (`was_converted` flag)

4. **DB Check & Insert/Update** (lines 395-478):
   - Query existing skill by: `(slug, council_id, source_type)` triplet
   - If exists AND content_hash differs:
     - UPDATE council.skills with new content/metadata
     - Increment `updated` counter
   - If not exists:
     - INSERT new skill row
     - Increment `discovered` counter
   - Commit transaction

5. **Skill Assignment Sync** (lines 485):
   - Calls `SkillsService.sync_assignments_from_agents()` to populate skill_assignments table
   - This syncs skills listed in agent YAML `skills: [...]` field

**DB Schema (Relevant Columns):**
```
council.skills (
    id UUID PRIMARY KEY,
    slug TEXT,
    name TEXT,
    description TEXT,
    content TEXT,
    frontmatter JSONB,
    source_type TEXT,  -- 'project' | 'personal' | 'plugin' | 'manual'
    source_path TEXT,
    content_hash TEXT,
    allowed_tools JSONB,
    disable_model_invocation BOOLEAN,
    user_invocable BOOLEAN,
    argument_hint TEXT,
    context_mode TEXT,
    council_id TEXT,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
)
```

**Return Dict:**
```python
{
    "discovered": int,           # New skills inserted
    "updated": int,              # Existing skills updated
    "converted": int,            # Skills auto-normalized
    "errors": list[str],         # Errors during sync
    "assignments_synced": int,   # Agent skill assignments synced
    "assignments_skipped": int,  # Assignments skipped
    "assignment_errors": list[str]  # Errors during assignment sync
}
```

**Confidence:** High (source code verified)

---

## 6. Non-.j2 Companion Files

**Pattern:** Files other than `SKILL.md.j2` are copied as-is

**Example Structure:**
```
.council/templates/skills/my-skill/
├── SKILL.md.j2              (rendered → SKILL.md)
├── examples/
│   └── example.py           (copied → examples/example.py)
└── reference.txt            (copied → reference.txt)
```

**Implementation** (lines 2240-2255 in generate.py):
```python
if source_path.name.endswith(".j2"):
    # ... Jinja2 rendering ...
    mode = "rendered"
else:
    payload = source_path.read_bytes()  # Copy as binary
    mode = "copied"

rendered_by_source[source_path] = (output_rel, payload, mode)
```

**Confidence:** High (source code verified)

---

## 7. End-to-End Flow Diagram

```
1. council update CLI (update_cmd.py)
   ↓
2. generate_for_repo() (generate.py:2416-2660)
   ├─ Load roster (DB or YAML)
   ├─ Build Jinja environment
   └─ Call generate_skills() (line 2646)
   ↓
3. generate_skills() (generate.py:2181-2347)
   ├─ Scan .council/templates/skills/** for all files
   ├─ For each file:
   │  ├─ If .j2: render with context vars
   │  └─ Else: copy binary
   ├─ Load previous manifest from .claude/skills/.skills_manifest.json
   ├─ For each target (.claude/skills, .codex/skills):
   │  ├─ Write generated/copied files
   │  ├─ Identify stale files (previous - current)
   │  └─ Delete stale files + prune empty dirs
   └─ Write new manifest
   ↓
4. Back to update() CLI (update_cmd.py:363-682)
   ↓
5. _sync_generated_project_skills() (update_cmd.py:319-330)
   ├─ Calls SkillsService.discover_skills()
   └─ Non-blocking (errors logged, not fatal)
   ↓
6. SkillsService.discover_skills() (skills.py:315-495)
   ├─ Scan .claude/skills/ and .codex/skills/
   ├─ For each SKILL.md:
   │  ├─ Parse frontmatter
   │  ├─ Generate slug
   │  ├─ Normalize frontmatter
   │  ├─ INSERT or UPDATE council.skills
   └─ Sync skill assignments from agent YAML
   ↓
7. Return to CLI, display summary
```

**Confidence:** High (source code verified)

---

## 8. Key Implementation Details

### Constants
- `_SKILLS_MANIFEST_FILENAME = ".skills_manifest.json"` (implicit from code)
- Skill slug pattern: `[^a-z0-9]+` → `-` (lowercase alphanumeric + hyphens only)

### Error Handling
- **Generation errors** logged to results["errors"] but don't stop pipeline
- **Sync errors** non-fatal; logged to result["errors"] and result["assignment_errors"]
- **DB errors during update** caught and silently logged in CLI (line 678 in update_cmd.py)

### Source Type Detection
Priority order (path-based, first match wins):
1. If `.claude/skills/` or `.codex/skills/`:
   - In home dir → "personal"
   - Elsewhere → "project"
2. If `/plugins/` → "plugin"
3. Default → "project"

### Slug Generation
```python
slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
```
Examples: "My Skill" → "my-skill", "Skill_2.0" → "skill-2-0"

**Confidence:** High (source code verified)

---

## Technical Analysis

### System Design Principles
1. **Manifest-managed generation** — Safe pruning of stale files without human intervention
2. **Two-target materialization** — Single render, dual output (.claude + .codex)
3. **Frontmatter-driven metadata** — Skills self-describe their capabilities
4. **Non-blocking DB sync** — File generation succeeds even if DB unavailable
5. **Source type discrimination** — Distinguishes project vs personal vs plugin skills

### Potential Risks Identified
1. **No validation of frontmatter fields** — Invalid context_mode or other enums not rejected at parse time
2. **Slug collisions possible** — Multiple skills could have the same slug if names differ only in non-alphanumeric chars
3. **DB sync silently fails** — Errors logged but not propagated to CLI exit code

### Strengths
1. **Robust file handling** — Empty parent dirs pruned automatically
2. **Deterministic output** — Sorted iteration ensures reproducibility
3. **Schema normalization** — Auto-converts old metadata formats
4. **Flexible file structure** — Supports arbitrary companion files

**Confidence:** High (source code verified)

---

## Recommendations

### For Skill Template Authors
1. Always provide `name` in frontmatter (fallback to dir name is unreliable for discovery)
2. Use hyphenated field names (e.g., `user-invocable`) for consistency with existing skills
3. Place companion files in subdirectories (e.g., `examples/`, `reference/`) for clarity

### For Implementation
1. Add validation of frontmatter enum fields (context_mode, allowed_tools) at parse time
2. Consider unique constraint on (slug, council_id, source_type) to prevent accidental duplicates
3. Document the two-target (.claude + .codex) architecture for downstream tooling

**Confidence:** Medium (based on code analysis + architecture patterns)

---

## Appendix: Key File References

| File | Function | Line Range | Responsibility |
|------|----------|-----------|-----------------|
| `src/council_mcp/agents/generate.py` | `generate_skills()` | 2181-2347 | Discover, render, materialize, manifest |
| `src/council_mcp/cli/update_cmd.py` | `_sync_generated_project_skills()` | 319-330 | CLI entry point for DB sync |
| `src/council_mcp/services/skills.py` | `SkillsService.discover_skills()` | 315-495 | FS scan, parse, INSERT/UPDATE |
| `src/council_mcp/services/skills.py` | `parse_skill_frontmatter()` | 47-139 | YAML parsing + field extraction |
| `.council/templates/skills/*/SKILL.md.j2` | - | - | Example skill template |

---

**Research Status:** Complete  
**Last Updated:** 2026-02-22 18:50 UTC
