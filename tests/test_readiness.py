from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from scribe_mcp import readiness
from scribe_mcp.readiness import (
    ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL,
    ACCEPTED_SELECTOR_READBACK_STATUS_LABEL,
    BLOCKED_CLEANUP_FAILED_REDACTED,
    BLOCKED_CONNECTIVITY_FAILED_REDACTED,
    BLOCKED_PRIVATE_INPUT_UNSAFE,
    BLOCKED_ROUNDTRIP_FAILED_REDACTED,
    BLOCKED_SELECTOR_READBACK_UNSAFE,
    BLOCKED_STORAGE_SETUP_REQUIRED,
    BLOCKED_TARGET_CLASS_UNSAFE,
    PASSED_CLEANUP_LABEL,
    PASSED_CONNECTIVITY_LABEL,
    PASSED_IDEMPOTENCY_LABEL,
    PASSED_ROUNDTRIP_LABEL,
    STORAGE_SETUP_NOT_RUN_LABEL,
    build_local_postgres_readiness_roundtrip_labels,
    build_readiness_summary,
    collect_managed_doc_quality_state,
    scribe_local_postgres_readiness_roundtrip_preflight,
)

EXPECTED_ROUNDTRIP_KEYS = {
    "command_class_label",
    "target_class_label",
    "selected_context_readback_status_label",
    "connectivity_status_label",
    "storage_setup_status_label",
    "scribe_roundtrip_label",
    "scribe_idempotency_label",
    "cleanup_status_label",
    "public_redaction_policy_label",
    "private_values_recorded",
    "train_local_db_g_technical_pass_candidate_label",
    "train_local_db_g_technical_pass_earned",
    "train_02g2_b_routing_authorized",
}

PUBLIC_SAFE_HANDLE_ID = "opaque_handle_30ay_local_test"
PUBLIC_SAFE_NAMESPACE = "train_30ay_public_safe_proof_namespace"


class FakeRoundtripRunner:
    def __init__(
        self,
        *,
        connect_label: str = PASSED_CONNECTIVITY_LABEL,
        first_roundtrip_label: str = PASSED_ROUNDTRIP_LABEL,
        second_roundtrip_label: str = PASSED_ROUNDTRIP_LABEL,
        cleanup_label: str = PASSED_CLEANUP_LABEL,
        fail_connect: bool = False,
        fail_first_roundtrip: bool = False,
        fail_second_roundtrip: bool = False,
        fail_cleanup: bool = False,
    ) -> None:
        self.connect_label = connect_label
        self.first_roundtrip_label = first_roundtrip_label
        self.second_roundtrip_label = second_roundtrip_label
        self.cleanup_label = cleanup_label
        self.fail_connect = fail_connect
        self.fail_first_roundtrip = fail_first_roundtrip
        self.fail_second_roundtrip = fail_second_roundtrip
        self.fail_cleanup = fail_cleanup
        self.connect_calls: list[str] = []
        self.roundtrip_calls: list[str] = []
        self.cleanup_calls: list[str] = []
        self.residue: set[str] = set()

    async def connect(self, private_target_handle_id: str) -> str:
        self.connect_calls.append(private_target_handle_id)
        if self.fail_connect:
            raise RuntimeError("raw connection detail must not leak")
        return self.connect_label

    async def roundtrip(self, proof_namespace_label: str) -> str:
        self.roundtrip_calls.append(proof_namespace_label)
        self.residue.add(proof_namespace_label)
        if self.fail_first_roundtrip and len(self.roundtrip_calls) == 1:
            raise RuntimeError("raw roundtrip detail must not leak")
        if self.fail_second_roundtrip and len(self.roundtrip_calls) == 2:
            raise RuntimeError("raw idempotency detail must not leak")
        if len(self.roundtrip_calls) == 1:
            return self.first_roundtrip_label
        return self.second_roundtrip_label

    async def cleanup(self, proof_namespace_label: str) -> str:
        self.cleanup_calls.append(proof_namespace_label)
        if self.fail_cleanup:
            raise RuntimeError("raw cleanup detail must not leak")
        self.residue.discard(proof_namespace_label)
        return self.cleanup_label


def _safe_kwargs() -> dict[str, str]:
    return {
        "private_target_handle_id": PUBLIC_SAFE_HANDLE_ID,
        "target_class_label": ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL,
        "selected_context_readback_status_label": ACCEPTED_SELECTOR_READBACK_STATUS_LABEL,
        "proof_namespace_label": PUBLIC_SAFE_NAMESPACE,
    }


def _assert_public_payload(payload: dict[str, str | bool]) -> None:
    assert set(payload) == EXPECTED_ROUNDTRIP_KEYS
    assert payload["private_values_recorded"] is False
    assert payload["train_local_db_g_technical_pass_candidate_label"] is False
    assert payload["train_local_db_g_technical_pass_earned"] is False
    assert payload["train_02g2_b_routing_authorized"] is False
    for value in payload.values():
        assert isinstance(value, (str, bool))
        if isinstance(value, str):
            assert "connection detail" not in value
            assert "opaque_handle" not in value


def test_readiness_preserves_scf_codes_and_counts(tmp_path: Path) -> None:
    checklist = tmp_path / "CHECKLIST.md"
    checklist.write_text("---\nstatus: ready\n---\n\n# Checklist\n\n- [ ] [TODO fill this]", encoding="utf-8")

    project = {
        "docs": {"checklist": str(checklist)},
        "name": "demo",
        "root": str(tmp_path),
    }
    quality = collect_managed_doc_quality_state(project)

    assert quality["readiness_blocker_count"] >= 1
    doc = quality["documents"][0]
    assert "SCF_FRONTMATTER_MISMATCH" in doc["warning_codes"]
    assert "SCF_FRONTMATTER_MISMATCH" in doc["readiness_blocker_codes"]
    assert "SCF_FRONTMATTER_MISMATCH" in doc["blocking_warning_codes"]
    assert quality["warning_counts_by_code"]["SCF_FRONTMATTER_MISMATCH"] >= 1
    assert quality["readiness_blocker_counts_by_code"]["SCF_FRONTMATTER_MISMATCH"] >= 1
    assert any(w.get("code") == "SCF_FRONTMATTER_MISMATCH" for w in quality["warnings"])


def test_readiness_phase_scoping_does_not_force_false_failure() -> None:
    managed = {
        "status": "pass",
        "readiness_blocker_count": 0,
        "total_warning_count": 2,
        "documents": [
            {
                "doc_name": "phase_plan",
                "warning_codes": ["SCF_INDEX_STALE", "SCF_DOC_UNINDEXED"],
                "readiness_blocker_codes": [],
            }
        ],
    }
    summary = build_readiness_summary(current_phase="Phase 1", managed_doc_quality=managed, log_signals=[]).to_dict()
    assert summary["blocker_count"] == 0
    assert summary["warning_count"] == 2


def test_readiness_summary_counts_align_with_project_health_shape() -> None:
    managed = {
        "status": "blocked",
        "readiness_blocker_count": 2,
        "total_warning_count": 3,
        "documents": [],
    }
    signals = [{"code": "LOG_MISSING_PRIORITY", "blocking": False}]
    summary = build_readiness_summary(current_phase=None, managed_doc_quality=managed, log_signals=signals).to_dict()

    assert summary["managed_doc_quality"]["readiness_blocker_count"] == 2
    assert summary["log_friction"]["status"] == "advisory"
    assert summary["warning_count"] == 3
    assert summary["blocker_count"] == 2


def test_collect_managed_doc_quality_filters_future_phase_index_warning(tmp_path: Path, monkeypatch) -> None:
    phase_plan = tmp_path / "PHASE_PLAN.md"
    phase_plan.write_text(
        "---\nstatus: in_progress\n---\n\n"
        "## Phase 1 (In Progress)\n\n"
        "## Research Index\n\n"
        "- [ ] [RESEARCH_PHASE2.md](research/RESEARCH_PHASE2.md)\n",
        encoding="utf-8",
    )
    project = {
        "docs": {"phase_plan": str(phase_plan)},
        "name": "demo",
        "root": str(tmp_path),
        "current_phase": "Phase 1",
    }
    monkeypatch.setattr(
        readiness,
        "collect_managed_doc_quality_warnings",
        lambda **_: [
            {
                "code": "SCF_INDEX_STALE",
                "blocking": True,
                "excerpt": "phase 2 index entry missing",
            }
        ],
    )
    quality = collect_managed_doc_quality_state(project)
    doc = quality["documents"][0]
    assert "SCF_INDEX_STALE" in doc["warning_codes"]
    assert "SCF_INDEX_STALE" not in doc["readiness_blocker_codes"]


def test_readiness_includes_lifecycle_status_mismatch_as_blocker(tmp_path: Path) -> None:
    spec = tmp_path / "SPEC.md"
    spec.write_text("---\nstatus: draft\n---\n\nStatus: ready\n", encoding="utf-8")

    project = {
        "docs": {"spec": str(spec)},
        "name": "demo",
        "root": str(tmp_path),
    }
    quality = collect_managed_doc_quality_state(project)

    assert quality["readiness_blocker_count"] >= 1
    doc = quality["documents"][0]
    assert "SCF_LIFECYCLE_STATUS_MISMATCH" in doc["warning_codes"]
    assert "SCF_LIFECYCLE_STATUS_MISMATCH" in doc["readiness_blocker_codes"]


def test_collect_managed_doc_quality_state_caches_unchanged_doc_signatures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    architecture = tmp_path / "ARCHITECTURE_GUIDE.md"
    architecture.write_text("initial", encoding="utf-8")
    project = {
        "docs": {"architecture": str(architecture)},
        "name": "demo",
        "root": str(tmp_path),
    }
    calls: list[str] = []

    def _warnings(**kwargs: Any) -> list[dict[str, Any]]:
        calls.append(str(kwargs.get("text") or ""))
        return []

    readiness.clear_managed_doc_quality_state_cache()
    monkeypatch.setattr(readiness, "collect_managed_doc_quality_warnings", _warnings)

    first = collect_managed_doc_quality_state(project)
    first["documents"].append({"doc_name": "mutated-by-caller"})
    second = collect_managed_doc_quality_state(project)

    assert calls == ["initial"]
    assert second["documents"] == [
        {
            "doc_name": "architecture",
            "path": str(architecture),
            "warning_codes": [],
            "readiness_blocker_codes": [],
            "blocking_warning_codes": [],
        }
    ]


def test_collect_managed_doc_quality_state_invalidates_after_doc_signature_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checklist = tmp_path / "CHECKLIST.md"
    checklist.write_text("clean", encoding="utf-8")
    project: Mapping[str, Any] = {
        "docs": {"checklist": str(checklist)},
        "name": "demo",
        "root": str(tmp_path),
    }
    calls: list[str] = []

    def _warnings(**kwargs: Any) -> list[dict[str, Any]]:
        text = str(kwargs.get("text") or "")
        calls.append(text)
        if "blocked" not in text:
            return []
        return [
            {
                "code": "SCF_FRONTMATTER_MISMATCH",
                "severity": "critical",
                "blocking": True,
                "suggested_repair": "repair",
            }
        ]

    readiness.clear_managed_doc_quality_state_cache()
    monkeypatch.setattr(readiness, "collect_managed_doc_quality_warnings", _warnings)

    first = collect_managed_doc_quality_state(project)
    checklist.write_text("blocked and changed", encoding="utf-8")
    second = collect_managed_doc_quality_state(project)

    assert calls == ["clean", "blocked and changed"]
    assert first["status"] == "pass"
    assert second["status"] == "blocked"
    assert second["readiness_blocker_count"] == 1
    assert second["warning_counts_by_code"]["SCF_FRONTMATTER_MISMATCH"] == 1


def test_local_postgres_roundtrip_label_builder_emits_public_labels_only() -> None:
    payload = build_local_postgres_readiness_roundtrip_labels(
        target_class_label=ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL,
        selected_context_readback_status_label=ACCEPTED_SELECTOR_READBACK_STATUS_LABEL,
        connectivity_status_label=PASSED_CONNECTIVITY_LABEL,
        storage_setup_status_label=STORAGE_SETUP_NOT_RUN_LABEL,
        scribe_roundtrip_label=PASSED_ROUNDTRIP_LABEL,
        scribe_idempotency_label=PASSED_IDEMPOTENCY_LABEL,
        cleanup_status_label=PASSED_CLEANUP_LABEL,
    )

    _assert_public_payload(payload)
    assert payload["target_class_label"] == ACCEPTED_LOCAL_POSTGRES_TARGET_CLASS_LABEL
    assert payload["selected_context_readback_status_label"] == ACCEPTED_SELECTOR_READBACK_STATUS_LABEL
    assert payload["connectivity_status_label"] == PASSED_CONNECTIVITY_LABEL
    assert payload["storage_setup_status_label"] == STORAGE_SETUP_NOT_RUN_LABEL
    assert payload["scribe_roundtrip_label"] == PASSED_ROUNDTRIP_LABEL
    assert payload["scribe_idempotency_label"] == PASSED_IDEMPOTENCY_LABEL
    assert payload["cleanup_status_label"] == PASSED_CLEANUP_LABEL


@pytest.mark.asyncio
async def test_roundtrip_preflight_passes_with_fake_runner_and_cleans_residue() -> None:
    runner = FakeRoundtripRunner()

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())

    _assert_public_payload(payload)
    assert payload["connectivity_status_label"] == PASSED_CONNECTIVITY_LABEL
    assert payload["storage_setup_status_label"] == STORAGE_SETUP_NOT_RUN_LABEL
    assert payload["scribe_roundtrip_label"] == PASSED_ROUNDTRIP_LABEL
    assert payload["scribe_idempotency_label"] == PASSED_IDEMPOTENCY_LABEL
    assert payload["cleanup_status_label"] == PASSED_CLEANUP_LABEL
    assert runner.connect_calls == [PUBLIC_SAFE_HANDLE_ID]
    assert runner.roundtrip_calls == [PUBLIC_SAFE_NAMESPACE, PUBLIC_SAFE_NAMESPACE]
    assert runner.cleanup_calls == [PUBLIC_SAFE_NAMESPACE]
    assert runner.residue == set()


@pytest.mark.asyncio
async def test_roundtrip_preflight_fails_closed_for_missing_or_unsafe_target_labels() -> None:
    runner = FakeRoundtripRunner()

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=runner,
        **{**_safe_kwargs(), "target_class_label": ""},
    )

    assert payload["target_class_label"] == BLOCKED_TARGET_CLASS_UNSAFE
    assert payload["connectivity_status_label"] == BLOCKED_TARGET_CLASS_UNSAFE
    _assert_public_payload(payload)
    assert runner.connect_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_fails_closed_for_unsafe_selector_readback_label() -> None:
    runner = FakeRoundtripRunner()

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=runner,
        **{**_safe_kwargs(), "selected_context_readback_status_label": "blocked_active_runtime_dependent_selector"},
    )

    assert payload["selected_context_readback_status_label"] == BLOCKED_SELECTOR_READBACK_UNSAFE
    assert payload["connectivity_status_label"] == BLOCKED_SELECTOR_READBACK_UNSAFE
    _assert_public_payload(payload)
    assert runner.connect_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_rejects_raw_looking_private_handle_without_use() -> None:
    runner = FakeRoundtripRunner()

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=runner,
        **{**_safe_kwargs(), "private_target_handle_id": "host=local-user@127.0.0.1/app"},
    )

    assert payload["connectivity_status_label"] == BLOCKED_PRIVATE_INPUT_UNSAFE
    _assert_public_payload(payload)
    assert runner.connect_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_rejects_alternate_private_fields_without_use() -> None:
    runner = FakeRoundtripRunner()

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=runner,
        alternate_target_material="host=local",
        **_safe_kwargs(),
    )

    assert payload["connectivity_status_label"] == BLOCKED_PRIVATE_INPUT_UNSAFE
    _assert_public_payload(payload)
    assert runner.connect_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_blocks_when_storage_setup_is_required() -> None:
    runner = FakeRoundtripRunner(connect_label=BLOCKED_STORAGE_SETUP_REQUIRED)

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())

    assert payload["connectivity_status_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    assert payload["storage_setup_status_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    assert payload["scribe_roundtrip_label"] == BLOCKED_STORAGE_SETUP_REQUIRED
    _assert_public_payload(payload)
    assert runner.roundtrip_calls == []
    assert runner.cleanup_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_redacts_connectivity_failure() -> None:
    runner = FakeRoundtripRunner(fail_connect=True)

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())

    assert payload["connectivity_status_label"] == BLOCKED_CONNECTIVITY_FAILED_REDACTED
    _assert_public_payload(payload)
    assert runner.roundtrip_calls == []
    assert runner.cleanup_calls == []


@pytest.mark.asyncio
async def test_roundtrip_preflight_runs_cleanup_after_roundtrip_failure() -> None:
    runner = FakeRoundtripRunner(fail_first_roundtrip=True)

    payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())

    assert payload["scribe_roundtrip_label"] == BLOCKED_ROUNDTRIP_FAILED_REDACTED
    assert payload["scribe_idempotency_label"] == BLOCKED_ROUNDTRIP_FAILED_REDACTED
    assert payload["cleanup_status_label"] == PASSED_CLEANUP_LABEL
    _assert_public_payload(payload)
    assert runner.roundtrip_calls == [PUBLIC_SAFE_NAMESPACE]
    assert runner.cleanup_calls == [PUBLIC_SAFE_NAMESPACE]
    assert runner.residue == set()


@pytest.mark.asyncio
async def test_roundtrip_preflight_redacts_idempotency_and_cleanup_failures() -> None:
    idempotency_runner = FakeRoundtripRunner(fail_second_roundtrip=True)
    idempotency_payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=idempotency_runner,
        **_safe_kwargs(),
    )

    assert idempotency_payload["scribe_idempotency_label"] == BLOCKED_ROUNDTRIP_FAILED_REDACTED
    assert idempotency_payload["cleanup_status_label"] == PASSED_CLEANUP_LABEL
    _assert_public_payload(idempotency_payload)

    cleanup_runner = FakeRoundtripRunner(fail_cleanup=True)
    cleanup_payload = await scribe_local_postgres_readiness_roundtrip_preflight(
        runner=cleanup_runner,
        **_safe_kwargs(),
    )

    assert cleanup_payload["scribe_roundtrip_label"] == PASSED_ROUNDTRIP_LABEL
    assert cleanup_payload["scribe_idempotency_label"] == PASSED_IDEMPOTENCY_LABEL
    assert cleanup_payload["cleanup_status_label"] == BLOCKED_CLEANUP_FAILED_REDACTED
    _assert_public_payload(cleanup_payload)


@pytest.mark.asyncio
async def test_roundtrip_preflight_second_execution_is_idempotent_with_same_namespace() -> None:
    runner = FakeRoundtripRunner()

    first_payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())
    second_payload = await scribe_local_postgres_readiness_roundtrip_preflight(runner=runner, **_safe_kwargs())

    assert first_payload == second_payload
    assert runner.roundtrip_calls == [
        PUBLIC_SAFE_NAMESPACE,
        PUBLIC_SAFE_NAMESPACE,
        PUBLIC_SAFE_NAMESPACE,
        PUBLIC_SAFE_NAMESPACE,
    ]
    assert runner.cleanup_calls == [PUBLIC_SAFE_NAMESPACE, PUBLIC_SAFE_NAMESPACE]
    assert runner.residue == set()
