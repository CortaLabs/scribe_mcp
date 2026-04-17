from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action


class _RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def record_doc_change(self, project, **kwargs):
        self.calls.append({"project": project, **kwargs})


@pytest.mark.asyncio
async def test_managed_edit_records_session_provenance_in_doc_change_metadata(tmp_path: Path) -> None:
    backend = _RecordingBackend()
    doc_path = tmp_path / "CHECKLIST.md"

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
        deprecation_warning=None,
        apply_doc_change=_apply_doc_change,
        get_or_create_storage_project=_get_or_create_storage_project,
        append_entry=_append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), None, None),
        index_doc_for_vector=_index_doc_for_vector,
        vector_indexing_enabled=False,
        get_index_updater_for_path=lambda **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda *_args, **_kwargs: None),
        server_module=SimpleNamespace(state_manager=None, storage_backend=None),
        logger=SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    )

    assert response["ok"] is True
    assert len(backend.calls) == 1

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
