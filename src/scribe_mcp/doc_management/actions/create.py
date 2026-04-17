"""Create-action routing helpers for manage_docs."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


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


def classify_create_doc_type(metadata: Optional[Dict[str, Any]]) -> str:
    """Return normalized doc_type for create intent routing."""
    if not isinstance(metadata, dict):
        return "custom"
    value = str(metadata.get("doc_type", "custom") or "custom").strip().lower()
    return value or "custom"


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
        doc_type = classify_create_doc_type(metadata)
        if doc_type == "custom":
            return "create_doc", None

        mapped_action = _CREATE_DOC_TYPE_ACTIONS.get(str(doc_type))
        if not mapped_action:
            return action, helper.error_response(
                f"Unknown doc_type: {doc_type}",
                suggestion=(
                    "Valid doc_types: custom, spec, "
                    + ", ".join(sorted(_SPECIAL_DOC_TYPES))
                ),
            )
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
