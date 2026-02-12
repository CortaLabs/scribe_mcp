"""Git-level change tracking with commit messages and diff history."""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.utils.time import utcnow


@dataclass
class ChangeRecord:
    """Represents a single change to a document."""
    id: str
    file_path: Path
    change_type: str  # 'created', 'modified', 'deleted', 'moved'
    commit_message: str
    author: str
    timestamp: datetime
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    content_hash_before: Optional[str] = None
    content_hash_after: Optional[str] = None
    diff_summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiffResult:
    """Result of comparing two content versions."""
    additions: int
    deletions: int
    modifications: int
    lines_added: List[str]
    lines_removed: List[str]
    unified_diff: str
    similarity_ratio: float


class ChangeLogger:
    """Git-style change tracking for document modifications."""

    def __init__(
        self,
        storage: StorageBackend,
        project_root: Path,
        max_history: int = 1000,
        enable_diff_calculation: bool = True
    ):
        self.storage = storage
        self.project_root = Path(project_root)
        self.max_history = max_history
        self.enable_diff_calculation = enable_diff_calculation

        self._logger = logging.getLogger(__name__)

    async def log_change(
        self,
        file_path: Path,
        change_type: str,
        commit_message: str,
        author: str,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ChangeRecord:
        """Log a change to a document."""

        change_id = self._generate_change_id(file_path, change_type)
        timestamp = utcnow()

        # Calculate content hashes
        old_hash = self._calculate_content_hash(old_content) if old_content else None
        new_hash = self._calculate_content_hash(new_content) if new_content else None

        # Calculate diff summary if enabled
        diff_summary = None
        if self.enable_diff_calculation and old_content and new_content:
            diff_result = self._calculate_diff(old_content, new_content)
            diff_summary = {
                'additions': diff_result.additions,
                'deletions': diff_result.deletions,
                'modifications': diff_result.modifications,
                'similarity_ratio': diff_result.similarity_ratio,
                'unified_diff': diff_result.unified_diff[:1000] + '...' if len(diff_result.unified_diff) > 1000 else diff_result.unified_diff
            }

        # Create change record
        change_record = ChangeRecord(
            id=change_id,
            file_path=file_path,
            change_type=change_type,
            commit_message=commit_message,
            author=author,
            timestamp=timestamp,
            old_content=old_content,
            new_content=new_content,
            content_hash_before=old_hash,
            content_hash_after=new_hash,
            diff_summary=json.dumps(diff_summary) if diff_summary else None,
            metadata=metadata or {}
        )

        # Store in database
        await self._store_change_record(change_record)

        self._logger.info(f"Logged change: {change_type} {file_path} by {author}")

        return change_record

    async def _store_change_record(self, change_record: ChangeRecord):
        """Store a change record in the database."""
        try:
            # Store in document_changes table
            await self.storage._execute(
                """
                INSERT INTO document_changes
                (project_root, document_path, change_type, old_content_hash, new_content_hash,
                 change_summary, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(self.project_root),
                    str(change_record.file_path),
                    change_record.change_type,
                    change_record.content_hash_before,
                    change_record.content_hash_after,
                    json.dumps({
                        'commit_message': change_record.commit_message,
                        'author': change_record.author,
                        'diff_summary': json.loads(change_record.diff_summary) if change_record.diff_summary else None
                    }, sort_keys=True),
                    json.dumps(change_record.metadata, sort_keys=True),
                    change_record.timestamp.isoformat()
                ]
            )

            # Cleanup old records if exceeding max_history
            await self._cleanup_old_changes()

        except Exception as e:
            self._logger.error(f"Failed to store change record: {e}")
            raise

    async def _cleanup_old_changes(self):
        """Remove old change records if exceeding max_history."""
        try:
            # Get total count for this project
            result = await self.storage._fetchone(
                "SELECT COUNT(*) as count FROM document_changes WHERE project_root = ?",
                (str(self.project_root),)
            )

            if result and result['count'] > self.max_history:
                # Delete oldest records beyond the limit
                excess_count = result['count'] - self.max_history
                await self.storage._execute(
                    """
                    DELETE FROM document_changes
                    WHERE project_root = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (str(self.project_root), excess_count)
                )
                self._logger.debug(f"Cleaned up {excess_count} old change records")

        except Exception as e:
            self._logger.warning(f"Failed to cleanup old changes: {e}")

    async def get_change_history(
        self,
        file_path: Optional[Path] = None,
        limit: int = 100,
        include_content: bool = False
    ) -> List[ChangeRecord]:
        """Get change history for a file or the entire project."""
        try:
            query = """
                SELECT document_path, change_type, old_content_hash, new_content_hash,
                       change_summary, metadata, created_at
                FROM document_changes
                WHERE project_root = ?
            """
            params = [str(self.project_root)]

            if file_path:
                query += " AND document_path = ?"
                params.append(str(file_path))

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = await self.storage._fetchall(query, tuple(params))

            changes = []
            for row in rows:
                summary = json.loads(row['change_summary']) if row['change_summary'] else {}

                change_record = ChangeRecord(
                    id=self._generate_change_id(Path(row['document_path']), row['change_type']),
                    file_path=Path(row['document_path']),
                    change_type=row['change_type'],
                    commit_message=summary.get('commit_message', ''),
                    author=summary.get('author', 'Unknown'),
                    timestamp=datetime.fromisoformat(row['created_at']),
                    content_hash_before=row['old_content_hash'],
                    content_hash_after=row['new_content_hash'],
                    diff_summary=json.dumps(summary.get('diff_summary')) if summary.get('diff_summary') else None,
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )

                # Include content if requested and available
                if include_content:
                    change_record.old_content = await self._get_content_at_hash(
                        Path(row['document_path']), row['old_content_hash']
                    )
                    change_record.new_content = await self._get_content_at_hash(
                        Path(row['document_path']), row['new_content_hash']
                    )

                changes.append(change_record)

            return changes

        except Exception as e:
            self._logger.error(f"Failed to get change history: {e}")
            return []

    async def _get_content_at_hash(self, file_path: Path, content_hash: Optional[str]) -> Optional[str]:
        """Get content for a file at a specific hash from document_sections."""
        if not content_hash:
            return None

        try:
            result = await self.storage._fetchone(
                """
                SELECT content FROM document_sections
                WHERE file_path = ? AND file_hash = ? AND project_root = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(file_path), content_hash, str(self.project_root))
            )

            return result['content'] if result else None

        except Exception as e:
            self._logger.debug(f"Failed to get content at hash {content_hash}: {e}")
            return None

    async def get_diff_between_versions(
        self,
        file_path: Path,
        from_hash: str,
        to_hash: str
    ) -> Optional[DiffResult]:
        """Get diff between two versions of a file."""
        try:
            from_content = await self._get_content_at_hash(file_path, from_hash)
            to_content = await self._get_content_at_hash(file_path, to_hash)

            if from_content is None or to_content is None:
                return None

            return self._calculate_diff(from_content, to_content)

        except Exception as e:
            self._logger.error(f"Failed to get diff between versions: {e}")
            return None

    def _calculate_diff(self, old_content: str, new_content: str) -> DiffResult:
        """Calculate diff between two content strings."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        # Calculate unified diff
        unified_diff = ''.join(difflib.unified_diff(
            old_lines, new_lines,
            fromfile='old', tofile='new',
            lineterm=''
        ))

        # Calculate line-based changes
        differ = difflib.Differ()
        diff_lines = list(differ.compare(old_lines, new_lines))

        additions = 0
        deletions = 0
        modifications = 0
        lines_added = []
        lines_removed = []

        for line in diff_lines:
            if line.startswith('+ ') and not line.startswith('+++'):
                additions += 1
                lines_added.append(line[2:])
            elif line.startswith('- ') and not line.startswith('---'):
                deletions += 1
                lines_removed.append(line[2:])
            elif line.startswith('? '):
                modifications += 1

        # Calculate similarity ratio
        similarity_ratio = difflib.SequenceMatcher(None, old_content, new_content).ratio()

        return DiffResult(
            additions=additions,
            deletions=deletions,
            modifications=modifications,
            lines_added=lines_added,
            lines_removed=lines_removed,
            unified_diff=unified_diff,
            similarity_ratio=similarity_ratio
        )

    async def get_file_statistics(self, file_path: Path) -> Dict[str, Any]:
        """Get change statistics for a specific file."""
        try:
            # Get total changes
            result = await self.storage._fetchone(
                """
                SELECT
                    COUNT(*) as total_changes,
                    COUNT(CASE WHEN change_type = 'created' THEN 1 END) as creations,
                    COUNT(CASE WHEN change_type = 'modified' THEN 1 END) as modifications,
                    COUNT(CASE WHEN change_type = 'deleted' THEN 1 END) as deletions,
                    MIN(created_at) as first_change,
                    MAX(created_at) as last_change
                FROM document_changes
                WHERE project_root = ? AND document_path = ?
                """,
                (str(self.project_root), str(file_path))
            )

            if not result:
                return {}

            # Get most recent change
            recent_change = await self.storage._fetchone(
                """
                SELECT change_summary, created_at
                FROM document_changes
                WHERE project_root = ? AND document_path = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(self.project_root), str(file_path))
            )

            stats = {
                'total_changes': result['total_changes'],
                'creations': result['creations'],
                'modifications': result['modifications'],
                'deletions': result['deletions'],
                'first_change': result['first_change'],
                'last_change': result['last_change']
            }

            if recent_change:
                summary = json.loads(recent_change['change_summary']) if recent_change['change_summary'] else {}
                stats['last_commit_message'] = summary.get('commit_message', '')
                stats['last_author'] = summary.get('author', 'Unknown')

            return stats

        except Exception as e:
            self._logger.error(f"Failed to get file statistics: {e}")
            return {}

    async def get_project_statistics(self) -> Dict[str, Any]:
        """Get overall change statistics for the project."""
        try:
            # Get overall statistics
            result = await self.storage._fetchone(
                """
                SELECT
                    COUNT(*) as total_changes,
                    COUNT(DISTINCT document_path) as files_changed,
                    COUNT(CASE WHEN change_type = 'created' THEN 1 END) as creations,
                    COUNT(CASE WHEN change_type = 'modified' THEN 1 END) as modifications,
                    COUNT(CASE WHEN change_type = 'deleted' THEN 1 END) as deletions,
                    MIN(created_at) as first_change,
                    MAX(created_at) as last_change
                FROM document_changes
                WHERE project_root = ?
                """,
                (str(self.project_root),)
            )

            if not result:
                return {}

            # Get top contributors
            contributors_result = await self.storage._fetchall(
                """
                SELECT json_extract(change_summary, '$.author') as author, COUNT(*) as changes
                FROM document_changes
                WHERE project_root = ? AND json_extract(change_summary, '$.author') IS NOT NULL
                GROUP BY json_extract(change_summary, '$.author')
                ORDER BY changes DESC
                LIMIT 10
                """,
                (str(self.project_root),)
            )

            contributors = [
                {'author': row['author'], 'changes': row['changes']}
                for row in contributors_result
            ]

            return {
                'total_changes': result['total_changes'],
                'files_changed': result['files_changed'],
                'creations': result['creations'],
                'modifications': result['modifications'],
                'deletions': result['deletions'],
                'first_change': result['first_change'],
                'last_change': result['last_change'],
                'top_contributors': contributors
            }

        except Exception as e:
            self._logger.error(f"Failed to get project statistics: {e}")
            return {}

    def _generate_change_id(self, file_path: Path, change_type: str) -> str:
        """Generate a unique change ID."""
        content = f"{file_path}_{change_type}_{time.time()}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:12]

    def _calculate_content_hash(self, content: Optional[str]) -> Optional[str]:
        """Calculate SHA-256 hash of content."""
        if not content:
            return None
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    async def create_commit(
        self,
        file_paths: List[Path],
        commit_message: str,
        author: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[ChangeRecord]:
        """Create a commit-like batch of changes."""
        changes = []

        for file_path in file_paths:
            try:
                # Determine change type based on file state
                if not file_path.exists():
                    change_type = 'deleted'
                    old_content = await self._get_latest_content(file_path)
                    new_content = None
                else:
                    current_content = file_path.read_text(encoding='utf-8')
                    old_content = await self._get_latest_content(file_path)

                    if old_content is None:
                        change_type = 'created'
                        new_content = current_content
                    else:
                        change_type = 'modified'
                        new_content = current_content

                change_record = await self.log_change(
                    file_path=file_path,
                    change_type=change_type,
                    commit_message=commit_message,
                    author=author,
                    old_content=old_content,
                    new_content=new_content,
                    metadata=metadata
                )

                changes.append(change_record)

            except Exception as e:
                self._logger.error(f"Failed to create change for {file_path}: {e}")

        return changes

    async def _get_latest_content(self, file_path: Path) -> Optional[str]:
        """Get the latest stored content for a file."""
        try:
            result = await self.storage._fetchone(
                """
                SELECT content FROM document_sections
                WHERE file_path = ? AND project_root = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(file_path), str(self.project_root))
            )

            return result['content'] if result else None

        except Exception as e:
            self._logger.debug(f"Failed to get latest content for {file_path}: {e}")
            return None