"""Storage backend factory and helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from scribe_mcp.storage.base import StorageBackend

if TYPE_CHECKING:
    from scribe_mcp.config.mode_detection import OperatingMode


def create_storage_backend(
    mode: Optional["OperatingMode"] = None,
) -> Optional[StorageBackend]:
    """Instantiate the configured storage backend.

    Imports are deferred so that only the chosen backend's module
    is loaded — avoids pulling in heavy dependency chains at import time.

    Args:
        mode: If ``OperatingMode.CLIENT``, return a
              :class:`~scribe_mcp.storage.remote.RemoteStorageBackend`
              that proxies all persistent ops to the remote server.
    """
    from scribe_mcp.config.settings import settings

    # Auto-detect mode from settings if not explicitly provided.
    # This handles the module-level call in server.py which passes no mode arg —
    # without this, a SCRIBE_DB_URL in .env would wastefully spin up PostgresStorage
    # only to be discarded by _startup() once CLIENT mode is detected.
    if mode is None:
        mode_str = getattr(settings, "mode", None)
        if mode_str == "client":
            from scribe_mcp.config.mode_detection import OperatingMode
            mode = OperatingMode.CLIENT

    # CLIENT mode: proxy all DB operations to the remote Scribe server
    if mode is not None:
        from scribe_mcp.config.mode_detection import OperatingMode as _OM

        if mode == _OM.CLIENT:
            from scribe_mcp.storage.remote import RemoteStorageBackend

            return RemoteStorageBackend(
                server_url=settings.remote_server_url or "",
                timeout=settings.remote_connect_timeout,
            )

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
