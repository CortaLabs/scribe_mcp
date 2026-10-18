from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.physical_logical_reconciliation import (
    _count_classification,
    build_physical_logical_reconciliation,
)
from scribe_mcp.storage.models import ProjectRecord


class _ReadOnlyBackend:
    def __init__(self, repo_root: Path) -> None:
        self.projects = [
            ProjectRecord(
                id=1,
                name="demo",
                repo_root=str(repo_root),
                progress_log_path=str(repo_root / ".scribe" / "docs" / "dev_plans" / "demo" / "PROGRESS_LOG.md"),
            ),
            ProjectRecord(
                id=2,
                name="logical_only",
                repo_root=str(repo_root),
                progress_log_path=str(repo_root / ".scribe" / "docs" / "dev_plans" / "logical_only" / "PROGRESS_LOG.md"),
            ),
        ]
        self.fetchall_calls = 0
        self.count_entries_calls = 0

    async def list_projects_by_repo(self, repo_root: str):
        return [project for project in self.projects if project.repo_root == repo_root]

    async def count_entries(self, project: ProjectRecord, filters=None):
        self.count_entries_calls += 1
        if project.name == "logical_only":
            return 3
        return 0

    async def _fetchall(self, query: str, params: tuple):
        self.fetchall_calls += 1
        if "FROM dev_plans" in query:
            project_id = params[0]
            if project_id == 1:
                return [
                    {
                        "project_id": 1,
                        "project_name": "demo",
                        "plan_type": "architecture",
                        "file_path": "/repo/demo/ARCHITECTURE_GUIDE.md",
                    }
                ]
            if project_id == 2:
                return [
                    {
                        "project_id": 2,
                        "project_name": "logical_only",
                        "plan_type": "phase_plan",
                        "file_path": str(Path(self.projects[1].progress_log_path).parent / "PHASE_PLAN.md"),
                    }
                ]
        if "FROM tool_calls" in query:
            return [{"project_name": "logical_only", "count": 2}]
        return []


def _write_project(repo_root: Path, slug: str) -> Path:
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / slug
    docs_dir.mkdir(parents=True)
    (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Progress\n- one\n- two\n", encoding="utf-8")
    (docs_dir / "TOOL_LOG.jsonl").write_text('{"tool":"set_project"}\n', encoding="utf-8")
    return docs_dir


def test_count_classification_flags_nonzero_physical_count_drift() -> None:
    assert (
        _count_classification(
            project_name="demo",
            projects_by_name={},
            physical_present=True,
            physical_count=2,
            logical_count=1,
        )
        == "missing_logical_rows"
    )
    assert (
        _count_classification(
            project_name="demo",
            projects_by_name={},
            physical_present=True,
            physical_count=5,
            logical_count=3,
        )
        == "missing_logical_rows"
    )


def test_count_classification_flags_nonzero_logical_count_drift() -> None:
    assert (
        _count_classification(
            project_name="demo",
            projects_by_name={},
            physical_present=True,
            physical_count=1,
            logical_count=2,
        )
        == "logical_only"
    )


@pytest.mark.asyncio
async def test_reconciliation_classifies_physical_logical_drift(tmp_path: Path) -> None:
    docs_dir = _write_project(tmp_path, "demo")
    orphan_docs_dir = _write_project(tmp_path, "orphan")
    backend = _ReadOnlyBackend(tmp_path)

    report = await build_physical_logical_reconciliation(
        repo_root=tmp_path,
        storage_backend=backend,
        project_configs={
            "demo": {
                "name": "demo",
                "root": str(tmp_path),
                "docs_dir": str(docs_dir),
                "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            },
            "orphan": {
                "name": "orphan",
                "root": str(tmp_path),
                "docs_dir": str(orphan_docs_dir),
                "progress_log": str(orphan_docs_dir / "PROGRESS_LOG.md"),
            },
        },
    )

    assert report["schema_version"] == "physical-logical-reconciliation.v1"
    assert report["read_only"] is True
    classifications = {item["classification"] for item in report["items"]}
    assert {"consistent", "physical_only", "logical_only", "missing_logical_rows"} <= classifications

    phase_doc = _find_item(report, kind="core_plan_doc", project="demo", plan_type="phase_plan")
    assert phase_doc["classification"] == "missing_logical_rows"

    progress = _find_item(report, kind="progress_log_entries", project="demo")
    assert progress["physical_count"] == 2
    assert progress["logical_count"] == 0
    assert progress["classification"] == "missing_logical_rows"

    tool_calls = _find_item(report, kind="tool_calls", project="demo")
    assert tool_calls["physical_count"] == 1
    assert tool_calls["logical_count"] == 0
    assert tool_calls["classification"] == "missing_logical_rows"

    logical_progress = _find_item(report, kind="progress_log_entries", project="logical_only")
    assert logical_progress["classification"] == "logical_only"


@pytest.mark.asyncio
async def test_reconciliation_repeat_run_has_no_file_or_backend_count_side_effects(tmp_path: Path) -> None:
    docs_dir = _write_project(tmp_path, "demo")
    backend = _ReadOnlyBackend(tmp_path)
    before_files = _file_snapshot(tmp_path)
    before_count_calls = backend.count_entries_calls

    kwargs = {
        "repo_root": tmp_path,
        "storage_backend": backend,
        "project_configs": {
            "demo": {
                "name": "demo",
                "root": str(tmp_path),
                "docs_dir": str(docs_dir),
                "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            }
        },
    }
    first = await build_physical_logical_reconciliation(**kwargs)
    second = await build_physical_logical_reconciliation(**kwargs)

    assert first["summary"] == second["summary"]
    assert _file_snapshot(tmp_path) == before_files
    assert backend.count_entries_calls == before_count_calls + 4


def _find_item(report: dict, **criteria: object) -> dict:
    for item in report["items"]:
        if all(item.get(key) == value for key, value in criteria.items()):
            return item
    raise AssertionError(f"Missing item for {criteria!r}")


def _file_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path.relative_to(root))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot
