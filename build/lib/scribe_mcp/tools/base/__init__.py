"""Base tool infrastructure for unified Scribe MCP tool development."""

from .base_tool import BaseTool
from .tool_result import ToolResult
from .parameter_normalizer import normalize_dict_param, normalize_list_param
from .tool_metadata import (
    ToolMetadata,
    ToolParameter,
    ToolExample,
    get_tool_metadata,
    list_tools_by_category,
    list_deprecated_tools,
    get_tool_examples,
    validate_tool_parameters,
    generate_tool_help,
    TOOL_METADATA
)

__all__ = [
    'BaseTool',
    'ToolResult',
    'normalize_dict_param',
    'normalize_list_param',
    'ToolMetadata',
    'ToolParameter',
    'ToolExample',
    'get_tool_metadata',
    'list_tools_by_category',
    'list_deprecated_tools',
    'get_tool_examples',
    'validate_tool_parameters',
    'generate_tool_help',
    'TOOL_METADATA'
]