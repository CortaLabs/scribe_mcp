"""Integration tests for enhanced read_file and search error paths."""

import sys
from pathlib import Path
import tempfile
import asyncio

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.read_file import read_file
from tools.search import search
from scribe_mcp.server import app
from scribe_mcp.shared.execution_context import ExecutionContext, AgentIdentity


@pytest.fixture
def execution_context(tmp_path):
    """Create test execution context with temp directory as repo root."""
    # Create a temporary repo structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").touch()
    (tmp_path / "src" / "auth_handler.py").touch()
    (tmp_path / "src" / "config.py").touch()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").touch()

    # Set up execution context
    agent_identity = AgentIdentity(
        agent_kind="test",
        instance_id="test_instance",
        sub_id=None,
        display_name="TestAgent",
        model="test-model"
    )

    from datetime import datetime, timezone

    context = ExecutionContext(
        execution_id="test_exec",
        session_id="test_session",
        intent="testing",
        repo_root=str(tmp_path),
        mode="project",
        agent_identity=agent_identity,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        affected_dev_projects=[]
    )

    # Store context in server
    app.state.execution_context = context

    yield tmp_path

    # Cleanup
    app.state.execution_context = None


# ============================================================================
# read_file Integration Tests (5 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_read_file_not_found_readable(execution_context):
    """format='readable' shows enriched suggestions for non-existent file."""
    result = await read_file(
        agent="TestAgent",
        path="src/auth_handlers.py",  # Typo: missing 's'
        format="readable"
    )

    # Should be a dict (readable format returns dict for errors)
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_type"] == "not_found"

    # Should have fuzzy suggestions
    assert "similar_files" in result
    similar_files = result["similar_files"]
    assert len(similar_files) > 0

    # Should suggest auth_handler.py (close match)
    file_names = [f["name"] for f in similar_files]
    assert "auth_handler.py" in file_names

    # Should have suggestion text
    assert "suggestion" in result
    assert "Did you mean" in result["suggestion"]

    # Should have parent listing
    assert "parent_directory" in result
    assert "parent_listing" in result
    listing = result["parent_listing"]
    assert "auth.py" in listing["files"]
    assert "auth_handler.py" in listing["files"]

    # Should have search suggestion
    assert "search_suggestion" in result
    assert "search(" in result["search_suggestion"]


@pytest.mark.asyncio
async def test_read_file_not_found_structured(execution_context):
    """format='structured' returns minimal response (no suggestions overhead)."""
    result = await read_file(
        agent="TestAgent",
        path="src/nonexistent.py",
        format="structured"
    )

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_type"] == "not_found"

    # Should NOT have expensive enrichment fields
    assert "similar_files" not in result
    assert "parent_listing" not in result
    assert "search_suggestion" not in result


@pytest.mark.asyncio
async def test_read_file_is_directory(execution_context):
    """Directory path shows correct error type."""
    result = await read_file(
        agent="TestAgent",
        path="src",  # This is a directory
        format="readable"
    )

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_type"] == "is_directory"
    assert result["error"] == "path is a directory"


@pytest.mark.asyncio
async def test_read_file_permission_error(execution_context):
    """Graceful degradation on permission issues."""
    # Create a file and try to make it unreadable
    restricted_file = execution_context / "restricted.txt"
    restricted_file.touch()

    import os
    try:
        os.chmod(restricted_file, 0o000)

        result = await read_file(
            agent="TestAgent",
            path="restricted.txt",
            format="readable"
        )

        # Should classify as permission_denied or unknown
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert result["error_type"] in ("permission_denied", "unknown")

    finally:
        # Restore permissions for cleanup
        os.chmod(restricted_file, 0o644)


@pytest.mark.asyncio
async def test_read_file_large_parent_dir(execution_context):
    """Parent with many files doesn't crash (respects MAX_DIRECTORY_ENTRIES)."""
    # Create a directory with many files
    large_dir = execution_context / "large"
    large_dir.mkdir()

    for i in range(100):
        (large_dir / f"file_{i}.py").touch()

    result = await read_file(
        agent="TestAgent",
        path="large/nonexistent.py",
        format="readable"
    )

    assert isinstance(result, dict)
    assert result["ok"] is False

    # Should have listing but truncated
    if "parent_listing" in result:
        listing = result["parent_listing"]
        # Should be truncated (max 30 files)
        assert len(listing.get("files", [])) <= 30
        assert listing.get("truncated") is True


# ============================================================================
# search Integration Tests (3 tests)
# ============================================================================

@pytest.mark.asyncio
async def test_search_path_not_found_readable(execution_context):
    """format='readable' shows enriched suggestions for non-existent path."""
    result = await search(
        agent="TestAgent",
        pattern="test",
        path="testz",  # Typo: should be "tests"
        format="readable"
    )

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_type"] == "not_found"

    # Should have fuzzy suggestions (prioritizing directories)
    if "similar_paths" in result:
        similar_paths = result["similar_paths"]
        assert len(similar_paths) > 0

        # Should suggest tests/ (close match)
        path_names = [p["name"] for p in similar_paths]
        assert "tests/" in path_names

        # All suggestions should be directories
        assert all(p["is_dir"] for p in similar_paths)

    # Should have parent listing
    if "parent_listing" in result:
        listing = result["parent_listing"]
        assert "tests/" in listing.get("directories", [])


@pytest.mark.asyncio
async def test_search_path_not_found_structured(execution_context):
    """format='structured' returns minimal response (no suggestions overhead)."""
    result = await search(
        agent="TestAgent",
        pattern="test",
        path="nonexistent",
        format="structured"
    )

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert result["error_type"] == "not_found"

    # Should NOT have expensive enrichment fields
    assert "similar_paths" not in result
    assert "parent_listing" not in result


@pytest.mark.asyncio
async def test_search_parent_unreadable(execution_context):
    """Graceful degradation when parent directory is unreadable."""
    # Create a restricted directory structure
    restricted = execution_context / "restricted"
    restricted.mkdir()
    child = restricted / "child"

    import os
    try:
        os.chmod(restricted, 0o000)

        result = await search(
            agent="TestAgent",
            pattern="test",
            path="restricted/child",
            format="readable"
        )

        # Should return error without crashing
        assert isinstance(result, dict)
        assert result["ok"] is False

        # If parent listing attempted, should handle permission error gracefully
        if "parent_listing" in result:
            assert result["parent_listing"].get("permission_error") is True

    finally:
        # Restore permissions for cleanup
        os.chmod(restricted, 0o755)


# ============================================================================
# Backwards Compatibility Tests
# ============================================================================

@pytest.mark.asyncio
async def test_backwards_compatibility_core_fields(execution_context):
    """Core error fields remain unchanged for backwards compatibility."""
    result = await read_file(
        agent="TestAgent",
        path="nonexistent.py",
        format="structured"
    )

    # Core fields that existed before enhancement
    assert "ok" in result
    assert result["ok"] is False
    assert "error" in result
    assert isinstance(result["error"], str)
    assert "absolute_path" in result

    # New fields are additive
    assert "error_type" in result


@pytest.mark.asyncio
async def test_compact_format_minimal_response(execution_context):
    """Compact format returns minimal response (no enrichment)."""
    result = await read_file(
        agent="TestAgent",
        path="nonexistent.py",
        format="compact"
    )

    # Should be minimal
    assert isinstance(result, dict)
    assert result["ok"] is False

    # Should NOT have enrichment fields
    assert "similar_files" not in result
    assert "parent_listing" not in result
