"""Deprecated vector configuration compatibility shim for the slim core package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class VectorConfig:
    """Disabled vector configuration placeholder retained for import compatibility."""

    enabled: bool = False
    backend: str = "disabled"
    dimension: int = 0
    model: str = ""
    gpu: bool = False
    queue_max: int = 0
    batch_size: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorConfig":
        """Create a disabled VectorConfig from dictionary input."""
        return cls(
            enabled=bool(data.get("enabled", False)),
            backend=str(data.get("backend", "disabled")),
            dimension=int(data.get("dimension", 0) or 0),
            model=str(data.get("model", "")),
            gpu=bool(data.get("gpu", False)),
            queue_max=int(data.get("queue_max", 0) or 0),
            batch_size=int(data.get("batch_size", 0) or 0),
        )

    @classmethod
    def from_file(cls, config_path: Path) -> Optional["VectorConfig"]:
        """Return a disabled config only when the file exists."""
        if not config_path.exists():
            return None
        return cls()

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
        }

    def save_to_file(self, config_path: Path) -> bool:
        """Core no longer writes vector configuration artifacts."""
        _ = config_path
        return False

    @classmethod
    def create_default(cls, config_path: Path) -> "VectorConfig":
        """Return a disabled default config without writing artifacts."""
        _ = config_path
        return cls()


def load_vector_config(repo_root: Optional[Path] = None) -> VectorConfig:
    """Return a disabled vector configuration placeholder."""
    _ = repo_root
    return VectorConfig()


def _detect_repo_root() -> Optional[Path]:
    """Legacy helper retained for compatibility."""
    return None


def merge_with_env_overrides(config: VectorConfig) -> VectorConfig:
    """Return the provided disabled config unchanged."""
    return config
