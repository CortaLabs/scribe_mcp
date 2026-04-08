#!/usr/bin/env python3
"""
Estimation utilities for log operations and resource calculations.

Provides standardized estimation algorithms for:
- File size to entry count estimation using EMA
- Entry count estimation with tail sampling refinement
- Bytes-per-line calculations with bounds checking
- Threshold band estimation for rotation decisions
- Pagination and result counting calculations
- Token estimation for response optimization
- Bulk processing chunking calculations

Extracted from multiple tools to eliminate duplication and provide
consistent, well-tested estimation algorithms across the codebase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple, Union

# Import token estimator if available
try:
    from .tokens import token_estimator
except ImportError:
    token_estimator = None


@dataclass
class EntryCountEstimate:
    """Result of entry count estimation with metadata."""
    count: int
    approximate: bool
    method: str
    details: Dict[str, Any]


@dataclass
class PaginationInfo:
    """Pagination metadata for responses."""
    page: int
    page_size: int
    total_count: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_count": self.total_count,
            "has_next": self.has_next,
            "has_prev": self.has_prev
        }


@dataclass
class ChunkCalculation:
    """Result of chunking calculations for bulk processing."""
    total_items: int
    chunk_size: int
    total_chunks: int
    remaining_items: int


class FileSizeEstimator:
    """Estimates entry counts from file sizes using various algorithms."""

    # Default constants from rotate_log.py
    DEFAULT_BYTES_PER_LINE = 80.0
    MIN_BYTES_PER_LINE = 16.0
    MAX_BYTES_PER_LINE = 512.0
    TAIL_SAMPLE_BYTES = 1024 * 1024  # 1MB

    def __init__(self,
                 default_bytes_per_line: float = DEFAULT_BYTES_PER_LINE,
                 min_bytes_per_line: float = MIN_BYTES_PER_LINE,
                 max_bytes_per_line: float = MAX_BYTES_PER_LINE,
                 tail_sample_bytes: int = TAIL_SAMPLE_BYTES):
        """Initialize estimator with configuration parameters."""
        self.default_bytes_per_line = default_bytes_per_line
        self.min_bytes_per_line = min_bytes_per_line
        self.max_bytes_per_line = max_bytes_per_line
        self.tail_sample_bytes = tail_sample_bytes

    def clamp_bytes_per_line(self, value: float) -> float:
        """Clamp bytes-per-line value within reasonable bounds."""
        return max(self.min_bytes_per_line, min(self.max_bytes_per_line, value))

    def estimate_entry_count_basic(self,
                                   size_bytes: int,
                                   bytes_per_line: Optional[float] = None) -> EntryCountEstimate:
        """
        Basic entry count estimation using file size and bytes-per-line.

        Args:
            size_bytes: File size in bytes
            bytes_per_line: Optional custom bytes-per-line value

        Returns:
            EntryCountEstimate with estimated count and metadata
        """
        if bytes_per_line is None:
            bytes_per_line = self.default_bytes_per_line
        else:
            bytes_per_line = self.clamp_bytes_per_line(bytes_per_line)

        if size_bytes <= 0:
            return EntryCountEstimate(0, False, "empty", {
                "size_bytes": size_bytes,
                "bytes_per_line": bytes_per_line,
                "method": "basic"
            })

        estimated = max(1, int(round(size_bytes / bytes_per_line)))
        return EntryCountEstimate(estimated, True, "basic", {
            "size_bytes": size_bytes,
            "bytes_per_line": bytes_per_line,
            "method": "basic",
            "approximation": "size_division"
        })

    def estimate_entry_count_with_cache(self,
                                       size_bytes: int,
                                       cached_stats: Optional[Dict[str, Any]] = None,
                                       file_mtime: Optional[int] = None) -> EntryCountEstimate:
        """
        Entry count estimation with cache support and EMA fallback.

        Args:
            size_bytes: Current file size in bytes
            cached_stats: Optional cached statistics from previous operations
            file_mtime: Optional file modification time for cache validation

        Returns:
            EntryCountEstimate with estimated count and metadata
        """
        details: Dict[str, Any] = {"size_bytes": size_bytes}

        # Check cache validity
        if cached_stats:
            cached_size = cached_stats.get("size_bytes")
            cached_mtime = cached_stats.get("mtime_ns")
            cached_line_count = cached_stats.get("line_count")

            if (cached_size is not None and
                cached_mtime is not None and
                cached_line_count is not None and
                cached_size == size_bytes and
                cached_mtime == file_mtime):

                details.update({
                    "source": cached_stats.get("source", "cache"),
                    "cache_hit": True,
                    "ema_bytes_per_line": cached_stats.get("ema_bytes_per_line"),
                })
                return EntryCountEstimate(int(cached_line_count), False, "cache", details)

            # Use EMA from cache if available
            ema = cached_stats.get("ema_bytes_per_line")
            if ema:
                ema = self.clamp_bytes_per_line(float(ema))
                details["ema_bytes_per_line"] = ema
            else:
                ema = None
        else:
            ema = None
            details["cache_hit"] = False

        # Fall back to default EMA
        if ema is None:
            ema = self.default_bytes_per_line
            details["source"] = "initial_estimate"

        details["ema_bytes_per_line"] = ema

        if size_bytes <= 0:
            return EntryCountEstimate(0, False, "empty", details)

        estimated = max(1, int(round(size_bytes / ema)))
        details["approximation"] = "ema"
        return EntryCountEstimate(estimated, True, "ema", details)

    def refine_estimate_with_sampling(self,
                                      log_path: Path,
                                      size_bytes: int,
                                      initial_estimate: EntryCountEstimate) -> Optional[EntryCountEstimate]:
        """
        Refine entry count estimate using tail sampling.

        Args:
            log_path: Path to the log file
            size_bytes: File size in bytes
            initial_estimate: Initial estimate to potentially refine

        Returns:
            Refined EntryCountEstimate or None if refinement failed
        """
        if not initial_estimate.approximate:
            return initial_estimate

        if not size_bytes:
            return None

        sample_size = min(size_bytes, self.tail_sample_bytes)
        if sample_size <= 0:
            return None

        try:
            with open(log_path, "rb") as handle:
                if size_bytes > sample_size:
                    handle.seek(size_bytes - sample_size)
                data = handle.read(sample_size)
        except OSError:
            return None

        newline_count = data.count(b"\n")
        if newline_count <= 0:
            return None

        bytes_per_line = sample_size / newline_count
        bytes_per_line = self.clamp_bytes_per_line(bytes_per_line)
        refined = max(1, int(round(size_bytes / bytes_per_line)))

        details = dict(initial_estimate.details)
        details.update({
            "tail_sample_bytes": sample_size,
            "tail_newlines": newline_count,
            "refined_bytes_per_line": bytes_per_line,
        })

        approximate = sample_size != size_bytes
        if not approximate:
            method = "full_tail"
        else:
            method = "tail" if initial_estimate.method == "empty" else f"{initial_estimate.method}+tail"

        return EntryCountEstimate(refined, approximate, method, details)

    def compute_bytes_per_line(self, size_bytes: Optional[int], line_count: Optional[int]) -> Optional[float]:
        """
        Compute bytes-per-line from size and count, with bounds checking.

        Args:
            size_bytes: File size in bytes
            line_count: Number of lines

        Returns:
            Bytes-per-line value within reasonable bounds or None
        """
        if not size_bytes or not line_count or line_count <= 0:
            return None

        return self.clamp_bytes_per_line(float(size_bytes) / float(line_count))


class ThresholdEstimator:
    """Estimates threshold bands and rotation decision parameters."""

    ESTIMATION_BAND_RATIO = 0.1
    ESTIMATION_BAND_MIN = 250

    def compute_estimation_band(self, threshold: Optional[int]) -> Optional[int]:
        """
        Compute estimation band for threshold-based decisions.

        Args:
            threshold: Base threshold value

        Returns:
            Estimated band value or None if no threshold
        """
        if not threshold:
            return None

        return max(int(threshold * self.ESTIMATION_BAND_RATIO), self.ESTIMATION_BAND_MIN)

    def classify_estimate(self, value: int, threshold: int, band: Optional[int]) -> str:
        """
        Classify an estimate relative to threshold and band.

        Args:
            value: Estimated value
            threshold: Threshold value
            band: Optional band for ranges

        Returns:
            Classification string
        """
        if band is None:
            return "above_threshold" if value >= threshold else "below_threshold"

        if value >= threshold:
            return "well_above_threshold"
        elif value >= threshold - band:
            return "near_threshold"
        else:
            return "well_below_threshold"


class PaginationCalculator:
    """Handles pagination calculations for query results."""

    @staticmethod
    def create_pagination_info(page: int, page_size: int, total_count: int) -> PaginationInfo:
        """
        Create pagination information for query results.

        Args:
            page: Current page number (1-based)
            page_size: Number of items per page
            total_count: Total number of items

        Returns:
            PaginationInfo with calculated metadata
        """
        has_next = (page * page_size) < total_count
        has_prev = page > 1

        return PaginationInfo(
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_next=has_next,
            has_prev=has_prev
        )

    @staticmethod
    def calculate_pagination_indices(page: int, page_size: int, total_count: int) -> Tuple[int, int]:
        """
        Calculate start and end indices for pagination.

        Args:
            page: Current page number (1-based)
            page_size: Number of items per page
            total_count: Total number of items

        Returns:
            Tuple of (start_idx, end_idx) for slicing
        """
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_count)
        return start_idx, end_idx

    @staticmethod
    def calculate_total_pages(total_count: int, page_size: int) -> int:
        """
        Calculate total number of pages needed.

        Args:
            total_count: Total number of items
            page_size: Number of items per page

        Returns:
            Total number of pages
        """
        return math.ceil(total_count / page_size) if total_count > 0 else 1


class BulkProcessingCalculator:
    """Handles calculations for bulk processing operations."""

    @staticmethod
    def calculate_chunks(total_items: int, chunk_size: int) -> ChunkCalculation:
        """
        Calculate chunking parameters for bulk processing.

        Args:
            total_items: Total number of items to process
            chunk_size: Desired chunk size

        Returns:
            ChunkCalculation with chunking details
        """
        if chunk_size <= 0:
            # Avoid division by zero - treat as single chunk
            return ChunkCalculation(
                total_items=total_items,
                chunk_size=chunk_size,
                total_chunks=1,
                remaining_items=total_items
            )

        total_chunks = (total_items + chunk_size - 1) // chunk_size
        remaining_items = total_items % chunk_size

        return ChunkCalculation(
            total_items=total_items,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            remaining_items=remaining_items
        )

    @staticmethod
    def calculate_optimal_chunk_size(total_items: int,
                                     target_chunks: int = 4,
                                     min_chunk_size: int = 10,
                                     max_chunk_size: int = 100) -> int:
        """
        Calculate optimal chunk size based on total items and target chunks.

        Args:
            total_items: Total number of items to process
            target_chunks: Desired number of chunks
            min_chunk_size: Minimum allowed chunk size
            max_chunk_size: Maximum allowed chunk size

        Returns:
            Optimal chunk size within bounds
        """
        if total_items <= min_chunk_size:
            return total_items

        optimal_size = max(min_chunk_size, total_items // target_chunks)
        return min(optimal_size, max_chunk_size)


class TokenEstimator:
    """Handles token estimation for response optimization."""

    @staticmethod
    def estimate_tokens(data: Union[Dict, List, str]) -> int:
        """
        Estimate token count for response data.

        Args:
            data: Data to estimate tokens for

        Returns:
            Estimated token count
        """
        try:
            if token_estimator:
                return token_estimator(data)
        except (ImportError, AttributeError, TypeError):
            pass  # Fall back to rough estimation

        # Fallback estimation: rough approximation
        if isinstance(data, str):
            # Rough approximation: ~4 characters per token
            return len(data) // 4
        elif isinstance(data, (dict, list)):
            # JSON serialization length approximation
            json_str = str(data)
            return len(json_str) // 4
        else:
            return len(str(data)) // 4

    @staticmethod
    def estimate_response_tokens(entries: List[Dict[str, Any]],
                               include_metadata: bool = True) -> int:
        """
        Estimate tokens for a list of log entries.

        Args:
            entries: List of log entry dictionaries
            include_metadata: Whether to include metadata in estimation

        Returns:
            Total estimated tokens
        """
        total_tokens = 0

        for entry in entries:
            # Estimate entry content tokens
            message = entry.get("message", "")
            total_tokens += TokenEstimator.estimate_tokens(message)

            if include_metadata:
                # Estimate metadata tokens
                metadata = {k: v for k, v in entry.items() if k != "message"}
                total_tokens += TokenEstimator.estimate_tokens(metadata)

        return total_tokens


class EstimatorUtilities:
    """High-level interface for all estimation operations."""

    def __init__(self):
        """Initialize all estimator components."""
        self.file_size = FileSizeEstimator()
        self.threshold = ThresholdEstimator()
        self.pagination = PaginationCalculator()
        self.bulk = BulkProcessingCalculator()
        self.tokens = TokenEstimator()

    def estimate_file_operations(self,
                                 file_path: Path,
                                 cached_stats: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Comprehensive file operation estimation.

        Args:
            file_path: Path to the file
            cached_stats: Optional cached statistics

        Returns:
            Dictionary with all estimation results
        """
        if not file_path.exists():
            return {
                "exists": False,
                "size_bytes": 0,
                "entry_estimate": EntryCountEstimate(0, False, "file_not_found", {})
            }

        stat = file_path.stat()
        size_bytes = stat.st_size
        mtime_ns = stat.st_mtime_ns

        # Basic estimation
        basic_estimate = self.file_size.estimate_entry_count_basic(size_bytes)

        # Cached estimation
        cached_estimate = self.file_size.estimate_entry_count_with_cache(
            size_bytes, cached_stats, mtime_ns
        )

        # Refined estimation if needed
        refined_estimate = self.file_size.refine_estimate_with_sampling(
            file_path, size_bytes, cached_estimate
        )

        final_estimate = refined_estimate or cached_estimate

        return {
            "exists": True,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 3),
            "mtime_ns": mtime_ns,
            "entry_estimate": final_estimate,
            "basic_estimate": basic_estimate,
            "cached_estimate": cached_estimate,
            "refined_estimate": refined_estimate
        }


class ParameterTypeEstimator:
    """
    Enhanced parameter type estimation and correction for bulletproof parameter handling.

    Provides intelligent type detection, conversion, and validation to automatically
    correct parameter type mismatches that cause MCP tool failures.
    """

    @staticmethod
    def estimate_and_convert_parameter_type(
        value: Any,
        expected_type: type,
        parameter_name: str = "parameter"
    ) -> Tuple[Any, bool, Optional[str]]:
        """
        Estimate parameter type and convert if necessary.

        Args:
            value: Input value to convert
            expected_type: Expected type for the parameter
            parameter_name: Name of the parameter for error messages

        Returns:
            Tuple of (converted_value, conversion_successful, error_message)
        """
        # If value is already correct type, return as-is
        if isinstance(value, expected_type):
            return value, True, None

        # Try type conversion based on expected type
        try:
            if expected_type == int:
                # Handle numeric conversion
                if isinstance(value, str):
                    # Remove common numeric formatting
                    cleaned = str(value).strip().replace(',', '')
                    # Handle comparison operators in strings (the main bug cause)
                    if cleaned and any(op in cleaned for op in ['<', '>', '=', '<=', '>=', '==', '!=']):
                        # Extract numeric part from comparison
                        import re
                        numeric_match = re.search(r'(\d+\.?\d*)', cleaned)
                        if numeric_match:
                            converted = int(float(numeric_match.group(1)))
                            return converted, True, f"Extracted numeric value from comparison: {cleaned}"
                    else:
                        converted = int(float(cleaned))
                        return converted, True, f"Converted string to integer: {value} -> {converted}"
                elif isinstance(value, float):
                    converted = int(value)
                    return converted, True, f"Converted float to integer: {value} -> {converted}"
                elif isinstance(value, bool):
                    converted = int(value)
                    return converted, True, f"Converted boolean to integer: {value} -> {converted}"

            elif expected_type == float:
                if isinstance(value, str):
                    cleaned = str(value).strip().replace(',', '')
                    # Handle comparison operators
                    if cleaned and any(op in cleaned for op in ['<', '>', '=', '<=', '>=', '==', '!=']):
                        import re
                        numeric_match = re.search(r'(\d+\.?\d*)', cleaned)
                        if numeric_match:
                            converted = float(numeric_match.group(1))
                            return converted, True, f"Extracted numeric value from comparison: {cleaned}"
                    else:
                        converted = float(cleaned)
                        return converted, True, f"Converted string to float: {value} -> {converted}"
                elif isinstance(value, int):
                    converted = float(value)
                    return converted, True, f"Converted integer to float: {value} -> {converted}"
                elif isinstance(value, bool):
                    converted = float(value)
                    return converted, True, f"Converted boolean to float: {value} -> {converted}"

            elif expected_type == str:
                converted = str(value)
                return converted, True, f"Converted to string: {type(value).__name__} -> {converted}"

            elif expected_type == bool:
                if isinstance(value, str):
                    lowered = str(value).lower().strip()
                    if lowered in ['true', '1', 'yes', 'on', 'enabled']:
                        converted = True
                        return converted, True, f"Converted string to boolean: {value} -> True"
                    elif lowered in ['false', '0', 'no', 'off', 'disabled']:
                        converted = False
                        return converted, True, f"Converted string to boolean: {value} -> False"
                elif isinstance(value, (int, float)):
                    converted = bool(value)
                    return converted, True, f"Converted numeric to boolean: {value} -> {converted}"

            elif expected_type == list:
                if isinstance(value, str):
                    # Handle comma-separated strings and common delimiters
                    delimiters = [',', ';', '|', '\n']
                    items = [value]
                    for delimiter in delimiters:
                        if delimiter in value:
                            items = [item.strip() for item in value.split(delimiter) if item.strip()]
                            break
                    return items, True, f"Split string into list: {value} -> {items}"
                elif not isinstance(value, list):
                    # Convert single item to list
                    return [value], True, f"Converted single item to list: {value} -> [{value}]"

            elif expected_type == dict:
                if isinstance(value, str):
                    # Try JSON parsing
                    try:
                        import json
                        parsed = json.loads(value)
                        if isinstance(parsed, dict):
                            return parsed, True, f"Parsed JSON string to dict: {value}"
                        else:
                            return {"value": parsed}, True, f"Wrapped JSON in dict: {parsed}"
                    except json.JSONDecodeError:
                        return {"value": value}, True, f"Wrapped string in dict: {value}"
                elif not isinstance(value, dict):
                    return {"value": value}, True, f"Wrapped value in dict: {value}"

        except (ValueError, TypeError, AttributeError) as e:
            return value, False, f"Failed to convert {parameter_name} from {type(value).__name__} to {expected_type.__name__}: {e}"

        # If no conversion strategy worked, return original
        return value, False, f"Cannot convert {parameter_name} from {type(value).__name__} to {expected_type.__name__}"

    @staticmethod
    def heal_comparison_operator_bug(
        value: Any,
        parameter_name: str = "parameter"
    ) -> Tuple[Any, bool, Optional[str]]:
        """
        Specifically heal the comparison operator bug that causes type errors.

        This addresses the core issue where strings containing comparison operators
        like "10 < 20" cause type errors when compared with integers.

        Args:
            value: Input value that may contain comparison operators
            parameter_name: Name of the parameter for error messages

        Returns:
            Tuple of (healed_value, healing_applied, healing_message)
        """
        if not isinstance(value, str):
            return value, False, None

        import re

        # Check for comparison operator patterns that cause the bug
        comparison_patterns = [
            r'^\s*\d+\.?\d*\s*[<>=!]+\s*\d+\.?\d*\s*$',  # Basic comparisons: "10 < 20"
            r'^\s*[<>=!]+\s*\d+\.?\d*\s*$',              # Prefix comparisons: "< 10"
            r'^\s*\d+\.?\d*\s*[<>=!]+\s*$',              # Suffix comparisons: "10 >"
        ]

        for pattern in comparison_patterns:
            if re.match(pattern, value.strip()):
                # Extract numeric value from comparison
                numeric_match = re.search(r'(\d+\.?\d*)', value)
                if numeric_match:
                    numeric_value = numeric_match.group(1)
                    try:
                        # Try to convert to int first, then float
                        if '.' in numeric_value:
                            healed_value = float(numeric_value)
                        else:
                            healed_value = int(numeric_value)

                        healing_message = f"Healed comparison operator bug in {parameter_name}: '{value}' -> {healed_value}"
                        return healed_value, True, healing_message
                    except ValueError:
                        # If conversion fails, quote the string to prevent interpretation
                        healed_value = f"'{value}'"
                        healing_message = f"Healed comparison operator bug in {parameter_name} by quoting: '{value}'"
                        return healed_value, True, healing_message

        return value, False, None

    @staticmethod
    def auto_heal_parameter_type(
        value: Any,
        expected_type: type,
        parameter_name: str = "parameter",
        fallback_value: Any = None
    ) -> Tuple[Any, bool, Optional[str]]:
        """
        Comprehensive auto-healing for parameter type issues.

        Args:
            value: Input value to heal
            expected_type: Expected type for the parameter
            parameter_name: Name of the parameter
            fallback_value: Fallback value if all healing attempts fail

        Returns:
            Tuple of (healed_value, healing_successful, healing_message)
        """
        # First, try to heal comparison operator bugs specifically
        healed_value, comparison_healed, comparison_message = ParameterTypeEstimator.heal_comparison_operator_bug(
            value, parameter_name
        )

        if comparison_healed:
            # Try to convert the healed value to expected type
            final_value, conversion_successful, conversion_message = ParameterTypeEstimator.estimate_and_convert_parameter_type(
                healed_value, expected_type, parameter_name
            )
            if conversion_successful:
                combined_message = f"{comparison_message}; {conversion_message}"
                return final_value, True, combined_message
            else:
                return healed_value, True, comparison_message

        # If no comparison bug, try regular type conversion
        converted_value, conversion_successful, conversion_message = ParameterTypeEstimator.estimate_and_convert_parameter_type(
            value, expected_type, parameter_name
        )

        if conversion_successful:
            return converted_value, True, conversion_message

        # If all else fails, use fallback value
        if fallback_value is not None:
            return fallback_value, True, f"Used fallback value for {parameter_name}: {fallback_value}"

        return value, False, f"Could not auto-heal {parameter_name} type from {type(value).__name__} to {expected_type.__name__}"