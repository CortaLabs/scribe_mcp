#!/usr/bin/env python3
"""
Tests for SPEC-FORMAT-002 fixes:
- rotate_log readable mode
- get_project verbose parameter
"""

import pytest
import pytest_asyncio
from mcp.types import CallToolResult
from scribe_mcp import server
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.rotate_log import rotate_log, _format_readable
from scribe_mcp.tools.get_project import get_project
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.append_entry import append_entry

pytestmark = pytest.mark.regression


def extract_result(mcp_result):
    """Extract actual result from MCP CallToolResult wrapper."""
    # If it's already a dict, return as-is
    if isinstance(mcp_result, dict):
        return mcp_result

    # If it's a CallToolResult, extract both content and structuredContent
    result = {}

    # Extract readable_content from TextContent
    if hasattr(mcp_result, 'content') and mcp_result.content:
        if hasattr(mcp_result.content[0], 'text'):
            result["readable_content"] = mcp_result.content[0].text

    # Extract structured data from structuredContent
    if hasattr(mcp_result, 'structuredContent') and mcp_result.structuredContent:
        # Merge structured content into result
        if isinstance(mcp_result.structuredContent, dict):
            result.update(mcp_result.structuredContent)
        else:
            return mcp_result.structuredContent

    # Return merged result or original if nothing extracted
    return result if result else mcp_result


@pytest.fixture
def test_project_name():
    """Generate unique test project name."""
    import uuid
    return f"test_format_fixes_{uuid.uuid4().hex[:8]}"


def successful_result(mcp_result, *, readable_header=None):
    """Require real tool success before checking its presentation."""
    result = extract_result(mcp_result)
    assert isinstance(result, dict), result
    if readable_header is not None:
        # Readable tools deliberately return text only, without an ok payload.
        assert isinstance(mcp_result, CallToolResult), mcp_result
        assert mcp_result.is_error is False, mcp_result
        readable = result.get("readable_content")
        assert isinstance(readable, str) and readable.strip(), result
        assert readable_header in readable, readable
    else:
        assert result.get("ok") is True, result
    assert not result.get("error"), result
    return result


@pytest_asyncio.fixture
async def format_project(tmp_path, monkeypatch, sqlite_db_path, test_agent, test_project_name):
    """Bind the canonical agent through real tools to an isolated repository."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    # The shared async sqlite_storage fixture uses pytest.fixture, which strict
    # asyncio mode leaves as a generator. Reuse its path with real setup/close.
    storage = SQLiteStorage(sqlite_db_path)
    await storage.setup()
    try:
        manager = StateManager(path=tmp_path / "state.json", storage_backend=storage)
        # Rebind real dependencies; no tool, authority, or result is mocked.
        monkeypatch.setattr(server, "storage_backend", storage)
        monkeypatch.setattr(server, "state_manager", manager)
        monkeypatch.setattr(server, "agent_context_manager", None)
        monkeypatch.setattr(server, "agent_identity", None)
        setup = successful_result(await set_project(
            agent=test_agent, name=test_project_name, root=str(root), format="structured",
        ))
        assert setup["project"]["name"] == test_project_name
        assert setup["project"]["root"] == str(root)
        yield setup["project"]
    finally:
        await storage.close()


async def append_test_entry(test_agent, message, status):
    return successful_result(await append_entry(
        agent=test_agent, message=message, status=status,
    ))


class TestRotateLogReadableFormat:
    """Test rotate_log readable format output."""

    @pytest.mark.asyncio
    async def test_rotate_log_has_format_parameter(self, test_project_name, test_agent, format_project):
        """Verify rotate_log accepts format parameter."""
        # Add some entries to create a log
        await append_test_entry(test_agent, message="Test entry 1", status="info")
        await append_test_entry(test_agent, message="Test entry 2", status="success")

        # Call with format parameter - dry run
        mcp_result = await rotate_log(agent=test_agent, format="readable", dry_run=True)
        result = successful_result(mcp_result, readable_header=f"📋 Dry run: {test_project_name}")

        # Should not error
        assert result is not None
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_rotate_log_readable_mode_returns_readable_content(self, test_project_name, test_agent, format_project):
        """Verify readable mode includes readable_content field."""
        # Add entries
        await append_test_entry(test_agent, message="Test entry", status="info")

        # Dry run with readable format
        mcp_result = await rotate_log(agent=test_agent, format="readable", dry_run=True)
        result = successful_result(mcp_result, readable_header=f"📋 Dry run: {test_project_name}")

        # Check for readable_content
        assert "readable_content" in result, "readable_content missing from response"
        assert isinstance(result["readable_content"], str)

    @pytest.mark.asyncio
    async def test_rotate_log_readable_content_format(self, test_project_name, test_agent, format_project):
        """Verify readable content has expected format."""
        # Add entries
        await append_test_entry(test_agent, message="Test entry", status="info")

        # Dry run with readable format
        mcp_result = await rotate_log(agent=test_agent, format="readable", dry_run=True)
        result = successful_result(mcp_result, readable_header=f"📋 Dry run: {test_project_name}")

        readable = result.get("readable_content", "")

        # Should contain project name and status emoji
        assert test_project_name in readable or "📋" in readable or "✅" in readable
        # Should be clean (no JSON-like structure)
        assert "{" not in readable or "}" not in readable

    @pytest.mark.asyncio
    async def test_rotate_log_structured_format_unchanged(self, test_project_name, test_agent, format_project):
        """Verify structured format still works (backwards compatibility)."""
        # Add entries
        await append_test_entry(test_agent, message="Test entry", status="info")

        # Dry run with structured format (default)
        mcp_result = await rotate_log(agent=test_agent, format="structured", dry_run=True)
        result = successful_result(mcp_result)

        # Should have standard structure (no readable_content wrapping)
        assert "ok" in result
        assert "dry_run" in result
        assert "results" in result
        # Structured mode shouldn't have readable_content as main output
        # (it might be in the dict but shouldn't be the primary return)

    def test_format_readable_helper_dry_run(self):
        """Test _format_readable helper with dry run response."""
        response = {
            "ok": True,
            "dry_run": True,
            "results": [
                {
                    "status": "dry_run_complete",
                    "log_type": "progress",
                    "entry_count": 150,
                    "estimated_size": 12288
                }
            ]
        }

        output = _format_readable(response, "test_project")

        # Should show dry run status
        assert "📋" in output or "Dry run" in output
        assert "test_project" in output
        assert "150" in output  # entry count
        assert "12.0 KB" in output or "12 KB" in output  # size

    def test_format_readable_helper_success(self):
        """Test _format_readable helper with successful rotation."""
        response = {
            "ok": True,
            "dry_run": False,
            "results": [
                {
                    "status": "rotated",
                    "log_type": "progress",
                    "original_path": "/path/to/PROGRESS_LOG.md",
                    "archive_path": "/path/to/PROGRESS_LOG.md.20260107.md",
                    "original_size_bytes": 15360
                }
            ]
        }

        output = _format_readable(response, "my_project")

        # Should show success status
        assert "✅" in output or "rotated" in output
        assert "my_project" in output
        assert "PROGRESS_LOG.md" in output
        assert "15.0 KB" in output or "15 KB" in output

    def test_format_readable_helper_failure(self):
        """Test _format_readable helper with error."""
        response = {
            "ok": False,
            "error": "File not found"
        }

        output = _format_readable(response, "failed_project")

        # Should show error status
        assert "❌" in output or "failed" in output
        assert "failed_project" in output
        assert "File not found" in output


class TestGetProjectVerboseParameter:
    """Test get_project verbose parameter."""

    @pytest.mark.asyncio
    async def test_get_project_has_verbose_parameter(self, test_project_name, test_agent, format_project):
        """Verify get_project accepts verbose parameter."""
        # Should not error
        mcp_result = await get_project(agent=test_agent, format="readable", verbose=False)
        result = successful_result(mcp_result, readable_header=f"📋 {test_project_name} (")
        assert result is not None

        mcp_result_verbose = await get_project(agent=test_agent, format="readable", verbose=True)
        result_verbose = successful_result(mcp_result_verbose, readable_header=f"📋 {test_project_name} (")
        assert result_verbose is not None

    @pytest.mark.asyncio
    async def test_get_project_verbose_false_excludes_entries(self, test_project_name, test_agent, format_project):
        """Verify verbose=False excludes recent entries from readable output."""
        # Create test project with entries
        await append_test_entry(test_agent, message="Test entry 1", status="info")
        await append_test_entry(test_agent, message="Test entry 2", status="success")

        # Get project with verbose=False (default)
        mcp_result = await get_project(agent=test_agent, format="readable", verbose=False)
        result = successful_result(mcp_result, readable_header=f"📋 {test_project_name} (")

        # Check that recent_entries is empty or not in payload
        recent = result.get("recent_entries", [])
        assert len(recent) == 0, f"verbose=False should exclude entries, got {len(recent)}"
        assert "Test entry" not in result["readable_content"]

    @pytest.mark.asyncio
    async def test_get_project_verbose_true_includes_entries(self, test_project_name, test_agent, format_project):
        """Verify verbose=True parameter is accepted and processed."""
        # Create test project with entries
        await append_test_entry(test_agent, message="Test entry 1", status="info")
        await append_test_entry(test_agent, message="Test entry 2", status="success")
        await append_test_entry(test_agent, message="Test entry 3", status="warn")

        # Get project with verbose=True
        mcp_result = await get_project(agent=test_agent, format="readable", verbose=True)
        result = successful_result(mcp_result, readable_header=f"📋 {test_project_name} (")
        for message in ("Test entry 1", "Test entry 2", "Test entry 3"):
            assert message in result["readable_content"]

        # Verify the call succeeded and verbose parameter was accepted
        assert result is not None, "verbose=True call should succeed"
        assert "readable_content" in result or "ok" in result, "Should return valid response"

        # Note: recent_entries might be empty if progress log file hasn't been flushed yet
        # The important thing is verbose=True doesn't cause errors
        recent = result.get("recent_entries", [])
        assert isinstance(recent, list), "recent_entries should be a list"
        # If entries exist, verify they're limited to 3
        if len(recent) > 0:
            assert len(recent) <= 3, "Should limit to 3 entries when present"

    @pytest.mark.asyncio
    async def test_get_project_default_verbose_is_false(self, test_project_name, test_agent, format_project):
        """Verify default verbose behavior matches verbose=False."""
        # Create test project with entries
        await append_test_entry(test_agent, message="Test entry", status="info")

        # Get project without verbose parameter (should default to False)
        mcp_result_default = await get_project(agent=test_agent, format="readable")
        result_default = successful_result(mcp_result_default, readable_header=f"📋 {test_project_name} (")

        mcp_result_explicit = await get_project(agent=test_agent, format="readable", verbose=False)
        result_explicit = successful_result(mcp_result_explicit, readable_header=f"📋 {test_project_name} (")

        # Should have same behavior
        recent_default = result_default.get("recent_entries", [])
        recent_explicit = result_explicit.get("recent_entries", [])

        assert len(recent_default) == len(recent_explicit), \
            "Default verbose should match verbose=False"
        assert len(recent_default) == 0, "Default should exclude entries"
        assert "Test entry" not in result_default["readable_content"]
        assert result_default["readable_content"] == result_explicit["readable_content"]

    @pytest.mark.asyncio
    async def test_get_project_structured_format_unaffected(self, test_project_name, test_agent, format_project):
        """Verify structured format ignores verbose parameter."""
        # Create test project with entries
        await append_test_entry(test_agent, message="Test entry", status="info")

        # Structured format should work regardless of verbose
        mcp_result_false = await get_project(agent=test_agent, format="structured", verbose=False)
        result_false = successful_result(mcp_result_false)

        mcp_result_true = await get_project(agent=test_agent, format="structured", verbose=True)
        result_true = successful_result(mcp_result_true)

        # Both should return valid structured data
        assert result_false.get("ok") == True
        assert result_true.get("ok") == True


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-x"])
