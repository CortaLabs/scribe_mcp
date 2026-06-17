"""P1.7 (WS1 F4 + F8) regression tests.

F4 — ``open_bug``/``open_security`` are a single ``_open_case`` body; security
     completeness is scored against ``_SECURITY_TEMPLATE_FIELDS`` (a per-case-type
     binding), NOT the bug field set.

F8 — case-ID dedup is an EXACT report-directory-name match. It performs ZERO
     report-body reads, so its per-allocation cost is independent of report file
     size (proven by an op-count assertion, not a wall-clock measurement), and it
     no longer false-positives when a case ID is quoted inside another report.

These tests are bounded-op: the F8 proofs assert scan/read counts that are
independent of input size N, and the F4 proofs assert envelope/scoring contracts
without touching real infrastructure.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import scribe_mcp.tools.sentinel_tools as st
from scribe_mcp.tools.sentinel_tools import (
    _BUG_TEMPLATE_FIELDS,
    _SECURITY_TEMPLATE_FIELDS,
    _case_id_directory_exists,
    _next_case_id_for_project,
    open_bug,
    open_security,
)


# ---------------------------------------------------------------------------
# Shared harness (mirrors tests/test_sentinel_tools.py contract)
# ---------------------------------------------------------------------------
def _make_execution_context(mode: str = "project") -> MagicMock:
    ctx = MagicMock()
    ctx.mode = mode
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


def _make_append_entry_result(ok: bool = True, **extra: Any) -> Dict[str, Any]:
    base = {
        "ok": ok,
        "id": "test-entry-id",
        "path": "/tmp/test-project/PROGRESS_LOG.md",
        "paths": ["/tmp/test-project/PROGRESS_LOG.md"],
        "project_name": "test-project",
    }
    base.update(extra)
    return base


def _make_manage_docs_result(ok: bool = True, **extra: Any) -> Dict[str, Any]:
    base = {
        "ok": ok,
        "path": "/tmp/test-project/docs/bugs/runtime/2026-03-15_BUG-2026-03-15-0001/report.md",
        "document_type": "bug_report",
        "doc_name": "BUG-2026-03-15-0001",
        "file_size": 1234,
    }
    base.update(extra)
    return base


class _RegistryBackend:
    def __init__(self) -> None:
        self.records: Dict[str, SimpleNamespace] = {}

    def compute_repo_id(self, repo_root: str) -> str:
        import hashlib

        return hashlib.sha256(repo_root.encode("utf-8")).hexdigest()

    async def upsert_case_registry_record(self, **kwargs: Any):
        record = SimpleNamespace(**kwargs)
        self.records[str(kwargs["case_id"])] = record
        return record

    async def fetch_case_registry_record(self, case_id: str, **_kwargs: Any):
        return self.records.get(case_id)


@pytest.fixture(autouse=True)
def _patch_registry_backend() -> _RegistryBackend:
    backend = _RegistryBackend()
    with patch("scribe_mcp.tools.sentinel_tools.server_module.storage_backend", backend):
        yield backend


async def _run_open(tool, case_id: str, **kwargs: Any) -> Dict[str, Any]:
    ctx = _make_execution_context("project")
    mock_append = AsyncMock(return_value=_make_append_entry_result())
    mock_manage = AsyncMock(
        return_value=_make_manage_docs_result(
            path=f"/tmp/test-project/docs/x/{case_id}/report.md"
        )
    )

    with patch("scribe_mcp.tools.sentinel_tools._get_context", return_value=ctx), patch(
        "scribe_mcp.tools.sentinel_tools._next_case_id_for_project", return_value=case_id
    ), patch("scribe_mcp.tools.append_entry.append_entry", mock_append), patch(
        "scribe_mcp.tools.manage_docs.manage_docs", mock_manage
    ):
        return await tool(**kwargs), mock_manage


# ---------------------------------------------------------------------------
# F4 — parity + per-case-type completeness scoring
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_open_bug_and_open_security_share_envelope_shape() -> None:
    """Both tools produce the same envelope contract (parity), differing only in
    the case-type literals — proving the extracted ``_open_case`` body is shared
    and behaviour-preserving."""
    bug_result, _ = await _run_open(
        open_bug,
        "BUG-2026-03-15-0001",
        agent="test-agent",
        title="t",
        symptoms="s",
        category="runtime",
    )
    sec_result, _ = await _run_open(
        open_security,
        "SEC-2026-03-15-0001",
        agent="test-agent",
        title="t",
        symptoms="s",
        category="runtime",
    )

    # Identical envelope key set except the kind-specific report alias key.
    common = set(bug_result) - {"bug_report"}
    common_sec = set(sec_result) - {"security_report"}
    assert common == common_sec

    # Kind-specific literals
    assert bug_result["doc_category"] == "bugs"
    assert sec_result["doc_category"] == "security"
    assert bug_result["case_registry"]["case_type"] == "bug"
    assert sec_result["case_registry"]["case_type"] == "security"
    assert bug_result["doc_path"] == bug_result["bug_report"]
    assert sec_result["doc_path"] == sec_result["security_report"]
    # Default severity differs (bug=medium, security=high)
    assert "Bug report" in bug_result["action_required"]
    assert "Security report" in sec_result["action_required"]


@pytest.mark.asyncio
async def test_security_completeness_scores_against_security_field_set() -> None:
    """F4 core: ``open_security`` must score completeness against
    ``_SECURITY_TEMPLATE_FIELDS`` — NOT the bug set. We patch the security field
    set to a strict subset and assert the security denominator follows it while
    the bug denominator stays on the bug set. This proves the scoring source is
    per-case-type, so a future security-only field is scored correctly."""
    # A deliberately smaller security field set (subset of the real one).
    shrunk_security_fields = ["symptoms", "severity"]

    with patch.object(st, "_SECURITY_TEMPLATE_FIELDS", shrunk_security_fields):
        sec_result, _ = await _run_open(
            open_security,
            "SEC-2026-03-15-0002",
            agent="test-agent",
            title="t",
            symptoms="s",
            category="runtime",
        )
    # Security denominator follows the (patched) SECURITY set, not the bug set.
    assert sec_result["completeness"]["score"].endswith(f"/{len(shrunk_security_fields)}")
    assert len(shrunk_security_fields) != len(_BUG_TEMPLATE_FIELDS)

    # Bug scoring is unaffected — still scores against the bug set denominator.
    bug_result, _ = await _run_open(
        open_bug,
        "BUG-2026-03-15-0002",
        agent="test-agent",
        title="t",
        symptoms="s",
        category="runtime",
    )
    assert bug_result["completeness"]["score"].endswith(f"/{len(_BUG_TEMPLATE_FIELDS)}")


def test_security_template_fields_is_distinct_binding() -> None:
    """The security field set is its own binding (currently equal in value to the
    bug set, but a separate object) so it can diverge without editing the shared
    scoring loop."""
    assert _SECURITY_TEMPLATE_FIELDS == _BUG_TEMPLATE_FIELDS
    assert _SECURITY_TEMPLATE_FIELDS is not _BUG_TEMPLATE_FIELDS


# ---------------------------------------------------------------------------
# F8 — bounded-op dedup (exact dir-name match, zero body reads)
# ---------------------------------------------------------------------------
def _seed_reports(repo_root: Path, section: str, dir_names: list[str], body: str) -> None:
    """Create ``docs/<section>/<category>/<dir_name>/report.md`` for each name."""
    for name in dir_names:
        d = repo_root / "docs" / section / "runtime" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.md").write_text(body, encoding="utf-8")


class _CountingPath(type(Path())):  # type: ignore[misc]
    """Path subclass that counts read_text calls across all instances."""

    read_text_calls = 0

    def read_text(self, *args: Any, **kwargs: Any) -> str:  # noqa: D401
        type(self).read_text_calls += 1
        return super().read_text(*args, **kwargs)


def test_dedup_performs_zero_report_body_reads(tmp_path: Path) -> None:
    """F8 proof (bounded-op): dedup compares directory NAMES, never report bodies.
    We instrument ``read_text`` and assert it is called ZERO times regardless of
    how large each report body is — the per-allocation cost is independent of
    report file size."""
    repo_root = tmp_path
    # Large bodies: if the old body-scan were still here, each would be read.
    big_body = "x" * 200_000
    _seed_reports(repo_root, "bugs", [f"2026-03-15_BUG-2026-03-15-{i:04d}" for i in range(1, 6)], big_body)
    _seed_reports(repo_root, "security", [f"2026-03-15_SEC-2026-03-15-{i:04d}" for i in range(1, 6)], big_body)

    _CountingPath.read_text_calls = 0
    counting_root = _CountingPath(str(repo_root))

    # Candidate that collides with an existing dir -> must detect via name match.
    assert _case_id_directory_exists(counting_root, "BUG-2026-03-15-0003", "_BUG-2026-03-15-0003") is True
    # Candidate that does NOT exist -> no collision.
    assert _case_id_directory_exists(counting_root, "BUG-2026-03-15-9999", "_BUG-2026-03-15-9999") is False

    assert _CountingPath.read_text_calls == 0, "dedup must not read any report body"


def test_dedup_scan_count_independent_of_file_size(tmp_path: Path) -> None:
    """Bounded-op: the number of filesystem traversals is a function of the report
    DIRECTORY count, not file size. Two corpora with identical directory counts
    but wildly different body sizes must produce the same scan cost (here: zero
    body reads in both)."""
    for body_size in (10, 500_000):
        repo_root = tmp_path / f"repo_{body_size}"
        body = "y" * body_size
        _seed_reports(repo_root, "bugs", [f"2026-03-15_BUG-2026-03-15-{i:04d}" for i in range(1, 11)], body)

        _CountingPath.read_text_calls = 0
        counting_root = _CountingPath(str(repo_root))
        _case_id_directory_exists(counting_root, "BUG-2026-03-15-0099", "_BUG-2026-03-15-0099")
        # Identical (zero) body-read cost across a 50,000x file-size difference.
        assert _CountingPath.read_text_calls == 0


def test_dedup_no_false_positive_on_quoted_id_in_other_report(tmp_path: Path) -> None:
    """F8 correctness: a case ID QUOTED inside a different report's body (e.g. a
    cross-reference) must NOT register as a duplicate. The old substring body scan
    false-positived here; exact dir-name matching does not."""
    repo_root = tmp_path
    # An existing report whose BODY mentions BUG-2026-03-15-0042 but whose
    # directory is a different case.
    _seed_reports(
        repo_root,
        "bugs",
        ["2026-03-15_BUG-2026-03-15-0001"],
        body="See related case BUG-2026-03-15-0042 for context.",
    )
    # 0042 is only quoted in another body, never owns a directory -> not a dup.
    assert _case_id_directory_exists(repo_root, "BUG-2026-03-15-0042", "_BUG-2026-03-15-0042") is False
    # 0001 owns a directory -> is a dup.
    assert _case_id_directory_exists(repo_root, "BUG-2026-03-15-0001", "_BUG-2026-03-15-0001") is True


def test_next_case_id_allocator_uses_dir_match_not_body_scan(tmp_path: Path) -> None:
    """End-to-end allocator: ``_next_case_id_for_project`` allocates the next free
    sequence using directory-name dedup. A report body that merely quotes the
    next candidate ID must NOT burn that sequence number (the old scan would)."""
    # Build a repo whose layout matches the allocator's resolution:
    # repo_root/.scribe/docs/dev_plans/<project>  is the project_dir.
    project = "demo-project"
    project_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / project
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "PROGRESS_LOG.md").write_text("log", encoding="utf-8")

    # Seed an existing BUG-...-0001 directory AND a body that quotes ...-0002.
    today_dir = tmp_path / "docs" / "bugs" / "runtime"
    today_dir.mkdir(parents=True, exist_ok=True)

    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (today_dir / f"{today}_BUG-{today}-0001").mkdir(parents=True, exist_ok=True)
    (today_dir / f"{today}_BUG-{today}-0001" / "report.md").write_text(
        f"cross-ref BUG-{today}-0002", encoding="utf-8"
    )

    # Pre-seed the counter so the next sequence is 0002.
    counter_dir = tmp_path / ".scribe"
    counter_dir.mkdir(parents=True, exist_ok=True)
    (counter_dir / ".sentinel_case_id_counters.json").write_text(
        json.dumps({today: {"BUG": 1}}), encoding="utf-8"
    )

    result = {
        "path": str(project_dir / "PROGRESS_LOG.md"),
        "paths": [str(project_dir / "PROGRESS_LOG.md")],
    }
    allocated = _next_case_id_for_project("BUG", result)
    # 0002 is only quoted in another body -> it is FREE and must be allocated.
    assert allocated == f"BUG-{today}-0002"
