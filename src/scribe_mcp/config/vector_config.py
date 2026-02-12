"""Vector indexing configuration management.

This module handles loading vector configuration from JSON files in the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class VectorConfig:
    """Vector indexing configuration loaded from JSON file."""
    enabled: bool = True
    backend: str = "faiss"
    dimension: int = 384
    model: str = "all-MiniLM-L6-v2"
    gpu: bool = False
    queue_max: int = 1024
    batch_size: int = 32
    # Performance tuning
    max_retries: int = 3
    retry_backoff_factor: float = 2.0
    queue_timeout_seconds: int = 1
    # Model settings
    model_device: str = "auto"  # "auto", "cpu", "cuda", "mps"
    cache_size: int = 1000  # Number of cached embeddings
    # Index settings
    index_type: str = "IndexFlatIP"  # FAISS index type
    metric: str = "cosine"  # "cosine" or "euclidean"
    # Thresholds
    min_similarity_threshold: float = 0.0
    search_k_limit: int = 100  # Maximum results per search

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorConfig":
        """Create VectorConfig from dictionary."""
        return cls(**data)

    @classmethod
    def from_file(cls, config_path: Path) -> Optional["VectorConfig"]:
        """Load VectorConfig from JSON file."""
        if not config_path.exists():
            return None

        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load vector config from {config_path}: {e}")
            return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert VectorConfig to dictionary."""
        return {
            "enabled": self.enabled,
            "backend": self.backend,
            "dimension": self.dimension,
            "model": self.model,
            "gpu": self.gpu,
            "queue_max": self.queue_max,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "retry_backoff_factor": self.retry_backoff_factor,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "model_device": self.model_device,
            "cache_size": self.cache_size,
            "index_type": self.index_type,
            "metric": self.metric,
            "min_similarity_threshold": self.min_similarity_threshold,
            "search_k_limit": self.search_k_limit
        }

    def save_to_file(self, config_path: Path) -> bool:
        """Save VectorConfig to JSON file."""
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write
            temp_path = config_path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            temp_path.rename(config_path)
            return True
        except (PermissionError, OSError) as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save vector config to {config_path}: {e}")
            return False

    @classmethod
    def create_default(cls, config_path: Path) -> "VectorConfig":
        """Create and save default configuration file."""
        default_config = cls()
        default_config.save_to_file(config_path)
        return default_config


def load_vector_config(repo_root: Optional[Path] = None) -> VectorConfig:
    """Load vector configuration from repository.

    Args:
        repo_root: Repository root path. If None, tries to detect automatically.

    Returns:
        VectorConfig instance with loaded or default values.
    """
    if repo_root is None:
        repo_root = _detect_repo_root()

    if repo_root is None:
        # Fallback to defaults
        return VectorConfig()

    # Look for config file in several locations
    config_paths = [
        repo_root / ".scribe" / "vector.json",
        repo_root / "vector.json",
        repo_root / ".scribe_vectors" / "vector.json"
    ]

    for config_path in config_paths:
        config = VectorConfig.from_file(config_path)
        if config is not None:
            return merge_with_env_overrides(config)

    # Create default config if none found
    default_path = repo_root / ".scribe_vectors" / "vector.json"
    default_config = VectorConfig.create_default(default_path)
    import logging
    logging.getLogger(__name__).info(f"Created default vector config at {default_path}")
    return merge_with_env_overrides(default_config)


def _detect_repo_root() -> Optional[Path]:
    """Try to detect repository root from current working directory."""
    current = Path.cwd()

    # Look for indicators of being in a Scribe repository
    indicators = [
        ".scribe",
        "config",
        "plugins",
        "docs/dev_plans"
    ]

    # Search up the directory tree
    path = current
    max_depth = 10  # Prevent infinite loops

    for _ in range(max_depth):
        # Check if any indicator exists
        if any((path / indicator).exists() for indicator in indicators):
            return path

        # Check if we've hit the root directory
        parent = path.parent
        if parent == path:
            break
        path = parent

    return None


def merge_with_env_overrides(config: VectorConfig) -> VectorConfig:
    """Merge configuration with environment variable overrides.

    Environment variables take precedence over file configuration.
    """
    import os

    env_overrides = {}

    # Map environment variables to config fields
    env_mapping = {
        'SCRIBE_VECTOR_ENABLED': ('enabled', lambda x: x.lower() in ['true', '1', 'yes']),
        'SCRIBE_VECTOR_BACKEND': ('backend', str),
        'SCRIBE_VECTOR_DIMENSION': ('dimension', int),
        'SCRIBE_VECTOR_MODEL': ('model', str),
        'SCRIBE_VECTOR_GPU': ('gpu', lambda x: x.lower() in ['true', '1', 'yes']),
        'SCRIBE_VECTOR_QUEUE_MAX': ('queue_max', int),
        'SCRIBE_VECTOR_BATCH_SIZE': ('batch_size', int),
        'SCRIBE_VECTOR_MODEL_DEVICE': ('model_device', str),
        'SCRIBE_VECTOR_CACHE_SIZE': ('cache_size', int),
        'SCRIBE_VECTOR_INDEX_TYPE': ('index_type', str),
        'SCRIBE_VECTOR_METRIC': ('metric', str),
        'SCRIBE_VECTOR_MIN_SIMILARITY': ('min_similarity_threshold', float),
        'SCRIBE_VECTOR_SEARCH_K_LIMIT': ('search_k_limit', int),
    }

    for env_var, (field, converter) in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                env_overrides[field] = converter(value)
            except (ValueError, TypeError):
                import logging
                logging.getLogger(__name__).warning(f"Invalid value for {env_var}: {value}")

    # Create merged config
    merged_data = config.to_dict()
    merged_data.update(env_overrides)

    return VectorConfig.from_dict(merged_data)
