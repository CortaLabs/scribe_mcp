"""Parameter-healing helpers shared by manage_docs flows."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from scribe_mcp.shared.logging_utils import coerce_metadata_mapping
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector


def normalize_metadata_with_healing(
    metadata: Optional[Dict[str, Any] | str],
) -> Tuple[Dict[str, Any], bool, List[str]]:
    """Normalize metadata and return (mapping, healed, messages)."""
    healing_messages: List[str] = []
    healing_applied = False

    try:
        healed_metadata = BulletproofParameterCorrector.correct_metadata_parameter(metadata)
        if healed_metadata != metadata:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected metadata parameter from {type(metadata).__name__} to valid dict"
            )
        metadata = healed_metadata
    except Exception as healing_error:
        healing_messages.append(
            f"Metadata healing failed: {str(healing_error)}, using fallback"
        )
        metadata = {}

    mapping, error = coerce_metadata_mapping(metadata)
    if error:
        mapping.setdefault("meta_error", error)
        healing_messages.append(f"Metadata coercion warning: {error}")
        healing_applied = True

    return mapping, healing_applied, healing_messages


def heal_manage_docs_parameters(
    *,
    action: str,
    doc_category: str,
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
    target_dir: Optional[str] = None,
    valid_actions: Optional[Iterable[str]] = None,
) -> Tuple[dict, bool, List[str]]:
    """Heal manage_docs parameters with strict-but-explained normalization."""
    healing_messages: List[str] = []
    healing_applied = False
    invalid_action = False
    healed_params: Dict[str, Any] = {}

    action_set: Set[str] = set(valid_actions or [])
    original_action = action
    healed_action = str(original_action).strip() if original_action is not None else ""
    if action_set and healed_action not in action_set:
        invalid_action = True
        healing_applied = True
        healing_messages.append(
            f"Invalid action '{original_action}'. Use one of: {', '.join(sorted(action_set))}."
        )
    healed_params["action"] = healed_action
    healed_params["invalid_action"] = invalid_action

    original_doc_category = doc_category
    healed_doc_category = (
        str(original_doc_category).strip() if original_doc_category is not None else ""
    )
    if healed_doc_category != original_doc_category:
        healing_applied = True
        healing_messages.append(
            f"Auto-normalized doc_category from '{original_doc_category}' to '{healed_doc_category}'"
        )
    healed_params["doc_category"] = healed_doc_category

    if section is not None:
        original_section = section
        healed_section = str(section).strip()
        if healed_section != original_section:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected section from '{original_section}' to '{healed_section}'"
            )
        healed_params["section"] = healed_section
    else:
        healed_params["section"] = None

    if content is not None:
        original_content = content
        healed_content = str(content)
        if healed_content != original_content:
            healing_applied = True
            healing_messages.append("Auto-corrected content parameter to string type")
        healed_params["content"] = healed_content
    else:
        healed_params["content"] = None

    if patch is not None:
        original_patch = patch
        healed_patch = str(patch)
        if healed_patch != original_patch:
            healing_applied = True
            healing_messages.append("Auto-corrected patch parameter to string type")
        healed_params["patch"] = healed_patch
    else:
        healed_params["patch"] = None

    if patch_source_hash is not None:
        original_hash = patch_source_hash
        healed_hash = str(patch_source_hash).strip()
        if healed_hash != original_hash:
            healing_applied = True
            healing_messages.append(
                "Auto-corrected patch_source_hash parameter to string type"
            )
        healed_params["patch_source_hash"] = healed_hash
    else:
        healed_params["patch_source_hash"] = None

    if expected_anchor_sha256 is not None:
        original_anchor_hash = expected_anchor_sha256
        healed_anchor_hash = str(expected_anchor_sha256).strip()
        if healed_anchor_hash != original_anchor_hash:
            healing_applied = True
            healing_messages.append(
                "Auto-corrected expected_anchor_sha256 parameter to string type"
            )
        healed_params["expected_anchor_sha256"] = healed_anchor_hash
    else:
        healed_params["expected_anchor_sha256"] = None

    healed_params["edit"] = None
    if edit is not None:
        if isinstance(edit, str):
            try:
                healed_params["edit"] = json.loads(edit)
                healing_applied = True
                healing_messages.append("Auto-parsed edit JSON string into dict")
            except json.JSONDecodeError:
                healed_params["edit"] = None
                healing_applied = True
                healing_messages.append("Failed to parse edit JSON; ignoring edit payload")
        elif isinstance(edit, dict):
            healed_params["edit"] = edit
        else:
            healed_params["edit"] = None
            healing_applied = True
            healing_messages.append("Auto-corrected edit parameter to None")

    healed_params["patch_mode_invalid"] = False
    if patch_mode is not None:
        original_mode = patch_mode
        healed_mode = str(patch_mode).strip().lower()
        if healed_mode != original_mode:
            healing_applied = True
            healing_messages.append("Auto-corrected patch_mode parameter to string type")
        if healed_mode not in {"structured", "unified"}:
            healing_applied = True
            healed_params["patch_mode_invalid"] = True
            healing_messages.append("Invalid patch_mode; expected 'structured' or 'unified'")
        healed_params["patch_mode"] = healed_mode
    else:
        healed_params["patch_mode"] = None

    def _coerce_line_number(value: Optional[int], label: str) -> Optional[int]:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        try:
            coerced = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        healing_messages.append(f"Auto-corrected {label} to integer {coerced}")
        return coerced

    healed_params["start_line"] = _coerce_line_number(start_line, "start_line")
    healed_params["end_line"] = _coerce_line_number(end_line, "end_line")

    if template is not None:
        original_template = template
        healed_template = str(template).strip()
        if healed_template != original_template:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected template from '{original_template}' to '{healed_template}'"
            )
        healed_params["template"] = healed_template
    else:
        healed_params["template"] = None

    healed_metadata, metadata_healed, metadata_messages = normalize_metadata_with_healing(
        metadata
    )
    if metadata_healed:
        healing_applied = True
        healing_messages.extend(metadata_messages)
    healed_params["metadata"] = healed_metadata

    original_dry_run = dry_run
    healed_dry_run = bool(dry_run)
    if isinstance(dry_run, str):
        healed_dry_run = dry_run.lower() in ("true", "1", "yes")
        if healed_dry_run != original_dry_run:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected dry_run from '{dry_run}' to {healed_dry_run}"
            )
    healed_params["dry_run"] = healed_dry_run

    if doc_name is not None:
        original_doc_name = doc_name
        healed_doc_name = str(doc_name).strip()
        if healed_doc_name != original_doc_name:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected doc_name from '{original_doc_name}' to '{healed_doc_name}'"
            )
        healed_params["doc_name"] = healed_doc_name
    else:
        healed_params["doc_name"] = None

    if target_dir is not None:
        original_target_dir = target_dir
        healed_target_dir = str(target_dir).strip()
        if healed_target_dir != original_target_dir:
            healing_applied = True
            healing_messages.append(
                f"Auto-corrected target_dir from '{original_target_dir}' to '{healed_target_dir}'"
            )
        healed_params["target_dir"] = healed_target_dir
    else:
        healed_params["target_dir"] = None

    return healed_params, healing_applied, healing_messages


def add_healing_info_to_response(
    response: Dict[str, Any],
    healing_applied: bool,
    healing_messages: List[str],
) -> Dict[str, Any]:
    """Attach healing metadata to API responses."""
    if healing_applied and healing_messages:
        response["parameter_healing"] = {
            "applied": True,
            "messages": healing_messages,
            "message": "Parameters auto-corrected using Phase 1 exception healing",
        }
    return response
