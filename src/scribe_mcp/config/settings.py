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

    # Load defaults from repo root .env regardless of working directory, but
    # never override explicitly exported environment variables.
    _dotenv_path = repo_root() / ".env"
    load_dotenv(_dotenv_path, override=False)
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


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _optional_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value is not None:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


@dataclass(frozen=True)
class SettingsContractEntry:
    """Public classification for a supported Scribe environment variable."""

    name: str
    classification: str
    scope: str
    description: str
    canonical_name: Optional[str] = None


PUBLIC_STORAGE_MODES: tuple[str, ...] = ("sqlite", "postgres", "remote/client")

PUBLIC_STORAGE_SETTINGS_CONTRACT: tuple[SettingsContractEntry, ...] = (
    SettingsContractEntry(
        name="SCRIBE_STORAGE_BACKEND",
        classification="canonical",
        scope="runtime",
        description="Select `sqlite` for local standalone storage or `postgres` for direct database/server mode.",
    ),
    SettingsContractEntry(
        name="SCRIBE_DB_URL",
        classification="canonical",
        scope="runtime",
        description="Direct Postgres connection string for the public server/runtime contract.",
    ),
    SettingsContractEntry(
        name="SCRIBE_DB_PATH",
        classification="canonical",
        scope="runtime",
        description="Optional SQLite database path override. If unset, Scribe uses the portable default_db_path().",
    ),
    SettingsContractEntry(
        name="SCRIBE_SQLITE_PATH",
        classification="compatibility",
        scope="runtime",
        description="Compatibility alias for `SCRIBE_DB_PATH`.",
        canonical_name="SCRIBE_DB_PATH",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_SCHEMA",
        classification="canonical",
        scope="runtime",
        description="Schema namespace for direct Postgres/server mode.",
    ),
    SettingsContractEntry(
        name="SCRIBE_DB_SCHEMA",
        classification="compatibility",
        scope="runtime",
        description="Compatibility alias for `SCRIBE_POSTGRES_SCHEMA`.",
        canonical_name="SCRIBE_POSTGRES_SCHEMA",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_POOL_MIN_SIZE",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres pooling control for minimum open connections.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_POOL_MAX_SIZE",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres pooling control for maximum open connections.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres command timeout override.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres connection timeout override.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_CONNECT_RETRIES",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres retry count for transient connection failures.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_CONNECT_RETRY_BACKOFF_SECONDS",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres retry backoff between connection attempts.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_MAX_INACTIVE_SECONDS",
        classification="advanced/public",
        scope="runtime",
        description="Advanced Postgres pool setting for max inactive connection lifetime.",
    ),
    SettingsContractEntry(
        name="SCRIBE_MODE",
        classification="canonical",
        scope="runtime",
        description="Operating mode selector. Use `client` to explicitly select the public remote/client contract.",
    ),
    SettingsContractEntry(
        name="SCRIBE_REMOTE_URL",
        classification="canonical",
        scope="runtime",
        description="Remote Scribe server base URL for client mode.",
    ),
    SettingsContractEntry(
        name="SCRIBE_REMOTE_AUTH_TOKEN",
        classification="canonical",
        scope="runtime",
        description="Client auth token for remote/client mode; falls back to the server-side transport token names for single-environment deployments.",
    ),
    SettingsContractEntry(
        name="SCRIBE_REMOTE_CONNECT_TIMEOUT",
        classification="advanced/public",
        scope="runtime",
        description="Advanced remote/client timeout override in seconds.",
    ),
    SettingsContractEntry(
        name="SCRIBE_REMOTE_FALLBACK",
        classification="advanced/public",
        scope="runtime",
        description="Advanced remote/client toggle controlling fallback to standalone when the remote is unavailable.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_ADMIN_*",
        classification="bootstrap-only",
        scope="bootstrap-only",
        description="Bootstrap convenience variables used by `scribe bootstrap` for admin/setup connections.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_APP_*",
        classification="bootstrap-only",
        scope="bootstrap-only",
        description="Bootstrap convenience variables used by `scribe bootstrap` when provisioning the runtime app role/user.",
    ),
    SettingsContractEntry(
        name="SCRIBE_POSTGRES_SUPERUSER_*",
        classification="bootstrap-only",
        scope="bootstrap-only",
        description="Bootstrap convenience variables used only when Postgres setup needs elevated/superuser access.",
    ),
)

PUBLIC_STORAGE_SETTINGS_BY_NAME = {
    entry.name: entry for entry in PUBLIC_STORAGE_SETTINGS_CONTRACT
}


@dataclass(frozen=True)
class Settings:
    """Resolved configuration for the MCP server."""

    project_root: Path
    default_state_path: Path
    db_url: Optional[str]
    storage_backend: str
    sqlite_path: Path
    postgres_schema: str
    postgres_pool_min_size: int
    postgres_pool_max_size: int
    postgres_command_timeout_seconds: float
    postgres_connect_timeout_seconds: float
    postgres_max_inactive_connection_lifetime_seconds: float
    postgres_connect_retries: int
    postgres_connect_retry_backoff_seconds: float
    allow_network: bool
    transport_host: str
    transport_port: int
    transport_auth_token: Optional[str]
    allow_outside_repo_reads: bool
    force_disable_outside_repo_reads: bool
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
    # Object store settings
    object_store_url: Optional[str]
    object_store_provider: str
    object_store_key: Optional[str]
    object_store_project: Optional[str]
    object_store_timeout: float
    s3_bucket: Optional[str]
    s3_prefix: str
    s3_region: str
    # Client/server mode detection
    mode: str  # "auto", "server", "client", "standalone"
    remote_server_url: Optional[str]
    remote_auth_token: Optional[str]
    remote_connect_timeout: float
    remote_fallback: bool

    def resolve_outside_repo_read_policy(
        self,
        transport_policy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve the canonical outside-repo read posture for the active runtime."""
        policy = transport_policy if isinstance(transport_policy, dict) else {}
        transport = str(policy.get("transport") or "stdio").strip().lower() or "stdio"
        bind_host = str(policy.get("bind_host") or self.transport_host).strip() or self.transport_host
        network_exposed = bool(policy.get("network_exposed", False))
        auth_required = bool(policy.get("auth_required", transport == "sse"))
        auth_configured = bool(
            policy.get("auth_configured", bool(self.transport_auth_token))
        )
        force_enabled = bool(policy.get("allow_outside_repo_reads", False))
        trusted_runtime = transport == "stdio" or (
            transport == "sse"
            and not network_exposed
            and auth_required
            and auth_configured
        )
        return {
            "transport": transport,
            "bind_host": bind_host,
            "network_exposed": network_exposed,
            "auth_required": auth_required,
            "auth_configured": auth_configured,
            "trusted_runtime": trusted_runtime,
            "default_allowed": trusted_runtime,
            "force_enabled": force_enabled,
            "force_disabled": self.force_disable_outside_repo_reads,
            "enabled": (
                False
                if self.force_disable_outside_repo_reads
                else bool(trusted_runtime or force_enabled)
            ),
        }

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

        # Backward-compatible SQLite path support:
        # - SCRIBE_DB_PATH is canonical
        # - SCRIBE_SQLITE_PATH is accepted for downstream compatibility
        sqlite_override = os.environ.get("SCRIBE_DB_PATH") or os.environ.get(
            "SCRIBE_SQLITE_PATH"
        )
        if sqlite_override:
            sqlite_path = Path(sqlite_override).expanduser()
        else:
            sqlite_path = default_db_path()

        # Backward-compatible alias support:
        # - SCRIBE_POSTGRES_SCHEMA is canonical
        # - SCRIBE_DB_SCHEMA is accepted for downstream compatibility
        postgres_schema = (
            os.environ.get("SCRIBE_POSTGRES_SCHEMA")
            or os.environ.get("SCRIBE_DB_SCHEMA")
            or "scribe"
        ).strip() or "scribe"
        postgres_pool_min_size = max(1, _int_env("SCRIBE_POSTGRES_POOL_MIN_SIZE", 2))
        postgres_pool_max_size = max(postgres_pool_min_size, _int_env("SCRIBE_POSTGRES_POOL_MAX_SIZE", 20))
        postgres_command_timeout_seconds = max(
            1.0,
            float(os.environ.get("SCRIBE_POSTGRES_COMMAND_TIMEOUT_SECONDS", "30")),
        )
        postgres_connect_timeout_seconds = max(
            1.0,
            float(os.environ.get("SCRIBE_POSTGRES_CONNECT_TIMEOUT_SECONDS", "10")),
        )
        postgres_max_inactive_connection_lifetime_seconds = max(
            1.0,
            float(os.environ.get("SCRIBE_POSTGRES_MAX_INACTIVE_SECONDS", "300")),
        )
        postgres_connect_retries = max(0, _int_env("SCRIBE_POSTGRES_CONNECT_RETRIES", 3))
        postgres_connect_retry_backoff_seconds = max(
            0.1,
            float(os.environ.get("SCRIBE_POSTGRES_CONNECT_RETRY_BACKOFF_SECONDS", "1.0")),
        )

        allow_network = _bool_env("SCRIBE_ALLOW_NETWORK", False)
        transport_host = os.environ.get("SCRIBE_TRANSPORT_HOST", "127.0.0.1").strip() or "127.0.0.1"
        transport_port = max(1, _int_env("SCRIBE_TRANSPORT_PORT", 8200))
        transport_auth_token = _optional_env("SCRIBE_TRANSPORT_AUTH_TOKEN", "SCRIBE_AUTH_TOKEN")
        allow_outside_repo_reads = _bool_env(
            "SCRIBE_ALLOW_OUTSIDE_REPO_READS",
            _bool_env("SCRIBE_ALLOW_CROSS_REPO_READS", False),
        )
        force_disable_outside_repo_reads = _bool_env(
            "SCRIBE_FORCE_DISABLE_OUTSIDE_REPO_READS",
            _bool_env("SCRIBE_DISABLE_OUTSIDE_REPO_READS", False),
        )
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

        # Object store configuration
        object_store_url = os.environ.get("SCRIBE_OBJECT_STORE_URL")
        object_store_provider = os.environ.get("SCRIBE_OBJECT_STORE_PROVIDER", "corta")
        object_store_key = os.environ.get("SCRIBE_OBJECT_STORE_KEY")
        object_store_project = os.environ.get("SCRIBE_OBJECT_STORE_PROJECT")
        object_store_timeout = max(
            1.0,
            float(os.environ.get("SCRIBE_OBJECT_STORE_TIMEOUT", "10.0")),
        )
        s3_bucket = os.environ.get("SCRIBE_S3_BUCKET")
        s3_prefix = os.environ.get("SCRIBE_S3_PREFIX", "scribe/")
        s3_region = os.environ.get("SCRIBE_S3_REGION", "us-east-1")

        # Client/server mode detection
        mode = os.environ.get("SCRIBE_MODE", "auto").lower().strip()
        if mode not in ("auto", "server", "client", "standalone"):
            mode = "auto"
        remote_server_url = os.environ.get("SCRIBE_REMOTE_URL")  # standardized name per review
        remote_auth_token = _optional_env(
            "SCRIBE_REMOTE_AUTH_TOKEN",
            "SCRIBE_TRANSPORT_AUTH_TOKEN",
            "SCRIBE_AUTH_TOKEN",
        )
        remote_connect_timeout = max(
            0.5,
            float(os.environ.get("SCRIBE_REMOTE_CONNECT_TIMEOUT", "3.0")),
        )
        remote_fallback = os.environ.get("SCRIBE_REMOTE_FALLBACK", "true").lower() in {
            "1", "true", "yes"
        }

        return cls(
            project_root=project_root,
            default_state_path=state_path,
            db_url=db_url,
            storage_backend=storage_backend,
            sqlite_path=sqlite_path,
            postgres_schema=postgres_schema,
            postgres_pool_min_size=postgres_pool_min_size,
            postgres_pool_max_size=postgres_pool_max_size,
            postgres_command_timeout_seconds=postgres_command_timeout_seconds,
            postgres_connect_timeout_seconds=postgres_connect_timeout_seconds,
            postgres_max_inactive_connection_lifetime_seconds=postgres_max_inactive_connection_lifetime_seconds,
            postgres_connect_retries=postgres_connect_retries,
            postgres_connect_retry_backoff_seconds=postgres_connect_retry_backoff_seconds,
            allow_network=allow_network,
            transport_host=transport_host,
            transport_port=transport_port,
            transport_auth_token=transport_auth_token,
            allow_outside_repo_reads=allow_outside_repo_reads,
            force_disable_outside_repo_reads=force_disable_outside_repo_reads,
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
            object_store_url=object_store_url,
            object_store_provider=object_store_provider,
            object_store_key=object_store_key,
            object_store_project=object_store_project,
            object_store_timeout=object_store_timeout,
            s3_bucket=s3_bucket,
            s3_prefix=s3_prefix,
            s3_region=s3_region,
            mode=mode,
            remote_server_url=remote_server_url,
            remote_auth_token=remote_auth_token,
            remote_connect_timeout=remote_connect_timeout,
            remote_fallback=remote_fallback,
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
