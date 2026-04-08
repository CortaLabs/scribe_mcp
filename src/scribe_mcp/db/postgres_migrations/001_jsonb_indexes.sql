-- Extra JSONB/trigram indexes for high-volume Postgres operation.

CREATE INDEX IF NOT EXISTS idx_projects_tags_gin
    ON scribe_projects USING GIN (tags);

CREATE INDEX IF NOT EXISTS idx_projects_meta_gin
    ON scribe_projects USING GIN (meta);

CREATE INDEX IF NOT EXISTS idx_document_sections_metadata_gin
    ON document_sections USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_document_changes_metadata_gin
    ON document_changes USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_sync_status_conflict_details_gin
    ON sync_status USING GIN (conflict_details);

CREATE INDEX IF NOT EXISTS idx_reminder_history_context_metadata_gin
    ON reminder_history USING GIN (context_metadata);

CREATE INDEX IF NOT EXISTS idx_bridges_manifest_json_gin
    ON scribe_bridges USING GIN (manifest_json);

CREATE INDEX IF NOT EXISTS idx_bridges_health_json_gin
    ON scribe_bridges USING GIN (health_json);

CREATE INDEX IF NOT EXISTS idx_entries_message_trgm
    ON scribe_entries USING GIN (message gin_trgm_ops);

