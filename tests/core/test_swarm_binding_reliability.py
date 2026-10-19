"""C-14 artifact and stage-local behavioral contracts.

Missing frozen interfaces fail *inside* their case.  They are never collection
failures, skips, or a reason to replace the product with a test implementation.
The final composed cases stay RED until their real source dependencies land.
"""
from __future__ import annotations

import asyncio
import contextvars
import copy
import hashlib
import importlib
import inspect
import json
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fixtures.storage import sqlite_storage as _canonical_sqlite_storage

from fixtures.swarm import (
    MIX, TIMING_PHASES, CausalGate, ExpectedEffect, ManualClock, ObservedEffect,
    SwarmRunMetadata, build_mixed_schedule, build_swarm_topology,
    reconcile_exact_effects,
)

pytestmark = [pytest.mark.core, pytest.mark.regression,
              pytest.mark.usefixtures("test_agent")]
SEED = 20260927
@asynccontextmanager
async def canonical_sqlite_lifecycle(path):
    """Enter the canonical fixture only after a case's absence assertions."""
    lifecycle = _canonical_sqlite_storage.__wrapped__(path)
    try:
        yield await anext(lifecycle)
    finally:
        await lifecycle.aclose()


def required(module: str, *names: str):
    """Assert the precise frozen symbol boundary without hiding import defects."""
    loaded = importlib.import_module(module)
    missing = [name for name in names if not hasattr(loaded, name)]
    assert not missing, f"Frozen contract absent: {module}: {', '.join(missing)}"
    return loaded


def parameters(function, *names: str) -> None:
    missing = set(names) - inspect.signature(function).parameters.keys()
    assert not missing, f"Frozen contract absent: {function.__qualname__} parameters {sorted(missing)}"


def sqlite_contract():
    module = required("scribe_mcp.storage.sqlite", "SQLiteStorage")
    parameters(module.SQLiteStorage.set_session_project, "project_key", "expected_generation")
    return module.SQLiteStorage


def resolver_contract():
    module = required("scribe_mcp.shared.logging_utils", "resolve_project_target", "ProjectResolutionError")
    parameters(module.resolve_project_target, "caller_session_key", "target")
    return module


def receipt_contract():
    module = required("scribe_mcp.tools.set_project", "set_project")
    parameters(module.set_project, "expected_generation", "format")
    return module


def timing_contract():
    module = required("scribe_mcp.runtime_timing_envelope", "CALL_TIMING_PHASES_V2",
                      "CallTimingEnvelopeV2", "CallTimingRecorderV2", "build_call_timing_envelope_v2")
    assert module.CALL_TIMING_PHASES_V2 == TIMING_PHASES
    return module


def get_contract():
    mixin = required("scribe_mcp.shared.base_logging_tool", "LoggingToolMixin").LoggingToolMixin
    parameters(mixin.prepare_context, "resolved_request_context")
    assert callable(getattr(mixin, "project_record_from_context", None)), (
        "Frozen contract absent: LoggingToolMixin.project_record_from_context")
    return required("scribe_mcp.tools.get_project", "get_project")


def read_contract():
    module = required("scribe_mcp.tools.query_entries", "query_entries", "_build_search_query",
                      "_execute_search_with_fallbacks")
    parameters(module._build_search_query, "project_record")
    parameters(module._execute_search_with_fallbacks, "project_record", "resolved_request_context", "timing")
    return module


def payload(result) -> dict:
    if isinstance(result, dict):
        return result.get("structuredContent", result)
    data = result.structuredContent
    assert isinstance(data, dict), "structured result required"
    return data


def assert_error(result, code: str) -> None:
    data = payload(result)
    assert data["ok"] is False
    assert data["error_code"] == code
    assert set(("message", "retryable", "target", "candidates", "remediation", "correlation_id")) <= data.keys()
    assert data["correlation_id"]
    assert (result.get("isError") if isinstance(result, dict) else result.isError) is True


def receipt_from_response(result):
    """Read C-03 from structured output or a serialized readable receipt."""
    data = result if isinstance(result, dict) else result.structuredContent
    if isinstance(data, dict):
        return data["binding_receipt"]
    decoder = json.JSONDecoder()
    for block in result.content:
        text = getattr(block, "text", "")
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                if "binding_receipt" in candidate:
                    return candidate["binding_receipt"]
                if {"caller_session_key_hash", "binding_generation", "persistent_write_performed"} <= candidate.keys():
                    return candidate
    raise AssertionError("C-03 serialized binding receipt absent from readable response")


def assert_receipt(data: dict, *, limit: int) -> None:
    assert data["schema_version"] == "scribe-structured-receipt.v1"
    assert data["ok"] is True
    assert set(("operation", "project", "binding", "durability", "artifact", "correlation_id", "retry")) <= data.keys()
    assert data["binding"]["generation"] > 0
    assert len(data["binding"]["id"]) == 64
    assert set(("file", "db_mirror", "audit_id")) <= data["durability"].keys()
    assert set(("kind", "id", "path", "affected_count")) <= data["artifact"].keys()
    assert set(("queued", "retryable", "retry_after_ms")) <= data["retry"].keys()
    assert not set(("written_line", "reminders", "recent_projects", "timing", "paths")) & data.keys()
    metadata = {key: value for key, value in data.items() if key not in ("entries", "content")}
    assert len(json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()) <= limit


def assert_project_snapshot(data, *, mode, expected, messages, verbose):
    """Check requested project truth before comparing response projections."""
    assert data["ok"] is True
    project = data["project"]
    assert project["name"] == expected["name"]
    if mode in ("structured", "compact", "both"):
        assert_receipt(data, limit=1536)
        key = project["key"]
        assert data["binding"]["id"] == expected["caller_hash"]
        assert data["binding"]["generation"] == expected["generation"]
        assert "recent_entries" not in data, "concise project receipt leaked recent-entry narration"
    else:
        key = project["project_key"]
        assert project["root"] == expected["root"]
        assert project["progress_log"] == expected["progress_log"]
        assert project["docs"]["architecture"] == expected["architecture"]
        assert data["entry_count"] == len(messages)
        assert Counter(entry["message"] for entry in data.get("recent_entries", [])) == (Counter(messages) if verbose else Counter())
    assert key == expected["key"]
    return key, project["name"]


def assert_filtered_pages(pages, expected_entries, *, page_size=2):
    """Reconcile complete caller-requested bodies and IDs against seeded writes."""
    seen = {}
    total = len(expected_entries)
    assert len(pages) == (total + page_size - 1) // page_size + 1
    for number, data in enumerate(pages, 1):
        assert data["ok"] is True
        pagination = data["pagination"]
        assert {key: pagination[key] for key in ("page", "page_size", "total_count", "has_next", "has_prev")} == {
            "page": number, "page_size": page_size, "total_count": total,
            "has_next": number * page_size < total, "has_prev": number > 1}
        entries = data["entries"]
        assert len(entries) == min(page_size, max(0, total - (number - 1) * page_size))
        for entry in entries:
            entry_id = entry["id"]
            assert entry_id not in seen, "pagination repeated an entry"
            assert entry_id in expected_entries, "filter admitted an unrequested entry"
            assert entry["message"] == expected_entries[entry_id], "requested body changed or truncated"
            seen[entry_id] = entry["message"]
    assert seen == expected_entries, "pagination lost the partial terminal page"


def assert_noop_tool_state(before, after, sample):
    """Only append-only tool audit rows/files may differ after a no-op bind."""
    assert sample.binding_writes == 0
    for batch in sample.persistent_write_batches:
        assert batch["statements"], "a measured persistent write must be classified"
        assert all(re.match(r'\s*INSERT\s+INTO\s+["`\[]?tool_calls["`\]]?(?:\s|\()',
                            statement, re.IGNORECASE) for statement in batch["statements"]), batch
    def without_audit(snapshot):
        result = copy.deepcopy(snapshot)
        result["database"].pop("tool_calls", None)
        result["files"] = {path: content for path, content in result["files"].items()
                           if Path(path).name != "TOOL_LOG.jsonl"}
        return result
    assert without_audit(after) == without_audit(before)
    assert not (Counter(before["database"].get("tool_calls", []))
                - Counter(after["database"].get("tool_calls", []))), "existing audit rows changed"
    for path, content in before["files"].items():
        if Path(path).name == "TOOL_LOG.jsonl":
            assert after["files"][path].startswith(content), "existing audit bytes changed"


def sample_effect(operation_id="operation-1", *, code="OK", effect="log"):
    return ExpectedEffect("run-1", operation_id, "caller-00", "app-hash", "session-hash",
                          "project-a", None, "project-a", "content-digest", effect, code)


def observation(expected: ExpectedEffect, **changes) -> ObservedEffect:
    return ObservedEffect(**(asdict(expected) | {"default_after": expected.default_project_key} | changes))


def metadata(**changes) -> SwarmRunMetadata:
    return SwarmRunMetadata(**({"source_revision": "test-corpus", "seed": SEED,
                               "topology": {}, "set_project_count": {"caller-00": 1}} | changes))


class TestSBRHarness:
    @pytest.mark.parametrize("corruption", [None, "lost_tail", "duplicate", "filter_leak", "truncated_body",
                                             "wrong_total", "wrong_terminal", "missing_empty_page"])
    def test_filtered_page_assertions_detect_selection_and_pagination_corruption(self, corruption):
        expected = {f"entry-{i}": f"complete message {i}" for i in range(5)}
        rows = [{"id": key, "message": message} for key, message in expected.items()]
        pages = [{"ok": True, "entries": rows[(page - 1) * 2:page * 2], "pagination": {
            "page": page, "page_size": 2, "total_count": 5, "has_next": page < 3, "has_prev": page > 1}}
            for page in range(1, 5)]
        if corruption == "lost_tail":
            pages[2]["entries"] = []
        elif corruption == "duplicate":
            pages[2]["entries"] = [copy.deepcopy(rows[0])]
        elif corruption == "filter_leak":
            pages[2]["entries"] = [{"id": "excluded", "message": "foreign"}]
        elif corruption == "truncated_body":
            pages[0]["entries"][0]["message"] = "complete"
        elif corruption == "wrong_total":
            pages[0]["pagination"]["total_count"] = 10
        elif corruption == "wrong_terminal":
            pages[2]["pagination"]["has_next"] = True
        elif corruption == "missing_empty_page":
            pages.pop()
        if corruption is None:
            assert_filtered_pages(pages, expected)
        else:
            with pytest.raises(AssertionError):
                assert_filtered_pages(pages, expected)

    @pytest.mark.parametrize("corruption", [None, "key", "name", "root", "progress_log", "architecture", "body", "count"])
    def test_full_project_assertions_detect_identity_and_snapshot_corruption(self, corruption):
        expected = {"key": "project-key", "name": "target", "root": "/target", "progress_log": "/target/PROGRESS_LOG.md",
                    "architecture": "/target/ARCHITECTURE_GUIDE.md"}
        data = {"ok": True, "project": {"project_key": expected["key"], "name": expected["name"],
            "root": expected["root"], "progress_log": expected["progress_log"],
            "docs": {"architecture": expected["architecture"]}}, "entry_count": 1,
            "recent_entries": [{"message": "target snapshot"}]}
        if corruption in ("key", "name", "root", "progress_log"):
            data["project"]["project_key" if corruption == "key" else corruption] = "foreign"
        elif corruption == "architecture":
            data["project"]["docs"]["architecture"] = "/foreign/ARCHITECTURE_GUIDE.md"
        elif corruption == "body":
            data["recent_entries"][0]["message"] = "foreign snapshot"
        elif corruption == "count":
            data["entry_count"] = 0
        if corruption is None:
            assert assert_project_snapshot(data, mode="structured_full", expected=expected,
                                           messages=["target snapshot"], verbose=True) == (expected["key"], expected["name"])
        else:
            with pytest.raises(AssertionError):
                assert_project_snapshot(data, mode="structured_full", expected=expected,
                                        messages=["target snapshot"], verbose=True)

    @pytest.mark.parametrize("corruption", [None, "binding_write", "unchanged_update", "project", "recents", "defaults",
                                             "cache", "audit_rewrite", "audit_file_rewrite"])
    def test_noop_assertions_allow_only_append_only_audit(self, corruption):
        before = {"database": {"projects": [("target",)], "tool_calls": [("old-audit",)]},
                  "files": {"TOOL_LOG.jsonl": b"old audit\n", "PROGRESS_LOG.md": b"unchanged\n"},
                  "recents": ("target",), "defaults": {"session": "target"}, "project_cache": {"target": "record"}}
        after = copy.deepcopy(before)
        after["database"]["tool_calls"].append(("new-audit",))
        after["files"]["TOOL_LOG.jsonl"] += b"new audit\n"
        sample = CallObservation(persistent_write_batches=[{"changed_rows": 1,
            "statements": ("INSERT INTO tool_calls VALUES ('new-audit')",)}])
        if corruption == "binding_write":
            sample.binding_writes = 1
        elif corruption == "unchanged_update":
            sample.persistent_write_batches.append({"changed_rows": 1, "statements": ("UPDATE projects SET name = name",)})
        elif corruption == "project":
            after["database"]["projects"] = [("foreign",)]
        elif corruption in ("recents", "defaults"):
            after[corruption] = "foreign"
        elif corruption == "cache":
            after["project_cache"]["target"] = "changed"
        elif corruption == "audit_rewrite":
            after["database"]["tool_calls"][0] = ("rewritten",)
        elif corruption == "audit_file_rewrite":
            after["files"]["TOOL_LOG.jsonl"] = b"rewritten audit\n"
        if corruption is None:
            assert_noop_tool_state(before, after, sample)
        else:
            with pytest.raises(AssertionError):
                assert_noop_tool_state(before, after, sample)

    def test_topology_and_every_seeded_100_call_schedule(self, tmp_path, test_agent):
        topology = build_swarm_topology(tmp_path, agent_label=test_agent, seed=SEED)
        assert len(topology.repositories) == 4
        assert len(topology.projects) == 16
        assert len(topology.callers) == 32
        assert Counter(c.default.project_key for c in topology.callers) == {
            p.project_key: 2 for p in topology.projects}
        assert {c.agent_label for c in topology.callers} == {test_agent}
        assert Counter(p.name for p in topology.projects)["shared"] == 4
        ids = []
        for caller in topology.callers:
            schedule = build_mixed_schedule(caller, seed=SEED)
            assert len(schedule) == 100
            assert Counter(op.kind for op in schedule) == MIX
            assert schedule == build_mixed_schedule(caller, seed=SEED)
            assert schedule != build_mixed_schedule(caller, seed=SEED + 1)
            assert caller.same_repo.root == caller.default.root
            assert caller.same_repo != caller.default
            assert caller.cross_repo.root != caller.default.root
            ids.extend(op.operation_id for op in schedule)
        assert len(ids) == len(set(ids)) == 3200

    def test_manual_clock_uses_milliseconds(self):
        clock = ManualClock()
        assert clock.now() == 0
        clock.advance(100)
        clock.advance(400)
        assert clock.now() == 0.5

    @pytest.mark.parametrize("delta", [-1, True, 1.5, "100"])
    def test_manual_clock_rejects_nonmonotonic_or_ambiguous_input(self, delta):
        clock = ManualClock()
        with pytest.raises(ValueError):
            clock.advance(delta)
        assert clock.now() == 0

    @pytest.mark.asyncio
    async def test_causal_gate_proves_peer_progress_before_release(self):
        gate = CausalGate()
        task = asyncio.create_task(gate.hold())
        try:
            await asyncio.wait_for(gate.entered.wait(), 1)
            assert not task.done()
            async def peer():
                return "peer reached checkpoint"
            assert await asyncio.create_task(peer()) == "peer reached checkpoint"
            assert not gate.release.is_set() and not task.done()
            gate.release.set()
            await asyncio.wait_for(task, 1)
        finally:
            gate.release.set()
            await task

    def test_exact_multiset_rejects_missing_and_duplicate_equal_total(self):
        first, second = sample_effect("first"), sample_effect("second")
        result = reconcile_exact_effects([first, second], [observation(first), observation(first)], metadata=metadata())
        assert result.verdict == "FAIL"
        assert result.oracle_cardinalities["missing_effects"] == 1
        assert result.oracle_cardinalities["duplicate_effects"] == 1

    @pytest.mark.parametrize(("changes", "counter"), [
        ({"target_project_key": "project-b"}, "wrong_target"),
        ({"default_after": "project-b"}, "default_drift"),
        ({"generation_after": 2}, "default_drift"),
        ({"stable_session_id": "stolen"}, "cross_talk"),
        ({"application_id": "other"}, "cross_talk"),
        ({"mutation_fingerprint": "different-content"}, "missing_effects"),
        ({"result_code": "raw exception"}, "untyped_errors"),
        ({"stale_fence_accepted": True}, "stale_fences"),
        ({"binding_reads": 2}, "excess_reads"),
        ({"project_reads": 2}, "excess_reads"),
        ({"context_count": 2}, "context_or_timing"),
        ({"timing_envelope_count": 0}, "context_or_timing"),
        ({"accounted_ratio": 0.949}, "unaccounted_calls"),
    ])
    def test_oracle_detects_single_field_perturbation(self, changes, counter):
        expected = sample_effect()
        result = reconcile_exact_effects([expected], [observation(expected, **changes)], metadata=metadata())
        assert result.verdict == "FAIL"
        assert result.oracle_cardinalities[counter] == 1

    def test_denied_effect_is_never_hidden_by_a_success_boolean(self):
        expected = sample_effect(code="SCRIBE_PROJECT_NOT_FOUND", effect="none")
        result = reconcile_exact_effects([expected], [observation(expected, effect="log")], metadata=metadata())
        assert result.oracle_cardinalities["denied_effects"] == 1
        assert result.verdict == "FAIL"

    @pytest.mark.parametrize("metric", ["items", "bytes", "global", "project", "heavy"])
    def test_capacity_negative_controls(self, metric):
        sample = {k: 1 for k in ("items", "bytes", "global", "project", "heavy")}
        sample.update({f"{k}_limit": 1 for k in tuple(sample)})
        assert reconcile_exact_effects([], [], metadata=metadata(background_queue={"capacity_samples": [sample]})).verdict == "PASS"
        sample[metric] = 2
        result = reconcile_exact_effects([], [], metadata=metadata(background_queue={"capacity_samples": [sample]}))
        assert result.oracle_cardinalities["excess_capacity"] == 1

    @pytest.mark.parametrize(("field", "value"), [("lead_units", 2), ("eligible_peer_share", 0.51), ("starvation_ms", 5000)])
    def test_unfairness_negative_controls(self, field, value):
        sample = {"lead_units": 1, "eligible_peer_share": 0.5, "starvation_ms": 4999}
        assert reconcile_exact_effects([], [], metadata=metadata(background_queue={"fairness_samples": [sample]})).verdict == "PASS"
        sample[field] = value
        result = reconcile_exact_effects([], [], metadata=metadata(background_queue={"fairness_samples": [sample]}))
        assert result.oracle_cardinalities["unfairness"] == 1

    def test_bind_and_teardown_negative_controls(self):
        result = reconcile_exact_effects([], [], metadata=metadata(set_project_count={"caller-00": 2}, teardown_counts={"tasks": 1}))
        assert result.oracle_cardinalities["bind_count"] == 1
        assert result.oracle_cardinalities["teardown_leaks"] == 1

    def test_missing_bind_count_and_nested_result_mutation_cannot_hide_failure(self):
        expected = sample_effect()
        result = reconcile_exact_effects([expected], [observation(expected)], metadata=metadata(set_project_count={}))
        assert result.oracle_cardinalities["bind_count"] == 1
        exported = result.as_json_dict()
        exported["operation_ledger"][0]["observed"]["target_project_key"] = "forged"
        assert result.as_json_dict()["operation_ledger"][0]["observed"]["target_project_key"] == expected.target_project_key

    def test_swarm_exact_effects_and_c14_serialization_are_deterministic(self):
        a, b = sample_effect("a"), sample_effect("b")
        left = reconcile_exact_effects([a, b], [observation(a), observation(b)], metadata=metadata())
        right = reconcile_exact_effects([b, a], [observation(b), observation(a)], metadata=metadata())
        assert left.verdict == right.verdict == "PASS"
        assert left.as_json_dict() == right.as_json_dict()
        assert set(left.as_json_dict()) == {"schema_version", "source_revision", "seed", "topology",
            "set_project_count", "operation_ledger", "oracle_cardinalities", "background_queue",
            "timing_histograms", "fault_timeline", "teardown_counts", "verdict"}
        assert left.as_json_dict()["schema_version"] == "scribe-swarm-results.v1"
        assert json.loads(left.as_markdown().split("```json\n")[1].split("\n```")[0]) == left.as_json_dict()


@asynccontextmanager
async def binding_store(tmp_path, test_agent):
    storage_type = sqlite_contract()  # before any resource/setup
    storage = storage_type(tmp_path / "bindings.db")
    await storage.setup()
    try:
        projects = []
        for index in range(2):
            root = tmp_path / f"repo-{index}"
            root.mkdir()
            projects.append(await storage.upsert_project(name=f"project-{index}", repo_root=str(root),
                progress_log_path=str(root / "PROGRESS_LOG.md")))
        await storage.upsert_session(session_id="stable-1", agent_id=test_agent,
                                     repo_root=projects[0].repo_root, mode="project")
        yield storage, projects
    finally:
        await storage.close()


async def database_snapshot(storage):
    """Read every authoritative user table, including recents/index/cache mirrors."""
    names = await storage._fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name", ())
    return {row["name"]: sorted([tuple(r) for r in await storage._fetchall(
        'SELECT * FROM "' + row["name"].replace('"', '""') + '"', ())], key=repr) for row in names}


class TestSBRSQLiteBinding:
    def test_required_contract_is_present(self):
        sqlite_contract()

    @pytest.mark.parametrize("generation", [0, -1, True, 1.5])
    def test_session_binding_record_v2_rejects_invalid_generation_and_naive_timestamp(self, tmp_path, generation):
        model = required("scribe_mcp.storage.models", "SessionBindingRecordV2").SessionBindingRecordV2
        args = dict(caller_session_key_hash="a" * 64, project_key="key", project_name="project",
                    canonical_repo_root=str(tmp_path), binding_generation=generation,
                    updated_at=datetime.now(timezone.utc))
        with pytest.raises(ValueError):
            model(**args)
        with pytest.raises(ValueError):
            model(**(args | {"binding_generation": 1, "updated_at": datetime(2026, 1, 1)}))

    @pytest.mark.asyncio
    async def test_binding_contract_generation_and_zero_write_semantics(self, tmp_path, test_agent):
        async with binding_store(tmp_path, test_agent) as (store, projects):
            first = await store.set_session_project("stable-1", project_key=projects[0].project_key)
            assert first.binding_generation == 1
            assert first == await store.get_session_project("stable-1")
            changed = await store.set_session_project("stable-1", project_key=projects[1].project_key, expected_generation=1)
            assert changed.project_key == projects[1].project_key
            assert changed.binding_generation == 2
            assert changed.caller_session_key_hash == first.caller_session_key_hash

    @pytest.mark.asyncio
    async def test_unchanged_bind_has_zero_persistent_writes(self, tmp_path, test_agent, monkeypatch):
        async with binding_store(tmp_path, test_agent) as (store, projects):
            first = await store.set_session_project("stable-1", project_key=projects[0].project_key)
            before = await database_snapshot(store)
            writes = []
            original = store._internals._run_with_connection
            def measured(fn):
                def execute(conn):
                    previous = conn.total_changes
                    try:
                        return fn(conn)
                    finally:
                        writes.append(conn.total_changes - previous)
                return original(execute)
            with monkeypatch.context() as patch:
                patch.setattr(store._internals, "_run_with_connection", measured)
                second = await store.set_session_project("stable-1", project_key=projects[0].project_key, expected_generation=1)
            assert writes, "probe must observe the actual storage connection"
            assert sum(writes) == 0
            assert second == first and second.updated_at == first.updated_at
            assert await database_snapshot(store) == before

    @pytest.mark.asyncio
    async def test_stale_same_and_changed_bind_are_effect_free(self, tmp_path, test_agent):
        async with binding_store(tmp_path, test_agent) as (store, projects):
            await store.set_session_project("stable-1", project_key=projects[0].project_key)
            before = await database_snapshot(store)
            conflict = required("scribe_mcp.storage.base", "ConflictError").ConflictError
            for project in projects:
                with pytest.raises(conflict):
                    await store.set_session_project("stable-1", project_key=project.project_key, expected_generation=0)
                assert await database_snapshot(store) == before

    @pytest.mark.asyncio
    async def test_32_same_label_persisted_sessions_are_independent(self, tmp_path, test_agent):
        async with binding_store(tmp_path, test_agent) as (store, projects):
            for index in range(32):
                await store.upsert_session(session_id=f"session-{index}", agent_id=test_agent,
                                           repo_root=projects[index % 2].repo_root, mode="project")
            records = await asyncio.gather(*(store.set_session_project(f"session-{i}", project_key=projects[i % 2].project_key) for i in range(32)))
            assert len({r.caller_session_key_hash for r in records}) == 32
            assert [r.project_key for r in records] == [projects[i % 2].project_key for i in range(32)]
            assert all(r.binding_generation == 1 for r in records)
            for i, record in enumerate(records):
                assert await store.get_session_project(f"session-{i}") == record


def frozen_context(tmp_path, test_agent):
    c = required("scribe_mcp.shared.execution_context", "ResolvedProjectTargetV1", "build_resolved_request_context")
    target = c.ResolvedProjectTargetV1("key", "project", str(tmp_path), "repo", "project_key", 1)
    return c.build_resolved_request_context(caller_session_key="server-owned-caller",
        resolved_target=target, agent_attribution=c.AgentAttributionV1(test_agent),
        correlation_id="correlation-1", operating_mode="project",
        authorization_evidence=c.AuthorizationEvidenceV1("server", True, ("scope:project",)))


class TestSBRTargetResolution:
    def test_required_contract_is_present(self):
        resolver_contract()

    def test_implemented_context_is_frozen_and_attribution_is_not_authority(self, tmp_path, test_agent):
        from dataclasses import FrozenInstanceError
        c = frozen_context(tmp_path, test_agent)
        assert c.default_binding_generation == 1
        assert c.resolved_target.project_key == "key"
        assert len(c.caller_session_key_hash) == 64
        assert "server-owned-caller" not in repr(c)
        with pytest.raises(FrozenInstanceError):
            c.default_binding_generation = 2
        assert replace(c, agent_attribution=replace(c.agent_attribution, agent_id="display-only")) == c

    @pytest.mark.asyncio
    async def test_explicit_cross_repo_target_preserves_default(self, tmp_path, monkeypatch, test_agent):
        resolver_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller = w.topology.callers[0]
            await w.bind_storage(caller)
            before = await w.snapshot()
            c = required("scribe_mcp.shared.execution_context", "ProjectTargetV1")
            result = await resolver_contract().resolve_project_target(w.sessions[caller.caller_id],
                c.ProjectTargetV1(project_key=w.project(caller.cross_repo).project_key))
            assert result.project_key == w.project(caller.cross_repo).project_key
            assert result.default_binding_generation == 1
            assert await w.snapshot() == before

    @pytest.mark.parametrize("selector", ["project_key", "name_and_root", "unique_name", "caller_default"])
    @pytest.mark.asyncio
    async def test_resolver_precedence(self, tmp_path, monkeypatch, test_agent, selector):
        resolver_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller = w.topology.callers[2]
            await w.bind_storage(caller)
            p = w.project(caller.default)
            c = required("scribe_mcp.shared.execution_context", "ProjectTargetV1")
            target = {"project_key": c.ProjectTargetV1(project_key=p.project_key),
                      "name_and_root": c.ProjectTargetV1(project=p.name, repo_root=p.repo_root),
                      "unique_name": c.ProjectTargetV1(project=p.name), "caller_default": None}[selector]
            before = await w.snapshot()
            result = await resolver_contract().resolve_project_target(w.sessions[caller.caller_id], target)
            assert result.project_key == p.project_key
            assert result.resolution_source == selector
            assert await w.snapshot() == before

    @pytest.mark.parametrize("code", ["SCRIBE_PROJECT_AMBIGUOUS", "SCRIBE_PROJECT_NOT_FOUND",
        "SCRIBE_PROJECT_ROOT_MISMATCH", "SCRIBE_BINDING_MISSING", "SCRIBE_CALLER_SESSION_UNVERIFIED"])
    @pytest.mark.asyncio
    async def test_refusal_is_typed_and_effect_free(self, tmp_path, monkeypatch, test_agent, code):
        resolver_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            await w.assert_negative(w.topology.callers[0], code)


class TestSBRBindingReceipt:
    def test_required_contract_is_present(self):
        receipt_contract()

    @pytest.mark.asyncio
    async def test_delayed_second_write_preserves_generation(self, tmp_path, monkeypatch, test_agent):
        receipt_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller = w.topology.callers[0]
            await w.bind(caller)
            first = await w.binding(caller)
            await w.call(caller, "append_entry", message="first-write", project=caller.default.name)
            gate = CausalGate()
            async def delayed():
                await gate.hold()
                return await w.call(caller, "append_entry", message="second-write", project=caller.default.name)
            task = asyncio.create_task(delayed())
            try:
                await asyncio.wait_for(gate.entered.wait(), 1)
                await w.call(caller, "get_project")
                await w.call(caller, "read_recent", n=1)
                assert await w.binding(caller) == first
                gate.release.set()
                result = payload(await asyncio.wait_for(task, 5))
                assert result["ok"] is True
                assert w.samples[caller.caller_id].binding_writes == 0
                assert await w.binding(caller) == first
                assert w.bind_counts[caller.caller_id] == 1
                text = caller.default.progress_log.read_text()
                assert text.count("first-write") == text.count("second-write") == 1
            finally:
                gate.release.set()
                await task

    @pytest.mark.parametrize("mode", ["readable", "structured", "compact", "structured_full", "both", "both_full"])
    @pytest.mark.asyncio
    async def test_changed_reused_and_stale_receipts(self, tmp_path, monkeypatch, test_agent, mode):
        receipt_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller = w.topology.callers[0]
            receipt = receipt_from_response(await w.bind(caller, format=mode))
            assert receipt["binding_generation"] == 1
            assert receipt["persistent_write_performed"] is True
            assert receipt["binding_reused"] is False
            first = await w.binding(caller)
            before = await w.snapshot()
            reused = receipt_from_response(await w.bind(caller, format=mode, expected_generation=1))
            noop_sample = w.samples[caller.caller_id]
            assert reused["binding_reused"] is True and reused["persistent_write_performed"] is False
            assert await w.binding(caller) == first
            assert_noop_tool_state(before, await w.snapshot(), noop_sample)
            stale_before = await w.snapshot()
            assert_error(await w.bind(caller, format=mode, expected_generation=0), "SCRIBE_BINDING_GENERATION_STALE")
            assert await w.snapshot() == stale_before
            changed = receipt_from_response(await w.bind(caller, project=caller.same_repo, format=mode, expected_generation=1))
            assert changed["binding_generation"] == 2
            assert changed["project_key"] == w.project(caller.same_repo).project_key
            assert changed["persistent_write_performed"] is True


class TestSBRTiming:
    def test_required_contract_is_present(self):
        timing_contract()

    @pytest.mark.parametrize(("phase_ms", "total_ms", "slow", "tripped"), [
        (100, 500, [], False), (100.001, 500, ["tool_body"], True),
        (100, 500.001, [], True), (0, 0, [], False)])
    def test_strict_tripwire_boundaries_and_exact_phase_order(self, phase_ms, total_ms, slow, tripped):
        timing = timing_contract()
        envelope = timing.build_call_timing_envelope_v2(correlation_id="c", phases_ms={"tool_body": phase_ms}, total_ms=total_ms)
        assert tuple(envelope["phases_ms"]) == TIMING_PHASES
        assert envelope["slow_stages"] == slow
        assert envelope["tripwire_exceeded"] is tripped
        assert envelope["phases_ms"]["unaccounted"] == max(total_ms - phase_ms, 0)
        assert envelope["accounted_ratio"] == (min(phase_ms / total_ms, 1) if total_ms else 1)

    def test_manual_clock_recorder_accumulates_without_padding_coverage(self):
        timing = timing_contract()
        clock = ManualClock()
        recorder = timing.CallTimingRecorderV2.start(correlation_id="c", started_perf_counter=clock.now())
        for phase in TIMING_PHASES[:-1]:
            start = clock.now()
            clock.advance(10)
            recorder.record_phase(phase, (clock.now() - start) * 1000)
        recorder.record_phase("tool_body", 5)
        clock.advance(5)
        result = recorder.finalize(total_ms=clock.now() * 1000)
        assert result["correlation_id"] == "c"
        assert result["accounted_ratio"] == pytest.approx(1)
        assert result["phases_ms"]["tool_body"] == pytest.approx(15)
        deficient = timing.build_call_timing_envelope_v2(correlation_id="c", phases_ms={"tool_body": 94}, total_ms=100)
        assert deficient["accounted_ratio"] == 0.94
        assert deficient["phases_ms"]["unaccounted"] == 6

    @pytest.mark.parametrize("phases", [{"unknown": 1}, {"hooks": -1}, {"audit_append": float("nan")}, {"hooks": float("inf")}])
    def test_invalid_duration_or_phase_fails_closed(self, phases):
        timing = timing_contract()
        with pytest.raises(ValueError):
            timing.build_call_timing_envelope_v2(correlation_id="c", phases_ms=phases, total_ms=100)

    @pytest.mark.asyncio
    async def test_formatter_uses_frozen_context_without_reads_and_audits_before_projection(
            self, tmp_path, monkeypatch, test_agent):
        timing_contract()
        formatter_module = required("scribe_mcp.utils.formatters.dispatcher", "FormatterDispatcher",
                                    "project_structured_success")
        parameters(formatter_module.FormatterDispatcher.finalize_tool_response, "resolved_request_context")
        async with canonical_sqlite_lifecycle(tmp_path / "formatter.db") as sqlite_storage:
            from scribe_mcp import server
            from scribe_mcp.utils import tool_logger
            from scribe_mcp.config.settings import settings
            context = frozen_context(tmp_path, test_agent)
            monkeypatch.setattr(server, "storage_backend", sqlite_storage)
            monkeypatch.setattr(server, "get_execution_context", lambda: SimpleNamespace(
                session_id="test-session", affected_dev_projects=["project"], resolved_request_context=context))
            monkeypatch.setattr(tool_logger, "settings", replace(settings, project_root=tmp_path))
            reads, order, audits = [], [], []
            fetch = sqlite_storage.fetch_project_sync
            def counted_fetch(*args, **kwargs):
                reads.append((args, kwargs))
                return fetch(*args, **kwargs)
            monkeypatch.setattr(sqlite_storage, "fetch_project_sync", counted_fetch)
            audit = formatter_module._log_tool_call
            def audited(*args, **kwargs):
                order.append("audit")
                audits.append(dict(kwargs))
                assert kwargs["repo_root"] == str(tmp_path)
                return audit(*args, **kwargs)
            monkeypatch.setattr(formatter_module, "_log_tool_call", audited)
            projector = formatter_module.project_structured_success
            def projected(data, **kwargs):
                order.append("projection")
                assert kwargs["resolved_request_context"] is context
                assert data["written_line"] == "complete-audit-" + "x" * 2048
                return projector(data, **kwargs)
            monkeypatch.setattr(formatter_module, "project_structured_success", projected)
            complete = {"ok": True, "id": "entry-1", "entry_id": "entry-1", "project_name": "project",
                        "path": str(tmp_path / "PROGRESS_LOG.md"), "written_line": "complete-audit-" + "x" * 2048,
                        "db_mirror": {"status": "ok"}, "correlation_id": context.correlation_id,
                        "reminders": [{"message": "full diagnostic"}]}
            original = copy.deepcopy(complete)
            result = payload(await formatter_module.FormatterDispatcher().finalize_tool_response(
                complete, format="structured", tool_name="append_entry", resolved_request_context=context))
            assert reads == []
            assert order == ["audit", "projection"]
            assert len(audits) == 1
            assert audits[0]["response_size_bytes"] >= len(original["written_line"].encode())
            assert complete == original
            assert_receipt(result, limit=512)
            logs = list(tmp_path.rglob("TOOL_LOG.jsonl"))
            assert len(logs) == 1
            assert len(logs[0].read_text().splitlines()) == 1


class TestSBRGetProject:
    def test_required_contract_is_present(self):
        get_contract()

    @pytest.mark.parametrize("mode", ["structured", "compact", "structured_full", "both", "both_full"])
    @pytest.mark.parametrize("verbose", [False, True])
    @pytest.mark.asyncio
    async def test_immediate_project_snapshot_one_context_and_read(self, tmp_path, monkeypatch, test_agent, mode, verbose):
        get_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller, peer = w.topology.callers[2], w.topology.callers[10]
            await w.bind(caller)
            await w.bind(peer)
            messages = [f"target-project-snapshot-{i}" for i in range(3)]
            for message in messages:
                assert payload(await w.call(caller, "append_entry", message=message))["ok"] is True
            assert payload(await w.call(peer, "append_entry", message="foreign-project-snapshot"))["ok"] is True
            before = await w.binding(caller)
            expected = {"key": before.project_key, "name": caller.default.name,
                        "root": str(caller.default.root), "progress_log": str(caller.default.progress_log),
                        "architecture": str(caller.default.progress_log.parent / "ARCHITECTURE_GUIDE.md"),
                        "caller_hash": before.caller_session_key_hash, "generation": before.binding_generation}
            truths = []
            for response_mode in dict.fromkeys((mode, "structured", "structured_full")):
                result = payload(await w.call(caller, "get_project", format=response_mode, verbose=verbose))
                truths.append(assert_project_snapshot(result, mode=response_mode, expected=expected,
                    messages=messages, verbose=verbose))
                w.assert_call_observations(caller)
            assert all(truth == truths[0] for truth in truths), "receipt/full project snapshot drift"
            assert await w.binding(caller) == before


class TestSBRReadQuery:
    def test_required_contract_is_present(self):
        read_contract()

    @pytest.mark.parametrize("tool", ["read_recent", "query_entries"])
    @pytest.mark.parametrize("mode", ["structured", "compact", "structured_full", "both", "both_full"])
    @pytest.mark.asyncio
    async def test_complete_page_filter_snapshot_and_default_preservation(self, tmp_path, monkeypatch, test_agent, tool, mode):
        read_contract()
        async with world(tmp_path, monkeypatch, test_agent) as w:
            caller = w.topology.callers[0]
            await w.bind(caller)
            expected_entries = {}
            for i in range(5):
                message = f"snapshot-match-{i}-" + "z" * 200
                appended = payload(await w.call(caller, "append_entry", message=message,
                                               status="success", format="structured_full"))
                assert appended["ok"] is True
                expected_entries[appended["id"]] = message
                excluded = payload(await w.call(caller, "append_entry", message=f"excluded-row-{i}",
                                               status="warn", format="structured_full"))
                assert excluded["ok"] is True
                assert excluded["id"] not in expected_entries
            before = await w.binding(caller)
            options = ({"filter": {"status": "success"}, "page_size": 2} if tool == "read_recent"
                       else {"message": "snapshot-match", "page_size": 2})
            selections = []
            for response_mode in dict.fromkeys((mode, "structured", "structured_full")):
                pages = []
                for page in range(1, 5):
                    result = payload(await w.call(caller, tool, format=response_mode, **options, page=page))
                    pages.append(result)
                    if response_mode in ("structured", "compact", "both"):
                        assert_receipt(result, limit=1024)
                    w.assert_call_observations(caller)
                assert_filtered_pages(pages, expected_entries)
                selections.append([[entry["id"] for entry in page["entries"]] for page in pages])
            assert all(selection == selections[0] for selection in selections), "receipt/full page-selection drift"
            assert await w.binding(caller) == before


# The execution adapter below delegates to the product's execute_tool_call and
# real tools/storage.  Its wrappers only record observations and inject gates.
# It is deliberately not an alternative resolver, dispatcher, or storage model.
@asynccontextmanager
async def world(tmp_path, monkeypatch, test_agent):
    from scribe_mcp import server
    from scribe_mcp.config.settings import settings
    from scribe_mcp.shared.execution_context import RouterContextManager
    from scribe_mcp.state.manager import StateManager
    topology = build_swarm_topology(tmp_path / "topology", agent_label=test_agent, seed=SEED)
    storage = required("scribe_mcp.storage.sqlite", "SQLiteStorage").SQLiteStorage(tmp_path / "runtime.db")
    await storage.setup()
    manager = StateManager(path=tmp_path / "state.json", storage_backend=storage)
    router = RouterContextManager(storage)
    config = replace(settings, project_root=tmp_path, default_repo_root=None,
                     trusted_repo_roots=topology.repositories, db_url=None, storage_backend="sqlite",
                     sqlite_path=tmp_path / "runtime.db", default_state_path=tmp_path / "state.json",
                     dev_plans_base=tmp_path / "plans", allow_network=False)
    with monkeypatch.context() as patch:
        from scribe_mcp.shared import execution_context
        patch.setattr(execution_context, "_APPLICATION_IDENTITIES", {})
        patch.setattr(execution_context, "_STDIO_IDENTITIES", {})
        patch.setattr(server, "storage_backend", storage)
        patch.setattr(server, "state_manager", manager)
        patch.setattr(server, "router_context_manager", router)
        patch.setattr(server, "get_execution_context", lambda: w.router.get_current())
        patch.setattr(server, "settings", config)
        # Settings references are dependency injection, never mocked behavior.
        for name in ("set_project", "append_entry", "get_project", "read_recent", "query_entries", "manage_docs"):
            module = importlib.import_module(f"scribe_mcp.tools.{name}")
        for module in tuple(sys.modules.values()):
            if (getattr(module, "__name__", "").startswith("scribe_mcp.")
                    and getattr(module, "settings", None) is settings):
                patch.setattr(module, "settings", config)
        w = ToolObservations(topology, storage, manager, router, config, test_agent, patch)
        try:
            for p in topology.projects:
                w.records[p.project_key] = await storage.upsert_project(name=p.name, repo_root=str(p.root),
                    progress_log_path=str(p.progress_log), docs_json=json.dumps({
                        "progress_log": str(p.progress_log),
                        "architecture": str(p.progress_log.parent / "ARCHITECTURE_GUIDE.md")}))
            yield w
        finally:
            await storage.close()


@dataclass
class CallObservation:
    reads: Counter = field(default_factory=Counter)
    contexts: list = field(default_factory=list)
    envelopes: list = field(default_factory=list)
    full_results: list = field(default_factory=list)
    binding_writes: int = 0
    persistent_write_batches: list = field(default_factory=list)


CURRENT_OBSERVATION = contextvars.ContextVar("sbr_test_observation", default=None)


class ToolObservations:
    def __init__(self, topology, storage, manager, router, config, agent, patch):
        self.topology, self.storage, self.manager, self.router = topology, storage, manager, router
        self.settings, self.agent = config, agent
        self.records, self.identities, self.sessions, self.bind_counts = {}, {}, {}, Counter()
        self.stable_sessions = {}
        self.initial_bindings, self.initial_sessions = {}, {}
        self.raw_timings, self.fault_timeline = [], []
        self.samples = {}
        self._patch = patch
        run_connection = storage._internals._run_with_connection
        def measured_connection(fn):
            def execute(conn):
                statements = []
                before = conn.total_changes
                conn.set_trace_callback(statements.append)
                try:
                    return fn(conn)
                finally:
                    conn.set_trace_callback(None)
                    sample = CURRENT_OBSERVATION.get()
                    changed_rows = conn.total_changes - before
                    if sample is not None and changed_rows:
                        sample.persistent_write_batches.append({"changed_rows": changed_rows,
                            "statements": tuple(sql for sql in statements if sql.lstrip().upper().startswith(
                                ("INSERT", "UPDATE", "DELETE", "REPLACE")))})
                    binding_dml = any("SESSION_PROJECTS" in sql.upper() and sql.lstrip().upper().startswith(
                        ("INSERT", "UPDATE", "DELETE", "REPLACE")) for sql in statements)
                    if sample is not None and binding_dml:
                        sample.binding_writes += changed_rows
            return run_connection(execute)
        patch.setattr(storage._internals, "_run_with_connection", measured_connection)
        for name in ("get_session_project", "fetch_project"):
            original = getattr(storage, name)
            async def counted(*args, _name=name, _original=original, **kwargs):
                sample = CURRENT_OBSERVATION.get()
                if sample is not None:
                    sample.reads[_name] += 1
                return await _original(*args, **kwargs)
            patch.setattr(storage, name, counted)
        timing = importlib.import_module("scribe_mcp.runtime_timing_envelope")
        if hasattr(timing, "CallTimingRecorderV2"):
            finalize = timing.CallTimingRecorderV2.finalize
            def captured_envelope(recorder, **kwargs):
                result = finalize(recorder, **kwargs)
                sample = CURRENT_OBSERVATION.get()
                if sample is not None:
                    sample.envelopes.append(result)
                return result
            patch.setattr(timing.CallTimingRecorderV2, "finalize", captured_envelope)
        from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
        prepare = LoggingToolMixin.prepare_context
        async def captured_context(helper, *args, **kwargs):
            result = await prepare(helper, *args, **kwargs)
            sample = CURRENT_OBSERVATION.get()
            if sample is not None:
                sample.contexts.append(getattr(result, "resolved_request_context", None))
            return result
        captured_context.__signature__ = inspect.signature(prepare)
        patch.setattr(LoggingToolMixin, "prepare_context", captured_context)
        from scribe_mcp.utils.formatters.dispatcher import FormatterDispatcher
        finalize_response = FormatterDispatcher.finalize_tool_response
        async def captured_response(formatter, *args, **kwargs):
            sample = CURRENT_OBSERVATION.get()
            if sample is not None:
                sample.contexts.append(kwargs.get("resolved_request_context"))
                sample.full_results.append(kwargs.get("data", args[0] if args else {}))
            return await finalize_response(formatter, *args, **kwargs)
        captured_response.__signature__ = inspect.signature(finalize_response)
        patch.setattr(FormatterDispatcher, "finalize_tool_response", captured_response)

    def project(self, project):
        return self.records[project.project_key]

    def identity(self, caller):
        if caller.caller_id not in self.identities:
            from scribe_mcp.mcp_adapter import ProtocolEra
            from scribe_mcp.shared.execution_context import resolve_application_identity
            self.identities[caller.caller_id] = resolve_application_identity(principal_id=self.agent,
                protocol_era=ProtocolEra.MODERN, transport="streamable-http", supplied_handle=None,
                connection_id=caller.caller_id)
        return self.identities[caller.caller_id]

    async def call(self, caller, tool_name, *, verified=True, **arguments):
        from scribe_mcp.shared.tool_runtime import execute_tool_call, resolve_context_authoritative_session_key
        identity = self.identity(caller)
        app = SimpleNamespace(request_context=SimpleNamespace(application_identity=identity,
            protocol_era=identity.protocol_era, principal_id=identity.principal_id,
            transport=identity.transport, application_handle=identity.application_handle,
            request=SimpleNamespace(headers={}), meta=None))
        if not verified:
            app = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers={}), meta=None))
        function = getattr(importlib.import_module(f"scribe_mcp.tools.{tool_name}"), tool_name)
        sample = CallObservation()
        async def observed(**kwargs):
            context = self.router.get_current()
            sample.contexts.append(context.resolved_request_context)
            self.sessions[caller.caller_id] = resolve_context_authoritative_session_key(context)
            self.stable_sessions[caller.caller_id] = context.stable_session_id or context.session_id
            return await function(**kwargs)
        # Preserve the real tool signature for the runtime's argument validation.
        observed.__signature__ = inspect.signature(function)
        token = CURRENT_OBSERVATION.set(sample)
        try:
            return await execute_tool_call(name=tool_name, arguments={"agent": self.agent, "format": "structured"} | arguments,
                kwargs={}, registry={tool_name: observed}, app=app, storage_backend=self.storage, settings=self.settings,
                state_manager=self.manager, router_context_manager=self.router, sentinel_only=set(),
                sentinel_allowed={"set_project"}, log_scope_violation_cb=lambda *_a, **_k: None)
        finally:
            CURRENT_OBSERVATION.reset(token)
            self.samples[caller.caller_id] = sample
            self.raw_timings.extend(copy.deepcopy(sample.envelopes))

    async def bind(self, caller, *, project=None, **options):
        p = project or caller.default
        self.bind_counts[caller.caller_id] += 1
        result = await self.call(caller, "set_project", name=p.name, root=str(p.root), **options)
        if caller.caller_id in self.sessions:
            record = await self.binding(caller)
            if record is not None:
                self.initial_bindings.setdefault(caller.caller_id, record)
                self.initial_sessions.setdefault(caller.caller_id, self.stable_sessions[caller.caller_id])
        return result

    async def binding(self, caller):
        return await self.storage.get_session_project(self.sessions[caller.caller_id])

    async def snapshot(self):
        files = {str(p.relative_to(self.topology.repositories[0].parent)): p.read_bytes()
                 for root in self.topology.repositories for p in root.rglob("*") if p.is_file()}
        return {"database": await database_snapshot(self.storage), "files": files,
                "recents": tuple(self.manager._recent_projects_cache),
                "defaults": copy.deepcopy(self.manager._session_projects_cache),
                "router_defaults": dict(self.router._session_projects),
                "project_cache": copy.deepcopy(self.manager._projects_cache),
                "agent_cache": copy.deepcopy(self.manager._agent_state_cache),
                "session_modes": dict(self.manager._session_modes_cache),
                "router_transports": dict(self.router._transport_sessions),
                "router_agent_sessions": dict(self.router._stable_agent_sessions)}

    def assert_call_observations(self, caller):
        sample = self.samples[caller.caller_id]
        assert sample.reads["get_session_project"] <= 1
        assert sample.reads["fetch_project"] <= 1
        assert len(sample.contexts) >= 3, "entry, helper and formatter must consume C-11"
        assert sample.contexts[0] is not None
        assert all(context is sample.contexts[0] for context in sample.contexts)
        assert len(sample.envelopes) == 1
        assert sample.envelopes[0]["correlation_id"] == sample.contexts[0].correlation_id
        assert sample.envelopes[0]["accounted_ratio"] >= 0.95

    async def bind_storage(self, caller):
        """Resolver tests consume C-01 without calling set_project/runtime."""
        sqlite_contract()
        key = self.identity(caller).identity_key
        await self.storage.upsert_session(session_id=key, agent_id=self.agent,
            repo_root=str(caller.default.root), mode="project")
        self.sessions[caller.caller_id] = key
        return await self.storage.set_session_project(key, project_key=self.project(caller.default).project_key)

    async def assert_negative(self, caller, code):
        c = required("scribe_mcp.shared.execution_context", "ProjectTargetV1")
        resolver = resolver_contract()
        if caller.caller_id not in self.sessions and code not in ("SCRIBE_BINDING_MISSING", "SCRIBE_CALLER_SESSION_UNVERIFIED"):
            await self.bind_storage(caller)
        target = {"SCRIBE_PROJECT_AMBIGUOUS": c.ProjectTargetV1(project="shared"),
                  "SCRIBE_PROJECT_NOT_FOUND": c.ProjectTargetV1(project="absent"),
                  "SCRIBE_PROJECT_ROOT_MISMATCH": c.ProjectTargetV1(project_key=self.project(caller.default).project_key,
                        project=caller.default.name, repo_root=str(caller.cross_repo.root)),
                  "SCRIBE_BINDING_MISSING": None, "SCRIBE_CALLER_SESSION_UNVERIFIED": None}[code]
        if code == "SCRIBE_BINDING_MISSING":
            fresh = replace(caller, caller_id="unbound-" + caller.caller_id)
            key = self.identity(fresh).identity_key
            await self.storage.upsert_session(session_id=key, agent_id=self.agent,
                repo_root=str(caller.default.root), mode="project")
        else:
            key = "" if code == "SCRIBE_CALLER_SESSION_UNVERIFIED" else self.sessions[caller.caller_id]
        before = await self.snapshot()
        with pytest.raises(resolver.ProjectResolutionError) as error:
            await resolver.resolve_project_target(key, target)
        assert error.value.error_code == code
        assert await self.snapshot() == before


@pytest.mark.asyncio
async def test_delayed_second_explicit_write_preserves_default_and_generation(tmp_path, monkeypatch, test_agent):
    await TestSBRBindingReceipt().test_delayed_second_write_preserves_generation(tmp_path, monkeypatch, test_agent)


@pytest.mark.asyncio
async def test_32_same_label_sessions_execute_one_bind_and_100_mixed_calls_each(tmp_path, monkeypatch, test_agent):
    resolver_contract()
    timing_contract()
    get_contract()
    read_contract()
    from scribe_mcp.shared import execution_context
    identity_baseline = dict(execution_context._APPLICATION_IDENTITIES)
    tasks_baseline = asyncio.all_tasks()
    async with world(tmp_path, monkeypatch, test_agent) as w:
        expected, observed = [], []
        for caller in w.topology.callers:
            assert payload(await w.bind(caller))["ok"] is True
        assert len(set(w.sessions.values())) == 32
        # One operation from each caller per round, without serializing projects.
        schedules = {c.caller_id: build_mixed_schedule(c, seed=SEED) for c in w.topology.callers}
        for index in range(100):
            await asyncio.gather(*(execute_corpus_operation(w, caller, schedules[caller.caller_id][index],
                expected, observed) for caller in w.topology.callers))
        source_revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
            check=True, text=True, capture_output=True).stdout.strip()
    result = reconcile_exact_effects(expected, observed, metadata=SwarmRunMetadata(
        source_revision=source_revision, seed=SEED, topology=w.topology.as_json_dict(),
        set_project_count=w.bind_counts,
        timing_histograms={"raw_envelopes": w.raw_timings}, fault_timeline=w.fault_timeline,
        teardown_counts={"tasks": len(asyncio.all_tasks() - tasks_baseline),
            "storage_handles": int(w.storage._pool is not None),
            "registries": int(execution_context._APPLICATION_IDENTITIES != identity_baseline),
            "temporary_files": sum(1 for root in w.topology.repositories for _ in root.rglob("*.tmp"))}))
    assert len(expected) == len(observed) == 3200
    assert result.verdict == "PASS", result.as_json_dict()


async def execute_corpus_operation(w, caller, op, expected, observed):
    """Exercise the corpus through real public tools and read back actual effects."""
    before = await w.binding(caller)
    initial = w.initial_bindings[caller.caller_id]
    assert before == initial, "ambient default or generation drifted before the operation"
    target = caller.same_repo if op.kind == "explicit_same_repo" else caller.cross_repo if op.kind == "explicit_cross_repo" else caller.default
    project = w.project(target)
    options = {"project": project.name, "project_key": project.project_key, "repo_root": project.repo_root} if op.explicit_project_key else {}
    if op.kind == "negative":
        # These are real rejected tool calls, with no rebind hidden in the mix.
        code = op.expected_result_code
        if code == "SCRIBE_BINDING_MISSING":
            fresh = replace(caller, caller_id="unbound-" + caller.caller_id)
            result = await w.call(fresh, "append_entry", message=op.operation_id)
            sample = w.samples[fresh.caller_id]
        elif code == "SCRIBE_CALLER_SESSION_UNVERIFIED":
            result = await w.call(caller, "append_entry", verified=False, message=op.operation_id)
            sample = w.samples[caller.caller_id]
        else:
            selectors = {"SCRIBE_PROJECT_AMBIGUOUS": {"project": "shared"},
                "SCRIBE_PROJECT_NOT_FOUND": {"project": "absent"},
                "SCRIBE_PROJECT_ROOT_MISMATCH": {"project_key": before.project_key,
                    "project": caller.default.name, "repo_root": str(caller.cross_repo.root)}}[code]
            result = await w.call(caller, "append_entry", message=op.operation_id, **selectors)
            sample = w.samples[caller.caller_id]
        assert_error(result, code)
        w.fault_timeline.append({"operation_id": op.operation_id, "caller_id": caller.caller_id,
                                 "result_code": payload(result)["error_code"]})
        assert all(op.operation_id not in p.progress_log.read_text() for p in w.topology.projects)
        code, effect, fingerprint = payload(result)["error_code"], "none", op.mutation_fingerprint
    elif op.kind == "reconnect":
        from scribe_mcp.shared.execution_context import RouterContextManager
        w.router = RouterContextManager(w.storage)
        w.manager._session_projects_cache.clear()
        result = payload(await w.call(caller, "get_project"))
        assert result["ok"] is True
        code, effect, fingerprint = "OK", "none", op.mutation_fingerprint
    elif op.kind == "read":
        result = payload(await w.call(caller, ("get_project", "read_recent", "query_entries")[op.ordinal % 3]))
        assert result["ok"] is True
        code, effect, fingerprint = "OK", "none", op.mutation_fingerprint
    elif op.kind == "document":
        result = payload(await w.call(caller, "manage_docs", action="append", doc="architecture", content=op.operation_id))
        assert result["ok"] is True
        text = (target.progress_log.parent / "ARCHITECTURE_GUIDE.md").read_text()
        assert text.count(op.operation_id) == 1
        assert all(op.operation_id not in (p.progress_log.parent / "ARCHITECTURE_GUIDE.md").read_text()
                   for p in w.topology.projects if p != target)
        start = text.index(op.operation_id)
        fingerprint = hashlib.sha256(text[start:start + len(op.operation_id)].encode()).hexdigest()
        code, effect = "OK", "document"
    else:
        result = payload(await w.call(caller, "append_entry", message=op.operation_id, **options))
        assert result["ok"] is True
        text = target.progress_log.read_text()
        assert text.count(op.operation_id) == 1
        assert all(op.operation_id not in p.progress_log.read_text() for p in w.topology.projects if p != target)
        start = text.index(op.operation_id)
        fingerprint = hashlib.sha256(text[start:start + len(op.operation_id)].encode()).hexdigest()
        code, effect = "OK", "log"
    after = await w.binding(caller)
    if op.kind != "negative":
        sample = w.samples[caller.caller_id]
        w.assert_call_observations(caller)
    identity = w.identity(caller)
    record = ExpectedEffect("run", op.operation_id, caller.caller_id,
        hashlib.sha256(identity.identity_key.encode()).hexdigest(),
        w.initial_sessions[caller.caller_id], initial.project_key,
        project.project_key if op.explicit_project_key else None, project.project_key,
        op.mutation_fingerprint, op.expected_effect, op.expected_result_code, before.binding_generation)
    expected.append(record)
    actual_contexts = [c for c in sample.contexts if c is not None]
    actual_target = actual_contexts[0].resolved_target.project_key if actual_contexts else before.project_key
    observed.append(observation(record, target_project_key=actual_target, mutation_fingerprint=fingerprint,
        application_id=actual_contexts[0].caller_session_key_hash if actual_contexts else record.application_id,
        stable_session_id=w.stable_sessions[caller.caller_id],
        effect=effect, result_code=code, default_after=after.project_key, generation_after=after.binding_generation,
        binding_reads=sample.reads["get_session_project"], project_reads=sample.reads["fetch_project"],
        context_count=len({id(c) for c in actual_contexts}), timing_envelope_count=len(sample.envelopes),
        accounted_ratio=min((e["accounted_ratio"] for e in sample.envelopes), default=0)))


@pytest.mark.asyncio
async def test_reconnect_new_handle_and_single_caller_cleanup_are_isolated(tmp_path, monkeypatch, test_agent):
    resolver_contract()
    async with world(tmp_path, monkeypatch, test_agent) as w:
        for caller in w.topology.callers:
            await w.bind(caller)
        before = [await w.binding(c) for c in w.topology.callers]
        from scribe_mcp.shared.execution_context import RouterContextManager
        first = w.topology.callers[0]
        w.router = RouterContextManager(w.storage)
        w.manager._session_projects_cache.clear()
        assert payload(await w.call(first, "get_project"))["ok"] is True
        assert await w.binding(first) == before[0]
        fresh = replace(first, caller_id="fresh-handle")
        assert_error(await w.call(fresh, "get_project"), "SCRIBE_BINDING_MISSING")
        await w.router.cleanup_session(w.sessions[first.caller_id])
        for caller, record in zip(w.topology.callers[1:], before[1:]):
            assert await w.binding(caller) == record


@pytest.mark.parametrize(("blocked", "peer"), [("read_recent", "append_entry"), ("append_entry", "manage_docs"), ("get_project", "append_entry")])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.asyncio
async def test_unrelated_repositories_overlap_without_global_head_of_line_blocking(tmp_path, monkeypatch, test_agent, blocked, peer, reverse):
    resolver_contract()
    async with world(tmp_path, monkeypatch, test_agent) as w:
        a, b = w.topology.callers[0], w.topology.callers[8]
        if reverse:
            a, b = b, a
        await w.bind(a)
        await w.bind(b)
        gate = CausalGate()
        original = w.storage.fetch_project
        async def held(*args, **kwargs):
            record = await original(*args, **kwargs)
            if record and record.project_key == w.project(a.default).project_key:
                await gate.hold()
            return record
        with monkeypatch.context() as patch:
            patch.setattr(w.storage, "fetch_project", held)
            arguments = {"message": "blocked"} if blocked == "append_entry" else {}
            task = asyncio.create_task(w.call(a, blocked, **arguments))
            try:
                await asyncio.wait_for(gate.entered.wait(), 2)
                options = {"action": "append", "doc": "architecture", "content": "peer-document"} if peer == "manage_docs" else {"message": "peer-write"}
                result = await asyncio.wait_for(w.call(b, peer, **options), 2)
                assert payload(result)["ok"] is True
                assert not gate.release.is_set() and not task.done()
            finally:
                gate.release.set()
                await asyncio.wait_for(task, 2)


def test_swarm_exact_effects_and_c14_serialization_are_deterministic():
    TestSBRHarness().test_swarm_exact_effects_and_c14_serialization_are_deterministic()


@pytest.mark.parametrize("generation", [0, -1, True, 1.5])
def test_session_binding_record_v2_rejects_invalid_generation_and_naive_timestamp(tmp_path, generation):
    TestSBRSQLiteBinding().test_session_binding_record_v2_rejects_invalid_generation_and_naive_timestamp(tmp_path, generation)


@pytest.mark.asyncio
async def test_binding_contract_generation_and_zero_write_semantics(tmp_path, test_agent):
    await TestSBRSQLiteBinding().test_binding_contract_generation_and_zero_write_semantics(tmp_path, test_agent)


@pytest.mark.asyncio
async def test_sqlite_reliability_schema_upgrades_legacy_binding_without_default_drift(tmp_path, test_agent):
    """Reopen a real pre-C05 table, retaining target, timestamp and generation."""
    Storage = required("scribe_mcp.storage.sqlite", "SQLiteStorage").SQLiteStorage
    path = tmp_path / "legacy.db"
    root = tmp_path / "repository"
    root.mkdir()
    store = Storage(path)
    await store.setup()
    try:
        project = await store.upsert_project(name="legacy-project", repo_root=str(root),
            progress_log_path=str(root / "PROGRESS_LOG.md"))
        await store.upsert_session(session_id="legacy-session", agent_id=test_agent,
            repo_root=str(root), mode="project")
    finally:
        await store.close()
    timestamp = "2026-09-27T05:57:00+00:00"
    # Only the disposable table is replaced to reproduce the historical input.
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TABLE session_projects")
        conn.execute("CREATE TABLE session_projects (session_id TEXT PRIMARY KEY, project_name TEXT, updated_at TEXT NOT NULL)")
        conn.execute("INSERT INTO session_projects VALUES (?, ?, ?)", ("legacy-session", "legacy-project", timestamp))
    for _ in range(2):
        reopened = Storage(path)
        await reopened.setup()
        try:
            result = await reopened.get_session_project("legacy-session")
            assert result.project_key == project.project_key
            assert result.project_name == "legacy-project"
            assert result.canonical_repo_root == str(root)
            assert result.binding_generation == 1
            assert result.updated_at == datetime.fromisoformat(timestamp)
            rows = await reopened._fetchall("SELECT * FROM session_projects", ())
            assert len(rows) == 1
            assert await reopened._fetchall("PRAGMA foreign_key_check", ()) == []
        finally:
            await reopened.close()
