"""Hermetic contract tests for the source-owned MCP compatibility adapter."""

from __future__ import annotations

import importlib.metadata
import copy
import json
from types import SimpleNamespace

import pytest

from scribe_mcp.mcp_adapter import (
    MCPCompatibilityPolicy,
    MCPRuntime,
    ProtocolEra,
    build_mcp_server,
    classify_protocol_era,
    configure_mcp_server,
    load_mcp_runtime,
    normalize_tool_definition,
    normalize_tool_result,
)


def test_load_mcp_runtime_selects_public_sdk_v2_surfaces():
    runtime = load_mcp_runtime()

    assert runtime.major == 2
    assert runtime.version.startswith("2.")
    assert runtime.server_type.__name__ == "MCPServer"
    assert runtime.types.Tool.__module__.startswith("mcp_types")
    assert callable(runtime.stdio.stdio_server)


@pytest.mark.parametrize("version", ["", "latest", "2x", " 2.0.0"])
def test_load_mcp_runtime_rejects_malformed_versions(monkeypatch, version):
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: version)

    with pytest.raises(RuntimeError, match="malformed mcp distribution version"):
        load_mcp_runtime()


@pytest.mark.parametrize("version", ["1.26.0", "3.0.0"])
def test_load_mcp_runtime_rejects_unsupported_majors(monkeypatch, version):
    monkeypatch.setattr(importlib.metadata, "version", lambda _name: version)

    with pytest.raises(RuntimeError, match="unsupported mcp distribution major"):
        load_mcp_runtime()


def test_load_mcp_runtime_rejects_missing_distribution(monkeypatch):
    def missing(_name):
        raise importlib.metadata.PackageNotFoundError("mcp")

    monkeypatch.setattr(importlib.metadata, "version", missing)

    with pytest.raises(RuntimeError, match="mcp distribution is not installed"):
        load_mcp_runtime()


def test_load_mcp_runtime_does_not_swallow_transitive_import_failures(monkeypatch):
    original_import = importlib.import_module

    def broken_import(name):
        if name == "mcp.server.mcpserver":
            error = ImportError("missing transitive dependency")
            error.name = "unrelated_dependency"
            raise error
        return original_import(name)

    monkeypatch.setattr(importlib, "import_module", broken_import)

    with pytest.raises(RuntimeError, match="required public MCP SDK v2 surface") as exc_info:
        load_mcp_runtime()

    assert isinstance(exc_info.value.__cause__, ImportError)
    assert exc_info.value.__cause__.name == "unrelated_dependency"


def test_protocol_era_classification_is_explicit_and_closed():
    assert MCPCompatibilityPolicy().legacy_revisions == ("2025-11-25",)
    assert classify_protocol_era(
        protocol_revision=None,
        transport="stdio",
        explicit_legacy=False,
    ) is ProtocolEra.MODERN
    assert classify_protocol_era(
        protocol_revision="2025-11-25",
        transport="http-sse",
        explicit_legacy=True,
    ) is ProtocolEra.LEGACY

    with pytest.raises(ValueError, match="explicit legacy mode"):
        classify_protocol_era(
            protocol_revision="2025-11-25",
            transport="stdio",
            explicit_legacy=False,
        )
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2025-06-18",
            transport="stdio",
            explicit_legacy=True,
        )
    with pytest.raises(ValueError, match="unsupported MCP protocol revision"):
        classify_protocol_era(
            protocol_revision="2024-11-05",
            transport="stdio",
            explicit_legacy=True,
        )
    with pytest.raises(ValueError, match="unsupported MCP transport"):
        classify_protocol_era(
            protocol_revision="2026-07-28",
            transport="sse",
            explicit_legacy=False,
        )


@pytest.mark.parametrize("era", [ProtocolEra.MODERN, ProtocolEra.LEGACY])
def test_tool_definition_preserves_schema_metadata_and_hints(era):
    runtime = load_mcp_runtime()
    tool = normalize_tool_definition(
        runtime=runtime,
        era=era,
        name="sample",
        title="Sample",
        description="Sample tool",
        input_schema={
            "type": "object",
            "properties": {"agent": {"type": "string"}},
            "required": ["agent"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        annotations={"readOnlyHint": True},
        execution={"taskSupport": "forbidden"},
        meta={"scribe": {"trustTier": 0}},
        tags=["read-only", "context"],
    )

    payload = tool.model_dump(by_alias=True, exclude_none=True)
    assert payload["name"] == "sample"
    assert payload["inputSchema"]["required"] == ["agent"]
    assert payload["outputSchema"] == {"type": "object"}
    assert payload["annotations"]["readOnlyHint"] is True
    assert payload["execution"]["taskSupport"] == "forbidden"
    assert payload["_meta"]["scribe"]["trustTier"] == 0
    assert payload["_meta"]["scribe"]["tags"] == ["read-only", "context"]


def test_tool_definition_rejects_malformed_schema():
    runtime = load_mcp_runtime()

    with pytest.raises(ValueError, match="required property"):
        normalize_tool_definition(
            runtime=runtime,
            era=ProtocolEra.MODERN,
            name="bad",
            description="bad",
            input_schema={"type": "object", "properties": {}, "required": ["agent"]},
        )


@pytest.mark.parametrize("era", [ProtocolEra.MODERN, ProtocolEra.LEGACY])
def test_result_normalization_preserves_structured_text_and_error_semantics(era):
    runtime = load_mcp_runtime()
    success = normalize_tool_result(
        {"ok": True, "count": 2}, runtime=runtime, era=era
    )
    error = normalize_tool_result(
        {
            "content": [{"type": "text", "text": "denied"}],
            "structuredContent": {"ok": False, "reason": "denied"},
            "isError": True,
        },
        runtime=runtime,
        era=era,
    )

    assert success.structured_content == {"ok": True, "count": 2}
    assert success.content[0].text == '{"count":2,"ok":true}'
    assert success.is_error is False
    assert error.structured_content == {"ok": False, "reason": "denied"}
    assert error.content[0].text == "denied"
    assert error.is_error is True


def test_build_mcp_server_uses_the_public_sdk_v2_surface():
    server = build_mcp_server("scribe-test", MCPCompatibilityPolicy())

    assert type(server).__name__ == "MCPServer"
    assert callable(server.list_tools)
    assert callable(server.call_tool)
    assert callable(server.run_stdio_async)


@pytest.mark.asyncio
@pytest.mark.parametrize("era", [ProtocolEra.MODERN, ProtocolEra.LEGACY])
async def test_first_call_loads_lazy_definitions_and_preserves_refusals(era):
    runtime = load_mcp_runtime()
    server = build_mcp_server("scribe-lazy-test", MCPCompatibilityPolicy())
    definitions = {}
    events = []

    async def list_handler(request_era):
        assert request_era is era
        events.append("load")
        definitions["sample"] = normalize_tool_definition(
            runtime=runtime,
            era=ProtocolEra.MODERN,
            name="sample",
            description="A lazily registered tool",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        return list(definitions.values())

    async def call_handler(name, arguments, context, request_era):
        assert name == "sample"
        assert request_era is era
        assert context is None
        events.append("call")
        return {"ok": True, "value": arguments["value"]}

    configure_mcp_server(
        server,
        runtime=runtime,
        definition_provider=lambda: definitions,
        list_handler=list_handler,
        call_handler=call_handler,
    )

    for value in ("first", "warm"):
        result = await server.call_tool("sample", {"value": value}, protocol_era=era)
        assert result.structured_content == {"ok": True, "value": value}
        assert result.is_error is False
    assert events == ["load", "call", "call"]

    for invalid in ({}, {"value": 1}, {"value": "valid", "extra": True}):
        with pytest.raises(ValueError, match="invalid arguments"):
            await server.call_tool("sample", invalid, protocol_era=era)
    assert events == ["load", "call", "call"]

    with pytest.raises(ValueError, match="Unknown tool"):
        await server.call_tool("missing", {}, protocol_era=era)
    assert events.count("call") == 2


@pytest.mark.core
@pytest.mark.regression
class TestSBRDefaultOutput:
    """Adapter value/serialization tests; no authenticated caller is simulated."""

    @staticmethod
    def _size(result):
        payload = result.model_dump(by_alias=True, exclude_none=True)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        actual_sdk = result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")
        return len(canonical), len(actual_sdk)

    @pytest.mark.parametrize("era", list(ProtocolEra))
    @pytest.mark.parametrize("kind", ["raw-dict", "raw-string", "text-structured", "sdk-result"])
    def test_current_default_raw_and_existing_sdk_envelopes_fit(self, test_agent, era, kind):
        runtime = load_mcp_runtime()
        value = "漢🌊\\\"\n" * 20000
        data = {"ok": True, "metadata": {"notes": value}, "count": 1}
        if kind == "raw-dict":
            source = data
        elif kind == "raw-string":
            source = value
        else:
            source = {"content": [{"type": "text", "text": json.dumps(data)}],
                      "structuredContent": data, "isError": False}
            if kind == "sdk-result":
                source = runtime.types.CallToolResult(**source)
        before = copy.deepcopy(source)
        result = normalize_tool_result(source, runtime=runtime, era=era)
        canonical, sdk = self._size(result)
        assert source == before
        print(json.dumps({"fixture": "adapter-default", "era": era.value, "kind": kind,
                          "canonical_bytes": canonical, "sdk_bytes": sdk}))
        assert max(canonical, sdk) <= 2048, f"adapter bytes canonical={canonical} sdk={sdk}"

    @pytest.mark.parametrize("era", list(ProtocolEra))
    def test_normalizer_preserves_exact_control_facts(self, test_agent, era):
        """Small transient control values, independent of runtime authentication."""
        runtime = load_mcp_runtime()
        data = {"ok": True, "entries": [{"id": 1, "message": "漢🌊"}],
                "binding": {"id": "b" * 64, "generation": 23, "reused": True, "write_performed": False},
                "durability": {"file": "committed", "db_mirror": "queued", "audit_id": "a" * 64},
                "convergence": {"state": "queued", "digest": "d" * 64, "generation": 8, "replay": False},
                "retry": {"queued": True, "retryable": False, "retry_after_ms": 1200},
                "correlation_id": "c" * 64, "release_handle": "response-only-control"}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=runtime, era=era)
        assert result.structured_content == before
        assert json.loads(result.content[0].text) == before
        assert result.is_error is False
        assert data == before

    @pytest.mark.parametrize("era", list(ProtocolEra))
    @pytest.mark.parametrize("code", ["SCRIBE_OUTPUT_DETAIL_REQUIRED", "SCRIBE_FACT_PERSISTENCE_FAILED", "UNKNOWN_TOOL"])
    def test_error_control_retry_and_effect_facts_survive_both_eras(self, test_agent, era, code):
        runtime = load_mcp_runtime()
        data = {"schema_version": "scribe-error-summary.v1", "ok": False, "error_code": code,
                "message": "Use explicit full detail for this operation.", "retryable": False,
                "correlation_id": "c" * 64, "retry_after_ms": 1200,
                "effect_status": "unknown", "mutation_retry_safe": False,
                "target": {"state": "not_disclosed"},
                "candidates": {"state": "unavailable", "total_count": None}}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=runtime, era=era, is_error=True)
        assert result.is_error is True
        assert result.structured_content == before
        assert json.loads(result.content[0].text) == before
        assert max(self._size(result)) <= 2048
        assert data == before

    @pytest.mark.parametrize("era", list(ProtocolEra))
    def test_legacy_text_only_projection_remains_complete_json(self, test_agent, era):
        projected = {"ok": True, "kind": "preview", "returned_count": 3, "total_count": 10,
                     "omitted_count": 7, "complete": False,
                     "continuation": {"tool": "read_recent", "arguments": {"page": 4, "response_detail": "full"},
                                      "consistency": "current"}}
        result = normalize_tool_result(
            {"content": [{"type": "text", "text": json.dumps(projected)}], "isError": False},
            runtime=load_mcp_runtime(), era=era)
        assert json.loads(result.content[0].text) == projected
        assert max(self._size(result)) <= 2048

    @pytest.mark.asyncio
    @pytest.mark.parametrize("era", list(ProtocolEra))
    @pytest.mark.parametrize("selector", [None, False, 0, 1, [], {}, "", "FULL", " full", "full ", "unknown"])
    async def test_invalid_detail_is_rejected_before_adapter_producer(self, test_agent, era, selector):
        from scribe_mcp import server as source_server

        runtime = load_mcp_runtime()
        sdk_server = build_mcp_server("scribe-output-selector-test", MCPCompatibilityPolicy())
        source_server.list_registered_tools()
        definition = source_server._SCRIBE_TOOL_DEFS["append_entry"]
        calls = []

        async def list_handler(request_era):
            return [definition]

        async def producer(name, arguments, context, request_era):
            calls.append(name)
            return {"ok": True}

        configure_mcp_server(sdk_server, runtime=runtime,
                             definition_provider=lambda: {"append_entry": definition},
                             list_handler=list_handler, call_handler=producer)
        with pytest.raises(ValueError, match="response_detail|invalid arguments"):
            await sdk_server.call_tool("append_entry", {"agent": test_agent, "message": "one write",
                                                       "response_detail": selector}, protocol_era=era)
        assert calls == [], f"invalid detail reached producer {len(calls)} time(s)"

    @pytest.mark.parametrize("era", list(ProtocolEra))
    def test_raw_early_error_is_bounded_and_marked_error(self, test_agent, era):
        data = {"ok": False, "error_code": "SCRIBE_ARGUMENT_INVALID", "retryable": False,
                "correlation_id": "c" * 64, "effect_status": "none", "mutation_retry_safe": True,
                "message": "Invalid input", "debug": {"exception_notes": "x" * 100000}}
        before = copy.deepcopy(data)
        result = normalize_tool_result(data, runtime=load_mcp_runtime(), era=era)
        canonical, sdk = self._size(result)
        error_flag = result.is_error
        assert data == before
        print(json.dumps({"fixture": "early-error", "era": era.value,
                          "canonical_bytes": canonical, "sdk_bytes": sdk, "is_error": error_flag}))
        assert error_flag is True
        assert max(canonical, sdk) <= 2048
        for field in ("ok", "error_code", "retryable", "correlation_id", "effect_status", "mutation_retry_safe"):
            assert result.structured_content[field] == before[field]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("era", list(ProtocolEra))
    async def test_explicit_full_adapter_preserves_transient_content_once(self, test_agent, era):
        """SDK adapter proof only; the external producer makes no authority grant."""
        runtime = load_mcp_runtime()
        sdk_server = build_mcp_server("scribe-output-full-test", MCPCompatibilityPolicy())
        definition = normalize_tool_definition(
            runtime=runtime, era=era, name="selected_output", description="Test-only value producer",
            input_schema={"type": "object", "properties": {
                "agent": {"type": "string"},
                "response_detail": {"type": "string", "enum": ["default", "full"], "default": "default"}},
                "required": ["agent"], "additionalProperties": False})
        data = {"ok": True, "body": "漢🌊\\\"\n" * 20000,
                "apply": {"receipt": "test-only-response-control", "expires_at": "2030-01-01T00:00:00Z"}}
        calls = []

        async def list_handler(request_era):
            return [definition]

        async def producer(name, arguments, context, request_era):
            calls.append(name)
            return copy.deepcopy(data)

        configure_mcp_server(sdk_server, runtime=runtime,
                             definition_provider=lambda: {"selected_output": definition},
                             list_handler=list_handler, call_handler=producer)
        result = await sdk_server.call_tool("selected_output", {"agent": test_agent, "response_detail": "full"},
                                            protocol_era=era)
        assert calls == ["selected_output"]
        assert result.structured_content == data
        assert json.loads(result.content[0].text) == data
