"""Abstract interfaces for document storage and remote providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class DocumentStore(ABC):
    """Unified interface for document persistence.

    Implementations range from local-only (FilesystemStore) to composite
    write-through stores that keep a local copy and push to a remote backend.
    """

    @abstractmethod
    async def write(self, key: str, content: str) -> None:
        """Persist *content* under *key*."""

    @abstractmethod
    async def read(self, key: str) -> str | None:
        """Return content for *key*, or ``None`` if not found."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return ``True`` when *key* is present in the store."""

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """Return all keys matching *prefix*."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove *key* from the store (no-op if absent)."""

    # Optional lifecycle hooks ------------------------------------------------

    async def setup(self) -> None:  # noqa: B027
        """Run any one-time initialisation (connections, tables, etc.)."""

    async def close(self) -> None:  # noqa: B027
        """Release held resources."""


class RemoteProvider(ABC):
    """Backend-agnostic remote storage provider.

    Each provider maps Scribe document keys to its own addressing scheme
    (content-addressable hashes for CortaStore, flat keys for S3, etc.).
    """

    @abstractmethod
    async def put(self, key: str, content: str) -> None:
        """Upload *content* under *key*."""

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Download content for *key*, or ``None`` if absent."""

    @abstractmethod
    async def head(self, key: str) -> bool:
        """Return ``True`` when *key* exists remotely."""

    @abstractmethod
    async def list(self, prefix: str = "") -> list[str]:
        """List remote keys matching *prefix*."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete *key* from the remote store."""

    async def bulk_check(self, keys: list[str]) -> list[str]:
        """Return the subset of *keys* that are **missing** remotely.

        Default implementation falls back to per-key ``head()`` calls.
        Providers with a native bulk API (e.g. CortaStore ``/sync/check``)
        should override this for efficiency.
        """
        missing: list[str] = []
        for k in keys:
            if not await self.head(k):
                missing.append(k)
        return missing

    async def setup(self) -> None:  # noqa: B027
        """Run any one-time initialisation."""

    async def close(self) -> None:  # noqa: B027
        """Release held resources."""
