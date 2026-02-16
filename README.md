# 📝 Scribe MCP Server

<div align="center">

**[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](tests/)**
**[![Version](https://img.shields.io/badge/version-2.2-blue)](docs/whitepapers/)**
**[![License](https://img.shields.io/badge/license-Community+Small%20Business-orange)](LICENSE)**

*Enterprise-grade documentation governance for AI-powered development — by Corta Labs*

**Drop-in ready** • **13+ specialized templates** • **Zero-config SQLite** • **Production-tested**

</div>

---

## Update v2.2 (Architecture Cleanup)

Scribe MCP v2.2 delivers major architectural improvements:

**Performance:**
- **Connection Pooling**: New `storage/pool.py` with SQLiteConnectionPool delivers 50-80% latency reduction
- **Optimized Indexes**: New composite indexes for agent/emoji filtering

**Code Quality:**
- **ResponseFormatter Decomposition**: Monolithic 2,934-line class split into 7 specialized modules in `utils/formatters/`
- **Database-First State**: Session state migrated from state.json to database

**Data Management:**
- **Retention Policy**: New `scribe_entries_archive` table with configurable cleanup (default 90 days)
- **Agent Isolation**: All tools require `agent` parameter for session isolation

---

## History: Update v2.1.1 (Diff Editor, Readable Output & ANSI Colors)

Scribe MCP 2.1.1 introduces foundational document lifecycle upgrades, including a fully automated YAML frontmatter engine with round-trip safety, canonical metadata defaults, and extensible schema support. Frontmatter is created on first edit if missing, auto-updates `last_updated`, and supports explicit overrides without breaking existing fields. These changes establish a metadata plane separate from document body content, enabling safe diff operations, deterministic header/TOC tooling, and template-driven document creation.

**New: Enhanced Readable Output (Phase 1.5/1.6)**
- **ANSI Color Support**: Tool output now renders with colors in Claude Code/Codex - cyan boxes, green line numbers, bold titles
- **Green Line Numbers**: Clean `    1. content` format with dot separator, matching Claude's native Read tool style
- **CallToolResult Fix**: Workaround for Issue #9962 - returns TextContent-only for proper newline rendering
- **Config-Driven Colors**: Enable/disable via `use_ansi_colors: true` in `.scribe/config/scribe.yaml`
- **5-Char Line Padding**: Consistent line number width for improved readability

Structured edits are now the default path: agents express intent, the server compiles and applies deterministic mutations, and diagnostics remain explicit. Structural actions no longer auto-heal doc targets; if `doc_name` is not registered, the action fails with `DOC_NOT_FOUND` rather than redirecting the write.

- `manage_docs` now supports **apply_patch** and **replace_range** for precise edits.
- `apply_patch` auto-detects mode: unified when `patch` provided, structured when `edit` provided.
- `patch_source_hash` enforces stale-source protection for patches.
- Reminder system teaches **scaffold-only** `replace_section`, preferring structured/line edits.
- New doc lifecycle actions: `normalize_headers`, `generate_toc`, `create`, `validate_crosslinks`.
- `create` is the unified document creation action. Use `metadata.doc_type` to specify type: `custom`, `research`, `bug`, `review`, or `agent_card`. Content goes in `metadata.body`. Use `metadata.register_doc=true` to add the doc to the project registry.
- `validate_crosslinks` is read-only diagnostics (no write, no doc_updates log).
- `normalize_headers` supports ATX headers with or without space and Setext (`====` / `----`), skipping fenced code blocks. Output is canonical ATX.
- `generate_toc` uses GitHub-style anchors (NFKD normalization, ASCII folding, emoji removal, punctuation collapse, de-duped suffixes).
- Structural actions validate `doc_name` against the registry and fail hard on unknown docs (no silent redirects).

**New: `read_file` - Complete Code Intelligence System (Phase 5)**

The `read_file` tool is now a comprehensive code intelligence platform for Python and Markdown files, providing SWE agents with instant codebase understanding without reading full files:

**Python Intelligence:**
- **Full Signature Extraction**: Captures complete function/method signatures with type hints, default values, and return types
  - Example: `async def fetch_project(self, name: str) -> Optional[ProjectRecord]`
- **Line Range Analysis**: Shows start-end lines for every class, function, and method with line counts for complexity assessment
  - Example: `async def _initialise(self) -> None (lines 645-1121 (477))` - instantly identifies a 477-line method needing refactoring
- **Class Structure Display**: Shows class hierarchy with first 10 methods by default, including async markers
- **Structure Filtering**: Regex-based search to find specific classes or functions
  - Example: `structure_filter="validate"` finds all validation functions with full signatures
- **Structure Pagination**: Browse large classes page-by-page (default: 10 items/page)
  - Navigate through a 62-method class: page 1 shows methods 1-10, page 2 shows 11-20, etc.
- **Dependency Analysis**: Static import analysis with resolved paths for local modules

**Markdown Intelligence:**
- **Heading Extraction**: Complete document outline with all heading levels and line numbers
- **Quick Navigation**: Jump directly to specific sections using extracted line numbers

**Complete Workflow Example:**
```python
# Step 1: Find the class (scan_only mode - zero content, pure metadata)
read_file(path="storage/sqlite.py", mode="scan_only", structure_filter="SQLiteStorage")
# → Shows: class SQLiteStorage at lines 32-2334 (2303 lines)
#          Methods (page 1 of 7, showing 1-10 of 62)

# Step 2: Browse methods with pagination
read_file(path="storage/sqlite.py", mode="scan_only",
          structure_filter="SQLiteStorage", structure_page=2)
# → Methods 11-20 with full signatures and line ranges
#   Found: async def fetch_recent_entries(self) -> List[Dict[str, Any]] (lines 338-427 (90))

# Step 3: Read exact method implementation
read_file(path="storage/sqlite.py", mode="line_range", start_line=338, end_line=427)
# → Full method code for analysis

# Step 4: Edit with confidence
Edit(file_path="storage/sqlite.py", old_string="...", new_string="...")
```

**Key Benefits:**
- **Token Efficiency**: Get complete structural overview without reading full file content
- **Instant Complexity Assessment**: Line counts reveal 477-line monsters needing refactoring
- **Type-Aware Navigation**: Full signatures show exactly how to call each function
- **Regex Precision**: Find all functions matching `^_validate.*|^_sanitize` in seconds
- **Pagination for Scale**: Browse classes with 50+ methods without overwhelming output

Parameters: `path`, `mode` (scan_only/chunk/page/line_range/search), `structure_filter`, `structure_page`, `structure_page_size`, `include_dependencies`, `format`

**New: `search` - Multi-File Codebase Search (v2.2)**

The `search` tool provides grep/ripgrep-equivalent codebase search directly through MCP, with repo-boundary enforcement and audit logging:

- **Regex and Literal Patterns**: Full regex by default, with `regex=False` for literal string matching
- **File Filtering**: Filter by glob pattern (`glob="*.py"`) or file type (`type="py"`)
- **Three Output Modes**: `content` (matching lines with context), `files_with_matches` (file paths only), `count` (match counts per file)
- **Context Control**: Configurable before/after context lines around matches
- **Multiline Matching**: Patterns can span multiple lines with `multiline=True`
- **Safety Limits**: Configurable max matches per file (50), total matches (200), max files (100), and file size cap (10MB)

```python
# Find all async methods in Python files
search(agent="CoderAgent", pattern="async def ", type="py", output_mode="content", context_lines=2)

# Count occurrences of a function across the codebase
search(agent="CoderAgent", pattern="append_entry", output_mode="count")

# Search with glob filter
search(agent="CoderAgent", pattern="class.*Storage", glob="storage/*.py", output_mode="files_with_matches")
```

Parameters: `agent`, `pattern`, `path`, `glob`, `type`, `output_mode`, `format`, `context_lines`, `before_context`, `after_context`, `case_insensitive`, `regex`, `multiline`, `max_matches_per_file`, `max_total_matches`, `max_files`, `line_numbers`, `skip_binary`, `max_file_size_mb`

**New: `edit_file` - Safe File Editing with Audit Trail (v2.2)**

The `edit_file` tool provides exact string replacement with built-in safety mechanisms:

- **Read-Before-Edit Enforcement**: The file MUST have been read with `read_file` in the current session before editing (tool-enforced)
- **Dry-Run by Default**: `dry_run=True` is the default -- you must explicitly set `dry_run=False` to commit changes
- **Exact String Matching**: Finds and replaces exact strings (no regex), failing clearly if the target string is not found or is ambiguous
- **Replace All Mode**: Optional `replace_all=True` for renaming variables or updating repeated patterns
- **Diff Preview**: Dry-run mode returns a unified diff preview before committing
- **Repo-Boundary Enforcement**: Cannot edit files outside the repository root

```python
# Preview a change (dry_run=True is default)
edit_file(agent="CoderAgent", path="config/settings.py", old_string="DEBUG = True", new_string="DEBUG = False")

# Commit a change
edit_file(agent="CoderAgent", path="config/settings.py", old_string="DEBUG = True", new_string="DEBUG = False", dry_run=False)

# Rename across file
edit_file(agent="CoderAgent", path="utils/helpers.py", old_string="old_name", new_string="new_name", replace_all=True, dry_run=False)
```

Parameters: `agent`, `path`, `old_string`, `new_string`, `replace_all` (default: False), `dry_run` (default: True), `format`

- `scribe_doctor` reports repo root, config, plugin status, and vector readiness for faster diagnostics.
- `manage_docs` now supports semantic search via `action="search"` with `search_mode="semantic"`, including doc/log separation and `doc_k`/`log_k` overrides.
- Vector indexing now prefers registry-managed docs only; log/rotated-log files are excluded from doc indexing.
- Reindex supports `--rebuild` (clear index), `--safe` (low-thread fallback), and `--wait-for-drain` to block until embeddings are written.

Example (structured mode with edit):
```json
{
  "action": "apply_patch",
  "doc_name": "architecture",
  "edit": {
    "type": "replace_range",
    "start_line": 12,
    "end_line": 12,
    "content": "Updated line\n"
  }
}
```

Example (unified diff mode - auto-detected when patch provided):
```json
{
  "action": "apply_patch",
  "doc_name": "architecture",
  "patch": "<compiler output>"
}
```

## 🚀 Why Scribe MCP?

Scribe transforms how AI agents and developers maintain project documentation. Instead of scattered notes and outdated docs, Scribe provides **bulletproof audit trails**, **automated template generation**, and **cross-project intelligence** that keeps your entire development ecosystem in sync.

**Perfect for:**
- 🤖 **AI Agent Teams** - Structured workflows and quality grading
- 🏢 **Enterprise Teams** - Audit trails and compliance documentation
- 👨‍💻 **Solo Developers** - Automatic documentation that actually works
- 📚 **Research Projects** - Structured logs and reproducible reports

**Immediate Value:**
- ✅ **30-second setup** - Drop into any repository and start logging
- 🎯 **18+ specialized templates** - From architecture guides to bug reports
- 🔍 **Cross-project search** - Find patterns across your entire codebase
- 📊 **Agent report cards** - Performance grading for AI workflows
- 🛡️ **Bulletproof storage** - Atomic operations with crash recovery

## ⚡ Quick Start

**Get Scribe running in under 60 seconds (MCP-first, CLI optional):**

### 1️⃣ Install Dependencies
```bash
# Clone and navigate to Scribe
git clone <your-repo-url>
cd scribe_mcp

# Set up Python environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Scribe (editable + dev extras)
python -m pip install -e ".[dev]"

# Optional: verify wheel/non-editable install path too
python -m pip install .
```

### 2️⃣ Add Scribe MCP Server to Claude Code, Codex
- Codex CLI registration example:
  ```bash
  codex mcp add scribe \
    --env SCRIBE_ROOT=/home/path/to/scribe_mcp \
    --env REPO_ROOT=/home/path/to/your_project \
    --env SCRIBE_STORAGE_BACKEND=sqlite \
    -- bash -lc 'cd /home/path/to/scribe_mcp && exec scribe-server'
  ```
- Claude Code registration example:
  ```bash
  claude mcp add scribe \
    --env SCRIBE_ROOT=/home/path/to/scribe_mcp \
    --env REPO_ROOT=/home/path/to/your_project \
    --env SCRIBE_STORAGE_BACKEND=sqlite \
    -- bash -lc 'cd /home/path/to/scribe_mcp && exec scribe-server'
  ```
- Global Claude MCP example:
  ```bash
  claude mcp add scribe --scope user \
    --env SCRIBE_ROOT=/home/path/to/scribe_mcp \
    --env REPO_ROOT=/home/path/to/your_project \
    --env SCRIBE_STORAGE_BACKEND=sqlite \
    -- bash -lc 'cd /home/path/to/scribe_mcp && exec scribe-server'
  ```

Compatibility note: legacy launch `python -m server` still works during migration.

Once connected from Claude / Codex MCP:

- Use **`set_project`** to register/select a project and bootstrap dev_plan docs (pass `root=/abs/path/to/repo` to work in any repo).
- Use **`append_entry`** for all logging (single/bulk).
- Use **`manage_docs`** for architecture/phase/checklist updates.  **2.1.1** introduces diff edits.
- Use **`read_file`** for safe, auditable file reads (scan/chunk/page/search).
- Use **`scribe_doctor`** for readiness checks (repo root, config, vector index status).
- Use **`read_recent` / `list_projects`** to resume context after compaction.

**Automatic log routing (BUG / SECURITY)**
- `status=bug` (or a bug emoji) will also write to `BUG_LOG.md` when required meta is present (`severity`, `component`, `status`).
- Security events can also tee to `SECURITY_LOG.md` (example: use a security emoji, or `--meta security_event=true,impact=...,status=...`).
- If required meta is missing, Scribe returns a teaching reminder instead of inventing data.


### 3️⃣ (Optional) Manual CLI Tool Calls

For shell workflows or CI checks, use the unified CLI runtime:

```bash
# List all registered MCP tools
python -m scribe_mcp.cli.main tools --json

# Call any tool directly (example: append_entry)
python -m scribe_mcp.cli.main call append_entry \
  --agent Codex \
  --arg message="Scribe CLI call works" \
  --arg status=success
```

This path uses the same runtime dispatcher as MCP (`invoke_tool`), so mode/session guard behavior stays aligned.

---

## 🎯 Try These Examples

**Project Management:**
```bash
# Log project milestones
python -m scribe_mcp.scripts.scribe "Completed authentication module" --status success --meta component=auth,tests=47

# Track bugs and issues
python -m scribe_mcp.scripts.scribe "Fixed JWT token expiry bug" --status bug --meta severity=high,component=security
```


**Research Workflows:**
```bash
# Document research findings
python -m scribe_mcp.scripts.scribe "Discovered performance bottleneck in database queries" --status info --meta research=true,impact=high
```

**Team Collaboration:**
```bash
# List all projects
python -m scribe_mcp.scripts.scribe --list-projects

# Switch between projects
python -m scribe_mcp.scripts.scribe "Starting new feature work" --project frontend --status plan
```

---

## 🐳 Docker Deployment

**Deploy Scribe MCP as a containerized service with SSE transport:**

### Quick Start (Standalone)

```bash
# Build the image
docker build -f deploy/Dockerfile -t scribe-mcp:latest .

# Run the container
docker run -d \
  --name scribe-mcp \
  -p 8200:8200 \
  -v scribe_data:/app/.scribe \
  scribe-mcp:latest

# Verify health
curl http://localhost:8200/health
```

### Quick Start (With Council + PostgreSQL)

```bash
# From MCP_SPINE root
docker compose \
  -f council_mcp/deploy/docker-compose.yaml \
  -f scribe_mcp/deploy/docker-compose.scribe.yaml \
  up -d
```

### Connecting MCP Clients to Docker

Configure your MCP client for SSE transport instead of stdio:

```json
{
  "mcpServers": {
    "scribe": {
      "url": "http://localhost:8200/sse"
    }
  }
}
```

**Key features:**
- SSE transport on port 8200 (HTTP-based, replaces stdio)
- PostgreSQL support with Docker secrets for credentials
- Compose overlay pattern for Council integration
- Health checks at `/health` endpoint
- Non-root user (UID 1001), minimal attack surface

For full documentation including configuration, PostgreSQL setup, troubleshooting, and Council integration, see **[deploy/README.md](deploy/README.md)**.

---

## 🛠️ Installation Options

### Prerequisites
- **Python 3.11+** - Modern Python with async support
- **pip** - Standard Python package manager
- **Optional:** PostgreSQL for team deployments (SQLite works out of the box)

### Storage Backends

**🗄️ SQLite (Default - Zero Config)**
- Perfect for solo developers and small teams
- No setup required - just run and go
- Automatic database creation and management

**🐘 PostgreSQL (Enterprise)**
- Ideal for large teams and production deployments
- One-command interactive bootstrap (no env exports required):
  ```bash
  scribe bootstrap
  ```
- The interactive flow now explains setup-only vs runtime values:
  - `Scribe admin database`: usually `postgres`, used for admin/setup connections.
  - `Scribe app database`: where Scribe stores runtime data.
- Bootstrap writes `.env` keys automatically (`SCRIBE_STORAGE_BACKEND`, `SCRIBE_DB_URL`, schema/role fields).
- For CI or scripting (non-interactive), pass flags directly:
  ```bash
  scribe bootstrap --no-interactive --superuser-password '<superuser-password>' --app-db scribe --schema scribe
  ```

### Postgres Env Vars (Runtime + MCP)

When running Scribe in Postgres mode (including via MCP), set these environment variables in the server process:

- `SCRIBE_STORAGE_BACKEND=postgres`
- `SCRIBE_DB_URL=postgresql://<app_user>:<app_password>@<host>:<port>/<app_db>`
- `SCRIBE_POSTGRES_SCHEMA=scribe` (default schema namespace)
- `SCRIBE_DB_SCHEMA=...` (supported alias for schema; `SCRIBE_POSTGRES_SCHEMA` takes precedence)

Optional pool/network tuning (recommended for remote DBs):

- `SCRIBE_POSTGRES_POOL_MIN_SIZE=2`
- `SCRIBE_POSTGRES_POOL_MAX_SIZE=20`
- `SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS=10`
- `SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS=30`
- `SCRIBE_POSTGRES_CONNECT_RETRIES=3`
- `SCRIBE_POSTGRES_CONNECT_RETRY_BACKOFF_SECONDS=1.0`
- `SCRIBE_POSTGRES_MAX_INACTIVE_SECONDS=300`

These can be generated automatically by `scribe bootstrap` into your `.env`, then passed through your MCP client configuration.

### MCP Integration

In all examples below:
- **`SCRIBE_ROOT`** = where Scribe is installed (the directory you run `scribe-server` from).
- **`REPO_ROOT`** = the project repository you want Scribe to work in (the repo that gets `.scribe/` docs/plans once selected).
- Select the repo in-session with `set_project(..., root=/abs/path/to/repo)`.

**For Claude Desktop (JSON config):**
```jsonc
{
  "mcpServers": {
    "scribe": {
      // Run from SCRIBE_ROOT (where Scribe is installed)
      "command": "bash",
      "args": [
        "-lc",
        "cd /absolute/path/to/SCRIBE_ROOT && exec scribe-server"
      ],
      "env": {
        "SCRIBE_ROOT": "/absolute/path/to/SCRIBE_ROOT",
        "REPO_ROOT": "/absolute/path/to/YOUR_PROJECT_ROOT",
        // SQLite (default): "sqlite"
        // Postgres: set backend + db url (+ optional schema)
        "SCRIBE_STORAGE_BACKEND": "postgres",
        "SCRIBE_DB_URL": "postgresql://scribe_app:<password>@127.0.0.1:5432/scribe",
        "SCRIBE_POSTGRES_SCHEMA": "scribe"
      }
    }
  }
}
```

**For Codex / Claude Code CLI:**
```bash
# SQLite mode (default)
codex mcp add scribe \
  --env SCRIBE_ROOT=/absolute/path/to/SCRIBE_ROOT \
  --env REPO_ROOT=/absolute/path/to/YOUR_PROJECT_ROOT \
  --env SCRIBE_STORAGE_BACKEND=sqlite \
  -- bash -lc 'cd /absolute/path/to/SCRIBE_ROOT && exec scribe-server'

# Postgres mode
codex mcp add scribe \
  --env SCRIBE_ROOT=/absolute/path/to/SCRIBE_ROOT \
  --env REPO_ROOT=/absolute/path/to/YOUR_PROJECT_ROOT \
  --env SCRIBE_STORAGE_BACKEND=postgres \
  --env SCRIBE_DB_URL='postgresql://scribe_app:<password>@127.0.0.1:5432/scribe' \
  --env SCRIBE_POSTGRES_SCHEMA=scribe \
  -- bash -lc 'cd /absolute/path/to/SCRIBE_ROOT && exec scribe-server'
```

Notes:
- `REPO_ROOT` is a launch-time convenience value for your MCP config.
- Scribe project context is selected in-session via `set_project(name=..., root=/abs/path/to/repo)`.
- The launch command should run from `SCRIBE_ROOT`, not the target project repo.

---

## 🌐 Using Scribe Outside This Repo

You can run Scribe from any codebase (not just `MCP_SPINE`) by pointing it at that project’s root:

1. Start the MCP server from your Scribe install path (`SCRIBE_ROOT`).
2. Set `REPO_ROOT=/abs/path/to/your/repo` in your MCP config so the target repo is explicit.
3. Call `set_project(..., root=/abs/path/to/your/repo)` to activate that repo and create/update its `.scribe/` workspace.
4. Use `set_project(..., root=/abs/path/to/another/repo)` to switch repositories without re-registering MCP.
5. Optional env vars:
   - `SCRIBE_STATE_PATH=/abs/path/to/state.json` **(DEPRECATED in v2.2 - sessions now stored in database)**
   - `SCRIBE_STORAGE_BACKEND=postgres` and `SCRIBE_DB_URL=postgresql://...` if you want Postgres.
6. Prefer launching via installed entry points (`scribe-server`, `scribe`) so no manual `PYTHONPATH` wiring is required.

---

## 🧠 Project Registry & Lifecycle (High-Level)

Scribe includes a **SQLite-backed Project Registry** that tracks every project’s lifecycle and documentation state:

- **Lifecycle states**: `planning`, `in_progress`, `blocked`, `complete`, `archived`, `abandoned`.
- **Core hooks**:
  - `set_project` – bootstraps docs (`ARCHITECTURE_GUIDE`, `PHASE_PLAN`, `CHECKLIST`, `PROGRESS_LOG`) and ensures a registry row exists.
  - `append_entry` – writes progress logs, updates activity metrics, and can auto‑promote `planning` → `in_progress` once docs + first entry exist.
  - `manage_docs` – applies atomic doc updates and records baseline/current hashes and doc‑hygiene flags in the registry.
  - `list_projects` – surfaces registry data (status, timestamps, counts, tags, `meta.activity`, `meta.docs.flags`) with filters like `status`, `tags`, and `order_by`.

At a glance, you can:
- See which projects are fresh, stale, or long inactive.
- Detect when architecture/phase/checklist docs are still at template state.
- Spot drift between implementation logs and documentation.

For full technical details, see `docs/whitepapers/scribe_mcp_whitepaper.md`.

---

## 📜 License & Commercial Use

Scribe MCP is **source-available** and free to use for:

- Individual developers
- Open-source contributors
- Researchers and educational use
- Small teams and small businesses that:
  - Have **fewer than 25 employees**, and
  - Generate **less than $1,000,000 USD in annual revenue**, and
  - Are **not** selling, hosting, or packaging Scribe MCP (or derivatives) as part of a paid product or service.

You **may not** use Scribe MCP under the community license if:

- Your organization exceeds the employee or revenue limits above, or
- You embed Scribe MCP into a paid SaaS, internal platform, or commercial agent/orchestration product.

For enterprise or large-scale commercial use, contact **licensing@cortalabs.com** to obtain a commercial license.

Details:

- Current code is licensed under the **Scribe MCP License (Community + Small Business License)** in `LICENSE`.
- Earlier snapshots were MIT-licensed; see `LICENSE_HISTORY.md` for historical licensing context.

Notes:
- `.env` is auto-loaded on startup when present (via python-dotenv); shell exports/direnv still work the same.
- Overlap checks only block true path collisions (same progress_log/docs_dir). Sharing one repo root with many dev_plan folders is supported.

---

## 🎨 Template System Showcase

**Scribe includes 13+ specialized templates** that auto-generate professional documentation:

### 📋 Document Templates
- **📐 Architecture Guides** - System design and technical blueprints
- **📅 Phase Plans** - Development roadmaps with milestones
- **✅ Checklists** - Verification ledgers with acceptance criteria
- **🔬 Research Reports** - Structured investigation documentation
- **🐛 Bug Reports** - Automated issue tracking with indexing
- **📊 Agent Report Cards** - Performance grading and quality metrics
- **📝 Progress Logs** - Append-only audit trails with UTC timestamps
- **🔒 Security Logs** - Compliance and security event tracking

### 🚀 Template Features
- **🔒 Security Sandboxing** - Jinja2 templates run in restricted environments
- **📝 Template Inheritance** - Create custom template families
- **🎯 Smart Discovery** - Project → Repository → Built-in template hierarchy (precedence: `.scribe/templates` → repo custom → project templates → packs → built-ins)
- **⚡ Atomic Generation** - Bulletproof template creation with integrity verification

For a deeper dive into available variables and expected metadata per template, see `docs/TEMPLATE_VARIABLES.md`.

### Example: Generate Architecture Guide
```bash
# Auto-generate a complete architecture document
python -m scribe_mcp.scripts.scribe "Generated architecture guide for new project" --status success --meta template=architecture,auto_generated=true
```

---

## 💻 CLI Power Tools

**Scribe's command-line interface (386 lines of pure functionality)** gives you complete control:

### 🎯 Core Commands
```bash
# List all available projects
python -m scribe_mcp.scripts.scribe --list-projects

# Log with rich metadata
python -m scribe_mcp.scripts.scribe "Fixed critical bug" \
  --status success \
  --emoji 🔧 \
  --meta component=auth,tests=12,severity=high

# Dry run to preview entries
python -m scribe_mcp.scripts.scribe "Test message" --dry-run

# Switch between projects
python -m scribe_mcp.scripts.scribe "Starting frontend work" \
  --project mobile_app \
  --status plan
```

### 🎨 Rich Features
- **🎭 Emoji Support** - Built-in emoji mapping for all status types
- **📊 Metadata Tracking** - Rich key=value metadata for organization
- **🔍 Multiple Log Types** - Progress, bugs, security, and custom logs
- **📅 Timestamp Control** - Override timestamps for bulk imports
- **🎯 Project Discovery** - Automatic project configuration detection

### Status Types & Emojis
- `info` ℹ️ - General information and updates
- `success` ✅ - Completed tasks and achievements
- `warn` ⚠️ - Warning messages and cautions
- `error` ❌ - Errors and failures
- `bug` 🐞 - Bug reports and issues
- `plan` 📋 - Planning and roadmap entries

---

## 🔍 Enterprise Features

### 📊 Agent Report Cards
**Performance grading infrastructure** for AI workflows:
- Quality metrics tracking and trend analysis
- Performance levels with UPSERT operations
- Automated agent evaluation and reporting

### 🔒 Security & Compliance
- **🛡️ Security Sandboxing** - Restricted Jinja2 environments with 22+ built-in controls
- **📋 Audit Trails** - Complete change tracking with metadata
- **🔐 Access Control** - Path validation and input sanitization
- **📊 Compliance Reporting** - Structured logs for regulatory requirements

### ⚡ Advanced Search
**Phase 4 Enhanced Search** capabilities:
- 🔍 **Cross-Project Validation** - Find patterns across your entire codebase
- 📊 **Relevance Scoring** - 0.0-1.0 quality filtering
- 🎯 **Code Reference Verification** - Validate referenced code exists
- 📅 **Temporal Filtering** - Search by time ranges ("last_30d", "last_7d")

### 📝 Documentation Management
**Structured doc editing with full schema exposure**:
- 🔧 **Complete MCP Schema** - All `manage_docs` parameters properly exposed via JSON Schema
- 🎯 **Type-Safe Operations** - Proper parameter typing for reliable tool discovery and validation
- 📋 **Action-Driven Interface** - Atomic updates for architecture, phase plans, checklists, and research docs

#### `manage_docs` Quick Reference

**7 Primary Actions:**

| Action | Purpose | Required Params |
|--------|---------|-----------------|
| `create` | Create new doc (research/bug/custom) | `doc_name`, `metadata.doc_type` |
| `replace_section` | Replace content by section anchor | `doc_name`, `section`, `content` |
| `apply_patch` | Apply unified diff patch | `doc_name`, `patch` |
| `replace_range` | Replace explicit line range | `doc_name`, `start_line`, `end_line`, `content` |
| `replace_text` | Find/replace text pattern | `doc_name`, `metadata.find`, `metadata.replace` |
| `append` | Append content to doc/section | `doc_name`, `content` |
| `status_update` | Update checklist item status | `doc_name`, `section`, `metadata` |

**Global Optional Params:** `project`, `dry_run`, `target_dir`

**doc_type Values** (INSIDE metadata): `custom` (default), `research`, `bug`, `review`, `agent_card`

**Create Examples:**
```python
# Research doc
manage_docs(
    action="create",
    doc_name="RESEARCH_AUTH_20260119",
    metadata={"doc_type": "research", "research_goal": "Analyze auth flow"}
)

# Bug report (doc_name auto-generated)
manage_docs(
    action="create",
    metadata={
        "doc_type": "bug",
        "category": "logic",
        "slug": "auth_leak",
        "severity": "high",
        "title": "Auth token not invalidated"
    }
)

# Custom doc
manage_docs(
    action="create",
    doc_name="COORDINATION_PROTOCOL",
    metadata={"doc_type": "custom", "body": "# Protocol\n\nContent..."}
)
```

**Edit Examples:**
```python
# Replace section
manage_docs(
    action="replace_section",
    doc_name="architecture",
    section="problem_statement",
    content="## Problem Statement\nNew content here..."
)

# Apply unified diff patch (context-aware matching)
manage_docs(
    action="apply_patch",
    doc_name="architecture",
    patch="--- a/file.md\n+++ b/file.md\n@@ -10,3 +10,3 @@\n-old line\n+new line\n context"
)

# Update checklist status
manage_docs(
    action="status_update",
    doc_name="checklist",
    section="phase_1_task_1",
    metadata={"status": "done", "proof": "PR #123 merged"}
)
```

For complete documentation, see `docs/Scribe_Usage.md` or the `/scribe-mcp-usage` skill.

### 💾 Bulletproof Storage
- **🗄️ Multi-Backend Support** - SQLite (zero-config) + PostgreSQL (enterprise)
- **⚡ Atomic Operations** - Temp-file-then-rename with fsync guarantees
- **🔄 Write-Ahead Logging** - Bulletproof crash recovery with journaling
- **✅ Integrity Verification** - Automatic corruption detection and recovery

---

## 🧠 Intelligent Reminders

**Scribe keeps your documentation in sync** with intelligent context awareness:

### 📋 Smart Reminders
Every MCP tool response includes contextual reminders about:
- 📅 **Stale Documentation** - When architecture docs need updates
- ⏰ **Overdue Logs** - Gentle nudges to maintain progress tracking
- 🎯 **Project Context** - Active project status and recent activity
- 🔄 **Drift Detection** - When implementation deviates from plans

Reminders are throttled with a short cooldown per `(repo_root, agent_id)` so you see what matters without constant repetition. If an agent gets confused, you can clear cooldowns with `set_project(reset_reminders=true)`.

If you call a project-bound tool without selecting a project, Scribe returns a “last known project” hint (including last access time) to help you recover quickly.

### ⚙️ Customization
```json
{
  "name": "my_project",
  "defaults": {
    "reminder": {
      "tone": "friendly",
      "log_warning_minutes": 15,
      "log_urgent_minutes": 30,
      "severity_weights": {"warning": 7, "urgent": 10}
    }
  }
}
```

### 🌍 Environment Variables
- `SCRIBE_REMINDER_IDLE_MINUTES` - Work session reset timeout (default: 45)
- `SCRIBE_REMINDER_WARMUP_MINUTES` - Grace period after resuming (default: 5)
- `SCRIBE_REMINDER_DEFAULTS` - JSON configuration for all projects
- `SCRIBE_REMINDER_CACHE_PATH` - Optional path for reminder cooldown cache (default: `data/reminder_cooldowns.json`)

---

## 🏗️ Project Structure

```
scribe_mcp/
├── pyproject.toml             # Packaging + console scripts (scribe, scribe-server)
├── src/
│   └── scribe_mcp/
│       ├── server.py          # MCP server runtime
│       ├── __main__.py        # Entry point for scribe-server / scribe-mcp
│       ├── cli/               # Unified CLI (tools/call/session)
│       ├── config/            # Path + runtime configuration
│       ├── tools/             # MCP tool implementations
│       ├── storage/           # SQLite/Postgres backends
│       ├── plugins/           # Vector indexer and plugin registry
│       ├── template_engine/   # Jinja document template engine
│       ├── doc_management/    # manage_docs action pipeline
│       └── templates/         # Built-in templates (documents/fragments)
├── tests/                     # Repo-root test suite (installed-package flow)
├── docs/                      # Curated project docs
└── README.md
```

**Per-repo output location (dev plans + logs)**
- Default: `<repo>/.scribe/docs/dev_plans/<project_slug>/...`
- Back-compat: if `<repo>/docs/dev_plans/<project_slug>` exists, Scribe keeps using it.
- Override: set `SCRIBE_DEV_PLANS_BASE` (example: `docs/dev_plans`) to force a different base.

---

## 🧪 Testing & Quality

**Comprehensive testing infrastructure** with 79+ test files:

### 🧪 Run Tests
```bash
# Run all functional tests (69 tests)
pytest

# Run performance tests with file size benchmarks
pytest -m performance

# Run specific test categories
pytest tests/test_tools.py
pytest tests/test_storage.py
```

### ✅ Quality Assurance
- **🔬 Functional Testing** - 69 comprehensive tests covering all core functionality
- **⚡ Performance Testing** - Optimized benchmarks for file operations
- **🛡️ Security Testing** - Template sandboxing and access control validation
- **🔄 Integration Testing** - MCP server protocol compliance verification

### 🚀 Smoke Test
```bash
# Quick MCP server validation
python scripts/test_mcp_server.py
```

---

## 💡 Real-World Use Cases

### 🤖 AI Agent Teams
**Structured workflows for AI development:**
```bash
# Research phase
python -m scribe_mcp.scripts.scribe "Research completed: authentication patterns" --status info --meta phase=research,confidence=0.9

# Architecture phase
python -m scribe_mcp.scripts.scribe "Architecture guide updated with auth design" --status success --meta phase=architecture,sections=5

# Implementation phase
python -m scribe_mcp.scripts.scribe "JWT authentication implemented" --status success --meta phase=implementation,tests=47,coverage=95%
```

### 🏢 Enterprise Documentation
**Compliance and audit trails:**
```bash
# Security events
python -m scribe_mcp.scripts.scribe "Security audit completed - all controls verified" --log security --status success --meta auditor=external,findings=0

# Change management
python -m scribe_mcp.scripts.scribe "Production deployment completed" --status success --meta version=v2.1.0,rollback_available=true
```

### 📚 Research Projects
**Structured research documentation:**
```bash
# Research findings
python -m scribe_mcp.scripts.scribe "Performance bottleneck identified in database queries" --status info --meta research=true,impact=high,evidence=query_analysis

# Experiment results
python -m scribe_mcp.scripts.scribe "A/B test results: new algorithm 23% faster" --status success --meta experiment=performance_optimization,improvement=23%
```

---

## 🔧 Troubleshooting

### Common Issues & Solutions

**🚨 MCP SDK Missing**
```bash
# Install the MCP Python SDK
pip install mcp
```

**🔧 No Tools Returned**
```bash
# Ensure all modules are properly imported
# Check that your virtual environment is active
source .venv/bin/activate

# Verify tool imports
python -c "from scribe_mcp.tools import *; print('All tools loaded')"
```

**🗄️ SQLite Permission Issues**
```bash
# Check your state/db paths are writable
echo $SCRIBE_STATE_PATH
ls -la $(dirname "$SCRIBE_STATE_PATH")

# Check the target repo is writable (Scribe writes under <repo>/.scribe/ by default)
ls -la /abs/path/to/your/repo
ls -la /abs/path/to/your/repo/.scribe || true
```

**🐍 Python Path / Packaging Issues**
```bash
# Verify package import and resolved src-root path
python -c "import scribe_mcp; from scribe_mcp.config.paths import package_root; print(package_root())"

# Verify console-script entry points
scribe --help
scribe-server --help
```

**🤖 BertModel / torchvision mismatch warning**

If startup logs show `Could not import module 'BertModel'`, your torch and
torchvision builds are likely mismatched (common CUDA tag mismatch).

```bash
python - <<'PY'
import torch
print('torch:', torch.__version__)
try:
    import torchvision
    print('torchvision:', torchvision.__version__)
except Exception as exc:
    print('torchvision import failed:', exc)
PY
```

Scribe now guards this case by disabling broken torchvision integration for
transformers so text embeddings can still initialize. For a full env-level fix,
install matching torch/torchvision builds (same CUDA tag), or remove torchvision
if your workload is text-only.

**⚡ Server Not Starting**
```bash
# Ensure package + dev deps are installed
python -m pip install -e ".[dev]"

# Verify server startup
python -m server --help
```

### Getting Help

- **📖 Documentation**: Check `docs/whitepapers/scribe_mcp_whitepaper.md` for comprehensive technical details
- **🧪 Test Suite**: Run `pytest` to verify system functionality
- **📋 Project Templates**: Use `--list-projects` to see available configurations
- **🔍 Smoke Test**: Run `python scripts/test_mcp_server.py` for MCP validation

---

## 🤝 Contributing

**We welcome contributions!** Here's how to get started:

### 🧪 Development Workflow
```bash
# 1. Run the test suite
pytest

# 2. Verify MCP server functionality
python scripts/test_mcp_server.py

# 3. Test your changes
python -m scribe_mcp.scripts.scribe "Testing new feature" --dry-run

# 4. Log your contribution
python -m scribe_mcp.scripts.scribe "Added new feature: description" --status success --meta contribution=true,feature_type=enhancement
```

### 📋 Development Guidelines
- **✅ Test Coverage**: All new features must include tests
- **📝 Documentation**: Update relevant documentation sections
- **🔧 Integration**: Ensure MCP server compatibility
- **🛡️ Security**: Follow security best practices for templates and inputs

### 🚀 Quality Standards
- **🧪 69+ functional tests** must pass
- **⚡ Performance benchmarks** for file operations
- **🔒 Security validation** for template sandboxing
- **📋 MCP protocol compliance** verification

---

## 📚 Further Reading

### 📖 Technical Documentation
- **[📄 Whitepaper v2.1](docs/whitepapers/scribe_mcp_whitepaper.md)** - Comprehensive technical architecture
- **[🔧 API Reference](docs/api/)** - Complete MCP tool documentation
- **[🎨 Template Guide](docs/templates/)** - Custom template development
- **[🏗️ Architecture Patterns](docs/architecture/)** - System design and integration

### 🔒 Hooks & Enforcement
- **[Hooks Setup Guide](docs/guides/hooks_setup.md)** - Protect managed docs from direct Write/Edit with Claude Code hooks
- **[Scribe Onboarding Prompt](docs/guides/scribe_onboarding_prompt.md)** - Full instructional prompt for onboarding any project to Scribe MCP (protocol, tools, manage_docs, hooks)

### 🌟 Advanced Features
- **🤖 Claude Code Integration** - Structured workflows and subagent coordination
- **📊 Agent Report Cards** - Performance grading and quality metrics
- **🔍 Vector Search** - FAISS integration for semantic search
- **🔐 Security Framework** - Comprehensive access control and audit trails

### 🚀 Production Deployment
- **🐘 PostgreSQL Setup** - Enterprise-scale deployment guide
- **📈 Monitoring** - Performance tracking and alerting
- **🔄 Backup & Recovery** - Data protection strategies
- **🌐 Multi-tenant** - Organizational deployment patterns

---

## ⚠️ Known Limitations

### Concurrent Agent Session Collision

**MCP Transport Limitation:** Session identity is `{repo_root}:{transport}:{agent_name}`. When multiple agents with the **same name** work on **different Scribe projects** within the **same repository** concurrently, their sessions collide.

**Best Practice:** Use scoped agent names for concurrent work:
```python
# ❌ Same name = collision
agent="CoderAgent"  # on project_x
agent="CoderAgent"  # on project_y → logs may go to wrong project!

# ✅ Scoped names = safe
agent="CoderAgent-ProjectX"
agent="CoderAgent-ProjectY"
```

**Not affected:** Sequential dispatches, different repositories, or single agent switching projects.

See [Scribe_Usage.md](docs/Scribe_Usage.md#concurrent-agent-naming-session-isolation) for details.

---

## 🙏 Acknowledgments

Built with passion for better documentation and AI-human collaboration. Special thanks to:
- The **MCP protocol** team for the standardized AI tool interface
- **Jinja2** for the powerful and secure templating system
- Our **early adopters** for invaluable feedback and feature suggestions

---

<div align="center">

**🚀 Ready to transform your documentation?**

[Start Logging](#-quick-start) • [Explore Templates](#-template-system-showcase) • [Read Whitepaper](docs/whitepapers/scribe_mcp_whitepaper.md)

*Join thousands of developers and AI teams using Scribe for bulletproof documentation governance*

</div>
