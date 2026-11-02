#!/usr/bin/env python3
"""
Token estimation and metrics utilities.

Provides accurate token counting using tiktoken, usage tracking,
and budget management for response optimization.
"""

import importlib
import json
import logging
import time
import os
import threading
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from pathlib import Path

# Availability is unknown until the first exact request attempts the lazy import.
TIKTOKEN_AVAILABLE: Optional[bool] = None

# tiktoken 0.14.0 / 4e71bbe0c078468e00fefbf94b39849389f346e5.
# Recipe/data attribution and acquisition records: token_data/NOTICE.md.
# Fixed sizes, hashes and counts are independent of the runtime notice.
_TOKEN_RESOURCES = {
    "vocab.bpe": (456318, "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5", 50000),
    "encoder.json": (1042301, "196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783", 50257),
    "r50k_base.tiktoken": (835554, "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930", 50256),
    "p50k_base.tiktoken": (836186, "94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069", 50280),
    "cl100k_base.tiktoken": (1681126, "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7", 100256),
    "o200k_base.tiktoken": (3613922, "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d", 199998),
}
_R50K_PATTERN = r"""'(?:[sdmt]|ll|ve|re)| ?\p{L}++| ?\p{N}++| ?[^\s\p{L}\p{N}]++|\s++$|\s+(?!\S)|\s"""
_CL100K_PATTERN = r"""'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s"""
_O200K_PATTERN = "|".join([
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
    r"""\p{N}{1,3}""", r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""", r"""\s*[\r\n]+""", r"""\s+(?!\S)""", r"""\s+""",
])
_ALLOWED_SPECIAL_ID_ALIASES = {
    "o200k_harmony": {
        200018: frozenset({"<|endofprompt|>", "<|reserved_200018|>"}),
    },
}


def _token_recipe(encoding_name: str) -> dict:
    """Closed, lightweight port of the seven pinned native constructor recipes."""
    if encoding_name not in {"gpt2", "r50k_base", "p50k_base", "p50k_edit", "cl100k_base", "o200k_base", "o200k_harmony"}:
        raise ValueError(f"unsupported packaged encoding: {encoding_name!r}")
    pattern = _R50K_PATTERN
    # Keep pairs until validation: a dict would hide repeated special strings.
    specials = [("<|endoftext|>", 50256)]
    vocab = None
    if encoding_name in {"gpt2", "r50k_base", "p50k_base"}:
        vocab = 50281 if encoding_name == "p50k_base" else 50257
    elif encoding_name == "p50k_edit":
        specials.extend([("<|fim_prefix|>", 50281), ("<|fim_middle|>", 50282), ("<|fim_suffix|>", 50283)])
    elif encoding_name == "cl100k_base":
        pattern = _CL100K_PATTERN
        specials = [("<|endoftext|>", 100257), ("<|fim_prefix|>", 100258), ("<|fim_middle|>", 100259), ("<|fim_suffix|>", 100260), ("<|endofprompt|>", 100276)]
    elif encoding_name in {"o200k_base", "o200k_harmony"}:
        pattern = _O200K_PATTERN
        specials = [("<|endoftext|>", 199999), ("<|endofprompt|>", 200018)]
        if encoding_name == "o200k_harmony":
            specials.extend([
                ("<|startoftext|>", 199998), ("<|reserved_200000|>", 200000),
                ("<|reserved_200001|>", 200001), ("<|return|>", 200002),
                ("<|constrain|>", 200003), ("<|reserved_200004|>", 200004),
                ("<|channel|>", 200005), ("<|start|>", 200006), ("<|end|>", 200007),
                ("<|message|>", 200008), ("<|reserved_200009|>", 200009),
                ("<|reserved_200010|>", 200010), ("<|reserved_200011|>", 200011), ("<|call|>", 200012),
            ])
            specials.extend((f"<|reserved_{i}|>", i) for i in range(200013, 201088))
    recipe = {"name": encoding_name, "pat_str": pattern, "special_tokens": specials}
    if vocab is not None:
        recipe["explicit_n_vocab"] = vocab
    return recipe


def _read_token_resource(filename: str, encoding_name: str) -> bytes:
    """Read one bounded immutable buffer; verify it before any parser sees it."""
    from importlib.resources import files
    import hashlib

    expected_length, expected_hash, _ = _TOKEN_RESOURCES[filename]
    resource = files("scribe_mcp").joinpath("utils", "token_data", filename)
    try:
        with resource.open("rb") as stream:
            data = stream.read(expected_length + 1)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{encoding_name}: missing {filename}") from exc
    if len(data) != expected_length:
        raise ValueError(f"{encoding_name}: {filename}: length mismatch")
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError(f"{encoding_name}: {filename}: SHA256 mismatch")
    return data


def _parse_token_ranks(data: bytes, filename: str, encoding_name: str) -> dict[bytes, int]:
    import base64
    import binascii

    ranks = {}
    seen_ranks = set()
    for line_number, line in enumerate(data.splitlines(), 1):
        if not line:
            continue
        context = f"{encoding_name}: {filename}: line {line_number}"
        fields = line.split(b" ")
        if len(fields) != 2 or not fields[1].isascii() or not fields[1].isdigit():
            raise ValueError(f"{context}: malformed rank row")
        try:
            token = base64.b64decode(fields[0], validate=True)
            rank = int(fields[1])
        except (ValueError, binascii.Error) as exc:
            raise ValueError(f"{context}: invalid token or rank") from exc
        if not token or token in ranks or rank in seen_ranks:
            raise ValueError(f"{context}: empty or duplicate token/rank")
        ranks[token] = rank
        seen_ranks.add(rank)
    if not ranks or len(ranks) != _TOKEN_RESOURCES[filename][2]:
        raise ValueError(f"{encoding_name}: {filename}: rank count mismatch")
    return ranks


def _parse_gpt2_ranks(vocab_data: bytes, encoder_data: bytes) -> dict[bytes, int]:
    """Pure pinned data-gym conversion; never performs BPE or upstream I/O."""
    byte_order = [b for b in range(256) if chr(b).isprintable() and chr(b) != " "]
    byte_map = {chr(b): b for b in byte_order}
    extra = 0
    for b in range(256):
        if b not in byte_order:
            byte_map[chr(256 + extra)] = b
            byte_order.append(b)
            extra += 1

    def decode(value: str, filename: str) -> bytes:
        try:
            return bytes(byte_map[c] for c in value)
        except KeyError as exc:
            raise ValueError(f"gpt2: {filename}: unknown byte-unicode character") from exc

    try:
        lines = vocab_data.decode("utf-8", errors="strict").split("\n")
    except UnicodeDecodeError as exc:
        raise ValueError("gpt2: vocab.bpe: invalid UTF-8") from exc
    if not lines or lines[0] != "#version: 0.2" or lines[-1] != "":
        raise ValueError("gpt2: vocab.bpe: invalid header or final newline")
    ranks = {bytes([b]): i for i, b in enumerate(byte_order)}
    for line_number, line in enumerate(lines[1:-1], 2):
        fields = line.split(" ")
        if len(fields) != 2 or not all(fields):
            raise ValueError(f"gpt2: vocab.bpe: line {line_number}: malformed merge")
        first, second = (decode(value, "vocab.bpe") for value in fields)
        merged = first + second
        if first not in ranks or second not in ranks or merged in ranks:
            raise ValueError(f"gpt2: vocab.bpe: line {line_number}: invalid or duplicate merge")
        ranks[merged] = len(ranks)
    if len(ranks) != 256 + _TOKEN_RESOURCES["vocab.bpe"][2]:
        raise ValueError("gpt2: vocab.bpe: merge count mismatch")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("gpt2: encoder.json: duplicate JSON key")
            result[key] = value
        return result

    try:
        encoder = json.loads(encoder_data.decode("utf-8", errors="strict"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("gpt2: encoder.json: invalid UTF-8 or JSON") from exc
    if not isinstance(encoder, dict):
        raise ValueError("gpt2: encoder.json: expected object")
    decoded = {}
    ids = set()
    for key, value in encoder.items():
        if type(value) is not int or value < 0:
            raise ValueError("gpt2: encoder.json: invalid rank")
        token = decode(key, "encoder.json")
        if not token or token in decoded or value in ids:
            raise ValueError("gpt2: encoder.json: empty or duplicate token/rank")
        decoded[token] = value
        ids.add(value)
    if len(decoded) != _TOKEN_RESOURCES["encoder.json"][2]:
        raise ValueError("gpt2: encoder.json: token count mismatch")
    decoded.pop(b"<|endoftext|>", None)
    decoded.pop(b"<|startoftext|>", None)
    if ranks != decoded:
        raise ValueError("gpt2: vocab.bpe/encoder.json: merge/JSON consistency mismatch")
    return ranks


def _validate_token_recipe(recipe: dict, ranks: dict[bytes, int]) -> None:
    name = recipe["name"]
    filename = "vocab.bpe/encoder.json" if name == "gpt2" else {"p50k_edit": "p50k_base", "o200k_harmony": "o200k_base"}.get(name, name) + ".tiktoken"
    context = f"{name}: {filename}: ranks/specials"
    if not ranks or any(not isinstance(k, bytes) or not k or type(v) is not int or v < 0 for k, v in ranks.items()):
        raise ValueError(f"{context}: invalid rank table")
    rank_ids = set(ranks.values())
    pairs = recipe["special_tokens"]
    if len(rank_ids) != len(ranks) or any(not isinstance(k, str) or not k or type(v) is not int or v < 0 for k, v in pairs):
        raise ValueError(f"{context}: invalid or duplicate ranks/specials")
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError(f"{context}: duplicate special string")
    # This grouping validates aliases; it never selects a canonical spelling
    # or implements decoding for an ambiguous ID.
    strings_by_id = {}
    for key, value in pairs:
        strings_by_id.setdefault(value, set()).add(key)
    aliases = {value: keys for value, keys in strings_by_id.items() if len(keys) > 1}
    if aliases != _ALLOWED_SPECIAL_ID_ALIASES.get(name, {}):
        raise ValueError(f"{context}: special ID alias mismatch")
    specials = dict(pairs)
    special_ids = set(strings_by_id)
    if name == "o200k_harmony" and (
        len(specials) != 1091 or len(special_ids) != 1090
        or special_ids != set(range(199998, 201088))
        or specials.get("<|endofprompt|>") != 200018
        or specials.get("<|reserved_200018|>") != 200018
    ):
        raise ValueError(f"{context}: harmony special shape mismatch")
    if rank_ids & special_ids:
        raise ValueError(f"{context}: colliding special/rank IDs")
    vocab = recipe.get("explicit_n_vocab")
    if vocab is not None and (len(ranks) + len(special_ids) != vocab or max(rank_ids | special_ids) != vocab - 1):
        raise ValueError(f"{context}: explicit vocabulary mismatch")
    recipe["special_tokens"] = specials


def _load_packaged_encoder(encoding_name: str, tiktoken_module):
    """Construct only the pinned native engine from verified package resources."""
    if getattr(tiktoken_module, "__version__", None) != "0.14.0":
        raise RuntimeError(f"{encoding_name}: packaged resources require tiktoken==0.14.0")
    recipe = _token_recipe(encoding_name)
    if encoding_name == "gpt2":
        vocab_data = _read_token_resource("vocab.bpe", encoding_name)
        encoder_data = _read_token_resource("encoder.json", encoding_name)
        ranks = _parse_gpt2_ranks(vocab_data, encoder_data)
    else:
        base = {"p50k_edit": "p50k_base", "o200k_harmony": "o200k_base"}.get(encoding_name, encoding_name)
        filename = base + ".tiktoken"
        ranks = _parse_token_ranks(_read_token_resource(filename, encoding_name), filename, encoding_name)
    _validate_token_recipe(recipe, ranks)
    return tiktoken_module.Encoding(mergeable_ranks=ranks, **recipe)


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

        self.encoder = None
        self._encoder_initialized = False
        self._encoder_lock = threading.Lock()

        self.metrics_dir = Path.home() / ".scribe_metrics"
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

    def _get_encoder(self) -> Optional[Any]:
        """Initialize and cache the model encoder on the first exact request."""
        global TIKTOKEN_AVAILABLE

        if self._encoder_initialized:
            return self.encoder

        with self._encoder_lock:
            if self._encoder_initialized:
                return self.encoder

            try:
                tiktoken = importlib.import_module("tiktoken")
            except ImportError:
                TIKTOKEN_AVAILABLE = False
                self.encoder = None
                self._encoder_initialized = True
                return None

            TIKTOKEN_AVAILABLE = True
            if getattr(tiktoken, "__version__", None) != "0.14.0":
                raise RuntimeError(f"{self.model}: packaged resources require tiktoken==0.14.0")
            try:
                encoding_name = tiktoken.encoding_name_for_model(self.model)
            except KeyError:
                encoding_name = "cl100k_base"
            self.encoder = _load_packaged_encoder(encoding_name, tiktoken)

            # Cache only a completed initialization or the supported import fallback.
            # Unexpected failures must propagate and leave later exact calls retryable.
            self._encoder_initialized = True

        return self.encoder

    @staticmethod
    def estimate_tokens_cheap(data: Union[str, Dict, List, Any]) -> int:
        """Estimate tokens deterministically without importing tiktoken."""
        if isinstance(data, str):
            serialized = data
        elif isinstance(data, (dict, list)):
            serialized = json.dumps(data)
        else:
            serialized = str(data)
        return len(serialized) // 4

    def estimate_tokens(self, data: Union[str, Dict, List, Any], *, exact: bool = True) -> int:
        """
        Estimate token count for various data types using tiktoken.

        Args:
            data: The data to estimate tokens for

        Returns:
            Estimated token count
        """
        if not exact:
            return self.estimate_tokens_cheap(data)

        encoder = self._get_encoder()
        if encoder is not None:
            # Use tiktoken for accurate counting
            if isinstance(data, str):
                return len(encoder.encode(data))
            elif isinstance(data, (dict, list)):
                # Convert to JSON string and count tokens
                json_str = json.dumps(data, ensure_ascii=False)
                return len(encoder.encode(json_str))
            else:
                # Convert to string and count tokens
                return len(encoder.encode(str(data)))

        return self.estimate_tokens_cheap(data)

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
            "tiktoken_available": TIKTOKEN_AVAILABLE is not False
        }

        # Add tiktoken info if available
        if self.encoder is not None:
            stats["tokenizer"] = {
                "name": self.encoder.name,
                "vocab_size": self.encoder.n_vocab
            }

        return stats

    def get_tokenizer_info(self) -> Dict[str, Any]:
        """Get information about the tokenizer being used."""
        encoder = self._get_encoder()
        if encoder is None:
            return {
                "available": False,
                "message": "tiktoken not available. Install with: pip install tiktoken"
            }

        return {
            "available": True,
            "initialized": True,
            "name": encoder.name,
            "model": self.model,
            "vocab_size": encoder.n_vocab,
            "max_token_value": encoder.max_token_value
        }

    def save_metrics(self):
        """Save metrics history to file."""
        try:
            self.metrics_dir.mkdir(exist_ok=True)
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
