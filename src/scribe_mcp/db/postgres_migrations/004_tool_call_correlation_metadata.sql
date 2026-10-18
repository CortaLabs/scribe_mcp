ALTER TABLE tool_calls
    ADD COLUMN IF NOT EXISTS correlation_id TEXT,
    ADD COLUMN IF NOT EXISTS measurement_scope TEXT;

CREATE INDEX IF NOT EXISTS idx_tool_calls_correlation
    ON tool_calls (correlation_id);
