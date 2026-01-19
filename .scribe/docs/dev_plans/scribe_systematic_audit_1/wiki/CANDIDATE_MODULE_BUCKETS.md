# Candidate Module Buckets

**Purpose**: Consistent tagging system for extractable modules discovered during Wave 1 audits.

**Usage**: When agents identify reusable logic, tag it with one of these buckets in `cross_cutting_concerns.md`.

---

## 1. Formatting & Presentation

**Responsibilities**:
- Convert internal data to user-facing formats
- 3-way routing (readable/structured/compact)
- ANSI color application
- Table/box rendering
- Response finalization

**Examples**:
- `default_formatter.finalize_tool_response()`
- `format_project_sitrep_new()` / `format_project_sitrep_existing()`
- `format_projects_table()`

**Why Extract**: All tools need consistent output formatting, currently scattered across 15+ files

**Tag**: `[BUCKET:formatting]`

---

## 2. Persistence & Storage

**Responsibilities**:
- File I/O operations (read/write/append/rotate)
- Database operations (insert/upsert/query)
- Atomic writes and integrity checks
- State serialization/deserialization

**Examples**:
- `append_line()`, `rotate_file()`
- `backend.insert_entry()`, `backend.upsert_project()`
- SHA256 verification
- JSON state file operations

**Why Extract**: Mix of file-based and DB operations across all tools

**Tag**: `[BUCKET:persistence]`

---

## 3. Indexing & Search

**Responsibilities**:
- Vector indexing (FAISS)
- Full-text search
- Log entry parsing and filtering
- Cross-project search coordination

**Examples**:
- `VectorIndexer.index_entry()`
- `query_entries` search scopes (project/global/all_projects)
- `parse_log_line()` utilities

**Why Extract**: Search and indexing logic spans multiple tools

**Tag**: `[BUCKET:indexing]`

---

## 4. Configuration & Validation

**Responsibilities**:
- Config object handling (AppendEntryConfig, QueryEntriesConfig, etc.)
- Parameter validation and healing
- Schema validation (YAML frontmatter, JSON)
- Default value injection

**Examples**:
- Config class constructors
- Parameter healing in append_entry
- YAML frontmatter validation in manage_docs

**Why Extract**: Every tool has validation logic, much is duplicated

**Tag**: `[BUCKET:config]`

---

## 5. State & Session Management

**Responsibilities**:
- Active project tracking
- Agent session binding
- State file management (state.json, rotation_state.json)
- Project lifecycle transitions (planning → in_progress)

**Examples**:
- `state_manager.get_active_project()`
- `backend.set_agent_project()`
- Project registry lifecycle operations

**Why Extract**: State management is implicit and scattered

**Tag**: `[BUCKET:state]`

---

## 6. Metadata & Enrichment

**Responsibilities**:
- Doc inventory gathering (_gather_project_inventory, _gather_doc_info)
- Entry counting (_count_log_entries)
- Activity metrics computation
- Baseline/current hash tracking

**Examples**:
- set_project.py:61-127 - `_gather_project_inventory()`
- list_projects.py:50-128 - `_gather_doc_info()`
- get_project.py:130-179 - `_gather_doc_info()`

**Why Extract**: Same logic repeated 3+ times

**Tag**: `[BUCKET:metadata]`

---

## 7. Error Handling & Recovery

**Responsibilities**:
- Exception handling patterns
- Error escalation logic
- Graceful degradation
- Fallback value provision

**Examples**:
- Silent exception swallowing (`except Exception: pass`)
- Database failure → file-based fallback
- Parameter healing on invalid inputs

**Why Extract**: Inconsistent error handling across tools

**Tag**: `[BUCKET:error_handling]`

---

## 8. Reminders & Notifications

**Responsibilities**:
- Reminder generation and cooldown tracking
- Project hygiene warnings
- Stale documentation detection
- Logging gap notifications

**Examples**:
- ReminderEngine checks in all tool responses
- Doc drift detection
- Activity staleness warnings

**Why Extract**: Reminder system entangled with business logic

**Tag**: `[BUCKET:reminders]`

---

## 9. Templating & Code Generation

**Responsibilities**:
- Jinja2 template rendering
- Document template scaffolding
- YAML frontmatter generation
- Structured document creation

**Examples**:
- generate_doc_templates.py template engine
- manage_docs.py research/bug report creation
- Frontmatter injection

**Why Extract**: Template logic mixed with business logic

**Tag**: `[BUCKET:templating]`

---

## 10. Utilities & Helpers

**Responsibilities**:
- Time/date formatting (utcnow, format_utc)
- String manipulation
- Path resolution
- ID generation (entry_id, sha256)

**Examples**:
- `utils/time.py` functions
- `utils/files.py` helpers
- Hash computation utilities

**Why Extract**: Pure utilities scattered across modules

**Tag**: `[BUCKET:utilities]`

---

## How to Use

When documenting a candidate module in `cross_cutting_concerns.md`:

```markdown
### Candidate Module: DocInventoryGatherer [BUCKET:metadata]
- Origin: set_project.py:61-127, list_projects.py:50-128, get_project.py:130-179
- Responsibilities: Check doc existence, count lines, detect custom content
- Used by: set_project, list_projects, get_project
- Why it should be shared: Same logic repeated 3x (90-100 LOC each)
- Risks if extracted: Tools may have subtle differences in return shapes
- Unification strategy: Extract base contract, allow tool-specific adapters
```

**Tag with bucket** to enable cross-wave pattern analysis in Phase 6.

---

## Orchestrator Monitoring

**High-confidence refactor candidates** = Same bucket tagged by 2+ independent agents

Example: If Agent A tags `[BUCKET:formatting]` and Agent C independently tags same bucket, that's a **high-confidence unification opportunity**.

Phase 6 Architect uses these buckets to design module boundaries.
