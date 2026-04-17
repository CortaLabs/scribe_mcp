"""Edit/status/append action helper for manage_docs decomposition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp.utils.frontmatter import parse_frontmatter


_ALLOWED_DOC_ACTIONS = {
    "replace_section",
    "append",
    "status_update",
    "apply_patch",
    "replace_range",
    "replace_text",
    "normalize_headers",
    "generate_toc",
    "validate_crosslinks",
}


def _with_session_provenance(metadata: Optional[Dict[str, Any]], context: Any) -> Dict[str, Any]:
    enriched = dict(metadata or {})
    resolved_scope = getattr(context, "resolved_scope", None)
    provenance = {
        "session_id": str(getattr(context, "session_id", "") or ""),
        "stable_session_id": str(getattr(context, "stable_session_id", "") or ""),
        "transport_session_id": str(getattr(context, "transport_session_id", "") or ""),
        "agent_session_id": str(getattr(resolved_scope, "agent_session_id", "") or ""),
        "resolution_source": str(getattr(resolved_scope, "resolution_source", "") or ""),
        "trust_level": str(getattr(resolved_scope, "trust_level", "") or ""),
    }
    enriched["session_provenance"] = provenance
    return enriched


async def handle_edit_action(
    *,
    action: str,
    project: Dict[str, Any],
    doc_name: Optional[str],
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
    backend: Any,
    agent_id: str,
    helper: Any,
    context: Any,
    deprecation_warning: Optional[str],
    apply_doc_change: Any,
    get_or_create_storage_project: Any,
    append_entry: Any,
    normalize_metadata_with_healing: Any,
    index_doc_for_vector: Any,
    vector_indexing_enabled: Any,
    get_index_updater_for_path: Any,
    project_registry: Any,
    server_module: Any,
    logger: Any,
) -> Optional[Dict[str, Any]]:
    """Handle create_doc and document mutation actions when matched."""
    if action not in _ALLOWED_DOC_ACTIONS and action != "create_doc":
        return None

    if action in _ALLOWED_DOC_ACTIONS:
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return helper.apply_context_payload(response, context)

    if action == "create_doc" and isinstance(metadata, dict):
        register_existing = bool(metadata.get("register_existing"))
        if register_existing:
            register_key = metadata.get("register_as") or metadata.get("doc_name") or doc_name
            if not register_key:
                response = {
                    "ok": False,
                    "error": "register_existing requires metadata.register_as or metadata.doc_name",
                }
                return helper.apply_context_payload(response, context)
            try:
                from scribe_mcp.doc_management.manager import _resolve_create_doc_path

                doc_path = _resolve_create_doc_path(project, metadata, doc_name)
            except Exception as exc:
                response = {"ok": False, "error": f"register_existing failed to resolve path: {exc}"}
                return helper.apply_context_payload(response, context)
            if doc_path.exists():
                docs_mapping = dict(project.get("docs") or {})
                docs_mapping[str(register_key)] = str(doc_path)
                project["docs"] = docs_mapping
                registry_warning = ""
                try:
                    await server_module.state_manager.set_current_project(
                        project.get("name"),
                        project,
                        agent_id=agent_id,
                        mirror_global=False,
                    )
                    runtime_backend = getattr(server_module, "storage_backend", None)
                    if runtime_backend:
                        await runtime_backend.update_project_docs(project.get("name"), json.dumps(docs_mapping))
                except Exception as exc:
                    registry_warning = f"Registry update failed: {exc}"
                response: Dict[str, Any] = {
                    "ok": True,
                    "doc_name": doc_name,
                    "section": None,
                    "action": action,
                    "path": str(doc_path),
                    "dry_run": dry_run,
                    "diff": "",
                    "warning": "register_existing used; no content was written.",
                }
                if registry_warning:
                    response.setdefault("warnings", []).append(registry_warning)
                return helper.apply_context_payload(response, context)

    if not doc_name:
        response = {"ok": False, "error": f"Action '{action}' requires doc_name parameter"}
        return helper.apply_context_payload(response, context)

    try:
        change = await apply_doc_change(
            project,
            doc_name=doc_name,
            doc_category=doc_category,
            action=action,
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
        )
    except Exception as exc:
        return helper.apply_context_payload({"ok": False, "error": str(exc)}, context)

    doc_change_metadata = _with_session_provenance(metadata, context)

    if backend and not dry_run and action != "validate_crosslinks":
        try:
            storage_record = await get_or_create_storage_project(backend, project)
            await backend.record_doc_change(
                storage_record,
                doc=doc_name,
                section=section,
                action=action,
                agent=agent_id,
                metadata=doc_change_metadata,
                sha_before=change.before_hash,
                sha_after=change.after_hash,
            )
        except Exception as exc:
            logger.warning("Failed to record doc change in storage: %s", exc)
        else:
            try:
                project_name = project.get("name", "")
                if project_name:
                    project_registry.record_doc_update(
                        project_name,
                        doc_name=doc_name,
                        action=action,
                        before_hash=change.before_hash,
                        after_hash=change.after_hash,
                    )
            except Exception:
                pass

    log_error = None
    index_warning = None
    if not dry_run and action != "validate_crosslinks":
        healed_metadata, _, _ = normalize_metadata_with_healing(metadata)
        log_meta = healed_metadata
        log_meta.update(
            {
                "doc_name": doc_name,
                "doc_category": doc_category,
                "section": section or "",
                "action": action,
                "sha_after": change.after_hash,
            }
        )
        try:
            await append_entry(
                message=f"Doc update [{doc_name}] {section or 'full'} via {action}",
                status="info",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
                format="structured",
            )
        except Exception as exc:
            log_error = str(exc)

        if change.success and change.path:
            try:
                await index_doc_for_vector(
                    project=project,
                    doc_name=doc_name,
                    change_path=Path(change.path),
                    after_hash=change.after_hash or "",
                    agent_id=agent_id or "unknown",
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
            except Exception as exc:
                index_warning = str(exc)

            try:
                project_root = project.get("root")
                if isinstance(project_root, str):
                    project_root = Path(project_root)
                docs_dir_path = Path(project.get("docs_dir", ""))
                index_updater = get_index_updater_for_path(
                    file_path=Path(change.path),
                    project_root=project_root,
                    docs_dir=docs_dir_path,
                    agent_id=agent_id or "unknown",
                )
                if index_updater:
                    await index_updater()
            except Exception as exc:
                logger.warning("Failed to update index after edit: %s", exc)

    registry_warning = None
    response: Dict[str, Any] = {
        "ok": change.success,
        "action": action,
        "path": str(change.path) if change.success else "",
        "dry_run": dry_run,
        "diff": change.diff_preview,
    }
    if doc_name:
        response["doc_name"] = doc_name
    if section:
        response["section"] = section
    if change.success:
        response["hashes"] = {"before": change.before_hash, "after": change.after_hash}
    if change.extra:
        response["extra"] = change.extra
    if index_warning:
        response["index_warning"] = index_warning

    if action == "create_doc" and change.success and isinstance(metadata, dict):
        register_doc = metadata.get("register_doc")
        if register_doc is None:
            register_doc = True
        register_doc = bool(register_doc)
        register_key = metadata.get("register_as") or metadata.get("doc_name") or doc_name

        if register_doc and dry_run:
            response.setdefault("warnings", []).append(
                "register_doc skipped during dry_run; no project registry changes were applied."
            )
        elif register_doc:
            if not register_key:
                return helper.apply_context_payload(
                    helper.error_response("register_doc requires metadata.register_as or metadata.doc_name"),
                    context,
                )
            docs_mapping = dict(project.get("docs") or {})
            docs_mapping[str(register_key)] = str(change.path)
            project["docs"] = docs_mapping
            try:
                await server_module.state_manager.set_current_project(
                    project.get("name"),
                    project,
                    agent_id=agent_id,
                    mirror_global=False,
                )
                runtime_backend = getattr(server_module, "storage_backend", None)
                if runtime_backend:
                    await runtime_backend.update_project_docs(project.get("name"), json.dumps(docs_mapping))
            except Exception as exc:
                registry_warning = f"Registry update failed: {exc}"
            if metadata.get("register_doc") is None:
                response.setdefault("warnings", []).append(
                    "register_doc defaulted to true; set metadata.register_doc=false to skip registration."
                )

    if registry_warning:
        response.setdefault("warnings", []).append(registry_warning)
    if not change.success and change.error_message:
        response["error"] = change.error_message

    if not dry_run:
        response["verification_passed"] = change.verification_passed
        response["file_size_before"] = change.file_size_before
        response["file_size_after"] = change.file_size_after

    if log_error:
        response["log_warning"] = log_error

    include_full_preview = bool(isinstance(metadata, dict) and metadata.get("include_full_preview"))
    if dry_run and include_full_preview:
        preview_content = change.content_written
        include_frontmatter = bool(isinstance(metadata, dict) and metadata.get("include_frontmatter_preview"))
        if preview_content and not include_frontmatter:
            try:
                while True:
                    parsed_preview = parse_frontmatter(preview_content)
                    if not parsed_preview.has_frontmatter:
                        break
                    preview_content = parsed_preview.body
                    if not preview_content.lstrip().startswith("---"):
                        break
            except Exception:
                pass
        response["preview"] = preview_content

    if deprecation_warning:
        response["deprecated"] = deprecation_warning

    return helper.apply_context_payload(response, context)
