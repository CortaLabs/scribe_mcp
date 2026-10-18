"""Pure lifecycle helpers for Scribe bug/security case readback."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from scribe_mcp.doc_management import utils as doc_utils
from scribe_mcp.storage.models import CaseRegistryRecord

CanonicalDocAliasKind = Literal[
    "primary", "caller_alias", "legacy_compat", "path_alias"
]
ReopenCaseType = Literal["bug", "security"]

_REOPEN_CASE_ID_PATTERN = re.compile(r"^(BUG|SEC)-\d{4}-\d{2}-\d{2}-\d{4}$")
_REPORT_ID_HEADER_PATTERN = re.compile(
    r"^\*\*(Bug ID|Case ID):\*\*[ \t]+((?:BUG|SEC)-\d{4}-\d{2}-\d{2}-\d{4})[ \t]*$"
)
_REPORT_STATUS_PATTERN = re.compile(r"^\*\*Status:\*\*[ \t]*(.*?)[ \t]*$")
_REPORT_ID_CANDIDATE_PREFIXES = ("**Bug ID", "**Case ID")


@dataclass(frozen=True)
class CanonicalDocAlias:
    alias: str
    alias_kind: CanonicalDocAliasKind
    doc_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "alias": self.alias,
            "alias_kind": self.alias_kind,
            "doc_path": self.doc_path,
        }


@dataclass(frozen=True)
class CanonicalDocBinding:
    canonical_doc_name: str
    canonical_doc_path: str
    aliases: tuple[CanonicalDocAlias, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "canonical_doc_name": self.canonical_doc_name,
            "canonical_doc_path": self.canonical_doc_path,
            "aliases": [alias.to_dict() for alias in self.aliases],
        }


@dataclass(frozen=True)
class CaseLifecycleResult:
    case_id: str
    case_type: str
    lifecycle_status: str | None
    fix_link_recorded: bool
    case_closed: bool
    landing_status: str | None
    landing_status_terminal: bool
    registry_status_before: str | None
    registry_status_after: str | None
    closure_reason: str | None
    doc_binding: CanonicalDocBinding | None
    last_fix_link: dict[str, object] | None
    next_step: str

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "lifecycle_status": self.lifecycle_status,
            "fix_link_recorded": self.fix_link_recorded,
            "case_closed": self.case_closed,
            "landing_status": self.landing_status,
            "landing_status_terminal": self.landing_status_terminal,
            "registry_status_before": self.registry_status_before,
            "registry_status_after": self.registry_status_after,
            "closure_reason": self.closure_reason,
            "doc_binding": self.doc_binding.to_dict() if self.doc_binding else None,
            "last_fix_link": self.last_fix_link,
            "next_step": self.next_step,
        }


class CaseReopenValidationError(ValueError):
    """Stable-code validation failure for the pure case reopen contract."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class GovernedCaseReportProjection:
    case_id: str
    case_type: ReopenCaseType
    status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "status": self.status,
        }


@dataclass(frozen=True)
class CaseReopenDecision:
    case_id: str
    case_type: ReopenCaseType
    registry_status_before: str
    target_status: str
    report_case_id: str
    report_case_type: ReopenCaseType
    report_status: str
    transition_required: bool
    idempotent: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "registry_status_before": self.registry_status_before,
            "target_status": self.target_status,
            "report_case_id": self.report_case_id,
            "report_case_type": self.report_case_type,
            "report_status": self.report_status,
            "transition_required": self.transition_required,
            "idempotent": self.idempotent,
        }


def infer_reopen_case_type(case_id: str) -> ReopenCaseType:
    """Return the governed case type for one canonical BUG/SEC identifier."""
    _, case_type = _canonical_reopen_case_identity(case_id)
    return case_type


def parse_governed_case_report(
    report_text: str,
    expected_case_id: str,
    expected_case_type: str,
) -> GovernedCaseReportProjection:
    """Parse exact BUG/SEC identity and open Status fields from a governed report."""
    canonical_case_id, case_type_from_id = _canonical_reopen_case_identity(
        expected_case_id
    )
    if (
        expected_case_type not in {"bug", "security"}
        or case_type_from_id != expected_case_type
    ):
        raise CaseReopenValidationError("REPORT_ID_HEADER_TYPE_MISMATCH")
    if not isinstance(report_text, str):
        raise CaseReopenValidationError("REPORT_ID_HEADER_MISSING")
    case_type: ReopenCaseType = expected_case_type
    expected_label = "Bug ID" if case_type == "bug" else "Case ID"

    parsed_headers: list[tuple[str, str]] = []
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if not line.startswith(_REPORT_ID_CANDIDATE_PREFIXES):
            continue
        match = _REPORT_ID_HEADER_PATTERN.fullmatch(line)
        if match is None:
            raise CaseReopenValidationError("REPORT_ID_HEADER_MALFORMED")
        parsed_headers.append((match.group(1), match.group(2)))

    if any(label != expected_label for label, _ in parsed_headers):
        raise CaseReopenValidationError("REPORT_ID_HEADER_TYPE_MISMATCH")
    expected_headers = [
        case_id for label, case_id in parsed_headers if label == expected_label
    ]
    if not expected_headers:
        raise CaseReopenValidationError("REPORT_ID_HEADER_MISSING")
    if len(expected_headers) > 1:
        raise CaseReopenValidationError("REPORT_ID_HEADER_DUPLICATE")

    report_case_id = expected_headers[0]
    report_case_type = _case_type_for_prefix(report_case_id)
    if report_case_type != case_type:
        raise CaseReopenValidationError("REPORT_ID_HEADER_TYPE_MISMATCH")
    if report_case_id != canonical_case_id:
        raise CaseReopenValidationError("REPORT_ID_MISMATCH")

    report_statuses: list[str] = []
    for raw_line in report_text.splitlines():
        match = _REPORT_STATUS_PATTERN.fullmatch(raw_line.strip())
        if match is None:
            continue
        status = doc_utils.normalize_case_status(match.group(1))
        if status not in doc_utils.CASE_OPEN_STATUS_VALUES:
            raise CaseReopenValidationError("REPORT_STATUS_INVALID")
        report_statuses.append(status)

    if not report_statuses:
        raise CaseReopenValidationError("REPORT_STATUS_MISSING")
    unique_statuses = set(report_statuses)
    if len(unique_statuses) != 1:
        raise CaseReopenValidationError("REPORT_STATUS_CONFLICT")

    return GovernedCaseReportProjection(
        case_id=report_case_id,
        case_type=report_case_type,
        status=unique_statuses.pop(),
    )


def build_reopen_transition_decision(
    *,
    case_id: str,
    case_record: CaseRegistryRecord,
    target_status: str,
    report: GovernedCaseReportProjection,
) -> CaseReopenDecision:
    """Build a deterministic terminal-to-open or exact idempotent transition decision."""
    canonical_case_id, case_type = _canonical_reopen_case_identity(case_id)
    if (
        case_record.case_id != canonical_case_id
        or case_record.doc_name != canonical_case_id
        or case_record.case_type != case_type
        or case_record.doc_type != case_type
    ):
        raise CaseReopenValidationError("REGISTRY_IDENTITY_MISMATCH")

    if report.case_type != case_type:
        raise CaseReopenValidationError("REPORT_ID_HEADER_TYPE_MISMATCH")
    if report.case_id != canonical_case_id:
        raise CaseReopenValidationError("REPORT_ID_MISMATCH")

    normalized_target = doc_utils.normalize_case_status(target_status)
    if normalized_target not in doc_utils.CASE_OPEN_STATUS_VALUES:
        raise CaseReopenValidationError("INVALID_TARGET_STATUS")
    normalized_report_status = doc_utils.normalize_case_status(report.status)
    if normalized_report_status not in doc_utils.CASE_OPEN_STATUS_VALUES:
        raise CaseReopenValidationError("REPORT_STATUS_INVALID")
    if normalized_report_status != normalized_target:
        raise CaseReopenValidationError("REPORT_STATUS_MISMATCH")

    registry_status_before = doc_utils.normalize_case_status(case_record.status)
    allowed_registry_statuses = (
        doc_utils.CASE_OPEN_STATUS_VALUES | doc_utils.CASE_CLOSED_STATUS_VALUES
    )
    if registry_status_before not in allowed_registry_statuses:
        raise CaseReopenValidationError("REGISTRY_STATUS_INVALID")
    if registry_status_before == normalized_target:
        transition_required = False
        idempotent = True
    elif registry_status_before in doc_utils.CASE_CLOSED_STATUS_VALUES:
        transition_required = True
        idempotent = False
    else:
        raise CaseReopenValidationError("TRANSITION_NOT_ALLOWED")

    return CaseReopenDecision(
        case_id=canonical_case_id,
        case_type=case_type,
        registry_status_before=registry_status_before,
        target_status=normalized_target,
        report_case_id=report.case_id,
        report_case_type=report.case_type,
        report_status=normalized_report_status,
        transition_required=transition_required,
        idempotent=idempotent,
    )


def normalize_landing_status(value: str | None) -> str:
    """Normalize a landing status and reject tokens outside the shared vocabulary."""
    normalized = doc_utils.normalize_case_status(value)
    allowed_values = (
        doc_utils.CASE_OPEN_STATUS_VALUES | doc_utils.CASE_CLOSED_STATUS_VALUES
    )
    if not normalized or normalized not in allowed_values:
        raise ValueError(f"Unknown case landing status: {value!r}")
    return normalized


def resolve_registry_status_after(
    current_status: str | None,
    landing_status: str | None,
) -> tuple[str | None, bool, str | None]:
    landing = normalize_landing_status(landing_status)
    close_status = doc_utils.resolved_case_close_status(landing)
    if close_status is not None:
        return close_status, True, close_status
    return _normalize_registry_status(current_status), False, None


def build_canonical_doc_binding(
    case_id: str,
    doc_path: str,
    docs_mapping: Mapping[str, str],
    *,
    preferred_doc_name: str | None = None,
) -> CanonicalDocBinding:
    canonical_path = _normalize_doc_path(doc_path)
    canonical_name = (
        case_id
        or preferred_doc_name
        or _first_matching_name(canonical_path, docs_mapping)
    )
    if not canonical_name:
        canonical_name = Path(canonical_path).stem

    matching_names: list[str] = []
    for name, candidate_path in docs_mapping.items():
        if (
            _normalize_doc_path(candidate_path) == canonical_path
            and name not in matching_names
        ):
            matching_names.append(name)
    if canonical_name in matching_names:
        matching_names.remove(canonical_name)
    matching_names.insert(0, canonical_name)

    aliases: list[CanonicalDocAlias] = []
    for name in matching_names:
        aliases.append(
            CanonicalDocAlias(
                alias=name,
                alias_kind=_alias_kind(name, canonical_name, preferred_doc_name),
                doc_path=canonical_path,
            )
        )
    return CanonicalDocBinding(
        canonical_doc_name=canonical_name,
        canonical_doc_path=canonical_path,
        aliases=tuple(aliases),
    )


def doc_binding_to_metadata(binding: CanonicalDocBinding) -> dict[str, object]:
    return binding.to_dict()


def doc_binding_from_metadata(
    metadata: Mapping[str, object] | None,
    *,
    fallback_case_id: str | None = None,
    fallback_doc_path: str | None = None,
) -> CanonicalDocBinding | None:
    if metadata is None:
        if fallback_case_id and fallback_doc_path:
            return build_canonical_doc_binding(fallback_case_id, fallback_doc_path, {})
        return None

    raw_binding = metadata.get("doc_binding")
    binding_data = raw_binding if isinstance(raw_binding, Mapping) else metadata
    canonical_name = (
        _string_or_none(binding_data.get("canonical_doc_name")) or fallback_case_id
    )
    canonical_path = (
        _string_or_none(binding_data.get("canonical_doc_path")) or fallback_doc_path
    )
    if not canonical_name or not canonical_path:
        return None

    aliases = _aliases_from_metadata(binding_data.get("aliases"), canonical_path)
    if not aliases:
        aliases = (
            CanonicalDocAlias(
                alias=canonical_name,
                alias_kind="primary",
                doc_path=_normalize_doc_path(canonical_path),
            ),
        )
    return CanonicalDocBinding(
        canonical_doc_name=canonical_name,
        canonical_doc_path=_normalize_doc_path(canonical_path),
        aliases=aliases,
    )


def build_link_fix_lifecycle_result(
    *,
    case_record_before: CaseRegistryRecord,
    case_record_after: CaseRegistryRecord | None,
    landing_status: str,
    fix_link_recorded: bool,
    doc_binding: CanonicalDocBinding | None,
    doc_update_warning: str | None = None,
) -> CaseLifecycleResult:
    normalized_landing = normalize_landing_status(landing_status)
    registry_status_before = _normalize_registry_status(case_record_before.status)
    resolved_status_after, landing_terminal, closure_reason = (
        resolve_registry_status_after(
            registry_status_before,
            normalized_landing,
        )
    )
    registry_status_after = _normalize_registry_status(
        case_record_after.status if case_record_after is not None else None
    )
    if registry_status_after is None and not landing_terminal:
        registry_status_after = resolved_status_after
    case_closed = doc_utils.case_status_closes(registry_status_after)
    lifecycle_status = registry_status_after
    if case_closed:
        closure_reason = doc_utils.resolved_case_close_status(registry_status_after)
    next_step = _next_step(
        case_closed=case_closed,
        fix_link_recorded=fix_link_recorded,
        landing_status_terminal=landing_terminal,
        doc_update_warning=doc_update_warning,
    )
    metadata_record = (
        case_record_after if case_record_after is not None else case_record_before
    )

    return CaseLifecycleResult(
        case_id=case_record_before.case_id,
        case_type=case_record_before.case_type,
        lifecycle_status=lifecycle_status,
        fix_link_recorded=fix_link_recorded,
        case_closed=case_closed,
        landing_status=normalized_landing,
        landing_status_terminal=landing_terminal,
        registry_status_before=registry_status_before,
        registry_status_after=registry_status_after,
        closure_reason=closure_reason,
        doc_binding=doc_binding,
        last_fix_link=_last_fix_link(metadata_record),
        next_step=next_step,
    )


def case_status_snapshot(
    case_record: CaseRegistryRecord,
    *,
    doc_binding: CanonicalDocBinding | None = None,
) -> CaseLifecycleResult:
    lifecycle_status = _normalize_registry_status(case_record.status)
    case_closed = doc_utils.case_status_closes(lifecycle_status)
    closure_reason = (
        doc_utils.resolved_case_close_status(lifecycle_status) if case_closed else None
    )
    return CaseLifecycleResult(
        case_id=case_record.case_id,
        case_type=case_record.case_type,
        lifecycle_status=lifecycle_status,
        fix_link_recorded=_last_fix_link(case_record) is not None,
        case_closed=case_closed,
        landing_status=None,
        landing_status_terminal=False,
        registry_status_before=lifecycle_status,
        registry_status_after=lifecycle_status,
        closure_reason=closure_reason,
        doc_binding=doc_binding,
        last_fix_link=_last_fix_link(case_record),
        next_step=_next_step(
            case_closed=case_closed,
            fix_link_recorded=_last_fix_link(case_record) is not None,
        ),
    )


def _normalize_registry_status(value: str | None) -> str | None:
    normalized = doc_utils.normalize_case_status(value)
    return normalized or None


def _canonical_reopen_case_identity(case_id: str) -> tuple[str, ReopenCaseType]:
    if not isinstance(case_id, str):
        raise CaseReopenValidationError("INVALID_CASE_ID")
    canonical_case_id = case_id.strip()
    match = _REOPEN_CASE_ID_PATTERN.fullmatch(canonical_case_id)
    if match is None:
        raise CaseReopenValidationError("INVALID_CASE_ID")
    return canonical_case_id, _case_type_for_prefix(canonical_case_id)


def _case_type_for_prefix(case_id: str) -> ReopenCaseType:
    return "bug" if case_id.startswith("BUG-") else "security"


def _normalize_doc_path(value: str) -> str:
    return str(Path(value))


def _first_matching_name(
    canonical_path: str, docs_mapping: Mapping[str, str]
) -> str | None:
    for name, candidate_path in docs_mapping.items():
        if _normalize_doc_path(candidate_path) == canonical_path:
            return name
    return None


def _alias_kind(
    name: str,
    canonical_name: str,
    preferred_doc_name: str | None,
) -> CanonicalDocAliasKind:
    if name == canonical_name:
        return "primary"
    if preferred_doc_name is not None and name == preferred_doc_name:
        return "caller_alias"
    if "/" in name or name.endswith(".md"):
        return "path_alias"
    return "legacy_compat"


def _aliases_from_metadata(
    value: object, canonical_path: str
) -> tuple[CanonicalDocAlias, ...]:
    if not isinstance(value, list):
        return ()
    aliases: list[CanonicalDocAlias] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        alias = _string_or_none(item.get("alias"))
        alias_kind = _alias_kind_from_value(item.get("alias_kind"))
        doc_path = _string_or_none(item.get("doc_path")) or canonical_path
        if alias is None:
            continue
        aliases.append(
            CanonicalDocAlias(
                alias=alias,
                alias_kind=alias_kind,
                doc_path=_normalize_doc_path(doc_path),
            )
        )
    return tuple(aliases)


def _alias_kind_from_value(value: object) -> CanonicalDocAliasKind:
    if value in {"primary", "caller_alias", "legacy_compat", "path_alias"}:
        return value
    return "legacy_compat"


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _last_fix_link(case_record: CaseRegistryRecord) -> dict[str, object] | None:
    metadata = case_record.metadata
    if not isinstance(metadata, Mapping):
        return None
    fix_link = metadata.get("fix_link")
    if not isinstance(fix_link, Mapping):
        return None
    return {str(key): value for key, value in fix_link.items()}


def _next_step(
    *,
    case_closed: bool,
    fix_link_recorded: bool,
    landing_status_terminal: bool = False,
    doc_update_warning: str | None = None,
) -> str:
    if doc_update_warning:
        return f"Review case report update warning: {doc_update_warning}"
    if case_closed:
        return "Case is terminal; no follow-up required."
    if fix_link_recorded:
        if landing_status_terminal:
            return (
                "Fix link recorded with terminal landing_status, but registry close readback "
                "is missing or still open; retry link_fix after the case registry backend is current."
            )
        return "Fix link recorded; provide a terminal landing_status to close the case."
    return "No fix link recorded; record fix evidence or keep the case open for investigation."
