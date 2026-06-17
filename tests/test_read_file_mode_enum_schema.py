"""Contract regression for the WS4/WS5 read_file mode-enum schema (P2.1).

Proves the host-facing input schema for ``read_file`` now teaches its read-mode
vocabulary up front instead of leaving agents blind to cheap modes like
``scan_only`` (the schema-education research found agents default to expensive
full reads because they do not know the alternatives exist):

* ``mode`` carries an ``enum`` + a WHEN-to-use ``description`` and a
  ``scan_only`` default.
* ``additionalProperties`` stays ``True`` so the many passthrough kwargs are not
  regressed into hard host rejections.
* the enum is sourced from ``_READ_FILE_MODES`` and (anti-drift) equals the set
  of modes the tool body actually dispatches on — not a frozen guess that can
  silently diverge from the real ``if mode == "..."`` branches.

These mirror the proven ``set_project`` / ``manage_docs`` (P1.2) ``input_schema=``
override pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

from scribe_mcp import server
from scribe_mcp.tools import read_file as read_file_module


def _registered_read_file_schema() -> dict:
    """Return the host-facing input schema as the MCP host would see it."""
    server.list_registered_tools()
    defs = (
        getattr(type(server.app), "_scribe_tool_defs", None)
        or getattr(server.app, "_scribe_tool_defs", None)
    )
    assert defs, "Tool registry should be populated after list_registered_tools()"
    tool = defs["read_file"]
    return tool.inputSchema


def _modes_dispatched_in_source() -> set[str]:
    """Scrape the modes the tool body really branches on (``mode == "x"``).

    This is the ground truth the enum must not drift from. Only the bare
    ``mode`` local is matched: a leading ``(?<![\\w.])`` excludes qualified
    accesses such as ``exec_context.mode == "sentinel"`` and other ``*_mode``
    variables (``search_mode``/``resolved_mode``/``original_mode``).
    """
    source = Path(read_file_module.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'(?<![\w.])mode == "([a-z_]+)"', source))


def test_registered_schema_exposes_mode_enum_and_keeps_additional_properties():
    """A previously-untyped ``mode`` now has an enriched, teachable schema.

    Before P2.1, ``mode`` was a bare auto-built ``{"type": "string"}`` with no
    enum, so agents had no host-level signal that ``scan_only`` (cheap) existed.
    The enriched schema exposes the enum + descriptions while preserving
    ``additionalProperties``.
    """
    schema = _registered_read_file_schema()

    mode_schema = schema["properties"]["mode"]
    assert "enum" in mode_schema, "mode must expose an enum at the host layer"
    assert isinstance(mode_schema["enum"], list) and mode_schema["enum"], (
        "mode enum must be a non-empty list"
    )
    # The default steers agents to the cheap scan-first path.
    assert mode_schema.get("default") == "scan_only"
    # Descriptions teach WHEN to use each mode (scan_only is the headline).
    assert "description" in mode_schema
    assert "scan_only" in mode_schema["description"]

    # KEEP additionalProperties:true — read_file has many passthrough kwargs
    # (chunk_index, structure_page, etc.); they must not regress into rejections.
    assert schema["additionalProperties"] is True

    # ``path`` is mandatory; ``agent`` is injected as required by the server's
    # runtime-agent wrapper (mirrors the manage_docs keystone behavior).
    assert "path" in schema["required"]
    assert "agent" in schema["required"]


def test_mode_enum_matches_real_dispatch_modes_not_a_frozen_guess():
    """Anti-drift: the enum must equal the modes the tool body dispatches on."""
    schema = _registered_read_file_schema()
    enum_modes = set(schema["properties"]["mode"]["enum"])

    # The module-level schema the registration consumes agrees with the canonical
    # declaration (single source of truth).
    assert enum_modes == set(read_file_module._READ_FILE_MODES)
    assert (
        read_file_module._READ_FILE_INPUT_SCHEMA["properties"]["mode"]["enum"]
        == list(read_file_module._READ_FILE_MODES)
    )

    # And that canonical set is exactly the modes the dispatch really handles.
    dispatched = _modes_dispatched_in_source()
    assert dispatched, "expected to scrape real `mode == \"...\"` branches from source"
    assert enum_modes == dispatched, (
        "mode enum drifted from the real dispatch branches: "
        f"enum-only={enum_modes - dispatched}, dispatch-only={dispatched - enum_modes}"
    )


def test_every_enum_mode_has_a_when_to_use_description():
    """Each declared mode carries non-empty guidance — no bare enum values."""
    for name, desc in read_file_module._READ_FILE_MODES.items():
        assert isinstance(desc, str) and desc.strip(), (
            f"mode {name!r} must carry a WHEN-to-use description"
        )
