"""Tests for session-aware reminder hash generation."""

import pytest
from unittest.mock import patch, Mock
from scribe_mcp.utils.reminder_engine import ReminderEngine, ReminderContext
from scribe_mcp.config.settings import settings


class TestReminderHashSession:
    """Test session-aware hash generation with feature flag."""

    def test_hash_without_session_id(self):
        """Legacy format when session_id not provided."""
        engine = ReminderEngine()
        context = ReminderContext(
            tool_name="append_entry",
            project_name="test_project",
            project_root="/home/test",
            agent_id="test_agent",
            session_id=None,  # No session
            total_entries=10,
            minutes_since_log=5.0,
            last_log_time=None,
            docs_status={},
            docs_changed=[],
            current_phase=None,
            session_age_minutes=None
        )

        # Build variables to get the hash
        variables = engine._build_variables(context)

        # Should use legacy format (no session_id in hash)
        hash1 = engine._get_reminder_hash("test_reminder", variables)

        # Hash should be consistent
        hash2 = engine._get_reminder_hash("test_reminder", variables)
        assert hash1 == hash2

    def test_hash_with_session_id_flag_off(self):
        """Feature flag OFF = legacy format even with session_id provided."""
        # Create mock settings with flag OFF
        mock_settings = Mock()
        mock_settings.use_session_aware_hashes = False

        with patch('scribe_mcp.utils.reminder_engine.settings', mock_settings):
            engine = ReminderEngine()

            context = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_123",  # Provided but flag OFF
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            variables_with_session = engine._build_variables(context)
            hash_with_session = engine._get_reminder_hash("test_reminder", variables_with_session)

            # Create context without session_id
            context_no_session = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id=None,
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            variables_no_session = engine._build_variables(context_no_session)
            hash_no_session = engine._get_reminder_hash("test_reminder", variables_no_session)

            # Should produce same hash (legacy format ignores session_id)
            assert hash_with_session == hash_no_session

    def test_hash_with_session_id_flag_on(self):
        """Feature flag ON = new format with session_id in hash."""
        # Create mock settings with flag ON
        mock_settings = Mock()
        mock_settings.use_session_aware_hashes = True

        with patch('scribe_mcp.utils.reminder_engine.settings', mock_settings):
            engine = ReminderEngine()

            context_with_session = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_123",
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            context_no_session = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id=None,
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            variables_with = engine._build_variables(context_with_session)
            variables_without = engine._build_variables(context_no_session)

            hash_with = engine._get_reminder_hash("test_reminder", variables_with)
            hash_without = engine._get_reminder_hash("test_reminder", variables_without)

            # Different hashes (session-aware vs legacy)
            assert hash_with != hash_without

    def test_hash_different_sessions_different_hash(self):
        """Different session_ids produce different hashes."""
        # Create mock settings with flag ON
        mock_settings = Mock()
        mock_settings.use_session_aware_hashes = True

        with patch('scribe_mcp.utils.reminder_engine.settings', mock_settings):
            engine = ReminderEngine()

            context1 = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_123",
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            context2 = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_456",  # Different session
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            variables1 = engine._build_variables(context1)
            variables2 = engine._build_variables(context2)

            hash1 = engine._get_reminder_hash("test_reminder", variables1)
            hash2 = engine._get_reminder_hash("test_reminder", variables2)

            # Different sessions = different hashes
            assert hash1 != hash2

    def test_hash_same_session_same_hash(self):
        """Same session_id produces consistent hash."""
        # Create mock settings with flag ON
        mock_settings = Mock()
        mock_settings.use_session_aware_hashes = True

        with patch('scribe_mcp.utils.reminder_engine.settings', mock_settings):
            engine = ReminderEngine()

            context1 = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_123",
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            context2 = ReminderContext(
                tool_name="append_entry",
                project_name="test_project",
                project_root="/home/test",
                agent_id="test_agent",
                session_id="session_123",  # Same session
                total_entries=10,
                minutes_since_log=5.0,
                last_log_time=None,
                docs_status={},
                docs_changed=[],
                current_phase=None,
                session_age_minutes=None
            )

            variables1 = engine._build_variables(context1)
            variables2 = engine._build_variables(context2)

            hash1 = engine._get_reminder_hash("test_reminder", variables1)
            hash2 = engine._get_reminder_hash("test_reminder", variables2)

            # Same session = same hash (stable)
            assert hash1 == hash2
