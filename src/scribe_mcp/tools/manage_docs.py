"""Thin MCP tool router for manage_docs operations."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.tool_contracts import stateful_local_tool
from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.doc_management import runtime as runtime_shared
from scribe_mcp.doc_management import special_create as special_create_shared
from scribe_mcp.doc_management.manager import _resolve_doc_path
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector
from scribe_mcp.utils.error_handler import HealingErrorHandler
from scribe_mcp.utils.config_manager import ConfigManager
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import get_runtime_project_registry


logger = logging.getLogger(__name__)


class _ManageDocsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.parameter_corrector = BulletproofParameterCorrector()
        self.error_handler = HealingErrorHandler()
        self.config_manager = ConfigManager("manage_docs")


_MANAGE_DOCS_HELPER = _ManageDocsHelper()
_PROJECT_REGISTRY = get_runtime_project_registry()

PRIMARY_ACTIONS = runtime_shared.PRIMARY_ACTIONS
HIDDEN_ACTIONS = runtime_shared.HIDDEN_ACTIONS
VALID_ACTIONS = runtime_shared.VALID_ACTIONS
ACTION_ROUTER = runtime_shared.ACTION_ROUTER


def _should_skip_doc_index(doc_key: Optional[str], path: Path) -> bool:
    """Compatibility wrapper for legacy tests/import paths."""
    return indexing_shared.should_skip_doc_index(doc_key, path)


async def _get_or_create_storage_project(backend: Any, project: Dict[str, Any]) -> Any:
    """Compatibility wrapper for storage project bootstrap."""
    return await runtime_shared.get_or_create_storage_project(
        backend=backend,
        project=project,
        server_module=server_module,
    )


async def _auto_register_document(project: Dict[str, Any], doc_name: str) -> bool:
    """Compatibility wrapper for auto-registration logic."""
    return await runtime_shared.auto_register_document(
        project,
        doc_name,
        server_module=server_module,
        resolve_doc_path=_resolve_doc_path,
        project_registry=_PROJECT_REGISTRY,
        append_entry=append_entry,
        logger=logger,
    )


@app.tool(**stateful_local_tool(title="Manage Docs", tags=("docs", "governance", "write")))
async def manage_docs(
    agent: str = "Codex",
    action: str = "",
    doc_category: str = "",
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any] | str] = None,
    patch_mode: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    doc_name: Optional[str] = None,
    doc: Optional[str] = None,
    target_dir: Optional[str] = None,
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply structured document updates and creation workflows.

    Generic frontmatter workflow metadata (via `metadata`) supports top-level keys:
    `summary`, `tags`, `owners`, `category`, `status`, `version`, `related_docs`,
    `maintained_by`, `run_id`, `stage`, `session_id`, `work_item_id`.

    Reserved lifecycle behavior:
    - `created_by` is computed from the acting runtime agent (fallback `Scribe`) on create
      and treated as immutable on edit.
    - `maintained_by` defaults to the acting agent for create/edit mutations unless
      explicitly overridden.
    - `edit_trace` is reserved and authored by the tool. Raw caller-provided
      `metadata.edit_trace` / `metadata.frontmatter.edit_trace` is ignored with hints.

    `metadata.frontmatter` remains the advanced override surface for non-reserved fields.
    Responses include compact frontmatter summaries by default; set
    `metadata.include_frontmatter_extra=true` to include the full merged payload.
    """
    _ = agent  # reserved for audit metadata consistency in tool signature
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    if doc_name is None and doc is not None:
        doc_name = doc

    result = await runtime_shared.handle_manage_docs_request(
        action=action,
        doc_category=doc_category,
        section=section,
        content=content,
        patch=patch,
        patch_source_hash=patch_source_hash,
        edit=edit,
        patch_mode=patch_mode,
        start_line=start_line,
        end_line=end_line,
        template=template,
        metadata=metadata,
        dry_run=dry_run,
        doc_name=doc_name,
        target_dir=target_dir,
        project=project,
        state_snapshot=state_snapshot,
        helper=_MANAGE_DOCS_HELPER,
        server_module=server_module,
        append_entry=append_entry,
        project_registry=_PROJECT_REGISTRY,
        logger=logger,
        handle_special_document_creation=_handle_special_document_creation,
        get_or_create_storage_project=_get_or_create_storage_project,
        get_index_updater_for_path=_get_index_updater_for_path,
        auto_register_document=_auto_register_document,
        valid_actions=VALID_ACTIONS,
        action_router=ACTION_ROUTER,
    )
    if isinstance(result, dict):
        result.setdefault("supported_actions", runtime_shared.build_manage_docs_action_manifest())
    if action == "create" and isinstance(result, dict) and result.get("ok"):
        create_intent = runtime_shared.build_create_intent_payload(
            result=result,
            metadata=metadata if isinstance(metadata, dict) else None,
            requested_doc_name=doc_name,
        )
        if create_intent:
            result["create_intent"] = create_intent
            canonical_doc_name = create_intent.get("canonical_doc_name")
            if canonical_doc_name:
                result.setdefault("canonical_doc_name", canonical_doc_name)
            first_write_action = create_intent.get("first_write_action")
            if first_write_action:
                result.setdefault("first_write_action", first_write_action)
            guidance = create_intent.get("next_step_guidance")
            if guidance:
                result["next_step_guidance"] = guidance
    return result


def manage_docs_main():
    """CLI entry point for manage_docs functionality."""
    from scribe_mcp.doc_management.cli import run_manage_docs_cli

    return run_manage_docs_cli(manage_docs)


async def _handle_special_document_creation(
    project: Dict[str, Any],
    action: str,
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    agent_id: str,
    storage_backend: Any,
    helper: LoggingToolMixin,
    context: Any,
) -> Dict[str, Any]:
    """Compatibility wrapper delegating to shared special creation module."""
    return await special_create_shared.handle_special_document_creation(
        project=project,
        action=action,
        doc_name=doc_name,
        target_dir=target_dir,
        content=content,
        metadata=metadata,
        dry_run=dry_run,
        agent_id=agent_id,
        storage_backend=storage_backend,
        helper=helper,
        context=context,
        project_registry=_PROJECT_REGISTRY,
        logger=logger,
    )


def _get_index_updater_for_path(
    file_path: Path,
    project_root: Path,
    docs_dir: Path,
    agent_id: str,
) -> Optional[Callable[[], Awaitable[None]]]:
    """Compatibility wrapper for special index updater lookup."""
    return special_create_shared.get_index_updater_for_path(
        file_path=file_path,
        project_root=project_root,
        docs_dir=docs_dir,
        agent_id=agent_id,
    )


async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    """Compatibility wrapper delegating to shared special creation module."""
    await special_create_shared._update_research_index(research_dir, agent_id)


async def _update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    """Compatibility wrapper delegating to shared special creation module."""
    await special_create_shared._update_bug_index(bugs_dir, agent_id)


async def _update_review_index(docs_dir: Path, agent_id: str) -> None:
    """Compatibility wrapper delegating to shared special creation module."""
    await special_create_shared._update_review_index(docs_dir, agent_id)


async def _update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    """Compatibility wrapper delegating to shared special creation module."""
    await special_create_shared._update_agent_card_index(docs_dir, agent_id)


async def _render_review_report_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Compatibility wrapper delegating to shared special creation module."""
    return await special_create_shared._render_review_report_template(
        project=project,
        agent_id=agent_id,
        prepared_metadata=prepared_metadata,
        logger=logger,
    )


async def _render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Compatibility wrapper delegating to shared special creation module."""
    return await special_create_shared._render_agent_report_card_template(
        project=project,
        agent_id=agent_id,
        prepared_metadata=prepared_metadata,
        logger=logger,
    )


if __name__ == "__main__":
    sys.exit(manage_docs_main())
