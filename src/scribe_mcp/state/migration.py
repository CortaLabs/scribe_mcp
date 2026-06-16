"""Legacy state-file to DB migration utilities."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from scribe_mcp.config.settings import settings
from scribe_mcp.utils.time import parse_utc, utcnow


logger = logging.getLogger(__name__)

_GLOBAL_AGENT_ID = "Scribe"
_LEGACY_MIGRATION_SESSION_ID = "__legacy_state_migration__"


@dataclass(frozen=True)
class LegacyStateMigrationResult:
    migrated: bool
    projects_migrated: int
    session_projects_migrated: int
    session_modes_migrated: int
    renamed_to: Optional[str]
    message: str


def _extract_project_name(
    fallback_name: str,
    payload: Optional[Dict[str, Any]],
) -> Optional[str]:
    if isinstance(payload, dict) and payload.get("name"):
        candidate = str(payload["name"]).strip()
        if candidate:
            return candidate
    candidate = str(fallback_name or "").strip()
    return candidate or None


def _normalise_project_payload(
    *,
    project_name: str,
    payload: Optional[Dict[str, Any]],
    default_root: Path,
) -> Dict[str, Any]:
    data = dict(payload or {})
    data.setdefault("name", project_name)

    root = data.get("root") or data.get("repo_root") or str(default_root)
    progress_log = data.get("progress_log")
    if not progress_log:
        progress_log = str(
            settings.project_root
            / settings.dev_plans_base
            / project_name
            / "PROGRESS_LOG.md"
        )

    docs = data.get("docs")
    docs_json = json.dumps(docs) if isinstance(docs, dict) else None

    return {
        "name": project_name,
        "root": str(root),
        "progress_log": str(progress_log),
        "docs_json": docs_json,
    }


def _coerce_mode(value: Any) -> Optional[str]:
    candidate = str(value or "").strip().lower()
    if candidate in {"project", "sentinel"}:
        return candidate
    return None


def _coerce_iso_timestamp(value: Any) -> str:
    if isinstance(value, str):
        parsed = parse_utc(value)
        if parsed is not None:
            return parsed.isoformat()
    return utcnow().isoformat()


def _rename_migrated_source(state_path: Path) -> Path:
    target = state_path.with_suffix(state_path.suffix + ".migrated")
    if target.exists():
        suffix = utcnow().strftime("%Y%m%d%H%M%S")
        target = state_path.with_suffix(state_path.suffix + f".migrated.{suffix}")
    state_path.replace(target)
    return target


async def migrate_legacy_state_file(
    *,
    storage_backend: Any,
    state_path: Path,
    rename_source: bool = True,
) -> LegacyStateMigrationResult:
    """Migrate legacy state payload into DB tables via storage abstraction methods."""
    source = Path(state_path).expanduser()
    if not source.exists():
        return LegacyStateMigrationResult(
            migrated=False,
            projects_migrated=0,
            session_projects_migrated=0,
            session_modes_migrated=0,
            renamed_to=None,
            message="No legacy state file found; nothing to migrate.",
        )

    setup_fn = getattr(storage_backend, "setup", None)
    if callable(setup_fn):
        await setup_fn()

    try:
        raw_data = source.read_text(encoding="utf-8")
        payload = json.loads(raw_data)
    except (OSError, json.JSONDecodeError) as exc:
        return LegacyStateMigrationResult(
            migrated=False,
            projects_migrated=0,
            session_projects_migrated=0,
            session_modes_migrated=0,
            renamed_to=None,
            message=f"Failed to parse legacy state payload: {exc}",
        )

    if not isinstance(payload, dict):
        return LegacyStateMigrationResult(
            migrated=False,
            projects_migrated=0,
            session_projects_migrated=0,
            session_modes_migrated=0,
            renamed_to=None,
            message="Legacy state payload must be a JSON object.",
        )

    projects_migrated = 0
    session_projects_migrated = 0
    session_modes_migrated = 0
    default_root = source.parent

    legacy_projects = payload.get("projects") if isinstance(payload.get("projects"), dict) else {}
    for key, value in legacy_projects.items():
        if not isinstance(value, dict):
            value = {}
        project_name = _extract_project_name(str(key), value)
        if not project_name:
            continue

        normalised = _normalise_project_payload(
            project_name=project_name,
            payload=value,
            default_root=default_root,
        )

        await storage_backend.upsert_project(
            name=normalised["name"],
            repo_root=normalised["root"],
            progress_log_path=normalised["progress_log"],
            docs_json=normalised["docs_json"],
        )
        projects_migrated += 1

    current_project = payload.get("current_project")
    if current_project is not None:
        current_name = str(current_project).strip()
        if current_name:
            if hasattr(storage_backend, "upsert_agent_session"):
                await storage_backend.upsert_agent_session(
                    agent_id=_GLOBAL_AGENT_ID,
                    session_id=_LEGACY_MIGRATION_SESSION_ID,
                    metadata={"source": "legacy_state"},
                )

            # Ensure the synthetic migration session row exists in scribe_sessions
            # before binding a project to it — the FK constraint requires this.
            if hasattr(storage_backend, "upsert_session"):
                await storage_backend.upsert_session(
                    session_id=_LEGACY_MIGRATION_SESSION_ID,
                    mode="project",
                )

            if hasattr(storage_backend, "set_agent_project"):
                await storage_backend.set_agent_project(
                    agent_id=_GLOBAL_AGENT_ID,
                    project_name=current_name,
                    expected_version=None,
                    updated_by="migration",
                    session_id=_LEGACY_MIGRATION_SESSION_ID,
                )

            if hasattr(storage_backend, "set_session_project"):
                await storage_backend.set_session_project(_LEGACY_MIGRATION_SESSION_ID, current_name)

            if hasattr(storage_backend, "upsert_agent_recent_project"):
                await storage_backend.upsert_agent_recent_project(_GLOBAL_AGENT_ID, current_name)

    legacy_session_projects = payload.get("session_projects") if isinstance(payload.get("session_projects"), dict) else {}
    for session_id_raw, project_payload in legacy_session_projects.items():
        session_id = str(session_id_raw).strip()
        if not session_id:
            continue

        project_name = None
        project_dict: Dict[str, Any] = {}
        if isinstance(project_payload, dict):
            project_dict = dict(project_payload)
            project_name = _extract_project_name(session_id, project_dict)
        elif project_payload is not None:
            project_name = str(project_payload).strip() or None

        if not project_name:
            continue

        normalised = _normalise_project_payload(
            project_name=project_name,
            payload=project_dict,
            default_root=default_root,
        )

        await storage_backend.upsert_project(
            name=normalised["name"],
            repo_root=normalised["root"],
            progress_log_path=normalised["progress_log"],
            docs_json=normalised["docs_json"],
        )

        # Ensure the session row exists in scribe_sessions before binding a project
        # to it — the FK constraint on session_projects requires this ordering.
        if hasattr(storage_backend, "upsert_session"):
            await storage_backend.upsert_session(session_id=session_id, mode="project")
        if hasattr(storage_backend, "set_session_project"):
            await storage_backend.set_session_project(session_id, project_name)

        session_projects_migrated += 1

    legacy_session_modes = payload.get("session_modes") if isinstance(payload.get("session_modes"), dict) else {}
    for session_id_raw, mode_raw in legacy_session_modes.items():
        session_id = str(session_id_raw).strip()
        mode = _coerce_mode(mode_raw)
        if not session_id or not mode:
            continue

        if hasattr(storage_backend, "upsert_session"):
            await storage_backend.upsert_session(session_id=session_id, mode=mode)
        if hasattr(storage_backend, "set_session_mode"):
            await storage_backend.set_session_mode(session_id, mode)
        session_modes_migrated += 1

    # Preserve recent tool timeline best-effort under migration session.
    recent_tools = payload.get("recent_tools")
    if isinstance(recent_tools, list) and hasattr(storage_backend, "update_session_activity"):
        if hasattr(storage_backend, "upsert_agent_session"):
            await storage_backend.upsert_agent_session(
                agent_id=_GLOBAL_AGENT_ID,
                session_id=_LEGACY_MIGRATION_SESSION_ID,
                metadata={"source": "legacy_state_tools"},
            )

        for tool_entry in reversed(recent_tools):
            if isinstance(tool_entry, dict):
                tool_name = str(tool_entry.get("name") or "").strip()
                tool_ts = _coerce_iso_timestamp(tool_entry.get("ts"))
            else:
                tool_name = str(tool_entry).strip()
                tool_ts = utcnow().isoformat()

            if not tool_name:
                continue
            try:
                await storage_backend.update_session_activity(
                    session_id=_LEGACY_MIGRATION_SESSION_ID,
                    tool_name=tool_name,
                    timestamp=tool_ts,
                )
            except Exception:
                logger.debug("Skipping tool activity migration for '%s'", tool_name)

    renamed_to = None
    if rename_source:
        renamed_to = str(_rename_migrated_source(source))

    return LegacyStateMigrationResult(
        migrated=True,
        projects_migrated=projects_migrated,
        session_projects_migrated=session_projects_migrated,
        session_modes_migrated=session_modes_migrated,
        renamed_to=renamed_to,
        message="Legacy state migrated successfully.",
    )
