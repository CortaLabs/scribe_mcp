from __future__ import annotations

import importlib
import asyncio
import sys
import types
from pathlib import Path

import pytest

from scribe_mcp.doc_management import utils as utils_shared


def _load_special_create_module(monkeypatch: pytest.MonkeyPatch):
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
    module = importlib.import_module("scribe_mcp.doc_management.special_create")
    return importlib.reload(module)


def test_extract_case_registry_metadata_from_bug_report(tmp_path: Path) -> None:
    project_root = tmp_path
    report_path = project_root / "docs" / "bugs" / "runtime" / "2026-04-17_BUG-2026-04-17-0001" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "---\n"
        "doc_type: bug\n"
        "category: runtime\n"
        "case_id: BUG-2026-04-17-0001\n"
        "status: INVESTIGATING\n"
        "severity: high\n"
        "title: Runtime crash\n"
        "---\n\n"
        "# Bug Report\n",
        encoding="utf-8",
    )

    payload = utils_shared.extract_case_registry_metadata_from_report(
        report_path,
        project_root=project_root,
        project={"name": "demo", "root": str(project_root), "project_key": "k1", "repo_id": "r1"},
    )

    assert payload is not None
    assert payload["case_id"] == "BUG-2026-04-17-0001"
    assert payload["case_type"] == "bug"
    assert payload["status"] == "open"
    assert payload["category"] == "runtime"
    assert payload["project_key"] == "k1"
    assert payload["repo_id"] == "r1"


def test_build_case_registry_backfill_records_covers_bug_and_security(tmp_path: Path) -> None:
    project_root = tmp_path
    bug_report = project_root / "docs" / "bugs" / "logic" / "2026-04-17_BUG-2026-04-17-0002" / "report.md"
    sec_report = project_root / "docs" / "security" / "auth" / "2026-04-17_SEC-2026-04-17-0003" / "report.md"

    bug_report.parent.mkdir(parents=True, exist_ok=True)
    sec_report.parent.mkdir(parents=True, exist_ok=True)

    bug_report.write_text("---\ncase_id: BUG-2026-04-17-0002\nstatus: OPEN\n---\n\n# Bug\n", encoding="utf-8")
    sec_report.write_text("---\ncase_id: SEC-2026-04-17-0003\nstatus: CLOSED\n---\n\n# Security\n", encoding="utf-8")

    records = utils_shared.build_case_registry_backfill_records(project_root)

    assert len(records) == 2
    by_id = {record["case_id"]: record for record in records}
    assert by_id["BUG-2026-04-17-0002"]["case_type"] == "bug"
    assert by_id["BUG-2026-04-17-0002"]["status"] == "open"
    assert by_id["SEC-2026-04-17-0003"]["case_type"] == "security"
    assert by_id["SEC-2026-04-17-0003"]["status"] == "closed"


def test_register_case_in_shared_registry_uses_single_storage_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    special_create_shared = _load_special_create_module(monkeypatch)
    report_path = tmp_path / "docs" / "bugs" / "logic" / "2026-04-17_BUG-2026-04-17-0010" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("---\ncase_id: BUG-2026-04-17-0010\nstatus: open\n---\n\n# Bug\n", encoding="utf-8")

    captured: list[dict[str, object]] = []

    class DummyStorage:
        async def upsert_case_registry_record(self, **kwargs: object) -> None:
            captured.append(kwargs)

    warning = asyncio.run(
        special_create_shared._register_case_in_shared_registry(
            DummyStorage(),
            project={"name": "demo", "root": str(tmp_path), "project_key": "pkey", "repo_id": "rid"},
            target_path=report_path,
            metadata={"doc_type": "bug_report", "case_id": "BUG-2026-04-17-0010"},
            doc_label="bug_report",
        )
    )

    assert warning is None
    assert len(captured) == 1
    assert captured[0]["case_type"] == "bug"
    assert captured[0]["case_id"] == "BUG-2026-04-17-0010"
    assert captured[0]["doc_path"] == str(report_path.resolve())
    assert captured[0]["metadata"]["category"] == "logic"


def test_build_case_registry_upsert_kwargs_merges_metadata_namespaces() -> None:
    existing_record = {
        "case_id": "BUG-2026-04-17-0099",
        "case_type": "bug",
        "project_name": "demo",
        "repo_root": "/repo",
        "doc_type": "bug_report",
        "doc_name": "BUG-2026-04-17-0099",
        "doc_path": "/repo/docs/bugs/runtime/report.md",
        "title": "Existing title",
        "status": "open",
        "severity": "high",
        "metadata": {
            "category": "runtime",
            "reported_at": "2026-04-17T00:00:00Z",
            "ownership": {"resolution_source": "set_project"},
        },
    }
    kwargs = utils_shared.build_case_registry_upsert_kwargs(
        existing_record=existing_record,
        overrides={"source_tool": "link_fix"},
        metadata_overrides={
            "ownership": {"project_name_provenance": "resolved_scope"},
            "fix_link": {"artifact_ref": "src/app.py:12"},
            "execution_provenance": {"execution_id": "exec-1"},
        },
    )

    assert kwargs is not None
    assert kwargs["status"] == "open"
    assert kwargs["severity"] == "high"
    assert kwargs["metadata"]["category"] == "runtime"
    assert kwargs["metadata"]["reported_at"] == "2026-04-17T00:00:00Z"
    assert kwargs["metadata"]["ownership"]["resolution_source"] == "set_project"
    assert kwargs["metadata"]["ownership"]["project_name_provenance"] == "resolved_scope"
    assert kwargs["metadata"]["fix_link"]["artifact_ref"] == "src/app.py:12"


def test_register_case_in_shared_registry_warns_when_storage_interface_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    special_create_shared = _load_special_create_module(monkeypatch)
    report_path = tmp_path / "docs" / "security" / "auth" / "2026-04-17_SEC-2026-04-17-0011" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("---\ncase_id: SEC-2026-04-17-0011\n---\n\n# Security\n", encoding="utf-8")

    class DummyStorage:
        pass

    warning = asyncio.run(
        special_create_shared._register_case_in_shared_registry(
            DummyStorage(),
            project={"name": "demo", "root": str(tmp_path)},
            target_path=report_path,
            metadata={"doc_type": "security_report", "case_id": "SEC-2026-04-17-0011"},
            doc_label="security_report",
        )
    )

    assert warning is not None
    assert "shared case registration method" in warning


def test_call_case_registry_method_surfaces_backend_type_error_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    special_create_shared = _load_special_create_module(monkeypatch)
    calls = {"count": 0}

    def _backend(**_kwargs: object) -> None:
        calls["count"] += 1
        raise TypeError("backend serialization failed")

    with pytest.raises(TypeError, match="backend serialization failed"):
        asyncio.run(
            special_create_shared._call_case_registry_method(
                _backend,
                {"case_id": "BUG-2026-04-18-0001"},
            )
        )

    assert calls["count"] == 1
