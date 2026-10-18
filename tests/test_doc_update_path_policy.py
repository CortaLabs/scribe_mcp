from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from scribe_mcp import server as server_module
from scribe_mcp.doc_management.actions import edit as edit_module
from scribe_mcp.doc_management import special_create as special_create_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools import append_entry as append_entry_module


pytestmark = pytest.mark.asyncio


class _Helper:
    def apply_context_payload(self, payload: dict, _context: object) -> dict:
        return payload

    def error_response(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        response = {"ok": False, "error": message}
        if suggestion:
            response["suggestion"] = suggestion
        if extra:
            response.update(extra)
        return response


def _write_path_policy(repo_root: Path, *, private_prefix: Path | None = None) -> None:
    config_dir = repo_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        yaml.safe_dump(
            {
                "repo_slug": "repo",
                "path_policy": {
                    "enabled": True,
                    "detect_absolute_unknown_keys": True,
                    "rules": [
                        {
                            "label": "repo",
                            "private_prefix": str(private_prefix or repo_root),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def _project(repo_root: Path) -> dict:
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "name": "test-project",
        "root": str(repo_root),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs_dir": str(docs_dir),
        "docs": {"PLAN": str(docs_dir / "PLAN.md")},
        "defaults": {"agent": "test-agent"},
    }


def _install_append_context(monkeypatch: pytest.MonkeyPatch, project: dict) -> None:
    context = LoggingContext(
        tool_name="append_entry",
        project=project,
        recent_projects=[project["name"]],
        state_snapshot={},
        reminders=[],
    )

    async def resolve_context(**_kwargs: object) -> LoggingContext:
        return context

    monkeypatch.setattr(append_entry_module, "resolve_logging_context", resolve_context)
    monkeypatch.setattr(server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(server_module, "get_agent_identity", lambda: None)
    monkeypatch.setattr(server_module, "storage_backend", None)
    monkeypatch.setattr(
        server_module,
        "state_manager",
        SimpleNamespace(
            record_tool=AsyncMock(return_value={}),
            update_project_activity=AsyncMock(return_value=None),
            set_current_project=AsyncMock(return_value=None),
        ),
    )


def _read_doc_update_log(project: dict) -> str:
    log_path = Path(project["docs_dir"]) / "DOC_LOG.md"
    if not log_path.exists():
        return ""
    return log_path.read_text(encoding="utf-8")


def _safe_payload(payload: object) -> str:
    return json.dumps(payload, sort_keys=True)


async def test_special_create_generated_file_path_maps_before_doc_update_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_append_context(monkeypatch, project)
    monkeypatch.setattr(
        special_create_module,
        "resolve_authoritative_write_scope",
        lambda **_kwargs: {"authoritative_session_id": "session", "resolved_scope": None},
    )

    result = await special_create_module.handle_special_document_creation(
        project=project,
        action="create_review_report",
        doc_name="pkg-2-2",
        target_dir=None,
        content="# Package 2.2\n",
        metadata={"stage": "generated path policy"},
        dry_run=False,
        agent_id="test-agent",
        storage_backend=None,
        helper=_Helper(),
        context=SimpleNamespace(),
        project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
        logger=logging.getLogger(__name__),
    )

    assert result["ok"] is True
    raw_path = result["path"]
    written = _read_doc_update_log(project)
    assert "file_path=repo/.scribe/docs/dev_plans/test_project/" in written
    assert raw_path not in written
    assert "log_warning" not in result


async def test_special_create_generated_file_path_rejects_with_safe_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root, private_prefix=repo_root / "allowed")
    project = _project(repo_root)
    _install_append_context(monkeypatch, project)
    monkeypatch.setattr(
        special_create_module,
        "resolve_authoritative_write_scope",
        lambda **_kwargs: {"authoritative_session_id": "session", "resolved_scope": None},
    )

    result = await special_create_module.handle_special_document_creation(
        project=project,
        action="create_review_report",
        doc_name="pkg-2-2",
        target_dir=None,
        content="# Package 2.2\n",
        metadata={"stage": "generated path policy"},
        dry_run=False,
        agent_id="test-agent",
        storage_backend=None,
        helper=_Helper(),
        context=SimpleNamespace(),
        project_registry=SimpleNamespace(record_doc_update=lambda **_kwargs: None),
        logger=logging.getLogger(__name__),
    )

    assert result["ok"] is True
    assert Path(result["path"]).exists()
    assert result["log_warning"].startswith("doc_update_log_rejected:path_policy_rejected")
    assert _read_doc_update_log(project) == ""
    payload = _safe_payload(result)
    assert result["path"] not in result["log_warning"]
    assert "/allowed" not in payload


async def test_edit_generated_path_maps_before_doc_update_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_append_context(monkeypatch, project)
    changed_path = Path(project["docs"]["PLAN"])
    changed_path.write_text("# Plan\n", encoding="utf-8")

    async def apply_doc_change(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            path=changed_path,
            diff_preview="",
            before_hash="before",
            after_hash="after",
            extra={},
            error_message="",
            verification_passed=True,
            file_size_before=1,
            file_size_after=2,
            content_written="# Plan\n",
        )

    result = await edit_module.handle_edit_action(
        action="replace_section",
        project=project,
        doc_name="PLAN",
        doc_category="dev_plans",
        section="status",
        content="done",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=SimpleNamespace(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=apply_doc_change,
        get_or_create_storage_project=AsyncMock(),
        append_entry=append_entry_module.append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), [], []),
        index_doc_for_vector=AsyncMock(),
        vector_indexing_enabled=lambda _project: False,
        get_index_updater_for_path=lambda *_args, **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda *_args, **_kwargs: None),
        server_module=server_module,
        logger=logging.getLogger(__name__),
    )

    assert result["ok"] is True
    written = _read_doc_update_log(project)
    assert "path=repo/.scribe/docs/dev_plans/test_project/PLAN.md" in written
    assert str(changed_path) not in written
    assert "log_warning" not in result


async def test_edit_generated_path_rejects_with_safe_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root, private_prefix=repo_root / "allowed")
    project = _project(repo_root)
    _install_append_context(monkeypatch, project)
    changed_path = Path(project["docs"]["PLAN"])
    changed_path.parent.mkdir(parents=True, exist_ok=True)
    changed_path.write_text("# Plan\n", encoding="utf-8")

    async def apply_doc_change(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            path=changed_path,
            diff_preview="",
            before_hash="before",
            after_hash="after",
            extra={},
            error_message="",
            verification_passed=True,
            file_size_before=1,
            file_size_after=2,
            content_written="# Plan\n",
        )

    result = await edit_module.handle_edit_action(
        action="replace_section",
        project=project,
        doc_name="PLAN",
        doc_category="dev_plans",
        section="status",
        content="done",
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=SimpleNamespace(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=apply_doc_change,
        get_or_create_storage_project=AsyncMock(),
        append_entry=append_entry_module.append_entry,
        normalize_metadata_with_healing=lambda metadata: (dict(metadata or {}), [], []),
        index_doc_for_vector=AsyncMock(),
        vector_indexing_enabled=lambda _project: False,
        get_index_updater_for_path=lambda *_args, **_kwargs: None,
        project_registry=SimpleNamespace(record_doc_update=lambda *_args, **_kwargs: None),
        server_module=server_module,
        logger=logging.getLogger(__name__),
    )

    assert result["ok"] is True
    assert result["log_warning"].startswith("doc_update_log_rejected:path_policy_rejected")
    assert _read_doc_update_log(project) == ""
    payload = _safe_payload(result)
    assert str(changed_path) in result["path"]
    assert str(changed_path) not in result["log_warning"]
    assert "/allowed" not in payload
