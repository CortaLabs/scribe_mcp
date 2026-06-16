from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path, session_id: str):
    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
    }
    from scribe_mcp.tools import manage_docs as manage_docs_module

    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)

    server_module.state_manager = state_manager
    server_module.storage_backend = getattr(state_manager, "_storage_backend", None)
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project", session_id=session_id, stable_session_id=session_id
    )
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig

    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)
    try:

        async def _prepare_context_stub(**_kwargs):
            state = await state_manager.load()
            current_project = state.get_project(state.current_project) if state.current_project else None
            return LoggingContext(
                tool_name="manage_docs",
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot={},
                reminders=[],
                resolution_source="session_binding",
            )

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch("scribe_mcp.config.repo_config.get_current_repo_config", return_value=(project_root, fake_config)):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context
        if orig_exec_ctx is not None:
            server_module.get_execution_context = orig_exec_ctx
        if orig_agent_id is not None:
            server_module.get_agent_identity = orig_agent_id


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(
            session_id=session_id,
            transport_session_id=session_id,
            repo_root=repo_root,
            mode="project",
        )


@pytest.mark.asyncio
async def test_changelog_end_to_end_scaffold_preview_apply_and_trust_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "e2e_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "phase_4_2"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture = docs_dir / "ARCHITECTURE_GUIDE.md"
    phase_plan = docs_dir / "PHASE_PLAN.md"
    checklist = docs_dir / "CHECKLIST.md"
    progress_log = docs_dir / "PROGRESS_LOG.md"
    architecture.write_text("# Architecture\n", encoding="utf-8")
    phase_plan.write_text("## Phase 4.2\n", encoding="utf-8")
    checklist.write_text("# Checklist\n", encoding="utf-8")
    progress_log.write_text("# Progress\n", encoding="utf-8")

    project = {
        "name": "Phase 4.2 E2E",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {
            "architecture": str(architecture),
            "phase_plan": str(phase_plan),
            "checklist": str(checklist),
            "progress_log": str(progress_log),
        },
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "changelog-e2e-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="changelog-e2e-session"):
        create_result = await manage_docs(action="create", doc="CHANGELOG", content="# Project Changelog\n", dry_run=False)
        assert create_result["ok"] is True

        changelog_path = Path(create_result["path"])
        assert changelog_path.exists()
        assert changelog_path.name == "CHANGELOG.md"

        accepted_body = """# Project Changelog

## Add e2e flow
- `entry_id`: 20260512:e2e-flow
- `entry_status`: accepted
- `title`: Add e2e flow
- `summary`: Added final end-to-end proof flow.
- `evidence_refs`:
  - tests/doc_management/test_changelog_end_to_end.py
- `observed_context`:
  - `value`: 1.0.0
  - `source`: pyproject
  - `commit`: abc123
  - `dirty`: false
  - `observed_at`: 2026-05-12T00:00:00Z
  - `confidence`: exact
"""
        changelog_path.write_text(accepted_body, encoding="utf-8")

        (project_root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2.0.0"\n', encoding="utf-8")

        # The observed_context drift check for CHANGELOG only runs under the
        # release_gate quality mode (governance hardening gated it there), so the
        # quality_check must explicitly request release_gate to surface the drift.
        quality_result = await manage_docs(
            action="quality_check",
            doc="CHANGELOG",
            dry_run=True,
            metadata={"quality": {"mode": "release_gate"}},
        )
        assert quality_result["ok"] is True
        warning_codes = {w.get("code") for w in quality_result.get("warnings", [])}
        assert "SCF_RESEARCH_CONTEXT_DRIFT" in warning_codes

        preview_result = await manage_docs(
            action="preview_reconciliation",
            metadata={"preview_type": "changelog"},
            dry_run=True,
        )
        assert preview_result["ok"] is True
        assert preview_result["writes_performed"] is False
        assert "20260512:e2e-flow" in (preview_result.get("missing_in_global") or [])

        apply_result = await manage_docs(action="apply_global_changelog", dry_run=False)
        assert apply_result["ok"] is True
        assert apply_result["writes_performed"] is True

        global_changelog = project_root / ".scribe" / "docs" / "GLOBAL_CHANGELOG.md"
        assert global_changelog.exists()
        global_text = global_changelog.read_text(encoding="utf-8")
        assert "- `source_entry_id`: 20260512:e2e-flow" in global_text

        post_preview = await manage_docs(
            action="preview_reconciliation",
            metadata={"preview_type": "changelog"},
            dry_run=True,
        )
        assert post_preview["ok"] is True
        assert post_preview.get("missing_in_global") == []

        research_create = await manage_docs(action="create", doc="RESEARCH_E2E", dry_run=False)
        assert research_create["ok"] is True
        assert Path(research_create["path"]).name == "RESEARCH_E2E.md"

        review_doc = docs_dir / "REVIEW_REPORT_phase_4_2_2026-05-12_1200.md"
        review_doc.write_text("# Review\n", encoding="utf-8")
        health_result = await manage_docs(action="project_health", metadata={"limit": 10}, dry_run=True)
        assert health_result["ok"] is True
        status_sections = ((health_result.get("organization_digest") or {}).get("status_sections") or {})
        assert (status_sections.get("index") or {}).get("status") == "ok"
        assert (status_sections.get("project_artifacts") or {}).get("status") in {"needs_attention", "no_evidence"}

        checklist.write_text("---\nstatus: draft\n---\nStatus: ready\n", encoding="utf-8")
        mismatch_result = await manage_docs(action="quality_check", doc="CHECKLIST", dry_run=True)
        mismatch_codes = {w.get("code") for w in mismatch_result.get("warnings", [])}
        assert "SCF_LIFECYCLE_STATUS_MISMATCH" in mismatch_codes
