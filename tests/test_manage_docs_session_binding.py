from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.doc_management.runtime import register_document_path
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope


class _BackendStub:
    def __init__(self) -> None:
        self.update_calls = 0

    async def update_project_docs(self, project_name: str, docs_json: str, **_kwargs: Any) -> None:
        self.update_calls += 1


class _RegistryStub:
    def __init__(self) -> None:
        self.calls = 0

    def record_doc_update(self, **_: object) -> None:
        self.calls += 1


@pytest.mark.asyncio
async def test_register_document_path_uses_authoritative_context_session_id(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["agent_id"] = agent_id
        captured["mirror_global"] = mirror_global

    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    warning = await register_document_path(
        project,
        "checklist",
        doc_path,
        server_module=server_module,
        project_registry=registry,
        append_entry=_append_entry,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        execution_context=execution_context,
        agent_id="BugHunterAgent",
    )

    assert warning is None
    assert captured["session_id"] == "authoritative-session"
    assert backend.update_calls == 1
    assert registry.calls == 1


@pytest.mark.asyncio
async def test_register_document_path_fails_closed_without_authoritative_session(tmp_path: Path) -> None:
    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")

    backend = _BackendStub()
    registry = _RegistryStub()
    server_module = SimpleNamespace(
        storage_backend=backend,
        state_manager=SimpleNamespace(set_current_project=lambda **_: None),
    )
    async def _append_entry(**_: object) -> None:
        return None

    project = {"name": "demo", "docs": {}}
    execution_context = SimpleNamespace(session_id=None, stable_session_id=None)

    with pytest.raises(ValueError, match="authoritative session binding"):
        await register_document_path(
            project,
            "checklist",
            doc_path,
            server_module=server_module,
            project_registry=registry,
            append_entry=_append_entry,
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            execution_context=execution_context,
            agent_id="BugHunterAgent",
        )

    assert backend.update_calls == 0
    assert registry.calls == 0


def test_resolve_authoritative_write_scope_uses_context_authoritative_session_key() -> None:
    context = SimpleNamespace(
        session_id="context-session",
        stable_session_id="stable-session",
        authoritative_session_key="authoritative-session",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] == "authoritative-session"
    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_rejects_transport_only_scope() -> None:
    context = SimpleNamespace(
        transport_session_id="transport-only-session",
        resolved_scope=SimpleNamespace(
            transport_session_id="transport-only-session",
            stable_session_id=None,
            agent_session_id=None,
            authoritative_session_key=None,
            resolution_source="runtime_context",
        ),
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_key"] is None
    assert scope["authoritative_session_id"] is None


@pytest.mark.asyncio
async def test_handle_edit_action_register_doc_uses_authoritative_context_session_id(tmp_path: Path) -> None:
    created_path = tmp_path / "NOTE.md"
    created_path.write_text("# Note\n", encoding="utf-8")

    captured: dict[str, object] = {}

    async def _set_current_project(
        name: str,
        project_data: dict,
        *,
        agent_id: str,
        session_id: str,
        resolved_scope: object,
        mirror_global: bool,
    ) -> None:
        captured["name"] = name
        captured["session_id"] = session_id
        captured["mirror_global"] = mirror_global

    async def _apply_doc_change(*_args, **_kwargs):
        return SimpleNamespace(
            success=True,
            path=created_path,
            diff_preview="",
            before_hash=None,
            after_hash="after",
            extra={},
            error_message=None,
            verification_passed=True,
            file_size_before=0,
            file_size_after=created_path.stat().st_size,
            content_written=created_path.read_text(encoding="utf-8"),
        )

    async def _get_or_create_storage_project(*_args, **_kwargs):
        return object()

    async def _append_entry(**_kwargs):
        return None

    async def _index_doc_for_vector(**_kwargs):
        return None

    def _helper_error_response(message: str, extra: dict | None = None):
        payload = {"ok": False, "error": message}
        if extra:
            payload["extra"] = extra
        return payload

    helper = SimpleNamespace(
        apply_context_payload=lambda response, _context: response,
        error_response=_helper_error_response,
    )
    async def _record_doc_change(*_args, **_kwargs):
        return None

    async def _update_project_docs(*_args, **_kwargs):
        return None

    backend = SimpleNamespace(
        record_doc_change=_record_doc_change,
        update_project_docs=_update_project_docs,
    )
    server_module = SimpleNamespace(
        state_manager=SimpleNamespace(set_current_project=_set_current_project),
        storage_backend=backend,
    )
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")
    project = {"name": "demo", "docs": {}}

    result = await handle_edit_action(
        action="create_doc",
        project=project,
        doc_name="note_doc",
        doc_category="",
        section=None,
        content="# Note\n",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"doc_name": "note_doc", "register_doc": True},
        dry_run=False,
        backend=backend,
        agent_id="BugHunterAgent",
        helper=helper,
        context=context,
        execution_context=context,
        deprecation_warning=None,
        apply_doc_change=_apply_doc_change,
        get_or_create_storage_project=_get_or_create_storage_project,
        append_entry=_append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), False, []),
        index_doc_for_vector=_index_doc_for_vector,
        vector_indexing_enabled=lambda _repo_root: False,
        get_index_updater_for_path=lambda *_args, **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
        server_module=server_module,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result is not None
    assert result["ok"] is True
    warnings = result.get("warnings") or []
    assert all("Registry update failed" not in warning for warning in warnings)
    assert captured["session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_prefers_context_session_id_over_stable() -> None:
    """Contract test (BUG-2026-06-11-0004): without a resolved_scope, the
    request's own session_id outranks a bare carried-over stable_session_id.
    Originally pinned in 08d4d22; regressed by e320b3d; restored 2026-06-11."""
    context = SimpleNamespace(session_id="authoritative-session", stable_session_id="stale-session")

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "authoritative-session"


def test_resolve_authoritative_write_scope_verified_scope_still_wins() -> None:
    """Server-derived resolved_scope keys keep absolute priority — the
    trust-order fix only affects degraded contexts without a resolved scope."""
    resolved = SimpleNamespace(
        authoritative_session_key="scope-derived-key",
        stable_session_id="scope-stable",
        agent_session_id=None,
        resolution_source="runtime_context",
    )
    context = SimpleNamespace(
        resolved_scope=resolved,
        session_id="request-session",
        stable_session_id="raw-stable",
    )

    scope = resolve_authoritative_write_scope(context=context, agent_session_id=None)

    assert scope["authoritative_session_id"] == "scope-derived-key"
