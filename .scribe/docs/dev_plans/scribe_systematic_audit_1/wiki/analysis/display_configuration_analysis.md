# Display Configuration Analysis - Phase 5

**Created**: 2026-01-05
**Author**: ResearchAgent-Phase5-FormatValidator (Team B)
**Status**: COMPLETE
**Confidence**: 0.9

---

## Executive Summary

Scribe MCP provides **configurable display formatting** for readable output through ANSI color codes and box-drawing characters. Display configuration is managed through `.scribe/config/scribe.yaml` with the `use_ansi_colors` setting.

**Key Findings**:
- ✅ ANSI color support implemented and functional
- ✅ Box-drawing characters used for structured readable output
- ✅ Global config toggle (`use_ansi_colors`) controls color rendering
- ⚠️ Default behavior varies: `false` in template, implementation defaults to `true`
- ⚠️ No per-tool color customization (global on/off only)
- ⚠️ No metadata verbosity controls (all or nothing via `include_metadata`)

---

## Configuration Architecture

### Primary Configuration File

**Location**: `.scribe/config/scribe.yaml`

**Display Setting**:
```yaml
# Output formatting (Phase 1.5 - Issue #9962 fix)
use_ansi_colors: false  # Enable ANSI colors in tool output for Claude Code
```

**Template Default**: `false` (colors disabled)

**Implementation Fallback**: `true` (colors enabled if config load fails)

**Discrepancy**: Template says `false`, code defaults to `true` - potential confusion

---

### Config Loading Pattern

**File**: `utils/response.py`

**Function**:
```python
def _get_use_ansi_colors() -> bool:
    """
    Get ANSI color setting from repo config.

    Phase 1.5/1.6: Load use_ansi_colors from .scribe/config/scribe.yaml
    Falls back to True (colors enabled by default) if config unavailable.
    """
    try:
        from scribe_mcp.config.repo_config import get_current_repo_config
        _, config = get_current_repo_config()
        return config.use_ansi_colors
    except Exception:
        # Fallback: colors enabled by default
        return True
```

**Usage**:
```python
class ResponseFormatter:
    @property
    def USE_COLORS(self) -> bool:
        """
        Check if ANSI colors are enabled via repo config.

        Phase 1.5/1.6: Colors loaded from .scribe/config/scribe.yaml
        (use_ansi_colors setting). Enabled by default.
        """
        return _get_use_ansi_colors()
```

**Scope**: Global (affects all tools using ResponseFormatter)

---

## ANSI Color Codes

### Defined Colors

**File**: `utils/response.py` - `ResponseFormatter` class

**Color Constants**:
```python
# ANSI color codes for enhanced readability in Claude Code
ANSI_CYAN = "\033[36m"      # Box borders, structural elements
ANSI_GREEN = "\033[32m"     # Line numbers, keys in metadata
ANSI_YELLOW = "\033[33m"    # Warnings, highlights
ANSI_BLUE = "\033[34m"      # (Defined but less commonly used)
ANSI_MAGENTA = "\033[35m"   # Reminders, special sections
ANSI_BOLD = "\033[1m"       # Titles, emphasis
ANSI_DIM = "\033[2m"        # De-emphasized text
ANSI_RESET = "\033[0m"      # Reset to default
```

**Total Colors**: 7 codes (6 colors + 1 style) + 1 reset

---

### Color Usage Patterns

#### Pattern 1: Box Borders (Cyan)
```python
# Top border
lines.append(f"{C}╔" + "═" * (box_width - 2) + f"╗{R}")

# Side borders
lines.append(f"{C}║{R} {content} {C}║{R}")

# Bottom border
lines.append(f"{C}╚" + "═" * (box_width - 2) + f"╝{R}")
```

**Purpose**: Structural framing, visual hierarchy

---

#### Pattern 2: Line Numbers (Green)
```python
# Format each line with right-aligned line number (green with dot separator)
for i, line in enumerate(lines, start=start):
    line_num = str(i).rjust(width)
    numbered_lines.append(f"{G}{line_num}.{R} {line}")
```

**Purpose**: Code/content reference, matches Claude's native Read tool style

**Example Output**:
```
     1. First line of content
     2. Second line of content
```

---

#### Pattern 3: Metadata Keys (Green)
```python
# Apply colors: key in green, value in default
colored_content = f"{G}{key}:{R} {value_str}"
```

**Purpose**: Key-value distinction in metadata sections

**Example**:
```
key: value   (key is green, value is default color)
```

---

#### Pattern 4: Titles (Bold)
```python
# Title line (centered, bold)
title_display = f"{B}{title}{R}"
```

**Purpose**: Section headers, emphasis

---

#### Pattern 5: Warnings (Yellow)
```python
# Warning text
warning_text = f"{Y}⚠️ Warning: {message}{R}"
```

**Purpose**: Alerts, cautionary information

---

#### Pattern 6: Reminders (Magenta)
```python
# Reminder section
reminder_display = f"{M}• {reminder_text}{R}"
```

**Purpose**: User notifications, actionable items

---

### Color Toggle Logic

**Conditional Application**:
```python
# Color helpers
C = self.ANSI_CYAN if self.USE_COLORS else ""
G = self.ANSI_GREEN if self.USE_COLORS else ""
Y = self.ANSI_YELLOW if self.USE_COLORS else ""
B = self.ANSI_BOLD if self.USE_COLORS else ""
R = self.ANSI_RESET if self.USE_COLORS else ""
```

**Result**:
- `use_ansi_colors: true` → Full color codes inserted
- `use_ansi_colors: false` → Empty strings (no codes, plain text)

---

## Box-Drawing Characters

### Unicode Box-Drawing Set

**Character Table**:
```
╔ U+2554 Box Drawings Double Down and Right (top-left corner)
╗ U+2557 Box Drawings Double Down and Left (top-right corner)
╚ U+255A Box Drawings Double Up and Right (bottom-left corner)
╝ U+255D Box Drawings Double Up and Left (bottom-right corner)
═ U+2550 Box Drawings Double Horizontal (horizontal line)
║ U+2551 Box Drawings Double Vertical (vertical line)
╟ U+255F Box Drawings Double Vertical and Right (left T-junction)
╢ U+2562 Box Drawings Double Vertical and Left (right T-junction)
─ U+2500 Box Drawings Light Horizontal (separator line)
```

**Style**: Double-line borders (heavy weight), light-line separators

---

### Box Templates

#### Header Box
```
╔══════════════════════════════════════════════════════════╗
║ TITLE                                                    ║
╟──────────────────────────────────────────────────────────╢
║ key1: value1                                             ║
║ key2: value2                                             ║
╚══════════════════════════════════════════════════════════╝
```

**Method**: `ResponseFormatter._create_header_box(title, metadata)`

**Width**: 80 characters (configurable via `box_width` variable)

**Sections**:
1. Title (centered, bold if colors enabled)
2. Separator (light horizontal line)
3. Metadata rows (key: value pairs)

---

#### Footer Box
```
╔══════════════════════════════════════════════════════════╗
║ METADATA                                                 ║
╟──────────────────────────────────────────────────────────╢
║ audit_key1: value1                                       ║
║ audit_key2: value2                                       ║
╟──────────────────────────────────────────────────────────╢
║ REMINDERS                                                ║
║ • Reminder 1                                             ║
║ • Reminder 2                                             ║
╚══════════════════════════════════════════════════════════╝
```

**Method**: `ResponseFormatter._create_footer_box(audit_data, reminders)`

**Sections**:
1. Metadata section (audit trail data)
2. Optional reminders section (if provided)

---

### Box Width Configuration

**Current**: Hardcoded to 80 characters

**Location**: `utils/response.py` methods

**Snippet**:
```python
# Calculate box width (default 80 chars)
box_width = 80
inner_width = box_width - 4  # Account for borders
```

**Limitation**: Not configurable via `scribe.yaml` (hardcoded constant)

**Recommendation**: Add `box_width` config setting for customization

---

## Metadata Verbosity Controls

### Current Implementation

**Parameter**: `include_metadata` (boolean)

**Scope**: Per-call parameter, not global config

**Usage**:
```python
formatted_entries = [
    self.format_entry(entry, compact, fields, include_metadata)
    for entry in entries
]
```

**Behavior**:
- `include_metadata=True` → Full `meta` field included in entries
- `include_metadata=False` → `meta` field excluded

**Granularity**: All-or-nothing (cannot selectively show/hide specific metadata keys)

---

### Metadata Field Selection

**Parameter**: `fields` (list of strings)

**Scope**: Per-call parameter, allows selective field inclusion

**Usage**:
```python
# Show only specific fields
formatted = formatter.format_entry(
    entry,
    fields=["id", "message", "timestamp"]
)
```

**Limitation**: Requires explicit field list (no preset profiles)

**Alternative**: Could add metadata presets like:
- `minimal`: id, message, timestamp
- `standard`: id, message, timestamp, emoji, agent
- `full`: all fields including meta

---

## Per-Tool Display Configuration

### Current State

**Tool-Level Config**: ❌ NOT AVAILABLE

**Scope**: All tools share global `use_ansi_colors` setting

**Example** (what's NOT possible):
```yaml
# This does NOT exist
tool_display_config:
  list_projects:
    use_colors: true
    box_width: 100
  read_file:
    use_colors: false
    line_numbers: true
```

---

### High-Frequency Tools

**Observation**: Some tools are called frequently (list_projects, get_project, set_project)

**Implication**: Display verbosity has token cost impact

**Current Behavior**: Same display configuration for all invocations

**Optimization Opportunity**:
- High-frequency tools could default to `compact` format
- Low-frequency tools could default to `readable` format
- Config could specify per-tool format defaults

---

## Format Mode Display Characteristics

### Readable Mode

**Display Features**:
- ✅ ANSI colors (if enabled)
- ✅ Box-drawing characters
- ✅ Line numbers (for content)
- ✅ Metadata boxes (header/footer)
- ✅ Human-readable summaries

**Token Impact**: Variable (depends on content, averages 52% reduction vs structured)

**Target Audience**: Human users, Claude Code interface

---

### Structured Mode

**Display Features**:
- ❌ No ANSI colors (pure JSON)
- ❌ No box-drawing
- ❌ No formatting
- ✅ Full data structure

**Token Impact**: Baseline (full JSON output)

**Target Audience**: Programmatic consumers, data analysis

---

### Compact Mode

**Display Features** (EXPECTED, not implemented):
- ❌ No ANSI colors (pure JSON)
- ❌ No box-drawing
- ❌ No formatting
- ✅ Short field names
- ✅ Truncated values
- ✅ Minimal structure

**Token Impact**: 20-30% reduction vs structured (THEORETICAL - not working)

**Current Status**: ❌ **BUG-FORMAT-003** - Returns identical JSON to structured

**Target Audience**: Token-constrained environments

---

## Configuration File Analysis

### scribe_config_template.yaml

**Display Section**:
```yaml
# Output formatting (Phase 1.5 - Issue #9962 fix)
use_ansi_colors: false  # Enable ANSI colors in tool output for Claude Code
```

**Default**: `false` (colors disabled)

**Rationale**: Conservative default, opt-in for color support

---

### .scribe/config/scribe.yaml (Active Config)

**Actual Setting**: Not shown in scan (likely same as template)

**Loading Behavior**: If missing/error, defaults to `true` in code

**Discrepancy**: Template default (`false`) ≠ Code fallback (`true`)

---

### Other Display-Related Settings

**Not Present** (but could be useful):
- `box_width`: Box character width (currently hardcoded to 80)
- `metadata_preset`: Predefined field selection profiles
- `line_number_width`: Minimum width for line numbers (currently 5)
- `tool_format_defaults`: Per-tool default format modes
- `color_scheme`: Predefined color palettes (light/dark/high-contrast)

---

## Display Configuration Capabilities

### ✅ What's Configurable (Global)

1. **ANSI Colors**: On/off toggle via `use_ansi_colors`
2. **Metadata Inclusion**: Per-call `include_metadata` parameter
3. **Field Selection**: Per-call `fields` parameter
4. **Format Mode**: Per-call `format` parameter (readable/structured/compact)

---

### ❌ What's NOT Configurable

1. **Box Width**: Hardcoded to 80 characters
2. **Color Scheme**: Fixed color assignments (cyan, green, yellow, etc.)
3. **Per-Tool Display**: No tool-specific overrides
4. **Metadata Presets**: No named field selection profiles
5. **Line Number Style**: Hardcoded to green with dot separator
6. **Box-Drawing Style**: Fixed to double-line borders
7. **Default Formats**: Tools hardcode their default format modes

---

## Display Quality Analysis

### Strengths

✅ **Consistent Visual Hierarchy**:
- Box borders (cyan) create clear sections
- Line numbers (green) match Claude's Read tool
- Metadata keys (green) distinguish from values
- Titles (bold) provide emphasis

✅ **Graceful Degradation**:
- Colors toggle cleanly (no broken output when disabled)
- Box-drawing works in all terminals
- Plain text fallback preserves structure

✅ **Configurable Colors**:
- Single setting controls all color output
- Easy to disable for environments without color support

✅ **Professional Appearance**:
- Clean ASCII boxes
- Consistent formatting
- Readable summaries

---

### Weaknesses

❌ **No Customization Beyond On/Off**:
- Cannot change color scheme
- Cannot adjust box width
- Cannot customize line number format

❌ **Default Inconsistency**:
- Template says `false`, code defaults to `true`
- Unclear what "default" means

❌ **No Tool-Specific Config**:
- High-frequency tools use same verbose output as low-frequency
- Cannot optimize per-tool

❌ **Hardcoded Constants**:
- Box width (80 chars)
- Line number width (5 chars min)
- Color assignments
- All require code changes to modify

---

## Issue #9962 Context

### Background

**Issue**: MCP CallToolResult with both TextContent + structuredContent renders escaped newlines (`\n`) instead of actual line breaks in Claude Code

**Workaround**: Return TextContent ONLY (no structuredContent) for proper rendering

**Impact on Display**:
- Readable mode: Uses TextContent only (colors render correctly)
- Structured mode: Returns JSON string as TextContent (not ideal, but works)
- Compact mode: Broken (returns same JSON as structured)

**Related Code**:
```python
# Format constants (Phase 0)
FORMAT_READABLE = "readable"
FORMAT_STRUCTURED = "structured"
FORMAT_COMPACT = "compact"
FORMAT_BOTH = "both"  # TextContent + structuredContent (for when Issue #9962 is fixed)
```

**Future**: When Issue #9962 is fixed, `FORMAT_BOTH` mode can be used for optimal rendering

---

## Token Optimization Insights

### Display vs Token Trade-offs

**Readable Mode**:
- More characters for formatting (boxes, colors)
- Less characters for data (summaries instead of full JSON)
- **Net Result**: 52% avg token reduction (highly effective!)

**Structured Mode**:
- No formatting overhead
- Full data output
- **Net Result**: Baseline (highest token usage)

**Compact Mode** (when working):
- Minimal formatting
- Abbreviated data
- **Net Result**: 20-30% reduction (theoretical)

---

### Display Configuration Impact on Tokens

**ANSI Colors**:
- Each color code: ~7-10 bytes (`\033[36m`)
- Reset code: 4 bytes (`\033[0m`)
- Typical readable output: 50-100 color codes
- **Overhead**: ~500-1000 chars (~125-250 tokens)
- **Negligible** compared to data reduction from readable format

**Box-Drawing**:
- Header box: ~240 chars
- Footer box: ~180 chars (without reminders)
- **Overhead**: ~420 chars (~105 tokens)
- **Trade-off**: Visual clarity vs token cost

**Recommendation**: For token-constrained scenarios:
1. Use `format="compact"` (when fixed)
2. Disable colors (`use_ansi_colors: false`)
3. Minimal metadata (`include_metadata=false`)
4. Selective fields (`fields=["id", "message"]`)

---

## Recommendations

### Priority 1: Fix Default Inconsistency

**Issue**: Template says `false`, code fallback says `true`

**Fix Options**:
1. Change template default to `true` (match code)
2. Change code fallback to `false` (match template)
3. Remove fallback, require explicit config

**Recommendation**: Option 2 - Conservative default, explicit opt-in

**Impact**: LOW effort, HIGH clarity

---

### Priority 2: Add Box Width Configuration

**Current**: Hardcoded 80 chars

**Proposed**:
```yaml
# Output formatting
use_ansi_colors: false
box_width: 80  # Configurable box width (60-120 recommended)
```

**Implementation**:
```python
def _get_box_width() -> int:
    try:
        from scribe_mcp.config.repo_config import get_current_repo_config
        _, config = get_current_repo_config()
        return config.get('box_width', 80)
    except Exception:
        return 80
```

**Impact**: MEDIUM effort, MEDIUM value (user convenience)

---

### Priority 3: Add Metadata Presets

**Current**: All-or-nothing metadata inclusion

**Proposed**:
```yaml
# Output formatting
metadata_presets:
  minimal: ["id", "message", "timestamp"]
  standard: ["id", "message", "timestamp", "emoji", "agent"]
  full: null  # All fields
```

**Usage**:
```python
# In tool calls
result = tool.execute(metadata_preset="minimal")
```

**Impact**: MEDIUM effort, HIGH value (token optimization)

---

### Priority 4: Per-Tool Format Defaults

**Current**: Tools hardcode default formats

**Proposed**:
```yaml
# Tool-specific defaults
tool_defaults:
  list_projects:
    default_format: readable
  get_project:
    default_format: readable
  query_entries:
    default_format: readable
```

**Impact**: MEDIUM effort, MEDIUM value (UX improvement)

---

### Priority 5: Color Scheme Support

**Current**: Fixed color assignments

**Proposed**:
```yaml
# Output formatting
color_scheme: default  # default, light, dark, high_contrast, none

color_schemes:
  default:
    border: cyan
    line_numbers: green
    keys: green
    titles: bold
    warnings: yellow
    reminders: magenta
  high_contrast:
    border: white
    line_numbers: yellow
    keys: cyan
    titles: bold_white
    warnings: red
    reminders: magenta
```

**Impact**: HIGH effort, LOW value (nice-to-have)

---

## Cross-References

**Related Documents**:
- Format Parameter Audit: `.scribe/docs/dev_plans/scribe_systematic_audit_1/wiki/analysis/format_parameter_audit.md`
- Response Formatter Source: `utils/response.py`
- Config Template: `config/scribe_config_template.yaml`
- Active Config: `.scribe/config/scribe.yaml`

**Related Findings**:
- BUG-FORMAT-003: Compact mode not implemented
- BUG-FORMAT-004: rotate_log no readable mode
- Issue #9962: MCP CallToolResult rendering

**Implementation Specs** (to be created):
- SPEC-FORMAT-001: Format parameter standardization
- SPEC-FORMAT-002: Readable mode enhancement

---

## Summary Statistics

**Display Configuration Points**: 2
- `use_ansi_colors` (global toggle)
- Per-call parameters (format, fields, include_metadata)

**ANSI Color Codes Defined**: 8 (6 colors + 2 styles)

**Box-Drawing Characters Used**: 9

**Configurable Settings**: 1 (use_ansi_colors)

**Hardcoded Constants**: 6
- Box width (80)
- Color assignments
- Line number width (5)
- Box-drawing style (double-line)
- Format mode defaults
- Metadata field presets (none exist)

**Configuration Gaps Identified**: 5
- Box width customization
- Color scheme selection
- Per-tool display overrides
- Metadata presets
- Default format modes

---

**Analysis Status**: COMPLETE
**Confidence**: 0.9 (high confidence in findings, some uncertainty about future Issue #9962 resolution)
**Team**: ResearchAgent-Phase5-FormatValidator (Team B)
**Date**: 2026-01-05
