#!/usr/bin/env python3
"""Tests for the SQLite-backed ProjectRegistry helper."""

import sqlite3
from pathlib import Path

import pytest

from scribe_mcp.shared.project_registry import ProjectRegistry  # noqa: E402


def _make_temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "registry_test.db"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Minimal schema before ProjectRegistry._ensure_schema runs.
        cur.execute(
            """
            CREATE TABLE scribe_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                repo_root TEXT NOT NULL,
                progress_log_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE dev_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                project_name TEXT NOT NULL,
                plan_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                version TEXT,
                metadata TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE scribe_metrics (
                project_id INTEGER PRIMARY KEY,
                total_entries INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                warn_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                last_update TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _get_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cur.fetchall()}
    finally:
        conn.close()


def test_ensure_schema_adds_registry_columns(tmp_path: Path) -> None:
    """_ensure_schema should add registry-focused columns on existing installs."""
    db_path = _make_temp_db(tmp_path)

    # Instantiate registry against temp DB; this should run _ensure_schema.
    ProjectRegistry(db_path=db_path)

    cols = _get_columns(db_path, "scribe_projects")
    # Core original cols still there
    assert {"id", "name", "repo_root", "progress_log_path", "created_at", "updated_at"}.issubset(cols)
    # Registry columns added non-destructively
    for new_col in ("description", "last_entry_at", "last_access_at", "last_status_change", "tags", "meta"):
        assert new_col in cols


def test_touch_entry_auto_promotes_planning_to_in_progress(tmp_path: Path) -> None:
    """touch_entry should promote planning→in_progress once docs exist and a progress log is written."""
    db_path = _make_temp_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Insert planning project
        cur.execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, created_at, updated_at, status)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'planning')
            """,
            ("registry_lifecycle_test", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md")),
        )
        project_id = cur.lastrowid
        # Insert core dev_plan docs for this project
        for plan_type in ("architecture", "phase_plan", "checklist", "progress_log"):
            cur.execute(
                """
                INSERT INTO dev_plans (project_id, project_name, plan_type, file_path, version, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "registry_lifecycle_test",
                    plan_type,
                    str(tmp_path / f"{plan_type}.md"),
                    "1.0",
                    "{}",
                ),
            )
        conn.commit()
    finally:
        conn.close()

    registry = ProjectRegistry(db_path=db_path)

    # Call touch_entry with a non-progress log_type: should NOT promote.
    registry.touch_entry("registry_lifecycle_test", log_type="doc_updates")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM scribe_projects WHERE name = 'registry_lifecycle_test'"
        )
        (status_after_docs_only,) = cur.fetchone()
    finally:
        conn.close()
    assert status_after_docs_only == "planning"

    # Call touch_entry with progress log: should promote to in_progress.
    registry.touch_entry("registry_lifecycle_test", log_type="progress")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, last_status_change FROM scribe_projects WHERE name = 'registry_lifecycle_test'"
        )
        row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None
    status, last_status_change = row
    assert status == "in_progress"
    assert last_status_change is not None


def test_record_doc_update_sets_doc_hygiene_flags(tmp_path: Path) -> None:
    """record_doc_update should maintain hashes and derive simple flags."""
    db_path = _make_temp_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, created_at, updated_at, status)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'planning')
            """,
            ("doc_flags_test", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md")),
        )
        conn.commit()
    finally:
        conn.close()

    registry = ProjectRegistry(db_path=db_path)

    # First update: baseline + current hashes for architecture.
    registry.record_doc_update(
        "doc_flags_test",
        doc="architecture",
        action="replace_section",
        before_hash="template-hash",
        after_hash="edited-hash",
    )

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT meta FROM scribe_projects WHERE name = 'doc_flags_test'")
        (meta_raw,) = cur.fetchone()
    finally:
        conn.close()

    assert meta_raw is not None
    import json

    meta = json.loads(meta_raw)
    docs_meta = meta.get("docs") or {}

    baseline = docs_meta.get("baseline_hashes", {})
    current = docs_meta.get("current_hashes", {})
    flags = docs_meta.get("flags", {})

    assert baseline.get("architecture") == "template-hash"
    assert current.get("architecture") == "edited-hash"
    assert flags.get("architecture_touched") is True
    assert flags.get("architecture_modified") is True
    assert flags.get("docs_hash_drift") is True
    assert flags.get("docs_ready_for_work") is False


def test_record_doc_update_core_readiness_tracks_drift(tmp_path: Path) -> None:
    """Core-doc readiness should drop when a core doc drifts from baseline."""
    db_path = _make_temp_db(tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, created_at, updated_at, status)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'planning')
            """,
            ("doc_readiness_test", str(tmp_path), str(tmp_path / "PROGRESS_LOG.md")),
        )
        conn.commit()
    finally:
        conn.close()

    registry = ProjectRegistry(db_path=db_path)
    for doc_name, hash_value in (
        ("architecture", "arch-1"),
        ("phase_plan", "plan-1"),
        ("checklist", "check-1"),
    ):
        registry.record_doc_update(
            "doc_readiness_test",
            doc=doc_name,
            action="auto_register",
            after_hash=hash_value,
        )

    info = registry.get_project("doc_readiness_test")
    assert info is not None
    docs_meta = info.meta.get("docs") or {}
    flags = docs_meta.get("flags") or {}
    assert flags.get("docs_ready_for_work") is True
    assert flags.get("docs_hash_drift") is False
    assert docs_meta.get("core_docs_with_drift") == []

    registry.record_doc_update(
        "doc_readiness_test",
        doc="phase_plan",
        action="replace_section",
        before_hash="plan-1",
        after_hash="plan-2",
    )

    info = registry.get_project("doc_readiness_test")
    assert info is not None
    docs_meta = info.meta.get("docs") or {}
    flags = docs_meta.get("flags") or {}
    assert flags.get("phase_plan_modified") is True
    assert flags.get("docs_hash_drift") is True
    assert flags.get("docs_ready_for_work") is False
    assert docs_meta.get("core_docs_with_drift") == ["phase_plan"]


def test_get_project_enriches_meta_with_activity_and_drift(tmp_path: Path) -> None:
    """get_project should add activity metrics and doc drift hints into meta."""
    db_path = _make_temp_db(tmp_path)
    # Ensure registry-specific columns exist before inserting extended data.
    ProjectRegistry(db_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Create a project with explicit timestamps and doc meta.
        cur.execute(
            """
            INSERT INTO scribe_projects (name, repo_root, progress_log_path, created_at, updated_at, status, last_entry_at, last_access_at, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "activity_drift_test",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                "2000-01-01 00:00:00",
                "2000-01-01 00:00:00",
                "in_progress",
                "2000-01-20T00:00:00+00:00",
                "2000-01-10 00:00:00",
                '{"docs":{"last_update_at":"2000-01-01T00:00:00+00:00","flags":{"docs_ready_for_work":true}}}',
            ),
        )
        conn.commit()
    finally:
        conn.close()

    registry = ProjectRegistry(db_path=db_path)
    info = registry.get_project("activity_drift_test")
    assert info is not None

    activity = info.meta.get("activity") or {}
    assert "project_age_days" in activity
    assert "days_since_last_entry" in activity
    assert "days_since_last_access" in activity
    assert activity.get("staleness_level") in {"fresh", "warming", "stale", "frozen"}

    docs_meta = (info.meta.get("docs") or {})
    flags = (docs_meta.get("flags") or {})
    # Because last_entry_at is significantly later than last_update_at and status is in_progress,
    # doc_drift_suspected should be True and we should have a drift days metric.
    assert flags.get("doc_drift_suspected") is True
    assert "doc_drift_days_since_update" in docs_meta
    # Drift score should be positive when drift is suspected.
    assert docs_meta.get("drift_score", 0.0) > 0.0
