"""Batch action helper for manage_docs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _extract_range_coordinates(operation: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    action = str(operation.get("action") or "").strip()
    if action == "replace_range":
        start_line = operation.get("start_line")
        end_line = operation.get("end_line")
    elif action == "apply_patch":
        edit = operation.get("edit")
        if not isinstance(edit, dict) or str(edit.get("type") or "").strip() != "replace_range":
            return None
        start_line = edit.get("start_line")
        end_line = edit.get("end_line")
    else:
        return None

    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return None
    return start_line, end_line


def _normalize_range_batches(
    operations: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Reorder contiguous range-edit runs to keep later coordinates stable."""
    normalized: List[Dict[str, Any]] = []
    warnings: List[str] = []
    index = 0

    while index < len(operations):
        current = operations[index]
        current_range = _extract_range_coordinates(current) if isinstance(current, dict) else None
        current_doc = current.get("doc") if isinstance(current, dict) else None
        if current_range is None:
            normalized.append(current)
            index += 1
            continue

        block: List[Dict[str, Any]] = [current]
        lookahead = index + 1
        while lookahead < len(operations):
            candidate = operations[lookahead]
            if (
                not isinstance(candidate, dict)
                or candidate.get("doc") != current_doc
                or _extract_range_coordinates(candidate) is None
            ):
                break
            block.append(candidate)
            lookahead += 1

        if len(block) == 1:
            normalized.extend(block)
            index = lookahead
            continue

        ordered_block = sorted(
            block,
            key=lambda operation: _extract_range_coordinates(operation) or (0, 0),
            reverse=True,
        )
        if ordered_block != block:
            warnings.append(
                f"Reordered {len(block)} range edits for doc '{current_doc}' into descending line order "
                "to prevent later coordinates drifting after earlier replacements."
            )

        normalized.extend(ordered_block)
        index = lookahead

    return normalized, warnings


def _inherit_doc_name(
    operations: List[Dict[str, Any]],
    doc_name: Optional[str],
) -> List[Dict[str, Any]]:
    """Merge the batch-level doc_name into ops that do not target a doc themselves.

    An operation's own doc/doc_name always wins; inheritance only fills the gap
    so ops are not dispatched with doc_name=None (DOC_NOT_FOUND: 'None').
    """
    if not doc_name:
        return operations
    merged: List[Dict[str, Any]] = []
    for operation in operations:
        if isinstance(operation, dict) and not (
            operation.get("doc_name") or operation.get("doc")
        ):
            operation = {**operation, "doc_name": doc_name}
        merged.append(operation)
    return merged


async def handle_batch_action(
    *,
    action: str,
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    helper: Any,
    context: Any,
    doc_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Execute batch operations sequentially for the batch action."""
    if action != "batch":
        return None

    if not metadata or not isinstance(metadata, dict):
        return helper.apply_context_payload(
            helper.error_response("Batch action requires metadata with an 'operations' list."),
            context,
        )

    operations = metadata.get("operations")
    if not isinstance(operations, list):
        return helper.apply_context_payload(
            helper.error_response("Batch metadata must include an 'operations' list."),
            context,
        )

    operations = _inherit_doc_name(operations, doc_name)
    normalized_operations, warnings = _normalize_range_batches(operations)

    from scribe_mcp.tools.manage_docs import manage_docs

    results: List[Dict[str, Any]] = []
    for index, operation in enumerate(normalized_operations):
        if not isinstance(operation, dict):
            return helper.apply_context_payload(
                helper.error_response(f"Batch operation at index {index} is not a valid object."),
                context,
            )

        operation_payload = dict(operation)
        if operation_payload.get("action") == "batch":
            return helper.apply_context_payload(
                helper.error_response("Nested batch operations are not supported."),
                context,
            )

        # Fail-safe inheritance: a parent dry_run must never become a child write.
        if dry_run and "dry_run" not in operation_payload:
            operation_payload["dry_run"] = True

        batch_result = await manage_docs(**operation_payload)
        results.append({"index": index, "result": batch_result})
        if not batch_result.get("ok"):
            return helper.apply_context_payload(
                {
                    "ok": False,
                    "error": f"Batch operation {index} failed",
                    "results": results,
                    "warnings": warnings,
                },
                context,
            )

    return helper.apply_context_payload(
        {
            "ok": True,
            "results": results,
            "warnings": warnings,
        },
        context,
    )
