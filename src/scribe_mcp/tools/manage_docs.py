"""Thin MCP tool router for manage_docs operations."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

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


# Per-action `metadata` sub-key hints, sourced from the live runtime handlers
# (doc_management/manager.py) — keeps the host-facing description truthful instead
# of inventing keys. Used only to build the `metadata` description string below.
_METADATA_ACTION_HINTS = (
    "replace_text -> metadata.find (required), metadata.replace, "
    "metadata.match_mode (literal|regex|prefix), metadata.replace_all, "
    "metadata.scope, metadata.allow_no_match; "
    "replace_range -> metadata.line_reference (file|body); "
    "frontmatter_update -> metadata.frontmatter (object of frontmatter fields); "
    "status_update -> metadata.status, metadata.proof (checklist items only)"
)

# Generic frontmatter workflow keys accepted under `metadata` (mirrors the
# manage_docs docstring — the single source the agent already reads).
_METADATA_FRONTMATTER_KEYS = (
    "title, summary, tags, owners, category, status, version, related_docs, "
    "agent_id, maintained_by, run_id, stage, session_id, work_item_id"
)


def _build_manage_docs_input_schema() -> Dict[str, Any]:
    """Hand-authored host input schema for ``manage_docs``.

    Mirrors the ``set_project`` override pattern (``set_project.py`` /
    ``_SET_PROJECT_INPUT_SCHEMA``): the host uses this schema verbatim and the
    server's ``_with_runtime_agent_schema`` then injects the required ``agent``
    field. Two enrichments over the auto-built schema:

    * ``action`` carries an ``enum`` sourced live from
      ``build_manage_docs_action_manifest()["all_actions"]`` (single source of
      truth — never hand-copied, so it follows ``VALID_ACTIONS`` automatically).
    * ``metadata`` carries a ``description`` enumerating the supported
      frontmatter keys and the per-action sub-keys, so a mistyped action or an
      unknown metadata key is teachable at the host instead of opaque.

    ``additionalProperties`` stays ``True`` so passthrough kwargs and metadata
    compatibility aliases (e.g. ``doc``) are not regressed into hard rejections.
    ``action`` is declared required here to fix the signature/default mismatch:
    every parameter has a Python default, so the auto-builder marked nothing
    required even though ``action`` is mandatory.
    """
    all_actions = runtime_shared.build_manage_docs_action_manifest()["all_actions"]
    metadata_description = (
        "Structured workflow metadata. Generic frontmatter keys: "
        f"{_METADATA_FRONTMATTER_KEYS}. Per-action sub-keys: {_METADATA_ACTION_HINTS}."
    )
    return {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "action": {
                "type": "string",
                "enum": list(all_actions),
                "description": (
                    "Document operation to perform. Must be one of the listed "
                    "actions (sourced live from the action manifest)."
                ),
            },
            "doc_category": {"type": "string"},
            "section": {"type": "string"},
            "content": {"type": "string"},
            "patch": {"type": "string"},
            "patch_source_hash": {"type": "string"},
            "expected_anchor_sha256": {"type": "string"},
            "edit": {"type": "object"},
            "patch_mode": {"type": "string"},
            "start_line": {"type": ["integer", "string"]},
            "end_line": {"type": ["integer", "string"]},
            "template": {"type": "string"},
            "metadata": {"type": "object", "description": metadata_description},
            "dry_run": {"type": "boolean"},
            "doc_name": {"type": "string"},
            "doc": {"type": "string"},
            "target_dir": {"type": "string"},
            "project": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": True,
    }


_MANAGE_DOCS_INPUT_SCHEMA: Dict[str, Any] = _build_manage_docs_input_schema()


def _should_skip_doc_index(doc_key: Optional[str], path: Path) -> bool:
    """Compatibility wrapper for legacy tests/import paths."""
    return indexing_shared.should_skip_doc_index(doc_key, path)


def _preserve_explicit_create_actor(
    action: str,
    metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Protect explicit create attribution from ambient runtime identity."""
    if action != "create" or not isinstance(metadata, dict):
        return metadata

    explicit_actor = metadata.get("agent_id")
    if not isinstance(explicit_actor, str) or not explicit_actor.strip():
        return metadata
    if isinstance(metadata.get("created_by"), str) and metadata["created_by"].strip():
        return metadata

    normalized = dict(metadata)
    normalized["created_by"] = explicit_actor.strip()
    return normalized


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


@app.tool(
    **stateful_local_tool(title="Manage Docs", tags=("docs", "governance", "write")),
    input_schema=_MANAGE_DOCS_INPUT_SCHEMA,
)
async def manage_docs(
    agent: str = "Codex",
    action: str = "",
    doc_category: str = "",
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    expected_anchor_sha256: Optional[str] = None,
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

    `manage_docs` is the full governed-document engine, not just create/edit. It
    exposes 28 actions. The 8 PRIMARY write/edit actions are the everyday surface;
    the remaining 20 (the "governance engine") cover discovery, quality gating,
    topology/metadata scans, safe maintenance, and reporting — most are
    undocumented elsewhere, so this docstring is the canonical action catalog.

    PRIMARY — write / edit:
    - `create` — scaffold a new managed doc (a template, NOT a finished doc; always
      follow with `replace_section`).
    - `replace_section` — populate a scaffold section by anchor ID.
    - `apply_patch` — context-anchored surgical edit (preferred for existing content;
      survives line drift where `replace_range` does not).
    - `replace_range` — replace an explicit line span (line numbers; auto-adjusts
      file-relative numbers to body-relative).
    - `replace_text` — find/replace via `metadata.find` (+`metadata.replace`,
      `metadata.match_mode`).
    - `append` — append content to a doc.
    - `status_update` — checklist-only: mark a checklist item done with proof.
    - `frontmatter_update` — narrative-doc frontmatter/status edits via
      `metadata.frontmatter`.

    GOVERNANCE — discovery, quality, scans, maintenance, reporting:
    - `list_sections` / `list_checklist_items` — enumerate editable anchors /
      checklist items before editing.
    - `search` — search within managed docs.
    - `quality_check` — primary scaffold-quality proof path; returns structured
      `SCF_*` warnings (codes, severity, blocking, locations, suggested repairs).
    - `quality_handoff_check` — readiness/handoff gate built on the same warnings.
    - `scaffold_quality_check` — scaffold-residue detection.
    - `project_health` — recent doc-surface health for the active project.
    - `topology_scan` — typed cross-doc edge / relationship inspection.
    - `metadata_scan` / `metadata_repair` — audit and safely repair doc metadata.
    - `stale_cleanup_scan` — surface stale/orphaned doc cleanup recommendations.
    - `generate_toc` — (re)generate a table of contents.
    - `normalize_headers` — normalize heading levels.
    - `validate_crosslinks` — find broken `[[wikilinks]]` / cross-references.
    - `rehome_doc` — move a managed doc to its canonical location WITHOUT losing
      Scribe registration (never use shell `mv`/`cp` on managed docs).
    - `apply_global_changelog` — roll a change into the global changelog.
    - `preview_reconciliation` — preview physical/logical reconciliation before
      applying.
    - `regenerate_intelligence_exports` — rebuild intelligence/topology exports.
    - `ingestion_manifest_inspect` — inspect the sanitized downstream ingestion
      manifest.
    - `batch` — run multiple managed-doc operations in one call.

    Generic frontmatter workflow metadata (via `metadata`) supports top-level keys:
    `summary`, `tags`, `owners`, `category`, `status`, `version`, `related_docs`,
    `agent_id`, `maintained_by`, `run_id`, `stage`, `session_id`, `work_item_id`.

    Reserved lifecycle behavior:
    - `created_by` preserves an explicit non-empty create-time `metadata.agent_id`;
      otherwise it is computed from the acting runtime agent (fallback `Scribe`). It is
      treated as immutable on edit.
    - `maintained_by` defaults to the acting agent for create/edit mutations unless
      explicitly overridden.
    - `edit_trace` is reserved and authored by the tool. Raw caller-provided
      `metadata.edit_trace` / `metadata.frontmatter.edit_trace` is ignored with hints.

    Use `action="frontmatter_update"` for frontmatter-only narrative-document edits.
    Use `action="quality_check"` as the primary scaffold-quality proof path. It returns
    structured warnings with codes, severity, blocking status, locations, excerpts, and
    suggested repairs without requiring regex search payloads.
    `status_update` is checklist-only and returns `DOC_STATUS_INTENT_MISMATCH` when
    the payload looks like narrative frontmatter intent.
    `metadata.frontmatter` remains the advanced override surface for non-reserved fields.
    Responses include compact frontmatter summaries by default; set
    `metadata.include_frontmatter_extra=true` to include the full merged payload.
    """
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    if doc_name is None and doc is not None:
        doc_name = doc
    metadata = _preserve_explicit_create_actor(action, metadata)

    try:
        result = await runtime_shared.handle_manage_docs_request(
            action=action,
            doc_category=doc_category,
            section=section,
            content=content,
            patch=patch,
            patch_source_hash=patch_source_hash,
            expected_anchor_sha256=expected_anchor_sha256,
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
            caller_agent=agent,
            handle_special_document_creation=_handle_special_document_creation,
            get_or_create_storage_project=_get_or_create_storage_project,
            get_index_updater_for_path=_get_index_updater_for_path,
            auto_register_document=_auto_register_document,
            valid_actions=VALID_ACTIONS,
            action_router=ACTION_ROUTER,
        )
    except Exception as exc:
        logger.exception("manage_docs runtime request failed unexpectedly")
        return {
            "ok": False,
            "error": "manage_docs_runtime_error",
            "error_code": "MANAGE_DOCS_RUNTIME_EXCEPTION",
            "message": "manage_docs failed while processing the runtime request.",
            "exception_type": exc.__class__.__name__,
            "action": action,
            "doc_name": doc_name,
            "supported_actions": runtime_shared.build_manage_docs_action_manifest(),
        }
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
