#!/usr/bin/env python3
"""
Tests for utils/tool_logger.py - Tool logging without recursion.

CRITICAL: These tests verify that tool_logger.py has ZERO imports
of append_entry or response.py, preventing infinite recursion.
"""

import json
from unittest.mock import patch, mock_open
from pathlib import Path

import pytest
from scribe_mcp.utils.tool_logger import (
    get_tool_log_path,
    log_tool_call,
    _append_jsonl_line,
    _verify_no_recursion_imports,
)


class TestRecursionPrevention:
    """Test suite verifying zero recursion guarantee.

    NOTE: These tests document the import isolation challenge.
    When running via pytest, the test environment imports the entire
    scribe_mcp package hierarchy, which transitively loads response.py.

    The REAL test is: running utils/tool_logger.py directly (see __main__).
    That test proves tool_logger.py itself has NO forbidden imports.

    These pytest tests verify the MODULE STRUCTURE is correct, not the
    runtime import state (which pytest pollutes).
    """

    def test_no_forbidden_imports_runtime(self):
        """Runtime verification that tool_logger functions don't cause recursion."""
        import subprocess
        import sys
        from pathlib import Path

        # Get path to MCP_SPINE root
        mcp_spine_root = str(Path(__file__).parent.parent)

        # CRITICAL TEST: Verify log_tool_call() can execute without recursion
        # The real test is: can we CALL log_tool_call() without triggering
        # append_entry or response.finalize_tool_response?
        #
        # Note: Importing tool_logger will load utils/__init__.py which imports
        # response.py due to Python package structure. This is unavoidable and OK.
        # What matters is that CALLING log_tool_call() doesn't trigger those modules.

        test_code = """
import sys
import tempfile
from pathlib import Path

# Track which modules get imported AFTER we're done with initial imports
import scribe_mcp.utils.tool_logger as tool_logger

# Record modules loaded before calling log_tool_call
before = set(sys.modules.keys())

# Call log_tool_call() - this should NOT trigger append_entry
# Use a temp file so we don't pollute the actual log
with tempfile.TemporaryDirectory() as tmpdir:
    test_log = Path(tmpdir) / "test.jsonl"

    # Mock get_tool_log_path to use temp file
    original_get_path = tool_logger.get_tool_log_path
    tool_logger.get_tool_log_path = lambda: test_log

    # CRITICAL: Call the function
    tool_logger.log_tool_call(
        tool_name="test_tool",
        session_id="test_session",
        status="success"
    )

    # Restore
    tool_logger.get_tool_log_path = original_get_path

# Check which NEW modules were loaded during the function call
after = set(sys.modules.keys())
new_modules = after - before

# FORBIDDEN: These modules should NOT be loaded by calling log_tool_call()
forbidden_new = [
    'scribe_mcp.tools.append_entry',
    # Note: response.py is already loaded by utils/__init__.py, so we can't check it here
]

violations = [m for m in forbidden_new if m in new_modules]

if violations:
    print(f"RECURSION RISK: {violations}")
    print(f"log_tool_call() triggered forbidden imports!")
    exit(1)
else:
    print("SAFE: log_tool_call() executed without recursion")
    exit(0)
"""

        result = subprocess.run(
            [sys.executable, "-c", test_code],
            env={"PYTHONPATH": mcp_spine_root},
            capture_output=True,
            text=True,
            timeout=5
        )

        assert result.returncode == 0, (
            f"log_tool_call() triggered forbidden imports (recursion risk)!\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}"
        )
        assert "SAFE" in result.stdout, (
            f"Runtime execution check failed: {result.stdout}"
        )

    def test_module_has_minimal_imports(self):
        """Verify tool_logger.py source code has minimal imports."""
        import inspect
        import scribe_mcp.utils.tool_logger as tool_logger_module

        source = inspect.getsource(tool_logger_module)

        # Check for forbidden import statements in source code
        forbidden_imports = [
            "from scribe_mcp.tools.append_entry",
            "import scribe_mcp.tools.append_entry",
            "from scribe_mcp.utils.response",
            "import scribe_mcp.utils.response",
            "from scribe_mcp.utils.files",  # Would load utils/__init__.py
            "from scribe_mcp.server",
            "from scribe_mcp.shared",
        ]

        for forbidden in forbidden_imports:
            assert forbidden not in source, (
                f"FORBIDDEN IMPORT FOUND: {forbidden}\n"
                f"This will cause circular dependencies!"
            )

        # Verify only allowed imports
        assert "from scribe_mcp.config.settings import settings" in source

    def test_verification_function_exists(self):
        """Test that _verify_no_recursion_imports() function exists."""
        # Just check the function exists and is callable
        assert callable(_verify_no_recursion_imports)

    def test_module_structure_isolated(self):
        """Verify tool_logger module structure prevents recursion."""
        import scribe_mcp.utils.tool_logger as tool_logger_module

        # Check that module has the expected public API
        assert hasattr(tool_logger_module, 'log_tool_call')
        assert hasattr(tool_logger_module, 'get_tool_log_path')
        assert hasattr(tool_logger_module, '_append_jsonl_line')

        # Check module does NOT have append_entry or response references
        assert not hasattr(tool_logger_module, 'append_entry')
        assert not hasattr(tool_logger_module, 'finalize_tool_response')
        assert not hasattr(tool_logger_module, 'ResponseFormatter')


class TestToolLogPath:
    """Test get_tool_log_path() function."""

    def test_returns_path_object(self):
        """Verify get_tool_log_path returns a Path object."""
        result = get_tool_log_path()
        assert isinstance(result, Path)

    def test_correct_log_path(self):
        """Verify the log path is .scribe/logs/TOOL_LOG.jsonl."""
        result = get_tool_log_path()
        assert result.name == "TOOL_LOG.jsonl"
        assert result.parent.name == "logs"
        assert result.parent.parent.name == ".scribe"

    def test_custom_repo_root_sentinel_mode(self, tmp_path):
        """Verify get_tool_log_path uses repo-level logs when no progress_log_path (sentinel mode)."""
        result = get_tool_log_path(repo_root=tmp_path)
        assert result == tmp_path / ".scribe" / "logs" / "TOOL_LOG.jsonl"
        assert result.name == "TOOL_LOG.jsonl"
        assert result.parent.name == "logs"
        assert result.parent.parent.name == ".scribe"

    def test_progress_log_path_takes_precedence(self, tmp_path):
        """Verify get_tool_log_path uses progress_log_path directory (ensures correct slugification)."""
        # progress_log_path directory is used regardless of project_name
        progress_log = str(tmp_path / ".scribe" / "docs" / "dev_plans" / "disk_sync" / "PROGRESS_LOG.md")
        result = get_tool_log_path(progress_log_path=progress_log)
        expected = tmp_path / ".scribe" / "docs" / "dev_plans" / "disk_sync" / "TOOL_LOG.jsonl"
        assert result == expected
        assert result.name == "TOOL_LOG.jsonl"
        assert result.parent.name == "disk_sync"  # Uses slugified name from path, not project_name

    def test_progress_log_path_ignores_project_name(self, tmp_path):
        """Verify project_name is ignored when progress_log_path is provided."""
        # Even if project_name has hyphens, the path comes from progress_log_path
        progress_log = str(tmp_path / "disk_sync" / "PROGRESS_LOG.md")
        result = get_tool_log_path(
            project_name="disk-sync",  # Has hyphen, but should be ignored
            progress_log_path=progress_log
        )
        expected = tmp_path / "disk_sync" / "TOOL_LOG.jsonl"
        assert result == expected

    def test_no_progress_log_uses_fallback(self):
        """Verify falls back to SCRIBE_ROOT logs when no progress_log_path."""
        from scribe_mcp.config.settings import settings
        # Without progress_log_path, should fall back to repo-level logs
        result = get_tool_log_path(project_name="my_project")  # project_name alone doesn't create per-project path
        expected = settings.project_root / ".scribe" / "logs" / "TOOL_LOG.jsonl"
        assert result == expected

    def test_none_repo_root_uses_default(self):
        """Verify get_tool_log_path uses default when repo_root is None."""
        from scribe_mcp.config.settings import settings
        result = get_tool_log_path(repo_root=None)
        expected = settings.project_root / ".scribe" / "logs" / "TOOL_LOG.jsonl"
        assert result == expected


class TestAppendJsonlLine:
    """Test _append_jsonl_line() minimal JSONL writer."""

    def test_creates_parent_directory(self, tmp_path):
        """Verify parent directory is created if missing."""
        test_file = tmp_path / "nested" / "dir" / "test.jsonl"

        _append_jsonl_line(test_file, '{"test": "data"}')

        assert test_file.exists()
        assert test_file.parent.exists()

    def test_appends_with_newline(self, tmp_path):
        """Verify lines are appended with newlines."""
        test_file = tmp_path / "test.jsonl"

        _append_jsonl_line(test_file, '{"line": 1}')
        _append_jsonl_line(test_file, '{"line": 2}')

        content = test_file.read_text()
        lines = content.strip().split('\n')

        assert len(lines) == 2
        assert json.loads(lines[0]) == {"line": 1}
        assert json.loads(lines[1]) == {"line": 2}

    def test_adds_newline_if_missing(self, tmp_path):
        """Verify newline is added if not present in input."""
        test_file = tmp_path / "test.jsonl"

        _append_jsonl_line(test_file, '{"test": "data"}')  # No newline

        content = test_file.read_text()
        assert content.endswith('\n')


class TestLogToolCall:
    """Test log_tool_call() main function."""

    def test_minimal_call(self, tmp_path, monkeypatch):
        """Test log_tool_call with minimal required parameters."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        # Mock get_tool_log_path to use temp file (accepts optional repo_root)
        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        log_tool_call(
            tool_name="test_tool",
            session_id="session_123"
        )

        assert test_log.exists()
        content = test_log.read_text()
        entry = json.loads(content)

        assert entry["tool_name"] == "test_tool"
        assert entry["session_id"] == "session_123"
        assert entry["status"] == "success"  # Default
        assert "timestamp" in entry

    def test_all_optional_parameters(self, tmp_path, monkeypatch):
        """Test log_tool_call with all optional parameters."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        log_tool_call(
            tool_name="test_tool",
            session_id="session_123",
            duration_ms=45.2,
            status="error",
            format_requested="readable",
            project_name="test_project",
            agent_id="TestAgent",
            error_message="Test error",
            response_size_bytes=1024
        )

        content = test_log.read_text()
        entry = json.loads(content)

        assert entry["tool_name"] == "test_tool"
        assert entry["session_id"] == "session_123"
        assert entry["duration_ms"] == 45.2
        assert entry["status"] == "error"
        assert entry["format_requested"] == "readable"
        assert entry["project_name"] == "test_project"
        assert entry["agent_id"] == "TestAgent"
        assert entry["error_message"] == "Test error"
        assert entry["response_size_bytes"] == 1024

    def test_repo_root_parameter(self, tmp_path, monkeypatch):
        """Test that repo_root parameter is passed to get_tool_log_path and included in entry."""
        test_log = tmp_path / "TOOL_LOG.jsonl"
        captured_args = []

        # Mock get_tool_log_path to capture the args and use temp file
        def mock_get_tool_log_path(repo_root=None, project_name=None, progress_log_path=None):
            captured_args.append((repo_root, project_name, progress_log_path))
            return test_log

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            mock_get_tool_log_path
        )

        # Call with repo_root and project_name
        log_tool_call(
            tool_name="test_tool",
            session_id="session_123",
            repo_root="/some/repo/path",
            project_name="my_project"
        )

        # Verify args were passed to get_tool_log_path
        assert len(captured_args) == 1
        assert str(captured_args[0][0]) == "/some/repo/path"
        assert captured_args[0][1] == "my_project"

        # Verify repo_root is in the logged entry
        content = test_log.read_text()
        entry = json.loads(content)
        assert entry["repo_root"] == "/some/repo/path"
        assert entry["project_name"] == "my_project"

    def test_progress_log_path_parameter(self, tmp_path, monkeypatch):
        """Test that progress_log_path is passed to get_tool_log_path for correct slugification."""
        test_log = tmp_path / "TOOL_LOG.jsonl"
        captured_args = []

        # Mock get_tool_log_path to capture the args
        def mock_get_tool_log_path(repo_root=None, project_name=None, progress_log_path=None):
            captured_args.append((repo_root, project_name, progress_log_path))
            return test_log

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            mock_get_tool_log_path
        )

        # Call with progress_log_path
        log_tool_call(
            tool_name="test_tool",
            session_id="session_123",
            project_name="disk-sync",
            progress_log_path="/repo/.scribe/docs/dev_plans/disk_sync/PROGRESS_LOG.md"
        )

        # Verify progress_log_path was passed to get_tool_log_path
        assert len(captured_args) == 1
        assert captured_args[0][2] == "/repo/.scribe/docs/dev_plans/disk_sync/PROGRESS_LOG.md"

    def test_repo_root_none_not_in_entry(self, tmp_path, monkeypatch):
        """Test that repo_root is not in entry when None."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        # Call without repo_root
        log_tool_call(
            tool_name="test_tool",
            session_id="session_123"
        )

        # Verify repo_root is NOT in the logged entry
        content = test_log.read_text()
        entry = json.loads(content)
        assert "repo_root" not in entry

    def test_graceful_error_handling(self, monkeypatch, caplog):
        """Test that errors are logged via logging but don't raise."""
        import logging
        # Make get_tool_log_path raise an error (accepts optional params)
        def mock_error(repo_root=None, project_name=None, progress_log_path=None):
            raise RuntimeError("Simulated error")

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            mock_error
        )

        # Should not raise, just log via logger.warning
        with caplog.at_level(logging.WARNING, logger="scribe_mcp.utils.tool_logger"):
            log_tool_call(
                tool_name="test_tool",
                session_id="session_123"
            )

        # Check logger captured the warning
        assert "Failed to write tool log to JSONL" in caplog.text
        assert "Simulated error" in caplog.text

    def test_valid_json_format(self, tmp_path, monkeypatch):
        """Test that logged entries are valid JSON."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        log_tool_call(
            tool_name="test_tool",
            session_id="session_123",
            project_name="test_project"
        )

        content = test_log.read_text()

        # Should not raise json.JSONDecodeError
        entry = json.loads(content)
        assert isinstance(entry, dict)

    def test_multiple_calls_append(self, tmp_path, monkeypatch):
        """Test that multiple calls append to the same file."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        log_tool_call(tool_name="tool1", session_id="session_1")
        log_tool_call(tool_name="tool2", session_id="session_2")
        log_tool_call(tool_name="tool3", session_id="session_3")

        content = test_log.read_text()
        lines = content.strip().split('\n')

        assert len(lines) == 3
        assert json.loads(lines[0])["tool_name"] == "tool1"
        assert json.loads(lines[1])["tool_name"] == "tool2"
        assert json.loads(lines[2])["tool_name"] == "tool3"


class TestTimestampFormat:
    """Test timestamp formatting in log entries."""

    def test_timestamp_is_utc_iso_format(self, tmp_path, monkeypatch):
        """Verify timestamp is in UTC ISO format."""
        test_log = tmp_path / "TOOL_LOG.jsonl"

        monkeypatch.setattr(
            'scribe_mcp.utils.tool_logger.get_tool_log_path',
            lambda repo_root=None, project_name=None, progress_log_path=None: test_log
        )

        log_tool_call(tool_name="test_tool", session_id="session_123")

        content = test_log.read_text()
        entry = json.loads(content)

        # Timestamp should be ISO format with timezone
        timestamp = entry["timestamp"]
        assert "T" in timestamp
        assert timestamp.endswith("Z") or "+" in timestamp or "-" in timestamp.split("T")[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
