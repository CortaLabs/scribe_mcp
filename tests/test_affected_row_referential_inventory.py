from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from scribe_mcp.cli import main
from scribe_mcp.storage.affected_row_referential_inventory import (
    BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK,
    BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE,
    BLOCKED_STORAGE_BACKEND_UNAVAILABLE,
    BLOCKED_TARGET_BINDING_UNPROVEN,
    INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL,
    INVENTORY_NO_AFFECTED_ROWS,
    INVENTORY_REPAIR_NOT_REQUIRED,
    build_affected_row_referential_inventory_report,
    mutation_rejected_report,
    storage_backend_unavailable_report,
)
from scribe_mcp.storage.sqlite import SQLiteStorage


def _assert_public_safe(payload: dict[str, object]) -> None:
    forbidden_fragments = (
        "postgresql://",
        "sqlite://",
        "select ",
        "insert ",
        "update ",
        "delete ",
        "dump",
        "database=",
        "host=",
        "password",
        "/tmp/",
        "private_output_sentinel",
    )
    for value in payload.values():
        assert isinstance(value, (str, bool, int, list, dict))
        rendered = json.dumps(value).lower()
        assert all(fragment not in rendered for fragment in forbidden_fragments)


def test_public_report_contains_only_safe_aggregate_shape() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[{"repo_id": "", "project_key": ""}] * 5,
        reference_counts={"session_projects": 0, "agent_projects": 0, "agent_recent_projects": 0},
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == INVENTORY_REPAIR_NOT_REQUIRED
    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False
    assert payload["affected_project_rows_count_bucket"] == "PUBLIC_SAFE_AGGREGATE"
    _assert_public_safe(payload)


def test_public_report_redacts_private_output_fail_closed() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[],
        reference_counts={
            "session_projects": 0,
            "agent_projects": 0,
            "agent_recent_projects": 0,
            "private_selector_/tmp/target": 0,
        },
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["output_contract_status_label"] == "BLOCKED_PUBLIC_SAFE_OUTPUT_CONTRACT_UNPROVEN"
    assert payload["private_output_detected"] is True


def test_report_blocks_low_cardinality_identifying_buckets() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[{"repo_id": "", "project_key": ""}],
        reference_counts={"session_projects": 0, "agent_projects": 0, "agent_recent_projects": 0},
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert BLOCKED_LOW_CARDINALITY_OR_PRIVATE_RISK in payload["labels"]
    assert payload["affected_project_rows_count"] == 0
    assert payload["affected_project_rows_count_bucket"] == "LOW_CARDINALITY_SUPPRESSED"


def test_report_blocks_target_binding_failure() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[],
        reference_counts={"session_projects": 0, "agent_projects": 0, "agent_recent_projects": 0},
        target_binding_status_label="BLOCKED_TARGET_BINDING_UNPROVEN",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["target_binding_status_label"] == BLOCKED_TARGET_BINDING_UNPROVEN
    assert BLOCKED_TARGET_BINDING_UNPROVEN in payload["labels"]


def test_report_blocks_referential_inventory_incomplete() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[],
        reference_counts={},
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["referential_inventory_status_label"] == BLOCKED_REFERENTIAL_INVENTORY_INCOMPLETE


def test_report_labels_no_affected_rows() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[],
        reference_counts={"session_projects": 0, "agent_projects": 0, "agent_recent_projects": 0},
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    assert report.to_public_dict()["status_label"] == INVENTORY_NO_AFFECTED_ROWS


def test_report_labels_mutation_candidate_for_public_safe_references() -> None:
    report = build_affected_row_referential_inventory_report(
        project_rows=[{"repo_id": "", "project_key": ""}] * 5,
        reference_counts={"session_projects": 5, "agent_projects": 0, "agent_recent_projects": 0},
        target_binding_status_label="PASS",
        selected_context_readback_status_label="PASS",
    )

    payload = report.to_public_dict()

    assert payload["status_label"] == INVENTORY_MUTATION_CANDIDATE_REQUIRES_CUSTODY_AND_REHEARSAL
    assert payload["total_reference_rows_count_bucket"] == "PUBLIC_SAFE_AGGREGATE"


def test_storage_backend_unavailable_failure_payload() -> None:
    payload = storage_backend_unavailable_report().to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["storage_backend_status_label"] == BLOCKED_STORAGE_BACKEND_UNAVAILABLE
    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False


def test_mutation_shaped_cli_report_is_rejected() -> None:
    payload = mutation_rejected_report().to_public_dict()

    assert payload["status_label"] == "BLOCK"
    assert payload["mutation_attempted"] is False
    assert payload["mutation_authorized"] is False


def test_sqlite_storage_inventory_uses_readonly_connection_without_initialising(tmp_path: Path) -> None:
    db_path = tmp_path / "scribe.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE scribe_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            repo_root TEXT NOT NULL,
            repo_id TEXT,
            project_key TEXT,
            progress_log_path TEXT NOT NULL
        );
        CREATE TABLE session_projects (project_id INTEGER);
        CREATE TABLE agent_projects (project_name TEXT);
        CREATE TABLE agent_recent_projects (project_name TEXT);
        """
    )
    conn.executemany(
        "INSERT INTO scribe_projects (name, repo_root, repo_id, project_key, progress_log_path) VALUES (?, ?, ?, ?, ?)",
        [(f"p{i}", f"/repo/{i}", "", "", "PROGRESS.md") for i in range(5)],
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(db_path)
    report = asyncio.run(
        storage.affected_row_referential_inventory_readonly(
            target_binding_status_label="PASS",
            selected_context_readback_status_label="PASS",
        )
    )

    assert report.to_public_dict()["status_label"] == INVENTORY_REPAIR_NOT_REQUIRED
    assert storage._initialised is False


def test_cli_preflight_requires_dry_run() -> None:
    assert main.main(["affected-row-inventory", "preflight", "--json"]) == 2


def test_cli_preflight_rejects_apply() -> None:
    assert main.main(["affected-row-inventory", "preflight", "--dry-run", "--apply", "--json"]) == 2
