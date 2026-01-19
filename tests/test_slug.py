"""Tests for canonical slugify functions in utils/slug.py."""

import pytest

from scribe_mcp.utils.slug import slugify_project_name, slugify_filename


class TestSlugifyProjectName:
    """Test suite for slugify_project_name function."""

    def test_spaces_to_underscores(self):
        """Spaces should be converted to underscores."""
        assert slugify_project_name("my project") == "my_project"

    def test_hyphens_to_underscores(self):
        """Hyphens should be converted to underscores."""
        assert slugify_project_name("my-project") == "my_project"

    def test_mixed_separators(self):
        """Mixed spaces and hyphens should all become underscores."""
        assert slugify_project_name("my-project name") == "my_project_name"

    def test_special_chars_removed(self):
        """Special characters should be removed."""
        assert slugify_project_name("project@v1.0!") == "project_v1_0"

    def test_empty_returns_default(self):
        """Empty or whitespace-only strings should return 'project'."""
        assert slugify_project_name("") == "project"
        assert slugify_project_name("   ") == "project"

    def test_lowercase(self):
        """All characters should be converted to lowercase."""
        assert slugify_project_name("MyProject") == "myproject"

    def test_real_project_names(self):
        """Test with realistic project names."""
        assert slugify_project_name("manage-docs-fix") == "manage_docs_fix"
        assert slugify_project_name("My Awesome Project") == "my_awesome_project"
        assert slugify_project_name("auth_refactor") == "auth_refactor"
        assert slugify_project_name("db-migration-2024") == "db_migration_2024"

    def test_leading_trailing_underscores_stripped(self):
        """Leading and trailing underscores should be stripped."""
        assert slugify_project_name("_project_") == "project"
        assert slugify_project_name("__test__") == "test"

    def test_consecutive_special_chars_collapsed(self):
        """Consecutive special characters become single underscore."""
        # The regex [^0-9a-z_]+ matches one or more, so "a@#b" -> "a_b"
        result = slugify_project_name("a@#b")
        assert result == "a_b"

    def test_numbers_preserved(self):
        """Numbers should be preserved in slugs."""
        assert slugify_project_name("project123") == "project123"
        assert slugify_project_name("2024-release") == "2024_release"


class TestSlugifyFilename:
    """Test suite for slugify_filename function."""

    def test_preserves_hyphens(self):
        """Hyphens should be preserved in filenames."""
        assert slugify_filename("my-doc") == "my-doc"

    def test_preserves_dots(self):
        """Dots should be preserved in filenames."""
        assert slugify_filename("config.yaml") == "config.yaml"
        assert slugify_filename("file.tar.gz") == "file.tar.gz"

    def test_collapses_underscores(self):
        """Multiple underscores should be collapsed to single underscore."""
        assert slugify_filename("my___doc") == "my_doc"

    def test_empty_returns_default(self):
        """Empty strings should return 'document'."""
        assert slugify_filename("") == "document"
        assert slugify_filename("   ") == "document"

    def test_special_chars_to_underscore(self):
        """Special characters (not in allowed set) should become underscores."""
        assert slugify_filename("my@doc") == "my_doc"
        assert slugify_filename("file#name") == "file_name"

    def test_preserves_case(self):
        """Case should be preserved in filenames."""
        assert slugify_filename("MyDocument.md") == "MyDocument.md"

    def test_real_filenames(self):
        """Test with realistic filenames."""
        assert slugify_filename("ARCHITECTURE_GUIDE.md") == "ARCHITECTURE_GUIDE.md"
        assert slugify_filename("RESEARCH_auth_20240115.md") == "RESEARCH_auth_20240115.md"
        assert slugify_filename("config-file.yaml") == "config-file.yaml"


class TestBackwardsCompatibility:
    """Test that imports from old locations still work."""

    def test_import_from_project_utils(self):
        """Verify slugify_project_name can still be imported from project_utils."""
        from scribe_mcp.tools.project_utils import slugify_project_name as pu_slugify
        assert pu_slugify("test-project") == "test_project"

    def test_import_from_utils_root(self):
        """Verify slugify functions are exported from utils __init__.py."""
        from scribe_mcp.utils import slugify_project_name, slugify_filename
        assert slugify_project_name("my-project") == "my_project"
        assert slugify_filename("my-doc.md") == "my-doc.md"


class TestConsistencyAcrossModules:
    """Test that all slugify implementations behave consistently."""

    def test_all_sources_match(self):
        """All import paths should return identical results."""
        from scribe_mcp.utils.slug import slugify_project_name as canonical
        from scribe_mcp.tools.project_utils import slugify_project_name as pu_version

        test_cases = [
            "my project",
            "my-project",
            "MyProject",
            "manage-docs-fix",
            "",
            "   ",
            "project@v1.0!",
        ]

        for case in test_cases:
            assert canonical(case) == pu_version(case), f"Mismatch for input: {repr(case)}"
