"""Sentinel logging helpers (JSONL + MD) with bounded locking."""

from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp.shared.execution_context import ExecutionContext
from scribe_mcp.utils.files import ensure_parent_sync, file_lock, FileLockError


_JSONL_FILES = {
    "sentinel": "sentinel.jsonl",
    "bug": "bug.jsonl",
    "security": "security.jsonl",
}


def _repo_id(repo_root: str) -> str:
    return sha256(repo_root.encode("utf-8")).hexdigest()


def _sentinel_dir(context: ExecutionContext) -> Path:
    return Path(context.repo_root) / ".scribe" / "sentinel" / (context.sentinel_day or "unknown")


def _bounded_append(path: Path, line: str, *, repo_root: Path, timeout_seconds: float = 0.25) -> None:
    ensure_parent_sync(path, repo_root=repo_root, context={"component": "logs", "op": "sentinel"})
    deadline = time.time() + timeout_seconds
    while True:
        try:
            with file_lock(path, mode="a+", timeout=timeout_seconds, repo_root=repo_root) as handle:
                handle.write(line)
                if not line.endswith("\n"):
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            return
        except FileLockError:
            if time.time() >= deadline:
                raise
            time.sleep(0.05)


def _next_case_id(path: Path, prefix: str, *, repo_root: Path) -> str:
    ensure_parent_sync(path, repo_root=repo_root)
    with file_lock(path, mode="a+", timeout=0.25, repo_root=repo_root) as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        read_size = min(size, 65536)
        handle.seek(max(0, size - read_size))
        tail = handle.read().splitlines()
        last_seq = 0
        for raw in reversed(tail):
            try:
                entry = json.loads(raw)
            except Exception:
                continue
            case_id = entry.get("data", {}).get("case_id")
            if isinstance(case_id, str) and case_id.startswith(prefix):
                suffix = case_id.replace(prefix, "")
                if suffix.isdigit():
                    last_seq = int(suffix)
                    break
        next_seq = last_seq + 1
        return f"{prefix}{next_seq:04d}"


def append_sentinel_event(
    context: ExecutionContext,
    *,
    event_type: str,
    data: Dict[str, Any],
    log_type: str = "sentinel",
    include_md: bool = True,
) -> None:
    sentinel_dir = _sentinel_dir(context)
    jsonl_name = _JSONL_FILES.get(log_type, _JSONL_FILES["sentinel"])
    jsonl_path = sentinel_dir / jsonl_name
    md_path = sentinel_dir / "SENTINEL_LOG.md"

    payload = {
        "event_type": event_type,
        "timestamp_utc": context.timestamp_utc,
        "sentinel_day": context.sentinel_day,
        "repo_id": _repo_id(context.repo_root),
        "execution_id": context.execution_id,
        "agent_identity": {
            "agent_kind": context.agent_identity.agent_kind,
            "model": context.agent_identity.model,
            "instance_id": context.agent_identity.instance_id,
            "sub_id": context.agent_identity.sub_id,
            "display_name": context.agent_identity.display_name,
        },
        "intent": context.intent,
        "affected_dev_projects": list(context.affected_dev_projects),
        "data": data,
    }

    line = json.dumps(payload, ensure_ascii=True)

    repo_root = Path(context.repo_root)
    ensure_parent_sync(jsonl_path, repo_root=repo_root, context={"component": "logs", "op": "sentinel"})
    _bounded_append(jsonl_path, line, repo_root=repo_root)

    if include_md:
        md_line = (
            f"[{context.timestamp_utc}] "
            f"[exec:{context.execution_id}] "
            f"[event:{event_type}] "
            f"[agent:{context.agent_identity.instance_id}] "
            f"{context.intent}"
        )
        ensure_parent_sync(md_path, repo_root=repo_root, context={"component": "logs", "op": "sentinel"})
        _bounded_append(md_path, md_line, repo_root=repo_root)


def log_scope_violation(context: ExecutionContext, *, reason: str, tool_name: str) -> None:
    append_sentinel_event(
        context,
        event_type="scope_violation",
        data={"reason": reason, "tool_name": tool_name},
        log_type="sentinel",
        include_md=True,
    )


def append_case_event(
    context: ExecutionContext,
    *,
    kind: str,
    event_type: str,
    data: Dict[str, Any],
    include_md: bool = True,
) -> str:
    sentinel_dir = _sentinel_dir(context)
    jsonl_name = _JSONL_FILES["bug"] if kind == "BUG" else _JSONL_FILES["security"]
    jsonl_path = sentinel_dir / jsonl_name
    md_path = sentinel_dir / "SENTINEL_LOG.md"

    prefix = f"{kind}-{context.sentinel_day}-"
    case_id = _next_case_id(jsonl_path, prefix, repo_root=Path(context.repo_root))
    data = dict(data)
    data["case_id"] = case_id

    payload = {
        "event_type": event_type,
        "timestamp_utc": context.timestamp_utc,
        "sentinel_day": context.sentinel_day,
        "repo_id": _repo_id(context.repo_root),
        "execution_id": context.execution_id,
        "agent_identity": {
            "agent_kind": context.agent_identity.agent_kind,
            "model": context.agent_identity.model,
            "instance_id": context.agent_identity.instance_id,
            "sub_id": context.agent_identity.sub_id,
            "display_name": context.agent_identity.display_name,
        },
        "intent": context.intent,
        "affected_dev_projects": list(context.affected_dev_projects),
        "data": data,
    }

    line = json.dumps(payload, ensure_ascii=True)
    _bounded_append(jsonl_path, line, repo_root=Path(context.repo_root))

    if include_md:
        md_line = (
            f"[{context.timestamp_utc}] "
            f"[exec:{context.execution_id}] "
            f"[event:{event_type}] "
            f"[case:{case_id}] "
            f"[agent:{context.agent_identity.instance_id}] "
            f"{context.intent}"
        )
        _bounded_append(md_path, md_line, repo_root=Path(context.repo_root))

    return case_id
