"""
Integration tests for query_entries database routing.

Tests verify that query_entries correctly routes to the storage backend
instead of using flat-file parsing when the backend is available.
"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime

from scribe_mcp.tools.query_entries import query_entries


def extract_result(result):
    """Extract dict from CallToolResult or return dict directly."""
    if hasattr(result, 'content'):
        # It's a CallToolResult - extract text and parse JSON
        for content_item in result.content:
            if hasattr(content_item, 'text'):
                text = content_item.text
                # For structured format, the text is JSON
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # For readable format, we can't easily parse - return indicator
                    return {"text_content": text, "format": "readable"}
        return {}
    else:
        # Already a dict
        return result


@pytest.mark.asyncio
async def test_query_entries_uses_database():
    """
    Test that query_entries uses storage_backend.query_entries_paginated
    when backend is available instead of flat-file parsing.
    """
    # Setup mock backend
    mock_backend = MagicMock()
    mock_backend.query_entries_paginated = AsyncMock(return_value=(
        [
            {
                "id": "entry1",
                "ts": "1234567890",
                "ts_iso": "2025-01-15T10:00:00Z",
                "emoji": "✅",
                "agent": "TestAgent",
                "message": "Test entry from database",
                "meta": {"phase": "test"},
                "raw_line": "✅ Test entry from database"
            }
        ],
        1  # total_count
    ))

    # Mock project record
    mock_project_record = MagicMock()
    mock_project_record.id = 1
    mock_project_record.name = "test_project"

    mock_backend.fetch_project = AsyncMock(return_value=mock_project_record)

    # Mock project context
    mock_project_context = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"
    }

    # Patch dependencies
    with patch('scribe_mcp.tools.query_entries.server_module') as mock_server:
        mock_server.storage_backend = mock_backend
        mock_server.state_manager.record_tool = AsyncMock(return_value={})

        with patch('scribe_mcp.tools.query_entries.resolve_logging_context') as mock_resolve:
            # Mock context object
            mock_context = Mock()
            mock_context.project = mock_project_context
            mock_context.recent_projects = []
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.query_entries.load_project_config') as mock_load:
                mock_load.return_value = mock_project_context

                # Execute query with structured format to get dict output
                result = await query_entries(
                    agent="TestAgent",
                    project="test_project",
                    message="database",
                    page=1,
                    page_size=50,
                    format="structured"
                )

    # Extract result dict
    result_dict = extract_result(result)

    # Verify database method was called
    mock_backend.fetch_project.assert_called_once_with("test_project")
    mock_backend.query_entries_paginated.assert_called_once()

    # Verify call parameters
    call_kwargs = mock_backend.query_entries_paginated.call_args[1]
    assert call_kwargs["project"] == mock_project_record
    assert call_kwargs["page"] == 1
    assert call_kwargs["page_size"] == 50
    assert call_kwargs["message"] == "database"

    # Verify result structure
    assert result_dict["ok"] is True
    assert result_dict["source"] == "database"
    assert len(result_dict["entries"]) == 1
    assert result_dict["entries"][0]["message"] == "Test entry from database"
    assert result_dict["total_found"] == 1


@pytest.mark.asyncio
async def test_query_entries_message_filter():
    """
    Test that message filters are correctly passed to the database backend.
    """
    # Setup mock backend with filtered results
    mock_backend = MagicMock()
    mock_backend.query_entries_paginated = AsyncMock(return_value=(
        [
            {
                "id": "entry1",
                "ts": "1234567890",
                "ts_iso": "2025-01-15T10:00:00Z",
                "emoji": "✅",
                "agent": "TestAgent",
                "message": "Filtered message",
                "meta": {},
                "raw_line": "✅ Filtered message"
            }
        ],
        1
    ))

    mock_project_record = MagicMock()
    mock_project_record.id = 1
    mock_project_record.name = "test_project"

    mock_backend.fetch_project = AsyncMock(return_value=mock_project_record)

    mock_project_context = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"
    }

    with patch('scribe_mcp.tools.query_entries.server_module') as mock_server:
        mock_server.storage_backend = mock_backend
        mock_server.state_manager.record_tool = AsyncMock(return_value={})

        with patch('scribe_mcp.tools.query_entries.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project_context
            mock_context.recent_projects = []
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.query_entries.load_project_config') as mock_load:
                mock_load.return_value = mock_project_context

                # Execute query with message filter
                result = await query_entries(
                    agent="TestAgent",
                    project="test_project",
                    message="Filtered",
                    message_mode="substring",
                    case_sensitive=False,
                    format="structured"
                )

    # Verify message filter was passed to backend
    call_kwargs = mock_backend.query_entries_paginated.call_args[1]
    assert call_kwargs["message"] == "Filtered"
    assert call_kwargs["message_mode"] == "substring"
    assert call_kwargs["case_sensitive"] is False

    # Extract and verify results
    result_dict = extract_result(result)
    assert result_dict["ok"] is True
    assert result_dict["source"] == "database"
    assert result_dict["entries"][0]["message"] == "Filtered message"


@pytest.mark.asyncio
async def test_query_entries_fallback_to_files():
    """
    Test that query_entries falls back to flat-file parsing when
    database query fails without crashing.
    """
    # Setup mock backend that raises exception
    mock_backend = MagicMock()
    mock_backend.query_entries_paginated = AsyncMock(
        side_effect=Exception("Database connection failed")
    )

    mock_project_record = MagicMock()
    mock_project_record.id = 1
    mock_project_record.name = "test_project"

    mock_backend.fetch_project = AsyncMock(return_value=mock_project_record)

    mock_project_context = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"
    }

    # Mock flat-file reading
    mock_log_lines = [
        '✅ 2025-01-15T10:00:00Z | TestAgent | Test entry from file | meta={}'
    ]

    with patch('scribe_mcp.tools.query_entries.server_module') as mock_server:
        mock_server.storage_backend = mock_backend
        mock_server.state_manager.record_tool = AsyncMock(return_value={})

        with patch('scribe_mcp.tools.query_entries.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project_context
            mock_context.recent_projects = []
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.query_entries.load_project_config') as mock_load:
                mock_load.return_value = mock_project_context

                with patch('scribe_mcp.tools.query_entries.read_all_lines') as mock_read:
                    mock_read.return_value = mock_log_lines

                    # Execute query - should fall back to flat-file
                    result = await query_entries(
                        agent="TestAgent",
                        project="test_project",
                        format="structured"
                    )

    # Verify database was attempted
    mock_backend.fetch_project.assert_called_once_with("test_project")
    mock_backend.query_entries_paginated.assert_called_once()

    # Verify fallback to flat-file reading
    mock_read.assert_called_once()

    # Extract and verify result structure (flat-file response)
    result_dict = extract_result(result)
    assert result_dict["ok"] is True
    # Flat-file response should NOT have "source": "database"
    assert result_dict.get("source") != "database"

    # Verify warning about DB failure
    assert any("Database query failed" in w for w in result_dict.get("validation_warnings", []))


@pytest.mark.asyncio
async def test_query_entries_returns_source_indicator():
    """
    Test that the response includes source='database' indicator
    when database routing succeeds.
    """
    mock_backend = MagicMock()
    mock_backend.query_entries_paginated = AsyncMock(return_value=(
        [
            {
                "id": "entry1",
                "ts": "1234567890",
                "ts_iso": "2025-01-15T10:00:00Z",
                "emoji": "ℹ️",
                "agent": "TestAgent",
                "message": "Source indicator test",
                "meta": {},
                "raw_line": "ℹ️ Source indicator test"
            }
        ],
        1
    ))

    mock_project_record = MagicMock()
    mock_project_record.id = 1
    mock_project_record.name = "test_project"

    mock_backend.fetch_project = AsyncMock(return_value=mock_project_record)

    mock_project_context = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"
    }

    with patch('scribe_mcp.tools.query_entries.server_module') as mock_server:
        mock_server.storage_backend = mock_backend
        mock_server.state_manager.record_tool = AsyncMock(return_value={})

        with patch('scribe_mcp.tools.query_entries.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project_context
            mock_context.recent_projects = []
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.query_entries.load_project_config') as mock_load:
                mock_load.return_value = mock_project_context

                result = await query_entries(
                    agent="TestAgent",
                    project="test_project",
                    format="structured"
                )

    # Extract and verify source indicator
    result_dict = extract_result(result)
    assert "source" in result_dict
    assert result_dict["source"] == "database"

    # Verify other DB-specific response fields
    assert "pagination" in result_dict
    assert result_dict["pagination"]["page"] == 1
    assert result_dict["pagination"]["total_count"] == 1
    assert result_dict["total_found"] == 1
    assert result_dict["returned"] == 1


@pytest.mark.asyncio
async def test_query_entries_backend_missing():
    """
    Test that query_entries falls back to flat-file when backend is None.
    """
    mock_project_context = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/root/.scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"
    }

    mock_log_lines = [
        '✅ 2025-01-15T10:00:00Z | TestAgent | Test entry | meta={}'
    ]

    with patch('scribe_mcp.tools.query_entries.server_module') as mock_server:
        # Backend is None
        mock_server.storage_backend = None
        mock_server.state_manager.record_tool = AsyncMock(return_value={})

        with patch('scribe_mcp.tools.query_entries.resolve_logging_context') as mock_resolve:
            mock_context = Mock()
            mock_context.project = mock_project_context
            mock_context.recent_projects = []
            mock_context.reminders = []
            mock_resolve.return_value = mock_context

            with patch('scribe_mcp.tools.query_entries.load_project_config') as mock_load:
                mock_load.return_value = mock_project_context

                with patch('scribe_mcp.tools.query_entries.read_all_lines') as mock_read:
                    mock_read.return_value = mock_log_lines

                    result = await query_entries(
                        agent="TestAgent",
                        project="test_project",
                        format="structured"
                    )

    # Verify flat-file was used
    mock_read.assert_called_once()

    # Extract and verify no "database" source indicator
    result_dict = extract_result(result)
    assert result_dict.get("source") != "database"
    assert result_dict["ok"] is True
