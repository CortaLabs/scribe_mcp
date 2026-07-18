"""Regression: link_fix must record fix metadata ADDITIVELY, never clobber a report.

Background
----------
``link_fix`` updates a bug/security report's ``appendix`` and ``resolution_plan``
sections. The historical defect: it called ``manage_docs(action="replace_section")``
with a short generated block, and ``replace_section`` overwrites the *entire*
section body — silently destroying every authored subsection (Immediate Actions
prose + SQL, Long-Term Fixes, Testing Strategy, Logs & Evidence, Open Questions).
Six real reports were gutted before this was fixed.

The fix makes the two report writes opt into an additive ``preserve_authored``
mode on ``_replace_section``: authored content is kept and the fix block is
appended; only a genuinely-empty (structure-only) section is filled.

These tests exercise the REAL section-mutation path (``_replace_section``) — the
previous ``link_fix`` unit tests mocked ``manage_docs`` entirely, which is
exactly why the clobber was invisible for two days.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from scribe_mcp.doc_management.manager import _replace_section
from scribe_mcp.tools.sentinel_tools import link_fix


# ---------------------------------------------------------------------------
# A realistic bug report with rich AUTHORED content in the two sections
# link_fix writes to (resolution_plan + appendix), laid out exactly like the
# BUG_REPORT_TEMPLATE (heading above anchor, trailing --- separators).
# ---------------------------------------------------------------------------

_AUTHORED_SQL = "UPDATE public.data_migrations SET dry_run = FALSE WHERE id = 42;"
_AUTHORED_IMMEDIATE = "Notify the operator before re-running `data apply`."
_AUTHORED_LONGTERM = "Add an ON CONFLICT upgrade path so a stuck dry-run row is promoted."
_AUTHORED_TESTING = "Born-red regression test proving a stuck dry-run row is upgraded."
_AUTHORED_LOGS = "See ledger snapshot at logs/ledger-2026-07-18.txt"
_AUTHORED_OPENQ = "Does the reversed_at reset interact with idempotency?"

_ALL_AUTHORED = (
    _AUTHORED_SQL,
    _AUTHORED_IMMEDIATE,
    _AUTHORED_LONGTERM,
    _AUTHORED_TESTING,
    _AUTHORED_LOGS,
    _AUTHORED_OPENQ,
    "### Long-Term Fixes",
    "### Testing Strategy",
)


def _authored_report() -> str:
    return (
        "# 🐞 Bug Report\n\n"
        "## Bug Overview\n"
        "<!-- ID: bug_overview -->\n"
        "**Bug ID:** BUG-2026-03-15-0001\n\n"
        "**Status:** INVESTIGATING\n\n"
        "---\n"
        "## Resolution Plan\n"
        "<!-- ID: resolution_plan -->\n"
        "### Immediate Actions\n"
        f"- Roll back the poisoned rows:\n"
        "  ```sql\n"
        f"  {_AUTHORED_SQL}\n"
        "  ```\n"
        f"- {_AUTHORED_IMMEDIATE}\n\n"
        "### Long-Term Fixes\n"
        f"- {_AUTHORED_LONGTERM}\n\n"
        "### Testing Strategy\n"
        f"- {_AUTHORED_TESTING}\n\n"
        "---\n"
        "## Timeline & Ownership\n"
        "<!-- ID: timeline -->\n"
        "| Phase | Owner |\n"
        "| --- | --- |\n\n"
        "---\n"
        "## Appendix\n"
        "<!-- ID: appendix -->\n"
        f"- **Logs & Evidence:** {_AUTHORED_LOGS}\n"
        "- **Fix References:** [Git commits, PRs, or documentation]\n"
        f"- **Open Questions:** {_AUTHORED_OPENQ}\n\n"
        "---\n"
    )


# ---------------------------------------------------------------------------
# Hermetic manager-level proof: the exact section-mutation contract
# ---------------------------------------------------------------------------

_FIX_BLOCK = (
    "### Fix Landed\n"
    "Fix landed with status: **merged**\n\n"
    "### Fix Details\n"
    "- Artifact: src/agentkit/storage/data_migration_runner.py:120\n"
)


def test_destructive_replace_section_clobbers_authored_content() -> None:
    """Characterization of the defect: a plain replace_section wipes the section body."""
    doc = _authored_report()

    clobbered = _replace_section(doc, "resolution_plan", _FIX_BLOCK)

    # The generated block is present, but every authored line is GONE — this is
    # precisely the destructive behavior link_fix used to trigger.
    assert "Fix landed with status: **merged**" in clobbered
    assert _AUTHORED_SQL not in clobbered
    assert _AUTHORED_LONGTERM not in clobbered
    assert _AUTHORED_TESTING not in clobbered
    assert "### Long-Term Fixes" not in clobbered


def test_preserve_authored_keeps_resolution_plan_and_appends_fix() -> None:
    """preserve_authored=True keeps every authored byte AND records the fix block."""
    doc = _authored_report()

    updated = _replace_section(
        doc, "resolution_plan", _FIX_BLOCK, preserve_authored=True
    )

    # Authored content survives in full.
    assert _AUTHORED_SQL in updated
    assert _AUTHORED_IMMEDIATE in updated
    assert _AUTHORED_LONGTERM in updated
    assert _AUTHORED_TESTING in updated
    assert "### Long-Term Fixes" in updated
    assert "### Testing Strategy" in updated
    # Fix metadata is appended, not substituted.
    assert "Fix landed with status: **merged**" in updated
    assert "src/agentkit/storage/data_migration_runner.py:120" in updated
    # Adjacent sections and their anchors remain intact and unduplicated.
    assert updated.count("<!-- ID: resolution_plan -->") == 1
    assert "## Timeline & Ownership" in updated
    assert updated.count("<!-- ID: timeline -->") == 1


def test_preserve_authored_fills_a_genuinely_empty_section() -> None:
    """Complementary: an empty (structure-only) section MAY be filled, not skipped."""
    doc = (
        "## Resolution Plan\n"
        "<!-- ID: resolution_plan -->\n\n"
        "---\n"
        "## Appendix\n"
        "<!-- ID: appendix -->\n"
        "- authored appendix note\n"
    )

    updated = _replace_section(
        doc, "resolution_plan", _FIX_BLOCK, preserve_authored=True
    )

    assert "Fix landed with status: **merged**" in updated
    # No spurious blank-line duplication of the fix content.
    assert updated.count("Fix landed with status: **merged**") == 1
    # The genuinely-authored neighbor is untouched.
    assert "- authored appendix note" in updated


def test_preserve_authored_is_idempotent_for_identical_relink() -> None:
    """Re-linking the identical fix block must not duplicate it."""
    doc = _authored_report()

    once = _replace_section(
        doc, "resolution_plan", _FIX_BLOCK, preserve_authored=True
    )
    twice = _replace_section(
        once, "resolution_plan", _FIX_BLOCK, preserve_authored=True
    )

    assert twice.count("Fix landed with status: **merged**") == 1
    assert _AUTHORED_SQL in twice


# ---------------------------------------------------------------------------
# End-to-end proof through the REAL link_fix path
# ---------------------------------------------------------------------------


def _make_execution_context() -> Any:
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.mode = "project"
    ctx.repo_root = "/tmp"
    ctx.execution_id = "exec-live-123"
    ctx.parent_execution_id = None
    ctx.stable_session_id = "session-1"
    ctx.authoritative_session_key = "session-1"
    ctx.resolved_scope = SimpleNamespace(
        repo_root="/tmp",
        project_name="test-project",
        trust_level="verified",
        resolution_source="runtime_context",
        provenance=SimpleNamespace(repo_root="verified", project_name="verified"),
    )
    return ctx


class _RegistryBackend:
    def __init__(self) -> None:
        self.records: Dict[str, SimpleNamespace] = {}

    def compute_repo_id(self, repo_root: str) -> str:
        import hashlib

        return hashlib.sha256(repo_root.encode("utf-8")).hexdigest()

    def seed_case(self, *, case_id: str, doc_name: str) -> None:
        self.records[case_id] = SimpleNamespace(
            case_id=case_id,
            case_type="bug",
            repo_root="/tmp",
            project_name="test-project",
            project_key="repo-key:test-project",
            doc_type="bug",
            doc_name=doc_name,
            doc_path=f"/tmp/docs/bugs/runtime/{case_id}/report.md",
            status="open",
            metadata={},
        )

    async def upsert_case_registry_record(self, **kwargs: Any):
        record = SimpleNamespace(**kwargs)
        self.records[str(kwargs["case_id"])] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any):
        return self.records.get(case_id)

    async def fetch_entry_by_id(self, *_args: Any, **_kwargs: Any):
        return None


def _real_section_write_manage_docs(report_path: Path):
    """A side-effecting manage_docs stand-in that runs the REAL _replace_section.

    Only project resolution / registration is stubbed; the actual section
    mutation — including honoring ``metadata['preserve_authored']`` — is the real
    production code path. So this faithfully reproduces the clobber on unfixed
    link_fix (which omits the flag) and the preservation once it is fixed.
    """

    async def _fake(**kwargs: Any) -> Dict[str, Any]:
        action = kwargs.get("action")
        if action == "replace_section":
            text = report_path.read_text(encoding="utf-8")
            metadata = kwargs.get("metadata") or {}
            updated = _replace_section(
                text,
                kwargs.get("section"),
                kwargs.get("content") or "",
                preserve_authored=bool(metadata.get("preserve_authored")),
            )
            report_path.write_text(updated, encoding="utf-8")
        # quality_check (completeness gate) and any other action: benign, so the
        # gate falls open and the report-update path is reached.
        return {"ok": True, "path": str(report_path)}

    return _fake


@pytest.mark.asyncio
async def test_link_fix_preserves_authored_report_end_to_end(tmp_path: Path) -> None:
    """Driving REAL link_fix must leave every authored byte intact and add the fix."""
    from unittest.mock import AsyncMock, patch

    report_path = tmp_path / "report.md"
    report_path.write_text(_authored_report(), encoding="utf-8")

    ctx = _make_execution_context()
    backend = _RegistryBackend()
    backend.seed_case(case_id="BUG-2026-03-15-0001", doc_name="BUG-2026-03-15-0001")

    mock_append = AsyncMock(
        return_value={
            "ok": True,
            "id": "entry-1",
            "path": "/tmp/test-project/PROGRESS_LOG.md",
            "paths": ["/tmp/test-project/PROGRESS_LOG.md"],
            "project_name": "test-project",
        }
    )
    fake_manage = _real_section_write_manage_docs(report_path)

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), patch(
        "scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend
    ), patch("scribe_mcp.tools.append_entry.append_entry", mock_append), patch(
        "scribe_mcp.tools.manage_docs.manage_docs", fake_manage
    ):
        result = await link_fix(
            agent="mantis-test",
            case_id="BUG-2026-03-15-0001",
            execution_id="exec-live-123",
            artifact_ref="src/agentkit/storage/data_migration_runner.py:120",
            landing_status="merged",
        )

    assert result["ok"] is True

    final = report_path.read_text(encoding="utf-8")

    # HARD CONTRACT: every authored byte survives.
    for authored in _ALL_AUTHORED:
        assert authored in final, f"link_fix clobbered authored content: {authored!r}"

    # Fix metadata was recorded additively.
    assert "src/agentkit/storage/data_migration_runner.py:120" in final
    assert "merged" in final
    assert "mantis-test" in final

    # No section anchors were duplicated or lost.
    assert final.count("<!-- ID: resolution_plan -->") == 1
    assert final.count("<!-- ID: appendix -->") == 1
    assert final.count("<!-- ID: timeline -->") == 1
