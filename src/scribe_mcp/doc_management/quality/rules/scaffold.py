from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from scribe_mcp.doc_management.quality.registry import QualityRuleEntry, QualityRuleRegistry, always_active


def build_scaffold_registry() -> QualityRuleRegistry:
    from scribe_mcp.doc_management import scaffold_quality as sq

    registry = QualityRuleRegistry()
    registry.register(
        QualityRuleEntry(
            key="scf.placeholder_residue",
            order=10,
            evaluator=lambda context: sq._placeholder_residue_warnings(
                str(context.get("body") or ""),
                context=context.get("document_context"),
            ),
            metadata={"family": "scaffold", "codes": ["SCF_PLACEHOLDER_BRACKET", "SCF_TEMPLATE_PROSE", "SCF_EMPTY_FINDING", "SCF_UNFILLED_APPENDIX"]},
            is_active=always_active,
        )
    )
    registry.register(
        QualityRuleEntry(
            key="scf.trailing_whitespace",
            order=20,
            evaluator=lambda context: sq._trailing_whitespace_warnings(str(context.get("body") or "")),
            metadata={"family": "scaffold", "codes": ["SCF_TRAILING_WHITESPACE"]},
            is_active=always_active,
        )
    )
    registry.register(
        QualityRuleEntry(
            key="scf.lifecycle_status",
            order=30,
            evaluator=lambda context: sq._lifecycle_status_warnings(
                str(context.get("body") or ""),
                frontmatter_status=str(context.get("frontmatter_status") or ""),
                context=context.get("document_context"),
            ),
            metadata={"family": "lifecycle", "codes": ["SCF_LIFECYCLE_STATUS_MISMATCH"]},
            is_active=always_active,
        )
    )
    registry.register(
        QualityRuleEntry(
            key="scf.readiness_conformance",
            order=40,
            evaluator=lambda context: sq._conformance_warnings(
                str(context.get("body") or ""),
                readiness_claim=bool(context.get("readiness_claim", False)),
                doc_name=_optional_str(context.get("doc_name")),
                existing_warnings=context.get("warnings_so_far"),
            ),
            metadata={"family": "readiness", "codes": ["SCF_TODO_ONLY_SECTION", "SCF_LOG_TEMPLATE_ONLY", "SCF_FRONTMATTER_MISMATCH"]},
            is_active=always_active,
        )
    )
    return registry


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def evaluate_scaffold_rules(*, body: str, doc_name: Optional[str], frontmatter_status: str, readiness_claim: bool, document_context: Any) -> list[Dict[str, Any]]:
    registry = build_scaffold_registry()
    context: Mapping[str, Any] = {
        "body": body,
        "doc_name": doc_name,
        "frontmatter_status": frontmatter_status,
        "readiness_claim": readiness_claim,
        "document_context": document_context,
    }
    warnings: list[Dict[str, Any]] = []
    for entry in registry.ordered_entries():
        if not entry.is_active(context):
            continue
        eval_context = dict(context)
        eval_context["warnings_so_far"] = list(warnings)
        warnings.extend(entry.evaluator(eval_context))
    return warnings
