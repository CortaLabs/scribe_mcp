from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scribe_mcp.storage.models import CaseRegistryRecord, compute_project_key, compute_repo_id, normalize_repo_root
from scribe_mcp.tools import backfill_case_registry as backfill_module


@dataclass
class _Project:
    name: str
    root: str
    docs_json: str | None = None


class _Backend:
    def __init__(
        self,
        *,
        project: _Project | None = None,
        records: list[CaseRegistryRecord] | None = None,
    ) -> None:
        self.project = project
        self.records = records or []
        self.upserts: list[dict[str, object]] = []

    async def fetch_project(self, name: str) -> _Project | None:
        if self.project is not None and self.project.name == name:
            return self.project
        return None

    async def query_case_registry_records(
        self,
        *,
        repo_root: str | None = None,
        project_name: str | None = None,
        case_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CaseRegistryRecord]:
        filtered = [
            record
            for record in self.records
            if (repo_root is None or record.repo_root == normalize_repo_root(repo_root))
            and (project_name is None or record.project_name == project_name)
            and (case_type is None or record.case_type == case_type)
        ]
        return filtered[offset : offset + limit]

    async def upsert_case_registry_record(self, **kwargs: object) -> None:
        self.upserts.append(kwargs)


def _bind_tool_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: _Backend,
    repo_root: Path,
    project_name: str | None = "demo",
) -> None:
    context = SimpleNamespace(
        mode="local",
        resolved_scope=SimpleNamespace(repo_root=str(repo_root), project_name=project_name),
    )
    monkeypatch.setattr(
        backfill_module,
        "server_module",
        SimpleNamespace(storage_backend=backend, get_execution_context=lambda: context),
    )


def _write_report(
    repo_root: Path,
    *,
    folder: str = "bugs",
    category: str = "logic",
    case_id: str = "BUG-2026-06-25-0001",
    status: str = "open",
    project_name: str | None = None,
) -> Path:
    report_path = repo_root / ".scribe" / "docs" / folder / category / f"2026-06-25_{case_id}" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    project_line = f"project_name: {project_name}\n" if project_name else ""
    report_path.write_text(
        "---\n"
        f"case_id: {case_id}\n"
        f"status: {status}\n"
        f"{project_line}"
        "severity: high\n"
        "title: Backfill candidate\n"
        "---\n\n"
        "# Case\n",
        encoding="utf-8",
    )
    return report_path


def _record(
    *,
    repo_root: Path,
    project_name: str,
    case_id: str,
    doc_path: str,
    status: str = "open",
    metadata: dict[str, Any] | None = None,
) -> CaseRegistryRecord:
    normalized_root = normalize_repo_root(str(repo_root))
    return CaseRegistryRecord(
        case_id=case_id,
        case_type="bug",
        project_name=project_name,
        repo_root=normalized_root,
        repo_id=compute_repo_id(normalized_root),
        project_key=compute_project_key(repo_root=normalized_root, project_name=project_name),
        doc_type="bug_report",
        doc_name=case_id,
        doc_path=doc_path,
        status=status,
        metadata=metadata,
    )


def test_backfill_case_registry_dry_run_reports_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _write_report(tmp_path, case_id="BUG-2026-06-25-0101")
    backend = _Backend(project=_Project(name="demo", root=str(tmp_path)))
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path)

    result = asyncio.run(backfill_module.backfill_case_registry())

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["would_upsert"] == 1
    assert result["operator_review_required"] is False
    assert backend.upserts == []
    assert result["records"][0]["case_id"] == "BUG-2026-06-25-0101"
    assert result["records"][0]["doc_path"] == str(report_path.resolve())


def test_backfill_case_registry_merges_same_path_aliases_from_project_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = "BUG-2026-06-25-0102"
    report_path = _write_report(tmp_path, case_id=case_id)
    docs = {
        case_id: str(report_path.resolve()),
        "caller_alias": str(report_path.resolve()),
        f"bug_report_{report_path.stem}": str(report_path.resolve()),
    }
    existing = _record(
        repo_root=tmp_path,
        project_name="demo",
        case_id=case_id,
        doc_path=str(report_path.resolve()),
        metadata={
            "doc_binding": {
                "canonical_doc_name": case_id,
                "canonical_doc_path": str(report_path.resolve()),
                "aliases": [{"alias": case_id, "alias_kind": "primary", "doc_path": str(report_path.resolve())}],
            }
        },
    )
    backend = _Backend(
        project=_Project(name="demo", root=str(tmp_path), docs_json=json.dumps(docs)),
        records=[existing],
    )
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path)

    result = asyncio.run(backfill_module.backfill_case_registry())

    assert result["would_update_aliases"] == 1
    record = result["records"][0]
    assert record["action"] == "update_aliases"
    assert record["alias_update"] is True
    assert set(record["aliases"]) >= {case_id, "caller_alias", f"bug_report_{report_path.stem}", str(report_path.resolve())}


def test_backfill_case_registry_requires_review_for_same_scope_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = "BUG-2026-06-25-0103"
    _write_report(tmp_path, case_id=case_id, category="logic")
    _write_report(tmp_path, case_id=case_id, category="runtime")
    backend = _Backend(project=_Project(name="demo", root=str(tmp_path)))
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path)

    result = asyncio.run(backfill_module.backfill_case_registry())

    assert result["ok"] is False
    assert result["operator_review_required"] is True
    assert len(result["collisions"]) == 1
    assert result["collisions"][0]["case_id"] == case_id
    assert backend.upserts == []


def test_backfill_case_registry_preserves_scoped_duplicate_case_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = "BUG-2026-06-25-0104"
    _write_report(tmp_path, case_id=case_id, category="alpha", project_name="alpha")
    _write_report(tmp_path, case_id=case_id, category="beta", project_name="beta")
    backend = _Backend()
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path, project_name=None)

    result = asyncio.run(backfill_module.backfill_case_registry(project=None))

    assert result["operator_review_required"] is False
    assert result["would_upsert"] == 2
    assert {record["project_name"] for record in result["records"]} == {"alpha", "beta"}
    assert len({record["project_key"] for record in result["records"]}) == 2


def test_backfill_case_registry_preserves_terminal_registry_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = "BUG-2026-06-25-0105"
    report_path = _write_report(tmp_path, case_id=case_id, status="open")
    existing = _record(
        repo_root=tmp_path,
        project_name="demo",
        case_id=case_id,
        doc_path=str(report_path.resolve()),
        status="resolved",
    )
    backend = _Backend(project=_Project(name="demo", root=str(tmp_path)), records=[existing])
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path)

    result = asyncio.run(backfill_module.backfill_case_registry())

    assert result["records"][0]["status"] == "resolved"
    assert result["records"][0]["action"] == "update_aliases"
    assert result["records"][0]["alias_update"] is True
    assert backend.upserts == []


def test_backfill_case_registry_refuses_apply_in_first_wave(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_report(tmp_path, case_id="BUG-2026-06-25-0106")
    backend = _Backend(project=_Project(name="demo", root=str(tmp_path)))
    _bind_tool_context(monkeypatch, backend=backend, repo_root=tmp_path)

    result = asyncio.run(backfill_module.backfill_case_registry(apply=True))

    assert result["ok"] is False
    assert result["dry_run"] is False
    assert result["operator_review_required"] is True
    assert result["skipped"][0]["reason"] == "apply_not_implemented"
    assert backend.upserts == []
