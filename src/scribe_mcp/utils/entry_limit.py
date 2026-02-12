#!/usr/bin/env python3
"""
EntryLimitManager - Intelligent entry limiting based on priority and display mode.

Replaces TokenBudgetManager's blind truncation with count-based limits
that preserve complete entries and prioritize important content.
"""

from typing import Any, Dict, List, Optional, Tuple


class EntryLimitManager:
    """Intelligent entry limiting based on priority and display mode.

    Replaces TokenBudgetManager's blind truncation with count-based limits
    that preserve complete entries and prioritize important content.
    """

    # Default limits per display mode
    MODE_LIMITS = {
        "summary": 50,
        "full": 10,
        "expandable": 50,
        "structured": 100,
        "compact": 200,
        "readable": 50,  # Same as summary
    }

    # Priority sort order (lower = higher priority)
    PRIORITY_ORDER = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def limit_entries(
        self,
        entries: List[Dict[str, Any]],
        mode: str = "summary",
        priority_filter: Optional[List[str]] = None,
        max_entries: Optional[int] = None,
        sort_by_priority: bool = True,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Limit entries intelligently based on mode and priority.

        Args:
            entries: List of log entry dicts
            mode: Display mode (summary, full, expandable, structured, compact, readable)
            priority_filter: Only include entries with these priorities
            max_entries: Override default limit for mode
            sort_by_priority: If True, sort by priority first, then by time

        Returns:
            Tuple of (limited_entries, metadata_dict)

        Metadata dict contains:
            - total_available: Original entry count
            - filtered_count: Count after priority filter
            - returned_count: Final count returned
            - entries_omitted: How many were cut
            - mode: Display mode used
            - limit_applied: The limit that was applied
        """
        total_available = len(entries)

        # Apply priority filter if provided
        if priority_filter:
            filtered_entries = self._filter_by_priority(entries, priority_filter)
        else:
            filtered_entries = entries.copy()

        filtered_count = len(filtered_entries)

        # Sort by priority if requested
        if sort_by_priority:
            # Sort by priority order (ASC), then by timestamp (DESC - newest first)
            filtered_entries = sorted(
                filtered_entries,
                key=lambda e: (
                    self.PRIORITY_ORDER.get(e.get("priority", "medium"), 2),
                    e.get("ts_iso", "")
                ),
                reverse=False  # Priority ASC, but we need time DESC
            )

            # Fix time sorting: within each priority, sort newest first
            # Group by priority and re-sort each group by time DESC
            priority_groups: Dict[int, List[Dict[str, Any]]] = {}
            for entry in filtered_entries:
                priority = entry.get("priority", "medium")
                priority_order = self.PRIORITY_ORDER.get(priority, 2)
                if priority_order not in priority_groups:
                    priority_groups[priority_order] = []
                priority_groups[priority_order].append(entry)

            # Sort each group by timestamp DESC (newest first)
            filtered_entries = []
            for priority_order in sorted(priority_groups.keys()):
                group = priority_groups[priority_order]
                group_sorted = sorted(
                    group,
                    key=lambda e: e.get("ts_iso", ""),
                    reverse=True  # Newest first within priority group
                )
                filtered_entries.extend(group_sorted)

        # Determine limit
        limit = max_entries if max_entries is not None else self.MODE_LIMITS.get(mode, 50)

        # Apply limit
        limited_entries = filtered_entries[:limit]
        returned_count = len(limited_entries)
        entries_omitted = filtered_count - returned_count

        # Build metadata
        metadata = {
            "total_available": total_available,
            "filtered_count": filtered_count,
            "returned_count": returned_count,
            "entries_omitted": max(0, entries_omitted),
            "mode": mode,
            "limit_applied": limit,
        }

        return limited_entries, metadata

    def _get_priority_sort_key(self, entry: Dict[str, Any]) -> Tuple[int, str]:
        """
        Generate sort key for priority-based ordering.
        Returns (priority_order, timestamp) for proper sorting.

        Note: This is a helper method. The actual sorting logic in limit_entries
        handles the reversal for timestamp DESC within each priority group.
        """
        priority = entry.get("priority", "medium")
        priority_order = self.PRIORITY_ORDER.get(priority, 2)  # Default to medium
        ts_iso = entry.get("ts_iso", "")
        return (priority_order, ts_iso)

    def _filter_by_priority(
        self,
        entries: List[Dict[str, Any]],
        priority_filter: List[str]
    ) -> List[Dict[str, Any]]:
        """Filter entries to only include specified priorities."""
        return [
            entry for entry in entries
            if entry.get("priority", "medium") in priority_filter
        ]
