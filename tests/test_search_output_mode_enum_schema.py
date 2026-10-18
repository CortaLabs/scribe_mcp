"""Contract regression for the WS4 search output_mode-enum schema (P2.3).

Proves the host-facing input schema for ``search`` now teaches its
``output_mode`` vocabulary up front (and likewise documents the ``format`` enum)
instead of leaving agents blind to the available result shapes:

* ``output_mode`` carries an ``enum`` + a teaching ``description`` at the host
  layer, while ``additionalProperties`` stays ``True`` so the many passthrough
  kwargs (pagination, context lines, limits, etc.) are not regressed into hard
  host rejections.
* the enum is sourced from :data:`VALID_OUTPUT_MODES` and (anti-drift) equals the
  set of modes the tool body actually dispatches on — not a frozen guess that can
  silently diverge from the real ``output_mode == "..."`` branches.
* a boundary violation (invalid ``output_mode``) now returns an
  ``ErrorHandler.create_validation_error`` response carrying a ``suggestion``
  that names the valid modes, instead of an opaque flat error string.

These mirror the committed ``manage_docs`` (P1.2) and ``read_file`` (P2.1)
``input_schema=`` override pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scribe_mcp import server
from scribe_mcp.shared import execution_context as exec_context_module
from scribe_mcp.shared.execution_context import ExecutionContext, AgentIdentity
from scribe_mcp.tools import search as search_module
from scribe_mcp.tools.search import VALID_OUTPUT_MODES, search


def _registered_search_schema() -> dict:
    """Return the host-facing input schema as the MCP host would see it."""
    server.list_registered_tools()
    defs = (
        getattr(type(server.app), "_scribe_tool_defs", None)
        or getattr(server.app, "_scribe_tool_defs", None)
    )
    assert defs, "Tool registry should be populated after list_registered_tools()"
    tool = defs["search"]
    return tool.inputSchema


def _output_modes_dispatched_in_source() -> set[str]:
    """Scrape the output_mode values the tool body really branches on.

    This is the ground truth the enum must not drift from. Matches both the
    validation set membership and the ``output_mode == "x"`` render branches.
    """
    source = Path(search_module.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'output_mode == "([a-z_]+)"', source))


def test_registered_schema_exposes_output_mode_enum_and_keeps_additional_properties():
    """A previously-untyped ``output_mode`` now has an enriched, teachable schema.

    Before P2.3, ``output_mode`` was a bare auto-built ``{"type": "string"}`` with
    no enum, so agents had no host-level signal about the available result
    shapes. The enriched schema exposes the enum + description while preserving
    ``additionalProperties``.
    """
    schema = _registered_search_schema()

    output_mode_schema = schema["properties"]["output_mode"]
    assert "enum" in output_mode_schema, "output_mode must expose an enum at the host layer"
    assert isinstance(output_mode_schema["enum"], list) and output_mode_schema["enum"], (
        "output_mode enum must be a non-empty list"
    )
    # Enum values match search's REAL accepted modes (single source of truth).
    assert output_mode_schema["enum"] == list(VALID_OUTPUT_MODES)
    assert set(output_mode_schema["enum"]) == {"content", "files_with_matches", "count"}
    # Description teaches what each mode returns.
    assert "description" in output_mode_schema
    assert "files_with_matches" in output_mode_schema["description"]

    # KEEP additionalProperties:true — search has many passthrough kwargs
    # (page, context_lines, max_files, etc.); they must not regress into rejections.
    assert schema["additionalProperties"] is True

    # ``pattern`` is mandatory; ``agent`` is injected as required by the server's
    # runtime-agent wrapper (mirrors the manage_docs keystone behavior).
    assert "pattern" in schema["required"]
    assert "agent" in schema["required"]


def test_output_mode_enum_matches_real_dispatch_modes_not_a_frozen_guess():
    """Anti-drift: the enum must equal the modes the tool body dispatches on."""
    schema = _registered_search_schema()
    enum_modes = set(schema["properties"]["output_mode"]["enum"])

    # The module-level schema the registration consumes agrees with the canonical
    # declaration (single source of truth).
    assert enum_modes == set(VALID_OUTPUT_MODES)
    assert (
        search_module._SEARCH_INPUT_SCHEMA["properties"]["output_mode"]["enum"]
        == list(VALID_OUTPUT_MODES)
    )

    # And that canonical set is exactly the modes the body really handles.
    dispatched = _output_modes_dispatched_in_source()
    assert dispatched, "expected to scrape real `output_mode == \"...\"` branches from source"
    assert enum_modes == dispatched, (
        "output_mode enum drifted from the real dispatch branches: "
        f"enum-only={enum_modes - dispatched}, dispatch-only={dispatched - enum_modes}"
    )


def test_format_field_is_also_documented_as_an_enum():
    """``format`` is a free-form-string-but-actually-enum field — document it too."""
    schema = _registered_search_schema()
    format_schema = schema["properties"]["format"]
    assert format_schema.get("enum") == ["readable", "structured", "compact"]
    assert "description" in format_schema


@pytest.fixture
def execution_context(tmp_path):
    """Minimal execution context with temp dir as repo root (mirrors integration)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").touch()

    agent_identity = AgentIdentity(
        agent_kind="test",
        instance_id="test_instance",
        sub_id=None,
        display_name="TestAgent",
        model="test-model",
    )

    from datetime import datetime, timezone

    context = ExecutionContext(
        execution_id="test_exec",
        session_id="test_session",
        intent="testing",
        repo_root=str(tmp_path),
        mode="project",
        agent_identity=agent_identity,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        affected_dev_projects=[],
    )
    # The runtime resolves context from the request-local contextvar
    # (``get_current_execution_context``); bind it the same way.
    token = exec_context_module._CURRENT_CONTEXT.set(context)
    yield tmp_path
    exec_context_module._CURRENT_CONTEXT.reset(token)


@pytest.mark.asyncio
async def test_invalid_output_mode_returns_validation_error_with_suggestion(execution_context):
    """A boundary violation teaches the agent instead of failing opaquely."""
    result = await search(
        agent="test-agent",
        pattern="auth",
        output_mode="lines",  # invalid — not one of the accepted modes
        format="structured",
    )

    assert isinstance(result, dict)
    assert result["ok"] is False
    assert "lines" in result["error"]
    # The teaching suggestion names the valid modes so the mistake is correctable.
    assert "suggestion" in result, "boundary error must carry a teaching suggestion"
    for mode in VALID_OUTPUT_MODES:
        assert mode in result["suggestion"], f"suggestion should name valid mode {mode!r}"
    # Context echoes the rejected value.
    assert result.get("output_mode") == "lines"


@pytest.mark.asyncio
async def test_valid_output_mode_is_accepted(execution_context):
    """Each declared enum value passes boundary validation (no false rejects)."""
    for mode in VALID_OUTPUT_MODES:
        result = await search(
            agent="test-agent",
            pattern="auth",
            output_mode=mode,
            format="structured",
        )
        assert isinstance(result, dict)
        # Must NOT be the output_mode validation error.
        assert not (result.get("ok") is False and "Invalid output_mode" in result.get("error", "")), (
            f"valid mode {mode!r} was wrongly rejected"
        )
