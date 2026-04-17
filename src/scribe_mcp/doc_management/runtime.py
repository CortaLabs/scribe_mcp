"""Runtime orchestration helpers for the manage_docs MCP tool."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from scribe_mcp.doc_management.manager import apply_doc_change, resolve_registered_doc_key
from scribe_mcp.doc_management import healing as healing_shared
from scribe_mcp.doc_management import indexing as indexing_shared
from scribe_mcp.doc_management import utils as utils_shared
from scribe_mcp.doc_management.actions import append as append_actions
from scribe_mcp.doc_management.actions import batch as batch_actions
from scribe_mcp.doc_management.actions import create as create_actions
from scribe_mcp.doc_management.actions import edit as edit_actions
from scribe_mcp.doc_management.actions import query as query_actions
from scribe_mcp.doc_management.actions import search as search_actions
from scribe_mcp.doc_management.actions import status as status_actions
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.logging_utils import LoggingContext, ProjectResolutionError
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope
from scribe_mcp.utils.slug import slugify_project_name, normalize_project_input


PRIMARY_ACTIONS = {
    "create",
    "replace_section",
    "apply_patch",
    "replace_range",
    "replace_text",
    "append",
    "status_update",
}

# Deprecated action aliases intentionally removed in fail-hard mode.
DEPRECATED_ALIASES: Dict[str, tuple[str, Dict[str, Any]]] = {}

HIDDEN_ACTIONS = {
    "normalize_headers",
    "generate_toc",
    "validate_crosslinks",
    "list_sections",
    "list_checklist_items",
    "preview_reconciliation",
    "search",
    "batch",
}

VALID_ACTIONS = PRIMARY_ACTIONS | HIDDEN_ACTIONS

ACTION_ROUTER = {
    "create_doc": "edit",
    "replace_section": "edit",
    "apply_patch": "edit",
    "replace_range": "edit",
    "replace_text": "edit",
    "append": "append",
    "status_update": "status",
    "normalize_headers": "query_transform",
    "generate_toc": "query_transform",
    "validate_crosslinks": "query_transform",
    "list_sections": "query",
    "list_checklist_items": "query",
    "preview_reconciliation": "query",
    "search": "search",
    "batch": "batch",
}

_MUTATION_ACTIONS = {
    "replace_section",
    "apply_patch",
    "replace_range",
    "append",
    "status_update",
    "normalize_headers",
    "generate_toc",
    "replace_text",
    "validate_crosslinks",
}

_CUSTOM_DOC_TYPES = {"research", "bugs", "reviews", "agent_cards"}
_READ_ONLY_REGISTRATION_GATED_ACTIONS = {
    "list_sections",
    "list_checklist_items",
    "preview_reconciliation",
    "search",
}


_SPECIAL_DOC_TYPES = {"research", "bug", "security", "review", "agent_card"}


def build_create_intent_payload(
    *,
    result: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    requested_doc_name: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build additive create-intent guidance for caller-facing clarity."""
    if not isinstance(result, dict) or not result.get("ok"):
        return None

    metadata_mapping = metadata if isinstance(metadata, dict) else {}
    doc_type = str(metadata_mapping.get("doc_type", "custom") or "custom").strip().lower()
    canonical_doc_name = (
        metadata_mapping.get("register_as")
        or metadata_mapping.get("doc_name")
        or result.get("doc_name")
        or requested_doc_name
    )
    canonical_doc_name = str(canonical_doc_name).strip() if canonical_doc_name else ""

    first_write_action = "replace_section"
    target_for_guidance = canonical_doc_name or requested_doc_name or "doc_name"

    if bool(metadata_mapping.get("register_existing")):
        first_write_action = "apply_patch"
        follow_up = (
            "create registered an existing file without writing new content. "
            "For the first mutation, call manage_docs(action='apply_patch', "
            f"doc='{target_for_guidance}', ...) so edits work on non-scaffold content."
        )
        return {
            "kind": "empty_registered_doc",
            "canonical_doc_name": canonical_doc_name or None,
            "first_write_action": first_write_action,
            "next_step_guidance": follow_up,
        }

    if doc_type in _SPECIAL_DOC_TYPES or bool(result.get("document_type")):
        first_write_action = "apply_patch"
        follow_up = (
            "create produced a contentful special document. "
            "Use manage_docs(action='apply_patch', ...) for follow-up edits."
        )
        return {
            "kind": "contentful_special_doc",
            "canonical_doc_name": canonical_doc_name or None,
            "first_write_action": first_write_action,
            "next_step_guidance": follow_up,
        }

    follow_up = (
        "create scaffolds a governed document. Next, call "
        f"manage_docs(action='replace_section', doc='{target_for_guidance}', ...) "
        "to add or replace section content anchored by <!-- ID: ... --> markers. "
        "If section boundaries drift or anchors/headings become ambiguous, switch to "
        "manage_docs(action='replace_range', ...) or action='apply_patch' for explicit control."
    )
    return {
        "kind": "governed_scaffold_doc",
        "canonical_doc_name": canonical_doc_name or None,
        "first_write_action": first_write_action,
        "next_step_guidance": follow_up,
    }


async def get_or_create_storage_project(backend: Any, project: Dict[str, Any], server_module: Any) -> Any:
    """Fetch or create the backing storage record for a project."""
    timeout = server_module.settings.storage_timeout_seconds
    async with asyncio.timeout(timeout):
        storage_record = await backend.fetch_project(project["name"])
    if not storage_record:
        async with asyncio.timeout(timeout):
            storage_record = await backend.upsert_project(
                name=project["name"],
                repo_root=project["root"],
                progress_log_path=project["progress_log"],
            )
    return storage_record


async def auto_register_document(
    project: Dict[str, Any],
    doc_name: str,
    *,
    server_module: Any,
    resolve_doc_path: Callable[[Dict[str, Any], str], Path],
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> bool:
    """Auto-register an unregistered document into persistent docs mapping."""
    try:
        doc_path = resolve_doc_path(project, doc_name)
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise ValueError(
            f"Cannot auto-register '{doc_name}': Invalid document identifier or path resolution failed. "
            f"Use 'generate_doc_templates' to create standard documents first. Error: {exc}"
        ) from exc

    if not doc_path.exists():
        raise ValueError(
            f"Cannot auto-register '{doc_name}': File {doc_path} does not exist. "
            f"Use 'generate_doc_templates' to create it first."
        )

    try:
        with open(doc_path, "rb") as handle:
            doc_hash = hashlib.sha256(handle.read()).hexdigest()
    except Exception as exc:  # pragma: no cover - filesystem failure
        raise ValueError(f"Failed to read document {doc_path} for hashing: {exc}") from exc

    backend = server_module.storage_backend
    if not backend:
        raise ValueError("Storage backend not available for auto-registration")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("Project must have a name for auto-registration")

    try:
        current_docs = dict(project.get("docs", {}) or {})
        current_docs[doc_name] = str(doc_path)
        project["docs"] = current_docs
        docs_json = json.dumps(current_docs)
        await backend.update_project_docs(project_name, docs_json)
        state_manager = getattr(server_module, "state_manager", None)
        if state_manager and hasattr(state_manager, "set_current_project"):
            execution_context = None
            get_execution_context = getattr(server_module, "get_execution_context", None)
            if callable(get_execution_context):
                try:
                    execution_context = get_execution_context()
                except Exception:  # pragma: no cover - defensive context lookup
                    execution_context = None
            authoritative_scope = resolve_authoritative_write_scope(
                context=execution_context,
                agent_session_id=None,
            )
            try:
                await state_manager.set_current_project(
                    project_name,
                    project,
                    agent_id="manage_docs",
                    session_id=authoritative_scope.get("authoritative_session_id"),
                    resolved_scope=authoritative_scope.get("resolved_scope"),
                    mirror_global=False,
                )
            except Exception as exc:  # pragma: no cover - defensive state sync
                logger.warning(
                    "Auto-registration database update succeeded but state sync failed for '%s': %s",
                    doc_name,
                    exc,
                )
        logger.info("Auto-registered document '%s' for project '%s'", doc_name, project_name)
    except Exception as exc:
        raise ValueError(f"Failed to update database for auto-registration: {exc}") from exc

    try:
        registry_call = project_registry.record_doc_update(
            project_name=project_name,
            doc=doc_name,
            action="auto_register",
            after_hash=doc_hash,
        )
        if inspect.isawaitable(registry_call):
            await registry_call
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to update ProjectRegistry for '%s': %s", doc_name, exc)

    try:
        await append_entry(
            message=f"Auto-registered document: {doc_name} ({doc_path.name})",
            status="info",
            agent="manage_docs",
            meta={
                "action": "auto_register",
                "doc": doc_name,
                "doc_name": doc_name,
                "path": str(doc_path),
                "hash": doc_hash[:8],
            },
            format="structured",
        )
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to log auto-registration event: %s", exc)

    return True


async def register_document_path(
    project: Dict[str, Any],
    doc_name: str,
    doc_path: Path,
    *,
    server_module: Any,
    project_registry: Any,
    append_entry: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
    execution_context: Any = None,
    agent_id: str = "manage_docs",
) -> Optional[str]:
    """Persist a resolved document path into docs mapping and registry state."""
    if not doc_path.exists():
        raise ValueError(f"Cannot register '{doc_name}': File {doc_path} does not exist.")

    try:
        with open(doc_path, "rb") as handle:
            doc_hash = hashlib.sha256(handle.read()).hexdigest()
    except Exception as exc:  # pragma: no cover - filesystem failure
        raise ValueError(f"Failed to read document {doc_path} for hashing: {exc}") from exc

    backend = server_module.storage_backend
    if not backend:
        raise ValueError("Storage backend not available for registration")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("Project must have a name for registration")

    current_docs = dict(project.get("docs", {}) or {})
    current_docs[doc_name] = str(doc_path)
    project["docs"] = current_docs
    docs_json = json.dumps(current_docs)
    await backend.update_project_docs(project_name, docs_json)

    reload_warning: Optional[str] = None
    state_manager = getattr(server_module, "state_manager", None)
    if state_manager and hasattr(state_manager, "set_current_project"):
        authoritative_scope = resolve_authoritative_write_scope(
            context=execution_context,
            agent_session_id=None,
        )
        try:
            await state_manager.set_current_project(
                project_name,
                project,
                agent_id=agent_id,
                session_id=authoritative_scope.get("authoritative_session_id"),
                resolved_scope=authoritative_scope.get("resolved_scope"),
                mirror_global=False,
            )
        except Exception as exc:  # pragma: no cover - defensive state sync
            reload_warning = (
                f"Registration persisted for '{doc_name}', but context reload failed: {exc}"
            )
            logger.warning(reload_warning)

    try:
        registry_call = project_registry.record_doc_update(
            project_name=project_name,
            doc=doc_name,
            action="auto_register",
            after_hash=doc_hash,
        )
        if inspect.isawaitable(registry_call):
            await registry_call
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to update ProjectRegistry for '%s': %s", doc_name, exc)

    try:
        await append_entry(
            message=f"Auto-registered document: {doc_name} ({doc_path.name})",
            status="info",
            agent="manage_docs",
            meta={
                "action": "auto_register",
                "doc": doc_name,
                "doc_name": doc_name,
                "path": str(doc_path),
                "hash": doc_hash[:8],
            },
            format="structured",
        )
    except Exception as exc:  # pragma: no cover - non-fatal logging path
        logger.warning("Failed to log auto-registration event: %s", exc)

    return reload_warning


async def handle_manage_docs_request(
    *,
    action: str,
    doc_category: str,
    section: Optional[str],
    content: Optional[str],
    patch: Optional[str],
    patch_source_hash: Optional[str],
    edit: Optional[Dict[str, Any] | str],
    patch_mode: Optional[str],
    start_line: Optional[int],
    end_line: Optional[int],
    template: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    doc_name: Optional[str],
    target_dir: Optional[str],
    project: Optional[str],
    state_snapshot: Dict[str, Any],
    helper: LoggingToolMixin,
    context: Optional[LoggingContext] = None,
    server_module: Any,
    append_entry: Callable[..., Awaitable[Any]],
    project_registry: Any,
    logger: logging.Logger,
    handle_special_document_creation: Callable[..., Awaitable[Dict[str, Any]]],
    get_or_create_storage_project: Callable[..., Awaitable[Any]],
    get_index_updater_for_path: Callable[[Path, Path, Path, str], Optional[Callable[[], Awaitable[None]]]],
    auto_register_document: Callable[[Dict[str, Any], str], Awaitable[bool]],
    valid_actions: set[str] = VALID_ACTIONS,
    action_router: Dict[str, str] = ACTION_ROUTER,
) -> Dict[str, Any]:
    """Execute manage_docs runtime flow after thin-router argument collection."""
    try:
        healed_params, _, healing_messages = healing_shared.heal_manage_docs_parameters(
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
            valid_actions=valid_actions,
        )

        action = healed_params["action"]
        doc_category = healed_params["doc_category"]
        section = healed_params["section"]
        content = healed_params["content"]
        patch = healed_params["patch"]
        patch_source_hash = healed_params["patch_source_hash"]
        edit = healed_params["edit"]
        patch_mode = healed_params["patch_mode"]
        start_line = healed_params["start_line"]
        end_line = healed_params["end_line"]
        template = healed_params["template"]
        metadata = healed_params["metadata"]
        dry_run = healed_params["dry_run"]
        doc_name = healed_params["doc_name"]
        target_dir = healed_params["target_dir"]
    except Exception as healing_error:
        return helper.error_response(
            "manage_docs parameter healing failed; no changes applied.",
            suggestion="Verify action/doc/section parameters and retry. For edits, prefer action='apply_patch'.",
            extra={"error_detail": str(healing_error)},
        )

    deprecation_warning: Optional[str] = None

    if healed_params.get("invalid_action"):
        return helper.error_response(
            f"Invalid manage_docs action '{action}'.",
            suggestion="Use action='apply_patch' for edits, 'replace_section' only for initial scaffolding.",
            extra={
                "allowed_actions": sorted(
                    {
                        "create",
                        "replace_section",
                        "append",
                        "status_update",
                        "apply_patch",
                        "replace_range",
                        "replace_text",
                        "normalize_headers",
                        "generate_toc",
                        "list_sections",
                        "list_checklist_items",
                        "preview_reconciliation",
                        "batch",
                        "validate_crosslinks",
                        "search",
                    }
                ),
                "healing_messages": healing_messages,
            },
        )

    if action == "apply_patch" and healed_params.get("patch_mode_invalid"):
        return helper.error_response(
            "Invalid patch_mode; expected 'structured' or 'unified'.",
            suggestion="Set patch_mode to 'structured' for edit payloads or 'unified' for diff patches.",
            extra={
                "allowed_patch_modes": ["structured", "unified"],
                "received_patch_mode": patch_mode,
                "healing_messages": healing_messages,
            },
        )

    scaffold_flag = False
    if isinstance(metadata, dict):
        raw_scaffold = metadata.get("scaffold")
        if isinstance(raw_scaffold, bool):
            scaffold_flag = raw_scaffold
        elif isinstance(raw_scaffold, str):
            scaffold_flag = raw_scaffold.strip().lower() in {"true", "1", "yes"}

    if project is not None:
        project = normalize_project_input(project)

    if context is not None and project is not None:
        try:
            context = await helper.prepare_context(
                tool_name="manage_docs",
                agent_id=None,
                explicit_project=project,
                require_project=True,
                state_snapshot=state_snapshot,
                reminder_variables={"action": action, "scaffold": scaffold_flag},
                recovery_mode="none",
            )
        except ProjectResolutionError as exc:
            payload = helper.translate_project_error(exc)
            payload.setdefault("suggestion", "Invoke set_project before managing docs.")
            payload.setdefault("reminders", [])
            return payload
    elif context is None:
        try:
            context = await helper.prepare_context(
                tool_name="manage_docs",
                agent_id=None,
                explicit_project=project,
                require_project=True,
                state_snapshot=state_snapshot,
                reminder_variables={"action": action, "scaffold": scaffold_flag},
                recovery_mode="none",
            )
        except ProjectResolutionError as exc:
            payload = helper.translate_project_error(exc)
            payload.setdefault("suggestion", "Invoke set_project before managing docs.")
            payload.setdefault("reminders", [])
            return payload

    active_project = context.project or {}
    original_doc_name = doc_name
    doc_name = resolve_registered_doc_key(active_project, doc_name) if doc_name else doc_name
    if original_doc_name and doc_name and original_doc_name != doc_name:
        logger.info("Canonicalized doc reference '%s' -> '%s'", original_doc_name, doc_name)

    agent_identity = server_module.get_agent_identity()
    agent_id = "Scribe"
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    backend = server_module.storage_backend

    runtime_warnings: list[str] = []
    execution_context = None
    if hasattr(server_module, "get_execution_context"):
        try:
            execution_context = server_module.get_execution_context()
        except Exception:
            execution_context = None
    if action in _READ_ONLY_REGISTRATION_GATED_ACTIONS and doc_name:
        logger.debug("Skipping auto-registration for read-only action '%s' on '%s'", action, doc_name)

    if action in _MUTATION_ACTIONS and doc_category in _CUSTOM_DOC_TYPES and doc_name:
        resolved_path = utils_shared.resolve_custom_doc_path(
            project=active_project,
            doc_category=doc_category,
            doc_name=doc_name,
        )
        if resolved_path:
            logger.info("Resolved custom document: %s", resolved_path)
            if not resolved_path.exists():
                error_payload = helper.error_response(
                    f"Custom document '{doc_name}' resolved to a missing file",
                    suggestion="Ensure the file exists before running mutation actions.",
                    extra={"doc_name": doc_name, "resolved_path": str(resolved_path)},
                )
                return helper.apply_context_payload(error_payload, context)

            docs_mapping = active_project.get("docs", {}) or {}
            needs_registration = doc_name not in docs_mapping or doc_category not in docs_mapping
            if needs_registration and dry_run:
                active_project = active_project.copy()
                staged_docs = dict(active_project.get("docs", {}) or {})
                staged_docs[doc_name] = str(resolved_path)
                staged_docs[doc_category] = str(resolved_path)
                active_project["docs"] = staged_docs
                runtime_warnings.append(
                    f"dry_run: would register '{doc_name}' and '{doc_category}' to '{resolved_path}' before mutation."
                )
            elif needs_registration:
                for registration_key in (doc_name, doc_category):
                    if registration_key in docs_mapping:
                        continue
                    reload_warning = await register_document_path(
                        active_project,
                        registration_key,
                        resolved_path,
                        server_module=server_module,
                        project_registry=project_registry,
                        append_entry=append_entry,
                        logger=logger,
                        execution_context=execution_context,
                        agent_id=str(agent_id),
                    )
                    if reload_warning:
                        runtime_warnings.append(reload_warning)
                try:
                    context = await helper.prepare_context(
                        tool_name="manage_docs",
                        agent_id=None,
                        require_project=True,
                        state_snapshot=state_snapshot,
                        reminder_variables={"action": action, "scaffold": scaffold_flag},
                    )
                    active_project = context.project or active_project
                except Exception as reload_error:
                    runtime_warnings.append(
                        f"Custom document registration persisted, but context reload failed: {reload_error}"
                    )
                    logger.warning(runtime_warnings[-1])
        else:
            project_slug = slugify_project_name(active_project.get("name", "<project>"))
            error_payload = helper.error_response(
                f"Custom document '{doc_name}' not found",
                suggestion=(
                    f"Ensure document was created with create_{doc_category}_doc action. "
                    f"Check doc_name spelling and verify the document exists. "
                    f"For research docs: check .scribe/docs/dev_plans/{project_slug}/research/ "
                    f"For bug reports: check docs/bugs/<category>/<date>_{doc_name}/"
                ),
                extra={
                    "doc_type": doc_category,
                    "doc_name": doc_name,
                    "searched_in": str(Path(active_project.get("progress_log")).parent)
                    if active_project.get("progress_log")
                    else "unknown",
                    "project_root": str(active_project.get("root")),
                },
            )
            return helper.apply_context_payload(error_payload, context)
    elif action in _MUTATION_ACTIONS and doc_name:
        docs = active_project.get("docs", {})
        if doc_name not in docs:
            logger.info("Document '%s' not registered, attempting auto-registration...", doc_name)
            if dry_run:
                runtime_warnings.append(
                    f"dry_run: would auto-register '{doc_name}' before executing mutation action '{action}'."
                )
            try:
                if not dry_run:
                    await auto_register_document(active_project, doc_name)
                    try:
                        context = await helper.prepare_context(
                            tool_name="manage_docs",
                            agent_id=None,
                            require_project=True,
                            state_snapshot=state_snapshot,
                            reminder_variables={"action": action, "scaffold": scaffold_flag},
                        )
                        active_project = context.project or {}
                        logger.info(
                            "Successfully auto-registered and reloaded project context for '%s'",
                            doc_name,
                        )
                    except Exception as reload_error:
                        warning = (
                            "Auto-registration succeeded but context reload failed: "
                            f"{reload_error}"
                        )
                        runtime_warnings.append(warning)
                        logger.warning(warning)
            except Exception as exc:
                error_payload = helper.error_response(
                    f"Auto-registration failed for document '{doc_name}'",
                    suggestion=(
                        f"Ensure the file exists or use 'generate_doc_templates' to create it. "
                        f"Error: {str(exc)}"
                    ),
                    extra={"doc_name": doc_name, "auto_registration_error": str(exc)},
                )
                return helper.apply_context_payload(error_payload, context)

    metadata_mapping = metadata if isinstance(metadata, dict) else None

    # For replace_range called via the MCP tool surface, default to file-relative
    # line numbers so that agents using read_file line numbers get correct results.
    # The internal API (apply_doc_change) defaults to body-relative for backwards
    # compatibility; this injection bridges the gap.
    if action == "replace_range":
        if metadata_mapping is None:
            metadata_mapping = {}
        if "line_reference" not in metadata_mapping:
            metadata_mapping["line_reference"] = "file"

    action, create_response = await create_actions.normalize_or_handle_create_action(
        action=action,
        metadata=metadata_mapping,
        doc_name=doc_name,
        target_dir=target_dir,
        content=content,
        dry_run=dry_run,
        agent_id=agent_id,
        project=active_project,
        storage_backend=backend,
        helper=helper,
        context=context,
        handle_special_document_creation=handle_special_document_creation,
        deprecation_warning=deprecation_warning,
    )
    if create_response is not None:
        return create_response

    route_key = action_router.get(action)
    if route_key is None:
        return helper.apply_context_payload({"ok": False, "error": f"Unsupported action '{action}'"}, context)

    action_kwargs = {
        "action": action,
        "project": active_project,
        "doc_name": doc_name,
        "doc_category": doc_category,
        "section": section,
        "content": content,
        "patch": patch,
        "patch_source_hash": patch_source_hash,
        "edit": edit,
        "patch_mode": patch_mode,
        "start_line": start_line,
        "end_line": end_line,
        "template": template,
        "metadata": metadata_mapping,
        "dry_run": dry_run,
        "backend": backend,
        "agent_id": agent_id,
        "helper": helper,
        "context": context,
        "deprecation_warning": deprecation_warning,
        "apply_doc_change": apply_doc_change,
        "get_or_create_storage_project": get_or_create_storage_project,
        "append_entry": append_entry,
        "normalize_metadata_with_healing": healing_shared.normalize_metadata_with_healing,
        "index_doc_for_vector": indexing_shared.index_doc_for_vector,
        "vector_indexing_enabled": indexing_shared.vector_indexing_enabled,
        "get_index_updater_for_path": get_index_updater_for_path,
        "project_registry": project_registry,
        "server_module": server_module,
        "logger": logger,
    }

    if route_key == "query":
        response = await query_actions.handle_query_actions(
            action=action,
            project=active_project,
            doc_name=doc_name,
            metadata=metadata_mapping,
            helper=helper,
            context=context,
        )
    elif route_key == "search":
        response = await search_actions.handle_search_action(
            action=action,
            project=active_project,
            doc_name=doc_name,
            metadata=metadata_mapping,
            helper=helper,
            context=context,
        )
    elif route_key == "query_transform":
        response = await query_actions.handle_query_transform_actions(
            action=action,
            action_kwargs=action_kwargs,
            handle_edit_action=edit_actions.handle_edit_action,
        )
    elif route_key == "append":
        response = await append_actions.handle_append_action(**action_kwargs)
    elif route_key == "status":
        response = await status_actions.handle_status_action(**action_kwargs)
    elif route_key == "edit":
        response = await edit_actions.handle_edit_action(**action_kwargs)
    elif route_key == "batch":
        response = await batch_actions.handle_batch_action(
            action=action,
            project=active_project,
            metadata=metadata_mapping,
            dry_run=dry_run,
            helper=helper,
            context=context,
        )
    else:
        return helper.apply_context_payload(
            {
                "ok": False,
                "error": f"ACTION_ROUTER misconfigured for action '{action}'",
                "route_key": route_key,
            },
            context,
        )

    if response is not None:
        if runtime_warnings and isinstance(response, dict) and response.get("ok") is not False:
            response.setdefault("warnings", []).extend(runtime_warnings)
        return response

    return helper.apply_context_payload(
        {"ok": False, "error": f"No handler consumed action '{action}'", "route_key": route_key},
        context,
    )
