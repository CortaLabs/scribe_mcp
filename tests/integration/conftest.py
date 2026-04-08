"""Area-local fixtures for release-facing integration workflow tests."""

from __future__ import annotations

import pytest

from scribe_mcp.shared.execution_context import RouterContextManager


@pytest.fixture
def project_tree(tmp_path):
    """Create a realistic project tree with mixed file types."""
    (tmp_path / "main.py").write_text("import os\nimport sys\n\ndef main():\n    print('hello')\n")
    (tmp_path / "utils.py").write_text("def helper():\n    return 42\n\ndef another_helper():\n    return 99\n")

    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "core.py").write_text("class Core:\n    def run(self):\n        pass\n")
    (sub / "config.json").write_text('{"key": "value"}\n')

    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (tmp_path / "data.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
    (tmp_path / "compiled.pyc").write_bytes(b"\x00" * 50)
    (tmp_path / "readme.md").write_text("# Readme\n\nSome documentation.\n")
    (tmp_path / ".hidden").write_text("secret\n")
    return tmp_path


@pytest.fixture
def router():
    """Create a fresh RouterContextManager for session tests."""
    return RouterContextManager()
