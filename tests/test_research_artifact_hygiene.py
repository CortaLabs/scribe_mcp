from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scribe_mcp.doc_management.special_create import handle_special_document_creation


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


@pytest.mark.asyncio
async def test_research_create_respects_explicit_target_dir_override(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "agent_ux"
    docs_dir.mkdir(parents=True, exist_ok=True)
    progress_log = docs_dir / "PROGRESS_LOG.md"
    progress_log.write_text("# Log\n", encoding="utf-8")
    explicit_dir = project_root / "docs" / "dev_plans" / "agent_ux" / "research"

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
        target_dir=str(explicit_dir),
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
    assert created_path.parent == explicit_dir
    assert "explicit research override active" in result.get("placement_warning", "").lower()
