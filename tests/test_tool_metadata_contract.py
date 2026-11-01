from __future__ import annotations

import inspect
import pytest

from scribe_mcp import server


EXPECTED_REGISTERED_TOOLS = {
    "analyze_logs",
    "append_entry",
    "append_event",
    "authorize_repo_root",
    "backfill_case_registry",
    "configure_reminders",
    "delete_project",
    "edit_file",
    "generate_doc_templates",
    "get_case_status",
    "get_project",
    "link_fix",
    "list_open_cases",
    "list_projects",
    "manage_docs",
    "open_bug",
    "open_security",
    "progress_log_projection",
    "query_entries",
    "query_reminders",
    "read_file",
    "read_recent",
    "read_write_barrier_state",
    "reopen_case",
    "reset_reminders",
    "rotate_log",
    "scribe_doctor",
    "scribe_affected_row_referential_inventory_readonly_public_safe",
    "scribe_local_postgres_readiness_roundtrip_preflight",
    "scribe_owned_write_barrier_acquire_maintained",
    "scribe_owned_write_barrier_acquire_release_proof",
    "scribe_owned_write_barrier_release_maintained",
    "scribe_private_context_selector_readback",
    "search",
    "set_project",
}


def _tool_defs():
    server.list_registered_tools()
    defs = getattr(type(server.app), "_scribe_tool_defs", None) or getattr(
        server.app, "_scribe_tool_defs", None
    )
    assert defs, "Tool registry should be populated after list_registered_tools()"
    return defs


def test_metadata_contract_covers_entire_registered_surface():
    registered = set(server.list_registered_tools())
    assert registered - {"health_check"} == EXPECTED_REGISTERED_TOOLS


def test_all_registered_tools_expose_explicit_metadata():
    defs = _tool_defs()

    for tool_name in set(server.list_registered_tools()):
        tool = defs[tool_name]
        assert tool.title, f"{tool_name} is missing an explicit title"
        assert tool.description, f"{tool_name} is missing a description"
        assert tool.annotations is not None, f"{tool_name} is missing tool annotations"
        assert isinstance(tool.meta, dict), f"{tool_name} is missing tool meta"
        assert getattr(tool, "tags", None), f"{tool_name} is missing tags"

        scribe_meta = tool.meta.get("scribe", {})
        assert scribe_meta.get("trustTier") in {0, 1, 2, 3, 4}, (
            f"{tool_name} has invalid trust tier"
        )
        assert scribe_meta.get("riskClass"), f"{tool_name} is missing riskClass"
        assert scribe_meta.get("surface") in {"operator", "admin"}, (
            f"{tool_name} has invalid surface"
        )
        assert scribe_meta.get("locality") == "local", (
            f"{tool_name} should be local-only"
        )


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

    reopen_case = defs["reopen_case"]
    assert reopen_case.title == "Reopen Case"
    assert reopen_case.annotations.readOnlyHint is False
    assert reopen_case.annotations.destructiveHint is False
    assert reopen_case.annotations.idempotentHint is False
    assert reopen_case.annotations.openWorldHint is False
    assert reopen_case.meta["scribe"]["trustTier"] == 2
    assert reopen_case.meta["scribe"]["riskClass"] == "local_stateful_write"
    assert reopen_case.meta["scribe"]["surface"] == "operator"
    assert {"project", "case", "lifecycle", "write"} <= set(reopen_case.tags)

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
    assert (
        roundtrip_preflight["title"]
        == "Scribe Local Postgres Readiness Roundtrip Preflight"
    )
    assert roundtrip_preflight["annotations"]["readOnlyHint"] is False
    assert roundtrip_preflight["annotations"]["destructiveHint"] is False
    assert roundtrip_preflight["annotations"]["openWorldHint"] is False
    assert roundtrip_preflight["meta"]["scribe"]["trustTier"] == 1
    assert (
        roundtrip_preflight["meta"]["scribe"]["riskClass"]
        == "bounded_mutation_preflight"
    )
    assert roundtrip_preflight["meta"]["scribe"]["surface"] == "operator"
    assert roundtrip_preflight["meta"]["scribe"]["locality"] == "local"
    assert roundtrip_preflight["execution"]["taskSupport"] == "forbidden"
    assert "bounded-preflight" in roundtrip_preflight["tags"]

    affected_inventory = details[
        "scribe_affected_row_referential_inventory_readonly_public_safe"
    ]
    assert (
        affected_inventory["title"]
        == "Scribe Affected Row Referential Inventory Readonly Public Safe"
    )
    assert affected_inventory["annotations"]["readOnlyHint"] is True
    assert affected_inventory["annotations"]["destructiveHint"] is False
    assert affected_inventory["annotations"]["openWorldHint"] is False
    assert affected_inventory["meta"]["scribe"]["trustTier"] == 0
    assert affected_inventory["meta"]["scribe"]["riskClass"] == "local_read_only"
    assert affected_inventory["meta"]["scribe"]["surface"] == "operator"
    assert affected_inventory["execution"]["taskSupport"] == "forbidden"
    assert "referential-inventory" in affected_inventory["tags"]

    acquire_maintained = details["scribe_owned_write_barrier_acquire_maintained"]
    assert (
        acquire_maintained["title"] == "Scribe Owned Write Barrier Acquire Maintained"
    )
    assert acquire_maintained["annotations"]["readOnlyHint"] is False
    assert acquire_maintained["annotations"]["destructiveHint"] is False
    assert acquire_maintained["annotations"]["openWorldHint"] is False
    assert acquire_maintained["meta"]["scribe"]["trustTier"] == 2
    assert acquire_maintained["meta"]["scribe"]["riskClass"] == "local_stateful_write"
    assert acquire_maintained["meta"]["scribe"]["surface"] == "operator"
    assert acquire_maintained["meta"]["scribe"]["locality"] == "local"
    assert "maintained" in acquire_maintained["tags"]

    release_maintained = details["scribe_owned_write_barrier_release_maintained"]
    assert (
        release_maintained["title"] == "Scribe Owned Write Barrier Release Maintained"
    )
    assert release_maintained["annotations"]["readOnlyHint"] is False
    assert release_maintained["annotations"]["destructiveHint"] is False
    assert release_maintained["annotations"]["openWorldHint"] is False
    assert release_maintained["meta"]["scribe"]["trustTier"] == 2
    assert release_maintained["meta"]["scribe"]["riskClass"] == "local_stateful_write"
    assert release_maintained["meta"]["scribe"]["surface"] == "operator"
    assert release_maintained["meta"]["scribe"]["locality"] == "local"
    assert "release" in release_maintained["tags"]


def test_direct_tool_schemas_require_operational_inputs():
    details = server.describe_registered_tools()

    expected_public_arguments = {
        "set_project": {
            "name",
            "root",
        },
        "reopen_case": {
            "case_id",
            "reason",
        },
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
        "scribe_affected_row_referential_inventory_readonly_public_safe": {
            "target_binding_status_label",
            "selected_context_readback_status_label",
            "inventory_scope_label",
        },
        "scribe_owned_write_barrier_acquire_maintained": {
            "owner_label",
            "reason_label",
        },
        "scribe_owned_write_barrier_release_maintained": {
            "owner_label",
            "reason_label",
        },
    }

    for tool_name, public_arguments in expected_public_arguments.items():
        schema = details[tool_name]["input_schema"]
        properties = schema["properties"]
        required = set(schema["required"])

        assert properties["agent"] == {"type": "string"}
        assert {"agent", *public_arguments} <= required
        assert public_arguments <= set(properties)

    reopen_schema = details["reopen_case"]["input_schema"]
    assert "target_status" in reopen_schema["properties"]
    assert "target_status" not in set(reopen_schema["required"])
    assert reopen_schema["properties"]["target_status"]["default"] == "investigating"


def test_scribe_doctor_schema_and_read_only_metadata_are_explicit():
    doctor = server.describe_registered_tools()["scribe_doctor"]

    # The accepted major-line B4 extension adds one optional presentation selector.
    # Preserve the exact original schema pin after removing ONLY that extension.
    schema = dict(doctor["input_schema"])
    schema["properties"] = dict(schema["properties"])
    selector = schema["properties"].pop("response_detail", None)
    assert isinstance(selector, dict), "accepted B4 response_detail selector is missing"
    assert selector.get("type") == "string"
    assert selector.get("enum") == ["default", "full"]
    assert selector.get("default") == "default"
    assert "response_detail" not in schema.get("required", [])
    assert schema == {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "reconciliation": {
                "type": "string",
                "enum": ["deferred", "full"],
                "default": "deferred",
                "description": "deferred skips inventory collection; full returns the complete existing physical/logical reconciliation report.",
            },
        },
        "required": ["agent"],
        "additionalProperties": True,
    }
    assert doctor["annotations"]["readOnlyHint"] is True
    assert doctor["annotations"]["destructiveHint"] is False
    assert doctor["annotations"]["idempotentHint"] is True
    assert doctor["annotations"]["openWorldHint"] is False
    assert doctor["meta"]["scribe"]["trustTier"] == 0
    assert doctor["meta"]["scribe"]["riskClass"] == "local_read_only"
    assert doctor["meta"]["scribe"]["surface"] == "operator"
    assert doctor["meta"]["scribe"]["locality"] == "local"


@pytest.mark.core
@pytest.mark.regression
class TestSBRDefaultOutput:
    def test_all_35_registered_schemas_offer_strict_default_full_selector(self, test_agent):
        details = server.describe_registered_tools()
        assert set(details) == EXPECTED_REGISTERED_TOOLS
        assert len(details) == 35
        missing = []
        for name, detail in details.items():
            schema = detail["input_schema"]
            selector = schema["properties"].get("response_detail", {})
            if (selector.get("type") != "string" or selector.get("enum") != ["default", "full"]
                    or selector.get("default") != "default" or "response_detail" in schema.get("required", [])):
                missing.append(name)
        assert not missing, f"missing/incorrect presentation selectors: {missing}"

    def test_dynamic_registration_schema_is_covered_without_executing_callable(self, test_agent):
        baseline = set(server.list_registered_tools())
        assert baseline == EXPECTED_REGISTERED_TOOLS
        calls = []

        async def dynamic_output_contract(agent: str):
            """Test-only unclassified bridge-like producer; never execute it."""
            calls.append(agent)
            raise AssertionError("registry inspection must not execute a dynamic producer")

        name = "test_output_contract_dynamic"
        try:
            server.app.tool(name=name)(dynamic_output_contract)
            details = server.describe_registered_tools()
            assert set(details) == baseline | {name}
            assert set(server.list_registered_tools()) == baseline | {name}
            schema = details[name]["input_schema"]
            selector = schema["properties"].get("response_detail", {})
            assert selector.get("enum") == ["default", "full"]
            assert selector.get("default") == "default"
            assert "response_detail" not in inspect.signature(dynamic_output_contract).parameters
            assert calls == []
        finally:
            server._SCRIBE_TOOL_REGISTRY.pop(name, None)
            server._SCRIBE_TOOL_DEFS.pop(name, None)
        assert set(server.list_registered_tools()) == baseline
