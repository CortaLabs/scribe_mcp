"""Create-action routing helpers for manage_docs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from scribe_mcp.config.repo_config import resolve_create_doc_type_config
from scribe_mcp.templates import template_root

_CREATE_DOC_TYPE_ACTIONS = {
    "research": "create_research_doc",
    "bug": "create_bug_report",
    "security": "create_security_report",
    "review": "create_review_report",
    "agent_card": "create_agent_report_card",
    "spec": "create_doc",
}

_SPECIAL_CREATE_ACTIONS = set(_CREATE_DOC_TYPE_ACTIONS.values())
_SPECIAL_DOC_TYPES = {"research", "bug", "security", "review", "agent_card"}
def _builtin_template_roots() -> list[Path]:
    return [template_root(), template_root() / "documents"]


def _builtin_template_options() -> list[str]:
    options = set()
    for root in _builtin_template_roots():
        if root.exists():
            options.update(path.stem for path in root.glob("*.md"))
    return sorted(options)


def _template_resolution_diagnostic(
    *,
    requested_template: str,
    requested_doc_type: str,
    resolved_doc_type: str,
    config_source: Optional[str],
) -> Dict[str, Any]:
    return {
        "failure_kind": "template_resolution",
        "registration_attempted": False,
        "requested_template": requested_template,
        "requested_doc_type": requested_doc_type,
        "resolved_doc_type": resolved_doc_type,
        "config_source": config_source or "built_in",
        "searched_template_roots": [str(root) for root in _builtin_template_roots()],
        "available_templates": _builtin_template_options(),
        "available_doc_types": ["custom", "spec", *sorted(_SPECIAL_DOC_TYPES)],
        "recommended_action": (
            "Use metadata.doc_type='custom' with content/body for a custom managed doc, "
            "or configure doc_types.create_templates to one of available_templates."
        ),
    }


def classify_create_doc_type(metadata: Optional[Dict[str, Any]]) -> str:
    """Return normalized doc_type for create intent routing."""
    if not isinstance(metadata, dict):
        return "custom"
    value = str(metadata.get("doc_type", "custom") or "custom").strip().lower()
    return value or "custom"


def _resolve_doc_type_from_config(
    requested_doc_type: str,
    project_root: Optional[str],
) -> tuple[str, str, Optional[str], list[str], Optional[str], Optional[str]]:
    if not project_root:
        return requested_doc_type, requested_doc_type, None, [], None, None
    try:
        from scribe_mcp.config.repo_config import RepoDiscovery

        repo_config = RepoDiscovery.load_config(Path(project_root), seed_if_missing=False)
    except Exception as exc:
        return requested_doc_type, requested_doc_type, None, [f"Failed loading repo config for doc_types config: {exc}"], None, None

    resolved_config = resolve_create_doc_type_config(repo_config)
    alias_target = resolved_config.aliases.get(requested_doc_type)
    template_name = resolved_config.templates.get(requested_doc_type)
    resolved = alias_target or requested_doc_type
    if alias_target:
        config_source = f"{resolved_config.source_path}.create_aliases"
    elif template_name:
        config_source = f"{resolved_config.source_path}.create_templates"
    else:
        config_source = None
    return requested_doc_type, resolved, template_name, resolved_config.warnings, config_source, resolved_config.source_path


def _validate_configured_template(template_name: str) -> Optional[str]:
    normalized = str(template_name or "").strip()
    if not normalized:
        return "Configured template is empty."
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        return "Configured template must be a template name, not a path."
    candidate = template_root() / f"{normalized}.md"
    if not candidate.exists():
        return f"Configured template '{normalized}' was not found at {candidate}."
    return None


async def normalize_or_handle_create_action(
    *,
    action: str,
    metadata: Optional[Dict[str, Any]],
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    dry_run: bool,
    agent_id: str,
    project: Dict[str, Any],
    storage_backend: Any,
    helper: Any,
    context: Any,
    handle_special_document_creation: Any,
    deprecation_warning: Optional[str] = None,
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Normalize create action and dispatch special create handlers when needed."""
    if action == "create":
        requested_doc_type = classify_create_doc_type(metadata)
        _, doc_type, resolved_template, config_warnings, config_source, _ = _resolve_doc_type_from_config(
            requested_doc_type=requested_doc_type,
            project_root=project.get("root") if isinstance(project, dict) else None,
        )

        if metadata is not None and isinstance(metadata, dict):
            metadata["_requested_doc_type"] = requested_doc_type
            metadata["_resolved_doc_type"] = doc_type
            metadata["_resolved_handler"] = _CREATE_DOC_TYPE_ACTIONS.get(str(doc_type), "create_doc")
            metadata["_config_source"] = config_source or "built_in"
            if resolved_template:
                metadata.setdefault("template", resolved_template)
            if config_warnings:
                metadata.setdefault("_create_config_warnings", [])
                metadata["_create_config_warnings"].extend(config_warnings)

        if resolved_template:
            template_error = _validate_configured_template(resolved_template)
            if template_error:
                template_resolution = _template_resolution_diagnostic(
                    requested_template=resolved_template,
                    requested_doc_type=requested_doc_type,
                    resolved_doc_type=doc_type,
                    config_source=config_source,
                )
                error = helper.error_response(
                    f"Invalid configured template for doc_type '{requested_doc_type}'.",
                    suggestion=(
                        "Template resolution failed before doc registration. Update repo config at "
                        "doc_types.create_templates with a valid template name under templates/documents, "
                        "or use metadata.doc_type='custom' with content/body."
                    ),
                )
                error["requested_doc_type"] = requested_doc_type
                error["resolved_doc_type"] = doc_type
                error["resolved_handler"] = "create_doc"
                error["config_source"] = config_source or "built_in"
                error["template_resolution"] = template_resolution
                error.setdefault("warnings", []).append(template_error)
                return action, error

        if doc_type == "custom" or resolved_template:
            return "create_doc", None

        mapped_action = _CREATE_DOC_TYPE_ACTIONS.get(str(doc_type))
        if not mapped_action:
            error = helper.error_response(
                f"Unknown doc_type: {doc_type}",
                suggestion=(
                    "Valid doc_types: custom, spec, "
                    + ", ".join(sorted(_SPECIAL_DOC_TYPES))
                ),
            )
            error["requested_doc_type"] = requested_doc_type
            error["resolved_doc_type"] = doc_type
            error["resolved_handler"] = "unresolved"
            error["config_source"] = config_source or "built_in"
            error["template_resolution"] = {
                "failure_kind": "doc_type_registration",
                "registration_attempted": False,
                "available_doc_types": ["custom", "spec", *sorted(_SPECIAL_DOC_TYPES)],
                "recommended_action": (
                    "Use metadata.doc_type='custom' for a custom managed doc, or choose one "
                    "of available_doc_types."
                ),
            }
            if config_warnings:
                error["warnings"] = config_warnings
            return action, error
        if mapped_action == "create_doc":
            return mapped_action, None

        response = await handle_special_document_creation(
            project,
            action=mapped_action,
            doc_name=doc_name,
            target_dir=target_dir,
            content=content,
            metadata=metadata,
            dry_run=dry_run,
            agent_id=agent_id,
            storage_backend=storage_backend,
            helper=helper,
            context=context,
        )
        response["requested_doc_type"] = requested_doc_type
        response["resolved_doc_type"] = doc_type
        response["resolved_handler"] = mapped_action
        response["config_source"] = config_source or "built_in"
        if config_warnings:
            response.setdefault("warnings", [])
            response["warnings"].extend(config_warnings)
        return action, response

    if action in _SPECIAL_CREATE_ACTIONS:
        response = await handle_special_document_creation(
            project,
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
        )
        if deprecation_warning:
            response["deprecated"] = deprecation_warning
        return action, response

    return action, None
