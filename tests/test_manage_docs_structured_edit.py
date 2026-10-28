from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import (
    DocumentOperationError,
    _apply_unified_patch,
    _apply_unified_patch_smart,
    _normalize_headers_text,
    _replace_block_text,
    apply_doc_change,
)
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.diff_compiler import compile_unified_diff


async def _setup_project(tmp_path: Path) -> dict:
    project_root = tmp_path / "structured_repo"
    docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)

    architecture_path = docs_dir / "ARCHITECTURE_GUIDE.md"
    architecture_path.write_text(
        "alpha\nbeta\ngamma\n",
        encoding="utf-8",
    )
    (docs_dir / "PHASE_PLAN.md").write_text("# Phase\n", encoding="utf-8")
    (docs_dir / "CHECKLIST.md").write_text("# Checklist\n", encoding="utf-8")
    (docs_dir / "PROGRESS_LOG.md").write_text("# Log\n", encoding="utf-8")

    return {
        "name": "Structured Project",
        "root": str(project_root),
        "docs_dir": str(docs_dir),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs": {
            "architecture": str(architecture_path),
            "phase_plan": str(docs_dir / "PHASE_PLAN.md"),
            "checklist": str(docs_dir / "CHECKLIST.md"),
            "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        },
        "defaults": {"agent": "QA Bot"},
    }


@pytest.mark.asyncio
async def test_apply_structured_edit_replace_range(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_range",
            "start_line": 2,
            "end_line": 2,
            "content": "beta updated\n",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    assert change.extra.get("hunks_applied", 0) >= 0
    updated = architecture_path.read_text(encoding="utf-8")
    assert "beta updated" in updated


@pytest.mark.asyncio
async def test_structured_replace_range_with_header_content_honors_line_range(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Section A\nline a1\nline a2\n\n## Section B\nline b1\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_range",
            "start_line": 2,
            "end_line": 2,
            "content": "## Section B\n",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert change.success
    parsed = parse_frontmatter(change.content_written)
    body = parsed.body
    assert "line a1" not in body
    assert "line a2" in body
    assert "line b1" in body


@pytest.mark.asyncio
async def test_apply_structured_edit_replace_block(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Title\n**Solution Summary:** Old summary\nMore detail\n\nNext section\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success
    updated = architecture_path.read_text(encoding="utf-8")
    assert "New summary" in updated
    assert "Old summary" not in updated


@pytest.mark.asyncio
async def test_replace_block_ignores_code_fence(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "## Title\n```\n**Solution Summary:** Old summary\n```\n",
        encoding="utf-8",
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not change.success
    assert "STRUCTURED_EDIT_ANCHOR_NOT_FOUND" in (change.error_message or "")


@pytest.mark.asyncio
async def test_replace_block_ambiguous_anchor(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    progress_log_path = Path(project["docs"]["progress_log"])
    architecture_path.write_text(
        "## Title\n**Solution Summary:** One\n\n**Solution Summary:** Two\n",
        encoding="utf-8",
    )
    progress_log_path.write_text("Progress\n", encoding="utf-8")
    original_doc = architecture_path.read_text(encoding="utf-8")
    original_log = progress_log_path.read_text(encoding="utf-8")

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit={
            "type": "replace_block",
            "anchor": "**Solution Summary:**",
            "new_content": "**Solution Summary:** New summary",
        },
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert not change.success
    error_message = change.error_message or ""
    assert "STRUCTURED_EDIT_ANCHOR_AMBIGUOUS" in error_message
    assert "matches: [line 2, line 4]" in error_message
    assert change.diff_preview == ""
    assert architecture_path.read_text(encoding="utf-8") == original_doc
    assert progress_log_path.read_text(encoding="utf-8") == original_log


@pytest.mark.asyncio
async def test_normalize_headers_idempotent_and_skip_fences(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    architecture_path.write_text(
        "# Title\n## Subtitle\n```\n## 3. Code Block\n```\n### Third\n",
        encoding="utf-8",
    )

    first = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )
    assert first.success
    parsed_first = parse_frontmatter(architecture_path.read_text(encoding="utf-8"))
    assert "# 1 Title" in parsed_first.body
    assert "## 1.1 Subtitle" in parsed_first.body
    assert "### 1.1.1 Third" in parsed_first.body
    assert "## 3. Code Block" in parsed_first.body

    second = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )
    assert second.success
    assert second.diff_preview == ""


@pytest.mark.asyncio
async def test_normalize_headers_guardrail_rejects_non_atx_promotions(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    architecture_path = Path(project["docs"]["architecture"])
    original = (
        "- Keep this section updated before each implementation phase.\n"
        "---\n"
        "No optimization patches until functional parity is complete.\n"
        "---\n"
        "- [ ] Stakeholder sign-off recorded in PROGRESS_LOG.md\n"
        "---\n"
        "# Valid Header\n"
    )
    architecture_path.write_text(original, encoding="utf-8")

    result = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert not result.success
    assert "NORMALIZE_HEADERS_GUARDRAIL" in (result.error_message or "")
    assert result.extra.get("guardrail") == "non_atx_promotion"
    violations = result.extra.get("violations") or []
    assert violations
    assert architecture_path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_normalize_headers_invalid_doc_fails(tmp_path: Path) -> None:
    project = await _setup_project(tmp_path)
    result = await apply_doc_change(
        project,
        doc="missing_doc_key",
        action="normalize_headers",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=None,
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=True,
    )

    assert not result.success
    error_message = result.error_message or ""
    assert "DOC_NOT_FOUND" in error_message


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["normalize_headers", "replace_block"])
@pytest.mark.parametrize("separator", ["\u2028", "\u2029"], ids=["U2028", "U2029"])
@pytest.mark.parametrize("fence", ["```", "~~~"], ids=["backtick", "tilde"])
async def test_structured_edits_preserve_unicode_literal_bytes(
    tmp_path: Path, operation: str, separator: str, fence: str, test_agent: str
) -> None:
    project = await _setup_project(tmp_path)
    project["defaults"]["agent"] = test_agent
    architecture_path = Path(project["docs"]["architecture"])
    literal = (
        f"{fence}text\nalpha{separator}beta{separator}## Literal header\n"
        f"\\{fence}\n**Target:** fenced anchor\n{fence}\n"
    )
    old_block = "**Target:** Old summary\nOld detail"
    new_block = f"**Target:** New{separator}summary\nNew detail"
    original = (
        f"# Title\nBefore untouched{separator}neighbor\n\n{literal}\n"
        f"{old_block}\n\nAfter untouched{separator}neighbor\n"
    )
    architecture_path.write_bytes(original.encode("utf-8"))
    expected = (
        original.replace("# Title", "# 1 Title", 1)
        if operation == "normalize_headers"
        else original.replace(old_block, new_block, 1)
    )

    change = await apply_doc_change(
        project,
        doc="architecture",
        action="normalize_headers" if operation == "normalize_headers" else "apply_patch",
        section=None,
        content=None,
        patch=None,
        patch_source_hash=None,
        edit=(
            {"type": "replace_block", "anchor": "**Target:**", "new_content": new_block}
            if operation == "replace_block"
            else None
        ),
        start_line=None,
        end_line=None,
        template=None,
        metadata={},
        dry_run=False,
    )

    assert change.success, change.error_message
    updated_bytes = architecture_path.read_bytes()
    literal_bytes = literal.encode("utf-8")
    assert literal_bytes in updated_bytes
    assert hashlib.sha256(updated_bytes).hexdigest() == hashlib.sha256(
        expected.encode("utf-8")
    ).hexdigest()
    assert updated_bytes == expected.encode("utf-8")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("", ""),
        ("\n", "\n"),
        ("# Title", "# 1 Title"),
        ("# Title\n", "# 1 Title\n"),
        ("# Title\r\nbody\r\n", "# 1 Title\nbody\n"),
        ("# Title\rbody\r", "# 1 Title\nbody"),
    ],
)
def test_normalize_headers_preserves_newline_conventions(
    original: str, expected: str, test_agent: str
) -> None:
    assert _normalize_headers_text(original) == expected


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("ending", ["", "\n", "\r\n", "\r"])
@pytest.mark.parametrize("replacement", ["", "Target: new\r\nNew detail\r\n"])
def test_replace_block_preserves_newline_and_empty_replacement_semantics(
    ending: str, replacement: str, test_agent: str
) -> None:
    original = "Target: old\r\nOld detail\r\n\r\nAfter" + ending
    expected = "\nAfter" if not replacement else "Target: new\nNew detail\n\nAfter"
    assert _replace_block_text(original, "Target:", replacement) == expected


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize(
    ("original", "anchor", "error"),
    [
        ("", "", "STRUCTURED_EDIT_ANCHOR_REQUIRED"),
        ("", "Target:", "STRUCTURED_EDIT_ANCHOR_NOT_FOUND"),
        ("```\nTarget: hidden\n", "Target:", "STRUCTURED_EDIT_ANCHOR_NOT_FOUND"),
        ("Target: one\n\nTarget: two", "Target:", "STRUCTURED_EDIT_ANCHOR_AMBIGUOUS"),
    ],
)
def test_replace_block_preserves_anchor_errors(
    original: str, anchor: str, error: str, test_agent: str
) -> None:
    with pytest.raises(DocumentOperationError, match=error):
        _replace_block_text(original, anchor, "replacement")


@pytest.mark.core
@pytest.mark.regression
@pytest.mark.parametrize("separator", ["\u2028", "\u2029"], ids=["U2028", "U2029"])
@pytest.mark.parametrize("smart", [False, True], ids=["strict", "smart"])
def test_compiled_structured_diff_preserves_unicode_context_and_additions(
    separator: str, smart: bool, test_agent: str
) -> None:
    before = f"```text\nalpha{separator}beta\n```\nTarget: old\n"
    after = before.replace("Target: old", f"Target: new{separator}value")
    patch = compile_unified_diff(before, after)
    apply_patch = _apply_unified_patch_smart if smart else _apply_unified_patch
    updated, hunks, *_ = apply_patch(before, patch)
    assert hunks == 1
    assert updated.encode("utf-8") == after.encode("utf-8")
