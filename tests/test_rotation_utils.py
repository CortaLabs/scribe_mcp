"""
Comprehensive unit tests for rotation utility modules.

Tests the integrity, audit, and rotation state utilities that form
the foundation of the enhanced log rotation system.
"""

import pytest
import tempfile
import json
import uuid
from pathlib import Path
from datetime import datetime
import time

from scribe_mcp.utils.integrity import (
    compute_file_hash,
    verify_file_integrity,
    create_file_metadata,
    hash_file_string,
    count_file_lines,
    create_rotation_metadata,
    benchmark_hash_performance
)

from scribe_mcp.utils.audit import (
    AuditTrailManager,
    get_audit_manager,
    store_rotation_metadata,
    get_rotation_history,
    verify_rotation_integrity,
    get_audit_summary
)

from scribe_mcp.utils.rotation_state import (
    RotationStateManager,
    get_state_manager,
    get_project_state,
    update_project_state,
    get_next_sequence_number,
    generate_rotation_id
)


class TestIntegrityUtils:
    """Test file integrity utility functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_file = self.temp_dir / "test_log.txt"
        self.test_content = """# Test Log Entry 1
[2025-10-24 11:00:00 UTC] [Agent: Test] [Project: Test] First entry | phase=1
[2025-10-24 11:01:00 UTC] [Agent: Test] [Project: Test] Second entry | phase=1
[2025-10-24 11:02:00 UTC] [Agent: Test] [Project: Test] Third entry | phase=2
"""
        self.test_file.write_text(self.test_content)

    def test_compute_file_hash(self):
        """Test SHA-256 hash computation."""
        file_hash, file_size = compute_file_hash(str(self.test_file))

        assert isinstance(file_hash, str)
        assert len(file_hash) == 64  # SHA-256 hex digest length
        assert isinstance(file_size, int)
        assert file_size == len(self.test_content.encode('utf-8'))

    def test_compute_file_hash_nonexistent(self):
        """Test hash computation with non-existent file."""
        with pytest.raises(FileNotFoundError):
            compute_file_hash("/nonexistent/file.txt")

    def test_verify_file_integrity(self):
        """Test file integrity verification."""
        # Get correct hash
        correct_hash, _ = compute_file_hash(str(self.test_file))

        # Test with correct hash
        is_valid, actual_hash = verify_file_integrity(str(self.test_file), correct_hash)
        assert is_valid is True
        assert actual_hash == correct_hash

        # Test with incorrect hash
        is_valid, actual_hash = verify_file_integrity(str(self.test_file), "wrong_hash")
        assert is_valid is False
        assert actual_hash != "wrong_hash"

    def test_create_file_metadata(self):
        """Test file metadata creation."""
        metadata = create_file_metadata(str(self.test_file))

        assert metadata["file_name"] == "test_log.txt"
        assert metadata["file_size"] > 0
        assert isinstance(metadata["sha256_hash"], str)
        assert len(metadata["sha256_hash"]) == 64  # SHA-256 hex digest length
        assert "created_timestamp" in metadata
        assert "modified_timestamp" in metadata
        assert metadata["is_readable"] is True

    def test_hash_file_string(self):
        """Test hash string formatting."""
        hash_string = hash_file_string(str(self.test_file))
        assert hash_string.startswith("sha256:")
        assert len(hash_string) == 71  # "sha256:" + 64 char hash

    def test_count_file_lines(self):
        """Test line counting."""
        line_count = count_file_lines(str(self.test_file))
        assert line_count == 4  # 4 lines in test content (including header)

    def test_create_rotation_metadata(self):
        """Test rotation metadata creation."""
        rotation_uuid = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + " UTC"

        metadata = create_rotation_metadata(
            archived_file_path=str(self.test_file),
            rotation_uuid=rotation_uuid,
            rotation_timestamp=timestamp,
            sequence_number=1,
            previous_hash="sha256:previous_hash"
        )

        assert metadata["rotation_uuid"] == rotation_uuid
        assert metadata["rotation_timestamp_utc"] == timestamp
        assert metadata["sequence_number"] == 1
        assert metadata["entry_count"] == 4  # 4 lines in test content
        assert metadata["hash_chain_previous"] == "sha256:previous_hash"
        assert isinstance(metadata["file_hash"], str)
        assert len(metadata["file_hash"]) == 64  # SHA-256 hex digest length

    def test_benchmark_hash_performance(self):
        """Test hash performance benchmarking."""
        # Create a larger test file for meaningful benchmarking
        large_file = self.temp_dir / "large_test.txt"
        large_content = self.test_content * 100  # Repeat content
        large_file.write_text(large_content)

        benchmark = benchmark_hash_performance(str(large_file))

        assert "file_size_mb" in benchmark
        assert "hash_time_seconds" in benchmark
        assert "throughput_mbps" in benchmark
        assert benchmark["file_size_mb"] > 0
        assert benchmark["hash_time_seconds"] >= 0


class TestAuditTrailManager:
    """Test audit trail management functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.audit_manager = AuditTrailManager(str(self.temp_dir))
        self.project_name = "Test Project"
        self.test_metadata = {
            "rotation_uuid": str(uuid.uuid4()),
            "rotation_timestamp_utc": datetime.utcnow().isoformat() + " UTC",
            "sequence_number": 1,
            "archived_file_path": "/test/path.md",
            "entry_count": 10,
            "file_hash": "sha256:test_hash"
        }

    def test_store_rotation_metadata(self):
        """Test storing rotation metadata."""
        success = self.audit_manager.store_rotation_metadata(self.project_name, self.test_metadata)
        assert success is True

    def test_get_rotation_history(self):
        """Test retrieving rotation history."""
        # Store multiple rotations
        for i in range(3):
            metadata = self.test_metadata.copy()
            metadata["rotation_uuid"] = str(uuid.uuid4())
            metadata["sequence_number"] = i + 1
            self.audit_manager.store_rotation_metadata(self.project_name, metadata)

        history = self.audit_manager.get_rotation_history(self.project_name)
        assert len(history) == 3

        # Test limit
        limited_history = self.audit_manager.get_rotation_history(self.project_name, limit=2)
        assert len(limited_history) == 2

    def test_get_rotation_by_uuid(self):
        """Test retrieving specific rotation by UUID."""
        # Store rotation
        self.audit_manager.store_rotation_metadata(self.project_name, self.test_metadata)

        # Retrieve by UUID
        found_rotation = self.audit_manager.get_rotation_by_uuid(
            self.project_name, self.test_metadata["rotation_uuid"]
        )
        assert found_rotation is not None
        assert found_rotation["rotation_uuid"] == self.test_metadata["rotation_uuid"]

        # Test non-existent UUID
        not_found = self.audit_manager.get_rotation_by_uuid(
            self.project_name, "non-existent-uuid"
        )
        assert not_found is None

    def test_get_audit_summary(self):
        """Test audit summary generation."""
        # Store rotation
        self.audit_manager.store_rotation_metadata(self.project_name, self.test_metadata)

        summary = self.audit_manager.get_audit_summary(self.project_name)

        assert summary["project_name"] == self.project_name
        assert summary["total_rotations"] == 1
        assert summary["total_entries_archived"] == 10
        assert summary["audit_file_path"].endswith("rotation_audit_Test_Project.json")

    def test_cleanup_old_rotations(self):
        """Test cleanup of old rotation records."""
        # Store many rotations
        for i in range(10):
            metadata = self.test_metadata.copy()
            metadata["rotation_uuid"] = str(uuid.uuid4())
            metadata["sequence_number"] = i + 1
            self.audit_manager.store_rotation_metadata(self.project_name, metadata)

        # Cleanup keeping only 5
        removed_count, success = self.audit_manager.cleanup_old_rotations(self.project_name, keep_count=5)
        assert success is True
        assert removed_count == 5

        # Verify only 5 remain
        history = self.audit_manager.get_rotation_history(self.project_name)
        assert len(history) == 5

    def test_list_audited_projects(self):
        """Test listing audited projects."""
        # Store rotations for multiple projects
        for project in ["Project A", "Project B", "Project C"]:
            metadata = self.test_metadata.copy()
            metadata["rotation_uuid"] = str(uuid.uuid4())
            self.audit_manager.store_rotation_metadata(project, metadata)

        projects = self.audit_manager.list_audited_projects()
        assert len(projects) >= 3
        assert "Project A" in projects
        assert "Project B" in projects
        assert "Project C" in projects


class TestRotationStateManager:
    """Test rotation state management functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.state_manager = RotationStateManager(str(self.temp_dir))
        self.project_name = "Test Project"
        self.test_rotation_metadata = {
            "rotation_uuid": str(uuid.uuid4()),
            "rotation_timestamp_utc": datetime.utcnow().isoformat() + " UTC",
            "sequence_number": 1,
            "archived_file_path": "/test/path.md",
            "file_hash": "sha256:test_hash_1234567890abcdef",
            "entry_count": 15
        }

    def test_get_project_state_initial(self):
        """Test initial project state creation."""
        state = self.state_manager.get_project_state(self.project_name)

        assert state["current_sequence"] == 0
        assert state["total_rotations"] == 0
        assert state["rotation_ids"] == []
        assert state["hash_chain"]["root_hash"] is None
        assert state["hash_chain"]["current_sequence"] == 0

    def test_generate_rotation_id(self):
        """Test rotation ID generation."""
        rotation_id = self.state_manager.generate_rotation_id(self.project_name)

        assert isinstance(rotation_id, str)
        # Should be a valid UUID
        uuid.UUID(rotation_id)  # Will raise if invalid

    def test_get_next_sequence_number(self):
        """Test sequence number incrementing."""
        # Initial sequence should be 1
        sequence = self.state_manager.get_next_sequence_number(self.project_name)
        assert sequence == 1

        # Update project state to sequence 1
        self.test_rotation_metadata["sequence_number"] = 1
        self.state_manager.update_project_state(self.project_name, self.test_rotation_metadata)

        # Next sequence should be 2
        sequence = self.state_manager.get_next_sequence_number(self.project_name)
        assert sequence == 2

    def test_update_project_state(self):
        """Test project state updates."""
        success = self.state_manager.update_project_state(
            self.project_name, self.test_rotation_metadata
        )
        assert success is True

        state = self.state_manager.get_project_state(self.project_name)
        assert state["current_sequence"] == 1
        assert state["total_rotations"] == 1
        assert state["last_rotation_timestamp"] == self.test_rotation_metadata["rotation_timestamp_utc"]
        assert self.test_rotation_metadata["rotation_uuid"] in state["rotation_ids"]

    def test_hash_chain_tracking(self):
        """Test hash chain functionality."""
        # First rotation - should establish root hash
        success = self.state_manager.update_project_state(
            self.project_name, self.test_rotation_metadata
        )
        assert success is True

        state = self.state_manager.get_project_state(self.project_name)
        assert state["hash_chain"]["root_hash"] == self.test_rotation_metadata["file_hash"]
        assert state["hash_chain"]["last_hash"] == self.test_rotation_metadata["file_hash"]

        # Second rotation - should update last hash
        second_metadata = self.test_rotation_metadata.copy()
        second_metadata["rotation_uuid"] = str(uuid.uuid4())
        second_metadata["sequence_number"] = 2
        second_metadata["file_hash"] = "sha256:test_hash_abcdef1234567890"

        success = self.state_manager.update_project_state(
            self.project_name, second_metadata
        )
        assert success is True

        state = self.state_manager.get_project_state(self.project_name)
        assert state["hash_chain"]["root_hash"] == self.test_rotation_metadata["file_hash"]  # Unchanged
        assert state["hash_chain"]["last_hash"] == second_metadata["file_hash"]  # Updated
        assert state["hash_chain"]["current_sequence"] == 2

    def test_get_project_statistics(self):
        """Test project statistics generation."""
        # Add some rotation data
        self.state_manager.update_project_state(self.project_name, self.test_rotation_metadata)

        stats = self.state_manager.get_project_statistics(self.project_name)

        assert stats["project_name"] == self.project_name
        assert stats["current_sequence"] == 1
        assert stats["total_rotations"] == 1
        assert stats["hash_chain_root"] == self.test_rotation_metadata["file_hash"]
        assert stats["rotation_ids_count"] == 1

    def test_cleanup_project_state(self):
        """Test project state cleanup."""
        # Add many rotation IDs
        for i in range(10):
            metadata = self.test_rotation_metadata.copy()
            metadata["rotation_uuid"] = str(uuid.uuid4())
            metadata["sequence_number"] = i + 1
            self.state_manager.update_project_state(self.project_name, metadata)

        # Cleanup keeping only 5
        removed_count, success = self.state_manager.cleanup_project_state(
            self.project_name, keep_count=5
        )
        assert success is True
        assert removed_count == 5

        # Verify project state
        state = self.state_manager.get_project_state(self.project_name)
        assert len(state["rotation_ids"]) == 5

    def test_list_tracked_projects(self):
        """Test listing tracked projects."""
        # Add state for multiple projects
        for project in ["Project A", "Project B", "Project C"]:
            self.state_manager.get_project_state(project)  # Creates state entry

        projects = self.state_manager.list_tracked_projects()
        assert len(projects) >= 3
        assert "Project A" in projects
        assert "Project B" in projects
        assert "Project C" in projects

    def test_reset_project_state(self):
        """Test project state reset."""
        # Add some state
        self.state_manager.update_project_state(self.project_name, self.test_rotation_metadata)

        # Reset state
        success = self.state_manager.reset_project_state(self.project_name)
        assert success is True

        # Verify state is reset
        projects = self.state_manager.list_tracked_projects()
        assert self.project_name not in projects

    def test_global_settings(self):
        """Test global settings management."""
        # Update settings
        new_settings = {
            "max_rotations_per_project": 200,
            "hash_chaining_enabled": False
        }
        success = self.state_manager.update_global_settings(new_settings)
        assert success is True

        # Verify settings
        settings = self.state_manager.get_global_settings()
        assert settings["max_rotations_per_project"] == 200
        assert settings["hash_chaining_enabled"] is False
        # Unchanged setting should remain
        assert settings["integrity_verification_enabled"] is True


class TestConvenienceFunctions:
    """Test global convenience functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def test_audit_manager_convenience_functions(self):
        """Test audit manager convenience functions."""
        # Use global functions with custom state directory
        from scribe_mcp.utils.audit import get_audit_manager

        manager = get_audit_manager(str(self.temp_dir))
        assert isinstance(manager, AuditTrailManager)

    def test_state_manager_convenience_functions(self):
        """Test state manager convenience functions."""
        # Use global functions with custom state directory
        from scribe_mcp.utils.rotation_state import get_state_manager

        manager = get_state_manager(str(self.temp_dir))
        assert isinstance(manager, RotationStateManager)


def test_entry_count_estimation_cache_invalidation():
    """Ensure cached snapshot mismatches fall back to EMA estimation."""
    from tools.rotate_log import _estimate_entry_count

    snapshot = {"size_bytes": 1024, "mtime_ns": 1000, "inode": 42}
    cached = {
        "size_bytes": 1024,
        "mtime_ns": 1000,
        "line_count": 20,
        "ema_bytes_per_line": 64.0,
        "initialized": True,
    }

    precise = _estimate_entry_count(snapshot, cached)
    assert precise.approximate is False
    assert precise.method == "cache"

    mutated_snapshot = {"size_bytes": 2048, "mtime_ns": 2000, "inode": 42}
    fallback = _estimate_entry_count(mutated_snapshot, cached)
    assert fallback.approximate is True
    assert fallback.method == "ema"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
