"""Tests for deterministic entry ID generation in append_entry."""

from scribe_mcp.tools.append_entry import (
    _generate_deterministic_entry_id,
    _get_repo_slug,
    _compose_line
)


class TestAppendEntryDeterministicEntryIDs:
    """Test deterministic entry ID generation functionality."""

    def test_get_repo_slug_basic(self):
        """Test basic repo slug generation."""
        # Test simple case
        result = _get_repo_slug("/home/user/my-project")
        assert result == "my-project"

    def test_get_repo_slug_with_special_chars(self):
        """Test repo slug generation with special characters."""
        result = _get_repo_slug("/home/user/My Project v2.0")
        assert result == "my-project-v2-0"

    def test_get_repo_slug_with_spaces(self):
        """Test repo slug generation with spaces."""
        result = _get_repo_slug("/home/user/scribe mcp")
        assert result == "scribe-mcp"

    def test_get_repo_slug_empty_fallback(self):
        """Test repo slug generation fallback for empty paths."""
        result = _get_repo_slug("")
        assert result == "unknown-repo"

    def test_deterministic_entry_id_basic(self):
        """Test basic deterministic entry ID generation."""
        entry_id = _generate_deterministic_entry_id(
            repo_slug="my-repo",
            project_slug="my-project",
            timestamp="2025-10-26 12:00:00 UTC",
            agent="TestAgent",
            message="Test message",
            meta={"phase": "test"}
        )

        # Should be exactly 32 characters
        assert len(entry_id) == 32
        # Should be hexadecimal
        assert all(c in "0123456789abcdef" for c in entry_id)

    def test_deterministic_entry_id_consistency(self):
        """Test that same input always produces same ID."""
        params = {
            "repo_slug": "my-repo",
            "project_slug": "my-project",
            "timestamp": "2025-10-26 12:00:00 UTC",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"phase": "test"}
        }

        entry_id1 = _generate_deterministic_entry_id(**params)
        entry_id2 = _generate_deterministic_entry_id(**params)

        assert entry_id1 == entry_id2

    def test_deterministic_entry_id_uniqueness(self):
        """Test that different inputs produce different IDs."""
        base_params = {
            "repo_slug": "my-repo",
            "project_slug": "my-project",
            "timestamp": "2025-10-26 12:00:00 UTC",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"phase": "test"}
        }

        # Test message changes
        params1 = {**base_params, "message": "Different message"}
        entry_id1 = _generate_deterministic_entry_id(**params1)
        entry_id2 = _generate_deterministic_entry_id(**base_params)
        assert entry_id1 != entry_id2

        # Test timestamp changes
        params2 = {**base_params, "timestamp": "2025-10-26 12:01:00 UTC"}
        entry_id3 = _generate_deterministic_entry_id(**params2)
        assert entry_id3 != entry_id2

        # Test meta changes
        params3 = {**base_params, "meta": {"phase": "different"}}
        entry_id4 = _generate_deterministic_entry_id(**params3)
        assert entry_id4 != entry_id2

    def test_deterministic_entry_id_meta_order_independence(self):
        """Test that metadata order doesn't affect the ID."""
        params = {
            "repo_slug": "my-repo",
            "project_slug": "my-project",
            "timestamp": "2025-10-26 12:00:00 UTC",
            "agent": "TestAgent",
            "message": "Test message",
            "meta": {"z": "last", "a": "first", "m": "middle"}
        }

        entry_id1 = _generate_deterministic_entry_id(**params)

        # Same metadata in different order
        params["meta"] = {"a": "first", "m": "middle", "z": "last"}
        entry_id2 = _generate_deterministic_entry_id(**params)

        assert entry_id1 == entry_id2

    def test_deterministic_entry_id_empty_meta(self):
        """Test entry ID generation with empty metadata."""
        entry_id = _generate_deterministic_entry_id(
            repo_slug="my-repo",
            project_slug="my-project",
            timestamp="2025-10-26 12:00:00 UTC",
            agent="TestAgent",
            message="Test message",
            meta={}
        )

        assert len(entry_id) == 32
        assert all(c in "0123456789abcdef" for c in entry_id)

    def test_compose_line_with_entry_id(self):
        """Test line composition includes entry ID."""
        line = _compose_line(
            emoji="✅",
            timestamp="2025-10-26 12:00:00 UTC",
            agent="TestAgent",
            project_name="Test Project",
            message="Test message",
            meta_pairs=(("phase", "test"),),
            entry_id="abcdef1234567890abcdef1234567890ab"
        )

        assert "[ID: abcdef1234567890abcdef1234567890ab]" in line
        assert "✅" in line
        assert "TestAgent" in line
        assert "Test Project" in line
        assert "Test message" in line
        assert "phase=test" in line

    def test_compose_line_without_entry_id(self):
        """Test line composition without entry ID (backward compatibility)."""
        line = _compose_line(
            emoji="✅",
            timestamp="2025-10-26 12:00:00 UTC",
            agent="TestAgent",
            project_name="Test Project",
            message="Test message",
            meta_pairs=(("phase", "test"),),
            entry_id=None
        )

        assert "[ID:" not in line
        assert "✅" in line
        assert "TestAgent" in line
        assert "Test Project" in line
        assert "Test message" in line
        assert "phase=test" in line

    def test_entry_id_reproducibility_across_calls(self):
        """Test that entry IDs are reproducible across multiple function calls."""
        # This is crucial for append-entry id stability across repeated writes
        test_cases = [
            {
                "repo_slug": "test-repo",
                "project_slug": "test-project",
                "timestamp": "2025-10-26 12:00:00 UTC",
                "agent": "TestAgent",
                "message": "Simple test message",
                "meta": {}
            },
            {
                "repo_slug": "complex-repo-name",
                "project_slug": "complex-project-name-v2",
                "timestamp": "2025-10-26 15:30:45 UTC",
                "agent": "ComplexAgent",
                "message": "Complex test with special chars: !@#$%^&*()",
                "meta": {"component": "test", "version": "1.0", "env": "dev"}
            }
        ]

        # Generate IDs multiple times for each test case
        for params in test_cases:
            ids = []
            for i in range(5):  # Generate 5 times
                entry_id = _generate_deterministic_entry_id(**params)
                ids.append(entry_id)

            # All should be identical
            assert all(entry_id == ids[0] for entry_id in ids[1:]), \
                f"Entry IDs should be reproducible for params: {params}"
