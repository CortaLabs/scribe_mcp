"""Source-owned MCP SDK, protocol-era, tool, and result compatibility boundary."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from types import MethodType, ModuleType, SimpleNamespace
from typing import Any, Awaitable, Callable, Mapping, Sequence


class ProtocolEra(str, Enum):
    """The finite protocol eras supported by Scribe."""

    MODERN = "modern"
    LEGACY = "legacy"


@dataclass(frozen=True, slots=True)
class MCPCompatibilityPolicy:
    """Closed compatibility policy for Scribe's supported MCP clients."""

    default_revision: str = "2026-07-28"
    legacy_revisions: tuple[str, ...] = ("2025-11-25",)
    modern_transports: tuple[str, ...] = ("stdio", "streamable-http")
    legacy_transports: tuple[str, ...] = ("stdio", "http-sse")
    legacy_enabled: bool = True

    def __post_init__(self) -> None:
        _validate_revision(self.default_revision, field="default_revision")
        if not self.legacy_revisions:
            raise ValueError("legacy_revisions must not be empty")
        for revision in self.legacy_revisions:
            _validate_revision(revision, field="legacy revision")
        if self.default_revision in self.legacy_revisions:
            raise ValueError("modern and legacy protocol revisions must be distinct")
        _validate_transport_set(self.modern_transports, field="modern_transports")
        _validate_transport_set(self.legacy_transports, field="legacy_transports")


@dataclass(frozen=True, slots=True)
class MCPRuntime:
    """Resolved public MCP SDK v2 surfaces used by Scribe."""

    version: str
    major: int
    server_type: type[Any]
    types: ModuleType
    stdio: ModuleType


ToolListHandler = Callable[[ProtocolEra], Awaitable[Sequence[Any]]]
ToolCallHandler = Callable[[str, dict[str, Any], Any, ProtocolEra], Awaitable[Any]]
ToolDefinitionProvider = Callable[[], Mapping[str, Any]]


_VERSION_PATTERN = re.compile(r"(?P<major>[0-9]+)(?:\.[0-9A-Za-z][0-9A-Za-z.+-]*)*")
_REVISION_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_JSON_TYPES = {
    "null": type(None),
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "string": str,
    "array": list,
    "object": dict,
}


def _validate_revision(value: str, *, field: str) -> None:
    if not isinstance(value, str) or _REVISION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be an YYYY-MM-DD protocol revision")


def _validate_transport_set(value: tuple[str, ...], *, field: str) -> None:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{field} must be a non-empty tuple")
    if any(not isinstance(item, str) or not item or item != item.strip() for item in value):
        raise ValueError(f"{field} contains a malformed transport")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} contains duplicate transports")


def load_mcp_runtime() -> MCPRuntime:
    """Load the required public MCP SDK v2 surfaces and fail closed otherwise."""

    try:
        version = importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError("mcp distribution is not installed") from exc
    if not isinstance(version, str) or version != version.strip():
        raise RuntimeError("malformed mcp distribution version")
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise RuntimeError("malformed mcp distribution version")
    major = int(match.group("major"))
    if major != 2:
        raise RuntimeError(f"unsupported mcp distribution major: {major}")

    try:
        server_module = importlib.import_module("mcp.server.mcpserver")
        types_module = importlib.import_module("mcp.types")
        stdio_module = importlib.import_module("mcp.server.stdio")
        server_type = getattr(server_module, "MCPServer")
        getattr(types_module, "Tool")
        getattr(types_module, "CallToolResult")
        getattr(types_module, "TextContent")
        getattr(stdio_module, "stdio_server")
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("required public MCP SDK v2 surface is unavailable") from exc
    if not isinstance(server_type, type):
        raise RuntimeError("required public MCP SDK v2 server surface is malformed")
    return MCPRuntime(
        version=version,
        major=major,
        server_type=server_type,
        types=types_module,
        stdio=stdio_module,
    )


def build_mcp_server(name: str, policy: MCPCompatibilityPolicy) -> Any:
    """Construct Scribe's server from the public MCP SDK v2 surface."""

    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError("MCP server name must be a non-empty normalized string")
    if not isinstance(policy, MCPCompatibilityPolicy):
        raise TypeError("policy must be MCPCompatibilityPolicy")
    runtime = load_mcp_runtime()
    server = runtime.server_type(name=name)
    setattr(server, "scribe_compatibility_policy", policy)
    return server


def classify_protocol_era(
    *,
    protocol_revision: str | None,
    transport: str,
    explicit_legacy: bool,
) -> ProtocolEra:
    """Classify only the frozen modern and named-legacy combinations."""

    policy = MCPCompatibilityPolicy()
    if not isinstance(transport, str) or not transport or transport != transport.strip():
        raise ValueError("unsupported MCP transport")
    if type(explicit_legacy) is not bool:
        raise TypeError("explicit_legacy must be boolean")
    if protocol_revision is not None:
        _validate_revision(protocol_revision, field="protocol_revision")

    if explicit_legacy:
        if not policy.legacy_enabled:
            raise ValueError("legacy MCP compatibility is disabled")
        revision = protocol_revision or policy.legacy_revisions[0]
        if revision not in policy.legacy_revisions:
            raise ValueError(f"unsupported MCP protocol revision: {revision}")
        if transport not in policy.legacy_transports:
            raise ValueError(f"unsupported MCP transport for legacy era: {transport}")
        return ProtocolEra.LEGACY

    revision = protocol_revision or policy.default_revision
    if revision in policy.legacy_revisions:
        raise ValueError("legacy MCP revision requires explicit legacy mode")
    if revision != policy.default_revision:
        raise ValueError(f"unsupported MCP protocol revision: {revision}")
    if transport not in policy.modern_transports:
        raise ValueError(f"unsupported MCP transport for modern era: {transport}")
    return ProtocolEra.MODERN


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON-compatible values") from exc


def _validate_schema(schema: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    copied = _json_copy(dict(schema), field=field)
    if not isinstance(copied, dict) or copied.get("type") != "object":
        raise ValueError(f"{field} must be an object JSON schema")
    properties = copied.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"{field} properties must be an object")
    required = copied.get("required", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError(f"{field} required must be a string list")
    for item in required:
        if item not in properties:
            raise ValueError(f"{field} required property {item!r} is not declared")
    if len(set(required)) != len(required):
        raise ValueError(f"{field} contains duplicate required properties")
    return copied


def _model_value(value: Any, model_type: type[Any], *, field: str) -> Any:
    if value is None or isinstance(value, model_type):
        return value
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be a mapping or {model_type.__name__}")
    return model_type(**dict(value))


def _install_model_aliases(model: Any) -> None:
    """Keep existing Scribe readback attributes while wire models use snake case."""

    model_fields = getattr(type(model), "model_fields", {})
    for field_name, field_info in model_fields.items():
        alias = getattr(field_info, "alias", None)
        if not isinstance(alias, str) or alias == field_name or not alias.isidentifier():
            continue
        object.__setattr__(model, alias, getattr(model, field_name))


def normalize_tool_definition(
    *,
    runtime: MCPRuntime,
    era: ProtocolEra,
    name: str,
    description: str,
    input_schema: Mapping[str, Any],
    output_schema: Mapping[str, Any] | None = None,
    title: str | None = None,
    annotations: Any = None,
    icons: Sequence[Any] | None = None,
    meta: Mapping[str, Any] | None = None,
    execution: Any = None,
    tags: Sequence[str] | None = None,
) -> Any:
    """Build one canonical tool definition for modern or named-legacy listing."""

    if not isinstance(runtime, MCPRuntime) or runtime.major != 2:
        raise TypeError("runtime must be a loaded MCP SDK v2 runtime")
    if not isinstance(era, ProtocolEra):
        raise ValueError("unsupported MCP protocol era")
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise ValueError("tool name must be a non-empty normalized string")
    if not isinstance(description, str):
        raise TypeError("tool description must be a string")
    normalized_input = _validate_schema(input_schema, field="input_schema")
    normalized_output = (
        _validate_schema(output_schema, field="output_schema")
        if output_schema is not None
        else None
    )
    normalized_meta = _json_copy(dict(meta or {}), field="meta")
    normalized_tags: list[str] = []
    for raw_tag in tags or ():
        if not isinstance(raw_tag, str) or not raw_tag.strip():
            raise ValueError("tool tags must be non-empty strings")
        tag = raw_tag.strip()
        if tag not in normalized_tags:
            normalized_tags.append(tag)
    if normalized_tags:
        scribe_meta = normalized_meta.setdefault("scribe", {})
        if not isinstance(scribe_meta, dict):
            raise ValueError("meta.scribe must be an object")
        scribe_meta["tags"] = normalized_tags

    normalized_annotations = _model_value(
        annotations, runtime.types.ToolAnnotations, field="annotations"
    )
    normalized_execution = _model_value(
        execution, runtime.types.ToolExecution, field="execution"
    )
    normalized_icons = None
    if icons is not None:
        if isinstance(icons, (str, bytes)):
            raise TypeError("icons must be a sequence")
        normalized_icons = [
            _model_value(icon, runtime.types.Icon, field="icon") for icon in icons
        ]
    tool = runtime.types.Tool(
        name=name,
        title=title,
        description=description,
        inputSchema=normalized_input,
        outputSchema=normalized_output,
        annotations=normalized_annotations,
        icons=normalized_icons,
        _meta=normalized_meta or None,
        execution=normalized_execution,
    )
    _install_model_aliases(tool)
    if normalized_annotations is not None:
        _install_model_aliases(normalized_annotations)
    if normalized_execution is not None:
        _install_model_aliases(normalized_execution)
    for icon in normalized_icons or ():
        _install_model_aliases(icon)
    object.__setattr__(tool, "tags", list(normalized_tags))
    return tool


def _content_block(runtime: MCPRuntime, block: Any) -> Any:
    if not isinstance(block, Mapping):
        if hasattr(block, "model_dump"):
            return block
        raise TypeError("MCP result content entries must be mappings or MCP content models")
    block_type = block.get("type")
    model_names = {
        "text": "TextContent",
        "image": "ImageContent",
        "audio": "AudioContent",
        "resource": "EmbeddedResource",
        "resource_link": "ResourceLink",
    }
    model_name = model_names.get(block_type)
    if model_name is None:
        raise ValueError(f"unsupported MCP content block type: {block_type!r}")
    return getattr(runtime.types, model_name)(**dict(block))


def normalize_tool_result(
    result: Any,
    *,
    runtime: MCPRuntime,
    era: ProtocolEra,
    is_error: bool = False,
) -> Any:
    """Normalize one Scribe result without duplicating or diverging its payload."""

    if not isinstance(runtime, MCPRuntime) or runtime.major != 2:
        raise TypeError("runtime must be a loaded MCP SDK v2 runtime")
    if not isinstance(era, ProtocolEra):
        raise ValueError("unsupported MCP protocol era")
    if type(is_error) is not bool:
        raise TypeError("is_error must be boolean")
    if isinstance(result, runtime.types.CallToolResult):
        _install_model_aliases(result)
        return result

    if isinstance(result, Mapping) and "content" in result:
        content = result.get("content")
        if isinstance(content, (str, bytes)) or not isinstance(content, Sequence):
            raise TypeError("MCP result content must be a sequence")
        structured = result.get("structuredContent", result.get("structured_content"))
        if structured is not None and not isinstance(structured, Mapping):
            raise TypeError("MCP structured content must be an object")
        error_flag = result.get("isError", result.get("is_error", is_error))
        if type(error_flag) is not bool:
            raise TypeError("MCP result error flag must be boolean")
        normalized = runtime.types.CallToolResult(
            content=[_content_block(runtime, block) for block in content],
            structuredContent=_json_copy(dict(structured), field="structuredContent")
            if structured is not None
            else None,
            isError=error_flag,
        )
        _install_model_aliases(normalized)
        return normalized

    if isinstance(result, Mapping):
        structured = _json_copy(dict(result), field="result")
        text = json.dumps(structured, sort_keys=True, separators=(",", ":"), allow_nan=False)
        normalized = runtime.types.CallToolResult(
            content=[runtime.types.TextContent(type="text", text=text)],
            structuredContent=structured,
            isError=is_error,
        )
        _install_model_aliases(normalized)
        return normalized
    if isinstance(result, str):
        normalized = runtime.types.CallToolResult(
            content=[runtime.types.TextContent(type="text", text=result)],
            isError=is_error,
        )
        _install_model_aliases(normalized)
        return normalized
    structured = {"result": _json_copy(result, field="result")}
    text = json.dumps(structured, sort_keys=True, separators=(",", ":"), allow_nan=False)
    normalized = runtime.types.CallToolResult(
        content=[runtime.types.TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=is_error,
    )
    _install_model_aliases(normalized)
    return normalized


def _schema_matches(value: Any, schema: Mapping[str, Any]) -> bool:
    if "enum" in schema and value not in schema["enum"]:
        return False
    alternatives = schema.get("anyOf") or schema.get("oneOf")
    if alternatives is not None:
        return isinstance(alternatives, list) and any(
            isinstance(item, Mapping) and _schema_matches(value, item) for item in alternatives
        )
    expected = schema.get("type")
    if expected is None:
        return True
    expected_types = expected if isinstance(expected, list) else [expected]
    for type_name in expected_types:
        python_type = _JSON_TYPES.get(type_name)
        if python_type is None:
            continue
        if type_name == "integer" and isinstance(value, bool):
            continue
        if type_name == "number" and isinstance(value, bool):
            continue
        if isinstance(value, python_type):
            return True
    return False


def validate_tool_arguments(tool_definition: Any, arguments: Mapping[str, Any]) -> None:
    """Validate the object-schema subset Scribe publishes before dispatch."""

    if not isinstance(arguments, Mapping):
        raise ValueError("invalid arguments: expected an object")
    schema = getattr(tool_definition, "input_schema", None)
    if schema is None:
        schema = getattr(tool_definition, "inputSchema", None)
    if not isinstance(schema, Mapping):
        raise ValueError("invalid tool schema")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    missing = [name for name in required if name not in arguments]
    if missing:
        raise ValueError(f"invalid arguments: missing required {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        extras = sorted(set(arguments) - set(properties))
        if extras:
            raise ValueError(f"invalid arguments: unexpected {', '.join(extras)}")
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if isinstance(property_schema, Mapping) and not _schema_matches(value, property_schema):
            raise ValueError(f"invalid arguments: {name} does not match its schema")


def configure_mcp_server(
    server: Any,
    *,
    runtime: MCPRuntime,
    definition_provider: ToolDefinitionProvider,
    list_handler: ToolListHandler,
    call_handler: ToolCallHandler,
) -> None:
    """Bind Scribe's one registry to the public SDK list/call server methods."""

    if not isinstance(server, runtime.server_type):
        raise TypeError("server does not match the loaded MCP runtime")

    async def list_tools_bound(
        _server: Any,
        *,
        protocol_era: ProtocolEra = ProtocolEra.MODERN,
    ) -> list[Any]:
        if not isinstance(protocol_era, ProtocolEra):
            raise ValueError("unsupported MCP protocol era")
        return list(await list_handler(protocol_era))

    async def call_tool_bound(
        _server: Any,
        name: str,
        arguments: dict[str, Any],
        context: Any = None,
        *,
        protocol_era: ProtocolEra = ProtocolEra.MODERN,
    ) -> Any:
        if not isinstance(protocol_era, ProtocolEra):
            raise ValueError("unsupported MCP protocol era")
        definitions = definition_provider()
        definition = definitions.get(name)
        if definition is None:
            raise ValueError(f"Unknown tool {name!r}")
        validate_tool_arguments(definition, arguments)
        raw_result = await call_handler(name, dict(arguments), context, protocol_era)
        return normalize_tool_result(raw_result, runtime=runtime, era=protocol_era)

    server.list_tools = MethodType(list_tools_bound, server)
    server.call_tool = MethodType(call_tool_bound, server)

    async def call_request_handler(request: Any) -> Any:
        params = request.params
        result = await server.call_tool(params.name, dict(params.arguments or {}))
        return SimpleNamespace(root=result)

    async def list_request_handler(_request: Any) -> Any:
        result = runtime.types.ListToolsResult(tools=await server.list_tools())
        return SimpleNamespace(root=result)

    server.request_handlers = {
        runtime.types.CallToolRequest: call_request_handler,
        runtime.types.ListToolsRequest: list_request_handler,
    }


__all__ = [
    "MCPCompatibilityPolicy",
    "MCPRuntime",
    "ProtocolEra",
    "build_mcp_server",
    "classify_protocol_era",
    "configure_mcp_server",
    "load_mcp_runtime",
    "normalize_tool_definition",
    "normalize_tool_result",
    "validate_tool_arguments",
]
