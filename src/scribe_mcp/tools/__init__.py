"""Lazy-loading tool module registry.

Tool modules self-register with the MCP server at import time. To keep cold start
lightweight, this package defers imports until a specific tool is requested.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Dict, List, Optional, Set

_TOOL_MODULES: Dict[str, str] = {
    "authorize_repo_root": "scribe_mcp.tools.authorize_repo_root",
    "append_entry": "scribe_mcp.tools.append_entry",
    "backfill_case_registry": "scribe_mcp.tools.backfill_case_registry",
    "delete_project": "scribe_mcp.tools.delete_project",
    "doctor": "scribe_mcp.tools.doctor",
    "edit_file": "scribe_mcp.tools.edit_file",
    "generate_doc_templates": "scribe_mcp.tools.generate_doc_templates",
    "get_case_status": "scribe_mcp.tools.get_case_status",
    "get_project": "scribe_mcp.tools.get_project",
    "list_projects": "scribe_mcp.tools.list_projects",
    "list_open_cases": "scribe_mcp.tools.list_open_cases",
    "log_intelligence": "scribe_mcp.tools.log_intelligence",
    "manage_docs": "scribe_mcp.tools.manage_docs",
    "manage_docs_validation": "scribe_mcp.tools.manage_docs_validation",
    "progress_log_projection": "scribe_mcp.tools.progress_log_projection",
    "query_entries": "scribe_mcp.tools.query_entries",
    "read_file": "scribe_mcp.tools.read_file",
    "read_recent": "scribe_mcp.tools.read_recent",
    "reminder_tools": "scribe_mcp.tools.reminder_tools",
    "rotate_log": "scribe_mcp.tools.rotate_log",
    "search": "scribe_mcp.tools.search",
    "sentinel_tools": "scribe_mcp.tools.sentinel_tools",
    "set_project": "scribe_mcp.tools.set_project",
    "write_barrier": "scribe_mcp.tools.write_barrier",
}

_TOOL_NAME_TO_MODULE: Dict[str, str] = {
    "authorize_repo_root": "authorize_repo_root",
    "append_entry": "append_entry",
    "append_event": "sentinel_tools",
    "backfill_case_registry": "backfill_case_registry",
    "configure_reminders": "reminder_tools",
    "delete_project": "delete_project",
    "edit_file": "edit_file",
    "generate_doc_templates": "generate_doc_templates",
    "get_case_status": "get_case_status",
    "get_project": "get_project",
    "link_fix": "sentinel_tools",
    "list_projects": "list_projects",
    "list_open_cases": "list_open_cases",
    "analyze_logs": "log_intelligence",
    "manage_docs": "manage_docs",
    "open_bug": "sentinel_tools",
    "open_security": "sentinel_tools",
    "progress_log_projection": "progress_log_projection",
    "query_entries": "query_entries",
    "query_reminders": "reminder_tools",
    "read_file": "read_file",
    "read_recent": "read_recent",
    "reopen_case": "sentinel_tools",
    "reset_reminders": "reminder_tools",
    "rotate_log": "rotate_log",
    "scribe_doctor": "doctor",
    "search": "search",
    "set_project": "set_project",
    "read_write_barrier_state": "write_barrier",
    "scribe_owned_write_barrier_acquire_release_proof": "write_barrier",
    "scribe_owned_write_barrier_acquire_maintained": "write_barrier",
    "scribe_owned_write_barrier_release_maintained": "write_barrier",
}

_LOADED_MODULES: Set[str] = set()


def _load_module(module_key: str) -> ModuleType:
    if module_key in _LOADED_MODULES:
        loaded = globals().get(module_key)
        if isinstance(loaded, ModuleType):
            return loaded

    module_path = _TOOL_MODULES[module_key]
    module = import_module(module_path)
    globals()[module_key] = module
    _LOADED_MODULES.add(module_key)
    return module


def ensure_tool_loaded(tool_name: str) -> bool:
    """Import the owning module for a registered tool name if known."""
    module_key = _TOOL_NAME_TO_MODULE.get(tool_name)
    if not module_key:
        return False
    _load_module(module_key)
    return True


def ensure_all_tools_loaded() -> List[str]:
    """Import every tool module to fully populate MCP registry metadata."""
    for module_key in _TOOL_MODULES:
        _load_module(module_key)
    return sorted(_LOADED_MODULES)


def tool_module_for_name(tool_name: str) -> Optional[str]:
    """Return the module key owning a tool name, if known."""
    return _TOOL_NAME_TO_MODULE.get(tool_name)


def __getattr__(name: str) -> ModuleType:
    if name in _TOOL_MODULES:
        return _load_module(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = sorted(_TOOL_MODULES.keys()) + [
    "ensure_all_tools_loaded",
    "ensure_tool_loaded",
    "tool_module_for_name",
]
