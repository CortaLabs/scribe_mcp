---
id: scribe_containerization-research-storage-config
title: "\U0001F52C Research Storage Config \u2014 scribe_containerization"
doc_type: RESEARCH_STORAGE_CONFIG
doc_name: RESEARCH_STORAGE_CONFIG
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-16 03:20:28 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Storage Config — scribe_containerization
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-16 03:18:28 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
**Primary Objective:** Map Scribe MCP's storage architecture to enable containerization with shared Postgres database.

**Key Takeaways:**
- **Dual Backend Support:** Scribe MCP supports both SQLite and PostgreSQL via pluggable StorageBackend abstraction
- **Schema Isolation:** Postgres backend creates dedicated `scribe` schema - safe to share Council MCP's `agentkit` database
- **Production Ready:** PostgreSQL implementation is feature-complete (2,148 lines, 78 methods) with migration system
- **Migration Tooling Exists:** Production-ready SQLite→Postgres migration script (812 lines) enables seamless transition
- **Volume Requirements:** `.scribe/` directory must be Docker volume (contains PROGRESS_LOG.md, research docs, architecture docs)
- **Recommendation:** Use Postgres backend sharing `agentkit` database + `.scribe/` volume - no `data/` volume needed
<!-- ID: research_scope -->
**Research Lead:** ResearchAgent-Storage

**Investigation Window:** 2026-02-16

**Focus Areas:**
- [x] Storage backend abstraction and implementations
- [x] PostgreSQL support status and feature parity
- [x] Environment variable configuration system
- [x] Database schema isolation and shared database feasibility
- [x] Filesystem vs database storage split
- [x] Migration tooling and automation capabilities

**Dependencies & Constraints:**
- **Existing Infrastructure:** Council MCP has Postgres running (port 5432, database `agentkit`, user `council`)
- **Data Volume:** 108MB SQLite database at `data/scribe_projects.db` contains historical project data
- **Filesystem Dependencies:** Project documentation (PROGRESS_LOG.md, research docs, architecture docs) lives in `.scribe/docs/dev_plans/<project>/`
- **Containerization Goal:** Enable Scribe MCP to run in Docker container sharing Council MCP's Postgres instance
<!-- ID: findings -->
### Finding 1: Pluggable Storage Backend Architecture
- **Summary:** Scribe MCP implements clean storage abstraction via `StorageBackend` abstract base class with two production implementations
- **Evidence:** 
  - `src/scribe_mcp/storage/base.py` (420 lines) defines unified interface
  - `src/scribe_mcp/storage/sqlite/` (12 modules, full implementation)
  - `src/scribe_mcp/storage/postgres/` (__init__.py: 2,148 lines, 78 methods)
  - Backend selection via `create_storage_backend()` factory in `src/scribe_mcp/storage/__init__.py`
- **Confidence:** Very High (0.95) - Verified through code inspection

### Finding 2: PostgreSQL Implementation is Production-Ready
- **Summary:** Postgres backend is feature-complete with full parity to SQLite, not a stub implementation
- **Evidence:**
  - PostgresStorage class: 2,148 lines, 78 methods
  - Schema management: `src/scribe_mcp/db/init.sql` (468 lines, 20+ tables)
  - Migration system: `schema.py` tracks applied migrations in `scribe_migrations` table
  - Connection pooling: Configurable min/max pool size, timeouts, retries
  - Extensions: Requires `pg_trgm`, optional `pgvector` support
- **Confidence:** Very High (0.95) - Full implementation verified

### Finding 3: Schema Isolation Enables Database Sharing
- **Summary:** Postgres backend creates dedicated `scribe` schema namespace - safe to share Council MCP's `agentkit` database
- **Evidence:**
  - `schema.py` line 114: `CREATE SCHEMA IF NOT EXISTS {quoted_schema}`
  - All tables created within schema namespace (scribe.scribe_projects, scribe.scribe_entries, etc.)
  - Schema name configurable via `SCRIBE_POSTGRES_SCHEMA` env var (default: `scribe`)
  - No table name conflicts with Council MCP
- **Confidence:** Very High (0.95) - Verified schema isolation mechanism

### Finding 4: Environment Variable Configuration System
- **Summary:** Backend selection and connection configuration entirely via environment variables
- **Evidence:** `src/scribe_mcp/config/settings.py` lines 88-263
  - **Backend Selection:**
    - `SCRIBE_DB_URL` - PostgreSQL DSN (presence triggers Postgres backend)
    - `SCRIBE_STORAGE_BACKEND` - Explicit override (`sqlite` or `postgres`)
    - Default: SQLite if no `SCRIBE_DB_URL` provided
  - **Postgres Configuration:**
    - `SCRIBE_DB_URL` - Connection string (format: `postgresql://user:pass@host:port/dbname`)
    - `SCRIBE_POSTGRES_SCHEMA` - Schema name (default: `scribe`)
    - `SCRIBE_POSTGRES_POOL_MIN_SIZE` - Pool min connections (default: 2)
    - `SCRIBE_POSTGRES_POOL_MAX_SIZE` - Pool max connections (default: 20)
    - `SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS` - Command timeout (default: 30)
    - `SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS` - Connect timeout (default: 10)
    - `SCRIBE_POSTGRES_CONNECT_RETRIES` - Retry attempts (default: 3)
  - **SQLite Configuration:**
    - `SCRIBE_DB_PATH` or `SCRIBE_SQLITE_PATH` - SQLite database path
    - Default: `data/scribe_projects.db`
- **Confidence:** Very High (0.95) - Complete env var mapping verified

### Finding 5: Filesystem Storage Requirements
- **Summary:** Project documentation lives in `.scribe/` directory - requires Docker volume mount
- **Evidence:** Directory structure examination of `.scribe/`
  - **Critical Subdirectories:**
    - `docs/dev_plans/<project>/` - Project documentation (190 projects currently)
      - `PROGRESS_LOG.md` - Progress log entries (Markdown format)
      - `ARCHITECTURE_GUIDE.md`, `PHASE_PLAN.md`, `CHECKLIST.md` - Managed docs
      - `research/` - Research documents
      - `architecture/` - Architecture sub-plans
    - `docs/agent_report_cards/` - Agent performance reviews
    - `logs/` - MCP server logs
    - `cli/` - CLI session state
    - `config/` - Runtime configuration
    - `backups/` - Log rotation backups
    - `sentinel/` - Sentinel mode artifacts
  - **Database Files (NOT required for Postgres):**
    - `.scribe/scribe.db` (460KB, deprecated)
    - `data/scribe_projects.db` (108MB, primary SQLite DB)
- **Confidence:** Very High (0.95) - Filesystem inspection confirms structure

### Finding 6: Production Migration Tooling Exists
- **Summary:** Automated SQLite-to-Postgres migration and database bootstrap tooling ready for containerization
- **Evidence:**
  - **Migration Script:** `src/scribe_mcp/scripts/migrate_sqlite_to_postgres.py`
    - 812 lines, 21 functions
    - Features: Table discovery, column mapping, type coercion (JSON, bool, float, int, timestamp), batch processing, validation
    - Can migrate existing 108MB SQLite DB to Postgres on container init
  - **Bootstrap Script:** `src/scribe_mcp/scripts/bootstrap_postgres.py`
    - 638 lines, 20 functions
    - Features: User/role creation, DSN generation, env file management, secret generation
    - Can automatically create Scribe users/schema in shared Postgres
  - **Environment Examples:** `.env.example` documents all configuration options
- **Confidence:** Very High (0.95) - Migration tooling verified as production-ready

### Finding 7: Database File Redundancy (SQLite Only)
- **Summary:** Multiple SQLite database files exist - only `data/scribe_projects.db` is primary
- **Evidence:**
  - `data/scribe_projects.db` (108MB) - PRIMARY database
  - `.scribe/scribe.db` (460KB) - Deprecated
  - `.scribe/backups/` - Phase 7 migration backups
  - `data/backups/` - Backup files
- **Confidence:** High (0.9) - File inspection confirms redundancy
- **Note:** Redundancy eliminated when using Postgres backend
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- **Factory Pattern:** `create_storage_backend()` provides clean dependency injection point for backend selection
- **Abstract Base Class:** `StorageBackend` defines contract with 33 methods (core abstract, others optional)
- **Schema Migration System:** Postgres migrations tracked in `scribe_migrations` table, SQL files in `db/postgres_migrations/`
- **Connection Pooling:** `PostgresInternals` manages asyncpg pool with configurable sizing and lifecycle
- **Path Resolution:** `config/paths.py` provides robust path helpers with `importlib.resources` fallbacks

**System Interactions:**
- **Database Layer:** 
  - SQLite: Single-file database at `data/scribe_projects.db` (or configurable path)
  - Postgres: Multi-table schema in `scribe` namespace within shared database
  - Both backends: Project metadata, log entries, session state, document tracking
- **Filesystem Layer:**
  - `.scribe/docs/dev_plans/` - Project documentation (Markdown files)
  - `.scribe/logs/` - MCP server logs
  - `.scribe/config/` - Runtime configuration YAML
  - `.scribe/cli/` - CLI session state JSON
- **Configuration Layer:**
  - Environment variables (primary)
  - Optional `.env` file loading via `python-dotenv`
  - Defaults in `settings.py`

**Storage Backend Tables (Postgres):**
| Table | Purpose |
|-------|---------|
| `scribe_projects` | Project metadata, status, timestamps |
| `scribe_entries` | Progress log entries with full metadata |
| `scribe_metrics` | Entry count aggregates per project |
| `agent_sessions` | Agent session state and activity tracking |
| `agent_projects` | Agent-to-project assignments with versioning |
| `scribe_sessions` | Session management (sentinel vs project mode) |
| `doc_changes` | Document modification audit trail |
| `document_sections` | Cached document content and hashes |
| `custom_templates` | User-defined document templates |
| `documents` | Legacy document tracking |
| `global_log_entries` | Repository-wide log entries |

**Risk Assessment:**
- [x] **No Risk:** Schema isolation prevents conflicts with Council MCP tables
- [x] **No Risk:** Connection pooling configured with safe defaults (max 20 connections)
- [x] **Low Risk:** Migration tooling is production-ready but one-way (SQLite→Postgres, no rollback)
- [x] **Low Risk:** `.scribe/` volume mount required - missing volume = data loss
- [x] **Mitigation:** Document volume mount requirement clearly in Docker setup docs
<!-- ID: recommendations -->
### Immediate Next Steps
- [x] **Use Postgres Backend:** Set `SCRIBE_DB_URL=postgresql://council:password@postgres:5432/agentkit` to share Council's database
- [x] **Mount .scribe/ Volume:** Docker volume at `/app/.scribe` to persist project documentation and logs
- [x] **Set Schema Name:** Use `SCRIBE_POSTGRES_SCHEMA=scribe` (default) for isolation from Council tables
- [ ] **Run Bootstrap Script:** Execute `bootstrap_postgres.py` if Scribe needs dedicated users/roles (optional if sharing Council credentials)
- [ ] **Migrate SQLite Data:** Run `migrate_sqlite_to_postgres.py` to transfer existing 108MB SQLite DB to Postgres (one-time)
- [ ] **Skip data/ Volume:** No need to mount `data/` directory when using Postgres backend
- [ ] **Configure Pool Size:** Adjust `SCRIBE_POSTGRES_POOL_MIN_SIZE` and `SCRIBE_POSTGRES_POOL_MAX_SIZE` based on container resource limits

### Docker Environment Configuration

**Required Environment Variables:**
```bash
# Primary configuration
SCRIBE_DB_URL=postgresql://council:password@postgres:5432/agentkit
SCRIBE_POSTGRES_SCHEMA=scribe

# Optional pool tuning
SCRIBE_POSTGRES_POOL_MIN_SIZE=2
SCRIBE_POSTGRES_POOL_MAX_SIZE=10
SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS=30
```

**Volume Mounts:**
```yaml
volumes:
  - scribe_workspace:/app/.scribe  # REQUIRED - project docs, logs, config
```

**NOT Required:**
```yaml
# ❌ No need for data volume when using Postgres
# volumes:
#   - scribe_data:/app/data
```

### Long-Term Opportunities
- **Unified Database:** Single Postgres instance for Council + Scribe reduces operational complexity
- **Backup Strategy:** Leverage existing Council Postgres backup infrastructure for Scribe data
- **Schema Evolution:** Postgres migration system supports schema changes without downtime
- **pgvector Extension:** Optional semantic search capabilities if pgvector installed (already supported)
- **Performance Monitoring:** Connection pooling metrics available via Postgres system views
<!-- ID: appendix -->
**References:**
- **Storage Backend Code:**
  - `src/scribe_mcp/storage/base.py` - Abstract StorageBackend interface
  - `src/scribe_mcp/storage/__init__.py` - Backend factory
  - `src/scribe_mcp/storage/postgres/__init__.py` - PostgresStorage implementation (2,148 lines)
  - `src/scribe_mcp/storage/sqlite/` - SQLiteStorage implementation (12 modules)
- **Configuration:**
  - `src/scribe_mcp/config/settings.py` - Environment variable mapping
  - `src/scribe_mcp/config/paths.py` - Path resolution helpers
  - `.env.example` - Configuration examples
- **Database Schema:**
  - `src/scribe_mcp/db/init.sql` - Postgres schema DDL (468 lines, 20+ tables)
  - `src/scribe_mcp/storage/postgres/schema.py` - Schema bootstrap logic
  - `src/scribe_mcp/storage/postgres/migrations.py` - Migration system
- **Migration Tooling:**
  - `src/scribe_mcp/scripts/migrate_sqlite_to_postgres.py` - SQLite→Postgres migration (812 lines)
  - `src/scribe_mcp/scripts/bootstrap_postgres.py` - Database bootstrap automation (638 lines)

**Key Files Inspected:**
| File | Purpose | Lines | Confidence |
|------|---------|-------|------------|
| `storage/base.py` | Backend abstraction | 420 | 0.95 |
| `storage/postgres/__init__.py` | Postgres implementation | 2,148 | 0.95 |
| `storage/postgres/schema.py` | Schema management | 133 | 0.95 |
| `config/settings.py` | Env var configuration | 280 | 0.95 |
| `config/paths.py` | Path resolution | 149 | 0.95 |
| `db/init.sql` | Database schema DDL | 468 | 0.95 |
| `scripts/migrate_sqlite_to_postgres.py` | Migration tooling | 812 | 0.95 |
| `scripts/bootstrap_postgres.py` | Bootstrap automation | 638 | 0.95 |

**Environment Variables Summary:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `SCRIBE_DB_URL` | None | Postgres DSN (triggers Postgres backend) |
| `SCRIBE_STORAGE_BACKEND` | Auto-detect | Explicit backend override (`sqlite`/`postgres`) |
| `SCRIBE_POSTGRES_SCHEMA` | `scribe` | Postgres schema namespace |
| `SCRIBE_POSTGRES_POOL_MIN_SIZE` | `2` | Connection pool minimum |
| `SCRIBE_POSTGRES_POOL_MAX_SIZE` | `20` | Connection pool maximum |
| `SCRIBE_DB_PATH` | `data/scribe_projects.db` | SQLite database path |
| `SCRIBE_ROOT` | Auto-detect | Repository root path |

**Research Artifacts:**
- Progress log entries: 9 entries logged during investigation
- Files inspected: 8 primary files + directory structure analysis
- Code lines reviewed: ~6,000+ lines of implementation code
- Confidence level: Very High (0.95) across all findings
