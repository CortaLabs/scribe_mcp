from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import subprocess
from pathlib import Path
from typing import Literal


ContextSource = Literal["manual", "pyproject", "git_tag", "git_commit", "unknown"]
ContextConfidence = Literal["exact", "partial", "unknown"]


@dataclass(frozen=True)
class ObservedContext:
    value: str
    source: ContextSource
    commit: str | None
    dirty: bool | None
    observed_at: str
    confidence: ContextConfidence



def unknown_context(*, observed_at: str | None = None) -> ObservedContext:
    return ObservedContext(
        value="unknown",
        source="unknown",
        commit=None,
        dirty=None,
        observed_at=observed_at or _utc_now_iso(),
        confidence="unknown",
    )



def resolve_observed_context(
    *,
    repo_root: Path | None = None,
    pyproject_path: Path | None = None,
    manual_value: str | None = None,
    observed_at: str | None = None,
) -> ObservedContext:
    stamp = observed_at or _utc_now_iso()

    if manual_value and manual_value.strip():
        return ObservedContext(
            value=manual_value.strip(),
            source="manual",
            commit=_maybe_git_commit(repo_root),
            dirty=_maybe_git_dirty(repo_root),
            observed_at=stamp,
            confidence="exact",
        )

    project_version = _read_pyproject_version(pyproject_path)
    if project_version:
        return ObservedContext(
            value=project_version,
            source="pyproject",
            commit=_maybe_git_commit(repo_root),
            dirty=_maybe_git_dirty(repo_root),
            observed_at=stamp,
            confidence="exact",
        )

    commit = _maybe_git_commit(repo_root)
    dirty = _maybe_git_dirty(repo_root)
    if commit:
        return ObservedContext(
            value=commit,
            source="git_commit",
            commit=commit,
            dirty=dirty,
            observed_at=stamp,
            confidence="partial",
        )

    return unknown_context(observed_at=stamp)



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")



def _read_pyproject_version(pyproject_path: Path | None) -> str | None:
    path = pyproject_path or Path("pyproject.toml")
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("version"):
            _, _, rhs = stripped.partition("=")
            value = rhs.strip().strip('"').strip("'")
            return value or None
    return None



def _maybe_git_commit(repo_root: Path | None) -> str | None:
    return _run_git(repo_root, ["rev-parse", "--short", "HEAD"])



def _maybe_git_dirty(repo_root: Path | None) -> bool | None:
    out = _run_git(repo_root, ["status", "--porcelain"])
    if out is None:
        return None
    return bool(out.strip())



def _run_git(repo_root: Path | None, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root) if repo_root else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
