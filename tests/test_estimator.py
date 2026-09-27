#!/usr/bin/env python3
"""
Comprehensive tests for estimation utilities.

Tests all estimation algorithms extracted from tools to ensure
identical behavior and proper edge case handling.
"""

import pytest
import tempfile
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path
from typing import Dict, Any

from scribe_mcp.utils.estimator import (
    EntryCountEstimate,
    PaginationInfo,
    ChunkCalculation,
    FileSizeEstimator,
    ThresholdEstimator,
    PaginationCalculator,
    BulkProcessingCalculator,
    TokenEstimator,
    EstimatorUtilities
)
import scribe_mcp.utils.tokens as token_utils
from scribe_mcp.utils.tokens import TokenEstimator as MetricsTokenEstimator, TokenMetrics


class TestEntryCountEstimate:
    """Test EntryCountEstimate dataclass."""

    def test_entry_count_estimate_creation(self):
        """Test EntryCountEstimate creation and attributes."""
        estimate = EntryCountEstimate(
            count=100,
            approximate=True,
            method="test",
            details={"test": "data"}
        )

        assert estimate.count == 100
        assert estimate.approximate is True
        assert estimate.method == "test"
        assert estimate.details["test"] == "data"


class TestPaginationInfo:
    """Test PaginationInfo dataclass."""

    def test_pagination_info_creation(self):
        """Test PaginationInfo creation and to_dict method."""
        info = PaginationInfo(
            page=2,
            page_size=50,
            total_count=150,
            has_next=True,
            has_prev=True
        )

        assert info.page == 2
        assert info.page_size == 50
        assert info.total_count == 150
        assert info.has_next is True
        assert info.has_prev is True

        result_dict = info.to_dict()
        expected = {
            "page": 2,
            "page_size": 50,
            "total_count": 150,
            "has_next": True,
            "has_prev": True
        }
        assert result_dict == expected


class TestChunkCalculation:
    """Test ChunkCalculation dataclass."""

    def test_chunk_calculation_creation(self):
        """Test ChunkCalculation creation."""
        calc = ChunkCalculation(
            total_items=150,
            chunk_size=50,
            total_chunks=3,
            remaining_items=0
        )

        assert calc.total_items == 150
        assert calc.chunk_size == 50
        assert calc.total_chunks == 3
        assert calc.remaining_items == 0


class TestFileSizeEstimator:
    """Test FileSizeEstimator class."""

    def test_estimator_initialization(self):
        """Test FileSizeEstimator initialization with custom values."""
        estimator = FileSizeEstimator(
            default_bytes_per_line=100.0,
            min_bytes_per_line=20.0,
            max_bytes_per_line=600.0,
            tail_sample_bytes=2_000_000
        )

        assert estimator.default_bytes_per_line == 100.0
        assert estimator.min_bytes_per_line == 20.0
        assert estimator.max_bytes_per_line == 600.0
        assert estimator.tail_sample_bytes == 2_000_000

    def test_clamp_bytes_per_line(self):
        """Test bytes-per-line clamping within bounds."""
        estimator = FileSizeEstimator()

        # Below minimum
        result = estimator.clamp_bytes_per_line(10.0)
        assert result == estimator.min_bytes_per_line

        # Above maximum
        result = estimator.clamp_bytes_per_line(1000.0)
        assert result == estimator.max_bytes_per_line

        # Within bounds
        result = estimator.clamp_bytes_per_line(100.0)
        assert result == 100.0

    def test_estimate_entry_count_basic(self):
        """Test basic entry count estimation."""
        estimator = FileSizeEstimator()

        # Zero size
        result = estimator.estimate_entry_count_basic(0)
        assert result.count == 0
        assert result.approximate is False
        assert result.method == "empty"

        # Negative size
        result = estimator.estimate_entry_count_basic(-100)
        assert result.count == 0
        assert result.method == "empty"

        # Normal size with default bytes-per-line
        result = estimator.estimate_entry_count_basic(8000)  # 8000 bytes / 80 = 100 entries
        assert result.count == 100
        assert result.approximate is True
        assert result.method == "basic"

        # Custom bytes-per-line
        result = estimator.estimate_entry_count_basic(8000, bytes_per_line=100.0)
        assert result.count == 80
        assert result.details["bytes_per_line"] == 100.0

    def test_estimate_entry_count_with_cache(self):
        """Test entry count estimation with cache support."""
        estimator = FileSizeEstimator()

        # No cache
        result = estimator.estimate_entry_count_with_cache(8000)
        assert result.count == 100
        assert result.method == "ema"
        assert result.details["source"] == "initial_estimate"

        # Valid cache hit
        cache_stats = {
            "size_bytes": 8000,
            "mtime_ns": 12345,
            "line_count": 100,
            "source": "test_cache"
        }
        result = estimator.estimate_entry_count_with_cache(8000, cache_stats, 12345)
        assert result.count == 100
        assert result.approximate is False
        assert result.method == "cache"
        assert result.details["cache_hit"] is True

        # Cache miss due to size change
        result = estimator.estimate_entry_count_with_cache(9000, cache_stats, 12345)
        assert result.method == "ema"
        assert result.details.get("cache_hit") is not True

        # Cache with EMA
        cache_stats_ema = {
            "ema_bytes_per_line": 90.0
        }
        result = estimator.estimate_entry_count_with_cache(9000, cache_stats_ema)
        assert result.count == 100  # 9000 / 90 = 100
        assert result.details["ema_bytes_per_line"] == 90.0

    def test_refine_estimate_with_sampling(self):
        """Test estimate refinement using tail sampling."""
        estimator = FileSizeEstimator()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            # Write 100 lines with approximately 80 bytes each
            for i in range(100):
                f.write(f"Test log entry {i:03d} with some content to make it longer\n")
            temp_path = Path(f.name)

        try:
            # Non-approximate estimate should be returned unchanged
            exact_estimate = EntryCountEstimate(100, False, "exact", {})
            result = estimator.refine_estimate_with_sampling(temp_path, 8000, exact_estimate)
            assert result == exact_estimate

            # Approximate estimate should be refined
            approx_estimate = EntryCountEstimate(50, True, "basic", {})
            result = estimator.refine_estimate_with_sampling(temp_path, temp_path.stat().st_size, approx_estimate)

            assert result is not None
            assert result.method in ["tail", "full_tail", "basic+tail"]
            assert result.count > 0
            assert "tail_sample_bytes" in result.details
            assert "refined_bytes_per_line" in result.details

        finally:
            temp_path.unlink()

        # Non-existent file should return None
        result = estimator.refine_estimate_with_sampling(
            Path("/non/existent/file.log"), 8000, approx_estimate
        )
        assert result is None

    def test_compute_bytes_per_line(self):
        """Test bytes-per-line computation."""
        estimator = FileSizeEstimator()

        # Valid inputs
        result = estimator.compute_bytes_per_line(8000, 100)
        assert result == 80.0

        # Zero values
        result = estimator.compute_bytes_per_line(0, 100)
        assert result is None

        result = estimator.compute_bytes_per_line(8000, 0)
        assert result is None

        # None values
        result = estimator.compute_bytes_per_line(None, 100)
        assert result is None

        result = estimator.compute_bytes_per_line(8000, None)
        assert result is None

        # Value outside bounds should be clamped
        result = estimator.compute_bytes_per_line(100000, 100)  # 1000 BPL, above max
        assert result == estimator.max_bytes_per_line


class TestThresholdEstimator:
    """Test ThresholdEstimator class."""

    def test_compute_estimation_band(self):
        """Test estimation band calculation."""
        estimator = ThresholdEstimator()

        # No threshold
        result = estimator.compute_estimation_band(None)
        assert result is None

        # Normal threshold
        result = estimator.compute_estimation_band(1000)
        expected = max(int(1000 * estimator.ESTIMATION_BAND_RATIO), estimator.ESTIMATION_BAND_MIN)
        assert result == expected

        # Small threshold
        result = estimator.compute_estimation_band(100)
        assert result >= estimator.ESTIMATION_BAND_MIN

    def test_classify_estimate(self):
        """Test estimate classification."""
        estimator = ThresholdEstimator()

        # No band
        result = estimator.classify_estimate(150, 100, None)
        assert result == "above_threshold"

        result = estimator.classify_estimate(50, 100, None)
        assert result == "below_threshold"

        # With band
        band = 50
        result = estimator.classify_estimate(150, 100, band)
        assert result == "well_above_threshold"

        result = estimator.classify_estimate(80, 100, band)
        assert result == "near_threshold"

        result = estimator.classify_estimate(30, 100, band)
        assert result == "well_below_threshold"


class TestPaginationCalculator:
    """Test PaginationCalculator class."""

    def test_create_pagination_info(self):
        """Test pagination info creation."""
        calc = PaginationCalculator()

        # First page
        result = calc.create_pagination_info(1, 50, 150)
        assert result.page == 1
        assert result.page_size == 50
        assert result.total_count == 150
        assert result.has_next is True
        assert result.has_prev is False

        # Middle page
        result = calc.create_pagination_info(2, 50, 150)
        assert result.has_next is True
        assert result.has_prev is True

        # Last page
        result = calc.create_pagination_info(3, 50, 150)
        assert result.has_next is False
        assert result.has_prev is True

        # Single page
        result = calc.create_pagination_info(1, 50, 30)
        assert result.has_next is False
        assert result.has_prev is False

    def test_calculate_pagination_indices(self):
        """Test pagination index calculation."""
        calc = PaginationCalculator()

        # First page
        start, end = calc.calculate_pagination_indices(1, 50, 150)
        assert start == 0
        assert end == 50

        # Middle page
        start, end = calc.calculate_pagination_indices(2, 50, 150)
        assert start == 50
        assert end == 100

        # Last page (partial)
        start, end = calc.calculate_pagination_indices(3, 50, 120)
        assert start == 100
        assert end == 120

    def test_calculate_total_pages(self):
        """Test total pages calculation."""
        calc = PaginationCalculator()

        # Exact division
        result = calc.calculate_total_pages(100, 50)
        assert result == 2

        # Partial last page
        result = calc.calculate_total_pages(120, 50)
        assert result == 3

        # Zero items
        result = calc.calculate_total_pages(0, 50)
        assert result == 1

        # Single item
        result = calc.calculate_total_pages(1, 50)
        assert result == 1


class TestBulkProcessingCalculator:
    """Test BulkProcessingCalculator class."""

    def test_calculate_chunks(self):
        """Test chunk calculation."""
        calc = BulkProcessingCalculator()

        # Exact division
        result = calc.calculate_chunks(100, 50)
        assert result.total_items == 100
        assert result.chunk_size == 50
        assert result.total_chunks == 2
        assert result.remaining_items == 0

        # Partial last chunk
        result = calc.calculate_chunks(120, 50)
        assert result.total_chunks == 3
        assert result.remaining_items == 20

        # Single item chunks
        result = calc.calculate_chunks(5, 10)
        assert result.total_chunks == 1
        assert result.remaining_items == 5

        # Zero chunk size
        result = calc.calculate_chunks(100, 0)
        assert result.total_chunks == 1
        assert result.remaining_items == 100

    def test_calculate_optimal_chunk_size(self):
        """Test optimal chunk size calculation."""
        calc = BulkProcessingCalculator()

        # Small total items
        result = calc.calculate_optimal_chunk_size(5)
        assert result == 5

        # Normal case
        result = calc.calculate_optimal_chunk_size(100)
        assert result == 25  # 100 / 4 target chunks

        # Large total items
        result = calc.calculate_optimal_chunk_size(1000)
        assert result == 100  # hits max_chunk_size limit

        # Custom parameters
        result = calc.calculate_optimal_chunk_size(
            200, target_chunks=5, min_chunk_size=20, max_chunk_size=60
        )
        assert result == 40  # 200 / 5 = 40


class TestTokenEstimator:
    """Test TokenEstimator class."""

    def test_estimate_tokens_string(self):
        """Test token estimation for strings."""
        estimator = TokenEstimator()

        # Short string
        result = estimator.estimate_tokens("Hello world")
        assert result > 0
        assert isinstance(result, int)

        # Empty string
        result = estimator.estimate_tokens("")
        assert result == 0

        # Long string
        long_text = "word " * 100
        result = estimator.estimate_tokens(long_text)
        assert result > 0

    def test_estimate_tokens_dict_list(self):
        """Test token estimation for dictionaries and lists."""
        estimator = TokenEstimator()

        # Dictionary
        data = {"key1": "value1", "key2": "value2"}
        result = estimator.estimate_tokens(data)
        assert result > 0

        # List
        data = ["item1", "item2", "item3"]
        result = estimator.estimate_tokens(data)
        assert result > 0

        # Complex structure
        data = {"nested": {"list": [1, 2, 3]}}
        result = estimator.estimate_tokens(data)
        assert result > 0

    def test_estimate_response_tokens(self):
        """Test token estimation for response data."""
        estimator = TokenEstimator()

        entries = [
            {"message": "First message", "timestamp": "2023-01-01"},
            {"message": "Second message", "timestamp": "2023-01-02"}
        ]

        # With metadata
        result = estimator.estimate_response_tokens(entries, include_metadata=True)
        assert result > 0

        # Without metadata
        result = estimator.estimate_response_tokens(entries, include_metadata=False)
        assert result > 0

        # Empty list
        result = estimator.estimate_response_tokens([])
        assert result == 0


@pytest.mark.core
@pytest.mark.regression
class TestMetricsTokenEstimator:
    """Permanent guards for lazy token metrics estimation and utility exports."""

    def test_construction_and_cheap_estimation_are_encoder_and_filesystem_free(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        import_calls = []

        def fail_import(name):
            import_calls.append(name)
            raise AssertionError("cheap estimation must not import tiktoken")

        monkeypatch.setattr(token_utils.importlib, "import_module", fail_import)

        estimator = MetricsTokenEstimator()
        assert estimator.encoder is None
        assert estimator.estimate_tokens_cheap("abcdefgh") == 2
        assert estimator.estimate_tokens({"key": "value"}, exact=False) == (
            len(token_utils.json.dumps({"key": "value"})) // 4
        )
        assert estimator.estimate_tokens([1, 2, 3], exact=False) == (
            len(token_utils.json.dumps([1, 2, 3])) // 4
        )
        assert import_calls == []
        assert not (tmp_path / ".scribe_metrics").exists()

    def test_exact_estimation_initializes_one_reusable_encoder(self, monkeypatch):
        monkeypatch.setattr(token_utils, "TIKTOKEN_AVAILABLE", None)

        class FakeEncoder:
            name = "fake"
            n_vocab = 100
            max_token_value = 99

            @staticmethod
            def encode(value):
                return value.split()

        encoder = FakeEncoder()
        calls = {"import": 0, "model": 0}

        def encoding_for_model(model):
            calls["model"] += 1
            assert model == "gpt-4"
            return encoder

        fake_tiktoken = SimpleNamespace(
            encoding_for_model=encoding_for_model,
            get_encoding=lambda name: pytest.fail(f"unexpected fallback: {name}"),
        )

        def import_module(name):
            calls["import"] += 1
            assert name == "tiktoken"
            return fake_tiktoken

        monkeypatch.setattr(token_utils.importlib, "import_module", import_module)
        estimator = MetricsTokenEstimator()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(estimator.estimate_tokens, ["one two"] * 16))

        assert results == [2] * 16
        assert estimator.encoder is encoder
        assert estimator.estimate_tokens("three four") == 2
        assert estimator.encoder is encoder
        assert calls == {"import": 1, "model": 1}

    def test_exact_estimation_preserves_unknown_model_and_import_fallbacks(
        self, monkeypatch
    ):
        monkeypatch.setattr(token_utils, "TIKTOKEN_AVAILABLE", None)
        fallback_encoder = SimpleNamespace(encode=lambda value: [value])
        fallback_calls = []
        fake_tiktoken = SimpleNamespace(
            encoding_for_model=lambda model: (_ for _ in ()).throw(KeyError(model)),
            get_encoding=lambda name: fallback_calls.append(name) or fallback_encoder,
        )
        monkeypatch.setattr(
            token_utils.importlib,
            "import_module",
            lambda name: fake_tiktoken,
        )

        unknown_model = MetricsTokenEstimator(model="unknown-model")
        assert unknown_model.estimate_tokens("value") == 1
        assert fallback_calls == ["cl100k_base"]

        unavailable = MetricsTokenEstimator()
        monkeypatch.setattr(
            token_utils.importlib,
            "import_module",
            lambda name: (_ for _ in ()).throw(ImportError(name)),
        )
        assert unavailable.estimate_tokens("abcdefgh") == 2
        assert unavailable.encoder is None

    def test_metrics_persistence_and_result_shapes_remain_compatible(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        estimator = MetricsTokenEstimator()
        estimator.metrics_history.append(TokenMetrics("probe", 1, 2, 3))

        assert not estimator.metrics_dir.exists()
        estimator.save_metrics()
        assert estimator.metrics_file.exists()

        restored = MetricsTokenEstimator()
        restored.load_metrics()
        assert [metric.total_tokens for metric in restored.metrics_history] == [3]
        assert set(restored.get_usage_stats()) == {
            "total_operations",
            "total_tokens_used",
            "average_tokens_per_operation",
            "compact_mode_average",
            "full_mode_average",
            "recent_average",
            "compact_savings",
            "daily_usage",
            "daily_limit",
            "operation_limit",
            "model",
            "tiktoken_available",
        }

    def test_utils_package_defers_export_modules_until_attribute_access(self):
        script = """
import json
import sys
import scribe_mcp.utils as utils

deferred = {
    "scribe_mcp.utils.files",
    "scribe_mcp.utils.slug",
    "scribe_mcp.utils.time",
    "scribe_mcp.utils.response",
    "scribe_mcp.utils.tokens",
}
assert deferred.isdisjoint(sys.modules)
assert callable(utils.append_line)
assert "scribe_mcp.utils.files" in sys.modules
assert "scribe_mcp.utils.response" not in sys.modules
assert "scribe_mcp.utils.tokens" not in sys.modules
print(json.dumps(utils.__all__))
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert token_utils.json.loads(result.stdout) == [
            "append_line",
            "ensure_parent",
            "read_tail",
            "rotate_file",
            "slugify_project_name",
            "slugify_filename",
            "format_utc",
            "utcnow",
            "ResponseFormatter",
            "default_formatter",
            "create_pagination_info",
            "PaginationInfo",
            "TokenEstimator",
            "TokenMetrics",
            "TokenBudget",
            "token_estimator",
        ]


class TestEstimatorUtilities:
    """Test EstimatorUtilities high-level interface."""

    def test_utilities_initialization(self):
        """Test EstimatorUtilities initialization."""
        utilities = EstimatorUtilities()

        assert isinstance(utilities.file_size, FileSizeEstimator)
        assert isinstance(utilities.threshold, ThresholdEstimator)
        assert isinstance(utilities.pagination, PaginationCalculator)
        assert isinstance(utilities.bulk, BulkProcessingCalculator)
        assert isinstance(utilities.tokens, TokenEstimator)

    def test_estimate_file_operations_nonexistent(self):
        """Test file operation estimation for non-existent file."""
        utilities = EstimatorUtilities()

        result = utilities.estimate_file_operations(Path("/non/existent/file.log"))

        assert result["exists"] is False
        assert result["size_bytes"] == 0
        assert result["entry_estimate"].method == "file_not_found"
        assert result["entry_estimate"].count == 0

    def test_estimate_file_operations_existing(self):
        """Test file operation estimation for existing file."""
        utilities = EstimatorUtilities()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            # Write 50 lines
            for i in range(50):
                f.write(f"Test log entry {i:03d}\n")
            temp_path = Path(f.name)

        try:
            result = utilities.estimate_file_operations(temp_path)

            assert result["exists"] is True
            assert result["size_bytes"] > 0
            assert result["size_mb"] > 0
            assert result["mtime_ns"] > 0

            # Check estimates
            assert isinstance(result["entry_estimate"], EntryCountEstimate)
            assert isinstance(result["basic_estimate"], EntryCountEstimate)
            assert isinstance(result["cached_estimate"], EntryCountEstimate)

            # Entry count should be reasonable (around 50)
            assert 1 <= result["entry_estimate"].count <= 200

        finally:
            temp_path.unlink()

    def test_estimate_file_operations_with_cache(self):
        """Test file operation estimation with cache."""
        utilities = EstimatorUtilities()

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for i in range(30):
                f.write(f"Cached entry {i:03d}\n")
            temp_path = Path(f.name)

        try:
            file_stat = temp_path.stat()
            cache_stats = {
                "size_bytes": file_stat.st_size,
                "mtime_ns": file_stat.st_mtime_ns,
                "line_count": 30,
                "source": "test_cache"
            }

            result = utilities.estimate_file_operations(temp_path, cache_stats)

            # Should use cache
            assert result["cached_estimate"].method == "cache"
            assert result["cached_estimate"].approximate is False
            assert result["cached_estimate"].count == 30

        finally:
            temp_path.unlink()


class TestIntegration:
    """Integration tests for estimator utilities."""

    def test_end_to_end_estimation_workflow(self):
        """Test complete estimation workflow."""
        utilities = EstimatorUtilities()

        # Create test data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            for i in range(75):
                f.write(f"Integration test entry {i:03d} with varying content lengths\n")
            temp_path = Path(f.name)

        try:
            # File operations estimation
            file_result = utilities.estimate_file_operations(temp_path)

            # Threshold estimation
            threshold = 50
            band = utilities.threshold.compute_estimation_band(threshold)
            classification = utilities.threshold.classify_estimate(
                file_result["entry_estimate"].count, threshold, band
            )

            # Pagination calculation
            total_items = file_result["entry_estimate"].count
            page_size = 20
            pagination_info = utilities.pagination.create_pagination_info(
                1, page_size, total_items
            )

            # Bulk processing calculation
            chunk_calc = utilities.bulk.calculate_chunks(total_items, 25)

            # Token estimation
            sample_entries = [
                {"message": f"Entry {i}", "timestamp": "2023-01-01"}
                for i in range(min(10, total_items))
            ]
            token_estimate = utilities.tokens.estimate_response_tokens(sample_entries)

            # Verify all components work together
            assert file_result["exists"] is True
            assert file_result["entry_estimate"].count > 0
            assert isinstance(band, int)
            assert classification in ["well_above_threshold", "near_threshold", "well_below_threshold"]
            assert isinstance(pagination_info, PaginationInfo)
            assert isinstance(chunk_calc, ChunkCalculation)
            assert token_estimate > 0

            # Verify consistency
            assert total_items == file_result["entry_estimate"].count
            assert pagination_info.total_count == total_items
            assert chunk_calc.total_items == total_items

        finally:
            temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__])
