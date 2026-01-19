#!/usr/bin/env python3
"""Integration tests for Stage 4: Session Integration.

Tests session_id propagation through execution context to ReminderContext
and validates graceful fallback when session_id is unavailable.
"""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock
from scribe_mcp.reminders import _build_legacy_context
from scribe_mcp.utils.reminder_engine import ReminderContext


@pytest.mark.asyncio
async def test_session_id_extracted_from_state():
    """Test that session_id is extracted from state and passed to ReminderContext."""
    # Arrange
    project = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/progress.log"
    }

    # Create mock state with session_id
    mock_state = MagicMock()
    mock_state.session_id = "test-session-123"

    # Act
    context = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=mock_state,
        agent_id="test-agent"
    )

    # Assert
    assert isinstance(context, ReminderContext)
    assert context.session_id == "test-session-123"
    assert context.tool_name == "test_tool"
    assert context.project_name == "test_project"
    assert context.agent_id == "test-agent"


@pytest.mark.asyncio
async def test_graceful_fallback_no_session_id():
    """Test that system works gracefully when session_id is not available."""
    # Arrange
    project = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/progress.log"
    }

    # Create mock state WITHOUT session_id
    mock_state = MagicMock()
    # Explicitly delete session_id attribute to simulate missing field
    if hasattr(mock_state, 'session_id'):
        delattr(mock_state, 'session_id')

    # Act
    context = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=mock_state,
        agent_id="test-agent"
    )

    # Assert
    assert isinstance(context, ReminderContext)
    assert context.session_id is None  # Should default to None
    assert context.tool_name == "test_tool"
    assert context.project_name == "test_project"


@pytest.mark.asyncio
async def test_graceful_fallback_no_state():
    """Test that system works when state is None."""
    # Arrange
    project = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/progress.log"
    }

    # Act - No state provided
    context = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=None,
        agent_id="test-agent"
    )

    # Assert
    assert isinstance(context, ReminderContext)
    assert context.session_id is None
    assert context.session_age_minutes is None
    assert context.tool_name == "test_tool"


@pytest.mark.asyncio
async def test_different_sessions_different_contexts():
    """Test that different session_ids create different reminder contexts."""
    # Arrange
    project = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/progress.log"
    }

    # Create two states with different session_ids
    mock_state_1 = MagicMock()
    mock_state_1.session_id = "session-alpha"

    mock_state_2 = MagicMock()
    mock_state_2.session_id = "session-beta"

    # Act
    context_1 = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=mock_state_1,
        agent_id="test-agent"
    )

    context_2 = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=mock_state_2,
        agent_id="test-agent"
    )

    # Assert
    assert context_1.session_id == "session-alpha"
    assert context_2.session_id == "session-beta"
    assert context_1.session_id != context_2.session_id
    # All other fields should be identical
    assert context_1.project_name == context_2.project_name
    assert context_1.tool_name == context_2.tool_name
    assert context_1.agent_id == context_2.agent_id


@pytest.mark.asyncio
async def test_session_id_with_other_state_fields():
    """Test that session_id extraction works alongside other state fields."""
    # Arrange
    project = {
        "name": "test_project",
        "root": "/test/root",
        "progress_log": "/test/progress.log"
    }

    # Create mock state with multiple fields including session_id
    mock_state = MagicMock()
    mock_state.session_id = "complex-session-456"
    mock_state.session_started_at = "2026-01-03T18:00:00+00:00"
    mock_state.projects = {}

    # Act
    context = await _build_legacy_context(
        project=project,
        tool_name="test_tool",
        state=mock_state,
        agent_id="test-agent"
    )

    # Assert
    assert context.session_id == "complex-session-456"
    # Verify other state fields were also processed
    assert context.session_age_minutes is not None  # Should be calculated
    assert context.session_age_minutes >= 0


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])
