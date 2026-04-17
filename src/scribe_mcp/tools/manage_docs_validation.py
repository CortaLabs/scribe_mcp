"""Validation helpers expected by manage_docs enhancement tests.

This module intentionally provides a small, stable import surface used by tests:
  - ParameterValidationError
  - _validate_inputs
  - _validate_comparison_symbols
  - create_manage_docs_validator

Callers should import these helpers from this module directly; no Python
builtins are mutated at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


COMPARISON_REGEX = re.compile(r"\b\d+(?:\.\d+)?\s*(?:<=|>=|<|>)\s*\d+(?:\.\d+)?\b")
SUPPORTED_WORKFLOW_METADATA_KEYS = (
    "summary",
    "tags",
    "owners",
    "category",
    "status",
    "version",
    "related_docs",
    "maintained_by",
    "run_id",
    "stage",
    "session_id",
    "work_item_id",
)
RESERVED_LIFECYCLE_FIELDS = ("created_by", "edit_trace")


def _validate_comparison_symbols(text: str) -> bool:
    """Return False when text contains numeric comparisons like '5 > 3'."""
    if not isinstance(text, str):
        return True
    return not bool(COMPARISON_REGEX.search(text))


class ParameterValidationError(Exception):
    """Raised when manage_docs parameters fail validation."""

    def __init__(
        self,
        message: str,
        *,
        param_name: Optional[str] = None,
        suggestion: Optional[str] = None,
        tool_name: str = "manage_docs",
    ) -> None:
        self.tool_name = tool_name
        self.param_name = param_name
        self.suggestion = suggestion
        super().__init__(message)

    def __str__(self) -> str:
        base = super().__str__()
        parts = [f"[{self.tool_name}] {base}"]
        if self.param_name:
            parts.append(f"Parameter: {self.param_name}")
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return " | ".join(parts)


@dataclass(frozen=True)
class EnhancedManageDocsValidator:
    """Minimal validator implementation used by tests."""

    tool_name: str = "manage_docs"

    def create_validation_error(
        self,
        message: str,
        *,
        param_name: Optional[str] = None,
        suggestion: Optional[str] = None,
    ) -> ParameterValidationError:
        return ParameterValidationError(
            message,
            param_name=param_name,
            suggestion=suggestion,
            tool_name=self.tool_name,
        )

    def validate_string_param(
        self,
        value: Any,
        param_name: str,
        *,
        required: bool = True,
        min_length: int = 1,
        max_length: Optional[int] = None,
    ) -> str:
        if not isinstance(value, str):
            raise self.create_validation_error(
                f"{param_name} must be a string",
                param_name=param_name,
                suggestion="Provide a string value.",
            )
        if required and len(value) < min_length:
            raise self.create_validation_error(
                f"{param_name} is required and must be at least {min_length} characters",
                param_name=param_name,
                suggestion=f"Provide a non-empty string (min {min_length}).",
            )
        if max_length is not None and len(value) > max_length:
            raise self.create_validation_error(
                f"{param_name} must be no more than {max_length} characters",
                param_name=param_name,
                suggestion=f"Shorten the value to <= {max_length} characters.",
            )
        return value

    def validate_enum_param(
        self,
        value: Any,
        param_name: str,
        allowed_values: Iterable[str],
    ) -> str:
        value_str = self.validate_string_param(value, param_name, required=True, min_length=1)
        allowed_set = set(allowed_values)
        if value_str not in allowed_set:
            raise self.create_validation_error(
                f"{param_name} must be one of: {', '.join(sorted(allowed_set))}",
                param_name=param_name,
                suggestion="Use a supported enum value.",
            )
        return value_str

    def validate_metadata(self, value: Any, param_name: str = "metadata") -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise self.create_validation_error(
                f"{param_name} must be a dictionary",
                param_name=param_name,
                suggestion="Pass a JSON object / dict.",
            )
        for key in value.keys():
            if not isinstance(key, str):
                raise self.create_validation_error(
                    f"{param_name} key must be a string",
                    param_name=param_name,
                    suggestion="Use string keys only.",
                )
        return value

    def validate_comparison_operators(self, value: Any, param_name: str) -> Any:
        if isinstance(value, str) and not _validate_comparison_symbols(value):
            raise self.create_validation_error(
                f"{param_name} contains a numeric comparison; escape operators or rephrase",
                param_name=param_name,
                suggestion="Avoid patterns like '5 > 3' in user-provided strings.",
            )
        return value

    def validate_list_param(
        self,
        value: Any,
        param_name: str,
        *,
        max_items: Optional[int] = None,
    ) -> List[Any]:
        if not isinstance(value, list):
            raise self.create_validation_error(
                f"{param_name} must be a list",
                param_name=param_name,
                suggestion="Pass a JSON array / list.",
            )
        if max_items is not None and len(value) > max_items:
            raise self.create_validation_error(
                f"{param_name} cannot have more than {max_items} items",
                param_name=param_name,
                suggestion=f"Reduce the list length to <= {max_items}.",
            )
        return value


def create_manage_docs_validator() -> EnhancedManageDocsValidator:
    return EnhancedManageDocsValidator()


def summarize_frontmatter_metadata_hints(
    metadata: Dict[str, Any],
    *,
    action: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Return additive hints for supported/ignored generic workflow metadata fields."""
    hints: List[Dict[str, str]] = []
    if not isinstance(metadata, dict):
        return hints

    if action == "create_doc" and not str(metadata.get("summary", "")).strip():
        hints.append(
            {
                "code": "summary_missing_on_create",
                "message": "summary is recommended on create for workflow routing context.",
            }
        )

    if isinstance(metadata.get("tags"), str):
        hints.append(
            {
                "code": "tags_scalar_normalized_to_list",
                "message": "tags scalar input will be normalized to a single-item list.",
            }
        )
    if isinstance(metadata.get("owners"), str):
        hints.append(
            {
                "code": "owners_scalar_normalized_to_list",
                "message": "owners scalar input will be normalized to a single-item list.",
            }
        )

    if "edit_trace" in metadata or (
        isinstance(metadata.get("frontmatter"), dict) and "edit_trace" in metadata["frontmatter"]
    ):
        hints.append(
            {"code": "edit_trace_ignored", "message": "edit_trace is reserved and authored by manage_docs."}
        )

    if action and action != "create_doc":
        if "created_by" in metadata or (
            isinstance(metadata.get("frontmatter"), dict) and "created_by" in metadata["frontmatter"]
        ):
            hints.append(
                {
                    "code": "created_by_edit_override_ignored",
                    "message": "created_by is immutable after create in the generic frontmatter contract.",
                }
            )

    return hints


def _validate_inputs(
    *,
    doc: Any,
    action: Any,
    section: Any,
    content: Any,
    patch: Any = None,
    patch_source_hash: Any = None,
    edit: Any = None,
    patch_mode: Any = None,
    start_line: Any = None,
    end_line: Any = None,
    template: Any,
    metadata: Any,
) -> None:
    """
    Strict manage_docs validation used by enhancement tests.

    Raises:
      - DocumentValidationError for manage_docs contract violations
      - ParameterValidationError for type/shape violations
    """
    # Lazy import to avoid circular imports (tests import manager first).
    from scribe_mcp.doc_management.manager import DocumentValidationError

    validator = create_manage_docs_validator()

    validator.validate_string_param(doc, "doc")
    validator.validate_string_param(action, "action")

    allowed_actions = {
        "replace_section",
        "append",
        "status_update",
        "list_sections",
        "list_checklist_items",
        "batch",
        "apply_patch",
        "replace_range",
        "replace_text",
        "normalize_headers",
        "generate_toc",
        "create_doc",
        "validate_crosslinks",
        "create_research_doc",
        "create_bug_report",
        "create_review_report",
        "create_agent_report_card",
    }
    if action not in allowed_actions:
        raise DocumentValidationError(f"Invalid action '{action}' for manage_docs")

    if action == "replace_section":
        if not section:
            raise DocumentValidationError("Section parameter is required for replace_section")

    if action == "status_update":
        if metadata is None:
            raise DocumentValidationError("Metadata is required for status_update")
        validator.validate_metadata(metadata, "metadata")

    if action == "apply_patch":
        if patch or content:
            if not patch_mode:
                raise DocumentValidationError("patch_mode is required when providing a patch")
            if isinstance(patch_mode, str) and patch_mode not in {"structured", "unified"}:
                raise DocumentValidationError("patch_mode must be 'structured' or 'unified'")
        else:
            if edit is None:
                raise DocumentValidationError("edit payload is required for structured apply_patch")
        if edit is not None:
            validator.validate_metadata(edit, "edit")

    if action == "replace_range":
        if start_line is None or end_line is None:
            raise DocumentValidationError("start_line and end_line are required for replace_range")

    if action == "replace_text":
        if metadata is None:
            raise DocumentValidationError("metadata is required for replace_text")
        validator.validate_metadata(metadata, "metadata")
        if not metadata.get("find"):
            raise DocumentValidationError("metadata.find is required for replace_text")

    if action == "create_doc":
        if metadata is None:
            raise DocumentValidationError("metadata is required for create_doc")

    if action == "validate_crosslinks":
        if metadata is not None:
            validator.validate_metadata(metadata, "metadata")

    # Validate comparison operators in user-provided strings (content + metadata values).
    if isinstance(content, str) and not _validate_comparison_symbols(content):
        raise DocumentValidationError("Content contains numeric comparison operators")

    if isinstance(template, str) and not _validate_comparison_symbols(template):
        raise DocumentValidationError("Template contains numeric comparison operators")

    if metadata is not None:
        meta_dict = validator.validate_metadata(metadata, "metadata")
        for k, v in meta_dict.items():
            validator.validate_comparison_operators(v, f"metadata.{k}")
