"""Boundary-guard tests for the ``analyze_logs`` MCP tool (WS1 F3).

MCP tools must return error dictionaries, never raise raw exceptions to the host
(.claude/rules/error-handling.md). Prior to the F3 fix, ``analyze_logs`` was a bare
``return build_report_from_path(path, ...)`` whose inner builder calls
``Path(path).read_text(...)`` with no guard, so a missing/dir/unreadable path
propagated ``FileNotFoundError`` / ``IsADirectoryError`` / ``PermissionError`` straight
through the MCP boundary.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from scribe_mcp.tools.log_intelligence import analyze_logs


def _run(coro):
    return asyncio.run(coro)


def test_missing_path_returns_error_dict_not_raise():
    """A typo'd / non-existent path returns a teaching error dict, not a raise."""
    result = _run(analyze_logs(agent="test-agent", path="/nonexistent/typo_log.md"))
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert "typo_log.md" in result["error"]
    assert result["suggestion"]  # actionable remediation present


def test_directory_path_returns_error_dict(tmp_path: Path):
    """A directory (would raise IsADirectoryError downstream) returns an error dict."""
    result = _run(analyze_logs(agent="test-agent", path=str(tmp_path)))
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert str(tmp_path) in result["error"] or str(tmp_path) in result.get("path", "")


def test_empty_path_returns_error_dict():
    """An empty/blank path string is rejected at the boundary, not passed downstream."""
    result = _run(analyze_logs(agent="test-agent", path="   "))
    assert isinstance(result, dict)
    assert result["ok"] is False
    assert "non-empty string" in result["error"]


def test_valid_file_returns_report_payload_unchanged(tmp_path: Path):
    """A real readable log file still returns the normal builder report (no regression).

    The success path must NOT inject an ``ok`` key — it returns the same
    counts/signals/scope/timing payload as ``build_report_from_path`` so the CLI
    parity contract (test_cli_logs_analyze_entrypoint_matches_shared_builder_payload)
    stays intact.
    """
    log_file = tmp_path / "PROGRESS_LOG.md"
    log_file.write_text(
        "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] "
        'Complete task | priority=high; category=milestone; tags=["ship"]',
        encoding="utf-8",
    )
    result = _run(analyze_logs(agent="test-agent", path=str(log_file), project="Alpha"))
    assert isinstance(result, dict)
    assert "ok" not in result  # success path returns the raw report, not an envelope
    assert result["counts"]["entries_total"] == 1
    assert result["scope"]["project"] == "Alpha"
