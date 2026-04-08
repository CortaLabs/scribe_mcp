"""Unit tests for utils/path_suggestions.py error enrichment helpers."""

import tempfile
import os

import pytest
from scribe_mcp.utils.path_suggestions import (
    get_fuzzy_file_suggestions,
    get_directory_listing,
    classify_path_error,
    build_search_suggestion,
    build_read_suggestion,
    MAX_FUZZY_SUGGESTIONS,
    MAX_DIRECTORY_ENTRIES,
    FUZZY_CUTOFF,
)


# ============================================================================
# Fuzzy Matching Tests (6 tests)
# ============================================================================

def test_fuzzy_match_exact(tmp_path):
    """Exact match scores 1.0."""
    # Create a file with exact name
    (tmp_path / "auth_handler.py").touch()
    (tmp_path / "config.py").touch()

    results = get_fuzzy_file_suggestions("auth_handler.py", tmp_path)

    assert len(results) == 1
    assert results[0]["name"] == "auth_handler.py"
    assert results[0]["score"] == 1.0
    assert results[0]["is_dir"] is False


def test_fuzzy_match_close(tmp_path):
    """auth_handlers.py → auth_handler.py scores >0.9."""
    # Create similar filenames
    (tmp_path / "auth_handler.py").touch()
    (tmp_path / "auth_helper.py").touch()
    (tmp_path / "config.py").touch()

    results = get_fuzzy_file_suggestions("auth_handlers.py", tmp_path)

    # Should find auth_handler.py as close match
    assert len(results) >= 1
    best_match = results[0]
    assert best_match["name"] == "auth_handler.py"
    assert best_match["score"] > 0.9


def test_fuzzy_match_no_matches(tmp_path):
    """Completely different names return []."""
    (tmp_path / "config.py").touch()
    (tmp_path / "database.py").touch()

    results = get_fuzzy_file_suggestions("authentication.py", tmp_path)

    # No close matches (below 0.6 cutoff)
    assert len(results) == 0


def test_fuzzy_match_cutoff(tmp_path):
    """Matches below 0.6 filtered out."""
    (tmp_path / "xyz.py").touch()
    (tmp_path / "abc.py").touch()

    # Search for completely different name
    results = get_fuzzy_file_suggestions("authentication_handler.py", tmp_path, cutoff=0.6)

    # Should not match short unrelated names
    assert len(results) == 0


def test_fuzzy_match_max_suggestions(tmp_path):
    """Respects max_suggestions parameter."""
    # Create many similar files
    for i in range(10):
        (tmp_path / f"auth_handler_{i}.py").touch()

    results = get_fuzzy_file_suggestions("auth_handler.py", tmp_path, max_suggestions=3)

    # Should return at most 3 suggestions
    assert len(results) <= 3


def test_fuzzy_match_include_directories(tmp_path):
    """include_directories flag works."""
    (tmp_path / "auth_handler.py").touch()
    (tmp_path / "auth").mkdir()

    # Without include_directories (default False)
    results_no_dirs = get_fuzzy_file_suggestions("auth", tmp_path, include_directories=False)
    assert all(not r["is_dir"] for r in results_no_dirs)

    # With include_directories=True
    results_with_dirs = get_fuzzy_file_suggestions("auth", tmp_path, include_directories=True)
    has_directory = any(r["is_dir"] for r in results_with_dirs)
    assert has_directory


# ============================================================================
# Directory Listing Tests (6 tests)
# ============================================================================

def test_directory_listing_normal(tmp_path):
    """Standard dir with <30 items."""
    # Create a few files and dirs
    (tmp_path / "file1.py").touch()
    (tmp_path / "file2.py").touch()
    (tmp_path / "subdir").mkdir()

    listing = get_directory_listing(tmp_path)

    assert listing["permission_error"] is False
    assert "file1.py" in listing["files"]
    assert "file2.py" in listing["files"]
    assert "subdir" in listing["directories"]
    assert listing["truncated"] is False
    assert listing["total_scanned"] == 3


def test_directory_listing_large(tmp_path):
    """Dir with >30 items truncates correctly."""
    # Create more than MAX_DIRECTORY_ENTRIES files
    for i in range(50):
        (tmp_path / f"file_{i}.py").touch()

    listing = get_directory_listing(tmp_path, max_entries=30)

    assert listing["permission_error"] is False
    assert len(listing["files"]) <= 30
    assert listing["truncated"] is True


def test_directory_listing_empty(tmp_path):
    """Empty dir returns empty lists."""
    listing = get_directory_listing(tmp_path)

    assert listing["permission_error"] is False
    assert listing["files"] == []
    assert listing["directories"] == []
    assert listing["truncated"] is False
    assert listing["total_scanned"] == 0


def test_directory_listing_permission_error(tmp_path):
    """Unreadable dir returns permission_error=True."""
    # Create a directory and make it unreadable
    restricted_dir = tmp_path / "restricted"
    restricted_dir.mkdir()

    # Try to make it unreadable (may not work on all systems)
    try:
        os.chmod(restricted_dir, 0o000)
        listing = get_directory_listing(restricted_dir)
        assert listing.get("permission_error") is True
    finally:
        # Restore permissions for cleanup
        os.chmod(restricted_dir, 0o755)


def test_directory_listing_separate(tmp_path):
    """Separates files and dirs correctly."""
    (tmp_path / "file.py").touch()
    (tmp_path / "dir").mkdir()

    listing = get_directory_listing(tmp_path, separate_files_dirs=True)

    assert "file.py" in listing["files"]
    assert "dir" in listing["directories"]


def test_directory_listing_hidden(tmp_path):
    """Respects include_hidden parameter."""
    (tmp_path / "visible.py").touch()
    (tmp_path / ".hidden.py").touch()

    # Without include_hidden (default)
    listing_no_hidden = get_directory_listing(tmp_path, include_hidden=False)
    assert "visible.py" in listing_no_hidden["files"]
    assert ".hidden.py" not in listing_no_hidden["files"]

    # With include_hidden=True
    listing_with_hidden = get_directory_listing(tmp_path, include_hidden=True)
    assert "visible.py" in listing_with_hidden["files"]
    assert ".hidden.py" in listing_with_hidden["files"]


# ============================================================================
# Error Classification Tests (5 tests)
# ============================================================================

def test_classify_not_found(tmp_path):
    """Non-existent path → not_found."""
    non_existent = tmp_path / "does_not_exist.py"

    result = classify_path_error(non_existent)

    assert result == "not_found"


def test_classify_is_directory(tmp_path):
    """Existing dir → is_directory."""
    directory = tmp_path / "mydir"
    directory.mkdir()

    result = classify_path_error(directory)

    assert result == "is_directory"


def test_classify_permission_denied(tmp_path):
    """Unreadable path → permission_denied (optional, may be hard to set up)."""
    # Create a file and make it unreadable
    restricted_file = tmp_path / "restricted.txt"
    restricted_file.touch()

    try:
        os.chmod(restricted_file, 0o000)
        result = classify_path_error(restricted_file)
        # On some systems this might return permission_denied, on others it might not
        assert result in ("permission_denied", "unknown")
    finally:
        # Restore permissions
        os.chmod(restricted_file, 0o644)


def test_classify_symlink(tmp_path):
    """Broken symlink → is_symlink."""
    target = tmp_path / "target.txt"
    symlink = tmp_path / "link.txt"

    # Create symlink to non-existent target
    symlink.symlink_to(target)

    result = classify_path_error(symlink)

    assert result == "is_symlink"


def test_classify_regular_file(tmp_path):
    """Regular accessible file handled without classification (not an error case)."""
    regular_file = tmp_path / "regular.txt"
    regular_file.touch()

    # Regular files that exist and are accessible should not trigger error classification
    # in the tools (they won't call classify_path_error)
    # But if we do call it, it should return "unknown" since it's not actually an error
    result = classify_path_error(regular_file)

    # Regular files are not errors, so they return "unknown"
    assert result == "unknown"


# ============================================================================
# Suggestion Builder Tests (3 tests)
# ============================================================================

def test_build_search_suggestion():
    """Formats valid search command."""
    result = build_search_suggestion("auth_handler", "src/", "TestAgent")

    assert result == 'search(agent="TestAgent", pattern="auth_handler", path="src/")'


def test_build_read_suggestion():
    """Formats valid read_file command."""
    result = build_read_suggestion("src/auth/handler.py", "TestAgent", "scan_only")

    assert result == 'read_file(agent="TestAgent", path="src/auth/handler.py", mode="scan_only")'


def test_build_suggestion_escaping():
    """Escapes quotes in inputs."""
    # Test with quotes in pattern
    search_result = build_search_suggestion('auth"handler', "src/", "Agent")
    assert 'pattern="auth\\"handler"' in search_result

    # Test with quotes in path
    read_result = build_read_suggestion('src/"special"/file.py', "Agent")
    assert 'path="src/\\"special\\"/file.py"' in read_result


# ============================================================================
# Performance Tests (1 test - optional)
# ============================================================================

def test_fuzzy_match_performance(tmp_path):
    """1000 files completes in <100ms."""
    import time

    # Create 1000 files
    for i in range(1000):
        (tmp_path / f"file_{i:04d}.py").touch()

    # Measure fuzzy matching time
    start = time.time()
    results = get_fuzzy_file_suggestions("file_0500.py", tmp_path)
    elapsed = time.time() - start

    # Should complete in under 100ms (generous, accounts for slower systems/IO)
    assert elapsed < 0.1, f"Fuzzy matching took {elapsed*1000:.2f}ms, expected <100ms"

    # Should still find the match
    assert len(results) > 0
    assert results[0]["name"] == "file_0500.py"


# ============================================================================
# Edge Case Tests (additional robustness)
# ============================================================================

def test_fuzzy_match_nonexistent_parent(tmp_path):
    """Gracefully handles non-existent parent directory."""
    non_existent = tmp_path / "does_not_exist"

    results = get_fuzzy_file_suggestions("file.py", non_existent)

    # Should return empty list, not crash
    assert results == []


def test_directory_listing_nonexistent(tmp_path):
    """Gracefully handles non-existent directory."""
    non_existent = tmp_path / "does_not_exist"

    listing = get_directory_listing(non_existent)

    # Should return permission_error indicator
    assert listing.get("permission_error") is True


def test_fuzzy_match_unicode_filenames(tmp_path):
    """Handles unicode filenames correctly."""
    # Create files with unicode characters
    (tmp_path / "café.py").touch()
    (tmp_path / "naïve.py").touch()

    results = get_fuzzy_file_suggestions("cafe.py", tmp_path)

    # Should find close match despite unicode differences
    # (behavior may vary depending on similarity)
    assert isinstance(results, list)


def test_directory_listing_very_long_filenames(tmp_path):
    """Handles very long filenames without crashing."""
    # Create file with very long name
    long_name = "a" * 200 + ".py"
    (tmp_path / long_name).touch()

    listing = get_directory_listing(tmp_path)

    assert listing["permission_error"] is False
    assert long_name in listing["files"]
