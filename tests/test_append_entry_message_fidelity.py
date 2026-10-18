"""Entry messages must survive the write path byte-identical.

A silent write-time cap on the message corrupts the audit trail in both the
file trail and the DB mirror, which is the one thing the trail exists to
prevent. These tests pin the message as uncapped while keeping the short
identifier-shaped fields (agent, emoji, log_type) capped as before.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scribe_mcp import server as server_module
from scribe_mcp.shared.logging_utils import LoggingContext
from scribe_mcp.tools import append_entry as append_entry_module
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector


pytestmark = [pytest.mark.asyncio, pytest.mark.regression]


def _as_dict(result: object) -> dict:
    if isinstance(result, dict):
        return result
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    return {}


def _project(repo_root: Path) -> dict:
    docs_dir = repo_root / ".scribe" / "docs" / "dev_plans" / "test_project"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "name": "test-project",
        "root": str(repo_root),
        "progress_log": str(docs_dir / "PROGRESS_LOG.md"),
        "docs_dir": str(docs_dir),
        "defaults": {"agent": "test-agent"},
    }


def _install_context(monkeypatch: pytest.MonkeyPatch, project: dict) -> None:
    context = LoggingContext(
        tool_name="append_entry",
        project=project,
        recent_projects=[project["name"]],
        state_snapshot={},
        reminders=[],
    )

    async def resolve_context(**_kwargs: object) -> LoggingContext:
        return context

    monkeypatch.setattr(append_entry_module, "resolve_logging_context", resolve_context)
    monkeypatch.setattr(server_module, "get_execution_context", lambda: None)
    monkeypatch.setattr(server_module, "get_agent_identity", lambda: None)
    monkeypatch.setattr(
        server_module,
        "state_manager",
        SimpleNamespace(
            record_tool=AsyncMock(return_value={}),
            update_project_activity=AsyncMock(return_value=None),
        ),
    )


def _capturing_backend(monkeypatch: pytest.MonkeyPatch, project: dict) -> list[str]:
    """Install a storage backend that records each mirrored message."""
    inserted: list[str] = []

    async def _insert(**kwargs: object) -> None:
        inserted.append(kwargs["message"])

    monkeypatch.setattr(
        server_module,
        "storage_backend",
        SimpleNamespace(
            fetch_project=AsyncMock(return_value=SimpleNamespace(name=project["name"])),
            upsert_project=AsyncMock(),
            insert_entry=AsyncMock(side_effect=_insert),
        ),
    )
    return inserted


async def test_long_message_persists_in_full_to_file_and_db_mirror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    project = _project(repo_root)
    _install_context(monkeypatch, project)

    inserted: list[object] = []

    async def _insert(**kwargs: object) -> None:
        # backend.insert_entry is called with all-keyword arguments; `message`
        # is the mirrored trail content this test is pinning.
        inserted.append(kwargs["message"])

    backend = SimpleNamespace(
        fetch_project=AsyncMock(return_value=SimpleNamespace(name=project["name"])),
        upsert_project=AsyncMock(),
        insert_entry=AsyncMock(side_effect=_insert),
    )
    monkeypatch.setattr(server_module, "storage_backend", backend)

    # Distinct head and tail so a cut anywhere in between is detectable.
    long_message = "HEAD_MARKER " + ("filler " * 720) + "TAIL_MARKER"
    assert len(long_message) > 5000

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message=long_message,
            format="structured",
        )
    )
    assert result["ok"] is True

    written = Path(project["progress_log"]).read_text(encoding="utf-8")
    assert long_message in written, "file trail lost or truncated the message"
    assert "..." not in written.split("HEAD_MARKER")[-1].split("TAIL_MARKER")[0]

    assert len(inserted) == 1, "DB mirror did not receive the entry"
    assert inserted[0] == long_message, "DB mirror stored a truncated message"


async def test_message_corrector_is_uncapped_but_identifiers_stay_capped() -> None:
    corrector = BulletproofParameterCorrector

    long_value = "X" * 5000

    # The message call site passes max_length=None: nothing is dropped.
    assert corrector.correct_message_parameter(long_value, max_length=None) == long_value

    # Identifier-shaped fields keep the original 1000-char cap and its ellipsis.
    capped = corrector.correct_message_parameter(long_value)
    assert len(capped) == 1000
    assert capped.endswith("...")

    # An explicit cap is still honoured for callers that ask for one.
    explicit = corrector.correct_message_parameter(long_value, max_length=50)
    assert len(explicit) == 50
    assert explicit.endswith("...")


async def test_short_message_is_unchanged_by_the_uncapped_path() -> None:
    corrector = BulletproofParameterCorrector
    assert corrector.correct_message_parameter("a short entry", max_length=None) == "a short entry"


# ---------------------------------------------------------------------------
# Structure axis: newlines are structure, not "problematic characters".
#
# The corrector used to flatten them to spaces before `_sanitize_message` could
# escape them, so every multiline entry landed as one run-on line. Preserving
# them exposed a second defect: bulk-mode detection routed on newline presence
# alone and ignored `auto_split`, so `auto_split=False` wrote NOTHING.
# ---------------------------------------------------------------------------

MULTILINE = "HEAD_MARKER\n" + "".join(f"body line {i}\n" for i in range(400)) + "TAIL_MARKER"


def _message_body(log_line: str, start_marker: str) -> str:
    """The rendered message, between the bracketed prefix and the meta suffix."""
    return log_line[log_line.index(start_marker) : log_line.rindex(" | ")]


async def test_multiline_message_keeps_real_newlines_in_db_and_escapes_them_in_the_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The non-split path: one entry, structure intact in both stores.

    The file record must stay on one line (it is a line-delimited log), so it
    carries the sanitizer's escaped form. The DB has no such constraint and
    keeps the caller's text byte-identical.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    inserted = _capturing_backend(monkeypatch, project)

    assert len(MULTILINE) > 3000

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message=MULTILINE,
            format="structured",
            auto_split=False,
        )
    )
    assert result["ok"] is True

    # DB mirror: byte-identical, real newlines.
    assert len(inserted) == 1
    assert inserted[0] == MULTILINE
    assert "\n" in inserted[0]

    # File trail: exactly one record, newlines escaped rather than flattened.
    written = Path(project["progress_log"]).read_text(encoding="utf-8")
    records = [ln for ln in written.splitlines() if "HEAD_MARKER" in ln]
    assert len(records) == 1
    body = _message_body(records[0], "HEAD_MARKER")
    assert body == MULTILINE.replace("\n", "\\n")
    assert "HEAD_MARKER" in body and "TAIL_MARKER" in body
    # RED: the old flattening replaced newlines with spaces.
    assert "HEAD_MARKER body line 0" not in body


async def test_auto_split_multiline_yields_one_clean_entry_per_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto_split=True is scribe's designed multiline handler — pin the shape."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    inserted = _capturing_backend(monkeypatch, project)

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="alpha\nbeta\ngamma",
            format="structured",
            auto_split=True,
        )
    )
    assert result["ok"] is True

    assert inserted == ["alpha", "beta", "gamma"]
    # RED: the flattened shape was a single run-on entry.
    assert inserted != ["alpha beta gamma"]


async def test_auto_split_false_multiline_persists_and_never_vanishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The drop bug: bulk routing with an empty item list wrote zero rows.

    `auto_split=False` means the caller asked for one entry. Routing that to
    bulk mode produced ok=False and NOTHING in either store — silent total loss,
    strictly worse than the flattening it replaced.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    project = _project(repo_root)
    _install_context(monkeypatch, project)
    inserted = _capturing_backend(monkeypatch, project)

    result = _as_dict(
        await append_entry_module.append_entry(
            agent="test-agent",
            message="alpha\nbeta\ngamma",
            format="structured",
            auto_split=False,
        )
    )

    # RED is the 0-rows shape.
    assert result["ok"] is True
    assert len(inserted) == 1, "auto_split=False multiline must persist as one entry"
    assert inserted[0] == "alpha\nbeta\ngamma"
    assert Path(project["progress_log"]).exists()


async def test_bulk_detection_honours_auto_split() -> None:
    """The single line both earlier rulings died on."""
    from scribe_mcp.utils.bulk_processor import BulkProcessor

    assert BulkProcessor.detect_bulk_mode("a\nb", auto_split=True) is True
    assert BulkProcessor.detect_bulk_mode("a\nb", auto_split=False) is False
    # Explicit items always mean bulk, whatever auto_split says.
    assert BulkProcessor.detect_bulk_mode("a", items_list=[{"message": "x"}], auto_split=False) is True
    # Single-line content is never bulk.
    assert BulkProcessor.detect_bulk_mode("single line", auto_split=True) is False


async def test_identifier_fields_still_flatten_newlines() -> None:
    """Identifiers are structure, not content — flattening them is contractual.

    `agent`/`emoji`/`log_type` render inside a bracketed, pipe-delimited field
    of a single-line record; a newline there would break the record format.
    `ToolValidator.sanitize_identifier` strips brackets and pipes for the same
    reason.
    """
    corrector = BulletproofParameterCorrector

    assert corrector.correct_message_parameter("two\nlines") == "two lines"
    assert corrector.correct_message_parameter("two\nlines", max_length=None) == "two\nlines"
