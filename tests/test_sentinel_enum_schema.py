"""Contract regression for the WS4/WS1 sentinel enum schema (P2.2).

Proves the host-facing input schemas for ``open_bug`` / ``open_security`` /
``link_fix`` now teach their constrained vocabularies up front instead of
leaving agents to guess (and then be opaquely rejected at runtime):

* ``severity`` (open_bug, open_security) carries an ``enum`` sourced LIVE from
  the canonical ``LogPriority`` vocabulary — not a frozen literal that can drift.
* ``landing_status`` (link_fix) carries an ``enum`` sourced LIVE from the
  unified case-status vocabulary (``CASE_OPEN_STATUS_VALUES`` |
  ``CASE_CLOSED_STATUS_VALUES``) — exactly the tokens
  ``resolved_case_close_status`` understands.
* ``category`` is intentionally NOT enumerated (it is a free-form organizational
  label validated only as non-empty at runtime); it carries teaching guidance
  via ``description`` instead of a fabricated enum that would falsely reject
  valid free-form categories.
* ``additionalProperties`` stays ``True`` on all three so the rich optional-kwarg
  surface is never regressed into hard host rejections, and ``agent`` is injected
  as required by the server's runtime-agent wrapper.

These mirror the proven ``set_project`` / ``manage_docs`` (P1.2) ``input_schema=``
override pattern.
"""

from __future__ import annotations

import pytest

from scribe_mcp import server
from scribe_mcp.doc_management import utils as doc_utils
from scribe_mcp.shared.log_enums import LogPriority
from scribe_mcp.tools import sentinel_tools


def _registered_schema(tool_name: str) -> dict:
    """Return the host-facing input schema as the MCP host would see it."""
    server.list_registered_tools()
    defs = (
        getattr(type(server.app), "_scribe_tool_defs", None)
        or getattr(server.app, "_scribe_tool_defs", None)
    )
    assert defs, "Tool registry should be populated after list_registered_tools()"
    tool = defs[tool_name]
    return tool.inputSchema


@pytest.mark.parametrize(
    "tool_name, module_schema, required_business_field",
    [
        ("open_bug", sentinel_tools._OPEN_BUG_INPUT_SCHEMA, "category"),
        ("open_security", sentinel_tools._OPEN_SECURITY_INPUT_SCHEMA, "category"),
    ],
)
def test_severity_enum_exposed_and_additional_properties_preserved(
    tool_name: str, module_schema: dict, required_business_field: str
) -> None:
    """severity exposes the canonical enum; additionalProperties + agent intact."""
    schema = _registered_schema(tool_name)

    severity_schema = schema["properties"]["severity"]
    assert "enum" in severity_schema, "severity must expose an enum at the host layer"
    assert isinstance(severity_schema["enum"], list) and severity_schema["enum"], (
        "severity enum must be a non-empty list"
    )

    # KEEP additionalProperties:true — the rich optional-kwarg surface
    # (component, environment, preview, ...) must not regress into rejections.
    assert schema["additionalProperties"] is True

    # Business-required field is declared; agent is injected as required.
    assert required_business_field in schema["required"]
    assert "agent" in schema["required"]

    # The registered schema is exactly the module-level dict the registration
    # consumes (no divergence between source-of-truth and host surface).
    assert schema["properties"]["severity"]["enum"] == module_schema["properties"]["severity"]["enum"]


@pytest.mark.parametrize("tool_name", ["open_bug", "open_security"])
def test_severity_enum_is_sourced_from_logpriority_not_a_frozen_literal(tool_name: str) -> None:
    """Anti-drift: the severity enum must equal the live ``LogPriority`` values."""
    schema = _registered_schema(tool_name)
    canonical = [member.value for member in LogPriority]

    assert schema["properties"]["severity"]["enum"] == canonical
    # And the module-level constant the schema builders consume agrees.
    assert sentinel_tools._SEVERITY_ENUM == canonical


@pytest.mark.parametrize("tool_name", ["open_bug", "open_security"])
def test_category_is_documented_free_form_not_enumerated(tool_name: str) -> None:
    """category is free-form: described, never enumerated (no false rejections)."""
    schema = _registered_schema(tool_name)
    category_schema = schema["properties"]["category"]

    assert "enum" not in category_schema, (
        "category is a free-form organizational label and must NOT carry an enum"
    )
    assert category_schema.get("description", "").strip(), (
        "category must carry teaching guidance via description"
    )


def test_link_fix_landing_status_enum_exposed_and_additional_properties_preserved() -> None:
    """landing_status exposes the unified case-status enum; surface preserved."""
    schema = _registered_schema("link_fix")

    landing_schema = schema["properties"]["landing_status"]
    assert "enum" in landing_schema, "landing_status must expose an enum at the host layer"
    assert isinstance(landing_schema["enum"], list) and landing_schema["enum"], (
        "landing_status enum must be a non-empty list"
    )
    assert landing_schema.get("description", "").strip(), (
        "landing_status must carry teaching guidance via description"
    )

    assert schema["additionalProperties"] is True
    assert "case_id" in schema["required"]
    assert "artifact_ref" in schema["required"]
    assert "landing_status" in schema["required"]
    assert "agent" in schema["required"]

    # case_id description teaches the BUG-/SEC- ID format.
    case_id_desc = schema["properties"]["case_id"].get("description", "")
    assert "BUG-" in case_id_desc and "SEC-" in case_id_desc


def test_landing_status_enum_is_sourced_from_unified_case_vocab_not_a_frozen_literal() -> None:
    """Anti-drift: landing_status enum equals the live unified case-status vocab.

    The enum must follow the exact tokens ``resolved_case_close_status``
    recognizes: open (leaves case open) + fix-terminal + non-fix-terminal.
    """
    schema = _registered_schema("link_fix")
    canonical = sorted(
        doc_utils.CASE_OPEN_STATUS_VALUES | doc_utils.CASE_CLOSED_STATUS_VALUES
    )

    assert schema["properties"]["landing_status"]["enum"] == canonical
    # Module-level constant the registration consumes agrees.
    assert sentinel_tools._LINK_FIX_INPUT_SCHEMA["properties"]["landing_status"]["enum"] == canonical

    # Every enumerated token is real: each is classifiable by the canonical
    # resolver (open -> None, fix-terminal -> "closed", non-fix -> preserved).
    for token in schema["properties"]["landing_status"]["enum"]:
        if token in doc_utils.CASE_OPEN_STATUS_VALUES:
            assert doc_utils.resolved_case_close_status(token) is None
        else:
            assert doc_utils.resolved_case_close_status(token) is not None


def test_landing_status_enum_tracks_vocab_dynamically() -> None:
    """If the unified vocab gains a token, a freshly-built enum follows it."""
    sentinel_token = "__p2_2_probe_status__"
    original = doc_utils.CASE_OPEN_STATUS_VALUES
    try:
        doc_utils.CASE_OPEN_STATUS_VALUES = frozenset(original | {sentinel_token})
        rebuilt = sentinel_tools._build_link_fix_input_schema()
        assert sentinel_token in rebuilt["properties"]["landing_status"]["enum"]
    finally:
        doc_utils.CASE_OPEN_STATUS_VALUES = original

    # Baseline restored: a fresh build no longer contains the probe.
    clean = sentinel_tools._build_link_fix_input_schema()
    assert sentinel_token not in clean["properties"]["landing_status"]["enum"]
