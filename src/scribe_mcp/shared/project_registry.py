from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import sqlite3

from scribe_mcp.config.settings import settings
from scribe_mcp.storage.models import ProjectRecord

_DOC_KEY_ALIASES: Dict[str, str] = {
    "architecture_guide": "architecture",
    "architecture-guide": "architecture",
    "phaseplan": "phase_plan",
}

_CORE_DOC_CANONICAL_KEYS = {"architecture", "phase_plan", "checklist"}


def _float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _canonical_doc_key(doc: str) -> str:
    normalized = str(doc or "").strip().lower().replace(".md", "")
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return _DOC_KEY_ALIASES.get(normalized, normalized)


@dataclass
class ProjectInfo:
    """High-level view of a project's registry state.

    This is a logical view, not a 1:1 mapping to any single table.
    Fields are computed from `scribe_projects`, `scribe_metrics`,
    and dev plan tables where available.
    """

    project_slug: str
    project_name: str
    description: Optional[str]
    status: str
    created_at: Optional[datetime]
    last_entry_at: Optional[datetime]
    last_access_at: Optional[datetime]
    last_status_change: Optional[datetime]
    total_entries: int
    total_files: int
    total_phases: int
    tags: List[str]
    meta: Dict[str, Any]


class ProjectRegistry:
    """SQLite-first Project Registry helper.

    For v1 this helper focuses on the SQLite backend defined by
    `settings.sqlite_path`. The SQL is written to remain portable
    so that a future Postgres implementation can mirror behaviour.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path or settings.sqlite_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._timeout_seconds = _float_env("SCRIBE_REGISTRY_DB_TIMEOUT_SECONDS", 1.5, 0.1)
        self._busy_timeout_ms = _int_env("SCRIBE_REGISTRY_DB_BUSY_TIMEOUT_MS", 500, 10)
        self._ensure_schema()

    def _connect(self, *, row_factory: bool = False) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path,
            timeout=self._timeout_seconds,
            check_same_thread=False,
        )
        if row_factory:
            conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms};")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_project(
        self,
        project: ProjectRecord,
        *,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Ensure registry row exists for this project.

        SQLiteStorage already guarantees a scribe_projects row; here we
        opportunistically backfill new registry-focused columns.
        """
        tags_str = ",".join(sorted(set(tags))) if tags else None
        meta_str = None
        if meta:
            # Store as a simple JSON string; avoid importing json at top-level
            import json

            meta_str = json.dumps(meta, separators=(",", ":"), sort_keys=True)

        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scribe_projects
                SET
                    description = COALESCE(description, ?),
                    tags = COALESCE(tags, ?),
                    meta = COALESCE(meta, ?),
                    last_access_at = COALESCE(last_access_at, ?)
                WHERE name = ?
                """,
                (description, tags_str, meta_str, now, project.name),
            )

    def touch_access(self, project_name: str) -> None:
        """Update last_access_at when a project is (re)selected."""
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                "UPDATE scribe_projects SET last_access_at = ? WHERE name = ?",
                (now, project_name),
            )

    def touch_entry(self, project_name: str, log_type: Optional[str] = None) -> None:
        """Update last_entry_at when we write logs/docs.

        Also applies soft lifecycle rules:
        - If status == 'planning'
        - AND core dev_plan docs exist (architecture, phase_plan, checklist)
        - AND at least one *progress* log entry has been written
        → auto-promote to 'in_progress' and set last_status_change.
        """
        now = self._now_iso()
        normalized_log_type = (log_type or "progress").lower()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE scribe_projects SET last_entry_at = ? WHERE name = ?",
                (now, project_name),
            )

            # Fetch project id + current status for lifecycle checks
            cursor.execute(
                "SELECT id, COALESCE(status, 'planning') FROM scribe_projects WHERE name = ?",
                (project_name,),
            )
            row = cursor.fetchone()
            if not row:
                conn.commit()
                return

            project_id, status = row

            if status == "planning":
                # Check for core dev_plan docs: architecture, phase_plan, checklist
                try:
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM dev_plans
                        WHERE project_id = ?
                          AND plan_type IN ('architecture', 'phase_plan', 'checklist')
                        """,
                        (project_id,),
                    )
                    docs_count = cursor.fetchone()[0] or 0
                except sqlite3.Error:
                    docs_count = 0

                if docs_count < 3:
                    conn.commit()
                    return

                # Only auto-promote on progress log writes; other log types
                # (e.g., doc_updates) still update last_entry_at but do not
                # change lifecycle state.
                if normalized_log_type != "progress":
                    conn.commit()
                    return

                # All conditions met; promote planning -> in_progress
                cursor.execute(
                    """
                    UPDATE scribe_projects
                    SET status = 'in_progress',
                        last_status_change = ?
                    WHERE id = ?
                    """,
                    (now, project_id),
                )
                conn.commit()
                return

            if status != "in_progress":
                conn.commit()
                return

            if normalized_log_type != "progress":
                conn.commit()
                return

            # Check latest progress log metadata for completion signals.
            try:
                cursor.execute(
                    """
                    SELECT meta FROM scribe_entries
                    WHERE project_id = ?
                    ORDER BY ts_iso DESC, created_at DESC
                    LIMIT 1
                    """,
                    (project_id,),
                )
                entry_row = cursor.fetchone()
            except sqlite3.Error:
                entry_row = None

            if not entry_row or not entry_row[0]:
                conn.commit()
                return

            try:
                import json

                entry_meta = json.loads(entry_row[0])
            except Exception:
                entry_meta = {}

            final_grade = entry_meta.get("final_grade")
            approval_status = entry_meta.get("approval_status")
            project_status = entry_meta.get("project_status")

            grade_ok = False
            if final_grade is not None:
                try:
                    grade_ok = float(final_grade) >= 93.0
                except (TypeError, ValueError):
                    grade_ok = False

            approval_ok = (
                isinstance(approval_status, str)
                and approval_status.strip().upper() == "APPROVED"
            )
            project_status_ok = (
                isinstance(project_status, str)
                and project_status.strip().lower() == "ready_for_production"
            )

            if not (grade_ok or approval_ok or project_status_ok):
                conn.commit()
                return

            cursor.execute(
                """
                UPDATE scribe_projects
                SET status = 'complete',
                    last_status_change = ?
                WHERE id = ?
                """,
                (now, project_id),
            )
            conn.commit()

    def set_status(
        self,
        project_name: str,
        status: str,
    ) -> None:
        """Set lifecycle status and bump last_status_change."""
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE scribe_projects
                SET status = ?, last_status_change = ?
                WHERE name = ?
                """,
                (status, now, project_name),
            )

    def record_doc_update(
        self,
        project_name: str,
        *,
        doc: str,
        action: str,
        before_hash: Optional[str] = None,
        after_hash: Optional[str] = None,
    ) -> None:
        """Record manage_docs-specific metrics in the registry meta blob.

        We treat these as lightweight counters/timestamps so agents can
        distinguish doc updates (usually at phase boundaries) from the
        more frequent progress log traffic.
        """
        now = self._now_iso()
        with self._connect(row_factory=True) as conn:
            row = conn.execute(
                "SELECT meta FROM scribe_projects WHERE name = ?",
                (project_name,),
            ).fetchone()

            meta: Dict[str, Any] = {}
            if row and row["meta"]:
                try:
                    import json

                    meta = json.loads(row["meta"])
                except Exception:
                    meta = {"raw": row["meta"]}

            docs_meta = meta.get("docs") or {}
            # Simple counters + timestamps; easy to extend later.
            docs_meta["last_update_at"] = now
            docs_meta["last_doc_type"] = doc
            docs_meta["last_action"] = action
            docs_meta["update_count"] = int(docs_meta.get("update_count") or 0) + 1

            # Baseline and current hashes per doc type
            raw_doc_key = str(doc or "").strip()
            canonical_doc_key = _canonical_doc_key(raw_doc_key)
            baseline_map = docs_meta.get("baseline_hashes") or {}
            current_map = docs_meta.get("current_hashes") or {}
            if canonical_doc_key not in baseline_map and before_hash:
                baseline_map[canonical_doc_key] = before_hash
            if after_hash:
                current_map[canonical_doc_key] = after_hash

            # Keep compatibility aliases coherent with canonical keys.
            alias_keys = {raw_doc_key, canonical_doc_key}
            for existing_key in set(baseline_map.keys()) | set(current_map.keys()):
                if _canonical_doc_key(existing_key) == canonical_doc_key:
                    alias_keys.add(existing_key)
            if before_hash:
                for key in alias_keys:
                    baseline_map.setdefault(key, before_hash)
            if after_hash:
                for key in alias_keys:
                    current_map[key] = after_hash
            docs_meta["baseline_hashes"] = baseline_map
            docs_meta["current_hashes"] = current_map

            # Derive simple doc-hygiene flags from hashes so agents
            # don't need to compare them manually.
            flags = docs_meta.get("flags") or {}
            seen_docs = set(baseline_map.keys()) | set(current_map.keys())
            for doc_name in seen_docs:
                baseline_val = baseline_map.get(doc_name)
                current_val = current_map.get(doc_name)
                touched = bool(baseline_val or current_val)
                modified = (
                    bool(baseline_val)
                    and bool(current_val)
                    and baseline_val != current_val
                )
                flags[f"{doc_name}_touched"] = touched
                flags[f"{doc_name}_modified"] = modified

            # Mirror canonical flags from aliases to preserve compatibility.
            for doc_name in seen_docs:
                canonical_name = _canonical_doc_key(doc_name)
                if canonical_name == doc_name:
                    continue
                flags[f"{canonical_name}_touched"] = bool(
                    flags.get(f"{canonical_name}_touched")
                    or flags.get(f"{doc_name}_touched")
                )
                flags[f"{canonical_name}_modified"] = bool(
                    flags.get(f"{canonical_name}_modified")
                    or flags.get(f"{doc_name}_modified")
                )

            # Aggregate readiness hints for core dev_plan docs.
            canonical_seen = {_canonical_doc_key(name) for name in seen_docs}
            if _CORE_DOC_CANONICAL_KEYS & canonical_seen:
                core_docs_with_drift = sorted(
                    name
                    for name in _CORE_DOC_CANONICAL_KEYS
                    if bool(flags.get(f"{name}_modified"))
                )
                flags["docs_started"] = any(
                    flags.get(f"{name}_touched") for name in _CORE_DOC_CANONICAL_KEYS
                )
                flags["docs_hash_drift"] = bool(core_docs_with_drift)
                flags["docs_ready_for_work"] = all(
                    flags.get(f"{name}_touched") for name in _CORE_DOC_CANONICAL_KEYS
                ) and not flags["docs_hash_drift"]
                docs_meta["core_docs_with_drift"] = core_docs_with_drift

            docs_meta["flags"] = flags

            meta["docs"] = docs_meta

            try:
                import json

                meta_str = json.dumps(meta, separators=(",", ":"), sort_keys=True)
            except Exception:
                meta_str = str(meta)

            conn.execute(
                """
                UPDATE scribe_projects
                SET meta = ?, last_entry_at = COALESCE(last_entry_at, ?)
                WHERE name = ?
                """,
                (meta_str, now, project_name),
            )

    def get_project(self, project_name: str) -> Optional[ProjectInfo]:
        """Fetch registry view for a single project."""
        with self._connect(row_factory=True) as conn:
            row = conn.execute(
                """
                SELECT
                    p.name AS project_slug,
                    p.name AS project_name,
                    p.description,
                    COALESCE(p.status, 'planning') AS status,
                    p.created_at,
                    p.last_entry_at,
                    p.last_access_at,
                    p.last_status_change,
                    COALESCE(m.total_entries, 0) AS total_entries,
                    COALESCE(df.total_files, 0) AS total_files,
                    COALESCE(ph.total_phases, 0) AS total_phases,
                    p.tags,
                    p.meta
                FROM scribe_projects p
                LEFT JOIN scribe_metrics m
                    ON m.project_id = p.id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS total_files
                    FROM dev_plans
                    GROUP BY project_id
                ) AS df
                    ON df.project_id = p.id
                LEFT JOIN (
                    SELECT project_id, COUNT(*) AS total_phases
                    FROM phases
                    GROUP BY project_id
                ) AS ph
                    ON ph.project_id = p.id
                WHERE p.name = ?
                """,
                (project_name,),
            ).fetchone()

        if not row:
            return None
        return self._row_to_project_info(row)

    def list_projects(
        self,
        *,
        status: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[ProjectInfo]:
        """List projects with basic filtering.

        This is a minimal v1 implementation; richer filters will be
        layered on when we add the dedicated MCP tools.
        """
        clauses = ["1=1"]
        params: List[Any] = []
        if status:
            placeholders = ",".join("?" for _ in status)
            clauses.append(f"p.status IN ({placeholders})")
            params.extend(status)

        where_clause = " AND ".join(clauses)
        query = f"""
            SELECT
                p.name AS project_slug,
                p.name AS project_name,
                p.description,
                COALESCE(p.status, 'planning') AS status,
                p.created_at,
                p.last_entry_at,
                p.last_access_at,
                p.last_status_change,
                COALESCE(m.total_entries, 0) AS total_entries,
                COALESCE(df.total_files, 0) AS total_files,
                COALESCE(ph.total_phases, 0) AS total_phases,
                p.tags,
                p.meta
            FROM scribe_projects p
            LEFT JOIN scribe_metrics m
                ON m.project_id = p.id
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS total_files
                FROM dev_plans
                GROUP BY project_id
            ) AS df
                ON df.project_id = p.id
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS total_phases
                FROM phases
                GROUP BY project_id
            ) AS ph
                ON ph.project_id = p.id
            WHERE {where_clause}
            ORDER BY COALESCE(p.last_entry_at, p.created_at) DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect(row_factory=True) as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_project_info(r) for r in rows]

    def get_last_known_project(
        self,
        *,
        candidates: Optional[List[str]] = None,
    ) -> Optional[ProjectInfo]:
        """Return the most recently accessed project (optionally among candidates)."""
        clauses = ["1=1"]
        params: List[Any] = []
        if candidates:
            placeholders = ",".join("?" for _ in candidates)
            clauses.append(f"p.name IN ({placeholders})")
            params.extend(candidates)

        where_clause = " AND ".join(clauses)
        query = f"""
            SELECT
                p.name AS project_slug,
                p.name AS project_name,
                p.description,
                COALESCE(p.status, 'planning') AS status,
                p.created_at,
                p.last_entry_at,
                p.last_access_at,
                p.last_status_change,
                COALESCE(m.total_entries, 0) AS total_entries,
                COALESCE(df.total_files, 0) AS total_files,
                COALESCE(ph.total_phases, 0) AS total_phases,
                p.tags,
                p.meta
            FROM scribe_projects p
            LEFT JOIN scribe_metrics m
                ON m.project_id = p.id
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS total_files
                FROM dev_plans
                GROUP BY project_id
            ) AS df
                ON df.project_id = p.id
            LEFT JOIN (
                SELECT project_id, COUNT(*) AS total_phases
                FROM phases
                GROUP BY project_id
            ) AS ph
                ON ph.project_id = p.id
            WHERE {where_clause}
            ORDER BY COALESCE(p.last_access_at, p.last_entry_at, p.created_at) DESC
            LIMIT 1
        """

        with self._connect(row_factory=True) as conn:
            row = conn.execute(query, params).fetchone()

        if not row:
            return None
        return self._row_to_project_info(row)

    def get_last_known_project_for_recovery(
        self,
        *,
        candidates: Optional[List[str]] = None,
    ) -> Optional[ProjectInfo]:
        """Compatibility-only helper for explicit recovery/bootstrap flows."""
        return self.get_last_known_project(candidates=candidates)

    def get_planning_advisories(self, project_name: str) -> Dict[str, Any]:
        """Return additive readiness/drift advisories for caller-visible responses."""
        info = self.get_project(project_name)
        if info is None:
            return {}
        return build_planning_advisories(info)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Ensure registry-specific columns exist on scribe_projects.

        We only add columns that are safe no-ops on existing installs.
        Older fields like status/phase/last_activity are preserved.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            # Create a minimal table if it does not exist. This avoids first-run
            # failures when running Scribe against a fresh repo before the main
            # storage backend has created schema.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scribe_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    repo_root TEXT,
                    progress_log_path TEXT,
                    description TEXT,
                    status TEXT,
                    progress_log TEXT,
                    root TEXT,
                    created_at TEXT,
                    last_entry_at TEXT,
                    last_access_at TEXT,
                    last_status_change TEXT,
                    tags TEXT,
                    meta TEXT
                )
                """
            )

            # Ensure supporting tables exist so LEFT JOINs don't fail.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS scribe_metrics (
                    project_id INTEGER PRIMARY KEY REFERENCES scribe_projects(id) ON DELETE CASCADE,
                    total_entries INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    warn_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    last_update TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dev_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                    file_path TEXT,
                    plan_type TEXT,
                    doc_type TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS phases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES scribe_projects(id) ON DELETE CASCADE,
                    phase_name TEXT
                )
                """
            )

            cursor.execute("PRAGMA table_info(scribe_projects)")
            existing = {row[1] for row in cursor.fetchall()}

            def add_column(name: str, ddl: str) -> None:
                if name in existing:
                    return
                cursor.execute(f"ALTER TABLE scribe_projects ADD COLUMN {ddl}")

            # New registry-focused fields for v1
            add_column("description", "description TEXT")
            add_column("last_entry_at", "last_entry_at TEXT")
            add_column("last_access_at", "last_access_at TEXT")
            add_column("last_status_change", "last_status_change TEXT")
            add_column("tags", "tags TEXT")
            add_column("meta", "meta TEXT")
            cursor.execute("PRAGMA table_info(dev_plans)")
            dev_plan_columns = {row[1] for row in cursor.fetchall()}
            if "plan_type" not in dev_plan_columns:
                cursor.execute("ALTER TABLE dev_plans ADD COLUMN plan_type TEXT")
            conn.commit()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_ts(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    def _row_to_project_info(self, row: sqlite3.Row) -> ProjectInfo:
        tags_raw = row["tags"]
        tags: List[str] = []
        if tags_raw:
            tags = [t for t in tags_raw.split(",") if t]

        meta_raw = row["meta"]
        meta: Dict[str, Any] = {}
        if meta_raw:
            try:
                import json

                meta = json.loads(meta_raw)
            except Exception:
                meta = {"raw": meta_raw}

        # Ensure project-scoped metadata container exists and has a work_blockers list.
        project_meta = (meta.get("project") or {}).copy()
        project_meta.setdefault("work_blockers", [])
        meta["project"] = project_meta

        # Derive activity metrics for this project (non-persistent).
        now = datetime.now(timezone.utc)
        created_ts = self._parse_ts(row["created_at"]) or now
        last_entry_ts = self._parse_ts(row["last_entry_at"]) or created_ts
        last_access_ts = self._parse_ts(row["last_access_at"]) or created_ts

        age_days = max(0.0, (now - created_ts).total_seconds() / 86400.0)
        since_entry = max(0.0, (now - last_entry_ts).total_seconds() / 86400.0)
        since_access = max(0.0, (now - last_access_ts).total_seconds() / 86400.0)

        if age_days <= 2:
            staleness_level = "fresh"
        elif age_days <= 7:
            staleness_level = "warming"
        elif age_days <= 30:
            staleness_level = "stale"
        else:
            staleness_level = "frozen"

        # Basic activity metrics.
        activity_meta: Dict[str, Any] = {
            "project_age_days": age_days,
            "days_since_last_entry": since_entry,
            "days_since_last_access": since_access,
            "staleness_level": staleness_level,
        }

        # Activity score: higher means "more active / higher priority".
        entries = int(row["total_entries"])
        entry_rate = entries / age_days if age_days > 0 else float(entries)

        priority_raw = project_meta.get("priority")
        priority_score = 0.0
        if isinstance(priority_raw, (int, float)):
            priority_score = float(priority_raw)
        elif isinstance(priority_raw, str):
            _prio_map = {
                "low": 0.0,
                "medium": 1.0,
                "high": 2.0,
                "critical": 3.0,
            }
            priority_score = _prio_map.get(priority_raw.lower(), 0.0)

        # Doc flags may influence activity score (e.g., docs ready for work).
        docs_meta = (meta.get("docs") or {}).copy()
        flags = (docs_meta.get("flags") or {}).copy()
        docs_ready = bool(flags.get("docs_ready_for_work"))

        activity_score = (
            -since_entry
            - 0.5 * since_access
            + 1.5 * entry_rate
            + (2.0 if docs_ready else 0.0)
            + 0.5 * priority_score
        )
        activity_meta["activity_score"] = activity_score

        # Doc drift hints based on docs meta + lifecycle.
        status = row["status"]
        last_docs_update_ts = None
        last_docs_update_raw = docs_meta.get("last_update_at")
        if isinstance(last_docs_update_raw, str):
            last_docs_update_ts = self._parse_ts(last_docs_update_raw)

        doc_drift = False
        doc_drift_days = None
        if status in ("in_progress", "complete"):
            if not docs_ready:
                doc_drift = True
            if last_entry_ts and not last_docs_update_ts:
                doc_drift = True
            elif last_entry_ts and last_docs_update_ts:
                diff_days = (last_entry_ts - last_docs_update_ts).total_seconds() / 86400.0
                doc_drift_days = diff_days
                if diff_days >= 7.0:
                    doc_drift = True

        if doc_drift_days is not None:
            docs_meta["doc_drift_days_since_update"] = doc_drift_days

        # Drift score: single scalar for how "bad" drift is.
        drift_score = 0.0
        if doc_drift:
            if doc_drift_days is not None:
                drift_score += max(0.0, doc_drift_days)
            if not docs_ready:
                drift_score += 5.0
        docs_meta["drift_score"] = drift_score

        flags["doc_drift_suspected"] = doc_drift
        docs_meta["flags"] = flags
        if docs_meta:
            meta["docs"] = docs_meta

        meta.setdefault("activity", activity_meta)

        return ProjectInfo(
            project_slug=row["project_slug"],
            project_name=row["project_name"],
            description=row["description"],
            status=row["status"],
            created_at=self._parse_ts(row["created_at"]),
            last_entry_at=self._parse_ts(row["last_entry_at"]),
            last_access_at=self._parse_ts(row["last_access_at"]),
            last_status_change=self._parse_ts(row["last_status_change"]),
            total_entries=int(row["total_entries"]),
            total_files=int(row["total_files"]),
            total_phases=int(row["total_phases"]),
            tags=tags,
            meta=meta,
        )


class RuntimeProjectRegistry:
    """Runtime-safe facade around the SQLite-first registry helper."""

    def __init__(self, registry: Optional[ProjectRegistry], advisory_context: Optional[Dict[str, Any]] = None) -> None:
        self._registry = registry
        context = dict(advisory_context or {})
        context.setdefault("available", registry is not None)
        self._advisory_context = context

    @property
    def available(self) -> bool:
        return self._registry is not None

    def ensure_project(self, *args: Any, **kwargs: Any) -> None:
        if self._registry is not None:
            self._registry.ensure_project(*args, **kwargs)

    def touch_access(self, *args: Any, **kwargs: Any) -> None:
        if self._registry is not None:
            self._registry.touch_access(*args, **kwargs)

    def touch_entry(self, *args: Any, **kwargs: Any) -> None:
        if self._registry is not None:
            self._registry.touch_entry(*args, **kwargs)

    def record_doc_update(self, *args: Any, **kwargs: Any) -> None:
        if self._registry is not None:
            self._registry.record_doc_update(*args, **kwargs)

    def get_project(self, *args: Any, **kwargs: Any) -> Optional[ProjectInfo]:
        if self._registry is None:
            return None
        return self._registry.get_project(*args, **kwargs)

    def get_last_known_project(self, *args: Any, **kwargs: Any) -> Optional[ProjectInfo]:
        if self._registry is None:
            return None
        return self._registry.get_last_known_project(*args, **kwargs)

    def get_last_known_project_for_recovery(self, *args: Any, **kwargs: Any) -> Optional[ProjectInfo]:
        if self._registry is None:
            return None
        return self._registry.get_last_known_project_for_recovery(*args, **kwargs)

    def list_projects(self) -> List[ProjectInfo]:
        if self._registry is None:
            return []
        return self._registry.list_projects()

    def get_planning_advisories(self, project_name: str) -> Dict[str, Any]:
        if self._registry is None:
            advisory = {
                "code": "planning_registry_unavailable",
                "severity": "info",
                "classification": self._advisory_context.get("classification", "environment_mismatch"),
                "message": self._advisory_context.get(
                    "message",
                    "Planning-doc drift advisories are unavailable in this runtime.",
                ),
                "provenance": {
                    "source": "runtime.project_registry",
                    "fields": ["available", "reason_code", "classification", "mode", "storage_backend"],
                },
            }
            return {
                "available": False,
                "reason_code": self._advisory_context.get("reason_code", "runtime_registry_unavailable"),
                "classification": self._advisory_context.get("classification", "environment_mismatch"),
                "mode": self._advisory_context.get("mode"),
                "storage_backend": self._advisory_context.get("storage_backend"),
                "advisories": [advisory],
            }
        return self._registry.get_planning_advisories(project_name)

    def get_registry_advisory_context(self) -> Dict[str, Any]:
        return dict(self._advisory_context)


def build_planning_advisories(project_info: ProjectInfo) -> Dict[str, Any]:
    """Build low-noise, provenance-aware planning advisories from registry meta."""
    docs_meta = (project_info.meta or {}).get("docs") or {}
    flags = docs_meta.get("flags") or {}
    activity_meta = (project_info.meta or {}).get("activity") or {}

    docs_ready_for_work = bool(flags.get("docs_ready_for_work"))
    docs_hash_drift = bool(flags.get("docs_hash_drift"))
    doc_drift_suspected = bool(flags.get("doc_drift_suspected"))
    core_docs_with_drift = list(docs_meta.get("core_docs_with_drift") or [])

    contradictory_readiness = docs_ready_for_work and docs_hash_drift
    stale_docs_warning = doc_drift_suspected and activity_meta.get("days_since_last_entry") is not None

    advisories: List[Dict[str, Any]] = []
    if contradictory_readiness:
        advisories.append(
            {
                "code": "docs_readiness_conflict",
                "severity": "warn",
                "message": "docs_ready_for_work is true while docs_hash_drift is true.",
                "provenance": {
                    "source": "registry.docs.flags",
                    "fields": ["docs_ready_for_work", "docs_hash_drift"],
                },
            }
        )

    if stale_docs_warning:
        advisories.append(
            {
                "code": "doc_drift_suspected",
                "severity": "info",
                "message": "Recent project activity may have outpaced planning-doc updates.",
                "provenance": {
                    "source": "registry.docs+activity",
                    "fields": [
                        "doc_drift_suspected",
                        "doc_drift_days_since_update",
                        "days_since_last_entry",
                    ],
                },
            }
        )

    return {
        "docs_ready_for_work": docs_ready_for_work,
        "docs_hash_drift": docs_hash_drift,
        "doc_drift_suspected": doc_drift_suspected,
        "core_docs_with_drift": core_docs_with_drift,
        "has_contradiction": contradictory_readiness,
        "advisories": advisories,
    }


_RUNTIME_REGISTRY: Optional[RuntimeProjectRegistry] = None


def get_runtime_project_registry() -> RuntimeProjectRegistry:
    """Return a runtime-safe registry facade.

    Registry access is only enabled for explicit standalone SQLite runtime.
    Server/public-release paths receive an unavailable facade to avoid any
    implicit SQLite bootstrap side effects.
    """
    global _RUNTIME_REGISTRY
    if _RUNTIME_REGISTRY is not None:
        return _RUNTIME_REGISTRY

    registry: Optional[ProjectRegistry] = None
    advisory_context: Dict[str, Any] = {
        "available": False,
        "classification": "environment_mismatch",
        "reason_code": "runtime_registry_unavailable",
        "message": "Planning-doc drift advisories are unavailable in this runtime.",
    }
    try:
        from scribe_mcp.config.mode_detection import OperatingMode, resolve_configured_mode

        mode = resolve_configured_mode(settings)
        backend = str(settings.storage_backend).strip().lower()
        advisory_context["mode"] = getattr(mode, "value", str(mode))
        advisory_context["storage_backend"] = backend
        if mode == OperatingMode.STANDALONE and backend == "sqlite":
            registry = ProjectRegistry()
            advisory_context.update(
                {
                    "available": True,
                    "classification": "healthy",
                    "reason_code": "runtime_registry_enabled",
                    "message": "Planning-doc drift advisories are active.",
                }
            )
        elif mode != OperatingMode.STANDALONE:
            advisory_context.update(
                {
                    "classification": "environment_mismatch",
                    "reason_code": "runtime_mode_non_standalone",
                    "message": "Planning-doc drift advisories require standalone runtime mode.",
                }
            )
        else:
            advisory_context.update(
                {
                    "classification": "environment_mismatch",
                    "reason_code": "runtime_backend_non_sqlite",
                    "message": "Planning-doc drift advisories require sqlite storage backend in standalone mode.",
                }
            )
    except Exception:
        registry = None
        advisory_context.update(
            {
                "classification": "repo_defect",
                "reason_code": "runtime_registry_bootstrap_error",
                "message": "Planning-doc drift advisories failed to initialize due to runtime bootstrap error.",
            }
        )

    _RUNTIME_REGISTRY = RuntimeProjectRegistry(registry, advisory_context=advisory_context)
    return _RUNTIME_REGISTRY


__all__ = [
    "ProjectInfo",
    "ProjectRegistry",
    "RuntimeProjectRegistry",
    "build_planning_advisories",
    "get_runtime_project_registry",
]
