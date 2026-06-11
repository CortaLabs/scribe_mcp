"""Edit/status/append action helper for manage_docs decomposition."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp.doc_management import errors as doc_errors
from scribe_mcp.doc_management.boundary_guidance import (
    build_manage_docs_boundary_guidance,
    is_manage_docs_boundary_error,
)
from scribe_mcp.doc_management.scaffold_quality import build_research_index_hygiene_warnings
from scribe_mcp.tools.agent_project_utils import resolve_authoritative_write_scope
from scribe_mcp.utils.frontmatter import parse_frontmatter


_ALLOWED_DOC_ACTIONS = {
    "replace_section",
    "append",
    "status_update",
    "frontmatter_update",
    "apply_patch",
    "replace_range",
    "replace_text",
    "normalize_headers",
    "generate_toc",
    "validate_crosslinks",
}

_FRONTMATTER_INTENT_KEYS = {
    "frontmatter",
    "status",
    "summary",
    "owners",
    "tags",
    "related_docs",
    "maintained_by",
}

_DEFAULT_READINESS_VALUES = {"ready", "done", "complete", "finished"}
_SIDE_EFFECT_TIMEOUT_SECONDS = 5.0


def _readiness_values(metadata: Optional[Dict[str, Any]]) -> set[str]:
    if not isinstance(metadata, dict):
        return set(_DEFAULT_READINESS_VALUES)
    quality_cfg = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
    configured = quality_cfg.get("readiness_values") if isinstance(quality_cfg, dict) else None
    if not isinstance(configured, list):
        return set(_DEFAULT_READINESS_VALUES)
    return {str(v).strip().lower() for v in configured if str(v).strip()}


def _is_readiness_claim(text: str, metadata: Optional[Dict[str, Any]]) -> bool:
    parsed = parse_frontmatter(text)
    status = str(parsed.frontmatter_data.get("status", "")).strip().lower()
    return status in _readiness_values(metadata)


def _readiness_blockers(warnings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [w for w in warnings if isinstance(w, dict) and bool(w.get("blocking"))]


def _status_intent_mismatch_response(
    metadata: Optional[Dict[str, Any]],
    *,
    doc_name: Optional[str],
    doc_category: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(metadata, dict):
        return None
    normalized_doc_name = str(doc_name or "").strip().lower()
    normalized_doc_category = str(doc_category or "").strip().lower()
    if normalized_doc_name == "checklist" or normalized_doc_category == "checklist":
        return None
    has_frontmatter_payload = isinstance(metadata.get("frontmatter"), dict)
    has_frontmatter_intent_key = any(key in metadata for key in _FRONTMATTER_INTENT_KEYS)
    if not (has_frontmatter_payload or has_frontmatter_intent_key):
        return None
    return {
        "ok": False,
        "code": "DOC_STATUS_INTENT_MISMATCH",
        "error": (
            "status_update is checklist-only. For narrative-doc frontmatter status/metadata changes, "
            "use manage_docs(action=\"frontmatter_update\", metadata={...}) or metadata.frontmatter."
        ),
    }


def _strip_unexpected_prefix(message: str) -> str:
    prefix = "Unexpected error: "
    if str(message).startswith(prefix):
        return str(message)[len(prefix) :]
    return str(message)


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
    execution_context: Any,
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
        if action == "status_update":
            mismatch = _status_intent_mismatch_response(
                metadata,
                doc_name=doc_name,
                doc_category=doc_category,
            )
            if mismatch is not None:
                return helper.apply_context_payload(mismatch, context)
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            near = doc_errors.find_near_misses(str(doc_name or ""), sorted(allowed_docs))
            response = {
                "ok": False,
                "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered",
                "code": "DOC_NOT_FOUND",
                "remediation": (
                    (f"Did you mean '{near[0]}'? " if near else "")
                    + "Registered docs for this project: "
                    + (", ".join(sorted(allowed_docs)) or "(none)")
                    + ". Use manage_docs(action='create', ...) to create a new doc, or "
                    "metadata.register_existing=true to register an existing file."
                ),
                "alternatives": near or sorted(allowed_docs)[:5],
            }
            return helper.apply_context_payload(response, context)

    if action == "create_doc" and isinstance(metadata, dict):
        if not template and isinstance(metadata.get("template"), str):
            template = str(metadata.get("template") or "").strip() or None
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
                    authoritative_scope = resolve_authoritative_write_scope(
                        context=execution_context,
                        agent_session_id=None,
                    )
                    authoritative_session_id = authoritative_scope.get("authoritative_session_id")
                    if not authoritative_session_id:
                        raise ValueError(
                            "Cannot establish authoritative session binding for register_existing."
                        )
                    await server_module.state_manager.set_current_project(
                        project.get("name"),
                        project,
                        agent_id=agent_id,
                        session_id=authoritative_session_id,
                        resolved_scope=authoritative_scope.get("resolved_scope"),
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

    if action in _ALLOWED_DOC_ACTIONS and action != "status_update":
        try:
            preview_change = await apply_doc_change(
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
                dry_run=True,
            )
        except Exception as exc:
            return helper.apply_context_payload(
                doc_errors.attach_remediation({"ok": False, "error": str(exc)}, exc),
                context,
            )

        preview_warnings = []
        if isinstance(preview_change.extra, dict):
            preview_warnings = preview_change.extra.get("scaffold_quality_warnings") or []
        if _is_readiness_claim(preview_change.content_written, metadata):
            blockers = _readiness_blockers(preview_warnings)
            if blockers:
                response = {
                    "ok": False,
                    "code": "DOC_NOT_DONE_SCAFFOLD_QUALITY",
                    "error": "Readiness claim blocked: scaffold residue remains. Repair listed warnings before marking done.",
                    "doc_name": doc_name,
                    "action": action,
                    "readiness_blockers": [
                        {
                            "code": b.get("code"),
                            "location": b.get("location"),
                            "excerpt": b.get("excerpt"),
                            "message": b.get("message"),
                            "suggested_repair": b.get("suggested_repair"),
                        }
                        for b in blockers
                    ],
                    "quality_warnings": preview_warnings,
                }
                if not dry_run:
                    try:
                        await append_entry(
                            message=f"Blocked readiness attempt for {doc_name}",
                            status="warn",
                            meta={
                                "doc": doc_name,
                                "doc_name": doc_name,
                                "section": section or "",
                                "action": action,
                                "reason_code": "DOC_NOT_DONE_SCAFFOLD_QUALITY",
                                "blocker_codes": [b.get("code") for b in blockers],
                            },
                            agent=agent_id,
                            log_type="doc_updates",
                            format="structured",
                        )
                    except Exception:
                        pass
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
        return helper.apply_context_payload(
            doc_errors.attach_remediation({"ok": False, "error": str(exc)}, exc),
            context,
        )

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
                # "doc" satisfies the doc_updates metadata_requirements contract
                # (log_config.json); "doc_name" retained for downstream consumers.
                "doc": doc_name,
                "doc_name": doc_name,
                "doc_category": doc_category,
                "section": section or "",
                "action": action,
                "sha_after": change.after_hash,
            }
        )
        try:
            await asyncio.wait_for(
                append_entry(
                    message=f"Doc update [{doc_name}] {section or 'full'} via {action}",
                    status="info",
                    meta=log_meta,
                    agent=agent_id,
                    log_type="doc_updates",
                    format="structured",
                ),
                timeout=_SIDE_EFFECT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            log_error = str(exc)

        if change.success and change.path:
            try:
                await asyncio.wait_for(
                    index_doc_for_vector(
                        project=project,
                        doc_name=doc_name,
                        change_path=Path(change.path),
                        after_hash=change.after_hash or "",
                        agent_id=agent_id or "unknown",
                        metadata=metadata if isinstance(metadata, dict) else None,
                    ),
                    timeout=_SIDE_EFFECT_TIMEOUT_SECONDS,
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
        structured_warnings = change.extra.get("scaffold_quality_warnings")
        if isinstance(structured_warnings, list) and structured_warnings:
            response["quality_warnings"] = structured_warnings
    canonical_doc_name = ""
    if isinstance(metadata, dict):
        canonical_doc_name = str(metadata.get("register_as") or metadata.get("doc_name") or doc_name or "").strip()
    if not canonical_doc_name:
        canonical_doc_name = str(doc_name or "").strip()
    response["requested_doc_name"] = doc_name
    response["canonical_doc_name"] = canonical_doc_name or None
    response["final_path"] = response.get("path") or None
    if isinstance(metadata, dict):
        requested_doc_type = metadata.get("_requested_doc_type")
        resolved_doc_type = metadata.get("_resolved_doc_type")
        resolved_handler = metadata.get("_resolved_handler")
        config_source = metadata.get("_config_source")
        if requested_doc_type is not None:
            response["requested_doc_type"] = requested_doc_type
        if resolved_doc_type is not None:
            response["resolved_doc_type"] = resolved_doc_type
        if resolved_handler is not None:
            response["resolved_handler"] = resolved_handler
        if config_source is not None:
            response["config_source"] = config_source
        create_warnings = metadata.get("_create_config_warnings")
        if isinstance(create_warnings, list) and create_warnings:
            response.setdefault("warnings", [])
            response["warnings"].extend(str(item) for item in create_warnings)

    try:
        changed_path = Path(change.path) if change.path else None
        if changed_path:
            docs_dir_path = Path(str(project.get("docs_dir", ""))).expanduser()
            canonical_research_dir = (docs_dir_path / "research").resolve() if str(docs_dir_path) else None
            research_dir = None
            if canonical_research_dir:
                try:
                    changed_path.resolve().relative_to(canonical_research_dir)
                    research_dir = canonical_research_dir
                except ValueError:
                    pass
            if research_dir is None and changed_path.parent.name == "research":
                research_dir = changed_path.parent.resolve()
            if research_dir and research_dir.exists():
                research_warnings = build_research_index_hygiene_warnings(
                    research_dir=research_dir,
                    changed_path=changed_path,
                    canonical_research_dir=canonical_research_dir,
                )
                if research_warnings:
                    response.setdefault("research_hygiene_warnings", []).extend(research_warnings)
    except Exception:
        pass
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
            authoritative_scope = resolve_authoritative_write_scope(
                context=execution_context,
                agent_session_id=None,
            )
            authoritative_session_id = authoritative_scope.get("authoritative_session_id")
            if not authoritative_session_id:
                return helper.apply_context_payload(
                    helper.error_response(
                        "Cannot establish authoritative session binding for register_doc.",
                        extra={"path": str(change.path)},
                    ),
                    context,
                )
            try:
                await server_module.state_manager.set_current_project(
                    project.get("name"),
                    project,
                    agent_id=agent_id,
                    session_id=authoritative_session_id,
                    resolved_scope=authoritative_scope.get("resolved_scope"),
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
        normalized_error = _strip_unexpected_prefix(change.error_message)
        response["error"] = normalized_error
        if is_manage_docs_boundary_error(normalized_error):
            rejected_target = None
            if isinstance(metadata, dict):
                rejected_target = metadata.get("target_dir")
            response["boundary_guidance"] = build_manage_docs_boundary_guidance(
                project,
                rejected_target=str(rejected_target) if rejected_target else None,
            )
            response["suggestion"] = (
                "Choose a target_dir inside the active project root, or omit target_dir "
                "to use the project docs_dir."
            )

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
