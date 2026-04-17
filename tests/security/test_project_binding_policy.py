from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pathlib import Path

from scribe_mcp.doc_management.runtime import (
    auto_register_document,
    handle_manage_docs_request,
    register_document_path,
)
from scribe_mcp.shared import logging_utils as logging_utils_module
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, resolve_logging_context
from scribe_mcp.state.manager import StateManager
from scribe_mcp.tools import set_project as set_project_tool


class _ScopedBackend:
    def __init__(self, *, scoped_records=None, global_project_name=None) -> None:
        self._scoped_records = list(scoped_records or [])
        self._global_project_name = global_project_name
        self.list_projects_calls = 0
        self.list_projects_by_repo_calls = 0

    async def setup(self) -> None:
        return None

    async def list_projects_by_repo(self, _repo_root: str):
        self.list_projects_by_repo_calls += 1
        return list(self._scoped_records)

    async def list_projects(self):
        self.list_projects_calls += 1
        return [
            SimpleNamespace(
                name="global-fallback",
                repo_root="/tmp/global",
                progress_log_path="/tmp/global/PROGRESS_LOG.md",
                docs_json=None,
            )
        ]

    async def get_session_project(self, _session_id: str):
        return None

    async def get_agent_project(self, _agent_id: str):
        if not self._global_project_name:
            return None
        return {"project_name": self._global_project_name}

    async def get_session_mode(self, _session_id: str):
        return None

    async def get_session_activity(self, _session_id: str):
        return None


@pytest.mark.asyncio
async def test_state_manager_fails_closed_without_scoped_binding(tmp_path) -> None:
    backend = _ScopedBackend(scoped_records=[])
    manager = StateManager(path=tmp_path / "state.json", storage_backend=backend)

    execution_context = SimpleNamespace(
        repo_root=str(tmp_path),
        stable_session_id="session-1",
        session_id="session-1",
    )
    router_context_manager = SimpleNamespace(get_current=lambda: execution_context)
    fake_server = SimpleNamespace(
        get_execution_context=lambda: execution_context,
        router_context_manager=router_context_manager,
    )

    with patch("scribe_mcp.server", fake_server):
        state = await manager.load()

    assert state.current_project is None
    assert state.projects == {}
    assert backend.list_projects_by_repo_calls == 1
    assert backend.list_projects_calls == 0


@pytest.mark.asyncio
async def test_state_manager_does_not_use_global_agent_project_fallback(tmp_path) -> None:
    backend = _ScopedBackend(scoped_records=[], global_project_name="global-only")
    manager = StateManager(path=tmp_path / "state.json", storage_backend=backend)

    execution_context = SimpleNamespace(
        repo_root=str(tmp_path),
        stable_session_id="session-2",
        session_id="session-2",
    )
    router_context_manager = SimpleNamespace(get_current=lambda: execution_context)
    fake_server = SimpleNamespace(
        get_execution_context=lambda: execution_context,
        router_context_manager=router_context_manager,
    )

    with patch("scribe_mcp.server", fake_server):
        state = await manager.load()

    assert state.current_project is None
    assert state.session_projects == {}


class _BindingState:
    current_project = "trusted-project"
    recent_projects = ["trusted-project"]

    def get_session_project(self, _session_key: str):
        return None

    def get_project(self, name: str):
        if name == "trusted-project":
            return {"name": "trusted-project", "root": "/tmp/trusted-project", "progress_log": "/tmp/trusted-project/PROGRESS_LOG.md"}
        return None


class _BindingStateManager:
    async def record_tool(self, tool_name: str):
        return {"tool": tool_name}

    async def load(self):
        return _BindingState()


class _BindingBackend:
    async def get_session_project(self, _session_id: str):
        return None

    async def fetch_project(self, _name: str):
        return None

    async def list_projects(self):
        return []

class _ExplicitOverrideBackend:
    async def get_session_project(self, _session_id: str):
        return "trusted-project"

    async def fetch_project(self, name: str):
        if name == "trusted-project":
            return SimpleNamespace(
                name="trusted-project",
                repo_root="/tmp/trusted-project",
                progress_log_path="/tmp/trusted-project/PROGRESS_LOG.md",
                docs_json=None,
            )
        if name == "other-project":
            return SimpleNamespace(
                name="other-project",
                repo_root="/tmp/other-project",
                progress_log_path="/tmp/other-project/PROGRESS_LOG.md",
                docs_json=None,
            )
        return None

    async def list_projects(self):
        return []


class _ExplicitOverrideNoBindingBackend:
    async def get_session_project(self, _session_id: str):
        return None

    async def fetch_project(self, name: str):
        if name == "other-project":
            return SimpleNamespace(
                name="other-project",
                repo_root="/tmp/other-project",
                progress_log_path="/tmp/other-project/PROGRESS_LOG.md",
                docs_json=None,
            )
        return None

    async def list_projects(self):
        return []


class _PolicyHelper(LoggingToolMixin):
    def __init__(self, server_module):
        self.server_module = server_module
        self.last_prepare_context_kwargs = None

    async def prepare_context(self, **kwargs):
        self.last_prepare_context_kwargs = dict(kwargs)
        return await super().prepare_context(**kwargs)


@pytest.mark.asyncio
async def test_manage_docs_revalidates_explicit_project_override_with_existing_context() -> None:
    server_module = SimpleNamespace(
        state_manager=_BindingStateManager(),
        storage_backend=_BindingBackend(),
        get_execution_context=lambda: SimpleNamespace(mode="project", stable_session_id="session-security", session_id="session-security"),
        get_agent_identity=lambda: None,
    )
    helper = _PolicyHelper(server_module=server_module)
    context = LoggingContext(
        tool_name="manage_docs",
        project={"name": "trusted-project"},
        recent_projects=["trusted-project"],
        state_snapshot={},
        reminders=[],
    )

    response = await handle_manage_docs_request(
        action="search",
        doc_category="research",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
        doc_name="CHECKLIST",
        target_dir=None,
        project="forged-project",
        state_snapshot={},
        helper=helper,
        context=context,
        server_module=server_module,
        append_entry=lambda **_kwargs: None,
        project_registry=SimpleNamespace(),
        logger=SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, debug=lambda *args, **kwargs: None),
        handle_special_document_creation=lambda **_kwargs: None,
        get_or_create_storage_project=lambda *args, **kwargs: None,
        get_index_updater_for_path=lambda *args, **kwargs: None,
        auto_register_document=lambda *args, **kwargs: False,
    )

    assert response["ok"] is False
    assert "Explicit project 'forged_project' was not found." in response["error"]
    assert response["recent_projects"] == ["trusted-project"]
    assert helper.last_prepare_context_kwargs is not None
    assert helper.last_prepare_context_kwargs["recovery_mode"] == "none"

@pytest.mark.asyncio
async def test_rejects_unauthorized_explicit_project_override_in_public_release(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(
            record_tool=lambda _tool: {"tool": "query_entries"},
            load=lambda: _BindingState(),
        ),
        storage_backend=_ExplicitOverrideBackend(),
        get_execution_context=lambda: SimpleNamespace(
            mode="project",
            stable_session_id="session-security",
            session_id="session-security",
        ),
        get_agent_identity=lambda: None,
    )

    async def _record_tool(_tool_name: str):
        return {"tool": _tool_name}

    async def _load_state():
        return _BindingState()

    server_module.state_manager.record_tool = _record_tool
    server_module.state_manager.load = _load_state

    with pytest.raises(logging_utils_module.ProjectResolutionError) as excinfo:
        await resolve_logging_context(
            tool_name="query_entries",
            server_module=server_module,
            explicit_project="other-project",
            require_project=True,
            recovery_mode="none",
        )

    assert "not authorized for this session" in str(excinfo.value)


@pytest.mark.asyncio
async def test_rejects_explicit_project_override_without_authorized_session_binding_in_public_release(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")
    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(
            record_tool=lambda _tool: {"tool": "query_entries"},
            load=lambda: _BindingState(),
        ),
        storage_backend=_ExplicitOverrideNoBindingBackend(),
        get_execution_context=lambda: SimpleNamespace(
            mode="project",
            stable_session_id="session-security",
            session_id="session-security",
        ),
        get_agent_identity=lambda: None,
    )

    async def _record_tool(_tool_name: str):
        return {"tool": _tool_name}

    async def _load_state():
        return _BindingState()

    server_module.state_manager.record_tool = _record_tool
    server_module.state_manager.load = _load_state

    with pytest.raises(logging_utils_module.ProjectResolutionError) as excinfo:
        await resolve_logging_context(
            tool_name="query_entries",
            server_module=server_module,
            explicit_project="other-project",
            require_project=True,
            recovery_mode="none",
        )

    assert "not authorized for this session" in str(excinfo.value)


@pytest.mark.asyncio
async def test_public_release_rejects_global_current_recent_fallback_rehydration(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_RELEASE_PROFILE", "public")

    class _FallbackState:
        current_project = "global-fallback"
        recent_projects = ["global-fallback", "recent-fallback"]

        def get_session_project(self, _session_key: str):
            return None

        def get_project(self, _name: str):
            return {"name": "global-fallback", "root": "/tmp/global", "progress_log": "/tmp/global/PROGRESS_LOG.md"}

    async def _record_tool(_tool_name: str):
        return {"tool": _tool_name}

    async def _load_state():
        return _FallbackState()

    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(record_tool=_record_tool, load=_load_state),
        storage_backend=SimpleNamespace(fetch_project=lambda _name: None, list_projects=lambda: []),
        get_execution_context=lambda: None,
        get_agent_identity=lambda: None,
    )

    context = await resolve_logging_context(
        tool_name="query_entries",
        server_module=server_module,
        require_project=False,
        recovery_mode="compat_all",
    )

    assert context.project is None
    assert context.fallback_used is False


@pytest.mark.asyncio
async def test_set_project_ignores_untrusted_scribe_user_workspace_remap(monkeypatch) -> None:
    monkeypatch.setenv("SCRIBE_USER", "trusted-user")
    assert set_project_tool._trusted_workspace_user("attacker-user") == "trusted-user"


@pytest.mark.asyncio
async def test_register_document_path_uses_canonical_stable_session_binding(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class _Backend:
        async def update_project_docs(self, _project_name: str, _docs_json: str) -> None:
            return None

    class _StateManager:
        async def set_current_project(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {}

    async def _append_entry(**_kwargs):
        return None

    async def _record_doc_update(**_kwargs):
        return None

    execution_context = SimpleNamespace(
        stable_session_id="stable-session-canonical",
        session_id="transport-session-legacy",
        resolved_scope=SimpleNamespace(
            stable_session_id="stable-session-canonical",
            transport_session_id="transport-session-legacy",
            resolution_source="execution_context",
        ),
    )
    fake_server = SimpleNamespace(
        storage_backend=_Backend(),
        state_manager=_StateManager(),
        get_execution_context=lambda: execution_context,
    )
    fake_registry = SimpleNamespace(record_doc_update=_record_doc_update)
    fake_logger = SimpleNamespace(warning=lambda *args, **kwargs: None)

    warning = await register_document_path(
        {"name": "trusted-project", "docs": {}},
        "CHECKLIST",
        doc_path,
        server_module=fake_server,
        project_registry=fake_registry,
        append_entry=_append_entry,
        logger=fake_logger,
        execution_context=execution_context,
        agent_id="manage_docs",
    )

    assert warning is None
    kwargs = captured["kwargs"]
    assert kwargs["session_id"] == "stable-session-canonical"
    assert kwargs["resolved_scope"] is execution_context.resolved_scope


@pytest.mark.asyncio
async def test_auto_register_document_uses_canonical_stable_session_binding(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class _Backend:
        async def update_project_docs(self, _project_name: str, _docs_json: str) -> None:
            return None

    class _StateManager:
        async def set_current_project(self, *args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {}

    async def _append_entry(**_kwargs):
        return None

    async def _record_doc_update(**_kwargs):
        return None

    execution_context = SimpleNamespace(
        stable_session_id="stable-session-canonical",
        session_id="transport-session-legacy",
        resolved_scope=SimpleNamespace(
            stable_session_id="stable-session-canonical",
            transport_session_id="transport-session-legacy",
            resolution_source="execution_context",
        ),
    )
    fake_server = SimpleNamespace(
        storage_backend=_Backend(),
        state_manager=_StateManager(),
        get_execution_context=lambda: execution_context,
    )
    fake_registry = SimpleNamespace(record_doc_update=_record_doc_update)
    fake_logger = SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None)

    result = await auto_register_document(
        {"name": "trusted-project", "docs": {}},
        "CHECKLIST",
        server_module=fake_server,
        resolve_doc_path=lambda _project, _doc_name: doc_path,
        project_registry=fake_registry,
        append_entry=_append_entry,
        logger=fake_logger,
    )

    assert result is True
    kwargs = captured["kwargs"]
    assert kwargs["session_id"] == "stable-session-canonical"
    assert kwargs["resolved_scope"] is execution_context.resolved_scope
