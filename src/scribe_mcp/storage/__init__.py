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
        return PostgresStorage(
            settings.db_url,
            schema_name=settings.postgres_schema,
            pool_min_size=settings.postgres_pool_min_size,
            pool_max_size=settings.postgres_pool_max_size,
            command_timeout_seconds=settings.postgres_command_timeout_seconds,
            connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
            max_inactive_connection_lifetime_seconds=settings.postgres_max_inactive_connection_lifetime_seconds,
            connect_retries=settings.postgres_connect_retries,
            connect_retry_backoff_seconds=settings.postgres_connect_retry_backoff_seconds,
        )
    if backend_name == "sqlite":
        from scribe_mcp.storage.sqlite import SQLiteStorage
        return SQLiteStorage(settings.sqlite_path)
    # Fallback: if postgres requested but no URL, default to sqlite
    if settings.db_url:
        from scribe_mcp.storage.postgres import PostgresStorage
        return PostgresStorage(
            settings.db_url,
            schema_name=settings.postgres_schema,
            pool_min_size=settings.postgres_pool_min_size,
            pool_max_size=settings.postgres_pool_max_size,
            command_timeout_seconds=settings.postgres_command_timeout_seconds,
            connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
            max_inactive_connection_lifetime_seconds=settings.postgres_max_inactive_connection_lifetime_seconds,
            connect_retries=settings.postgres_connect_retries,
            connect_retry_backoff_seconds=settings.postgres_connect_retry_backoff_seconds,
        )
    from scribe_mcp.storage.sqlite import SQLiteStorage
    return SQLiteStorage(settings.sqlite_path)
