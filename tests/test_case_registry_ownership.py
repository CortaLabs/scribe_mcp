from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from scribe_mcp.tools.sentinel_tools import link_fix, open_bug, open_security


class _RegistryBackend:
    def __init__(self, *, repo_root: str = "/tmp/repo") -> None:
        self.repo_root = repo_root
        self.upserts: list[dict[str, Any]] = []
        self.fetch_record: Any | None = None
        self.return_default_record = True

    async def upsert_case_registry_record(self, **kwargs: Any) -> Any:
        self.upserts.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any) -> Any:
        if self.fetch_record is not None:
            return self.fetch_record
        if not self.return_default_record:
            return None
        kind = "security" if case_id.startswith("SEC-") else "bug"
        return SimpleNamespace(
            case_id=case_id,
            case_type=kind,
            repo_root=self.repo_root,
            project_name="integrate_bug_management_system_20260417",
            doc_type=kind,
            doc_name=case_id,
            doc_path=f"{self.repo_root}/docs/{'security' if kind == 'security' else 'bugs'}/runtime/{case_id}/report.md",
            metadata={},
        )


@pytest.mark.asyncio
async def test_link_fix_project_mode_requires_registered_case_row() -> None:
    backend = _RegistryBackend(repo_root="/tmp/repo")
    backend.return_default_record = False

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx(repo_root="/tmp/repo")),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
    ):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-04-17-0999",
            execution_id="exec-live",
            artifact_ref="src/module.py:10",
            landing_status="merged",
        )

    assert result["ok"] is False
    assert result["mode"] == "project"
    assert "shared case registry" in result["error"]
    assert result["warnings"]


def _ctx(*, repo_root: str = "/tmp/repo") -> Any:
    return SimpleNamespace(
        mode="project",
        repo_root=repo_root,
        execution_id="exec-live",
        parent_execution_id=None,
        stable_session_id="session-1",
        authoritative_session_key="session-1",
        resolved_scope=SimpleNamespace(
            repo_root=repo_root,
            project_name="integrate_bug_management_system_20260417",
            trust_level="verified",
            resolution_source="runtime_context",
            provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
        ),
    )


@pytest.mark.asyncio
async def test_bug_and_security_register_with_shared_case_registry_model() -> None:
    backend = _RegistryBackend()
    append_result = {
        "ok": True,
        "id": "entry-1",
        "path": "/tmp/repo/.scribe/docs/dev_plans/integrate_bug_management_system_20260417/PROGRESS_LOG.md",
        "paths": ["/tmp/repo/.scribe/docs/dev_plans/integrate_bug_management_system_20260417/PROGRESS_LOG.md"],
        "project_name": "integrate_bug_management_system_20260417",
    }
    manage_result = {"ok": True, "path": "/tmp/repo/docs/bugs/runtime/x/report.md"}

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx()),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
        patch("scribe_mcp.tools.sentinel_tools._next_case_id_for_project", side_effect=["BUG-2026-04-17-0001", "SEC-2026-04-17-0001"]),
        patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock(return_value=append_result)),
        patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock(return_value=manage_result)),
    ):
        bug_result = await open_bug(
            agent="test-agent",
            title="Bug title",
            symptoms="bug symptoms",
            category="runtime",
        )
        sec_result = await open_security(
            agent="test-agent",
            title="Security title",
            symptoms="security symptoms",
            category="auth",
        )

    assert bug_result["ok"] is True
    assert sec_result["ok"] is True
    assert len(backend.upserts) == 2
    assert backend.upserts[0]["case_type"] == "bug"
    assert backend.upserts[1]["case_type"] == "security"
    assert backend.upserts[0]["doc_name"] == "BUG-2026-04-17-0001"
    assert backend.upserts[1]["doc_name"] == "SEC-2026-04-17-0001"
    assert bug_result["case_registry"]["doc_path"] == backend.upserts[0]["doc_path"]
    assert sec_result["case_registry"]["doc_path"] == backend.upserts[1]["doc_path"]
    assert backend.upserts[0]["project_name"] == "integrate_bug_management_system_20260417"
    assert backend.upserts[1]["project_name"] == "integrate_bug_management_system_20260417"
    assert backend.upserts[0]["metadata"]["ownership"]["repo_root_provenance"] == "verified"
    assert backend.upserts[1]["metadata"]["ownership"]["project_name_provenance"] == "verified"


@pytest.mark.asyncio
async def test_link_fix_denies_wrong_repo_ownership() -> None:
    backend = _RegistryBackend()
    backend.fetch_record = SimpleNamespace(
        case_id="BUG-2026-04-17-0002",
        repo_root="/tmp/other-repo",
        project_name="integrate_bug_management_system_20260417",
        doc_type="bug",
        doc_name="BUG-2026-04-17-0002",
    )

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx(repo_root="/tmp/repo")),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
    ):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-04-17-0002",
            execution_id="exec-live",
            artifact_ref="src/module.py:10",
            landing_status="merged",
        )

    assert result["ok"] is False
    assert "repo ownership mismatch" in result["error"]


@pytest.mark.asyncio
async def test_link_fix_denies_case_from_different_project_in_same_repo_scope() -> None:
    backend = _RegistryBackend(repo_root="/tmp/repo")
    backend.return_default_record = False

    async def _scoped_fetch(case_id: str, **kwargs: Any) -> Any:
        if kwargs.get("project_name") == "integrate_bug_management_system_20260417":
            return None
        return SimpleNamespace(
            case_id=case_id,
            case_type="bug",
            repo_root="/tmp/repo",
            project_name="other_project",
            doc_type="bug",
            doc_name=case_id,
            doc_path=f"/tmp/repo/docs/bugs/runtime/{case_id}/report.md",
            metadata={},
        )

    backend.fetch_case_registry_record = _scoped_fetch  # type: ignore[method-assign]

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx(repo_root="/tmp/repo")),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
    ):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-04-17-1111",
            execution_id="exec-live",
            artifact_ref="src/module.py:10",
            landing_status="merged",
        )

    assert result["ok"] is False
    assert "active repo/project scope" in result["error"]


@pytest.mark.asyncio
async def test_link_fix_succeeds_with_matching_repo_ownership() -> None:
    backend = _RegistryBackend(repo_root="/tmp/repo")

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx(repo_root="/tmp/repo")),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
        patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock(return_value={"ok": True, "id": "e1", "path": "/tmp/p", "project_name": "integrate_bug_management_system_20260417"})),
        patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock(return_value={"ok": True, "path": "/tmp/doc.md"})),
    ):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-04-17-0003",
            execution_id="exec-live",
            artifact_ref="src/module.py:10",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert result["warnings"] == []
    assert result["next_step"] == "No follow-up required."
    assert result["case_registry"]["project_name"] == "integrate_bug_management_system_20260417"


@pytest.mark.asyncio
async def test_link_fix_preserves_existing_case_metadata_when_merging_fix_details() -> None:
    backend = _RegistryBackend(repo_root="/tmp/repo")
    backend.fetch_record = SimpleNamespace(
        case_id="BUG-2026-04-17-0004",
        case_type="bug",
        repo_root="/tmp/repo",
        project_name="integrate_bug_management_system_20260417",
        doc_type="bug",
        doc_name="BUG-2026-04-17-0004",
        doc_path="/tmp/repo/docs/bugs/runtime/BUG-2026-04-17-0004/report.md",
        metadata={
            "category": "runtime",
            "query_key": "db-pool",
        },
    )

    with (
        patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=_ctx(repo_root="/tmp/repo")),
        patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend),
        patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock(return_value={"ok": True, "id": "e1", "path": "/tmp/p", "project_name": "integrate_bug_management_system_20260417"})),
        patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock(return_value={"ok": True, "path": "/tmp/doc.md"})),
    ):
        result = await link_fix(
            agent="test-agent",
            case_id="BUG-2026-04-17-0004",
            execution_id="exec-live",
            artifact_ref="src/module.py:10",
            landing_status="merged",
        )

    assert result["ok"] is True
    assert backend.upserts, "link_fix should upsert the shared case registry row on success"
    metadata = backend.upserts[-1]["metadata"]
    assert metadata["category"] == "runtime"
    assert metadata["query_key"] == "db-pool"
    assert metadata["fix_link"]["execution_id"] == "exec-live"
    assert metadata["fix_link"]["artifact_ref"] == "src/module.py:10"
    assert metadata["fix_link"]["landing_status"] == "merged"
    assert metadata["fix_link"]["execution_ref"]["value"] == "exec-live"
    assert metadata["fix_link"]["artifact_ref_meta"]["kind"] == "artifact"
    assert metadata["execution_provenance"]["execution_id"] == "exec-live"
    assert metadata["execution_provenance"]["stable_session_id"] == "session-1"
