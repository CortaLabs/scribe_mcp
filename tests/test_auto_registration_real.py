#!/usr/bin/env python3
"""
Real production tests for auto-registration fallback path.

These tests use DB-backed project records as the source of truth and avoid
state.json mutation, matching the Phase 3 storage direction.
"""

import sys
import json
import uuid
from pathlib import Path

# Add MCP_SPINE to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.tools.delete_project import delete_project
from scribe_mcp.tools.manage_docs import _auto_register_document
from scribe_mcp.tools.project_utils import slugify_project_name
from scribe_mcp.tools.set_project import set_project


@pytest.mark.asyncio
async def test_auto_registration_fallback_path():
    """
    Test auto-registration works when doc is NOT pre-registered.

    This forces _resolve_doc_path() to use fallback logic (line 729-734).

    Steps:
    1. Create a real project with set_project() - this creates docs in .scribe/
    2. Verify ARCHITECTURE_GUIDE.md exists at correct path from DB docs_json
    3. Clear docs_json in DB to force fallback path execution
    4. Call _auto_register_document() with empty docs mapping
    5. Verify DB docs_json is restored using .scribe path
    """
    # Create a unique test project
    project_name = f"fallback_test_{uuid.uuid4().hex[:8]}"

    try:
        # Step 1: Create project with set_project
        await set_project(name=project_name, root=str(settings.project_root))

        backend = server_module.storage_backend
        assert backend is not None, "Storage backend should be available"

        project_record = await backend.fetch_project(project_name)
        assert project_record is not None, "Project should be created in database"

        docs_json = json.loads(project_record.docs_json or "{}")
        arch_registered = docs_json.get("architecture")
        assert arch_registered, "Architecture doc should be registered by set_project"

        arch_path = Path(arch_registered)
        docs_dir = arch_path.parent
        assert docs_dir.exists(), f"docs_dir should exist: {docs_dir}"
        assert ".scribe" in str(docs_dir), f"docs_dir should use .scribe: {docs_dir}"

        assert arch_path.exists(), f"ARCHITECTURE_GUIDE.md should exist: {arch_path}"

        # Step 3: Clear docs_json in DB to force fallback resolution path
        await backend.update_project_docs(project_name, json.dumps({}))

        # Step 4: Auto-register using a project payload with empty docs
        payload = {
            "name": project_name,
            "root": str(settings.project_root),
            "progress_log": project_record.progress_log_path,
            "docs_dir": str(docs_dir),
            "docs": {},
        }
        assert await _auto_register_document(payload, "architecture") is True

        # Step 5: Verify DB docs_json was restored
        updated = await backend.fetch_project(project_name)
        updated_docs = json.loads(updated.docs_json or "{}")
        registered_path = updated_docs.get("architecture")
        assert registered_path, "Architecture should be auto-registered into DB docs_json"
        assert ".scribe" in registered_path, f"Registered path should use .scribe: {registered_path}"
        assert Path(registered_path) == arch_path

        print(f"✅ Test PASSED: Fallback path correctly uses .scribe structure")
        print(f"   Project: {project_name}")
        print(f"   docs_dir: {docs_dir}")
        print(f"   Registered path: {registered_path}")

    finally:
        # Cleanup: Delete test project
        try:
            await delete_project(
                name=project_name,
                root=str(settings.project_root),
                mode="permanent",
                confirm=True,
            )
        except Exception as e:
            print(f"Warning: Cleanup failed for {project_name}: {e}")


@pytest.mark.asyncio
async def test_fallback_path_without_docs_dir():
    """
    Test fallback logic when project has NO docs_dir field.

    This tests the final fallback to .scribe/docs/dev_plans/<project_name>
    when docs_dir is not provided in the project payload.
    """
    project_name = f"no_docs_dir_{uuid.uuid4().hex[:8]}"

    try:
        await set_project(name=project_name, root=str(settings.project_root))
        backend = server_module.storage_backend
        assert backend is not None, "Storage backend should be available"

        # Clear DB docs mapping to force registration from fallback path only.
        await backend.update_project_docs(project_name, json.dumps({}))

        payload = {
            "name": project_name,
            "root": str(settings.project_root),
            "progress_log": str(
                settings.project_root
                / ".scribe"
                / "docs"
                / "dev_plans"
                / slugify_project_name(project_name)
                / "PROGRESS_LOG.md"
            ),
            "docs": {},
        }
        assert await _auto_register_document(payload, "architecture") is True

        updated = await backend.fetch_project(project_name)
        updated_docs = json.loads(updated.docs_json or "{}")
        registered_path = updated_docs.get("architecture")
        assert registered_path, "Architecture should be registered in DB"
        assert ".scribe" in registered_path, f"Final fallback should use .scribe: {registered_path}"
        assert Path(registered_path).exists(), f"Registered path should exist: {registered_path}"

        print(f"✅ Test PASSED: Final fallback correctly uses .scribe structure")
        print(f"   Registered path: {registered_path}")

    finally:
        try:
            await delete_project(
                name=project_name,
                root=str(settings.project_root),
                mode="permanent",
                confirm=True,
            )
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
