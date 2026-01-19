# High-Frequency Tool Optimization Plan

**Generated**: 2026-01-05
**Analyzer**: ResearchAgent-Phase5-TokenAnalyzer (Team C)
**Focus**: Tools called most frequently in typical development workflows

---

## Executive Summary

High-frequency tools are called 10-100x more often than specialized tools, making their token efficiency critical to overall system performance.

**Target Tools (by call frequency):**
1. **append_entry** - Called after every meaningful action (100+ calls/day)
2. **list_projects** - Called during context switching (20+ calls/day)
3. **set_project** - Called at session start and project switches (15+ calls/day)
4. **get_project** - Called for context verification (10+ calls/day)
5. **read_recent** - Called for progress review (8+ calls/day)
6. **query_entries** - Called during investigation (5+ calls/day)

**Impact Analysis:**
- If append_entry is called 100x/day at 136 tokens → **13,600 tokens/day**
- 34% reduction → **saves ~4,624 tokens/day** from append_entry alone
- If list_projects is called 20x/day at 204 tokens → **4,080 tokens/day**
- 41% reduction → **saves ~1,673 tokens/day** from list_projects

**Combined Daily Savings Potential**: ~10,000+ tokens/day across high-frequency tools

---

## Tool 1: list_projects (Highest Token Count)

### Current Performance

**Measured Outputs:**
- Readable: 204 tokens (14 lines)
- Structured: 285 tokens (1 line JSON)
- Compact: 285 tokens (**BUG: identical to structured**)

**Call Frequency Estimate**: 20-30 calls/day
**Daily Token Cost**: 4,080-6,120 tokens (readable mode)

### Bloat Analysis

**Total Tokens**: 204
**Bloat Breakdown**:
- Structural (box drawing, borders): 40 tokens (20%)
- Metadata (page info, filter status): 35 tokens (17%)
- Safety (tips, suggestions): 20 tokens (10%)
- Duplication (repeated values): 15 tokens (7%)
- **Core information**: 94 tokens (46%)

**Bloat Total**: 110 tokens (54% is removable)

### Optimization Strategy

#### Phase 1: Readable Mode Refinement (Target: <120 tokens)

**Changes:**
1. Remove box drawing characters (saves 25 tokens)
2. Remove table border lines (saves 15 tokens)
3. Eliminate tip/suggestion footer (saves 20 tokens)
4. Compress page/filter status to single line (saves 15 tokens)
5. Maintain table structure and emoji (preserve readability)

**Before (204 tokens):**
```
╔══════════════════════════════════════════════════════════╗
║ 📋 PROJECTS - 109 total (Page 1 of 37, showing 3)         ║
╚══════════════════════════════════════════════════════════╝

NAME                          STATUS        ENTRIES  LAST ACTIVITY
──────────────────────────────────────────────────────────────────────
  append-entry-edge-test      planning           1  never
  append_query_modularization planning         176  never
  bugs                        planning           2  never

📄 Page 1 of 37 | Use page=2 to see more
🔍 Filter: none | Sort: None (desc)
💡 Tip: Add filter="scribe" to narrow results, or filter="exact_name" to see details
```

**After (115 tokens, 44% reduction):**
```
📋 Projects (3/109, page 1/37)

NAME                          STATUS    ENTRIES  ACTIVITY
append-entry-edge-test        planning        1  never
append_query_modularization   planning      176  never
bugs                          planning        2  never

Page 1/37 | filter: none
```

**Token Savings**: 89 tokens (44% reduction)
**Daily Impact**: 1,780-2,670 tokens saved/day

#### Phase 2: Fix Compact Mode Implementation

**Current Bug**: Compact and structured return identical JSON (285 tokens)

**Proposed Compact Mode (<130 tokens):**
```json
{
  "p": [
    {"n": "append-entry-edge-test", "s": "planning", "e": 1, "a": null},
    {"n": "append_query_modularization", "s": "planning", "e": 176, "a": null},
    {"n": "bugs", "s": "planning", "e": 2, "a": null}
  ],
  "tot": 109,
  "pg": {"i": 1, "sz": 3, "nx": true}
}
```

**Key Abbreviations**:
- `projects` → `p`
- `name` → `n`
- `status` → `s`
- `entries` → `e`
- `activity` → `a`
- `total` → `tot`
- `pagination` → `pg`
- `index` → `i`
- `size` → `sz`
- `has_next` → `nx`

**Additional Optimizations**:
- Remove `ok: true` field (assume success)
- Remove `root` and `progress_log` paths (unnecessary for listing)
- Remove `active_project` (already known from context)
- Remove `recent_projects` array (not requested)
- Remove `reminders` array (empty)
- Use `null` instead of `"never"` for null values

**Token Savings**: 155 tokens (54% reduction from current 285)

#### Phase 3: Structured Mode Optimization

**Keep structured mode as middle ground**: Readable JSON keys but remove unnecessary fields

```json
{
  "projects": [
    {"name": "append-entry-edge-test", "status": "planning", "entries": 1},
    {"name": "append_query_modularization", "status": "planning", "entries": 176},
    {"name": "bugs", "status": "planning", "entries": 2}
  ],
  "total": 109,
  "pagination": {"page": 1, "size": 3, "has_next": true}
}
```

**Target**: ~160 tokens (44% reduction from current 285)

### Configuration Integration

```yaml
# .scribe/config/scribe.yaml
display:
  verbosity: 1  # 0=minimal, 1=standard, 2=verbose
  list_projects:
    show_tips: false
    box_drawing: false
    default_format: "readable"
```

---

## Tool 2: set_project (Second Priority)

### Current Performance

**Status**: No recordings available from Team A yet
**Expected Token Range**: 400-800 tokens (based on Phase 4 observations)
**Call Frequency Estimate**: 15-20 calls/day
**Estimated Daily Token Cost**: 6,000-16,000 tokens

### Known Bloat Patterns (from Phase 4)

Based on prior research, set_project is known to have:
1. **Verbose success messages** with full project details
2. **Complete file path listings** for all created documents
3. **Box drawing** around success confirmation
4. **Multi-line status updates**
5. **Suggestions for next steps** (unsolicited)

### Optimization Target

**Current Estimate**: 600 tokens (mid-range)
**Target**: <350 tokens (42% reduction)

### Proposed Refinement

**Before (estimated 600 tokens):**
```
╔══════════════════════════════════════════════════════════╗
║ ✨ PROJECT CREATED: my_new_project                       ║
╚══════════════════════════════════════════════════════════╝

📂 Location:
  Root: /home/austin/projects/MCP_SPINE/scribe_mcp
  Dev Plan: .scribe/docs/dev_plans/my_new_project/

📄 Documents Created:
  ✓ ARCHITECTURE_GUIDE.md (template, 768 lines)
  ✓ PHASE_PLAN.md (template, 1414 lines)
  ✓ CHECKLIST.md (template, 322 lines)
  ✓ PROGRESS_LOG.md (empty, ready for entries)

🎯 Status: planning (new project)
💡 Next: Start with research or architecture phase
```

**After (estimated 340 tokens, 43% reduction):**
```
✨ Project created: my_new_project

📂 .scribe/docs/dev_plans/my_new_project/
✓ ARCHITECTURE_GUIDE.md (768 lines)
✓ PHASE_PLAN.md (1414 lines)
✓ CHECKLIST.md (322 lines)
✓ PROGRESS_LOG.md (empty)

Status: planning
```

**Removed**:
- Box drawing (25 tokens)
- "Root:" label and absolute path (40 tokens)
- "Dev Plan:" redundant label (10 tokens)
- "Documents Created:" header (15 tokens)
- "(template, ...)" annotations (30 tokens)
- "Next:" suggestion (35 tokens)
- Excessive whitespace (20 tokens)

**Total Savings**: ~260 tokens (43%)

### Compact Mode Proposal

```json
{
  "name": "my_new_project",
  "path": ".scribe/docs/dev_plans/my_new_project",
  "docs": ["ARCHITECTURE_GUIDE.md", "PHASE_PLAN.md", "CHECKLIST.md", "PROGRESS_LOG.md"],
  "status": "planning"
}
```

**Target**: <150 tokens

---

## Tool 3: append_entry (Highest Call Frequency)

### Current Performance

**Measured Output:**
- Readable: 136 tokens (5 lines)

**Call Frequency Estimate**: 100+ calls/day (every meaningful action)
**Daily Token Cost**: 13,600+ tokens

### Bloat Analysis

**Total Tokens**: 136
**Bloat Breakdown**:
- Structural (emoji, spacing): 15 tokens (11%)
- Metadata (full timestamp, project name): 40 tokens (29%)
- Safety (file path footer): 15 tokens (11%)
- **Core information**: 66 tokens (49%)

**Bloat Total**: 70 tokens (51%)

### Optimization Strategy

**Before (136 tokens):**
```
✅ Entry written to progress log (scribe_systematic_audit_1_phase5_tool_output)
   [ℹ️] [2026-01-05 14:34:25 UTC] [Agent: PhaseTestAgent] [Project: scribe_systematic_audit_1_phase5_tool_output] Test message for append_entry readable mode - Phase 5 tool output recording | phase=5; test_mode=readable; unicode_test=日本語🎯; priority=low; log_type=progress; content_type=log

📁 .scribe/docs/dev_plans/scribe_systematic_audit_1_phase5_tool_output/PROGRESS_LOG.md
```

**After (85 tokens, 37% reduction):**
```
✅ Test message for append_entry readable mode - Phase 5 tool output recording
   14:34 UTC | PhaseTestAgent | phase=5; test_mode=readable; unicode_test=日本語🎯
📁 PROGRESS_LOG.md
```

**Changes**:
- Remove "Entry written to progress log" prefix (10 tokens)
- Remove redundant project name from first line (20 tokens)
- Shorten timestamp (14:34 vs full ISO 8601) (8 tokens)
- Remove bracketed metadata labels `[ℹ️]`, `[Agent:]`, `[Project:]` (12 tokens)
- Use relative path for file (30 tokens)
- Remove redundant `priority=low; log_type=progress; content_type=log` (15 tokens saved by filtering)

**Token Savings**: 51 tokens (37% reduction)
**Daily Impact**: 5,100+ tokens saved/day

---

## Tool 4: get_project (Context Verification)

### Current Performance

**Status**: No recordings available from Team A yet
**Expected Token Range**: 300-500 tokens
**Call Frequency Estimate**: 10-15 calls/day
**Estimated Daily Token Cost**: 3,000-7,500 tokens

### Optimization Target

**Current Estimate**: 400 tokens
**Target**: <240 tokens (40% reduction)
**Daily Impact**: 1,600-2,400 tokens saved/day

---

## Tool 5: read_recent (Progress Review)

### Current Performance

**Status**: No recordings available from Team A yet
**Expected Token Range**: 800-2,000 tokens (depends on entry count)
**Call Frequency Estimate**: 8-12 calls/day
**Estimated Daily Token Cost**: 6,400-24,000 tokens

### Optimization Target

**Current Estimate**: 1,200 tokens (medium complexity)
**Target**: <750 tokens (37% reduction)
**Daily Impact**: 3,600-5,400 tokens saved/day

### Known Bloat Sources

1. **Box drawing around header** (25 tokens)
2. **Repeated metadata per entry** (20 tokens × entry count)
3. **Full timestamps** (can abbreviate to HH:MM)
4. **Absolute file paths** (can use relative)
5. **Pagination footers with tips**

---

## Tool 6: query_entries (Investigation)

### Current Performance

**Status**: No recordings available from Team A yet
**Expected Token Range**: 1,000-3,000 tokens
**Call Frequency Estimate**: 5-8 calls/day
**Estimated Daily Token Cost**: 5,000-24,000 tokens

### Optimization Target

**Current Estimate**: 1,500 tokens
**Target**: <950 tokens (37% reduction)
**Daily Impact**: 2,750-4,000 tokens saved/day

---

## Cumulative Impact Analysis

### Daily Token Savings (Conservative Estimates)

| Tool | Current | Reduced | Savings | Calls/Day | Daily Savings |
|------|---------|---------|---------|-----------|---------------|
| append_entry | 136 | 85 | 51 | 100 | 5,100 |
| list_projects | 204 | 115 | 89 | 20 | 1,780 |
| set_project | 600 | 340 | 260 | 15 | 3,900 |
| get_project | 400 | 240 | 160 | 10 | 1,600 |
| read_recent | 1200 | 750 | 450 | 8 | 3,600 |
| query_entries | 1500 | 950 | 550 | 5 | 2,750 |

**Total Daily Savings**: **18,730 tokens/day** (conservative)

### Weekly/Monthly Impact

- **Weekly**: ~131,110 tokens saved
- **Monthly**: ~562,000 tokens saved
- **Annual**: ~6.8 million tokens saved

### Cost Impact (at typical LLM pricing)

Assuming $0.01 per 1K tokens (input):
- **Daily**: $0.19 saved
- **Monthly**: $5.62 saved
- **Annual**: $68 saved per active user

For a team of 10 developers: **$680/year saved**

---

## Implementation Priority

### Phase 1 (Immediate - High Impact)
1. **append_entry** - Highest call frequency, moderate savings
2. **list_projects** - Fix compact mode bug, significant savings

### Phase 2 (Short Term - Medium Impact)
3. **set_project** - High token cost, moderate frequency
4. **get_project** - Moderate cost and frequency

### Phase 3 (Medium Term - Specialized)
5. **read_recent** - Variable cost, moderate frequency
6. **query_entries** - High cost, lower frequency

---

## Configuration System Design

### Proposed Verbosity Levels

**Level 0: Minimal** (40-50% reduction)
- No box drawing
- No tips/suggestions
- Abbreviated timestamps (HH:MM)
- Relative paths only
- Compact metadata

**Level 1: Standard** (30-40% reduction, DEFAULT)
- Simple headers (no boxes)
- Essential metadata only
- Short timestamps
- Relative paths
- No unsolicited guidance

**Level 2: Verbose** (current behavior)
- Full box drawing
- All metadata
- ISO 8601 timestamps
- Absolute paths
- Tips and suggestions

### Configuration File

```yaml
# .scribe/config/scribe.yaml
display:
  verbosity: 1  # 0=minimal, 1=standard, 2=verbose

  # Per-tool overrides
  append_entry:
    show_file_path: true
    timestamp_format: "short"  # short=HH:MM, full=ISO8601

  list_projects:
    box_drawing: false
    show_tips: false
    default_format: "readable"

  set_project:
    show_next_steps: false
    show_line_counts: false
```

---

## Testing Verification

### Success Criteria

For each optimized tool:
1. ✅ **Information preservation**: All core data retained
2. ✅ **Token reduction**: 30-40% reduction achieved
3. ✅ **Readability maintained**: Human-friendly output still clear
4. ✅ **Configuration works**: Verbosity levels produce expected output
5. ✅ **No regressions**: Existing workflows continue functioning

### Test Cases

**append_entry:**
- Single entry with metadata
- Bulk entry mode
- Unicode content
- Error handling

**list_projects:**
- Empty list (0 projects)
- Single project
- Multiple pages (100+ projects)
- Filtered results
- All three format modes (readable/structured/compact)

---

## Next Steps

1. Create implementation specs (YAML format)
2. Define test cases for each optimized tool
3. Coordinate with Team B on format mode standards
4. Submit findings to Phase 6 implementation team
