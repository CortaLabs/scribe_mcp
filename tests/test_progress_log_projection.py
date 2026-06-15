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
from scribe_mcp.tools import progress_log_projection as projection_module

pytestmark = pytest.mark.asyncio


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
    }


def _install_context(monkeypatch: pytest.MonkeyPatch, project: dict) -> None:
    context = LoggingContext(
        tool_name="progress_log_projection",
        project=project,
        recent_projects=[project["name"]],
        state_snapshot={},
        reminders=[],
    )

    async def resolve_context(**_kwargs: object) -> LoggingContext:
        return context

    monkeypatch.setattr(projection_module, "resolve_logging_context", resolve_context)


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
    monkeypatch.setattr(
        server_module,
        "state_manager",
        SimpleNamespace(
            record_tool=AsyncMock(return_value={}),
            update_project_activity=AsyncMock(return_value=None),
        ),
    )


def _write_log(project: dict, line: str, *, log_type: str = "progress") -> Path:
    if log_type == "doc_updates":
        path = Path(project["docs_dir"]) / "DOC_LOG.md"
    else:
        path = Path(project["progress_log"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line + "\n", encoding="utf-8")
    return path


async def test_projection_does_not_mutate_canonical_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    log_path = _write_log(
        project,
        f"[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] mapped | path={repo_root / 'docs' / 'plan.md'}",
    )
    before = log_path.read_bytes()

    result = await projection_module.progress_log_projection(agent="test-agent", mode="render")

    assert log_path.read_bytes() == before
    assert result["canonical_mutated"] is False
    assert result["log_ref"] == ".scribe/docs/dev_plans/test_project/PROGRESS_LOG.md"


async def test_render_output_and_failed_diagnostics_hide_raw_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    raw_path = "/private/outside/secret.txt"
    _write_log(
        project,
        f"[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] blocked | file_path={raw_path}",
    )

    result = await projection_module.progress_log_projection(agent="test-agent", mode="render")
    payload = json.dumps(result, sort_keys=True)

    assert result["ok"] is False
    assert result["readiness"] == "failed"
    assert result["contains_raw_local_paths"] is True
    assert result["issues"][0]["metadata_key"] == "file_path"
    assert result["issues"][0]["issue_code"] == "unmapped_absolute_path"
    assert raw_path not in payload
    assert "/private/outside" not in payload
    assert "canonical_path" not in payload


async def test_unmapped_path_blocks_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    _write_log(
        project,
        "[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] blocked | path=/unmapped/outside.txt",
    )

    result = await projection_module.progress_log_projection(agent="test-agent", mode="readiness")

    assert result["ok"] is False
    assert result["readiness"] == "failed"
    assert result["issue_count"] == 1
    assert "projected_lines" not in result


async def test_mapped_path_renders_label_safe_output_for_doc_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    raw_path = repo_root / "docs" / "managed.md"
    _write_log(
        project,
        f"[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] doc update | path={raw_path}",
        log_type="doc_updates",
    )

    result = await projection_module.progress_log_projection(
        agent="test-agent",
        log_type="doc_updates",
        mode="render",
    )

    assert result["ok"] is True
    assert result["readiness"] == "ready"
    assert result["projected_lines"] == [
        "[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] doc update | path=repo/docs/managed.md"
    ]
    assert str(raw_path) not in json.dumps(result)


async def test_repeated_projection_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    _write_log(
        project,
        "[ℹ️] [2026-06-15 10:00:00 UTC] [Agent: test-agent] [Project: test-project] clean | path=repo/docs/plan.md",
    )

    first = await projection_module.progress_log_projection(agent="test-agent", mode="render")
    second = await projection_module.progress_log_projection(agent="test-agent", mode="render")

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["projected_lines"] == first["projected_lines"]


async def test_append_mapping_then_projection_is_idempotent_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "home" / "austin" / "projects" / "MCP_SPINE" / "scribe_mcp"
    repo_root.mkdir(parents=True)
    _write_path_policy(repo_root)
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    _install_append_context(monkeypatch, project)
    backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project["name"])),
        upsert_project=AsyncMock(),
        insert_entry=AsyncMock(),
    )
    monkeypatch.setattr(server_module, "storage_backend", backend)
    raw_path = repo_root / "docs" / "runtime-proof.md"

    append_result = await append_entry_module.append_entry(
        agent="test-agent",
        message="runtime metadata proof",
        meta={"path": str(raw_path), "phase": "package-3-1"},
        format="structured",
    )

    assert append_result["ok"] is True
    assert append_result["meta"]["path"] == "repo/docs/runtime-proof.md"
    backend.insert_entry.assert_awaited_once()
    mirror_kwargs = backend.insert_entry.await_args.kwargs
    assert mirror_kwargs["meta"]["path"] == "repo/docs/runtime-proof.md"
    assert str(raw_path) not in json.dumps(mirror_kwargs["meta"], sort_keys=True)

    log_path = Path(project["progress_log"])
    canonical_after_append = log_path.read_bytes()
    first_projection = await projection_module.progress_log_projection(agent="test-agent", mode="render")
    second_projection = await projection_module.progress_log_projection(agent="test-agent", mode="render")

    assert log_path.read_bytes() == canonical_after_append
    assert first_projection["canonical_mutated"] is False
    assert first_projection["ok"] is True
    assert first_projection["readiness"] == "ready"
    assert first_projection["projected_lines"] == second_projection["projected_lines"]
    assert "path=repo/docs/runtime-proof.md" in first_projection["projected_lines"][0]
    assert str(raw_path) not in json.dumps(first_projection, sort_keys=True)

    unmapped_path = "/home/austin/not-this-repo/secret.md"
    rejected = await append_entry_module.append_entry(
        agent="test-agent",
        message="rejected metadata proof",
        meta={"path": unmapped_path},
        format="structured",
    )
    rejected_payload = json.dumps(rejected, sort_keys=True)

    assert rejected["ok"] is False
    assert rejected["issue_code"] == "path_policy_rejected"
    assert unmapped_path not in rejected_payload
    assert "/home/austin/not-this-repo" not in rejected_payload
    assert log_path.read_bytes() == canonical_after_append
    backend.insert_entry.assert_awaited_once()

    readiness_after_rejection = await projection_module.progress_log_projection(
        agent="test-agent",
        mode="readiness",
    )
    assert readiness_after_rejection["ok"] is True
    assert readiness_after_rejection["issue_count"] == 0


async def test_registry_exposes_progress_log_projection_tool() -> None:
    from scribe_mcp.tools import ensure_tool_loaded, tool_module_for_name

    assert tool_module_for_name("progress_log_projection") == "progress_log_projection"
    assert ensure_tool_loaded("progress_log_projection") is True
