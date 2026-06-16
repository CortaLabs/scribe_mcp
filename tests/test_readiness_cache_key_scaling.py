"""Tests for Package A: O(1) cache-key construction in _research_dir_signatures.

Regression guards that make O(N) filesystem ops un-reintroducible.
All assertions are on operation *counts*, never on wall-clock time.

Key assertions
--------------
1. ``glob`` is NEVER called inside ``_research_dir_signatures`` for any N.
2. ``stat`` call count is O(#research_dirs), NOT O(N research files).
3. Cache *hits* on a second ``collect_managed_doc_quality_state`` call (key stable).
4. Adding a research file *busts* the cache key (correctness).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src layout is importable when running standalone
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"
for _p in (_SRC_ROOT, _SRC_ROOT / "scribe_mcp"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scribe_mcp.readiness import (
    _collect_research_dirs,
    _managed_doc_quality_cache_key,
    _research_dir_signatures,
    clear_managed_doc_quality_state_cache,
    collect_managed_doc_quality_state,
)
from _furnace_fixture import build_furnace_project, patch_fs_ops

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT = "test-agent"

# Number of research files for the two scale points
N_SMALL = 5
N_LARGE = 300


def _snap_stat_count(counters: dict[str, int]) -> int:
    return counters["stat"]


# ---------------------------------------------------------------------------
# Test 1: glob is NEVER called inside _research_dir_signatures for any N
# ---------------------------------------------------------------------------


def test_no_glob_inside_research_dir_signatures_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_research_dir_signatures must not call glob for N=5 research files."""
    project = build_furnace_project(tmp_path, n_research_files=N_SMALL)
    doc_paths = [Path(v) for v in project["docs"].values() if v.endswith(".md")]

    counters = patch_fs_ops(monkeypatch)
    _research_dir_signatures(project.get("docs_dir"), doc_paths)

    assert counters["glob"] == 0, (
        f"glob was called {counters['glob']} time(s) inside _research_dir_signatures "
        f"for N={N_SMALL}; expected 0 (O(1) dir-sentinel design)"
    )


def test_no_glob_inside_research_dir_signatures_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_research_dir_signatures must not call glob for N=300 research files."""
    project = build_furnace_project(tmp_path, n_research_files=N_LARGE)
    doc_paths = [Path(v) for v in project["docs"].values() if v.endswith(".md")]

    counters = patch_fs_ops(monkeypatch)
    _research_dir_signatures(project.get("docs_dir"), doc_paths)

    assert counters["glob"] == 0, (
        f"glob was called {counters['glob']} time(s) inside _research_dir_signatures "
        f"for N={N_LARGE}; expected 0 (O(1) dir-sentinel design)"
    )


# ---------------------------------------------------------------------------
# Test 2: stat count is O(#research_dirs), NOT O(N research files)
# ---------------------------------------------------------------------------


def test_stat_count_bounded_independent_of_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stat call count must not grow with N research files (bounded by #research_dirs).

    We use two separate tmp directories so the projects are independent.
    """
    tmp_small = tmp_path / "small"
    tmp_large = tmp_path / "large"
    tmp_small.mkdir()
    tmp_large.mkdir()

    project_small = build_furnace_project(tmp_small, n_research_files=N_SMALL)
    project_large = build_furnace_project(tmp_large, n_research_files=N_LARGE)

    doc_paths_small = [Path(v) for v in project_small["docs"].values() if v.endswith(".md")]
    doc_paths_large = [Path(v) for v in project_large["docs"].values() if v.endswith(".md")]

    # Count stat calls for N=5
    counters_small: dict[str, int] = {"stat": 0, "glob": 0, "rglob": 0}
    original_stat = Path.stat

    def counting_stat_small(self: Path, *, follow_symlinks: bool = True):  # type: ignore[no-untyped-def]
        counters_small["stat"] += 1
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", counting_stat_small)
    _research_dir_signatures(project_small.get("docs_dir"), doc_paths_small)
    stat_small = counters_small["stat"]
    monkeypatch.undo()

    # Count stat calls for N=300
    counters_large: dict[str, int] = {"stat": 0, "glob": 0, "rglob": 0}

    def counting_stat_large(self: Path, *, follow_symlinks: bool = True):  # type: ignore[no-untyped-def]
        counters_large["stat"] += 1
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", counting_stat_large)
    _research_dir_signatures(project_large.get("docs_dir"), doc_paths_large)
    stat_large = counters_large["stat"]
    monkeypatch.undo()

    # Both projects have exactly 1 research directory and 4 managed docs.
    # The stat count must be IDENTICAL between N=5 and N=300 — it must not scale
    # with the number of research files.
    #
    # The actual count is:
    #   _collect_research_dirs: 1 stat per resolve() on docs_dir/research path
    #                         + 1 stat per resolve() on each managed-doc path (4 docs)
    #   _dir_signature:         1 stat per research directory
    # Total = 1 + 4 + 1 = 6 for this furnace project.  This is O(#managed_docs +
    # #research_dirs), NOT O(N research files) — which is the invariant we protect.
    assert stat_small == stat_large, (
        f"stat count differs between N={N_SMALL} ({stat_small}) and "
        f"N={N_LARGE} ({stat_large}). "
        "This indicates O(N) stat calls — the O(1) dir-sentinel invariant is broken."
    )
    # Absolute bound: a constant independent of N.
    # Allow up to (4 managed docs * 2 + 4 research dirs) = 12 as a generous ceiling;
    # the actual observed value is 6 for 4 managed docs + 1 research dir.
    # If this grows with N, the equality assertion above will already catch it.
    assert stat_large <= 12, (
        f"stat count {stat_large} exceeds absolute constant bound 12 for N={N_LARGE} "
        "files with 1 research directory and 4 managed docs."
    )


# ---------------------------------------------------------------------------
# Test 3: cache hit on second call (key stability)
# ---------------------------------------------------------------------------


def test_cache_hit_on_second_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second collect_managed_doc_quality_state call must hit the cache (no recompute)."""
    clear_managed_doc_quality_state_cache()
    project = build_furnace_project(tmp_path, n_research_files=N_SMALL)

    # Track calls to the uncached function via monkeypatching the module
    import scribe_mcp.readiness as readiness_mod

    call_count = {"n": 0}
    original_uncached = readiness_mod._collect_managed_doc_quality_state_uncached

    def spy_uncached(proj):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        return original_uncached(proj)

    monkeypatch.setattr(readiness_mod, "_collect_managed_doc_quality_state_uncached", spy_uncached)

    # First call should miss cache and invoke uncached
    collect_managed_doc_quality_state(project)
    assert call_count["n"] == 1, "Expected first call to invoke _collect_managed_doc_quality_state_uncached"

    # Second call with identical project must hit cache (no recompute)
    collect_managed_doc_quality_state(project)
    assert call_count["n"] == 1, (
        "Second call with unchanged project should hit the cache, "
        "but _collect_managed_doc_quality_state_uncached was called again."
    )

    clear_managed_doc_quality_state_cache()


# ---------------------------------------------------------------------------
# Test 4: adding a research file busts the cache key (correctness)
# ---------------------------------------------------------------------------


def test_adding_research_file_busts_cache_key(tmp_path: Path) -> None:
    """The cache key must change when a research file is added to the research dir."""
    project = build_furnace_project(tmp_path, n_research_files=N_SMALL)

    key_before = _managed_doc_quality_cache_key(project)

    # Add one research file
    doc_paths_before = [Path(v) for v in project["docs"].values() if v.endswith(".md")]
    research_dir = _collect_research_dirs(project.get("docs_dir"), doc_paths_before)
    assert research_dir, "Expected at least one research directory"
    first_research_dir = next(iter(sorted(research_dir, key=str)))
    new_file = first_research_dir / f"RESEARCH_{N_SMALL + 1:04d}_new.md"
    new_file.write_text("# New research\n\nAdded after key snapshot.\n", encoding="utf-8")

    key_after = _managed_doc_quality_cache_key(project)

    assert key_before != key_after, (
        "Cache key must change when a research file is added; "
        "directory-level sentinel (mtime/nlink) did not capture the add."
    )

    # Clean up so we do not affect other tests
    new_file.unlink()


# ---------------------------------------------------------------------------
# Test 5: existing managed-doc quality targets not affected
# (4 managed-doc per-file signatures in targets tuple stay unchanged by A)
# ---------------------------------------------------------------------------


def test_managed_doc_targets_not_affected_by_research_change(tmp_path: Path) -> None:
    """Changing a research file must not change the managed-doc targets portion of the key."""
    project = build_furnace_project(tmp_path, n_research_files=N_SMALL)

    key_before = _managed_doc_quality_cache_key(project)
    # targets portion is index 2 of the key tuple
    targets_before = key_before[2]

    # Modify a research file (not a managed doc)
    doc_paths = [Path(v) for v in project["docs"].values() if v.endswith(".md")]
    research_dirs = _collect_research_dirs(project.get("docs_dir"), doc_paths)
    first_research_dir = next(iter(sorted(research_dirs, key=str)))
    research_files = sorted(first_research_dir.glob("*.md"))
    assert research_files, "Expected at least one research file in the furnace project"
    research_files[0].write_text("# Modified content\n", encoding="utf-8")

    key_after = _managed_doc_quality_cache_key(project)
    targets_after = key_after[2]

    # The managed-doc targets tuple (index 2) must be identical — only the
    # research signatures portion (index 4) changes.
    assert targets_before == targets_after, (
        "Managed-doc targets signatures changed when a research file was modified; "
        "Package A must not affect the 4 managed-doc per-file signature tuples."
    )
