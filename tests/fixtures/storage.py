"""Reusable storage fixtures for integration and tool tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.storage.sqlite import SQLiteStorage


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> Path:
    """Return an isolated SQLite DB path for a test."""
    return tmp_path / "scribe_projects.db"


@pytest.fixture
async def sqlite_storage(sqlite_db_path: Path):
    """Return an initialized SQLiteStorage backed by tmp_path."""
    storage = SQLiteStorage(sqlite_db_path)
    await storage.setup()
    try:
        yield storage
    finally:
        close_fn = getattr(storage, "close", None)
        if callable(close_fn):
            maybe_awaitable = close_fn()
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable
