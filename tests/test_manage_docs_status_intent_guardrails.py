from __future__ import annotations

import pytest

from scribe_mcp.doc_management.actions.edit import handle_edit_action


class _Helper:
    def apply_context_payload(self, response, _context):
        return response


@pytest.mark.asyncio
async def test_status_update_frontmatter_intent_returns_exact_mismatch_code() -> None:
    result = await handle_edit_action(
        action="status_update",
        project={"docs": {"architecture": "/tmp/arch.md"}},
        doc_name="architecture",
        doc_category="",
        section="main",
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"frontmatter": {"status": "done"}},
        dry_run=True,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=object(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=None,
        get_or_create_storage_project=None,
        append_entry=None,
        normalize_metadata_with_healing=None,
        index_doc_for_vector=None,
        vector_indexing_enabled=False,
        get_index_updater_for_path=None,
        project_registry=None,
        server_module=None,
        logger=None,
    )
    assert result is not None
    assert result.get("code") == "DOC_STATUS_INTENT_MISMATCH"
    assert "frontmatter_update" in result.get("error", "")
    assert "metadata.frontmatter" in result.get("error", "")


@pytest.mark.asyncio
async def test_status_update_non_frontmatter_payload_does_not_trigger_mismatch_code() -> None:
    result = await handle_edit_action(
        action="status_update",
        project={"docs": {}},
        doc_name="architecture",
        doc_category="",
        section="main",
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"completed": True},
        dry_run=True,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=object(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=None,
        get_or_create_storage_project=None,
        append_entry=None,
        normalize_metadata_with_healing=None,
        index_doc_for_vector=None,
        vector_indexing_enabled=False,
        get_index_updater_for_path=None,
        project_registry=None,
        server_module=None,
        logger=None,
    )
    assert result is not None
    assert result.get("code") != "DOC_STATUS_INTENT_MISMATCH"


@pytest.mark.asyncio
async def test_status_update_checklist_status_does_not_trigger_mismatch_code() -> None:
    result = await handle_edit_action(
        action="status_update",
        project={"docs": {"checklist": "/tmp/checklist.md"}},
        doc_name="checklist",
        doc_category="checklist",
        section="item-a",
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"status": "done"},
        dry_run=True,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=object(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=None,
        get_or_create_storage_project=None,
        append_entry=None,
        normalize_metadata_with_healing=None,
        index_doc_for_vector=None,
        vector_indexing_enabled=False,
        get_index_updater_for_path=None,
        project_registry=None,
        server_module=None,
        logger=None,
    )
    assert result is not None
    assert result.get("code") != "DOC_STATUS_INTENT_MISMATCH"


@pytest.mark.asyncio
async def test_status_update_narrative_top_level_status_intent_returns_exact_mismatch_code() -> None:
    result = await handle_edit_action(
        action="status_update",
        project={"docs": {"architecture": "/tmp/arch.md"}},
        doc_name="architecture",
        doc_category="",
        section="main",
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={"status": "done", "summary": "Narrative status edit"},
        dry_run=True,
        backend=None,
        agent_id="test-agent",
        helper=_Helper(),
        context=object(),
        execution_context=None,
        deprecation_warning=None,
        apply_doc_change=None,
        get_or_create_storage_project=None,
        append_entry=None,
        normalize_metadata_with_healing=None,
        index_doc_for_vector=None,
        vector_indexing_enabled=False,
        get_index_updater_for_path=None,
        project_registry=None,
        server_module=None,
        logger=None,
    )
    assert result is not None
    assert result.get("code") == "DOC_STATUS_INTENT_MISMATCH"
    assert "frontmatter_update" in result.get("error", "")
    assert "metadata.frontmatter" in result.get("error", "")
