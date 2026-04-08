-- Retain legacy document/log tables for SQLite parity and future object-store expansion.

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
