"""
Project state detection utilities for hash-based SITREP generation.

This module provides functions to determine project state based on document hash
comparison, solving BUG-001 where post-rotation projects were incorrectly flagged as NEW.
"""

from typing import Dict, Tuple, Any, Optional


def detect_project_state(
    project: Dict[str, Any],
    entry_count: int,
    progress_log_path: Optional[str] = None,
    docs_were_generated: bool = False
) -> Tuple[str, str]:
    """
    Detect project state using four-state logic with hash comparison.

    This function implements hash-based project state detection to fix BUG-001,
    where projects were incorrectly marked as "NEW" after log rotation due to
    relying on entry_count == 0 instead of document generation status.

    States:
    - NEW: No baseline hashes AND docs were just generated (truly new project)
    - EXISTING_LEGACY: No baseline BUT docs already existed (pre-hash-tracking or rotated)
    - UNCHANGED: Baseline exists AND baseline == current (no doc modifications)
    - MODIFIED: Baseline exists AND baseline != current (docs changed since baseline)

    Args:
        project: Project dict from get_active_project() with meta.docs fields:
            - meta.docs.baseline_hashes: Dict of doc hashes at baseline
            - meta.docs.current_hashes: Dict of current doc hashes
            - meta.docs.flags: Dict of modification flags (e.g., architecture_modified)
        entry_count: Number of progress log entries (from backend.count_entries())
        progress_log_path: Optional path to progress log file (unused, kept for compatibility)
        docs_were_generated: True if docs were just created in this call, False if they existed

    Returns:
        (state, sitrep_message) tuple where:
        - state: One of ["NEW", "EXISTING_LEGACY", "UNCHANGED", "MODIFIED"]
        - sitrep_message: Human-readable status message for SITREP output

    Examples:
        >>> # New project
        >>> detect_project_state({"meta": {"docs": {}}}, 0)
        ("NEW", "🆕 New project initialized")

        >>> # Legacy project (pre-hash tracking)
        >>> detect_project_state({"meta": {"docs": {}}}, 47)
        ("EXISTING_LEGACY", "📋 Existing project (47 entries, pre-hash-tracking)")

        >>> # Post-rotation project (unchanged)
        >>> project = {
        ...     "meta": {
        ...         "docs": {
        ...             "baseline_hashes": {"architecture": "abc123"},
        ...             "current_hashes": {"architecture": "abc123"}
        ...         }
        ...     }
        ... }
        >>> detect_project_state(project, 0)
        ("UNCHANGED", "📋 Project unchanged (0 entries, docs match baseline)")

        >>> # Modified project
        >>> project = {
        ...     "meta": {
        ...         "docs": {
        ...             "baseline_hashes": {"architecture": "abc123"},
        ...             "current_hashes": {"architecture": "def456"},
        ...             "flags": {"architecture_modified": True}
        ...         }
        ...     }
        ... }
        >>> detect_project_state(project, 15)
        ("MODIFIED", "✏️ Modified: architecture (15 entries)")
    """
    # Extract hash metadata from project
    # Check both project["meta"]["docs"] and project["docs"] for compatibility
    # (logging_utils stores at project["docs"], set_project stores at meta["docs"])
    meta = project.get("meta", {})
    docs = meta.get("docs", {}) or project.get("docs", {})

    # Hashes can be at docs["_hashes"], docs directly, or legacy locations
    hashes = docs.get("_hashes", {})
    baseline_hashes = hashes.get("baseline_hashes", {}) or docs.get("baseline_hashes", {})
    current_hashes = hashes.get("current_hashes", {}) or docs.get("current_hashes", {})
    flags = docs.get("flags", {})

    if docs_were_generated and entry_count == 0:
        return ("NEW", "🆕 New project initialized")

    # Four-state detection logic
    if not baseline_hashes:
        # No baseline hashes exist.
        # If entries already exist we can confidently classify legacy/existing.
        if entry_count > 0:
            return ("EXISTING_LEGACY", f"📋 Existing project ({entry_count} entries, pre-hash-tracking)")

        # With zero entries, trust explicit generation signal when provided.
        if docs_were_generated:
            return ("NEW", "🆕 New project initialized")

        # If caller provided a concrete progress log path and docs were not generated
        # in this operation, treat as existing legacy (common post-rotation case).
        if progress_log_path:
            return ("EXISTING_LEGACY", "📋 Existing project (0 entries, post-rotation or pre-hash-tracking)")

        # Default for context-poor callers/tests: preserve legacy NEW semantics.
        return ("NEW", "🆕 New project initialized")
    else:
        # Baseline hashes exist - compare with current
        if baseline_hashes == current_hashes:
            # Documents match baseline (including post-rotation scenario)
            return ("UNCHANGED", f"📋 Project unchanged ({entry_count} entries, docs match baseline)")
        else:
            # Documents have been modified since baseline
            modified_docs = _extract_modified_docs(flags)
            if modified_docs:
                modified_list = ", ".join(modified_docs)
                return ("MODIFIED", f"✏️ Modified: {modified_list} ({entry_count} entries)")
            else:
                # Hashes differ but no flags set - generic modified message
                return ("MODIFIED", f"✏️ Project modified ({entry_count} entries, docs changed)")


def _extract_modified_docs(flags: Dict[str, Any]) -> list:
    """
    Extract list of modified document names from flags dict.

    Args:
        flags: Dict of modification flags (e.g., {"architecture_modified": True})

    Returns:
        List of document names that have been modified (e.g., ["architecture", "phase_plan"])

    Examples:
        >>> _extract_modified_docs({"architecture_modified": True, "phase_plan_modified": False})
        ['architecture']

        >>> _extract_modified_docs({"architecture_modified": True, "checklist_modified": True})
        ['architecture', 'checklist']

        >>> _extract_modified_docs({})
        []
    """
    modified = []
    for flag_name, is_modified in flags.items():
        if is_modified and flag_name.endswith("_modified"):
            # Extract doc name by removing "_modified" suffix
            doc_name = flag_name.replace("_modified", "")
            modified.append(doc_name)
    return modified
