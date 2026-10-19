"""Utility helpers."""

from importlib import import_module
from typing import Any

__all__ = [
    "append_line",
    "ensure_parent",
    "read_tail",
    "rotate_file",
    "slugify_project_name",
    "slugify_filename",
    "format_utc",
    "utcnow",
    "ResponseFormatter",
    "default_formatter",
    "create_pagination_info",
    "PaginationInfo",
    "TokenEstimator",
    "TokenMetrics",
    "TokenBudget",
    "token_estimator",
]


_LAZY_EXPORTS = {
    "append_line": (".files", "append_line"),
    "ensure_parent": (".files", "ensure_parent"),
    "read_tail": (".files", "read_tail"),
    "rotate_file": (".files", "rotate_file"),
    "slugify_project_name": (".slug", "slugify_project_name"),
    "slugify_filename": (".slug", "slugify_filename"),
    "format_utc": (".time", "format_utc"),
    "utcnow": (".time", "utcnow"),
    "ResponseFormatter": (".response", "ResponseFormatter"),
    "default_formatter": (".response", "default_formatter"),
    "create_pagination_info": (".response", "create_pagination_info"),
    "PaginationInfo": (".response", "PaginationInfo"),
    "TokenEstimator": (".tokens", "TokenEstimator"),
    "TokenMetrics": (".tokens", "TokenMetrics"),
    "TokenBudget": (".tokens", "TokenBudget"),
    "token_estimator": (".tokens", "token_estimator"),
}


def __getattr__(name: str) -> Any:
    """Resolve heavyweight compatibility exports only when first requested."""
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
