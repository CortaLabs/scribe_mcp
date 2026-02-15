"""Shared tool runtime dispatch for MCP and CLI execution paths."""

from __future__ import annotations

import hashlib
import inspect
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Mapping, MutableMapping, Optional, Set, cast

ToolCallable = Callable[..., Any]
BridgeToolResolver = Callable[[str], Optional[ToolCallable]]
ScopeViolationLogger = Callable[..., None]


def _normalize_repo_root(value: Any, project_root: Path) -> Optional[str]:
    if not value:
        return None
    try:
        root_path = Path(str(value)).expanduser()
    except (TypeError, ValueError):
        return None
    if not root_path.is_absolute():
        root_path = (project_root / root_path).resolve()
    else:
        root_path = root_path.resolve()
    return str(root_path)


def _extract_request_repo_root(app: Any) -> Optional[str]:
    try:
        request_context = app.request_context
    except Exception:
        return None
    if not request_context:
        return None
    meta = getattr(request_context, "meta", None)
    if not meta:
        return None
    if isinstance(meta, dict):
        for key in ("repo_root", "workspace_root", "cwd"):
            value = meta.get(key)
            if value:
                return str(value)
    else:
        for key in ("repo_root", "workspace_root", "cwd"):
            value = getattr(meta, key, None)
            if value:
                return str(value)
    return None


def _derive_transport_session_id(
    *,
    app: Any,
    fallback_process_id: str,
    kwargs: Mapping[str, Any],
) -> str:
    fallback = kwargs.get("session_id") or kwargs.get("client_id") or kwargs.get("connection_id")
    if fallback:
        return str(fallback)

    try:
        request_context = app.request_context
    except Exception:
        request_context = None

    if request_context:
        request = getattr(request_context, "request", None)
        if request is not None:
            headers = getattr(request, "headers", None)
            if headers:
                header_val = headers.get("mcp-session-id")
                if header_val:
                    return str(header_val)
        meta = getattr(request_context, "meta", None)
        client_id = getattr(meta, "client_id", None) if meta else None
        if client_id:
            return str(client_id)

    return f"process:{fallback_process_id}"


def _derive_session_identity_preview(
    context_payload: Mapping[str, Any],
    arguments: Mapping[str, Any],
) -> tuple[str, Dict[str, str]]:
    repo_root = os.path.realpath(str(context_payload.get("repo_root", "")))

    mode = str(context_payload.get("mode", "sentinel"))
    if mode == "sentinel":
        timestamp_utc = context_payload.get("timestamp_utc")
        if not timestamp_utc:
            timestamp_utc = datetime.now(timezone.utc).isoformat()
        scope_key = str(timestamp_utc).split("T")[0]
    else:
        scope_key = str(
            context_payload.get("transport_session_id")
            or context_payload.get("session_id")
            or datetime.now(timezone.utc).isoformat()
        )

    agent_key = arguments.get("agent")
    if not agent_key:
        raise ValueError("agent parameter is required for all tool calls")

    identity = f"{repo_root}:{mode}:{scope_key}:{agent_key}"
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()
    return identity_hash, {
        "repo_root": repo_root,
        "mode": mode,
        "scope_key": scope_key,
        "agent_key": str(agent_key),
    }


def _accepts_keyword_argument(func: ToolCallable, argument_name: str) -> bool:
    """Return True when a callable can accept a named kwarg."""

    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        # Some wrapped callables do not expose signatures reliably.
        return True

    parameter = signature.parameters.get(argument_name)
    if parameter and parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        return True

    return any(
        candidate.kind == inspect.Parameter.VAR_KEYWORD
        for candidate in signature.parameters.values()
    )


async def _resolve_mode(
    *,
    tool_name: str,
    context_payload: MutableMapping[str, Any],
    arguments: Mapping[str, Any],
    storage_backend: Any,
    state_manager: Any,
) -> None:
    if context_payload.get("mode") in {"sentinel", "project"}:
        return

    project_tools = {
        "set_project",
        "get_project",
        "append_entry",
        "read_recent",
        "query_entries",
        "rotate_log",
        "manage_docs",
        "generate_doc_templates",
    }
    if tool_name in project_tools:
        context_payload["mode"] = "project"
        return

    session_mode = None
    session_id = context_payload.get("session_id")
    if session_id:
        if storage_backend and hasattr(storage_backend, "get_session_mode"):
            session_mode = await storage_backend.get_session_mode(session_id)
        if session_mode is None:
            state = await state_manager.load()
            session_mode = state.get_session_mode(session_id)
    context_payload["mode"] = session_mode or "sentinel"

    affected = context_payload.get("affected_dev_projects")
    if not isinstance(affected, list):
        affected = []
    if not affected:
        project_hint = arguments.get("project") or arguments.get("name")
        if project_hint:
            affected = [str(project_hint)]
    context_payload["affected_dev_projects"] = affected


async def execute_tool_call(
    *,
    name: str,
    arguments: Dict[str, Any],
    kwargs: Mapping[str, Any],
    registry: Mapping[str, ToolCallable],
    app: Any,
    storage_backend: Any,
    settings: Any,
    state_manager: Any,
    router_context_manager: Any,
    sentinel_only: Set[str],
    sentinel_allowed: Set[str],
    log_scope_violation_cb: ScopeViolationLogger,
    bridge_tool_resolver: Optional[BridgeToolResolver] = None,
) -> Any:
    func = registry.get(name)

    if not func and ":" in name and bridge_tool_resolver is not None:
        try:
            func = bridge_tool_resolver(name)
        except Exception:
            func = None

    if not func:
        raise ValueError(f"Unknown tool '{name}'")

    call_arguments = dict(arguments)

    context_payload = call_arguments.pop("context", None)
    if context_payload is None and "context" in kwargs:
        context_payload = kwargs.get("context")
    if not isinstance(context_payload, dict):
        context_payload = {}

    if not context_payload.get("repo_root"):
        request_repo_root = _extract_request_repo_root(app)
        if request_repo_root:
            try:
                request_path = Path(request_repo_root).expanduser()
                if request_path.is_absolute():
                    from scribe_mcp.config.repo_config import RepoDiscovery

                    candidate_root = RepoDiscovery.find_repo_root(request_path)
                    if candidate_root and candidate_root.exists():
                        context_payload["repo_root"] = str(candidate_root.resolve())
            except Exception:
                pass

    repo_root_hint = _normalize_repo_root(context_payload.get("repo_root"), settings.project_root)
    if not repo_root_hint:
        repo_root_hint = _normalize_repo_root(
            call_arguments.get("root") or call_arguments.get("repo_root"),
            settings.project_root,
        )
    if repo_root_hint:
        context_payload["repo_root"] = repo_root_hint

    if not context_payload.get("session_id") and not context_payload.get("transport_session_id"):
        context_payload["transport_session_id"] = _derive_transport_session_id(
            app=app,
            fallback_process_id=str(getattr(router_context_manager, "_process_instance_id", "unknown")),
            kwargs=kwargs,
        )

    if not context_payload.get("session_id") and context_payload.get("transport_session_id"):
        if storage_backend and hasattr(storage_backend, "get_session_by_transport"):
            existing = await storage_backend.get_session_by_transport(
                str(context_payload["transport_session_id"])
            )
            if existing and existing.get("session_id"):
                context_payload["session_id"] = existing["session_id"]
            if existing and not context_payload.get("repo_root"):
                context_payload["repo_root"] = _normalize_repo_root(
                    existing.get("repo_root"),
                    settings.project_root,
                )
        if not context_payload.get("session_id"):
            session_id = await router_context_manager.get_or_create_session_id(
                context_payload["transport_session_id"]
            )
            context_payload["session_id"] = session_id

    if not context_payload.get("repo_root") and storage_backend and hasattr(storage_backend, "fetch_project"):
        explicit_project = call_arguments.get("project") or call_arguments.get("name")
        if explicit_project:
            project_record = await storage_backend.fetch_project(str(explicit_project))
            if project_record:
                context_payload["repo_root"] = _normalize_repo_root(
                    project_record.repo_root,
                    settings.project_root,
                )
        if not context_payload.get("repo_root") and context_payload.get("session_id"):
            project_name = None
            if hasattr(storage_backend, "get_session_project"):
                project_name = await storage_backend.get_session_project(context_payload.get("session_id"))
            if project_name:
                project_record = await storage_backend.fetch_project(str(project_name))
                if project_record:
                    context_payload["repo_root"] = _normalize_repo_root(
                        project_record.repo_root,
                        settings.project_root,
                    )

    if not context_payload.get("repo_root"):
        context_payload["repo_root"] = str(settings.project_root.resolve())

    await _resolve_mode(
        tool_name=name,
        context_payload=context_payload,
        arguments=call_arguments,
        storage_backend=storage_backend,
        state_manager=state_manager,
    )

    if not context_payload.get("session_id") and not context_payload.get("transport_session_id"):
        raise ValueError("ExecutionContext requires context.session_id or context.transport_session_id")

    if not context_payload.get("intent"):
        context_payload["intent"] = f"tool:{name}"

    if storage_backend and hasattr(storage_backend, "upsert_session"):
        try:
            await storage_backend.upsert_session(
                session_id=context_payload.get("session_id"),
                transport_session_id=context_payload.get("transport_session_id"),
                repo_root=context_payload.get("repo_root"),
                mode=context_payload.get("mode"),
            )
        except Exception:
            pass

    identity_hash, identity_parts = _derive_session_identity_preview(context_payload, call_arguments)
    stable_session_id = context_payload.get("stable_session_id")

    if not stable_session_id and hasattr(router_context_manager, "get_cached_agent_session_id"):
        stable_session_id = await router_context_manager.get_cached_agent_session_id(identity_hash)

    if (
        not stable_session_id
        and storage_backend
        and hasattr(storage_backend, "get_or_create_agent_session")
    ):
        stable_session_id = await storage_backend.get_or_create_agent_session(
            identity_key=identity_hash,
            agent_name=identity_parts["agent_key"],
            agent_key=identity_parts["agent_key"],
            repo_root=identity_parts["repo_root"],
            mode=identity_parts["mode"],
            scope_key=identity_parts["scope_key"],
        )
        if stable_session_id and hasattr(router_context_manager, "cache_agent_session_id"):
            await router_context_manager.cache_agent_session_id(identity_hash, stable_session_id)

    if stable_session_id:
        context_payload["stable_session_id"] = stable_session_id

    exec_context = await router_context_manager.build_execution_context(context_payload)

    if exec_context.mode == "sentinel" and name not in sentinel_allowed:
        log_scope_violation_cb(
            exec_context,
            reason="tool_not_allowed_in_sentinel_mode",
            tool_name=name,
        )
        raise ValueError(f"Tool '{name}' not allowed in sentinel mode")

    if exec_context.mode == "project" and name in sentinel_only and name != "append_event":
        raise ValueError(f"Tool '{name}' not allowed in project mode")

    token = router_context_manager.set_current(exec_context)

    if "project" not in call_arguments and "project_name" not in call_arguments:
        cached_project = await router_context_manager.get_cached_project(exec_context.stable_session_id)
        if cached_project:
            if _accepts_keyword_argument(func, "project"):
                call_arguments["project"] = cached_project
            elif _accepts_keyword_argument(func, "project_name"):
                call_arguments["project_name"] = cached_project

    try:
        result = func(**call_arguments)
    except TypeError as exc:
        raise ValueError(f"Invalid arguments for tool '{name}'") from exc

    if inspect.isawaitable(result):
        try:
            return await cast(Awaitable[Any], result)
        finally:
            router_context_manager.reset(token)
    try:
        return result
    finally:
        router_context_manager.reset(token)
