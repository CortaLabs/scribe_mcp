from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.doc_management.utils import ScribeSourceDocument
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


def _project_payload(project_root: Path, slug: str) -> dict:
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / slug
    docs_dir.mkdir(parents=True, exist_ok=True)
    custom_log_path = docs_dir / "DECISIONS.md"
    for filename, title in (("ARCHITECTURE_GUIDE.md", "Architecture"), ("CHECKLIST.md", "Checklist")):
        (docs_dir / filename).write_text(f"# {title}\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("## Phase 1 (In Progress)\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text(
        "\n".join(
            [
                "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Complete task | priority=high; category=milestone; tags=[\"ship\"]",
                "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing category and tags | priority=medium",
            ]
        ),
        encoding="utf-8",
    )
    custom_log_path.write_text("[2026-05-01] custom log entry\n", encoding="utf-8")
    config_dir = project_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        "repo_slug: test\n"
        "logs:\n"
        "  decisions:\n"
        "    path: \"{docs_dir}/DECISIONS.md\"\n"
        "    metadata_requirements: []\n",
        encoding="utf-8",
    )
    return {"name": slug.replace("_", " ").title(), "root": str(project_root), "docs_dir": str(docs_dir), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "docs": {"architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"), "phase_plan": str(docs_dir / "PHASE_PLAN.md"), "checklist": str(docs_dir / "CHECKLIST.md"), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "decisions": str(custom_log_path)}}


async def _seed_runtime_session(state_manager: StateManager, session_id: str, repo_root: str) -> None:
    backend = getattr(state_manager, "_storage_backend", None)
    if backend and hasattr(backend, "upsert_session"):
        await backend.upsert_session(session_id=session_id, transport_session_id=session_id, repo_root=repo_root, mode="project")


@pytest.mark.asyncio
async def test_project_health_includes_managed_doc_quality(tmp_path: Path) -> None:
    project_root = tmp_path / "quality_repo"
    active_project = _project_payload(project_root, "active_project")
    architecture_path = Path(active_project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "quality-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="quality-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    quality = result.get("managed_doc_quality") or {}
    assert quality.get("status") == "blocked"
    assert quality.get("readiness_blocker_count", 0) >= 1
    names = {doc.get("doc_name") for doc in quality.get("documents", [])}
    assert "progress_log" not in names
    assert "decisions" not in names
    readiness = result.get("readiness_summary") or {}
    assert isinstance(readiness.get("managed_doc_quality"), dict)
    assert readiness.get("managed_doc_quality") == quality
    assert readiness.get("current_phase")
    assert "Phase 1" in str(readiness.get("current_phase"))
    log_friction = readiness.get("log_friction") or {}
    signals = log_friction.get("signals") or []
    assert signals
    assert log_friction.get("status") == "advisory"
    assert {s.get("code") for s in signals} == {"LOG_MISSING_CATEGORY", "LOG_MISSING_TAGS"}
    assert readiness.get("warning_count", 0) == quality.get("total_warning_count", 0)
    assert readiness.get("blocker_count", 0) == quality.get("readiness_blocker_count", 0)
    organization_digest = result.get("organization_digest") or {}
    assert isinstance(organization_digest.get("quality_warning_digest"), list)
    truth_model = organization_digest.get("truth_model") or {}
    assert "direct_artifact" in truth_model
    assert "derived_signal" in truth_model
    derived = organization_digest.get("derived_signals") or []
    assert any(item.get("truth_label") == "derived_signal" for item in derived)
    status_sections = organization_digest.get("status_sections") or {}
    required_keys = {"organization", "index", "project_artifacts", "archive", "artifact_claims", "ownership"}
    assert required_keys.issubset(set(status_sections.keys()))
    for key in required_keys:
        section = status_sections.get(key) or {}
        assert isinstance(section.get("status"), str)
        assert isinstance(section.get("truth_label"), str)
        assert isinstance(section.get("summary"), str)
        assert isinstance(section.get("next_safe_action"), str)


@pytest.mark.asyncio
async def test_project_health_counts_research_hygiene_for_path_registered_docs(tmp_path: Path) -> None:
    project_root = tmp_path / "research_quality_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_FRONTMATTER.md"
    research_doc.write_text("# Research\nEvidence.\n", encoding="utf-8")
    active_project["docs"] = {
        "architecture": active_project["docs"]["architecture"],
        "research_frontmatter": str(research_doc),
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "research-quality-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="research-quality-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    quality = result.get("managed_doc_quality") or {}
    research_entry = next(doc for doc in quality.get("documents", []) if doc.get("doc_name") == "research_frontmatter")
    assert "SCF_INDEX_MISSING" in research_entry.get("warning_codes", [])
    organization_digest = result.get("organization_digest") or {}
    warning_digest = organization_digest.get("quality_warning_digest") or []
    assert any(item.get("warning_code") == "SCF_INDEX_MISSING" for item in warning_digest)
    status_sections = organization_digest.get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    assert index_section.get("status") == "needs_attention"
    assert "research-index warning" in str(index_section.get("summary", "")).lower()


@pytest.mark.asyncio
async def test_project_health_marks_index_needs_attention_for_unindexed_doc_warning(tmp_path: Path) -> None:
    project_root = tmp_path / "index_unindexed_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    indexed_doc = research_dir / "RESEARCH_INDEXED.md"
    indexed_doc.write_text("---\nindex: true\n---\n# Indexed\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "index-unindexed-test-session", active_project["root"])

    quality_payload = {
        "status": "warn",
        "documents": [
            {
                "doc_name": "research_indexed",
                "path": str(indexed_doc),
                "project_slug": "active_project",
                "warning_count": 1,
                "warning_codes": ["SCF_DOC_UNINDEXED"],
            }
        ],
        "readiness_blocker_count": 0,
        "total_warning_count": 1,
        "warnings": [
            {
                "code": "SCF_DOC_UNINDEXED",
                "severity": "warning",
                "blocking": False,
                "doc_name": "research_indexed",
                "path": str(indexed_doc),
                "suggested_repair": "Index the doc.",
            }
        ],
    }
    with _isolated_server(state_manager, project_root=project_root, session_id="index-unindexed-test-session"):
        with patch("scribe_mcp.doc_management.runtime.collect_managed_doc_quality_state", return_value=quality_payload):
            result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    organization_digest = result.get("organization_digest") or {}
    warning_digest = organization_digest.get("quality_warning_digest") or []
    assert any(item.get("warning_code") == "SCF_DOC_UNINDEXED" for item in warning_digest)
    status_sections = organization_digest.get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    assert index_section.get("status") == "needs_attention"


@pytest.mark.asyncio
async def test_project_health_does_not_treat_non_research_warning_as_research_index_failure(tmp_path: Path) -> None:
    project_root = tmp_path / "non_research_index_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    review_doc = docs_dir / "REVIEW_REPORT_PHASE_2.md"
    review_doc.write_text("# Review\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "non-research-index-test-session", active_project["root"])

    quality_payload = {
        "status": "warn",
        "documents": [
            {
                "doc_name": "review_report_phase_2",
                "path": str(review_doc),
                "project_slug": "active_project",
                "warning_count": 1,
                "warning_codes": ["SCF_DOC_UNINDEXED"],
            }
        ],
        "readiness_blocker_count": 0,
        "total_warning_count": 1,
        "warnings": [
            {
                "code": "SCF_DOC_UNINDEXED",
                "severity": "warning",
                "blocking": False,
                "doc_name": "review_report_phase_2",
                "path": str(review_doc),
                "suggested_repair": "Refresh relevant index.",
            }
        ],
    }

    with _isolated_server(state_manager, project_root=project_root, session_id="non-research-index-test-session"):
        with patch("scribe_mcp.doc_management.runtime.collect_managed_doc_quality_state", return_value=quality_payload):
            result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    status_sections = (result.get("organization_digest") or {}).get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    project_artifacts = status_sections.get("project_artifacts") or {}
    assert index_section.get("status") == "ok"
    assert project_artifacts.get("status") == "needs_attention"
    assert "synthesis/review artifact" in str(project_artifacts.get("summary", "")).lower()


@pytest.mark.asyncio
async def test_project_health_reports_archive_preflight_status(tmp_path: Path) -> None:
    project_root = tmp_path / "archive_quality_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    preflight_family = docs_dir / "archive" / "preflight" / "research"
    preflight_family.mkdir(parents=True, exist_ok=True)
    (preflight_family / "RESEARCH_NOTE.md").write_text("# Archived note\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "archive-quality-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="archive-quality-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    archive_section = status_sections.get("archive") or {}
    assert archive_section.get("status") == "evidence_present"
    assert archive_section.get("truth_label") == "direct_artifact"
    assert "contains 1 files across 1 families" in str(archive_section.get("summary"))


@pytest.mark.asyncio
async def test_project_health_reports_artifact_claim_status_for_duplicates_and_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "artifact_claims_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    registered_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    active_project["docs"]["architecture_alias"] = str(registered_path)
    active_project["docs"]["missing_doc"] = str(docs_dir / "MISSING.md")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "artifact-claims-test-session", active_project["root"])

    with _isolated_server(state_manager, project_root=project_root, session_id="artifact-claims-test-session"):
        result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    artifact_section = status_sections.get("artifact_claims") or {}
    assert artifact_section.get("status") == "needs_attention"
    details = artifact_section.get("details") or {}
    assert "missing_doc" in (details.get("missing_registered_paths") or [])
    duplicates = details.get("duplicate_claimed_paths") or {}
    assert str(registered_path) in duplicates
    assert set(duplicates[str(registered_path)]) >= {"architecture", "architecture_alias"}


@pytest.mark.asyncio
async def test_project_health_ignores_system_research_index_for_unregistered_claims(tmp_path: Path) -> None:
    project_root = tmp_path / "artifact_claims_index_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_index = research_dir / "INDEX.md"
    indexed_doc = research_dir / "RESEARCH_INDEXED.md"
    indexed_doc.write_text("# Indexed\n", encoding="utf-8")
    unregistered_doc = research_dir / "RESEARCH_UNREGISTERED.md"
    unregistered_doc.write_text("# Unregistered\n", encoding="utf-8")
    research_index.write_text(
        "# Research Documents Index\n\n"
        "- **[RESEARCH_INDEXED](RESEARCH_INDEXED.md)**\n",
        encoding="utf-8",
    )

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)
    await _seed_runtime_session(state_manager, "artifact-claims-index-test-session", active_project["root"])

    discovered_docs = [
        ScribeSourceDocument(
            path=research_index,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
        ScribeSourceDocument(
            path=indexed_doc,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
        ScribeSourceDocument(
            path=unregistered_doc,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
    ]

    with _isolated_server(state_manager, project_root=project_root, session_id="artifact-claims-index-test-session"):
        with patch("scribe_mcp.doc_management.runtime.utils_shared.discover_scribe_source_documents", return_value=discovered_docs):
            result = await manage_docs(action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    artifact_section = status_sections.get("artifact_claims") or {}
    assert artifact_section.get("status") == "needs_attention"
    details = artifact_section.get("details") or {}
    unregistered = details.get("unregistered_active_docs") or []
    assert str(research_index) not in unregistered
    assert str(indexed_doc) not in unregistered
    assert str(unregistered_doc) in unregistered
