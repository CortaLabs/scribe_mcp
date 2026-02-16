"""Scribe Object Store — pluggable document persistence layer.

Public API
----------
- ``create_document_store(settings)`` — factory (returns FilesystemStore or HybridStore)
- ``sync_file_to_store(file_path, content, repo_root)`` — fire-and-forget helper for write paths

The store is selected automatically based on environment variables:

* No ``SCRIBE_OBJECT_STORE_URL`` → :class:`FilesystemStore` (zero overhead)
* URL set, provider ``corta`` → :class:`HybridStore` with :class:`CortaStoreProvider`
* URL set, provider ``s3`` → :class:`HybridStore` with :class:`S3Provider`
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scribe_mcp.object_store.base import DocumentStore, RemoteProvider
from scribe_mcp.object_store.filesystem import FilesystemStore
from scribe_mcp.object_store.keys import key_to_path, path_to_key, should_sync

if TYPE_CHECKING:
    from scribe_mcp.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = [
    "DocumentStore",
    "RemoteProvider",
    "FilesystemStore",
    "create_document_store",
    "sync_file_to_store",
    "path_to_key",
    "key_to_path",
    "should_sync",
]


def create_document_store(settings: Settings) -> DocumentStore:
    """Build the appropriate :class:`DocumentStore` from *settings*.

    When ``object_store_url`` is not set the returned store is a plain
    :class:`FilesystemStore` with zero remote overhead — existing behaviour
    is preserved exactly.
    """
    repo_root = settings.project_root
    local = FilesystemStore(repo_root)

    url: str | None = getattr(settings, "object_store_url", None)
    if not url:
        logger.debug("No SCRIBE_OBJECT_STORE_URL — using local-only FilesystemStore")
        return local

    provider_name: str = getattr(settings, "object_store_provider", "corta")
    timeout: float = getattr(settings, "object_store_timeout", 10.0)

    kwargs: dict[str, Any] = {}

    if provider_name == "corta":
        kwargs["base_url"] = url
        kwargs["hmac_key"] = getattr(settings, "object_store_key", "") or ""
        kwargs["project"] = getattr(settings, "object_store_project", "") or "scribe"
        kwargs["timeout"] = timeout
    elif provider_name == "s3":
        kwargs["endpoint_url"] = url
        kwargs["bucket"] = getattr(settings, "s3_bucket", "") or ""
        kwargs["prefix"] = getattr(settings, "s3_prefix", "scribe/")
        kwargs["region"] = getattr(settings, "s3_region", "us-east-1")
        kwargs["timeout"] = timeout
    else:
        kwargs["base_url"] = url
        kwargs["timeout"] = timeout

    from scribe_mcp.object_store.providers import create_provider

    remote = create_provider(provider_name, **kwargs)

    from scribe_mcp.object_store.hybrid import HybridStore

    logger.info(
        "Object store enabled: provider=%s url=%s",
        provider_name,
        url,
    )
    return HybridStore(local=local, remote=remote)


async def sync_file_to_store(
    file_path: Path,
    content: str,
    repo_root: Path,
) -> None:
    """Fire-and-forget sync of a single file to the remote object store.

    This is the integration point used by secondary write paths
    (``edit_file``, ``special_create``, ``generate_doc_templates``, etc.).

    No-op when no object store is configured or the file is not eligible
    for sync (according to :func:`should_sync`).
    """
    if not should_sync(file_path, repo_root):
        return

    try:
        from scribe_mcp.server import app, background_tasks
    except ImportError:
        return

    store: DocumentStore | None = getattr(getattr(app, "state", None), "document_store", None)
    if store is None:
        return

    key = path_to_key(file_path, repo_root)

    async def _push() -> None:
        try:
            await store.write(key, content)
        except Exception:
            logger.warning("Object store sync failed for %s", key, exc_info=True)

    task = asyncio.create_task(_push())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
