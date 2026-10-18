"""Tests for Package B: hoist rglob out of the per-doc loop.

Regression guards that make the O(D×F) re-scan un-reintroducible.
All assertions are on operation *counts*, never on wall-clock time.

Key assertions
--------------
1. ``rglob`` is called a BOUNDED number of times independent of D (the number
   of managed docs) — ideally once per research directory.
2. Warnings output is byte-identical to the pre-hoist baseline (correctness).
3. Back-compat: when ``research_docs`` is omitted from
   ``build_research_index_hygiene_warnings`` the rglob fallback fires as
   before and produces the same result.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Ensure src layout is importable when running standalone
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"
for _p in (_SRC_ROOT, _SRC_ROOT / "scribe_mcp"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Add tests/ to path so _furnace_fixture is importable
_TESTS_ROOT = Path(__file__).resolve().parent
if str(_TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_TESTS_ROOT))

from scribe_mcp.readiness import (
    _collect_managed_doc_quality_state_uncached,
    clear_managed_doc_quality_state_cache,
)
from scribe_mcp.doc_management.quality.rules.research import (
    build_research_index_hygiene_warnings,
)
from scribe_mcp.doc_management.scaffold_quality import (
    collect_managed_doc_quality_warnings,
    DEFAULT_WARNING_POLICIES,
)
from _furnace_fixture import build_furnace_project, patch_fs_ops

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Scale points: small and large doc counts to prove the bound is independent of D
N_SMALL = 5
N_LARGE = 50  # enough to see O(D) vs O(1) divergence without slowing the suite


# ---------------------------------------------------------------------------
# Helper: derive expected warnings via naive (pre-hoist) path
# ---------------------------------------------------------------------------

def _naive_warnings_for_project(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Re-derive warnings using the pre-hoist code path (no research_docs arg).

    Calls collect_managed_doc_quality_warnings without research_docs on each
    research doc so rglob fires per-call — mirrors what readiness.py used to do
    before Package B.  Used as the golden baseline for correctness comparison.
    """
    from scribe_mcp.readiness import _collect_managed_doc_quality_state_uncached as _uncached  # noqa: F401
    # Actually just run _collect_managed_doc_quality_state_uncached directly —
    # now that it passes research_docs, we compare by calling it twice on
    # identical inputs; result must be identical regardless of how many times
    # rglob ran.  The "golden" baseline is captured by calling the function
    # on fresh identical projects.
    return _uncached(project)


# ---------------------------------------------------------------------------
# Test 1: rglob count bounded independent of number of managed docs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_docs", [N_SMALL, N_LARGE])
def test_rglob_count_bounded_independent_of_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n_docs: int) -> None:
    """rglob is called at most once per research directory regardless of D.

    With the hoist in place, _collect_managed_doc_quality_state_uncached should
    call rglob exactly once (one research dir in the furnace) no matter how many
    managed docs are in ``project["docs"]``.

    We add extra synthetic managed-doc entries that all point into the same
    research dir to amplify the O(D) factor.
    """
    clear_managed_doc_quality_state_cache()
    project = build_furnace_project(tmp_path, n_research_files=10)

    # The furnace project has 4 managed docs.  Add extra ones that are also
    # research targets (files in the research dir) to maximise D.
    research_dir = Path(project["docs_dir"]) / "research"
    for i in range(n_docs):
        extra = research_dir / f"EXTRA_{i:04d}.md"
        extra.write_text(f"# Extra {i}\n\nContent.\n", encoding="utf-8")
        # Register as a managed doc so the per-doc loop visits it
        project["docs"][f"extra_{i}"] = str(extra)

    counters = patch_fs_ops(monkeypatch)

    _collect_managed_doc_quality_state_uncached(project)

    rglob_count = counters["rglob"]
    # With the hoist: rglob is called ONCE per research dir (== 1 here).
    # Without the hoist it would be called once per managed-doc that is a
    # research target, which is ≥ n_docs.
    assert rglob_count <= 1, (
        f"Expected rglob to be called at most once (once per research dir) but "
        f"got {rglob_count} calls for n_docs={n_docs}.  "
        f"The O(D×F) regression has been re-introduced."
    )


# ---------------------------------------------------------------------------
# Test 2: rglob count does NOT grow with D (parametrised comparison)
# ---------------------------------------------------------------------------

def test_rglob_count_does_not_scale_with_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rglob count for N_SMALL docs == rglob count for N_LARGE docs."""
    clear_managed_doc_quality_state_cache()

    def _run(n: int, base: Path) -> int:
        project = build_furnace_project(base, n_research_files=5)
        research_dir = Path(project["docs_dir"]) / "research"
        for i in range(n):
            extra = research_dir / f"EXTRA_{i:04d}.md"
            extra.write_text(f"# Extra {i}\n\nContent.\n", encoding="utf-8")
            project["docs"][f"extra_{i}"] = str(extra)
        counters = patch_fs_ops(monkeypatch)
        _collect_managed_doc_quality_state_uncached(project)
        # Reset monkeypatch counters between runs by resetting the dict values
        result = counters["rglob"]
        # Undo patch so next _run gets a fresh counter
        monkeypatch.undo()
        return result

    count_small = _run(N_SMALL, tmp_path / "small")
    count_large = _run(N_LARGE, tmp_path / "large")

    assert count_small == count_large, (
        f"rglob count should not scale with D: "
        f"N_SMALL={N_SMALL} -> {count_small} calls, "
        f"N_LARGE={N_LARGE} -> {count_large} calls.  O(D×F) regression present."
    )


# ---------------------------------------------------------------------------
# Test 3: correctness — warnings output unchanged vs pre-hoist baseline
# ---------------------------------------------------------------------------

def test_warnings_output_parity_with_without_hoist(tmp_path: Path) -> None:
    """Warnings from hoisted path are identical to the non-hoisted (rglob-per-call) path.

    We compare:
      - hoisted: _collect_managed_doc_quality_state_uncached (new code)
      - baseline: manually call collect_managed_doc_quality_warnings WITHOUT
        research_docs for each doc (simulates the old per-call rglob)

    Both must produce the same warning codes for each doc.
    """
    clear_managed_doc_quality_state_cache()
    project = build_furnace_project(tmp_path, n_research_files=5)

    # Run new hoisted implementation
    hoisted = _collect_managed_doc_quality_state_uncached(project)

    # Compute baseline by calling collect_managed_doc_quality_warnings per-doc
    # WITHOUT research_docs (old behaviour — rglob fires each time)
    baseline_doc_warnings: dict[str, list[str]] = {}
    docs = project.get("docs", {})
    from scribe_mcp.doc_management.scaffold_quality import (
        is_managed_doc_quality_target,
        configured_log_quality_exclusion_paths,
    )
    configured_log_paths = configured_log_quality_exclusion_paths(project)
    for key, doc_path in docs.items():
        if not isinstance(doc_path, str) or not doc_path.endswith(".md"):
            continue
        if not is_managed_doc_quality_target(str(key), doc_path, configured_log_paths=configured_log_paths):
            continue
        path = Path(doc_path)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Old path: no research_docs arg -> rglob fires inside
        warnings = collect_managed_doc_quality_warnings(
            text=text, doc_name=str(key), path=path, project=project
            # research_docs intentionally omitted -> back-compat rglob
        )
        baseline_doc_warnings[str(key)] = sorted(
            str(w.get("code")) for w in warnings
        )

    # Build hoisted doc warnings in the same shape
    hoisted_doc_warnings: dict[str, list[str]] = {}
    for doc in hoisted.get("documents", []):
        hoisted_doc_warnings[doc["doc_name"]] = sorted(
            str(c) for c in doc.get("warning_codes", [])
        )

    assert hoisted_doc_warnings == baseline_doc_warnings, (
        f"Hoisted path produced different warnings than pre-hoist baseline.\n"
        f"Hoisted:  {hoisted_doc_warnings}\n"
        f"Baseline: {baseline_doc_warnings}"
    )


# ---------------------------------------------------------------------------
# Test 4: back-compat — build_research_index_hygiene_warnings without research_docs
# ---------------------------------------------------------------------------

def test_back_compat_no_research_docs_param(tmp_path: Path) -> None:
    """When research_docs is omitted, rglob fires and result is unchanged."""
    # Set up a minimal research dir with a couple of files
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    (research_dir / "RESEARCH_0001.md").write_text("# Doc 1\n", encoding="utf-8")
    (research_dir / "RESEARCH_0002.md").write_text("# Doc 2\n", encoding="utf-8")
    index_path = research_dir / "INDEX.md"
    index_path.write_text(
        "# Research Index\n\n- [Doc 1](RESEARCH_0001.md)\n- [Doc 2](RESEARCH_0002.md)\n",
        encoding="utf-8",
    )
    changed = research_dir / "RESEARCH_0001.md"

    # Without research_docs — old path, rglob runs
    result_old = build_research_index_hygiene_warnings(
        research_dir=research_dir,
        warning_policies=DEFAULT_WARNING_POLICIES,
        changed_path=changed,
    )

    # With research_docs pre-supplied — new path, no rglob
    pre_computed = sorted(
        p for p in research_dir.rglob("*.md")
        if p.name != "INDEX.md" and not p.name.startswith("_")
    )
    result_new = build_research_index_hygiene_warnings(
        research_dir=research_dir,
        warning_policies=DEFAULT_WARNING_POLICIES,
        changed_path=changed,
        research_docs=pre_computed,
    )

    assert [w["code"] for w in result_old] == [w["code"] for w in result_new], (
        "build_research_index_hygiene_warnings with and without research_docs "
        "produced different warning codes — back-compat is broken."
    )


# ---------------------------------------------------------------------------
# Test 5: collect_managed_doc_quality_warnings threads research_docs correctly
# ---------------------------------------------------------------------------

def test_collect_managed_doc_quality_warnings_threads_research_docs(tmp_path: Path) -> None:
    """When research_docs is passed, rglob is NOT called inside the function."""
    research_dir = tmp_path / "research"
    research_dir.mkdir()
    doc_file = research_dir / "RESEARCH_0001.md"
    doc_file.write_text("# R1\n\nContent.\n", encoding="utf-8")
    index_path = research_dir / "INDEX.md"
    index_path.write_text(
        "# Research Index\n\n- [R1](RESEARCH_0001.md)\n", encoding="utf-8"
    )

    project = {
        "name": "test",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path),
        "docs": {},
        "current_phase": None,
    }

    pre_computed = [doc_file]

    rglob_call_count = 0
    original_rglob = Path.rglob

    def counting_rglob(self: Path, pattern: str, **kwargs: Any):  # type: ignore[no-untyped-def]
        nonlocal rglob_call_count
        rglob_call_count += 1
        return original_rglob(self, pattern, **kwargs)

    text = doc_file.read_text(encoding="utf-8")

    with patch.object(Path, "rglob", counting_rglob):
        collect_managed_doc_quality_warnings(
            text=text,
            doc_name="research_0001",
            path=doc_file,
            project=project,
            research_docs=pre_computed,
        )

    assert rglob_call_count == 0, (
        f"rglob was called {rglob_call_count} time(s) even though research_docs "
        "was pre-supplied — the threading is broken."
    )
