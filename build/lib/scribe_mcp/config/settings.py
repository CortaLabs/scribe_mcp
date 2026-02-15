"""Runtime configuration helpers for the Scribe MCP server."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from scribe_mcp.config.paths import default_db_path, repo_root

try:  # Prefer optional dotenv loading to keep env setup simple outside the repo
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()  # best-effort; safe no-op if .env missing
except Exception:
    pass


def _load_env_json(name: str) -> Dict[str, Any]:
    """Return JSON data from the environment when available."""
    raw = os.environ.get(name)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for the MCP server."""

    project_root: Path
    default_state_path: Path
    db_url: Optional[str]
    storage_backend: str
    sqlite_path: Path
    allow_network: bool
    mcp_server_name: str
    extra_options: Dict[str, Any]
    recent_projects_limit: int
    log_rate_limit_count: int
    log_rate_limit_window: int
    log_max_bytes: int
    storage_timeout_seconds: float
    retention_days: int
    reminder_defaults: Dict[str, Any]
    reminder_idle_minutes: int
    reminder_warmup_minutes: int
    dev_plans_base: Path
    # Vector indexing settings
    vector_enabled: bool
    vector_backend: str
    vector_dimension: int
    vector_model: str
    vector_gpu: bool
    vector_queue_max: int
    vector_batch_size: int
    # Token optimization settings
    default_page_size: int
    max_page_size: int
    default_compact_mode: bool
    token_warning_threshold: int
    token_daily_limit: int
    token_operation_limit: int
    token_warning_threshold_percent: float
    default_field_selection: List[str]
    tokenizer_model: str
    # Reminder system feature flags
    use_db_cooldown_tracking: bool
    use_session_aware_hashes: bool
    require_explicit_root: bool

    @classmethod
    def load(cls) -> "Settings":
        project_root = Path(os.environ.get("SCRIBE_ROOT", _default_root())).resolve()
        env_state_path = os.environ.get("SCRIBE_STATE_PATH")
        if env_state_path:
            state_path = Path(env_state_path).expanduser()
        else:
            state_path = (project_root / ".scribe" / "state.json").resolve()

        db_url = os.environ.get("SCRIBE_DB_URL")
        storage_backend = os.environ.get("SCRIBE_STORAGE_BACKEND")
        if storage_backend:
            storage_backend = storage_backend.lower()
        else:
            storage_backend = "postgres" if db_url else "sqlite"

        sqlite_override = os.environ.get("SCRIBE_DB_PATH") or os.environ.get(
            "SCRIBE_SQLITE_PATH"
        )
        if sqlite_override:
            sqlite_path = Path(sqlite_override).expanduser()
        else:
            sqlite_path = default_db_path()

        allow_network = os.environ.get("SCRIBE_ALLOW_NETWORK", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        mcp_server_name = os.environ.get("SCRIBE_MCP_NAME", "scribe.mcp")

        extra_options = _load_env_json("SCRIBE_EXTRA_OPTIONS")
        recent_limit_raw = os.environ.get("SCRIBE_RECENT_PROJECT_LIMIT", "5")
        try:
            recent_limit = max(1, int(recent_limit_raw))
        except ValueError:
            recent_limit = 5

        log_rate_limit_count = max(0, _int_env("SCRIBE_LOG_RATE_LIMIT_COUNT", 0))
        log_rate_limit_window = max(0, _int_env("SCRIBE_LOG_RATE_LIMIT_WINDOW", 60))
        log_max_bytes = max(0, _int_env("SCRIBE_LOG_MAX_BYTES", 512 * 1024))
        storage_timeout_seconds = max(0.1, float(os.environ.get("SCRIBE_STORAGE_TIMEOUT_SECONDS", "5")))
        retention_days = max(1, _int_env("SCRIBE_RETENTION_DAYS", 90))
        reminder_defaults = _load_env_json("SCRIBE_REMINDER_DEFAULTS")
        reminder_idle_minutes = max(1, _int_env("SCRIBE_REMINDER_IDLE_MINUTES", 45))
        reminder_warmup_minutes = max(0, _int_env("SCRIBE_REMINDER_WARMUP_MINUTES", 5))

        dev_plans_base_raw = os.environ.get("SCRIBE_DEV_PLANS_BASE", ".scribe/docs/dev_plans")
        dev_plans_base = Path(dev_plans_base_raw).expanduser()
        if dev_plans_base.is_absolute():
            # Treat as a relative-to-repo path by stripping the anchor.
            # This keeps the setting repo-scoped even if an absolute was provided.
            dev_plans_base = Path(*dev_plans_base.parts[1:])

        # Vector indexing configuration
        from .vector_config import load_vector_config, merge_with_env_overrides

        vector_config = load_vector_config(project_root)
        vector_config = merge_with_env_overrides(vector_config)

        vector_enabled = vector_config.enabled
        vector_backend = vector_config.backend
        vector_dimension = max(1, vector_config.dimension)
        vector_model = vector_config.model
        vector_gpu = vector_config.gpu
        vector_queue_max = max(1, vector_config.queue_max)
        vector_batch_size = max(1, vector_config.batch_size)

        # Token optimization configuration
        default_page_size = max(1, _int_env("SCRIBE_DEFAULT_PAGE_SIZE", 50))
        max_page_size = max(1, _int_env("SCRIBE_MAX_PAGE_SIZE", 100))
        default_compact_mode = os.environ.get("SCRIBE_DEFAULT_COMPACT_MODE", "false").lower() in {
            "1", "true", "yes"
        }
        token_warning_threshold = max(100, _int_env("SCRIBE_TOKEN_WARNING_THRESHOLD", 4000))
        token_daily_limit = max(1000, _int_env("SCRIBE_TOKEN_DAILY_LIMIT", 100000))
        token_operation_limit = max(100, _int_env("SCRIBE_TOKEN_OPERATION_LIMIT", 8000))
        token_warning_threshold_percent = max(0.1, min(1.0,
            float(os.environ.get("SCRIBE_TOKEN_WARNING_THRESHOLD_PERCENT", "0.8"))
        ))

        # Default field selection for compact mode
        default_fields_raw = os.environ.get("SCRIBE_DEFAULT_FIELD_SELECTION",
            "id,message,timestamp,emoji,agent")
        default_field_selection = [field.strip() for field in default_fields_raw.split(",") if field.strip()]

        # Tokenizer model
        tokenizer_model = os.environ.get("SCRIBE_TOKENIZER_MODEL", "gpt-4")

        # Reminder system feature flags (default OFF for backward compatibility)
        use_db_cooldown_tracking = os.environ.get("SCRIBE_REMINDER_USE_DB", "false").lower() in {
            "1", "true", "yes"
        }
        use_session_aware_hashes = os.environ.get("SCRIBE_REMINDER_SESSION_HASH", "false").lower() in {
            "1", "true", "yes"
        }
        require_explicit_root = os.environ.get("SCRIBE_REQUIRE_EXPLICIT_ROOT", "true").lower() in {
            "1", "true", "yes"
        }

        return cls(
            project_root=project_root,
            default_state_path=state_path,
            db_url=db_url,
            storage_backend=storage_backend,
            sqlite_path=sqlite_path,
            allow_network=allow_network,
            mcp_server_name=mcp_server_name,
            extra_options=extra_options,
            recent_projects_limit=recent_limit,
            log_rate_limit_count=log_rate_limit_count,
            log_rate_limit_window=log_rate_limit_window,
            log_max_bytes=log_max_bytes,
            storage_timeout_seconds=storage_timeout_seconds,
            retention_days=retention_days,
            reminder_defaults=reminder_defaults,
            reminder_idle_minutes=reminder_idle_minutes,
            reminder_warmup_minutes=reminder_warmup_minutes,
            dev_plans_base=dev_plans_base,
            vector_enabled=vector_enabled,
            vector_backend=vector_backend,
            vector_dimension=vector_dimension,
            vector_model=vector_model,
            vector_gpu=vector_gpu,
            vector_queue_max=vector_queue_max,
            vector_batch_size=vector_batch_size,
            default_page_size=default_page_size,
            max_page_size=max_page_size,
            default_compact_mode=default_compact_mode,
            token_warning_threshold=token_warning_threshold,
            token_daily_limit=token_daily_limit,
            token_operation_limit=token_operation_limit,
            token_warning_threshold_percent=token_warning_threshold_percent,
            default_field_selection=default_field_selection,
            tokenizer_model=tokenizer_model,
            use_db_cooldown_tracking=use_db_cooldown_tracking,
            use_session_aware_hashes=use_session_aware_hashes,
            require_explicit_root=require_explicit_root,
        )


def _default_root() -> str:
    """Infer repository root without relying on module-path traversal hacks."""
    return str(repo_root())


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


settings = Settings.load()
