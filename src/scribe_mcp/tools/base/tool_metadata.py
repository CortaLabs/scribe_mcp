"""Tool metadata framework for consistent tool descriptions and best practices.

Provides centralized tool metadata management including descriptions, examples,
parameter documentation, and usage patterns for all Scribe MCP tools.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ToolParameter:
    """Metadata for a tool parameter."""
    name: str
    type: str
    required: bool = False
    description: str = ""
    example: Optional[Any] = None
    default: Optional[Any] = None
    validation: Optional[str] = None
    deprecated: bool = False
    deprecation_message: Optional[str] = None


@dataclass
class ToolExample:
    """Example usage for a tool."""
    name: str
    description: str
    code: str
    result: Optional[str] = None
    context: Optional[str] = None


@dataclass
class ToolMetadata:
    """Comprehensive metadata for a tool."""
    name: str
    description: str
    category: str
    version: str = "1.0.0"
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[ToolExample] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    related_tools: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


# Tool registry for centralized metadata
TOOL_METADATA: Dict[str, ToolMetadata] = {
    "append_entry": ToolMetadata(
        name="append_entry",
        description="**PRIMARY TOOL** - Add structured log entries with metadata. Supports single entry and bulk modes with automatic multiline detection.",
        category="Logging",
        parameters=[
            ToolParameter(
                name="message",
                type="str",
                description="Log message (auto-splits multiline if auto_split=True)"
            ),
            ToolParameter(
                name="status",
                type="str",
                description="Status type (info|success|warn|error|bug|plan)",
                example="success"
            ),
            ToolParameter(
                name="emoji",
                type="str",
                description="Custom emoji override",
                example="✅"
            ),
            ToolParameter(
                name="meta",
                type="dict",
                description="Metadata dictionary (applied to all entries in bulk/split mode)",
                example={"phase": "development", "component": "auth"}
            ),
            ToolParameter(
                name="items",
                type="str",
                description="JSON string array for bulk mode (backwards compatibility)",
                example='[{"message": "Task completed", "status": "success"}]'
            ),
            ToolParameter(
                name="items_list",
                type="list",
                description="Direct list of entry dictionaries for bulk mode (NEW)",
                example=[{"message": "Task completed", "status": "success"}]
            ),
        ],
        examples=[
            ToolExample(
                name="Single entry",
                description="Log a single successful action",
                code='await append_entry(message="Fixed authentication bug", status="success", meta={"phase": "bugfix", "component": "auth"})',
                result="Creates one log entry with success emoji"
            ),
            ToolExample(
                name="Bulk mode",
                description="Log multiple entries at once",
                code='await append_entry(items_list=[{"message": "First task", "status": "success"}, {"message": "Second task", "status": "info"}])',
                result="Creates two separate log entries with individual timestamps"
            ),
        ],
        notes=[
            "Auto-detects multiline content and switches to bulk mode",
            "Supports both JSON string (items) and direct list (items_list) for bulk mode",
            "Each entry gets individual timestamps in bulk mode"
        ],
        tags=["logging", "primary", "bulk", "metadata"]
    ),

    "set_project": ToolMetadata(
        name="set_project",
        description="Create/select project and bootstrap docs. Auto-generates all 4 documentation files (ARCHITECTURE_GUIDE.md, PHASE_PLAN.md, CHECKLIST.md, PROGRESS_LOG.md).",
        category="Project Management",
        parameters=[
            ToolParameter(
                name="name",
                type="str",
                required=True,
                description="Project name"
            ),
            ToolParameter(
                name="root",
                type="str",
                description="Project root directory (required unless context repo_root is provided)"
            ),
            ToolParameter(
                name="defaults",
                type="dict",
                description="Project defaults including emoji and agent",
                example={"emoji": "🧪", "agent": "MyAgent"}
            ),
            ToolParameter(
                name="overwrite_docs",
                type="bool",
                description="Overwrite existing documentation files",
                default=False
            ),
        ],
        examples=[
            ToolExample(
                name="Basic project setup",
                description="Create a new project with default settings",
                code='await set_project(name="My Project", root="/path/to/repo")',
                result="Creates project with docs directory and 4 documentation files"
            ),
            ToolExample(
                name="Custom defaults",
                description="Create project with custom emoji and agent",
                code='await set_project(name="My Project", root="/path/to/repo", defaults={"emoji": "🚀", "agent": "DevBot"})',
                result="Project with custom rocket emoji and DevBot as default agent"
            ),
        ],
        notes=[
            "Automatically bootstraps documentation structure",
            "Supports agent-scoped project contexts",
            "Uses optimistic concurrency control for multi-agent environments"
        ],
        tags=["project", "setup", "documentation", "bootstrap"]
    ),

    "query_entries": ToolMetadata(
        name="query_entries",
        description="Advanced log searching and filtering with pagination. Supports text search, date ranges, agent filtering, and metadata filtering.",
        category="Search & Analysis",
        parameters=[
            ToolParameter(
                name="message",
                type="str",
                description="Message text filter"
            ),
            ToolParameter(
                name="message_mode",
                type="str",
                description="How to match message (substring, regex, exact)",
                default="substring",
                example="substring"
            ),
            ToolParameter(
                name="meta_filters",
                type="dict",
                description="Filter by metadata key/value pairs",
                example={"phase": "development", "component": "auth"}
            ),
            ToolParameter(
                name="agents",
                type="list",
                description="Filter by agent name(s)",
                example=["Scribe", "DevBot"]
            ),
            ToolParameter(
                name="start",
                type="str",
                description="Start timestamp filter (ISO format)",
                example="2025-10-23T00:00:00Z"
            ),
            ToolParameter(
                name="end",
                type="str",
                description="End timestamp filter (ISO format)",
                example="2025-10-24T23:59:59Z"
            ),
        ],
        examples=[
            ToolExample(
                name="Text search",
                description="Find entries containing specific text",
                code='await query_entries(message="authentication", message_mode="substring")',
                result="Returns all entries mentioning 'authentication'"
            ),
            ToolExample(
                name="Metadata filter",
                description="Find entries by metadata",
                code='await query_entries(meta_filters={"phase": "bugfix", "component": "auth"})',
                result="Returns entries from bugfix phase in auth component"
            ),
        ],
        notes=[
            "Supports both SQLite and PostgreSQL backends",
            "Intelligent pagination with performance optimization",
            "Regex support for advanced pattern matching"
        ],
        tags=["search", "filter", "analysis", "pagination"]
    ),

    "list_projects": ToolMetadata(
        name="list_projects",
        description="Discover available projects with intelligent filtering and pagination. Auto-excludes test/temp projects and provides context-safe responses.",
        category="Project Management",
        parameters=[
            ToolParameter(
                name="limit",
                type="int",
                description="Maximum number of projects to return (default: 5 for context safety)",
                default=5
            ),
            ToolParameter(
                name="include_test",
                type="bool",
                description="Include test/temp projects (default: False)",
                default=False
            ),
            ToolParameter(
                name="page",
                type="int",
                description="Page number for pagination",
                default=1
            ),
            ToolParameter(
                name="page_size",
                type="int",
                description="Number of projects per page",
                default=5
            ),
        ],
        examples=[
            ToolExample(
                name="List recent projects",
                description="Get 5 most recent active projects",
                code='await list_projects()',
                result="Returns up to 5 active projects, excluding test projects"
            ),
            ToolExample(
                name="Include test projects",
                description="List all projects including test/temp ones",
                code='await list_projects(include_test=True, limit=20)',
                result="Returns up to 20 projects including test projects"
            ),
        ],
        notes=[
            "Auto-excludes test projects (test-*, temp-*, demo-*, etc.)",
            "Provides token warnings for large responses",
            "Intelligent pagination prevents context window overflow"
        ],
        tags=["project", "discovery", "filtering", "safety"]
    ),

    "rotate_log": ToolMetadata(
        name="rotate_log",
        description="Archive current progress log and start fresh file with comprehensive auditability and integrity verification. Defaults to dry-run mode for safety.",
        category="Maintenance",
        parameters=[
            ToolParameter(
                name="confirm",
                type="bool",
                description="Must be True to perform actual rotation (default: False)",
                default=False
            ),
            ToolParameter(
                name="dry_run",
                type="bool",
                description="Simulate rotation without making changes (default: True)",
                default=True
            ),
            ToolParameter(
                name="suffix",
                type="str",
                description="Optional suffix for the archive filename",
                default="archive"
            ),
            ToolParameter(
                name="custom_metadata",
                type="str",
                description="JSON string of additional metadata to include",
                example='{"reason": "project_milestone", "version": "2.0.0"}'
            ),
        ],
        examples=[
            ToolExample(
                name="Preview rotation",
                description="See what would happen without actually rotating",
                code='await rotate_log()',
                result="Shows dry-run preview with file sizes and entry counts"
            ),
            ToolExample(
                name="Perform rotation",
                description="Actually rotate the log with confirmation",
                code='await rotate_log(confirm=True, suffix="milestone-1")',
                result="Archives current log and creates fresh one with milestone-1 suffix"
            ),
        ],
        warnings=[
            "Always defaults to dry-run mode for safety",
            "Use confirm=True to perform actual rotation",
            "Archives are cryptographically verified"
        ],
        notes=[
            "Atomic operations prevent data loss",
            "Comprehensive audit trail with integrity verification",
            "Supports custom metadata for rotation context"
        ],
        tags=["maintenance", "archive", "safety", "audit"]
    ),
}


def get_tool_metadata(tool_name: str) -> Optional[ToolMetadata]:
    """Get metadata for a specific tool."""
    return TOOL_METADATA.get(tool_name)


def list_tools_by_category(category: str) -> List[ToolMetadata]:
    """List all tools in a specific category."""
    return [tool for tool in TOOL_METADATA.values() if tool.category == category]


def list_deprecated_tools() -> List[ToolMetadata]:
    """List all deprecated tools with migration guidance."""
    return [tool for tool in TOOL_METADATA.values() if tool.deprecated]


def get_tool_examples(tool_name: str) -> List[ToolExample]:
    """Get examples for a specific tool."""
    metadata = get_tool_metadata(tool_name)
    return metadata.examples if metadata else []


def validate_tool_parameters(tool_name: str, params: Dict[str, Any]) -> List[str]:
    """Validate parameters against tool metadata requirements."""
    metadata = get_tool_metadata(tool_name)
    if not metadata:
        return [f"Unknown tool: {tool_name}"]

    errors = []
    required_params = [p for p in metadata.parameters if p.required]

    # Check for missing required parameters
    for param in required_params:
        if param.name not in params:
            errors.append(f"Missing required parameter: {param.name}")

    # Check for deprecated parameters
    for param in metadata.parameters:
        if param.deprecated and param.name in params:
            if param.deprecation_message:
                errors.append(f"Parameter '{param.name}' is deprecated: {param.deprecation_message}")
            else:
                errors.append(f"Parameter '{param.name}' is deprecated")

    return errors


def generate_tool_help(tool_name: str) -> Optional[str]:
    """Generate formatted help text for a tool."""
    metadata = get_tool_metadata(tool_name)
    if not metadata:
        return None

    help_text = [f"## {metadata.name}", f"**Category:** {metadata.category}", f"**Description:** {metadata.description}"]

    if metadata.deprecated:
        help_text.append(f"⚠️ **DEPRECATED:** {metadata.deprecation_message or 'This tool is deprecated'}")

    if metadata.parameters:
        help_text.append("\n### Parameters:")
        for param in metadata.parameters:
            required = "REQUIRED" if param.required else f"optional (default: {param.default})"
            help_text.append(f"- **{param.name}** ({param.type}) - {required}: {param.description}")
            if param.example:
                help_text.append(f"  - Example: `{param.example}`")
            if param.deprecated:
                help_text.append(f"  - ⚠️ *Deprecated:* {param.deprecation_message}")

    if metadata.examples:
        help_text.append("\n### Examples:")
        for example in metadata.examples:
            help_text.append(f"**{example.name}:** {example.description}")
            help_text.append(f"```python\n{example.code}\n```")
            if example.result:
                help_text.append(f"*Result:* {example.result}")

    if metadata.warnings:
        help_text.append("\n### ⚠️ Warnings:")
        for warning in metadata.warnings:
            help_text.append(f"- {warning}")

    if metadata.notes:
        help_text.append("\n### Notes:")
        for note in metadata.notes:
            help_text.append(f"- {note}")

    if metadata.related_tools:
        help_text.append(f"\n**Related Tools:** {', '.join(metadata.related_tools)}")

    if metadata.tags:
        help_text.append(f"\n**Tags:** {', '.join(['#' + tag for tag in metadata.tags])}")

    return "\n".join(help_text)
