"""End-to-end tests for Jinja2 template engine and manage_docs integration."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Dict
from uuid import uuid4

import pytest

from scribe_mcp.doc_management.manager import (
    apply_doc_change,
    DocumentOperationError,
    SECTION_MARKER,
    _replace_section,
    _toggle_checklist_status,
)
from scribe_mcp import server as server_module
from scribe_mcp.state import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.template_engine import Jinja2TemplateEngine
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.tools import manage_docs as manage_docs_module
from scribe_mcp.utils.frontmatter import parse_frontmatter


def test_template_engine_renders_builtin_and_custom_templates(tmp_path: Path) -> None:
    """Ensure every built-in document template renders and custom overrides work."""
    repo_root = Path(__file__).resolve().parents[1]
    engine = Jinja2TemplateEngine(project_root=repo_root, project_name="Template QA")

    documents_dir = repo_root / "src" / "scribe_mcp" / "templates" / "documents"
    templates_rendered = 0
    metadata = {
        "author": "QA Bot",
        "summary": "Automated coverage",
        "problem_statement": {
            "context": "Test harness",
            "goals": ["Exercise templates"],
            "non_goals": [],
            "success_metrics": ["All templates render"],
        },
        "requirements": {
            "functional": ["Render templates"],
            "non_functional": [],
            "assumptions": [],
            "risks": [],
        },
        "architecture_overview": {
            "summary": "Test overview",
            "components": [
                {
                    "name": "engine",
                    "description": "Rendering pipeline",
                    "interfaces": "Inputs/Outputs",
                    "notes": "Core logic",
                }
            ],
            "data_flow": "n/a",
            "external_integrations": "n/a",
        },
        "subsystems": [
            {
                "name": "engine",
                "purpose": "Test",
                "interfaces": "n/a",
                "notes": "n/a",
                "error_handling": "n/a",
            }
        ],
        "directory_structure": "/tmp/project\n├── docs/\n└── src/",
        "data_storage": {},
        "testing_strategy": {},
        "deployment": {},
        "open_questions": [],
        "references": ["Design doc", "ADR-001"],
        "appendix": "Extended data",
        "phases": [
            {
                "name": "Foundation",
                "goal": "Stabilize writer",
                "deliverables": ["Async write", "DB schema"],
                "confidence": 0.95,
                "anchor": "phase_foundation",
                "tasks": ["Add async_atomic_write", "Add verification"],
                "acceptance": [
                    {"label": "No silent failures", "proof": "tests"},
                    {"label": "DB stays in sync", "proof": "fts"},
                ],
                "dependencies": "SQLite",
                "notes": "Baseline reliability",
            },
            {
                "name": "Templates",
                "goal": "Ship Jinja2 engine",
                "deliverables": ["Base templates", "CLI"],
                "confidence": 0.85,
                "anchor": "phase_templates",
                "tasks": ["Add base_document", "Add base_log"],
                "acceptance": [
                    {"label": "All templates render", "proof": "pytest"},
                ],
                "dependencies": "Phase 0",
                "notes": "Introduce inheritance",
            },
        ],
        "milestones": [
            {
                "name": "Phase 0 Complete",
                "target": "2025-10-29",
                "owner": "DevTeam",
                "status": "✅ Complete",
                "evidence": "PROGRESS_LOG#123",
            }
        ],
        "sections": [
            {
                "title": "Documentation Hygiene",
                "anchor": "documentation_hygiene",
                "items": [
                    {"label": "Architecture guide updated", "proof": "log#1"},
                    {"label": "Phase plan current", "proof": "log#2"},
                ],
            },
            {
                "title": "Phase 0",
                "anchor": "phase_0",
                "items": [
                    {"label": "Async bug fixed", "proof": "commit123"},
                ],
            },
        ],
    }

    for template_path in documents_dir.glob("*.md"):
        template_name = f"documents/{template_path.name}"
        rendered = engine.render_template(template_name, metadata=metadata)
        assert "Template QA" in rendered
        assert rendered.strip(), f"{template_name} should not render empty content"
        templates_rendered += 1

    assert templates_rendered > 0, "Expected to render at least one built-in template"

    # Custom project overrides (.scribe/templates) should take precedence
    project_root = tmp_path / "custom_repo"
    (project_root / ".scribe" / "templates").mkdir(parents=True, exist_ok=True)
    custom_template = project_root / ".scribe" / "templates" / "welcome.md"
    custom_template.write_text("# Welcome {{ project_name }} :: {{ metadata.note }}", encoding="utf-8")

    custom_engine = Jinja2TemplateEngine(project_root=project_root, project_name="Custom Project")
    custom_rendered = custom_engine.render_template("welcome.md", metadata={"note": "Rendered"})

    assert "Custom Project :: Rendered" in custom_rendered


@pytest.mark.asyncio
async def test_manage_docs_renders_jinja_content_and_custom_templates(tmp_path: Path) -> None:
    """Verify manage_docs updates sections via inline Jinja content and custom templates."""
    repo_root = Path(__file__).resolve().parents[1]
    test_root = repo_root / "tmp_tests" / f"manage_docs_{uuid4().hex}"
    project_root = test_root
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "# Architecture\n"
        "<!-- ID: problem_statement -->\n"
        "Old problem statement\n\n"
        "<!-- ID: requirements_constraints -->\n"
        "Old requirements section\n",
        encoding="utf-8",
    )

    # Create placeholder files for other doc references
    for name in ("PHASE_PLAN", "CHECKLIST", "PROGRESS_LOG"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    project: Dict[str, object] = {
        "name": "Test Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }

    # Replace the problem_statement section using inline Jinja content
    metadata = {"note": "Upgraded via test"}
    change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_section",
        section="problem_statement",
        content="**Project:** {{ project_name }} | Note: {{ metadata.note }}",
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata=metadata,
        dry_run=False,
    )

    assert change.success
    assert change.verification_passed
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "**Project:** Test Project | Note: Upgraded via test" in updated_text
    preflight_backup = change.extra.get("preflight_backup")
    assert isinstance(preflight_backup, str) and preflight_backup
    preflight_backup_path = Path(preflight_backup)
    assert preflight_backup_path.is_file()
    assert preflight_backup_path.suffix == ".bak"
    expected_archive_dir = docs_dir / "archive" / "preflight" / "planning"
    assert preflight_backup_path.parent == expected_archive_dir
    assert "ARCHITECTURE_GUIDE" in preflight_backup_path.name
    assert ".preflight-" in preflight_backup_path.name
    assert not list(architecture_path.parent.glob("ARCHITECTURE_GUIDE.preflight-*.bak"))

    # Append additional content via a custom template stored under .scribe/templates
    custom_templates_dir = project_root / ".scribe" / "templates"
    custom_templates_dir.mkdir(parents=True, exist_ok=True)
    (custom_templates_dir / "summary_block.md").write_text(
        "### Auto Summary\nContext: {{ metadata.context }}\n", encoding="utf-8"
    )

    metadata_append = {"context": "manage_docs+jinja"}
    append_change = await apply_doc_change(
        project,
        doc="architecture",
        action="append",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        start_line=None,
        end_line=None,
        template="summary_block",
        metadata=metadata_append,
        dry_run=False,
    )

    assert append_change.success
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "### Auto Summary" in updated_text
    assert "Context: manage_docs+jinja" in updated_text

    shutil.rmtree(test_root, ignore_errors=True)


@pytest.mark.asyncio
async def test_manage_docs_apply_patch_and_replace_range(tmp_path: Path) -> None:
    """Verify apply_patch and replace_range operations on documents."""
    project_root = tmp_path / "patch_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "alpha\nbeta\ngamma\n",
        encoding="utf-8",
    )

    project: Dict[str, object] = {
        "name": "Patch Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }

    patch_text = "\n".join(
        [
            "--- before",
            "+++ after",
            "@@ -1,3 +1,3 @@",
            "-alpha",
            "+alpha updated",
            " beta",
            " gamma",
        ]
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "alpha updated" in updated_text

    range_change = await apply_doc_change(
        project,
        doc="architecture",
        action="replace_range",
        section=None,
        content="BETA\nGAMMA\n",
        patch=None,
        patch_source_hash=None,
        start_line=2,
        end_line=3,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert range_change.success
    updated_text = architecture_path.read_text(encoding="utf-8")
    assert "BETA" in updated_text
    assert "GAMMA" in updated_text


@pytest.mark.asyncio
async def test_manage_docs_apply_patch_mismatch_fails(tmp_path: Path) -> None:
    """Verify apply_patch fails with strict context mismatch."""
    project_root = tmp_path / "patch_repo_mismatch"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "alpha\nbeta\ngamma\n",
        encoding="utf-8",
    )

    project: Dict[str, object] = {
        "name": "Patch Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }

    patch_text = "\n".join(
        [
            "--- before",
            "+++ after",
            "@@ -1,3 +1,3 @@",
            "-delta",
            "+delta updated",
            " beta",
            " gamma",
        ]
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash=None,
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "PATCH_DELETE_MISMATCH" in (change.error_message or "")


@pytest.mark.asyncio
async def test_manage_docs_apply_patch_stale_source_fails(tmp_path: Path) -> None:
    """Verify apply_patch fails when patch_source_hash does not match current file."""
    project_root = tmp_path / "patch_repo_stale"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "alpha\nbeta\ngamma\n",
        encoding="utf-8",
    )

    project: Dict[str, object] = {
        "name": "Patch Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }

    patch_text = "\n".join(
        [
            "--- before",
            "+++ after",
            "@@ -1,3 +1,3 @@",
            "-alpha",
            "+alpha updated",
            " beta",
            " gamma",
        ]
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=patch_text,
        patch_source_hash="deadbeef",
        patch_mode="unified",
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "PATCH_STALE_SOURCE" in (change.error_message or "")
    assert change.extra.get("precondition_failed") == "SOURCE_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_special_document_templates_and_agent_card_storage(tmp_path: Path) -> None:
    """Ensure special document creation uses Jinja templates and stores agent metrics."""
    project_name = "TestProject"
    repo_root = Path(__file__).resolve().parents[1]
    project_root = repo_root / "tmp_tests" / f"manage_docs_special_{uuid4().hex}"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / project_name
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Seed required doc files
    for name in ("ARCHITECTURE_GUIDE", "PHASE_PLAN", "CHECKLIST", "PROGRESS_LOG"):
        (docs_dir / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    original_state_manager = server_module.state_manager
    original_storage_backend = server_module.storage_backend

    state_manager = StateManager(path=tmp_path / "state.json")
    storage = SQLiteStorage(tmp_path / "scribe.db")
    await storage.setup()

    server_module.state_manager = state_manager
    server_module.storage_backend = storage

    had_get_execution_context = hasattr(server_module, "get_execution_context")
    had_get_agent_identity = hasattr(server_module, "get_agent_identity")
    original_get_execution_context = getattr(server_module, "get_execution_context", None)
    original_get_agent_identity = getattr(server_module, "get_agent_identity", None)
    original_prepare_context = manage_docs_module._MANAGE_DOCS_HELPER.prepare_context

    try:
        server_module.get_execution_context = lambda: SimpleNamespace(mode="local")
        server_module.get_agent_identity = lambda: None
        async def _prepare_context_stub(**kwargs):
            state = await state_manager.load()
            current_project = state.get_project(state.current_project) if state.current_project else None
            return SimpleNamespace(
                tool_name=str(kwargs.get("tool_name") or "manage_docs"),
                project=current_project,
                recent_projects=list(getattr(state, "recent_projects", []) or []),
                state_snapshot=kwargs.get("state_snapshot") if isinstance(kwargs.get("state_snapshot"), dict) else {},
                reminders=[],
                agent_id="test_agent",
                resolution_source="compat_active_project",
                fallback_used=False,
                fallback_chain=[],
                denied_fallback_attempts=[],
                compatibility_usage={"requested": True, "requested_mode": "compat_active_project", "applied": True},
            )
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = _prepare_context_stub
        project_config = {
            "name": project_name,
            "root": str(project_root),
            "docs_dir": str(docs_dir),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            "docs": {
                "architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"),
                "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
                "checklist": str(docs_dir / "CHECKLIST.md"),
                "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
            },
            "defaults": {"agent": "QA Bot"},
        }

        await state_manager.set_current_project(project_name, project_config)

        # Dry-run research doc to confirm templated content
        research_result = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            doc_name="architecture_findings",
            metadata={"doc_type": "research", "objective": "Assess coverage"},
            dry_run=True,
        )
        assert research_result["ok"]
        assert "## Executive Summary" in research_result["content"]
        assert "## Research Scope" in research_result["content"]

        # Explicit body/snippet payload should bypass template rendering.
        explicit_body = "# Body Override\n\nEvidence payload"
        research_body_result = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            doc_name="body_override_findings",
            metadata={"doc_type": "research", "body": explicit_body},
            dry_run=True,
        )
        assert research_body_result["ok"]
        assert research_body_result["content"] == explicit_body + "\n"
        assert "## Executive Summary" not in research_body_result["content"]

        # Dry-run bug report to confirm templated content
        bug_result = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            metadata={"doc_type": "bug", "category": "backend", "severity": "high"},
            dry_run=True,
        )
        assert bug_result["ok"]
        assert "## Bug Overview" in bug_result["content"]
        assert "## Resolution Plan" in bug_result["content"]

        # Existing special docs should require explicit overwrite to replace content.
        first_write = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            doc_name="overwrite_guard_findings",
            metadata={"doc_type": "research", "body": "# First Pass"},
            dry_run=False,
        )
        assert first_write["ok"]

        second_write = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            doc_name="overwrite_guard_findings",
            metadata={"doc_type": "research", "body": "# Second Pass"},
            dry_run=False,
        )
        assert second_write["ok"] is False
        assert "CREATE_DOC_EXISTS" in second_write.get("error", "")

        overwrite_write = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            doc_name="overwrite_guard_findings",
            metadata={"doc_type": "research", "body": "# Second Pass", "overwrite": True},
            dry_run=False,
        )
        assert overwrite_write["ok"]
        assert Path(overwrite_write["path"]).read_text(encoding="utf-8") == "# Second Pass\n"

        # Metadata JSON arrays should normalize without failing
        array_meta_result = await manage_docs(
            agent="test_agent",
            action="append",
            doc="phase_plan",
            content="Iteration planning update",
            metadata="[]",
            dry_run=True,
        )
        assert array_meta_result["ok"]

        append_inside_result = await manage_docs(
            agent="test_agent",
            action="append",
            doc="architecture",
            section="problem_statement",
            content="Inserted via inside append",
            metadata={"position": "inside"},
            dry_run=False,
        )
        assert append_inside_result["ok"]

        architecture_path = Path(project_config["docs"]["architecture"])
        architecture_text = architecture_path.read_text(encoding="utf-8")
        assert "Inserted via inside append" in architecture_text

        batch_result = await manage_docs(
            agent="test_agent",
            action="batch",
            doc="architecture",
            metadata={
                "operations": [
                    {
                        "action": "append",
                        "doc": "architecture",
                        "section": "requirements_constraints",
                        "content": "Batch item one",
                        "metadata": {"position": "after"},
                        "dry_run": False,
                    },
                    {
                        "action": "append",
                        "doc": "architecture",
                        "section": "architecture_overview",
                        "content": "Batch item two",
                        "metadata": {"position": "inside"},
                        "dry_run": False,
                    },
                ]
            },
        )
        assert batch_result["ok"]

        architecture_text = architecture_path.read_text(encoding="utf-8")
        assert "Batch item one" in architecture_text
        assert "Batch item two" in architecture_text

        sections_result = await manage_docs(
            agent="test_agent",
            action="list_sections",
            doc="architecture",
        )
        assert sections_result["ok"]
        assert any(section["id"] == "problem_statement" for section in sections_result["sections"])

        architecture_path.write_text(
            "line 1\nline 2\nline 3\nline 4\nline 5\n",
            encoding="utf-8",
        )

        batch_ranges = await manage_docs(
            agent="test_agent",
            action="batch",
            doc="architecture",
            metadata={
                "operations": [
                    {
                        "action": "replace_range",
                        "doc": "architecture",
                        "start_line": 2,
                        "end_line": 2,
                        "content": "line 2a\nline 2b",
                        "metadata": {"line_reference": "body"},
                        "dry_run": False,
                    },
                    {
                        "action": "replace_range",
                        "doc": "architecture",
                        "start_line": 4,
                        "end_line": 4,
                        "content": "line 4 updated",
                        "metadata": {"line_reference": "body"},
                        "dry_run": False,
                    },
                ]
            },
        )
        assert batch_ranges["ok"]
        assert batch_ranges["warnings"]

        architecture_text = architecture_path.read_text(encoding="utf-8")
        parsed_architecture = parse_frontmatter(architecture_text)
        assert parsed_architecture.body.splitlines() == [
            "line 1",
            "line 2a",
            "line 2b",
            "line 3",
            "line 4 updated",
            "line 5",
        ]

        # Create an agent report card and ensure storage captures metrics
        agent_metadata = {
            "agent_name": "Ai-Dev",
            "stage": "review",
            "overall_grade": "92%",
            "performance_level": "EXCELLENT",
        }
        agent_result = await manage_docs(
            agent="test_agent",
            action="create",
            doc="architecture",
            metadata={"doc_type": "agent_card", **agent_metadata},
            dry_run=False,
        )
        assert agent_result["ok"]
        card_path = Path(agent_result["path"])
        assert card_path.exists()
        assert agent_result["document_type"] == "agent_report_card"

        conn = sqlite3.connect(storage._path)
        try:
            card_rows = conn.execute(
                "SELECT agent_name, stage, overall_grade, performance_level, metadata FROM agent_report_cards"
            ).fetchall()
            assert len(card_rows) == 1
            agent_name, stage, overall_grade, performance_level, metadata_json = card_rows[0]
            assert agent_name == "Ai-Dev"
            assert stage == "review"
            assert pytest.approx(overall_grade, rel=1e-6) == 92.0
            assert performance_level == "EXCELLENT"
            assert "Ai-Dev" in metadata_json

            doc_changes = conn.execute(
                "SELECT doc_name FROM doc_changes WHERE doc_name = 'agent_report_card'"
            ).fetchall()
            assert doc_changes, "Expected doc_changes entry for agent report card"

            section_columns = {row[1] for row in conn.execute("PRAGMA table_info(document_sections)").fetchall()}
            assert {"project_root", "file_path", "relative_path"}.issubset(section_columns)

            sync_columns = {row[1] for row in conn.execute("PRAGMA table_info(sync_status)").fetchall()}
            assert "project_root" in sync_columns

            changes_columns = {row[1] for row in conn.execute("PRAGMA table_info(document_changes)").fetchall()}
            assert "project_root" in changes_columns
        finally:
            conn.close()
    finally:
        await storage.close()
        server_module.state_manager = original_state_manager
        server_module.storage_backend = original_storage_backend
        if had_get_execution_context:
            server_module.get_execution_context = original_get_execution_context
        elif hasattr(server_module, "get_execution_context"):
            delattr(server_module, "get_execution_context")
        if had_get_agent_identity:
            server_module.get_agent_identity = original_get_agent_identity
        elif hasattr(server_module, "get_agent_identity"):
            delattr(server_module, "get_agent_identity")
        manage_docs_module._MANAGE_DOCS_HELPER.prepare_context = original_prepare_context
        shutil.rmtree(project_root, ignore_errors=True)


def test_replace_section_auto_inserts_anchor() -> None:
    original = "# Document\n"
    result = _replace_section(original, "auto_section", "Healed content block", allow_append=True)
    marker = SECTION_MARKER.format(section="auto_section")
    assert marker in result
    assert "Healed content block" in result


def test_replace_section_missing_anchor_requires_allow_append() -> None:
    original = "# Document\n"
    with pytest.raises(DocumentOperationError):
        _replace_section(original, "missing_section", "Content")


def test_replace_section_duplicate_anchor_fails() -> None:
    marker = SECTION_MARKER.format(section="dup_section")
    original = f"{marker}\nFirst\n\n{marker}\nSecond\n"
    with pytest.raises(DocumentOperationError):
        _replace_section(original, "dup_section", "Content")


def test_toggle_checklist_status_metadata_only_updates_proof() -> None:
    marker = SECTION_MARKER.format(section="phase_0")
    original = f"{marker}\n- [ ] Ship feature\n"
    updated = _toggle_checklist_status(original, "phase_0", {"proof": "commit123"})
    assert "- [ ] Ship feature | proof=commit123" in updated


def test_toggle_checklist_status_creates_section_when_missing_when_allowed() -> None:
    original = "# Checklist\n"
    updated = _toggle_checklist_status(
        original,
        "phase_1",
        {
            "status": "done",
            "proof": "log#1",
            "label": "Ship UI",
            "allow_append": True,
        },
    )
    marker = SECTION_MARKER.format(section="phase_1")
    assert marker in updated
    assert "- [x] Ship UI | proof=log#1" in updated


def test_toggle_checklist_status_missing_section_fails_hard_by_default() -> None:
    original = "# Checklist\n- [ ] Existing item\n"
    with pytest.raises(DocumentOperationError):
        _toggle_checklist_status(
            original,
            "phase_1",
            {"status": "done", "proof": "log#2", "label": "Ship API"},
        )


def test_toggle_checklist_status_updates_inline_section_anchor_without_appending() -> None:
    original = "# Checklist\n- [ ] Ship docs <!-- ID: p4_documents -->\n- [ ] Ship API <!-- ID: p4_api -->\n"
    updated = _toggle_checklist_status(
        original,
        "p4_documents",
        {"status": "done", "proof": "commit_abc"},
    )
    assert "- [x] Ship docs | proof=commit_abc <!-- ID: p4_documents -->" in updated
    assert "<!-- ID: p4_documents -->" in updated
    assert "\n\n<!-- ID: p4_documents -->\n" not in updated


def test_toggle_checklist_status_requires_explicit_scope_for_multi_item_section() -> None:
    marker = SECTION_MARKER.format(section="phase_0")
    original = (
        f"{marker}\n"
        "- [ ] Ship docs\n"
        "- [ ] Ship API\n"
        "- [x] Ship tests | proof=old\n"
        "<!-- ID: phase_1 -->\n"
        "- [ ] Later\n"
    )

    with pytest.raises(DocumentOperationError) as exc_info:
        _toggle_checklist_status(
            original,
            "phase_0",
            {"status": "done", "proof": "commit_xyz"},
        )

    assert "CHECKLIST_SECTION_AMBIGUOUS" in str(exc_info.value)


def test_toggle_checklist_status_updates_all_items_when_explicitly_requested() -> None:
    marker = SECTION_MARKER.format(section="phase_0")
    original = (
        f"{marker}\n"
        "- [ ] Ship docs\n"
        "- [ ] Ship API\n"
        "- [x] Ship tests | proof=old\n"
        "<!-- ID: phase_1 -->\n"
        "- [ ] Later\n"
    )

    updated = _toggle_checklist_status(
        original,
        "phase_0",
        {"status": "done", "proof": "commit_xyz", "all_items": True},
    )

    assert "- [x] Ship docs | proof=commit_xyz" in updated
    assert "- [x] Ship API | proof=commit_xyz" in updated
    assert "- [x] Ship tests | proof=commit_xyz" in updated
    assert "- [ ] Later" in updated


def test_toggle_checklist_status_targets_label_within_section() -> None:
    marker = SECTION_MARKER.format(section="phase_0")
    original = (
        f"{marker}\n"
        "- [ ] Ship docs\n"
        "- [ ] Ship API\n"
        "<!-- ID: phase_1 -->\n"
        "- [ ] Later\n"
    )

    updated = _toggle_checklist_status(
        original,
        "phase_0",
        {"status": "done", "proof": "commit_api", "label": "Ship API"},
    )

    assert "- [ ] Ship docs" in updated
    assert "- [x] Ship API | proof=commit_api" in updated
    assert "- [ ] Later" in updated


def test_toggle_checklist_status_targets_item_index_within_section() -> None:
    marker = SECTION_MARKER.format(section="phase_0")
    original = (
        f"{marker}\n"
        "- [ ] Ship docs\n"
        "- [ ] Ship API\n"
        "- [ ] Ship tests\n"
    )

    updated = _toggle_checklist_status(
        original,
        "phase_0",
        {"status": "done", "proof": "commit_idx", "item_index": 2},
    )

    assert "- [ ] Ship docs" in updated
    assert "- [x] Ship API | proof=commit_idx" in updated
    assert "- [ ] Ship tests" in updated
