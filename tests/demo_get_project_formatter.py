#!/usr/bin/env python3
"""
Visual demo of format_project_context() output.

Shows what the "Where am I?" formatter actually produces.
"""

import sys
from pathlib import Path

# Add MCP_SPINE to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scribe_mcp.utils.response import ResponseFormatter


def demo_full_context():
    """Demonstrate full context output with 5 entries."""
    print("=" * 80)
    print("DEMO: Full Project Context (5 entries)")
    print("=" * 80)
    print()

    formatter = ResponseFormatter()

    project = {
        "name": "scribe_tool_output_refinement",
        "root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
        "progress_log": "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/scribe_tool_output_refinement/PROGRESS_LOG.md"
    }

    docs_info = {
        "architecture": {"exists": True, "lines": 1274},
        "phase_plan": {"exists": True, "lines": 542},
        "checklist": {"exists": True, "lines": 356},
        "progress": {"exists": True, "entries": 298}
    }

    activity = {
        "status": "in_progress",
        "total_entries": 298,
        "last_entry_at": "2026-01-03T08:15:30Z"
    }

    recent_entries = [
        {
            "timestamp": "2026-01-03T09:53:42Z",
            "emoji": "🧭",
            "agent": "Orchestrator",
            "message": "Refined approach: Use existing format parameter in list_projects tool instead of creating new tool"
        },
        {
            "timestamp": "2026-01-03 09:48:15 UTC",
            "emoji": "🧭",
            "agent": "Orchestrator",
            "message": "Code audit complete: list_projects returns massive JSON blob - must add context hydration"
        },
        {
            "timestamp": "2026-01-03T09:45:00Z",
            "emoji": "🧭",
            "agent": "Orchestrator",
            "message": "Planning session started: Phase 4 continuation after test fixes"
        },
        {
            "timestamp": "2026-01-03T05:24:18Z",
            "emoji": "✅",
            "agent": "Orchestrator",
            "message": "Fixed test_query_priority_filters.py - Root cause was default priority filtering in query_entries"
        },
        {
            "timestamp": "2026-01-03T05:18:42Z",
            "emoji": "⚠️",
            "agent": "Orchestrator",
            "message": "Batch 3 Complete (with test issues) - 5 tests passing, 1 failing (investigating)"
        }
    ]

    result = formatter.format_project_context(
        project,
        recent_entries,
        docs_info,
        activity
    )

    print(result)
    print()


def demo_partial_context():
    """Demonstrate context with only 2 entries (shows hint)."""
    print("=" * 80)
    print("DEMO: Partial Project Context (2 entries - shows hint)")
    print("=" * 80)
    print()

    formatter = ResponseFormatter()

    project = {
        "name": "new_project",
        "root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
        "progress_log": "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/new_project/PROGRESS_LOG.md"
    }

    docs_info = {
        "architecture": {"exists": True, "lines": 200},
        "phase_plan": {"exists": False, "lines": 0},  # Missing
        "checklist": {"exists": True, "lines": 50},
        "progress": {"exists": True, "entries": 2}
    }

    activity = {
        "status": "planning",
        "total_entries": 2,
        "last_entry_at": "2026-01-03T10:00:00Z"
    }

    recent_entries = [
        {
            "timestamp": "2026-01-03T10:00:00Z",
            "emoji": "✅",
            "agent": "Architect",
            "message": "Created initial architecture design"
        },
        {
            "timestamp": "2026-01-03T09:30:00Z",
            "emoji": "🔍",
            "agent": "ResearchAgent",
            "message": "Completed initial research phase"
        }
    ]

    result = formatter.format_project_context(
        project,
        recent_entries,
        docs_info,
        activity
    )

    print(result)
    print()


def demo_empty_context():
    """Demonstrate context with no entries."""
    print("=" * 80)
    print("DEMO: Empty Project Context (no entries)")
    print("=" * 80)
    print()

    formatter = ResponseFormatter()

    project = {
        "name": "brand_new_project",
        "root": "/home/austin/projects/MCP_SPINE/scribe_mcp",
        "progress_log": "/home/austin/projects/MCP_SPINE/scribe_mcp/.scribe/docs/dev_plans/brand_new_project/PROGRESS_LOG.md"
    }

    docs_info = {
        "architecture": {"exists": True, "lines": 100},
        "phase_plan": {"exists": True, "lines": 50},
        "checklist": {"exists": True, "lines": 25},
        "progress": {"exists": True, "entries": 0}
    }

    activity = {
        "status": "planning",
        "total_entries": 0,
        "last_entry_at": ""
    }

    result = formatter.format_project_context(
        project,
        [],
        docs_info,
        activity
    )

    print(result)
    print()


if __name__ == "__main__":
    demo_full_context()
    demo_partial_context()
    demo_empty_context()
