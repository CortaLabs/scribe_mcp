"""Scribe doctor tool for runtime diagnostics."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit
import yaml

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.config.settings import settings
from scribe_mcp.config.repo_config import RepoDiscovery, resolve_runtime_efficiency_budgets
from scribe_mcp.config.mode_detection import resolve_configured_mode
from scribe_mcp.tool_contracts import read_only_local_tool
from scribe_mcp.plugins.registry import (
    get_plugin_registry,
    trusted_plugin_runtime_enabled,
    trusted_plugin_runtime_opt_in_vars,
)
from scribe_mcp.shared.project_registry import get_runtime_project_registry
from scribe_mcp.shared.tool_runtime import (
    repo_root_grant_diagnostics,
    resolve_context_authoritative_session_key,
)
from scribe_mcp.runtime_timing_envelope import build_timing_envelope
from scribe_mcp.physical_logical_reconciliation import build_physical_logical_reconciliation


def _list_loaded_plugins() -> list[str]:
    try:
        registry = get_plugin_registry()
    except Exception:
        return []
    return sorted(registry.plugins.keys())


def _plugin_loader_diagnostics() -> Dict[str, Any] | None:
    try:
        registry = get_plugin_registry()
    except Exception:
        return None
    diagnostics = getattr(registry, "last_load_diagnostics", None)
    return dict(diagnostics) if isinstance(diagnostics, dict) else None


def _discover_repo_plugin_stems(plugins_dir: Path | None) -> list[str]:
    if not plugins_dir or not plugins_dir.exists() or not plugins_dir.is_dir():
        return []
    return sorted(
        plugin_file.stem
        for plugin_file in plugins_dir.glob("*.py")
        if not plugin_file.name.startswith("__")
    )


def _build_plugin_diagnostics(config: Any, loaded_plugins: list[str]) -> Dict[str, Any]:
    plugin_settings = config.plugin_config or {}
    plugin_loading_requested = bool(config.plugin_loading_requested())
    repo_plugin_trust_enabled = trusted_plugin_runtime_enabled()
    plugins_dir = config.plugins_dir
    plugins_dir_exists = bool(plugins_dir and plugins_dir.exists() and plugins_dir.is_dir())
    discovered_stems = _discover_repo_plugin_stems(plugins_dir)
    allowlist = sorted(str(item) for item in plugin_settings.get("allowlist", []) or [])
    blocklist = sorted(str(item) for item in plugin_settings.get("blocklist", []) or [])
    blocked_reason = None
    guidance = None

    if plugin_loading_requested and discovered_stems and not repo_plugin_trust_enabled:
        blocked_reason = "repo_plugin_trust_not_enabled"
        primary_opt_in = trusted_plugin_runtime_opt_in_vars()[0]
        guidance = {
            "available_action": (
                f"Set {primary_opt_in}=1 in a trusted local runtime, then restart or "
                "reinitialize the Scribe MCP server."
            ),
            "equivalent_opt_in_vars": list(trusted_plugin_runtime_opt_in_vars()),
            "restart_required": True,
        }
    elif plugin_loading_requested and not plugins_dir_exists:
        blocked_reason = "plugins_dir_missing"
    elif not plugin_loading_requested and discovered_stems:
        blocked_reason = "plugin_config_not_enabled"

    return {
        "repo_plugin_trust_enabled": repo_plugin_trust_enabled,
        "plugin_loading_requested": plugin_loading_requested,
        "plugins_dir": str(plugins_dir) if plugins_dir else None,
        "plugins_dir_exists": plugins_dir_exists,
        "configured_allowlist_stems": allowlist,
        "configured_blocklist_stems": blocklist,
        "discovered_repo_local_stems": discovered_stems,
        "blocked_reason": blocked_reason,
        "guidance": guidance,
        "eligible": bool(plugin_loading_requested and repo_plugin_trust_enabled and plugins_dir_exists),
        "loaded": bool(loaded_plugins),
    }


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _redact_db_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        path = parts.path or ""
        netloc = f"***@{host}{port}" if host else "***"
        return urlunsplit((parts.scheme, netloc, path, "", ""))
    except Exception:
        return "<configured>"


def _backend_name(value: Any) -> str | None:
    if value is None:
        return None
    return type(value).__name__


def _bridge_hygiene_advisory(repo_root: Path | None) -> Dict[str, Any]:
    if repo_root is None:
        return {"status": "unknown", "deferred_non_blocking": []}
    manifest_path = repo_root / ".scribe" / "config" / "bridges" / "council_mcp.yaml"
    if not manifest_path.exists():
        return {"status": "not_present", "deferred_non_blocking": []}
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        payload = {}
    runtime_plugin = payload.get("runtime_plugin") if isinstance(payload, dict) else None
    if runtime_plugin:
        return {"status": "configured", "deferred_non_blocking": []}
    return {
        "status": "deferred_hygiene",
        "deferred_non_blocking": [
            {
                "code": "BRIDGE_RUNTIME_PLUGIN_DEFERRED",
                "severity": "low",
                "blocking": False,
                "path": str(manifest_path),
                "message": "Bridge manifest runtime_plugin warning is deferred hygiene unless a bridge tool path is invoked.",
            }
        ],
    }


async def _active_project_authority_snapshot(
    *,
    storage_backend: Any,
    runtime_exec_context: Any,
) -> Dict[str, Any]:
    authoritative_session_key = resolve_context_authoritative_session_key(runtime_exec_context)
    resolved_scope = getattr(runtime_exec_context, "resolved_scope", None) if runtime_exec_context else None
    resolved_repo_root = getattr(resolved_scope, "repo_root", None)
    resolved_project_name = getattr(resolved_scope, "project_name", None)
    resolution_source = getattr(resolved_scope, "resolution_source", None)
    provenance = getattr(resolved_scope, "provenance", None)
    repo_root_provenance = getattr(provenance, "repo_root", None) if provenance else None
    project_name_provenance = getattr(provenance, "project_name", None) if provenance else None

    bound_project_name = None
    if (
        authoritative_session_key
        and storage_backend is not None
        and hasattr(storage_backend, "get_session_project")
    ):
        try:
            bound_project_name = await storage_backend.get_session_project(str(authoritative_session_key))
        except Exception:
            bound_project_name = None
    project_name = bound_project_name or resolved_project_name

    project_record = None
    if (
        project_name
        and storage_backend is not None
        and hasattr(storage_backend, "fetch_project")
    ):
        try:
            project_record = await storage_backend.fetch_project(
                str(project_name),
                repo_root=str(resolved_repo_root) if resolved_repo_root else None,
            )
        except TypeError:
            project_record = await storage_backend.fetch_project(str(project_name))
        except Exception:
            project_record = None

    authority_source = str(resolution_source or "runtime_context")
    compatibility_bound = authority_source.startswith("compat_")
    if not compatibility_bound and isinstance(repo_root_provenance, str):
        compatibility_bound = repo_root_provenance in {"claimed", "inferred", "anonymous"}
    if compatibility_bound:
        authority_state = "compatibility_bound"
    elif str(repo_root_provenance or "").lower() == "verified":
        authority_state = "verified"
    else:
        authority_state = "granted"

    return {
        "authority_state": authority_state,
        "authority_source": authority_source,
        "authoritative_session_key": authoritative_session_key,
        "repo_root": str(resolved_repo_root) if resolved_repo_root else None,
        "project_name": str(project_name) if project_name else None,
        "project_key": getattr(project_record, "project_key", None) if project_record else None,
        "repo_id": getattr(project_record, "repo_id", None) if project_record else None,
        "provenance": {
            "repo_root": repo_root_provenance,
            "project_name": project_name_provenance,
        },
        "compatibility_usage": {
            "active_session_compatibility_bound": compatibility_bound,
            "remaining_legacy_skip_validation_compatibility_usage": 1 if compatibility_bound else 0,
            "denied_fallback_attempts": [],
        },
    }


async def _case_telemetry_snapshot(*, storage_backend: Any, runtime_exec_context: Any) -> Dict[str, Any]:
    if storage_backend is None or not hasattr(storage_backend, "query_case_registry_records"):
        return {
            "registry_surface_available": False,
            "list_surface_activity": {"query_attempted": False, "records_scanned": 0},
        }

    resolved_scope = getattr(runtime_exec_context, "resolved_scope", None) if runtime_exec_context else None
    repo_root = getattr(resolved_scope, "repo_root", None)
    project_name = getattr(resolved_scope, "project_name", None)
    normalized_status_counts: Dict[str, int] = {}
    ownership_snapshots: list[Dict[str, Any]] = []
    case_type_counts: Dict[str, int] = {}
    records_scanned = 0
    try:
        records = await storage_backend.query_case_registry_records(
            repo_root=str(repo_root) if repo_root else None,
            project_name=str(project_name) if project_name else None,
            limit=200,
            offset=0,
        )
    except Exception:
        records = []

    for record in records:
        records_scanned += 1
        status_value = str(getattr(record, "status", "") or "").strip().lower() or "open"
        normalized_status_counts[status_value] = normalized_status_counts.get(status_value, 0) + 1
        case_type = str(getattr(record, "case_type", "") or "").strip().lower() or "unknown"
        case_type_counts[case_type] = case_type_counts.get(case_type, 0) + 1
        if len(ownership_snapshots) < 3:
            ownership_snapshots.append(
                {
                    "case_id": getattr(record, "case_id", None),
                    "case_type": case_type,
                    "normalized_status": status_value,
                    "ownership": {
                        "project_name": getattr(record, "project_name", None),
                        "repo_id": getattr(record, "repo_id", None),
                        "project_key": getattr(record, "project_key", None),
                        "source_tool": getattr(record, "source_tool", None),
                    },
                }
            )

    return {
        "registry_surface_available": True,
        "list_surface_activity": {
            "query_attempted": True,
            "records_scanned": records_scanned,
        },
        "counts": {
            "total_cases": records_scanned,
            "by_case_type": case_type_counts,
            "by_normalized_status": normalized_status_counts,
        },
        "ownership_snapshots": ownership_snapshots,
    }


def _storage_diagnostics() -> dict[str, Any]:
    backend = str(getattr(settings, "storage_backend", "")).strip().lower()
    has_db_url = bool(getattr(settings, "db_url", None))
    mode = str(getattr(settings, "mode", "auto")).strip().lower()
    warnings: list[str] = []

    if backend == "postgres" and not has_db_url and mode != "standalone":
        warnings.append(
            "Postgres is selected but SCRIBE_DB_URL is missing. Server-class runtime will fail closed."
        )
    if backend == "sqlite" and has_db_url:
        warnings.append(
            "SQLite selected while SCRIBE_DB_URL is set. SCRIBE_ALLOW_SQLITE_WITH_DB_URL is diagnostic-only."
        )

    resolved_mode = None
    resolve_error = None
    try:
        resolved_mode = resolve_configured_mode(settings).value
    except Exception as exc:
        resolve_error = str(exc)

    return {
        "resolved_mode": resolved_mode,
        "resolve_error": resolve_error,
        "warnings": warnings,
    }


@app.tool(**read_only_local_tool(title="Scribe Doctor", tags=("diagnostics", "runtime", "read-only")))
async def scribe_doctor(agent: str) -> Dict[str, Any]:
    """Return runtime diagnostics for the current MCP server instance."""
    repo_root = settings.project_root
    repo_root_str = str(repo_root) if repo_root else None
    module_root = Path(settings.project_root)
    cwd = Path.cwd()
    config = None
    config_error = None
    config_path = None
    if repo_root:
        try:
            config = RepoDiscovery.load_config(Path(repo_root))
            config_path = _detect_config_path(Path(repo_root))
        except Exception as exc:  # pragma: no cover - defensive
            config_error = str(exc)

    plugin_info: Dict[str, Any] = {}
    loaded_plugins = _list_loaded_plugins()
    plugin_info["loaded"] = loaded_plugins
    plugin_info["count"] = len(loaded_plugins)
    loader_diagnostics = _plugin_loader_diagnostics()
    if loader_diagnostics is not None:
        plugin_info["loader_diagnostics"] = loader_diagnostics

    runtime_storage_backend = getattr(server_module, "storage_backend", None)
    runtime_state_manager = getattr(server_module, "state_manager", None)
    runtime_router_context_manager = getattr(server_module, "router_context_manager", None)
    runtime_exec_context = None
    try:
        runtime_exec_context = server_module.get_execution_context()
    except Exception:
        runtime_exec_context = None
    storage_diagnostics = _storage_diagnostics()
    grant_diagnostics = repo_root_grant_diagnostics(storage_backend=runtime_storage_backend)
    authority_snapshot = await _active_project_authority_snapshot(
        storage_backend=runtime_storage_backend,
        runtime_exec_context=runtime_exec_context,
    )
    case_snapshot = await _case_telemetry_snapshot(
        storage_backend=runtime_storage_backend,
        runtime_exec_context=runtime_exec_context,
    )
    physical_logical_reconciliation = await build_physical_logical_reconciliation(
        repo_root=Path(repo_root) if repo_root else Path.cwd(),
        storage_backend=runtime_storage_backend,
    )
    planning_registry = get_runtime_project_registry()
    planning_registry_context: Dict[str, Any] = {}
    try:
        planning_registry_context = planning_registry.get_registry_advisory_context()
    except Exception:
        planning_registry_context = {}

    config_view = None
    runtime_timing = dict(getattr(server_module, "_last_runtime_timing", {}) or {})
    if config is not None:
        plugin_info.update(_build_plugin_diagnostics(config, loaded_plugins))
        config_view = {
            "repo_slug": config.repo_slug,
            "repo_root": str(config.repo_root),
            "plugins_dir": str(config.plugins_dir) if config.plugins_dir else None,
            "plugin_config_enabled": _safe_bool((config.plugin_config or {}).get("enabled")),
            "storage_backend": config.storage_backend,
            "doc_snapshots": _safe_bool(config.doc_snapshots),
        }
    bridge_hygiene = _bridge_hygiene_advisory(repo_root if isinstance(repo_root, Path) else None)
    runtime_efficiency_budgets = resolve_runtime_efficiency_budgets(repo_root if isinstance(repo_root, Path) else None)

    return {
        "ok": True,
        "repo_root": repo_root_str,
        "module_root": str(module_root),
        "cwd": str(cwd),
        "env": {
            "SCRIBE_ROOT": os.environ.get("SCRIBE_ROOT"),
            "SCRIBE_STATE_PATH": os.environ.get("SCRIBE_STATE_PATH"),
            "SCRIBE_STORAGE_BACKEND": os.environ.get("SCRIBE_STORAGE_BACKEND"),
            "SCRIBE_DB_URL_set": bool(os.environ.get("SCRIBE_DB_URL")),
            "SCRIBE_ALLOW_SQLITE_WITH_DB_URL": os.environ.get("SCRIBE_ALLOW_SQLITE_WITH_DB_URL"),
            "SCRIBE_MODE": os.environ.get("SCRIBE_MODE"),
            "SCRIBE_REMOTE_URL": os.environ.get("SCRIBE_REMOTE_URL"),
        },
        "repo_root_candidates": {
            "from_settings": repo_root_str,
            "from_module_root": str(module_root),
            "from_cwd": str(cwd),
            "from_discovery": str(RepoDiscovery.find_repo_root(cwd) or ""),
        },
        "settings": {
            "project_root": repo_root_str,
            "dotenv_path": str((repo_root / ".env").resolve()) if repo_root else None,
            "dotenv_exists": bool(repo_root and (repo_root / ".env").exists()),
            "storage_backend": settings.storage_backend,
            "db_url_set": bool(settings.db_url),
            "db_url_redacted": _redact_db_url(settings.db_url),
            "mode": settings.mode,
            "remote_server_url": settings.remote_server_url,
            "remote_auth_configured": bool(settings.remote_auth_token),
            "sqlite_path": str(settings.sqlite_path),
            "postgres_schema": settings.postgres_schema,
        },
        "runtime": {
            "storage_backend": _backend_name(runtime_storage_backend),
            "state_manager_backend": _backend_name(
                getattr(runtime_state_manager, "_storage_backend", None)
            ),
            "router_context_backend": _backend_name(
                getattr(runtime_router_context_manager, "_storage_backend", None)
            ),
            "execution_context": {
                "repo_root": getattr(runtime_exec_context, "repo_root", None),
                "mode": getattr(runtime_exec_context, "mode", None),
                "session_id": getattr(runtime_exec_context, "session_id", None),
                "stable_session_id": getattr(runtime_exec_context, "stable_session_id", None),
                "transport_session_id": getattr(runtime_exec_context, "transport_session_id", None),
                "authoritative_session_key": resolve_context_authoritative_session_key(
                    runtime_exec_context
                ),
            } if runtime_exec_context else None,
            "repo_authority": {
                "authoritative_session_key": resolve_context_authoritative_session_key(
                    runtime_exec_context
                ) if runtime_exec_context else None,
                **grant_diagnostics,
                **authority_snapshot,
            },
            "case_telemetry": case_snapshot,
            "physical_logical_reconciliation": physical_logical_reconciliation,
            "storage_diagnostics": storage_diagnostics,
            "timing_envelope": build_timing_envelope(
                dispatch_path=runtime_timing.get("dispatch_path"),
                startup_profile=runtime_timing.get("startup_profile"),
                startup_phases_ms=runtime_timing.get("startup_phases_ms"),
                set_project_phase_ms=runtime_timing.get("set_project_phase_ms"),
                budget_thresholds=runtime_efficiency_budgets,
                source="runtime_snapshot",
            ),
            "planning_registry": {
                "available": bool(getattr(planning_registry, "available", False)),
                "classification": planning_registry_context.get("classification"),
                "reason_code": planning_registry_context.get("reason_code"),
                "message": planning_registry_context.get("message"),
                "mode": planning_registry_context.get("mode"),
                "storage_backend": planning_registry_context.get("storage_backend"),
            },
        },
        "config": config_view,
        "config_path": str(config_path) if config_path else None,
        "config_error": config_error,
        "plugins": plugin_info,
        "diagnostic_hygiene": bridge_hygiene,
    }


def _detect_config_path(repo_root: Path) -> Path | None:
    config_paths = [
        repo_root / ".scribe" / "config" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yaml",
        repo_root / ".scribe" / "scribe.yml",
        repo_root / "docs" / "dev_plans" / "scribe.yaml",
        repo_root / ".scribe" / "config.json",
    ]
    for candidate in config_paths:
        if candidate.exists():
            return candidate
    return None
