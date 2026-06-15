"""Non-mutating public-safe projection/readiness for Scribe logs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Literal

from scribe_mcp import server as server_module
from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.progress_log_parser import Entry, parse_lines
from scribe_mcp.server import app
from scribe_mcp.shared.logging_utils import (
    ProjectResolutionError,
    compose_log_line,
    normalize_metadata,
    resolve_log_definition,
    resolve_logging_context,
)
from scribe_mcp.shared.path_policy import (
    PathPolicyConfig,
    PathPolicyResult,
    PathPolicyViolation,
    load_path_policy,
    looks_like_local_absolute_path,
    render_projection,
)
from scribe_mcp.tool_contracts import read_only_local_tool

LogType = Literal["progress", "doc_updates"]
ProjectionMode = Literal["readiness", "render"]

_LOCAL_PATH_TOKEN_RE = re.compile(r"(?:(?<=\s)|^)(?:/[^\s;|]+|[A-Za-z]:[\\/][^\s;|]+)")


@app.tool(
    **read_only_local_tool(
        title="Progress Log Projection",
        tags=("logs", "projection", "read-only"),
    )
)
async def progress_log_projection(
    agent: str,
    project: str | None = None,
    log_type: LogType = "progress",
    mode: ProjectionMode = "readiness",
) -> Dict[str, Any]:
    """Return public-safe projection/readiness without mutating canonical logs."""

    if log_type not in ("progress", "doc_updates"):
        return _error_response("unsupported_log_type")
    if mode not in ("readiness", "render"):
        return _error_response("unsupported_mode")

    try:
        context = await resolve_logging_context(
            tool_name="progress_log_projection",
            server_module=server_module,
            agent_id=agent,
            explicit_project=project,
            require_project=True,
            allow_cross_project_read=True,
        )
    except ProjectResolutionError as exc:
        return {
            "ok": False,
            "readiness": "failed",
            "error": "Project could not be resolved.",
            "issue_code": "project_resolution_failed",
            "canonical_mutated": False,
            "issue_count": 1,
            "issues": [
                {
                    "line_number": None,
                    "metadata_key": "project",
                    "issue_code": "project_resolution_failed",
                    "safe_descriptor": "project_unresolved",
                }
            ],
            "contains_raw_local_paths": False,
            "recent_projects": list(exc.recent_projects),
        }

    assert context.project is not None
    project_data = context.project
    log_path, _definition = resolve_log_definition(project_data, log_type)
    log_ref = _safe_log_ref(log_path, project_data)
    if not log_path.exists():
        payload: Dict[str, Any] = {
            "ok": True,
            "readiness": "ready",
            "log_ref": log_ref,
            "log_type": log_type,
            "canonical_mutated": False,
            "issue_count": 0,
            "issues": [],
            "contains_raw_local_paths": False,
        }
        if mode == "render":
            payload["projected_lines"] = []
        return payload

    before_bytes = log_path.read_bytes()
    lines = before_bytes.decode("utf-8", errors="replace").splitlines()

    try:
        policy = _load_policy(project_data)
    except ValueError:
        return {
            "ok": False,
            "readiness": "failed",
            "log_ref": log_ref,
            "log_type": log_type,
            "canonical_mutated": False,
            "issue_count": 1,
            "issues": [
                {
                    "line_number": None,
                    "metadata_key": "path_policy",
                    "issue_code": "path_policy_config_invalid",
                    "safe_descriptor": "invalid_public_projection_policy",
                }
            ],
            "contains_raw_local_paths": True,
        }

    entries = parse_lines(lines)
    issues: list[Dict[str, Any]] = []
    projected_by_line: dict[int, str] = {}

    for entry in entries:
        result = render_projection(entry.meta, policy=policy)
        issues.extend(_issue_payloads(result.violations, line_number=entry.line_no))
        projected_line = _project_entry(entry, result)
        if _contains_raw_local_path(projected_line):
            issues.append(
                {
                    "line_number": entry.line_no,
                    "metadata_key": "_line",
                    "issue_code": "raw_local_path_in_projected_line",
                    "safe_descriptor": "local_absolute_path",
                    "value_sha256_prefix": hashlib.sha256(projected_line.encode("utf-8")).hexdigest()[:12],
                }
            )
        else:
            projected_by_line[entry.line_no] = projected_line

    after_bytes = log_path.read_bytes()
    canonical_mutated = before_bytes != after_bytes
    contains_raw_local_paths = bool(issues)
    payload = {
        "ok": not contains_raw_local_paths and not canonical_mutated,
        "readiness": "ready" if not contains_raw_local_paths and not canonical_mutated else "failed",
        "log_ref": log_ref,
        "log_type": log_type,
        "canonical_mutated": False,
        "issue_count": len(issues),
        "issues": issues,
        "contains_raw_local_paths": contains_raw_local_paths,
    }
    if canonical_mutated:
        payload["issues"].append(
            {
                "line_number": None,
                "metadata_key": "canonical_log",
                "issue_code": "canonical_mutation_detected",
                "safe_descriptor": "canonical_bytes_changed",
            }
        )
        payload["issue_count"] = len(payload["issues"])
    if mode == "render":
        payload["projected_lines"] = [
            projected_by_line.get(line_number, line)
            for line_number, line in enumerate(lines, start=1)
            if line_number in projected_by_line or not _contains_raw_local_path(line)
        ]
    return payload


def _load_policy(project: Dict[str, Any]) -> PathPolicyConfig:
    repo_root = Path(str(project.get("root") or "")).resolve()
    repo_config = RepoDiscovery.load_config(repo_root, seed_if_missing=False)
    return load_path_policy(repo_config, project)


def _project_entry(entry: Entry, result: PathPolicyResult) -> str:
    meta_pairs = normalize_metadata(result.mapped)
    return compose_log_line(
        emoji=entry.emoji,
        timestamp=entry.timestamp,
        agent=entry.agent,
        project_name=entry.project,
        message=entry.message,
        meta_pairs=meta_pairs,
    )


def _issue_payloads(
    violations: tuple[PathPolicyViolation, ...],
    *,
    line_number: int,
) -> list[Dict[str, Any]]:
    return [
        {
            "line_number": line_number,
            "metadata_key": _safe_metadata_key(violation.key),
            "issue_code": violation.reason,
            "safe_descriptor": violation.safe_descriptor,
            "value_sha256_prefix": violation.value_sha256_prefix,
        }
        for violation in violations
    ]


def _safe_metadata_key(key: str) -> str:
    if looks_like_local_absolute_path(key) or "/" in key or "\\" in key:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        return f"unsafe_key:{digest}"
    return key


def _contains_raw_local_path(value: str) -> bool:
    if looks_like_local_absolute_path(value):
        return True
    for match in _LOCAL_PATH_TOKEN_RE.finditer(value):
        if looks_like_local_absolute_path(match.group(0)):
            return True
    return False


def _safe_log_ref(log_path: Path, project: Dict[str, Any]) -> str:
    try:
        root = Path(str(project.get("root") or "")).resolve()
        return log_path.resolve().relative_to(root).as_posix()
    except Exception:
        digest = hashlib.sha256(str(log_path).encode("utf-8")).hexdigest()[:12]
        return f"log:{digest}"


def _error_response(issue_code: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "readiness": "failed",
        "log_ref": "log:unresolved",
        "log_type": "invalid",
        "canonical_mutated": False,
        "issue_count": 1,
        "issues": [
            {
                "line_number": None,
                "metadata_key": "request",
                "issue_code": issue_code,
                "safe_descriptor": "invalid_projection_request",
            }
        ],
        "contains_raw_local_paths": False,
    }
