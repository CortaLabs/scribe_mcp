"""Composite, lock-ordered transaction boundary for managed-document rehome."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from scribe_mcp.doc_management.manager import MutationLockTarget, document_mutation_locks


_RECOVERY_REQUIRED = "APPLY_RECEIPT_RECOVERY_REQUIRED"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping_digest(mapping: Mapping[str, object]) -> str:
    encoded = json.dumps(mapping, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _authority_digest(project: Mapping[str, object]) -> str:
    return _mapping_digest(
        {
            key: project.get(key)
            for key in ("name", "root", "docs_dir")
        }
    )


@dataclass(frozen=True)
class RehomeCompositeBinding:
    """All authority, path, registry, index, and file preimages for one rehome."""

    source_project: str
    target_project: str
    source_repo_root: str
    target_repo_root: str
    source_docs_dir: str
    target_docs_dir: str
    source_doc_keys: tuple[str, ...]
    target_doc_key: str
    source_path: str
    target_path: str
    move: bool
    overwrite: bool
    source_sha256: str
    target_sha256: str | None
    source_registry_digest: str
    target_registry_digest: str
    index_paths: tuple[str, ...]
    source_authority_digest: str = ""
    target_authority_digest: str = ""
    source_registry_after_digest: str = ""
    target_registry_after_digest: str = ""
    index_preimages: tuple[tuple[str, str | None], ...] = ()

    @property
    def lock_targets(self) -> tuple[MutationLockTarget, ...]:
        targets = [
            MutationLockTarget(repo_root=self.source_repo_root, path=self.source_path),
            MutationLockTarget(repo_root=self.target_repo_root, path=self.target_path),
        ]
        for path in self.index_paths:
            resolved = Path(path).expanduser().resolve()
            root = (
                self.source_repo_root
                if resolved.is_relative_to(Path(self.source_repo_root).resolve())
                else self.target_repo_root
            )
            targets.append(MutationLockTarget(repo_root=root, path=resolved))
        return tuple(targets)

    def as_storage_payload(self) -> dict[str, object]:
        return {
            "source_project": self.source_project,
            "target_project": self.target_project,
            "source_repo_root": self.source_repo_root,
            "target_repo_root": self.target_repo_root,
            "source_docs_dir": self.source_docs_dir,
            "target_docs_dir": self.target_docs_dir,
            "source_doc_keys": list(self.source_doc_keys),
            "target_doc_key": self.target_doc_key,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "move": self.move,
            "overwrite": self.overwrite,
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
            "source_registry_digest": self.source_registry_digest,
            "target_registry_digest": self.target_registry_digest,
            "index_paths": list(self.index_paths),
            "source_authority_digest": self.source_authority_digest,
            "target_authority_digest": self.target_authority_digest,
            "source_registry_after_digest": self.source_registry_after_digest,
            "target_registry_after_digest": self.target_registry_after_digest,
            "index_preimages": [list(item) for item in self.index_preimages],
        }

    @classmethod
    def from_storage_payload(cls, payload: object) -> RehomeCompositeBinding:
        """Restore one server-retained binding without accepting shape drift."""

        if not isinstance(payload, Mapping):
            raise ValueError("stored rehome binding must be an object")
        values = dict(payload)
        try:
            source_doc_keys = values.pop("source_doc_keys")
            index_paths = values.pop("index_paths")
            index_preimages = values.pop("index_preimages")
        except KeyError as exc:
            raise ValueError("stored rehome binding is incomplete") from exc
        if not isinstance(source_doc_keys, list) or not all(
            isinstance(item, str) for item in source_doc_keys
        ):
            raise ValueError("stored rehome source keys are invalid")
        if not isinstance(index_paths, list) or not all(
            isinstance(item, str) for item in index_paths
        ):
            raise ValueError("stored rehome index paths are invalid")
        if not isinstance(index_preimages, list):
            raise ValueError("stored rehome index preimages are invalid")
        parsed_preimages: list[tuple[str, str | None]] = []
        for item in index_preimages:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or not isinstance(item[0], str)
                or (item[1] is not None and not isinstance(item[1], str))
            ):
                raise ValueError("stored rehome index preimage is invalid")
            parsed_preimages.append((item[0], item[1]))
        expected_names = {
            field_name
            for field_name in cls.__dataclass_fields__
            if field_name not in {"source_doc_keys", "index_paths", "index_preimages"}
        }
        if set(values) != expected_names:
            raise ValueError("stored rehome binding fields are invalid")
        return cls(
            **values,
            source_doc_keys=tuple(source_doc_keys),
            index_paths=tuple(index_paths),
            index_preimages=tuple(parsed_preimages),
        )


def capture_rehome_binding(
    *,
    source_project: Mapping[str, object],
    target_project: Mapping[str, object],
    source_doc_keys: Sequence[str],
    target_doc_key: str,
    source_path: Path,
    target_path: Path,
    move: bool,
    overwrite: bool,
    index_paths: Sequence[Path] = (),
    source_registry_after: Mapping[str, object] | None = None,
    target_registry_after: Mapping[str, object] | None = None,
) -> RehomeCompositeBinding:
    """Capture a deterministic composite preimage before preview or mutation."""

    source_path = source_path.expanduser().resolve()
    target_path = target_path.expanduser().resolve()
    source_sha = _sha256(source_path)
    if source_sha is None:
        raise ValueError("rehome source must exist when its binding is captured")
    resolved_index_paths = tuple(
        str(Path(path).expanduser().resolve()) for path in index_paths
    )
    source_registry = (
        source_project.get("docs")
        if isinstance(source_project.get("docs"), Mapping)
        else {}
    )
    target_registry = (
        target_project.get("docs")
        if isinstance(target_project.get("docs"), Mapping)
        else {}
    )
    return RehomeCompositeBinding(
        source_project=str(source_project.get("name") or ""),
        target_project=str(target_project.get("name") or ""),
        source_repo_root=str(Path(str(source_project.get("root") or "")).resolve()),
        target_repo_root=str(Path(str(target_project.get("root") or "")).resolve()),
        source_docs_dir=str(Path(str(source_project.get("docs_dir") or "")).resolve()),
        target_docs_dir=str(Path(str(target_project.get("docs_dir") or "")).resolve()),
        source_doc_keys=tuple(str(key) for key in source_doc_keys),
        target_doc_key=str(target_doc_key),
        source_path=str(source_path),
        target_path=str(target_path),
        move=bool(move),
        overwrite=bool(overwrite),
        source_sha256=source_sha,
        target_sha256=_sha256(target_path),
        source_registry_digest=_mapping_digest(source_registry),
        target_registry_digest=_mapping_digest(target_registry),
        index_paths=resolved_index_paths,
        source_authority_digest=_authority_digest(source_project),
        target_authority_digest=_authority_digest(target_project),
        source_registry_after_digest=_mapping_digest(
            source_registry if source_registry_after is None else source_registry_after
        ),
        target_registry_after_digest=_mapping_digest(
            target_registry if target_registry_after is None else target_registry_after
        ),
        index_preimages=tuple(
            (path, _sha256(Path(path))) for path in resolved_index_paths
        ),
    )


def _classify_file_state(binding: RehomeCompositeBinding) -> str:
    source_sha = _sha256(Path(binding.source_path))
    target_sha = _sha256(Path(binding.target_path))
    before = source_sha == binding.source_sha256 and target_sha == binding.target_sha256
    after = target_sha == binding.source_sha256 and (
        source_sha is None if binding.move else source_sha == binding.source_sha256
    )
    partial = binding.move and source_sha == binding.source_sha256 and target_sha == binding.source_sha256
    if before:
        return "BEFORE"
    if after:
        return "AFTER"
    if partial:
        return "PARTIAL"
    return "OTHER"


def classify_rehome_transaction_state(
    binding: RehomeCompositeBinding,
    *,
    source_project: Mapping[str, object] | None = None,
    target_project: Mapping[str, object] | None = None,
) -> str:
    """Classify the complete immutable binding as BEFORE/AFTER/PARTIAL/OTHER."""

    file_state = _classify_file_state(binding)
    if source_project is None or target_project is None:
        return file_state
    if (
        not binding.source_authority_digest
        or not binding.target_authority_digest
        or _authority_digest(source_project) != binding.source_authority_digest
        or _authority_digest(target_project) != binding.target_authority_digest
    ):
        return "OTHER"
    source_docs = (
        source_project.get("docs")
        if isinstance(source_project.get("docs"), Mapping)
        else {}
    )
    target_docs = (
        target_project.get("docs")
        if isinstance(target_project.get("docs"), Mapping)
        else {}
    )
    registry_digests = (_mapping_digest(source_docs), _mapping_digest(target_docs))
    registry_before = registry_digests == (
        binding.source_registry_digest,
        binding.target_registry_digest,
    )
    registry_after = registry_digests == (
        binding.source_registry_after_digest,
        binding.target_registry_after_digest,
    )
    registry_partial = all(
        current in {before, after}
        for current, before, after in zip(
            registry_digests,
            (binding.source_registry_digest, binding.target_registry_digest),
            (
                binding.source_registry_after_digest,
                binding.target_registry_after_digest,
            ),
            strict=True,
        )
    )
    indexes_before = all(
        _sha256(Path(path)) == expected for path, expected in binding.index_preimages
    )
    if file_state == "BEFORE" and registry_before and indexes_before:
        return "BEFORE"
    if file_state == "BEFORE" and registry_before:
        return "OTHER"
    if file_state == "AFTER" and registry_after:
        return "AFTER"
    if (
        file_state in {"BEFORE", "PARTIAL", "AFTER"}
        and registry_partial
        and indexes_before
    ):
        return "PARTIAL"
    return "OTHER"


async def execute_rehome_transaction(
    binding: RehomeCompositeBinding,
    *,
    operation: Callable[[], Awaitable[dict[str, object]]],
    receipt_fence: int | None = None,
    locks_already_held: bool = False,
    source_project: Mapping[str, object] | None = None,
    target_project: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Execute once under the complete deterministic lock set, or fail closed."""

    del receipt_fence  # Fence ownership is enforced by the durable receipt service.
    @asynccontextmanager
    async def _existing_lock_scope():
        yield

    lock_scope = (
        _existing_lock_scope()
        if locks_already_held
        else document_mutation_locks(binding.lock_targets)
    )
    async with lock_scope:
        state = classify_rehome_transaction_state(
            binding,
            source_project=source_project,
            target_project=target_project,
        )
        if state == "AFTER":
            return {"ok": True, "code": "APPLY_RECEIPT_REPLAYED", "replayed": True}
        if state == "OTHER":
            return {"ok": False, "code": _RECOVERY_REQUIRED, "recovery_state": state}
        try:
            result = await operation()
        except Exception:
            return {
                "ok": False,
                "code": _RECOVERY_REQUIRED,
                "recovery_state": classify_rehome_transaction_state(
                    binding,
                    source_project=source_project,
                    target_project=target_project,
                ),
            }
        if not isinstance(result, dict) or result.get("ok") is False:
            return result
        final_state = classify_rehome_transaction_state(
            binding,
            source_project=source_project,
            target_project=target_project,
        )
        if final_state != "AFTER":
            return {
                "ok": False,
                "code": _RECOVERY_REQUIRED,
                "recovery_state": final_state,
            }
        return result


async def recover_rehome_transaction(
    binding: RehomeCompositeBinding,
    *,
    operation: Callable[[], Awaitable[dict[str, object]]],
    receipt_fence: int | None = None,
    locks_already_held: bool = False,
    source_project: Mapping[str, object] | None = None,
    target_project: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Re-enter the same composite executor for a fenced recovery attempt."""

    return await execute_rehome_transaction(
        binding,
        operation=operation,
        receipt_fence=receipt_fence,
        locks_already_held=locks_already_held,
        source_project=source_project,
        target_project=target_project,
    )


__all__ = [
    "RehomeCompositeBinding",
    "capture_rehome_binding",
    "classify_rehome_transaction_state",
    "execute_rehome_transaction",
    "recover_rehome_transaction",
]
