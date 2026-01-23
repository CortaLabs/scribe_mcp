"""Unit tests for Scribe MCP tools."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
import sys

# Add the MCP_SPINE directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scribe_mcp import server
from scribe_mcp.config.settings import settings
from scribe_mcp.state.manager import StateManager
from scribe_mcp.storage.sqlite import SQLiteStorage
from scribe_mcp.tools import (
    append_entry,
    generate_doc_templates,
    get_project,
    list_projects,
    read_recent,
    rotate_log,
    set_project,
)
from scribe_mcp.tools.project_utils import slugify_project_name


def run(coro):
    """Execute an async coroutine from a synchronous test."""

    return asyncio.run(coro)


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Provide an isolated StateManager and assign it to the server module."""

    manager = StateManager(path=tmp_path / "state.json")
    monkeypatch.setattr(server, "state_manager", manager, raising=False)
    if getattr(server, "storage_backend", None):
        run(server.storage_backend.close())
    storage = SQLiteStorage(tmp_path / "scribe.db")
    run(storage.setup())
    monkeypatch.setattr(server, "storage_backend", storage, raising=False)
    append_entry._RATE_TRACKER.clear()
    append_entry._RATE_LOCKS.clear()

    # Clean up audit trail files for test isolation
    import shutil
    audit_dir = Path(__file__).parent.parent / "scribe_mcp" / "state"
    if audit_dir.exists():
        for audit_file in audit_dir.glob("rotation_audit_*.json"):
            # Only remove test-related audit files (those with test patterns)
            if any(pattern in audit_file.name for pattern in [
                "test-", "test_", "-test", "_test", "performance", "metadata",
                "integrity", "hash-chain", "history", "invalid-metadata", "enhanced-rotation"
            ]):
                try:
                    audit_file.unlink()
                except Exception:
                    pass  # Ignore cleanup errors

    return manager


@pytest.fixture
def project_root(tmp_path):
    root = settings.project_root / "tmp_tests" / str(uuid.uuid4())
    root.mkdir(parents=True, exist_ok=True)
    yield root
    if root.exists():
        shutil.rmtree(root)


def test_set_and_get_project_roundtrip(isolated_state, project_root):
    root = project_root
    result = run(
        set_project.set_project(
            agent="test_agent",
            name="test-project",
            root=str(root),
            defaults={"emoji": "✅", "agent": "Tester"},
        format="structured",
        )
    )

    assert result["ok"]
    assert len(result["generated"]) >= 1
    active = run(get_project.get_project(agent="test_agent", format="structured"))
    assert active["ok"]
    project = active["project"]
    assert project["name"] == "test-project"
    docs_dir = root / settings.dev_plans_base / slugify_project_name("test-project")
    assert project["progress_log"] == str((docs_dir / "PROGRESS_LOG.md").resolve())
    assert project["docs"]["architecture"].endswith("ARCHITECTURE_GUIDE.md")
    assert active["recent_projects"][0] == "test-project"


def test_append_and_read_recent(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="log-test", root=str(root), format="structured"))

    append_result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="Recorded unit test entry",
            status="info",
            meta={"scope": "unit-test"},

            format="structured",
        )
    )

    assert append_result["ok"]
    written_line = append_result["written_line"]
    lines = [line for line in Path(append_result["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[-1] == written_line

    recent = run(read_recent.read_recent(agent="test_agent", n=5, format="structured"))
    assert recent["ok"]
    # Check if any entry contains "unit-test" in the message or meta field
    found_unit_test = False
    for entry in recent["entries"]:
        # Handle both dict entries (from DB) and string entries (from file)
        if isinstance(entry, dict):
            if "unit-test" in str(entry.get("message", "")) or "unit-test" in str(entry.get("meta", "")):
                found_unit_test = True
                break
        else:
            # String entry from file
            if "unit-test" in str(entry):
                found_unit_test = True
                break
    assert found_unit_test, f"No entry containing 'unit-test' found in entries: {recent['entries']}"

    projects = run(list_projects.list_projects(agent="test_agent", format="structured"))
    assert "projects" in projects
    # Session isolation: list_projects by default only shows projects for current repo
    # The test creates projects in tmp dirs, so they may not show up
    # Just verify we got a valid response
    assert isinstance(projects["projects"], list)


def test_append_entry_uses_slugified_log_path(isolated_state, project_root):
    root = project_root
    project_name = "IMPLEMENTATION TESTING"
    slug = slugify_project_name(project_name)
    run(set_project.set_project(agent="test_agent", name=project_name, root=str(root), format="structured"))

    canonical_dir = (root / settings.dev_plans_base / slug).resolve()
    log_path = (canonical_dir / "PROGRESS_LOG.md").resolve()
    assert log_path.exists()

    append_result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="Verifying slugified path usage",
            status="success",

            format="structured",
        )
    )
    assert append_result["ok"]
    assert Path(append_result["path"]).resolve() == log_path


def test_append_entry_accepts_json_string_meta(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="meta-json-test", root=str(root), format="structured"))

    meta_payload = '{"task":"meta_json","component":"append_entry","flag":true}'
    result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="Metadata JSON string payload",
            status="info",
            meta=meta_payload,

            format="structured",
        )
    )

    assert result["ok"]
    assert result["meta"]["component"] == "append_entry"
    assert result["meta"]["flag"] == "True"  # Values are stringified downstream


def test_append_entry_accepts_sequence_metadata(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="meta-sequence-test", root=str(root), format="structured"))

    sequence_meta = [("task", "sequence_meta"), ("index", 1)]
    result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="Metadata sequence payload",
            status="info",
            meta=sequence_meta,

            format="structured",
        )
    )

    assert result["ok"]
    assert result["meta"]["task"] == "sequence_meta"
    assert result["meta"]["index"] == "1"

    log_path = Path(result["path"])
    log_content = log_path.read_text(encoding="utf-8")
    assert "sequence_meta" in log_content


def test_append_entry_items_list_string_meta(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="meta-items-list", root=str(root), format="structured"))

    items_list = [{"message": "Child entry", "meta": "scope=child"}]
    result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="",
            status="info",
            meta={"parent": "value"},
            items_list=items_list,
            format="structured",
        )
    )

    assert result["ok"]
    assert result["failed_count"] == 0
    written_line = result["written_lines"][0]
    assert "scope=child" in written_line
    assert "parent=value" in written_line


def test_rotate_log_creates_archive(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="rotate-test", root=str(root), format="structured"))
    run(append_entry.append_entry(
            agent="test_agent",
            message="Before rotation"))

    result = run(rotate_log.rotate_log(agent="test_agent", suffix="test", confirm=True, format="structured"))
    assert result["ok"]
    archive_path = Path(result["archived_to"])
    assert archive_path.exists()
    assert archive_path.read_text(encoding="utf-8")
    assert "estimated_entry_count" in result
    assert "entry_count_method" in result


def test_generate_doc_templates_renders_files(tmp_path, isolated_state):
    project_name = "UnitTestDocs"
    target_dir = tmp_path / "docs" / "dev_plans" / slugify_project_name(project_name)
    if target_dir.exists():
        shutil.rmtree(target_dir)

    try:
        result = run(
            generate_doc_templates.generate_doc_templates(
                agent="test_agent",
                project_name=project_name,
                author="QA",
                base_dir=str(tmp_path),
            )
        )
        assert result["ok"]
        for filename in (
            "ARCHITECTURE_GUIDE.md",
            "PHASE_PLAN.md",
            "CHECKLIST.md",
            "PROGRESS_LOG.md",
        ):
            path = target_dir / filename
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "{{" not in content
    finally:
        if target_dir.exists():
            shutil.rmtree(target_dir)


def test_log_rotation_triggers_when_max_bytes_reached(monkeypatch, isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="rotation-limit", root=str(root), format="structured"))

    # First, create a large log file that exceeds the threshold
    result = run(append_entry.append_entry(
        agent="test_agent",
        message="Initial large entry that exceeds max bytes threshold when combined with metadata" * 10,
        status="info",
        meta={"test": "large" * 20},
        format="structured",
    ))
    assert result["ok"]
    log_path = Path(result["path"])

    # Manually patch the log to be larger than threshold
    initial_content = log_path.read_text(encoding="utf-8")
    large_content = initial_content + "\n" + "Large content to exceed max bytes" * 100
    log_path.write_text(large_content, encoding="utf-8")

    # Now set a very low threshold and patch settings
    patched_settings = replace(
        settings,
        log_max_bytes=100,  # Set higher than 10 to avoid edge cases but still low
    )
    monkeypatch.setattr(append_entry, "settings", patched_settings, raising=False)
    append_entry._RATE_TRACKER.clear()
    append_entry._RATE_LOCKS.clear()

    # Add another entry - this should trigger rotation
    result = run(
        append_entry.append_entry(
            agent="test_agent",
            message="Entry that should trigger rotation",
            status="info",

            format="structured",
        )
    )
    assert result["ok"]

    # Check for archive files
    archives = list(log_path.parent.glob(f"{log_path.name}.*.md"))
    assert archives, "Expected rotated archive file to be created"


class TestEnhancedRotationEngine:
    """Integration tests for enhanced rotation engine with Phase 0 utilities."""

    def test_enhanced_rotation_with_integrity(isolated_state, project_root):
        """Test enhanced rotation with SHA-256 integrity verification."""
        # Set up project
        root = project_root
        result = run(
            set_project.set_project(
            agent="test_agent",
            name="enhanced-rotation-test",
                root=str(root),
                defaults={"emoji": "🧪", "agent": "TestAgent"},
            format="structured",
            )
        )
        assert result["ok"]

        # Add test entries
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Test entry 1 before rotation",
                status="info",
                meta={"phase": "1", "test": "true"}
            )
        )
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Test entry 2 before rotation",
                status="success",
                meta={"phase": "1", "test": "true"}
            )
        )

        # Test dry run rotation
        dry_run_result = run(
            rotate_log.rotate_log(agent="test_agent", dry_run=True, format="structured")
        )
        assert dry_run_result["ok"]
        assert dry_run_result["dry_run"] is True
        assert "rotation_id" in dry_run_result
        assert "file_hash" in dry_run_result
        assert "entry_count" in dry_run_result
        assert "sequence_number" in dry_run_result

        # Test actual enhanced rotation
        rotation_result = run(
            rotate_log.rotate_log(agent="test_agent", suffix="test-enhanced", confirm=True, format="structured")
        )
        if not rotation_result["ok"]:
            print(f"Rotation failed with error: {rotation_result.get('error', 'Unknown error')}")
            print(f"Full rotation result: {rotation_result}")
        assert rotation_result["ok"]

        print(f"✅ Rotation successful!")
        print(f"   Archive path: {rotation_result.get('archive_path', 'N/A')}")
        print(f"   Archive hash: {rotation_result.get('archive_hash', 'N/A')}")
        print(f"   Entry count: {rotation_result.get('entry_count', 'N/A')}")
        assert rotation_result["rotation_completed"] is True
        assert "rotation_id" in rotation_result
        assert "archive_path" in rotation_result
        assert "archive_hash" in rotation_result
        assert "entry_count" in rotation_result
        assert "rotation_duration_seconds" in rotation_result
        assert rotation_result["integrity_verified"] is True
        assert rotation_result["audit_trail_stored"] is True
        assert rotation_result["state_updated"] is True

        # Verify archive file exists
        archive_path = Path(rotation_result["archive_path"])
        assert archive_path.exists()

        # Verify new progress log was created
        active = run(get_project.get_project(agent="test_agent", format="structured"))
        assert active["ok"]
        new_log_path = Path(active["project"]["progress_log"])
        assert new_log_path.exists()
        assert new_log_path != archive_path


def test_rotate_log_dry_run_precision_controls(isolated_state, project_root):
    root = project_root
    run(set_project.set_project(agent="test_agent", name="rotate-precision-test", root=str(root), format="structured"))
    run(append_entry.append_entry(
            agent="test_agent",
            message="Precision dry-run entry"))

    estimate_result = run(rotate_log.rotate_log(agent="test_agent", dry_run=True, format="structured"))
    assert estimate_result["ok"]
    assert estimate_result["dry_run"] is True
    assert estimate_result["entry_count"] >= 1
    assert "entry_count_method" in estimate_result
    assert "entry_count_approximate" in estimate_result

    precise_result = run(rotate_log.rotate_log(agent="test_agent", dry_run=True, dry_run_mode="precise", format="structured"))
    assert precise_result["ok"]
    assert precise_result["dry_run"] is True
    assert precise_result["entry_count_approximate"] is False
    assert precise_result["entry_count_method"] == "full_count"
    assert precise_result["entry_count"] >= 1

    def test_rotation_with_custom_metadata(isolated_state, project_root):
        """Test rotation with custom metadata."""
        # Set up project
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="metadata-test",
                root=str(root),
            )
        )

        # Add test entry
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Test entry for metadata rotation",
                status="info"
            )
        )

        # Test rotation with custom metadata
        custom_metadata = {"environment": "test", "version": "1.0", "test_run": True}
        rotation_result = run(
            rotate_log.rotate_log(
                suffix="metadata-test",
                custom_metadata=json.dumps(custom_metadata),
                confirm=True
            )
        )
        assert rotation_result["ok"]
        assert rotation_result["rotation_completed"] is True

    def test_rotation_with_invalid_metadata(isolated_state, project_root):
        """Test rotation with invalid JSON metadata."""
        # Set up project
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="invalid-metadata-test",
                root=str(root),
            )
        )

        # Test rotation with invalid JSON
        rotation_result = run(
            rotate_log.rotate_log(
                custom_metadata="{'invalid': json structure"
            )
        )
        assert rotation_result["ok"] is False
        assert "Invalid JSON" in rotation_result["error"]

    def test_rotation_hash_chain_tracking(isolated_state, project_root):
        """Test hash chain tracking across multiple rotations."""
        # Set up project
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="hash-chain-test",
                root=str(root),
            )
        )

        # First rotation
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Entry before first rotation",
                status="info"
            )
        )
        rotation_1 = run(rotate_log.rotate_log(agent="test_agent", suffix="rotation-1", confirm=True, format="structured"))
        assert rotation_1["ok"]
        hash_1 = rotation_1["archive_hash"]
        sequence_1 = rotation_1["sequence_number"]

        # Add entries and second rotation
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Entry between rotations",
                status="info"
            )
        )
        rotation_2 = run(rotate_log.rotate_log(agent="test_agent", suffix="rotation-2", confirm=True, format="structured"))
        assert rotation_2["ok"]
        hash_2 = rotation_2["archive_hash"]
        sequence_2 = rotation_2["sequence_number"]

        # Verify hash chain
        assert sequence_2 == sequence_1 + 1
        assert hash_2 != hash_1

    def test_rotation_integrity_verification(isolated_state, project_root):
        """Test rotation integrity verification."""
        # Set up project
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="integrity-test",
                root=str(root),
            )
        )

        # Add test entry and rotate
        run(
            append_entry.append_entry(
            agent="test_agent",
            message="Test entry for integrity verification",
                status="info"
            )
        )
        rotation_result = run(rotate_log.rotate_log(agent="test_agent", confirm=True, format="structured"))
        assert rotation_result["ok"]

        # Test integrity verification
        verification_result = run(
            rotate_log.verify_rotation_integrity(rotation_result["rotation_id"])
        )
        if not verification_result["ok"]:
            print(f"❌ Integrity verification failed: {verification_result.get('error', 'Unknown error')}")
            print(f"   Rotation ID: {rotation_result['rotation_id']}")
        assert verification_result["ok"]
        assert verification_result["integrity_valid"] is True
        assert verification_result["project"] == "integrity-test"

    def test_rotation_history_tracking(isolated_state, project_root):
        """Test rotation history tracking."""
        # Set up project with unique name to avoid audit file conflicts
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        project_name = f"history-test-{unique_id}"

        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name=project_name,
                root=str(root),
            )
        )

        # Perform multiple rotations
        for i in range(3):
            run(
                append_entry.append_entry(
            agent="test_agent",
            message=f"Entry before rotation {i+1}",
                    status="info"
                )
            )
            rotation_result = run(rotate_log.rotate_log(suffix=f"rotation-{i+1}", confirm=True))
            assert rotation_result["ok"]

        # Test rotation history
        history_result = run(rotate_log.get_rotation_history(agent="test_agent", limit=5))
        if not history_result["ok"]:
            print(f"❌ History tracking failed: {history_result.get('error', 'Unknown error')}")
        assert history_result["ok"]
        assert history_result["project"] == project_name
        assert history_result["rotation_count"] == 3
        assert len(history_result["rotations"]) == 3

    def test_rotation_error_handling(isolated_state, project_root, monkeypatch):
        """Test rotation error handling."""
        # Test with no project configured - mock all project discovery methods
        from scribe_mcp.state.manager import StateManager
        from scribe_mcp import server as server_module
        from scribe_mcp.tools import project_utils

        # Mock environment variable to prevent fallback project discovery
        monkeypatch.delenv("SCRIBE_DEFAULT_PROJECT", raising=False)

        # Mock load_project_config to return None (no project configuration found)
        def mock_load_project_config(project_name=None):
            return None

        monkeypatch.setattr(project_utils, "load_project_config", mock_load_project_config)

        # Create a completely fresh state manager with no project data
        fresh_state_path = project_root / "fresh_state.json"
        fresh_state_manager = StateManager(path=fresh_state_path)

        # Temporarily replace the server's state manager
        original_state_manager = server_module.state_manager
        server_module.state_manager = fresh_state_manager

        try:
            error_result = run(rotate_log.rotate_log(agent="test_agent", format="structured"))
            assert error_result["ok"] is False
            assert "No project configured" in error_result["error"]
        finally:
            # Restore original state manager
            server_module.state_manager = original_state_manager

        # Set up project but don't create log file
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="error-test",
                root=str(root),
            )
        )

        # Manually delete progress log to test error handling
        active = run(get_project.get_project(agent="test_agent", format="structured"))
        log_path = Path(active["project"]["progress_log"])
        if log_path.exists():
            log_path.unlink()

        error_result = run(rotate_log.rotate_log(agent="test_agent", format="structured"))
        assert error_result["ok"] is False
        assert "not found" in error_result["error"]

    def test_rotation_performance_monitoring(isolated_state, project_root):
        """Test rotation performance monitoring."""
        # Set up project
        root = project_root
        run(
            set_project.set_project(
            agent="test_agent",
            name="performance-test",
                root=str(root),
            )
        )

        # Add some test entries
        for i in range(5):
            run(
                append_entry.append_entry(
            agent="test_agent",
            message=f"Performance test entry {i+1}",
                    status="info"
                )
            )

        # Test rotation with performance monitoring
        rotation_result = run(rotate_log.rotate_log(agent="test_agent", confirm=True, format="structured"))
        assert rotation_result["ok"]
        assert "rotation_duration_seconds" in rotation_result
        assert rotation_result["rotation_duration_seconds"] >= 0
        assert rotation_result["integrity_verified"] is True
