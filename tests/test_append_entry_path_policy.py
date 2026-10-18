from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools import append_entry as append_entry_module


pytestmark = pytest.mark.asyncio


def _as_dict(result: object) -> dict:
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    return {}


def _write_path_policy(repo_root: Path, *, detect_unknown: bool = True) -> None:
    config_dir = repo_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        yaml.safe_dump(
            {
                "repo_slug": "repo",
                "path_policy": {
                    "enabled": True,
                    "detect_absolute_unknown_keys": detect_unknown,
                    "rules": [
                        {
                            "label": "repo",
                            "private_prefix": str(repo_root),
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
        "defaults": {"agent": "test-agent"},
    }


def _install_context(monkeypatch: pytest.MonkeyPatch, project: dict) -> None:
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
    monkeypatch.setattr(
        server_module,
        "state_manager",
        SimpleNamespace(
            record_tool=AsyncMock(return_value={}),
            update_project_activity=AsyncMock(return_value=None),
        ),
    )


async def test_single_append_maps_configured_path_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    monkeypatch.setattr(server_module, "storage_backend", None)

    raw_path = repo_root / "docs" / "plan.md"
    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="mapped path",
            meta={"path": str(raw_path), "phase": "one"},
            format="structured",
        )
    )

    assert result["ok"] is True
    assert result["meta"]["path"] == "repo/docs/plan.md"
    assert result["meta"]["phase"] == "one"
    written = Path(project["progress_log"]).read_text(encoding="utf-8")
    assert "path=repo/docs/plan.md" in written
    assert str(raw_path) not in written


async def test_unmapped_path_rejects_before_write_and_db_mirror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    raw_path = "/private/unmapped/project/file.txt"
    append_line = AsyncMock()
    backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project["name"])),
        upsert_project=AsyncMock(),
        insert_entry=AsyncMock(),
    )
    monkeypatch.setattr(append_entry_module, "append_line", append_line)
    monkeypatch.setattr(server_module, "storage_backend", backend)

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="reject me",
            meta={"file_path": raw_path},
            format="structured",
        )
    )

    assert result["ok"] is False
    assert result["issue_code"] == "path_policy_rejected"
    assert result["issues"][0]["metadata_key"] == "file_path"
    append_line.assert_not_awaited()
    backend.insert_entry.assert_not_awaited()
    assert not Path(project["progress_log"]).exists()
    payload = json.dumps(result, sort_keys=True)
    assert raw_path not in payload
    assert "/private/unmapped" not in payload


async def test_bulk_items_list_applies_same_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    monkeypatch.setattr(server_module, "storage_backend", None)
    rejected_path = "/private/outside/rejected.txt"

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="",
            items_list=[
                {"message": "mapped", "meta": {"path": str(repo_root / "ok.txt")}},
                {"message": "rejected", "meta": {"path": rejected_path}},
            ],
            format="structured",
        )
    )

    assert result["bulk_mode"] is True
    assert result["successful"] == 1
    assert result["failed"] == 1
    assert result["written_count"] == 1
    assert "path=repo/ok.txt" in result["written_lines"][0]
    failed_payload = json.dumps(result["failed_items"], sort_keys=True)
    assert "path_policy_rejected" in failed_payload
    assert rejected_path not in failed_payload
    written = Path(project["progress_log"]).read_text(encoding="utf-8")
    assert "path=repo/ok.txt" in written
    assert rejected_path not in written


async def test_unknown_structured_path_key_is_governed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root, detect_unknown=True)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    monkeypatch.setattr(server_module, "storage_backend", None)
    raw_path = "/private/outside/unknown-key.txt"

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="unknown key",
            meta={"surprise": raw_path},
            format="structured",
        )
    )

    assert result["ok"] is False
    assert result["issues"][0]["metadata_key"] == "surprise"
    payload = json.dumps(result, sort_keys=True)
    assert raw_path not in payload
    assert "/private/outside" not in payload


async def test_rejection_diagnostics_sanitize_unsafe_metadata_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root, detect_unknown=True)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    monkeypatch.setattr(server_module, "storage_backend", None)
    raw_key = "/private/key/name"
    raw_path = "/private/value/name.txt"

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="unsafe key",
            meta={raw_key: raw_path},
            format="structured",
        )
    )

    assert result["ok"] is False
    assert result["issues"][0]["metadata_key"].startswith("unsafe_key:")
    assert result["issues"][0]["safe_descriptor"] == "local_absolute_path"
    payload = json.dumps(result, sort_keys=True)
    assert raw_key not in payload
    assert raw_path not in payload
    assert "/private/" not in payload


async def test_clean_non_path_metadata_preserves_append_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    monkeypatch.setattr(server_module, "storage_backend", None)

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="clean metadata",
            meta={"phase": "one", "count": 3},
            format="structured",
        )
    )

    assert result["ok"] is True
    assert result["meta"]["phase"] == "one"
    assert result["meta"]["count"] == "3"
    written = Path(project["progress_log"]).read_text(encoding="utf-8")
    assert "phase=one" in written
    assert "count=3" in written
