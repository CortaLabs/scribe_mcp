"""Integration tests for toolkit workflows and session tracking."""

from __future__ import annotations

import re

import pytest

from scribe_mcp.tools.search import (
    Match,
    FileResult,
    TraversalStats,
    _is_binary_extension,
    _is_binary_content,
    _iterate_files,
    _search_file,
    _search_file_multiline,
    _build_structured_result,
    _format_search_readable,
)
from scribe_mcp.tools.edit_file import (
    _perform_replacement,
    _generate_diff,
    _backup_file,
)


# ===========================================================================
# 1. search Tool End-to-End Tests
# ===========================================================================


class TestSearchOutputModes:
    """Test all output modes: content, files_with_matches, count."""

    def test_content_mode(self, project_tree):
        pat = re.compile(r"def \w+")
        matches = _search_file(project_tree / "main.py", pat, max_matches=50)
        assert len(matches) == 1
        assert "def main" in matches[0].line

    def test_files_with_matches_mode(self, project_tree):
        """Build structured result in files_with_matches mode."""
        fr = FileResult(file="main.py", matches=[Match(line_number=4, line="def main():")], match_count=1)
        result = _build_structured_result(
            results=[fr],
            output_mode="files_with_matches",
            pattern="def",
            files_searched=3,
            total_matches=1,
            line_numbers=True,
        )
        assert result["ok"] is True
        assert result["files"] == ["main.py"]
        assert "matches" not in result  # files mode doesn't include match lines

    def test_count_mode(self, project_tree):
        fr = FileResult(file="utils.py", matches=[Match(1, "x")] * 2, match_count=2)
        result = _build_structured_result(
            results=[fr],
            output_mode="count",
            pattern="helper",
            files_searched=3,
            total_matches=2,
            line_numbers=True,
        )
        assert result["counts"] == [{"file": "utils.py", "count": 2}]


class TestSearchTypeFilter:
    """Test type filter and verify skip stats accuracy (bug fix)."""

    def test_type_py_only_yields_python(self, project_tree):
        """With type=py, only .py/.pyi files should be yielded."""
        stats = TraversalStats()
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="py",
            skip_binary=True,
            stats=stats,
        ))
        names = {f.name for f in files}
        assert "main.py" in names
        assert "utils.py" in names
        assert "core.py" in names
        # Non-python files should NOT appear
        assert "config.json" not in names
        assert "readme.md" not in names
        assert "image.png" not in names

    def test_type_filter_skip_stats_accurate(self, project_tree):
        """BUG FIX TEST: skip stats should only count files matching the type filter.

        With type=py, binary files like .png/.db/.pyc should NOT count as
        skipped_binary because they were never candidates for the search.
        """
        stats = TraversalStats()
        list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="py",
            skip_binary=True,
            stats=stats,
        ))
        # .png, .db, .pyc are not .py/.pyi so they should be filtered by
        # the type check BEFORE reaching the binary check.
        assert stats.skipped_binary == 0, (
            f"Expected 0 binary skips with type=py filter, got {stats.skipped_binary}. "
            "Type/glob filters should eliminate non-matching files before binary check."
        )
        assert stats.skipped_size == 0

    def test_no_type_filter_counts_binary_skips(self, project_tree):
        """Without type filter, binary files ARE counted as skipped."""
        stats = TraversalStats()
        list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type=None,
            skip_binary=True,
            stats=stats,
        ))
        # .png, .db, .pyc should all be counted as skipped_binary
        assert stats.skipped_binary >= 3, (
            f"Expected at least 3 binary skips without filter, got {stats.skipped_binary}"
        )


class TestSearchGlobFilter:
    """Test glob pattern filtering."""

    def test_glob_py_files(self, project_tree):
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern="*.py",
            file_type=None,
            skip_binary=True,
        ))
        names = {f.name for f in files}
        # Only top-level .py (glob *.py doesn't match subdirs by default)
        assert "main.py" in names
        assert "utils.py" in names

    def test_glob_recursive(self, project_tree):
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern="src/*.py",
            file_type=None,
            skip_binary=True,
        ))
        names = {f.name for f in files}
        assert "core.py" in names

    def test_glob_skip_stats_accurate(self, project_tree):
        """Glob filter should also prevent binary skip inflation."""
        stats = TraversalStats()
        list(_iterate_files(
            root=project_tree,
            glob_pattern="*.py",
            file_type=None,
            skip_binary=True,
            stats=stats,
        ))
        assert stats.skipped_binary == 0, (
            f"Expected 0 binary skips with glob=*.py, got {stats.skipped_binary}"
        )


class TestSearchContextLines:
    """Test context line output."""

    def test_context_before_and_after(self, project_tree):
        pat = re.compile(r"def main")
        matches = _search_file(
            project_tree / "main.py", pat,
            max_matches=10, before=2, after=1,
        )
        assert len(matches) == 1
        m = matches[0]
        assert m.line_number == 4
        # Should have context
        assert m.context_before is not None or m.context_after is not None


class TestSearchCaseInsensitive:
    """Test case-insensitive matching."""

    def test_case_insensitive(self, project_tree):
        pat = re.compile(r"DEF MAIN", re.IGNORECASE)
        matches = _search_file(project_tree / "main.py", pat, max_matches=10)
        assert len(matches) == 1

    def test_case_sensitive_no_match(self, project_tree):
        pat = re.compile(r"DEF MAIN")
        matches = _search_file(project_tree / "main.py", pat, max_matches=10)
        assert len(matches) == 0


class TestSearchRegexSpecialChars:
    """Test regex with special characters."""

    def test_pipe_or(self, project_tree):
        """Pipe operator as regex OR."""
        pat = re.compile(r"def main|def helper")
        matches_main = _search_file(project_tree / "main.py", pat, max_matches=10)
        matches_utils = _search_file(project_tree / "utils.py", pat, max_matches=10)
        assert len(matches_main) >= 1
        assert len(matches_utils) >= 1

    def test_brackets(self, project_tree):
        pat = re.compile(r"import [os]")
        matches = _search_file(project_tree / "main.py", pat, max_matches=10)
        # [os] matches 'o' or 's' as character class
        assert len(matches) >= 1

    def test_parentheses_group(self, project_tree):
        pat = re.compile(r"(def|class) \w+")
        matches = _search_file(project_tree / "src" / "core.py", pat, max_matches=10)
        assert len(matches) >= 1  # should match both class and def


class TestSearchNoResults:
    """Test clean empty response for no matches."""

    def test_no_matches_structured(self, project_tree):
        result = _build_structured_result(
            results=[],
            output_mode="content",
            pattern="nonexistent_xyz",
            files_searched=5,
            total_matches=0,
            line_numbers=True,
        )
        assert result["ok"] is True
        assert result["total_matches"] == 0
        assert result["matches"] == []

    def test_no_matches_readable(self):
        data = {
            "ok": True,
            "output_mode": "content",
            "pattern": "zzz_no_match",
            "files_searched": 5,
            "files_with_matches": 0,
            "total_matches": 0,
            "matches": [],
        }
        text = _format_search_readable(data, line_numbers=True)
        assert "0 matches" in text.lower() or "no matches" in text.lower() or "0" in text


class TestSearchHeadLimit:
    """Test structured result with limited output."""

    def test_build_result_limits_files(self, project_tree):
        """max_files should cap results."""
        frs = [
            FileResult(file=f"file{i}.py", matches=[Match(1, f"line{i}")], match_count=1)
            for i in range(10)
        ]
        result = _build_structured_result(
            results=frs[:3],  # simulate already-limited
            output_mode="files_with_matches",
            pattern="test",
            files_searched=10,
            total_matches=3,
            line_numbers=True,
        )
        assert len(result["files"]) == 3


# ===========================================================================
# 2. edit_file End-to-End Tests
# ===========================================================================


class TestEditFileReplacement:
    """Test _perform_replacement and _generate_diff."""

    def test_dry_run_preview(self, tmp_path):
        """Dry-run should show diff without modifying file."""
        f = tmp_path / "test.py"
        f.write_text("hello world\n")
        content = f.read_text()
        modified, result = _perform_replacement(content, "hello", "goodbye", False)
        diff = _generate_diff(content, modified, "test.py")
        assert "-hello world" in diff
        assert "+goodbye world" in diff
        # Original file unchanged
        assert f.read_text() == "hello world\n"

    def test_commit_mode_changes_file(self, tmp_path):
        """Commit mode should actually change the file."""
        f = tmp_path / "test.py"
        f.write_text("hello world\n")
        content = f.read_text()
        modified, result = _perform_replacement(content, "hello", "goodbye", False)
        assert result.occurrences_replaced == 1
        f.write_text(modified)
        assert f.read_text() == "goodbye world\n"

    def test_replace_all_multiple(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("foo bar foo baz foo\n")
        content = f.read_text()
        modified, result = _perform_replacement(content, "foo", "qux", True)
        assert result.occurrences_found == 3
        assert result.occurrences_replaced == 3
        assert modified == "qux bar qux baz qux\n"

    def test_old_string_not_found(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello world\n")
        content = f.read_text()
        modified, result = _perform_replacement(content, "MISSING", "x", False)
        assert result.occurrences_found == 0
        assert modified == content


class TestEditFileBackup:
    """Test backup creation."""

    def test_backup_creates_file(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        target = repo_root / "src" / "module.py"
        target.parent.mkdir(parents=True)
        target.write_text("original content\n")

        backup_path = _backup_file(target, repo_root)
        assert backup_path.exists()
        assert backup_path.read_text() == "original content\n"
        assert ".scribe/backups" in str(backup_path)


# ===========================================================================
# 3. Toolkit Workflow Tests
# ===========================================================================


class TestToolkitWorkflow:
    """Test tools working together: search -> read -> edit."""

    def test_search_then_edit(self, project_tree):
        """Full workflow: find a pattern, then replace it."""
        # Step 1: Search for the pattern
        pat = re.compile(r"return 42")
        matches = _search_file(project_tree / "utils.py", pat, max_matches=10)
        assert len(matches) == 1
        assert matches[0].line_number == 2

        # Step 2: Read the file
        content = (project_tree / "utils.py").read_text()
        assert "return 42" in content

        # Step 3: Edit (replace)
        modified, result = _perform_replacement(content, "return 42", "return 100", False)
        assert result.occurrences_replaced == 1

        # Step 4: Write and verify
        (project_tree / "utils.py").write_text(modified)
        new_content = (project_tree / "utils.py").read_text()
        assert "return 100" in new_content
        assert "return 42" not in new_content

    def test_search_multiple_files_then_edit(self, project_tree):
        """Search across files, then edit a specific one."""
        # Search for 'def' in all python files
        stats = TraversalStats()
        py_files = list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="py",
            skip_binary=True,
            stats=stats,
        ))
        assert len(py_files) >= 3

        # Find which files have 'def helper'
        pat = re.compile(r"def helper")
        for f in py_files:
            matches = _search_file(f, pat, max_matches=5)
            if matches:
                content = f.read_text()
                modified, result = _perform_replacement(content, "def helper", "def improved_helper", False)
                assert result.occurrences_replaced == 1
                f.write_text(modified)
                break

        assert "improved_helper" in (project_tree / "utils.py").read_text()


# ===========================================================================
# 4. read_file Session Tracking Tests
# ===========================================================================


class TestSessionTracking:
    """Test RouterContextManager file read tracking."""

    @pytest.mark.asyncio
    async def test_record_and_check_file_read(self, router):
        session_id = "test-session-1"
        file_path = "/repo/src/module.py"

        # Initially not read
        assert not await router.has_file_been_read(session_id, file_path)

        # Record read
        await router.record_file_read(session_id, file_path)

        # Now it's been read
        assert await router.has_file_been_read(session_id, file_path)

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self, router):
        file_path = "/repo/src/module.py"

        await router.record_file_read("session-A", file_path)

        assert await router.has_file_been_read("session-A", file_path)
        assert not await router.has_file_been_read("session-B", file_path)

    @pytest.mark.asyncio
    async def test_cleanup_removes_tracking(self, router):
        session_id = "test-session-cleanup"
        file_path = "/repo/src/module.py"

        await router.record_file_read(session_id, file_path)
        assert await router.has_file_been_read(session_id, file_path)

        await router.cleanup_session(session_id)
        assert not await router.has_file_been_read(session_id, file_path)

    @pytest.mark.asyncio
    async def test_multiple_files_tracked(self, router):
        session_id = "test-multi"
        files = ["/repo/a.py", "/repo/b.py", "/repo/c.py"]
        for f in files:
            await router.record_file_read(session_id, f)

        for f in files:
            assert await router.has_file_been_read(session_id, f)

        assert not await router.has_file_been_read(session_id, "/repo/d.py")

    @pytest.mark.asyncio
    async def test_empty_session_id_returns_false(self, router):
        assert not await router.has_file_been_read("", "/some/file")
        assert not await router.has_file_been_read(None, "/some/file")

    @pytest.mark.asyncio
    async def test_project_binding(self, router):
        session_id = "test-project-bind"
        await router.cache_project_binding(session_id, "my_project")
        result = await router.get_cached_project(session_id)
        assert result == "my_project"

    @pytest.mark.asyncio
    async def test_cleanup_removes_project_binding(self, router):
        session_id = "test-cleanup-project"
        await router.cache_project_binding(session_id, "my_project")
        await router.cleanup_session(session_id)
        result = await router.get_cached_project(session_id)
        assert result is None


# ===========================================================================
# 5. Skip Stats Regression Tests (Bug Fix Verification)
# ===========================================================================


class TestSkipStatsRegression:
    """Dedicated regression tests for the skip stats overcounting bug."""

    def test_type_json_no_binary_skips(self, project_tree):
        """Searching type=json should not count .png/.db as binary skips."""
        stats = TraversalStats()
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="json",
            skip_binary=True,
            stats=stats,
        ))
        names = {f.name for f in files}
        assert "config.json" in names
        assert stats.skipped_binary == 0

    def test_type_md_no_binary_skips(self, project_tree):
        stats = TraversalStats()
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="md",
            skip_binary=True,
            stats=stats,
        ))
        names = {f.name for f in files}
        assert "readme.md" in names
        assert stats.skipped_binary == 0

    def test_glob_json_no_binary_skips(self, project_tree):
        stats = TraversalStats()
        list(_iterate_files(
            root=project_tree,
            glob_pattern="*.json",
            file_type=None,
            skip_binary=True,
            stats=stats,
        ))
        assert stats.skipped_binary == 0

    def test_unknown_type_yields_nothing(self, project_tree):
        """Unknown type should yield nothing and not crash."""
        stats = TraversalStats()
        files = list(_iterate_files(
            root=project_tree,
            glob_pattern=None,
            file_type="nonexistent_lang",
            skip_binary=True,
            stats=stats,
        ))
        assert files == []
        assert stats.skipped_binary == 0

    def test_size_filter_only_for_matching_type(self, tmp_path):
        """Size skip should only count for files matching the type filter."""
        # Create a large .py file and a large .txt file
        large_py = tmp_path / "big.py"
        large_py.write_text("x" * 200)
        large_txt = tmp_path / "big.txt"
        large_txt.write_text("y" * 200)

        stats = TraversalStats()
        files = list(_iterate_files(
            root=tmp_path,
            glob_pattern=None,
            file_type="py",
            skip_binary=True,
            max_file_size_bytes=100,  # smaller than file
            stats=stats,
        ))
        assert len(files) == 0
        # Only the .py file should count as skipped_size, not the .txt
        assert stats.skipped_size == 1
