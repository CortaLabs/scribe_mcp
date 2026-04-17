"""File system integrity verification and validation."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from scribe_mcp.storage.base import StorageBackend
from scribe_mcp.utils.time import utcnow
from scribe_mcp.utils.error_handler import sanitize_error_message


class IntegrityStatus(Enum):
    """File integrity status."""
    VALID = "valid"                    # File matches database record
    CORRUPTED = "corrupted"            # File content is corrupted
    MISSING = "missing"                # File exists in database but not on disk
    UNTRACKED = "untracked"            # File exists on disk but not in database
    MODIFIED = "modified"              # File modified since last sync
    ACCESS_DENIED = "access_denied"    # Cannot access file


@dataclass
class IntegrityCheck:
    """Result of integrity check for a single file."""
    file_path: Path
    status: IntegrityStatus
    expected_hash: Optional[str]
    actual_hash: Optional[str]
    file_size: int
    last_modified: float
    database_timestamp: Optional[float]
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrityReport:
    """Summary of integrity verification results."""
    timestamp: str
    total_files_checked: int
    status_counts: Dict[IntegrityStatus, int]
    files_with_issues: List[IntegrityCheck]
    check_duration: float
    recommendations: List[str]


class IntegrityVerifier:
    """Verifies file system integrity against database records."""

    def __init__(
        self,
        storage: StorageBackend,
        project_root: Path,
        cache_duration: float = 300.0  # 5 minutes
    ):
        self.storage = storage
        self.project_root = Path(project_root)
        self.cache_duration = cache_duration

        self._logger = logging.getLogger(__name__)
        self._integrity_cache: Dict[str, Tuple[float, IntegrityCheck]] = {}
        self._verification_lock = asyncio.Lock()

    async def verify_file_integrity(self, file_path: Path) -> IntegrityCheck:
        """Verify integrity of a single file."""
        try:
            # Check cache first
            cache_key = str(file_path)
            if cache_key in self._integrity_cache:
                cached_time, cached_result = self._integrity_cache[cache_key]
                if time.time() - cached_time < self.cache_duration:
                    return cached_result

            # Get database record
            db_record = await self._get_database_record(file_path)

            # Check file on disk
            file_info = await self._get_file_info(file_path)

            # Perform integrity check
            check_result = await self._perform_integrity_check(file_path, db_record, file_info)

            # Cache result
            self._integrity_cache[cache_key] = (time.time(), check_result)

            return check_result

        except Exception as e:
            safe_error = sanitize_error_message(str(e))
            self._logger.error(f"Failed to verify integrity for {file_path}: {safe_error}")
            return IntegrityCheck(
                file_path=file_path,
                status=IntegrityStatus.ACCESS_DENIED,
                expected_hash=None,
                actual_hash=None,
                file_size=0,
                last_modified=0,
                database_timestamp=None,
                error_message=safe_error
            )

    async def verify_project_integrity(
        self,
        file_patterns: Optional[List[str]] = None,
        include_untracked: bool = True
    ) -> IntegrityReport:
        """Verify integrity of all tracked files in the project."""
        start_time = time.time()

        async with self._verification_lock:
            try:
                # Get files to check
                files_to_check = await self._get_files_to_check(file_patterns, include_untracked)

                # Check each file
                checks = []
                for file_path in files_to_check:
                    check = await self.verify_file_integrity(file_path)
                    checks.append(check)

                # Generate report
                report = await self._generate_integrity_report(checks, time.time() - start_time)

                self._logger.info(f"Integrity verification completed: {report.total_files_checked} files checked")
                return report

            except Exception as e:
                safe_error = sanitize_error_message(str(e))
                self._logger.error(f"Failed to verify project integrity: {safe_error}")
                return IntegrityReport(
                    timestamp=utcnow().isoformat(),
                    total_files_checked=0,
                    status_counts={},
                    files_with_issues=[],
                    check_duration=time.time() - start_time,
                    recommendations=[f"Integrity verification failed: {safe_error}"]
                )

    async def _get_database_record(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get database record for a file."""
        try:
            # Try sync_status first
            result = await self.storage._fetchone(
                """
                SELECT last_file_hash, last_sync_at, sync_status
                FROM sync_status
                WHERE file_path = ? AND project_root = ?
                """,
                (str(file_path), str(self.project_root))
            )

            if result:
                return {
                    'hash': result['last_file_hash'],
                    'timestamp': result['last_sync_at'],
                    'status': result['sync_status']
                }

            # Try document_sections
            result = await self.storage._fetchone(
                """
                SELECT file_hash, updated_at
                FROM document_sections
                WHERE file_path = ? AND project_root = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(file_path), str(self.project_root))
            )

            if result:
                return {
                    'hash': result['file_hash'],
                    'timestamp': result['updated_at'],
                    'status': 'synced'
                }

            return None

        except Exception as e:
            self._logger.debug(
                "Failed to get database record for %s: %s",
                file_path,
                sanitize_error_message(str(e)),
            )
            return None

    async def _get_file_info(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get file information from disk."""
        try:
            if not file_path.exists():
                return None

            stat = file_path.stat()

            # Calculate file hash
            file_hash = await self._calculate_file_hash(file_path)

            return {
                'hash': file_hash,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'exists': True,
                'accessible': True
            }

        except (OSError, PermissionError) as e:
            safe_error = sanitize_error_message(str(e))
            self._logger.debug(f"Cannot access file {file_path}: {safe_error}")
            return {
                'hash': None,
                'size': 0,
                'modified': 0,
                'exists': file_path.exists(),
                'accessible': False,
                'error': safe_error
            }

    async def _perform_integrity_check(
        self,
        file_path: Path,
        db_record: Optional[Dict[str, Any]],
        file_info: Optional[Dict[str, Any]]
    ) -> IntegrityCheck:
        """Perform the actual integrity check."""
        # File doesn't exist on disk
        if not file_info or not file_info.get('exists'):
            if db_record:
                return IntegrityCheck(
                    file_path=file_path,
                    status=IntegrityStatus.MISSING,
                    expected_hash=db_record.get('hash'),
                    actual_hash=None,
                    file_size=0,
                    last_modified=0,
                    database_timestamp=db_record.get('timestamp')
                )
            else:
                # File doesn't exist anywhere
                return IntegrityCheck(
                    file_path=file_path,
                    status=IntegrityStatus.VALID,
                    expected_hash=None,
                    actual_hash=None,
                    file_size=0,
                    last_modified=0,
                    database_timestamp=None
                )

        # File exists but is not accessible
        if not file_info.get('accessible'):
            return IntegrityCheck(
                file_path=file_path,
                status=IntegrityStatus.ACCESS_DENIED,
                expected_hash=db_record.get('hash') if db_record else None,
                actual_hash=None,
                file_size=file_info.get('size', 0),
                last_modified=file_info.get('modified', 0),
                database_timestamp=db_record.get('timestamp') if db_record else None,
                error_message=file_info.get('error', 'Access denied')
            )

        # File exists but no database record
        if not db_record:
            return IntegrityCheck(
                file_path=file_path,
                status=IntegrityStatus.UNTRACKED,
                expected_hash=None,
                actual_hash=file_info.get('hash'),
                file_size=file_info.get('size', 0),
                last_modified=file_info.get('modified', 0),
                database_timestamp=None
            )

        # Compare hashes
        expected_hash = db_record.get('hash')
        actual_hash = file_info.get('hash')

        if expected_hash == actual_hash:
            status = IntegrityStatus.VALID
        else:
            # Check if file was modified after last sync
            file_time = float(file_info.get('modified', 0) or 0.0)
            db_raw = db_record.get('timestamp', 0)
            try:
                if isinstance(db_raw, (int, float)):
                    db_time = float(db_raw)
                else:
                    from datetime import datetime
                    db_time = datetime.fromisoformat(str(db_raw)).timestamp()
            except Exception:
                db_time = 0.0

            if file_time > db_time:
                status = IntegrityStatus.MODIFIED
            else:
                status = IntegrityStatus.CORRUPTED

        return IntegrityCheck(
            file_path=file_path,
            status=status,
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            file_size=file_info.get('size', 0),
            last_modified=file_info.get('modified', 0),
            database_timestamp=db_record.get('timestamp')
        )

    async def _get_files_to_check(
        self,
        file_patterns: Optional[List[str]],
        include_untracked: bool
    ) -> List[Path]:
        """Get list of files to check."""
        files = set()

        # Get tracked files from database
        try:
            # From sync_status
            results = await self.storage._fetchall(
                """
                SELECT DISTINCT file_path FROM sync_status
                WHERE project_root = ?
                """,
                (str(self.project_root),)
            )

            for result in results:
                files.add(Path(result['file_path']))

            # From document_sections
            results = await self.storage._fetchall(
                """
                SELECT DISTINCT file_path FROM document_sections
                WHERE project_root = ?
                """,
                (str(self.project_root),)
            )

            for result in results:
                files.add(Path(result['file_path']))

        except Exception as e:
            safe_error = sanitize_error_message(e)
            self._logger.warning(f"Failed to get tracked files from database: {safe_error}")

        # Add untracked files if requested
        if include_untracked:
            patterns = file_patterns or ['**/*.md', '**/*.txt', '**/*.json']
            for pattern in patterns:
                try:
                    for file_path in self.project_root.glob(pattern):
                        if file_path.is_file():
                            files.add(file_path)
                except Exception as e:
                    safe_error = sanitize_error_message(e)
                    self._logger.warning(f"Failed to glob pattern {pattern}: {safe_error}")

        return list(files)

    async def _generate_integrity_report(self, checks: List[IntegrityCheck], duration: float) -> IntegrityReport:
        """Generate integrity verification report."""
        # Count statuses
        status_counts = {}
        files_with_issues = []

        for check in checks:
            status_counts[check.status] = status_counts.get(check.status, 0) + 1

            if check.status != IntegrityStatus.VALID:
                files_with_issues.append(check)

        # Generate recommendations
        recommendations = self._generate_recommendations(status_counts, files_with_issues)

        return IntegrityReport(
            timestamp=utcnow().isoformat(),
            total_files_checked=len(checks),
            status_counts=status_counts,
            files_with_issues=files_with_issues,
            check_duration=duration,
            recommendations=recommendations
        )

    def _generate_recommendations(
        self,
        status_counts: Dict[IntegrityStatus, int],
        files_with_issues: List[IntegrityCheck]
    ) -> List[str]:
        """Generate recommendations based on integrity check results."""
        recommendations = []

        if status_counts.get(IntegrityStatus.CORRUPTED, 0) > 0:
            recommendations.append(
                f"Found {status_counts[IntegrityStatus.CORRUPTED]} corrupted files. "
                "Consider restoring from backup or database."
            )

        if status_counts.get(IntegrityStatus.MISSING, 0) > 0:
            recommendations.append(
                f"Found {status_counts[IntegrityStatus.MISSING]} missing files. "
                "Check if files were intentionally deleted or need restoration."
            )

        if status_counts.get(IntegrityStatus.MODIFIED, 0) > 0:
            recommendations.append(
                f"Found {status_counts[IntegrityStatus.MODIFIED]} modified files. "
                "Run sync to update database with latest changes."
            )

        if status_counts.get(IntegrityStatus.UNTRACKED, 0) > 0:
            recommendations.append(
                f"Found {status_counts[IntegrityStatus.UNTRACKED]} untracked files. "
                "Consider adding them to the database if they should be tracked."
            )

        if status_counts.get(IntegrityStatus.ACCESS_DENIED, 0) > 0:
            recommendations.append(
                f"Found {status_counts[IntegrityStatus.ACCESS_DENIED]} inaccessible files. "
                "Check file permissions and accessibility."
            )

        if not files_with_issues:
            recommendations.append("All files have valid integrity. No action needed.")

        return recommendations

    async def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """Calculate SHA-256 hash of file content (fast-path: first 64KB)."""
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                content = f.read(65536)
                h.update(content)
            return h.hexdigest()
        except (OSError, IOError):
            return None

    async def repair_file(self, file_path: Path, repair_strategy: str = "database_wins") -> bool:
        """Attempt to repair a file with integrity issues."""
        try:
            check = await self.verify_file_integrity(file_path)

            if check.status == IntegrityStatus.VALID:
                return True  # No repair needed

            if repair_strategy == "database_wins":
                # Restore from database
                db_record = await self._get_database_record(file_path)
                if db_record and db_record.get('hash'):
                    # Get content from document_sections
                    content_result = await self.storage._fetchone(
                        """
                        SELECT content FROM document_sections
                        WHERE file_path = ? AND file_hash = ? AND project_root = ?
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (str(file_path), db_record['hash'], str(self.project_root))
                    )

                    if content_result:
                        file_path.write_text(content_result['content'], encoding='utf-8')
                        self._logger.info(f"Repaired {file_path} from database")
                        return True

            elif repair_strategy == "file_wins":
                # Update database with file content
                if file_path.exists():
                    content = file_path.read_text(encoding='utf-8')
                    file_hash = await self._calculate_file_hash(file_path)

                    await self.storage._execute(
                        """
                        INSERT OR REPLACE INTO document_sections
                        (project_root, file_path, relative_path, content, file_hash, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            str(self.project_root),
                            str(file_path),
                            str(file_path.relative_to(self.project_root)),
                            content,
                            file_hash,
                            utcnow(),
                            utcnow()
                        ]
                    )

                    self._logger.info(f"Updated database with {file_path} content")
                    return True

            return False

        except Exception as e:
            safe_error = sanitize_error_message(e)
            self._logger.error(f"Failed to repair {file_path}: {safe_error}")
            return False

    async def clear_cache(self):
        """Clear the integrity check cache."""
        self._integrity_cache.clear()
        self._logger.debug("Integrity check cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the integrity check cache."""
        return {
            'cached_files': len(self._integrity_cache),
            'cache_duration': self.cache_duration,
            'oldest_entry': min((t for t, _ in self._integrity_cache.values()), default=0),
            'newest_entry': max((t for t, _ in self._integrity_cache.values()), default=0)
        }
