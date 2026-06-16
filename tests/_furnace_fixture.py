"""Shared furnace fixture for scribe_scale_cache_arch package tests.

Creates a synthetic Scribe project with N research files and 4 managed docs
under a temp directory.  Exposes filesystem-op counters via monkeypatching so
Wave-2 packages (B, C, D) can import and reuse without touching conftest.py.

Usage
-----
from _furnace_fixture import build_furnace_project, patch_fs_ops

def test_something(tmp_path, monkeypatch):
    project = build_furnace_project(tmp_path, n_research_files=50)
    counters = patch_fs_ops(monkeypatch)
    # ... exercise the code under test ...
    assert counters["stat"] <= BOUNDED_CONSTANT
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Furnace project builder
# ---------------------------------------------------------------------------

_MANAGED_DOC_NAMES = {
    "architecture": "ARCHITECTURE_GUIDE.md",
    "phase_plan": "PHASE_PLAN.md",
    "checklist": "CHECKLIST.md",
    "progress_log": "PROGRESS_LOG.md",
}

_MANAGED_DOC_MINIMAL_CONTENT = """\
---
status: draft
---
# {title}

Minimal managed doc for furnace testing.
"""


def build_furnace_project(
    tmp_path: Path,
    *,
    n_research_files: int = 10,
    research_subdir: str = "research",
) -> dict[str, Any]:
    """Build a synthetic Scribe project structure and return a project dict.

    Creates:
      tmp_path/
        project_root/
          PROGRESS_LOG.md
          research/          <- research dir
            doc_001.md
            ...
            doc_N.md
          ARCHITECTURE_GUIDE.md
          PHASE_PLAN.md
          CHECKLIST.md

    Parameters
    ----------
    tmp_path:
        Base temp directory (pytest's tmp_path fixture or any writable dir).
    n_research_files:
        Number of synthetic ``*.md`` files to create in the research directory.
    research_subdir:
        Name of the research subdirectory (default: ``"research"``).

    Returns
    -------
    dict
        A project mapping compatible with ``collect_managed_doc_quality_state``
        and ``_managed_doc_quality_cache_key``.
    """
    root = tmp_path / "furnace_project"
    root.mkdir(parents=True, exist_ok=True)

    # Create managed docs
    docs: dict[str, str] = {}
    for key, filename in _MANAGED_DOC_NAMES.items():
        path = root / filename
        path.write_text(
            _MANAGED_DOC_MINIMAL_CONTENT.format(title=filename.replace(".md", "")),
            encoding="utf-8",
        )
        docs[key] = str(path)

    # Create research directory with N synthetic files
    research_dir = root / research_subdir
    research_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_research_files + 1):
        (research_dir / f"RESEARCH_{i:04d}.md").write_text(
            f"# Research doc {i}\n\nSynthetic content.\n",
            encoding="utf-8",
        )

    return {
        "name": "furnace_project",
        "root": str(root),
        "docs_dir": str(root),
        "docs": docs,
        "current_phase": None,
    }


# ---------------------------------------------------------------------------
# Filesystem-op counters (monkeypatch helpers)
# ---------------------------------------------------------------------------


def patch_fs_ops(monkeypatch: Any) -> dict[str, int]:
    """Monkeypatch Path.stat and Path.glob to count calls; return the counter dict.

    The returned dict is mutated in-place as calls happen.  Import and call
    this helper *before* exercising the code under test.

    Counted keys
    ------------
    ``stat``  : calls to ``Path.stat``
    ``glob``  : calls to ``Path.glob``
    ``rglob`` : calls to ``Path.rglob``

    Example
    -------
    counters = patch_fs_ops(monkeypatch)
    build_cache_key(project)
    assert counters["glob"] == 0          # no glob calls inside key builder
    assert counters["stat"] <= 10         # bounded constant
    """
    counters: dict[str, int] = {"stat": 0, "glob": 0, "rglob": 0}

    original_stat = Path.stat
    original_glob = Path.glob
    original_rglob = Path.rglob

    def counting_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        counters["stat"] += 1
        return original_stat(self, follow_symlinks=follow_symlinks)

    def counting_glob(self: Path, pattern: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        counters["glob"] += 1
        return original_glob(self, pattern, **kwargs)

    def counting_rglob(self: Path, pattern: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        counters["rglob"] += 1
        return original_rglob(self, pattern, **kwargs)

    monkeypatch.setattr(Path, "stat", counting_stat)
    monkeypatch.setattr(Path, "glob", counting_glob)
    monkeypatch.setattr(Path, "rglob", counting_rglob)
    return counters
