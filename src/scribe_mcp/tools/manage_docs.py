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
from scribe_mcp.doc_management import utils as utils_shared
from scribe_mcp.doc_management.manager import _resolve_doc_path
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector
from scribe_mcp.utils.error_handler import HealingErrorHandler
from scribe_mcp.utils.config_manager import ConfigManager
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import ProjectRegistry


logger = logging.getLogger(__name__)


class _ManageDocsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.parameter_corrector = BulletproofParameterCorrector()
        self.error_handler = HealingErrorHandler()
        self.config_manager = ConfigManager("manage_docs")


_MANAGE_DOCS_HELPER = _ManageDocsHelper()
_PROJECT_REGISTRY = ProjectRegistry()

PRIMARY_ACTIONS = runtime_shared.PRIMARY_ACTIONS
HIDDEN_ACTIONS = runtime_shared.HIDDEN_ACTIONS
VALID_ACTIONS = runtime_shared.VALID_ACTIONS
ACTION_ROUTER = runtime_shared.ACTION_ROUTER


def _chunk_text_for_vector(text: str, max_chars: int = 4000) -> List[str]:
    """Compatibility wrapper for legacy tests/import paths."""
    return utils_shared.chunk_text_for_vector(text, max_chars=max_chars)


def _should_skip_doc_index(doc_key: Optional[str], path: Path) -> bool:
    """Compatibility wrapper for legacy tests/import paths."""
    return indexing_shared.should_skip_doc_index(doc_key, path)


def _resolve_semantic_limits(*, search_meta: Dict[str, Any], repo_root: Optional[Path]) -> Dict[str, Any]:
    """Compatibility wrapper for legacy tests/import paths."""
    return indexing_shared.resolve_semantic_limits(search_meta=search_meta, repo_root=repo_root)


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
    """Apply structured updates to architecture/phase/checklist documents and create research/bug documents."""
    _ = agent  # reserved for audit metadata consistency in tool signature
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    if doc_name is None and doc is not None:
        doc_name = doc

    return await runtime_shared.handle_manage_docs_request(
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
