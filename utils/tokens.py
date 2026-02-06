#!/usr/bin/env python3
"""
Token estimation and metrics utilities.

Provides accurate token counting using tiktoken, usage tracking,
and budget management for response optimization.
"""

import json
import logging
import time
import os
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path

# Try to import tiktoken, fall back to basic estimation if not available
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    import warnings
    warnings.warn("tiktoken not available, using basic token estimation. Install with: pip install tiktoken")


@dataclass
class TokenMetrics:
    """Token usage metrics for a single operation."""
    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    timestamp: float = field(default_factory=time.time)
    compact_mode: bool = False
    page_size: int = 0
    response_compressed: bool = False


@dataclass
class TokenBudget:
    """Token budget configuration and tracking."""
    daily_limit: int
    operation_limit: int
    warning_threshold: float = 0.8  # Warn at 80% of limit
    current_daily_usage: int = 0
    current_operation_count: int = 0
    last_reset_time: float = field(default_factory=time.time)

    def should_warn(self, tokens: int) -> bool:
        """Check if token usage should trigger warning."""
        return (tokens / self.operation_limit) >= self.warning_threshold

    def is_over_limit(self, tokens: int) -> bool:
        """Check if tokens exceed operation limit."""
        return tokens > self.operation_limit

    def needs_daily_reset(self) -> bool:
        """Check if daily counter needs reset (24h cycle)."""
        hours_since_reset = (time.time() - self.last_reset_time) / 3600
        return hours_since_reset >= 24

    def reset_daily(self):
        """Reset daily usage counter."""
        self.current_daily_usage = 0
        self.last_reset_time = time.time()


class TokenEstimator:
    """Token estimation and budget management using tiktoken for accuracy."""

    def __init__(self, model: str = "gpt-4", daily_limit: int = 100000, operation_limit: int = 8000):
        self.model = model
        self.budget = self._load_budget_config(daily_limit, operation_limit)
        self.metrics_history: list[TokenMetrics] = []
        self.max_history_size = 1000

        # Initialize tiktoken encoder
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoder = tiktoken.encoding_for_model(model)
            except KeyError:
                # Fallback to cl100k_base (GPT-4) if model not found
                self.encoder = tiktoken.get_encoding("cl100k_base")
        else:
            self.encoder = None

        # Create metrics directory if needed
        self.metrics_dir = Path.home() / ".scribe_metrics"
        self.metrics_dir.mkdir(exist_ok=True)
        self.metrics_file = self.metrics_dir / "token_usage.json"

    def _load_budget_config(self, daily_limit: int = 100000, operation_limit: int = 8000) -> TokenBudget:
        """Load token budget configuration from environment or parameters."""
        daily_limit_env = int(os.getenv("SCRIBE_TOKEN_DAILY_LIMIT", daily_limit))
        operation_limit_env = int(os.getenv("SCRIBE_TOKEN_OPERATION_LIMIT", operation_limit))
        warning_threshold = float(os.getenv("SCRIBE_TOKEN_WARNING_THRESHOLD", "0.8"))

        return TokenBudget(
            daily_limit=daily_limit_env,
            operation_limit=operation_limit_env,
            warning_threshold=warning_threshold
        )

    def estimate_tokens(self, data: Union[str, Dict, List, Any]) -> int:
        """
        Estimate token count for various data types using tiktoken.

        Args:
            data: The data to estimate tokens for

        Returns:
            Estimated token count
        """
        if self.encoder is not None:
            # Use tiktoken for accurate counting
            if isinstance(data, str):
                return len(self.encoder.encode(data))
            elif isinstance(data, (dict, list)):
                # Convert to JSON string and count tokens
                json_str = json.dumps(data, ensure_ascii=False)
                return len(self.encoder.encode(json_str))
            else:
                # Convert to string and count tokens
                return len(self.encoder.encode(str(data)))
        else:
            # Fallback to basic estimation if tiktoken not available
            # Rough approximation: 1 token ≈ 4 characters for English text
            if isinstance(data, str):
                return len(data) // 4
            elif isinstance(data, (dict, list)):
                return len(json.dumps(data)) // 4
            else:
                return len(str(data)) // 4

    def estimate_response_tokens(self, response: Dict[str, Any]) -> Dict[str, int]:
        """
        Estimate tokens for different parts of a response.

        Returns breakdown by section (entries, pagination, metadata, etc.).
        """
        breakdown = {}

        # Main response structure overhead
        base_overhead = self.estimate_tokens({"ok": True, "count": 0})
        breakdown["base"] = base_overhead

        # Entries section
        if "entries" in response:
            entries_tokens = self.estimate_tokens(response["entries"])
            breakdown["entries"] = entries_tokens

        # Pagination section
        if "pagination" in response:
            pagination_tokens = self.estimate_tokens(response["pagination"])
            breakdown["pagination"] = pagination_tokens

        # Other metadata (reminders, warnings, etc.)
        other_tokens = 0
        for key, value in response.items():
            if key not in ["ok", "entries", "pagination", "count"]:
                other_tokens += self.estimate_tokens({key: value})
        breakdown["metadata"] = other_tokens

        # Total
        breakdown["total"] = sum(breakdown.values())

        return breakdown

    def record_operation(self, operation: str, input_data: Any, response: Dict[str, Any],
                        compact_mode: bool = False, page_size: int = 0) -> TokenMetrics:
        """
        Record token usage for an operation.

        Args:
            operation: Name of the operation (tool name)
            input_data: Input parameters/data
            response: Response data
            compact_mode: Whether compact mode was used
            page_size: Page size if paginated

        Returns:
            TokenMetrics for the operation
        """
        input_tokens = self.estimate_tokens(input_data)
        response_breakdown = self.estimate_response_tokens(response)
        output_tokens = response_breakdown["total"]
        total_tokens = input_tokens + output_tokens

        metrics = TokenMetrics(
            operation=operation,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            compact_mode=compact_mode,
            page_size=page_size,
            response_compressed=response.get("_compressed", False)
        )

        # Store metrics
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.max_history_size:
            self.metrics_history.pop(0)

        # Update budget tracking
        if self.budget.needs_daily_reset():
            self.budget.reset_daily()
        self.budget.current_daily_usage += total_tokens
        self.budget.current_operation_count += 1

        # Log warning if needed
        if self.budget.should_warn(total_tokens):
            logger.warning("Token Warning: %s used %d tokens (%.1f%% of limit)",
                           operation, total_tokens, total_tokens / self.budget.operation_limit * 100)

        # Log if over limit
        if self.budget.is_over_limit(total_tokens):
            logger.warning("Token Limit Exceeded: %s used %d tokens (limit: %d)",
                           operation, total_tokens, self.budget.operation_limit)

        return metrics

    def get_optimization_suggestion(self, operation: str, tokens: int,
                                  compact_mode: bool = False) -> Optional[str]:
        """
        Get optimization suggestion based on token usage pattern.
        """
        if tokens < 1000:
            return None

        suggestions = []

        # High token usage suggestions
        if tokens > 5000:
            if not compact_mode:
                savings = int(tokens * 0.7)  # 70% savings with compact mode
                suggestions.append(f"Use compact=True to save ~{savings} tokens")

            # Check if pagination would help
            if "query" in operation or "read" in operation:
                suggestions.append("Use smaller page_size to reduce tokens per request")

        # Context-specific suggestions
        if "query_entries" in operation and tokens > 3000:
            suggestions.append("Consider adding date range filters to limit results")

        if "read_recent" in operation and tokens > 2000:
            suggestions.append("Use smaller 'n' parameter or add field selection")

        return " | ".join(suggestions) if suggestions else None

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current token usage statistics."""
        if not self.metrics_history:
            return {"message": "No operations recorded yet"}

        # Calculate stats
        total_operations = len(self.metrics_history)
        total_tokens = sum(m.total_tokens for m in self.metrics_history)
        avg_tokens = total_tokens / total_operations

        compact_operations = [m for m in self.metrics_history if m.compact_mode]
        compact_avg = (sum(m.total_tokens for m in compact_operations) /
                      len(compact_operations)) if compact_operations else 0

        full_operations = [m for m in self.metrics_history if not m.compact_mode]
        full_avg = (sum(m.total_tokens for m in full_operations) /
                   len(full_operations)) if full_operations else 0

        # Recent trend (last 10 operations)
        recent = self.metrics_history[-10:]
        recent_avg = sum(m.total_tokens for m in recent) / len(recent) if recent else 0

        stats = {
            "total_operations": total_operations,
            "total_tokens_used": total_tokens,
            "average_tokens_per_operation": int(avg_tokens),
            "compact_mode_average": int(compact_avg),
            "full_mode_average": int(full_avg),
            "recent_average": int(recent_avg),
            "compact_savings": f"{((full_avg - compact_avg) / full_avg * 100):.1f}%" if full_avg > 0 else "N/A",
            "daily_usage": self.budget.current_daily_usage,
            "daily_limit": self.budget.daily_limit,
            "operation_limit": self.budget.operation_limit,
            "model": self.model,
            "tiktoken_available": TIKTOKEN_AVAILABLE
        }

        # Add tiktoken info if available
        if TIKTOKEN_AVAILABLE and self.encoder:
            stats["tokenizer"] = {
                "name": self.encoder.name,
                "vocab_size": self.encoder.n_vocab
            }

        return stats

    def get_tokenizer_info(self) -> Dict[str, Any]:
        """Get information about the tokenizer being used."""
        if not TIKTOKEN_AVAILABLE:
            return {
                "available": False,
                "message": "tiktoken not available. Install with: pip install tiktoken"
            }

        if not self.encoder:
            return {
                "available": True,
                "initialized": False,
                "message": "Tokenizer failed to initialize"
            }

        return {
            "available": True,
            "initialized": True,
            "name": self.encoder.name,
            "model": self.model,
            "vocab_size": self.encoder.n_vocab,
            "max_token_value": self.encoder.max_token_value
        }

    def save_metrics(self):
        """Save metrics history to file."""
        try:
            metrics_data = []
            for m in self.metrics_history:
                metrics_data.append({
                    "operation": m.operation,
                    "input_tokens": m.input_tokens,
                    "output_tokens": m.output_tokens,
                    "total_tokens": m.total_tokens,
                    "timestamp": m.timestamp,
                    "compact_mode": m.compact_mode,
                    "page_size": m.page_size,
                    "response_compressed": m.response_compressed
                })

            with open(self.metrics_file, 'w') as f:
                json.dump(metrics_data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save metrics: %s", e)

    def load_metrics(self):
        """Load metrics history from file."""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r') as f:
                    metrics_data = json.load(f)

                self.metrics_history = []
                for data in metrics_data:
                    self.metrics_history.append(TokenMetrics(**data))
        except Exception as e:
            logger.warning("Failed to load metrics: %s", e)


# Global estimator instance
token_estimator = TokenEstimator()