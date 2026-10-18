"""Focused producer-side managed-anchor CAS contract tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import (
    AnchorCASDenied,
    _managed_anchor_snapshot,
    apply_doc_change,
)


DOCUMENT = """# Alpha
<!-- ID: alpha -->
alpha body

## Beta
<!-- ID: beta -->
beta body
"""


def _project(tmp_path: Path, text: str = DOCUMENT) -> tuple[dict, Path]:
    root = tmp_path / "repo"
    docs = root / ".scribe" / "docs"
    docs.mkdir(parents=True)
    path = docs / "DOC.md"
    path.write_text(text, encoding="utf-8")
    return (
        {
            "name": "anchor-cas",
            "root": str(root),
            "docs_dir": str(docs),
            "docs": {"doc": str(path)},
        },
        path,
    )


def _digest(text: str, section: str, path: Path) -> str:
    return _managed_anchor_snapshot(text, section, path)["anchor_sha256"]


async def _replace(
    project: dict,
    section: str,
    content: str,
    digest: str,
    *,
    doc_name: str = "doc",
):
    return await apply_doc_change(
        project,
        doc_name=doc_name,
        action="replace_section",
        section=section,
        content=content,
        patch=None,
        patch_source_hash=None,
        expected_anchor_sha256=digest,
        template=None,
        metadata={},
        dry_run=False,
    )


@pytest.mark.asyncio
async def test_anchor_receipt_and_same_anchor_stale_denial(tmp_path: Path) -> None:
    project, path = _project(tmp_path)
    original = path.read_text(encoding="utf-8")
    digest = _digest(original, "alpha", path)

    change = await _replace(project, "alpha", "alpha updated", digest)

    assert change.success
    assert change.extra["anchor_id"] == "alpha"
    assert change.extra["anchor_sha256_before"] == digest
    assert len(change.extra["anchor_sha256_after"]) == 64
    assert change.extra["anchor_digest_algorithm"] == "managed_anchor_sha256_v1"
    updated = path.read_bytes()

    with pytest.raises(AnchorCASDenied, match="ANCHOR_STALE"):
        await _replace(project, "alpha", "second writer", digest)
    assert path.read_bytes() == updated


@pytest.mark.asyncio
async def test_disjoint_anchor_writers_both_succeed(tmp_path: Path) -> None:
    project, path = _project(tmp_path)
    original = path.read_text(encoding="utf-8")
    alpha_digest = _digest(original, "alpha", path)
    beta_digest = _digest(original, "beta", path)

    results = await asyncio.gather(
        _replace(project, "alpha", "alpha parallel", alpha_digest),
        _replace(project, "beta", "beta parallel", beta_digest),
        return_exceptions=True,
    )

    assert all(not isinstance(result, BaseException) for result in results)
    assert all(result.success for result in results)
    final = path.read_text(encoding="utf-8")
    assert "alpha parallel" in final
    assert "beta parallel" in final


@pytest.mark.asyncio
async def test_same_anchor_race_has_one_winner(tmp_path: Path) -> None:
    project, path = _project(tmp_path)
    original = path.read_text(encoding="utf-8")
    digest = _digest(original, "alpha", path)

    results = await asyncio.gather(
        _replace(project, "alpha", "writer one", digest),
        _replace(project, "alpha", "writer two", digest),
        return_exceptions=True,
    )

    winners = [result for result in results if not isinstance(result, BaseException)]
    denied = [result for result in results if isinstance(result, AnchorCASDenied)]
    assert len(winners) == 1
    assert winners[0].success
    assert len(denied) == 1
    assert ("writer one" in path.read_text(encoding="utf-8")) ^ (
        "writer two" in path.read_text(encoding="utf-8")
    )


@pytest.mark.asyncio
async def test_alias_race_shares_physical_document_lock(tmp_path: Path) -> None:
    project, path = _project(tmp_path)
    alias_project = {**project, "docs": {"alias": str(path)}}
    original = path.read_text(encoding="utf-8")
    digest = _digest(original, "alpha", path)

    results = await asyncio.gather(
        _replace(project, "alpha", "canonical writer", digest),
        _replace(
            alias_project,
            "alpha",
            "alias writer",
            digest,
            doc_name="alias",
        ),
        return_exceptions=True,
    )

    winners = [result for result in results if not isinstance(result, AnchorCASDenied)]
    denied = [result for result in results if isinstance(result, AnchorCASDenied)]
    assert len(winners) == 1
    assert winners[0].success
    assert len(denied) == 1
    final = path.read_text(encoding="utf-8")
    assert ("canonical writer" in final) ^ ("alias writer" in final)


@pytest.mark.asyncio
async def test_duplicate_or_moved_anchor_denies_without_mutation(tmp_path: Path) -> None:
    duplicate = DOCUMENT + "\n<!-- ID: alpha -->\ncopy\n"
    project, path = _project(tmp_path, duplicate)
    before = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_AMBIGUOUS"):
        await _replace(project, "alpha", "no write", "0" * 64)
    assert path.read_bytes() == before

    moved = DOCUMENT.replace("# Alpha\n", "Intro\n")
    project, path = _project(tmp_path / "moved", moved)
    before = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_MOVED"):
        await _replace(project, "alpha", "no write", "0" * 64)
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_malformed_anchor_denial_has_no_bytes_log_or_registry_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    malformed = DOCUMENT.replace("<!-- ID: alpha -->", "prefix <!-- ID: alpha -->")
    project, path = _project(tmp_path, malformed)
    before = path.read_bytes()
    registry_before = dict(project["docs"])

    import scribe_mcp.doc_management.manager as manager_module

    log_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        manager_module,
        "_log_operation",
        lambda *args, **kwargs: log_calls.append((args, kwargs)),
    )

    with pytest.raises(AnchorCASDenied, match="ANCHOR_MALFORMED"):
        await _replace(project, "alpha", "no write", "0" * 64)

    assert path.read_bytes() == before
    assert project["docs"] == registry_before
    assert log_calls == []


@pytest.mark.asyncio
async def test_invalid_path_cas_denial_has_no_bytes_or_registry_mutation(
    tmp_path: Path,
) -> None:
    project, _ = _project(tmp_path / "project")
    outside_path = tmp_path / "outside.md"
    outside_path.write_text(DOCUMENT, encoding="utf-8")
    project["docs"]["doc"] = str(outside_path)
    before = outside_path.read_bytes()
    registry_before = dict(project["docs"])

    result = await _replace(project, "alpha", "no write", "0" * 64)

    assert not result.success
    assert result.extra["boundary_violation"] is True
    assert outside_path.read_bytes() == before
    assert project["docs"] == registry_before


@pytest.mark.asyncio
async def test_bad_digest_and_write_crash_do_not_mutate_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project, path = _project(tmp_path)
    before = path.read_bytes()
    with pytest.raises(AnchorCASDenied, match="ANCHOR_DIGEST_INVALID"):
        await _replace(project, "alpha", "no write", "bad")
    assert path.read_bytes() == before

    import scribe_mcp.doc_management.manager as manager_module

    async def fail_write(*_args, **_kwargs):
        raise RuntimeError("simulated crash before replace")

    monkeypatch.setattr(manager_module, "async_atomic_write", fail_write)
    digest = _digest(DOCUMENT, "alpha", path)
    change = await _replace(project, "alpha", "crash", digest)
    assert not change.success
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_replace_then_crash_is_recovered_as_complete_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, path = _project(tmp_path)
    digest = _digest(DOCUMENT, "alpha", path)

    import scribe_mcp.doc_management.manager as manager_module

    async def replace_then_fail(file_path, content, **_kwargs):
        Path(file_path).write_text(content, encoding="utf-8")
        raise RuntimeError("simulated crash after replace")

    monkeypatch.setattr(manager_module, "async_atomic_write", replace_then_fail)
    change = await _replace(project, "alpha", "recovered", digest)
    assert change.success
    assert "recovered" in path.read_text(encoding="utf-8")
    assert change.extra["anchor_digest_algorithm"] == "managed_anchor_sha256_v1"


def test_manage_docs_schema_exposes_anchor_digest_without_removing_patch_hash() -> None:
    import importlib

    module = importlib.import_module("scribe_mcp.tools.manage_docs")
    properties = module._MANAGE_DOCS_INPUT_SCHEMA["properties"]
    assert properties["patch_source_hash"] == {"type": "string"}
    assert properties["expected_anchor_sha256"] == {"type": "string"}
