"""Universal command-line interface for Scribe tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, Sequence

import httpx

from scribe_mcp.cli.session_store import (
    CliSessionState,
    build_scoped_reuse_key,
    load_session_state,
    save_session_state,
)
from scribe_mcp.config.paths import cli_session_state_path
from scribe_mcp.storage.affected_row_referential_inventory import (
    mutation_rejected_report,
    storage_backend_unavailable_report,
)
from scribe_mcp.storage.project_identity_preflight import (
    DRY_RUN_REQUIRED_LABEL,
    MUTATION_REJECTED_LABEL,
)


_KNOWN_COMMANDS = {
    "call",
    "session",
    "tools",
    "bootstrap",
    "plugins",
    "templates",
    "logs",
    "install",
    "project-identity",
    "affected-row-inventory",
}
_DEFAULT_CALL_TIMEOUT_SECONDS = 6.0


def _discover_repo_root(start: Path) -> Path:
    candidate = start.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / ".git").exists() or (current / ".scribe").exists():
            return current
    return candidate


def _coerce_value(raw: str) -> Any:
    stripped = raw.strip()
    if stripped == "":
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return raw


def _load_json_object(raw: str | None, *, flag_name: str) -> Dict[str, Any]:
    if not raw:
        return {}
    payload = raw
    if raw.startswith("@"):
        payload = Path(raw[1:]).read_text(encoding="utf-8")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{flag_name} must be valid JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SystemExit(f"{flag_name} must decode to a JSON object")
    return parsed


def _load_optional_json_source(
    raw: str | None,
    *,
    file_path: str | None = None,
    flag_name: str,
) -> Dict[str, Any]:
    if raw and file_path:
        raise SystemExit(f"Use either {flag_name} or --meta-file, not both")
    if file_path:
        return _load_json_object(f"@{file_path}", flag_name="--meta-file")
    return _load_json_object(raw, flag_name=flag_name)


def _parse_key_value_pairs(values: Sequence[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit(f"--arg values must be key=value (received: {item})")
        key, raw_value = item.split("=", 1)
        key = key.strip().replace("-", "_")
        if not key:
            raise SystemExit("Argument key cannot be empty")
        parsed[key] = _coerce_value(raw_value)
    return parsed


def _parse_passthrough_options(tokens: Sequence[str]) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            raise SystemExit(f"Unexpected token: {token}. Tool options must be --key value.")
        key = token[2:]
        if not key:
            raise SystemExit("Empty option name is not valid")
        if key.startswith("no-"):
            parsed[key[3:].replace("-", "_")] = False
            index += 1
            continue
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            parsed[key.replace("-", "_")] = _coerce_value(tokens[index + 1])
            index += 2
            continue
        parsed[key.replace("-", "_")] = True
        index += 1
    return parsed


def _normalize_argv(argv: Sequence[str]) -> list[str]:
    normalized = list(argv)
    if not normalized:
        return normalized
    first = normalized[0]
    if first in _KNOWN_COMMANDS or first in {"-h", "--help"}:
        return normalized
    if first.startswith("-"):
        return normalized
    # Shorthand: `scribe read_file --path ...` -> `scribe call read_file --path ...`
    return ["call", *normalized]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scribe",
        description="Unified Scribe CLI for calling any registered tool.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    tools_parser = subparsers.add_parser("tools", help="List registered tools")
    tools_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    tools_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Guided Postgres setup for Scribe MCP.",
        description=(
            "Run the interactive Corta Labs / Scribe MCP Postgres bootstrap.\n"
            "Creates/updates roles, app database, schema grants, and .env runtime keys."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  scribe bootstrap\n"
            "  scribe bootstrap --dry-run\n"
            "  scribe bootstrap --no-interactive --superuser-password '<password>'\n"
        ),
    )
    bootstrap_parser.add_argument(
        "bootstrap_args",
        nargs=argparse.REMAINDER,
        help="Optional passthrough args for bootstrap-postgres.",
    )

    plugins_parser = subparsers.add_parser(
        "plugins",
        help="Project or validate first-party Scribe plugin bundles.",
    )
    plugins_subparsers = plugins_parser.add_subparsers(dest="plugins_action", required=True)

    project_codex_parser = plugins_subparsers.add_parser(
        "project-codex",
        help="Project the bundled Codex plugin into native Codex config/agent surfaces.",
    )
    project_codex_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    project_codex_parser.add_argument(
        "--plugin-root",
        dest="plugin_root",
        type=Path,
        default=None,
        help="Optional Codex plugin root override. Defaults to <repo-root>/plugins/codex.",
    )
    project_codex_parser.add_argument(
        "--codex-home",
        dest="codex_home",
        type=Path,
        default=None,
        help="Target CODEX_HOME directory. Defaults to $CODEX_HOME or ~/.codex.",
    )
    project_codex_parser.add_argument(
        "--config-path",
        dest="config_path",
        type=Path,
        default=None,
        help="Optional config.toml target. Defaults to <codex-home>/config.toml.",
    )

    templates_parser = subparsers.add_parser(
        "templates",
        help="Inspect and validate the active template stack.",
    )
    templates_subparsers = templates_parser.add_subparsers(dest="templates_action", required=True)

    templates_list_parser = templates_subparsers.add_parser(
        "list",
        help="List templates discovered for the active repository.",
    )
    templates_list_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    templates_list_parser.add_argument(
        "--project-name",
        default=None,
        help="Optional project name override for template context.",
    )
    templates_list_parser.add_argument(
        "--extension",
        default=".md",
        help="File extension to list (default: .md).",
    )
    templates_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )

    templates_validate_parser = templates_subparsers.add_parser(
        "validate",
        help="Validate Jinja templates discovered for the active repository.",
    )
    templates_validate_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    templates_validate_parser.add_argument(
        "--project-name",
        default=None,
        help="Optional project name override for template context.",
    )
    templates_validate_parser.add_argument(
        "--template",
        action="append",
        default=[],
        help="Validate one template by name (repeatable). Defaults to all discovered templates.",
    )
    templates_validate_parser.add_argument(
        "--extension",
        default=".md",
        help="File extension to validate when --template is omitted (default: .md).",
    )
    templates_validate_parser.add_argument(
        "--render-check",
        action="store_true",
        help="After syntax validation, perform a strict render smoke-test with the provided metadata.",
    )
    templates_validate_parser.add_argument(
        "--meta-json",
        default=None,
        help="Metadata JSON object used for render smoke-tests.",
    )
    templates_validate_parser.add_argument(
        "--meta-file",
        default=None,
        help="Path to a JSON file used for render smoke-tests.",
    )
    templates_validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )

    logs_parser = subparsers.add_parser("logs", help="Inspect progress logs")
    logs_subparsers = logs_parser.add_subparsers(dest="logs_action", required=True)
    logs_analyze_parser = logs_subparsers.add_parser("analyze", help="Analyze log intelligence signals")
    logs_analyze_parser.add_argument("file", help="Path to progress log markdown file")
    logs_analyze_parser.add_argument("--project", default=None, help="Optional project label for report scope")

    install_parser = subparsers.add_parser("install", help="Preview or commit secure install flow")
    install_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    install_parser.add_argument(
        "--profile",
        choices=["local-postgres", "sqlite-eval", "existing-postgres", "internal-remote"],
        default="local-postgres",
        help="Install profile preview target.",
    )
    install_parser.add_argument(
        "--allow-advanced-profile",
        action="store_true",
        help="Explicitly allow advanced profile previews (internal-remote).",
    )
    install_parser.add_argument("--commit", action="store_true", help="Apply install mutations.")
    install_parser.add_argument("--yes", action="store_true", help="Non-interactive confirmation for commit path.")
    install_parser.add_argument("--dangerous-overwrite-secrets", action="store_true", help="Explicitly allow overwriting existing secret env values.")
    install_parser.add_argument("--project-codex", action="store_true", help="Run optional Codex projection after successful commit verification.")

    identity_parser = subparsers.add_parser(
        "project-identity",
        help="Inspect project identity readiness without mutating storage.",
    )
    identity_subparsers = identity_parser.add_subparsers(dest="project_identity_action", required=True)
    identity_preflight_parser = identity_subparsers.add_parser(
        "preflight",
        help="Run a read-only project identity repair readiness preflight.",
        allow_abbrev=False,
    )
    identity_preflight_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    identity_preflight_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Required read-only mode for the preflight.",
    )
    identity_preflight_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    identity_preflight_parser.add_argument(
        "--apply",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    inventory_parser = subparsers.add_parser(
        "affected-row-inventory",
        help="Inspect affected-row referential inventory readiness without mutating storage.",
    )
    inventory_subparsers = inventory_parser.add_subparsers(dest="affected_row_inventory_action", required=True)
    inventory_preflight_parser = inventory_subparsers.add_parser(
        "preflight",
        help="Run a read-only affected-row referential inventory preflight.",
        allow_abbrev=False,
    )
    inventory_preflight_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    inventory_preflight_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Required read-only mode for the preflight.",
    )
    inventory_preflight_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    inventory_preflight_parser.add_argument(
        "--target-binding-status-label",
        default="PASS",
        help="Public target-binding proof label.",
    )
    inventory_preflight_parser.add_argument(
        "--selected-context-readback-status-label",
        default="PASS",
        help="Public selected-context readback proof label.",
    )
    inventory_preflight_parser.add_argument(
        "--apply",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    call_parser = subparsers.add_parser("call", help="Invoke a tool by name", allow_abbrev=False)
    call_parser.add_argument("tool", help="Tool name (for example: read_file)")
    call_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    call_parser.add_argument(
        "--session",
        default="default",
        help="Named CLI session used for persisted execution context.",
    )
    call_parser.add_argument(
        "--agent",
        required=True,
        help="Agent identity for this tool call (required).",
    )
    call_parser.add_argument(
        "--args-json",
        default="{}",
        help="JSON object merged into tool arguments (supports @path/to/file.json).",
    )
    call_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value (repeatable, JSON values allowed).",
    )
    call_parser.add_argument(
        "--context-json",
        default=None,
        help="JSON object merged into runtime context (supports @path/to/file.json).",
    )
    call_parser.add_argument(
        "--session-mode",
        choices=["auto", "project", "sentinel"],
        default="auto",
        help="Override mode for this call. `auto` keeps persisted mode.",
    )
    call_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON responses.",
    )
    call_parser.add_argument(
        "--no-save-session",
        action="store_true",
        help="Do not persist updated session context after call.",
    )
    call_parser.add_argument(
        "--tool-timeout-seconds",
        type=float,
        default=None,
        help=(
            "Timeout for one-shot storage-backed call execution in seconds. "
            "Defaults to SCRIBE_CALL_TIMEOUT_SECONDS or 6.0."
        ),
    )

    session_parser = subparsers.add_parser("session", help="Inspect/reset CLI session state")
    session_subparsers = session_parser.add_subparsers(dest="session_action", required=True)

    show_parser = session_subparsers.add_parser("show", help="Show current session state")
    show_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    show_parser.add_argument("--name", default="default", help="Session name")
    show_parser.add_argument("--agent", default=None, help="Agent identity override")

    reset_parser = session_subparsers.add_parser("reset", help="Delete a stored session")
    reset_parser.add_argument(
        "--repo-root",
        dest="repo_root",
        type=Path,
        default=Path.cwd(),
        help="Repository root or any path inside the target repository.",
    )
    reset_parser.add_argument("--name", default="default", help="Session name")

    return parser


def _resolve_agent(agent: str | None) -> str:
    if agent:
        return agent
    return os.environ.get("SCRIBE_CLI_AGENT", "cli")


def _prepare_environment(repo_root: Path) -> None:
    os.environ["SCRIBE_ROOT"] = str(repo_root.resolve())


def _resolve_call_timeout_seconds(explicit: float | None) -> float:
    """Resolve one-shot CLI timeout in seconds for storage-backed tool calls."""
    if explicit is not None:
        return max(0.1, float(explicit))
    raw = os.environ.get("SCRIBE_CALL_TIMEOUT_SECONDS")
    if raw is None:
        return _DEFAULT_CALL_TIMEOUT_SECONDS
    try:
        return max(0.1, float(raw))
    except ValueError:
        return _DEFAULT_CALL_TIMEOUT_SECONDS


def _bound_server_endpoint() -> str | None:
    """Return configured/discoverable server endpoint for bound execution."""
    endpoint = os.environ.get("SCRIBE_REMOTE_URL")
    if isinstance(endpoint, str) and endpoint.strip():
        return endpoint.strip()
    return None


def _redacted_auth_state() -> str:
    """Return a non-secret auth state marker for diagnostics."""
    token = os.environ.get("SCRIBE_REMOTE_AUTH_TOKEN") or os.environ.get("SCRIBE_TRANSPORT_AUTH_TOKEN")
    return "configured" if token else "missing"


def _bound_server_headers() -> dict[str, str]:
    token = os.environ.get("SCRIBE_REMOTE_AUTH_TOKEN") or os.environ.get("SCRIBE_TRANSPORT_AUTH_TOKEN")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}", "x-scribe-auth": token}


async def _invoke_tool_bound_server(
    *,
    endpoint: str,
    tool: str,
    call_args: Dict[str, Any],
    context: Dict[str, Any],
    timeout_seconds: float,
) -> Dict[str, Any]:
    url = f"{endpoint.rstrip('/')}/api/v1/tools/invoke"
    payload = {"tool_name": tool, "arguments": call_args, "context": context}
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=_bound_server_headers(), json=payload)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("Bound server returned non-object response")
    if "error" in body:
        raise RuntimeError(str(body.get("error") or "unknown bound-server error"))
    result = body.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("Bound server returned invalid result payload")
    return result


def _normalize_tracked_path(repo_root: Path, candidate: Any) -> str | None:
    """Normalize and sandbox-check persisted read paths for CLI parity."""
    if not isinstance(candidate, str) or not candidate.strip():
        return None

    raw_path = Path(candidate).expanduser()
    if not raw_path.is_absolute():
        raw_path = repo_root / raw_path

    try:
        resolved = raw_path.resolve()
    except OSError:
        return None

    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None

    return str(resolved)


def _load_tracked_reads(context: Dict[str, Any], repo_root: Path) -> list[str]:
    """Return deduplicated, normalized file-read history from context."""
    raw_values = context.get("files_read")
    if not isinstance(raw_values, list):
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for value in raw_values:
        normalized_value = _normalize_tracked_path(repo_root, value)
        if normalized_value and normalized_value not in seen:
            seen.add(normalized_value)
            normalized.append(normalized_value)

    return normalized


def _result_is_success(result: Any) -> bool:
    """Best-effort success detection for tool return payloads."""
    if isinstance(result, dict):
        if "isError" in result:
            return not bool(result.get("isError"))
        if "ok" in result:
            return bool(result.get("ok"))
        if result.get("error"):
            return False
    return True


async def _rehydrate_file_reads(
    *,
    server_module: Any,
    session_id: str | None,
    tracked_reads: Sequence[str],
) -> None:
    """Restore per-session read history into runtime cache for edit_file checks."""
    if not session_id or not tracked_reads:
        return

    context_manager = getattr(server_module, "router_context_manager", None)
    if context_manager is None or not hasattr(context_manager, "record_file_read"):
        return

    for file_path in tracked_reads:
        try:
            await context_manager.record_file_read(session_id, file_path)
        except Exception:
            # Rehydration should never block user tool calls.
            continue


def _json_print(payload: Any, pretty: bool = False) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    elif hasattr(payload, "dict") and callable(payload.dict):
        payload = payload.dict()

    if isinstance(payload, (dict, list)):
        if pretty:
            print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        return
    print(payload)


def _session_record_value(record: Any, field: str) -> Any:
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def _refresh_context_after_set_project(
    *,
    context: Dict[str, Any],
    result: Any,
    repo_root: Path,
) -> None:
    """Persist verified project binding details after a successful set_project."""
    if not (_result_is_success(result) and isinstance(result, dict)):
        return

    project = result.get("project")
    if not isinstance(project, dict):
        return

    project_name_raw = project.get("name") or result.get("project_name")
    project_name = str(project_name_raw).strip() if project_name_raw is not None else ""
    if not project_name:
        return

    project_root_raw = project.get("root") or context.get("repo_root") or str(repo_root.resolve())
    project_root = str(Path(str(project_root_raw)).expanduser().resolve())

    scope_provenance = context.get("scope_provenance")
    if not isinstance(scope_provenance, dict):
        scope_provenance = {}
    scope_provenance["project_name"] = "verified"
    scope_provenance["repo_root"] = "verified"

    scoped_reuse_key = build_scoped_reuse_key(repo_root, project_name)
    context["project_name"] = project_name
    context["repo_root"] = project_root
    context["scope_provenance"] = scope_provenance
    context["session_scope_state"] = "project_bound"
    context["scoped_reuse_key"] = scoped_reuse_key
    context["session_reuse_scope"] = scoped_reuse_key


async def _run_tools_command(args: argparse.Namespace) -> int:
    from scribe_mcp import server as server_module

    tools = server_module.describe_registered_tools()
    for details in tools.values():
        schema_required = details.get("input_schema", {}).get("required", [])
        if not isinstance(schema_required, list):
            schema_required = []

        effective_required = sorted({str(item) for item in schema_required if item} | {"agent"})
        details["runtime_required"] = ["agent"]
        details["effective_required"] = effective_required

    if args.json:
        _json_print(tools, pretty=True)
        return 0

    for tool_name in sorted(tools):
        details = tools[tool_name]
        required = details.get("effective_required", ["agent"])
        required_text = ", ".join(required)
        print(f"{tool_name}\trequired: {required_text}")
    return 0


async def _run_call_command(args: argparse.Namespace, passthrough_options: Dict[str, Any]) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    from scribe_mcp import server as server_module

    agent = _resolve_agent(args.agent)
    session_state = load_session_state(args.session, repo_root, agent)
    session_state.agent = agent
    session_state.repo_root = str(repo_root.resolve())

    call_args = _load_json_object(args.args_json, flag_name="--args-json")
    call_args.update(_parse_key_value_pairs(args.arg))
    call_args.update(passthrough_options)
    if "agent" not in call_args:
        call_args["agent"] = agent

    context = dict(session_state.context)
    context["repo_root"] = str(repo_root.resolve())
    context["transport_session_id"] = session_state.transport_session_id
    if args.session_mode != "auto":
        context["mode"] = args.session_mode

    context_overrides = _load_json_object(args.context_json, flag_name="--context-json")
    context.update(context_overrides)

    tracked_reads = _load_tracked_reads(context, repo_root)
    if tracked_reads:
        context["files_read"] = tracked_reads

    initial_session_id = context.get("session_id")
    await _rehydrate_file_reads(
        server_module=server_module,
        session_id=initial_session_id if isinstance(initial_session_id, str) else None,
        tracked_reads=tracked_reads,
    )

    startup_profile = str(
        getattr(server_module, "resolve_tool_startup_profile", lambda _name: "full_server")(args.tool)
    )
    skip_startup = startup_profile == "local_only"
    dispatch_path = "local_one_shot"
    endpoint = _bound_server_endpoint()
    if (not skip_startup) and endpoint:
        # Fast path: run through configured server/client endpoint when available.
        context["dispatch_path"] = "bound_server"
        context["remote_server_url"] = endpoint
        dispatch_path = "bound_server"
    if skip_startup:
        context["dispatch_path"] = "local_one_shot"
        context["startup_profile"] = startup_profile
        result = await server_module.invoke_tool(args.tool, call_args, context=context)
    else:
        timeout_seconds = _resolve_call_timeout_seconds(args.tool_timeout_seconds)
        context["startup_profile"] = startup_profile
        try:
            if dispatch_path == "bound_server":
                result = await _invoke_tool_bound_server(
                    endpoint=endpoint,
                    tool=args.tool,
                    call_args=call_args,
                    context=context,
                    timeout_seconds=timeout_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    server_module.invoke_tool(args.tool, call_args, context=context),
                    timeout=timeout_seconds,
                )
        except (asyncio.TimeoutError, httpx.HTTPError, RuntimeError):
            if dispatch_path == "bound_server":
                print(
                    (
                        f"warning: bound_server path unavailable for '{args.tool}' (endpoint={endpoint}, "
                        f"auth={_redacted_auth_state()}); falling back to local_one_shot."
                    ),
                    file=sys.stderr,
                )
                context["dispatch_path"] = "local_one_shot"
                try:
                    context.pop("remote_server_url", None)
                    result = await asyncio.wait_for(
                        server_module.invoke_tool(args.tool, call_args, context=context),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    print(
                        (
                            f"error: tool call timed out after {timeout_seconds:.1f}s while starting storage-backed "
                            f"execution for '{args.tool}'. Verify storage/server config (Postgres reachability, "
                            "credentials, and SCRIBE_* settings), or raise --tool-timeout-seconds."
                        ),
                        file=sys.stderr,
                    )
                    return 2
            else:
                print(
                    (
                        f"error: tool call timed out after {timeout_seconds:.1f}s while starting storage-backed "
                        f"execution for '{args.tool}'. Verify storage/server config (Postgres reachability, "
                        "credentials, and SCRIBE_* settings), or raise --tool-timeout-seconds."
                    ),
                    file=sys.stderr,
                )
                return 2

    backend = getattr(server_module, "storage_backend", None)
    if backend and hasattr(backend, "get_session_by_transport"):
        session_record = await backend.get_session_by_transport(session_state.transport_session_id)
        if session_record:
            stored_session_id = _session_record_value(session_record, "session_id")
            stored_mode = _session_record_value(session_record, "mode")
            if stored_session_id:
                context["session_id"] = str(stored_session_id)
            if stored_mode:
                context["mode"] = str(stored_mode)

    if args.tool == "set_project":
        context["mode"] = "project"
        _refresh_context_after_set_project(
            context=context,
            result=result,
            repo_root=repo_root,
        )

    if args.tool == "read_file" and _result_is_success(result):
        tracked_path = _normalize_tracked_path(repo_root, call_args.get("path"))
        if tracked_path:
            if tracked_path not in tracked_reads:
                tracked_reads.append(tracked_path)
            context["files_read"] = tracked_reads

            session_id_value = context.get("session_id")
            await _rehydrate_file_reads(
                server_module=server_module,
                session_id=session_id_value if isinstance(session_id_value, str) else None,
                tracked_reads=[tracked_path],
            )

    session_state.context = context
    if not args.no_save_session:
        save_session_state(session_state)

    if isinstance(result, dict):
        result.setdefault("dispatch_path", context.get("dispatch_path", dispatch_path))
    _json_print(result, pretty=args.pretty)
    return 0


def _run_session_command(args: argparse.Namespace) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    if args.session_action == "reset":
        session_path = cli_session_state_path(args.name)
        if session_path.exists():
            session_path.unlink()
            print(f"Removed session state: {session_path}")
        else:
            print(f"Session state not found: {session_path}")
        return 0

    agent = _resolve_agent(getattr(args, "agent", None))
    session_state = load_session_state(args.name, repo_root, agent)
    _json_print(session_state.to_dict(), pretty=True)
    return 0


def _run_bootstrap_command(args: argparse.Namespace) -> int:
    from scribe_mcp.scripts.bootstrap_postgres import main as bootstrap_main

    bootstrap_args = list(args.bootstrap_args)
    if bootstrap_args and bootstrap_args[0] == "--":
        bootstrap_args = bootstrap_args[1:]
    return int(bootstrap_main(bootstrap_args))


def _run_plugins_command(args: argparse.Namespace) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    if args.plugins_action != "project-codex":
        raise ValueError(f"Unsupported plugins action: {args.plugins_action}")

    from scribe_mcp.scripts.project_codex_plugin import project_codex_plugin, render_codex_projection_error

    plugin_root = args.plugin_root or (repo_root / "plugins" / "codex")
    try:
        result = project_codex_plugin(
            plugin_root=plugin_root,
            codex_home=args.codex_home,
            config_path=args.config_path,
        )
    except (FileNotFoundError, OSError, TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {render_codex_projection_error(exc)}", file=sys.stderr)
        return 1

    _json_print(result, pretty=True)
    return 0


def _run_templates_command(args: argparse.Namespace) -> int:
    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    from scribe_mcp.template_engine import Jinja2TemplateEngine

    project_name = args.project_name or repo_root.name
    engine = Jinja2TemplateEngine(project_root=repo_root, project_name=project_name)

    if args.templates_action == "list":
        templates = engine.list_templates(extension=args.extension)
        payload = {
            "project_root": str(repo_root),
            "project_name": project_name,
            "extension": args.extension,
            "count": len(templates),
            "templates": [
                {
                    "template": template_name,
                    **engine.get_template_info(template_name),
                }
                for template_name in templates
            ],
        }
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print(f"Template stack for {project_name} ({len(templates)} templates):")
            for item in payload["templates"]:
                print(
                    f"- {item['template']} [{item['template_type']}]"
                    + (f" -> {item['path']}" if item.get("path") else "")
                )
        return 0

    if args.templates_action != "validate":
        raise ValueError(f"Unsupported templates action: {args.templates_action}")

    metadata = _load_optional_json_source(
        args.meta_json,
        file_path=args.meta_file,
        flag_name="--meta-json",
    )
    template_names = args.template or None
    payload = engine.validate_templates(
        template_names=template_names,
        extension=args.extension,
        metadata=metadata,
        render_check=args.render_check,
    )
    payload.update(
        {
            "project_root": str(repo_root),
            "project_name": project_name,
            "extension": args.extension,
        }
    )

    if args.json:
        _json_print(payload, pretty=True)
    else:
        mode_label = "syntax + render" if args.render_check else "syntax-only"
        print(
            f"Validated {payload['checked']} template(s) for {project_name}"
            f" using {mode_label} checks: "
            f"{payload['valid_count']} passed, {payload['invalid_count']} failed."
        )
        for item in payload["templates"]:
            status = "PASS" if item.get("valid") else "FAIL"
            print(f"- [{status}] {item['template']} [{item.get('template_type', 'unknown')}]")
            for error in item.get("errors", []):
                print(f"    error: {error}")
            for warning in item.get("warnings", []):
                print(f"    warning: {warning}")

    return 0 if payload.get("valid") else 1


def _run_logs_command(args: argparse.Namespace) -> int:
    from scribe_mcp.log_intelligence import build_report_from_path

    if args.logs_action != "analyze":
        raise ValueError(f"Unsupported logs action: {args.logs_action}")
    report = build_report_from_path(args.file, project=args.project)
    _json_print(report, pretty=True)
    return 0


async def _run_project_identity_command(args: argparse.Namespace) -> int:
    if args.project_identity_action != "preflight":
        raise ValueError(f"Unsupported project-identity action: {args.project_identity_action}")

    if bool(getattr(args, "apply", False)):
        payload = {
            "status_label": "BLOCK",
            "error_label": MUTATION_REJECTED_LABEL,
            "mutation_attempted": False,
            "mutation_authorized": False,
        }
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print(f"error: {MUTATION_REJECTED_LABEL}", file=sys.stderr)
        return 2

    if not bool(getattr(args, "dry_run", False)):
        payload = {
            "status_label": "BLOCK",
            "error_label": DRY_RUN_REQUIRED_LABEL,
            "mutation_attempted": False,
            "mutation_authorized": False,
        }
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print(f"error: {DRY_RUN_REQUIRED_LABEL}", file=sys.stderr)
        return 2

    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    from scribe_mcp.storage import create_storage_backend

    backend = create_storage_backend()
    if backend is None or not hasattr(backend, "preflight_project_identity_repair"):
        payload = {
            "status_label": "BLOCK",
            "error_label": "PROJECT_IDENTITY_PREFLIGHT_BACKEND_UNAVAILABLE",
            "mutation_attempted": False,
            "mutation_authorized": False,
        }
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print("error: PROJECT_IDENTITY_PREFLIGHT_BACKEND_UNAVAILABLE", file=sys.stderr)
        return 2

    try:
        report = await backend.preflight_project_identity_repair()
    finally:
        close = getattr(backend, "close", None)
        if close is not None:
            await close()

    payload = report.to_public_dict()
    if args.json:
        _json_print(payload, pretty=True)
        return 0 if payload.get("status_label") == "PASS" else 1

    print(f"status_label={payload['status_label']}")
    print(f"mutation_attempted={payload['mutation_attempted']}")
    print(f"mutation_authorized={payload['mutation_authorized']}")
    print(f"blocked_state_count={payload['blocked_state_count']}")
    print(f"redaction_status_label={payload['redaction_status_label']}")
    return 0 if payload.get("status_label") == "PASS" else 1


async def _run_affected_row_inventory_command(args: argparse.Namespace) -> int:
    if args.affected_row_inventory_action != "preflight":
        raise ValueError(f"Unsupported affected-row-inventory action: {args.affected_row_inventory_action}")

    if getattr(args, "apply", False) or not getattr(args, "dry_run", False):
        payload = mutation_rejected_report().to_public_dict()
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print(f"error: {payload['labels'][0]}", file=sys.stderr)
        return 2

    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)

    from scribe_mcp.storage import create_storage_backend

    backend = create_storage_backend()
    if backend is None or not hasattr(backend, "affected_row_referential_inventory_readonly"):
        payload = storage_backend_unavailable_report().to_public_dict()
        if args.json:
            _json_print(payload, pretty=True)
        else:
            print("error: BLOCKED_STORAGE_BACKEND_UNAVAILABLE", file=sys.stderr)
        return 2

    try:
        report = await backend.affected_row_referential_inventory_readonly(
            target_binding_status_label=args.target_binding_status_label,
            selected_context_readback_status_label=args.selected_context_readback_status_label,
        )
    finally:
        close = getattr(backend, "close", None)
        if close is not None:
            await close()

    payload = report.to_public_dict()
    pass_labels = {
        "INVENTORY_NO_AFFECTED_ROWS",
        "INVENTORY_REPAIR_NOT_REQUIRED",
        "INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL",
    }
    if args.json:
        _json_print(payload, pretty=True)
        return 0 if payload.get("status_label") in pass_labels else 1

    print(f"status_label={payload['status_label']}")
    print(f"mutation_attempted={payload['mutation_attempted']}")
    print(f"mutation_authorized={payload['mutation_authorized']}")
    print(f"blocked_state_count={payload['blocked_state_count']}")
    print(f"redaction_status_label={payload['redaction_status_label']}")
    return 0 if payload.get("status_label") in pass_labels else 1


def _run_install_command(args: argparse.Namespace) -> int:
    from scribe_mcp.install_wizard import build_install_plan, execute_install_commit, execute_projection_opt_in
    from scribe_mcp.utils.error_handler import sanitize_error_message

    repo_root = _discover_repo_root(args.repo_root)
    _prepare_environment(repo_root)
    try:
        if args.commit:
            payload = asyncio.run(execute_install_commit(
                repo_root=repo_root,
                profile=args.profile,
                commit=bool(args.commit),
                yes=bool(args.yes),
                allow_advanced_profile=bool(args.allow_advanced_profile),
                dangerous_overwrite_secrets=bool(args.dangerous_overwrite_secrets),
            ))
            if payload.get("ok") and bool(args.project_codex):
                payload["projection"] = execute_projection_opt_in(repo_root=repo_root)
            _json_print(payload, pretty=True)
            return 0 if payload.get("ok") else 1
        plan = build_install_plan(
            repo_root=repo_root,
            profile=args.profile,
            include_advanced_profile=bool(args.allow_advanced_profile),
        )
    except ValueError as exc:
        print(f"error: {sanitize_error_message(str(exc))}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {sanitize_error_message(f'install failed: {exc}')}", file=sys.stderr)
        return 2
    _json_print(plan.to_dict(), pretty=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    normalized_argv = _normalize_argv(argv or sys.argv[1:])
    parser = _build_parser()
    args, unknown = parser.parse_known_args(normalized_argv)

    if args.command == "call":
        passthrough_options = _parse_passthrough_options(unknown)
    else:
        if unknown:
            parser.error(f"Unexpected arguments: {' '.join(unknown)}")
        passthrough_options = {}

    if args.command == "session":
        return _run_session_command(args)

    if args.command == "tools":
        repo_root = _discover_repo_root(args.repo_root)
        _prepare_environment(repo_root)
        return asyncio.run(_run_tools_command(args))

    if args.command == "bootstrap":
        return _run_bootstrap_command(args)

    if args.command == "plugins":
        return _run_plugins_command(args)

    if args.command == "templates":
        return _run_templates_command(args)
    if args.command == "logs":
        return _run_logs_command(args)
    if args.command == "install":
        return _run_install_command(args)
    if args.command == "project-identity":
        return asyncio.run(_run_project_identity_command(args))
    if args.command == "affected-row-inventory":
        return asyncio.run(_run_affected_row_inventory_command(args))

    return asyncio.run(_run_call_command(args, passthrough_options))


if __name__ == "__main__":
    raise SystemExit(main())
