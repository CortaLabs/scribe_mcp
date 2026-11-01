#!/usr/bin/env python3
"""
Test priority/category parameters for append_entry tool.

Tests the new priority, category, tags, and confidence parameters added
as part of scribe_tool_output_refinement project.
"""

import pytest
import pytest_asyncio
import json
from scribe_mcp import server as server_module
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.shared.logging_utils import ProjectResolutionError
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.config.settings import settings
from scribe_mcp.shared.log_enums import LogPriority, LogCategory


@pytest_asyncio.fixture(loop_scope="module")
async def test_project():
    """Bind a DB-backed project for the suite.

    append_entry resolves project context through the database/session path, so
    a project must be established via set_project first. The legacy state.json
    global-project default no longer satisfies this. The module-scoped loop keeps
    the loop-bound context binding valid across every test in this suite, matching
    the convention in test_query_priority_filters.py.
    """
    project_name = "test_append_entry_priority"
    await set_project(
        agent="test_agent",
        name=project_name,
        root=str(settings.project_root),
    )
    return project_name


def get_result_dict(result):
    """Extract dict from CallToolResult or return dict directly."""
    try:
        from mcp.types import CallToolResult, TextContent
        if isinstance(result, CallToolResult):
            # For structured format, parse the text content as JSON
            if len(result.content) == 1 and isinstance(result.content[0], TextContent):
                text = result.content[0].text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Return a dict with the text as a message
                    return {"ok": True, "text": text}
            return {"ok": True}
    except ImportError:
        pass

    # Already a dict
    if isinstance(result, dict):
        return result

    return {"ok": True}


@pytest.mark.asyncio(loop_scope="module")
async def test_explicit_priority(test_project):
    """Test explicit priority parameter."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Critical security issue detected",
        priority="critical",
        category="security",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Verify priority was set in metadata
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "critical"


@pytest.mark.asyncio(loop_scope="module")
async def test_priority_from_status(test_project):
    """Test priority auto-inference from status."""
    # Bug status should infer high priority
    raw_result = await append_entry(
        agent="test_agent",
        message="Bug found in authentication module",
        status="bug",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Priority should be auto-inferred as 'high' from bug status
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "high"


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_priority_defaults(test_project):
    """Test invalid priority defaults to medium."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Test message with invalid priority",
        priority="invalid_priority_value",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should default to medium for invalid priority
    assert "priority" in result.get("meta", {})
    assert result["meta"]["priority"] == "medium"


@pytest.mark.asyncio(loop_scope="module")
async def test_category_validation(test_project):
    """Test category validation."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Implemented new authentication flow",
        category="implementation",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert "category" in result.get("meta", {})
    assert result["meta"]["category"] == "implementation"


@pytest.mark.asyncio(loop_scope="module")
async def test_invalid_category(test_project):
    """Test invalid category is rejected."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Test message",
        category="invalid_category",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Invalid category should be None (not stored)
    meta = result.get("meta", {})
    # Either not present or None
    assert meta.get("category") is None


@pytest.mark.asyncio(loop_scope="module")
async def test_tags_and_confidence(test_project):
    """Test tags and confidence parameters."""
    raw_result = await append_entry(
        agent="test_agent",
        message="Refactored authentication module for better performance",
        tags=["refactor", "performance", "auth"],
        confidence=0.85,
        category="implementation",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert "tags" in result.get("meta", {})
    assert "confidence" in result.get("meta", {})
    assert result["meta"]["confidence"] == 0.85


@pytest.mark.asyncio(loop_scope="module")
async def test_bulk_mode_with_priority(test_project):
    """Test bulk mode with per-item priority."""
    items = [
        {
            "message": "Critical bug in payment processing",
            "priority": "critical",
            "category": "bug",
            "confidence": 0.95
        },
        {
            "message": "Minor documentation update",
            "priority": "low",
            "category": "documentation",
            "confidence": 1.0
        },
    ]
    raw_result = await append_entry(agent="test_agent", items_list=items, format="structured")
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    assert result.get("processed", 0) == 2
    assert result.get("successful", 0) == 2


@pytest.mark.asyncio(loop_scope="module")
async def test_confidence_validation(test_project):
    """Test confidence range validation (F6 clamp-toward-truth contract)."""
    # Out-of-range values clamp into [0.0, 1.0] rather than defaulting to MAX.
    raw_result = await append_entry(
        agent="test_agent",
        message="Test confidence validation",
        confidence=1.5,  # Above range -> clamps to ceiling 1.0
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # F6: above-range value clamps to the ceiling 1.0.
    assert result.get("meta", {}).get("confidence") == 1.0

    # F6 heals toward truth, not toward MAX: a negative value clamps to the
    # floor 0.0 (NOT silently promoted to 1.0, which was the prior bug).
    raw_result2 = await append_entry(
        agent="test_agent",
        message="Test negative confidence",
        confidence=-0.5,  # Out of range
        format="structured"
    )
    result2 = get_result_dict(raw_result2)
    assert result2["ok"] is True
    assert result2.get("meta", {}).get("confidence") == 0.0


@pytest.mark.asyncio(loop_scope="module")
async def test_all_priority_levels(test_project):
    """Test all valid priority levels."""
    priorities = ["critical", "high", "medium", "low"]

    for priority in priorities:
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test message with {priority} priority",
            priority=priority,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == priority


@pytest.mark.asyncio(loop_scope="module")
async def test_all_categories(test_project):
    """Test all valid categories."""
    categories = [
        "decision", "investigation", "bug", "implementation",
        "test", "milestone", "config", "security",
        "performance", "documentation"
    ]

    for category in categories:
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test message with {category} category",
            category=category,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("category") == category


@pytest.mark.asyncio(loop_scope="module")
async def test_priority_status_mapping(test_project):
    """Test priority auto-inference from different status values."""
    status_priority_map = {
        "error": "high",
        "bug": "high",
        "warn": "medium",
        "success": "medium",
        "info": "low",
        "plan": "medium"
    }

    for status, expected_priority in status_priority_map.items():
        raw_result = await append_entry(
            agent="test_agent",
            message=f"Test {status} status",
            status=status,
            format="structured"
        )
        result = get_result_dict(raw_result)
        assert result["ok"] is True
        assert result.get("meta", {}).get("priority") == expected_priority


@pytest.mark.asyncio(loop_scope="module")
async def test_backward_compatibility(test_project):
    """Test that existing code still works without new parameters."""
    # Old-style call without any new parameters
    raw_result = await append_entry(
        agent="test_agent",
        message="Test backward compatibility",
        status="success",
        format="structured"
    )
    result = get_result_dict(raw_result)
    assert result["ok"] is True
    # Should have auto-inferred priority from status
    assert "priority" in result.get("meta", {})


@pytest_asyncio.fixture
async def append_retry_project(tmp_path, monkeypatch, test_agent):
    """Real standalone storage, with every mutable artifact in tmp_path."""
    storage = SQLiteStorage(tmp_path / "retry.db")
    await storage.setup()
    log_path = tmp_path / "PROGRESS_LOG.md"
    log_path.write_text("existing trail\n", encoding="utf-8")
    project = await storage.upsert_project(
        name="append_retry_project",
        repo_root=str(tmp_path),
        progress_log_path=str(log_path),
    )
    monkeypatch.setattr(server_module, "storage_backend", storage)
    monkeypatch.setattr(
        server_module, "state_manager",
        StateManager(tmp_path / "state.json", storage_backend=storage),
    )
    monkeypatch.setattr(server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(server_module, "get_agent_identity", lambda: None)
    # This is the standalone explicit-project path, not a simulated fleet bind.
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "internal")
    try:
        context = await append_entry_module.resolve_logging_context(
            tool_name="append_entry", server_module=server_module,
            agent_id=test_agent, explicit_project=project.name,
            require_project=True, state_snapshot={},
        )
        assert context.project["root"] == str(tmp_path)
        assert context.resolution_source == "explicit_project"
        yield project, storage, log_path
    finally:
        await storage.close()


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.asyncio
@pytest.mark.parametrize("retry_project_exists", [True, False], ids=["real-retry", "missing-project"])
async def test_append_retry_resolution_returns_clean_refusal_without_write(
    append_retry_project, monkeypatch, test_agent, retry_project_exists,
):
    """A controlled first failure must never turn into an uninitialized local.

    The existing healer rewrites the oversized identity. This does not grant
    permission to write as that identity: a clean refusal is the safe oracle
    until the identity trust decision is made separately.
    """
    project, storage, log_path = append_retry_project
    explicit_project = project.name if retry_project_exists else "missing_retry_project"
    oversized_identity = (test_agent + "-" * 1100)[:1100]
    real_resolve = append_entry_module.resolve_logging_context
    calls = []
    resolved = []
    retry_errors = []

    async def fail_first_resolution(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ProjectResolutionError("controlled first resolution failure")
        try:
            context = await real_resolve(**kwargs)
        except ProjectResolutionError as exc:
            retry_errors.append(str(exc))
            raise
        resolved.append(context)
        return context

    before_log = log_path.read_bytes()
    before_count = await storage.count_entries(project=project)
    monkeypatch.setattr(append_entry_module, "resolve_logging_context", fail_first_resolution)
    result = await append_entry(
        agent=test_agent, agent_id=oversized_identity, project=explicit_project,
        message="controlled retry regression", format="structured",
    )
    assert isinstance(result, dict), result
    assert len(calls) == 2, (calls, result)
    assert calls[0]["agent_id"] == oversized_identity
    assert calls[1]["agent_id"] != oversized_identity  # observed healing, not authorization
    assert all(call["explicit_project"] == explicit_project for call in calls)
    assert all(call["require_project"] is True for call in calls)
    if retry_project_exists:
        assert not retry_errors, retry_errors
        assert len(resolved) == 1
        assert resolved[0].project["name"] == project.name
        assert resolved[0].resolution_source == "explicit_project"
    else:
        assert not resolved
        assert len(retry_errors) == 1
        assert "not found" in retry_errors[0], retry_errors

    # Check both actual persistence surfaces even when the response is faulty.
    assert log_path.read_bytes() == before_log, result
    assert await storage.count_entries(project=project) == before_count, result
    assert result.get("ok") is False, result
    error = result.get("error", "")
    assert error, result
    assert "error_response" not in error, result
    assert "append_entry failed:" not in error, result
    if retry_project_exists:
        assert "controlled first resolution failure" in error, result
        assert "does not authorize this append" in result.get("suggestion", ""), result
        assert "original agent identity" in result["suggestion"], result
        assert result.get("debug_path") == "project_resolution_failed_healed", result
    if not retry_project_exists:
        assert "controlled first resolution failure" in error, result
        assert result.get("debug_path") == "project_resolution_failed_healed", result


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.asyncio
async def test_append_retry_resolution_preserves_authorized_append(
    append_retry_project, test_agent,
):
    """An unchanged identity still appends through the real file and DB path."""
    project, storage, log_path = append_retry_project
    before_log = log_path.read_bytes()
    before_count = await storage.count_entries(project=project)
    message = "authorized append positive control"

    result = await append_entry(
        agent=test_agent, agent_id=test_agent, project=project.name,
        message=message, format="structured",
    )

    assert isinstance(result, dict), result
    assert result.get("ok") is True, result
    assert log_path.read_bytes().startswith(before_log), result
    assert message in log_path.read_text(encoding="utf-8"), result
    assert await storage.count_entries(project=project) == before_count + 1, result


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
