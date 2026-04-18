#!/usr/bin/env python3
"""
Unit tests for SPEC-SET-001: Fix BUG-001 Empty Log Detection

Tests verify that empty progress logs (after rotation or manual clearing) are
correctly identified as EXISTING projects, not NEW projects.
"""

import asyncio
import tempfile
from pathlib import Path
import pytest
import shutil
from types import SimpleNamespace
import uuid

from scribe_mcp.tools import set_project as set_project_module
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.tools import rotate_log as rotate_log_module

# Get actual functions (unwrapped from MCP decorator)
set_project = set_project_module.set_project
append_entry = append_entry_module.append_entry
rotate_log = rotate_log_module.rotate_log


def extract_result(result):
    """
    Extract data from tool result.

    For readable format: Returns dict by parsing CallToolResult
    For structured/compact: Returns dict directly
    """
    # Check if it's a CallToolResult (MCP framework object)
    if hasattr(result, 'content'):
        # Extract the text content (readable output)
        text_content = None
        for content_item in result.content:
            if hasattr(content_item, 'text'):
                text_content = content_item.text
                break

        # Parse dict from result if available (hidden in structured data)
        # For now, just return the text content
        return {"readable_content": text_content, "format": "readable", "ok": True}
    else:
        # It's already a dict (structured/compact format)
        return result


class TestBug001EmptyLogDetection:
    """Test suite for BUG-001: Empty log detection fix (SPEC-SET-001)."""

    @pytest.mark.asyncio
    async def test_bug_001_empty_log_shows_existing_sitrep(self):
        """
        Verify rotated/empty logs show existing SITREP, not new SITREP.

        This test reproduces the original bug:
        1. Create a project
        2. Add an entry
        3. Rotate the log (creating empty file)
        4. Call set_project again
        5. Verify it shows EXISTING, not NEW
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            unique_id = str(uuid.uuid4())[:8]
            project_name = f"test_bug_001_rotation_{unique_id}"
            agent_name = f"TestAgent-Bug001-{unique_id}"
            project_root = Path(tmpdir)

            # Step 1: Create initial project (use readable format to get is_new flag)
            raw_result1 = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result1 = extract_result(raw_result1)
            assert result1["ok"], "Initial project creation failed"

            # Check for NEW PROJECT message in readable content
            readable1 = result1.get("readable_content", "")
            assert "NEW PROJECT" in readable1.upper(), \
                f"Should show NEW PROJECT message initially. Got: {readable1[:200]}"

            # Step 2: Add an entry to make it non-empty
            await append_entry(
                message="Test entry before rotation",
                status="info",
                agent=agent_name
            )

            # Step 3: Rotate the log (creates empty file)
            raw_rotate = await rotate_log(agent=agent_name, confirm=True)
            rotate_result = extract_result(raw_rotate)
            assert rotate_result["ok"], "Log rotation failed"

            # Step 4: Call set_project again after rotation
            raw_result2 = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result2 = extract_result(raw_result2)

            # Step 5: Verify it's detected as EXISTING, not NEW
            assert result2["ok"], "Second set_project call failed"

            # Check that it shows ACTIVATED (existing) not CREATED (new)
            readable2 = result2.get("readable_content", "")
            assert "PROJECT ACTIVATED" in readable2.upper() or "EXISTING PROJECT" in readable2.upper(), \
                f"BUG-001: Should show PROJECT ACTIVATED for rotated log. Got: {readable2[:200]}"
            assert "NEW PROJECT CREATED" not in readable2, \
                f"BUG-001: Should not show NEW PROJECT CREATED for rotated log. Got: {readable2[:200]}"

    @pytest.mark.asyncio
    async def test_bug_001_genuinely_new_project(self):
        """
        Regression test: Ensure truly new projects still work correctly.

        This verifies the fix doesn't break the happy path where a project
        is genuinely new (log file doesn't exist at all).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            unique_id = str(uuid.uuid4())[:8]
            project_name = f"test_bug_001_new_{unique_id}"
            agent_name = f"TestAgent-Bug001New-{unique_id}"
            project_root = Path(tmpdir)

            # Create a genuinely new project
            raw_result = await set_project(
                agent=agent_name,
                name=project_name,
                root=str(project_root),
                format="readable"
            )
            result = extract_result(raw_result)

            # Verify it's correctly detected as NEW
            assert result["ok"], "New project creation failed"

            # Verify NEW PROJECT message appears
            readable = result.get("readable_content", "")
            assert "NEW PROJECT" in readable.upper(), \
                f"New project should show NEW PROJECT message. Got: {readable[:200]}"

            # Verify log file exists after creation
            docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / project_name
            log_path = docs_dir / "PROGRESS_LOG.md"
            assert log_path.exists(), \
                f"Progress log should exist after creation at {log_path}"


class TestSlugCollisionDetection:
    """Test suite for slug collision detection in set_project (Task Package 1.8)."""

    @pytest.mark.asyncio
    async def test_collision_different_names_same_slug(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify that creating 'my-project' after 'my_project' is rejected with clear error.

        This tests the core collision detection: two different names that normalize to
        the same canonical slug should not be allowed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-Collision-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create first project: 'my_project'
            result1 = await set_project(
                agent=agent_name,
                name="my_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"First project creation failed: {result1}"

            # Try to create second project with different name but same slug: 'my-project'
            result2 = await set_project(
                agent=agent_name,
                name="my-project",
                root=str(project_root),
                format="structured"
            )
            result2 = extract_result(result2)

            # Should fail with collision error
            assert not result2.get("ok", False), \
                "Second project with colliding slug should be rejected"
            assert "error" in result2, "Collision response should include error message"
            assert "my_project" in result2["error"], \
                f"Error should mention existing project 'my_project'. Got: {result2['error']}"

            # Error can come from either path validation OR slug collision check
            # Both are valid ways to catch the same collision
            error_msg = result2["error"]
            is_path_collision = "already belongs to project" in error_msg
            is_slug_collision = "collision" in result2

            assert is_path_collision or is_slug_collision, \
                f"Should detect collision via path or slug check. Got: {result2}"

            # If it's a slug collision (reached our new check), verify details
            if is_slug_collision:
                collision = result2.get("collision", {})
                assert collision.get("new_name") == "my-project", \
                    "Collision should specify attempted new name"
                assert collision.get("existing_name") == "my_project", \
                    "Collision should specify existing project name"
                assert collision.get("canonical_slug") == "my_project", \
                    "Collision should show canonical slug both normalize to"

    @pytest.mark.asyncio
    async def test_no_collision_same_name_update(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify that updating a project with the same exact name is allowed (not a collision).

        This is critical: calling set_project twice with the same name should work
        (it's an update operation), even though the slugs are identical.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-NoCollision-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create project
            result1 = await set_project(
                agent=agent_name,
                name="test_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"First project creation failed: {result1}"

            # Update same project (same name) - should succeed
            result2 = await set_project(
                agent=agent_name,
                name="test_project",
                root=str(project_root),
                description="Updated description",
                format="structured"
            )
            result2 = extract_result(result2)

            # Should succeed
            assert result2.get("ok", False), \
                f"Updating project with same name should succeed. Got: {result2}"

    @pytest.mark.asyncio
    async def test_collision_multiple_variants(self, monkeypatch: pytest.MonkeyPatch):
        """
        Verify collision detection works with various slug variants.

        Tests: 'my_project', 'my-project', 'My Project', 'MY-PROJECT' all normalize
        to the same slug and should collide.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            unique_id = str(uuid.uuid4())[:8]
            agent_name = f"TestAgent-MultiVariant-{unique_id}"
            project_root = Path(tmpdir)
            (project_root / ".git").mkdir()

            async def _resolve_root_stub(*_args, **_kwargs):
                return project_root.resolve(), {
                    "resolved_root": str(project_root.resolve()),
                    "reason_code": "test_stubbed_root",
                }

            monkeypatch.setattr(set_project_module, "_resolve_root", _resolve_root_stub)

            # Create base project
            result1 = await set_project(
                agent=agent_name,
                name="my_project",
                root=str(project_root),
                format="structured"
            )
            result1 = extract_result(result1)
            assert result1.get("ok", False), f"Base project creation failed: {result1}"

            # Try various colliding names
            colliding_names = ["my-project", "My-Project", "MY_PROJECT", "my project"]

            for variant in colliding_names:
                result = await set_project(
                    agent=agent_name,
                    name=variant,
                    root=str(project_root),
                    format="structured"
                )
                result = extract_result(result)

                # All should fail with collision
                assert not result.get("ok", False), \
                    f"Variant '{variant}' should collide with 'my_project'"
                assert "collision" in result or "error" in result, \
                    f"Variant '{variant}' should have collision/error in response"

    @pytest.mark.asyncio
    async def test_slug_collision_precheck_ignores_other_repo(self):
        class FakeBackend:
            async def fetch_project(self, _name):
                return None

            async def list_projects(self):
                return [
                    SimpleNamespace(name="my_project", repo_root="/tmp/other_repo"),
                ]

        collision = await set_project_module._check_slug_collision(
            "my-project",
            FakeBackend(),
            Path("/tmp/current_repo"),
        )

        assert collision is None

    @pytest.mark.asyncio
    async def test_slug_collision_precheck_blocks_same_repo(self):
        class FakeBackend:
            async def fetch_project(self, _name):
                return None

            async def list_projects(self):
                return [
                    SimpleNamespace(name="my_project", repo_root="/tmp/current_repo"),
                ]

        collision = await set_project_module._check_slug_collision(
            "my-project",
            FakeBackend(),
            Path("/tmp/current_repo"),
        )

        assert collision is not None
        assert collision["collision"]["existing_name"] == "my_project"
        assert collision["collision"]["new_name"] == "my-project"
        assert collision["collision"]["canonical_slug"] == "my_project"


@pytest.mark.asyncio
async def test_set_project_handles_execution_context_failure(monkeypatch):
    """set_project should still succeed when execution context lookup raises."""
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_id = str(uuid.uuid4())[:8]
        agent_name = f"TestAgent-ContextFail-{unique_id}"
        project_name = f"context_fail_project_{unique_id}"
        project_root = Path(tmpdir)

        def _raise_context_error():
            raise RuntimeError("forced execution-context failure")

        monkeypatch.setattr(set_project_module.server_module, "get_execution_context", _raise_context_error)

        result = await set_project(
            agent=agent_name,
            name=project_name,
            root=str(project_root),
            format="structured",
        )
        result = extract_result(result)
        assert result.get("ok", False), f"set_project should tolerate context failure. Got: {result}"


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
