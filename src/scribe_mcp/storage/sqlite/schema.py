"""Schema creation helpers for the SQLite storage backend."""
from __future__ import annotations
from typing import Any, Awaitable, Callable, List
ExecuteFn = Callable[[str, tuple[Any, ...]], Awaitable[None]]
ExecuteManyFn = Callable[[List[str]], Awaitable[None]]
MigrateAgentSessionsFn = Callable[[], Awaitable[None]]
MIGRATION_TABLE_STATEMENT = """
CREATE TABLE IF NOT EXISTS scribe_migrations (
    name TEXT PRIMARY KEY,
    completed_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""
CORE_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scribe_projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        repo_root TEXT NOT NULL,
        progress_log_path TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        docs_json TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scribe_entries (
        id TEXT PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        ts TEXT NOT NULL,
        ts_iso TEXT NOT NULL,
        emoji TEXT NOT NULL,
        agent TEXT,
        message TEXT NOT NULL,
        meta TEXT,
        raw_line TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        log_type TEXT DEFAULT 'progress'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scribe_metrics (
        project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
        total_entries INTEGER NOT NULL DEFAULT 0,
        success_count INTEGER NOT NULL DEFAULT 0,
        warn_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        last_update TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
]
SESSION_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS agent_sessions (
        session_id TEXT PRIMARY KEY,
        identity_key TEXT UNIQUE NOT NULL,
        agent_name TEXT NOT NULL,
        agent_key TEXT NOT NULL,
        repo_root TEXT NOT NULL,
        mode TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_projects (
        agent_id TEXT PRIMARY KEY,
        project_name TEXT,
        version INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_by TEXT,
        session_id TEXT,
        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_project_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK (event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')),
        from_project TEXT,
        to_project TEXT NOT NULL,
        expected_version INTEGER,
        actual_version INTEGER,
        success BOOLEAN NOT NULL DEFAULT 1,
        error_message TEXT,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scribe_sessions (
        session_id TEXT PRIMARY KEY,
        transport_session_id TEXT,
        agent_id TEXT,
        repo_root TEXT,
        mode TEXT NOT NULL CHECK (mode IN ('sentinel','project')) DEFAULT 'sentinel',
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS session_projects (
        session_id TEXT PRIMARY KEY,
        project_name TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE,
        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
    );
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_session_projects_requires_session_insert
    BEFORE INSERT ON session_projects
    FOR EACH ROW
    WHEN (SELECT 1 FROM scribe_sessions WHERE session_id = NEW.session_id) IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'session_projects.session_id requires a live scribe_sessions row');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_session_projects_requires_session_update
    BEFORE UPDATE OF session_id ON session_projects
    FOR EACH ROW
    WHEN (SELECT 1 FROM scribe_sessions WHERE session_id = NEW.session_id) IS NULL
    BEGIN
        SELECT RAISE(ABORT, 'session_projects.session_id requires a live scribe_sessions row');
    END;
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_recent_projects (
        agent_id TEXT NOT NULL,
        project_name TEXT NOT NULL,
        last_access_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(agent_id, project_name),
        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE CASCADE
    );
    """,
]
DOCUMENT_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS doc_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        doc_name TEXT NOT NULL,
        section TEXT,
        action TEXT NOT NULL,
        agent TEXT,
        metadata TEXT,
        sha_before TEXT,
        sha_after TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
        project_root TEXT,
        document_type TEXT,
        section_id TEXT,
        file_path TEXT,
        relative_path TEXT,
        content TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, document_type, section_id),
        UNIQUE(project_root, file_path)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS custom_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        template_name TEXT NOT NULL,
        template_content TEXT NOT NULL,
        variables TEXT,
        is_global BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, template_name)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS document_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
        project_root TEXT,
        file_path TEXT,
        change_type TEXT NOT NULL,
        old_content_hash TEXT,
        new_content_hash TEXT,
        change_summary TEXT,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
        project_root TEXT,
        file_path TEXT NOT NULL,
        relative_path TEXT,
        last_sync_at TEXT,
        last_file_hash TEXT,
        last_db_hash TEXT,
        sync_status TEXT NOT NULL DEFAULT 'synced',
        conflict_details TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, file_path)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_report_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        file_path TEXT NOT NULL,
        agent_name TEXT NOT NULL,
        stage TEXT,
        overall_grade REAL,
        performance_level TEXT,
        metadata TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_id, file_path)
    );
    """,
]
PLANNING_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS dev_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        project_name TEXT NOT NULL,
        plan_type TEXT NOT NULL CHECK (plan_type IN ('architecture', 'phase_plan', 'checklist', 'progress_log')),
        file_path TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT '1.0',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        metadata TEXT,
        UNIQUE(project_id, plan_type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS phases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        dev_plan_id INTEGER NOT NULL REFERENCES dev_plans(id) ON DELETE CASCADE,
        phase_number INTEGER NOT NULL,
        phase_name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'blocked')) DEFAULT 'planned',
        start_date TEXT,
        end_date TEXT,
        deliverables_count INTEGER NOT NULL DEFAULT 0,
        deliverables_completed INTEGER NOT NULL DEFAULT 0,
        confidence_score REAL NOT NULL DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
        metadata TEXT,
        UNIQUE(project_id, phase_number)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS milestones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
        milestone_name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'overdue')) DEFAULT 'pending',
        target_date TEXT,
        completed_date TEXT,
        evidence_url TEXT,
        metadata TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS benchmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        benchmark_type TEXT NOT NULL CHECK (benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')),
        test_name TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        metric_value REAL NOT NULL,
        metric_unit TEXT NOT NULL,
        test_parameters TEXT,
        environment_info TEXT,
        test_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        requirement_target REAL,
        requirement_met BOOLEAN NOT NULL DEFAULT FALSE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS checklists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
        checklist_item TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked')) DEFAULT 'pending',
        acceptance_criteria TEXT NOT NULL,
        proof_required BOOLEAN NOT NULL DEFAULT TRUE,
        proof_url TEXT,
        assignee TEXT,
        priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        metadata TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS performance_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
        metric_category TEXT NOT NULL CHECK (metric_category IN ('development', 'testing', 'deployment', 'operations')),
        metric_name TEXT NOT NULL,
        metric_value REAL NOT NULL,
        metric_unit TEXT NOT NULL,
        baseline_value REAL,
        improvement_percentage REAL,
        collection_timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        metadata TEXT
    );
    """,
]
TELEMETRY_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS reminder_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        reminder_hash TEXT NOT NULL,
        project_root TEXT,
        agent_id TEXT,
        tool_name TEXT,
        reminder_key TEXT,
        shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        operation_status TEXT NOT NULL DEFAULT 'neutral' CHECK (operation_status IN ('success', 'failure', 'neutral')),
        context_metadata TEXT,
        FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tool_calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        duration_ms REAL,
        status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'error', 'partial')),
        format_requested TEXT,
        project_name TEXT,
        agent_id TEXT,
        error_message TEXT,
        response_size_bytes INTEGER,
        repo_root TEXT,
        correlation_id TEXT,
        measurement_scope TEXT,
        FOREIGN KEY (session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE
    );
    """,
]
BRIDGE_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scribe_bridges (
        bridge_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        version TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('registered', 'active', 'inactive', 'error', 'unregistered')) DEFAULT 'registered',
        health_json TEXT,
        registered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_health_check TEXT,
        last_error TEXT
    );
    """,
]
ARCHIVE_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS scribe_entries_archive (
        id TEXT PRIMARY KEY,
        project_id INTEGER,
        ts TEXT,
        ts_iso TEXT,
        emoji TEXT,
        agent TEXT,
        message TEXT,
        meta TEXT,
        raw_line TEXT,
        sha256 TEXT,
        log_type TEXT,
        priority TEXT,
        category TEXT,
        confidence REAL,
        archived_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
]
FTS_TABLE_STATEMENTS = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS document_sections_fts
    USING fts5(document_type, section_id, content, content=document_sections, content_rowid=id)
    """,
    """
    CREATE TRIGGER IF NOT EXISTS document_sections_fts_insert
    AFTER INSERT ON document_sections BEGIN
        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
        VALUES (new.id, new.document_type, new.section_id, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS document_sections_fts_delete
    AFTER DELETE ON document_sections BEGIN
        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS document_sections_fts_update
    AFTER UPDATE ON document_sections BEGIN
        INSERT INTO document_sections_fts(document_sections_fts, rowid, document_type, section_id, content)
        VALUES ('delete', old.id, old.document_type, old.section_id, old.content);
        INSERT INTO document_sections_fts(rowid, document_type, section_id, content)
        VALUES (new.id, new.document_type, new.section_id, new.content);
    END
    """,
]
INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_identity ON agent_sessions(identity_key);",
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_active ON agent_sessions(last_active_at);",
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_expires ON agent_sessions(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_agent_projects_updated_at ON agent_projects(updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_agent_project_events_agent_id ON agent_project_events(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_agent_project_events_created_at ON agent_project_events(created_at);",
    """
    WITH ranked AS (
        SELECT
            rowid,
            ROW_NUMBER() OVER (
                PARTITION BY transport_session_id
                ORDER BY last_active_at DESC, started_at DESC, session_id DESC
            ) AS rn
        FROM scribe_sessions
        WHERE transport_session_id IS NOT NULL
    )
    UPDATE scribe_sessions
    SET transport_session_id = NULL
    WHERE rowid IN (SELECT rowid FROM ranked WHERE rn > 1);
    """,
    "DROP INDEX IF EXISTS idx_scribe_sessions_transport;",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_scribe_sessions_transport
        ON scribe_sessions(transport_session_id)
        WHERE transport_session_id IS NOT NULL;
    """,
    "CREATE INDEX IF NOT EXISTS idx_scribe_sessions_agent ON scribe_sessions(agent_id);",
    "CREATE INDEX IF NOT EXISTS idx_doc_changes_project ON doc_changes(project_id, created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_entries_project_ts ON scribe_entries(project_id, ts_iso DESC);",
    "CREATE INDEX IF NOT EXISTS idx_dev_plans_project_type ON dev_plans(project_id, plan_type);",
    "CREATE INDEX IF NOT EXISTS idx_phases_project_status ON phases(project_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_milestones_project_status ON milestones(project_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_benchmarks_project_type ON benchmarks(project_id, benchmark_type);",
    "CREATE INDEX IF NOT EXISTS idx_benchmarks_timestamp ON benchmarks(test_timestamp DESC);",
    "CREATE INDEX IF NOT EXISTS idx_checklists_project_status ON checklists(project_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_checklists_phase ON checklists(phase_id);",
    "CREATE INDEX IF NOT EXISTS idx_metrics_project_category ON performance_metrics(project_id, metric_category);",
    "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(collection_timestamp DESC);",
    """
    CREATE INDEX IF NOT EXISTS idx_reminder_history_session_hash
        ON reminder_history(session_id, reminder_hash);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reminder_history_shown_at
        ON reminder_history(shown_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reminder_history_session_tool
        ON reminder_history(session_id, tool_name);
    """,
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_project ON tool_calls(project_name);",
    "CREATE INDEX IF NOT EXISTS idx_tool_calls_correlation ON tool_calls(correlation_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_sections_project ON document_sections(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_sections_updated ON document_sections(updated_at);",
    "CREATE INDEX IF NOT EXISTS idx_document_changes_project ON document_changes(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_changes_created ON document_changes(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_sync_status_project ON sync_status(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status(sync_status);",
    "CREATE INDEX IF NOT EXISTS idx_bridges_state ON scribe_bridges(state);",
    "CREATE INDEX IF NOT EXISTS idx_bridges_registered_at ON scribe_bridges(registered_at);",
    "CREATE INDEX IF NOT EXISTS idx_archive_project_ts ON scribe_entries_archive(project_id, ts_iso DESC);",
    "CREATE INDEX IF NOT EXISTS idx_archive_archived_at ON scribe_entries_archive(archived_at DESC);",
]
async def create_migration_table(execute_fn: ExecuteFn) -> None:
    await execute_fn(MIGRATION_TABLE_STATEMENT, ())
async def create_core_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(CORE_TABLE_STATEMENTS)
async def create_session_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(SESSION_TABLE_STATEMENTS)
async def create_document_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(DOCUMENT_TABLE_STATEMENTS)
async def create_planning_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(PLANNING_TABLE_STATEMENTS)
async def create_telemetry_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(TELEMETRY_TABLE_STATEMENTS)
async def ensure_telemetry_index_columns(execute_fn: ExecuteFn) -> None:
    """Ensure optional telemetry columns exist before index creation."""
    for column_name, column_definition in (
        ("duration_ms", "REAL"),
        ("status", "TEXT NOT NULL DEFAULT 'success'"),
        ("format_requested", "TEXT"),
        ("project_name", "TEXT"),
        ("agent_id", "TEXT"),
        ("error_message", "TEXT"),
        ("response_size_bytes", "INTEGER"),
        ("repo_root", "TEXT"),
        ("correlation_id", "TEXT"),
        ("measurement_scope", "TEXT"),
    ):
        try:
            await execute_fn(f"ALTER TABLE tool_calls ADD COLUMN {column_name} {column_definition};", ())
        except Exception as exc:
            if "duplicate column" not in str(exc).lower():
                raise
async def create_bridge_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(BRIDGE_TABLE_STATEMENTS)
async def create_archive_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(ARCHIVE_TABLE_STATEMENTS)
async def create_fts_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(FTS_TABLE_STATEMENTS)
async def create_all_indexes(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(INDEX_STATEMENTS)
async def create_schema(
    execute_fn: ExecuteFn,
    execute_many_fn: ExecuteManyFn,
    migrate_agent_sessions_schema_fn: MigrateAgentSessionsFn,
) -> None:
    """Create all base SQLite tables/indexes used by SQLiteStorage."""
    await create_migration_table(execute_fn)
    await migrate_agent_sessions_schema_fn()
    await create_core_tables(execute_many_fn)
    await create_session_tables(execute_many_fn)
    await create_document_tables(execute_many_fn)
    await create_planning_tables(execute_many_fn)
    await create_telemetry_tables(execute_many_fn)
    await create_bridge_tables(execute_many_fn)
    await create_archive_tables(execute_many_fn)
    await create_fts_tables(execute_many_fn)
    await ensure_telemetry_index_columns(execute_fn)
    await create_all_indexes(execute_many_fn)
