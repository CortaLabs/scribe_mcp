"""Schema creation helpers for the SQLite storage backend."""
from __future__ import annotations
import asyncio
from typing import Any, Awaitable, Callable, List
ExecuteFn = Callable[[str, tuple[Any, ...]], Awaitable[None]]
ExecuteManyFn = Callable[[List[str]], Awaitable[None]]
MigrateAgentSessionsFn = Callable[[], Awaitable[None]]


def _binding_classification_sql(
    row_ref: str,
    supplied_key_sql: str,
) -> tuple[str, str, str]:
    """Build SQLite expressions matching migration 007's C-05 classifier."""
    session_exists = (
        f"EXISTS (SELECT 1 FROM scribe_sessions AS ss "
        f"WHERE ss.session_id = {row_ref}.session_id)"
    )
    match_count = (
        "(SELECT COUNT(*) FROM scribe_projects AS p "
        "JOIN scribe_sessions AS ss ON ss.session_id = "
        f"{row_ref}.session_id WHERE p.repo_root = ss.repo_root "
        f"AND p.name = {row_ref}.project_name)"
    )
    usable_key_count = (
        "(SELECT COUNT(*) FROM scribe_projects AS p "
        "JOIN scribe_sessions AS ss ON ss.session_id = "
        f"{row_ref}.session_id WHERE p.repo_root = ss.repo_root "
        f"AND p.name = {row_ref}.project_name "
        "AND NULLIF(trim(p.project_key), '') IS NOT NULL)"
    )
    canonical_key = (
        "(SELECT p.project_key FROM scribe_projects AS p "
        "JOIN scribe_sessions AS ss ON ss.session_id = "
        f"{row_ref}.session_id WHERE p.repo_root = ss.repo_root "
        f"AND p.name = {row_ref}.project_name "
        "AND NULLIF(trim(p.project_key), '') IS NOT NULL LIMIT 1)"
    )
    resolvable = (
        f"{row_ref}.project_name IS NOT NULL AND {session_exists} "
        f"AND {match_count} = 1 AND {usable_key_count} = 1 "
        f"AND (({supplied_key_sql}) IS NULL OR "
        f"({supplied_key_sql}) = {canonical_key})"
    )
    project_key = f"CASE WHEN {resolvable} THEN {canonical_key} ELSE NULL END"
    binding_state = f"CASE WHEN {resolvable} THEN 'resolved' ELSE 'unresolved' END"
    reason = (
        "CASE "
        f"WHEN {row_ref}.project_name IS NULL THEN 'project_name_absent' "
        f"WHEN NOT {session_exists} THEN 'session_missing' "
        f"WHEN {match_count} = 0 THEN 'project_identity_zero_matches' "
        f"WHEN {match_count} > 1 THEN 'project_identity_ambiguous' "
        f"WHEN {usable_key_count} <> 1 THEN 'project_key_missing' "
        f"WHEN ({supplied_key_sql}) IS NOT NULL "
        f"AND ({supplied_key_sql}) <> {canonical_key} "
        "THEN 'project_key_mismatch' ELSE NULL END"
    )
    return project_key, binding_state, reason


_INSERT_SUPPLIED_KEY = "NULLIF(trim(NEW.project_key), '')"
(
    _INSERT_PROJECT_KEY,
    _INSERT_BINDING_STATE,
    _INSERT_BINDING_REASON,
) = _binding_classification_sql("NEW", _INSERT_SUPPLIED_KEY)
_UPDATE_SUPPLIED_KEY = (
    "CASE WHEN NEW.project_name IS NOT OLD.project_name "
    "AND NEW.project_key IS OLD.project_key "
    "THEN NULL ELSE NULLIF(trim(NEW.project_key), '') END"
)
(
    _UPDATE_PROJECT_KEY,
    _UPDATE_BINDING_STATE,
    _UPDATE_BINDING_REASON,
) = _binding_classification_sql("NEW", _UPDATE_SUPPLIED_KEY)
_UPDATE_BINDING_GENERATION = (
    "CASE WHEN OLD.binding_state IS NOT NULL AND NOT ("
    "OLD.project_key IS NULL AND OLD.binding_generation = 1 "
    "AND OLD.binding_state = 'unresolved' "
    "AND OLD.binding_state_reason IS NULL"
    ") AND ("
    "NEW.session_id IS NOT OLD.session_id OR "
    "NEW.project_name IS NOT OLD.project_name OR "
    f"({_UPDATE_PROJECT_KEY}) IS NOT OLD.project_key OR "
    f"({_UPDATE_BINDING_STATE}) IS NOT OLD.binding_state OR "
    f"({_UPDATE_BINDING_REASON}) IS NOT OLD.binding_state_reason"
    ") THEN CASE WHEN OLD.binding_generation IS NULL OR OLD.binding_generation < 1 "
    "THEN 2 ELSE OLD.binding_generation + 1 END "
    "ELSE CASE WHEN OLD.binding_generation IS NULL OR OLD.binding_generation < 1 "
    "THEN 1 ELSE OLD.binding_generation END END"
)
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
        project_key TEXT,
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
        project_key TEXT
            CHECK (project_key IS NULL OR trim(project_key) <> ''),
        binding_generation INTEGER NOT NULL DEFAULT 1
            CHECK (binding_generation >= 1),
        binding_state TEXT NOT NULL DEFAULT 'unresolved'
            CHECK (binding_state IN ('resolved', 'unresolved')),
        binding_state_reason TEXT DEFAULT 'project_name_absent',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(session_id) REFERENCES scribe_sessions(session_id) ON DELETE CASCADE,
        FOREIGN KEY(project_name) REFERENCES scribe_projects(name) ON DELETE SET NULL,
        CHECK (
            (
                binding_state = 'resolved'
                AND project_key IS NOT NULL
                AND binding_state_reason IS NULL
            )
            OR (
                binding_state = 'unresolved'
                AND project_key IS NULL
                AND trim(COALESCE(binding_state_reason, '')) <> ''
            )
        )
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scribe_binding_classification_guard (
        session_id TEXT PRIMARY KEY
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
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_session_projects_classify_insert
    AFTER INSERT ON session_projects
    FOR EACH ROW
    BEGIN
        INSERT OR REPLACE INTO scribe_binding_classification_guard (session_id)
        VALUES (NEW.session_id);
        UPDATE session_projects
        SET project_key = {_INSERT_PROJECT_KEY},
            binding_generation = 1,
            binding_state = {_INSERT_BINDING_STATE},
            binding_state_reason = {_INSERT_BINDING_REASON}
        WHERE session_id = NEW.session_id;
        DELETE FROM scribe_binding_classification_guard
        WHERE session_id = NEW.session_id;
    END;
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS trg_session_projects_classify_update
    AFTER UPDATE ON session_projects
    FOR EACH ROW
    WHEN NOT EXISTS (
        SELECT 1 FROM scribe_binding_classification_guard AS guard
        WHERE guard.session_id = NEW.session_id
    )
    BEGIN
        INSERT OR REPLACE INTO scribe_binding_classification_guard (session_id)
        VALUES (NEW.session_id);
        UPDATE session_projects
        SET project_key = {_UPDATE_PROJECT_KEY},
            binding_generation = {_UPDATE_BINDING_GENERATION},
            binding_state = {_UPDATE_BINDING_STATE},
            binding_state_reason = {_UPDATE_BINDING_REASON}
        WHERE session_id = NEW.session_id;
        DELETE FROM scribe_binding_classification_guard
        WHERE session_id = NEW.session_id;
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
APPLY_PREVIEW_RECEIPT_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS apply_preview_receipts (
        token_sha256 TEXT PRIMARY KEY
            CHECK (
                length(token_sha256) = 64
                AND token_sha256 NOT GLOB '*[^0-9a-f]*'
            ),
        receipt_version INTEGER NOT NULL CHECK (receipt_version >= 1),
        state TEXT NOT NULL
            CHECK (state IN ('issued', 'applying', 'applied', 'failed_terminal')),
        principal_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        project_key TEXT NOT NULL,
        repo_id TEXT NOT NULL,
        action TEXT NOT NULL,
        normalized_intent_json TEXT NOT NULL,
        target_binding_json TEXT NOT NULL,
        precondition_json TEXT NOT NULL,
        predicted_after_json TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        fence INTEGER NOT NULL DEFAULT 0 CHECK (fence >= 0),
        apply_lease_expires_at TEXT,
        terminal_result_code TEXT,
        terminal_result_json TEXT,
        terminal_at TEXT,
        audit_correlation_id TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]
BACKGROUND_RECEIPT_TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS background_receipts (
        operation_id TEXT NOT NULL PRIMARY KEY
            CHECK (trim(operation_id) <> ''),
        canonical_project_key TEXT NOT NULL
            CHECK (trim(canonical_project_key) <> ''),
        lane TEXT NOT NULL
            CHECK (lane IN ('control', 'durable', 'heavy')),
        idempotency_key TEXT NOT NULL
            CHECK (trim(idempotency_key) <> ''),
        payload_digest TEXT NOT NULL
            CHECK (
                length(payload_digest) = 64
                AND payload_digest NOT GLOB '*[^0-9a-f]*'
            ),
        payload_bytes INTEGER NOT NULL
            CHECK (payload_bytes >= 0),
        durability_class TEXT NOT NULL
            CHECK (trim(durability_class) <> ''),
        state TEXT NOT NULL
            CHECK (state IN (
                'accepted',
                'ready',
                'leased',
                'retry_wait',
                'succeeded',
                'failed_terminal',
                'cancelled'
            )),
        state_version INTEGER NOT NULL DEFAULT 1
            CHECK (state_version >= 1),
        attempt_count INTEGER NOT NULL DEFAULT 0
            CHECK (attempt_count >= 0),
        next_attempt_at TEXT,
        lease_owner TEXT,
        lease_expires_at TEXT,
        fencing_token INTEGER NOT NULL DEFAULT 0
            CHECK (fencing_token >= 0),
        cancel_requested INTEGER NOT NULL DEFAULT 0
            CHECK (cancel_requested IN (0, 1)),
        result_ref TEXT,
        error_code TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (canonical_project_key, idempotency_key),
        CHECK (updated_at >= created_at),
        CHECK (attempt_count = fencing_token),
        CHECK ((lease_owner IS NULL) = (lease_expires_at IS NULL)),
        CHECK (lease_owner IS NULL OR trim(lease_owner) <> ''),
        CHECK (result_ref IS NULL OR trim(result_ref) <> ''),
        CHECK (error_code IS NULL OR trim(error_code) <> ''),
        CHECK (
            (
                state = 'accepted'
                AND state_version = 1
                AND attempt_count = 0
                AND fencing_token = 0
                AND cancel_requested = 0
                AND next_attempt_at IS NULL
                AND lease_owner IS NULL
                AND result_ref IS NULL
                AND error_code IS NULL
            )
            OR (
                state = 'ready'
                AND state_version >= 2
                AND attempt_count = 0
                AND fencing_token = 0
                AND cancel_requested = 0
                AND next_attempt_at IS NULL
                AND lease_owner IS NULL
                AND result_ref IS NULL
                AND error_code IS NULL
            )
            OR (
                state = 'leased'
                AND state_version >= 3
                AND attempt_count >= 1
                AND fencing_token >= 1
                AND next_attempt_at IS NULL
                AND lease_owner IS NOT NULL
                AND result_ref IS NULL
                AND error_code IS NULL
            )
            OR (
                state = 'retry_wait'
                AND state_version >= 4
                AND attempt_count >= 1
                AND fencing_token >= 1
                AND next_attempt_at IS NOT NULL
                AND lease_owner IS NULL
                AND result_ref IS NULL
                AND error_code IS NULL
            )
            OR (
                state = 'succeeded'
                AND state_version >= 4
                AND attempt_count >= 1
                AND fencing_token >= 1
                AND next_attempt_at IS NULL
                AND lease_owner IS NULL
                AND result_ref IS NOT NULL
                AND error_code IS NULL
            )
            OR (
                state = 'failed_terminal'
                AND state_version >= 4
                AND attempt_count >= 1
                AND fencing_token >= 1
                AND next_attempt_at IS NULL
                AND lease_owner IS NULL
                AND result_ref IS NULL
                AND error_code IS NOT NULL
            )
            OR (
                state = 'cancelled'
                AND state_version >= 2
                AND next_attempt_at IS NULL
                AND lease_owner IS NULL
                AND result_ref IS NULL
                AND error_code IS NULL
            )
        )
    );
    """,
]
SESSION_PROJECT_COLUMNS = (
    "session_id",
    "project_name",
    "project_key",
    "binding_generation",
    "binding_state",
    "binding_state_reason",
    "updated_at",
)
BACKGROUND_RECEIPT_COLUMNS = (
    "operation_id",
    "canonical_project_key",
    "lane",
    "idempotency_key",
    "payload_digest",
    "payload_bytes",
    "durability_class",
    "state",
    "state_version",
    "attempt_count",
    "next_attempt_at",
    "lease_owner",
    "lease_expires_at",
    "fencing_token",
    "cancel_requested",
    "result_ref",
    "error_code",
    "created_at",
    "updated_at",
)


def _compact_schema_sql_expression(table_name: str) -> str:
    """Return a SQLite expression that removes insignificant SQL whitespace."""
    return (
        "lower(replace(replace(replace(replace(COALESCE(("
        "SELECT sql FROM sqlite_master "
        f"WHERE type = 'table' AND name = '{table_name}'"
        "), ''), char(10), ''), char(13), ''), char(9), ''), ' ', ''))"
    )


def _compact_sql_text(statement: str) -> str:
    return "".join(statement.lower().split()).rstrip(";")


def _create_body_fingerprint(statement: str) -> str:
    compact = _compact_sql_text(statement)
    return compact[compact.index("(") :]


def _schema_body_expression(table_name: str) -> str:
    compact = _compact_schema_sql_expression(table_name)
    return f"substr({compact}, instr({compact}, '('))"


def _column_signature_expression(table_name: str) -> str:
    """Return an ordered, deterministic signature for a table's columns."""
    return (
        "(SELECT group_concat(signature, '|') FROM ("
        "SELECT printf('%d:%s:%s:%d:%s:%d', "
        "cid, name, upper(type), \"notnull\", COALESCE(dflt_value, ''), pk) AS signature "
        f"FROM pragma_table_info('{table_name}') ORDER BY cid))"
    )


def _compact_object_sql_expression(object_type: str, object_name: str) -> str:
    return (
        "lower(replace(replace(replace(replace(COALESCE(("
        "SELECT sql FROM sqlite_master "
        f"WHERE type = '{object_type}' AND name = '{object_name}'"
        "), ''), char(10), ''), char(13), ''), char(9), ''), ' ', ''))"
    )


def _trigger_body_fingerprint(statement: str) -> str:
    compact = _compact_sql_text(statement)
    positions = [
        position
        for keyword in ("before", "after")
        if (position := compact.find(keyword)) >= 0
    ]
    return compact[min(positions) :]


def _trigger_body_expression(trigger_name: str) -> str:
    compact = _compact_object_sql_expression("trigger", trigger_name)
    start = (
        f"CASE WHEN instr({compact}, 'before') = 0 "
        f"THEN instr({compact}, 'after') "
        f"WHEN instr({compact}, 'after') = 0 "
        f"THEN instr({compact}, 'before') "
        f"ELSE min(instr({compact}, 'before'), instr({compact}, 'after')) END"
    )
    return f"substr({compact}, {start})"


SESSION_PROJECTS_COLUMN_SIGNATURE = (
    "0:session_id:TEXT:0::1|1:project_name:TEXT:0::0|"
    "2:project_key:TEXT:0::0|3:binding_generation:INTEGER:1:1:0|"
    "4:binding_state:TEXT:1:'unresolved':0|"
    "5:binding_state_reason:TEXT:0:'project_name_absent':0|"
    "6:updated_at:TEXT:1:CURRENT_TIMESTAMP:0"
)
BACKGROUND_RECEIPTS_COLUMN_SIGNATURE = (
    "0:operation_id:TEXT:1::1|1:canonical_project_key:TEXT:1::0|"
    "2:lane:TEXT:1::0|3:idempotency_key:TEXT:1::0|"
    "4:payload_digest:TEXT:1::0|5:payload_bytes:INTEGER:1::0|"
    "6:durability_class:TEXT:1::0|7:state:TEXT:1::0|"
    "8:state_version:INTEGER:1:1:0|9:attempt_count:INTEGER:1:0:0|"
    "10:next_attempt_at:TEXT:0::0|11:lease_owner:TEXT:0::0|"
    "12:lease_expires_at:TEXT:0::0|13:fencing_token:INTEGER:1:0:0|"
    "14:cancel_requested:INTEGER:1:0:0|15:result_ref:TEXT:0::0|"
    "16:error_code:TEXT:0::0|17:created_at:TEXT:1:CURRENT_TIMESTAMP:0|"
    "18:updated_at:TEXT:1:CURRENT_TIMESTAMP:0"
)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


SESSION_PROJECTS_CREATE_BODY = _create_body_fingerprint(SESSION_TABLE_STATEMENTS[4])
SESSION_PROJECTS_INSERT_TRIGGER_BODY = _trigger_body_fingerprint(
    SESSION_TABLE_STATEMENTS[6]
)
SESSION_PROJECTS_UPDATE_TRIGGER_BODY = _trigger_body_fingerprint(
    SESSION_TABLE_STATEMENTS[7]
)
SESSION_PROJECTS_CLASSIFY_INSERT_TRIGGER_BODY = _trigger_body_fingerprint(
    SESSION_TABLE_STATEMENTS[8]
)
SESSION_PROJECTS_CLASSIFY_UPDATE_TRIGGER_BODY = _trigger_body_fingerprint(
    SESSION_TABLE_STATEMENTS[9]
)
SESSION_PROJECTS_CANONICAL_PREDICATE = " AND ".join(
    (
        f"{_schema_body_expression('session_projects')} = "
        f"{_sql_literal(SESSION_PROJECTS_CREATE_BODY)}",
        f"{_column_signature_expression('session_projects')} = "
        f"{_sql_literal(SESSION_PROJECTS_COLUMN_SIGNATURE)}",
        "(SELECT COUNT(*) FROM pragma_foreign_key_list('session_projects') "
        "WHERE \"table\" = 'scribe_sessions' AND \"from\" = 'session_id' "
        "AND \"to\" = 'session_id' AND on_delete = 'CASCADE') = 1",
        "(SELECT COUNT(*) FROM pragma_foreign_key_list('session_projects') "
        "WHERE \"table\" = 'scribe_projects' AND \"from\" = 'project_name' "
        "AND \"to\" = 'name' AND on_delete = 'SET NULL') = 1",
        "(SELECT COUNT(*) FROM pragma_foreign_key_list('session_projects')) = 2",
        "(SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name = 'session_projects' AND name IN ("
        "'trg_session_projects_requires_session_insert', "
        "'trg_session_projects_requires_session_update', "
        "'trg_session_projects_classify_insert', "
        "'trg_session_projects_classify_update')) = 4",
        f"{_trigger_body_expression('trg_session_projects_requires_session_insert')} = "
        f"{_sql_literal(SESSION_PROJECTS_INSERT_TRIGGER_BODY)}",
        f"{_trigger_body_expression('trg_session_projects_requires_session_update')} = "
        f"{_sql_literal(SESSION_PROJECTS_UPDATE_TRIGGER_BODY)}",
        f"{_trigger_body_expression('trg_session_projects_classify_insert')} = "
        f"{_sql_literal(SESSION_PROJECTS_CLASSIFY_INSERT_TRIGGER_BODY)}",
        f"{_trigger_body_expression('trg_session_projects_classify_update')} = "
        f"{_sql_literal(SESSION_PROJECTS_CLASSIFY_UPDATE_TRIGGER_BODY)}",
    )
)

BACKGROUND_RECEIPTS_CREATE_BODY = _create_body_fingerprint(
    BACKGROUND_RECEIPT_TABLE_STATEMENTS[0]
)
BACKGROUND_RECEIPTS_CANONICAL_PREDICATE = " AND ".join(
    (
        f"{_schema_body_expression('background_receipts')} = "
        f"{_sql_literal(BACKGROUND_RECEIPTS_CREATE_BODY)}",
        f"{_column_signature_expression('background_receipts')} = "
        f"{_sql_literal(BACKGROUND_RECEIPTS_COLUMN_SIGNATURE)}",
        "(SELECT COUNT(*) FROM pragma_index_list('background_receipts') "
        "WHERE \"unique\" = 1 AND origin = 'u' AND name IN ("
        "SELECT name FROM pragma_index_list('background_receipts') AS indexes "
        "WHERE (SELECT group_concat(name, '|') FROM ("
        "SELECT name FROM pragma_index_info(indexes.name) ORDER BY seqno)) = "
        "'canonical_project_key|idempotency_key')) = 1",
        "(SELECT group_concat(name, '|') FROM (SELECT name FROM "
        "pragma_index_info('idx_background_receipts_claim') ORDER BY seqno)) = "
        "'canonical_project_key|lane|state|next_attempt_at|created_at'",
        "(SELECT group_concat(name, '|') FROM (SELECT name FROM "
        "pragma_index_info('idx_background_receipts_state_lease') ORDER BY seqno)) = "
        "'state|lease_expires_at'",
        "(SELECT group_concat(name, '|') FROM (SELECT name FROM "
        "pragma_index_info('idx_background_receipts_project_state') ORDER BY seqno)) = "
        "'canonical_project_key|state|payload_bytes'",
    )
)

_SCHEMA_PROBE_TABLE = "scribe_reliability_schema_probe"


def _schema_probe_statements(table_name: str, predicate: str) -> List[str]:
    """Build a side-effect-free transactional probe for one canonical table."""
    marker = f"scribe_reliability_schema_noncanonical:{table_name}"
    trigger_name = f"scribe_reliability_schema_probe_{table_name}"
    return [
        "BEGIN IMMEDIATE;",
        f"DROP TABLE IF EXISTS temp.{_SCHEMA_PROBE_TABLE};",
        f"CREATE TEMP TABLE {_SCHEMA_PROBE_TABLE} (value INTEGER NOT NULL);",
        (
            f"CREATE TEMP TRIGGER {trigger_name} BEFORE INSERT ON {_SCHEMA_PROBE_TABLE} "
            f"WHEN NOT ({predicate}) BEGIN SELECT RAISE(ROLLBACK, '{marker}'); END;"
        ),
        f"INSERT INTO {_SCHEMA_PROBE_TABLE} (value) VALUES (1);",
        f"DROP TABLE {_SCHEMA_PROBE_TABLE};",
        "COMMIT;",
    ]


async def _table_requires_rebuild(
    execute_many_fn: ExecuteManyFn,
    table_name: str,
    predicate: str,
) -> bool:
    """Return whether SQLite introspection finds a non-canonical table shape."""
    marker = f"scribe_reliability_schema_noncanonical:{table_name}"
    try:
        await execute_many_fn(_schema_probe_statements(table_name, predicate))
    except Exception as exc:
        if marker not in str(exc):
            raise
        return True
    return False


async def _execute_rebuild(
    execute_many_fn: ExecuteManyFn,
    statements: List[str],
) -> None:
    """Execute and roll back a rebuild on one acquired SQLite connection."""
    owner = getattr(execute_many_fn, "__self__", None)
    internals = getattr(owner, "_internals", None)
    write_gate = getattr(internals, "_write_gate", None)
    run_with_connection = getattr(internals, "_run_with_connection", None)
    if write_gate is None or not callable(run_with_connection):
        raise RuntimeError(
            "SQLite reliability rebuild requires a connection-affine executor"
        )

    def _run() -> None:
        def _apply(conn: Any) -> None:
            savepoint = "scribe_reliability_rebuild"
            nested = bool(conn.in_transaction)
            if nested:
                conn.execute(f"SAVEPOINT {savepoint};")
            else:
                conn.execute("BEGIN IMMEDIATE;")
            try:
                for statement in statements:
                    conn.execute(statement)
                if nested:
                    conn.execute(f"RELEASE SAVEPOINT {savepoint};")
                else:
                    conn.commit()
            except BaseException:
                try:
                    if nested:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint};")
                        conn.execute(f"RELEASE SAVEPOINT {savepoint};")
                    else:
                        conn.rollback()
                except BaseException as rollback_exc:
                    raise RuntimeError(
                        "SQLite reliability rebuild failed and rollback failed"
                    ) from rollback_exc
                raise

        with write_gate:
            run_with_connection(_apply)

    await asyncio.to_thread(_run)


def _copy_validation_statements(table_name: str, columns: tuple[str, ...]) -> List[str]:
    """Fail the rebuild transaction unless source and replacement rows are identical."""
    replacement_name = f"{table_name}_reliability_new"
    column_list = ", ".join(columns)
    marker = f"scribe_reliability_copy_mismatch:{table_name}"
    probe_table = f"{_SCHEMA_PROBE_TABLE}_copy"
    trigger_name = f"scribe_reliability_copy_probe_{table_name}"
    mismatch = (
        f"(SELECT COUNT(*) FROM {table_name}) <> "
        f"(SELECT COUNT(*) FROM {replacement_name}) OR "
        f"EXISTS (SELECT {column_list} FROM {table_name} "
        f"EXCEPT SELECT {column_list} FROM {replacement_name}) OR "
        f"EXISTS (SELECT {column_list} FROM {replacement_name} "
        f"EXCEPT SELECT {column_list} FROM {table_name})"
    )
    return [
        f"CREATE TEMP TABLE {probe_table} (value INTEGER NOT NULL);",
        (
            f"CREATE TEMP TRIGGER {trigger_name} BEFORE INSERT ON {probe_table} "
            f"WHEN ({mismatch}) BEGIN SELECT RAISE(ABORT, '{marker}'); END;"
        ),
        f"INSERT INTO {probe_table} (value) VALUES (1);",
        f"DROP TABLE {probe_table};",
    ]


def _post_rebuild_validation_statements(
    table_name: str,
    predicate: str,
) -> List[str]:
    """Fail before commit if canonical shape or foreign-key integrity is missing."""
    marker = f"scribe_reliability_validation_mismatch:{table_name}"
    probe_table = f"{_SCHEMA_PROBE_TABLE}_validation"
    trigger_name = f"scribe_reliability_validation_probe_{table_name}"
    mismatch = (
        f"NOT ({predicate}) OR EXISTS ("
        f"SELECT 1 FROM pragma_foreign_key_check('{table_name}'))"
    )
    return [
        f"CREATE TEMP TABLE {probe_table} (value INTEGER NOT NULL);",
        (
            f"CREATE TEMP TRIGGER {trigger_name} BEFORE INSERT ON {probe_table} "
            f"WHEN ({mismatch}) BEGIN SELECT RAISE(ABORT, '{marker}'); END;"
        ),
        f"INSERT INTO {probe_table} (value) VALUES (1);",
        f"DROP TABLE {probe_table};",
    ]


def _rebuild_table_statements(
    table_name: str,
    create_statement: str,
    columns: tuple[str, ...],
    *,
    restore_statements: tuple[str, ...] = (),
    canonical_predicate: str,
) -> List[str]:
    """Build one transactional, row-preserving canonical table replacement."""
    replacement_name = f"{table_name}_reliability_new"
    canonical_create = create_statement.replace(
        f"CREATE TABLE IF NOT EXISTS {table_name} (",
        f"CREATE TABLE {replacement_name} (",
        1,
    )
    column_list = ", ".join(columns)
    return [
        f"DROP TABLE IF EXISTS {replacement_name};",
        canonical_create,
        (
            f"INSERT INTO {replacement_name} ({column_list}) "
            f"SELECT {column_list} FROM {table_name};"
        ),
        *_copy_validation_statements(table_name, columns),
        f"DROP TABLE {table_name};",
        f"ALTER TABLE {replacement_name} RENAME TO {table_name};",
        *restore_statements,
        *_post_rebuild_validation_statements(table_name, canonical_predicate),
    ]


SESSION_PROJECT_REBUILD_STATEMENTS = _rebuild_table_statements(
    "session_projects",
    SESSION_TABLE_STATEMENTS[4],
    SESSION_PROJECT_COLUMNS,
    restore_statements=(
        SESSION_TABLE_STATEMENTS[5],
        SESSION_TABLE_STATEMENTS[6],
        SESSION_TABLE_STATEMENTS[7],
        SESSION_TABLE_STATEMENTS[8],
        SESSION_TABLE_STATEMENTS[9],
    ),
    canonical_predicate=SESSION_PROJECTS_CANONICAL_PREDICATE,
)
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
BACKGROUND_RECEIPT_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS idx_background_receipts_claim
        ON background_receipts (
            canonical_project_key,
            lane,
            state,
            next_attempt_at,
            created_at
        );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_background_receipts_state_lease
        ON background_receipts(state, lease_expires_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_background_receipts_project_state
        ON background_receipts(canonical_project_key, state, payload_bytes);
    """,
)
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
    "CREATE INDEX IF NOT EXISTS idx_apply_preview_receipts_expiry ON apply_preview_receipts(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_apply_preview_receipts_state_lease ON apply_preview_receipts(state, apply_lease_expires_at);",
    *BACKGROUND_RECEIPT_INDEX_STATEMENTS,
]

BACKGROUND_RECEIPT_REBUILD_STATEMENTS = _rebuild_table_statements(
    "background_receipts",
    BACKGROUND_RECEIPT_TABLE_STATEMENTS[0],
    BACKGROUND_RECEIPT_COLUMNS,
    restore_statements=BACKGROUND_RECEIPT_INDEX_STATEMENTS,
    canonical_predicate=BACKGROUND_RECEIPTS_CANONICAL_PREDICATE,
)

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
async def create_apply_preview_receipt_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(APPLY_PREVIEW_RECEIPT_TABLE_STATEMENTS)
async def create_background_receipt_tables(execute_many_fn: ExecuteManyFn) -> None:
    await execute_many_fn(BACKGROUND_RECEIPT_TABLE_STATEMENTS)
async def ensure_reliability_schema(
    execute_fn: ExecuteFn,
    execute_many_fn: ExecuteManyFn,
) -> None:
    """Materialize the additive C-05/C-06 SQLite schema."""
    for table, column, definition in (
        ("scribe_projects", "project_key", "TEXT"),
        ("session_projects", "project_key", "TEXT"),
        ("session_projects", "binding_generation", "INTEGER NOT NULL DEFAULT 1"),
        ("session_projects", "binding_state", "TEXT NOT NULL DEFAULT 'unresolved'"),
        ("session_projects", "binding_state_reason", "TEXT"),
    ):
        try:
            await execute_fn(f"ALTER TABLE {table} ADD COLUMN {column} {definition};", ())
        except Exception as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    await execute_fn(
        """
        UPDATE session_projects
        SET
            project_key = CASE
                WHEN project_name IS NOT NULL
                 AND EXISTS (
                    SELECT 1 FROM scribe_sessions AS ss
                    WHERE ss.session_id = session_projects.session_id
                 )
                 AND (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                 ) = 1
                 AND (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                      AND NULLIF(trim(p.project_key), '') IS NOT NULL
                 ) = 1
                THEN (
                    SELECT p.project_key FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                    LIMIT 1
                )
                ELSE NULL
            END,
            binding_generation = CASE
                WHEN binding_generation IS NULL OR binding_generation < 1 THEN 1
                ELSE binding_generation
            END,
            binding_state = CASE
                WHEN project_name IS NOT NULL
                 AND (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                      AND NULLIF(trim(p.project_key), '') IS NOT NULL
                 ) = 1
                 AND (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                 ) = 1
                THEN 'resolved'
                ELSE 'unresolved'
            END,
            binding_state_reason = CASE
                WHEN project_name IS NULL THEN 'project_name_absent'
                WHEN NOT EXISTS (
                    SELECT 1 FROM scribe_sessions AS ss
                    WHERE ss.session_id = session_projects.session_id
                ) THEN 'session_missing'
                WHEN (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                ) = 0 THEN 'project_identity_zero_matches'
                WHEN (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                ) > 1 THEN 'project_identity_ambiguous'
                WHEN (
                    SELECT COUNT(*) FROM scribe_projects AS p
                    JOIN scribe_sessions AS ss
                      ON ss.session_id = session_projects.session_id
                    WHERE p.repo_root = ss.repo_root
                      AND p.name = session_projects.project_name
                      AND NULLIF(trim(p.project_key), '') IS NOT NULL
                ) <> 1 THEN 'project_key_missing'
                ELSE NULL
            END
        WHERE binding_generation IS NULL
           OR binding_generation < 1
           OR binding_state IS NULL
           OR binding_state NOT IN ('resolved', 'unresolved')
           OR (
                binding_state = 'resolved'
                AND (
                    trim(COALESCE(project_key, '')) = ''
                    OR binding_state_reason IS NOT NULL
                )
           )
           OR (
                binding_state = 'unresolved'
                AND (
                    project_key IS NOT NULL
                    OR trim(COALESCE(binding_state_reason, '')) = ''
                )
           );
        """,
        (),
    )
    await create_background_receipt_tables(execute_many_fn)
    await execute_many_fn(
        [
            SESSION_TABLE_STATEMENTS[5],
            SESSION_TABLE_STATEMENTS[6],
            SESSION_TABLE_STATEMENTS[7],
            SESSION_TABLE_STATEMENTS[8],
            SESSION_TABLE_STATEMENTS[9],
            *BACKGROUND_RECEIPT_INDEX_STATEMENTS,
        ]
    )
    if await _table_requires_rebuild(
        execute_many_fn,
        "session_projects",
        SESSION_PROJECTS_CANONICAL_PREDICATE,
    ):
        await _execute_rebuild(execute_many_fn, SESSION_PROJECT_REBUILD_STATEMENTS)
    if await _table_requires_rebuild(
        execute_many_fn,
        "background_receipts",
        BACKGROUND_RECEIPTS_CANONICAL_PREDICATE,
    ):
        await _execute_rebuild(execute_many_fn, BACKGROUND_RECEIPT_REBUILD_STATEMENTS)
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
    await create_apply_preview_receipt_tables(execute_many_fn)
    await create_fts_tables(execute_many_fn)
    await ensure_telemetry_index_columns(execute_fn)
    await ensure_reliability_schema(execute_fn, execute_many_fn)
    await create_all_indexes(execute_many_fn)
