# Auto-Transform Viability Analysis: normalize_headers & generate_toc

**Research Agent:** ResearchAgent
**Date:** 2026-01-19
**Project:** agent_ux_overhaul
**Overall Confidence:** 0.92

---

## Executive Summary
<!-- ID: executive_summary -->

This research investigates whether `normalize_headers` and `generate_toc` should run **automatically** after edit actions instead of requiring explicit agent calls.

**RECOMMENDATION: DO NOT AUTO-ENABLE BY DEFAULT**

While both functions are technically safe (idempotent, O(n), frontmatter-preserving), automatic execution creates semantic problems for certain document types. A **per-doc opt-in via frontmatter** is the recommended approach.

**Key Takeaways:**
- Both functions are idempotent and safe to run multiple times
- Performance cost is negligible (O(n) linear scan)
- normalize_headers is INAPPROPRIATE for user-facing docs (README.md) due to emoji/custom formatting
- generate_toc is INAPPROPRIATE for log files (PROGRESS_LOG.md)
- Opt-in via frontmatter flags is the safest implementation path

---

## Research Scope
<!-- ID: research_scope -->

**Research Lead:** ResearchAgent
**Investigation Window:** 2026-01-19

**Focus Areas:**
- [x] normalize_headers implementation analysis
- [x] generate_toc implementation analysis
- [x] Idempotency verification
- [x] Performance assessment
- [x] Edge case identification
- [x] Risk analysis by document type

**Dependencies & Constraints:**
- Both functions exist in `doc_management/manager.py` (lines 1722-1890)
- Tests exist confirming idempotency
- No existing opt-out mechanism in frontmatter
- Frontmatter infrastructure supports custom fields

---

## Findings
<!-- ID: findings -->

### Finding 1: normalize_headers Implementation
- **Summary:** Single-pass O(n) algorithm that strips existing number prefixes and re-generates hierarchical numbering
- **Evidence:** Code at lines 1722-1784 in manager.py; regex `r"^\d+(?:\.\d+)*[.)]?\s+"` strips existing numbers
- **Confidence:** 0.98
- **Key Detail:** Handles both ATX (`#`) and Setext (`===`/`---`) headers; skips fenced code blocks

### Finding 2: generate_toc Implementation
- **Summary:** Two-pass O(n) algorithm that generates GitHub-style anchor TOC
- **Evidence:** Code at lines 1808-1890 in manager.py
- **Confidence:** 0.95
- **Key Detail:** Replaces existing `<!-- TOC:start/end -->` block or PREPENDS to top if no markers exist

### Finding 3: Both Functions Are Idempotent
- **Summary:** Running either function twice produces identical output
- **Evidence:** Test at line 233 (test_manage_docs_structured_edit.py) and line 88 (test_manage_docs_generate_toc.py) both assert `diff_preview == ""`
- **Confidence:** 0.98

### Finding 4: Frontmatter Is Safely Preserved
- **Summary:** Transforms operate on document BODY only; frontmatter extracted before and recombined after
- **Evidence:** Lines 177-180 in manager.py: `original_parsed = parse_frontmatter(original_text); original_body = original_parsed.body`
- **Confidence:** 0.98

### Finding 5: README.md Unsuitable for normalize_headers
- **Summary:** User-facing docs with emoji headers would be corrupted
- **Evidence:** README.md has headers like `## [sparkles] Update v2.1.1` which would become `## 1 [sparkles] Update v2.1.1`
- **Confidence:** 0.95

### Finding 6: PROGRESS_LOG.md Unsuitable for Either Transform
- **Summary:** Log files have no meaningful header structure; TOC would be massive and useless
- **Evidence:** Log format analysis; entries are timestamped lines, not structured sections
- **Confidence:** 0.99

### Additional Notes
- No existing opt-out mechanism (skip_toc, no_headers flags) found in codebase
- Frontmatter already supports arbitrary YAML fields for potential opt-in flags

---

## Technical Analysis
<!-- ID: technical_analysis -->

### Code Patterns Identified

**normalize_headers (lines 1722-1784):**
```python
# Key regex for stripping existing numbers
title = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", title)

# Hierarchical counter management
def _next_prefix(level: int) -> str:
    counters[level - 1] += 1
    for idx in range(level, 6):
        counters[idx] = 0
    return ".".join(str(value) for value in counters[:level])
```

**generate_toc (lines 1808-1890):**
```python
# TOC marker constants
toc_start = "<!-- TOC:start -->"
toc_end = "<!-- TOC:end -->"

# Anchor generation with de-duplication
anchor = _build_github_anchor(title, anchor_counts)

# Placement logic
if start_idx is not None and end_idx is not None:
    body_lines = lines[:start_idx] + toc_block + lines[end_idx + 1:]
else:
    body_lines = toc_block + [""] + lines  # PREPENDS if no markers
```

### System Interactions
- Both functions are pure text transforms - no database or file system calls
- Called from `apply_doc_change()` action dispatcher (lines 355-358)
- Frontmatter parsing via `utils/frontmatter.py`

### Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| User-facing doc corruption | HIGH | Exclude README, CONTRIBUTING from auto-transform |
| Log file pollution | HIGH | Never auto-transform PROGRESS_LOG.md |
| Unwanted TOC on short docs | MEDIUM | Minimum header count threshold (e.g., >= 5) |
| Unexpected numbering changes | LOW | Idempotency ensures consistency |
| Performance overhead | LOW | O(n) is negligible for typical doc sizes |

---

## Recommendations
<!-- ID: recommendations -->

### Primary Recommendation: Opt-In via Frontmatter

Add frontmatter flags to control auto-transform:

```yaml
---
id: my-doc
auto_normalize_headers: true   # default: false
auto_generate_toc: true        # default: false
---
```

**Implementation Location:** Around line 475-480 in manager.py, after `updated_body` computed:

```python
if original_parsed.frontmatter_data.get("auto_normalize_headers"):
    updated_body = _normalize_headers_text(updated_body)
if original_parsed.frontmatter_data.get("auto_generate_toc"):
    updated_body = _generate_toc_text(updated_body)
```

### Alternative: Doc-Type Defaults

| doc_type | auto_normalize_headers | auto_generate_toc |
|----------|------------------------|-------------------|
| architecture | true | true |
| phase_plan | true | true |
| research | false | true |
| checklist | false | false |
| progress_log | false | false |
| (default) | false | false |

### Immediate Next Steps
- [ ] Add `auto_normalize_headers` and `auto_generate_toc` fields to frontmatter schema
- [ ] Implement conditional transform in apply_doc_change() after line 475
- [ ] Exclude actions that shouldn't trigger: `normalize_headers`, `generate_toc`, `validate_crosslinks`, `create_doc`
- [ ] Add tests for opt-in behavior

### Long-Term Opportunities
- Consider `auto_transform_on: ["finalize", "merge"]` for workflow-based triggers
- Add minimum header count for TOC generation (configurable threshold)
- Warning log entry on first auto-transform: "Auto-normalized headers per frontmatter config"

---

## Appendix
<!-- ID: appendix -->

### Key File References
- **Implementation:** `doc_management/manager.py` lines 1722-1890
- **Tests:** `tests/test_manage_docs_structured_edit.py` (normalize_headers), `tests/test_manage_docs_generate_toc.py`
- **Frontmatter:** `utils/frontmatter.py`

### Open Questions for Architect
1. Should we add CLI/tool flag override? e.g., `manage_docs(..., skip_auto_transform=True)`
2. Should generate_toc require minimum header count? e.g., only auto-generate if >= 5 headers
3. Should we warn on first auto-transform? Log entry noting transformation occurred

### Verified Claims Matrix

| Claim | Confidence | Evidence Location |
|-------|------------|-------------------|
| normalize_headers is idempotent | 0.98 | test line 233, code line 1770 |
| generate_toc is idempotent | 0.98 | test line 88 |
| Both are O(n) | 0.95 | Code inspection, no nested loops |
| Frontmatter preserved | 0.98 | Lines 177-180 extraction |
| PROGRESS_LOG inappropriate | 0.99 | Format analysis |
| README inappropriate for normalize | 0.95 | Emoji header inspection |

---

*Research complete. Document ready for Architect phase.*
