#!/usr/bin/env python3
"""Test SPEC-GEN-001: Verify generate_doc_templates records baseline hashes in ProjectRegistry."""

from pathlib import Path
import sqlite3
import pytest
import asyncio

from scribe_mcp.tools.generate_doc_templates import generate_doc_templates
from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.config.settings import settings


@pytest.fixture
def temp_project_root(tmp_path: Path) -> Path:
    """Create a temporary project root directory."""
    project_root = tmp_path / "test_project"
    project_root.mkdir(parents=True)
    return project_root


@pytest.fixture
def temp_registry_db(tmp_path: Path) -> Path:
    """Create a temporary registry database."""
    db_path = tmp_path / "test_registry.db"
    return db_path


@pytest.mark.asyncio
async def test_gen_001_baseline_hash_recorded(temp_project_root: Path, temp_registry_db: Path, monkeypatch):
    """
    SPEC-GEN-001: Verify that generate_doc_templates records baseline hashes
    in ProjectRegistry for all created templates.

    This test ensures that:
    1. Template generation creates files
    2. Baseline hashes are recorded in doc_changes table
    3. before_hash == after_hash (indicating pristine template)
    4. All generated templates get hash entries
    """
    project_name = "test_gen_001_project"

    # Create a temporary registry pointing to our test DB
    registry = ProjectRegistry(db_path=str(temp_registry_db))

    # Manually insert a project row in the test database
    conn = sqlite3.connect(temp_registry_db)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, created_at, status)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'planning')
            """,
            (project_name, str(temp_project_root), str(temp_project_root / "PROGRESS_LOG.md")),
        )
        conn.commit()
    finally:
        conn.close()

    # Patch the module-level registry to use our test DB
    from scribe_mcp.tools import generate_doc_templates as gen_module
    monkeypatch.setattr(gen_module, "_PROJECT_REGISTRY", registry)

    # Generate templates with our test project
    # We need to point to the temp directory for file output
    base_dir = temp_project_root / "docs" / "dev_plans" / project_name

    result = await generate_doc_templates(
        project_name=project_name,
        base_dir=str(base_dir),
        force=True,  # Force creation even if files exist
    )

    # Verify templates were created
    assert result["ok"] is True
    assert len(result["files"]) > 0, "Should have created at least one template file"

    # Query the scribe_projects meta JSON to verify hashes were recorded
    conn = sqlite3.connect(temp_registry_db)
    try:
        cursor = conn.cursor()

        # Get the meta JSON blob from scribe_projects
        cursor.execute(
            "SELECT meta FROM scribe_projects WHERE name = ?",
            (project_name,)
        )
        row = cursor.fetchone()

        assert row is not None, "Project should exist in registry"
        assert row[0] is not None, "Project meta should not be None"

        # Parse the meta JSON
        import json
        meta = json.loads(row[0])

        # Verify docs metadata exists
        assert "docs" in meta, "Meta should contain 'docs' key"
        docs_meta = meta["docs"]

        # Verify baseline and current hashes exist
        assert "baseline_hashes" in docs_meta, "Should have baseline_hashes"
        assert "current_hashes" in docs_meta, "Should have current_hashes"

        baseline_hashes = docs_meta["baseline_hashes"]
        current_hashes = docs_meta["current_hashes"]

        # Verify we have hash entries for created templates
        assert len(baseline_hashes) > 0, "Should have recorded baseline hashes for templates"
        assert len(current_hashes) > 0, "Should have recorded current hashes for templates"

        # Verify expected document types were created
        expected_docs = {"architecture", "phase_plan", "checklist"}
        baseline_doc_types = set(baseline_hashes.keys())

        # At minimum, we should have these core documents
        assert expected_docs.issubset(baseline_doc_types), f"Missing expected docs. Got: {baseline_doc_types}"

        # Verify each entry has matching before/after hashes (pristine baseline)
        for doc in baseline_doc_types:
            baseline_hash = baseline_hashes.get(doc)
            current_hash = current_hashes.get(doc)

            assert baseline_hash is not None, f"baseline_hash should not be None for {doc}"
            assert current_hash is not None, f"current_hash should not be None for {doc}"
            assert baseline_hash == current_hash, f"Baseline/current hashes should match for pristine template {doc}"
            assert len(baseline_hash) == 64, f"Hash should be SHA256 (64 chars) for {doc}"

        # Verify flags were set correctly
        assert "flags" in docs_meta, "Should have flags"
        flags = docs_meta["flags"]

        # Check that pristine templates are marked as touched but not modified
        for doc in expected_docs:
            assert flags.get(f"{doc}_touched") is True, f"{doc} should be touched"
            assert flags.get(f"{doc}_modified") is False, f"{doc} should not be modified (pristine)"

    finally:
        conn.close()


@pytest.mark.asyncio
async def test_gen_001_hash_recording_best_effort(temp_project_root: Path, temp_registry_db: Path, monkeypatch):
    """
    SPEC-GEN-001: Verify that hash recording failures don't break template generation.

    This test ensures the best-effort pattern works correctly:
    1. If registry fails, templates are still created
    2. No exceptions are raised
    3. Template generation succeeds despite registry errors
    """
    project_name = "test_gen_001_best_effort"

    # Mock ProjectRegistry.record_doc_update to always raise an exception
    def mock_record_doc_update(*args, **kwargs):
        raise RuntimeError("Simulated registry failure")

    # Patch the module-level registry instance
    from scribe_mcp.tools import generate_doc_templates as gen_module
    original_method = gen_module._PROJECT_REGISTRY.record_doc_update
    monkeypatch.setattr(gen_module._PROJECT_REGISTRY, "record_doc_update", mock_record_doc_update)

    try:
        base_dir = temp_project_root / "docs" / "dev_plans" / project_name

        # This should NOT raise an exception despite registry failure
        result = await generate_doc_templates(
            project_name=project_name,
            base_dir=str(base_dir),
            force=True,
        )

        # Verify templates were still created successfully
        assert result["ok"] is True
        assert len(result["files"]) > 0, "Templates should be created despite registry failure"

        # Verify files actually exist on disk
        for file_path in result["files"]:
            assert Path(file_path).exists(), f"Template file should exist: {file_path}"

    finally:
        # Restore original method
        monkeypatch.setattr(gen_module._PROJECT_REGISTRY, "record_doc_update", original_method)


if __name__ == "__main__":
    # Allow running this test file directly
    pytest.main([__file__, "-v"])
