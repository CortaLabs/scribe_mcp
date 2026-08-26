"""replace_text must refuse an ambiguous replacement instead of deleting.

A wrong-parameter call (`content=` instead of `metadata.replace`) used to delete
the matched block and return ok/verification_passed, because an absent
`metadata.replace` was coerced to "" and `content` was never inspected. The
distinction that must survive any future fix: an *omitted* replace is an error,
while an *explicitly empty* replace is a deliberate deletion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scribe_mcp.doc_management.manager import apply_doc_change


pytestmark = [pytest.mark.asyncio, pytest.mark.regression]

DOC_BODY = "intro line\nTARGET BLOCK\noutro line\n"


def _project(tmp_path: Path) -> tuple[dict, Path]:
    docs_dir = tmp_path / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_path = docs_dir / "NOTES.md"
    doc_path.write_text(DOC_BODY, encoding="utf-8")
    project = {
        "name": "test-project",
        "root": str(tmp_path),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs_dir": str(docs_dir),
        "documents": {"NOTES.md": str(doc_path)},
        "defaults": {"agent": "test-agent"},
    }
    return project, doc_path


async def _replace_text(project: dict, *, metadata: dict, content: str | None = None):
    return await apply_doc_change(
        project,
        doc_name="NOTES.md",
        action="replace_text",
        section=None,
        content=content,
        template=None,
        metadata=metadata,
        dry_run=False,
    )


async def test_absent_replace_refuses_and_leaves_the_file_untouched(tmp_path: Path) -> None:
    project, doc_path = _project(tmp_path)

    result = await _replace_text(project, metadata={"find": "TARGET BLOCK"})

    assert result.success is False
    assert "REPLACE_TEXT_MISSING_REPLACE" in (result.error_message or "")
    # The whole point: a refusal must not be a partial edit.
    assert doc_path.read_text(encoding="utf-8") == DOC_BODY


async def test_null_replace_refuses_and_leaves_the_file_untouched(tmp_path: Path) -> None:
    """A null replacement is an omission, not a request to write the word "None".

    This case was silently corrupting documents: the parameter corrector
    stringified None to "None" before this branch ran, so the guard could not
    fire and the literal word landed in the file with success reported.
    """
    project, doc_path = _project(tmp_path)

    result = await _replace_text(
        project, metadata={"find": "TARGET BLOCK", "replace": None}
    )

    assert result.success is False
    assert "REPLACE_TEXT_MISSING_REPLACE" in (result.error_message or "")
    body = doc_path.read_text(encoding="utf-8")
    assert body == DOC_BODY
    assert "None" not in body


async def test_replacing_with_the_word_none_is_still_allowed(tmp_path: Path) -> None:
    """The refusal keys on the null value, never on the string that spells it."""
    project, doc_path = _project(tmp_path)

    result = await _replace_text(
        project, metadata={"find": "TARGET BLOCK", "replace": "None"}
    )

    assert result.success is True, result.error_message
    assert "None" in doc_path.read_text(encoding="utf-8")


async def test_explicit_empty_replace_still_deletes_deliberately(tmp_path: Path) -> None:
    project, doc_path = _project(tmp_path)

    result = await _replace_text(
        project, metadata={"find": "TARGET BLOCK\n", "replace": ""}
    )

    assert result.success is True, result.error_message
    body = doc_path.read_text(encoding="utf-8")
    assert "TARGET BLOCK" not in body
    assert "intro line" in body and "outro line" in body


async def test_content_parameter_is_refused_and_names_metadata_replace(tmp_path: Path) -> None:
    project, doc_path = _project(tmp_path)

    result = await _replace_text(
        project,
        metadata={"find": "TARGET BLOCK"},
        content="THE REPLACEMENT",
    )

    assert result.success is False
    message = result.error_message or ""
    assert "REPLACE_TEXT_UNEXPECTED_CONTENT" in message
    assert "metadata.replace" in message, "the refusal must name the correct parameter"
    assert doc_path.read_text(encoding="utf-8") == DOC_BODY


async def test_ordinary_replacement_is_unaffected(tmp_path: Path) -> None:
    project, doc_path = _project(tmp_path)

    result = await _replace_text(
        project, metadata={"find": "TARGET BLOCK", "replace": "NEW BLOCK"}
    )

    assert result.success is True, result.error_message
    assert "NEW BLOCK" in doc_path.read_text(encoding="utf-8")
