---
id: council_unified_platform-research-skill-generation-pipeline-20260222
title: "\U0001F52C Research Skill Generation Pipeline 20260222 \u2014 council_unified_platform"
doc_type: RESEARCH_SKILL_GENERATION_PIPELINE_20260222
doc_name: RESEARCH_SKILL_GENERATION_PIPELINE_20260222
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-22 18:53:39 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Skill Generation Pipeline 20260222 — council_unified_platform
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-22 18:53:03 UTC

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
<!-- ID: findings -->
## Findings

### 1. Template Discovery (HIGH CONFIDENCE)
**Location**: `generate.py:2181-2216` (`generate_skills` function)

- Skills source: `.council/templates/skills/` directory tree
- Discovery: `sorted(templates_root.rglob("*"))` — recursive glob all files
- Files included: Both `.j2` templates AND companion files (examples/, README.md, assets)
- Filtered: Only `path.is_file()` — directories skipped
- Status tracking: Results include `"enabled": templates_root.is_dir()`

**Evidence**: Lines 2200-2218 explicitly show directory check and recursive rglob pattern.

### 2. Rendering Strategy (HIGH CONFIDENCE)
**Location**: `generate.py:2228-2264`

**Two-pass rendering**:
- **Pass 1** (lines 2231-2264): Render/copy source files ONCE, cache in `rendered_by_source` dict
  - Key: `source_path` (Path object)
  - Value: `(output_rel, payload, mode)` tuple
  - `.j2` files: template render with Jinja2 env + context
  - Non-.j2 files: raw bytes copy (mode="copied")
- **Pass 2** (lines 2266-2337): Write cached payloads to BOTH targets

**Template rendering context** (lines 2243-2250):
```python
rendered = template.render(
    orchestrator=orchestrator,          # Coordinator agent
    agents=agents,                       # All agents with defaults applied
    repo_root=str(repo_root),            # Repository root path
    timestamp=timestamp,                 # UTC ISO timestamp
    skill_slug=output_rel.parts[0],      # First path component (skill name)
    skill_template_path=rel_source.as_posix(),  # Original template path
)
```

**Evidence**: Lines 2231-2257 show explicit branching by `.endswith(".j2")`

### 3. Dual-Target Materialization (HIGH CONFIDENCE)
**Location**: `generate.py:2201-2203, 2266-2337`

Targets defined:
```python
targets = {
    "claude": repo_root / ".claude" / "skills",
    "codex": repo_root / ".codex" / "skills",
}
```

**Materialization logic** (lines 2266-2337):
- For each target, iterate `rendered_by_source` (cached renders)
- Load previous manifest via `_load_skills_manifest()` (line 2267)
- For each source artifact:
  1. Compute `rel_key = output_rel.as_posix()`
  2. Add to `current` set
  3. Check if payload differs from existing (`existing == payload`)
  4. Write if changed: `output_path.write_bytes(payload)` (line 2291)
  5. Track result: "generated", "unchanged", or error

- Prune stale files (lines 2312-2333):
  1. Compute stale: `stale = sorted(previous - current)`
  2. For each stale file: unlink + call `_prune_empty_parents()`

**Evidence**: Lines 2266-2337 show explicit loop `for target_name, target_dir in targets.items()`

### 4. Manifest System (HIGH CONFIDENCE)
**Location**: `generate.py:2108-2154`

**Manifest file**: `.claude/skills/.manifest.json` and `.codex/skills/.manifest.json`

**Structure** (lines 2146-2154):
```json
{
  "version": 1,
  "generator": "council update",
  "generated_files": ["sorted", "list", "of", "posix", "paths"],
  "updated_at": "2026-02-22T18:52:00.000000+00:00"
}
```

**Loading** (lines 2108-2113):
```python
def _load_skills_manifest(manifest_path: Path) -> set[str]:
    """Load previous manifest set, return empty if missing."""
    if not manifest_path.exists():
        return set()
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = data.get("generated_files", [])
        return {str(item) for item in files if isinstance(item, str)}
    except:
        return set()
```

**Purpose**: Safe stale file detection via set difference: `stale = previous - current`

**Evidence**: Lines 2108-2143 show complete manifest lifecycle

### 5. Stale File Pruning (HIGH CONFIDENCE)
**Location**: `generate.py:2312-2333, 2157-2178`

**Detection**: Manifest tracks previous files. On new run:
- Build `current` set from newly generated files
- Compute `stale = sorted(previous - current)` — files no longer generated
- Iterate stale files and unlink

**Safety**: `_prune_empty_parents()` (lines 2157-2178)
- Removes empty parent directories UP TO `target_dir` boundary
- Prevents orphaned empty directories
- Stops at `stop_at` path or when parent contains other files

**Evidence**: Lines 2312-2333 explicitly show stale computation and unlink logic

### 6. Non-.j2 File Handling (HIGH CONFIDENCE)
**Location**: `generate.py:2234-2255`

**Path transformation**:
- `.j2` files: strip `.j2` extension
  - Input: `skill_name/README.md.j2` → Output: `skill_name/README.md`
  - Input: `skill_name/examples/main.py.j2` → Output: `skill_name/examples/main.py`
- Non-.j2 files: preserve as-is
  - Input: `skill_name/examples/` → Output: `skill_name/examples/` (directory, skipped)
  - Input: `skill_name/data.json` → Output: `skill_name/data.json`

**Copy logic** (lines 2253-2255):
```python
else:
    payload = source_path.read_bytes()
    mode = "copied"
```

**Evidence**: Lines 2234-2255 show explicit branching and mode assignment

### 7. DB Sync (Medium Confidence)
**Location**: `skills.py:315-480` (`discover_skills` method)

**Trigger**: Called separately via CLI or web, not automatically in `council update`

**Discovery flow**:
1. Scan filesystem: `path.rglob("SKILL.md")` (line 337)
2. For each file:
   - Parse frontmatter + extract name
   - Generate slug via regex: `re.sub(r"[^a-z0-9]+", "-", name.lower())`
   - Determine source_type (project/personal/plugin) from path
   - Normalize frontmatter (infer URN, version, channels, scope)
   - Check DB: `WHERE slug = %(slug)s AND council_id = %(cid)s AND source_type = %(st)s`
   - INSERT (new) or UPDATE (if content hash differs) (lines 445-475)

**Non-blocking errors** (line 329): `errors: list[str] = []` collects errors but continues discovery

**Evidence**: Lines 315-480 show complete async discovery pipeline with DB upsert logic

### 8. Slug Generation (HIGH CONFIDENCE)
**Frontmatter-based** (skills.py:350, generate.py does NOT use):
```python
slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
```

Pattern: One or more non-alphanumeric → single hyphen, strip leading/trailing hyphens

**Examples**:
- "My Skill" → "my-skill"
- "Agent_Roster" → "agent-roster"
- "council-mcp-dev" → "council-mcp-dev"

**Evidence**: Consistent pattern in skills.py line 350

### 9. Frontmatter Parsing (High Confidence)
**Location**: `skills.py:47-139`

**Fields supported** (hyphenated or underscored):
- name (required if not using directory name fallback)
- slug (optional, generated if missing)
- description
- user-invocable / user_invocable
- context
- allowed_tools / allowed-tools
- version
- artifact_urn
- channels (inferred from source path if missing)
- scope
- owner_council
- [custom fields preserved]

**Normalization** (lines 241-312):
- Infers artifact_urn: `urn:council:skill:{slug}` if missing
- Infers version: `0.1.0` if missing
- Infers channels from path: ["claude"] if .claude/skills/, ["codex"] if .codex/skills/, else both
- Infers scope: "personal" if source_type==personal, else "project"
- Adds provenance metadata (source_type, source_path, discovered_at, etc.)

**Evidence**: Lines 47-139 show comprehensive frontmatter parsing with field mapping
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
## Recommendations

### For Bootstrap-Council Skill Template
1. **Complement DB sync docs** — The bootstrap skill should document that `council update` generates skills to filesystem, while `council skills sync` discovers and syncs to DB. These are separate workflows.

2. **Manifest strategy note** — When creating skills, the manifest ensures clean stale file cleanup. Mention that deleting a skill template will automatically remove its output files on next `council update`.

3. **Template context available** — Skills rendered with `orchestrator`, `agents`, `repo_root`, `timestamp`, `skill_slug`, `skill_template_path` context. Use these in examples.

4. **Frontmatter inference** — Document that name → slug transformation is automatic (regex pattern). Users can override via explicit `slug` field if needed.

### For Generate.py Enhancement
None needed. The implementation is solid:
- Error handling is appropriate (DB sync non-blocking)
- Manifest system is sound for safe pruning
- Dual-target rendering is efficient (single render, dual write)

### For Skills.py Enhancement  
None needed. Discovery and DB sync are well-designed:
- Slug generation is consistent
- Frontmatter normalization preserves user data + adds provenance
- (slug, council_id, source_type) triplet prevents duplicates
<!-- ID: appendix -->
## Appendix: Code References

### Key Files
- `src/council_mcp/agents/generate.py:2181-2347` — `generate_skills()` function (skill generation pipeline)
- `src/council_mcp/agents/generate.py:2108-2154` — Manifest system (write/load)
- `src/council_mcp/agents/generate.py:2157-2178` — Empty directory pruning
- `src/council_mcp/services/skills.py:315-480` — `discover_skills()` async method (DB sync)
- `src/council_mcp/services/skills.py:47-139` — Frontmatter parsing
- `src/council_mcp/services/skills.py:241-312` — Frontmatter normalization

### Constants
- `_SKILLS_MANIFEST_FILENAME = ".manifest.json"` (generate.py ~2125)
- Manifest version: 1
- Slug pattern: `[^a-z0-9]+` → `-`

### Manifest Location
- `.claude/skills/.manifest.json`
- `.codex/skills/.manifest.json`

### Data Structures
**Render cache**:
```python
rendered_by_source: dict[Path, tuple[Path, bytes, str]]
# Keys: source_path (Path)
# Values: (output_rel, payload, mode)
# mode: "rendered" or "copied"
```

**Results dict** (returned from `generate_skills()`):
```python
{
    "generated": list[dict],    # Files written
    "unchanged": list[dict],    # Files already correct
    "removed": list[dict],      # Stale files deleted
    "errors": list[dict],       # Any errors encountered
    "dry_run": bool,
    "enabled": bool             # templates_root.is_dir()
}
```
