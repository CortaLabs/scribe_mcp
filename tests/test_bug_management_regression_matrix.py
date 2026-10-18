from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.repo_authority import RepoAuthoritySnapshot
from scribe_mcp.shared.tool_runtime import validate_repo_root_grant
from scribe_mcp.tools.authorize_repo_root import authorize_repo_root
from scribe_mcp.tools.list_open_cases import list_open_cases
from scribe_mcp.tools import sentinel_tools
from scribe_mcp.tools import set_project as set_project_tool


class _MatrixStorage:
    def __init__(self) -> None:
        self._grants: dict[str, SimpleNamespace] = {}
        self._cases: dict[str, SimpleNamespace] = {}

    async def create_repo_scope_grant(
        self,
        *,
        authoritative_session_key: str,
        repo_root: str,
        reason: str,
        ttl_minutes: int = 30,
    ) -> SimpleNamespace:
        grant_id = f"grant-{len(self._grants) + 1}"
        resolved_root = str(Path(repo_root).resolve())
        grant = SimpleNamespace(
            grant_id=grant_id,
            authoritative_session_key=authoritative_session_key,
            repo_root=resolved_root,
            repo_id=f"repo-{abs(hash(resolved_root)) % 100000}",
            reason=reason,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=max(1, ttl_minutes)),
        )
        self._grants[grant_id] = grant
        return grant

    async def fetch_repo_scope_grant(self, grant_id: str) -> SimpleNamespace | None:
        return self._grants.get(grant_id)

    async def upsert_case_registry_record(self, **kwargs: Any) -> Any:
        repo_root = str(kwargs.get("repo_root", "") or "")
        record = SimpleNamespace(
            repo_id=kwargs.get("repo_id") or f"repo-{abs(hash(repo_root)) % 100000}",
            project_key=kwargs.get("project_key") or f"pk::{kwargs.get('project_name','')}::{repo_root}",
            created_at=kwargs.get("created_at") or datetime.now(timezone.utc),
            updated_at=kwargs.get("updated_at") or datetime.now(timezone.utc),
            **kwargs,
        )
        self._cases[str(record.case_id)] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any) -> Any:
        return self._cases.get(case_id)

    async def query_case_registry_records(
        self,
        *,
        repo_root: str | None = None,
        project_name: str | None = None,
        case_type: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[Any]:
        records = list(self._cases.values())
        if repo_root:
            want_root = str(Path(repo_root).resolve())
            records = [r for r in records if str(Path(r.repo_root).resolve()) == want_root]
        if project_name:
            records = [r for r in records if str(r.project_name) == str(project_name)]
        if case_type:
            records = [r for r in records if str(r.case_type) == str(case_type)]
        records.sort(key=lambda r: getattr(r, "updated_at", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return records[offset : offset + limit]


def _context(*, session_key: str, repo_root: Path, project_name: str) -> Any:
    resolved_root = str(repo_root.resolve())
    return SimpleNamespace(
        mode="project",
        repo_root=resolved_root,
        execution_id=f"exec-{session_key}",
        parent_execution_id=None,
        stable_session_id=session_key,
        authoritative_session_key=session_key,
        resolved_scope=SimpleNamespace(
            authoritative_session_key=session_key,
            stable_session_id=session_key,
            repo_root=resolved_root,
            project_name=project_name,
            trust_level="verified",
            resolution_source="runtime_context",
            provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
        ),
    )


def test_bug_management_regression_matrix_two_sessions_two_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _run() -> None:
        repo_a = (tmp_path / "external-repo-a").resolve()
        repo_b = (tmp_path / "external-repo-b").resolve()
        repo_a.mkdir()
        repo_b.mkdir()
        (repo_a / ".git").mkdir()
        (repo_b / ".git").mkdir()

        # This path intentionally has no .git marker; skip_validation must not bypass grant flow.
        non_repo_external = (tmp_path / "external-no-git").resolve()
        non_repo_external.mkdir()

        project_name = "shared-project-name"
        session_1 = "stable-session-1"
        session_2 = "stable-session-2"

        storage = _MatrixStorage()
        monkeypatch.setattr(server_module, "storage_backend", storage)

        active_context = _context(session_key=session_1, repo_root=repo_a, project_name=project_name)
        monkeypatch.setattr(server_module, "get_execution_context", lambda: active_context)

        grant_1 = await authorize_repo_root(root=str(repo_a), reason="matrix-session-1")
        assert grant_1["ok"] is True

        active_context = _context(session_key=session_2, repo_root=repo_b, project_name=project_name)
        grant_2 = await authorize_repo_root(root=str(repo_b), reason="matrix-session-2")
        assert grant_2["ok"] is True

        valid_a, details_a = await validate_repo_root_grant(
            storage_backend=storage,
            grant_id=grant_1["grant_id"],
            repo_root=str(repo_a),
            authoritative_session_key=session_1,
        )
        assert valid_a is True
        assert details_a["grant_id"] == grant_1["grant_id"]

        wrong_session_valid, wrong_session_details = await validate_repo_root_grant(
            storage_backend=storage,
            grant_id=grant_1["grant_id"],
            repo_root=str(repo_a),
            authoritative_session_key=session_2,
        )
        assert wrong_session_valid is False
        assert wrong_session_details["reason_code"] == "grant_session_mismatch"

        with pytest.raises(set_project_tool.ProjectRootAuthorizationError) as skip_validation_exc:
            await set_project_tool._resolve_root(
                root=str(non_repo_external),
                authority_snapshot=RepoAuthoritySnapshot(
                    verified_binding_root=str(repo_a),
                    verified_request_root=None,
                    enrolled_first_party_roots=tuple(),
                    authoritative_session_key=session_1,
                ),
                skip_validation=True,
                grant_id=None,
                storage_backend=storage,
                scribe_user=None,
            )
        assert skip_validation_exc.value.payload.get("reason_code") == "explicit_root_not_local_repo"

        append_result_a = {
            "ok": True,
            "id": "entry-a",
            "path": str(repo_a / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md"),
            "paths": [str(repo_a / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md")],
            "project_name": project_name,
        }
        append_result_b = {
            "ok": True,
            "id": "entry-b",
            "path": str(repo_b / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md"),
            "paths": [str(repo_b / ".scribe" / "docs" / "dev_plans" / project_name / "PROGRESS_LOG.md")],
            "project_name": project_name,
        }

        async def _append_entry_side_effect(**kwargs: Any) -> dict[str, Any]:
            del kwargs
            context = server_module.get_execution_context()
            if context.authoritative_session_key == session_1:
                return append_result_a
            return append_result_b

        async def _manage_docs_side_effect(**kwargs: Any) -> dict[str, Any]:
            metadata = kwargs.get("metadata", {})
            case_id = metadata.get("case_id", "UNKNOWN")
            context = server_module.get_execution_context()
            return {
                "ok": True,
                "path": str(Path(context.repo_root) / "docs" / "bugs" / "runtime" / str(case_id) / "report.md"),
            }

        with (
            patch("scribe_mcp.tools.append_entry.append_entry", AsyncMock(side_effect=_append_entry_side_effect)),
            patch("scribe_mcp.tools.manage_docs.manage_docs", AsyncMock(side_effect=_manage_docs_side_effect)),
            patch(
                "scribe_mcp.tools.sentinel_tools._next_case_id_for_project",
                side_effect=["BUG-2026-04-17-0001", "BUG-2026-04-17-0002"],
            ),
        ):
            active_context = _context(session_key=session_1, repo_root=repo_a, project_name=project_name)
            bug_a = await sentinel_tools.open_bug(
                agent="test-agent",
                title="bug-a",
                symptoms="symptoms-a",
                category="runtime",
            )
            assert bug_a["ok"] is True

            active_context = _context(session_key=session_2, repo_root=repo_b, project_name=project_name)
            bug_b = await sentinel_tools.open_bug(
                agent="test-agent",
                title="bug-b",
                symptoms="symptoms-b",
                category="runtime",
            )
            assert bug_b["ok"] is True

            # Ownership enforcement: session 2 cannot link fix to session 1 case.
            denied_link = await sentinel_tools.link_fix(
                agent="test-agent",
                case_id=bug_a["case_id"],
                execution_id=f"exec-{session_2}",
                artifact_ref="src/module.py:10",
                landing_status="merged",
            )
            assert denied_link["ok"] is False
            assert "repo ownership mismatch" in denied_link["error"]

            # list_open_cases remains repo-scoped even when project names are repeated.
            # Verify open-case scoping BEFORE the merged fix below closes bug_a: a
            # link_fix with landing_status="merged" auto-closes the case by design
            # (case-registry follow-up), so an open-case listing must precede it.
            active_context = _context(session_key=session_1, repo_root=repo_a, project_name=project_name)
            list_a = await list_open_cases(case_type="bug", limit=10)
            assert list_a["ok"] is True
            assert {item["case_id"] for item in list_a["cases"]} == {bug_a["case_id"]}

            active_context = _context(session_key=session_2, repo_root=repo_b, project_name=project_name)
            list_b = await list_open_cases(case_type="bug", limit=10)
            assert list_b["ok"] is True
            assert {item["case_id"] for item in list_b["cases"]} == {bug_b["case_id"]}

            active_context = _context(session_key=session_1, repo_root=repo_a, project_name=project_name)
            allowed_link = await sentinel_tools.link_fix(
                agent="test-agent",
                case_id=bug_a["case_id"],
                execution_id=f"exec-{session_1}",
                artifact_ref="src/module.py:11",
                landing_status="merged",
            )
            assert allowed_link["ok"] is True

            # The merged fix above closed bug_a; it must no longer appear as open.
            active_context = _context(session_key=session_1, repo_root=repo_a, project_name=project_name)
            list_a_after = await list_open_cases(case_type="bug", limit=10)
            assert list_a_after["ok"] is True
            assert bug_a["case_id"] not in {item["case_id"] for item in list_a_after["cases"]}

        # Repeated project names across repos must remain distinct in case registry ownership.
        case_a = await storage.fetch_case_registry_record(bug_a["case_id"])
        case_b = await storage.fetch_case_registry_record(bug_b["case_id"])
        assert case_a is not None and case_b is not None
        assert case_a.project_name == case_b.project_name == project_name
        assert str(Path(case_a.repo_root).resolve()) != str(Path(case_b.repo_root).resolve())

    asyncio.run(_run())
