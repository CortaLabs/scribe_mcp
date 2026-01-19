# Cross-Cutting Concerns: set_project.py Analysis

**Research Agent**: ResearchAgent-E-SetProject
**Tool**: `set_project.py` (807 LOC)
**Date**: 2026-01-05

This document identifies patterns, modules, and concerns that appear across multiple tools and should be considered for unification in Phase 6.

---

## [BUCKET:metadata] - Doc Inventory Gathering

### Overview
Multiple tools need to gather standardized information about project documentation (existence, line counts, custom content). Currently duplicated across 3 tools with minor variations.

### Affected Tools
- `set_project.py` (lines 61-127)
- `list_projects.py` (lines 88-125)
- `get_project.py` (lines 146-164)

### Current Implementation Pattern

**set_project.py** (lines 91-125):
```python
# Check standard documents
arch_file = dev_plan_dir / "ARCHITECTURE_GUIDE.md"
if arch_file.exists():
    result["docs"]["architecture"] = {
        "exists": True,
        "lines": default_formatter._get_doc_line_count(arch_file),
        "modified": False  # TODO: Check registry hashes if needed
    }

# Same pattern for phase_plan, checklist, progress_log

# Detect custom content
result["custom"] = default_formatter._detect_custom_content(dev_plan_dir)
```

**list_projects.py** (lines 88-104):
```python
# Same checking logic with default_formatter._get_doc_line_count()
# Same custom content detection
```

**get_project.py** (lines 146-164):
```python
# Same checking logic
# Adds hash tracking variant (lines unknown - needs investigation)
```

### Variations
- **set_project**: Returns `{"exists": bool, "lines": int, "modified": bool}`
- **list_projects**: Returns `{"exists": bool, "lines": int}` (no modified flag)
- **get_project**: Adds document hash tracking for drift detection

### Unification Proposal: DocInventoryGatherer Module

#### Responsibilities
- Check existence of ARCHITECTURE_GUIDE, PHASE_PLAN, CHECKLIST, PROGRESS_LOG
- Count lines in each document (via `_get_doc_line_count()`)
- Detect custom content (research files, bugs, jsonl files)
- Calculate doc hashes for drift detection (optional)
- Return standardized inventory structure

#### Proposed API
```python
class DocInventoryGatherer:
    """Unified document inventory gathering for project tools."""

    @staticmethod
    async def gather(
        dev_plan_dir: Path,
        include_hashes: bool = False,
        include_modified_flags: bool = False
    ) -> Dict[str, Any]:
        """
        Gather full project documentation inventory.

        Args:
            dev_plan_dir: Path to project's dev_plans directory
            include_hashes: If True, compute sha256 hashes for each doc
            include_modified_flags: If True, compare against baseline hashes

        Returns:
            {
                "docs": {
                    "architecture": {"exists": True, "lines": 1274, "hash": "...", "modified": False},
                    "phase_plan": {"exists": True, "lines": 542, ...},
                    ...
                },
                "custom": {
                    "research_files": 3,
                    "bugs_present": False,
                    "jsonl_files": ["TOOL_LOG.jsonl"]
                }
            }
        """
        pass
```

#### Before/After Mental Model
- **Before**: 3 responsibilities mixed (doc checking + line counting + hash tracking) in each tool
- **After**: Single `DocInventoryGatherer` handles invariant checks, tools adapt results to their needs
- **Conceptual Win**: Tools reason about "get doc status" not "check files + count lines + hash content"

#### Integration Points
- `set_project.py`: Replace `_gather_project_inventory()` with `DocInventoryGatherer.gather()`
- `list_projects.py`: Replace inline doc checking with `DocInventoryGatherer.gather()`
- `get_project.py`: Use `DocInventoryGatherer.gather(include_hashes=True)`
- `manage_docs.py`: Could use for validation before doc operations

#### Benefits
- **Consistency**: All tools see identical doc inventory logic
- **Single Source of Truth**: Doc counting/hashing rules in one place
- **Testability**: Inventory logic tested once, works everywhere
- **Maintainability**: Update doc detection rules in one location

#### Risks
- Tools may have subtle differences in what constitutes "custom content"
- Return shape variations require adapter layer in each tool
- Hash tracking only needed by get_project (optional parameter handles this)

#### Estimated Effort
- Module creation: 2 hours
- Integration (3 tools): 3 hours
- Testing: 2 hours
- **Total**: ~7 hours

---

## [BUCKET:parameter_healing] - MCP Parameter Normalization

### Overview
MCP framework sometimes sends dict/list parameters as JSON strings. All monster tools need identical healing logic with consistent fallback behavior.

### Affected Tools
- `set_project.py` (lines 168-185, 207-215)
- `append_entry.py` (unknown lines - needs investigation)
- `manage_docs.py` (unknown lines - needs investigation)
- `query_entries.py` (unknown lines - needs investigation)
- `rotate_log.py` (unknown lines - needs investigation)

### Current Implementation Pattern

**set_project.py** (lines 168-185):
```python
if isinstance(defaults, str):
    try:
        # Try standardized normalization first
        normalized_defaults = normalize_dict_param(defaults, "defaults")
        if isinstance(normalized_defaults, dict):
            defaults = normalized_defaults
        else:
            pass  # Fall through to JSON parsing
    except ValueError:
        # FALLBACK: Original JSON parsing
        try:
            import json
            defaults = json.loads(defaults)
            if not isinstance(defaults, dict):
                defaults = {}
        except (json.JSONDecodeError, TypeError):
            defaults = {}
```

**Similar pattern for list params** (lines 207-215):
```python
if isinstance(tags, str):
    try:
        normalized_tags = normalize_list_param(tags, "tags")
        if isinstance(normalized_tags, list):
            tags = normalized_tags
        else:
            tags = [tags]  # Fallback: single item
    except ValueError:
        tags = [tags]  # Fallback: single item
```

### Variations
- Different fallback values (empty dict vs empty list vs single-item list)
- Different error messages (some silent, some logged)
- Inconsistent use of normalize_dict_param vs direct JSON parsing

### Unification Proposal: ParameterHealer Module

#### Responsibilities
- Detect MCP framework JSON-stringified params
- Attempt normalize_dict_param/normalize_list_param
- Fallback to safe defaults with consistent policy
- Log healing attempts for debugging

#### Proposed API
```python
class ParameterHealer:
    """Unified parameter normalization for MCP tools."""

    @staticmethod
    def heal_dict(
        value: Any,
        param_name: str,
        fallback: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Heal dict parameter from MCP framework.

        Args:
            value: Parameter value (may be string, dict, or other)
            param_name: Parameter name for error messages
            fallback: Fallback value if healing fails (default: {})

        Returns:
            Healed dict value (never fails)
        """
        if fallback is None:
            fallback = {}

        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            try:
                normalized = normalize_dict_param(value, param_name)
                if isinstance(normalized, dict):
                    return normalized
            except ValueError:
                pass

            # Fallback to JSON parsing
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        return fallback

    @staticmethod
    def heal_list(
        value: Any,
        param_name: str,
        fallback: Optional[List[Any]] = None,
        allow_single_item: bool = True
    ) -> List[Any]:
        """
        Heal list parameter from MCP framework.

        Args:
            value: Parameter value (may be string, list, or other)
            param_name: Parameter name for error messages
            fallback: Fallback value if healing fails (default: [])
            allow_single_item: If True, wrap single values in list

        Returns:
            Healed list value (never fails)
        """
        if fallback is None:
            fallback = []

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            try:
                normalized = normalize_list_param(value, param_name)
                if isinstance(normalized, list):
                    return normalized
            except ValueError:
                pass

            # Allow single item wrapping
            if allow_single_item:
                return [value]

        return fallback
```

#### Before/After Mental Model
- **Before**: Each tool tries JSON parsing with different fallback strategies
- **After**: ParameterHealer.heal(param, expected_type, fallback) with consistent behavior
- **Conceptual Win**: Parameter healing is policy, not scattered try/except blocks

#### Integration Points
- All monster tools replace inline normalization with ParameterHealer calls
- Consistent error logging via single module
- Configuration-driven fallback policies

#### Benefits
- **Consistency**: All tools handle MCP quirks identically
- **Debuggability**: Healing attempts logged in one place
- **Policy Control**: Change fallback behavior globally
- **Testability**: Healing logic tested once

#### Estimated Effort
- Module creation: 3 hours
- Integration (5+ tools): 5 hours
- Testing: 3 hours
- **Total**: ~11 hours

---

## [BUCKET:formatting] - SITREP Generation

### Overview
`set_project` delegates SITREP formatting to `default_formatter`, but token analysis shows optimization opportunities. Other tools may also use SITREP-style output.

### Affected Tools
- `set_project.py` (lines 472-531) - calls `format_project_sitrep_new/existing()`
- `utils/response.py` - contains formatter implementation
- Potentially: `list_projects.py`, `get_project.py` (if they use similar formatting)

### Current Implementation

**set_project.py** (line 472):
```python
readable_content = default_formatter.format_project_sitrep_new(
    project_data,
    docs_created
)
```

**set_project.py** (line 512):
```python
readable_content = default_formatter.format_project_sitrep_existing(
    project_data,
    inventory,
    activity
)
```

### Token Analysis Results
- **Average SITREP**: 283 tokens (range 198-390)
- **Structural overhead**: 82 tokens (28.8%) - boxes, headers, separators
- **Duplication**: 36 tokens (12.7%) - "Location" block in every response
- **Reminders**: Up to 71 additional tokens
- **Compact format**: 17 tokens (94% reduction possible)

### Optimization Opportunities

#### 1. Optional Structural Elements
**Current**: All SITREPs include decorative boxes (╔══╗ style)
**Tokens**: ~80 tokens per response
**Proposal**: Make boxes optional in compact mode
```python
format_project_sitrep_new(project_data, docs_created, decorative_boxes=True)
```

#### 2. Template Fragments for Duplication
**Current**: "Location" block appears in every SITREP
**Tokens**: ~36 tokens per response
**Proposal**: Shared template fragment
```python
# Before: Inline in every formatter
📂 Location:
  Root: {root}
  Dev Plan: {dev_plan}

# After: Template fragment
@fragment
def location_block(project_data):
    return f"📂 Location:\n  Root: {project_data['root']}\n  ..."
```

#### 3. Reminder Separation
**Current**: Reminders embedded in SITREP output
**Tokens**: Up to 71 additional tokens
**Proposal**: Separate concerns - reminders as optional section
```python
# Tool decides whether to include reminders
readable_content = formatter.sitrep(..., include_reminders=False)
reminders_section = formatter.reminders(...) if needs_reminders else ""
```

#### 4. Compact Mode Implementation
**Target**: <20 tokens for essential data only
**Example**: `✅ Project: test | Status: in_progress | Entries: 127`
**Use Case**: High-frequency tool calls where verbosity hurts

### Unification Notes
- SITREP formatting is already semi-unified via `default_formatter`
- Improvements should be made in `utils/response.py`, not per-tool
- Other tools (list_projects, get_project) may benefit from same optimizations

### Estimated Effort
- Refactor formatters for optional components: 4 hours
- Add compact mode: 2 hours
- Template fragment extraction: 3 hours
- Testing across all tools: 3 hours
- **Total**: ~12 hours

---

## [BUCKET:error_handling] - Silent DB Failure Policy

### Overview
Multiple tools use defensive `try/except` with print() fallback for database mirroring failures. This is a conscious architectural decision but should be standardized.

### Affected Tools
- `set_project.py` (lines 305, 333, 345, 391)
- Likely: `append_entry.py`, `manage_docs.py`, other DB-mirroring tools

### Current Implementation Pattern

**set_project.py** (lines 305-306):
```python
except Exception as exc:  # pragma: no cover - defensive
    print(f"⚠️  ProjectRegistry ensure/touch_access failed in set_project: {exc}")
```

**set_project.py** (lines 389-393):
```python
except Exception as e:
    print(f"⚠️  Agent context management failed: {e}")
    print("   💡 Falling back to legacy global state management")
    mirror_global = True
```

### Policy Rationale
- **state.json is source of truth** - SQLite is supplementary
- **Failures should not block core operations** - project creation/activation must succeed
- **Best-effort mirroring** - database state is optimization, not requirement

### Issues with Current Approach
1. **No structured logging**: print() goes to stdout, not captured
2. **No failure tracking**: Can't query how often DB fails
3. **Inconsistent messages**: Each tool has different error format
4. **No alerting**: Silent failures may go unnoticed

### Unification Proposal: ErrorPolicy Module

#### Responsibilities
- Centralize silent failure policy
- Structured logging of swallowed errors
- Failure tracking/metrics
- Configurable escalation (silent vs warn vs fail)

#### Proposed API
```python
class ErrorPolicy:
    """Centralized error handling policy for DB mirroring."""

    @staticmethod
    async def swallow_db_error(
        operation: str,
        error: Exception,
        context: Dict[str, Any] = None,
        fallback_action: Optional[Callable] = None
    ) -> None:
        """
        Handle non-fatal database errors with consistent policy.

        Args:
            operation: Operation name (e.g., "ProjectRegistry.touch_access")
            error: Exception that occurred
            context: Additional context for debugging
            fallback_action: Optional fallback to execute

        Policy:
            - Logs to structured error log (not stdout)
            - Records failure metric
            - Optionally executes fallback
            - Never raises (swallows all errors)
        """
        # Structured logging
        logger.warning(
            f"DB operation failed: {operation}",
            extra={
                "operation": operation,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "context": context
            }
        )

        # Metrics
        await ErrorPolicy._record_metric("db_failure", operation)

        # Execute fallback if provided
        if fallback_action:
            try:
                await fallback_action()
            except Exception as fallback_error:
                logger.error(f"Fallback failed for {operation}: {fallback_error}")
```

#### Usage Example
```python
# Before
try:
    _PROJECT_REGISTRY.ensure_project(project_record, ...)
    _PROJECT_REGISTRY.touch_access(project_record.name)
except Exception as exc:
    print(f"⚠️  ProjectRegistry ensure/touch_access failed: {exc}")

# After
try:
    _PROJECT_REGISTRY.ensure_project(project_record, ...)
    _PROJECT_REGISTRY.touch_access(project_record.name)
except Exception as exc:
    await ErrorPolicy.swallow_db_error(
        "ProjectRegistry.touch_access",
        exc,
        context={"project": project_record.name}
    )
```

#### Benefits
- **Observability**: Know when/why DB operations fail
- **Consistency**: All tools handle failures identically
- **Debuggability**: Structured logs queryable
- **Metrics**: Track failure rates over time

#### Estimated Effort
- Module creation: 4 hours
- Integration (5+ tools): 6 hours
- Testing: 3 hours
- **Total**: ~13 hours

---

## [BUCKET:state] - Session Binding Logic

### Overview
`set_project` contains complex session binding logic with stable_session_id vs context_session_id handling. Other tools may need similar logic.

### Affected Tools
- `set_project.py` (lines 349-402, 410-437)
- Potentially: Any tool that needs session-scoped context

### Current Implementation

**Stable Session Retrieval** (lines 354-359):
```python
context = server_module.get_execution_context()
if context:
    context_session_id = context.session_id
    stable_session_id = getattr(context, 'stable_session_id', None)
```

**Session Key Selection** (line 411):
```python
session_key = stable_session_id or context_session_id or session_id
```

### Critical Decision
- **Stable session ID preferred** (deterministic)
- **Context session ID fallback** (UUID, changes per request)
- **Agent session ID last resort**

### Unification Notes
This is likely specific to set_project's needs. Other tools may not need session binding. Tag for monitoring but likely NOT a candidate module unless pattern emerges elsewhere.

**Next Steps**: Check append_entry, manage_docs, query_entries for session binding logic. If absent, this is set_project-specific and should remain internal.

---

## [BUCKET:config] - Configuration Handling

### Overview
`set_project` accepts 20+ parameters with complex normalization, defaults merging, and validation. This could indicate need for configuration abstraction.

### Observed Patterns
- Multiple parameter sources (direct params, defaults dict, emoji param, agent param)
- Priority resolution (emoji_param > defaults.emoji > defaults.default_emoji)
- Validation scattered across helper functions

### Current Implementation
**_normalise_defaults()** (lines 594-621):
```python
def _normalise_defaults(
    defaults: Dict[str, Any],
    emoji_param: Optional[str] = None,
    agent_param: Optional[str] = None
) -> Dict[str, Any]:
    # Priority resolution logic
    emoji_value = emoji_param or defaults.get("emoji") or defaults.get("default_emoji")
    agent_value = agent_param or defaults.get("agent") or defaults.get("default_agent")
    # ...
```

### NOT a Candidate Module: set_project-Specific Logic
This normalization is tightly coupled to set_project's specific parameter contract. Extracting would require passing 20+ params to a module, no clarity gain.

**Decision**: Keep as internal helper. Only flag if other tools need identical priority resolution.

---

## Summary of Unification Candidates

| Bucket | Module | Tools Affected | Effort | Priority |
|--------|--------|---------------|--------|----------|
| metadata | DocInventoryGatherer | 3 (set_project, list_projects, get_project) | 7h | High |
| parameter_healing | ParameterHealer | 5+ (all monster tools) | 11h | High |
| formatting | SITREP Optimization | 3+ (set_project, list_projects, get_project) | 12h | Medium |
| error_handling | ErrorPolicy | 5+ (all DB-mirroring tools) | 13h | Medium |
| state | Session Binding | 1 (set_project only) | N/A | Low (monitor) |
| config | Config Normalization | 1 (set_project only) | N/A | Low (keep internal) |

**Total Estimated Effort**: 43 hours (High priority items: 18 hours)

---

## Next Steps for Phase 6

1. **Validate cross-tool patterns**:
   - Check append_entry, manage_docs, query_entries for parameter healing
   - Confirm list_projects, get_project have doc inventory duplication
   - Verify error handling patterns across DB-mirroring tools

2. **Prioritize by impact**:
   - DocInventoryGatherer: High (affects 3 tools, consistency critical)
   - ParameterHealer: High (affects all tools, user-facing bugs possible)
   - SITREP Optimization: Medium (token savings, but not broken)
   - ErrorPolicy: Medium (observability, not functional)

3. **Design module contracts**:
   - API design sessions for each module
   - Integration planning with existing tools
   - Testing strategy for each extraction

4. **Incremental extraction**:
   - Start with DocInventoryGatherer (smallest scope)
   - Add ParameterHealer (high reuse)
   - Refine based on learnings

---

**Document Status**: Initial analysis from set_project.py
**Aggregation Pending**: Await findings from agents A-D (append_entry, manage_docs, query_entries, rotate_log)
**Phase**: 1 (Research) - To be refined in Phase 6 (Modularization)
