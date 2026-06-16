from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.doc_management import runtime as runtime_shared
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


@contextmanager
def _isolated_server(state_manager: StateManager, *, project_root: Path, session_id: str):
    originals = {"state_manager": server_module.state_manager, "storage_backend": server_module.storage_backend}
    from scribe_mcp.tools import manage_docs as manage_docs_module
    orig_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context
    orig_exec_ctx = getattr(server_module, "get_execution_context", None)
    orig_agent_id = getattr(server_module, "get_agent_identity", None)
    server_module.state_manager = state_manager
    server_module.storage_backend = getattr(state_manager, "_storage_backend", None)
    server_module.get_execution_context = lambda: SimpleNamespace(mode="project", session_id=session_id, stable_session_id=session_id)
    server_module.get_agent_identity = lambda: None

    from scribe_mcp.config.repo_config import RepoConfig
    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)
    try:
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            current_project = state.get_project(state.current_project) if state.current_project else None
            return LoggingContext(tool_name="manage_docs", project=current_project, recent_projects=list(getattr(state, "recent_projects", []) or []), state_snapshot={}, reminders=[], resolution_source="session_binding")

        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        with patch("scribe_mcp.config.repo_config.get_current_repo_config", return_value=(project_root, fake_config)):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        if orig_exec_ctx is not None:
            server_module.get_execution_context = orig_exec_ctx
        if orig_agent_id is not None:
            server_module.get_agent_identity = orig_agent_id
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = orig_prepare_context


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(session_id=session_id, transport_session_id=session_id, repo_root=repo_root, mode="project")


@pytest.mark.asyncio
async def test_quality_check_returns_structured_quality_proof(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-check-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-check-session"):
        result = await manage_docs(action="quality_check", doc_name="ARCHITECTURE_GUIDE", dry_run=True)

    assert result["ok"] is True
    assert result["quality_status"] in {"warn", "fail"}
    assert result["scope"]["doc_name"] == "ARCHITECTURE_GUIDE"
    assert result["summary"]["total_warnings"] >= 1
    first = result["warnings"][0]
    for key in ("code", "severity", "blocking", "location", "file_location", "location_basis", "excerpt", "message", "suggested_repair"):
        assert key in first
    for key in ("category", "gate_scope", "scope_kind", "suppressible", "source_owner", "rule_version", "repair_kind", "edit_action_hint", "provenance"):
        assert key in first
    for key in ("ok", "quality_status", "scope", "summary", "warnings", "warning_groups", "agent_actions", "runtime_warnings", "readiness_blockers", "next_actions"):
        assert key in result
    assert result["summary"]["mode"] == "local_default"
    assert result["summary"]["has_blockers"] is True
    assert result["summary"]["highest_severity"] in {"critical", "high"}
    assert result["summary"]["warning_counts_by_code"]
    assert result["summary"]["blocking_warning_counts_by_code"]
    assert result["summary"]["category_counts"]
    assert result["summary"]["repair_kind_counts"]
    assert result["warning_groups"]
    assert result["agent_actions"]
    assert result["readiness_blockers"]
    assert result["next_actions"]
    assert isinstance(result["next_actions"][0], str)
    assert result["agent_actions"][0]["blocking"] is True
    assert result["agent_actions"][0]["suggested_repair"]


@pytest.mark.asyncio
async def test_quality_check_returns_agent_triage_groups_and_actions(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_agent_triage_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text(
        """---
status: complete
---
# Findings
| finding |
| |

[fill this section]
TODO: add implementation evidence
""",
        encoding="utf-8",
    )
    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-agent-triage-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-agent-triage-session"):
        result = await manage_docs(action="quality_check", doc_name="ARCHITECTURE_GUIDE", dry_run=True)

    summary = result["summary"]
    assert summary["warning_counts_by_code"]["SCF_PLACEHOLDER_BRACKET"] == 1
    assert summary["blocking_warning_counts_by_code"]["SCF_PLACEHOLDER_BRACKET"] == 1
    assert summary["has_blockers"] is True
    assert summary["actionable_warning_count"] >= 3
    assert summary["repair_kind_counts"]["content_completion"] >= 1

    placeholder_warning = next(warning for warning in result["warnings"] if warning["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_warning["location_basis"] == "body_relative"
    assert placeholder_warning["location"]["line"] == 5
    assert placeholder_warning["file_location"]["line"] == 8
    assert placeholder_warning["file_location"]["source_line"] == 5
    assert placeholder_warning["section"]["heading"] == "Findings"
    assert placeholder_warning["section"]["file_line"] == 4
    assert placeholder_warning["repair_kind"] == "content_completion"
    assert placeholder_warning["edit_action_hint"] == "replace_range"
    assert placeholder_warning["provenance"]["body_start_line"] == 4

    groups_by_code = {group["code"]: group for group in result["warning_groups"]}
    placeholder = groups_by_code["SCF_PLACEHOLDER_BRACKET"]
    assert placeholder["count"] == 1
    assert placeholder["blocking_count"] == 1
    assert placeholder["first_location"]["line"] >= 1
    assert placeholder["first_file_location"]["line"] == 8
    assert placeholder["affected_lines"]
    assert placeholder["affected_lines"] == [8]
    assert placeholder["sections"][0]["heading"] == "Findings"
    assert placeholder["repair_kind"] == "content_completion"
    assert placeholder["edit_action_hint"] == "replace_range"
    assert placeholder["message_samples"]
    assert placeholder["suggested_repair"]

    action_codes = [action["code"] for action in result["agent_actions"]]
    assert "SCF_PLACEHOLDER_BRACKET" in action_codes
    placeholder_action = next(action for action in result["agent_actions"] if action["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_action["rank"] >= 1
    assert placeholder_action["blocking"] is True
    assert placeholder_action["summary"]
    assert placeholder_action["affected_lines"] == [8]
    assert placeholder_action["first_file_location"]["line"] == 8
    assert placeholder_action["section"]["heading"] == "Findings"
    assert placeholder_action["repair_kind"] == "content_completion"
    assert placeholder_action["edit_action_hint"] == "replace_range"


@pytest.mark.asyncio
async def test_quality_check_clean_doc_passes(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase = docs_dir / "PHASE_PLAN.md"
    phase.write_text("---\nstatus: in_progress\n---\n# Phase\nComplete evidence text.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-pass-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-pass-session"):
        result = await manage_docs(action="quality_check", doc="PHASE_PLAN", dry_run=True)

    assert result["ok"] is True
    assert result["quality_status"] == "pass"
    assert result["readiness_blockers"] == []


@pytest.mark.asyncio
async def test_quality_check_bulk_project_returns_atlas_aggregate_payload(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_bulk_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    phase = docs_dir / "PHASE_PLAN.md"
    progress_log = docs_dir / "PROGRESS_LOG.md"
    arch.write_text("---\nstatus: complete\n---\n# Findings\n[fill this section]\n", encoding="utf-8")
    phase.write_text("---\nstatus: in_progress\n---\n# Phase\nReal implementation evidence.\n", encoding="utf-8")
    progress_log.write_text("[fill should not affect project bulk quality]\n", encoding="utf-8")
    project = {
        "name": "Q",
        "root": str(project_root),
        "progress_log": str(progress_log),
        "docs": {
            "ARCHITECTURE_GUIDE": str(arch),
            "PHASE_PLAN": str(phase),
            "progress_log": str(progress_log),
        },
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-bulk-session", project["root"])

    metadata = {"quality": {"bulk": {"scope": "project", "include_clean": True, "max_agent_actions": 3}}}
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-bulk-session"):
        result = await manage_docs(action="quality_check", metadata=metadata, dry_run=True)

    assert result["ok"] is True
    assert result["quality_status"] == "fail"
    assert result["scope"]["type"] == "bulk"
    assert result["scope"]["checked_count"] == 2
    assert result["scope"]["included_document_count"] == 2
    assert result["summary"]["scope_kind"] == "bulk"
    assert result["summary"]["checked_documents"] == 2
    assert result["summary"]["documents_with_warnings"] == 1
    assert result["summary"]["documents_with_blockers"] == 1
    assert result["summary"]["warning_counts_by_code"]["SCF_PLACEHOLDER_BRACKET"] == 1
    assert result["summary"]["blocking_warning_counts_by_code"]["SCF_PLACEHOLDER_BRACKET"] == 1
    assert {document["doc_name"] for document in result["documents"]} == {"ARCHITECTURE_GUIDE", "PHASE_PLAN"}
    assert all(document["doc_name"] != "progress_log" for document in result["documents"])

    placeholder_warning = next(warning for warning in result["warnings"] if warning["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_warning["doc_name"] == "ARCHITECTURE_GUIDE"
    assert placeholder_warning["path"] == str(arch.resolve())
    placeholder_group = next(group for group in result["warning_groups"] if group["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_group["document_count"] == 1
    assert placeholder_group["documents"][0]["doc_name"] == "ARCHITECTURE_GUIDE"
    placeholder_action = next(action for action in result["agent_actions"] if action["code"] == "SCF_PLACEHOLDER_BRACKET")
    assert placeholder_action["document_count"] == 1
    assert placeholder_action["documents"][0]["path"] == str(arch.resolve())
    assert result["next_actions"]


@pytest.mark.asyncio
async def test_quality_check_bulk_doc_list_supports_compact_atlas_mode(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_bulk_compact_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    phase = docs_dir / "PHASE_PLAN.md"
    arch.write_text("---\nstatus: complete\n---\n# Findings\nTODO: replace planning stub.\n", encoding="utf-8")
    phase.write_text("---\nstatus: in_progress\n---\n# Phase\nReal implementation evidence.\n", encoding="utf-8")
    project = {
        "name": "Q",
        "root": str(project_root),
        "docs": {"ARCHITECTURE_GUIDE": str(arch), "PHASE_PLAN": str(phase)},
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-bulk-compact-session", project["root"])

    metadata = {
        "quality": {
            "bulk": {
                "doc_names": ["ARCHITECTURE_GUIDE", "PHASE_PLAN"],
                "include_clean": False,
                "include_warnings": False,
                "max_agent_actions": 1,
            }
        }
    }
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-bulk-compact-session"):
        result = await manage_docs(action="quality_check", metadata=metadata, dry_run=True)

    assert result["ok"] is True
    assert result["scope"]["type"] == "bulk"
    assert result["scope"]["mode"] == "doc_names"
    assert result["scope"]["checked_count"] == 2
    assert result["scope"]["included_document_count"] == 1
    assert result["scope"]["include_warnings"] is False
    assert result["warnings"] == []
    assert result["readiness_blockers"] == []
    assert result["summary"]["total_warnings"] >= 1
    assert result["summary"]["documents_with_warnings"] == 1
    assert [document["doc_name"] for document in result["documents"]] == ["ARCHITECTURE_GUIDE"]
    assert result["documents"][0]["warnings"] == []
    assert len(result["agent_actions"]) == 1
    assert result["agent_actions"][0]["documents"][0]["doc_name"] == "ARCHITECTURE_GUIDE"


@pytest.mark.asyncio
async def test_quality_handoff_check_blocks_when_scaffold_blockers_exist(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_handoff_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-handoff-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-handoff-session"):
        result = await manage_docs(action="quality_handoff_check", dry_run=True)

    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["action"] == "quality_handoff_check"
    assert result["total_blocker_count"] >= 1
    assert result["quality_summary"]["readiness_blocker_count"] >= 1
    assert result["quality_summary"]["readiness_blocker_counts_by_code"]
    assert result["handoff_actions"]
    assert result["handoff_actions"][0]["doc_name"] == "ARCHITECTURE_GUIDE"
    assert "quality_check" in result["handoff_actions"][0]["command_hint"]
    assert result["handoff_actions"][0]["blocker_codes"]


@pytest.mark.asyncio
async def test_quality_check_detects_failed_write_residue_blocker(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_residue_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase = docs_dir / "PHASE_PLAN.md"
    phase.write_text("---\nstatus: in_progress\n---\nThis has failed write residue from prior run.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-residue-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-residue-session"):
        result = await manage_docs(action="quality_check", doc="PHASE_PLAN", dry_run=True)

    codes = {w.get("code") for w in result.get("warnings", [])}
    assert "SCF_FAILED_WRITE_RESIDUE" in codes


@pytest.mark.asyncio
async def test_quality_check_respects_metadata_quality_overrides(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    checklist = docs_dir / "CHECKLIST.md"
    checklist.write_text("---\nstatus: complete\n---\nTODO: do this\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"CHECKLIST": str(checklist)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-override-session", project["root"])

    metadata = {"quality": {"severity_overrides": {"SCF_TODO_ONLY_SECTION": "low"}, "blocking_overrides": {"SCF_TODO_ONLY_SECTION": False}}}
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-override-session"):
        result = await manage_docs(action="quality_check", doc_name="CHECKLIST", metadata=metadata, dry_run=True)

    todo = [w for w in result["warnings"] if w.get("code") == "SCF_TODO_ONLY_SECTION"][0]
    assert todo["severity"] == "low"
    assert todo["blocking"] is False
    assert result["summary"]["config_source"] == "metadata.quality"


@pytest.mark.asyncio
async def test_quality_check_resolves_registered_doc_aliases(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_alias"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PACKAGE_5_1_VERIFICATION_CLOSEOUT": str(closeout)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-alias-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-alias-session"):
        result = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    assert result["ok"] is True
    assert result["scope"]["doc_name"] == "PACKAGE_5_1_VERIFICATION_CLOSEOUT"


@pytest.mark.asyncio
async def test_quality_check_auto_registers_package_doc_and_accepts_alias_forms(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_bind"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    proof_doc = docs_dir / "PACKAGE_5_1_LIVE_PROOF_DOC.md"
    proof_doc.write_text("# Live Proof\n\nEvidence.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs_dir": str(docs_dir), "docs": {}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-bind-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-bind-session"):
        by_doc_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_LIVE_PROOF_DOC.md", dry_run=True)
        by_doc = await manage_docs(action="quality_check", doc="PACKAGE_5_1_LIVE_PROOF_DOC", dry_run=True)

    assert by_doc_name["ok"] is True
    assert by_doc_name["scope"]["doc_name"] == "package_5_1_live_proof_doc"
    assert by_doc["ok"] is True
    assert by_doc["scope"]["doc_name"] == "package_5_1_live_proof_doc"


@pytest.mark.asyncio
async def test_quality_check_derives_docs_dir_from_progress_log_when_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_progress_derived"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)

    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Progress\n", encoding="utf-8")
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")

    project = {
        "name": "Q",
        "root": str(project_root),
        "progress_log": str(progress_log),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(progress_log),
        },
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-progress-derive-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-progress-derive-session"):
        by_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT", dry_run=True)
        by_path_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    assert by_name["ok"] is True
    assert by_path_name["ok"] is True


@pytest.mark.asyncio
async def test_quality_check_uses_discovered_doc_when_auto_registration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "quality_repo_registration_blocked"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)

    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Progress\n", encoding="utf-8")
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    closeout = docs_dir / "PACKAGE_5_1_VERIFICATION_CLOSEOUT.md"
    closeout.write_text("# Closeout\n\nVerification evidence.\n", encoding="utf-8")
    project = {
        "name": "Q",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {
            "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(progress_log),
        },
    }

    async def _blocked_registration(*_args, **_kwargs):
        raise ValueError("Cannot establish authoritative session binding for manage_docs registration.")

    monkeypatch.setattr(runtime_shared, "register_document_path", _blocked_registration)

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-registration-blocked-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-registration-blocked-session"):
        by_name = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT", dry_run=True)
        by_md = await manage_docs(action="quality_check", doc_name="PACKAGE_5_1_VERIFICATION_CLOSEOUT.md", dry_run=True)

    for result in (by_name, by_md):
        assert result["ok"] is True
        assert result["scope"]["path"] == str(closeout)
        assert result["scope"]["doc_name"] == "package_5_1_verification_closeout"
        assert "authoritative session binding" in result["runtime_warnings"][0]


@pytest.mark.asyncio
async def test_quality_check_changelog_does_not_require_current_version_coverage_in_local_default(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_changelog_release"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='q'\nversion='9.9.0'\n", encoding="utf-8")

    changelog = docs_dir / "CHANGELOG.md"
    changelog.write_text(
        """# Project Changelog

## Prior release
- `entry_id`: 20260514:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Prior summary
- `evidence_refs`:
  - tests/prior.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 9.8.0
""",
        encoding="utf-8",
    )
    project = {"name": "Q", "root": str(project_root), "docs": {"CHANGELOG": str(changelog)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-changelog-release-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-changelog-release-session"):
        result = await manage_docs(action="quality_check", doc_name="CHANGELOG", dry_run=True)

    codes = {w.get("code") for w in result.get("warnings", [])}
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" not in codes
    assert result["summary"]["mode"] == "local_default"
    assert result["summary"]["release_trigger"] is None


@pytest.mark.asyncio
async def test_quality_check_explicit_release_mode_records_trigger(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_release_mode"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase = docs_dir / "PHASE_PLAN.md"
    phase.write_text("# Phase Plan\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-release-mode-session", project["root"])

    metadata = {"quality": {"mode": "release_gate", "release_trigger": "manual_release_intent"}}
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-release-mode-session"):
        result = await manage_docs(action="quality_check", doc_name="PHASE_PLAN", metadata=metadata, dry_run=True)

    assert result["summary"]["mode"] == "release_gate"
    assert result["summary"]["release_trigger"] == "manual_release_intent"
    assert result["summary"]["release_trigger_source"] == "explicit"
    assert result["summary"]["release_triggers"] == ["manual_release_intent"]


@pytest.mark.asyncio
async def test_quality_check_inferred_release_mode_emits_current_version_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_inferred_release_mode"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='q'\nversion='9.9.0'\n", encoding="utf-8")

    changelog = docs_dir / "CHANGELOG.md"
    changelog.write_text(
        """# Project Changelog

## Prior release
- `entry_id`: 20260514:prior
- `entry_status`: accepted
- `title`: Prior
- `summary`: Prior summary
- `evidence_refs`:
  - tests/prior.py
- `observed_context`:
  - `source`: pyproject
  - `value`: 9.8.0
""",
        encoding="utf-8",
    )
    project = {"name": "Q", "root": str(project_root), "docs": {"CHANGELOG": str(changelog)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-inferred-release-mode-session", project["root"])

    metadata = {"quality": {"infer_release_gate": True, "release_trigger": "manual_release_intent"}}
    with _isolated_server(state_manager, project_root=project_root, session_id="quality-inferred-release-mode-session"):
        result = await manage_docs(action="quality_check", doc_name="CHANGELOG", metadata=metadata, dry_run=True)

    codes = {w.get("code") for w in result.get("warnings", [])}
    assert result["summary"]["mode"] == "release_gate"
    assert result["summary"]["release_trigger_source"] == "inferred"
    assert "SCF_CHANGELOG_CURRENT_VERSION_MISSING" in codes


@pytest.mark.asyncio
async def test_quality_check_accepts_repo_relative_markdown_report_path(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_relative_path"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "active"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text("# Architecture\n", encoding="utf-8")

    report = project_root / "docs" / "bugs" / "case_001" / "report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Bug Report\n\nObserved behavior.\n", encoding="utf-8")

    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-relative-path-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-relative-path-session"):
        result = await manage_docs(action="quality_check", doc_name="docs/bugs/case_001/report.md", dry_run=True)

    assert result["ok"] is True
    assert result["scope"]["path"] == str(report.resolve())
    assert result["scope"]["doc_name"] == "report"


@pytest.mark.asyncio
async def test_quality_check_accepts_absolute_markdown_path_from_other_dev_plan_project(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_absolute_path"
    active_docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "active"
    active_docs_dir.mkdir(parents=True, exist_ok=True)
    phase = active_docs_dir / "PHASE_PLAN.md"
    phase.write_text("# Phase Plan\n", encoding="utf-8")

    other_doc = project_root / ".scribe" / "docs" / "dev_plans" / "other_project" / "PACKAGE_9_1_REPORT.md"
    other_doc.parent.mkdir(parents=True, exist_ok=True)
    other_doc.write_text("# Package Report\n\nCross-project quality check target.\n", encoding="utf-8")

    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-absolute-path-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-absolute-path-session"):
        result = await manage_docs(action="quality_check", doc_name=str(other_doc.resolve()), dry_run=True)

    assert result["ok"] is True
    assert result["scope"]["path"] == str(other_doc.resolve())
    assert result["scope"]["doc_name"] == "package_9_1_report"


@pytest.mark.asyncio
async def test_quality_check_alias_route_matches_scaffold_quality_check(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_alias_route"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    phase = docs_dir / "PHASE_PLAN.md"
    phase.write_text("# Phase Plan\n\nShippable evidence content.\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"PHASE_PLAN": str(phase)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-alias-route-session", project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-alias-route-session"):
        primary = await manage_docs(action="quality_check", doc_name="PHASE_PLAN", dry_run=True)
        alias = await manage_docs(action="scaffold_quality_check", doc_name="PHASE_PLAN", dry_run=True)

    assert primary == alias


@pytest.mark.asyncio
async def test_quality_check_and_alias_preserve_legacy_top_level_keys(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo_schema_stability"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "q"
    docs_dir.mkdir(parents=True, exist_ok=True)
    arch = docs_dir / "ARCHITECTURE_GUIDE.md"
    arch.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")
    project = {"name": "Q", "root": str(project_root), "docs": {"ARCHITECTURE_GUIDE": str(arch)}}

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)
    await _seed_runtime_session(state_manager, "quality-schema-session", project["root"])

    legacy_keys = {
        "ok",
        "quality_status",
        "scope",
        "summary",
        "warnings",
        "runtime_warnings",
        "readiness_blockers",
        "next_actions",
    }

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-schema-session"):
        primary = await manage_docs(action="quality_check", doc_name="ARCHITECTURE_GUIDE", dry_run=True)
        alias = await manage_docs(action="scaffold_quality_check", doc_name="ARCHITECTURE_GUIDE", dry_run=True)

    for payload in (primary, alias):
        assert legacy_keys.issubset(payload.keys())
