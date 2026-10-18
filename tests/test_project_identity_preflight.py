from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from scribe_mcp.cli import main as cli_main
from scribe_mcp.storage.project_identity_preflight import (
    AMBIGUOUS_TARGET_BINDING_LABEL,
    DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL,
    LOW_CARDINALITY_BUCKET_LABEL,
    MUTATION_REJECTED_LABEL,
    REDACTION_GUARD_BLOCK,
    REFERENTIAL_INTEGRITY_UNCERTAIN_LABEL,
    ProjectIdentityPreflightReport,
    build_project_identity_preflight_report,
    build_sqlite_project_identity_preflight,
)
from scribe_mcp.storage.models import compute_project_key, compute_repo_id, normalize_repo_root
from scribe_mcp.storage.sqlite import SQLiteStorage


def test_public_report_contains_only_safe_aggregate_shape() -> None:
    report = ProjectIdentityPreflightReport(
        status_label="BLOCK",
        total_project_rows=2,
        missing_identity_rows=1,
        canonical_retention_candidates=1,
        blocked_state_count=4,
        labels=("EXISTING_ROW_REPAIR_READINESS_CANDIDATES",),
    )

    payload = report.to_public_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False
    assert payload["status_label"] == "BLOCK"
    assert "pk_" not in encoded
    assert "repo_alpha" not in encoded
    assert "synthetic_project" not in encoded


def test_public_report_redacts_private_output_fail_closed() -> None:
    report = ProjectIdentityPreflightReport(
        status_label="PASS",
        blocked_state_count=0,
        labels=("PRIVATE_OUTPUT_SENTINEL",),
    )

    payload = report.to_public_dict()
    encoded = json.dumps(payload, sort_keys=True)

    assert payload["status_label"] == "BLOCK"
    assert payload["redaction_status_label"] == REDACTION_GUARD_BLOCK
    assert payload["private_output_detected"] is True
    assert payload["blocked_state_count"] == 1
    assert "PRIVATE_OUTPUT_SENTINEL" not in encoded


def test_preflight_report_blocks_ambiguous_target_binding_by_default() -> None:
    report = build_project_identity_preflight_report(
        project_rows=[],
        legacy_name_constraint_present=False,
        legacy_name_index_present=False,
        dependent_reference_rows=0,
    )
    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["ambiguous_target_binding_status_label"] == AMBIGUOUS_TARGET_BINDING_LABEL
    assert AMBIGUOUS_TARGET_BINDING_LABEL in payload["labels"]


def test_preflight_report_blocks_already_populated_duplicate_project_keys() -> None:
    normalized_root = normalize_repo_root("synthetic-duplicate-repo")
    duplicate_key = compute_project_key(repo_root=normalized_root, project_name="synthetic-duplicate")
    repo_id = compute_repo_id(normalized_root)

    report = build_project_identity_preflight_report(
        project_rows=[
            {
                "id": 1,
                "name": "synthetic-duplicate",
                "repo_root": normalized_root,
                "repo_id": repo_id,
                "project_key": duplicate_key,
            },
            {
                "id": 2,
                "name": "synthetic-duplicate-alias",
                "repo_root": normalized_root,
                "repo_id": repo_id,
                "project_key": duplicate_key,
            },
        ],
        legacy_name_constraint_present=False,
        legacy_name_index_present=False,
        dependent_reference_rows=0,
    )
    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["already_populated_duplicate_project_key_groups"] == 1
    assert "ALREADY_POPULATED_DUPLICATE_PROJECT_KEY_GROUPS" in payload["labels"]


def test_preflight_report_blocks_low_cardinality_identifying_buckets() -> None:
    report = build_project_identity_preflight_report(
        project_rows=[
            {
                "id": 1,
                "name": "synthetic-singleton",
                "repo_root": "synthetic-singleton-repo",
                "repo_id": None,
                "project_key": None,
            }
        ],
        legacy_name_constraint_present=False,
        legacy_name_index_present=False,
        dependent_reference_rows=0,
    )
    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["low_cardinality_bucket_status_label"] == LOW_CARDINALITY_BUCKET_LABEL
    assert LOW_CARDINALITY_BUCKET_LABEL in payload["labels"]


def test_preflight_report_blocks_dependent_reference_uncertainty() -> None:
    report = build_project_identity_preflight_report(
        project_rows=[],
        legacy_name_constraint_present=False,
        legacy_name_index_present=False,
        dependent_reference_rows=2,
    )
    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["dependent_reference_rows"] == 2
    assert payload["dependent_reference_preservation_status_label"] == DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL
    assert payload["referential_integrity_status_label"] == REFERENTIAL_INTEGRITY_UNCERTAIN_LABEL
    assert DEPENDENT_REFERENCE_PRESERVATION_REQUIRED_LABEL in payload["labels"]


def test_sqlite_preflight_classifies_candidates_without_mutating(tmp_path: Path) -> None:
    db_path = tmp_path / "identity_preflight.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            repo_id TEXT,
            project_key TEXT,
            progress_log_path TEXT NOT NULL
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO scribe_projects (name, repo_root, repo_id, project_key, progress_log_path)
        VALUES (?, ?, ?, ?, ?);
        """,
        [
            ("synthetic-alpha", str(tmp_path / "repo_alpha"), None, None, "alpha.log"),
            ("synthetic_alpha", str(tmp_path / "repo_alpha"), None, None, "alpha-alias.log"),
            ("synthetic-beta", "", None, None, "beta.log"),
        ],
    )
    before = [dict(row) for row in conn.execute("SELECT * FROM scribe_projects ORDER BY id;").fetchall()]

    async def _fetchone(query: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        return conn.execute(query, params).fetchone()

    async def _fetchall(query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        return list(conn.execute(query, params).fetchall())

    report = asyncio.run(
        build_sqlite_project_identity_preflight(
            fetchall_fn=_fetchall,
            fetchone_fn=_fetchone,
        )
    )
    after = [dict(row) for row in conn.execute("SELECT * FROM scribe_projects ORDER BY id;").fetchall()]
    conn.close()

    payload = report.to_public_dict()
    assert before == after
    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False
    assert payload["status_label"] == "BLOCK"
    assert payload["missing_identity_rows"] == 2
    assert payload["canonical_retention_candidates"] == 1
    assert payload["legacy_key_assignment_candidates"] == 1
    assert payload["missing_unusable_repo_root_rows"] == 1
    assert payload["redaction_status_label"] == "REDACTION_GUARD_PASS"


def test_sqlite_storage_preflight_does_not_initialise_or_write(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "storage_preflight.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            repo_id TEXT,
            project_key TEXT,
            progress_log_path TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO scribe_projects (name, repo_root, repo_id, project_key, progress_log_path)
        VALUES (?, ?, ?, ?, ?);
        """,
        ("synthetic-alpha", str(tmp_path / "repo_alpha"), None, None, "alpha.log"),
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(db_path)

    async def fail_initialise() -> None:
        raise AssertionError("preflight must not initialise SQLite storage")

    monkeypatch.setattr(storage, "_initialise", fail_initialise)

    async def _run() -> None:
        report = await storage.preflight_project_identity_repair()
        assert report.to_public_dict()["missing_identity_rows"] == 1

    asyncio.run(_run())


def test_cli_project_identity_apply_fails_before_storage_access(monkeypatch, capsys) -> None:
    def fail_create_storage_backend():
        raise AssertionError("mutation-shaped invocation must not create storage")

    monkeypatch.setattr("scribe_mcp.storage.create_storage_backend", fail_create_storage_backend)

    exit_code = cli_main.main(["project-identity", "preflight", "--apply"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert MUTATION_REJECTED_LABEL in captured.err
    assert "project_key" not in captured.out
