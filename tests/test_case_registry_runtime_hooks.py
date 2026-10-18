from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext


class _RuntimeHelper(LoggingToolMixin):
    def __init__(self, server_module: object) -> None:
        self.server_module = server_module


async def _noop_append_entry(**_kwargs: object) -> None:
    return None


async def _noop_special_create(**_kwargs: object) -> dict[str, object]:
    return {"ok": False, "error": "not-used"}


async def _noop_storage_project(*_args: object, **_kwargs: object) -> object:
    return object()


async def _noop_auto_register(*_args: object, **_kwargs: object) -> bool:
    return False


def _load_runtime_module(monkeypatch: pytest.MonkeyPatch):
    class _DummyApp:
        def tool(self, *args, **kwargs):  # noqa: ANN002, ANN003
            def _decorator(func):
                return func

            return _decorator

    fake_server = types.ModuleType("scribe_mcp.server")
    fake_server.settings = types.SimpleNamespace(storage_timeout_seconds=5)
    fake_server.state_manager = None
    fake_server.app = _DummyApp()
    monkeypatch.setitem(sys.modules, "scribe_mcp.server", fake_server)
    module = importlib.import_module("scribe_mcp.doc_management.runtime")
    return importlib.reload(module)


@pytest.mark.parametrize(
    ("collection", "case_id", "doc_type", "expected_case_type"),
    [
        ("bugs", "BUG-2026-04-17-1010", "bug", "bug"),
        ("security", "SEC-2026-04-17-1011", "security", "security"),
    ],
)
def test_runtime_mutation_refreshes_shared_case_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collection: str,
    case_id: str,
    doc_type: str,
    expected_case_type: str,
) -> None:
    runtime_shared = _load_runtime_module(monkeypatch)
    report_path = tmp_path / "docs" / collection / "runtime" / f"2026-04-17_{case_id}" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "---\n"
        f"doc_type: {doc_type}\n"
        f"case_id: {case_id}\n"
        "status: open\n"
        "category: runtime\n"
        "---\n\n"
        "# Report\n",
        encoding="utf-8",
    )

    captured: list[dict[str, object]] = []

    class _StorageBackend:
        async def upsert_case_registry_record(self, **kwargs: object) -> None:
            captured.append(kwargs)

    async def _edit_action_stub(**kwargs: object) -> dict[str, object]:
        target = Path(str(kwargs["project"]["docs"]["CASE_DOC"]))
        target.write_text(
            "---\n"
            f"doc_type: {doc_type}\n"
            f"case_id: {case_id}\n"
            "status: closed\n"
            "category: runtime\n"
            "---\n\n"
            "# Report\n",
            encoding="utf-8",
        )
        return {"ok": True, "path": str(target)}

    monkeypatch.setattr(runtime_shared.edit_actions, "handle_edit_action", _edit_action_stub)

    server_module = SimpleNamespace(
        storage_backend=_StorageBackend(),
        get_execution_context=lambda: None,
        get_agent_identity=lambda: None,
    )
    helper = _RuntimeHelper(server_module=server_module)
    context = LoggingContext(
        tool_name="manage_docs",
        project={
            "name": "demo-project",
            "root": str(tmp_path),
            "docs": {"CASE_DOC": str(report_path)},
            "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
            "project_key": "pk-demo",
            "repo_id": "repo-demo",
        },
        recent_projects=["demo-project"],
        state_snapshot={},
        reminders=[],
    )

    response = asyncio.run(
        runtime_shared.handle_manage_docs_request(
            action="replace_section",
            doc_category="progress",
            section="summary",
            content="updated",
            patch=None,
            patch_source_hash=None,
            edit=None,
            patch_mode=None,
            start_line=None,
            end_line=None,
            template=None,
            metadata={},
            dry_run=False,
            doc_name="CASE_DOC",
            target_dir=None,
            project=None,
            state_snapshot={},
            helper=helper,
            context=context,
            server_module=server_module,
            append_entry=_noop_append_entry,
            project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
            logger=SimpleNamespace(
                info=lambda *_args, **_kwargs: None,
                warning=lambda *_args, **_kwargs: None,
                debug=lambda *_args, **_kwargs: None,
            ),
            handle_special_document_creation=_noop_special_create,
            get_or_create_storage_project=_noop_storage_project,
            get_index_updater_for_path=lambda *_args, **_kwargs: None,
            auto_register_document=_noop_auto_register,
        )
    )

    assert response["ok"] is True, response
    assert len(captured) == 1
    assert captured[0]["case_id"] == case_id
    assert captured[0]["case_type"] == expected_case_type
    assert captured[0]["status"] == "closed"
    assert captured[0]["metadata"]["category"] == "runtime"


def test_runtime_call_case_registry_method_surfaces_backend_type_error_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_shared = _load_runtime_module(monkeypatch)
    calls = {"count": 0}

    def _backend(**_kwargs: object) -> None:
        calls["count"] += 1
        raise TypeError("backend mapping failed")

    with pytest.raises(TypeError, match="backend mapping failed"):
        asyncio.run(
            runtime_shared._call_case_registry_method(
                _backend,
                {"case_id": "BUG-2026-04-18-0002"},
            )
        )

    assert calls["count"] == 1
