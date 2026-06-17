"""Contract regression for the WS4 manage_docs schema-enrichment keystone (P1.2).

Proves the host-facing input schema for ``manage_docs`` now teaches its
constrained vocabulary up front instead of opaquely rejecting valid calls:

* ``action`` carries an ``enum`` and ``additionalProperties`` stays ``True``
  (so passthrough kwargs / metadata aliases are not regressed into hard
  host rejections).
* the ``action`` enum is sourced LIVE from
  ``build_manage_docs_action_manifest()["all_actions"]`` — a single source of
  truth, not a frozen literal that can drift from ``VALID_ACTIONS``.

These mirror the proven ``set_project`` ``input_schema=`` override pattern.
"""

from __future__ import annotations

from scribe_mcp import server
from scribe_mcp.doc_management import runtime as runtime_shared
from scribe_mcp.tools import manage_docs as manage_docs_module


def _registered_manage_docs_schema() -> dict:
    """Return the host-facing input schema as the MCP host would see it."""
    server.list_registered_tools()
    defs = (
        getattr(type(server.app), "_scribe_tool_defs", None)
        or getattr(server.app, "_scribe_tool_defs", None)
    )
    assert defs, "Tool registry should be populated after list_registered_tools()"
    tool = defs["manage_docs"]
    return tool.inputSchema


def test_registered_schema_exposes_action_enum_and_keeps_additional_properties():
    """A previously host-rejectable valid call now has an enriched, teachable schema.

    Before the keystone, ``action`` was a bare ``{"type": "string"}`` with no
    enum, so a mistyped action was rejected with opaque ``Invalid arguments``.
    The enriched schema exposes the enum while preserving ``additionalProperties``.
    """
    schema = _registered_manage_docs_schema()

    action_schema = schema["properties"]["action"]
    assert "enum" in action_schema, "action must expose an enum at the host layer"
    assert isinstance(action_schema["enum"], list) and action_schema["enum"], (
        "action enum must be a non-empty list"
    )

    # KEEP additionalProperties:true — passthrough kwargs / metadata aliases
    # (e.g. `doc`) must not regress into hard host rejections.
    assert schema["additionalProperties"] is True

    # The required/default mismatch fix: `action` is declared required even
    # though the Python signature gives it a default. `agent` is injected as
    # required by the server's runtime-agent wrapper.
    assert "action" in schema["required"]
    assert "agent" in schema["required"]

    # metadata is documented so unknown sub-keys are teachable, not silent.
    assert "description" in schema["properties"]["metadata"]


def test_action_enum_is_sourced_from_manifest_not_a_frozen_literal():
    """The enum must equal the live manifest's ``all_actions`` (single source of truth)."""
    schema = _registered_manage_docs_schema()
    manifest_actions = runtime_shared.build_manage_docs_action_manifest()["all_actions"]

    assert schema["properties"]["action"]["enum"] == list(manifest_actions)
    # And the module-level schema dict the registration consumes agrees.
    assert (
        manage_docs_module._MANAGE_DOCS_INPUT_SCHEMA["properties"]["action"]["enum"]
        == list(manifest_actions)
    )


def test_enum_tracks_valid_actions_dynamically():
    """If ``VALID_ACTIONS`` changes, the freshly-built schema follows it.

    This is the anti-drift guarantee: the enum is derived, not copied. Building
    the schema after injecting a synthetic action must include that action,
    proving the source is the manifest and not a hand-frozen list.
    """
    sentinel_action = "__keystone_probe_action__"
    original = runtime_shared.VALID_ACTIONS
    try:
        runtime_shared.VALID_ACTIONS = set(original) | {sentinel_action}
        rebuilt = manage_docs_module._build_manage_docs_input_schema()
        assert sentinel_action in rebuilt["properties"]["action"]["enum"]
    finally:
        runtime_shared.VALID_ACTIONS = original

    # Baseline state restored: a fresh build no longer contains the probe.
    clean = manage_docs_module._build_manage_docs_input_schema()
    assert sentinel_action not in clean["properties"]["action"]["enum"]
