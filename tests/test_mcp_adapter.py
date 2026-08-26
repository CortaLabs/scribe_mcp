"""Hermetic contract tests for the source-owned MCP compatibility adapter."""

from __future__ import annotations

import importlib.metadata
from types import SimpleNamespace

import pytest

from scribe_mcp.mcp_adapter import (
    MCPCompatibilityPolicy,
    MCPRuntime,
    ProtocolEra,
    build_mcp_server,
    classify_protocol_era,
    load_mcp_runtime,
    normalize_tool_definition,
    normalize_tool_result,
)


def test_load_mcp_runtime_selects_public_sdk_v2_surfaces():
    runtime = load_mcp_runtime()

    assert runtime.major == 2
    assert runtime.version == "2.0.0"
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
