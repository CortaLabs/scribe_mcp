#!/usr/bin/env python3
"""Lightweight integration test for list_projects registry enrichment."""

import pytest

from scribe_mcp.tools.list_projects import list_projects  # noqa: E402


@pytest.mark.asyncio
async def test_list_projects_includes_registry_fields_for_active_project() -> None:
    """list_projects should be able to return registry-enriched fields for the active project.

    This is a thin smoke test that relies on the existing storage backend and
    state; it asks for explicit fields so we can assert presence without
    depending on full registry internals.
    """
    # Request a small set of fields, including registry-related ones.
    result = await list_projects(
        limit=10,
        compact=False,
        fields=[
            "name",
            "status",
            "created_at",
            "last_entry_at",
            "last_access_at",
            "total_entries",
            "total_files",
            "total_phases",
        ],
    )

    assert result.get("ok") is True
    projects = result.get("projects") or []
    # We only assert that at least one project has status and created_at,
    # which indicates registry enrichment ran without error.
    assert projects
    enriched = [
        p
        for p in projects
        if "name" in p and "status" in p and "created_at" in p
    ]
    assert enriched, "Expected at least one project with registry-enriched fields"

