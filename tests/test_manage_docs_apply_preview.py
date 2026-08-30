from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scribe_mcp.doc_management import runtime
from scribe_mcp.doc_management.rehome_transaction import (
    RehomeCompositeBinding,
    classify_rehome_transaction_state,
    execute_rehome_transaction,
)


@pytest.mark.regression
def test_apply_preview_is_exposed_by_live_action_manifest() -> None:
    manifest = runtime.build_manage_docs_action_manifest()

    assert "apply_preview" in manifest["all_actions"]
    assert runtime.ACTION_ROUTER["apply_preview"] == "apply_preview"


@pytest.mark.regression
def test_apply_preview_request_accepts_only_opaque_metadata_receipt() -> None:
    assert runtime._validate_apply_preview_request(  # noqa: SLF001
        metadata={"receipt": "r" * 43},
        doc_name=None,
        doc_category="",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        expected_anchor_sha256=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        target_dir=None,
        project=None,
        dry_run=False,
    ) == "r" * 43

    assert runtime._validate_apply_preview_request(  # noqa: SLF001
        metadata={"receipt": "r" * 43, "content": "caller-resubmitted"},
        doc_name=None,
        doc_category="",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        expected_anchor_sha256=None,
        edit=None,
        patch_mode=None,
        start_line=None,
        end_line=None,
        template=None,
        target_dir=None,
        project=None,
        dry_run=False,
    ) is None


@pytest.mark.asyncio
@pytest.mark.regression
async def test_eligible_preview_gets_exact_compact_apply_affordance(tmp_path: Path) -> None:
    target = tmp_path / "ARCHITECTURE_GUIDE.md"
    target.write_text("before\n", encoding="utf-8")
    issued: dict[str, object] = {}

    class Service:
        async def issue(self, **kwargs: object) -> SimpleNamespace:
            issued.update(kwargs)
            return SimpleNamespace(
                as_public_dict=lambda: {
                    "action": "apply_preview",
                    "receipt": "x" * 43,
                    "expires_at": "2026-08-30T22:00:00+00:00",
                }
            )

    response = {
        "ok": True,
        "dry_run": True,
        "path": str(target),
        "sha_before": hashlib.sha256(b"before\n").hexdigest(),
        "sha_after": hashlib.sha256(b"after\n").hexdigest(),
    }
    result = await runtime._attach_apply_preview_affordance(  # noqa: SLF001
        response,
        action="replace_section",
        normalized_intent={"action": "replace_section", "doc_name": "ARCHITECTURE_GUIDE"},
        active_project={
            "name": "project",
            "project_key": "project-key",
            "repo_id": "repo-id",
            "root": str(tmp_path),
        },
        scope={
            "principal_id": "agent",
            "session_id": "session",
            "run_id": "run",
            "project_key": "project-key",
            "repo_id": "repo-id",
        },
        service=Service(),
    )

    assert result["apply"] == {
        "action": "apply_preview",
        "receipt": "x" * 43,
        "expires_at": "2026-08-30T22:00:00+00:00",
    }
    assert set(result["apply"]) == {"action", "receipt", "expires_at"}
    assert issued["action"] == "replace_section"


@pytest.mark.asyncio
@pytest.mark.regression
async def test_read_only_preview_never_issues_apply_affordance(tmp_path: Path) -> None:
    class Service:
        async def issue(self, **kwargs: object) -> SimpleNamespace:
            raise AssertionError(f"read-only preview must not issue: {kwargs}")

    response = {"ok": True, "dry_run": True, "path": str(tmp_path / "doc.md")}
    result = await runtime._attach_apply_preview_affordance(  # noqa: SLF001
        response,
        action="quality_check",
        normalized_intent={"action": "quality_check"},
        active_project={"name": "project", "root": str(tmp_path)},
        scope={},
        service=Service(),
    )

    assert "apply" not in result


@pytest.mark.asyncio
@pytest.mark.regression
async def test_rehome_composite_executor_rejects_unknown_preimage_without_mutation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    source.write_text("changed after preview", encoding="utf-8")
    called = False

    binding = RehomeCompositeBinding(
        source_project="source",
        target_project="target",
        source_repo_root=str(tmp_path),
        target_repo_root=str(tmp_path),
        source_docs_dir=str(tmp_path),
        target_docs_dir=str(tmp_path),
        source_doc_keys=("DOC",),
        target_doc_key="DOC",
        source_path=str(source),
        target_path=str(target),
        move=True,
        overwrite=False,
        source_sha256=hashlib.sha256(b"previewed source").hexdigest(),
        target_sha256=None,
        source_registry_digest="source-registry",
        target_registry_digest="target-registry",
        index_paths=(),
    )

    async def operation() -> dict[str, object]:
        nonlocal called
        called = True
        return {"ok": True}

    result = await execute_rehome_transaction(binding, operation=operation)

    assert result["ok"] is False
    assert result["code"] == "APPLY_RECEIPT_RECOVERY_REQUIRED"
    assert called is False


@pytest.mark.asyncio
@pytest.mark.regression
async def test_rehome_receipt_persists_immutable_composite_binding(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    index = tmp_path / "INDEX.md"
    source.write_text("previewed source", encoding="utf-8")
    index.write_text("previewed index", encoding="utf-8")
    source_project = {
        "name": "source",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path),
        "project_key": "source-key",
        "repo_id": "repo-id",
        "docs": {"DOC": str(source)},
    }
    target_project = {
        "name": "target",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path),
        "project_key": "target-key",
        "repo_id": "repo-id",
        "docs": {},
    }
    binding = runtime.capture_rehome_binding(
        source_project=source_project,
        target_project=target_project,
        source_doc_keys=("DOC",),
        target_doc_key="DOC",
        source_path=source,
        target_path=target,
        move=True,
        overwrite=False,
        index_paths=(index,),
        source_registry_after={},
        target_registry_after={"DOC": str(target)},
    )
    issued: dict[str, object] = {}

    class Service:
        async def issue(self, **kwargs: object) -> SimpleNamespace:
            issued.update(kwargs)
            return SimpleNamespace(
                as_public_dict=lambda: {
                    "action": "apply_preview",
                    "receipt": "x" * 43,
                    "expires_at": "2026-08-30T22:00:00+00:00",
                }
            )

    response = {
        "ok": True,
        "dry_run": True,
        "source_path": str(source),
        "target_path": str(target),
        "moved": True,
    }
    result = await runtime._attach_apply_preview_affordance(  # noqa: SLF001
        response,
        action="rehome_doc",
        normalized_intent={"action": "rehome_doc", "doc_name": "DOC"},
        active_project=source_project,
        scope={
            "principal_id": "agent",
            "session_id": "session",
            "run_id": "run",
            "project_key": "source-key",
            "repo_id": "repo-id",
        },
        service=Service(),
        rehome_binding=binding,
    )

    stored = issued["binding"].storage_payload()  # type: ignore[union-attr]
    restored = RehomeCompositeBinding.from_storage_payload(stored["target"]["rehome"])
    assert restored == binding
    assert set(result["apply"]) == {"action", "receipt", "expires_at"}
    assert "_rehome_binding" not in result
    assert binding.source_registry_digest not in repr(result)


@pytest.mark.regression
def test_rehome_composite_classification_rejects_registry_index_and_authority_drift(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    target = tmp_path / "target.md"
    index = tmp_path / "INDEX.md"
    source.write_text("previewed source", encoding="utf-8")
    index.write_text("previewed index", encoding="utf-8")
    source_project = {
        "name": "source",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path),
        "project_key": "source-key",
        "repo_id": "repo-id",
        "docs": {"DOC": str(source)},
    }
    target_project = {
        "name": "target",
        "root": str(tmp_path),
        "docs_dir": str(tmp_path),
        "project_key": "target-key",
        "repo_id": "repo-id",
        "docs": {},
    }
    binding = runtime.capture_rehome_binding(
        source_project=source_project,
        target_project=target_project,
        source_doc_keys=("DOC",),
        target_doc_key="DOC",
        source_path=source,
        target_path=target,
        move=True,
        overwrite=False,
        index_paths=(index,),
        source_registry_after={},
        target_registry_after={"DOC": str(target)},
    )

    assert classify_rehome_transaction_state(
        binding, source_project=source_project, target_project=target_project
    ) == "BEFORE"

    registry_drift = {**source_project, "docs": {"DOC": str(tmp_path / "other.md")}}
    assert classify_rehome_transaction_state(
        binding, source_project=registry_drift, target_project=target_project
    ) == "OTHER"

    index.write_text("attacker index drift", encoding="utf-8")
    assert classify_rehome_transaction_state(
        binding, source_project=source_project, target_project=target_project
    ) == "OTHER"

    index.write_text("previewed index", encoding="utf-8")
    authority_drift = {**source_project, "root": str(tmp_path / "other-root")}
    assert classify_rehome_transaction_state(
        binding, source_project=authority_drift, target_project=target_project
    ) == "OTHER"
