"""Reusable project fixtures for src-layout tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_payload(tmp_path: Path) -> dict[str, str]:
    """Return a project payload rooted in tmp_path."""
    project_root = tmp_path / "test_project"
    project_root.mkdir(parents=True, exist_ok=True)
    return {
        "name": "test_project",
        "root": str(project_root),
        "progress_log": str(project_root / "PROGRESS_LOG.md"),
    }
