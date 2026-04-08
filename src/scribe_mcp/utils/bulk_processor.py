"""
Bulk Processing Utilities for MCP Tools

This module provides reusable bulk processing patterns extracted from
append_entry.py, query_entries.py, and rotate_log.py to reduce code
duplication and improve maintainability.

Extracted from TOOL_AUDIT_1112025 refactoring project - Phase 1 Task 1.4
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Tuple
import re
import json

from ..shared.logging_utils import coerce_metadata_mapping

# Import time utilities from existing modules
try:
    from scribe_mcp.utils.time import utcnow
    from scribe_mcp.utils.time import _parse_timestamp as parse_timestamp
except ImportError:
    # Fallback implementations for compatibility
    def utcnow() -> datetime:
        """Get current UTC datetime."""
        return datetime.utcnow()

    def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
        """Parse timestamp string to datetime object."""
        try:
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            return None


class BulkProcessor:
    """
    Utility class containing static methods for common bulk processing patterns
    extracted from MCP tools to reduce code duplication and improve maintainability.

    All methods are pure functions with no side effects for easy testing and reuse.
    """

    @staticmethod
    def detect_bulk_mode(
        message: str = "",
        items: Optional[str] = None,
        items_list: Optional[List[Dict[str, Any]]] = None,
        length_threshold: int = 500
    ) -> bool:
        """
        Detect if content should be processed as bulk entries.

        Extracted from append_entry.py _should_use_bulk_mode() (lines 115-129).

        Args:
            message: Message content to analyze
            items: JSON string items indicator
            items_list: Direct list items indicator
            length_threshold: Character length threshold for bulk mode

        Returns:
            True if content should be processed in bulk mode
        """
        if items is not None or items_list is not None:
            return True

        # Check for multiline content. Bulk mode is intended for multi-entry operations
        # (explicit `items`/`items_list`) or auto-splitting multiline content.
        # Long single-line messages and pipe characters should remain single-entry logs.
        return message.count("\n") > 0

    @staticmethod
    def split_multiline_content(
        message: str,
        delimiter: str = "\n",
        auto_detect_status: bool = True,
        auto_detect_emoji: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Split multiline message into individual entries with smart content detection.

        Extracted from append_entry.py _split_multiline_message() (lines 132-168).

        Args:
            message: Multiline message to split
            delimiter: Delimiter for splitting lines
            auto_detect_status: Whether to auto-detect status from content
            auto_detect_emoji: Whether to auto-detect emoji from content

        Returns:
            List of entry dictionaries with split content
        """
        if not message:
            return []

        # Split by delimiter
        lines = message.split(delimiter)
        entries = []

        for line in lines:
            line = line.strip()
            if not line:  # Skip empty lines
                continue

            # Detect if this line might be structured (contains status indicators, emojis, etc.)
            entry = {"message": line}

            # Auto-detect status from common patterns
            if auto_detect_status:
                if any(indicator in line.lower() for indicator in ["error:", "fail", "exception", "traceback"]):
                    entry["status"] = "error"
                elif any(indicator in line.lower() for indicator in ["warning:", "warn", "caution"]):
                    entry["status"] = "warn"
                elif any(indicator in line.lower() for indicator in ["success:", "complete", "done", "finished"]):
                    entry["status"] = "success"
                elif any(indicator in line.lower() for indicator in ["fix:", "fixed", "resolved", "patched"]):
                    entry["status"] = "success"

            # Auto-detect emoji from line
            if auto_detect_emoji:
                words = line.split()
                for word in words:
                    if word.strip() and len(word.strip()) == 1 and ord(word.strip()[0]) > 127:  # Likely emoji
                        entry["emoji"] = word.strip()
                        break

            entries.append(entry)

        return entries

    @staticmethod
    def apply_timestamp_staggering(
        items: List[Dict[str, Any]],
        base_timestamp: Optional[str] = None,
        stagger_seconds: int = 1,
        timestamp_field: str = "timestamp_utc"
    ) -> List[Dict[str, Any]]:
        """
        Add individual timestamps to bulk items with staggering.

        Extracted from append_entry.py _prepare_bulk_items_with_timestamps() (lines 171-194).

        Args:
            items: List of items to add timestamps to
            base_timestamp: Base timestamp string (ISO format)
            stagger_seconds: Seconds to stagger between items
            timestamp_field: Field name for timestamp in items

        Returns:
            Items list with timestamps added
        """
        if not items:
            return items

        # Parse base timestamp or use current time
        base_dt = None
        if base_timestamp:
            base_dt = parse_timestamp(base_timestamp)

        if not base_dt:
            base_dt = utcnow()

        # Add staggered timestamps to each item
        for i, item in enumerate(items):
            if timestamp_field not in item:
                item_dt = base_dt + timedelta(seconds=i * stagger_seconds)
                item[timestamp_field] = item_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        return items

    @staticmethod
    def apply_inherited_metadata(
        items: List[Dict[str, Any]],
        inherited_meta: Optional[Dict[str, Any]] = None,
        inherited_status: Optional[str] = None,
        inherited_emoji: Optional[str] = None,
        inherited_agent: Optional[str] = None,
        meta_field: str = "meta"
    ) -> List[Dict[str, Any]]:
        """
        Apply inherited metadata and values to all items in bulk.

        Extracted from append_entry.py _apply_inherited_metadata() (lines 197-228).

        Args:
            items: List of items to apply metadata to
            inherited_meta: Metadata dictionary to merge
            inherited_status: Status to apply if missing
            inherited_emoji: Emoji to apply if missing
            inherited_agent: Agent to apply if missing
            meta_field: Field name for metadata in items

        Returns:
            Items list with inherited metadata applied
        """
        if not items:
            return items

        for item in items:
            # Apply inherited status if item doesn't have one
            if inherited_status and "status" not in item:
                item["status"] = inherited_status

            # Apply inherited emoji if item doesn't have one
            if inherited_emoji and "emoji" not in item:
                item["emoji"] = inherited_emoji

            # Apply inherited agent if item doesn't have one
            if inherited_agent and "agent" not in item:
                item["agent"] = inherited_agent

            # Merge inherited metadata with item metadata
            if inherited_meta or meta_field in item:
                item_meta_raw = item.get(meta_field)
                coerced_meta, error = coerce_metadata_mapping(item_meta_raw)
                if error:
                    coerced_meta.setdefault("meta_error", error)
                if inherited_meta:
                    merged_meta = {**coerced_meta, **inherited_meta}
                else:
                    merged_meta = coerced_meta
                if merged_meta:
                    item[meta_field] = merged_meta
                elif meta_field in item:
                    item[meta_field] = {}

        return items

    @staticmethod
    def filter_by_relevance_threshold(
        results: List[Dict[str, Any]],
        threshold: float = 0.0,
        relevance_field: str = "relevance_score"
    ) -> List[Dict[str, Any]]:
        """
        Filter results by relevance threshold.

        Extracted from query_entries.py _apply_relevance_scoring() (lines 1074-1085).

        Args:
            results: List of result dictionaries
            threshold: Minimum relevance score (0.0-1.0)
            relevance_field: Field name containing relevance score

        Returns:
            Filtered results meeting threshold
        """
        if threshold <= 0.0:
            return results

        # Filter results by relevance threshold
        filtered_results = [
            result for result in results
            if result.get(relevance_field, 0.0) >= threshold
        ]

        return filtered_results

    @staticmethod
    def prepare_bulk_items(
        items: Optional[List[Dict[str, Any]]] = None,
        message: str = "",
        meta: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        emoji: Optional[str] = None,
        agent: Optional[str] = None,
        timestamp_utc: Optional[str] = None,
        stagger_seconds: int = 1,
        auto_split: bool = True,
        split_delimiter: str = "\n",
        detect_bulk_mode: bool = True,
        length_threshold: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Comprehensive bulk item preparation combining all bulk processing utilities.

        This is a convenience method that combines the main bulk processing operations
        in the correct order for typical use cases.

        Args:
            items: Existing items list (takes precedence over message)
            message: Message to split if no items provided
            meta: Metadata to apply to all items
            status: Status to apply to all items
            emoji: Emoji to apply to all items
            agent: Agent to apply to all items
            timestamp_utc: Base timestamp for staggering
            stagger_seconds: Seconds between timestamps
            auto_split: Whether to auto-split message content
            split_delimiter: Delimiter for splitting message
            detect_bulk_mode: Whether to detect bulk mode automatically
            length_threshold: Character threshold for bulk detection

        Returns:
            Prepared list of bulk items
        """
        bulk_items = items

        # Convert message to bulk items if no items provided
        if not bulk_items and message:
            if detect_bulk_mode and BulkProcessor.detect_bulk_mode(message, length_threshold=length_threshold):
                # Split message into items
                bulk_items = BulkProcessor.split_multiline_content(
                    message, split_delimiter, auto_detect_status=True, auto_detect_emoji=True
                )
            else:
                # Single item from message
                bulk_items = [{"message": message}]

        if not bulk_items:
            return []

        # Apply inherited metadata and values
        bulk_items = BulkProcessor.apply_inherited_metadata(
            bulk_items, meta, status, emoji, agent
        )

        # Apply timestamp staggering
        bulk_items = BulkProcessor.apply_timestamp_staggering(
            bulk_items, timestamp_utc, stagger_seconds
        )

        return bulk_items

    @staticmethod
    def parse_json_items(items_json: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """
        Parse JSON items string with error handling.

        Helper method for consistent JSON parsing across tools.

        Args:
            items_json: JSON string to parse

        Returns:
            Tuple of (parsed_items, error_message)
        """
        try:
            parsed_items = json.loads(items_json)
            if not isinstance(parsed_items, list):
                return None, "Items parameter must be a JSON array"
            return parsed_items, None
        except json.JSONDecodeError:
            return None, "Items parameter must be valid JSON array"

    @staticmethod
    def validate_bulk_items(items: List[Dict[str, Any]], required_fields: List[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate bulk items structure and required fields.

        Args:
            items: List of items to validate
            required_fields: List of required field names

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(items, list):
            return False, "Items must be a list"

        if required_fields:
            for i, item in enumerate(items):
                if not isinstance(item, dict):
                    return False, f"Item {i} must be a dictionary"

                for field in required_fields:
                    if field not in item:
                        return False, f"Item {i} missing required field: {field}"

        return True, None


class ParallelBulkProcessor(BulkProcessor):
    """
    Enhanced bulk processor with parallel processing capabilities for performance optimization.

    Extends BulkProcessor with parallel execution foundations to address the 1-second delay
    bottleneck in append_entry bulk processing.
    """

    @staticmethod
    def prepare_parallel_bulk_items(
        items: Optional[List[Dict[str, Any]]] = None,
        message: str = "",
        meta: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        emoji: Optional[str] = None,
        agent: Optional[str] = None,
        timestamp_utc: Optional[str] = None,
        stagger_seconds: int = 0,  # Reduced for parallel processing
        auto_split: bool = True,
        split_delimiter: str = "\n",
        chunk_size: int = 10,  # Items to process in parallel
        max_workers: int = 4   # Maximum parallel workers
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Prepare bulk items with parallel processing configuration.

        Args:
            items: Existing items list (takes precedence over message)
            message: Message to split if no items provided
            meta: Metadata to apply to all items
            status: Status to apply to all items
            emoji: Emoji to apply to all items
            agent: Agent to apply to all items
            timestamp_utc: Base timestamp for staggering
            stagger_seconds: Seconds between timestamps (reduced for parallel)
            auto_split: Whether to auto-split message content
            split_delimiter: Delimiter for splitting message
            chunk_size: Number of items to process in each chunk
            max_workers: Maximum number of parallel workers

        Returns:
            Tuple of (prepared_items, processing_config)
        """
        # Prepare items using parent method
        prepared_items = BulkProcessor.prepare_bulk_items(
            items=items,
            message=message,
            meta=meta,
            status=status,
            emoji=emoji,
            agent=agent,
            timestamp_utc=timestamp_utc,
            stagger_seconds=stagger_seconds,
            auto_split=auto_split,
            split_delimiter=split_delimiter
        )

        # Create processing configuration for parallel execution
        processing_config = {
            "chunk_size": chunk_size,
            "max_workers": max_workers,
            "total_items": len(prepared_items),
            "estimated_chunks": (len(prepared_items) + chunk_size - 1) // chunk_size,
            "parallel_enabled": len(prepared_items) > chunk_size,
            "performance_optimization": True
        }

        return prepared_items, processing_config

    @staticmethod
    def create_processing_chunks(
        items: List[Dict[str, Any]],
        chunk_size: int = 10
    ) -> List[List[Dict[str, Any]]]:
        """
        Split bulk items into processing chunks for parallel execution.

        Args:
            items: List of items to chunk
            chunk_size: Size of each chunk

        Returns:
            List of item chunks
        """
        if not items:
            return []

        chunks = []
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            chunks.append(chunk)

        return chunks

    @staticmethod
    def estimate_processing_time(
        items_count: int,
        sequential_delay_seconds: float = 1.0,
        parallel_workers: int = 4,
        chunk_size: int = 10
    ) -> Dict[str, float]:
        """
        Estimate processing time for sequential vs parallel processing.

        Args:
            items_count: Number of items to process
            sequential_delay_seconds: Delay per item in sequential processing
            parallel_workers: Number of parallel workers
            chunk_size: Size of processing chunks

        Returns:
            Dictionary with time estimates in seconds
        """
        # Sequential processing time (current bottleneck)
        sequential_time = items_count * sequential_delay_seconds

        # Parallel processing time estimate
        if items_count <= chunk_size:
            parallel_time = sequential_delay_seconds  # Single chunk
        else:
            chunks = (items_count + chunk_size - 1) // chunk_size
            workers_needed = min(chunks, parallel_workers)
            parallel_time = chunks * (sequential_delay_seconds / workers_needed)

        return {
            "sequential_seconds": sequential_time,
            "parallel_seconds": parallel_time,
            "time_saved_seconds": sequential_time - parallel_time,
            "speedup_factor": sequential_time / parallel_time if parallel_time > 0 else 1.0
        }

    @staticmethod
    def optimize_for_performance(
        items: List[Dict[str, Any]],
        performance_mode: str = "balanced"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Optimize bulk items for performance based on mode.

        Args:
            items: List of items to optimize
            performance_mode: "fast", "balanced", or "conservative"

        Returns:
            Tuple of (optimized_items, optimization_info)
        """
        if not items:
            return items, {"optimized": False, "reason": "no_items"}

        optimization_config = {
            "fast": {
                "stagger_seconds": 0,
                "chunk_size": 20,
                "max_workers": 8,
                "metadata_compression": True
            },
            "balanced": {
                "stagger_seconds": 0,
                "chunk_size": 10,
                "max_workers": 4,
                "metadata_compression": False
            },
            "conservative": {
                "stagger_seconds": 1,
                "chunk_size": 5,
                "max_workers": 2,
                "metadata_compression": False
            }
        }

        config = optimization_config.get(performance_mode, optimization_config["balanced"])

        # Apply performance optimizations
        optimized_items = items.copy()

        # Reduce staggering for performance
        if config["stagger_seconds"] == 0:
            for item in optimized_items:
                if "timestamp_utc" in item:
                    # Use same timestamp for all items
                    if hasattr(ParallelBulkProcessor, '_base_timestamp'):
                        item["timestamp_utc"] = ParallelBulkProcessor._base_timestamp
                    else:
                        ParallelBulkProcessor._base_timestamp = item["timestamp_utc"]

        # Compress metadata if enabled
        if config.get("metadata_compression"):
            for item in optimized_items:
                if "meta" in item and isinstance(item["meta"], dict):
                    # Remove redundant or verbose metadata
                    compressed_meta = {}
                    for key, value in item["meta"].items():
                        if key in ["phase", "component", "action"]:  # Keep important keys
                            compressed_meta[key] = value
                        elif isinstance(value, str) and len(value) > 100:
                            # Truncate long string values
                            compressed_meta[key] = value[:50] + "..."
                        else:
                            compressed_meta[key] = value
                    item["meta"] = compressed_meta

        optimization_info = {
            "optimized": True,
            "performance_mode": performance_mode,
            "config": config,
            "items_processed": len(optimized_items),
            "estimated_improvement": ParallelBulkProcessor.estimate_processing_time(
                len(items), 1.0, config["max_workers"], config["chunk_size"]
            )
        }

        return optimized_items, optimization_info
