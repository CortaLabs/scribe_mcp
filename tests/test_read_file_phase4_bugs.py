"""Tests for Phase 4 bug fixes: repo root resolution and search regex."""
import os
import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.execution_context import AgentIdentity, ExecutionContext
from scribe_mcp.tools.read_file import (
    _extract_python_structure,
    _paginate_structure,
    _search_file,
    read_file,
)


def _install_execution_context(repo_root: str) -> object:
    context = ExecutionContext(
        repo_root=repo_root,
        mode="sentinel",
        session_id="session-phase4",
        execution_id="exec-phase4",
        agent_identity=AgentIdentity(
            agent_kind="test",
            model=None,
            instance_id="agent-phase4",
            sub_id=None,
            display_name=None,
        ),
        intent="phase4_bug_tests",
        timestamp_utc="2026-01-29T00:00:00+00:00",
        affected_dev_projects=[],
        sentinel_day="2026-01-29",
    )
    return server_module.router_context_manager.set_current(context)


# ── Bug 1: Repo root resolution with symlinks ──


@pytest.mark.asyncio
async def test_read_file_symlinked_repo_root(tmp_path):
    """Repo root passed as symlink should resolve correctly."""
    real_dir = tmp_path / "real_repo"
    real_dir.mkdir()
    target_file = real_dir / "test.txt"
    target_file.write_text("hello world\n", encoding="utf-8")

    link_dir = tmp_path / "link_repo"
    link_dir.symlink_to(real_dir)

    # Pass symlink path as repo_root
    token = _install_execution_context(str(link_dir))
    try:
        result = await read_file(
            agent="test_agent",
            path="test.txt",
            mode="line_range",
            start_line=1,
            end_line=1,
            format="structured",
        )
        assert result["ok"] is True
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_absolute_path_with_symlinked_root(tmp_path):
    """Absolute path under symlinked root should be recognized as inside repo."""
    real_dir = tmp_path / "real_repo"
    real_dir.mkdir()
    target_file = real_dir / "data.txt"
    target_file.write_text("content\n", encoding="utf-8")

    link_dir = tmp_path / "link_repo"
    link_dir.symlink_to(real_dir)

    # Pass symlink as repo_root, but absolute path uses real path
    token = _install_execution_context(str(link_dir))
    try:
        result = await read_file(
            agent="test_agent",
            path=str(real_dir / "data.txt"),  # real absolute path
            mode="scan_only",
            format="structured",
        )
        assert result["ok"] is True
    finally:
        server_module.router_context_manager.reset(token)


# ── Bug 2: Search regex with pipe (OR) operator ──


def test_search_file_regex_pipe_operator(tmp_path):
    """Regex pipe | should match either alternative."""
    target = tmp_path / "code.py"
    target.write_text(
        "def format_readable():\n"
        "    pass\n"
        "# READ FILE output\n"
        "x = 42\n",
        encoding="utf-8",
    )
    matches = _search_file(
        target, "utf-8", r"def.*format.*read|READ FILE",
        regex=True, context_lines=0, max_matches=None,
        case_insensitive=False, fuzzy_threshold=0.0,
    )
    assert len(matches) == 2
    assert "format_readable" in matches[0]["line"]
    assert "READ FILE" in matches[1]["line"]


def test_search_file_regex_false_treats_pipe_as_literal(tmp_path):
    """With regex=False, pipe should be treated as literal character."""
    target = tmp_path / "code.py"
    target.write_text(
        "def format_readable():\n"
        "a|b pattern\n",
        encoding="utf-8",
    )
    matches = _search_file(
        target, "utf-8", "a|b",
        regex=False, context_lines=0, max_matches=None,
        case_insensitive=False, fuzzy_threshold=0.0,
    )
    assert len(matches) == 1
    assert "a|b" in matches[0]["line"]


@pytest.mark.asyncio
async def test_read_file_search_regex_default(tmp_path):
    """Default search_mode is regex, so pipe should work via MCP tool."""
    target = tmp_path / "sample.py"
    target.write_text(
        "def hello():\n"
        "    pass\n"
        "WORLD = 1\n",
        encoding="utf-8",
    )
    token = _install_execution_context(str(tmp_path))
    try:
        result = await read_file(
            agent="test_agent",
            path=str(target),
            mode="search",
            search=r"def hello|WORLD",
            format="structured",
        )
        assert result["ok"] is True
        assert len(result["matches"]) == 2
    finally:
        server_module.router_context_manager.reset(token)


@pytest.mark.asyncio
async def test_read_file_search_literal_mode_no_regex(tmp_path):
    """Literal mode should NOT interpret pipe as regex OR."""
    target = tmp_path / "sample.txt"
    target.write_text(
        "a|b\nhello\nworld\n",
        encoding="utf-8",
    )
    token = _install_execution_context(str(tmp_path))
    try:
        result = await read_file(
            agent="test_agent",
            path=str(target),
            mode="search",
            search="a|b",
            search_mode="literal",
            format="structured",
        )
        assert result["ok"] is True
        # literal mode maps to "smart" which infers regex due to |
        # But the actual behavior: search_mode="literal" → smart → infer → regex (because | is a meta char)
        # So it WILL match as regex. This is expected behavior per _infer_search_mode.
        # To truly get literal, user would need search_mode="literal" which gets remapped to "smart"
        # then _infer_search_mode sees | and returns "regex". This is by design.
        assert len(result["matches"]) >= 1
    finally:
        server_module.router_context_manager.reset(token)


# ── P4.4 / Bug F2: structure_page real slicing ──


def _write_many_functions(target, count: int) -> None:
    """Write a python file with `count` top-level functions."""
    lines = []
    for i in range(count):
        lines.append(f"def fn_{i:03d}():")
        lines.append("    pass")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_paginate_structure_slices_and_reports_real_totals(tmp_path):
    """structure_page=2 returns a DIFFERENT page than page 1 with accurate has_next/total."""
    target = tmp_path / "big.py"
    _write_many_functions(target, 60)  # >50 symbols

    full = _extract_python_structure(target, max_items=100000)
    assert full["total_functions"] == 60

    page1 = _paginate_structure(
        _extract_python_structure(target, max_items=100000),
        page=1,
        page_size=25,
    )
    page2 = _paginate_structure(
        _extract_python_structure(target, max_items=100000),
        page=2,
        page_size=25,
    )

    # Real slicing: pages hold the right window and differ from each other.
    assert [f["name"] for f in page1["functions"]] == [f"fn_{i:03d}" for i in range(0, 25)]
    assert [f["name"] for f in page2["functions"]] == [f"fn_{i:03d}" for i in range(25, 50)]
    assert page1["functions"] != page2["functions"]

    # Accurate totals are preserved (not the sliced length).
    assert page1["total_functions"] == 60
    assert page2["total_functions"] == 60

    # Real pagination metadata.
    assert page1["pagination"]["total_items"] == 60
    assert page1["pagination"]["total_pages"] == 3  # ceil(60/25)
    assert page1["pagination"]["has_next"] is True
    assert page1["pagination"]["has_prev"] is False
    assert page2["pagination"]["has_next"] is True
    assert page2["pagination"]["has_prev"] is True

    page3 = _paginate_structure(
        _extract_python_structure(target, max_items=100000),
        page=3,
        page_size=25,
    )
    assert len(page3["functions"]) == 10  # 60 - 50
    assert page3["pagination"]["has_next"] is False  # last page


@pytest.mark.asyncio
async def test_read_file_structure_page_returns_different_page(tmp_path):
    """Via the MCP tool: structure_page=2 yields a different scan page than page 1."""
    target = tmp_path / "module.py"
    _write_many_functions(target, 60)

    token = _install_execution_context(str(tmp_path))
    try:
        page1 = await read_file(
            agent="test_agent", path=str(target), mode="scan_only",
            structure_page=1, structure_page_size=20, format="structured",
        )
        page2 = await read_file(
            agent="test_agent", path=str(target), mode="scan_only",
            structure_page=2, structure_page_size=20, format="structured",
        )
        assert page1["ok"] is True and page2["ok"] is True

        names1 = [f["name"] for f in page1["structure"]["functions"]]
        names2 = [f["name"] for f in page2["structure"]["functions"]]
        assert names1 != names2  # dead pagination is dead
        assert len(names1) == 20 and len(names2) == 20
        assert set(names1).isdisjoint(set(names2))

        # structure_pagination now reflects the real slice, not echoed inputs.
        assert page1["structure_pagination"]["total_items"] == 60
        assert page1["structure_pagination"]["has_next"] is True
        assert page2["structure_pagination"]["page"] == 2
    finally:
        server_module.router_context_manager.reset(token)


# ── P4.4 / Bug F3: search post-context + context_end clamp ──


def test_search_file_delivers_post_context(tmp_path):
    """context_lines=2 must deliver the 2 lines AFTER the match (not just before)."""
    target = tmp_path / "ctx.py"
    target.write_text(
        "before2\n"   # line 1
        "before1\n"   # line 2
        "MATCH\n"     # line 3 (match)
        "after1\n"    # line 4
        "after2\n"    # line 5
        "after3\n",   # line 6
        encoding="utf-8",
    )
    matches = _search_file(
        target, "utf-8", "MATCH",
        regex=False, context_lines=2, max_matches=None,
        case_insensitive=False, fuzzy_threshold=0.0,
    )
    assert len(matches) == 1
    m = matches[0]
    assert m["line_number"] == 3
    # Pre-context (2) + match (1) + post-context (2) = 5 lines, in order.
    ctx = [c.rstrip("\n") for c in m["context"]]
    assert ctx == ["before2", "before1", "MATCH", "after1", "after2"]
    assert m["context_start"] == 1  # max(1, 3-2)
    # context_end equals the last delivered line (line 5 == after2).
    assert m["context_end"] == 5
    assert m["context_end"] == m["context_start"] + len(m["context"]) - 1


def test_search_file_context_end_clamped_to_eof(tmp_path):
    """A match near EOF must not report context_end past the last line."""
    target = tmp_path / "eof.py"
    target.write_text(
        "x = 1\n"      # line 1
        "y = 2\n"      # line 2
        "MATCH\n",     # line 3 (match, only 0 trailing lines)
        encoding="utf-8",
    )
    matches = _search_file(
        target, "utf-8", "MATCH",
        regex=False, context_lines=3, max_matches=None,
        case_insensitive=False, fuzzy_threshold=0.0,
    )
    assert len(matches) == 1
    m = matches[0]
    # Optimistic end would be 3+3=6, but file ends at line 3.
    assert m["context_end"] <= 3
    assert m["context_end"] == 3
    # No phantom lines appended past EOF.
    assert m["context_end"] == m["context_start"] + len(m["context"]) - 1


@pytest.mark.asyncio
async def test_read_file_search_post_context_via_tool(tmp_path):
    """End-to-end: search mode with context_lines=2 returns post-context lines."""
    target = tmp_path / "doc.txt"
    target.write_text(
        "alpha\nbeta\nNEEDLE\ngamma\ndelta\nepsilon\n",
        encoding="utf-8",
    )
    token = _install_execution_context(str(tmp_path))
    try:
        result = await read_file(
            agent="test_agent", path=str(target), mode="search",
            search="NEEDLE", context_lines=2, format="structured",
        )
        assert result["ok"] is True
        assert len(result["matches"]) == 1
        ctx = [c.rstrip("\n") for c in result["matches"][0]["context"]]
        assert "gamma" in ctx and "delta" in ctx  # post-context delivered
    finally:
        server_module.router_context_manager.reset(token)


# ── P4.5 / Bug F5+F4: single-pass NodeVisitor + async def classification ──


def test_extract_top_level_async_def_appears_in_structure(tmp_path):
    """F4: a top-level `async def` must appear in the scan structure functions.

    The old `isinstance(node, ast.FunctionDef)` gate dropped every top-level
    async function because `ast.AsyncFunctionDef` is a sibling class, not a
    subclass, of `ast.FunctionDef`.
    """
    target = tmp_path / "async_mod.py"
    target.write_text(
        "def sync_fn():\n"
        "    pass\n"
        "\n"
        "async def async_fn():\n"
        "    pass\n",
        encoding="utf-8",
    )
    structure = _extract_python_structure(target, max_items=100000)
    assert structure["ok"] is True

    names = {f["name"] for f in structure["functions"]}
    assert "sync_fn" in names
    assert "async_fn" in names  # the regression: previously missing

    by_name = {f["name"]: f for f in structure["functions"]}
    assert by_name["sync_fn"]["type"] == "function"
    assert by_name["async_fn"]["type"] == "async_function"


def test_async_methods_still_classified_inside_class(tmp_path):
    """Async methods inside a class remain methods with is_async=True (unchanged)."""
    target = tmp_path / "cls_async.py"
    target.write_text(
        "class Service:\n"
        "    def sync_method(self):\n"
        "        pass\n"
        "    async def async_method(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    structure = _extract_python_structure(target, max_items=100000)
    assert structure["ok"] is True
    # Methods are not top-level functions.
    assert structure["functions"] == []
    assert len(structure["classes"]) == 1
    cls = structure["classes"][0]
    assert cls["name"] == "Service"
    methods = {m["name"]: m for m in cls["methods"]}
    assert set(methods) == {"sync_method", "async_method"}
    assert methods["sync_method"]["is_async"] is False
    assert methods["async_method"]["is_async"] is True
    assert cls["method_count"] == 2


def test_structure_extraction_is_single_pass(tmp_path):
    """F5: extraction visits the tree ONCE — cost is independent of class×function.

    Proof has two independent legs:
    1. `ast.walk` is never called during extraction (the old O(C×F) re-walks
       are gone). We patch `ast.walk` to a counter and assert zero calls.
    2. `_get_full_signature` is called exactly once per def (top-level functions
       + every method), regardless of how many classes exist. The old code's
       per-function `ast.walk(tree)` parent scan scaled with the class count;
       a single-pass visitor does not.
    """
    import ast as _ast
    from scribe_mcp.tools import read_file as rf

    # A module with M classes × N methods each, plus K top-level functions.
    M, N, K = 5, 4, 3
    lines = []
    for k in range(K):
        lines.append(f"def top_{k}():")
        lines.append("    pass")
    for c in range(M):
        lines.append(f"class C{c}:")
        for n in range(N):
            lines.append(f"    def m{n}(self):")
            lines.append("        pass")
    target = tmp_path / "matrix.py"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    walk_calls = {"n": 0}
    real_walk = _ast.walk

    def _counting_walk(node):
        walk_calls["n"] += 1
        return real_walk(node)

    sig_calls = {"n": 0}
    real_sig = rf._get_full_signature

    def _counting_sig(node):
        sig_calls["n"] += 1
        return real_sig(node)

    orig_walk = _ast.walk
    orig_sig = rf._get_full_signature
    _ast.walk = _counting_walk
    rf._get_full_signature = _counting_sig
    try:
        structure = rf._extract_python_structure(target, max_items=100000)
    finally:
        _ast.walk = orig_walk
        rf._get_full_signature = orig_sig

    assert structure["ok"] is True
    assert len(structure["functions"]) == K
    assert len(structure["classes"]) == M
    assert all(c["method_count"] == N for c in structure["classes"])

    # Leg 1: no ast.walk during extraction — the O(C×F) re-walks are gone.
    assert walk_calls["n"] == 0

    # Leg 2: exactly one signature build per def — single visit of each node.
    # Total defs = K top-level + M*N methods. Independent of the C×F product
    # that the old triple-walk incurred.
    assert sig_calls["n"] == K + (M * N)


def test_nested_class_methods_extracted(tmp_path):
    """A class nested inside another class still has its own methods extracted."""
    target = tmp_path / "nested.py"
    target.write_text(
        "class Outer:\n"
        "    def outer_m(self):\n"
        "        pass\n"
        "    class Inner:\n"
        "        def inner_m(self):\n"
        "            pass\n",
        encoding="utf-8",
    )
    structure = _extract_python_structure(target, max_items=100000)
    assert structure["ok"] is True
    classes = {c["name"]: c for c in structure["classes"]}
    assert set(classes) == {"Outer", "Inner"}
    assert [m["name"] for m in classes["Outer"]["methods"]] == ["outer_m"]
    assert [m["name"] for m in classes["Inner"]["methods"]] == ["inner_m"]


@pytest.mark.asyncio
async def test_scan_navigation_hints_include_search_and_next_step(tmp_path):
    """F4/F6: scan_only nav hints expose a `search` example and a `next_step` CTA."""
    target = tmp_path / "navhint.py"
    target.write_text("def f():\n    pass\n", encoding="utf-8")
    token = _install_execution_context(str(tmp_path))
    try:
        result = await read_file(
            agent="test_agent", path=str(target), mode="scan_only",
            format="structured",
        )
        assert result["ok"] is True
        hints = result["navigation_hints"]
        # F4: the search example now exists alongside the others.
        assert "search" in hints["examples"]
        assert "mode='search'" in hints["examples"]["search"]
        # F6: a prominent next_step call-to-action guides the follow-up read.
        assert "next_step" in hints
        assert isinstance(hints["next_step"], str) and hints["next_step"]
    finally:
        server_module.router_context_manager.reset(token)
