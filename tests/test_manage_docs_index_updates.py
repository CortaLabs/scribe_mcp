"""
Test index updates after document edits (Phase 4: Index Update Event Coverage).

Verifies that INDEX.md files are updated when special docs are edited,
not just when they're created.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest

from scribe_mcp.doc_management.utils import (
    classify_scribe_source_document,
    discover_scribe_source_documents,
)
from scribe_mcp.doc_management import special_create as special_create_shared
from scribe_mcp.tools.manage_docs import manage_docs, _get_index_updater_for_path


@pytest.mark.asyncio
async def test_index_updater_detection_research():
    """Test _get_index_updater_for_path detects research docs correctly."""
    print("\n1. Testing index updater detection for research docs...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)

        # Create a research doc path
        research_doc = research_dir / "RESEARCH_TEST_20260120.md"
        research_doc.write_text("# Test Research\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=research_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect research doc and return updater"
        print("✅ Research doc detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_bug():
    """Test _get_index_updater_for_path detects bug reports correctly."""
    print("\n2. Testing index updater detection for bug reports...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        bugs_dir = project_root / "docs" / "bugs" / "logic" / "2026-01-20_auth_leak"
        bugs_dir.mkdir(parents=True, exist_ok=True)

        # Create a bug report path
        bug_doc = bugs_dir / "report.md"
        bug_doc.write_text("# Bug Report\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=bug_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect bug report and return updater"
        print("✅ Bug report detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_security():
    """Test _get_index_updater_for_path detects security reports correctly."""
    print("\n3. Testing index updater detection for security reports...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        security_dir = project_root / "docs" / "security" / "auth" / "2026-01-20_token_leak"
        security_dir.mkdir(parents=True, exist_ok=True)

        security_doc = security_dir / "report.md"
        security_doc.write_text("# Security Report\n")

        updater = _get_index_updater_for_path(
            file_path=security_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect security report and return updater"
        print("✅ Security report detection works")


@pytest.mark.asyncio
async def test_index_updater_routes_bug_reports_to_collection_root(monkeypatch):
    """Bug report edits should refresh docs/bugs/INDEX.md, not a category-local index."""
    captured = {}

    async def _capture_bug_index(path: Path, agent_id: str, repo_root: Path | None = None) -> None:
        captured["path"] = path
        captured["agent_id"] = agent_id
        captured["repo_root"] = repo_root

    monkeypatch.setattr(special_create_shared, "_update_bug_index", _capture_bug_index)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        bug_report_dir = project_root / "docs" / "bugs" / "logic" / "2026-01-20_auth_leak"
        bug_report_dir.mkdir(parents=True, exist_ok=True)
        bug_doc = bug_report_dir / "report.md"
        bug_doc.write_text("# Bug Report\n")

        updater = _get_index_updater_for_path(
            file_path=bug_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent",
        )

        assert updater is not None
        await updater()
        assert captured["path"] == project_root / "docs" / "bugs"


@pytest.mark.asyncio
async def test_index_updater_routes_security_reports_to_collection_root(monkeypatch):
    """Security report edits should refresh docs/security/INDEX.md, not a category-local index."""
    captured = {}

    async def _capture_bug_index(path: Path, agent_id: str, repo_root: Path | None = None) -> None:
        captured["path"] = path
        captured["agent_id"] = agent_id
        captured["repo_root"] = repo_root

    monkeypatch.setattr(special_create_shared, "_update_security_index", _capture_bug_index)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        security_report_dir = project_root / "docs" / "security" / "auth" / "2026-01-20_token_leak"
        security_report_dir.mkdir(parents=True, exist_ok=True)
        security_doc = security_report_dir / "report.md"
        security_doc.write_text("# Security Report\n")

        updater = _get_index_updater_for_path(
            file_path=security_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent",
        )

        assert updater is not None
        await updater()
        assert captured["path"] == project_root / "docs" / "security"


@pytest.mark.asyncio
async def test_index_updater_detection_review():
    """Test _get_index_updater_for_path detects review reports correctly."""
    print("\n4. Testing index updater detection for review reports...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create a review report path
        review_doc = docs_dir / "REVIEW_REPORT_phase1_2026-01-20_1430.md"
        review_doc.write_text("# Review Report\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=review_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect review report and return updater"
        print("✅ Review report detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_agent_card():
    """Test _get_index_updater_for_path detects agent cards correctly."""
    print("\n5. Testing index updater detection for agent cards...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create an agent card path
        card_doc = docs_dir / "AGENT_REPORT_CARD_Coder_phase1_20260120_1430.md"
        card_doc.write_text("# Agent Report Card\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=card_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is not None, "Should detect agent card and return updater"
        print("✅ Agent card detection works")


@pytest.mark.asyncio
async def test_index_updater_detection_regular_doc():
    """Test _get_index_updater_for_path returns None for regular docs."""
    print("\n6. Testing index updater returns None for regular docs...")
    print("-" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create a regular managed doc path (not special)
        regular_doc = docs_dir / "ARCHITECTURE_GUIDE.md"
        regular_doc.write_text("# Architecture\n")

        # Get index updater
        updater = _get_index_updater_for_path(
            file_path=regular_doc,
            project_root=project_root,
            docs_dir=docs_dir,
            agent_id="test_agent"
        )

        assert updater is None, "Should return None for regular managed docs"
        print("✅ Regular doc detection works (returns None)")


def test_discover_scribe_source_documents_enumerates_canonical_families():
    """Discovery should enumerate canonical dev-plan and case-report corpora."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)

        (research_dir / "RESEARCH_TEST.md").write_text("# Research\n")
        (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n")
        (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n")
        (docs_dir / "CHECKLIST.md").write_text("# Checklist\n")

        bug_report = project_root / "docs" / "bugs" / "logic" / "2026-01-20_loop_bug"
        bug_report.mkdir(parents=True, exist_ok=True)
        (bug_report / "report.md").write_text("---\ncase_id: BUG-2026-001\ndoc_type: bug\n---\n# Bug\n")

        security_report = project_root / "docs" / "security" / "auth" / "2026-01-20_token_leak"
        security_report.mkdir(parents=True, exist_ok=True)
        (security_report / "report.md").write_text(
            "---\ncase_id: SEC-2026-001\ndoc_type: security\n---\n# Security\n"
        )

        discovered = discover_scribe_source_documents(project_root)
        discovered_types = {(doc.source_family, doc.doc_type) for doc in discovered}

        assert ("dev_plan", "research") in discovered_types
        assert ("dev_plan", "architecture_guide") in discovered_types
        assert ("dev_plan", "phase_plan") in discovered_types
        assert ("dev_plan", "checklist") in discovered_types
        assert ("case_report", "bug_report") in discovered_types
        assert ("case_report", "security_report") in discovered_types


def test_discover_scribe_source_documents_supports_legacy_docs_dev_plans():
    """Discovery should still enumerate legacy docs/dev_plans repos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        docs_dir = project_root / "docs" / "dev_plans" / "legacy_project"
        research_dir = docs_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)

        (research_dir / "RESEARCH_TEST.md").write_text("# Research\n")
        (docs_dir / "ARCHITECTURE_GUIDE.md").write_text("# Architecture\n")
        discovered = discover_scribe_source_documents(project_root)

        discovered_paths = {doc.path for doc in discovered}
        assert research_dir / "RESEARCH_TEST.md" in discovered_paths
        assert docs_dir / "ARCHITECTURE_GUIDE.md" in discovered_paths


def test_discover_scribe_source_documents_supports_explicit_custom_dev_plans_dir():
    """Discovery should respect an explicit custom dev_plans root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        custom_root = project_root / "artifacts" / "plans"
        docs_dir = custom_root / "custom_project"
        docs_dir.mkdir(parents=True, exist_ok=True)

        (docs_dir / "CHECKLIST.md").write_text("# Checklist\n")
        discovered = discover_scribe_source_documents(project_root, dev_plans_dir=custom_root)

        assert any(doc.path == docs_dir / "CHECKLIST.md" for doc in discovered)


def test_classification_prefers_metadata_over_case_report_path():
    """SEC metadata under docs/bugs should classify as security, not bug."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        misplaced_security = (
            project_root / "docs" / "bugs" / "auth" / "2026-01-20_token_leak" / "report.md"
        )
        misplaced_security.parent.mkdir(parents=True, exist_ok=True)
        misplaced_security.write_text(
            "---\ncase_id: SEC-2026-001\ndoc_type: security\n---\n# Security Report\n"
        )

        classified = classify_scribe_source_document(
            misplaced_security,
            project_root=project_root,
        )

        assert classified is not None
        assert classified.source_family == "case_report"
        assert classified.doc_type == "security_report"
        assert classified.category == "auth"


def test_classification_uses_case_id_prefix_before_path_fallback():
    """SEC-* case IDs under docs/bugs should still classify as security."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        misplaced_security = (
            project_root / "docs" / "bugs" / "integration" / "2026-01-20_api_leak" / "report.md"
        )
        misplaced_security.parent.mkdir(parents=True, exist_ok=True)
        misplaced_security.write_text("---\ncase_id: SEC-2026-044\n---\n# Security Report\n")

        classified = classify_scribe_source_document(
            misplaced_security,
            project_root=project_root,
        )

        assert classified is not None
        assert classified.doc_type == "security_report"
        assert classified.case_id == "SEC-2026-044"


def test_classification_honors_repo_config_doc_type_alias(tmp_path: Path) -> None:
    project_root = tmp_path
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_path = docs_dir / "INCIDENT.md"
    doc_path.write_text("---\ndoc_type: incident\n---\n# Incident\n", encoding="utf-8")

    config_dir = project_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_aliases:\n"
        "    incident: bug\n",
        encoding="utf-8",
    )

    classified = classify_scribe_source_document(
        doc_path,
        project_root=project_root,
        docs_dir=docs_dir,
    )
    assert classified is not None
    assert classified.source_family == "case_report"
    assert classified.doc_type == "bug_report"


def test_classification_honors_template_backed_doc_type(tmp_path: Path) -> None:
    project_root = tmp_path
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_path = docs_dir / "INCIDENT_TEMPLATE.md"
    doc_path.write_text("---\ndoc_type: incident\n---\n# Incident Template\n", encoding="utf-8")

    config_dir = project_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        "doc_types:\n"
        "  create_templates:\n"
        "    incident: RESEARCH_REPORT_TEMPLATE\n",
        encoding="utf-8",
    )

    classified = classify_scribe_source_document(
        doc_path,
        project_root=project_root,
        docs_dir=docs_dir,
    )
    assert classified is not None
    assert classified.source_family == "dev_plan"
    assert classified.doc_type == "incident"


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Index Update Event Coverage (Phase 4)")
    print("=" * 60)

    asyncio.run(test_index_updater_detection_research())
    asyncio.run(test_index_updater_detection_bug())
    asyncio.run(test_index_updater_detection_security())
    asyncio.run(test_index_updater_detection_review())
    asyncio.run(test_index_updater_detection_agent_card())
    asyncio.run(test_index_updater_detection_regular_doc())

    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
