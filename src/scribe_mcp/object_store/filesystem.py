"""Local filesystem implementation of DocumentStore.

This is the default store when no remote object store URL is configured.
It wraps existing ``atomic_write`` from ``utils/files.py`` and adds the
``DocumentStore`` interface on top with zero overhead.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.object_store.base import DocumentStore
from scribe_mcp.object_store.keys import key_to_path, path_to_key


class FilesystemStore(DocumentStore):
    """Reads and writes documents directly on disk under *repo_root*."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root.resolve()

    # -- DocumentStore interface ----------------------------------------------

    async def write(self, key: str, content: str) -> None:
        target = key_to_path(key, self._root)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Reuse the battle-tested atomic_write helper.
        from scribe_mcp.utils.files import atomic_write

        await asyncio.to_thread(atomic_write, target, content, "w", self._root)

    async def read(self, key: str) -> str | None:
        target = key_to_path(key, self._root)
        if not target.is_file():
            return None
        return await asyncio.to_thread(target.read_text, "utf-8")

    async def exists(self, key: str) -> bool:
        return key_to_path(key, self._root).is_file()

    async def list_keys(self, prefix: str = "") -> list[str]:
        def _scan() -> list[str]:
            keys: list[str] = []
            for pattern in ("**/*.md", "**/*.bak"):
                for p in self._root.rglob(pattern):
                    if not p.is_file():
                        continue
                    k = path_to_key(p, self._root)
                    if k.startswith(prefix):
                        keys.append(k)
            return sorted(set(keys))

        return await asyncio.to_thread(_scan)

    async def delete(self, key: str) -> None:
        target = key_to_path(key, self._root)
        if target.is_file():
            await asyncio.to_thread(target.unlink)
