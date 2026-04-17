#!/usr/bin/env python3
"""Lightweight probe runner for Scribe MCP tools.

Inspired by council_probe, this script lets you call any registered Scribe tool
with explicit payloads (no inline python hacks or MCP reloads). It is intended
for manual/interactive testing and quick smoke runs of individual tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from scribe_mcp.config.paths import repo_root

REPO_ROOT = repo_root()

# Keep Scribe paths predictable for probes (no writes to ~/.scribe unless requested).
os.environ.setdefault("SCRIBE_ROOT", str(REPO_ROOT))
os.environ.setdefault("SCRIBE_STATE_PATH", str(REPO_ROOT / "tmp_state_probe.json"))

from scribe_mcp.shared.project_registry import ProjectRegistry


# Optional rich formatting
try:
    from rich import print as rprint
    from rich.panel import Panel
except Exception:  # pragma: no cover - rich might be unavailable
    rprint = print
    Panel = None  # type: ignore


ToolFn = Callable[..., Any]


def _registry_sanity_probe(limit: Optional[int] = None, project: Optional[str] = None) -> Dict[str, Any]:
    """Lightweight registry health check using ProjectRegistry (probe-only, not an MCP tool)."""
    registry = ProjectRegistry()
    projects = registry.list_projects(limit=limit or 200)
    if project:
        projects = [info for info in projects if info.project_name == project]
    warnings: list[Dict[str, Any]] = []

    for info in projects:
        meta = info.meta or {}
        docs = meta.get("docs") or {}
        flags = docs.get("flags") or {}
        activity = meta.get("activity") or {}

        project_warnings: list[str] = []

        if info.total_files == 0:
            project_warnings.append("no_dev_plans")

        if info.status in ("in_progress", "complete") and not flags.get("docs_ready_for_work", False):
            project_warnings.append("docs_not_ready_for_work")

        if info.status == "complete" and info.total_entries == 0:
            project_warnings.append("complete_but_no_entries")

        dsle = activity.get("days_since_last_entry")
        dsla = activity.get("days_since_last_access")
        if isinstance(dsle, (int, float)) and isinstance(dsla, (int, float)):
            if dsle > 14 and dsla > 14:
                project_warnings.append("long_inactive_project")

        baseline_hashes = docs.get("baseline_hashes") or {}
        current_hashes = docs.get("current_hashes") or {}
        if docs and not baseline_hashes:
            project_warnings.append("docs_missing_baseline_hashes")
        docs_hash_drift = bool(flags.get("docs_hash_drift"))
        if not docs_hash_drift and baseline_hashes and current_hashes:
            for doc_name, baseline in baseline_hashes.items():
                current = current_hashes.get(doc_name)
                if baseline and current and baseline != current:
                    docs_hash_drift = True
                    break
        if docs_hash_drift and flags.get("docs_ready_for_work") is True:
            project_warnings.append("docs_ready_conflicts_with_hash_drift")

        if project_warnings:
            warnings.append(
                {
                    "project": info.project_name,
                    "status": info.status,
                    "docs_ready_for_work": bool(flags.get("docs_ready_for_work")),
                    "docs_hash_drift": docs_hash_drift,
                    "warnings": project_warnings,
                }
            )

    return {"ok": True, "warnings": warnings}


def _runtime_budget_result(*, elapsed_ms: int, budget_ms: int, loaded_tool_count: int) -> Dict[str, Any]:
    return {
        "elapsed_ms": elapsed_ms,
        "budget_ms": budget_ms,
        "within_budget": elapsed_ms <= budget_ms,
        "loaded_tool_count": loaded_tool_count,
    }


def _normalize_result_payload(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    structured_camel = getattr(result, "structuredContent", None)
    if isinstance(structured_camel, dict):
        return structured_camel
    is_error = getattr(result, "isError", None)
    content = getattr(result, "content", None)
    if isinstance(is_error, bool):
        text_snippets: list[str] = []
        if isinstance(content, list):
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str) and text.strip():
                    text_snippets.append(text.strip())
        payload: Dict[str, Any] = {"ok": not is_error}
        if text_snippets:
            payload["message"] = " ".join(text_snippets[:2])
        return payload
    return {"ok": False, "error": f"Unexpected result type: {type(result).__name__}"}


def _external_mismatch(
    *,
    code: str,
    message: str,
    step: str,
    steps: list[Dict[str, Any]],
    runtime_budget: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "ok": False,
        "classification": "environment_orchestration_mismatch",
        "error_code": code,
        "message": message,
        "failed_step": step,
        "steps": steps,
        "runtime_budget": runtime_budget,
    }


async def _release_bootstrap_proof(
    project: str,
    root: Optional[str] = None,
    external_observations: Optional[Dict[str, Any]] = None,
    runtime_budget_ms: int = 1500,
) -> Dict[str, Any]:
    """Probe-only release lane for startup/discovery truth at the repo boundary."""
    started = time.perf_counter()
    loaded_tool_count = len(_load_tool_runners())
    observations = external_observations or {}
    steps: list[Dict[str, Any]] = []

    def _budget() -> Dict[str, Any]:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return _runtime_budget_result(
            elapsed_ms=elapsed_ms,
            budget_ms=runtime_budget_ms,
            loaded_tool_count=loaded_tool_count,
        )

    persona_registered = observations.get("persona_registered")
    steps.append(
        {
            "step": "persona_precondition",
            "status": "ok" if persona_registered is not False else "failed",
            "value": persona_registered,
            "expected": True,
        }
    )
    if persona_registered is False:
        return _external_mismatch(
            code="persona_not_registered",
            message="Persona/profile precondition failed before repo startup flow.",
            step="persona_precondition",
            steps=steps,
            runtime_budget=_budget(),
        )

    open_session_ok = observations.get("open_session_ok")
    steps.append(
        {
            "step": "open_session",
            "status": "ok" if open_session_ok is not False else "failed",
            "value": open_session_ok,
            "expected": True,
        }
    )
    if open_session_ok is False:
        return _external_mismatch(
            code="open_session_failed",
            message="open_session failed before repo-owned tool flow.",
            step="open_session",
            steps=steps,
            runtime_budget=_budget(),
        )

    discovery_error = observations.get("discovery_error")
    discovered_tools = observations.get("discovered_tools")
    lazy_exposure = bool(observations.get("lazy_exposure", False))
    steps.append(
        {
            "step": "tool_discovery",
            "status": "failed" if discovery_error else "ok",
            "discovered_tools": discovered_tools,
            "lazy_exposure": lazy_exposure,
            "error": discovery_error,
        }
    )
    if discovery_error:
        return _external_mismatch(
            code="tool_discovery_failed",
            message="Tool discovery failed before repo-owned flow.",
            step="tool_discovery",
            steps=steps,
            runtime_budget=_budget(),
        )
    if isinstance(discovered_tools, list) and "set_project" not in discovered_tools and not lazy_exposure:
        return _external_mismatch(
            code="set_project_not_exposed",
            message="set_project missing from discovered tools without lazy exposure semantics.",
            step="tool_discovery",
            steps=steps,
            runtime_budget=_budget(),
        )

    set_payload: Dict[str, Any] = {"name": project}
    if root:
        set_payload["root"] = root
    try:
        set_result_raw = await _run_tool("set_project", set_payload)
    except Exception as exc:
        return {
            "ok": False,
            "classification": "repo_startup_defect",
            "error_code": "set_project_exception",
            "failed_step": "set_project",
            "message": str(exc),
            "steps": steps,
            "runtime_budget": _budget(),
        }

    set_result = _normalize_result_payload(set_result_raw)
    steps.append({"step": "set_project", "status": "ok" if set_result.get("ok") else "failed", "result": set_result})
    if not set_result.get("ok"):
        return {
            "ok": False,
            "classification": "repo_startup_defect",
            "error_code": "set_project_failed",
            "failed_step": "set_project",
            "message": set_result.get("error") or "set_project returned failure",
            "steps": steps,
            "runtime_budget": _budget(),
        }

    try:
        project_result_raw = await _run_tool(
            "query_entries",
            {
                "project": project,
                "limit": 1,
                "page": 1,
                "page_size": 1,
                "search_scope": "project",
                "document_types": [],
                "include_metadata": False,
                "compact": True,
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "classification": "repo_startup_defect",
            "error_code": "project_flow_exception",
            "failed_step": "project_bound_flow",
            "message": str(exc),
            "steps": steps,
            "runtime_budget": _budget(),
        }

    project_result = _normalize_result_payload(project_result_raw)
    steps.append(
        {
            "step": "project_bound_flow",
            "status": "ok" if project_result.get("ok") else "failed",
            "result": project_result,
        }
    )
    runtime_budget = _budget()
    return {
        "ok": bool(project_result.get("ok")),
        "classification": "repo_flow_verified" if project_result.get("ok") else "repo_startup_defect",
        "steps": steps,
        "runtime_budget": runtime_budget,
        "release_artifact": {
            "type": "startup_probe_budget",
            "project": project,
            "external_observations": observations,
            "result": "pass" if project_result.get("ok") else "fail",
            "within_runtime_budget": runtime_budget["within_budget"],
        },
    }


def _load_tool_runners() -> dict[str, ToolFn]:
    runners: dict[str, ToolFn] = {
        # Probe-only helper (not exposed as an MCP tool)
        "registry_sanity": _registry_sanity_probe,
        "release_bootstrap_proof": _release_bootstrap_proof,
    }
    try:
        from scribe_mcp.tools.append_entry import append_entry
        from scribe_mcp.tools.delete_project import delete_project
        from scribe_mcp.tools.generate_doc_templates import generate_doc_templates
        from scribe_mcp.tools.get_project import get_project
        from scribe_mcp.tools.list_projects import list_projects
        from scribe_mcp.tools.manage_docs import manage_docs
        from scribe_mcp.tools.query_entries import query_entries
        from scribe_mcp.tools.read_recent import read_recent
        from scribe_mcp.tools.rotate_log import rotate_log
        from scribe_mcp.tools.set_project import set_project
    except Exception:
        return runners

    runners.update(
        {
            "set_project": set_project,
            "get_project": get_project,
            "list_projects": list_projects,
            "append_entry": append_entry,
            "query_entries": query_entries,
            "read_recent": read_recent,
            "rotate_log": rotate_log,
            "manage_docs": manage_docs,
            "generate_doc_templates": generate_doc_templates,
            "delete_project": delete_project,
        }
    )
    return runners


def _json_or_str(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    try:
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    except Exception:
        pass
    return None


def _parse_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_payload_file(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    payload_path = Path(path)
    if not payload_path.exists():
        raise FileNotFoundError(f"Payload file not found: {payload_path}")
    with payload_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("Payload file must contain a JSON object.")
        return data


def _build_payload(tool: str, args: "ProbeArgs") -> Dict[str, Any]:
    """Construct a best-effort payload for the requested tool using CLI args."""
    if args.payload:
        return dict(args.payload)

    # Per-tool defaults with sensible knobs for manual overrides.
    if tool == "set_project":
        payload: Dict[str, Any] = {
            "name": args.project,
        }
        if args.root:
            payload["root"] = args.root
        if args.defaults:
            payload["defaults"] = args.defaults
        return payload

    if tool == "append_entry":
        meta = _json_or_str(args.meta) or {}
        payload = {
            "message": args.message or "Probe entry",
            "status": args.status,
            "emoji": args.emoji,
            "agent": args.agent,
            "meta": meta,
            "log_type": args.log_type,
        }
        return payload

    if tool == "query_entries":
        payload = {
            "project": args.project,
            "message": args.message,
            "limit": args.limit,
            "page": args.page,
            "page_size": args.page_size,
            "search_scope": args.search_scope,
            "document_types": _parse_list(args.document_types),
            "include_metadata": not args.compact,
            "compact": args.compact,
        }
        return payload

    if tool == "read_recent":
        return {
            "n": args.limit,
            "compact": args.compact,
            "include_metadata": not args.compact,
        }

    if tool == "rotate_log":
        return {
            "log_type": args.log_type or "progress",
            "confirm": args.confirm_rotate,
            "dry_run": args.dry_run,
        }

    if tool == "manage_docs":
        metadata = _json_or_str(args.meta) or {}
        return {
            "action": args.doc_action,
            "doc": args.doc,
            "section": args.section,
            "content": args.doc_content,
            "template": args.template,
            "metadata": metadata,
            "dry_run": args.dry_run,
            "doc_name": args.doc_name,
            "target_dir": args.target_dir,
        }

    if tool == "generate_doc_templates":
        return {"project": args.project, "overwrite": False}

    if tool == "delete_project":
        return {"name": args.project, "mode": "archive", "confirm": False}

    if tool == "get_project":
        return {}

    if tool == "list_projects":
        status_list = _parse_list(getattr(args, "status_list", None))
        tags_list = _parse_list(getattr(args, "tags_list", None))
        return {
            "limit": args.limit,
            "filter": args.message,
            "compact": args.compact,
            "fields": _parse_list(getattr(args, "fields", None)),
            "status": status_list or None,
            "tags": tags_list or None,
            "order_by": getattr(args, "order_by", None),
            "direction": getattr(args, "direction", "desc"),
        }

    if tool == "registry_sanity":
        return {
            "limit": args.limit,
            "project": args.project,
        }

    if tool == "release_bootstrap_proof":
        payload: Dict[str, Any] = {
            "project": args.project,
            "runtime_budget_ms": args.runtime_budget_ms,
        }
        if args.root:
            payload["root"] = args.root
        if args.bootstrap_observations is not None:
            payload["external_observations"] = args.bootstrap_observations
        return payload

    return {}


async def _run_tool(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    runner = _load_tool_runners().get(name)
    if runner is None:
        raise ValueError(f"Unknown tool: {name}")
    result = runner(**payload)
    if asyncio.iscoroutine(result):
        return await result  # type: ignore[return-value]
    return result  # type: ignore[return-value]


def _print(title: str, payload: Dict[str, Any]) -> None:
    if Panel:
        rprint(Panel(json.dumps(payload, indent=2, ensure_ascii=False), title=title, expand=False))
    else:
        rprint(f"\n=== {title} ===\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n")


@dataclass
class ProbeArgs:
    tools: Iterable[str]
    project: str
    message: Optional[str]
    status: str
    emoji: str
    agent: str
    meta: Optional[str]
    log_type: Optional[str]
    limit: Optional[int]
    page: int
    page_size: int
    search_scope: str
    document_types: Optional[str]
    compact: bool
    confirm_rotate: bool
    dry_run: bool
    doc_action: str
    doc: str
    section: Optional[str]
    doc_content: Optional[str]
    template: Optional[str]
    doc_name: Optional[str]
    target_dir: Optional[str]
    root: Optional[str]
    defaults: Optional[Dict[str, Any]]
    payload: Optional[Dict[str, Any]]
    # list_projects-specific
    fields: Optional[str]
    status_list: Optional[str]
    tags_list: Optional[str]
    order_by: Optional[str]
    direction: str
    runtime_budget_ms: int
    bootstrap_observations: Optional[Dict[str, Any]]


def parse_args(argv: list[str]) -> ProbeArgs:
    parser = argparse.ArgumentParser(description="Scribe MCP probe runner")
    parser.add_argument(
        "--tools",
        default="set_project,query_entries",
        help="Comma-separated list of tools to invoke (e.g., set_project,append_entry,query_entries,manage_docs).",
    )
    parser.add_argument("--project", default="mcp_connection_test")
    parser.add_argument("--message", help="Message/query text for append_entry/query_entries.")
    parser.add_argument("--status", default="info", help="Status for append_entry.")
    parser.add_argument("--emoji", default="🧪", help="Emoji for append_entry.")
    parser.add_argument("--agent", default="ScribeProbe", help="Agent name for append_entry.")
    parser.add_argument("--meta", help="JSON metadata string for append_entry/manage_docs.")
    parser.add_argument("--log-type", help="Log type for append_entry/rotate_log (default progress).")
    parser.add_argument("--limit", type=int, help="Limit for query_entries/read_recent.")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument(
        "--search-scope",
        default="project",
        help="Search scope for query_entries (project|global|all_projects|research|bugs|all).",
    )
    parser.add_argument("--document-types", help="Comma-separated document types for query_entries.")
    parser.add_argument("--compact", action="store_true", help="Use compact response for query_entries/read_recent.")
    parser.add_argument("--confirm-rotate", action="store_true", help="Set confirm=True for rotate_log.")
    parser.add_argument("--dry-run", action="store_true", help="Enable dry_run for rotate_log/manage_docs.")
    parser.add_argument("--doc-action", default="status_update", help="manage_docs action.")
    parser.add_argument("--doc", default="architecture", help="manage_docs doc type.")
    parser.add_argument("--section", help="manage_docs target section.")
    parser.add_argument("--doc-content", help="manage_docs content.")
    parser.add_argument("--template", help="manage_docs template name.")
    parser.add_argument("--doc-name", help="manage_docs doc_name override.")
    parser.add_argument("--target-dir", help="manage_docs target_dir override.")
    parser.add_argument("--root", help="Root override for set_project.")
    parser.add_argument("--defaults-json", help="JSON string for set_project defaults.")
    parser.add_argument("--payload-file", help="JSON file with explicit payload (applies to all selected tools).")
    parser.add_argument("--fields", help="Comma-separated fields for list_projects.")
    parser.add_argument("--status-list", help="Comma-separated statuses for list_projects (planning,in_progress,…).")
    parser.add_argument("--tags-list", help="Comma-separated tags filter for list_projects.")
    parser.add_argument("--order-by", help="Ordering field for list_projects (created_at,last_entry_at,last_access_at,total_entries).")
    parser.add_argument("--direction", default="desc", help="Ordering direction for list_projects (asc|desc).")
    parser.add_argument(
        "--runtime-budget-ms",
        type=int,
        default=1500,
        help="Runtime budget for release_bootstrap_proof artifact.",
    )
    parser.add_argument(
        "--bootstrap-observations-json",
        help="JSON object for release_bootstrap_proof external observations (persona/open_session/discovery).",
    )

    args_ns = parser.parse_args(argv)
    defaults = _json_or_str(args_ns.defaults_json)
    payload = _load_payload_file(args_ns.payload_file)
    bootstrap_observations = _json_or_str(args_ns.bootstrap_observations_json)

    tools = [tool.strip() for tool in args_ns.tools.split(",") if tool.strip()]
    return ProbeArgs(
        tools=tools,
        project=args_ns.project,
        message=args_ns.message,
        status=args_ns.status,
        emoji=args_ns.emoji,
        agent=args_ns.agent,
        meta=args_ns.meta,
        log_type=args_ns.log_type,
        limit=args_ns.limit,
        page=args_ns.page,
        page_size=args_ns.page_size,
        search_scope=args_ns.search_scope,
        document_types=args_ns.document_types,
        compact=args_ns.compact,
        confirm_rotate=args_ns.confirm_rotate,
        dry_run=args_ns.dry_run,
        doc_action=args_ns.doc_action,
        doc=args_ns.doc,
        section=args_ns.section,
        doc_content=args_ns.doc_content,
        template=args_ns.template,
        doc_name=args_ns.doc_name,
        target_dir=args_ns.target_dir,
        root=args_ns.root,
        defaults=defaults,
        payload=payload,
        fields=args_ns.fields,
        status_list=args_ns.status_list,
        tags_list=args_ns.tags_list,
        order_by=args_ns.order_by,
        direction=args_ns.direction,
        runtime_budget_ms=args_ns.runtime_budget_ms,
        bootstrap_observations=bootstrap_observations,
    )


async def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv or sys.argv[1:])

    results: list[tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    for tool in args.tools:
        payload = _build_payload(tool, args)
        _print(f"Payload: {tool}", payload)
        try:
            result = await _run_tool(tool, payload)
            results.append((tool, payload, result))
        except Exception as exc:  # pragma: no cover - manual probe mode
            results.append((tool, payload, {"ok": False, "error": str(exc)}))

    for tool, payload, result in results:
        _print(f"Result: {tool}", result if isinstance(result, dict) else {"result": result})


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
