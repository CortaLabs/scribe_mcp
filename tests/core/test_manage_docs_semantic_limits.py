"""Focused regression coverage for Phase 4.2-A collection hygiene."""

import builtins
import importlib
import sys
from pathlib import Path

from scribe_mcp.tools.manage_docs import _should_skip_doc_index


_FORBIDDEN_BUILTIN_EXPORTS = (
    "ParameterValidationError",
    "_validate_inputs",
    "_validate_comparison_symbols",
    "create_manage_docs_validator",
)


def test_doc_index_skip_for_logs() -> None:
    assert _should_skip_doc_index("progress_log", Path("PROGRESS_LOG.md"))
    assert _should_skip_doc_index("doc_log", Path("DOC_LOG.md"))
    assert _should_skip_doc_index("architecture", Path("PROGRESS_LOG.md.2026-01-02.md"))


def test_doc_index_keeps_regular_docs_indexable() -> None:
    assert not _should_skip_doc_index("architecture", Path("ARCHITECTURE_GUIDE.md"))


def test_manage_docs_validation_import_keeps_helpers_on_module_not_builtins() -> None:
    original_exports = {
        name: getattr(builtins, name)
        for name in _FORBIDDEN_BUILTIN_EXPORTS
        if hasattr(builtins, name)
    }

    try:
        for name in _FORBIDDEN_BUILTIN_EXPORTS:
            if hasattr(builtins, name):
                delattr(builtins, name)

        sys.modules.pop("scribe_mcp.tools.manage_docs_validation", None)
        module = importlib.import_module("scribe_mcp.tools.manage_docs_validation")

        assert callable(module.create_manage_docs_validator)
        assert callable(module._validate_inputs)
        assert callable(module._validate_comparison_symbols)
        assert issubclass(module.ParameterValidationError, Exception)

        for name in _FORBIDDEN_BUILTIN_EXPORTS:
            assert not hasattr(builtins, name)
    finally:
        for name in _FORBIDDEN_BUILTIN_EXPORTS:
            if name in original_exports:
                setattr(builtins, name, original_exports[name])
            elif hasattr(builtins, name):
                delattr(builtins, name)
