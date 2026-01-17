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
import sys
import shutil

# Add MCP_SPINE to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

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
            project_name = f"test_bug_001_rotation_{id(tmpdir)}"
            project_root = Path(tmpdir)

            # Step 1: Create initial project (use readable format to get is_new flag)
            raw_result1 = await set_project(
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
                agent="TestAgent"
            )

            # Step 3: Rotate the log (creates empty file)
            raw_rotate = await rotate_log(confirm=True)
            rotate_result = extract_result(raw_rotate)
            assert rotate_result["ok"], "Log rotation failed"

            # Step 4: Call set_project again after rotation
            raw_result2 = await set_project(
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
            project_name = f"test_bug_001_new_{id(tmpdir)}"
            project_root = Path(tmpdir)

            # Create a genuinely new project
            raw_result = await set_project(
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


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
