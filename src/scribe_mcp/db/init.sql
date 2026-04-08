-- Schema for Scribe MCP PostgreSQL backend.
-- This schema mirrors the active SQLite domain model and runtime call paths.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS scribe_migrations (
    name TEXT PRIMARY KEY,
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scribe_projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    docs_json TEXT,
    bridge_id TEXT,
    bridge_managed BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT,
    phase TEXT,
    confidence REAL DEFAULT 0.0,
    completed_at TIMESTAMPTZ,
    last_activity TIMESTAMPTZ,
    description TEXT,
    last_entry_at TIMESTAMPTZ,
    last_access_at TIMESTAMPTZ,
    last_status_change TIMESTAMPTZ,
    tags JSONB,
    meta JSONB
);

-- Legacy document/log tables retained for SQLite parity and future object-store extension.
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    doc_type TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    size_bytes INTEGER,
    checksum TEXT,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS document_relationships (
    id TEXT PRIMARY KEY,
    source_doc_id TEXT NOT NULL,
    target_doc_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS global_log_entries (
    id TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    entry_type TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    metadata JSONB,
    project_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scribe_entries (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL,
    ts_iso TIMESTAMPTZ NOT NULL,
    emoji TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    meta JSONB,
    raw_line TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    log_type TEXT DEFAULT 'progress',
    priority TEXT DEFAULT 'medium',
    category TEXT,
    tags TEXT,
    confidence REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS scribe_metrics (
    project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
    total_entries INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    warn_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_update TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    identity_key TEXT UNIQUE NOT NULL,
    agent_name TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    repo_root TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('sentinel', 'project', 'legacy')),
    scope_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    recent_tools JSONB DEFAULT '[]'::jsonb,
    session_started_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_projects (
    agent_id TEXT PRIMARY KEY,
    project_name TEXT REFERENCES scribe_projects(name) ON DELETE SET NULL,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    session_id TEXT
);

CREATE TABLE IF NOT EXISTS agent_project_events (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')
    ),
    from_project TEXT,
    to_project TEXT NOT NULL,
    expected_version INTEGER,
    actual_version INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scribe_sessions (
    session_id TEXT PRIMARY KEY,
    transport_session_id TEXT,
    agent_id TEXT,
    repo_root TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('sentinel', 'project')) DEFAULT 'sentinel',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_projects (
    session_id TEXT PRIMARY KEY,
    project_name TEXT REFERENCES scribe_projects(name) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_recent_projects (
    agent_id TEXT NOT NULL,
    project_name TEXT NOT NULL REFERENCES scribe_projects(name) ON DELETE CASCADE,
    last_access_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent_id, project_name)
);

CREATE TABLE IF NOT EXISTS doc_changes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    doc_name TEXT NOT NULL,
    section TEXT,
    action TEXT NOT NULL,
    agent TEXT,
    metadata JSONB,
    sha_before TEXT,
    sha_after TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_sections (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    document_type TEXT,
    section_id TEXT,
    file_path TEXT,
    relative_path TEXT,
    content TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, document_type, section_id),
    UNIQUE (project_root, file_path)
);

CREATE TABLE IF NOT EXISTS custom_templates (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    template_name TEXT NOT NULL,
    template_content TEXT NOT NULL,
    variables JSONB,
    is_global BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, template_name)
);

CREATE TABLE IF NOT EXISTS document_changes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    file_path TEXT,
    change_type TEXT NOT NULL,
    old_content_hash TEXT,
    new_content_hash TEXT,
    change_summary TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sync_status (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_root TEXT,
    file_path TEXT NOT NULL,
    relative_path TEXT,
    last_sync_at TIMESTAMPTZ,
    last_file_hash TEXT,
    last_db_hash TEXT,
    sync_status TEXT NOT NULL DEFAULT 'synced',
    conflict_details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, file_path)
);

CREATE TABLE IF NOT EXISTS agent_report_cards (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    stage TEXT,
    overall_grade REAL,
    performance_level TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, file_path)
);

CREATE TABLE IF NOT EXISTS dev_plans (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    project_name TEXT NOT NULL,
    plan_type TEXT NOT NULL CHECK (plan_type IN ('architecture', 'phase_plan', 'checklist', 'progress_log')),
    file_path TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB,
    UNIQUE (project_id, plan_type)
);

CREATE TABLE IF NOT EXISTS phases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    dev_plan_id INTEGER NOT NULL REFERENCES dev_plans(id) ON DELETE CASCADE,
    phase_number INTEGER NOT NULL,
    phase_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planned', 'in_progress', 'completed', 'blocked')) DEFAULT 'planned',
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    deliverables_count INTEGER NOT NULL DEFAULT 0,
    deliverables_completed INTEGER NOT NULL DEFAULT 0,
    confidence_score REAL NOT NULL DEFAULT 0.0 CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    metadata JSONB,
    UNIQUE (project_id, phase_number)
);

CREATE TABLE IF NOT EXISTS milestones (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
    milestone_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'overdue')) DEFAULT 'pending',
    target_date TIMESTAMPTZ,
    completed_date TIMESTAMPTZ,
    evidence_url TEXT,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS benchmarks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    benchmark_type TEXT NOT NULL CHECK (
        benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')
    ),
    test_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    test_parameters JSONB,
    environment_info JSONB,
    test_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requirement_target REAL,
    requirement_met BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS checklists (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES phases(id) ON DELETE SET NULL,
    checklist_item TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'completed', 'blocked')) DEFAULT 'pending',
    acceptance_criteria TEXT NOT NULL,
    proof_required BOOLEAN NOT NULL DEFAULT TRUE,
    proof_url TEXT,
    assignee TEXT,
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    metric_category TEXT NOT NULL CHECK (metric_category IN ('development', 'testing', 'deployment', 'operations')),
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metric_unit TEXT NOT NULL,
    baseline_value REAL,
    improvement_percentage REAL,
    collection_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS reminder_history (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES scribe_sessions(session_id) ON DELETE CASCADE,
    reminder_hash TEXT NOT NULL,
    project_root TEXT,
    agent_id TEXT,
    tool_name TEXT,
    reminder_key TEXT,
    shown_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    operation_status TEXT NOT NULL DEFAULT 'neutral' CHECK (operation_status IN ('success', 'failure', 'neutral')),
    context_metadata JSONB
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES scribe_sessions(session_id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms REAL,
    status TEXT NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'error', 'partial')),
    format_requested TEXT,
    project_name TEXT,
    agent_id TEXT,
    error_message TEXT,
    response_size_bytes INTEGER,
    repo_root TEXT
);

CREATE TABLE IF NOT EXISTS scribe_bridges (
    bridge_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('registered', 'active', 'inactive', 'error', 'unregistered')) DEFAULT 'registered',
    health_json JSONB,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_health_check TIMESTAMPTZ,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS scribe_entries_archive (
    id TEXT PRIMARY KEY,
    project_id INTEGER,
    ts TIMESTAMPTZ,
    ts_iso TIMESTAMPTZ,
    emoji TEXT,
    agent TEXT,
    message TEXT,
    meta JSONB,
    raw_line TEXT,
    sha256 TEXT,
    log_type TEXT,
    priority TEXT,
    category TEXT,
    confidence REAL,
    archived_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_projects_repo ON scribe_projects(repo_root);
CREATE INDEX IF NOT EXISTS idx_projects_bridge ON scribe_projects(bridge_id);
CREATE INDEX IF NOT EXISTS idx_projects_tags_gin ON scribe_projects USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_metadata_gin ON documents USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_document_relationships_source ON document_relationships(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_document_relationships_target ON document_relationships(target_doc_id);
CREATE INDEX IF NOT EXISTS idx_document_relationships_metadata_gin ON document_relationships USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_global_log_timestamp ON global_log_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_global_log_entry_type ON global_log_entries(entry_type);
CREATE INDEX IF NOT EXISTS idx_global_log_project_id ON global_log_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_global_log_metadata_gin ON global_log_entries USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_projects_meta_gin ON scribe_projects USING GIN (meta);

CREATE INDEX IF NOT EXISTS idx_entries_project_ts ON scribe_entries(project_id, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_meta_gin ON scribe_entries USING GIN (meta);
CREATE INDEX IF NOT EXISTS idx_entries_priority_ts ON scribe_entries(priority, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_category_ts ON scribe_entries(category, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_project_priority_category ON scribe_entries(project_id, priority, category, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_log_type ON scribe_entries(project_id, log_type, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_agent_ts ON scribe_entries(agent, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_entries_emoji_ts ON scribe_entries(emoji, ts_iso DESC);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_identity ON agent_sessions(identity_key);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_last_active ON agent_sessions(last_active_at);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_expires ON agent_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_agent_projects_updated_at ON agent_projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_project_events_agent_id ON agent_project_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_project_events_created_at ON agent_project_events(created_at);

CREATE INDEX IF NOT EXISTS idx_scribe_sessions_transport ON scribe_sessions(transport_session_id);
CREATE INDEX IF NOT EXISTS idx_scribe_sessions_agent ON scribe_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_scribe_sessions_last_active ON scribe_sessions(last_active_at DESC);

CREATE INDEX IF NOT EXISTS idx_doc_changes_project ON doc_changes(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_sections_project ON document_sections(project_id);
CREATE INDEX IF NOT EXISTS idx_document_sections_updated ON document_sections(updated_at);
CREATE INDEX IF NOT EXISTS idx_document_sections_content_trgm ON document_sections USING GIN (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_document_sections_metadata_gin ON document_sections USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_document_changes_project ON document_changes(project_id);
CREATE INDEX IF NOT EXISTS idx_document_changes_created ON document_changes(created_at);
CREATE INDEX IF NOT EXISTS idx_document_changes_metadata_gin ON document_changes USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_sync_status_project ON sync_status(project_id);
CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status(sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_status_conflict_details_gin ON sync_status USING GIN (conflict_details);
CREATE INDEX IF NOT EXISTS idx_agent_report_cards_project_agent ON agent_report_cards(project_id, agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_report_cards_stage ON agent_report_cards(stage);

CREATE INDEX IF NOT EXISTS idx_dev_plans_project_type ON dev_plans(project_id, plan_type);
CREATE INDEX IF NOT EXISTS idx_phases_project_status ON phases(project_id, status);
CREATE INDEX IF NOT EXISTS idx_milestones_project_status ON milestones(project_id, status);
CREATE INDEX IF NOT EXISTS idx_benchmarks_project_type ON benchmarks(project_id, benchmark_type);
CREATE INDEX IF NOT EXISTS idx_benchmarks_timestamp ON benchmarks(test_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_checklists_project_status ON checklists(project_id, status);
CREATE INDEX IF NOT EXISTS idx_checklists_phase ON checklists(phase_id);
CREATE INDEX IF NOT EXISTS idx_metrics_project_category ON performance_metrics(project_id, metric_category);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON performance_metrics(collection_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_reminder_history_session_hash ON reminder_history(session_id, reminder_hash);
CREATE INDEX IF NOT EXISTS idx_reminder_history_shown_at ON reminder_history(shown_at);
CREATE INDEX IF NOT EXISTS idx_reminder_history_session_tool ON reminder_history(session_id, tool_name);
CREATE INDEX IF NOT EXISTS idx_reminder_history_context_metadata_gin ON reminder_history USING GIN (context_metadata);

CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_name ON tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_timestamp ON tool_calls(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_project ON tool_calls(project_name);
CREATE INDEX IF NOT EXISTS idx_tool_calls_repo_root ON tool_calls(repo_root);

CREATE INDEX IF NOT EXISTS idx_bridges_state ON scribe_bridges(state);
CREATE INDEX IF NOT EXISTS idx_bridges_registered_at ON scribe_bridges(registered_at DESC);
CREATE INDEX IF NOT EXISTS idx_bridges_manifest_json_gin ON scribe_bridges USING GIN (manifest_json);
CREATE INDEX IF NOT EXISTS idx_bridges_health_json_gin ON scribe_bridges USING GIN (health_json);

CREATE INDEX IF NOT EXISTS idx_archive_project_ts ON scribe_entries_archive(project_id, ts_iso DESC);
CREATE INDEX IF NOT EXISTS idx_archive_archived_at ON scribe_entries_archive(archived_at DESC);
