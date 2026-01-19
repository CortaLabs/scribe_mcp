# manage_docs Action Type Analysis

**Purpose**: Document all 20+ action types in manage_docs.py to determine which are related, which should be separate tools, and how dependencies map.

---

## Action Type Catalog

### Document Editing Actions (Core Group)

#### 1. `replace_section`
**Lines**: Routed to `apply_doc_change()` via doc_management (1298-1314)
**Purpose**: Replace content of a section marked with `<!-- ID: section_name -->`
**Parameters**: `doc`, `section`, `content`, `template`, `dry_run`
**Related To**: All core editing actions use same `apply_doc_change()` backend
**Should Be Separate**: NO - part of core document editing group

---

#### 2. `append`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Append content to end of document
**Parameters**: `doc`, `content`, `dry_run`
**Related To**: Core editing group
**Should Be Separate**: NO - shares backend with other edits

---

#### 3. `status_update`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Toggle checklist item status (`[ ]` ↔ `[x]`)
**Parameters**: `doc`, `section`, `metadata.status`, `metadata.proof`, `dry_run`
**Related To**: Core editing group
**Should Be Separate**: NO - specialized edit type

---

#### 4. `apply_patch`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Apply structured or unified diff patch
**Parameters**: `doc`, `edit`, `patch`, `patch_mode`, `patch_source_hash`, `dry_run`
**Related To**: Core editing group
**Should Be Separate**: NO - precision edit mechanism

---

#### 5. `replace_range`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Replace specific line range (body-relative)
**Parameters**: `doc`, `start_line`, `end_line`, `content`, `dry_run`
**Related To**: Core editing group
**Should Be Separate**: NO - line-level edit type

---

#### 6. `replace_text`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Find/replace text within document
**Parameters**: `doc`, `content` (old→new mapping), `dry_run`
**Related To**: Core editing group
**Should Be Separate**: NO - text transformation edit

---

#### 7. `normalize_headers`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Convert headers to canonical ATX format (`# Header`)
**Parameters**: `doc`, `dry_run`
**Related To**: Core editing group (formatting sub-type)
**Should Be Separate**: NO - document formatting utility

---

#### 8. `generate_toc`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Generate table of contents from headers
**Parameters**: `doc`, `dry_run`
**Related To**: Core editing group (formatting sub-type)
**Should Be Separate**: NO - document formatting utility

---

#### 9. `validate_crosslinks`
**Lines**: Routed to `apply_doc_change()` (1298-1314)
**Purpose**: Validate internal document links
**Parameters**: `doc`, `dry_run`
**Related To**: Core editing group (validation sub-type)
**Should Be Separate**: NO - document validation utility

---

**Core Editing Group Summary**:
- **Count**: 9 actions
- **Shared Backend**: All route to `apply_doc_change()` in `doc_management/manager.py`
- **Coupling**: HIGH - these MUST stay together because they share editing infrastructure
- **Should Split**: NO - these are variants of "edit document", not separate concerns

---

### Document Creation Actions (Special Docs Group)

#### 10. `create_research_doc`
**Lines**: Routed to `_handle_special_document_creation()` (1006-1019 → 1926-2186)
**Purpose**: Create research report with template
**Parameters**: `doc_name`, `metadata.research_goal`, `content`, `dry_run`
**Output**: `docs/dev_plans/{project}/research/{doc_name}.md`
**Index**: Updates `research/INDEX.md`
**Related To**: Other create_* actions (shared creation workflow)
**Should Be Separate**: MAYBE - distinct document lifecycle

---

#### 11. `create_bug_report`
**Lines**: Routed to `_handle_special_document_creation()` (1006-1019 → 1926-2186)
**Purpose**: Create bug report with template
**Parameters**: `metadata.category`, `metadata.slug`, `metadata.severity`, `content`, `dry_run`
**Output**: `docs/bugs/{category}/{date}_{slug}/report.md`
**Index**: Updates `docs/bugs/INDEX.md`
**Related To**: Other create_* actions
**Should Be Separate**: MAYBE - bug tracking is a distinct domain

---

#### 12. `create_review_report`
**Lines**: Routed to `_handle_special_document_creation()` (1006-1019 → 1926-2186)
**Purpose**: Create review report with template
**Parameters**: `metadata.stage`, `content`, `dry_run`
**Output**: `REVIEW_REPORT_{stage}_{date}_{time}.md`
**Index**: Updates `REVIEW_INDEX.md`
**Related To**: Other create_* actions
**Should Be Separate**: MAYBE - review workflow is a distinct domain

---

#### 13. `create_agent_report_card`
**Lines**: Routed to `_handle_special_document_creation()` (1006-1019 → 1926-2186)
**Purpose**: Create agent performance evaluation
**Parameters**: `metadata.agent_name`, `metadata.stage`, `content`, `dry_run`
**Output**: `AGENT_REPORT_CARD_{agent}_{stage}_{datetime}.md`
**Index**: Updates `AGENT_CARDS_INDEX.md`
**Related To**: Other create_* actions
**Should Be Separate**: MAYBE - agent evaluation is a distinct domain

---

**Special Document Group Summary**:
- **Count**: 4 actions
- **Shared Backend**: All route to `_handle_special_document_creation()`
- **Coupling**: MEDIUM - shared template rendering + index update workflow
- **Should Split**: MAYBE - each document type has distinct lifecycle:
  - Research: Investigative findings
  - Bugs: Defect tracking
  - Reviews: Quality assurance
  - Agent Cards: Performance evaluation
- **Recommendation**: Could be 4 separate tools with shared `SpecialDocumentCreator` base class

---

### Document Introspection Actions (Query Group)

#### 14. `list_sections`
**Lines**: Routed to `_handle_list_sections()` (1021-1031 → 1710-1767)
**Purpose**: Return all section anchors with line numbers
**Parameters**: `doc`
**Output**: List of `{id, line, file_line}` for each `<!-- ID: ... -->` marker
**Related To**: `list_checklist_items` (both parse document structure)
**Should Be Separate**: NO - document introspection is a single concern

---

#### 15. `list_checklist_items`
**Lines**: Routed to `_handle_list_checklist_items()` (1032-1043 → 1770-1870)
**Purpose**: Parse checklist items with status and line numbers
**Parameters**: `doc`, `metadata.text`, `metadata.case_sensitive`, `metadata.require_match`
**Output**: List of `{line, status, text, section}` for each `- [ ]` or `- [x]` item
**Related To**: `list_sections` (both introspect structure)
**Should Be Separate**: NO - same concern as list_sections

---

**Introspection Group Summary**:
- **Count**: 2 actions
- **Shared Purpose**: Parse document structure for metadata
- **Coupling**: LOW - independent implementations but same domain
- **Should Split**: NO - these are query operations on document structure
- **Note**: Could be unified as `introspect_document(type="sections"|"checklist")`

---

### Search Actions (Search Group)

#### 16. `search` (semantic mode)
**Lines**: Inline handler (1045-1188, ~143 LOC)
**Purpose**: Vector-based semantic search across docs and logs
**Parameters**: `doc`, `metadata.query`, `metadata.search_mode="semantic"`, `metadata.k`, `metadata.min_similarity`, filters
**Output**: Combined doc/log results sorted by similarity
**Related To**: `search` (exact/fuzzy) - same action, different modes
**Should Be Separate**: YES - semantic search is a standalone feature

**Critical Finding**: Semantic search is NOT a manage_docs responsibility. It's a general-purpose search capability that should be available to all tools.

---

#### 17. `search` (exact/fuzzy mode)
**Lines**: Inline handler (1190-1229, ~39 LOC)
**Purpose**: Text-based search within document content
**Parameters**: `doc`, `metadata.query`, `metadata.search_mode="exact"|"fuzzy"`, `metadata.fuzzy_threshold`
**Output**: List of `{doc, path, matches}` where matches are `{line, snippet}` or `{line, snippet, score}`
**Related To**: `search` (semantic) - same action
**Should Be Separate**: MAYBE - text search could be part of document introspection

---

**Search Group Summary**:
- **Count**: 1 action with 2 modes (semantic vs exact/fuzzy)
- **Coupling**: NONE (semantic) / LOW (exact/fuzzy)
- **Should Split**: YES
  - **Semantic search** → Standalone `semantic_search` tool (reusable by all tools)
  - **Exact/fuzzy search** → Could stay in manage_docs or move to `DocumentIntrospector`

---

### Batch Operations (Orchestration Group)

#### 18. `batch`
**Lines**: Routed to `_handle_batch_operations()` (1231-1237 → 1873-1923)
**Purpose**: Execute multiple manage_docs actions sequentially
**Parameters**: `metadata.operations` (list of action specs)
**Output**: Array of results, stops on first failure
**Related To**: None - wraps other actions
**Should Be Separate**: NO - this is a manage_docs feature, not reusable

---

**Batch Group Summary**:
- **Count**: 1 action
- **Coupling**: HIGH - depends on manage_docs itself
- **Should Split**: NO - batch is a manage_docs orchestration feature

---

### Document Registration (Lifecycle Group)

#### 19. `create_doc`
**Lines**: Special handling (1256-1296), routed to `apply_doc_change()` (1298-1314)
**Purpose**: Create new document and optionally register in project state
**Parameters**: `doc`, `content`, `template`, `metadata.register_doc`, `metadata.register_as`, `dry_run`
**Output**: New document file + optional project.docs update
**Related To**: Core editing group (uses same backend)
**Should Be Separate**: NO - document lifecycle is part of manage_docs

---

**Lifecycle Group Summary**:
- **Count**: 1 action
- **Coupling**: MEDIUM - touches project state registry
- **Should Split**: NO - document registration is a manage_docs responsibility

---

## Action Dependency Map

```
manage_docs (main router)
├── Core Editing Group (9 actions)
│   ├── replace_section ──┐
│   ├── append ───────────┤
│   ├── status_update ────┤
│   ├── apply_patch ──────┤── apply_doc_change() (doc_management)
│   ├── replace_range ────┤
│   ├── replace_text ─────┤
│   ├── normalize_headers ┤
│   ├── generate_toc ─────┤
│   └── validate_crosslinks┘
│
├── Special Docs Group (4 actions)
│   ├── create_research_doc ──┐
│   ├── create_bug_report ────┤── _handle_special_document_creation()
│   ├── create_review_report ─┤   ├── Template rendering (Jinja2)
│   └── create_agent_report_card┘  ├── Index updates (4 updaters)
│                                   └── Storage backend mirroring
│
├── Introspection Group (2 actions)
│   ├── list_sections ────────── _handle_list_sections()
│   └── list_checklist_items ─── _handle_list_checklist_items()
│
├── Search Group (1 action, 2 modes)
│   └── search
│       ├── semantic ──────────── Inline handler (184 LOC)
│       └── exact/fuzzy ───────── Inline handler (39 LOC)
│
├── Batch Group (1 action)
│   └── batch ────────────────── _handle_batch_operations()
│
└── Lifecycle Group (1 action)
    └── create_doc ───────────── apply_doc_change() + registry update
```

---

## Action Splitting Recommendations

### HIGH PRIORITY: Extract Semantic Search

**Actions Affected**: `search` (semantic mode)
**Recommendation**: Create new `tools/semantic_search.py` as standalone MCP tool

**Rationale**:
1. Semantic search is NOT a manage_docs responsibility
2. Should be available to all tools (append_entry, query_entries, etc.)
3. 184 LOC of self-contained logic
4. No coupling to manage_docs internals

**New Tool Signature**:
```python
async def semantic_search(
    query: str,
    content_type: str = "all",  # "doc" | "log" | "all"
    k: int = 10,
    min_similarity: float = 0.7,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Vector-based semantic search across docs and logs."""
```

**Impact**:
- manage_docs keeps `search` action but delegates to semantic_search tool
- All tools can now use semantic search
- Reduces manage_docs LOC by 184

---

### MEDIUM PRIORITY: Consider Splitting Special Doc Creation

**Actions Affected**: `create_research_doc`, `create_bug_report`, `create_review_report`, `create_agent_report_card`
**Recommendation**: MAYBE create 4 separate tools OR keep as-is with shared infrastructure

**Rationale for Splitting**:
1. Each document type has distinct lifecycle
2. Research vs bugs vs reviews are different domains
3. Each has its own index management
4. Reduces manage_docs action count from 20+ to 16

**Rationale for Keeping Together**:
1. Shared template rendering infrastructure
2. Shared index update pattern (85% duplicated code)
3. Shared storage backend mirroring
4. Only ~260 LOC for all 4 actions

**Recommendation**: KEEP TOGETHER until Phase 6 when `IndexGenerator` is extracted. Then re-evaluate if splitting makes sense.

---

### LOW PRIORITY: Unify Introspection Actions

**Actions Affected**: `list_sections`, `list_checklist_items`
**Recommendation**: Consider unifying as `introspect_document(type="sections"|"checklist"|"structure")`

**Rationale**:
1. Both parse document structure
2. Both return metadata about document contents
3. Could be extended with `type="headers"`, `type="links"`, etc.

**Impact**: Reduces action count by 1, improves consistency

---

## Action Group Summary

| Group | Action Count | Should Split | Priority |
|-------|--------------|--------------|----------|
| **Core Editing** | 9 | NO | N/A (keep together) |
| **Special Docs** | 4 | MAYBE | MEDIUM |
| **Introspection** | 2 | NO | LOW (unify instead) |
| **Search** | 1 (2 modes) | YES (semantic) | HIGH |
| **Batch** | 1 | NO | N/A (keep) |
| **Lifecycle** | 1 | NO | N/A (keep) |
| **TOTAL** | 18 actions | Extract 1-5 | - |

---

## Before/After Models

### Before: All 18 Actions in manage_docs
```
tools/manage_docs.py (2,663 LOC)
├── 9 core editing actions → apply_doc_change()
├── 4 special doc creation actions → _handle_special_document_creation()
├── 2 introspection actions → _handle_list_*()
├── 1 search action (2 modes) → inline handlers (223 LOC)
├── 1 batch action → _handle_batch_operations()
└── 1 lifecycle action → create_doc special case
```

### After: Semantic Search Extracted
```
tools/manage_docs.py (2,479 LOC)
├── 9 core editing actions → apply_doc_change()
├── 4 special doc creation actions → _handle_special_document_creation()
├── 2 introspection actions → _handle_list_*()
├── 1 search action → delegates to tools/semantic_search.py
├── 1 batch action → _handle_batch_operations()
└── 1 lifecycle action → create_doc special case

tools/semantic_search.py (200 LOC) ← NEW
└── semantic_search(query, filters, k, min_similarity) → results
```

### After: Special Docs Split (Optional)
```
tools/manage_docs.py (2,200 LOC)
├── 9 core editing actions → apply_doc_change()
├── 2 introspection actions → _handle_list_*()
├── 1 search action → delegates to semantic_search
├── 1 batch action → _handle_batch_operations()
└── 1 lifecycle action → create_doc

tools/semantic_search.py (200 LOC)
tools/create_research_doc.py (80 LOC) ← NEW
tools/create_bug_report.py (80 LOC) ← NEW
tools/create_review_report.py (80 LOC) ← NEW
tools/create_agent_report_card.py (80 LOC) ← NEW

utils/special_doc_creator.py (150 LOC) ← NEW (shared infrastructure)
├── Template rendering
├── Index updates (via IndexGenerator)
└── Storage backend mirroring
```

---

## Critical Findings

1. **Semantic Search Must Be Extracted**: It's a standalone feature, not a manage_docs responsibility. Current architecture buries it in a 184-line inline handler.

2. **Core Editing Group Is Tightly Coupled**: All 9 editing actions route to `apply_doc_change()` and share the same infrastructure. These MUST stay together.

3. **Special Doc Creation Could Be Split**: The 4 create_* actions are independent domain operations that happen to share infrastructure. Splitting would reduce manage_docs complexity but requires extracting shared code first.

4. **Batch Is Not Reusable**: The batch action is manage_docs-specific. Don't try to extract it.

5. **Introspection Actions Are Underutilized**: `list_sections` and `list_checklist_items` are useful query operations that could be exposed more prominently (maybe as a unified `introspect` action).

---

## Implementation Order

**Phase 1** (HIGH priority):
1. Extract semantic search to standalone tool
2. Update manage_docs to delegate search action

**Phase 2** (MEDIUM priority):
1. Extract `IndexGenerator` to unify 4 index updaters
2. Re-evaluate if special doc creation should be split

**Phase 3** (LOW priority):
1. Unify introspection actions as `introspect_document(type)`
2. Extract `DocumentIntrospector` utility class

---

**Conclusion**: Of 18 actions, **1 must be extracted** (semantic search), **4 could be split** (special docs), and **13 should stay** (core editing, introspection, batch, lifecycle). Total extractable: 1-5 actions depending on Phase 2 decisions.
