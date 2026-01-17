#!/usr/bin/env python3
"""
Real production test for auto-registration fallback path.

This test FORCES _resolve_doc_path() to use fallback logic (line 729)
by clearing the project["docs"] registry before testing.

Bug: Line 729 hardcoded "docs/dev_plans" instead of using ".scribe/docs/dev_plans"
Fix: Use project.get("docs_dir") first, then fallback to ".scribe/docs/dev_plans"
"""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import uuid
import json
from scribe_mcp.tools.set_project import set_project
from scribe_mcp.tools.manage_docs import manage_docs
from scribe_mcp.tools.delete_project import delete_project
from scribe_mcp.config.settings import settings


@pytest.mark.asyncio
async def test_auto_registration_fallback_path():
    """
    Test auto-registration works when doc is NOT pre-registered.

    This forces _resolve_doc_path() to use fallback logic (line 729-734).

    Steps:
    1. Create a real project with set_project() - this creates docs in .scribe/
    2. Verify ARCHITECTURE_GUIDE.md exists at correct path
    3. Clear project["docs"] to force fallback path execution
    4. Call manage_docs which triggers _resolve_doc_path()
    5. Verify auto-registration happens and uses correct .scribe/ path
    """
    # Create a unique test project
    project_name = f"fallback_test_{uuid.uuid4().hex[:8]}"

    try:
        # Step 1: Create project with set_project
        await set_project(name=project_name, root=str(settings.project_root))

        # Step 2: Verify ARCHITECTURE_GUIDE exists in .scribe/ structure
        state_path = Path(settings.project_root) / ".scribe" / "state.json"
        with open(state_path, "r") as f:
            state = json.load(f)

        project = state["projects"][project_name]
        assert "docs_dir" in project, "Project should have docs_dir field"

        docs_dir = Path(project["docs_dir"])
        assert docs_dir.exists(), f"docs_dir should exist: {docs_dir}"
        assert ".scribe" in str(docs_dir), f"docs_dir should use .scribe: {docs_dir}"

        # Verify ARCHITECTURE_GUIDE was created
        arch_path = docs_dir / "ARCHITECTURE_GUIDE.md"
        assert arch_path.exists(), f"ARCHITECTURE_GUIDE.md should exist: {arch_path}"

        # Step 3: Clear project["docs"] to force fallback logic
        # This simulates a scenario where docs are NOT pre-registered
        project["docs"] = {}
        state["projects"][project_name] = project

        # Write modified state back
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        # Verify docs is actually empty
        with open(state_path, "r") as f:
            state_after = json.load(f)
        assert state_after["projects"][project_name].get("docs", {}) == {}, "Docs should be cleared"

        # Step 4: Call manage_docs with empty docs registry
        # This will trigger _resolve_doc_path() fallback logic at line 729-734
        await manage_docs(action="list_sections", doc="architecture")

        # Step 5: Verify auto-registration happened (proves fallback path works)

        # Verify auto-registration happened
        with open(state_path, "r") as f:
            state_final = json.load(f)

        project_final = state_final["projects"][project_name]
        assert "architecture" in project_final.get("docs", {}), "Architecture should be auto-registered"

        # Verify the registered path is correct (.scribe structure)
        registered_path = project_final["docs"]["architecture"]
        assert ".scribe" in registered_path, f"Registered path should use .scribe: {registered_path}"

        print(f"✅ Test PASSED: Fallback path correctly uses .scribe structure")
        print(f"   Project: {project_name}")
        print(f"   docs_dir: {docs_dir}")
        print(f"   Registered path: {registered_path}")

    finally:
        # Cleanup: Delete test project
        try:
            await delete_project(name=project_name, mode="permanent", confirm=True)
        except Exception as e:
            print(f"Warning: Cleanup failed for {project_name}: {e}")


@pytest.mark.asyncio
async def test_fallback_path_without_docs_dir():
    """
    Test fallback logic when project has NO docs_dir field.

    This tests the final fallback to .scribe/docs/dev_plans/<project_name>
    """
    project_name = f"no_docs_dir_{uuid.uuid4().hex[:8]}"

    try:
        # Create project
        await set_project(name=project_name, root=str(settings.project_root))

        # Manually remove docs_dir from project config
        state_path = Path(settings.project_root) / ".scribe" / "state.json"
        with open(state_path, "r") as f:
            state = json.load(f)

        project = state["projects"][project_name]

        # Remove both docs and docs_dir
        project["docs"] = {}
        if "docs_dir" in project:
            del project["docs_dir"]

        state["projects"][project_name] = project

        # Write modified state back
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        # Verify removal
        with open(state_path, "r") as f:
            state_after = json.load(f)
        project_after = state_after["projects"][project_name]
        assert "docs_dir" not in project_after, "docs_dir should be removed"
        assert project_after.get("docs", {}) == {}, "docs should be empty"

        # Call manage_docs - should use final fallback to .scribe/
        await manage_docs(action="list_sections", doc="architecture")

        # Verify auto-registered path uses .scribe
        with open(state_path, "r") as f:
            state_final = json.load(f)

        project_final = state_final["projects"][project_name]
        registered_path = project_final["docs"]["architecture"]
        assert ".scribe" in registered_path, f"Final fallback should use .scribe: {registered_path}"

        print(f"✅ Test PASSED: Final fallback correctly uses .scribe structure")
        print(f"   Registered path: {registered_path}")

    finally:
        try:
            await delete_project(name=project_name, mode="permanent", confirm=True)
        except Exception as e:
            print(f"Warning: Cleanup failed: {e}")


if __name__ == "__main__":
    import asyncio

    print("=" * 80)
    print("RUNNING REAL PRODUCTION TEST FOR AUTO-REGISTRATION FALLBACK PATH")
    print("=" * 80)

    # Run both tests
    asyncio.run(test_auto_registration_fallback_path())
    print()
    asyncio.run(test_fallback_path_without_docs_dir())

    print()
    print("=" * 80)
    print("ALL TESTS PASSED - BUG FIX VERIFIED")
    print("=" * 80)
