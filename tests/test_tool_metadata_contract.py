from __future__ import annotations

from scribe_mcp import server


EXPECTED_REGISTERED_TOOLS = {
    "analyze_logs",
    "append_entry",
    "append_event",
    "authorize_repo_root",
    "configure_reminders",
    "delete_project",
    "edit_file",
    "generate_doc_templates",
    "get_project",
    "link_fix",
    "list_open_cases",
    "list_projects",
    "manage_docs",
    "open_bug",
    "open_security",
    "query_entries",
    "query_reminders",
    "read_file",
    "read_recent",
    "reset_reminders",
    "rotate_log",
    "scribe_doctor",
    "scribe_local_postgres_readiness_roundtrip_preflight",
    "scribe_private_context_selector_readback",
    "search",
    "set_project",
}


def _tool_defs():
    server.list_registered_tools()
    defs = getattr(type(server.app), "_scribe_tool_defs", None) or getattr(server.app, "_scribe_tool_defs", None)
    assert defs, "Tool registry should be populated after list_registered_tools()"
    return defs


def test_metadata_contract_covers_entire_registered_surface():
    assert set(server.list_registered_tools()) == EXPECTED_REGISTERED_TOOLS


def test_all_registered_tools_expose_explicit_metadata():
    defs = _tool_defs()

    for tool_name in EXPECTED_REGISTERED_TOOLS:
        tool = defs[tool_name]
        assert tool.title, f"{tool_name} is missing an explicit title"
        assert tool.description, f"{tool_name} is missing a description"
        assert tool.annotations is not None, f"{tool_name} is missing tool annotations"
        assert isinstance(tool.meta, dict), f"{tool_name} is missing tool meta"
        assert getattr(tool, "tags", None), f"{tool_name} is missing tags"

        scribe_meta = tool.meta.get("scribe", {})
        assert scribe_meta.get("trustTier") in {0, 1, 2, 3, 4}, f"{tool_name} has invalid trust tier"
        assert scribe_meta.get("riskClass"), f"{tool_name} is missing riskClass"
        assert scribe_meta.get("surface") in {"operator", "admin"}, f"{tool_name} has invalid surface"
        assert scribe_meta.get("locality") == "local", f"{tool_name} should be local-only"


def test_representative_tool_annotations_match_risk_profile():
    defs = _tool_defs()

    read_file = defs["read_file"]
    assert read_file.annotations.readOnlyHint is True
    assert read_file.annotations.destructiveHint is False
    assert read_file.annotations.idempotentHint is True
    assert read_file.annotations.openWorldHint is False
    assert read_file.meta["scribe"]["trustTier"] == 0

    append_entry = defs["append_entry"]
    assert append_entry.annotations.readOnlyHint is False
    assert append_entry.annotations.destructiveHint is False
    assert append_entry.meta["scribe"]["trustTier"] == 1

    set_project = defs["set_project"]
    assert set_project.annotations.readOnlyHint is False
    assert set_project.annotations.destructiveHint is False
    assert set_project.meta["scribe"]["trustTier"] == 2

    delete_project = defs["delete_project"]
    assert delete_project.annotations.readOnlyHint is False
    assert delete_project.annotations.destructiveHint is True
    assert delete_project.meta["scribe"]["trustTier"] == 3
    assert delete_project.meta["scribe"]["surface"] == "admin"


def test_describe_registered_tools_returns_json_friendly_metadata():
    details = server.describe_registered_tools()

    read_file = details["read_file"]
    assert read_file["title"] == "Read File"
    assert read_file["description"]
    assert read_file["annotations"]["readOnlyHint"] is True
    assert read_file["meta"]["scribe"]["trustTier"] == 0
    assert "inspection" in read_file["tags"]

    selector_readback = details["scribe_private_context_selector_readback"]
    assert selector_readback["title"] == "Scribe Private Context Selector Readback"
    assert selector_readback["annotations"]["readOnlyHint"] is True
    assert selector_readback["annotations"]["destructiveHint"] is False
    assert selector_readback["annotations"]["openWorldHint"] is False
    assert selector_readback["meta"]["scribe"]["trustTier"] == 0
    assert selector_readback["meta"]["scribe"]["riskClass"] == "local_read_only"
    assert selector_readback["meta"]["scribe"]["surface"] == "operator"
    assert selector_readback["execution"]["taskSupport"] == "forbidden"
    assert "readback" in selector_readback["tags"]

    roundtrip_preflight = details["scribe_local_postgres_readiness_roundtrip_preflight"]
    assert roundtrip_preflight["title"] == "Scribe Local Postgres Readiness Roundtrip Preflight"
    assert roundtrip_preflight["annotations"]["readOnlyHint"] is False
    assert roundtrip_preflight["annotations"]["destructiveHint"] is False
    assert roundtrip_preflight["annotations"]["openWorldHint"] is False
    assert roundtrip_preflight["meta"]["scribe"]["trustTier"] == 1
    assert roundtrip_preflight["meta"]["scribe"]["riskClass"] == "bounded_mutation_preflight"
    assert roundtrip_preflight["meta"]["scribe"]["surface"] == "operator"
    assert roundtrip_preflight["meta"]["scribe"]["locality"] == "local"
    assert roundtrip_preflight["execution"]["taskSupport"] == "forbidden"
    assert "bounded-preflight" in roundtrip_preflight["tags"]


def test_direct_selector_and_readiness_schemas_require_runtime_agent_identity():
    details = server.describe_registered_tools()

    expected_public_arguments = {
        "scribe_private_context_selector_readback": {
            "selector_class_label",
            "target_fingerprint_binding_label",
            "runtime_role_label",
            "default_context_bypass_label",
            "active_runtime_exclusion_label",
            "source_authority_label",
        },
        "scribe_local_postgres_readiness_roundtrip_preflight": {
            "private_target_handle_id",
            "target_class_label",
            "selected_context_readback_status_label",
            "proof_namespace_label",
        },
    }

    for tool_name, public_arguments in expected_public_arguments.items():
        schema = details[tool_name]["input_schema"]
        properties = schema["properties"]
        required = set(schema["required"])

        assert properties["agent"] == {"type": "string"}
        assert {"agent", *public_arguments} <= required
        assert public_arguments <= set(properties)
