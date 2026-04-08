"""Hybrid (write-through) document store.

Writes are committed locally first (must succeed), then pushed to the
remote provider as a fire-and-forget background task.  Reads hit local
first; on a miss the remote is queried and the result is cached locally.
"""

from __future__ import annotations

import asyncio
import logging

from scribe_mcp.object_store.base import DocumentStore, RemoteProvider
from scribe_mcp.object_store.filesystem import FilesystemStore

logger = logging.getLogger(__name__)


class HybridStore(DocumentStore):
    """Composite store: local :class:`FilesystemStore` + remote :class:`RemoteProvider`."""

    def __init__(self, local: FilesystemStore, remote: RemoteProvider) -> None:
        self._local = local
        self._remote = remote

    # -- lifecycle ------------------------------------------------------------

    async def setup(self) -> None:
        await self._remote.setup()

    async def close(self) -> None:
        await self._remote.close()

    # -- DocumentStore interface ----------------------------------------------

    async def write(self, key: str, content: str) -> None:
        # Local write is mandatory — must succeed.
        await self._local.write(key, content)

        # Remote write is fire-and-forget; failures are logged, never raised.
        try:
            await self._remote.put(key, content)
        except Exception:
            logger.warning("Remote write failed for %s", key, exc_info=True)

    async def read(self, key: str) -> str | None:
        # Try local first.
        result = await self._local.read(key)
        if result is not None:
            return result

        # Cache miss — try remote.
        try:
            result = await self._remote.get(key)
        except Exception:
            logger.warning("Remote read failed for %s", key, exc_info=True)
            return None

        if result is not None:
            # Cache locally for subsequent reads.
            try:
                await self._local.write(key, result)
            except Exception:
                logger.warning("Local cache-write failed for %s", key, exc_info=True)

        return result

    async def exists(self, key: str) -> bool:
        if await self._local.exists(key):
            return True
        try:
            return await self._remote.head(key)
        except Exception:
            return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        local_keys = await self._local.list_keys(prefix)
        try:
            remote_keys = await self._remote.list(prefix)
        except Exception:
            logger.warning("Remote list failed for prefix %r", prefix, exc_info=True)
            remote_keys = []
        # Merge and deduplicate, preserving order.
        seen: set[str] = set(local_keys)
        merged = list(local_keys)
        for k in remote_keys:
            if k not in seen:
                seen.add(k)
                merged.append(k)
        return sorted(merged)

    async def delete(self, key: str) -> None:
        await self._local.delete(key)
        try:
            await self._remote.delete(key)
        except Exception:
            logger.warning("Remote delete failed for %s", key, exc_info=True)
