#!/usr/bin/env python3
"""
Test suite for get_project SITREP enhancement (Phase 4.2).

Tests comprehensive status reporting including:
- State detection integration
- Recent entry display (NO truncation)
- Doc counts and modification flags
- Timestamp inclusion
- Readable format (compact box ~150-200 tokens)
- JSON format with pagination
"""

import pytest
import hashlib
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any, List
from pathlib import Path

from scribe_mcp.tools.get_project import (
    get_project,
    _compute_doc_status,
    _read_recent_progress_entries,
    _format_readable_sitrep
)


from test_get_project_integration import reader_environment


async def _seed_sitrep_entries(env, messages):
    for index, message in enumerate(messages):
        raw = f"[info] {message}"
        await env.storage.insert_entry(
            entry_id=f"sitrep-{index}", project=env.record,
            ts=datetime(2026, 1, 6, 12, index, tzinfo=timezone.utc),
            emoji="info", agent=env.agent, message=message, meta={},
            raw_line=raw, sha256=hashlib.sha256(raw.encode()).hexdigest(),
            log_type="progress",
        )


class TestGetProjectStateDetection:
    """Test state detection integration in get_project."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_get_project_includes_state_detection(self, reader_environment, monkeypatch):
        """SITREP detection receives the verified target and its actual entry count."""
        env = reader_environment
        await _seed_sitrep_entries(env, [f"Entry {i}" for i in range(15)])
        before = await env.snapshot()
        detect = Mock(return_value=("MODIFIED", "Modified: architecture (15 entries)"))
        monkeypatch.setattr("scribe_mcp.tools.get_project.detect_project_state", detect)
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        detect.assert_called_once()
        assert detect.call_args.args[0]["project_key"] == env.record.project_key
        assert detect.call_args.args[0]["root"] == str(env.root)
        assert detect.call_args.args[1] == 15
        assert result["state"] == "MODIFIED"
        assert result["sitrep_message"] == "Modified: architecture (15 entries)"
        assert result["entry_count"] == 15
        assert await env.snapshot() == before


class TestRecentEntriesDisplay:
    """Test recent entry display with NO truncation."""

    @pytest.mark.asyncio
    async def test_read_recent_progress_entries_no_truncation(self):
        """Verify _read_recent_progress_entries returns COMPLETE messages."""
        # Create temp progress log with long message
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            long_message = "This is a very long message " * 50  # ~1400 chars
            long_message = long_message.rstrip()  # Remove trailing space for exact match
            f.write(f"[ℹ️] [2026-01-06 12:00:00 UTC] [Agent: TestAgent] [Project: test] {long_message}\n")
            f.write(f"[✅] [2026-01-06 12:01:00 UTC] [Agent: TestAgent] [Project: test] Short message\n")
            temp_path = f.name

        try:
            # Read entries
            entries = await _read_recent_progress_entries(temp_path, limit=5)

            # Verify NO truncation
            assert len(entries) == 2
            assert entries[0]["message"] == long_message  # COMPLETE message
            assert entries[1]["message"] == "Short message"
            assert len(entries[0]["message"]) > 1000  # Verify it's actually long

        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_get_project_includes_recent_entries(self, reader_environment):
        """The real verified target supplies its recent entries without truncation."""
        env = reader_environment
        messages = ["Entry 1", "Entry 2", "Entry 3 " + "complete message " * 20]
        await _seed_sitrep_entries(env, messages)
        expected = await env.storage.fetch_recent_entries(
            project=env.record, limit=5,
            filters={"log_type": ["progress", "bugs", "bug", "security"]},
        )
        before = await env.snapshot()
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        assert result["project"]["project_key"] == env.record.project_key
        assert len(result["recent_entries"]) == 3
        assert [row["message"] for row in result["recent_entries"]] == [row["message"] for row in expected]
        assert {row["message"] for row in result["recent_entries"]} == set(messages)
        assert all({"emoji", "timestamp", "agent", "message"} <= row.keys() for row in result["recent_entries"])
        assert await env.snapshot() == before


class TestDocCountsAndList:
    """Test document counts and modification flags."""

    @pytest.mark.asyncio
    async def test_compute_doc_status_includes_counts(self):
        """Verify _compute_doc_status calculates doc counts correctly."""
        with patch('scribe_mcp.tools.get_project._PROJECT_REGISTRY') as mock_registry:
            # Mock project info
            mock_info = Mock()
            mock_info.meta = {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc",
                        "phase_plan": "def",
                        "checklist": "ghi",
                        "progress_log": "jkl",
                        "RESEARCH_FOO": "mno",
                        "RESEARCH_BAR": "pqr"
                    },
                    "flags": {
                        "architecture_modified": True,
                        "phase_plan_modified": False
                    }
                }
            }
            mock_registry.get_project.return_value = mock_info

            result = await _compute_doc_status("test_project")

            # Verify counts
            assert result["total_docs"] == 6
            assert result["base_docs"] == 4
            assert result["custom_docs"] == 2

    @pytest.mark.asyncio
    async def test_compute_doc_status_includes_modification_flags(self):
        """Verify _compute_doc_status includes ✏️/✓ flags in doc list."""
        with patch('scribe_mcp.tools.get_project._PROJECT_REGISTRY') as mock_registry:
            mock_info = Mock()
            mock_info.meta = {
                "docs": {
                    "baseline_hashes": {
                        "architecture": "abc",
                        "phase_plan": "def"
                    },
                    "flags": {
                        "architecture_modified": True,
                        "phase_plan_modified": False
                    }
                }
            }
            mock_registry.get_project.return_value = mock_info

            result = await _compute_doc_status("test_project")

            # Verify doc list with flags
            assert "doc_list" in result
            assert "✏️ architecture" in result["doc_list"]
            assert "✓ phase_plan" in result["doc_list"]


class TestTimestamps:
    """Test timestamp inclusion."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_get_project_includes_timestamps(self, reader_environment, monkeypatch):
        """Timestamp structure survives without borrowing label-only registry metadata."""
        env = reader_environment
        registry = Mock()
        registry.get_project.return_value = Mock(
            project_key="foreign-key", repo_root="/foreign",
            created_at=datetime(2025, 12, 15, tzinfo=timezone.utc),
            last_entry_at=datetime(2026, 1, 6, tzinfo=timezone.utc), meta={},
        )
        monkeypatch.setattr("scribe_mcp.tools.get_project._PROJECT_REGISTRY", registry)
        before = await env.snapshot()
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="structured")
        finally:
            env.router.reset(token)
        assert result["project"]["project_key"] == env.record.project_key
        assert isinstance(result["timestamps"], dict)
        assert {"created_at", "last_entry_at", "current_time"} <= result["timestamps"].keys()
        assert result["timestamps"]["created_at"] is None
        assert result["timestamps"]["last_entry_at"] is None
        assert datetime.fromisoformat(result["timestamps"]["current_time"]).tzinfo is not None
        assert await env.snapshot() == before


class TestReadableFormat:
    """Test readable format compact box display."""

    @pytest.mark.asyncio
    async def test_format_readable_sitrep_compact(self):
        """Verify _format_readable_sitrep produces compact output (~150-200 tokens)."""
        timestamps = {
            "created_at": "2025-12-15T14:23:00+00:00",
            "last_entry_at": "2026-01-06T13:41:00+00:00",
            "current_time": "2026-01-06T13:42:00+00:00"
        }

        doc_status = {
            "total_docs": 4,
            "base_docs": 4,
            "custom_docs": 0,
            "doc_list": ["✓ architecture", "✓ phase_plan", "✓ checklist", "✓ progress_log"]
        }

        recent_entries = [
            {"emoji": "✅", "message": "Implemented auth module"},
            {"emoji": "🐞", "message": "Found JWT bug"},
            {"emoji": "✅", "message": "All tests passing"}
        ]

        result = await _format_readable_sitrep(
            project_name="test_project",
            state="UNCHANGED",
            sitrep_message="📋 Project unchanged (47 entries)",
            entry_count=47,
            timestamps=timestamps,
            doc_status=doc_status,
            recent_entries=recent_entries
        )

        # Verify it's a box format
        assert "╔" in result
        assert "║" in result
        assert "╚" in result

        # Verify key content
        assert "test_project" in result
        assert "UNCHANGED" in result
        assert "47 total" in result
        assert "Created: 2025-12-15" in result
        assert "Last Entry: 2026-01-06" in result
        assert "Docs: 4 (4 base + 0 custom)" in result
        assert "✅" in result
        assert "Implemented auth module" in result

        # Verify compact (~150-200 tokens, but allow flexibility)
        token_estimate = len(result) / 4  # Rough token estimate
        assert 100 < token_estimate < 300, f"Token estimate {token_estimate} outside range"


class TestJSONFormat:
    """Test JSON format with pagination."""

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_get_project_json_format_includes_pagination(self, reader_environment):
        """JSON pagination describes real entries under current canonical authority."""
        env = reader_environment
        await _seed_sitrep_entries(env, [f"Entry {i}" for i in range(5)])
        before = await env.snapshot()
        token = env.router.set_current(env.context)
        try:
            result = await get_project(agent=env.agent, format="json")
        finally:
            env.router.reset(token)
        assert result["ok"] is True
        assert result["project"]["project_key"] == env.record.project_key
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["page_size"] == 5
        assert result["pagination"]["total_count"] == 5
        assert len(result["recent_entries"]) == 5
        assert await env.snapshot() == before


class TestInfrastructureReuse:
    """Test that existing helpers are properly reused."""

    def test_imports_detect_project_state(self):
        """Verify detect_project_state is imported from shared.project_utils."""
        from scribe_mcp.tools import get_project as gp_module
        assert hasattr(gp_module, 'detect_project_state')

    def test_uses_server_module_storage_backend(self):
        """Verify storage backend is accessed via server_module."""
        from scribe_mcp.tools import get_project as gp_module
        # Verify server_module is imported (which provides storage_backend)
        assert hasattr(gp_module, 'server_module')

    def test_uses_read_recent_progress_entries(self):
        """Verify _read_recent_progress_entries helper exists and is used."""
        from scribe_mcp.tools.get_project import _read_recent_progress_entries
        assert callable(_read_recent_progress_entries)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
