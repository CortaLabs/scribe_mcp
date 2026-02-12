"""Batch action helper for manage_docs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


async def handle_batch_action(
    *,
    action: str,
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    helper: Any,
    context: Any,
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

    from scribe_mcp.tools.manage_docs import manage_docs

    results: List[Dict[str, Any]] = []
    for index, operation in enumerate(operations):
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
                },
                context,
            )

    return helper.apply_context_payload(
        {
            "ok": True,
            "results": results,
        },
        context,
    )
