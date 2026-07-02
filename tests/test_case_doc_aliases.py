from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


class _CaseAliasBackend:
    def __init__(self) -> None:
        self.docs_json: str | None = None
        self.upserts: list[dict[str, Any]] = []

    async def update_project_docs(self, _project_name: str, docs_json: str, **_kwargs: Any) -> None:
        self.docs_json = docs_json

    async def fetch_project(self, project_name: str, **_kwargs: Any) -> Any:
        return SimpleNamespace(name=project_name, docs_json=self.docs_json)

    async def record_document_change(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def upsert_case_registry_record(self, **kwargs: Any) -> Any:
        existing = await self.fetch_case_registry_record(kwargs["case_id"])
        merged = dict(kwargs)
        if existing is not None and isinstance(getattr(existing, "metadata", None), dict):
            metadata = dict(existing.metadata)
            metadata.update(merged.get("metadata") or {})
            merged["metadata"] = metadata
        self.upserts.append(merged)
        return SimpleNamespace(**merged)

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any) -> Any:
        for upsert in reversed(self.upserts):
            if upsert.get("case_id") == case_id:
                return SimpleNamespace(**upsert)
        return None


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path, storage_backend: Any):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)

    from scribe_mcp.tools import manage_docs as manage_docs_module

    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    server_module.state_manager = state_manager
    server_module.storage_backend = storage_backend
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id="case-doc-alias-test",
        stable_session_id="case-doc-alias-test",
    )
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="case-doc-alias-test", repo_root=project_root)

    async def _prepare_context_stub(**kwargs: Any) -> LoggingContext:
        state = await state_manager.load()
        current_name = state.current_project
        current_project = state.get_project(current_name) if current_name else None
        state_snapshot = kwargs.get("state_snapshot")
        return LoggingContext(
            tool_name="manage_docs",
            project=current_project,
            recent_projects=list(getattr(state, "recent_projects", []) or []),
            state_snapshot=state_snapshot if isinstance(state_snapshot, dict) else {},
            reminders=[],
        )

    try:
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch(
            "scribe_mcp.config.repo_config.get_current_repo_config",
            return_value=(project_root, fake_config),
        ):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        if orig_exec_ctx is not None:
            server_module.get_execution_context = orig_exec_ctx
        if orig_agent_id is not None:
            server_module.get_agent_identity = orig_agent_id
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context


async def _setup_project(tmp_path: Path) -> tuple[dict[str, Any], StateManager, _CaseAliasBackend]:
    project_root = tmp_path / "case_doc_alias_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "case_doc_alias_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    project = {
        "name": "case_doc_alias_project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"progress_log": str(progress_log)},
        "defaults": {"agent": "test-agent"},
    }
    state_manager = StateManager(path=tmp_path / "state.json")
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(
            session_id="case-doc-alias-test",
            repo_root=str(project_root),
            mode="project",
        )
    await state_manager.set_current_project(project["name"], project)
    return project, state_manager, _CaseAliasBackend()


@pytest.mark.asyncio
async def test_case_report_aliases_bind_to_one_canonical_doc_and_registry_row(tmp_path: Path) -> None:
    project, state_manager, backend = await _setup_project(tmp_path)
    project_root = Path(project["root"])
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

    with _isolated_server(state_manager, project_root=project_root, storage_backend=backend):
        create_result = await manage_docs(
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
        assert create_result.get("ok") is True, create_result
        report_path = Path(str(create_result["path"]))
        assert report_path.exists()
        assert create_result["canonical_doc_name"] == case_id
        assert create_result["canonical_doc_path"] == str(report_path)
        assert backend.upserts[-1]["status"] == "open"
        backend.upserts[-1]["status"] = "closed"

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

    assert "Updated through caller alias." in report_path.read_text(encoding="utf-8")
    assert "Updated through case ID." in report_path.read_text(encoding="utf-8")

    assert backend.docs_json is not None
    docs_mapping = json.loads(backend.docs_json)
    assert docs_mapping[case_id] == str(report_path)
    assert docs_mapping[caller_alias] == str(report_path)
    assert docs_mapping[f"bug_report_{report_path.stem}"] == str(report_path)

    case_rows = [upsert for upsert in backend.upserts if upsert["case_id"] == case_id]
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
