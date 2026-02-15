-- Schema for Scribe MCP server.
CREATE TABLE IF NOT EXISTS scribe_projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    repo_root TEXT NOT NULL,
    progress_log_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scribe_entries (
    id UUID PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES scribe_projects(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL,
    ts_iso TIMESTAMPTZ NOT NULL,
    emoji TEXT NOT NULL,
    agent TEXT,
    message TEXT NOT NULL,
    meta JSONB,
    raw_line TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scribe_metrics (
    project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
    total_entries INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    warn_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_update TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Agent sessions table for multi-agent context management
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL CHECK (status IN ('active','expired')) DEFAULT 'active',
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent ON agent_sessions(agent_id);

-- Agent projects table for agent-scoped current project tracking
CREATE TABLE IF NOT EXISTS agent_projects (
    agent_id TEXT PRIMARY KEY,
    project_name TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    session_id TEXT,
    FOREIGN KEY (project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_projects_updated_at ON agent_projects(updated_at DESC);

CREATE TABLE IF NOT EXISTS agent_project_events (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('project_set', 'project_switched', 'session_started', 'session_ended', 'conflict_detected')),
    from_project TEXT,
    to_project TEXT NOT NULL,
    expected_version INTEGER,
    actual_version INTEGER,
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_project_events_agent_id ON agent_project_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_project_events_created_at ON agent_project_events(created_at);

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

CREATE INDEX IF NOT EXISTS idx_doc_changes_project ON doc_changes(project_id, created_at DESC);

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
    UNIQUE(project_id, plan_type)
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
    UNIQUE(project_id, phase_number)
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
    benchmark_type TEXT NOT NULL CHECK (benchmark_type IN ('hash_performance', 'throughput', 'latency', 'stress_test', 'integrity', 'concurrency')),
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_entries_project_ts
    ON scribe_entries (project_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_entries_meta_gin
    ON scribe_entries USING GIN (meta);

CREATE INDEX IF NOT EXISTS idx_dev_plans_project_type
    ON dev_plans (project_id, plan_type);

CREATE INDEX IF NOT EXISTS idx_phases_project_status
    ON phases (project_id, status);

CREATE INDEX IF NOT EXISTS idx_milestones_project_status
    ON milestones (project_id, status);

CREATE INDEX IF NOT EXISTS idx_benchmarks_project_type
    ON benchmarks (project_id, benchmark_type);

CREATE INDEX IF NOT EXISTS idx_benchmarks_timestamp
    ON benchmarks (test_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_checklists_project_status
    ON checklists (project_id, status);

CREATE INDEX IF NOT EXISTS idx_checklists_phase
    ON checklists (phase_id);

CREATE INDEX IF NOT EXISTS idx_metrics_project_category
    ON performance_metrics (project_id, metric_category);

CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
    ON performance_metrics (collection_timestamp DESC);
