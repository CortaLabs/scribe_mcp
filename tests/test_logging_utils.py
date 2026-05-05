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
    build_resolution_metadata,
    clean_list,
    compose_log_line,
    default_status_emoji,
    normalize_metadata,
    normalize_meta_filters,
    resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.storage.models import ProjectRecord
from scribe_mcp.config import repo_config as repo_config_module


@pytest.fixture(autouse=True)
def _stub_reminders(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_reminders(*_args, **_kwargs):
        return []

    monkeypatch.setattr("scribe_mcp.shared.logging_utils.reminders.get_reminders", _fake_get_reminders)


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


def test_build_resolution_metadata_includes_compatibility_and_denied_fallbacks() -> None:
    context = LoggingContext(
        tool_name="query_entries",
        project={"name": "demo"},
        recent_projects=["demo"],
        state_snapshot={},
        reminders=[],
        resolution_source="session_binding",
        fallback_used=False,
        fallback_chain=[],
        denied_fallback_attempts=["compat_recent_project:public_release_blocked"],
        compatibility_usage={
            "requested": True,
            "requested_mode": "compat_recent_project",
            "applied": False,
        },
    )

    payload = build_resolution_metadata(context)
    assert payload["denied_fallback_attempts"] == [
        "compat_recent_project:public_release_blocked"
    ]
    assert payload["compatibility_usage"]["requested"] is True
    assert payload["compatibility_usage"]["applied"] is False


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


def test_resolve_log_definition_uses_repo_local_scribe_yaml(tmp_path: Path) -> None:
    config_dir = tmp_path / ".scribe" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "scribe.yaml").write_text(
        "\n".join(
            [
                "repo_slug: demo",
                "log_path: .scribe/custom/MAIN.md",
                "logs:",
                "  decisions:",
                "    path: \"{docs_dir}/DECISIONS.md\"",
                "    metadata_requirements: [owner]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    project = {
        "name": "demo_project",
        "root": str(tmp_path),
        "progress_log": str(tmp_path / "fallback" / "PROGRESS_LOG.md"),
        "docs_dir": str(tmp_path / ".scribe" / "docs" / "dev_plans" / "demo_project"),
    }
    cache: Dict[str, Tuple[Path, Dict[str, Any]]] = {}

    progress_path, _progress_definition = resolve_log_definition(project, "progress", cache=cache)
    decisions_path, decisions_definition = resolve_log_definition(project, "decisions", cache=cache)

    assert progress_path == tmp_path / ".scribe" / "custom" / "MAIN.md"
    assert decisions_path == tmp_path / ".scribe" / "docs" / "dev_plans" / "demo_project" / "DECISIONS.md"
    assert decisions_definition["metadata_requirements"] == ["owner"]


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
async def test_resolve_logging_context_prefers_canonical_stable_session_key() -> None:
    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return SimpleNamespace(recent_projects=["demo"], current_project="demo")

    class DummyBackend:
        def __init__(self) -> None:
            self.session_keys: list[str] = []

        async def get_session_project(self, session_key: str) -> Optional[str]:
            self.session_keys.append(session_key)
            if session_key == "stable-session-001":
                return "demo"
            return None

        async def fetch_project(self, _name: str) -> ProjectRecord:
            return ProjectRecord(
                id=1,
                name="demo",
                repo_root="/tmp/demo",
                progress_log_path="/tmp/demo/PROGRESS_LOG.md",
                docs_json=None,
            )

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = DummyBackend()

        @staticmethod
        def get_execution_context() -> Any:
            return SimpleNamespace(
                mode="project",
                stable_session_id="stable-session-001",
                session_id="transport-session-001",
            )

    context = await resolve_logging_context(
        tool_name="list_projects",
        server_module=DummyServerModule(),
        require_project=False,
    )

    assert context.project is not None
    assert context.project["name"] == "demo"
    assert context.resolution_source == "session_binding"
    assert DummyServerModule.storage_backend.session_keys == ["stable-session-001"]


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
    assert context.project["docs_dir"] == "/tmp/council_mcp_v2"
    assert context.resolution_source == "explicit_project"
    assert context.fallback_used is False
    assert context.fallback_chain == []


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


@pytest.mark.asyncio
async def test_resolve_logging_context_fails_closed_without_explicit_recovery_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested_project = {
        "name": "tmp_nested_project",
        "root": "/workspace/repo/tmp_tests/manage_docs_special_123",
        "progress_log": "/workspace/repo/tmp_tests/manage_docs_special_123/.scribe/docs/dev_plans/TestProject/PROGRESS_LOG.md",
        "docs": {
            "progress_log": "/workspace/repo/tmp_tests/manage_docs_special_123/.scribe/docs/dev_plans/TestProject/PROGRESS_LOG.md",
        },
    }

    class DummyState:
        current_project = "tmp_nested_project"
        recent_projects = ["tmp_nested_project"]

        def get_session_project(self, session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return None

        def get_project(self, name: Optional[str]) -> Optional[Dict[str, Any]]:
            if name == "tmp_nested_project":
                return nested_project
            return None

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = None

        @staticmethod
        def get_execution_context() -> Any:
            return None

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")

    async def fake_load_active_project(_state_manager):
        return nested_project, "tmp_nested_project", ("tmp_nested_project",)

    def fake_load_project_config(_name=None, allow_fallback=True):
        return None

    project_module.load_active_project = fake_load_active_project  # type: ignore[attr-defined]
    project_module.load_project_config = fake_load_project_config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)
    monkeypatch.setattr(repo_config_module, "get_current_repo_config", lambda: (Path("/workspace/repo"), {}))

    with pytest.raises(ProjectResolutionError, match="No project configured"):
        await resolve_logging_context(
            tool_name="manage_docs",
            server_module=DummyServerModule(),
            require_project=True,
        )


@pytest.mark.asyncio
async def test_resolve_logging_context_allows_explicit_compat_active_project_recovery_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested_project = {
        "name": "tmp_nested_project",
        "root": "/workspace/repo/tmp_tests/manage_docs_special_123",
        "progress_log": "/workspace/repo/tmp_tests/manage_docs_special_123/.scribe/docs/dev_plans/TestProject/PROGRESS_LOG.md",
        "docs": {
            "progress_log": "/workspace/repo/tmp_tests/manage_docs_special_123/.scribe/docs/dev_plans/TestProject/PROGRESS_LOG.md",
        },
    }

    class DummyState:
        current_project = "tmp_nested_project"
        recent_projects = ["tmp_nested_project"]

        def get_session_project(self, session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return None

        def get_project(self, name: Optional[str]) -> Optional[Dict[str, Any]]:
            if name == "tmp_nested_project":
                return nested_project
            return None

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = None

        @staticmethod
        def get_execution_context() -> Any:
            return None

    project_module = types.ModuleType("scribe_mcp.tools.project_utils")

    async def fake_load_active_project(_state_manager):
        return nested_project, "tmp_nested_project", ("tmp_nested_project",)

    def fake_load_project_config(_name=None, allow_fallback=True):
        return None

    project_module.load_active_project = fake_load_active_project  # type: ignore[attr-defined]
    project_module.load_project_config = fake_load_project_config  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "scribe_mcp.tools.project_utils", project_module)
    monkeypatch.setattr(repo_config_module, "get_current_repo_config", lambda: (Path("/workspace/repo"), {}))

    context = await resolve_logging_context(
        tool_name="manage_docs",
        server_module=DummyServerModule(),
        require_project=True,
        recovery_mode="compat_active_project",
    )

    assert context.project is not None
    assert context.project["name"] == "tmp_nested_project"
    assert context.resolution_source == "compat_active_project"
    assert context.fallback_used is True
    assert "compat_active_project" in (context.fallback_chain or [])


@pytest.mark.asyncio
async def test_resolve_logging_context_project_mode_does_not_use_state_session_fallback_when_backend_lookup_available() -> None:
    class DummyState:
        recent_projects = ["security_public_release_hardening_20260409_0940utc"]
        current_project = None

        def get_session_project(self, _session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return {
                "name": "security_public_release_hardening_20260409_0940utc",
                "root": "/tmp/stale",
                "progress_log": "/tmp/stale/PROGRESS_LOG.md",
            }

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyBackend:
        async def get_session_project(self, _session_id: str) -> Optional[str]:
            return None

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = DummyBackend()

        @staticmethod
        def get_execution_context() -> Any:
            return SimpleNamespace(
                mode="project",
                stable_session_id="stable-session-404",
                session_id="transport-session-404",
            )

    context = await resolve_logging_context(
        tool_name="list_projects",
        server_module=DummyServerModule(),
        require_project=False,
    )

    assert context.project is None
    assert context.resolution_source == "unresolved"


@pytest.mark.asyncio
async def test_resolve_logging_context_project_mode_prefers_authoritative_execution_session_id_over_stale_stable() -> None:
    class DummyState:
        recent_projects: List[str] = []
        current_project = None

        def get_session_project(self, _session_key: Optional[str]) -> Optional[Dict[str, Any]]:
            return None

    class DummyStateManager:
        async def record_tool(self, tool_name: str) -> Dict[str, Any]:
            return {"tool": tool_name}

        async def load(self) -> Any:
            return DummyState()

    class DummyBackend:
        async def get_session_project(self, session_id: str) -> Optional[str]:
            if session_id == "execution-session-123":
                return "authoritative_project"
            if session_id == "stale-prebinding-session-999":
                return "stale_project"
            return None

        async def fetch_project(self, name: str) -> Optional[ProjectRecord]:
            if name == "authoritative_project":
                return ProjectRecord(
                    id=1,
                    name="authoritative_project",
                    repo_root="/tmp/authoritative",
                    progress_log_path="/tmp/authoritative/PROGRESS_LOG.md",
                    docs_json=None,
                )
            if name == "stale_project":
                return ProjectRecord(
                    id=2,
                    name="stale_project",
                    repo_root="/tmp/stale",
                    progress_log_path="/tmp/stale/PROGRESS_LOG.md",
                    docs_json=None,
                )
            return None

    class DummyServerModule:
        state_manager = DummyStateManager()
        storage_backend = DummyBackend()

        @staticmethod
        def get_execution_context() -> Any:
            return SimpleNamespace(
                mode="project",
                session_id="execution-session-123",
                stable_session_id="stale-prebinding-session-999",
            )

    context = await resolve_logging_context(
        tool_name="list_projects",
        server_module=DummyServerModule(),
        require_project=False,
    )

    assert context.project is not None
    assert context.project["name"] == "authoritative_project"
    assert context.project["root"] == "/tmp/authoritative"
    assert context.resolution_source == "session_binding"
