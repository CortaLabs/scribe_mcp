"""Closed public-contract tests for the explicit project-scoped reopen_case tool."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from collections import UserDict
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Dict

import pytest

from scribe_mcp.storage.models import CaseRegistryRecord
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.tools import sentinel_tools


EXPECTED_RESPONSE_FIELDS = {
    "ok": "bool",
    "mode": "project|sentinel|unresolved",
    "case_id": "str|null",
    "case_type": "bug|security|null",
    "partial": "bool",
    "failure_stage": "failure_stage|null",
    "error_code": "error_code|null",
    "message": "str",
    "changed": "bool|null",
    "reopened": "bool|null",
    "idempotent": "bool|null",
    "target_status": "str|null",
    "report_status": "str|null",
    "registry_status_before": "str|null",
    "registry_status_after": "str|null",
    "registry_mutation_attempted": "bool",
    "registry_readback_verified": "bool",
    "mutation_may_have_occurred": "bool",
    "requested_event_id": "str|null",
    "completed_event_id": "str|null",
    "case_scope": "object",
    "case_registry": "object",
    "warnings": "list[str]",
    "next_step": "str",
}
EXPECTED_TOP_LEVEL_KEYS = set(EXPECTED_RESPONSE_FIELDS)
EXPECTED_CASE_SCOPE_FIELDS = {
    "active_repo_verified": "bool",
    "active_project_verified": "bool",
}
EXPECTED_CASE_REGISTRY_FIELDS = {
    "record_found": "bool",
    "identity_verified": "bool",
}
EXPECTED_SUCCESS_MESSAGES = {
    "changed": "The case was reopened and independently verified.",
    "idempotent": (
        "The case was already at the requested open status; "
        "no registry mutation was performed."
    ),
}
EXPECTED_FAILURE_CONTRACT = {
    "CONTEXT_UNAVAILABLE": {
        "failure_stage": "context",
        "message": "The execution context could not be verified.",
        "next_step": "Retry from a bound project execution context.",
    },
    "PROJECT_MODE_REQUIRED": {
        "failure_stage": "context",
        "message": "The case reopen operation is available only in project mode.",
        "next_step": "Bind the target project and retry the same request.",
    },
    "INVALID_CASE_ID": {
        "failure_stage": "input",
        "message": "The case identifier is invalid.",
        "next_step": (
            "Provide a canonical BUG-YYYY-MM-DD-NNNN or SEC-YYYY-MM-DD-NNNN identifier."
        ),
    },
    "INVALID_REASON": {
        "failure_stage": "input",
        "message": "A non-empty reopen reason is required.",
        "next_step": "Provide a non-empty reason and retry.",
    },
    "INVALID_TARGET_STATUS": {
        "failure_stage": "input",
        "message": "The requested target status is not an allowed open status.",
        "next_step": "Choose a canonical open status and retry.",
    },
    "ACTIVE_SCOPE_UNAVAILABLE": {
        "failure_stage": "scope",
        "message": "The active repository and project scope could not be verified.",
        "next_step": "Bind the target project scope and retry.",
    },
    "CASE_NOT_FOUND": {
        "failure_stage": "registry_lookup",
        "message": "The requested case was not found in the active scope.",
        "next_step": (
            "Verify the case identifier and active project scope, then retry."
        ),
    },
    "CASE_SCOPE_MISMATCH": {
        "failure_stage": "registry_identity",
        "message": "The case does not belong to the verified active scope.",
        "next_step": "Bind the case's owning project scope and retry.",
    },
    "REGISTRY_IDENTITY_MISMATCH": {
        "failure_stage": "registry_identity",
        "message": ("The case registry identity does not match the requested case."),
        "next_step": ("Repair the governed registry/report binding before retrying."),
    },
    "REPORT_UNAVAILABLE": {
        "failure_stage": "report_access",
        "message": "The governed case report is unavailable.",
        "next_step": ("Restore the governed report at its registered path and retry."),
    },
    "REPORT_OUTSIDE_SCOPE": {
        "failure_stage": "report_access",
        "message": "The governed case report is outside the active repository.",
        "next_step": "Repair the registered report path before retrying.",
    },
    "REPORT_READ_FAILED": {
        "failure_stage": "report_access",
        "message": "The governed case report could not be read.",
        "next_step": "Restore a readable UTF-8 governed report and retry.",
    },
    "REPORT_ID_HEADER_MISSING": {
        "failure_stage": "report_identity",
        "message": (
            "The governed report is missing its required case identifier header."
        ),
        "next_step": "Repair the governed report identity header and retry.",
    },
    "REPORT_ID_HEADER_DUPLICATE": {
        "failure_stage": "report_identity",
        "message": ("The governed report contains duplicate case identifier headers."),
        "next_step": "Repair the governed report identity header and retry.",
    },
    "REPORT_ID_HEADER_MALFORMED": {
        "failure_stage": "report_identity",
        "message": "The governed report case identifier header is malformed.",
        "next_step": "Repair the governed report identity header and retry.",
    },
    "REPORT_ID_HEADER_TYPE_MISMATCH": {
        "failure_stage": "report_identity",
        "message": (
            "The governed report case identifier header does not match "
            "the registered case type."
        ),
        "next_step": "Repair the governed report identity header and retry.",
    },
    "REPORT_ID_MISMATCH": {
        "failure_stage": "report_identity",
        "message": (
            "The governed report case identifier does not match the requested case."
        ),
        "next_step": "Repair the governed report identity header and retry.",
    },
    "REPORT_STATUS_MISSING": {
        "failure_stage": "report_status",
        "message": "The governed report is missing a Status field.",
        "next_step": "Repair the governed report Status fields and retry.",
    },
    "REPORT_STATUS_CONFLICT": {
        "failure_stage": "report_status",
        "message": "The governed report contains conflicting Status fields.",
        "next_step": "Repair the governed report Status fields and retry.",
    },
    "REPORT_STATUS_INVALID": {
        "failure_stage": "report_status",
        "message": "The governed report contains an invalid Status value.",
        "next_step": "Repair the governed report Status fields and retry.",
    },
    "REPORT_STATUS_MISMATCH": {
        "failure_stage": "report_status",
        "message": (
            "The governed report Status does not match the requested target status."
        ),
        "next_step": "Repair the governed report Status fields and retry.",
    },
    "REGISTRY_STATUS_INVALID": {
        "failure_stage": "transition",
        "message": "The registry contains an invalid lifecycle status.",
        "next_step": "Repair the governed registry status before retrying.",
    },
    "TRANSITION_NOT_ALLOWED": {
        "failure_stage": "transition",
        "message": "The requested case transition is not allowed.",
        "next_step": (
            "Use reopen_case only for terminal-to-open recovery "
            "or an exact already-open retry."
        ),
    },
    "AUDIT_REQUEST_FAILED": {
        "failure_stage": "audit_requested",
        "message": (
            "The reopen request audit event was not recorded; "
            "no registry mutation was attempted."
        ),
        "next_step": "Restore audit delivery and retry the same request.",
    },
    "REGISTRY_PAYLOAD_BUILD_FAILED": {
        "failure_stage": "registry_mutation",
        "message": (
            "The registry update could not be prepared; "
            "no registry mutation was attempted."
        ),
        "next_step": (
            "Repair the registry record contract and retry the same request."
        ),
    },
    "REGISTRY_UPSERT_FAILED": {
        "failure_stage": "registry_mutation",
        "message": (
            "The registry update did not complete with independently verified state."
        ),
        "next_step": (
            "Retry the same request; the idempotent path will reconcile "
            "any committed transition and create a new audit pair."
        ),
    },
    "REGISTRY_READBACK_FAILED": {
        "failure_stage": "registry_readback",
        "message": "The registry state could not be independently verified.",
        "next_step": (
            "Retry the same request; the idempotent path will reconcile "
            "any committed transition and create a new audit pair."
        ),
    },
    "REGISTRY_READBACK_MISMATCH": {
        "failure_stage": "registry_readback",
        "message": (
            "The independently read registry state did not match the reopen contract."
        ),
        "next_step": (
            "Retry the same request; the idempotent path will reconcile "
            "any committed transition and create a new audit pair."
        ),
    },
    "AUDIT_COMPLETION_FAILED": {
        "failure_stage": "audit_completed",
        "message": (
            "The registry branch completed, but the completion audit "
            "event was not recorded."
        ),
        "next_step": (
            "Restore audit delivery and retry the same request "
            "to create a complete audit pair."
        ),
    },
}
EXPECTED_DESCRIPTOR_SHA256 = (
    "a1ac84d87a81eb308ccca9f9261269721661bf44bf87a450943b7301d42520e8"
)
_DEFAULT_READBACK = object()
_MISSING_CONTEXT = object()


REGISTRY_ROW_FIELDS = (
    "case_id",
    "case_type",
    "project_name",
    "repo_root",
    "repo_id",
    "project_key",
    "doc_type",
    "doc_name",
    "doc_path",
    "title",
    "status",
    "severity",
    "source_tool",
    "metadata",
    "created_at",
    "updated_at",
)
REQUIRED_REGISTRY_ROW_FIELDS = REGISTRY_ROW_FIELDS[:9]
OPTIONAL_REGISTRY_ROW_FIELDS = REGISTRY_ROW_FIELDS[9:]


def _record_mapping(record: CaseRegistryRecord) -> dict[str, object]:
    return {
        field: copy.deepcopy(getattr(record, field)) for field in REGISTRY_ROW_FIELDS
    }


class _TripwireMapping(Mapping[object, object]):
    def __init__(
        self,
        data: dict[object, object],
        *,
        iter_keys: tuple[object, ...] | None = None,
        fail_getitem: object | None = None,
        raise_iter: bool = False,
        raise_len: bool = False,
        events: list[tuple[str, object]] | None = None,
    ) -> None:
        self._data = dict(data)
        self._iter_keys = iter_keys if iter_keys is not None else tuple(data)
        self._fail_getitem = fail_getitem
        self._raise_iter = raise_iter
        self._raise_len = raise_len
        self._events = events
        self.iter_calls = 0
        self.getitem_calls: list[object] = []
        self.len_calls = 0
        self.str_calls = 0
        self.repr_calls = 0

    def __getitem__(self, key: object) -> object:
        self.getitem_calls.append(key)
        if self._events is not None:
            self._events.append(("getitem", key))
        if key == self._fail_getitem:
            raise RuntimeError(
                "postgresql://private:secret@db.invalid/scribe Bearer private-token"
            )
        return self._data[key]

    def __iter__(self) -> Iterator[object]:
        self.iter_calls += 1
        if self._events is not None:
            self._events.append(("iter", self.iter_calls))
        if self._raise_iter:
            raise RuntimeError("api_key=private-iterator-key")
        return iter(self._iter_keys)

    def __len__(self) -> int:
        self.len_calls += 1
        if self._raise_len:
            raise RuntimeError("password=private-length-secret")
        return len(self._iter_keys)

    def __str__(self) -> str:
        self.str_calls += 1
        raise RuntimeError("private mapping __str__ must not run")

    def __repr__(self) -> str:
        self.repr_calls += 1
        raise RuntimeError("private mapping __repr__ must not run")


class _ExplosiveDictValue:
    def __init__(self) -> None:
        self.deepcopy_calls = 0
        self.str_calls = 0

    def __deepcopy__(self, memo: dict[int, object]) -> object:
        del memo
        self.deepcopy_calls += 1
        raise RuntimeError("Authorization: Bearer private-deepcopy-token")

    def __str__(self) -> str:
        self.str_calls += 1
        raise RuntimeError("private nested __str__ must not run")


class _ExplosiveString(str):
    strip_calls: int
    str_calls: int

    def __new__(cls, value: str) -> _ExplosiveString:
        instance = super().__new__(cls, value)
        instance.strip_calls = 0
        instance.str_calls = 0
        return instance

    def strip(self, chars: str | None = None) -> str:
        del chars
        self.strip_calls += 1
        raise RuntimeError("private string strip must not run")

    def __str__(self) -> str:
        self.str_calls += 1
        raise RuntimeError("private string __str__ must not run")


class _PropertyTripwireRow:
    def __init__(self) -> None:
        self.attribute_calls: list[str] = []
        self.str_calls = 0

    def __getattr__(self, name: str) -> object:
        self.attribute_calls.append(name)
        raise RuntimeError(f"private property access: {name}")

    def __str__(self) -> str:
        self.str_calls += 1
        raise RuntimeError("private row __str__ must not run")


class _CaseRegistryRecordTripwire(CaseRegistryRecord):
    attribute_calls: list[str]

    def __getattribute__(self, name: str) -> object:
        if name in REGISTRY_ROW_FIELDS:
            calls = object.__getattribute__(self, "attribute_calls")
            calls.append(name)
            raise RuntimeError(f"private subclass property access: {name}")
        return super().__getattribute__(name)


class _RegistryBackend:
    def __init__(self, record: object | None) -> None:
        self.record = copy.deepcopy(record)
        self.fetch_calls: list[dict[str, Any]] = []
        self.upsert_calls: list[dict[str, Any]] = []
        self.upsert_exception: Exception | None = None
        self.readback_exception: Exception | None = None
        self.readback_override: object = _DEFAULT_READBACK
        self.return_record_raw = False
        self.return_readback_raw = False
        self.upsert_return: object = {
            "backend_payload": "UNTRUSTED_UPSERT_RETURN_MUST_NOT_ESCAPE"
        }

    async def fetch_case_registry_record(
        self,
        case_id: str,
        *,
        repo_root: str | None = None,
        project_name: str | None = None,
    ) -> object | None:
        self.fetch_calls.append(
            {
                "case_id": case_id,
                "repo_root": repo_root,
                "project_name": project_name,
            }
        )
        if len(self.fetch_calls) > 1:
            if self.readback_exception is not None:
                raise self.readback_exception
            if self.readback_override is not _DEFAULT_READBACK:
                if self.return_readback_raw:
                    return self.readback_override
                return copy.deepcopy(self.readback_override)
        if self.return_record_raw:
            return self.record
        return copy.deepcopy(self.record)

    async def upsert_case_registry_record(self, **kwargs: Any) -> object:
        self.upsert_calls.append(copy.deepcopy(kwargs))
        if self.upsert_exception is not None:
            raise self.upsert_exception
        assert self.record is not None

        def _value(field: str) -> object:
            if isinstance(self.record, Mapping):
                return self.record.get(field)
            return getattr(self.record, field)

        self.record = CaseRegistryRecord(
            **kwargs,
            repo_id=_value("repo_id"),
            project_key=_value("project_key"),
            created_at=_value("created_at"),
            updated_at=(
                _value("updated_at") + timedelta(seconds=1)
                if _value("updated_at") is not None
                else None
            ),
        )
        return self.upsert_return


class _AuditSink:
    def __init__(
        self,
        *,
        fail_event: str | None = None,
        raise_event: str | None = None,
        failure_detail: str = "audit backend unavailable",
    ) -> None:
        self.fail_event = fail_event
        self.raise_event = raise_event
        self.failure_detail = failure_detail
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(kwargs))
        event = str((kwargs.get("meta") or {}).get("case_event") or "")
        if event == self.raise_event:
            raise RuntimeError(self.failure_detail)
        if event == self.fail_event:
            return {"ok": False, "error": self.failure_detail}
        return {
            "ok": True,
            "id": f"audit-event-{len(self.calls)}",
            "path": "/private/audit/path",
            "project_name": "private-project",
        }


class _OrderedAuditSink(_AuditSink):
    def __init__(self, events: list[tuple[str, object]]) -> None:
        super().__init__()
        self._events = events

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        event = str((kwargs.get("meta") or {}).get("case_event") or "")
        self._events.append(("audit", event))
        return await super().__call__(**kwargs)


def _context(
    repo_root: Path,
    *,
    mode: str = "project",
    project_name: str | None = "test-project",
) -> SimpleNamespace:
    return SimpleNamespace(
        mode=mode,
        repo_root=str(repo_root) if repo_root else None,
        execution_id="exec-test",
        parent_execution_id=None,
        authoritative_session_key="session-test",
        stable_session_id="session-test",
        resolved_scope=SimpleNamespace(
            repo_root=str(repo_root) if repo_root else None,
            project_name=project_name,
            trust_level="verified",
            resolution_source="runtime_context",
            provenance=SimpleNamespace(
                repo_root="verified",
                project_name="verified",
            ),
        ),
    )


def _make_record(
    tmp_path: Path,
    *,
    case_id: str = "BUG-2026-07-11-0001",
    case_type: str | None = None,
    status: str = "closed",
    report_text: str | None = None,
) -> tuple[CaseRegistryRecord, SimpleNamespace, Path]:
    repo_root = (tmp_path / "repo").resolve()
    report_path = repo_root / ".scribe" / "docs" / "cases" / case_id / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_type = case_type or ("security" if case_id.startswith("SEC-") else "bug")
    label = "Case ID" if resolved_type == "security" else "Bug ID"
    if report_text is None:
        report_text = (
            f"**{label}:** {case_id}\n"
            "**Status:** investigating\n"
            "Private report line: never return this text.\n"
            "**Status:** investigating\n"
        )
    report_path.write_text(report_text, encoding="utf-8")
    created_at = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    record = CaseRegistryRecord(
        case_id=case_id,
        case_type=resolved_type,
        project_name="test-project",
        repo_root=str(repo_root),
        repo_id="repo-id-stable",
        project_key="project-key-stable",
        doc_type=resolved_type,
        doc_name=case_id,
        doc_path=str(report_path),
        title="Private case title",
        status=status,
        severity="high",
        source_tool="open_security" if resolved_type == "security" else "open_bug",
        metadata={
            "category": "private-category",
            "history": [{"event": "opened"}, {"event": "closed"}],
            "fix_link": {"artifact_ref": "private-artifact"},
            "nested": {"preserve": [1, 2, 3]},
        },
        created_at=created_at,
        updated_at=created_at,
    )
    return record, _context(repo_root), report_path


async def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backend: _RegistryBackend,
    context: object,
    audit: _AuditSink | None = None,
    case_id: object = "BUG-2026-07-11-0001",
    reason: object = "Correct accidental terminalization.",
    target_status: object = "investigating",
) -> dict[str, object]:
    def _context_getter() -> object:
        if context is _MISSING_CONTEXT:
            raise ValueError("private context failure")
        return context

    audit_sink = audit or _AuditSink()
    monkeypatch.setattr(sentinel_tools, "_get_context", _context_getter)
    monkeypatch.setattr(sentinel_tools.server_module, "storage_backend", backend)
    monkeypatch.setattr(append_entry_module, "append_entry", audit_sink)
    return await sentinel_tools.reopen_case(
        agent="test_agent",
        case_id=case_id,
        reason=reason,
        target_status=target_status,
    )


def _assert_closed_envelope(result: dict[str, object]) -> None:
    assert set(result) == EXPECTED_TOP_LEVEL_KEYS
    assert set(result["case_scope"]) == set(EXPECTED_CASE_SCOPE_FIELDS)
    assert set(result["case_registry"]) == set(EXPECTED_CASE_REGISTRY_FIELDS)
    assert type(result["ok"]) is bool
    assert result["mode"] in {"project", "sentinel", "unresolved"}
    assert result["case_id"] is None or isinstance(result["case_id"], str)
    assert result["case_type"] in {"bug", "security", None}
    assert type(result["partial"]) is bool
    assert result["failure_stage"] is None or isinstance(result["failure_stage"], str)
    assert result["error_code"] is None or isinstance(result["error_code"], str)
    assert isinstance(result["message"], str)
    assert result["changed"] is None or type(result["changed"]) is bool
    assert result["reopened"] is None or type(result["reopened"]) is bool
    assert result["idempotent"] is None or type(result["idempotent"]) is bool
    for field in (
        "target_status",
        "report_status",
        "registry_status_before",
        "registry_status_after",
        "requested_event_id",
        "completed_event_id",
    ):
        assert result[field] is None or isinstance(result[field], str)
    for field in (
        "registry_mutation_attempted",
        "registry_readback_verified",
        "mutation_may_have_occurred",
    ):
        assert type(result[field]) is bool
    assert all(type(value) is bool for value in result["case_scope"].values())
    assert all(type(value) is bool for value in result["case_registry"].values())
    assert result["warnings"] == []
    assert isinstance(result["next_step"], str)

    code = result["error_code"]
    if code is None:
        assert result["failure_stage"] is None
        assert result["next_step"] == ""
    else:
        expected = EXPECTED_FAILURE_CONTRACT[code]
        assert result["failure_stage"] == expected["failure_stage"]
        assert result["message"] == expected["message"]
        assert result["next_step"] == expected["next_step"]


def _branch_projection(result: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        result[field]
        for field in (
            "ok",
            "partial",
            "changed",
            "reopened",
            "idempotent",
            "registry_mutation_attempted",
            "registry_readback_verified",
            "mutation_may_have_occurred",
            "requested_event_id",
            "completed_event_id",
        )
    )


@pytest.mark.asyncio
async def test_plain_dict_registry_row_is_normalized_before_lifecycle_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard BUG-2026-07-11-0004: a valid storage mapping must never escape raw."""
    record, context, _ = _make_record(tmp_path)
    row = _record_mapping(record)
    backend = _RegistryBackend(row)
    backend.return_record_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["registry_readback_verified"] is True
    assert len(backend.upsert_calls) == 1
    assert backend.upsert_calls[0]["metadata"] == record.metadata
    assert isinstance(backend.record, CaseRegistryRecord)
    assert backend.record.repo_id == record.repo_id
    assert backend.record.project_key == record.project_key
    assert backend.record.created_at == record.created_at
    assert backend.record.metadata == record.metadata
    assert [call["meta"]["case_event"] for call in audit.calls] == [
        "case_reopen_requested",
        "case_reopen_completed",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["closed", "investigating"])
async def test_plain_dict_matches_registry_row_object_on_real_and_idempotent_paths(
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status=status)
    lifecycle_record_types: list[type[object]] = []
    real_decision_builder = sentinel_tools.build_reopen_transition_decision

    def _checked_decision_builder(**kwargs: Any) -> object:
        case_record = kwargs["case_record"]
        lifecycle_record_types.append(type(case_record))
        assert not isinstance(case_record, Mapping)
        return real_decision_builder(**kwargs)

    monkeypatch.setattr(
        sentinel_tools,
        "build_reopen_transition_decision",
        _checked_decision_builder,
    )
    object_backend = _RegistryBackend(record)
    object_result = await _invoke(
        monkeypatch,
        backend=object_backend,
        context=context,
    )

    mapping_backend = _RegistryBackend(None)
    mapping_backend.record = _record_mapping(record)
    mapping_backend.return_record_raw = True
    mapping_result = await _invoke(
        monkeypatch,
        backend=mapping_backend,
        context=context,
    )

    _assert_closed_envelope(object_result)
    _assert_closed_envelope(mapping_result)
    assert mapping_result == object_result
    assert mapping_backend.upsert_calls == object_backend.upsert_calls
    assert lifecycle_record_types == [CaseRegistryRecord, CaseRegistryRecord]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mapping_kind",
    ["mapping_proxy", "user_dict", "mapping_subclass"],
)
async def test_valid_mapping_implementations_follow_the_verified_idempotent_path(
    mapping_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status="investigating")
    row = _record_mapping(record)
    probe: _TripwireMapping | None = None
    if mapping_kind == "mapping_proxy":
        raw_row: Mapping[object, object] = MappingProxyType(row)
    elif mapping_kind == "user_dict":
        raw_row = UserDict(row)
    else:
        probe = _TripwireMapping(row, raise_len=True)
        raw_row = probe
    backend = _RegistryBackend(None)
    backend.record = raw_row
    backend.return_record_raw = True

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["ok"] is True
    assert result["idempotent"] is True
    assert result["registry_readback_verified"] is True
    assert not backend.upsert_calls
    if probe is not None:
        assert probe.iter_calls == 2
        assert probe.getitem_calls == list(REGISTRY_ROW_FIELDS) * 2
        assert probe.len_calls == 0
        assert probe.str_calls == 0
        assert probe.repr_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("optional_field", OPTIONAL_REGISTRY_ROW_FIELDS)
async def test_mapping_optional_field_omissions_follow_storage_dto_defaults(
    optional_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    row = _record_mapping(record)
    del row[optional_field]
    backend = _RegistryBackend(None)
    backend.record = row
    backend.return_record_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    if optional_field == "status":
        assert result["error_code"] == "REGISTRY_STATUS_INVALID"
        assert result["case_registry"]["identity_verified"] is True
        assert not backend.upsert_calls
        assert not audit.calls
    else:
        assert result["ok"] is True
        assert result["registry_readback_verified"] is True
        assert len(backend.upsert_calls) == 1
        assert isinstance(backend.record, CaseRegistryRecord)
        assert getattr(backend.record, optional_field) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_field", REQUIRED_REGISTRY_ROW_FIELDS)
async def test_mapping_missing_each_required_storage_field_fails_closed(
    missing_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, report_path = _make_record(tmp_path)
    row = _record_mapping(record)
    del row[missing_field]
    backend = _RegistryBackend(None)
    backend.record = row
    backend.return_record_raw = True
    audit = _AuditSink()
    report_before = report_path.read_bytes()
    mtime_before = report_path.stat().st_mtime_ns

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_IDENTITY_MISMATCH"
    assert result["partial"] is False
    assert result["case_registry"] == {
        "record_found": True,
        "identity_verified": False,
    }
    assert result["registry_mutation_attempted"] is False
    assert result["mutation_may_have_occurred"] is False
    assert len(backend.fetch_calls) == 1
    assert not backend.upsert_calls
    assert not audit.calls
    assert report_path.read_bytes() == report_before
    assert report_path.stat().st_mtime_ns == mtime_before


@pytest.mark.asyncio
@pytest.mark.parametrize("required_field", REQUIRED_REGISTRY_ROW_FIELDS)
@pytest.mark.parametrize("bad_kind", ["none", "integer", "list", "empty_string"])
async def test_mapping_required_fields_reject_wrong_scalar_and_container_types(
    required_field: str,
    bad_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    row = _record_mapping(record)
    bad_values: dict[str, object] = {
        "none": None,
        "integer": 7,
        "list": ["private-value"],
        "empty_string": "",
    }
    row[required_field] = bad_values[bad_kind]
    backend = _RegistryBackend(None)
    backend.record = row
    backend.return_record_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_IDENTITY_MISMATCH"
    assert result["partial"] is False
    assert not backend.upsert_calls
    assert not audit.calls
    assert "private-value" not in json.dumps(result, sort_keys=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("optional_field", OPTIONAL_REGISTRY_ROW_FIELDS)
async def test_mapping_optional_fields_reject_wrong_declared_types(
    optional_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    row = _record_mapping(record)
    bad_values: dict[str, object] = {
        "title": ["private-title"],
        "status": {"private": "status"},
        "severity": 7,
        "source_tool": True,
        "metadata": ["private-metadata"],
        "created_at": "2026-07-11T12:00:00+00:00",
        "updated_at": {"private": "timestamp"},
    }
    row[optional_field] = bad_values[optional_field]
    backend = _RegistryBackend(None)
    backend.record = row
    backend.return_record_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_IDENTITY_MISMATCH"
    assert not backend.upsert_calls
    assert not audit.calls
    assert "private" not in json.dumps(result, sort_keys=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape_kind",
    [
        "none",
        "bool",
        "integer",
        "float",
        "string",
        "bytes",
        "list",
        "tuple",
        "set",
        "object",
        "namespace",
        "property_row",
        "record_subclass",
    ],
)
async def test_non_mapping_backend_row_shapes_return_only_the_closed_envelope(
    shape_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    property_probe: _PropertyTripwireRow | None = None
    subclass_probe: _CaseRegistryRecordTripwire | None = None
    shapes: dict[str, object | None] = {
        "none": None,
        "bool": True,
        "integer": 9,
        "float": 1.25,
        "string": "postgresql://private:secret@db.invalid/scribe",
        "bytes": b"Bearer private-token",
        "list": ["api_key=private-list-key"],
        "tuple": ("private-tuple",),
        "set": {"private-set"},
        "object": object(),
        "namespace": SimpleNamespace(**_record_mapping(record)),
    }
    if shape_kind == "property_row":
        property_probe = _PropertyTripwireRow()
        raw_row: object | None = property_probe
    elif shape_kind == "record_subclass":
        subclass_probe = _CaseRegistryRecordTripwire(**_record_mapping(record))
        subclass_probe.attribute_calls = []
        raw_row = subclass_probe
    else:
        raw_row = shapes[shape_kind]
    backend = _RegistryBackend(None)
    backend.record = raw_row
    backend.return_record_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == (
        "CASE_NOT_FOUND" if shape_kind == "none" else "REGISTRY_IDENTITY_MISMATCH"
    )
    assert not backend.upsert_calls
    assert not audit.calls
    serialized = json.dumps(result, sort_keys=True)
    for private in ("private", "secret", "db.invalid", "Bearer", "api_key"):
        assert private not in serialized
    if property_probe is not None:
        assert property_probe.attribute_calls == []
        assert property_probe.str_calls == 0
    if subclass_probe is not None:
        assert subclass_probe.attribute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "shape_kind",
    [
        "extra_key",
        "non_string_key",
        "duplicate_iteration_key",
        "iterator_exception",
        "first_getitem_exception",
        "last_getitem_exception",
        "required_string_subclass",
        "optional_string_subclass",
        "metadata_cycle",
        "metadata_non_string_key",
        "metadata_tuple_value",
        "metadata_deepcopy_exception",
    ],
)
async def test_adversarial_mapping_rows_fail_before_report_audit_or_mutation(
    shape_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, report_path = _make_record(tmp_path)
    row = _record_mapping(record)
    mapping_probe: _TripwireMapping | None = None
    string_probe: _ExplosiveString | None = None
    deepcopy_probe: _ExplosiveDictValue | None = None
    if shape_kind == "extra_key":
        mapping_probe = _TripwireMapping({**row, "private_extra": "secret"})
        raw_row: object = mapping_probe
    elif shape_kind == "non_string_key":
        mapping_probe = _TripwireMapping({**row, 7: "secret"})
        raw_row = mapping_probe
    elif shape_kind == "duplicate_iteration_key":
        mapping_probe = _TripwireMapping(
            row,
            iter_keys=(*REGISTRY_ROW_FIELDS, "case_id"),
        )
        raw_row = mapping_probe
    elif shape_kind == "iterator_exception":
        mapping_probe = _TripwireMapping(row, raise_iter=True)
        raw_row = mapping_probe
    elif shape_kind == "first_getitem_exception":
        mapping_probe = _TripwireMapping(row, fail_getitem="case_id")
        raw_row = mapping_probe
    elif shape_kind == "last_getitem_exception":
        mapping_probe = _TripwireMapping(row, fail_getitem="updated_at")
        raw_row = mapping_probe
    elif shape_kind == "required_string_subclass":
        string_probe = _ExplosiveString(record.case_id)
        row["case_id"] = string_probe
        raw_row = row
    elif shape_kind == "optional_string_subclass":
        string_probe = _ExplosiveString(record.title or "title")
        row["title"] = string_probe
        raw_row = row
    elif shape_kind == "metadata_cycle":
        cyclic_metadata: dict[str, object] = {}
        cyclic_metadata["cycle"] = cyclic_metadata
        row["metadata"] = cyclic_metadata
        raw_row = row
    elif shape_kind == "metadata_non_string_key":
        row["metadata"] = {7: "private-metadata-value"}
        raw_row = row
    elif shape_kind == "metadata_tuple_value":
        row["metadata"] = {"nested": ("private-metadata-value",)}
        raw_row = row
    else:
        deepcopy_probe = _ExplosiveDictValue()
        row["metadata"] = {"nested": deepcopy_probe}
        raw_row = row
    backend = _RegistryBackend(None)
    backend.record = raw_row
    backend.return_record_raw = True
    audit = _AuditSink()
    report_before = report_path.read_bytes()
    mtime_before = report_path.stat().st_mtime_ns

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_IDENTITY_MISMATCH"
    assert result["partial"] is False
    assert result["registry_mutation_attempted"] is False
    assert result["mutation_may_have_occurred"] is False
    assert len(backend.fetch_calls) == 1
    assert not backend.upsert_calls
    assert not audit.calls
    assert report_path.read_bytes() == report_before
    assert report_path.stat().st_mtime_ns == mtime_before
    serialized = json.dumps(result, sort_keys=True)
    for private in ("private", "secret", "db.invalid", "Bearer", "api_key"):
        assert private not in serialized
    if mapping_probe is not None:
        assert mapping_probe.len_calls == 0
        assert mapping_probe.str_calls == 0
        assert mapping_probe.repr_calls == 0
        if shape_kind in {"extra_key", "non_string_key", "duplicate_iteration_key"}:
            assert mapping_probe.getitem_calls == []
    if string_probe is not None:
        assert string_probe.strip_calls == 0
        assert string_probe.str_calls == 0
    if deepcopy_probe is not None:
        assert deepcopy_probe.deepcopy_calls == 0
        assert deepcopy_probe.str_calls == 0


@pytest.mark.asyncio
async def test_mapping_tripwire_access_order_precedes_each_audit_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status="investigating")
    events: list[tuple[str, object]] = []
    probe = _TripwireMapping(
        _record_mapping(record),
        raise_len=True,
        events=events,
    )
    backend = _RegistryBackend(None)
    backend.record = probe
    backend.return_record_raw = True
    audit = _OrderedAuditSink(events)

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["ok"] is True
    assert result["idempotent"] is True
    one_projection = [
        ("iter", 1),
        *(("getitem", field) for field in REGISTRY_ROW_FIELDS),
    ]
    two_projection = [
        ("iter", 2),
        *(("getitem", field) for field in REGISTRY_ROW_FIELDS),
    ]
    assert events == [
        *one_projection,
        ("audit", "case_reopen_requested"),
        *two_projection,
        ("audit", "case_reopen_completed"),
    ]
    assert probe.len_calls == 0
    assert probe.str_calls == 0
    assert probe.repr_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["closed", "investigating"])
async def test_valid_plain_dict_readback_matches_registry_row_readback(
    status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status=status)
    backend = _RegistryBackend(record)
    readback = _record_mapping(record)
    readback["status"] = "investigating"
    if status == "closed" and record.updated_at is not None:
        readback["updated_at"] = record.updated_at + timedelta(seconds=1)
    backend.readback_override = readback

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["ok"] is True
    assert result["registry_readback_verified"] is True
    assert result["changed"] is (status == "closed")
    assert result["idempotent"] is (status == "investigating")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "readback_kind",
    [
        "none",
        "scalar",
        "missing_required",
        "extra_key",
        "non_string_key",
        "wrong_metadata",
        "getitem_exception",
        "property_row",
    ],
)
async def test_malformed_readback_rows_use_the_frozen_partial_mismatch_branch(
    readback_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    expected = _record_mapping(record)
    expected["status"] = "investigating"
    if record.updated_at is not None:
        expected["updated_at"] = record.updated_at + timedelta(seconds=1)
    probe: _TripwireMapping | _PropertyTripwireRow | None = None
    if readback_kind == "none":
        raw_readback: object | None = None
    elif readback_kind == "scalar":
        raw_readback = "Bearer private-readback-token"
    elif readback_kind == "missing_required":
        del expected["case_id"]
        raw_readback = expected
    elif readback_kind == "extra_key":
        raw_readback = {**expected, "private_extra": "secret"}
    elif readback_kind == "non_string_key":
        raw_readback = {**expected, 7: "secret"}
    elif readback_kind == "wrong_metadata":
        expected["metadata"] = ["api_key=private-readback-key"]
        raw_readback = expected
    elif readback_kind == "getitem_exception":
        probe = _TripwireMapping(expected, fail_getitem="metadata")
        raw_readback = probe
    else:
        probe = _PropertyTripwireRow()
        raw_readback = probe
    backend = _RegistryBackend(record)
    backend.readback_override = raw_readback
    backend.return_readback_raw = True
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_READBACK_MISMATCH"
    assert result["partial"] is True
    assert result["changed"] is None
    assert result["reopened"] is None
    assert result["registry_mutation_attempted"] is True
    assert result["registry_readback_verified"] is False
    assert result["mutation_may_have_occurred"] is True
    assert result["requested_event_id"] == "audit-event-1"
    assert result["completed_event_id"] is None
    assert len(backend.upsert_calls) == 1
    assert [call["meta"]["case_event"] for call in audit.calls] == [
        "case_reopen_requested"
    ]
    serialized = json.dumps(result, sort_keys=True)
    for private in ("private", "secret", "Bearer", "api_key"):
        assert private not in serialized
    if isinstance(probe, _TripwireMapping):
        assert probe.str_calls == 0
        assert probe.repr_calls == 0
    if isinstance(probe, _PropertyTripwireRow):
        assert probe.attribute_calls == []
        assert probe.str_calls == 0


@pytest.mark.asyncio
async def test_malformed_idempotent_readback_keeps_mutation_flags_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status="investigating")
    backend = _RegistryBackend(record)
    backend.readback_override = {"private_extra": "secret"}
    audit = _AuditSink()

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
    )

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_READBACK_MISMATCH"
    assert result["partial"] is True
    assert result["changed"] is False
    assert result["reopened"] is False
    assert result["idempotent"] is True
    assert result["registry_mutation_attempted"] is False
    assert result["registry_readback_verified"] is False
    assert result["mutation_may_have_occurred"] is False
    assert not backend.upsert_calls
    assert [call["meta"]["case_event"] for call in audit.calls] == [
        "case_reopen_requested"
    ]


def test_descriptor_signature_and_closed_vocabulary_are_frozen() -> None:
    signature = inspect.signature(sentinel_tools.reopen_case, eval_str=True)
    assert list(signature.parameters) == [
        "agent",
        "case_id",
        "reason",
        "target_status",
    ]
    assert signature.parameters["target_status"].default == "investigating"
    assert signature.return_annotation == Dict[str, object]

    descriptor = sentinel_tools.REOPEN_CASE_PUBLIC_CONTRACT_DESCRIPTOR
    assert descriptor == {
        "schema_version": "reopen-case-public-envelope.v1",
        "response_fields": EXPECTED_RESPONSE_FIELDS,
        "case_scope_fields": EXPECTED_CASE_SCOPE_FIELDS,
        "case_registry_fields": EXPECTED_CASE_REGISTRY_FIELDS,
        "failure_contract": EXPECTED_FAILURE_CONTRACT,
        "success_messages": EXPECTED_SUCCESS_MESSAGES,
    }
    canonical = json.dumps(
        descriptor,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == EXPECTED_DESCRIPTOR_SHA256
    assert len(EXPECTED_FAILURE_CONTRACT) == 29


@pytest.mark.asyncio
async def test_context_input_scope_and_lookup_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)

    scenarios = [
        (
            _MISSING_CONTEXT,
            _RegistryBackend(record),
            {},
            "CONTEXT_UNAVAILABLE",
            "unresolved",
        ),
        (
            _context(Path(record.repo_root), mode="sentinel"),
            _RegistryBackend(record),
            {},
            "PROJECT_MODE_REQUIRED",
            "sentinel",
        ),
        (
            context,
            _RegistryBackend(record),
            {"case_id": "bug-private-invalid"},
            "INVALID_CASE_ID",
            "project",
        ),
        (
            context,
            _RegistryBackend(record),
            {"reason": "   "},
            "INVALID_REASON",
            "project",
        ),
        (
            context,
            _RegistryBackend(record),
            {"target_status": "closed"},
            "INVALID_TARGET_STATUS",
            "project",
        ),
        (
            _context(Path(record.repo_root), project_name=None),
            _RegistryBackend(record),
            {},
            "ACTIVE_SCOPE_UNAVAILABLE",
            "project",
        ),
        (
            context,
            _RegistryBackend(None),
            {},
            "CASE_NOT_FOUND",
            "project",
        ),
    ]
    for scenario_context, backend, kwargs, code, mode in scenarios:
        result = await _invoke(
            monkeypatch,
            backend=backend,
            context=scenario_context,
            **kwargs,
        )
        _assert_closed_envelope(result)
        assert result["ok"] is False
        assert result["mode"] == mode
        assert result["error_code"] == code
        assert result["partial"] is False
        assert result["changed"] is None
        assert result["reopened"] is False
        assert result["idempotent"] is None
        assert not backend.upsert_calls

    invalid = await _invoke(
        monkeypatch,
        backend=_RegistryBackend(record),
        context=context,
        case_id="postgresql://user:password@private.invalid/project",
    )
    assert invalid["case_id"] is None
    assert "private.invalid" not in json.dumps(invalid, sort_keys=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_field", ["repo_root", "project_name"])
async def test_wrong_repo_and_project_are_distinctly_exercised_but_public_safe(
    scope_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    if scope_field == "repo_root":
        record = replace(record, repo_root="/private/wrong-repository")
    else:
        record = replace(record, project_name="private-wrong-project")
    backend = _RegistryBackend(record)

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == "CASE_SCOPE_MISMATCH"
    assert result["case_scope"] == {
        "active_repo_verified": True,
        "active_project_verified": True,
    }
    assert result["case_registry"] == {
        "record_found": True,
        "identity_verified": False,
    }
    serialized = json.dumps(result, sort_keys=True)
    assert "private/wrong-repository" not in serialized
    assert "private-wrong-project" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identity_field", ["case_id", "case_type", "doc_type", "doc_name"]
)
async def test_exact_registry_identity_binding_denies_each_mismatch(
    identity_field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    mismatches: dict[str, object] = {
        "case_id": "BUG-2026-07-11-9999",
        "case_type": "security",
        "doc_type": "security",
        "doc_name": "BUG-2026-07-11-9999",
    }
    record = replace(record, **{identity_field: mismatches[identity_field]})
    backend = _RegistryBackend(record)

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_IDENTITY_MISMATCH"
    assert result["case_registry"] == {
        "record_found": True,
        "identity_verified": False,
    }
    assert not backend.upsert_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report_text, expected_code",
    [
        ("**Status:** investigating\n", "REPORT_ID_HEADER_MISSING"),
        (
            "**Bug ID:** BUG-2026-07-11-0001\n"
            "**Bug ID:** BUG-2026-07-11-0001\n"
            "**Status:** investigating\n",
            "REPORT_ID_HEADER_DUPLICATE",
        ),
        (
            "**Bug ID** BUG-2026-07-11-0001\n**Status:** investigating\n",
            "REPORT_ID_HEADER_MALFORMED",
        ),
        (
            "**Case ID:** BUG-2026-07-11-0001\n**Status:** investigating\n",
            "REPORT_ID_HEADER_TYPE_MISMATCH",
        ),
        (
            "**Bug ID:** BUG-2026-07-11-9999\n**Status:** investigating\n",
            "REPORT_ID_MISMATCH",
        ),
        ("**Bug ID:** BUG-2026-07-11-0001\n", "REPORT_STATUS_MISSING"),
        (
            "**Bug ID:** BUG-2026-07-11-0001\n"
            "**Status:** investigating\n"
            "**Status:** open\n",
            "REPORT_STATUS_CONFLICT",
        ),
        (
            "**Bug ID:** BUG-2026-07-11-0001\n**Status:** closed\n",
            "REPORT_STATUS_INVALID",
        ),
        (
            "**Bug ID:** BUG-2026-07-11-0001\n**Status:** open\n",
            "REPORT_STATUS_MISMATCH",
        ),
    ],
)
async def test_every_rc1a_report_failure_maps_through_closed_public_contract(
    report_text: str,
    expected_code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, report_text=report_text)
    backend = _RegistryBackend(record)

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == expected_code
    assert result["case_registry"]["identity_verified"] is True
    assert result["registry_status_before"] == "closed"
    assert result["changed"] is None
    assert result["idempotent"] is None
    assert not backend.upsert_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "access_mode, expected_code",
    [
        ("missing", "REPORT_UNAVAILABLE"),
        ("outside", "REPORT_OUTSIDE_SCOPE"),
        ("invalid_utf8", "REPORT_READ_FAILED"),
    ],
)
async def test_report_containment_availability_and_utf8_failures_are_stable(
    access_mode: str,
    expected_code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, report_path = _make_record(tmp_path)
    if access_mode == "missing":
        report_path.unlink()
    elif access_mode == "outside":
        outside = (tmp_path / "outside" / "report.md").resolve()
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
        record = replace(record, doc_path=str(outside))
    else:
        report_path.write_bytes(b"\xff\xfe\x00private")
    backend = _RegistryBackend(record)

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == expected_code
    assert result["case_registry"]["identity_verified"] is True
    assert result["registry_status_before"] == "closed"
    assert not backend.upsert_calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id, case_type, terminal_status",
    [
        ("BUG-2026-07-11-0001", "bug", "closed"),
        ("BUG-2026-07-11-0001", "bug", "validated"),
        ("BUG-2026-07-11-0001", "bug", "duplicate"),
        ("BUG-2026-07-11-0001", "bug", "false_positive"),
        ("SEC-2026-07-11-0001", "security", "closed"),
    ],
)
async def test_terminal_families_reopen_with_preserved_payload_and_audit_order(
    case_id: str,
    case_type: str,
    terminal_status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(
        tmp_path,
        case_id=case_id,
        case_type=case_type,
        status=terminal_status,
    )
    before = copy.deepcopy(record)
    backend = _RegistryBackend(record)
    audit = _AuditSink()
    reason = "Exact audit-only recovery reason."

    result = await _invoke(
        monkeypatch,
        backend=backend,
        context=context,
        audit=audit,
        case_id=case_id,
        reason=reason,
    )

    _assert_closed_envelope(result)
    assert _branch_projection(result) == (
        True,
        False,
        True,
        True,
        False,
        True,
        True,
        False,
        "audit-event-1",
        "audit-event-2",
    )
    assert result["message"] == EXPECTED_SUCCESS_MESSAGES["changed"]
    assert result["case_scope"] == {
        "active_repo_verified": True,
        "active_project_verified": True,
    }
    assert result["case_registry"] == {
        "record_found": True,
        "identity_verified": True,
    }
    assert len(backend.upsert_calls) == 1
    upsert = backend.upsert_calls[0]
    assert set(upsert) == {
        "case_id",
        "case_type",
        "project_name",
        "repo_root",
        "doc_type",
        "doc_name",
        "doc_path",
        "title",
        "status",
        "severity",
        "source_tool",
        "metadata",
    }
    for field in (
        "case_id",
        "case_type",
        "project_name",
        "repo_root",
        "doc_type",
        "doc_name",
        "doc_path",
        "title",
        "severity",
        "source_tool",
        "metadata",
    ):
        assert upsert[field] == getattr(before, field)
    assert upsert["status"] == "investigating"
    assert backend.record is not None
    assert backend.record.repo_id == before.repo_id
    assert backend.record.project_key == before.project_key
    assert backend.record.created_at == before.created_at
    assert backend.record.metadata == before.metadata

    assert [call["meta"]["case_event"] for call in audit.calls] == [
        "case_reopen_requested",
        "case_reopen_completed",
    ]
    requested_meta = audit.calls[0]["meta"]
    completed_meta = audit.calls[1]["meta"]
    assert requested_meta["reason"] == reason
    assert requested_meta["source_tool"] == "reopen_case"
    assert requested_meta["case_id"] == case_id
    assert requested_meta["case_type"] == case_type
    assert requested_meta["registry_status_before"] == terminal_status
    assert requested_meta["target_status"] == "investigating"
    assert requested_meta["report_status"] == "investigating"
    assert requested_meta["transition_required"] is True
    assert requested_meta["idempotent"] is False
    assert completed_meta["registry_status_after"] == "investigating"
    assert completed_meta["registry_readback_verified"] is True
    assert completed_meta["requested_event_id"] == "audit-event-1"
    if case_type == "security":
        assert requested_meta["security_event"] == "1"
        assert completed_meta["security_event"] == "1"
    else:
        assert "security_event" not in requested_meta
    assert reason not in json.dumps(result, sort_keys=True)
    assert "UNTRUSTED_UPSERT_RETURN_MUST_NOT_ESCAPE" not in json.dumps(
        result, sort_keys=True
    )


@pytest.mark.asyncio
async def test_already_open_is_verified_idempotent_and_different_open_state_denies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status="investigating")
    backend = _RegistryBackend(record)
    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert _branch_projection(result) == (
        True,
        False,
        False,
        False,
        True,
        False,
        True,
        False,
        "audit-event-1",
        "audit-event-2",
    )
    assert result["message"] == EXPECTED_SUCCESS_MESSAGES["idempotent"]
    assert not backend.upsert_calls

    record, context, _ = _make_record(
        tmp_path / "different-open",
        status="open",
    )
    backend = _RegistryBackend(record)
    result = await _invoke(monkeypatch, backend=backend, context=context)
    _assert_closed_envelope(result)
    assert result["error_code"] == "TRANSITION_NOT_ALLOWED"
    assert result["changed"] is None
    assert result["idempotent"] is None
    assert not backend.upsert_calls


@pytest.mark.asyncio
async def test_all_eleven_frozen_branch_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _scenario(
        name: str,
        *,
        status: str = "closed",
        audit: _AuditSink | None = None,
        configure_backend: Any | None = None,
        invalid_case_id: bool = False,
        payload_failure: bool = False,
    ) -> dict[str, object]:
        record, context, _ = _make_record(tmp_path / name, status=status)
        backend = _RegistryBackend(record)
        if configure_backend is not None:
            configure_backend(backend)
        if payload_failure:
            with pytest.MonkeyPatch.context() as patcher:
                patcher.setattr(
                    sentinel_tools.doc_utils,
                    "build_case_registry_upsert_kwargs",
                    lambda **_kwargs: None,
                )
                return await _invoke(
                    monkeypatch,
                    backend=backend,
                    context=context,
                    audit=audit,
                )
        return await _invoke(
            monkeypatch,
            backend=backend,
            context=context,
            audit=audit,
            case_id="not-a-case" if invalid_case_id else record.case_id,
        )

    real_success = await _scenario("real-success")
    idempotent_success = await _scenario("idempotent-success", status="investigating")
    common_failure = await _scenario("common-failure", invalid_case_id=True)
    requested_real = await _scenario(
        "requested-real",
        audit=_AuditSink(fail_event="case_reopen_requested"),
    )
    requested_idempotent = await _scenario(
        "requested-idempotent",
        status="investigating",
        audit=_AuditSink(fail_event="case_reopen_requested"),
    )
    payload_failure = await _scenario("payload-failure", payload_failure=True)
    upsert_failure = await _scenario(
        "upsert-failure",
        configure_backend=lambda backend: setattr(
            backend,
            "upsert_exception",
            RuntimeError("private upsert failure"),
        ),
    )
    real_readback_failure = await _scenario(
        "real-readback-failure",
        configure_backend=lambda backend: setattr(
            backend,
            "readback_exception",
            RuntimeError("private readback failure"),
        ),
    )
    idempotent_readback_failure = await _scenario(
        "idempotent-readback-failure",
        status="investigating",
        configure_backend=lambda backend: setattr(
            backend,
            "readback_override",
            None,
        ),
    )
    completed_real = await _scenario(
        "completed-real",
        audit=_AuditSink(fail_event="case_reopen_completed"),
    )
    completed_idempotent = await _scenario(
        "completed-idempotent",
        status="investigating",
        audit=_AuditSink(fail_event="case_reopen_completed"),
    )

    expected_rows = [
        (
            real_success,
            (
                True,
                False,
                True,
                True,
                False,
                True,
                True,
                False,
                "audit-event-1",
                "audit-event-2",
            ),
        ),
        (
            idempotent_success,
            (
                True,
                False,
                False,
                False,
                True,
                False,
                True,
                False,
                "audit-event-1",
                "audit-event-2",
            ),
        ),
        (
            common_failure,
            (False, False, None, False, None, False, False, False, None, None),
        ),
        (
            requested_real,
            (False, False, False, False, False, False, False, False, None, None),
        ),
        (
            requested_idempotent,
            (False, False, False, False, True, False, False, False, None, None),
        ),
        (
            payload_failure,
            (
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                False,
                "audit-event-1",
                None,
            ),
        ),
        (
            upsert_failure,
            (
                False,
                True,
                None,
                None,
                False,
                True,
                False,
                True,
                "audit-event-1",
                None,
            ),
        ),
        (
            real_readback_failure,
            (
                False,
                True,
                None,
                None,
                False,
                True,
                False,
                True,
                "audit-event-1",
                None,
            ),
        ),
        (
            idempotent_readback_failure,
            (
                False,
                True,
                False,
                False,
                True,
                False,
                False,
                False,
                "audit-event-1",
                None,
            ),
        ),
        (
            completed_real,
            (
                False,
                True,
                True,
                True,
                False,
                True,
                True,
                False,
                "audit-event-1",
                None,
            ),
        ),
        (
            completed_idempotent,
            (
                False,
                True,
                False,
                False,
                True,
                False,
                True,
                False,
                "audit-event-1",
                None,
            ),
        ),
    ]
    for result, expected in expected_rows:
        _assert_closed_envelope(result)
        assert _branch_projection(result) == expected

    assert requested_real["error_code"] == "AUDIT_REQUEST_FAILED"
    assert requested_idempotent["error_code"] == "AUDIT_REQUEST_FAILED"
    assert payload_failure["error_code"] == "REGISTRY_PAYLOAD_BUILD_FAILED"
    assert upsert_failure["error_code"] == "REGISTRY_UPSERT_FAILED"
    assert real_readback_failure["error_code"] == "REGISTRY_READBACK_FAILED"
    assert idempotent_readback_failure["error_code"] == "REGISTRY_READBACK_MISMATCH"
    assert completed_real["error_code"] == "AUDIT_COMPLETION_FAILED"
    assert completed_idempotent["error_code"] == "AUDIT_COMPLETION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize("branch_status", ["closed", "investigating"])
async def test_readback_mismatch_is_partial_without_inventing_idempotent_mutation(
    branch_status: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status=branch_status)
    backend = _RegistryBackend(record)
    mismatch = copy.deepcopy(record)
    mismatch.metadata = {"private": "mutated"}
    backend.readback_override = mismatch

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_READBACK_MISMATCH"
    assert result["partial"] is True
    if branch_status == "closed":
        assert result["changed"] is None
        assert result["reopened"] is None
        assert result["registry_mutation_attempted"] is True
        assert result["mutation_may_have_occurred"] is True
    else:
        assert result["changed"] is False
        assert result["reopened"] is False
        assert result["registry_mutation_attempted"] is False
        assert result["mutation_may_have_occurred"] is False


@pytest.mark.asyncio
async def test_public_output_redacts_backend_and_private_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path, status="closed")
    backend = _RegistryBackend(record)
    secret_detail = (
        "postgresql://admin:supersecret@db.internal/scribe "
        "Authorization: Bearer bearer-secret "
        "api_key=key-secret "
        f"{record.repo_root} "
        "test-project "
        "Private report line: never return this text. "
        "{'arbitrary_backend_payload': 'payload-secret'}"
    )
    backend.upsert_exception = RuntimeError(secret_detail)
    logged: list[str] = []
    monkeypatch.setattr(
        sentinel_tools.logger,
        "warning",
        lambda message, *args: logged.append(message % args),
    )

    result = await _invoke(monkeypatch, backend=backend, context=context)

    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_UPSERT_FAILED"
    serialized = json.dumps(result, sort_keys=True)
    for forbidden in (
        "supersecret",
        "bearer-secret",
        "key-secret",
        record.repo_root,
        "test-project",
        "Private report line",
        "arbitrary_backend_payload",
        "payload-secret",
        "db.internal",
    ):
        assert forbidden not in serialized
    log_text = "\n".join(logged)
    assert "REGISTRY_UPSERT_FAILED" in log_text
    assert "registry_mutation" in log_text
    assert "supersecret" not in log_text
    assert "bearer-secret" not in log_text
    assert "key-secret" not in log_text


@pytest.mark.asyncio
async def test_payload_builder_exception_and_audit_exceptions_stay_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, context, _ = _make_record(tmp_path)
    backend = _RegistryBackend(record)
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            sentinel_tools.doc_utils,
            "build_case_registry_upsert_kwargs",
            lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("password=private-payload-builder")
            ),
        )
        result = await _invoke(monkeypatch, backend=backend, context=context)
    _assert_closed_envelope(result)
    assert result["error_code"] == "REGISTRY_PAYLOAD_BUILD_FAILED"
    assert "private-payload-builder" not in json.dumps(result, sort_keys=True)

    requested = await _invoke(
        monkeypatch,
        backend=_RegistryBackend(record),
        context=context,
        audit=_AuditSink(
            raise_event="case_reopen_requested",
            failure_detail="Bearer private-request-token",
        ),
    )
    _assert_closed_envelope(requested)
    assert requested["error_code"] == "AUDIT_REQUEST_FAILED"
    assert "private-request-token" not in json.dumps(requested, sort_keys=True)

    completed = await _invoke(
        monkeypatch,
        backend=_RegistryBackend(record),
        context=context,
        audit=_AuditSink(
            raise_event="case_reopen_completed",
            failure_detail="api_key=private-completion-key",
        ),
    )
    _assert_closed_envelope(completed)
    assert completed["error_code"] == "AUDIT_COMPLETION_FAILED"
    assert "private-completion-key" not in json.dumps(completed, sort_keys=True)
