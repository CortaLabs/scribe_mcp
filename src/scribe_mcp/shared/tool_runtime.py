"""Shared tool runtime dispatch for MCP and CLI execution paths."""

from __future__ import annotations

import hashlib
import inspect
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Set, cast

from scribe_mcp.shared.repo_authority import build_repo_authority_snapshot
from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.shared.session_utils import get_canonical_session_key

ToolCallable = Callable[..., Any]
BridgeToolResolver = Callable[[str], Optional[ToolCallable]]
ScopeViolationLogger = Callable[..., None]
logger = logging.getLogger(__name__)
_PROVENANCE_VALUES = {"verified", "claimed", "inferred", "anonymous"}
_PROVENANCE_RANK = {
    "anonymous": 0,
    "inferred": 1,
    "claimed": 2,
    "verified": 3,
}
_UNTRUSTED_CALLER_SESSION_KEYS = (
    "session_id",
    "client_id",
    "connection_id",
    "transport_session_id",
)
_UNBOUND_REPO_SAFE_TOOLS = {"scribe_doctor", "list_projects"}


def _normalize_configured_repo_root(value: Any) -> Optional[str]:
    """Return a configured repo root only when it resolves to a real repo root."""
    if value is None:
        return None
    try:
        candidate = Path(str(value)).expanduser().resolve()
    except (TypeError, ValueError, OSError):
        return None
    discovered = RepoDiscovery.find_repo_root(candidate)
    if discovered is None:
        return None
    try:
        resolved = discovered.resolve()
    except (OSError, ValueError):
        return None
    if resolved != candidate or not resolved.exists():
        return None
    return str(resolved)


def _configured_repo_roots(settings: Any) -> tuple[Optional[str], tuple[str, ...]]:
    default_root = _normalize_configured_repo_root(
        getattr(settings, "default_repo_root", None)
    )
    trusted_values = getattr(settings, "trusted_repo_roots", ()) or ()
    if isinstance(trusted_values, (str, bytes)):
        trusted_iter: Iterable[Any] = (trusted_values,)
    else:
        trusted_iter = trusted_values
    trusted = []
    for item in trusted_iter:
        normalized = _normalize_configured_repo_root(item)
        if normalized and normalized not in trusted:
            trusted.append(normalized)
    if default_root and default_root not in trusted:
        trusted.append(default_root)
    return default_root, tuple(trusted)


def resolve_context_authoritative_session_key(context: Any) -> Optional[str]:
    """Resolve the canonical authoritative session key from runtime context."""
    if context is None:
        return None

    resolved_scope = getattr(context, "resolved_scope", None)
    for candidate in (
        getattr(resolved_scope, "authoritative_session_key", None),
        getattr(context, "authoritative_session_key", None),
        get_canonical_session_key(context),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


async def issue_repo_root_grant(
    *,
    storage_backend: Any,
    repo_root: str,
    reason: str,
    ttl_minutes: int,
    authoritative_session_key: str,
) -> Dict[str, str]:
    """Create a short-lived repo-root authorization grant."""
    if (
        storage_backend is None
        or not hasattr(storage_backend, "create_repo_scope_grant")
    ):
        raise ValueError("repo-scope grant storage backend is unavailable")

    normalized_root = str(Path(repo_root).expanduser().resolve())
    grant = await storage_backend.create_repo_scope_grant(
        authoritative_session_key=str(authoritative_session_key),
        repo_root=normalized_root,
        reason=str(reason),
        ttl_minutes=int(ttl_minutes),
    )
    return {
        "grant_id": str(grant.grant_id),
        "repo_root": str(grant.repo_root),
        "repo_id": str(grant.repo_id),
        "expires_at": grant.expires_at.isoformat(),
        "authoritative_session_key": str(grant.authoritative_session_key),
    }


async def validate_repo_root_grant(
    *,
    storage_backend: Any,
    grant_id: Optional[str],
    repo_root: str,
    authoritative_session_key: Optional[str],
) -> tuple[bool, Dict[str, str]]:
    """Validate a repo-root authorization grant against root and session."""
    if (
        storage_backend is None
        or not hasattr(storage_backend, "fetch_repo_scope_grant")
    ):
        return False, {"reason_code": "repo_scope_grant_storage_unavailable"}
    if not isinstance(grant_id, str) or not grant_id.strip():
        return False, {"reason_code": "missing_grant_id"}

    grant = await storage_backend.fetch_repo_scope_grant(grant_id.strip())
    if grant is None:
        return False, {"reason_code": "grant_not_found", "grant_id": grant_id.strip()}

    normalized_root = str(Path(repo_root).expanduser().resolve())
    grant_root = str(Path(str(grant.repo_root)).expanduser().resolve())
    if normalized_root != grant_root:
        return False, {
            "reason_code": "grant_root_mismatch",
            "grant_id": str(grant.grant_id),
            "requested_repo_root": normalized_root,
            "grant_repo_root": grant_root,
            "repo_id": str(grant.repo_id),
            "expires_at": grant.expires_at.isoformat(),
            "authoritative_session_key": str(grant.authoritative_session_key),
        }

    requested_session_key = (
        str(authoritative_session_key).strip()
        if isinstance(authoritative_session_key, str) and authoritative_session_key.strip()
        else None
    )
    if requested_session_key and requested_session_key != str(grant.authoritative_session_key):
        return False, {
            "reason_code": "grant_session_mismatch",
            "grant_id": str(grant.grant_id),
            "repo_root": grant_root,
            "repo_id": str(grant.repo_id),
            "expires_at": grant.expires_at.isoformat(),
            "authoritative_session_key": str(grant.authoritative_session_key),
            "requested_authoritative_session_key": requested_session_key,
        }

    return True, {
        "grant_id": str(grant.grant_id),
        "repo_root": grant_root,
        "repo_id": str(grant.repo_id),
        "expires_at": grant.expires_at.isoformat(),
        "authoritative_session_key": str(grant.authoritative_session_key),
    }


def repo_root_grant_diagnostics(*, storage_backend: Any) -> Dict[str, Any]:
    """Return basic diagnostics about repo-scope grant support."""
    backend_supports_grants = bool(
        storage_backend
        and hasattr(storage_backend, "create_repo_scope_grant")
        and hasattr(storage_backend, "fetch_repo_scope_grant")
    )
    return {
        "grant_storage_source": "backend" if backend_supports_grants else "unavailable",
        "grant_storage_ready": backend_supports_grants,
        "grant_metrics_available": False,
    }


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
    allow_untrusted_sources: bool = True,
    allow_process_fallback: bool = True,
) -> str:
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
        if meta:
            if isinstance(meta, dict):
                for key in ("transport_session_id", "session_id", "client_id", "connection_id"):
                    value = meta.get(key)
                    if value:
                        return str(value)
            else:
                for key in ("transport_session_id", "session_id", "client_id", "connection_id"):
                    value = getattr(meta, key, None)
                    if value:
                        return str(value)

    if allow_untrusted_sources:
        fallback = kwargs.get("session_id") or kwargs.get("client_id") or kwargs.get("connection_id")
        if fallback:
            return str(fallback)

    if not allow_process_fallback:
        return ""

    return f"process:{fallback_process_id}"


def _collect_public_release_session_claims(
    *,
    context_payload: Mapping[str, Any],
    kwargs: Mapping[str, Any],
    app: Any,
) -> Set[str]:
    claims: Set[str] = set()
    for key in _UNTRUSTED_CALLER_SESSION_KEYS:
        value = context_payload.get(key)
        if value:
            claims.add(key)
    for key in ("session_id", "client_id", "connection_id"):
        value = kwargs.get(key)
        if value:
            claims.add(key)
    try:
        request_context = app.request_context
    except Exception:
        request_context = None
    if request_context:
        request = getattr(request_context, "request", None)
        headers = getattr(request, "headers", None) if request is not None else None
        if headers and headers.get("mcp-session-id"):
            claims.add("mcp-session-id")
    return claims


def _set_scope_provenance(
    payload: MutableMapping[str, Any],
    *,
    field: str,
    label: str,
) -> None:
    if label not in _PROVENANCE_VALUES:
        return
    provenance = payload.get("scope_provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    existing = provenance.get(field)
    if existing not in _PROVENANCE_VALUES:
        provenance[field] = label
    elif _PROVENANCE_RANK[label] >= _PROVENANCE_RANK[existing]:
        provenance[field] = label
    payload["scope_provenance"] = provenance


def _set_scope_defaults(context_payload: MutableMapping[str, Any]) -> None:
    if not context_payload.get("resolution_source"):
        context_payload["resolution_source"] = "runtime_context"
    if context_payload.get("trust_level") not in _PROVENANCE_VALUES:
        context_payload["trust_level"] = "claimed"


def _derive_scoped_reuse_key(repo_root: str, project_name: str | None) -> str:
    normalized_repo_root = os.path.realpath(repo_root) if repo_root else ""
    normalized_project = (project_name or "").strip() or "__prebinding__"
    return f"{normalized_repo_root}:{normalized_project}"


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
        scope_day = str(timestamp_utc).split("T")[0]
        run_discriminator = str(context_payload.get("transport_session_id") or "").strip()
        if bool(context_payload.get("public_release")) and not run_discriminator:
            raise ValueError(
                "Public release sentinel mode requires trusted runtime-derived "
                "transport_session_id for identity isolation"
            )
        if run_discriminator:
            scope_key = f"{scope_day}:{run_discriminator}"
        else:
            scope_key = scope_day
    else:
        project_name = str(
            context_payload.get("project_name")
            or arguments.get("project")
            or arguments.get("project_name")
            or ""
        ).strip()
        scope_key = project_name or "__prebinding__"

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


def _coerce_int_params(func: ToolCallable, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce string-encoded integers to int for parameters annotated as int.

    MCP transport may serialize integer values as strings (e.g. page_number="1"
    instead of page_number=1).  The JSON schema for such parameters was widened
    to accept both "integer" and "string", so they pass schema validation.  This
    function converts any string value back to a proper Python int before the
    tool function is called, so the tool receives the type it expects.
    """
    import typing

    try:
        type_hints = typing.get_type_hints(func)
    except Exception:
        return arguments

    # Python 3.10+ uses types.UnionType for `X | Y` syntax; earlier Python uses
    # typing.Union.  Both need to be handled when unwrapping Optional[int].
    try:
        from types import UnionType as _UnionType  # Python 3.10+
    except ImportError:
        _UnionType = None  # type: ignore[assignment,misc]

    coerced = dict(arguments)
    for param_name, value in list(coerced.items()):
        if not isinstance(value, str):
            continue
        hint = type_hints.get(param_name)
        if hint is None:
            continue
        # Unwrap Optional[X] / Union[X, None] / X | None to get the inner type
        type_args = getattr(hint, "__args__", ())
        origin = getattr(hint, "__origin__", None)
        is_union = (origin is typing.Union) or (
            _UnionType is not None and isinstance(hint, _UnionType)
        )
        if is_union and type_args:
            non_none = [a for a in type_args if a is not type(None)]
            if len(non_none) == 1:
                hint = non_none[0]
        if hint is int:
            try:
                coerced[param_name] = int(value)
            except (ValueError, TypeError):
                pass  # Leave as-is; tool will handle the bad value
        elif hint is float:
            try:
                coerced[param_name] = float(value)
            except (ValueError, TypeError):
                pass
    return coerced


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

    bridge_resolution_attempted = False
    bridge_resolution_available = bridge_tool_resolver is not None
    if not func and ":" in name and bridge_tool_resolver is not None:
        bridge_resolution_attempted = True
        try:
            func = bridge_tool_resolver(name)
        except Exception:
            func = None

    if not func:
        if ":" in name and not bridge_resolution_available:
            raise ValueError(
                f"Unknown tool '{name}' (bridge resolution unavailable for this runtime path)"
            )
        if ":" in name and bridge_resolution_attempted:
            raise ValueError(
                f"Unknown tool '{name}' (bridge tool not registered or bridge runtime unavailable)"
            )
        raise ValueError(f"Unknown tool '{name}'")

    call_arguments = dict(arguments)

    context_payload = call_arguments.pop("context", None)
    if context_payload is None and "context" in kwargs:
        context_payload = kwargs.get("context")
    if not isinstance(context_payload, dict):
        context_payload = {}
    context_payload["_server_derived_session_id"] = False
    public_release = bool(getattr(settings, "public_release", False))
    context_payload["public_release"] = public_release
    current_context = None
    if hasattr(router_context_manager, "get_current"):
        try:
            current_context = router_context_manager.get_current()
        except Exception:
            current_context = None

    if public_release:
        caller_claims = _collect_public_release_session_claims(
            context_payload=context_payload,
            kwargs=kwargs,
            app=app,
        )
        # In public release, mixed caller identifiers are denied; single claims are ignored.
        if len(caller_claims) > 1:
            denied = ", ".join(sorted(caller_claims))
            raise ValueError(
                "Public release rejected untrusted caller session identifiers: "
                f"{denied}"
            )
        for key in _UNTRUSTED_CALLER_SESSION_KEYS:
            context_payload.pop(key, None)
        context_payload.pop("stable_session_id", None)

    if current_context is not None:
        current_scope = getattr(current_context, "resolved_scope", None)
        current_repo_root = getattr(current_scope, "repo_root", None)
        current_project_name = getattr(current_scope, "project_name", None)
        current_transport_session_id = getattr(current_scope, "transport_session_id", None)
        current_stable_session_id = (
            getattr(current_scope, "stable_session_id", None)
            or getattr(current_context, "stable_session_id", None)
        )
        if current_repo_root:
            context_payload["repo_root"] = str(current_repo_root)
            _set_scope_provenance(context_payload, field="repo_root", label="verified")
        if current_project_name:
            context_payload["project_name"] = str(current_project_name)
            _set_scope_provenance(context_payload, field="project_name", label="verified")
        if current_transport_session_id:
            context_payload["transport_session_id"] = str(current_transport_session_id)
            _set_scope_provenance(context_payload, field="transport_session_id", label="verified")
        if current_stable_session_id:
            context_payload["stable_session_id"] = str(current_stable_session_id)
            _set_scope_provenance(context_payload, field="stable_session_id", label="verified")
        current_session_id = getattr(current_context, "session_id", None)
        if current_session_id:
            context_payload["session_id"] = str(current_session_id)
            context_payload["_server_derived_session_id"] = True
        current_execution_id = getattr(current_context, "execution_id", None)
        if current_execution_id:
            context_payload["parent_execution_id"] = str(current_execution_id)
        if current_stable_session_id and not context_payload.get("_server_derived_session_id"):
            context_payload["_server_derived_session_id"] = True
    else:
        context_payload.pop("parent_execution_id", None)

    configured_default_repo_root, configured_trusted_roots = _configured_repo_roots(settings)

    repo_authority = build_repo_authority_snapshot(
        current_context=current_context,
        app=app,
        scribe_user=kwargs.get("_scribe_user"),
        authoritative_session_key=resolve_context_authoritative_session_key(current_context),
        enrolled_first_party_roots=configured_trusted_roots,
    )
    context_payload["repo_authority"] = repo_authority.as_dict()
    if not context_payload.get("repo_root") and repo_authority.verified_request_root:
        context_payload["repo_root"] = repo_authority.verified_request_root
        _set_scope_provenance(context_payload, field="repo_root", label="verified")
    if not context_payload.get("repo_root") and configured_default_repo_root:
        context_payload["repo_root"] = configured_default_repo_root
        context_payload["resolution_source"] = "configured_default_repo_root"
        _set_scope_provenance(context_payload, field="repo_root", label="verified")

    session_id_claimed = bool(context_payload.get("session_id"))

    runtime_transport_session_id = _derive_transport_session_id(
        app=app,
        fallback_process_id=str(getattr(router_context_manager, "_process_instance_id", "unknown")),
        kwargs={},
        allow_untrusted_sources=False,
        allow_process_fallback=False,
    )
    has_runtime_transport_identity = bool(runtime_transport_session_id) and not str(
        runtime_transport_session_id
    ).startswith("process:")

    repo_root_hint = _normalize_repo_root(context_payload.get("repo_root"), settings.project_root)
    existing_repo_root_provenance = (
        (context_payload.get("scope_provenance") or {}).get("repo_root")
        if isinstance(context_payload.get("scope_provenance"), dict)
        else None
    )
    if repo_root_hint:
        context_payload["repo_root"] = repo_root_hint
        if repo_root_hint in configured_trusted_roots:
            _set_scope_provenance(context_payload, field="repo_root", label="verified")
        elif existing_repo_root_provenance != "verified":
            _set_scope_provenance(context_payload, field="repo_root", label="claimed")
    else:
        repo_root_hint = _normalize_repo_root(
            call_arguments.get("root") or call_arguments.get("repo_root"),
            settings.project_root,
        )
        if repo_root_hint and name == "set_project":
            context_payload["repo_root"] = repo_root_hint
            _set_scope_provenance(context_payload, field="repo_root", label="claimed")
        elif repo_root_hint:
            context_payload["repo_root"] = repo_root_hint
            if repo_root_hint in configured_trusted_roots:
                _set_scope_provenance(context_payload, field="repo_root", label="verified")
            else:
                _set_scope_provenance(context_payload, field="repo_root", label="claimed")

    if not context_payload.get("project_name"):
        project_hint = call_arguments.get("project") or call_arguments.get("name")
        if project_hint:
            context_payload["project_name"] = str(project_hint)
            _set_scope_provenance(context_payload, field="project_name", label="claimed")

    if runtime_transport_session_id:
        context_payload["transport_session_id"] = runtime_transport_session_id
        _set_scope_provenance(context_payload, field="transport_session_id", label="verified")
        if has_runtime_transport_identity and context_payload.get("session_id"):
            context_payload["compat_session_id"] = str(context_payload.get("session_id"))
            context_payload.pop("session_id", None)
            session_id_claimed = False
    elif not context_payload.get("transport_session_id"):
        context_payload["transport_session_id"] = _derive_transport_session_id(
            app=app,
            fallback_process_id=str(getattr(router_context_manager, "_process_instance_id", "unknown")),
            kwargs=kwargs,
            allow_untrusted_sources=not public_release,
            allow_process_fallback=not public_release,
        )

    if (
        context_payload.get("transport_session_id")
        and not has_runtime_transport_identity
        and (
            (context_payload.get("scope_provenance") or {}).get("transport_session_id")
            if isinstance(context_payload.get("scope_provenance"), dict)
            else None
        ) != "verified"
    ):
        _set_scope_provenance(context_payload, field="transport_session_id", label="claimed")

    transport_session_provenance = (
        (context_payload.get("scope_provenance") or {}).get("transport_session_id")
        if isinstance(context_payload.get("scope_provenance"), dict)
        else None
    )
    if public_release and (
        not str(context_payload.get("transport_session_id") or "").strip()
        or transport_session_provenance != "verified"
    ):
        raise ValueError(
            "Public release requires trusted runtime-derived transport_session_id "
            "for session isolation"
        )

    if not context_payload.get("session_id") and context_payload.get("transport_session_id"):
        if storage_backend and hasattr(storage_backend, "get_session_by_transport"):
            existing = await storage_backend.get_session_by_transport(
                str(context_payload["transport_session_id"])
            )
            if existing and existing.get("session_id"):
                context_payload["session_id"] = existing["session_id"]
                context_payload["stable_session_id"] = existing["session_id"]
                context_payload["_server_derived_session_id"] = True
                _set_scope_provenance(context_payload, field="stable_session_id", label="verified")
                context_payload["trust_level"] = "verified"
                existing_repo_root = _normalize_repo_root(
                    existing.get("repo_root"),
                    settings.project_root,
                )
                if existing_repo_root and (
                    has_runtime_transport_identity
                    or str(context_payload.get("transport_session_id") or "").startswith("process:")
                ):
                    context_payload["repo_root"] = existing_repo_root
                    _set_scope_provenance(context_payload, field="repo_root", label="verified")
        if not context_payload.get("session_id"):
            session_id = await router_context_manager.get_or_create_session_id(
                context_payload["transport_session_id"]
            )
            context_payload["session_id"] = session_id
            context_payload["stable_session_id"] = session_id
            context_payload["_server_derived_session_id"] = True
            _set_scope_provenance(context_payload, field="stable_session_id", label="inferred")

    if storage_backend and hasattr(storage_backend, "fetch_project"):
        explicit_project = call_arguments.get("project") or call_arguments.get("name")
        explicit_root = call_arguments.get("root") or call_arguments.get("repo_root")
        current_repo_root_provenance = (
            (context_payload.get("scope_provenance") or {}).get("repo_root")
            if isinstance(context_payload.get("scope_provenance"), dict)
            else None
        )
        process_fallback_transport = str(context_payload.get("transport_session_id") or "").startswith("process:")
        if (
            name != "set_project"
            and explicit_project
            and (
                not context_payload.get("repo_root")
                or current_repo_root_provenance != "verified"
            )
        ):
            context_payload["project_name"] = str(explicit_project)
            _set_scope_provenance(context_payload, field="project_name", label="claimed")
            lookup_root = explicit_root or context_payload.get("repo_root")
            if lookup_root:
                project_record = await storage_backend.fetch_project(
                    str(explicit_project),
                    repo_root=str(lookup_root),
                )
            else:
                project_record = await storage_backend.fetch_project(str(explicit_project))
            if project_record:
                context_payload["repo_root"] = _normalize_repo_root(
                    project_record.repo_root,
                    settings.project_root,
                )
                _set_scope_provenance(context_payload, field="repo_root", label="verified")
                _set_scope_provenance(context_payload, field="project_name", label="verified")
        if (
            not context_payload.get("repo_root")
            and context_payload.get("session_id")
            and (session_id_claimed or has_runtime_transport_identity or process_fallback_transport)
        ):
            project_name = None
            if hasattr(storage_backend, "get_session_project"):
                project_name = await storage_backend.get_session_project(context_payload.get("session_id"))
            if project_name:
                context_payload["project_name"] = str(project_name)
                _set_scope_provenance(context_payload, field="project_name", label="verified")
                lookup_root = context_payload.get("repo_root")
                if lookup_root:
                    project_record = await storage_backend.fetch_project(
                        str(project_name),
                        repo_root=str(lookup_root),
                    )
                else:
                    project_record = await storage_backend.fetch_project(str(project_name))
                if project_record:
                    context_payload["repo_root"] = _normalize_repo_root(
                        project_record.repo_root,
                        settings.project_root,
                    )
                    _set_scope_provenance(context_payload, field="repo_root", label="verified")

    repo_root_provenance = (
        (context_payload.get("scope_provenance") or {}).get("repo_root")
        if isinstance(context_payload.get("scope_provenance"), dict)
        else None
    )
    if (
        context_payload.get("repo_root")
        and name != "set_project"
        and repo_root_provenance != "verified"
    ):
        context_payload.pop("repo_root", None)

    if not context_payload.get("repo_root") and name in _UNBOUND_REPO_SAFE_TOOLS:
        diagnostic_repo_root = _normalize_repo_root(settings.project_root, settings.project_root)
        if diagnostic_repo_root:
            context_payload["repo_root"] = diagnostic_repo_root
            context_payload["resolution_source"] = "diagnostic_server_root"
            _set_scope_provenance(context_payload, field="repo_root", label="anonymous")

    if not context_payload.get("repo_root"):
        if str(context_payload.get("mode", "")) == "sentinel" and name not in sentinel_allowed:
            raise ValueError(
                f"Tool '{name}' requires an active Scribe project. "
                "No project is active in sentinel mode; run set_project first."
            )
        context_payload["resolution_source"] = "unresolved_repo_scope"
        context_payload["scope_resolution_status"] = "unresolved"
        context_payload["scope_resolution_reason"] = (
            "repo_root_unresolved_no_verified_project_binding"
        )
        _set_scope_provenance(context_payload, field="repo_root", label="anonymous")
        raise ValueError(
            "ExecutionContext repo scope unresolved: no verified project binding "
            "for this request/session was available."
        )

    _set_scope_defaults(context_payload)

    await _resolve_mode(
        tool_name=name,
        context_payload=context_payload,
        arguments=call_arguments,
        storage_backend=storage_backend,
        state_manager=state_manager,
    )

    if (
        public_release
        and str(context_payload.get("mode", "")) == "sentinel"
        and not str(context_payload.get("transport_session_id") or "").strip()
    ):
        raise ValueError(
            "Public release sentinel mode requires trusted runtime-derived "
            "transport_session_id for identity isolation"
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
        except Exception as exc:
            logger.warning(
                "Failed to persist runtime session binding for tool '%s': %s",
                name,
                exc,
            )
            raise

    identity_hash, identity_parts = _derive_session_identity_preview(context_payload, call_arguments)
    if not _accepts_keyword_argument(func, "agent"):
        call_arguments.pop("agent", None)
    derived_scoped_reuse_key = _derive_scoped_reuse_key(
        identity_parts["repo_root"],
        None if identity_parts["scope_key"] == "__prebinding__" else identity_parts["scope_key"],
    )
    context_payload["scoped_reuse_key"] = derived_scoped_reuse_key
    context_payload["session_reuse_scope"] = derived_scoped_reuse_key
    agent_session_id = context_payload.get("agent_session_id")
    agent_session_source = "context" if agent_session_id else None

    if not agent_session_id and hasattr(router_context_manager, "get_cached_agent_session_id"):
        agent_session_id = await router_context_manager.get_cached_agent_session_id(identity_hash)
        if agent_session_id:
            agent_session_source = "cache"

    if (
        not agent_session_id
        and storage_backend
        and hasattr(storage_backend, "get_or_create_agent_session")
    ):
        agent_session_id = await storage_backend.get_or_create_agent_session(
            identity_key=identity_hash,
            agent_name=identity_parts["agent_key"],
            agent_key=identity_parts["agent_key"],
            repo_root=identity_parts["repo_root"],
            mode=identity_parts["mode"],
            scope_key=identity_parts["scope_key"],
        )
        if agent_session_id:
            agent_session_source = "allocator"
        if agent_session_id and hasattr(router_context_manager, "cache_agent_session_id"):
            await router_context_manager.cache_agent_session_id(identity_hash, agent_session_id)
        if agent_session_id and not context_payload.get("session_reuse_status"):
            context_payload["session_reuse_status"] = "allocated"

    if agent_session_id and storage_backend and hasattr(storage_backend, "get_last_agent_session_allocation"):
        allocation = await storage_backend.get_last_agent_session_allocation(identity_hash)
        if isinstance(allocation, Mapping):
            status = allocation.get("status")
            scope = allocation.get("scoped_reuse_key")
            allocation_session_id = allocation.get("session_id")
            if isinstance(status, str) and status:
                if allocation_session_id is None or str(allocation_session_id) == str(agent_session_id):
                    context_payload["session_reuse_status"] = status
            if isinstance(scope, str) and scope:
                context_payload["scoped_reuse_key"] = scope
                context_payload["session_reuse_scope"] = scope

    if agent_session_id and not context_payload.get("session_reuse_status"):
        if agent_session_source == "cache":
            context_payload["session_reuse_status"] = "cache_hit_unverified"
        else:
            context_payload["session_reuse_status"] = "reused"

    canonical_session_key = resolve_context_authoritative_session_key(current_context)
    if not canonical_session_key:
        canonical_session_key = (
            str(context_payload.get("stable_session_id")).strip()
            if str(context_payload.get("stable_session_id") or "").strip()
            else None
        ) or (
            str(context_payload.get("session_id")).strip()
            if str(context_payload.get("session_id") or "").strip()
            else None
        )
    if canonical_session_key:
        context_payload["authoritative_session_key"] = canonical_session_key

    if agent_session_id:
        context_payload["agent_session_id"] = agent_session_id
        _set_scope_provenance(context_payload, field="agent_session_id", label="verified")

    exec_context = await router_context_manager.build_execution_context(context_payload)

    if exec_context.mode == "sentinel" and name not in sentinel_allowed:
        log_scope_violation_cb(
            exec_context,
            reason="tool_not_allowed_in_sentinel_mode",
            tool_name=name,
        )
        raise ValueError(
            f"Tool '{name}' requires an active Scribe project. "
            "No project is active in sentinel mode; run set_project first."
        )

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

    # Coerce string-encoded integers/floats to their proper Python types.
    # MCP transport may pass integer parameters as strings (e.g. start_line="21").
    # The schema was widened to accept both types; here we normalize before dispatch.
    call_arguments = _coerce_int_params(func, call_arguments)

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
