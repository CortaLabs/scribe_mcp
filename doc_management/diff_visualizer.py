"""Change diff visualization and history browsing."""

from __future__ import annotations

import difflib
import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.doc_management.change_logger import ChangeLogger, DiffResult


@dataclass
class DiffVisualization:
    """Visual representation of a diff."""
    file_path: Path
    from_version: str
    to_version: str
    total_changes: int
    additions: int
    deletions: int
    sections: List[Dict[str, Any]]
    html_content: str
    text_content: str
    similarity_ratio: float


@dataclass
class HistoryEntry:
    """Represents an entry in the change history timeline."""
    timestamp: datetime
    file_path: Path
    change_type: str
    commit_message: str
    author: str
    content_hash: Optional[str]
    metadata: Dict[str, Any]


class DiffVisualizer:
    """Provides visualization and browsing of document changes."""

    def __init__(self, change_logger: ChangeLogger):
        self.change_logger = change_logger
        self._logger = logging.getLogger(__name__)

    async def create_diff_visualization(
        self,
        file_path: Path,
        from_hash: Optional[str] = None,
        to_hash: Optional[str] = None,
        format: str = 'html'
    ) -> Optional[DiffVisualization]:
        """Create a visual diff between two versions of a file."""
        try:
            # Get change history to determine versions
            history = await self.change_logger.get_change_history(file_path, limit=100)

            if not history:
                return None

            # Determine which versions to compare
            if from_hash is None and to_hash is None:
                # Compare latest two versions
                if len(history) >= 2:
                    from_hash = history[1].content_hash_after
                    to_hash = history[0].content_hash_after
                else:
                    # Only one version exists, compare with empty
                    from_hash = None
                    to_hash = history[0].content_hash_after
            elif from_hash is None:
                # Compare from empty to to_hash
                from_hash = None
            elif to_hash is None:
                # Compare from from_hash to latest
                to_hash = history[0].content_hash_after

            # Get content for both versions
            from_content = await self.change_logger._get_content_at_hash(file_path, from_hash) if from_hash else ""
            to_content = await self.change_logger._get_content_at_hash(file_path, to_hash) if to_hash else ""

            # Calculate diff
            diff_result = self.change_logger._calculate_diff(from_content, to_content)

            # Create visualization sections
            sections = self._create_diff_sections(from_content, to_content)

            # Generate formatted content
            if format == 'html':
                html_content = self._generate_html_diff(from_content, to_content, sections)
                text_content = self._generate_text_diff(from_content, to_content)
            else:
                html_content = ""
                text_content = self._generate_text_diff(from_content, to_content)

            return DiffVisualization(
                file_path=file_path,
                from_version=from_hash or "empty",
                to_version=to_hash or "empty",
                total_changes=diff_result.additions + diff_result.deletions,
                additions=diff_result.additions,
                deletions=diff_result.deletions,
                sections=sections,
                html_content=html_content,
                text_content=text_content,
                similarity_ratio=diff_result.similarity_ratio
            )

        except Exception as e:
            self._logger.error(f"Failed to create diff visualization for {file_path}: {e}")
            return None

    def _create_diff_sections(self, old_content: str, new_content: str) -> List[Dict[str, Any]]:
        """Create categorized sections for the diff."""
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        sections = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            section = {
                'type': tag,
                'old_lines': old_lines[i1:i2] if tag != 'insert' else [],
                'new_lines': new_lines[j1:j2] if tag != 'delete' else [],
                'old_start': i1 + 1 if tag != 'insert' else 0,
                'old_end': i2 if tag != 'insert' else 0,
                'new_start': j1 + 1 if tag != 'delete' else 0,
                'new_end': j2 if tag != 'delete' else 0,
                'description': self._get_section_description(tag, i1, i2, j1, j2)
            }
            sections.append(section)

        return sections

    def _get_section_description(self, tag: str, i1: int, i2: int, j1: int, j2: int) -> str:
        """Get a human-readable description of a diff section."""
        if tag == 'equal':
            return f"Unchanged lines {i1+1}-{i2}"
        elif tag == 'replace':
            return f"Replaced lines {i1+1}-{i2} with {j1+1}-{j2}"
        elif tag == 'delete':
            return f"Deleted lines {i1+1}-{i2}"
        elif tag == 'insert':
            return f"Inserted lines {j1+1}-{j2}"
        else:
            return f"Unknown change type: {tag}"

    def _generate_html_diff(self, old_content: str, new_content: str, sections: List[Dict[str, Any]]) -> str:
        """Generate HTML-formatted diff."""
        html_parts = [
            '<div class="diff-container">',
            '<style>',
            '.diff-container { font-family: monospace; white-space: pre-wrap; }',
            '.diff-line { padding: 2px 4px; margin: 1px 0; }',
            '.diff-context { background-color: #f8f9fa; }',
            '.diff-added { background-color: #d4edda; border-left: 3px solid #28a745; }',
            '.diff-removed { background-color: #f8d7da; border-left: 3px solid #dc3545; }',
            '.diff-header { background-color: #e2e3e5; font-weight: bold; padding: 8px; margin: 8px 0; }',
            '.diff-stats { background-color: #fff3cd; padding: 8px; margin: 8px 0; border-radius: 4px; }',
            '</style>'
        ]

        # Add diff statistics
        total_additions = sum(1 for s in sections if s['type'] in ['insert', 'replace'] for _ in s['new_lines'])
        total_deletions = sum(1 for s in sections if s['type'] in ['delete', 'replace'] for _ in s['old_lines'])

        html_parts.append(f"""
        <div class="diff-stats">
            <strong>Diff Statistics:</strong>
            <span class="diff-added">+{total_additions} additions</span>,
            <span class="diff-removed">-{total_deletions} deletions</span>
        </div>
        """)

        line_number_old = 1
        line_number_new = 1

        for section in sections:
            # Section header
            html_parts.append(f"""
            <div class="diff-header">
                {section['description']}
            </div>
            """)

            if section['type'] == 'equal':
                # Show unchanged lines
                for line in section['old_lines']:
                    html_parts.append(f"""
                    <div class="diff-line diff-context">
                        <span class="line-numbers">{line_number_old:4d},{line_number_new:4d}</span>
                        {html.escape(line)}
                    </div>
                    """)
                    line_number_old += 1
                    line_number_new += 1

            elif section['type'] == 'delete':
                # Show deleted lines
                for line in section['old_lines']:
                    html_parts.append(f"""
                    <div class="diff-line diff-removed">
                        <span class="line-numbers">{line_number_old:4d},   </span>
                        <span class="diff-marker">-</span>
                        {html.escape(line)}
                    </div>
                    """)
                    line_number_old += 1

            elif section['type'] == 'insert':
                # Show inserted lines
                for line in section['new_lines']:
                    html_parts.append(f"""
                    <div class="diff-line diff-added">
                        <span class="line-numbers">   ,{line_number_new:4d}</span>
                        <span class="diff-marker">+</span>
                        {html.escape(line)}
                    </div>
                    """)
                    line_number_new += 1

            elif section['type'] == 'replace':
                # Show deleted lines first, then inserted lines
                for line in section['old_lines']:
                    html_parts.append(f"""
                    <div class="diff-line diff-removed">
                        <span class="line-numbers">{line_number_old:4d},   </span>
                        <span class="diff-marker">-</span>
                        {html.escape(line)}
                    </div>
                    """)
                    line_number_old += 1

                for line in section['new_lines']:
                    html_parts.append(f"""
                    <div class="diff-line diff-added">
                        <span class="line-numbers">   ,{line_number_new:4d}</span>
                        <span class="diff-marker">+</span>
                        {html.escape(line)}
                    </div>
                    """)
                    line_number_new += 1

        html_parts.append('</div>')
        return ''.join(html_parts)

    def _generate_text_diff(self, old_content: str, new_content: str) -> str:
        """Generate plain text diff."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff_lines = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile='old', tofile='new',
            lineterm='', n=3
        ))

        return ''.join(diff_lines)

    async def create_history_timeline(
        self,
        file_path: Optional[Path] = None,
        limit: int = 50,
        include_stats: bool = True
    ) -> List[HistoryEntry]:
        """Create a timeline of changes for a file or project."""
        try:
            changes = await self.change_logger.get_change_history(
                file_path=file_path,
                limit=limit,
                include_content=False
            )

            timeline = []
            for change in changes:
                entry = HistoryEntry(
                    timestamp=change.timestamp,
                    file_path=change.file_path,
                    change_type=change.change_type,
                    commit_message=change.commit_message,
                    author=change.author,
                    content_hash=change.content_hash_after,
                    metadata=change.metadata
                )

                # Add statistics if requested
                if include_stats:
                    stats = await self.change_logger.get_file_statistics(change.file_path)
                    entry.metadata['file_stats'] = stats

                timeline.append(entry)

            return timeline

        except Exception as e:
            self._logger.error(f"Failed to create history timeline: {e}")
            return []

    async def generate_change_summary(
        self,
        since: Optional[datetime] = None,
        file_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Generate a summary of changes within a time period."""
        try:
            timeline = await self.create_history_timeline(
                file_path=file_path,
                limit=1000,
                include_stats=True
            )

            # Filter by date if specified
            if since:
                timeline = [entry for entry in timeline if entry.timestamp >= since]

            if not timeline:
                return {
                    'total_changes': 0,
                    'time_period': 'No changes found',
                    'files_changed': [],
                    'authors': [],
                    'change_types': {}
                }

            # Calculate summary statistics
            files_changed = {}
            authors = {}
            change_types = {}
            changes_by_day = {}

            for entry in timeline:
                # Count files
                if str(entry.file_path) not in files_changed:
                    files_changed[str(entry.file_path)] = 0
                files_changed[str(entry.file_path)] += 1

                # Count authors
                if entry.author not in authors:
                    authors[entry.author] = 0
                authors[entry.author] += 1

                # Count change types
                if entry.change_type not in change_types:
                    change_types[entry.change_type] = 0
                change_types[entry.change_type] += 1

                # Group by day
                day_key = entry.timestamp.strftime('%Y-%m-%d')
                if day_key not in changes_by_day:
                    changes_by_day[day_key] = 0
                changes_by_day[day_key] += 1

            # Sort files by change count
            sorted_files = sorted(files_changed.items(), key=lambda x: x[1], reverse=True)[:10]
            sorted_authors = sorted(authors.items(), key=lambda x: x[1], reverse=True)

            time_period = f"{timeline[-1].timestamp.strftime('%Y-%m-%d')} to {timeline[0].timestamp.strftime('%Y-%m-%d')}"

            return {
                'total_changes': len(timeline),
                'time_period': time_period,
                'files_changed': [{'path': path, 'changes': count} for path, count in sorted_files],
                'authors': [{'name': author, 'changes': count} for author, count in sorted_authors],
                'change_types': change_types,
                'changes_by_day': dict(sorted(changes_by_day.items(), reverse=True)),
                'most_active_day': max(changes_by_day.items(), key=lambda x: x[1]) if changes_by_day else None
            }

        except Exception as e:
            self._logger.error(f"Failed to generate change summary: {e}")
            return {}

    async def export_history(
        self,
        file_path: Optional[Path] = None,
        format: str = 'json',
        output_path: Optional[Path] = None
    ) -> str:
        """Export change history in various formats."""
        try:
            timeline = await self.create_history_timeline(file_path=file_path, limit=1000)

            if format == 'json':
                data = {
                    'export_timestamp': datetime.now().isoformat(),
                    'file_path': str(file_path) if file_path else 'project',
                    'total_changes': len(timeline),
                    'changes': [
                        {
                            'timestamp': entry.timestamp.isoformat(),
                            'file_path': str(entry.file_path),
                            'change_type': entry.change_type,
                            'commit_message': entry.commit_message,
                            'author': entry.author,
                            'metadata': entry.metadata
                        }
                        for entry in timeline
                    ]
                }
                result = json.dumps(data, indent=2)

            elif format == 'markdown':
                lines = [
                    f"# Change History",
                    f"",
                    f"**File:** {file_path or 'All files'}",
                    f"**Total Changes:** {len(timeline)}",
                    f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                    f"",
                    f"## Timeline",
                    f""
                ]

                for entry in timeline:
                    lines.extend([
                        f"### {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {entry.change_type}",
                        f"",
                        f"**File:** `{entry.file_path}`",
                        f"**Author:** {entry.author}",
                        f"**Message:** {entry.commit_message}",
                        f""
                    ])

                result = '\n'.join(lines)

            elif format == 'csv':
                lines = [
                    'timestamp,file_path,change_type,author,commit_message'
                ]

                for entry in timeline:
                    line = f'"{entry.timestamp.isoformat()}","{entry.file_path}","{entry.change_type}","{entry.author}","{entry.commit_message}"'
                    lines.append(line)

                result = '\n'.join(lines)

            else:
                raise ValueError(f"Unsupported export format: {format}")

            # Save to file if path provided
            if output_path:
                output_path.write_text(result, encoding='utf-8')
                self._logger.info(f"Exported history to {output_path}")

            return result

        except Exception as e:
            self._logger.error(f"Failed to export history: {e}")
            return ""

    async def compare_commits(
        self,
        commit_hash1: str,
        commit_hash2: str,
        file_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Compare two commits and show the differences."""
        try:
            # This would require extending the change logger to track commit groups
            # For now, we'll implement a basic version using change records
            timeline = await self.create_history_timeline(file_path=file_path, limit=1000)

            # Find changes around the commit hashes (simplified approach)
            changes1 = [c for c in timeline if c.content_hash == commit_hash1]
            changes2 = [c for c in timeline if c.content_hash == commit_hash2]

            comparison = {
                'commit1': {
                    'hash': commit_hash1,
                    'changes': len(changes1),
                    'timestamp': changes1[0].timestamp.isoformat() if changes1 else None
                },
                'commit2': {
                    'hash': commit_hash2,
                    'changes': len(changes2),
                    'timestamp': changes2[0].timestamp.isoformat() if changes2 else None
                },
                'files_between_commits': len(set(c.file_path for c in timeline))
            }

            return comparison

        except Exception as e:
            self._logger.error(f"Failed to compare commits: {e}")
            return {}