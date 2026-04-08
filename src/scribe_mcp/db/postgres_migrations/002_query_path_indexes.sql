-- Query-path indexes to keep read_recent/query_entries performant at scale.

CREATE INDEX IF NOT EXISTS idx_entries_ts_iso_desc
    ON scribe_entries (ts_iso DESC);

CREATE INDEX IF NOT EXISTS idx_entries_project_logtype_ts
    ON scribe_entries (project_id, log_type, ts_iso DESC);

CREATE INDEX IF NOT EXISTS idx_entries_project_agent_ts
    ON scribe_entries (project_id, agent, ts_iso DESC);

CREATE INDEX IF NOT EXISTS idx_entries_project_emoji_ts
    ON scribe_entries (project_id, emoji, ts_iso DESC);

CREATE INDEX IF NOT EXISTS idx_tool_calls_repo_timestamp
    ON tool_calls (repo_root, timestamp DESC);

