from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.doc_management.special_indexes import update_research_index
from scribe_mcp.doc_management.scaffold_quality import (
    DEFAULT_WARNING_POLICIES,
    build_research_index_hygiene_warnings,
)
from scribe_mcp.doc_management.special_create import _normalize_research_doc_name, handle_special_document_creation
from scribe_mcp.doc_management.runtime import _handle_rehome_doc
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.state import StateManager
from scribe_mcp.tools.manage_docs import manage_docs


class _Helper:
    @staticmethod
    def apply_context_payload(payload, _context):
        return payload

    @staticmethod
    def error_response(message: str):
        return {"ok": False, "error": message}


class _ProjectRegistry:
    @staticmethod
    def record_doc_update(**_kwargs):
        return None


@contextmanager
def _isolated_manage_docs_server(state_manager: StateManager, *, project_root: Path, session_id: str):
    from scribe_mcp.tools import manage_docs as manage_docs_module
    from scribe_mcp.config.repo_config import RepoConfig

    originals = {
        "state_manager": server_module.state_manager,
        "storage_backend": server_module.storage_backend,
        "prepare_context": manage_docs_module._MANAGE_DOCS_HELPER.prepare_context,
        "get_execution_context": getattr(server_module, "get_execution_context", None),
        "get_agent_identity": getattr(server_module, "get_agent_identity", None),
    }
    fake_config = RepoConfig(repo_slug="test", repo_root=project_root)
    server_module.state_manager = state_manager
    server_module.storage_backend = None
    server_module.get_execution_context = lambda: SimpleNamespace(
        mode="project",
        session_id=session_id,
        stable_session_id=session_id,
        transport_session_id=session_id,
    )
    server_module.get_agent_identity = lambda: None

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
    try:
        with patch("scribe_mcp.config.repo_config.get_current_repo_config", return_value=(project_root, fake_config)):
            yield
    finally:
        server_module.state_manager = originals["state_manager"]
        server_module.storage_backend = originals["storage_backend"]
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = originals["prepare_context"]
        if originals["get_execution_context"] is not None:
            server_module.get_execution_context = originals["get_execution_context"]
        if originals["get_agent_identity"] is not None:
            server_module.get_agent_identity = originals["get_agent_identity"]


@pytest.mark.asyncio
async def test_research_create_defaults_to_project_scoped_canonical_dir(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    canonical_docs = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    legacy_docs = project_root / "docs" / "dev_plans" / "agent_ux"
    canonical_docs.mkdir(parents=True, exist_ok=True)
    legacy_research = legacy_docs / "research"
    legacy_research.mkdir(parents=True, exist_ok=True)
    (legacy_research / "LEGACY_RESEARCH.md").write_text("# Legacy\n", encoding="utf-8")

    progress_log = canonical_docs / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")

    project = {
        "name": "agent_ux_doc_governance_hardening_20260416",
        "root": str(project_root),
        "docs_dir": str(legacy_docs),
        "progress_log": str(progress_log),
        "docs": {"progress_log": str(progress_log)},
    }

    result = await handle_special_document_creation(
        project=project,
        action="create_research_doc",
        doc_name="RESEARCH_CANONICAL_DEFAULT",
        target_dir=None,
        content="# Research\n",
        metadata={},
        dry_run=False,
        agent_id="test_agent",
        storage_backend=None,
        helper=_Helper(),
        context=None,
        project_registry=_ProjectRegistry(),
        logger=logging.getLogger(__name__),
    )

    assert result.get("ok") is True, result
    created_path = Path(result["path"])
    assert created_path.parent == canonical_docs / "research"
    assert (canonical_docs / "research" / "INDEX.md").exists()
    assert not (legacy_docs / "research" / "RESEARCH_CANONICAL_DEFAULT.md").exists()
    assert "legacy research artifact" in result.get("placement_warning", "").lower()


@pytest.mark.asyncio
async def test_research_create_normalizes_md_suffix_and_refreshes_index(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")

    project = {
        "name": "agent_ux_doc_governance_hardening_20260416",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"progress_log": str(progress_log)},
    }

    result = await handle_special_document_creation(
        project=project,
        action="create_research_doc",
        doc_name="RESEARCH_SUFFIX_TEST.md.md",
        target_dir=None,
        content="# Research\n",
        metadata={},
        dry_run=False,
        agent_id="test_agent",
        storage_backend=None,
        helper=_Helper(),
        context=None,
        project_registry=_ProjectRegistry(),
        logger=logging.getLogger(__name__),
    )

    assert result.get("ok") is True, result
    created_path = Path(result["path"])
    assert created_path.name == "RESEARCH_SUFFIX_TEST.md"
    assert not created_path.name.endswith(".md.md")

    index_path = created_path.parent / "INDEX.md"
    assert index_path.exists()
    index_content = index_path.read_text(encoding="utf-8")
    assert "RESEARCH_SUFFIX_TEST.md" in index_content


def test_research_name_normalization_collapses_duplicate_family_prefix() -> None:
    normalized = _normalize_research_doc_name("research_RESEARCH_DUPLICATE.md")
    assert normalized == "RESEARCH_DUPLICATE"


@pytest.mark.asyncio
async def test_research_create_ignores_target_dir_without_explicit_override_flag(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    repo_root_research_dir = project_root / "research"

    project = {
        "name": "agent_ux_doc_governance_hardening_20260416",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"progress_log": str(progress_log)},
    }

    result = await handle_special_document_creation(
        project=project,
        action="create_research_doc",
        doc_name="RESEARCH_OVERRIDE",
        target_dir=str(repo_root_research_dir),
        content="# Research\n",
        metadata={},
        dry_run=False,
        agent_id="test_agent",
        storage_backend=None,
        helper=_Helper(),
        context=None,
        project_registry=_ProjectRegistry(),
        logger=logging.getLogger(__name__),
    )

    assert result.get("ok") is True, result
    created_path = Path(result["path"])
    assert created_path.parent == docs_dir / "research"
    assert not (repo_root_research_dir / "RESEARCH_OVERRIDE.md").exists()
    warning = result.get("placement_warning", "").lower()
    assert "ignored research target_dir" in warning
    assert "repo_research=true" in warning


@pytest.mark.asyncio
async def test_research_create_respects_target_dir_with_explicit_override_flag(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    repo_root_research_dir = project_root / "research"

    project = {
        "name": "agent_ux_doc_governance_hardening_20260416",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"progress_log": str(progress_log)},
    }

    result = await handle_special_document_creation(
        project=project,
        action="create_research_doc",
        doc_name="RESEARCH_OVERRIDE",
        target_dir=str(repo_root_research_dir),
        content="# Research\n",
        metadata={"repo_research": True},
        dry_run=False,
        agent_id="test_agent",
        storage_backend=None,
        helper=_Helper(),
        context=None,
        project_registry=_ProjectRegistry(),
        logger=logging.getLogger(__name__),
    )

    assert result.get("ok") is True, result
    created_path = Path(result["path"])
    assert created_path.parent == repo_root_research_dir
    assert "explicit research override active" in result.get("placement_warning", "").lower()


def test_research_index_hygiene_warnings_for_missing_and_stale(tmp_path: Path) -> None:
    research_dir = tmp_path / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    doc = research_dir / "RESEARCH_A.md"
    doc.write_text("# A\n", encoding="utf-8")

    warnings_missing = build_research_index_hygiene_warnings(research_dir=research_dir, changed_path=doc, warning_policies=DEFAULT_WARNING_POLICIES)
    assert any(w.get("code") == "SCF_INDEX_MISSING" for w in warnings_missing)

    (research_dir / "INDEX.md").write_text("# Research Documents Index\n", encoding="utf-8")
    warnings_stale = build_research_index_hygiene_warnings(research_dir=research_dir, changed_path=doc, warning_policies=DEFAULT_WARNING_POLICIES)
    codes = {w.get("code") for w in warnings_stale}
    assert "SCF_INDEX_STALE" in codes or "SCF_DOC_UNINDEXED" in codes

    (research_dir / "INDEX.md").write_text(
        "# Research Documents Index\n- **[Missing](MISSING_RESEARCH.md)**\n",
        encoding="utf-8",
    )
    warnings_orphan = build_research_index_hygiene_warnings(research_dir=research_dir, changed_path=doc, warning_policies=DEFAULT_WARNING_POLICIES)
    orphan = next(w for w in warnings_orphan if "orphaned" in str(w.get("message", "")).lower())
    assert orphan["code"] == "SCF_DOC_UNINDEXED"
    assert "Regenerate research/INDEX.md" in orphan["suggested_repair"]


def test_research_hygiene_warns_for_noncanonical_locations(tmp_path: Path) -> None:
    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    canonical_research = docs_dir / "research"
    wave_dir = canonical_research / "wave_1"
    wave_dir.mkdir(parents=True, exist_ok=True)
    nested_doc = wave_dir / "RESEARCH_WAVE.md"
    nested_doc.write_text("# Nested\n", encoding="utf-8")
    (canonical_research / "INDEX.md").write_text("# Research Documents Index\n", encoding="utf-8")

    warnings = build_research_index_hygiene_warnings(
        research_dir=canonical_research,
        changed_path=nested_doc,
        canonical_research_dir=canonical_research,
        warning_policies=DEFAULT_WARNING_POLICIES,
    )

    noncanonical = next(w for w in warnings if w.get("code") == "SCF_NONCANONICAL_LOCATION")
    assert ".scribe/docs/dev_plans/<project>/research/" in noncanonical["message"]
    suggested_repair = str(noncanonical.get("suggested_repair") or "").lower()
    assert "top-level canonical" in suggested_repair or "flat" in suggested_repair


@pytest.mark.asyncio
async def test_managed_research_edit_refreshes_index_and_returns_path_metadata(tmp_path: Path) -> None:
    project_root = tmp_path / "edit_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_EDIT.md"
    research_doc.write_text("# Research\nOriginal evidence.\n", encoding="utf-8")
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    await update_research_index(research_dir, "test_agent", repo_root=project_root)
    before_index = (research_dir / "INDEX.md").read_text(encoding="utf-8")

    project = {
        "name": "agent_ux",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"research_edit": str(research_doc)},
    }
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_manage_docs_server(state_manager, project_root=project_root, session_id="edit-session"):
        result = await manage_docs(
            action="replace_text",
            doc_name="research_edit",
            metadata={"find": "Original evidence.", "replace": "Expanded evidence with a longer proof line.", "match_mode": "literal"},
            dry_run=False,
            agent="test_agent",
        )

    assert result["ok"] is True, result
    assert result["requested_doc_name"] == "research_edit"
    assert result["canonical_doc_name"] == "research_edit"
    assert result["final_path"] == str(research_doc)
    after_index = (research_dir / "INDEX.md").read_text(encoding="utf-8")
    assert after_index != before_index
    assert "RESEARCH_EDIT.md" in after_index


@pytest.mark.asyncio
async def test_managed_research_frontmatter_update_refreshes_index(tmp_path: Path) -> None:
    project_root = tmp_path / "frontmatter_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_FRONTMATTER.md"
    research_doc.write_text(
        "---\nstatus: in_progress\nsummary: Short.\n---\n# Research\nEvidence.\n",
        encoding="utf-8",
    )
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    await update_research_index(research_dir, "test_agent", repo_root=project_root)
    before_index = (research_dir / "INDEX.md").read_text(encoding="utf-8")

    project = {
        "name": "agent_ux",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {"research_frontmatter": str(research_doc)},
    }
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_manage_docs_server(state_manager, project_root=project_root, session_id="frontmatter-session"):
        result = await manage_docs(
            action="frontmatter_update",
            doc_name="research_frontmatter",
            metadata={"summary": "A much longer summary that changes displayed file metadata size."},
            dry_run=False,
            agent="test_agent",
        )

    assert result["ok"] is True, result
    assert result["requested_doc_name"] == "research_frontmatter"
    assert result["canonical_doc_name"] == "research_frontmatter"
    assert result["final_path"] == str(research_doc)
    after_index = (research_dir / "INDEX.md").read_text(encoding="utf-8")
    assert after_index != before_index
    assert "RESEARCH_FRONTMATTER.md" in after_index


@pytest.mark.asyncio
async def test_research_index_refresh_removes_stale_invalid_backup(tmp_path: Path) -> None:
    research_dir = tmp_path / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "RESEARCH_A.md").write_text("# A\n", encoding="utf-8")

    index_path = research_dir / "INDEX.md"
    index_path.write_text("invalid index body", encoding="utf-8")
    stale_backup = research_dir / "INDEX.invalid.backup"
    stale_backup.write_text("old stale backup", encoding="utf-8")

    await update_research_index(research_dir, "test_agent", repo_root=tmp_path)

    assert index_path.exists()
    assert not stale_backup.exists()


@pytest.mark.asyncio
async def test_quality_check_recovers_research_doc_after_registry_stale_rename(tmp_path: Path) -> None:
    project_root = tmp_path / "qc_recovery_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")

    canonical_doc = research_dir / "RESEARCH_W3_DATASET_FOUNDRY_CONSUMER_SOURCE_REFRESH.md"
    canonical_doc.write_text("# Research\nEvidence.\n", encoding="utf-8")

    project = {
        "name": "agent_ux",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        # stale mapping points at missing path
        "docs": {
            "research_RESEARCH_W3_DATASET_FOUNDRY_CONSUMER_SOURCE_REFRESH": str(
                research_dir / "research_RESEARCH_W3_DATASET_FOUNDRY_CONSUMER_SOURCE_REFRESH.md"
            ),
        },
    }
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_manage_docs_server(state_manager, project_root=project_root, session_id="qc-recovery-session"):
        result = await manage_docs(
            action="quality_check",
            doc_name="RESEARCH_W3_DATASET_FOUNDRY_CONSUMER_SOURCE_REFRESH",
            doc_category="research",
            dry_run=True,
            agent="test_agent",
        )

    assert result["ok"] is True, result
    scope = result.get("scope", {})
    assert scope.get("path") == str(canonical_doc)


@pytest.mark.asyncio
async def test_quality_check_research_prefers_canonical_research_dir_over_top_level_fallback(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "qc_precedence_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")

    doc_name = "RESEARCH_W3_DATASET_FOUNDRY_CONSUMER_SOURCE_REFRESH"
    misplaced_top_level = docs_dir / f"{doc_name}.md"
    canonical_doc = research_dir / f"{doc_name}.md"
    misplaced_top_level.write_text("# Wrong\nTop-level misplaced content.\n", encoding="utf-8")
    canonical_doc.write_text("# Right\nCanonical research content.\n", encoding="utf-8")

    project = {
        "name": "agent_ux",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(progress_log),
        "docs": {},
    }
    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(project["name"], project)

    with _isolated_manage_docs_server(state_manager, project_root=project_root, session_id="qc-precedence-session"):
        result = await manage_docs(
            action="quality_check",
            doc_name=doc_name,
            doc_category="research",
            dry_run=True,
            agent="test_agent",
        )

    assert result["ok"] is True, result
    scope = result.get("scope", {})
    assert scope.get("path") == str(canonical_doc)
    assert scope.get("path") != str(misplaced_top_level)


@pytest.mark.asyncio
async def test_rehome_research_doc_refreshes_indexes_and_returns_path_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source_repo"
    target_root = tmp_path / "target_repo"
    source_docs_dir = source_root / ".scribe" / "docs" / "dev_plans" / "p1"
    target_docs_dir = target_root / ".scribe" / "docs" / "dev_plans" / "p2"
    source_research = source_docs_dir / "research"
    target_research = target_docs_dir / "research"
    source_research.mkdir(parents=True, exist_ok=True)
    target_research.mkdir(parents=True, exist_ok=True)

    source_doc = source_research / "RESEARCH_MOVE.md"
    source_doc.write_text("# Move me\n", encoding="utf-8")
    (source_research / "INDEX.md").write_text("# idx\n", encoding="utf-8")
    (target_research / "INDEX.md").write_text("# idx\n", encoding="utf-8")

    refresh_calls: list[Path] = []

    async def _capture_refresh(path: Path, _agent_id: str, repo_root=None) -> None:
        _ = repo_root
        refresh_calls.append(path)

    monkeypatch.setattr(
        "scribe_mcp.doc_management.runtime.special_indexes_shared.update_research_index",
        _capture_refresh,
    )

    class _Backend:
        async def update_project_docs(self, _name: str, _docs_json: str, **_kwargs: Any) -> None:
            return None

    class _StateMgr:
        async def set_current_project(self, *_args, **_kwargs) -> None:
            return None

    class _Server:
        storage_backend = _Backend()
        state_manager = _StateMgr()

    class _Helper2:
        @staticmethod
        def apply_context_payload(payload, _ctx):
            return payload

        @staticmethod
        def error_response(message: str, extra=None):
            out = {"ok": False, "error": message}
            if extra:
                out["extra"] = extra
            return out

    active_project = {
        "name": "source_project",
        "root": str(source_root),
        "docs_dir": str(source_docs_dir),
        "docs": {"research_move": str(source_doc)},
        "progress_log": str(source_docs_dir / "PROGRESS_LOG.md"),
    }
    target_project = {
        "name": "target_project",
        "root": str(target_root),
        "docs_dir": str(target_docs_dir),
        "docs": {},
        "progress_log": str(target_docs_dir / "PROGRESS_LOG.md"),
    }

    async def _fake_load_project_record(*, project_name: str, server_module):
        _ = server_module
        return target_project if project_name == "target_project" else None

    monkeypatch.setattr("scribe_mcp.doc_management.runtime._load_project_record", _fake_load_project_record)

    response = await _handle_rehome_doc(
        active_project=active_project,
        doc_name="research_move",
        metadata={"target_project": "target_project"},
        dry_run=False,
        helper=_Helper2(),
        context=None,
        execution_context=type("Ctx", (), {})(),
        server_module=_Server(),
        agent_id="test_agent",
    )

    assert response["ok"] is True, response
    assert response["requested_doc_name"] == "research_move"
    assert response["canonical_doc_name"] == "research_move"
    assert response["final_path"].endswith("RESEARCH_MOVE.md")
    verification = response.get("rehome_verification") or {}
    assert verification["file_location"]["ok"] is True
    assert verification["registry_mapping"]["target_mapping_written"] is True
    assert verification["quality_check_binding"]["doc"] == "research_move"
    assert verification["quality_check_binding"]["attempted"] is True
    assert isinstance(verification["quality_check_binding"]["ok"], bool)
    assert isinstance((verification["quality_check_binding"].get("summary") or {}).get("total_warnings"), int)
    assert isinstance((verification["quality_check_binding"].get("summary") or {}).get("readiness_blocker_count"), int)
    readiness = verification.get("readiness") or {}
    assert readiness["attempted"] is True
    assert isinstance(readiness["ok"], bool)
    assert isinstance(readiness["readiness_blocker_count"], int)
    assert verification["index_freshness"]["source_research_index_refresh"] == "updated"
    assert verification["index_freshness"]["target_research_index_refresh"] == "updated"
    assert source_research in refresh_calls
    assert target_research in refresh_calls
