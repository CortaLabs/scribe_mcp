"""Tests for search tool pagination (TP-3.1 + TP-3.2)."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from scribe_mcp.tools.search import search
from scribe_mcp.shared.execution_context import ExecutionContext, AgentIdentity
from scribe_mcp import server as server_module


@pytest.fixture
def test_repo(tmp_path):
    """Create a test repository with multiple files containing many matches."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create file with 25 lines containing "test"
    test_file = repo / "test_file.py"
    lines = []
    for i in range(1, 26):
        lines.append(f"# This is test line {i}")
    test_file.write_text("\n".join(lines))

    # Create another file with 15 lines containing "test"
    another_file = repo / "another_file.py"
    lines = []
    for i in range(1, 16):
        lines.append(f"# Another test line {i}")
    another_file.write_text("\n".join(lines))

    return repo


def _install_execution_context(repo_root: str):
    """Install execution context for tests."""
    ctx = ExecutionContext(
        execution_id="test_exec",
        session_id="test_session",
        repo_root=repo_root,
        mode="sentinel",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        affected_dev_projects=[],
        intent="test_pagination",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="test-agent",
            sub_id=None,
            display_name=None
        ),
        sentinel_day="2026-02-01"
    )
    return server_module.router_context_manager.set_current(ctx)


@pytest.mark.asyncio
async def test_pagination_basic(test_repo):
    """Test basic pagination with page and page_size parameters."""
    token = _install_execution_context(str(test_repo))
    try:
        # Search for "test" which should match 40 lines total (25 + 15)
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=1,
            page_size=10,
        )

        assert result["ok"] is True
        assert "pagination" in result

        pagination = result["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 10
        assert pagination["total_matches"] == 40
        assert pagination["total_pages"] == 4
        assert pagination["has_next"] is True
        assert pagination["has_prev"] is False

        # Verify we got exactly 10 matches on page 1
        total_matches_on_page = sum(len(m["matches"]) for m in result["matches"])
        assert total_matches_on_page == 10

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_second_page(test_repo):
    """Test requesting a specific page."""
    token = _install_execution_context(str(test_repo))
    try:
        # Get page 2
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=2,
            page_size=10,
        )

        assert result["ok"] is True
        pagination = result["pagination"]
        assert pagination["page"] == 2
        assert pagination["has_next"] is True
        assert pagination["has_prev"] is True

        # Verify we got exactly 10 matches on page 2
        total_matches_on_page = sum(len(m["matches"]) for m in result["matches"])
        assert total_matches_on_page == 10

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_last_page(test_repo):
    """Test last page with partial results."""
    token = _install_execution_context(str(test_repo))
    try:
        # Get page 4 (last page) - should have 10 matches
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=4,
            page_size=10,
        )

        assert result["ok"] is True
        pagination = result["pagination"]
        assert pagination["page"] == 4
        assert pagination["total_pages"] == 4
        assert pagination["has_next"] is False
        assert pagination["has_prev"] is True

        # Page 4 should have exactly 10 matches (40 total / 10 per page = 4 full pages)
        total_matches_on_page = sum(len(m["matches"]) for m in result["matches"])
        assert total_matches_on_page == 10

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_page_too_high(test_repo):
    """Test requesting a page beyond total pages - should clamp to last page."""
    token = _install_execution_context(str(test_repo))
    try:
        # Request page 100 when only 4 pages exist
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=100,
            page_size=10,
        )

        assert result["ok"] is True
        pagination = result["pagination"]
        # Should clamp to page 4
        assert pagination["page"] == 4
        assert pagination["total_pages"] == 4

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_validation(test_repo):
    """Test parameter validation for page and page_size."""
    token = _install_execution_context(str(test_repo))
    try:
        # Test page < 1 should clamp to 1
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=0,
            page_size=10,
        )
        assert result["pagination"]["page"] == 1

        # Test page_size < 1 should clamp to 1
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=1,
            page_size=0,
        )
        assert result["pagination"]["page_size"] == 1

        # Test page_size > 100 should clamp to 100
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=1,
            page_size=200,
        )
        assert result["pagination"]["page_size"] == 100

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_readable_format(test_repo):
    """Test pagination metadata appears in readable format."""
    token = _install_execution_context(str(test_repo))
    try:
        # Get readable format with pagination
        result = await search(
            agent="test_agent",
            pattern="test",
            format="readable",
            page=2,
            page_size=5,
        )

        # Result should contain pagination indicators
        content = str(result)
        assert "Page 2/" in content
        assert "Showing matches" in content

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_default_values(test_repo):
    """Test default pagination values (page=1, page_size=10)."""
    token = _install_execution_context(str(test_repo))
    try:
        # Don't specify page/page_size - should use defaults
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
        )

        assert result["ok"] is True
        pagination = result["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 10

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_preserves_file_grouping(test_repo):
    """Test that pagination preserves file information for matches."""
    token = _install_execution_context(str(test_repo))
    try:
        # Get page 1
        result = await search(
            agent="test_agent",
            pattern="test",
            format="structured",
            page=1,
            page_size=10,
        )

        assert result["ok"] is True

        # Each match should have a file association
        for file_block in result["matches"]:
            assert "file" in file_block
            assert len(file_block["file"]) > 0
            assert "matches" in file_block
            assert len(file_block["matches"]) > 0

            # Each match should have line_number and line
            for match in file_block["matches"]:
                assert "line_number" in match
                assert "line" in match

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_pagination_empty_results(test_repo):
    """Test pagination with empty results (no matches)."""
    token = _install_execution_context(str(test_repo))
    try:
        # Search for pattern that matches nothing
        result = await search(
            agent="test_agent",
            pattern="NONEXISTENT_PATTERN_12345",
            format="structured",
            page=1,
            page_size=10,
        )

        assert result["ok"] is True
        pagination = result["pagination"]
        assert pagination["page"] == 1
        assert pagination["page_size"] == 10
        assert pagination["total_matches"] == 0
        assert pagination["total_pages"] == 1  # Should show 1/1 even with 0 matches
        assert pagination["has_next"] is False
        assert pagination["has_prev"] is False

        # Verify empty matches array
        assert result["matches"] == []

    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_missing_search_path_returns_structured_not_found(test_repo):
    """Missing path should return a structured not_found error, not raise import errors."""
    token = _install_execution_context(str(test_repo))
    try:
        result = await search(
            agent="test_agent",
            pattern=".",
            path="src/council_mcp/agents/templates",
            format="structured",
        )

        assert result["ok"] is False
        assert result["error"] == "search path does not exist"
        assert result["error_type"] == "not_found"

    finally:
        server_module.router_context_manager.reset(token)
