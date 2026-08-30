"""Server-only issuance and fenced execution for apply-preview receipts."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from scribe_mcp.doc_management.manager import MutationLockTarget, document_mutation_locks
from scribe_mcp.shared.write_barrier import WriteBarrierError, assert_writes_allowed
from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.storage.models import ApplyPreviewClaimResult, ApplyPreviewReceiptRecord


logger = logging.getLogger(__name__)

_RECEIPT_VERSION = 1
_DEFAULT_TTL_SECONDS = 600
_HARD_MAX_TTL_SECONDS = 1800
_DEFAULT_CLAIM_LEASE_SECONDS = 60
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SCOPE_FIELDS = ("principal_id", "session_id", "run_id", "project_key", "repo_id")


class ApplyPreviewError(RuntimeError):
    """Fail-closed issuance error whose message never includes secret context."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ApplyPreviewAffordance:
    """The only public data emitted by successful receipt issuance."""

    receipt: str = field(repr=False)
    expires_at: str
    action: str = "apply_preview"

    def as_public_dict(self) -> dict[str, str]:
        return {
            "action": self.action,
            "receipt": self.receipt,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ApplyPreviewBinding:
    """Verified scope and target identity captured with one successful preview."""

    principal_id: str = field(repr=False)
    session_id: str = field(repr=False)
    run_id: str = field(repr=False)
    project_key: str = field(repr=False)
    repo_id: str = field(repr=False)
    repo_root: str = field(repr=False)
    targets: Sequence[MutationLockTarget] = field(repr=False)
    target_binding: Mapping[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        for name in _SCOPE_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty verified identifier")
        root = Path(self.repo_root).expanduser().resolve()
        canonical_targets = tuple(
            target
            if isinstance(target, MutationLockTarget)
            else MutationLockTarget(**target)  # type: ignore[arg-type]
            for target in self.targets
        )
        if not canonical_targets:
            raise ValueError("binding must contain at least one mutation target")
        if not isinstance(self.target_binding, Mapping) or not self.target_binding:
            raise ValueError("target_binding must be a non-empty mapping")
        object.__setattr__(self, "repo_root", str(root))
        object.__setattr__(self, "targets", canonical_targets)

    def storage_payload(self) -> dict[str, object]:
        return {
            "repo_root": self.repo_root,
            "target": _json_value(self.target_binding),
            "targets": [
                {"repo_root": target.repo_root, "path": target.path}
                for target in self.targets
            ],
        }


class RetainedIntentExecutor(Protocol):
    """Normal mutation-path hooks required for apply-time revalidation."""

    async def authorize_apply_preview(
        self, *, execution_context: object, binding: Mapping[str, object]
    ) -> bool: ...

    async def resolve_apply_preview_targets(
        self, *, execution_context: object, binding: Mapping[str, object]
    ) -> Sequence[MutationLockTarget]: ...

    async def inspect_apply_preview_state(
        self, *, execution_context: object, binding: Mapping[str, object]
    ) -> Mapping[str, object]: ...

    async def execute_retained_intent(
        self,
        *,
        action: str,
        normalized_intent: Mapping[str, object],
        execution_context: object,
        binding: Mapping[str, object],
        fence: int,
    ) -> Mapping[str, object]: ...


def _json_value(value: object) -> object:
    """Return a detached, canonical-JSON-compatible value or fail closed."""

    try:
        return json.loads(
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("apply-preview payload must be canonical JSON data") from exc


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    normalized = _json_value(value)
    if not isinstance(normalized, dict):
        raise ValueError("apply-preview payload must be a JSON object")
    return normalized


def _encode_json(value: Mapping[str, object]) -> str:
    return json.dumps(_json_object(value), sort_keys=True, separators=(",", ":"))


def _decode_json_object(value: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored apply-preview value is not an object")
    return decoded


def _context_value(context: object, name: str) -> str:
    if isinstance(context, Mapping):
        value = context.get(name)
    else:
        value = getattr(context, name, None)
    return value.strip() if isinstance(value, str) else ""


def _public_result(code: str, *, replayed: bool = False) -> dict[str, object]:
    return {"ok": code in {"APPLY_RECEIPT_APPLIED", "APPLY_RECEIPT_REPLAYED"}, "code": code, "replayed": replayed}


def _success_result(*, correlation_id: str, replayed: bool) -> dict[str, object]:
    code = "APPLY_RECEIPT_REPLAYED" if replayed else "APPLY_RECEIPT_APPLIED"
    return {
        "ok": True,
        "code": code,
        "replayed": replayed,
        "audit_correlation_id": correlation_id,
    }


class ApplyPreviewService:
    """Issue opaque receipts and execute their retained intent at most once."""

    def __init__(
        self,
        storage: StorageBackend,
        *,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_ttl_seconds: int = _HARD_MAX_TTL_SECONDS,
        claim_lease_seconds: int = _DEFAULT_CLAIM_LEASE_SECONDS,
    ) -> None:
        for name, value in (
            ("ttl_seconds", ttl_seconds),
            ("max_ttl_seconds", max_ttl_seconds),
            ("claim_lease_seconds", claim_lease_seconds),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self._storage = storage
        self._max_ttl_seconds = min(max_ttl_seconds, _HARD_MAX_TTL_SECONDS)
        self._ttl_seconds = min(ttl_seconds, self._max_ttl_seconds)
        self._claim_lease_seconds = claim_lease_seconds

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(ttl_seconds={self._ttl_seconds}, "
            f"max_ttl_seconds={self._max_ttl_seconds}, "
            f"claim_lease_seconds={self._claim_lease_seconds})"
        )

    async def issue(
        self,
        *,
        action: str,
        normalized_intent: Mapping[str, object],
        binding: ApplyPreviewBinding,
        precondition: Mapping[str, object],
        predicted_after: Mapping[str, object],
    ) -> ApplyPreviewAffordance:
        if not isinstance(action, str) or not action.strip() or action == "apply_preview":
            raise ApplyPreviewError("APPLY_RECEIPT_INAPPLICABLE")
        intent = _json_object(normalized_intent)
        before = _json_object(precondition)
        after = _json_object(predicted_after)
        if not intent or not before or not after:
            raise ApplyPreviewError("APPLY_RECEIPT_INAPPLICABLE")

        token = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
        token_sha256 = hashlib.sha256(token.encode("ascii")).hexdigest()
        issued_at = datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        correlation_id = uuid.uuid4().hex
        record = ApplyPreviewReceiptRecord(
            token_sha256=token_sha256,
            receipt_version=_RECEIPT_VERSION,
            state="issued",
            principal_id=binding.principal_id,
            session_id=binding.session_id,
            run_id=binding.run_id,
            project_key=binding.project_key,
            repo_id=binding.repo_id,
            action=action.strip(),
            normalized_intent_json=_encode_json(intent),
            target_binding_json=_encode_json(binding.storage_payload()),
            precondition_json=_encode_json(before),
            predicted_after_json=_encode_json(after),
            issued_at=issued_at,
            expires_at=expires_at,
            fence=0,
            apply_lease_expires_at=None,
            terminal_result_code=None,
            terminal_result_json=None,
            terminal_at=None,
            audit_correlation_id=correlation_id,
            updated_at=issued_at,
        )
        try:
            persisted = await self._storage.issue_apply_preview_receipt(record)
        except Exception:
            raise ApplyPreviewError("APPLY_RECEIPT_STORAGE_UNAVAILABLE") from None
        if persisted != record:
            raise ApplyPreviewError("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
        logger.info(
            "Apply-preview receipt issued",
            extra={
                "event_type": "preview_receipt_issued",
                "service": "scribe_mcp",
                "summary": "server-retained mutation preview issued",
                "correlation_id": correlation_id,
                "action": record.action,
                "receipt_version": record.receipt_version,
            },
        )
        return ApplyPreviewAffordance(receipt=token, expires_at=expires_at.isoformat())

    async def apply(
        self,
        *,
        receipt: str,
        execution_context: object,
        executor: RetainedIntentExecutor,
    ) -> dict[str, object]:
        if not isinstance(receipt, str) or _TOKEN_PATTERN.fullmatch(receipt) is None:
            return _public_result("APPLY_RECEIPT_INVALID")
        token_sha256 = hashlib.sha256(receipt.encode("ascii")).hexdigest()
        try:
            record = await self._storage.fetch_apply_preview_receipt(token_sha256)
        except Exception:
            return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
        if record is None or record.token_sha256 != token_sha256:
            return _public_result("APPLY_RECEIPT_INVALID")
        if record.receipt_version != _RECEIPT_VERSION:
            return _public_result("APPLY_RECEIPT_INVALID")
        if record.expires_at <= datetime.now(timezone.utc) and record.state not in {
            "applied",
            "failed_terminal",
        }:
            return _public_result("APPLY_RECEIPT_EXPIRED")
        if not self._scope_matches(record, execution_context):
            return _public_result("APPLY_RECEIPT_SCOPE_MISMATCH")

        try:
            binding = _decode_json_object(record.target_binding_json)
            normalized_intent = _decode_json_object(record.normalized_intent_json)
            precondition = _decode_json_object(record.precondition_json)
            predicted_after = _decode_json_object(record.predicted_after_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            return _public_result("APPLY_RECEIPT_INVALID")

        preflight_code, expected_targets = await self._preflight(
            record=record,
            binding=binding,
            execution_context=execution_context,
            executor=executor,
        )
        if preflight_code is not None:
            return _public_result(preflight_code)

        try:
            claim = await self._storage.claim_apply_preview_receipt(
                token_sha256, lease_seconds=self._claim_lease_seconds
            )
        except Exception:
            return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
        claim_code = self._claim_outcome(claim)
        if claim_code is not None:
            if claim.status == "terminal" and claim.record is not None:
                return self._terminal_replay(claim.record)
            return _public_result(claim_code)
        claimed = claim.record
        if claimed is None or claimed.token_sha256 != token_sha256:
            return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")

        try:
            async with document_mutation_locks(expected_targets):
                recheck_code, current_targets = await self._preflight(
                    record=claimed,
                    binding=binding,
                    execution_context=execution_context,
                    executor=executor,
                )
                if recheck_code is not None or self._target_identities(
                    current_targets
                ) != self._target_identities(expected_targets):
                    return await self._finalize_failure(
                        claimed,
                        recheck_code or "APPLY_RECEIPT_TARGET_DRIFT",
                    )
                current = _json_object(
                    await executor.inspect_apply_preview_state(
                        execution_context=execution_context, binding=binding
                    )
                )
                if claim.status == "recovery" and current == predicted_after:
                    finalized, finalize_error = await self._finalize_success(claimed)
                    if finalize_error is not None:
                        return _public_result(finalize_error)
                    if finalized is None:
                        return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
                    result = _success_result(
                        correlation_id=claimed.audit_correlation_id, replayed=True
                    )
                    self._log_result(claimed, result)
                    return result
                recoverable_partial = (
                    claim.status == "recovery"
                    and current == {"rehome_state": "PARTIAL"}
                    and isinstance(binding.get("target"), dict)
                    and "rehome" in binding["target"]
                )
                if current != precondition and not recoverable_partial:
                    code = (
                        "APPLY_RECEIPT_RECOVERY_REQUIRED"
                        if claim.status == "recovery"
                        else "APPLY_RECEIPT_TARGET_DRIFT"
                    )
                    return await self._finalize_failure(claimed, code)
                execution_result = _json_object(
                    await executor.execute_retained_intent(
                        action=claimed.action,
                        normalized_intent=normalized_intent,
                        execution_context=execution_context,
                        binding=binding,
                        fence=claimed.fence,
                    )
                )
                if execution_result.get("ok") is False:
                    code = execution_result.get("code")
                    return await self._finalize_failure(
                        claimed,
                        code
                        if isinstance(code, str) and code.startswith("APPLY_RECEIPT_")
                        else "APPLY_RECEIPT_RECOVERY_REQUIRED",
                    )
                observed_after = _json_object(
                    await executor.inspect_apply_preview_state(
                        execution_context=execution_context, binding=binding
                    )
                )
                if observed_after != predicted_after:
                    return await self._finalize_failure(
                        claimed, "APPLY_RECEIPT_TARGET_DRIFT"
                    )
                finalized, finalize_error = await self._finalize_success(claimed)
                if finalize_error is not None:
                    return _public_result(finalize_error)
                if finalized is None:
                    return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
        except (WriteBarrierError, PermissionError):
            return await self._finalize_failure(claimed, "APPLY_RECEIPT_POLICY_DENIED")
        except Exception:
            return await self._finalize_failure(
                claimed, "APPLY_RECEIPT_RECOVERY_REQUIRED"
            )

        result = _success_result(correlation_id=claimed.audit_correlation_id, replayed=False)
        self._log_result(claimed, result)
        return result

    def _scope_matches(self, record: ApplyPreviewReceiptRecord, context: object) -> bool:
        return all(_context_value(context, name) == getattr(record, name) for name in _SCOPE_FIELDS)

    async def _preflight(
        self,
        *,
        record: ApplyPreviewReceiptRecord,
        binding: Mapping[str, object],
        execution_context: object,
        executor: RetainedIntentExecutor,
    ) -> tuple[str | None, tuple[MutationLockTarget, ...]]:
        repo_root = _context_value(execution_context, "repo_root")
        if not repo_root:
            return "APPLY_RECEIPT_SCOPE_MISMATCH", ()
        bound_root = binding.get("repo_root")
        if not isinstance(bound_root, str) or Path(repo_root).expanduser().resolve() != Path(
            bound_root
        ).expanduser().resolve():
            return "APPLY_RECEIPT_SCOPE_MISMATCH", ()
        try:
            assert_writes_allowed(Path(repo_root), operation_label="apply_preview")
            authorized = await executor.authorize_apply_preview(
                execution_context=execution_context, binding=binding
            )
            if not authorized:
                return "APPLY_RECEIPT_POLICY_DENIED", ()
            resolved = tuple(
                target
                if isinstance(target, MutationLockTarget)
                else MutationLockTarget(**target)  # type: ignore[arg-type]
                for target in await executor.resolve_apply_preview_targets(
                    execution_context=execution_context, binding=binding
                )
            )
            expected = self._expected_targets(binding)
        except (WriteBarrierError, PermissionError):
            return "APPLY_RECEIPT_POLICY_DENIED", ()
        except Exception:
            return "APPLY_RECEIPT_POLICY_DENIED", ()
        if not resolved or self._target_identities(resolved) != self._target_identities(expected):
            return "APPLY_RECEIPT_TARGET_DRIFT", ()
        return None, resolved

    @staticmethod
    def _target_identities(targets: Sequence[MutationLockTarget]) -> frozenset[str]:
        return frozenset(target.lock_identity for target in targets)

    @staticmethod
    def _expected_targets(binding: Mapping[str, object]) -> tuple[MutationLockTarget, ...]:
        raw_targets = binding.get("targets")
        if not isinstance(raw_targets, list):
            raise ValueError("stored target list is invalid")
        targets: list[MutationLockTarget] = []
        for item in raw_targets:
            if not isinstance(item, dict):
                raise ValueError("stored target is invalid")
            root = item.get("repo_root")
            path = item.get("path")
            if not isinstance(root, str) or not isinstance(path, str):
                raise ValueError("stored target identity is invalid")
            targets.append(MutationLockTarget(repo_root=root, path=path))
        return tuple(targets)

    @staticmethod
    def _claim_outcome(claim: ApplyPreviewClaimResult) -> str | None:
        return {
            "terminal": "APPLY_RECEIPT_REPLAYED",
            "busy": "APPLY_RECEIPT_BUSY",
            "expired": "APPLY_RECEIPT_EXPIRED",
            "not_found": "APPLY_RECEIPT_INVALID",
        }.get(claim.status)

    @staticmethod
    def _terminal_replay(record: ApplyPreviewReceiptRecord) -> dict[str, object]:
        if record.state == "applied":
            return _success_result(correlation_id=record.audit_correlation_id, replayed=True)
        code = record.terminal_result_code or "APPLY_RECEIPT_RECOVERY_REQUIRED"
        return _public_result(code, replayed=True)

    async def _finalize_success(
        self, record: ApplyPreviewReceiptRecord
    ) -> tuple[ApplyPreviewReceiptRecord | None, str | None]:
        result = _success_result(correlation_id=record.audit_correlation_id, replayed=False)
        try:
            return (
                await self._storage.finalize_apply_preview_receipt(
                    record.token_sha256,
                    fence=record.fence,
                    terminal_state="applied",
                    result_code="APPLY_RECEIPT_APPLIED",
                    result_json=_encode_json(result),
                ),
                None,
            )
        except LookupError:
            return None, "APPLY_RECEIPT_RECOVERY_REQUIRED"
        except Exception:
            return None, "APPLY_RECEIPT_STORAGE_UNAVAILABLE"

    async def _finalize_failure(
        self, record: ApplyPreviewReceiptRecord, code: str
    ) -> dict[str, object]:
        result = _public_result(code)
        if code == "APPLY_RECEIPT_RECOVERY_REQUIRED":
            self._log_result(record, result)
            return result
        try:
            await self._storage.finalize_apply_preview_receipt(
                record.token_sha256,
                fence=record.fence,
                terminal_state="failed_terminal",
                result_code=code,
                result_json=_encode_json(result),
            )
        except LookupError:
            return _public_result("APPLY_RECEIPT_RECOVERY_REQUIRED")
        except Exception:
            return _public_result("APPLY_RECEIPT_STORAGE_UNAVAILABLE")
        self._log_result(record, result)
        return result

    @staticmethod
    def _log_result(record: ApplyPreviewReceiptRecord, result: Mapping[str, object]) -> None:
        logger.info(
            "Apply-preview receipt result recorded",
            extra={
                "event_type": "preview_receipt_apply_result",
                "service": "scribe_mcp",
                "summary": str(result.get("code") or "apply receipt result"),
                "correlation_id": record.audit_correlation_id,
                "action": record.action,
                "receipt_version": record.receipt_version,
                "fence": record.fence,
                "replayed": bool(result.get("replayed")),
            },
        )
