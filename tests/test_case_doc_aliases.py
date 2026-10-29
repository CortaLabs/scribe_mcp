from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from scribe_mcp.doc_management.utils import build_case_registry_upsert_kwargs
from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from test_manage_docs_create_intent import (
    _call_manage_docs,
    _isolated_server,
    _read_persisted_project,
)


@pytest_asyncio.fixture
async def case_alias_backend(tmp_path: Path) -> AsyncIterator[SQLiteStorage]:
    backend = SQLiteStorage(tmp_path / "case_aliases.db")
    try:
        # Finish schema initialization before the stdio process opens this database.
        await backend.setup()
        yield backend
    finally:
        await backend.close()


@pytest.mark.asyncio
@pytest.mark.regression
async def test_case_report_aliases_bind_to_one_canonical_doc_and_registry_row(
    tmp_path: Path, test_agent: str, case_alias_backend: SQLiteStorage
) -> None:
    project_root = (tmp_path / "case_doc_alias_repo").resolve()
    project_root.mkdir()
    project_name = "case_doc_alias_project"
    backend = case_alias_backend
    state_manager = StateManager(path=tmp_path / "state.json", storage_backend=backend)
    case_id = "BUG-2026-06-25-0001"
    caller_alias = "runtime-alias-binding"

    content = "\n".join(
        [
            "# Runtime Alias Binding",
            "",
            "## Symptoms",
            "<!-- ID: symptoms -->",
            "Initial symptoms.",
            "",
            "## Fix",
            "<!-- ID: fix -->",
            "Pending fix.",
            "",
        ]
    )

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=project_name, agent=test_agent
    ) as client:
        async def manage_docs(**arguments: Any) -> dict[str, Any]:
            return await _call_manage_docs(client, test_agent, **arguments)

        async def read_case() -> dict[str, Any]:
            record = await backend.fetch_case_registry_record(
                case_id, repo_root=str(project_root), project_name=project_name
            )
            assert record is not None
            return vars(record)

        create_arguments = dict(
            action="create",
            doc_name=caller_alias,
            metadata={
                "doc_type": "bug",
                "category": "runtime",
                "slug": case_id,
                "reported_at": "2026-06-25T00:00:00Z",
            },
            content=content,
            dry_run=False,
        )
        before = await _read_persisted_project(state_manager, client, test_agent)
        before_files = {
            path: path.read_bytes() for path in project_root.rglob("*") if path.is_file()
        }
        preview = await manage_docs(**{**create_arguments, "dry_run": True})
        assert preview.get("ok") is True, preview
        assert preview.get("dry_run") is True, preview
        selected_path = Path(preview["path"]).resolve()
        assert selected_path.is_relative_to(project_root), preview
        assert not selected_path.exists(), preview
        assert {
            path: path.read_bytes() for path in project_root.rglob("*") if path.is_file()
        } == before_files
        after = await _read_persisted_project(state_manager, client, test_agent)
        assert after["docs"] == before["docs"]

        create_result = await manage_docs(**create_arguments)
        assert create_result.get("ok") is True, create_result
        report_path = Path(str(create_result["path"]))
        assert report_path.resolve() == selected_path
        assert report_path.is_relative_to(project_root)
        assert report_path.exists()
        assert create_result["canonical_doc_name"] == case_id
        assert create_result["canonical_doc_path"] == str(report_path)
        created_row = await read_case()
        case_rows = [created_row]
        assert created_row["status"] == "open"
        # Seed the original regression: registry closure must survive edits even
        # while the document still carries its initial open status.
        closed = build_case_registry_upsert_kwargs(
            existing_record=created_row, overrides={"status": "closed"}
        )
        assert closed is not None
        await backend.upsert_case_registry_record(**closed)

        caller_result = await manage_docs(
            action="replace_section",
            doc_name=caller_alias,
            doc_category="bugs",
            section="symptoms",
            content="Updated through caller alias.",
            dry_run=False,
        )
        assert caller_result.get("ok") is True, caller_result
        assert caller_result["canonical_doc_name"] == case_id
        assert caller_result["canonical_doc_path"] == str(report_path)
        case_rows.append(await read_case())
        assert case_rows[-1]["status"] == "closed"

        case_result = await manage_docs(
            action="replace_section",
            doc_name=case_id,
            doc_category="bugs",
            section="fix",
            content="Updated through case ID.",
            dry_run=False,
        )
        assert case_result.get("ok") is True, case_result
        assert case_result["canonical_doc_name"] == case_id
        assert case_result["canonical_doc_path"] == str(report_path)
        case_rows.append(await read_case())
        assert case_rows[-1]["status"] == "closed"

        path_result = await manage_docs(
            action="replace_section",
            doc_name=str(report_path),
            doc_category="bugs",
            section="symptoms",
            content="Updated through caller alias.\nUpdated through path alias.",
            dry_run=False,
        )
        assert path_result.get("ok") is True, path_result
        assert path_result["canonical_doc_name"] == case_id
        assert path_result["canonical_doc_path"] == str(report_path)
        case_rows.append(await read_case())
        assert case_rows[-1]["status"] == "closed"

    assert "Updated through caller alias." in report_path.read_text(encoding="utf-8")
    assert "Updated through case ID." in report_path.read_text(encoding="utf-8")
    assert "Updated through path alias." in report_path.read_text(encoding="utf-8")

    persisted_project = await backend.fetch_project(project_name, repo_root=str(project_root))
    assert persisted_project is not None
    assert persisted_project.docs_json is not None
    docs_mapping = json.loads(persisted_project.docs_json)
    assert docs_mapping[case_id] == str(report_path)
    assert docs_mapping[caller_alias] == str(report_path)
    assert docs_mapping[f"bug_report_{report_path.stem}"] == str(report_path)

    records = await backend.query_case_registry_records(
        repo_root=str(project_root), project_name=project_name, limit=10
    )
    assert len(records) == 1
    assert records[0].case_id == case_id
    assert len({row["doc_path"] for row in case_rows}) == 1
    assert case_rows[-1]["doc_name"] == case_id
    assert case_rows[-1]["doc_path"] == str(report_path)
    assert case_rows[-1]["status"] == "closed"

    doc_binding = case_rows[-1]["metadata"]["doc_binding"]
    assert doc_binding["canonical_doc_name"] == case_id
    assert doc_binding["canonical_doc_path"] == str(report_path)
    aliases = {alias["alias"]: alias["alias_kind"] for alias in doc_binding["aliases"]}
    assert aliases[case_id] == "primary"
    assert aliases[caller_alias] == "caller_alias"
    assert aliases[f"bug_report_{report_path.stem}"] == "legacy_compat"
    assert aliases[str(report_path)] == "path_alias"
