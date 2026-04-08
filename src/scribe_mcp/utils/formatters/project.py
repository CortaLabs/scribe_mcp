"""
Project formatting for list_projects, get_project, and set_project responses.

Phase 5 Task 5.5: Extracted from ResponseFormatter for modularity.

This module handles all project-related formatting:
- format_readable_projects: Legacy project list formatting
- format_readable_confirmation: Operation confirmations
- format_projects_table: Multi-project table view
- format_project_detail: Single project detail view
- format_no_projects_found: Empty state messaging
- format_project_context: Project context display (get_project)
- format_project_sitrep_new: New project SITREP (set_project)
- format_project_sitrep_existing: Existing project SITREP (set_project)
- format_projects_response: Project list response formatting
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import BaseFormatter, get_use_ansi_colors
from .ui import UIFormatter
from .file import FileFormatter


class ProjectFormatter(BaseFormatter):
    """Formats project information for display.

    Inherits from BaseFormatter for pagination and token utilities.
    Uses UIFormatter for ASCII boxes/tables and FileFormatter for doc line counts.
    """

    # ANSI color codes (duplicated from ResponseFormatter for standalone use)
    ANSI_CYAN = "\033[36m"
    ANSI_GREEN = "\033[32m"
    ANSI_YELLOW = "\033[33m"
    ANSI_BLUE = "\033[34m"
    ANSI_MAGENTA = "\033[35m"
    ANSI_BOLD = "\033[1m"
    ANSI_DIM = "\033[2m"
    ANSI_RESET = "\033[0m"

    # Unicode box-drawing characters (defined here to avoid f-string backslash issues)
    BOX_TOP_LEFT = "\u2554"      # ╔
    BOX_TOP_RIGHT = "\u2557"     # ╗
    BOX_BOTTOM_LEFT = "\u255A"   # ╚
    BOX_BOTTOM_RIGHT = "\u255D"  # ╝
    BOX_HORIZONTAL = "\u2550"    # ═
    BOX_VERTICAL = "\u2551"      # ║

    # Unicode emojis/symbols
    EMOJI_CLIPBOARD = "\U0001F4CB"  # 📋
    EMOJI_FOLDER = "\U0001F4C1"     # 📁
    EMOJI_CHART = "\U0001F4CA"      # 📊
    EMOJI_PAGE = "\U0001F4C4"       # 📄
    EMOJI_BULB = "\U0001F4A1"       # 💡
    EMOJI_SEARCH = "\U0001F50D"     # 🔍
    EMOJI_TARGET = "\U0001F3AF"     # 🎯
    EMOJI_OPEN_FOLDER = "\U0001F4C2"  # 📂
    EMOJI_PUSHPIN = "\U0001F4CC"    # 📌
    EMOJI_LABEL = "\U0001F3F7\uFE0F"  # 🏷️
    STAR = "\u2B50"                 # ⭐
    BULLET = "\u2022"               # •
    CHECK = "\u2713"                # ✓

    # Color palette for header/footer (consistent with ResponseFormatter)
    COLORS = {
        'header_title': "\033[1;36m",  # Bold cyan
        'header_meta': "\033[2;37m",   # Dim white
        'reset': "\033[0m",
    }

    def __init__(self, token_warning_threshold: int = 4000):
        super().__init__(token_warning_threshold)
        self._ui = UIFormatter(use_colors=self.USE_COLORS)
        self._file = FileFormatter(token_warning_threshold)

    @property
    def USE_COLORS(self) -> bool:
        """Check if ANSI colors are enabled via repo config."""
        return get_use_ansi_colors()

    # ==================== Delegated UI Methods ====================
    # These delegate to UIFormatter (Phase 5 Task 5.1)

    def _create_header_box(self, title: str, metadata: Dict[str, Any] = None) -> str:
        """Create header box. Delegates to UIFormatter."""
        return self._ui.create_header_box(title, metadata)

    def _create_footer_box(self, metadata: Dict[str, Any] = None, reminders: List[str] = None) -> str:
        """Create footer box. Delegates to UIFormatter."""
        return self._ui.create_footer_box(metadata, reminders)

    def _format_table(self, headers: List[str], rows: List[List[str]],
                      col_widths: List[int] = None) -> str:
        """Format table. Delegates to UIFormatter."""
        if col_widths is None:
            return self._ui.format_table(headers, rows)
        try:
            return self._ui.format_table(headers, rows, col_widths)
        except TypeError:
            return self._ui.format_table(headers, rows)

    # ==================== Delegated File Methods ====================
    # These delegate to FileFormatter (Phase 5 Task 5.3)

    def _get_doc_line_count(self, file_path: Union[str, Path]) -> int:
        """Get line count for a file. Delegates to FileFormatter."""
        return self._file._get_doc_line_count(file_path)

    def _detect_custom_content(self, docs_dir: Union[str, Path]) -> Dict[str, Any]:
        """Detect custom documents. Delegates to FileFormatter."""
        return self._file._detect_custom_content(docs_dir)

    # ==================== Project Formatting Methods ====================

    def format_readable_projects(self, projects: List[Dict], active: Optional[str] = None) -> str:
        """
        Format list_projects output in readable format.

        Args:
            projects: List of project dicts
            active: Name of active project (if any)

        Returns:
            Formatted string with header box, project table, footer
        """
        if not projects:
            return "No projects found."

        # Build header metadata
        header_meta = {
            'total_projects': len(projects),
            'active_project': active or 'none'
        }

        # Build table
        headers = ['Name', 'Status', 'Root', 'Last Entry']
        rows = []
        for project in projects:
            name = project.get('name', '')
            if name == active:
                name = f"* {name}"  # Mark active project

            status = project.get('lifecycle_status', 'unknown')
            root = project.get('root', '')[:40]  # Truncate long paths
            last_entry = project.get('last_entry_at', 'never')
            if 'T' in last_entry:
                last_entry = last_entry.split('T')[0]  # Date only

            rows.append([name, status, root, last_entry])

        # Build footer
        footer_meta = {'projects_shown': len(projects)}

        # Build readable output
        parts = []
        parts.append(self._create_header_box("PROJECTS", header_meta))
        parts.append("")
        parts.append(self._format_table(headers, rows))
        parts.append("")
        parts.append(self._create_footer_box(footer_meta))

        return '\n'.join(parts)

    def format_readable_confirmation(self, operation: str, data: Dict[str, Any]) -> str:
        """
        Format operation confirmations (append_entry, etc) in readable format.

        Args:
            operation: Operation name (e.g., "append_entry")
            data: Operation result data

        Returns:
            Formatted confirmation string
        """
        # Build header metadata
        header_meta = {
            'operation': operation,
            'status': 'success' if data.get('ok') else 'failed'
        }

        # Build main content
        parts = []
        parts.append(self._create_header_box("OPERATION RESULT", header_meta))
        parts.append("")

        # Operation-specific formatting
        if operation == "append_entry":
            message = data.get('written_line', data.get('message', ''))
            parts.append(f"\u2705 Entry written:")
            parts.append(f"   {message}")
            parts.append("")
            parts.append(f"Path: {data.get('path', 'unknown')}")

        # Build footer with audit data
        footer_meta = {}
        if 'id' in data:
            footer_meta['entry_id'] = data['id']
        if 'meta' in data:
            footer_meta['metadata'] = data['meta']

        reminders = data.get('reminders', [])

        parts.append("")
        parts.append(self._create_footer_box(footer_meta, reminders if reminders else None))

        return '\n'.join(parts)

    def format_projects_table(
        self,
        projects: List[Dict[str, Any]],
        active_name: Optional[str],
        pagination: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> str:
        """
        Format multiple projects as minimal table with pagination.

        Used when filter results in 2+ projects.

        Args:
            projects: List of project dicts (from list_projects query)
            active_name: Name of currently active project (for star marker)
            pagination: Dict with page, page_size, total_count, total_pages
            filters: Dict with name, status, tags, order_by, direction

        Returns:
            Formatted table string (~200 tokens)
        """
        # Extract pagination values
        page = pagination.get('page', 1)
        total_pages = pagination.get('total_pages', 1)
        total_count = pagination.get('total_count', len(projects))
        page_size = pagination.get('page_size', len(projects))

        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            GREEN = self.ANSI_GREEN
            RESET = self.ANSI_RESET
        else:
            CYAN = GREEN = RESET = ""

        lines = []

        # Header - simplified without box drawing
        header_text = f"\U0001F4CB Projects ({len(projects)}/{total_count}, page {page}/{total_pages})"
        lines.append(header_text)
        lines.append("")

        # Table headers - no separator line
        lines.append(f"{GREEN}NAME{' ' * 26}STATUS{' ' * 4}  ENTRIES  ACTIVITY{RESET}")

        # Table rows
        for project in projects:
            name = project.get('name', 'unknown')
            status = project.get('status') or project.get('lifecycle_status', 'unknown')
            total_entries = project.get('total_entries', 0)
            last_entry_at = project.get('last_entry_at')

            # Active project marker
            if name == active_name:
                prefix = "\u2B50 "
            else:
                prefix = "  "

            # Truncate long names to fit 30 char column (minus 3 for prefix/star)
            display_name = name[:27] if len(name) > 27 else name
            name_col = f"{prefix}{display_name:<28}"

            # Status column (12 chars)
            status_col = f"{status:<12}"

            # Entries column (8 chars, right-aligned)
            entries_col = f"{total_entries:>8}"

            # Last activity column (12 chars shortened)
            if last_entry_at:
                activity = self.format_relative_time(last_entry_at)
            else:
                activity = "never"
            activity_col = f"{activity:<12}"

            lines.append(f"{name_col}{status_col}{entries_col}  {activity_col}")

        lines.append("")

        # Footer: Simplified pagination and filter info
        filter_parts = []
        if filters.get('name'):
            filter_parts.append(f"name=\"{filters['name']}\"")
        if filters.get('status'):
            filter_parts.append(f"status={filters['status']}")
        if filters.get('tags'):
            filter_parts.append(f"tags={filters['tags']}")
        filter_str = " | ".join(filter_parts) if filter_parts else "none"

        lines.append(f"Page {page}/{total_pages} | filter: {filter_str}")

        return "\n".join(lines)

    def format_project_detail(
        self,
        project: Dict[str, Any],
        registry_info: Optional[Any],
        docs_info: Dict[str, Any]
    ) -> str:
        """
        Format single project with full details (deep dive).

        Used when filter results in exactly 1 project.

        Args:
            project: Project dict from list_projects
            registry_info: ProjectRecord from registry (or None)
            docs_info: Dict with document information:
                      {
                          "architecture": {"exists": True, "lines": 1274, "modified": True},
                          "phase_plan": {"exists": True, "lines": 542, "modified": False},
                          "checklist": {"exists": True, "lines": 356, "modified": False},
                          "progress": {"exists": True, "entries": 298},
                          "custom": {
                              "research_files": 3,
                              "bugs_present": False,
                              "jsonl_files": ["TOOL_LOG.jsonl"]
                          }
                      }

        Returns:
            Formatted detail view string (~400 tokens)
        """
        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            GREEN = self.ANSI_GREEN
            YELLOW = self.ANSI_YELLOW
            RESET = self.ANSI_RESET
        else:
            CYAN = GREEN = YELLOW = RESET = ""

        lines = []

        # Extract project name
        name = project.get('name', 'unknown')

        # Header box
        filter_hint = project.get('_filter_used', '')
        header_text = f"{self.EMOJI_FOLDER} PROJECT DETAIL: {name}"
        horiz_line = self.BOX_HORIZONTAL * 58
        lines.append(f"{CYAN}{self.BOX_TOP_LEFT}{horiz_line}{self.BOX_TOP_RIGHT}{RESET}")
        lines.append(f"{CYAN}{self.BOX_VERTICAL}{RESET} {header_text:<56} {CYAN}{self.BOX_VERTICAL}{RESET}")
        if filter_hint:
            subtitle = f'(1 match found for filter: "{filter_hint}")'
            lines.append(f"{CYAN}{self.BOX_VERTICAL}{RESET} {subtitle:<56} {CYAN}{self.BOX_VERTICAL}{RESET}")
        lines.append(f"{CYAN}{self.BOX_BOTTOM_LEFT}{horiz_line}{self.BOX_BOTTOM_RIGHT}{RESET}")
        lines.append("")

        # Status line
        status = project.get('status') or project.get('lifecycle_status', 'unknown')
        is_active = project.get('_is_active', False)
        if is_active:
            lines.append(f"Status: {GREEN}{status} {self.STAR} (active){RESET}")
        else:
            lines.append(f"Status: {status}")

        # Location info
        root = project.get('root', 'N/A')
        progress_log = project.get('progress_log', '')
        if progress_log:
            # Extract dev plan directory from progress log path
            dev_plan_dir = str(Path(progress_log).parent)
        else:
            dev_plan_dir = 'N/A'

        lines.append(f"Root: {root}")
        lines.append(f"Dev Plan: {dev_plan_dir}")
        lines.append("")

        # Activity section
        lines.append("\U0001F4CA Activity:")

        # Total entries
        if registry_info:
            total_entries = getattr(registry_info, 'total_entries', project.get('total_entries', 0))

            # Try to get per-log-type breakdown from project dict
            progress_count = project.get('entry_counts', {}).get('progress', total_entries)
            doc_updates_count = project.get('entry_counts', {}).get('doc_updates', 0)
            bugs_count = project.get('entry_counts', {}).get('bugs', 0)

            if doc_updates_count > 0 or bugs_count > 0:
                lines.append(f"  \u2022 Total Entries: {total_entries} (progress: {progress_count}, doc_updates: {doc_updates_count}, bugs: {bugs_count})")
            else:
                lines.append(f"  \u2022 Total Entries: {total_entries}")

            # Last entry timestamp
            last_entry_at = getattr(registry_info, 'last_entry_at', None)
            if last_entry_at:
                relative = self.format_relative_time(last_entry_at)
                utc_str = last_entry_at.strftime('%Y-%m-%d %H:%M UTC') if hasattr(last_entry_at, 'strftime') else str(last_entry_at)
                lines.append(f"  \u2022 Last Entry: {relative} ({utc_str})")

            # Last access
            last_access_at = getattr(registry_info, 'last_access_at', None)
            if last_access_at:
                relative = self.format_relative_time(last_access_at)
                lines.append(f"  \u2022 Last Access: {relative}")

            # Created
            created_at = getattr(registry_info, 'created_at', None)
            if created_at:
                relative = self.format_relative_time(created_at)
                lines.append(f"  \u2022 Created: {relative}")
        else:
            # Fallback to project dict
            total_entries = project.get('total_entries', 0)
            lines.append(f"  \u2022 Total Entries: {total_entries}")

        lines.append("")

        # Documents section
        lines.append("\U0001F4C4 Documents:")

        # Architecture
        arch_info = docs_info.get('architecture', {})
        if arch_info.get('exists'):
            lines_count = arch_info.get('lines', 0)
            if arch_info.get('modified'):
                lines.append(f"  {YELLOW}\u26A0\uFE0F  ARCHITECTURE_GUIDE.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}\u2713{RESET} ARCHITECTURE_GUIDE.md ({lines_count} lines)")

        # Phase plan
        phase_info = docs_info.get('phase_plan', {})
        if phase_info.get('exists'):
            lines_count = phase_info.get('lines', 0)
            if phase_info.get('modified'):
                lines.append(f"  {YELLOW}\u26A0\uFE0F  PHASE_PLAN.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}\u2713{RESET} PHASE_PLAN.md ({lines_count} lines)")

        # Checklist
        checklist_info = docs_info.get('checklist', {})
        if checklist_info.get('exists'):
            lines_count = checklist_info.get('lines', 0)
            if checklist_info.get('modified'):
                lines.append(f"  {YELLOW}\u26A0\uFE0F  CHECKLIST.md ({lines_count} lines, modified){RESET}")
            else:
                lines.append(f"  {GREEN}\u2713{RESET} CHECKLIST.md ({lines_count} lines)")

        # Progress log
        progress_info = docs_info.get('progress', {})
        if progress_info.get('exists'):
            entries_count = progress_info.get('entries', 0)
            lines.append(f"  {GREEN}\u2713{RESET} PROGRESS_LOG.md ({entries_count} entries)")

        # Custom content section (only if present)
        custom_info = docs_info.get('custom', {})
        research_files = custom_info.get('research_files', 0)
        jsonl_files = custom_info.get('jsonl_files', [])

        if research_files > 0 or jsonl_files:
            lines.append("")
            lines.append("\U0001F4C1 Custom Content:")

            if research_files > 0:
                lines.append(f"  \u2022 research/ ({research_files} files)")

            for jsonl_file in jsonl_files:
                lines.append(f"  \u2022 {jsonl_file} (present)")

        # Tags
        tags = project.get('tags', [])
        if tags:
            lines.append("")
            tags_str = ", ".join(tags)
            lines.append(f"\U0001F3F7\uFE0F  Tags: {tags_str}")

        # Docs status warning
        any_modified = (
            arch_info.get('modified', False) or
            phase_info.get('modified', False) or
            checklist_info.get('modified', False)
        )
        if any_modified:
            lines.append(f"{YELLOW}\u26A0\uFE0F  Docs Status: Architecture modified - not ready for work{RESET}")

        # Footer tip
        lines.append("")
        lines.append("\U0001F4A1 Use get_project() to see recent progress entries")

        return "\n".join(lines)

    def format_no_projects_found(self, filters: Dict[str, Any]) -> str:
        """
        Format helpful empty state when no projects match filters.

        Args:
            filters: Dict with name, status, tags filter values

        Returns:
            Formatted empty state string (~100 tokens)
        """
        # ANSI color support
        if self.USE_COLORS:
            CYAN = self.ANSI_CYAN
            RESET = self.ANSI_RESET
        else:
            CYAN = RESET = ""

        lines = []

        # Build filter summary for header
        filter_parts = []
        if filters.get('name'):
            filter_parts.append(f"\"{filters['name']}\"")
        if filters.get('status'):
            filter_parts.append(f"status={filters['status']}")
        if filters.get('tags'):
            filter_parts.append(f"tags={filters['tags']}")

        if filter_parts:
            filter_summary = filter_parts[0] if len(filter_parts) == 1 else "multiple filters"
        else:
            filter_summary = "none"

        # Header box
        header_text = f"{self.EMOJI_CLIPBOARD} PROJECTS - 0 matches for filter: {filter_summary}"
        horiz_line = self.BOX_HORIZONTAL * 58
        lines.append(f"{CYAN}{self.BOX_TOP_LEFT}{horiz_line}{self.BOX_TOP_RIGHT}{RESET}")
        lines.append(f"{CYAN}{self.BOX_VERTICAL}{RESET} {header_text:<56} {CYAN}{self.BOX_VERTICAL}{RESET}")
        lines.append(f"{CYAN}{self.BOX_BOTTOM_LEFT}{horiz_line}{self.BOX_BOTTOM_RIGHT}{RESET}")
        lines.append("")

        # Message
        lines.append("No projects found matching your criteria.")
        lines.append("")

        # Active filters section
        lines.append("\U0001F50D Active Filters:")
        if filters.get('name'):
            lines.append(f"  \u2022 Name: \"{filters['name']}\"")
        if filters.get('status'):
            lines.append(f"  \u2022 Status: {filters['status']}")
        if filters.get('tags'):
            lines.append(f"  \u2022 Tags: {filters['tags']}")

        lines.append("")

        # Suggestions
        lines.append("\U0001F4A1 Try:")
        lines.append("  \u2022 Remove filters: list_projects()")
        lines.append("  \u2022 Broader search: list_projects(filter=\"scribe\")")
        lines.append("  \u2022 Check status: list_projects(status=[\"planning\", \"in_progress\"])")

        return "\n".join(lines)

    def format_project_context(
        self,
        project: Dict[str, Any],
        recent_entries: List[Dict[str, Any]],
        docs_info: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format current project context with recent activity.

        Shows "Where am I?" information: location, documents, recent work.

        Args:
            project: Project dict with name, root, progress_log
            recent_entries: Last 1-5 progress log entries (COMPLETE, no truncation!)
            docs_info: Dict with document information:
                      {
                          "architecture": {"exists": True, "lines": 1274},
                          "phase_plan": {"exists": True, "lines": 542},
                          "checklist": {"exists": True, "lines": 356},
                          "progress": {"exists": True, "entries": 298}
                      }
            activity: Dict with activity summary:
                     {
                         "status": "in_progress",
                         "total_entries": 298,
                         "last_entry_at": "2026-01-03T08:15:30Z"
                     }

        Returns:
            Formatted context string (~300 tokens with 1-5 recent entries)
        """
        lines = []
        use_colors = self.USE_COLORS

        # ANSI color codes
        CYAN = "\033[96m" if use_colors else ""
        BOLD = "\033[1m" if use_colors else ""
        DIM = "\033[2m" if use_colors else ""
        RESET = "\033[0m" if use_colors else ""

        # Header box
        project_name = project.get('name', 'unknown')
        header_text = f" {self.EMOJI_TARGET} CURRENT PROJECT: {project_name} "
        box_width = max(58, len(header_text) + 4)
        horiz_line = self.BOX_HORIZONTAL * (box_width - 2)

        lines.append(f"{CYAN}{self.BOX_TOP_LEFT}{horiz_line}{self.BOX_TOP_RIGHT}{RESET}")
        lines.append(f"{CYAN}{self.BOX_VERTICAL}{RESET}{BOLD}{header_text:<{box_width - 2}}{RESET}{CYAN}{self.BOX_VERTICAL}{RESET}")
        lines.append(f"{CYAN}{self.BOX_BOTTOM_LEFT}{horiz_line}{self.BOX_BOTTOM_RIGHT}{RESET}")
        lines.append("")

        # Location section
        lines.append(f"{BOLD}\U0001F4C2 Location:{RESET}")
        root_path = project.get('root', 'unknown')
        lines.append(f"  Root: {root_path}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        if progress_log:
            # From: /path/to/.scribe/docs/dev_plans/project_name/PROGRESS_LOG.md
            # To: .scribe/docs/dev_plans/project_name/
            if '/.scribe/docs/dev_plans/' in progress_log:
                dev_plan_path = progress_log.split('PROGRESS_LOG.md')[0]
                # Make relative if it starts with root_path
                if dev_plan_path.startswith(root_path):
                    dev_plan_path = dev_plan_path[len(root_path):].lstrip('/')
                lines.append(f"  Dev Plan: {dev_plan_path}")

        lines.append("")

        # Documents section
        lines.append(f"{BOLD}\U0001F4C4 Documents:{RESET}")

        # Show only existing documents
        doc_mapping = {
            "architecture": "ARCHITECTURE_GUIDE.md",
            "phase_plan": "PHASE_PLAN.md",
            "checklist": "CHECKLIST.md",
            "progress": "PROGRESS_LOG.md"
        }

        for doc_key, doc_name in doc_mapping.items():
            doc_data = docs_info.get(doc_key, {})
            if doc_data.get('exists', False):
                if doc_key == 'progress':
                    entry_count = doc_data.get('entries', 0)
                    lines.append(f"  \u2022 {doc_name} ({entry_count} entries)")
                else:
                    line_count = doc_data.get('lines', 0)
                    lines.append(f"  \u2022 {doc_name} ({line_count} lines)")

        lines.append("")

        # Recent Activity section
        lines.append(f"{BOLD}\U0001F4CA Recent Activity{RESET} (last {len(recent_entries) if recent_entries else 0} entries):")

        if not recent_entries:
            lines.append("  No entries yet - new project")
        else:
            for idx, entry in enumerate(recent_entries, 1):
                # Extract timestamp (HH:MM format)
                timestamp = entry.get('timestamp', '') or entry.get('ts', '')
                timestamp_display = ""

                # Check UTC FIRST (because 'UTC' contains 'T')
                if 'UTC' in timestamp:
                    # "YYYY-MM-DD HH:MM:SS UTC" -> "HH:MM"
                    ts_parts = timestamp.split(' ')
                    if len(ts_parts) >= 3 and ts_parts[2] == 'UTC':
                        time_part = ts_parts[1]  # HH:MM:SS
                        timestamp_display = time_part.rsplit(':', 1)[0]  # Drop seconds
                    else:
                        timestamp_display = timestamp
                elif 'T' in timestamp and not timestamp.endswith('UTC'):
                    # "2026-01-03T15:42:37.123456Z" -> "15:42"
                    time_part = timestamp.split('T')[1].split('.')[0]  # HH:MM:SS
                    timestamp_display = time_part.rsplit(':', 1)[0]  # Drop seconds
                else:
                    timestamp_display = timestamp  # Fallback

                # Extract emoji and agent
                emoji = entry.get('emoji', '\u2139\uFE0F')
                agent = entry.get('agent', 'Unknown')

                # Truncate agent if too long
                if len(agent) > 15:
                    agent = agent[:12] + "..."

                # Get FULL message (NO truncation!)
                message = entry.get('message', '')

                # Format entry line
                emoji_part = f"{CYAN}[{emoji}]{RESET}" if use_colors else f"[{emoji}]"
                time_part = f"{DIM}{timestamp_display}{RESET}" if use_colors else timestamp_display
                agent_part = f"{BOLD}{agent}{RESET}" if use_colors else agent

                lines.append(f"    {idx}. {emoji_part} {time_part} | {agent_part} | {message}")

            # Add hint if showing fewer than 5 entries
            if len(recent_entries) < 5:
                lines.append("")
                lines.append("\U0001F4A1 Use read_recent(limit=20) for more entries")

        lines.append("")

        # Footer status line
        status = activity.get('status', 'unknown')
        total_entries = activity.get('total_entries', 0)
        last_entry_at = activity.get('last_entry_at', '')

        if last_entry_at:
            relative_time = self.format_relative_time(last_entry_at)
            lines.append(f"\u23F0 Status: {status} | Entries: {total_entries} | Last: {relative_time}")
        else:
            lines.append(f"\u23F0 Status: {status} | Entries: {total_entries}")

        return "\n".join(lines)

    def format_project_sitrep_new(
        self,
        project: Dict[str, Any],
        docs_created: Dict[str, str]
    ) -> str:
        """
        Format SITREP for newly created project.

        Shows: location, created documents with template info, next steps.

        Args:
            project: Project dict with name, root, progress_log
            docs_created: Dict mapping doc type to path:
                         {
                             "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
                             "phase_plan": "/path/to/PHASE_PLAN.md",
                             "checklist": "/path/to/CHECKLIST.md",
                             "progress_log": "/path/to/PROGRESS_LOG.md"
                         }

        Returns:
            Formatted SITREP string (~150 tokens)
        """
        lines = []
        project_name = project.get('name', 'unknown')
        sparkle = "\u2728"  # Sparkles emoji

        # Header box
        if self.USE_COLORS:
            header_title = f"{self.COLORS['header_title']}{sparkle} NEW PROJECT CREATED: {project_name}{self.COLORS['reset']}"
        else:
            header_title = f"{sparkle} NEW PROJECT CREATED: {project_name}"

        horiz_line = self.BOX_HORIZONTAL * 58
        lines.append(f"{self.BOX_TOP_LEFT}{horiz_line}{self.BOX_TOP_RIGHT}")
        lines.append(f"{self.BOX_VERTICAL} {header_title:<58}{self.BOX_VERTICAL}")
        lines.append(f"{self.BOX_BOTTOM_LEFT}{horiz_line}{self.BOX_BOTTOM_RIGHT}")
        lines.append("")

        # Location section
        lines.append("\U0001F4C2 Location:")
        lines.append(f"  Root: {project.get('root', 'unknown')}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        dev_plan = ''
        if 'PROGRESS_LOG.md' in progress_log:
            dev_plan = progress_log.replace('PROGRESS_LOG.md', '')
            # Convert to relative path if it's under the root
            root = project.get('root', '')
            if root and dev_plan.startswith(root):
                dev_plan = dev_plan[len(root):].lstrip('/')
        lines.append(f"  Dev Plan: {dev_plan}")
        lines.append("")

        # Documents Created section
        lines.append("\U0001F4C4 Documents Created:")

        # Define doc order and labels
        doc_labels = {
            'architecture': 'ARCHITECTURE_GUIDE.md',
            'phase_plan': 'PHASE_PLAN.md',
            'checklist': 'CHECKLIST.md',
            'progress_log': 'PROGRESS_LOG.md'
        }

        for doc_key in ['architecture', 'phase_plan', 'checklist', 'progress_log']:
            if doc_key in docs_created:
                doc_path = docs_created[doc_key]
                doc_label = doc_labels[doc_key]

                if doc_key == 'progress_log':
                    # Special case: progress log shows as "empty, ready for entries"
                    lines.append(f"  \u2713 {doc_label} (empty, ready for entries)")
                else:
                    # Get line count for templates
                    line_count = self._get_doc_line_count(doc_path)
                    lines.append(f"  \u2713 {doc_label} (template, {line_count} lines)")

        lines.append("")

        # Footer
        lines.append("\U0001F3AF Status: planning (new project)")
        lines.append("\U0001F4A1 Next: Start with research or architecture phase")

        return "\n".join(lines)

    def format_project_sitrep_existing(
        self,
        project: Dict[str, Any],
        inventory: Dict[str, Any],
        activity: Dict[str, Any]
    ) -> str:
        """
        Format SITREP for existing project activation.

        Shows: location, inventory (docs + custom content), activity, warnings.

        Args:
            project: Project dict with name, root, progress_log
            inventory: Dict with project inventory:
                      {
                          "docs": {
                              "architecture": {"exists": True, "lines": 1274, "modified": True},
                              "phase_plan": {"exists": True, "lines": 542, "modified": False},
                              "checklist": {"exists": True, "lines": 356, "modified": False},
                              "progress": {"exists": True, "entries": 298}
                          },
                          "custom": {
                              "research_files": 3,
                              "bugs_present": False,
                              "jsonl_files": ["TOOL_LOG.jsonl"]
                          }
                      }
            activity: Dict with activity summary:
                     {
                         "status": "in_progress",
                         "total_entries": 298,
                         "last_entry_at": "2026-01-03T08:15:30Z",
                         "per_log_counts": {
                             "progress": 298,
                             "doc_updates": 13,
                             "bugs": 0
                         }
                     }

        Returns:
            Formatted SITREP string (~250 tokens)
        """
        lines = []
        project_name = project.get('name', 'unknown')

        # Header box
        if self.USE_COLORS:
            header_title = f"{self.COLORS['header_title']}{self.EMOJI_PUSHPIN} PROJECT ACTIVATED: {project_name}{self.COLORS['reset']}"
        else:
            header_title = f"{self.EMOJI_PUSHPIN} PROJECT ACTIVATED: {project_name}"

        horiz_line = self.BOX_HORIZONTAL * 58
        lines.append(f"{self.BOX_TOP_LEFT}{horiz_line}{self.BOX_TOP_RIGHT}")
        lines.append(f"{self.BOX_VERTICAL} {header_title:<58}{self.BOX_VERTICAL}")
        lines.append(f"{self.BOX_BOTTOM_LEFT}{horiz_line}{self.BOX_BOTTOM_RIGHT}")
        lines.append("")

        # Location section
        lines.append("\U0001F4C2 Location:")
        lines.append(f"  Root: {project.get('root', 'unknown')}")

        # Extract dev plan path from progress_log
        progress_log = project.get('progress_log', '')
        dev_plan = ''
        if 'PROGRESS_LOG.md' in progress_log:
            dev_plan = progress_log.replace('PROGRESS_LOG.md', '')
            # Convert to relative path if it's under the root
            root = project.get('root', '')
            if root and dev_plan.startswith(root):
                dev_plan = dev_plan[len(root):].lstrip('/')
        lines.append(f"  Dev Plan: {dev_plan}")
        lines.append("")

        # Existing Project Inventory section
        lines.append("\U0001F4CA Existing Project Inventory:")

        # Status
        status = activity.get('status', 'unknown')
        status_annotation = ""
        if status == "in_progress":
            status_annotation = " (active work)"
        lines.append(f"  \u2022 Status: {status}{status_annotation}")

        # Total Entries with per-log breakdown
        total_entries = activity.get('total_entries', 0)
        per_log_counts = activity.get('per_log_counts', {})

        # Build per-log breakdown string (only show non-zero counts)
        breakdown_parts = []
        for log_type in sorted(per_log_counts.keys()):
            count = per_log_counts[log_type]
            if count > 0:
                breakdown_parts.append(f"{log_type}: {count}")

        breakdown_str = ", ".join(breakdown_parts) if breakdown_parts else ""
        if breakdown_str:
            lines.append(f"  \u2022 Total Entries: {total_entries} ({breakdown_str})")
        else:
            lines.append(f"  \u2022 Total Entries: {total_entries}")

        # Last Activity (relative time)
        last_entry_at = activity.get('last_entry_at')
        if last_entry_at:
            relative_time = self.format_relative_time(last_entry_at)
            lines.append(f"  \u2022 Last Activity: {relative_time}")

        lines.append("")

        # Documents section
        docs = inventory.get('docs', {})
        doc_count = sum(1 for doc_info in docs.values() if doc_info.get('exists', False))
        lines.append(f"\U0001F4C4 Documents ({doc_count} total):")

        # Define doc order and labels
        doc_labels = {
            'architecture': 'ARCHITECTURE_GUIDE.md',
            'phase_plan': 'PHASE_PLAN.md',
            'checklist': 'CHECKLIST.md',
            'progress': 'PROGRESS_LOG.md'
        }

        for doc_key in ['architecture', 'phase_plan', 'checklist', 'progress']:
            if doc_key in docs:
                doc_info = docs[doc_key]
                if not doc_info.get('exists', False):
                    continue

                doc_label = doc_labels[doc_key]
                is_modified = doc_info.get('modified', False)

                if doc_key == 'progress':
                    # Progress log shows entries count
                    entries = doc_info.get('entries', 0)
                    prefix = "\u26A0\uFE0F" if is_modified else "\u2713"
                    modifier = ", modified recently" if is_modified else ""
                    lines.append(f"  {prefix} {doc_label} ({entries} entries{modifier})")
                else:
                    # Other docs show line count
                    line_count = doc_info.get('lines', 0)
                    prefix = "\u26A0\uFE0F" if is_modified else "\u2713"
                    modifier = ", modified recently" if is_modified else ""
                    lines.append(f"  {prefix} {doc_label} ({line_count} lines{modifier})")

        lines.append("")

        # Custom Documents section (only if present)
        custom = inventory.get('custom', {})
        has_custom_content = False
        custom_lines = []

        research_files = custom.get('research_files', 0)
        if research_files > 0:
            has_custom_content = True
            custom_lines.append(f"  \u2022 research/ ({research_files} files)")

        jsonl_files = custom.get('jsonl_files', [])
        if jsonl_files:
            has_custom_content = True
            for jsonl_file in jsonl_files:
                custom_lines.append(f"  \u2022 {jsonl_file} (present)")

        if has_custom_content:
            lines.append("\U0001F4C1 Custom Documents:")
            lines.extend(custom_lines)
            lines.append("")

        # Footer tip
        lines.append("\U0001F4A1 Context: Continuing active development - review recent progress entries")

        return "\n".join(lines)

    def format_projects_response(
        self,
        projects: List[Dict[str, Any]],
        compact: bool = False,
        fields: Optional[List[str]] = None,
        extra_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Format response for list_projects tool."""
        # Format project entries
        if compact:
            # Compact project format with key fields only
            default_fields = ["name", "root", "progress_log"]
            formatted_projects = []
            for project in projects:
                compact_project = {}
                for field in fields or default_fields:
                    if field in project:
                        # Use first 3 chars of name as compact id
                        if field == "name":
                            compact_project["n"] = project[field]
                        elif field == "root":
                            compact_project["r"] = project[field]
                        elif field == "progress_log":
                            compact_project["p"] = project[field]
                formatted_projects.append(compact_project)
        else:
            # Full project format
            formatted_projects = [
                {k: v for k, v in project.items() if not fields or k in fields}
                for project in projects
            ]

        # Build response
        response = {
            "ok": True,
            "projects": formatted_projects,
            "count": len(formatted_projects)
        }

        if compact:
            response["compact"] = True

        # Add extra data
        if extra_data:
            response.update(extra_data)

        return response
