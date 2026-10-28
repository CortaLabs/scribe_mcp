from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scribe_mcp.doc_management.utils import ScribeSourceDocument
from scribe_mcp.state import StateManager
from test_manage_docs_create_doc import _call_manage_docs, _isolated_server


pytestmark = pytest.mark.regression


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read_text", "stat"])
async def test_project_health_yields_during_real_discovery_io(tmp_path: Path, operation: str) -> None:
    import asyncio
    import threading
    from scribe_mcp.doc_management import runtime

    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "sample"
    research = docs_dir / "research"
    research.mkdir(parents=True)
    target = research / "RESEARCH_pending.md"
    target.write_text("# Real research\n", encoding="utf-8")
    project = {"name": "sample", "root": str(tmp_path), "docs_dir": str(docs_dir), "docs": {}}
    entered, release = threading.Event(), threading.Event()
    timed_out = []
    observed_threads = []
    loop_thread = threading.get_ident()
    real_io = getattr(Path, operation)
    real_quality = runtime.collect_managed_doc_quality_state
    quality_threads, helper_threads = [], []

    def observed_io(path, *args, **kwargs):
        value = real_io(path, *args, **kwargs)
        if path == target and not entered.is_set():
            observed_threads.append(threading.get_ident())
            entered.set()
            # A bounded stand-in for a slow filesystem response, after real IO.
            # Only an independent event-loop task can release it promptly.
            timed_out.append(not release.wait(1.0))
        return value

    def observed_quality(active_project):
        quality_threads.append(threading.get_ident())
        return real_quality(active_project)

    def apply_context(payload, context):
        helper_threads.append(threading.get_ident())
        return payload

    async def independent_task():
        while not entered.is_set():
            await asyncio.sleep(0.001)
        pending = not handler.done()
        release.set()
        return pending

    helper = SimpleNamespace(apply_context_payload=apply_context)
    with patch.object(Path, operation, observed_io), patch.object(runtime, "collect_managed_doc_quality_state", observed_quality):
        handler = asyncio.create_task(runtime._handle_project_health(
            active_project=project, metadata={"limit": 1}, helper=helper, context=None,
        ))
        ticker = asyncio.create_task(independent_task())
        try:
            result, progressed_while_pending = await asyncio.wait_for(asyncio.gather(handler, ticker), 5)
        finally:
            release.set()

    assert progressed_while_pending is True
    assert timed_out == [False]
    assert observed_threads and observed_threads[0] != loop_thread
    assert quality_threads == [loop_thread]
    assert helper_threads == [loop_thread]
    details = result["organization_digest"]["status_sections"]["artifact_claims"]["details"]
    assert details["unregistered_active_docs"] == [str(target)]
    assert [item["path"] for item in details["registration_drift"]] == [str(target)]


@pytest.mark.asyncio
async def test_project_health_concurrent_requests_keep_full_results_isolated(tmp_path: Path) -> None:
    import asyncio
    from scribe_mcp.doc_management.runtime import _handle_project_health

    projects = []
    for slug in ("alpha", "beta"):
        root = tmp_path / slug
        docs_dir = root / ".scribe" / "docs" / "dev_plans" / slug
        research = docs_dir / "research"
        research.mkdir(parents=True)
        (research / f"RESEARCH_{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")
        projects.append({"name": slug, "root": str(root), "docs_dir": str(docs_dir), "docs": {}})
    loop = asyncio.get_running_loop()

    def apply_context(payload, context):
        assert asyncio.get_running_loop() is loop
        return {**payload, "context_marker": context}

    helper = SimpleNamespace(apply_context_payload=apply_context)

    async def run(project):
        return await _handle_project_health(
            active_project=project, metadata={"limit": 1}, helper=helper, context=project["name"],
        )

    expected = [await run(project) for project in projects]
    results = await asyncio.gather(*(run(project) for project in projects))
    assert results == expected
    for result, project in zip(results, projects):
        assert result["active_project"] == result["context_marker"] == project["name"]
        details = result["organization_digest"]["status_sections"]["artifact_claims"]["details"]
        assert details["unregistered_active_docs"] == [str(Path(project["docs_dir"]) / "research" / f"RESEARCH_{project['name']}.md")]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["error", "cancel"])
async def test_project_health_inventory_error_and_cancellation_do_not_finish_response(tmp_path: Path, outcome: str) -> None:
    import asyncio
    import threading
    from scribe_mcp.doc_management import runtime

    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "sample"
    research = docs_dir / "research"
    research.mkdir(parents=True)
    target = research / "RESEARCH_pending.md"
    target.write_text("# Real research\n", encoding="utf-8")
    project = {"name": "sample", "root": str(tmp_path), "docs_dir": str(docs_dir), "docs": {}}
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    real_read = Path.read_text
    quality_calls, helper_calls = [], []
    real_quality = runtime.collect_managed_doc_quality_state

    def observed_read(path, *args, **kwargs):
        value = real_read(path, *args, **kwargs)
        if path == target:
            if outcome == "error":
                raise RuntimeError("controlled discovery error")
            entered.set()
            try:
                if not release.wait(2):
                    raise AssertionError("test did not release cancelled inventory")
            finally:
                finished.set()
        return value

    def observed_quality(active_project):
        quality_calls.append(active_project)
        return real_quality(active_project)

    def apply_context(payload, context):
        helper_calls.append(context)
        return payload

    helper = SimpleNamespace(apply_context_payload=apply_context)
    with patch.object(Path, "read_text", observed_read), patch.object(runtime, "collect_managed_doc_quality_state", observed_quality):
        handler = asyncio.create_task(runtime._handle_project_health(
            active_project=project, metadata=None, helper=helper, context=None,
        ))
        try:
            if outcome == "error":
                with pytest.raises(RuntimeError, match="controlled discovery error"):
                    await handler
            else:
                assert await asyncio.to_thread(entered.wait, 2)
                handler.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await handler
        finally:
            release.set()
            if outcome == "cancel":
                assert await asyncio.to_thread(finished.wait, 2)

    assert quality_calls == []
    assert helper_calls == []
    # A failed/cancelled request cannot poison a later inventory or response.
    result = await runtime._handle_project_health(active_project=project, metadata=None, helper=helper, context="later")
    assert result["ok"] is True
    assert helper_calls == ["later"]


@pytest.mark.asyncio
@pytest.mark.parametrize("index_state", ["indexed", "unindexed", "missing", "unreadable"])
async def test_project_health_bounds_index_reads_without_changing_full_output(
    tmp_path: Path, index_state: str,
) -> None:
    from scribe_mcp.doc_management.runtime import _handle_project_health

    # Exercise the actual handler and discovery against real files, without Git,
    # a server or shared state. Fix mtimes so the entire output is comparable.
    root = tmp_path / "repo"
    docs_dir = root / ".scribe" / "docs" / "dev_plans" / "sample"
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True)
    research_paths = []
    indexed_paths = []
    for number in range(1200):
        path = research_dir / f"RESEARCH_{number:04d}.md"
        path.write_text("# Research\n", encoding="utf-8")
        os.utime(path, (1700000000 + number, 1700000000 + number))
        research_paths.append(path)
        if number % 3 != 2:
            indexed_paths.append(path)
    index_path = research_dir / "INDEX.md"
    if index_state != "missing":
        index_text = "# Research index\n"
        if index_state == "indexed":
            index_text += "\n".join(
                path.name if number % 2 == 0 else path.relative_to(docs_dir).as_posix()
                for number, path in enumerate(indexed_paths)
            )
        index_path.write_text(index_text, encoding="utf-8")
        os.utime(index_path, (1700002000, 1700002000))
    project = {"name": "sample", "root": str(root), "docs_dir": str(docs_dir), "docs": {}}
    helper = SimpleNamespace(apply_context_payload=lambda payload, context: payload)
    real_read = Path.read_text
    index_reads = 0

    def observed_read(path: Path, *args, **kwargs):
        nonlocal index_reads
        if path == index_path:
            index_reads += 1
            if index_state == "unreadable":
                # Portable read failure injection; all other IO is delegated.
                raise PermissionError("controlled unreadable research index")
        return real_read(path, *args, **kwargs)

    with patch.object(Path, "read_text", observed_read):
        result = await _handle_project_health(
            active_project=project, metadata={"limit": 5}, helper=helper, context=None,
        )

    claims = result["organization_digest"]["status_sections"]["artifact_claims"]
    expected_paths = sorted(
        str(path) for path in research_paths
        if index_state != "indexed" or path not in indexed_paths
    )
    assert result["ok"] is True
    assert claims["details"]["unregistered_active_docs"] == expected_paths
    assert [item["path"] for item in claims["details"]["registration_drift"]] == expected_paths
    assert len(expected_paths) == (400 if index_state == "indexed" else 1200)
    # Baseline hashes cover every field and list order, including full findings
    # beyond metadata.limit. Only the disposable root path is normalized.
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    canonical = serialized.replace(str(root), "/fixture")
    expected_hashes = {
        "indexed": "3b3dd2d18cd0121f2f77acc8bcd24958f6c1652f845b6e05d2f133b772b89a27",
        "unindexed": "1706e3c2eb5417fcb8b01e887656531c7993cae06b9c3379e561ff36d0f3f745",
        "missing": "fe07eb4b542eb6104b86be59478703e95362b65bb6ca7ba0011d2b2fe359a151",
        "unreadable": "1706e3c2eb5417fcb8b01e887656531c7993cae06b9c3379e561ff36d0f3f745",
    }
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == expected_hashes[index_state]
    # Discovery also reads INDEX.md once; membership must add at most one read.
    assert index_reads <= (0 if index_state == "missing" else 2)

    # A later call must observe changed/new/recovered content, never a cached
    # prior success, absence or read failure from another request.
    index_path.write_text(f"# Research index\n{research_paths[0].name}\n", encoding="utf-8")
    refreshed = await _handle_project_health(
        active_project=project, metadata={"limit": 5}, helper=helper, context=None,
    )
    refreshed_details = refreshed["organization_digest"]["status_sections"]["artifact_claims"]["details"]
    assert refreshed_details["unregistered_active_docs"] == sorted(str(path) for path in research_paths[1:])
    assert [item["path"] for item in refreshed_details["registration_drift"]] == sorted(str(path) for path in research_paths[1:])


def _project_payload(project_root: Path, slug: str) -> dict:
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / slug
    docs_dir.mkdir(parents=True, exist_ok=True)
    custom_log_path = docs_dir / "DECISIONS.md"
    for filename, title in (("ARCHITECTURE_GUIDE.md", "Architecture"), ("CHECKLIST.md", "Checklist")):
        (docs_dir / filename).write_text(f"# {title}\n", encoding="utf-8")
    (docs_dir / "PHASE_PLAN.md").write_text("## Phase 1 (In Progress)\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text(
        "\n".join(
            [
                "[✅] [2026-05-01 01:00:00 UTC] [Agent: Forge] [Project: Alpha] Complete task | priority=high; category=milestone; tags=[\"ship\"]",
                "[ℹ️] [2026-05-01 02:00:00 UTC] [Agent: Forge] [Project: Alpha] Missing category and tags | priority=medium",
            ]
        ),
        encoding="utf-8",
    )
    custom_log_path.write_text("[2026-05-01] custom log entry\n", encoding="utf-8")
    config_dir = project_root / ".scribe" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "scribe.yaml").write_text(
        "repo_slug: test\n"
        "logs:\n"
        "  decisions:\n"
        "    path: \"{docs_dir}/DECISIONS.md\"\n"
        "    metadata_requirements: []\n",
        encoding="utf-8",
    )
    return {"name": slug.replace("_", " ").title(), "root": str(project_root), "docs_dir": str(docs_dir), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "docs": {"architecture": str(docs_dir / "ARCHITECTURE_GUIDE.md"), "phase_plan": str(docs_dir / "PHASE_PLAN.md"), "checklist": str(docs_dir / "CHECKLIST.md"), "progress_log": str(docs_dir / "PROGRESS_LOG.md"), "decisions": str(custom_log_path)}}


@pytest.mark.asyncio
async def test_project_health_includes_managed_doc_quality(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "quality_repo"
    active_project = _project_payload(project_root, "active_project")
    architecture_path = Path(active_project["docs"]["architecture"])
    architecture_path.write_text("---\nstatus: complete\n---\n[fill this section]\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    quality = result.get("managed_doc_quality") or {}
    assert quality.get("status") == "blocked"
    assert quality.get("readiness_blocker_count", 0) >= 1
    names = {doc.get("doc_name") for doc in quality.get("documents", [])}
    assert "progress_log" not in names
    assert "decisions" not in names
    readiness = result.get("readiness_summary") or {}
    assert isinstance(readiness.get("managed_doc_quality"), dict)
    assert readiness.get("managed_doc_quality") == quality
    assert readiness.get("current_phase")
    assert "Phase 1" in str(readiness.get("current_phase"))
    log_friction = readiness.get("log_friction") or {}
    signals = log_friction.get("signals") or []
    assert signals
    assert log_friction.get("status") == "advisory"
    assert {s.get("code") for s in signals} == {"LOG_MISSING_CATEGORY", "LOG_MISSING_TAGS"}
    assert readiness.get("warning_count", 0) == quality.get("total_warning_count", 0)
    assert readiness.get("blocker_count", 0) == quality.get("readiness_blocker_count", 0)
    organization_digest = result.get("organization_digest") or {}
    assert isinstance(organization_digest.get("quality_warning_digest"), list)
    truth_model = organization_digest.get("truth_model") or {}
    assert "direct_artifact" in truth_model
    assert "derived_signal" in truth_model
    derived = organization_digest.get("derived_signals") or []
    assert any(item.get("truth_label") == "derived_signal" for item in derived)
    status_sections = organization_digest.get("status_sections") or {}
    required_keys = {"organization", "index", "project_artifacts", "archive", "artifact_claims", "ownership"}
    assert required_keys.issubset(set(status_sections.keys()))
    for key in required_keys:
        section = status_sections.get(key) or {}
        assert isinstance(section.get("status"), str)
        assert isinstance(section.get("truth_label"), str)
        assert isinstance(section.get("summary"), str)
        assert isinstance(section.get("next_safe_action"), str)


@pytest.mark.asyncio
async def test_project_health_counts_research_hygiene_for_path_registered_docs(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "research_quality_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_doc = research_dir / "RESEARCH_FRONTMATTER.md"
    research_doc.write_text("# Research\nEvidence.\n", encoding="utf-8")
    active_project["docs"] = {
        "architecture": active_project["docs"]["architecture"],
        "research_frontmatter": str(research_doc),
    }

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    quality = result.get("managed_doc_quality") or {}
    research_entry = next(doc for doc in quality.get("documents", []) if doc.get("doc_name") == "research_frontmatter")
    assert "SCF_INDEX_MISSING" in research_entry.get("warning_codes", [])
    from scribe_mcp.doc_management.scaffold_quality import collect_managed_doc_quality_warnings

    direct_warnings = collect_managed_doc_quality_warnings(
        text=research_doc.read_text(encoding="utf-8"),
        doc_name="research_frontmatter",
        path=research_doc,
        project={"docs_dir": str(docs_dir)},
    )
    research_warning = next(w for w in direct_warnings if w.get("code") == "SCF_INDEX_MISSING")
    assert research_warning.get("source_owner") == "research"
    organization_digest = result.get("organization_digest") or {}
    warning_digest = organization_digest.get("quality_warning_digest") or []
    assert any(item.get("warning_code") == "SCF_INDEX_MISSING" for item in warning_digest)
    status_sections = organization_digest.get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    assert index_section.get("status") == "needs_attention"
    assert "research-index warning" in str(index_section.get("summary", "")).lower()


@pytest.mark.asyncio
async def test_project_health_marks_index_needs_attention_for_unindexed_doc_warning(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "index_unindexed_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    indexed_doc = research_dir / "RESEARCH_INDEXED.md"
    indexed_doc.write_text("---\nindex: true\n---\n# Indexed\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    quality_payload = {
        "status": "warn",
        "documents": [
            {
                "doc_name": "research_indexed",
                "path": str(indexed_doc),
                "project_slug": "active_project",
                "warning_count": 1,
                "warning_codes": ["SCF_DOC_UNINDEXED"],
            }
        ],
        "readiness_blocker_count": 0,
        "total_warning_count": 1,
        "readiness_blocker_counts_by_code": {"SCF_CHANGELOG_CURRENT_VERSION_MISSING": 1},
        "warnings": [
            {
                "code": "SCF_DOC_UNINDEXED",
                "severity": "warning",
                "blocking": False,
                "doc_name": "research_indexed",
                "path": str(indexed_doc),
                "suggested_repair": "Index the doc.",
            }
        ],
    }
    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        with patch("scribe_mcp.doc_management.runtime.collect_managed_doc_quality_state", return_value=quality_payload):
            result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    organization_digest = result.get("organization_digest") or {}
    warning_digest = organization_digest.get("quality_warning_digest") or []
    assert any(item.get("warning_code") == "SCF_DOC_UNINDEXED" for item in warning_digest)
    quality_warnings = quality_payload.get("warnings") or []
    assert quality_warnings[0].get("source_owner") is None
    status_sections = organization_digest.get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    assert index_section.get("status") == "needs_attention"
    derived = organization_digest.get("derived_signals") or []
    release_signal = next(item for item in derived if item.get("signal") == "release_changelog_coverage_missing")
    assert release_signal.get("active") is True
    assert "preview_reconciliation" in str(release_signal.get("next_safe_action", ""))


@pytest.mark.asyncio
async def test_project_health_does_not_treat_non_research_warning_as_research_index_failure(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "non_research_index_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    review_doc = docs_dir / "REVIEW_REPORT_PHASE_2.md"
    review_doc.write_text("# Review\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    quality_payload = {
        "status": "warn",
        "documents": [
            {
                "doc_name": "review_report_phase_2",
                "path": str(review_doc),
                "project_slug": "active_project",
                "warning_count": 1,
                "warning_codes": ["SCF_DOC_UNINDEXED"],
            }
        ],
        "readiness_blocker_count": 0,
        "total_warning_count": 1,
        "warnings": [
            {
                "code": "SCF_DOC_UNINDEXED",
                "severity": "warning",
                "blocking": False,
                "doc_name": "review_report_phase_2",
                "path": str(review_doc),
                "suggested_repair": "Refresh relevant index.",
            }
        ],
    }

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        with patch("scribe_mcp.doc_management.runtime.collect_managed_doc_quality_state", return_value=quality_payload):
            result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    status_sections = (result.get("organization_digest") or {}).get("status_sections") or {}
    index_section = status_sections.get("index") or {}
    project_artifacts = status_sections.get("project_artifacts") or {}
    assert index_section.get("status") == "ok"
    assert project_artifacts.get("status") == "needs_attention"
    assert "synthesis/review artifact" in str(project_artifacts.get("summary", "")).lower()


@pytest.mark.asyncio
async def test_project_health_reports_archive_preflight_status(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "archive_quality_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    preflight_family = docs_dir / "archive" / "preflight" / "research"
    preflight_family.mkdir(parents=True, exist_ok=True)
    (preflight_family / "RESEARCH_NOTE.md").write_text("# Archived note\n", encoding="utf-8")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    archive_section = status_sections.get("archive") or {}
    assert archive_section.get("status") == "evidence_present"
    assert archive_section.get("truth_label") == "direct_artifact"
    assert "contains 1 files across 1 families" in str(archive_section.get("summary"))


@pytest.mark.asyncio
async def test_project_health_reports_artifact_claim_status_for_duplicates_and_missing(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "artifact_claims_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    registered_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    active_project["docs"]["architecture_alias"] = str(registered_path)
    active_project["docs"]["missing_doc"] = str(docs_dir / "MISSING.md")

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    artifact_section = status_sections.get("artifact_claims") or {}
    assert artifact_section.get("status") == "needs_attention"
    details = artifact_section.get("details") or {}
    assert "missing_doc" in (details.get("missing_registered_paths") or [])
    duplicates = details.get("duplicate_claimed_paths") or {}
    assert str(registered_path) in duplicates
    assert set(duplicates[str(registered_path)]) >= {"architecture", "architecture_alias"}


@pytest.mark.asyncio
async def test_project_health_ignores_system_research_index_for_unregistered_claims(tmp_path: Path, test_agent: str) -> None:
    project_root = tmp_path / "artifact_claims_index_repo"
    active_project = _project_payload(project_root, "active_project")
    docs_dir = Path(active_project["docs_dir"])
    research_dir = docs_dir / "research"
    research_dir.mkdir(parents=True, exist_ok=True)
    research_index = research_dir / "INDEX.md"
    indexed_doc = research_dir / "RESEARCH_INDEXED.md"
    indexed_doc.write_text("# Indexed\n", encoding="utf-8")
    unregistered_doc = research_dir / "RESEARCH_UNREGISTERED.md"
    unregistered_doc.write_text("# Unregistered\n", encoding="utf-8")
    research_index.write_text(
        "# Research Documents Index\n\n"
        "- **[RESEARCH_INDEXED](RESEARCH_INDEXED.md)**\n",
        encoding="utf-8",
    )

    state_manager = StateManager(path=tmp_path / "state.json")
    await state_manager.set_current_project(active_project["name"], active_project)

    discovered_docs = [
        ScribeSourceDocument(
            path=research_index,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
        ScribeSourceDocument(
            path=indexed_doc,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
        ScribeSourceDocument(
            path=unregistered_doc,
            source_family="dev_plan",
            doc_type="research",
            project_slug="active_project",
        ),
    ]

    async with _isolated_server(
        state_manager, project_root=project_root, project_name=active_project["name"], agent=test_agent,
    ) as client:
        with patch("scribe_mcp.doc_management.runtime.utils_shared.discover_scribe_source_documents", return_value=discovered_docs):
            result = await _call_manage_docs(client, test_agent, action="project_health", metadata={"limit": 5}, dry_run=True)

    assert result["ok"] is True
    assert result["active_project"] == active_project["name"]
    organization_digest = result.get("organization_digest") or {}
    status_sections = organization_digest.get("status_sections") or {}
    artifact_section = status_sections.get("artifact_claims") or {}
    assert artifact_section.get("status") == "needs_attention"
    details = artifact_section.get("details") or {}
    unregistered = details.get("unregistered_active_docs") or []
    assert str(research_index) not in unregistered
    assert str(indexed_doc) not in unregistered
    assert str(unregistered_doc) in unregistered
