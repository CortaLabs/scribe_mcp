"""Storage backend factory and helpers."""

from __future__ import annotations

from typing import Optional

from scribe_mcp.storage.base import StorageBackend


def create_storage_backend() -> Optional[StorageBackend]:
    """Instantiate the configured storage backend.

    Imports are deferred so that only the chosen backend's module
    is loaded — avoids pulling in heavy dependency chains at import time.
    """
    from scribe_mcp.config.settings import settings

    backend_name = settings.storage_backend
    if backend_name == "postgres" and settings.db_url:
        from scribe_mcp.storage.postgres import PostgresStorage
        return PostgresStorage(settings.db_url)
    if backend_name == "sqlite":
        from scribe_mcp.storage.sqlite import SQLiteStorage
        return SQLiteStorage(settings.sqlite_path)
    # Fallback: if postgres requested but no URL, default to sqlite
    if settings.db_url:
        from scribe_mcp.storage.postgres import PostgresStorage
        return PostgresStorage(settings.db_url)
    from scribe_mcp.storage.sqlite import SQLiteStorage
    return SQLiteStorage(settings.sqlite_path)
