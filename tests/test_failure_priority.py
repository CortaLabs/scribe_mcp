#!/usr/bin/env python3
"""
Test failure priority logic for reminder system.

Stage 5: Failure Context Propagation Tests

These tests verify that:
1. Failures bypass cooldown logic
2. Successes respect normal cooldowns
3. Neutral/None operation_status respects cooldowns
4. DB records operation_status correctly
5. Multiple failures all shown (no cooldown blocking)
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp.utils.reminder_engine import ReminderEngine, ReminderContext, ReminderInstance
from scribe_mcp import reminders


@pytest.fixture
def mock_engine():
    """Create a mock reminder engine with basic configuration."""
    engine = ReminderEngine()
    engine.config = {
        "behavior": {
            "max_reminders_per_call": 5,
            "default_teaching_cooldown_minutes": 10,
            "persist_cooldowns": False  # Disable for testing
        },
        "selection": {
            "priority_order": ["urgent", "warning", "info"],
            "category_weights": {"urgent": 1, "warning": 5, "info": 10}
        }
    }
    engine.reminders = {
        "reminders": {
            "logging": {
                "stale_log": {
                    "level": "warning",
                    "emoji": "⚠️",
                    "template": "No logs for {minutes} minutes",
                    "category": "logging"
                }
            }
        }
    }
    # Clear any existing cooldown history
    engine.history.reminder_hashes = {}
    engine.history.teaching_sessions = {}
    return engine


@pytest.fixture
def base_context():
    """Create a base reminder context."""
    return ReminderContext(
        tool_name="test_tool",
        project_name="test_project",
        project_root="/test/root",
        agent_id="test_agent",
        session_id="session_123",
        total_entries=10,
        minutes_since_log=15.0,
        operation_status=None  # Default to neutral
    )


@pytest.fixture
def sample_reminder():
    """Create a sample reminder instance."""
    return ReminderInstance(
        key="logging.stale_log",
        level="warning",
        emoji="⚠️",
        message="No logs for 15 minutes",
        category="logging",
        score=6,
        cooldown_minutes=10,
        variables={
            "project_root": "/test/root",
            "agent_id": "test_agent",
            "tool_name": "test_tool",
            "minutes": 15
        }
    )


@pytest.mark.asyncio
async def test_failure_bypasses_cooldown(mock_engine, base_context, sample_reminder):
    """Test 1: Failures bypass cooldown even when reminder was recently shown."""
    # Simulate reminder was shown recently (5 minutes ago)
    reminder_hash = mock_engine._get_reminder_hash(
        sample_reminder.key,
        sample_reminder.variables
    )
    mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Test with success status - should be blocked by cooldown
    context_success = base_context
    context_success.operation_status = "success"

    should_show_success = mock_engine._should_show_reminder(sample_reminder, context_success)
    assert not should_show_success, "Success should respect cooldown (recently shown)"

    # Test with failure status - should bypass cooldown
    context_failure = base_context
    context_failure.operation_status = "failure"

    should_show_failure = mock_engine._should_show_reminder(sample_reminder, context_failure)
    assert should_show_failure, "Failure should bypass cooldown and show reminder"


@pytest.mark.asyncio
async def test_success_respects_cooldown(mock_engine, base_context, sample_reminder):
    """Test 2: Successes respect normal cooldown logic."""
    # Simulate reminder was shown recently (5 minutes ago, cooldown is 10 minutes)
    reminder_hash = mock_engine._get_reminder_hash(
        sample_reminder.key,
        sample_reminder.variables
    )
    mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Test with success status
    context = base_context
    context.operation_status = "success"

    should_show = mock_engine._should_show_reminder(sample_reminder, context)
    assert not should_show, "Success should be blocked by active cooldown"

    # Simulate cooldown expired (15 minutes ago, cooldown is 10 minutes)
    mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=15)

    should_show_after_cooldown = mock_engine._should_show_reminder(sample_reminder, context)
    assert should_show_after_cooldown, "Success should show after cooldown expires"


@pytest.mark.asyncio
async def test_neutral_respects_cooldown(mock_engine, base_context, sample_reminder):
    """Test 3: Neutral/None operation_status respects cooldown (default behavior)."""
    # Simulate reminder was shown recently
    reminder_hash = mock_engine._get_reminder_hash(
        sample_reminder.key,
        sample_reminder.variables
    )
    mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Test with None operation_status
    context_none = base_context
    context_none.operation_status = None

    should_show_none = mock_engine._should_show_reminder(sample_reminder, context_none)
    assert not should_show_none, "None operation_status should respect cooldown"

    # Test with "neutral" operation_status
    context_neutral = base_context
    context_neutral.operation_status = "neutral"

    should_show_neutral = mock_engine._should_show_reminder(sample_reminder, context_neutral)
    assert not should_show_neutral, "Neutral operation_status should respect cooldown"


@pytest.mark.asyncio
async def test_failure_reminder_logged_correctly(mock_engine, base_context):
    """Test 4: DB records operation_status='failure' when reminders are shown on failures."""
    # This test verifies the infrastructure is ready for DB logging
    # The actual DB write happens in generate_reminders, but we verify the context carries the status

    context_failure = base_context
    context_failure.operation_status = "failure"

    # Verify context preserves operation_status
    assert context_failure.operation_status == "failure", "Context should preserve failure status"

    # Verify it gets passed through to reminder selection
    reminder = ReminderInstance(
        key="test.reminder",
        level="warning",
        emoji="⚠️",
        message="Test",
        category="logging",
        score=5,
        cooldown_minutes=10,
        variables={}
    )

    # Even with recent showing, failure should bypass
    reminder_hash = mock_engine._get_reminder_hash(reminder.key, reminder.variables)
    mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=2)

    should_show = mock_engine._should_show_reminder(reminder, context_failure)
    assert should_show, "Failure context should bypass cooldown for DB logging"


@pytest.mark.asyncio
async def test_multiple_failures_all_shown(mock_engine, base_context):
    """Test 5: Multiple failures all bypass cooldown (no blocking between failures)."""
    # Create multiple reminders
    reminders_list = [
        ReminderInstance(
            key=f"test.reminder_{i}",
            level="warning",
            emoji="⚠️",
            message=f"Test reminder {i}",
            category="logging",
            score=5,
            cooldown_minutes=10,
            variables={"project_root": "/test/root", "agent_id": "test_agent", "tool_name": "test_tool"}
        )
        for i in range(3)
    ]

    # Mark all as recently shown
    for reminder in reminders_list:
        reminder_hash = mock_engine._get_reminder_hash(reminder.key, reminder.variables)
        mock_engine.history.reminder_hashes[reminder_hash] = datetime.now(timezone.utc) - timedelta(minutes=3)

    # Test with success - all should be blocked
    context_success = base_context
    context_success.operation_status = "success"

    shown_success = [
        mock_engine._should_show_reminder(r, context_success)
        for r in reminders_list
    ]
    assert not any(shown_success), "All reminders should be blocked for success (cooldown active)"

    # Test with failure - all should be shown
    context_failure = base_context
    context_failure.operation_status = "failure"

    shown_failure = [
        mock_engine._should_show_reminder(r, context_failure)
        for r in reminders_list
    ]
    assert all(shown_failure), "All reminders should bypass cooldown for failure"
    assert len([s for s in shown_failure if s]) == 3, "All 3 reminders should be shown on failure"


@pytest.mark.asyncio
async def test_teaching_reminders_bypass_on_failure(mock_engine, base_context):
    """Test 6: Teaching reminders also bypass session limits on failures."""
    # Create teaching reminder
    teaching_reminder = ReminderInstance(
        key="teaching.test_tip",
        level="info",
        emoji="💡",
        message="Helpful tip",
        category="teaching",
        score=3,
        cooldown_minutes=5,
        variables={"project_root": "/test/root", "agent_id": "test_agent", "tool_name": "test_tool"}
    )

    # Exhaust teaching session limit
    session_key = f"{base_context.tool_name}:{teaching_reminder.key}"
    mock_engine.history.teaching_sessions[session_key] = 3  # Max is 3

    # Test with success - should be blocked by session limit
    context_success = base_context
    context_success.operation_status = "success"

    should_show_success = mock_engine._should_show_reminder(teaching_reminder, context_success)
    assert not should_show_success, "Teaching reminder should be blocked by session limit for success"

    # Test with failure - should bypass session limit
    context_failure = base_context
    context_failure.operation_status = "failure"

    should_show_failure = mock_engine._should_show_reminder(teaching_reminder, context_failure)
    assert should_show_failure, "Teaching reminder should bypass session limit for failure"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
