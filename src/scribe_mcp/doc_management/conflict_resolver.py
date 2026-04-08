"""Advanced conflict resolution system with manual override capabilities."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scribe_mcp.doc_management.change_logger import ChangeLogger
from scribe_mcp.doc_management.diff_visualizer import DiffVisualizer
from scribe_mcp.doc_management.sync_manager import ConflictResolution, SyncConflict
from scribe_mcp.utils.time import utcnow


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""
    LOW = "low"          # Minor whitespace or formatting differences
    MEDIUM = "medium"    # Content changes that don't affect structure
    HIGH = "high"        # Structural changes or conflicting modifications
    CRITICAL = "critical" # Conflicting changes to same sections


@dataclass
class ConflictAnalysis:
    """Detailed analysis of a conflict."""
    conflict: SyncConflict
    severity: ConflictSeverity
    affected_sections: List[str]
    auto_resolvable: bool
    suggested_resolution: ConflictResolution
    confidence_score: float
    analysis_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolutionAction:
    """Represents a resolution action taken."""
    conflict_id: str
    resolution_strategy: ConflictResolution
    resolver: str
    timestamp: str
    action_taken: str
    result_content_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConflictResolver:
    """Advanced conflict resolution with manual override and intelligence."""

    def __init__(
        self,
        change_logger: ChangeLogger,
        diff_visualizer: DiffVisualizer,
        default_resolution: ConflictResolution = ConflictResolution.LATEST_WINS
    ):
        self.change_logger = change_logger
        self.diff_visualizer = diff_visualizer
        self.default_resolution = default_resolution

        self._logger = logging.getLogger(__name__)
        self._resolution_history: List[ResolutionAction] = []

    async def analyze_conflict(self, conflict: SyncConflict) -> ConflictAnalysis:
        """Perform detailed analysis of a conflict."""
        try:
            # Determine severity
            severity = await self._determine_severity(conflict)

            # Identify affected sections
            affected_sections = await self._identify_affected_sections(conflict)

            # Check if auto-resolvable
            auto_resolvable = await self._is_auto_resolvable(conflict, severity)

            # Suggest resolution
            suggested_resolution = await self._suggest_resolution(conflict, severity)

            # Calculate confidence score
            confidence_score = await self._calculate_confidence(conflict, severity)

            analysis = ConflictAnalysis(
                conflict=conflict,
                severity=severity,
                affected_sections=affected_sections,
                auto_resolvable=auto_resolvable,
                suggested_resolution=suggested_resolution,
                confidence_score=confidence_score,
                analysis_details={
                    'time_difference': conflict.file_timestamp - conflict.database_timestamp,
                    'content_similarity': self._calculate_content_similarity(conflict),
                    'size_difference': self._calculate_size_difference(conflict)
                }
            )

            self._logger.debug(f"Conflict analysis completed for {conflict.file_path}: {severity.value} severity")
            return analysis

        except Exception as e:
            self._logger.error(f"Failed to analyze conflict: {e}")
            # Return basic analysis
            return ConflictAnalysis(
                conflict=conflict,
                severity=ConflictSeverity.MEDIUM,
                affected_sections=[],
                auto_resolvable=True,
                suggested_resolution=self.default_resolution,
                confidence_score=0.5
            )

    async def resolve_conflict(
        self,
        conflict: SyncConflict,
        resolution_strategy: Optional[ConflictResolution] = None,
        resolver: str = "system",
        manual_content: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Resolve a conflict using the specified strategy."""
        try:
            # Analyze conflict first
            analysis = await self.analyze_conflict(conflict)

            # Determine resolution strategy
            if resolution_strategy is None:
                resolution_strategy = analysis.suggested_resolution

            # Apply resolution
            if resolution_strategy == ConflictResolution.MANUAL:
                if manual_content is None:
                    # Try to create a merged version
                    resolved_content = await self._create_merge_suggestion(conflict)
                else:
                    resolved_content = manual_content
            elif resolution_strategy == ConflictResolution.FILE_WINS:
                resolved_content = conflict.file_content
            elif resolution_strategy == ConflictResolution.DATABASE_WINS:
                resolved_content = conflict.database_content
            elif resolution_strategy == ConflictResolution.LATEST_WINS:
                if conflict.file_timestamp > conflict.database_timestamp:
                    resolved_content = conflict.file_content
                else:
                    resolved_content = conflict.database_content
            else:
                resolved_content = conflict.file_content  # Fallback

            if resolved_content is None:
                return False, None

            # Record resolution action
            action = ResolutionAction(
                conflict_id=f"{conflict.file_path}_{conflict.file_timestamp}",
                resolution_strategy=resolution_strategy,
                resolver=resolver,
                timestamp=utcnow().isoformat(),
                action_taken=f"Resolved {conflict.conflict_type} conflict using {resolution_strategy.value}",
                result_content_hash=self.change_logger._calculate_content_hash(resolved_content),
                metadata={
                    'severity': analysis.severity.value,
                    'confidence': analysis.confidence_score,
                    'auto_resolvable': analysis.auto_resolvable
                }
            )

            self._resolution_history.append(action)

            # Log the resolution
            await self.change_logger.log_change(
                file_path=conflict.file_path,
                change_type="conflict_resolved",
                commit_message=f"Resolved {conflict.conflict_type} conflict using {resolution_strategy.value}",
                author=resolver,
                old_content=conflict.file_content,
                new_content=resolved_content,
                metadata={
                    'resolution_strategy': resolution_strategy.value,
                    'conflict_severity': analysis.severity.value,
                    'confidence_score': analysis.confidence_score
                }
            )

            self._logger.info(f"Conflict resolved for {conflict.file_path} using {resolution_strategy.value}")
            return True, resolved_content

        except Exception as e:
            self._logger.error(f"Failed to resolve conflict: {e}")
            return False, None

    async def _determine_severity(self, conflict: SyncConflict) -> ConflictSeverity:
        """Determine the severity level of a conflict."""
        if not conflict.file_content or not conflict.database_content:
            return ConflictSeverity.HIGH

        # Calculate content similarity
        similarity = self._calculate_content_similarity(conflict)

        # Check for structural changes
        file_lines = set(conflict.file_content.splitlines())
        db_lines = set(conflict.database_content.splitlines())
        structural_changes = len(file_lines.symmetric_difference(db_lines))

        # Determine severity based on similarity and changes
        if similarity > 0.9:
            return ConflictSeverity.LOW
        elif similarity > 0.7:
            return ConflictSeverity.MEDIUM
        elif similarity > 0.3:
            return ConflictSeverity.HIGH
        else:
            return ConflictSeverity.CRITICAL

    async def _identify_affected_sections(self, conflict: SyncConflict) -> List[str]:
        """Identify which sections of the document are affected by the conflict."""
        if not conflict.file_content or not conflict.database_content:
            return []

        sections = []

        # Look for section markers in markdown
        import re
        section_pattern = r'^#+\s+(.+)$|^<!-- ID:\s*(.+)\s*-->$'

        file_sections = re.findall(section_pattern, conflict.file_content, re.MULTILINE)
        db_sections = re.findall(section_pattern, conflict.database_content, re.MULTILINE)

        # Find sections that differ
        all_sections = set([s[0] or s[1] for s in file_sections + db_sections])

        for section in all_sections:
            if section.strip():
                sections.append(section.strip())

        return sections

    async def _is_auto_resolvable(self, conflict: SyncConflict, severity: ConflictSeverity) -> bool:
        """Determine if a conflict can be automatically resolved."""
        # Low severity conflicts are usually safe to auto-resolve
        if severity in [ConflictSeverity.LOW]:
            return True

        # Check time difference - large gaps suggest independent work
        time_diff = abs(conflict.file_timestamp - conflict.database_timestamp)
        if time_diff > 3600:  # 1 hour
            return True

        # Check content similarity
        similarity = self._calculate_content_similarity(conflict)
        if similarity > 0.8:
            return True

        return False

    async def _suggest_resolution(self, conflict: SyncConflict, severity: ConflictSeverity) -> ConflictResolution:
        """Suggest the best resolution strategy."""
        # For low severity, use latest wins
        if severity == ConflictSeverity.LOW:
            return ConflictResolution.LATEST_WINS

        # For critical conflicts, require manual intervention
        if severity == ConflictSeverity.CRITICAL:
            return ConflictResolution.MANUAL

        # For medium/high severity, consider time difference
        time_diff = conflict.file_timestamp - conflict.database_timestamp
        if abs(time_diff) < 60:  # Within 1 minute - likely concurrent edit
            return ConflictResolution.MANUAL
        elif time_diff > 0:
            return ConflictResolution.FILE_WINS  # File is newer
        else:
            return ConflictResolution.DATABASE_WINS  # Database is newer

    async def _calculate_confidence(self, conflict: SyncConflict, severity: ConflictSeverity) -> float:
        """Calculate confidence score for the suggested resolution."""
        base_confidence = 0.5

        # Adjust based on severity
        severity_adjustments = {
            ConflictSeverity.LOW: 0.4,
            ConflictSeverity.MEDIUM: 0.2,
            ConflictSeverity.HIGH: -0.1,
            ConflictSeverity.CRITICAL: -0.3
        }

        confidence = base_confidence + severity_adjustments[severity]

        # Adjust based on time difference
        time_diff = abs(conflict.file_timestamp - conflict.database_timestamp)
        if time_diff > 3600:  # Large time gap increases confidence
            confidence += 0.2

        # Adjust based on content similarity
        similarity = self._calculate_content_similarity(conflict)
        if similarity > 0.8:
            confidence += 0.1
        elif similarity < 0.3:
            confidence -= 0.2

        return max(0.0, min(1.0, confidence))

    def _calculate_content_similarity(self, conflict: SyncConflict) -> float:
        """Calculate similarity between file and database content."""
        if not conflict.file_content or not conflict.database_content:
            return 0.0

        import difflib
        return difflib.SequenceMatcher(None, conflict.file_content, conflict.database_content).ratio()

    def _calculate_size_difference(self, conflict: SyncConflict) -> int:
        """Calculate size difference between file and database content."""
        file_size = len(conflict.file_content) if conflict.file_content else 0
        db_size = len(conflict.database_content) if conflict.database_content else 0
        return file_size - db_size

    async def _create_merge_suggestion(self, conflict: SyncConflict) -> Optional[str]:
        """Create a merge suggestion for manual resolution."""
        try:
            if not conflict.file_content or not conflict.database_content:
                return conflict.file_content or conflict.database_content

            # For now, implement a simple strategy: prefer file content but note conflicts
            # In a more sophisticated implementation, this could use three-way merging
            return conflict.file_content

        except Exception as e:
            self._logger.error(f"Failed to create merge suggestion: {e}")
            return None

    async def get_resolution_history(self, limit: int = 100) -> List[ResolutionAction]:
        """Get the history of conflict resolutions."""
        return self._resolution_history[-limit:]

    async def get_conflict_statistics(self) -> Dict[str, Any]:
        """Get statistics about conflict resolution."""
        if not self._resolution_history:
            return {
                'total_resolutions': 0,
                'resolution_strategies': {},
                'resolvers': {},
                'average_confidence': 0.0
            }

        total_resolutions = len(self._resolution_history)
        strategies = {}
        resolvers = {}
        confidences = []

        for action in self._resolution_history:
            # Count strategies
            strategy = action.resolution_strategy.value
            strategies[strategy] = strategies.get(strategy, 0) + 1

            # Count resolvers
            resolver = action.resolver
            resolvers[resolver] = resolvers.get(resolver, 0) + 1

            # Collect confidences
            if 'confidence' in action.metadata:
                confidences.append(action.metadata['confidence'])

        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            'total_resolutions': total_resolutions,
            'resolution_strategies': strategies,
            'resolvers': resolvers,
            'average_confidence': avg_confidence,
            'most_common_strategy': max(strategies.items(), key=lambda x: x[1])[0] if strategies else None,
            'most_active_resolver': max(resolvers.items(), key=lambda x: x[1])[0] if resolvers else None
        }

    async def create_conflict_report(
        self,
        conflicts: List[SyncConflict],
        output_format: str = "json"
    ) -> str:
        """Create a comprehensive report of conflicts and their resolutions."""
        try:
            report_data = {
                'report_timestamp': self.change_logger._generate_change_id(Path("report"), "conflict_report"),
                'total_conflicts': len(conflicts),
                'conflicts': []
            }

            for conflict in conflicts:
                analysis = await self.analyze_conflict(conflict)

                conflict_data = {
                    'file_path': str(conflict.file_path),
                    'conflict_type': conflict.conflict_type,
                    'severity': analysis.severity.value,
                    'affected_sections': analysis.affected_sections,
                    'auto_resolvable': analysis.auto_resolvable,
                    'suggested_resolution': analysis.suggested_resolution.value,
                    'confidence_score': analysis.confidence_score,
                    'time_difference': conflict.file_timestamp - conflict.database_timestamp,
                    'content_similarity': analysis.analysis_details.get('content_similarity', 0.0)
                }

                report_data['conflicts'].append(conflict_data)

            # Add summary statistics
            severities = [c['severity'] for c in report_data['conflicts']]
            report_data['summary'] = {
                'by_severity': {
                    severity: severities.count(severity) for severity in set(severities)
                },
                'auto_resolvable_count': sum(1 for c in report_data['conflicts'] if c['auto_resolvable']),
                'average_confidence': sum(c['confidence_score'] for c in report_data['conflicts']) / len(report_data['conflicts']) if report_data['conflicts'] else 0
            }

            if output_format == "json":
                return json.dumps(report_data, indent=2)
            elif output_format == "markdown":
                return self._format_report_as_markdown(report_data)
            else:
                raise ValueError(f"Unsupported output format: {output_format}")

        except Exception as e:
            self._logger.error(f"Failed to create conflict report: {e}")
            return ""

    def _format_report_as_markdown(self, report_data: Dict[str, Any]) -> str:
        """Format conflict report as markdown."""
        lines = [
            "# Conflict Resolution Report",
            f"",
            f"**Total Conflicts:** {report_data['total_conflicts']}",
            f"**Auto-resolvable:** {report_data['summary']['auto_resolvable_count']}",
            f"**Average Confidence:** {report_data['summary']['average_confidence']:.2f}",
            f"",
            "## Severity Distribution",
            f""
        ]

        for severity, count in report_data['summary']['by_severity'].items():
            lines.append(f"- **{severity.title()}:** {count}")

        lines.extend([
            f"",
            "## Conflict Details",
            f""
        ])

        for conflict in report_data['conflicts']:
            lines.extend([
                f"### {conflict['file_path']}",
                f"",
                f"- **Type:** {conflict['conflict_type']}",
                f"- **Severity:** {conflict['severity']}",
                f"- **Suggested Resolution:** {conflict['suggested_resolution']}",
                f"- **Confidence:** {conflict['confidence_score']:.2f}",
                f"- **Auto-resolvable:** {'Yes' if conflict['auto_resolvable'] else 'No'}",
                f""
            ])

            if conflict['affected_sections']:
                lines.append("**Affected Sections:**")
                for section in conflict['affected_sections']:
                    lines.append(f"- {section}")
                lines.append("")

        return '\n'.join(lines)