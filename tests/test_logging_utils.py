"""Unit tests for shared.logging_utils helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest

from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    _sanitize_log_field,
    clean_list,
    compose_log_line,
    default_status_emoji,
    normalize_metadata,
    normalize_meta_filters,
    resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.storage.models import ProjectRecord


def test_normalize_metadata_with_dict() -> None:
    meta = {"Phase": "Alpha", "count": 10, "details": {"nested": True}}
    normalised = normalize_metadata(meta)

    assert ("Phase", "Alpha") in normalised
    assert ("count", "10") in normalised
    # Nested objects should become sorted JSON, stripped of problematic characters.
    assert any(pair[0] == "details" and pair[1] == '{"nested": true}' for pair in normalised)


def test_normalize_metadata_with_cli_string_pairs() -> None:
    meta = "phase=beta owner=codex"
    normalised = normalize_metadata(meta)

    assert normalised == (("phase", "beta"), ("owner", "codex"))


def test_normalize_metadata_invalid_input() -> None:
    normalised = normalize_metadata(12345)
    assert ("meta_error", "Unsupported metadata payload type: int") in normalised
    assert ("raw_meta", "12345") in normalised


def test_normalize_metadata_handles_json_array_string() -> None:
    meta = '[["phase","gamma"],["owner","codex"]]'
    normalised = normalize_metadata(meta)
    assert ("phase", "gamma") in normalised
    assert ("owner", "codex") in normalised


def test_normalize_metadata_handles_sequence_pairs() -> None:
    meta = [("phase", "delta"), ("count", 3)]
    normalised = normalize_metadata(meta)
    assert ("phase", "delta") in normalised
    assert ("count", "3") in normalised


def test_normalize_meta_filters_success() -> None:
    filters, error = normalize_meta_filters({"foo": "bar", "phase": 3})
    assert error is None
    assert filters == {"foo": "bar", "phase": "3"}


def test_normalize_meta_filters_invalid_key() -> None:
    filters, error = normalize_meta_filters({"bad key": "value"})
    assert filters == {}
    assert error == "Meta filter key 'bad key' contains unsupported characters."


def test_clean_list_handles_strings_and_duplicates() -> None:
    result = clean_list(["Alpha", "alpha", "  Beta  "])
    assert result == ["alpha", "beta"]

    result_from_string = clean_list('["Gamma", "Delta"]')
    assert result_from_string == ["gamma", "delta"]


def test_compose_log_line_includes_metadata() -> None:
    line = compose_log_line(
        emoji="✅",
        timestamp="2025-10-31 17:00:00 UTC",
        agent="Scribe",
        project_name="demo",
        message="Task complete",
        meta_pairs=(("phase", "alpha"),),
        entry_id="abc123",
    )
    assert line == "[✅] [2025-10-31 17:00:00 UTC] [Agent: Scribe] [Project: demo] [ID: abc123] Task complete | phase=alpha"


def test_sanitize_log_field_strips_newlines() -> None:
    """Verify _sanitize_log_field strips newline/carriage-return/null characters."""
    assert _sanitize_log_field("clean") == "clean"
    assert _sanitize_log_field("line1\nline2") == "line1 line2"
    assert _sanitize_log_field("line1\rline2") == "line1 line2"
    assert _sanitize_log_field("has\x00null") == "hasnull"
    assert _sanitize_log_field("multi\n\r\x00bad") == "multi  bad"
    # Non-string input
    assert _sanitize_log_field(12345) == "12345"


def test_compose_log_line_sanitizes_injection() -> None:
    """Verify compose_log_line prevents log injection via newlines in user fields."""
    injected_msg = "Legitimate entry\n[FAKE] [2026-01-01T00:00:00Z] [Agent: Attacker] Injected"
    line = compose_log_line(
        emoji="info",
        timestamp="2026-02-06T00:00:00Z",
        agent="Test\nAgent",
        project_name="proj\rname",
        message=injected_msg,
        meta_pairs=(),
    )
    # The entire output must be a single line (no newlines)
    assert "\n" not in line
    assert "\r" not in line
    # Sanitized fields should have spaces replacing newlines
    assert "[Agent: Test Agent]" in line
    assert "[Project: proj name]" in line


def test_default_status_emoji_prefers_explicit() -> None:
    project = {"defaults": {"emoji": "🛠️"}}
    assert default_status_emoji(explicit="🎯", status=None, project=project) == "🎯"
    assert default_status_emoji(explicit=None, status="success", project=project) == "✅"
    assert default_status_emoji(explicit=None, status=None, project=project) == "🛠️"


def test_resolve_log_definition_uses_cache(tmp_path) -> None:
    project = {
        "name": "demo_project",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
    }
    cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}

    path, definition = resolve_log_definition(project, "progress", cache=cache)
    assert path == tmp_path / "PROGRESS_LOG.md"
    assert "path" in definition
    # Second call should hit cache and return same path.
    cached_path, _ = resolve_log_definition(project, "progress", cache=cache)
    assert cached_path == path


@pytest.mark.asyncio
async def test_resolve_logging_context_with_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that agent-scoped project resolution surfaces reminders and recents."""

    recorded_tools: List[str] = []

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            recorded_tools.append(tool_name)
            return {"tool": tool_name}

        async def load(self) -> Any:
            return SimpleNamespace(current_project=None, recent_projects=[])

    class DummyServerModule:
        state_manager = DummyStateManager()

    async def fake_get_agent_project_data(agent_id: str) -> Tuple[Dict[str, Any], List[str]]:
        assert agent_id == "agent-1"
        project = {
            "name": "demo",
            "progress_log": "/tmp/demo.log",
            "defaults": {"emoji": "ℹ️"},
        }
        return project, ["demo"]

    async def fake_get_reminders(project: Dict[str, Any], tool_name: str, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [{"message": "hi", "tool": tool_name}]

    agent_module = types.ModuleType("scribe_mcp.tools.agent_project_utils")
    agent_module.get_agent_project_data = fake_get_agent_project_data  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.agent_project_utils", agent_module)

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")

    async def fake_load_active_project(state_manager):
        return (None, None, ())

    def fake_load_project_config(name, allow_fallback=True):
        return None

    project_module.load_active_project = fake_load_active_project  # type: ignore[attr-defined]
    project_module.load_project_config = fake_load_project_config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)

    monkeypatch.setattr("scribe_mcp.shared.logging_utils.reminders.get_reminders", fake_get_reminders)

    context = await resolve_logging_context(
        tool_name="append_entry",
        server_module=DummyServerModule(),
        agent_id="agent-1",
    )

    assert isinstance(context, LoggingContext)
    assert context.project and context.project["name"] == "demo"
    assert context.reminders == [{"message": "hi", "tool": "append_entry"}]
    assert recorded_tools == ["append_entry"]


@pytest.mark.asyncio
async def test_resolve_logging_context_requires_project(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

    class DummyServerModule:
        state_manager = DummyStateManager()

    async def no_project(*args, **kwargs):
        return (None, None, ())


    agent_module = types.ModuleType("scribe_mcp.tools.agent_project_utils")
    agent_module.get_agent_project_data = lambda agent_id: asyncio.sleep(0.0, result=(None, []))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.agent_project_utils", agent_module)

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")
    project_module.load_active_project = no_project  # type: ignore[attr-defined]
    project_module.load_project_config = lambda name, allow_fallback=True: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)

    monkeypatch.setattr("scribe_mcp.shared.logging_utils.reminders.get_reminders", lambda *args, **kwargs: asyncio.sleep(0.0, result=[]))

    with pytest.raises(ProjectResolutionError):
        await resolve_logging_context(
            tool_name="query_entries",
            server_module=DummyServerModule(),
            agent_id=None,
            explicit_project=None,
        )


@pytest.mark.asyncio
async def test_resolve_logging_context_explicit_project_uses_storage_backend() -> None:
    class DummyState:
        current_project = None
        recent_projects: List[str] = []

        def get_session_project(self, session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return None

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyBackend:
        async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
            if name != "council_mcp_v2":
                return None
            return ProjectRecord(
                id=1,
                name="council_mcp_v2",
                repo_root="/tmp/council_mcp_v2",
                progress_log_path="/tmp/council_mcp_v2/PROGRESS_LOG.md",
                docs_json='{"progress_log":"/tmp/council_mcp_v2/PROGRESS_LOG.md"}',
            )

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = DummyBackend()

        @staticmethod
        def get_execution_context() -> Any:
            return SimpleNamespace(mode="project", stable_session_id="session-1")

    context = await resolve_logging_context(
        tool_name="read_recent",
        server_module=DummyServerModule(),
        explicit_project="council_mcp_v2",
        require_project=True,
    )

    assert context.project is not None
    assert context.project["name"] == "council_mcp_v2"
    assert context.project["root"] == "/tmp/council_mcp_v2"
    assert context.project["progress_log"] == "/tmp/council_mcp_v2/PROGRESS_LOG.md"
    assert context.project["docs"]["progress_log"] == "/tmp/council_mcp_v2/PROGRESS_LOG.md"


@pytest.mark.asyncio
async def test_resolve_logging_context_explicit_project_missing_fails_hard(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyState:
        current_project = None
        recent_projects = ["scribe_pro_cleanup", "scribe_mcp"]

        def get_session_project(self, session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return None

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyBackend:
        async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
            return None

        async def list_projects(self):
            return []

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = DummyBackend()

        @staticmethod
        def get_execution_context() -> Any:
            return SimpleNamespace(mode="project", stable_session_id="session-1")

    observed_allow_fallback: List[bool] = []

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")

    async def fake_load_active_project(state_manager):
        return (None, None, ())

    def fake_load_project_config(name, allow_fallback=True):
        observed_allow_fallback.append(bool(allow_fallback))
        if allow_fallback:
            return {"name": "scribe_mcp", "progress_log": "/tmp/scribe_mcp/PROGRESS_LOG.md"}
        return None

    project_module.load_active_project = fake_load_active_project  # type: ignore[attr-defined]
    project_module.load_project_config = fake_load_project_config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)

    with pytest.raises(ProjectResolutionError, match="Explicit project 'missing_project' was not found"):
        await resolve_logging_context(
            tool_name="read_recent",
            server_module=DummyServerModule(),
            explicit_project="missing_project",
            require_project=True,
        )

    assert observed_allow_fallback
    assert all(flag is False for flag in observed_allow_fallback)
