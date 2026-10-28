from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action
from scribe_mcp.doc_management.manager import apply_doc_change
from scribe_mcp.shared.project_registry import ProjectRegistry
from test_project_registry import _make_temp_db


class _RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_doc_change(self, project, **kwargs):
        self.calls.append({"project": project, **kwargs})


@pytest.mark.asyncio
async def test_managed_edit_records_session_provenance_in_doc_change_metadata(tmp_path: Path) -> None:
    backend = _RecordingBackend()
    doc_path = tmp_path / "CHECKLIST.md"
    registry_path = _make_temp_db(tmp_path)
    registry = ProjectRegistry(db_path=registry_path)
    with sqlite3.connect(registry_path) as connection:
        connection.execute(
            "INSERT INTO scribe_projects (name, repo_root, progress_log_path, status) VALUES (?, ?, ?, ?)",
            ("hardening", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md"), "planning"),
        )

    change = SimpleNamespace(
        success=True,
        path=doc_path,
        diff_preview="",
        before_hash="before-sha",
        after_hash="after-sha",
        extra={},
        verification_passed=True,
        file_size_before=0,
        file_size_after=7,
        error_message=None,
        content_written="",
    )

    async def _apply_doc_change(*_args, **_kwargs):
        return change

    async def _get_or_create_storage_project(_backend, _project):
        return SimpleNamespace(id=101)

    async def _append_entry(**_kwargs):
        return None

    async def _index_doc_for_vector(**_kwargs):
        return None

    context = SimpleNamespace(
        session_id="session-abc",
        stable_session_id="stable-session-xyz",
        transport_session_id="transport-123",
        resolved_scope=SimpleNamespace(
            agent_session_id="agent-session-789",
            resolution_source="runtime_context",
            trust_level="verified",
        ),
    )

    response = await handle_edit_action(
        action="replace_section",
        project={"name": "hardening", "docs": {"checklist": str(doc_path)}, "docs_dir": str(tmp_path), "root": str(tmp_path)},
        doc_name="checklist",
        doc_category="dev_plan",
        section="package_3_2",
        content="updated",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"ticket": "P3.2"},
        dry_run=False,
        backend=backend,
        agent_id="CoderAgent",
        helper=SimpleNamespace(apply_context_payload=lambda payload, _ctx: payload, error_response=lambda message: {"ok": False, "error": message}),
        context=context,
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=_apply_doc_change,
        get_or_create_storage_project=_get_or_create_storage_project,
        append_entry=_append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), None, None),
        index_doc_for_vector=_index_doc_for_vector,
        vector_indexing_enabled=False,
        get_index_updater_for_path=lambda **_kwargs: None,
        project_registry=registry,
        server_module=SimpleNamespace(state_manager=None, storage_backend=None),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert response["ok"] is True
    assert len(backend.calls) == 1
    with sqlite3.connect(registry_path) as connection:
        raw = connection.execute("SELECT meta FROM scribe_projects WHERE name = ?", ("hardening",)).fetchone()[0]
    docs = json.loads(raw)["docs"]
    assert docs["baseline_hashes"]["checklist"] == "before-sha"
    assert docs["current_hashes"]["checklist"] == "after-sha"

    metadata = backend.calls[0]["metadata"]
    assert metadata["ticket"] == "P3.2"
    assert metadata["session_provenance"] == {
        "session_id": "session-abc",
        "stable_session_id": "stable-session-xyz",
        "transport_session_id": "transport-123",
        "agent_session_id": "agent-session-789",
        "resolution_source": "runtime_context",
        "trust_level": "verified",
    }


@pytest.mark.asyncio
@pytest.mark.regression
@pytest.mark.storage
@pytest.mark.parametrize("release_writer", [True, False], ids=["commit", "nonfatal-lock-timeout"])
async def test_managed_edit_registry_contention_keeps_event_loop_responsive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, release_writer: bool, test_agent: str
) -> None:
    """An event-loop task can release a real lock before the edit returns."""
    registry_path = _make_temp_db(tmp_path)
    registry = ProjectRegistry(db_path=registry_path)
    with sqlite3.connect(registry_path) as connection:
        connection.execute(
            "INSERT INTO scribe_projects (name, repo_root, progress_log_path, status) VALUES (?, ?, ?, ?)",
            ("hardening", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md"), "planning"),
        )

    doc_path = tmp_path / "CHECKLIST.md"
    doc_path.write_text("# Checklist\n", encoding="utf-8")
    backend = _RecordingBackend()
    loop = asyncio.get_running_loop()
    write_started = asyncio.Event()
    registry_errors: list[sqlite3.Error] = []
    real_connect = registry._connect

    def trace_statement(statement: str) -> None:
        if statement.lstrip().upper().startswith("UPDATE SCRIBE_PROJECTS"):
            # The real registry has read its row and is about to contend on
            # the writer lock. This observes SQLite; it does not replace it.
            loop.call_soon_threadsafe(write_started.set)

    class ObservedConnection:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection.__enter__()

        def __exit__(self, *args):
            if isinstance(args[1], sqlite3.Error):
                registry_errors.append(args[1])
            return self.connection.__exit__(*args)

    def traced_connect(*, row_factory=False):
        connection = real_connect(row_factory=row_factory)
        connection.set_trace_callback(trace_statement)
        return ObservedConnection(connection)

    monkeypatch.setattr(registry, "_connect", traced_connect)

    async def storage_project(_backend, _project):
        return SimpleNamespace(id=101)

    async def append_entry(**_kwargs):
        return None

    writer = sqlite3.connect(registry_path)
    writer.execute("BEGIN IMMEDIATE")
    task = asyncio.create_task(handle_edit_action(
        action="append",
        project={"name": "hardening", "docs": {"checklist": str(doc_path)}, "docs_dir": str(tmp_path), "root": str(tmp_path)},
        doc_name="checklist", doc_category="dev_plan", section=None,
        content="Registry contention update", patch=None, patch_source_hash=None,
        edit=None, patch_mode=None, start_line=None, end_line=None,
        template=None, metadata={}, dry_run=False, backend=backend,
        agent_id=test_agent,
        helper=SimpleNamespace(apply_context_payload=lambda payload, _ctx: payload),
        context=SimpleNamespace(), execution_context=None, deprecation_warning=None,
        apply_doc_change=apply_doc_change, get_or_create_storage_project=storage_project,
        append_entry=append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), None, None),
        index_doc_for_vector=None, vector_indexing_enabled=False,
        get_index_updater_for_path=lambda **_kwargs: None,
        project_registry=registry,
        server_module=SimpleNamespace(state_manager=None, storage_backend=None),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    ))
    try:
        await asyncio.wait_for(write_started.wait(), timeout=5)
        assert not task.done(), "Registry contention blocked the event loop until the edit returned"
        if release_writer:
            writer.rollback()
        response = await asyncio.wait_for(task, timeout=5)
    finally:
        writer.rollback()
        writer.close()
        # Drain the real operation even on assertion failure; no background work
        # should outlive this test's disposable database.
        if not task.done():
            await asyncio.wait_for(task, timeout=5)

    assert response["ok"] is True
    assert "Registry contention update" in doc_path.read_text(encoding="utf-8")
    assert len(backend.calls) == 1
    with sqlite3.connect(registry_path) as connection:
        raw = connection.execute("SELECT meta FROM scribe_projects WHERE name = ?", ("hardening",)).fetchone()[0]
    if release_writer:
        assert registry_errors == []
        docs = json.loads(raw)["docs"]
        assert docs["update_count"] == 1
        assert docs["last_doc_type"] == "checklist"
        assert docs["last_action"] == "append"
        assert docs["baseline_hashes"]["checklist"] == backend.calls[0]["sha_before"]
        assert docs["current_hashes"]["checklist"] == backend.calls[0]["sha_after"]
    else:
        # The handler must await and tolerate the actual SQLite busy failure,
        # preserving both the document edit and the storage audit call.
        assert raw is None
        assert len(registry_errors) == 1
        assert isinstance(registry_errors[0], sqlite3.OperationalError)
        assert "locked" in str(registry_errors[0])
