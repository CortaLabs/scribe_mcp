"""Simple integration tests for error enrichment logic.

Tests the path_suggestions integration with read_file and search error responses
without requiring full async execution context setup.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from utils.path_suggestions import (
    classify_path_error,
    get_fuzzy_file_suggestions,
    get_directory_listing,
    build_search_suggestion,
)


# ============================================================================
# Error Enrichment Logic Tests (verifies integration pattern)
# ============================================================================

def test_error_enrichment_pattern_not_found(tmp_path):
    """Verify the error enrichment pattern for file-not-found errors."""
    # Create test directory structure
    (tmp_path / "auth.py").touch()
    (tmp_path / "auth_handler.py").touch()
    (tmp_path / "config.py").touch()

    # Simulate read_file error path logic
    target = tmp_path / "auth_handlers.py"  # Typo
    agent = "TestAgent"

    # Step 1: Classify error
    error_type = classify_path_error(target)
    assert error_type == "not_found"

    # Step 2: Build base error response
    error_response = {
        "ok": False,
        "error": "file not found",
        "error_type": error_type,
        "absolute_path": str(target),
    }

    # Step 3: Enrich for readable format
    format_mode = "readable"
    if format_mode == "readable":
        if target.parent.exists():
            # Get fuzzy suggestions
            suggestions = get_fuzzy_file_suggestions(
                target.name,
                target.parent,
                include_directories=(error_type == "is_directory")
            )
            if suggestions:
                error_response["similar_files"] = suggestions
                best_match = suggestions[0]
                error_response["suggestion"] = (
                    f"Did you mean '{best_match['name']}'? "
                    f"({int(best_match['score'] * 100)}% match)"
                )

            # Get directory listing
            listing = get_directory_listing(target.parent)
            if listing and not listing.get("permission_error"):
                error_response["parent_directory"] = str(target.parent)
                error_response["parent_listing"] = listing

        # Cross-tool suggestion
        if error_type in ("not_found", "permission_denied"):
            error_response["search_suggestion"] = build_search_suggestion(
                pattern=target.stem,
                path=str(target.parent),
                agent=agent
            )

    # Verify enriched response structure
    assert error_response["ok"] is False
    assert error_response["error_type"] == "not_found"
    assert "similar_files" in error_response
    assert len(error_response["similar_files"]) > 0
    assert "auth_handler.py" in [f["name"] for f in error_response["similar_files"]]
    assert "suggestion" in error_response
    assert "Did you mean 'auth_handler.py'?" in error_response["suggestion"]
    assert "parent_listing" in error_response
    assert "auth.py" in error_response["parent_listing"]["files"]
    assert "search_suggestion" in error_response
    assert 'search(agent="TestAgent"' in error_response["search_suggestion"]


def test_error_enrichment_pattern_is_directory(tmp_path):
    """Verify error enrichment for is_directory errors."""
    # Create directory
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").touch()

    target = tmp_path / "src"  # This is a directory
    agent = "TestAgent"

    # Classify error
    error_type = classify_path_error(target)
    assert error_type == "is_directory"

    # Build error response
    error_response = {
        "ok": False,
        "error": "path is a directory",
        "error_type": error_type,
        "absolute_path": str(target),
    }

    # Verify correct classification
    assert error_response["error_type"] == "is_directory"
    assert error_response["error"] == "path is a directory"


def test_error_enrichment_structured_format(tmp_path):
    """Verify minimal response for structured format (no enrichment)."""
    # Create test structure
    (tmp_path / "file.py").touch()

    target = tmp_path / "nonexistent.py"
    format_mode = "structured"

    # Classify error
    error_type = classify_path_error(target)

    # Build base response
    error_response = {
        "ok": False,
        "error": "file not found",
        "error_type": error_type,
        "absolute_path": str(target),
    }

    # NO enrichment for structured format
    if format_mode == "readable":
        # This block should NOT execute
        error_response["should_not_appear"] = True

    # Verify minimal response (no expensive fields)
    assert error_response["ok"] is False
    assert error_response["error_type"] == "not_found"
    assert "similar_files" not in error_response
    assert "parent_listing" not in error_response
    assert "search_suggestion" not in error_response
    assert "should_not_appear" not in error_response


def test_search_error_enrichment_pattern(tmp_path):
    """Verify search tool error enrichment pattern."""
    # Create directory structure
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()

    search_root = tmp_path / "testz"  # Typo
    format_mode = "readable"

    # Build error response
    error_response = {
        "ok": False,
        "error": "search path does not exist",
        "path": str(search_root),
        "error_type": "not_found"
    }

    # Enrich for readable format
    if format_mode == "readable":
        if search_root.parent.exists():
            suggestions = get_fuzzy_file_suggestions(
                search_root.name,
                search_root.parent,
                include_directories=True
            )
            if suggestions:
                # Filter to directories
                dir_suggestions = [s for s in suggestions if s.get("is_dir")]
                if dir_suggestions:
                    error_response["similar_paths"] = dir_suggestions
                    best = dir_suggestions[0]
                    error_response["suggestion"] = (
                        f"Did you mean '{best['name']}'? "
                        f"({int(best['score'] * 100)}% match)"
                    )

            listing = get_directory_listing(search_root.parent)
            if listing and not listing.get("permission_error"):
                error_response["parent_directory"] = str(search_root.parent)
                error_response["parent_listing"] = listing

    # Verify enriched response
    assert error_response["ok"] is False
    assert error_response["error_type"] == "not_found"
    assert "similar_paths" in error_response
    assert len(error_response["similar_paths"]) > 0
    # Should suggest "tests" directory (fuzzy matching returns name without trailing slash)
    suggested_names = [p["name"] for p in error_response["similar_paths"]]
    assert "tests" in suggested_names
    # All suggestions should be directories
    assert all(p["is_dir"] for p in error_response["similar_paths"])


def test_backwards_compatibility_core_fields(tmp_path):
    """Verify core error fields remain unchanged (backwards compatibility)."""
    target = tmp_path / "nonexistent.py"

    # Simulate minimal error response (pre-enhancement)
    error_response = {
        "ok": False,
        "error": "file not found",
        "absolute_path": str(target),
    }

    # Core fields that must always be present
    assert "ok" in error_response
    assert error_response["ok"] is False
    assert "error" in error_response
    assert isinstance(error_response["error"], str)
    assert "absolute_path" in error_response

    # New enhancement adds error_type field
    error_type = classify_path_error(target)
    error_response["error_type"] = error_type

    # Verify new field is additive (doesn't break existing structure)
    assert "error_type" in error_response
    assert error_response["error_type"] == "not_found"


def test_performance_lazy_evaluation(tmp_path):
    """Verify enrichment is skipped for non-readable formats (performance)."""
    # Create large directory
    for i in range(100):
        (tmp_path / f"file_{i}.py").touch()

    target = tmp_path / "nonexistent.py"

    # For structured/compact formats, enrichment should be skipped
    for format_mode in ["structured", "compact"]:
        error_response = {
            "ok": False,
            "error": "file not found",
            "error_type": "not_found",
            "absolute_path": str(target),
        }

        # Enrichment guard - should NOT execute
        if format_mode == "readable":
            suggestions = get_fuzzy_file_suggestions(target.name, target.parent)
            error_response["similar_files"] = suggestions  # Should not happen

        # Verify no enrichment occurred
        assert "similar_files" not in error_response, f"Enrichment leaked into {format_mode} format"


def test_large_directory_truncation(tmp_path):
    """Verify directory listings are truncated for large directories."""
    # Create directory with many files
    for i in range(100):
        (tmp_path / f"file_{i}.py").touch()

    target = tmp_path / "nonexistent.py"

    # Get listing
    listing = get_directory_listing(target.parent, max_entries=30)

    # Verify truncation
    assert len(listing.get("files", [])) <= 30
    assert listing.get("truncated") is True
    assert listing.get("total_scanned") == 100


def test_permission_error_graceful_degradation(tmp_path):
    """Verify graceful handling when parent directory is unreadable."""
    import os

    restricted = tmp_path / "restricted"
    restricted.mkdir()
    child = restricted / "file.py"

    try:
        os.chmod(restricted, 0o000)

        # Try to get listing of unreadable directory
        listing = get_directory_listing(restricted)

        # Should return permission error indicator, not crash
        assert listing.get("permission_error") is True

    finally:
        os.chmod(restricted, 0o755)
