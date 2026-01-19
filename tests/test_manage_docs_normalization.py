"""
Unit test for Task Package 2.5: manage_docs project parameter normalization.

Verifies that manage_docs correctly normalizes project names regardless of input format
(hyphens, spaces, underscores, mixed case) by testing the normalization function directly.
"""

import pytest
from scribe_mcp.utils.slug import normalize_project_input


def test_normalize_project_input_handles_hyphens():
    """Test that normalize_project_input converts hyphens to underscores."""
    assert normalize_project_input("my-test-project") == "my_test_project"
    assert normalize_project_input("another-name") == "another_name"


def test_normalize_project_input_handles_mixed_case():
    """Test that normalize_project_input converts to lowercase."""
    assert normalize_project_input("My-Project") == "my_project"
    assert normalize_project_input("UPPERCASE") == "uppercase"
    assert normalize_project_input("MixedCase") == "mixedcase"


def test_normalize_project_input_handles_spaces():
    """Test that normalize_project_input converts spaces to underscores."""
    assert normalize_project_input("my project") == "my_project"
    assert normalize_project_input("test name here") == "test_name_here"


def test_normalize_project_input_handles_none():
    """Test that normalize_project_input handles None gracefully."""
    assert normalize_project_input(None) is None


def test_normalize_project_input_handles_empty_string():
    """Test that normalize_project_input handles empty strings."""
    result = normalize_project_input("")
    assert result is None or result == ""


def test_normalize_project_input_already_normalized():
    """Test that already normalized names pass through unchanged."""
    assert normalize_project_input("my_project") == "my_project"
    assert normalize_project_input("test_name") == "test_name"


def test_normalize_project_input_complex_cases():
    """Test complex normalization scenarios."""
    # Multiple types of separators
    assert normalize_project_input("My-Test_Project Name") == "my_test_project_name"

    # Special characters
    assert normalize_project_input("project@2024") == "project_2024"

    # Leading/trailing separators
    assert normalize_project_input("-my-project-") == "my_project"
