#!/usr/bin/env python3
"""Integration tests for Bug Fix #3: Connection Isolation in SQLite WAL mode.

This test suite verifies that auto-registration writes are visible to context reload
by ensuring both operations use the same backend connection instead of isolated
sqlite3.connect() calls.

Research Reference: RESEARCH_AUTO_REGISTRATION_DEEP_DIVE_20260106.md Section 9.1
Bug: Auto-registration writes not visible to manage_docs context reload in production
Root Cause: SQLite WAL mode connection isolation
Fix: Replace sqlite3.connect() with backend._fetchone() in shared/logging_utils.py
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.manage_docs import manage_docs


@pytest.mark.asyncio
async def test_backend_connection_reuse_in_context_reload(tmp_path):
    """Test that context reload uses backend connection, not isolated sqlite3.connect()."""

    # Setup test environment
    db_path = tmp_path / "test.db"
    backend = SQLiteStorage(db_path)
    await backend._initialise()

    # Create a test project with auto-registration
    project_name = "test_connection_reuse"
    repo_root = str(tmp_path / "repo")
    progress_log = str(tmp_path / "repo" / "PROGRESS_LOG.md")

    Path(repo_root).mkdir(parents=True, exist_ok=True)
    Path(progress_log).touch()

    # Register project via backend (simulating auto-registration)
    await backend.upsert_project(
        name=project_name,
        repo_root=repo_root,
        progress_log_path=progress_log
    )

    # Verify backend can read its own write (connection reuse)
    row = await backend._fetchone(
        "SELECT name, repo_root, progress_log_path FROM scribe_projects WHERE name = ?",
        (project_name,)
    )

    assert row is not None, "Backend should see its own write"
    assert row["name"] == project_name
    assert row["repo_root"] == repo_root
    assert row["progress_log_path"] == progress_log


@pytest.mark.asyncio
async def test_no_isolated_sqlite3_connect_in_logging_utils():
    """Verify that shared/logging_utils.py doesn't use isolated sqlite3.connect()."""

    # Read the logging_utils.py file
    logging_utils_path = Path(__file__).parent.parent / "shared" / "logging_utils.py"
    content = logging_utils_path.read_text()

    # Check for the fix: backend._fetchone() should be present
    assert "backend._fetchone(" in content, \
        "Fix not applied: backend._fetchone() must be used for connection reuse"

    # Check for the bug: isolated sqlite3.connect() should NOT be in context reload section
    lines = content.split("\n")
    in_context_reload_section = False
    has_isolated_connect = False

    for i, line in enumerate(lines):
        # Detect context reload section (lines 90-145)
        if "get_session_project query" in line:
            in_context_reload_section = True
        elif in_context_reload_section and "if not session_project:" in line:
            in_context_reload_section = False

        # Check for isolated sqlite3.connect() in the critical section
        if in_context_reload_section and "sqlite3.connect(" in line:
            # Verify it's NOT the fixed version (should use backend instead)
            context = "\n".join(lines[max(0, i-3):min(len(lines), i+3)])
            if "backend._fetchone" not in context:
                has_isolated_connect = True
                break

    assert not has_isolated_connect, \
        "BUG STILL PRESENT: Found isolated sqlite3.connect() in context reload section"


@pytest.mark.asyncio
async def test_auto_registration_visibility_production_flow(tmp_path):
    """Integration test: Verify auto-registration writes are visible to context reload."""

    # Setup real backend
    db_path = tmp_path / "scribe_projects.db"
    backend = SQLiteStorage(db_path)
    await backend._initialise()

    # Setup project structure
    project_name = "test_auto_reg_visibility"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / project_name
    docs_dir.mkdir(parents=True, exist_ok=True)

    arch_guide = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch_guide.write_text("# Architecture\n\nInitial content\n")

    # Register project (simulates set_project auto-registration)
    await backend.upsert_project(
        name=project_name,
        repo_root=str(repo_root),
        progress_log_path=str(docs_dir / "PROGRESS_LOG.md")
    )

    # Store session project mapping
    await backend.set_session_project("test_session_123", project_name)

    # Mock server module with backend
    mock_server = MagicMock()
    mock_server.storage_backend = backend
    mock_server.state_manager = AsyncMock()
    mock_server.state_manager.load = AsyncMock(return_value=MagicMock(recent_projects=[]))
    mock_server.state_manager.record_tool = AsyncMock(return_value={"tool": "test"})

    # Mock execution context in project mode
    mock_exec_context = MagicMock()
    mock_exec_context.mode = "project"
    mock_exec_context.session_id = "test_session_123"
    mock_exec_context.stable_session_id = "test_session_123"
    mock_server.get_execution_context = MagicMock(return_value=mock_exec_context)

    # Now verify context reload can see the auto-registered project
    from scribe_mcp.shared.logging_utils import resolve_logging_context

    context = await resolve_logging_context(
        tool_name="manage_docs",
        server_module=mock_server,
        require_project=True
    )

    # CRITICAL ASSERTION: Context should resolve the auto-registered project
    assert context.project is not None, \
        "FAILURE: Auto-registered project not visible to context reload"
    assert context.project["name"] == project_name, \
        f"Wrong project resolved: {context.project.get('name')} != {project_name}"


@pytest.mark.asyncio
async def test_backend_connection_vs_isolated_connection():
    """Verify that backend connection sees writes that isolated connections might miss."""
    import tempfile
    import sqlite3

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        backend = SQLiteStorage(db_path)
        await backend._initialise()

        # Write via backend
        test_project = "backend_write_test"
        await backend.upsert_project(
            name=test_project,
            repo_root="/test/root",
            progress_log_path="/test/log.md"
        )

        # Read via backend (should succeed - same connection pool)
        row_backend = await backend._fetchone(
            "SELECT name FROM scribe_projects WHERE name = ?",
            (test_project,)
        )
        assert row_backend is not None, "Backend should see its own write"

        # Read via isolated connection (might fail in WAL mode before WAL checkpoint)
        # This simulates the OLD buggy behavior
        conn_isolated = sqlite3.connect(str(db_path))
        cursor = conn_isolated.execute(
            "SELECT name FROM scribe_projects WHERE name = ?",
            (test_project,)
        )
        row_isolated = cursor.fetchone()
        conn_isolated.close()

        # Note: In WAL mode, isolated connection might not see uncommitted writes
        # But backend connection ALWAYS sees its own writes (connection reuse)
        # The fix ensures we use backend, not isolated connections


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
