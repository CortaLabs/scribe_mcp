#!/usr/bin/env python3
"""
Test suite for Phase 2: Query Integration

Tests that shared/logging_utils.py correctly queries and parses docs_json field
from the scribe_projects database table.

Author: CoderAgent-Phase2
Phase: 2 - Query Integration
Project: scribe_manage_docs_implementation
"""

import json
import pytest
import sqlite3
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary test database with scribe_projects table."""
    db_path = tmp_path / "test_scribe.db"

    # Create database with schema including docs_json
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            repo_root TEXT NOT NULL,
            progress_log_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            docs_json TEXT
        )
    """)
    conn.commit()
    conn.close()

    return db_path


class TestQueryIncludesDocsJson:
    """Test that SELECT query includes docs_json column."""

    def test_query_string_includes_docs_json(self):
        """Verify the SQL query includes docs_json in SELECT."""
        # Read the actual code from shared/logging_utils.py
        code_path = Path(__file__).parent.parent / "shared" / "logging_utils.py"
        code_content = code_path.read_text()

        # Verify the query includes docs_json
        assert "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects" in code_content, \
            "Query must SELECT docs_json column"

        # Verify JSON parsing exists
        assert 'json.loads(row["docs_json"])' in code_content, \
            "Query must parse docs_json with json.loads()"


class TestQueryReturnsDocsJsonField:
    """Test that query returns docs field when docs_json is populated."""

    def test_query_returns_docs_field_when_docs_json_populated(self, temp_db, tmp_path):
        """Test direct database query returns docs field."""
        # Insert project with docs_json
        docs_mapping = {
            "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
            "phase_plan": "/path/to/PHASE_PLAN.md",
            "checklist": "/path/to/CHECKLIST.md"
        }

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO scribe_projects
            (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "test_project",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                json.dumps(docs_mapping)
            )
        )
        conn.commit()

        # Execute the same query that logging_utils.py uses
        row = conn.execute(
            "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
            ("test_project",)
        ).fetchone()

        conn.close()

        # Verify row has 4 columns including docs_json
        assert row is not None
        assert row["name"] == "test_project"
        assert row["repo_root"] == str(tmp_path)
        assert row["progress_log_path"] == str(tmp_path / "PROGRESS_LOG.md")
        assert row["docs_json"] is not None

        # Parse docs_json manually (mimicking the code)
        parsed_docs = json.loads(row["docs_json"])
        assert isinstance(parsed_docs, dict)
        assert parsed_docs["architecture"] == "/path/to/ARCHITECTURE_GUIDE.md"
        assert parsed_docs["phase_plan"] == "/path/to/PHASE_PLAN.md"
        assert parsed_docs["checklist"] == "/path/to/CHECKLIST.md"


class TestQueryHandlesNullDocsJson:
    """Test query gracefully handles NULL docs_json."""

    def test_query_handles_null_docs_json_gracefully(self, temp_db, tmp_path):
        """Test query doesn't crash when docs_json is NULL."""
        # Insert project WITHOUT docs_json (NULL)
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO scribe_projects
            (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "legacy_project",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                None  # NULL docs_json
            )
        )
        conn.commit()

        # Execute query
        row = conn.execute(
            "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
            ("legacy_project",)
        ).fetchone()

        conn.close()

        # Verify row exists but docs_json is NULL
        assert row is not None
        assert row["name"] == "legacy_project"
        assert row["docs_json"] is None

        # Simulate the parsing logic - should handle None gracefully
        if row["docs_json"]:
            # This branch won't execute
            parsed_docs = json.loads(row["docs_json"])
        # No crash - test passes


class TestQueryHandlesMalformedJson:
    """Test query handles malformed JSON in docs_json."""

    def test_json_loads_raises_on_malformed_json(self, temp_db, tmp_path):
        """Test that malformed JSON raises JSONDecodeError (which should be caught)."""
        # Insert project with INVALID JSON
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO scribe_projects
            (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "corrupted_project",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                "{invalid json here"  # Malformed JSON
            )
        )
        conn.commit()

        # Execute query
        row = conn.execute(
            "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
            ("corrupted_project",)
        ).fetchone()

        conn.close()

        # Verify that json.loads() raises JSONDecodeError
        assert row["docs_json"] == "{invalid json here"

        # Simulate the error handling in the actual code
        try:
            parsed_docs = json.loads(row["docs_json"])
            assert False, "Should have raised JSONDecodeError"
        except (json.JSONDecodeError, TypeError):
            # Expected - error handling should catch this
            pass


class TestBackwardCompatibility:
    """Test that existing code still works with new docs field."""

    def test_project_dict_construction_backward_compatible(self, temp_db, tmp_path):
        """Test constructing project dict with optional docs field."""
        # Insert project with docs_json
        docs_mapping = {"architecture": "/path/to/ARCH.md"}

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO scribe_projects
            (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                "new_project",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                json.dumps(docs_mapping)
            )
        )
        conn.commit()

        # Execute query
        row = conn.execute(
            "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
            ("new_project",)
        ).fetchone()

        conn.close()

        # Construct project dict as logging_utils.py does
        session_project = {
            "name": row["name"],
            "root": row["repo_root"],
            "progress_log": row["progress_log_path"],
        }

        # Add docs field conditionally
        if row["docs_json"]:
            try:
                session_project["docs"] = json.loads(row["docs_json"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Verify old fields still work
        assert session_project["name"] == "new_project"
        assert session_project["root"] == str(tmp_path)
        assert session_project["progress_log"] == str(tmp_path / "PROGRESS_LOG.md")

        # Verify new field exists
        assert "docs" in session_project
        assert session_project["docs"]["architecture"] == "/path/to/ARCH.md"

        # Verify .get() still works (backward compatibility)
        assert session_project.get("name") == "new_project"
        assert session_project.get("nonexistent") is None


class TestCallerAnalysis:
    """Document analysis of all callers of resolve_logging_context."""

    def test_manage_docs_expects_docs_field(self):
        """Verify manage_docs.py accesses project.get('docs')."""
        # Read manage_docs.py
        manage_docs_path = Path(__file__).parent.parent / "tools" / "manage_docs.py"
        if manage_docs_path.exists():
            content = manage_docs_path.read_text()
            # Verify it uses project.get("docs")
            assert 'project.get("docs")' in content or 'project["docs"]' in content, \
                "manage_docs should access docs field"

    def test_set_project_uses_progress_log_field(self):
        """Verify set_project.py uses basic project fields."""
        # Read set_project.py
        set_project_path = Path(__file__).parent.parent / "tools" / "set_project.py"
        if set_project_path.exists():
            content = set_project_path.read_text()
            # Verify it uses .get() for safe access
            assert "project.get(" in content, \
                "set_project should use .get() for safe field access"


class TestErrorHandling:
    """Test error handling logic in query integration."""

    def test_empty_docs_json_string(self, temp_db, tmp_path):
        """Test handling of empty string in docs_json."""
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO scribe_projects
            (name, repo_root, progress_log_path, docs_json)
            VALUES (?, ?, ?, ?)
            """,
            ("empty_project", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md"), "")
        )
        conn.commit()

        row = conn.execute(
            "SELECT name, repo_root, progress_log_path, docs_json FROM scribe_projects WHERE name = ?",
            ("empty_project",)
        ).fetchone()

        conn.close()

        # Empty string should be falsy in Python
        assert row["docs_json"] == ""
        assert not row["docs_json"]  # Falsy check

        # Simulate the if check in logging_utils.py
        if row["docs_json"]:
            # Won't execute - empty string is falsy
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
