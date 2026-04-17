#!/usr/bin/env python3
"""Regression tests for caller-visible planning readiness/drift advisories."""

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scribe_mcp.shared.project_registry import ProjectRegistry
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools import get_project as get_project_module
from scribe_mcp.tools import read_recent as read_recent_module


def _make_temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "planning_truth_advisories.db"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
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


def test_registry_advisories_flag_readiness_contradiction_and_drift(tmp_path: Path) -> None:
    """Stale-doc contradictions should be surfaced as advisory payloads."""
    db_path = _make_temp_db(tmp_path)
    ProjectRegistry(db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO scribe_projects (
                name, repo_root, progress_log_path, created_at, updated_at,
                status, last_entry_at, meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "planning_truth_conflict",
                str(tmp_path),
                str(tmp_path / "PROGRESS_LOG.md"),
                "2000-01-01 00:00:00",
                "2000-01-01 00:00:00",
                "in_progress",
                "2000-01-20T00:00:00+00:00",
                (
                    '{"docs":{"last_update_at":"2000-01-01T00:00:00+00:00",'
                    '"flags":{"docs_ready_for_work":true,"docs_hash_drift":true}}}'
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    registry = ProjectRegistry(db_path=db_path)
    advisories = registry.get_planning_advisories("planning_truth_conflict")

    assert advisories["docs_ready_for_work"] is True
    assert advisories["docs_hash_drift"] is True
    assert advisories["doc_drift_suspected"] is True
    assert advisories["has_contradiction"] is True

    codes = {item.get("code") for item in advisories.get("advisories", [])}
    assert "docs_readiness_conflict" in codes
    assert "doc_drift_suspected" in codes


@pytest.mark.asyncio
async def test_read_recent_exposes_planning_advisories(monkeypatch, tmp_path: Path) -> None:
    """read_recent should include additive planning_advisories payloads."""
    project_name = "planning_truth_read_recent"

    expected = {
        "docs_ready_for_work": True,
        "docs_hash_drift": True,
        "doc_drift_suspected": True,
        "core_docs_with_drift": ["phase_plan"],
        "has_contradiction": True,
        "advisories": [
            {
                "code": "docs_readiness_conflict",
                "severity": "warn",
                "message": "docs_ready_for_work is true while docs_hash_drift is true.",
                "provenance": {
                    "source": "registry.docs.flags",
                    "fields": ["docs_ready_for_work", "docs_hash_drift"],
                },
            }
        ],
    }

    class _RegistryStub:
        def get_planning_advisories(self, requested_name: str):
            if requested_name == project_name:
                return expected
            return {}

    async def _prepare_context(**_kwargs):
        return LoggingContext(
            tool_name="read_recent",
            project={
                "name": project_name,
                "root": str(tmp_path),
                "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
            },
            recent_projects=[project_name],
            state_snapshot={},
            reminders=[],
        )

    fake_backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project_name)),
        fetch_recent_entries_paginated=AsyncMock(return_value=([], 0)),
    )
    fake_server = Mock()
    fake_server.state_manager = SimpleNamespace(record_tool=AsyncMock(return_value={"tool": "read_recent"}))
    fake_server.storage_backend = fake_backend
    fake_server.get_execution_context.return_value = None

    monkeypatch.setattr(read_recent_module, "server_module", fake_server)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "server_module", fake_server)
    monkeypatch.setattr(read_recent_module._READ_RECENT_HELPER, "prepare_context", _prepare_context)
    monkeypatch.setattr(read_recent_module, "_PROJECT_REGISTRY", _RegistryStub())

    result = await read_recent_module.read_recent(agent="test_agent", n=5, format="structured")

    assert result.get("ok") is not False
    assert "entries" in result
    assert result.get("planning_advisories") == expected


@pytest.mark.asyncio
async def test_get_project_structured_exposes_planning_advisories(monkeypatch, tmp_path: Path) -> None:
    """get_project structured payload should include additive planning advisories."""
    project_name = "planning_truth_get_project"
    expected = {
        "docs_ready_for_work": True,
        "docs_hash_drift": True,
        "doc_drift_suspected": True,
        "has_contradiction": True,
        "advisories": [
            {
                "code": "docs_readiness_conflict",
                "severity": "warn",
                "provenance": {
                    "source": "registry.docs.flags",
                    "fields": ["docs_ready_for_work", "docs_hash_drift"],
                },
            }
        ],
    }

    async def _prepare_context(**_kwargs):
        return LoggingContext(
            tool_name="get_project",
            project={
                "name": project_name,
                "root": str(tmp_path),
                "progress_log": str(tmp_path / "PROGRESS_LOG.md"),
            },
            recent_projects=[project_name],
            state_snapshot={},
            reminders=[],
        )

    class _RegistryStub:
        def get_planning_advisories(self, requested_name: str):
            if requested_name == project_name:
                return expected
            return {}

        def get_project(self, requested_name: str):  # noqa: ARG002
            return None

    fake_backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project_name)),
        count_entries=AsyncMock(return_value=0),
    )
    fake_server = Mock()
    fake_server.state_manager = SimpleNamespace(record_tool=AsyncMock(return_value={"tool": "get_project"}))
    fake_server.storage_backend = fake_backend
    fake_server.get_execution_context.return_value = None
    fake_server.get_agent_identity.return_value = None

    monkeypatch.setattr(get_project_module, "server_module", fake_server)
    monkeypatch.setattr(get_project_module._GET_PROJECT_HELPER, "server_module", fake_server)
    monkeypatch.setattr(get_project_module._GET_PROJECT_HELPER, "prepare_context", _prepare_context)
    monkeypatch.setattr(get_project_module, "_PROJECT_REGISTRY", _RegistryStub())

    result = await get_project_module.get_project(agent="test_agent", format="structured")

    assert result.get("ok") is True
    assert result.get("project", {}).get("meta", {}).get("planning_advisories") == expected
