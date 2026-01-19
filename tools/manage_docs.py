"""Tool for managing project documentation with structured updates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Callable, Awaitable, List

from scribe_mcp import server as server_module
from scribe_mcp.server import app
from scribe_mcp.config.repo_config import RepoDiscovery
from scribe_mcp.config.vector_config import load_vector_config
from scribe_mcp.doc_management.manager import (
    apply_doc_change,
    DocumentOperationError,
    SECTION_MARKER,
    _resolve_create_doc_path,
    _resolve_doc_path,
)
from scribe_mcp.tools.append_entry import append_entry
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.slug import slugify_project_name, normalize_project_input
from scribe_mcp.utils.time import format_utc
from scribe_mcp.utils.estimator import PaginationCalculator
from scribe_mcp.shared.logging_utils import (
    LoggingContext,
    ProjectResolutionError,
    coerce_metadata_mapping,
)
from scribe_mcp.utils.parameter_validator import BulletproofParameterCorrector
from scribe_mcp.utils.error_handler import HealingErrorHandler
from scribe_mcp.utils.config_manager import ConfigManager
from scribe_mcp.shared.base_logging_tool import LoggingToolMixin
from scribe_mcp.shared.project_registry import ProjectRegistry


class _ManageDocsHelper(LoggingToolMixin):
    def __init__(self) -> None:
        self.server_module = server_module
        self.parameter_corrector = BulletproofParameterCorrector()
        self.error_handler = HealingErrorHandler()
        self.config_manager = ConfigManager("manage_docs")


_MANAGE_DOCS_HELPER = _ManageDocsHelper()
_PROJECT_REGISTRY = ProjectRegistry()
_PROJECT_REGISTRY = ProjectRegistry()

# === ACTION REGISTRY (Module Level) ===
# Primary actions - the new consolidated API (7 actions)
PRIMARY_ACTIONS = {
    "create",           # Unified creation with doc_type routing
    "replace_section",  # Section-based editing (scaffolder)
    "apply_patch",      # Unified diff editing
    "replace_range",    # Line-based editing
    "replace_text",     # Find/replace
    "append",           # Add content
    "status_update",    # Checklist updates
}

# Deprecated aliases - old action names that route to new ones
# Format: old_name -> (new_action, default_metadata)
DEPRECATED_ALIASES = {
    "create_doc": ("create", {"doc_type": "custom"}),
    "create_research_doc": ("create", {"doc_type": "research"}),
    "create_bug_report": ("create", {"doc_type": "bug"}),
    "create_review_report": ("create", {"doc_type": "review"}),
    "create_agent_report_card": ("create", {"doc_type": "agent_card"}),
}

# Hidden actions - still work but not promoted (for backwards compat)
HIDDEN_ACTIONS = {
    "normalize_headers",
    "generate_toc",
    "validate_crosslinks",
    "list_sections",
    "list_checklist_items",
    "search",
    "batch",
}

# Combined set for validation (all valid actions)
VALID_ACTIONS = PRIMARY_ACTIONS | set(DEPRECATED_ALIASES.keys()) | HIDDEN_ACTIONS


def _normalize_metadata_with_healing(metadata: Optional[Dict[str, Any] | str]) -> tuple[Dict[str, Any], bool, List[str]]:
    """Normalize metadata parameter using Phase 1 exception healing."""
    healing_messages = []
    healing_applied = False

    # Apply Phase 1 BulletproofParameterCorrector for metadata healing
    try:
        healed_metadata = BulletproofParameterCorrector.correct_metadata_parameter(metadata)
        if healed_metadata != metadata:
            healing_applied = True
            healing_messages.append(f"Auto-corrected metadata parameter from {type(metadata).__name__} to valid dict")

        metadata = healed_metadata
    except Exception as healing_error:
        healing_messages.append(f"Metadata healing failed: {str(healing_error)}, using fallback")
        metadata = {}

    # Apply shared coercion helper for additional normalization
    mapping, error = coerce_metadata_mapping(metadata)
    if error:
        mapping.setdefault("meta_error", error)
        healing_messages.append(f"Metadata coercion warning: {error}")
        healing_applied = True

    return mapping, healing_applied, healing_messages


def _heal_manage_docs_parameters(
    action: str,
    doc_category: str,
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any] | str] = None,
    patch_mode: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    doc_name: Optional[str] = None,
    target_dir: Optional[str] = None,
) -> tuple[dict, bool, List[str]]:
    """Heal all manage_docs parameters using Phase 1 exception handling."""
    healing_messages = []
    healing_applied = False
    invalid_action = False

    # Use module-level ACTION REGISTRY constants
    healed_params = {}

    # Validate action parameter (no auto-correction to avoid accidental edits)
    original_action = action
    healed_action = str(original_action).strip() if original_action is not None else ""
    if healed_action not in VALID_ACTIONS:
        invalid_action = True
        healing_applied = True
        healing_messages.append(
            f"Invalid action '{original_action}'. Use one of: {', '.join(sorted(VALID_ACTIONS))}."
        )
    healed_params["action"] = healed_action
    healed_params["invalid_action"] = invalid_action

    # Heal doc_category parameter (string normalization only; no enum correction)
    original_doc_category = doc_category
    healed_doc_category = str(original_doc_category).strip() if original_doc_category is not None else ""
    if healed_doc_category != original_doc_category:
        healing_applied = True
        healing_messages.append(f"Auto-normalized doc_category from '{original_doc_category}' to '{healed_doc_category}'")
    healed_params["doc_category"] = healed_doc_category

    # Heal section parameter (string normalization)
    if section is not None:
        original_section = section
        healed_section = str(section).strip()
        if healed_section != original_section:
            healing_applied = True
            healing_messages.append(f"Auto-corrected section from '{original_section}' to '{healed_section}'")
        healed_params["section"] = healed_section
    else:
        healed_params["section"] = None

    # Heal content parameter (string normalization)
    if content is not None:
        original_content = content
        healed_content = str(content)
        if healed_content != original_content:
            healing_applied = True
            healing_messages.append(f"Auto-corrected content parameter to string type")
        healed_params["content"] = healed_content
    else:
        healed_params["content"] = None

    # Heal patch parameter (string normalization)
    if patch is not None:
        original_patch = patch
        healed_patch = str(patch)
        if healed_patch != original_patch:
            healing_applied = True
            healing_messages.append("Auto-corrected patch parameter to string type")
        healed_params["patch"] = healed_patch
    else:
        healed_params["patch"] = None

    # Heal patch_source_hash parameter (string normalization)
    if patch_source_hash is not None:
        original_hash = patch_source_hash
        healed_hash = str(patch_source_hash).strip()
        if healed_hash != original_hash:
            healing_applied = True
            healing_messages.append("Auto-corrected patch_source_hash parameter to string type")
        healed_params["patch_source_hash"] = healed_hash
    else:
        healed_params["patch_source_hash"] = None

    # Heal edit parameter (JSON parsing when provided as string)
    healed_params["edit"] = None
    if edit is not None:
        if isinstance(edit, str):
            try:
                healed_params["edit"] = json.loads(edit)
                healing_applied = True
                healing_messages.append("Auto-parsed edit JSON string into dict")
            except json.JSONDecodeError:
                healed_params["edit"] = None
                healing_applied = True
                healing_messages.append("Failed to parse edit JSON; ignoring edit payload")
        elif isinstance(edit, dict):
            healed_params["edit"] = edit
        else:
            healed_params["edit"] = None
            healing_applied = True
            healing_messages.append("Auto-corrected edit parameter to None")

    # Heal patch_mode parameter (string normalization)
    if patch_mode is not None:
        original_mode = patch_mode
        healed_mode = str(patch_mode).strip().lower()
        if healed_mode != original_mode:
            healing_applied = True
            healing_messages.append("Auto-corrected patch_mode parameter to string type")
        if healed_mode not in {"structured", "unified"}:
            healing_applied = True
            healing_messages.append("Invalid patch_mode; expected 'structured' or 'unified'")
            healed_mode = None
        healed_params["patch_mode"] = healed_mode
    else:
        healed_params["patch_mode"] = None

    def _coerce_line_number(value: Optional[int], label: str) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        try:
            coerced = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        healing_messages.append(f"Auto-corrected {label} to integer {coerced}")
        return coerced

    healed_params["start_line"] = _coerce_line_number(start_line, "start_line")
    healed_params["end_line"] = _coerce_line_number(end_line, "end_line")

    # Heal template parameter (string normalization)
    if template is not None:
        original_template = template
        healed_template = str(template).strip()
        if healed_template != original_template:
            healing_applied = True
            healing_messages.append(f"Auto-corrected template from '{original_template}' to '{healed_template}'")
        healed_params["template"] = healed_template
    else:
        healed_params["template"] = None

    # Heal metadata parameter using enhanced function
    healed_metadata, metadata_healed, metadata_messages = _normalize_metadata_with_healing(metadata)
    if metadata_healed:
        healing_applied = True
        healing_messages.extend(metadata_messages)
    healed_params["metadata"] = healed_metadata

    # Heal dry_run parameter
    original_dry_run = dry_run
    healed_dry_run = bool(dry_run)
    if isinstance(dry_run, str):
        healed_dry_run = dry_run.lower() in ("true", "1", "yes")
        if healed_dry_run != dry_run:
            healing_applied = True
            healing_messages.append(f"Auto-corrected dry_run from '{dry_run}' to {healed_dry_run}")
    elif healed_dry_run != original_dry_run:
        healing_applied = True
        healing_messages.append(f"Auto-corrected dry_run to boolean {healed_dry_run}")
    healed_params["dry_run"] = healed_dry_run

    # Heal doc_name parameter (string normalization only)
    # doc_name is the UNIQUE identifier - it cannot be inferred from doc_category
    if doc_name is not None:
        original_doc_name = doc_name
        healed_doc_name = str(doc_name).strip()
        if healed_doc_name != original_doc_name:
            healing_applied = True
            healing_messages.append(f"Auto-corrected doc_name from '{original_doc_name}' to '{healed_doc_name}'")
        healed_params["doc_name"] = healed_doc_name
    else:
        healed_params["doc_name"] = None

    # Heal target_dir parameter (string normalization)
    if target_dir is not None:
        original_target_dir = target_dir
        healed_target_dir = str(target_dir).strip()
        if healed_target_dir != original_target_dir:
            healing_applied = True
            healing_messages.append(f"Auto-corrected target_dir from '{original_target_dir}' to '{healed_target_dir}'")
        healed_params["target_dir"] = healed_target_dir
    else:
        healed_params["target_dir"] = None

    return healed_params, healing_applied, healing_messages


def _add_healing_info_to_response(
    response: Dict[str, Any],
    healing_applied: bool,
    healing_messages: List[str]
) -> Dict[str, Any]:
    """Add healing information to response if parameters were corrected."""
    if healing_applied and healing_messages:
        response["parameter_healing"] = {
            "applied": True,
            "messages": healing_messages,
            "message": "Parameters auto-corrected using Phase 1 exception healing"
        }
    return response


def _hash_text(content: str) -> str:
    """Return a deterministic hash for stored document content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _chunk_text_for_vector(text: str, max_chars: int = 4000) -> List[str]:
    if not text:
        return []

    def _split_into_sections(raw: str) -> List[str]:
        lines = raw.splitlines()
        sections: List[List[str]] = []
        current: List[str] = []
        for line in lines:
            if line.lstrip().startswith("#"):
                if current:
                    sections.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append(current)
        return ["\n".join(section).strip() for section in sections if "\n".join(section).strip()]

    def _split_section(section: str) -> List[str]:
        section = section.strip()
        if not section:
            return []
        if len(section) <= max_chars:
            return [section]

        lines = section.splitlines()
        heading = lines[0].strip() if lines and lines[0].lstrip().startswith("#") else None
        body = "\n".join(lines[1:]).strip() if heading else section
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

        chunks: List[str] = []
        buffer: List[str] = []
        buffer_len = 0
        header_len = len(heading) + 2 if heading else 0
        limit = max(1, max_chars - header_len)

        for paragraph in paragraphs:
            addition = len(paragraph) + (2 if buffer else 0)
            if buffer_len + addition > limit and buffer:
                chunk = "\n\n".join(buffer)
                if heading:
                    chunk = f"{heading}\n\n{chunk}"
                chunks.append(chunk)
                buffer = [paragraph]
                buffer_len = len(paragraph)
                continue
            buffer.append(paragraph)
            buffer_len += addition

        if buffer:
            chunk = "\n\n".join(buffer)
            if heading:
                chunk = f"{heading}\n\n{chunk}"
            chunks.append(chunk)

        return chunks

    sections = _split_into_sections(text)
    chunks: List[str] = []
    for section in sections:
        chunks.extend(_split_section(section))
    return chunks


def _generate_doc_entry_id(path: Path, chunk_index: int, content_hash: str) -> str:
    seed = f"{path}|{chunk_index}|{content_hash}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


_LOG_DOC_KEYS = {
    "progress_log",
    "doc_log",
    "security_log",
    "bug_log",
}

_LOG_DOC_FILENAMES = {
    "PROGRESS_LOG.md",
    "DOC_LOG.md",
    "SECURITY_LOG.md",
    "BUG_LOG.md",
    "GLOBAL_PROGRESS_LOG.md",
}


def _is_rotated_log_filename(name: str) -> bool:
    upper = name.upper()
    for base in _LOG_DOC_FILENAMES:
        if upper.startswith(f"{base.upper()}."):
            return True
    return False


def _should_skip_doc_index(doc_key: Optional[str], path: Path) -> bool:
    name = path.name
    upper = name.upper()
    if doc_key and doc_key.lower() in _LOG_DOC_KEYS:
        return True
    if name in _LOG_DOC_FILENAMES:
        return True
    if upper.endswith("_LOG.MD"):
        return True
    if _is_rotated_log_filename(name):
        return True
    return False


def _get_vector_search_defaults(repo_root: Optional[Path]) -> tuple[int, int]:
    default_doc_k = 5
    default_log_k = 3
    if not repo_root:
        return default_doc_k, default_log_k
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return default_doc_k, default_log_k
    try:
        default_doc_k = max(0, int(config.vector_search_doc_k))
    except (TypeError, ValueError):
        default_doc_k = 5
    try:
        default_log_k = max(0, int(config.vector_search_log_k))
    except (TypeError, ValueError):
        default_log_k = 3
    return default_doc_k, default_log_k


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_semantic_limits(
    *,
    search_meta: Dict[str, Any],
    repo_root: Optional[Path],
) -> Dict[str, Any]:
    default_doc_k, default_log_k = _get_vector_search_defaults(repo_root)
    k_override = _parse_int(search_meta.get("k"))
    doc_k_override = _parse_int(search_meta.get("doc_k"))
    log_k_override = _parse_int(search_meta.get("log_k"))

    if k_override is None:
        total_k = max(0, default_doc_k + default_log_k)
    else:
        total_k = max(0, k_override)

    doc_k = default_doc_k if doc_k_override is None else max(0, doc_k_override)
    log_k = default_log_k if log_k_override is None else max(0, log_k_override)

    if doc_k > total_k:
        doc_k = total_k
    remaining = max(0, total_k - doc_k)
    if log_k > remaining:
        log_k = remaining

    return {
        "total_k": total_k,
        "doc_k": doc_k,
        "log_k": log_k,
        "default_doc_k": default_doc_k,
        "default_log_k": default_log_k,
        "k_override": k_override,
        "doc_k_override": doc_k_override,
        "log_k_override": log_k_override,
    }


def _get_vector_indexer():
    try:
        from scribe_mcp.plugins.registry import get_plugin_registry
        registry = get_plugin_registry()
        for plugin in registry.plugins.values():
            if getattr(plugin, "name", None) == "vector_indexer" and getattr(plugin, "initialized", False):
                return plugin
    except Exception:
        return None
    return None


def _vector_indexing_enabled(repo_root: Optional[Path]) -> bool:
    if not repo_root:
        return False
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return False
    return bool(config.vector_index_docs)


def _vector_search_enabled(repo_root: Optional[Path], content_type: str) -> bool:
    if not repo_root:
        return False
    try:
        config = RepoDiscovery.load_config(repo_root)
    except Exception:
        return False
    if not (config.plugin_config or {}).get("enabled", False):
        return False
    vector_config = load_vector_config(repo_root)
    if not vector_config.enabled:
        return False
    if content_type == "log":
        return bool(config.vector_index_logs)
    return bool(config.vector_index_docs)


def _normalize_doc_search_mode(value: Optional[str]) -> str:
    if not value:
        return "exact"
    normalized = value.strip().lower()
    if normalized in {"exact", "literal"}:
        return "exact"
    if normalized in {"fuzzy", "approx"}:
        return "fuzzy"
    if normalized in {"semantic", "vector"}:
        return "semantic"
    return normalized


def _iter_doc_search_targets(project: Dict[str, Any], doc_name: str) -> List[tuple[str, Path]]:
    docs_mapping = project.get("docs") or {}
    if doc_name in {"*", "all"}:
        return [(key, Path(path)) for key, path in docs_mapping.items()]
    if doc_name not in docs_mapping:
        return []
    return [(doc_name, Path(docs_mapping[doc_name]))]


def _search_doc_lines(
    *,
    text: str,
    query: str,
    mode: str,
    fuzzy_threshold: float,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    lines = text.splitlines()
    if mode == "exact":
        for idx, line in enumerate(lines, start=1):
            if query in line:
                results.append({"line": idx, "snippet": line})
        return results

    if mode == "fuzzy":
        import difflib

        for idx, line in enumerate(lines, start=1):
            score = difflib.SequenceMatcher(None, query, line).ratio()
            if score >= fuzzy_threshold:
                results.append({"line": idx, "snippet": line, "score": round(score, 4)})
        return results

    return results


async def _index_doc_for_vector(
    *,
    project: Dict[str, Any],
    doc_name: str,
    change_path: Path,
    after_hash: str,
    agent_id: str,
    metadata: Optional[Dict[str, Any]],
    wait_for_queue: bool = False,
    queue_timeout: Optional[float] = None,
) -> None:
    repo_root = project.get("root")
    if isinstance(repo_root, str):
        repo_root = Path(repo_root)
    if not _vector_indexing_enabled(repo_root):
        return

    vector_indexer = _get_vector_indexer()
    if not vector_indexer:
        return

    if _should_skip_doc_index(doc_name, change_path):
        return

    try:
        raw_text = await asyncio.to_thread(change_path.read_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    frontmatter = {}
    body = raw_text
    try:
        parsed = parse_frontmatter(raw_text)
        if parsed.has_frontmatter:
            frontmatter = parsed.frontmatter_data
            body = parsed.body
    except ValueError:
        body = raw_text

    content = body.strip()
    if not content:
        return

    title = frontmatter.get("title")
    doc_type = frontmatter.get("doc_type")
    chunks = _chunk_text_for_vector(content)
    if not chunks:
        return

    timestamp = format_utc()
    project_name = project.get("name", "")
    chunk_total = len(chunks)

    for idx, chunk in enumerate(chunks):
        content_hash = _hash_text(chunk)
        entry_id = _generate_doc_entry_id(change_path, idx, content_hash)
        message = f"{title}\n\n{chunk}" if title else chunk
        doc_meta = {
            "content_type": "doc",
            "doc_name": doc_name,
            "doc_title": title,
            "doc_type": doc_type,
            "file_path": str(change_path),
            "chunk_index": idx,
            "chunk_total": chunk_total,
            "sha_after": after_hash,
        }
        if metadata:
            doc_meta["doc_metadata"] = metadata

        entry_data = {
            "entry_id": entry_id,
            "project_name": project_name,
            "message": message,
            "agent": agent_id,
            "timestamp": timestamp,
            "meta": doc_meta,
        }
        if wait_for_queue and hasattr(vector_indexer, "enqueue_entry"):
            vector_indexer.enqueue_entry(entry_data, wait=True, timeout=queue_timeout)
        else:
            vector_indexer.post_append(entry_data)


def _current_timestamp() -> str:
    """Return the current UTC timestamp for metadata usage."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _write_file_atomically(file_path: Path, content: str) -> bool:
    """Write file atomically using temp file and move operation."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file first, then move atomically
        temp_path = file_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Verify the temp file was written correctly
        if temp_path.exists() and temp_path.stat().st_size > 0:
            temp_path.replace(file_path)
            return True
        else:
            print(f"⚠️ Failed to write {file_path.name}: temporary file not created properly")
            # Clean up temp file if it exists
            if temp_path.exists():
                temp_path.unlink()
            return False

    except (OSError, IOError) as exc:
        print(f"⚠️ Failed to write {file_path.name}: {exc}")
        return False
    except Exception as exc:
        print(f"❌ Unexpected error writing {file_path.name}: {exc}")
        return False


def _validate_and_repair_index(index_path: Path, doc_dir: Path) -> bool:
    """Validate index file and repair if it's broken or out of sync."""
    try:
        # Check if index exists and is readable
        if not index_path.exists():
            print(f"🔧 Index file {index_path.name} missing, will create new one")
            return False

        # Try to read the index
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, IOError) as exc:
            print(f"🔧 Index file {index_path.name} corrupted ({exc}), will repair")
            # Backup corrupted file
            backup_path = index_path.with_suffix('.corrupted.backup')
            if index_path.exists():
                index_path.rename(backup_path)
            return False

        # Basic validation - check if it looks like a proper index
        if not content.strip().startswith('#'):
            print(f"🔧 Index file {index_path.name} doesn't look like valid index, will repair")
            backup_path = index_path.with_suffix('.invalid.backup')
            index_path.rename(backup_path)
            return False

        # Count actual documents vs indexed documents
        if doc_dir.exists():
            actual_docs = list(doc_dir.glob("*.md"))
            actual_docs = [d for d in actual_docs if d.name != "INDEX.md" and not d.name.startswith("_")]

            # Simple heuristic: if index says 0 docs but we have actual docs, it's stale
            if "Total Documents:** 0" in content and actual_docs:
                print(f"🔧 Index file {index_path.name} stale (shows 0 docs but {len(actual_docs)} found), will repair")
                return False

        return True

    except Exception as exc:
        print(f"🔧 Error validating index {index_path.name}: {exc}, will repair")
        return False


async def _get_or_create_storage_project(backend: Any, project: Dict[str, Any]) -> Any:
    """Fetch or create the backing storage record for a project."""
    timeout = server_module.settings.storage_timeout_seconds
    async with asyncio.timeout(timeout):
        storage_record = await backend.fetch_project(project["name"])
    if not storage_record:
        async with asyncio.timeout(timeout):
            storage_record = await backend.upsert_project(
                name=project["name"],
                repo_root=project["root"],
                progress_log_path=project["progress_log"],
            )
    return storage_record


def _build_special_metadata(
    project: Dict[str, Any],
    metadata: Dict[str, Any],
    agent_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Prepare metadata payload for template rendering and storage."""
    prepared = metadata.copy()
    prepared.setdefault("project_name", project.get("name"))
    prepared.setdefault("project_root", project.get("root"))
    prepared.setdefault("agent_id", agent_id)
    prepared.setdefault("agent_name", prepared.get("agent_name", agent_id))
    prepared.setdefault("timestamp", prepared.get("timestamp", _current_timestamp()))
    if extra:
        for key, value in extra.items():
            prepared.setdefault(key, value)
    return prepared


async def _render_special_template(
    project: Dict[str, Any],
    agent_id: str,
    template_name: str,
    metadata: Dict[str, Any],
    extra_metadata: Optional[Dict[str, Any]] = None,
    prepared_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Render a special document template using the shared Jinja2 engine."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox",
        )
        if prepared_metadata is None:
            prepared_metadata = _build_special_metadata(
                project,
                metadata,
                agent_id,
                extra=extra_metadata,
            )
        return engine.render_template(
            template_name=f"documents/{template_name}",
            metadata=prepared_metadata,
        )
    except (ImportError, TemplateEngineError) as exc:
        raise DocumentOperationError(f"Failed to render template '{template_name}': {exc}") from exc


async def _record_special_doc_change(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    doc_label: str,
    target_path: Path,
    metadata: Dict[str, Any],
    before_hash: str,
    after_hash: str,
) -> None:
    """Persist document change information for special documents."""
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:  # pragma: no cover - defensive logging mirror behaviour above
        print(f"⚠️  Failed to prepare storage record for {doc_label}: {exc}")
        return

    action = "create" if not before_hash else "update"
    try:
        await backend.record_doc_change(
            storage_record,
            doc=doc_label,
            section=None,
            action=action,
            agent=agent_id,
            metadata=metadata,
            sha_before=before_hash,
            sha_after=after_hash,
        )
    except Exception as exc:
        print(f"⚠️  Failed to record special doc change for {doc_label}: {exc}")


def _parse_numeric_grade(value: Any) -> Optional[float]:
    """Convert percentage-like values to float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).strip()
        if text.endswith("%"):
            text = text[:-1]
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


async def _record_agent_report_card_metadata(
    backend: Any,
    project: Dict[str, Any],
    agent_id: str,
    target_path: Path,
    metadata: Dict[str, Any],
) -> None:
    """Persist structured agent report card metadata when supported."""
    if not backend:
        return
    try:
        storage_record = await _get_or_create_storage_project(backend, project)
    except Exception as exc:
        print(f"⚠️  Failed to prepare storage project for agent card: {exc}")
        return

    try:
        await backend.record_agent_report_card(
            storage_record,
            file_path=str(target_path),
            agent_name=metadata.get("agent_name", agent_id),
            stage=metadata.get("stage"),
            overall_grade=_parse_numeric_grade(metadata.get("overall_grade")),
            performance_level=metadata.get("performance_level"),
            metadata=metadata,
        )
    except Exception as exc:
        print(f"⚠️  Failed to record agent report card metadata: {exc}")


async def _auto_register_document(
    project: Dict[str, Any],
    doc_name: str,
) -> bool:
    """
    Auto-register an unregistered document with the project.

    This function is called automatically for EDIT operations when a document
    is not yet registered in the project's docs mapping. It:
    1. Resolves the document path using existing conventions
    2. Verifies the file exists
    3. Computes SHA256 hash for tracking
    4. Updates the database docs_json column
    5. Updates ProjectRegistry for in-memory tracking
    6. Logs the registration event

    Args:
        project: Active project dict from context (must have name, root)
        doc_name: Unique document identifier (e.g., "architecture", "phase_plan", "checklist")

    Returns:
        True if registration successful

    Raises:
        ValueError: If document file doesn't exist or registration fails
        DocumentOperationError: If doc_name is invalid or path resolution fails
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Resolve document path using existing infrastructure
        doc_path = _resolve_doc_path(project, doc_name)
    except Exception as e:
        raise ValueError(
            f"Cannot auto-register '{doc_name}': Invalid document identifier or path resolution failed. "
            f"Use 'generate_doc_templates' to create standard documents first. Error: {e}"
        )

    # Verify file exists
    if not doc_path.exists():
        raise ValueError(
            f"Cannot auto-register '{doc_name}': File {doc_path} does not exist. "
            f"Use 'generate_doc_templates' to create it first."
        )

    # Compute SHA256 hash for document tracking
    try:
        with open(doc_path, 'rb') as f:
            doc_hash = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        raise ValueError(f"Failed to read document {doc_path} for hashing: {e}")

    # Update database docs_json column
    backend = server_module.storage_backend
    if not backend:
        raise ValueError("Storage backend not available for auto-registration")

    project_name = project.get("name")
    if not project_name:
        raise ValueError("Project must have a name for auto-registration")

    try:
        # Get current docs_json from database
        current_docs = project.get("docs", {})

        # Add new document to docs mapping
        current_docs[doc_name] = str(doc_path)
        docs_json = json.dumps(current_docs)

        # Update database via StorageBackend API
        await backend.update_project_docs(project_name, docs_json)

        logger.info(f"Auto-registered document '{doc_name}' for project '{project_name}'")

    except Exception as e:
        raise ValueError(f"Failed to update database for auto-registration: {e}")

    # Update ProjectRegistry for in-memory tracking
    try:
        await _PROJECT_REGISTRY.record_doc_update(
            project_name=project_name,
            doc_key=doc_name,
            file_path=str(doc_path),
            baseline_hash=doc_hash,
            current_hash=doc_hash,
        )
    except Exception as e:
        # Non-fatal - log warning but don't fail registration
        logger.warning(f"Failed to update ProjectRegistry for '{doc_name}': {e}")

    # Log registration event to progress log
    try:
        await append_entry(
            message=f"Auto-registered document: {doc_name} ({doc_path.name})",
            status="info",
            agent="manage_docs",
            meta={
                "action": "auto_register",
                "doc_name": doc_name,
                "path": str(doc_path),
                "hash": doc_hash[:8],
            }
        )
    except Exception as e:
        # Non-fatal - log warning but don't fail registration
        logger.warning(f"Failed to log auto-registration event: {e}")

    return True


def _resolve_custom_doc_path(
    project: Dict[str, Any],
    doc_category: str,
    doc_name: str,
) -> Optional[Path]:
    """
    Resolve custom document path by searching appropriate subdirectories.

    Supports:
    - research: research/<doc_name>.md
    - bugs: docs/bugs/<category>/<date>_<slug>/report.md
    - reviews: REVIEW_REPORT_<stage>_<timestamp>.md
    - agent_cards: AGENT_REPORT_CARD_<agent>_<stage>_<timestamp>.md

    Args:
        project: Project configuration dictionary
        doc_category: Category of custom document (research, bugs, reviews, agent_cards)
        doc_name: Unique document identifier (filename or slug)

    Returns:
        Path to document if found, None otherwise
    """
    # Derive docs_dir from progress_log path (source of truth from database)
    progress_log = project.get("progress_log")
    if not progress_log:
        # No progress_log means project not properly initialized
        return None

    # Extract docs_dir from progress_log path
    # e.g., /path/.scribe/docs/dev_plans/project/PROGRESS_LOG.md -> /path/.scribe/docs/dev_plans/project/
    docs_dir = Path(progress_log).parent
    project_root = Path(project.get("root", ""))

    # Research documents
    if doc_category == "research":
        research_dir = docs_dir / "research"
        if not research_dir.exists():
            return None

        # Try exact match with .md extension
        candidate = research_dir / f"{doc_name}.md"
        if candidate.exists():
            return candidate

        # Try without extension (if .md already provided)
        if doc_name.endswith(".md"):
            candidate = research_dir / doc_name
            if candidate.exists():
                return candidate

        return None

    # Bug reports
    elif doc_category == "bugs":
        bugs_root = project_root / "docs" / "bugs"
        if not bugs_root.exists():
            return None

        # Search all category directories for matching slug
        for category_dir in bugs_root.iterdir():
            if not category_dir.is_dir():
                continue
            # Search for directories ending with the slug
            for bug_dir in category_dir.iterdir():
                if not bug_dir.is_dir():
                    continue
                # Check if directory name ends with _<slug>
                if bug_dir.name.endswith(f"_{doc_name}"):
                    report_file = bug_dir / "report.md"
                    if report_file.exists():
                        return report_file

        return None

    # Review reports
    elif doc_category == "reviews":
        # Search for REVIEW_REPORT_* matching provided identifier
        pattern = f"REVIEW_REPORT_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            # Return most recent if multiple matches
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    # Agent report cards
    elif doc_category == "agent_cards":
        # Search for AGENT_REPORT_CARD_* matching provided identifier
        pattern = f"AGENT_REPORT_CARD_*{doc_name}*.md"
        candidates = list(docs_dir.glob(pattern))
        if candidates:
            # Return most recent if multiple matches
            return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        return None

    return None


@app.tool()
async def manage_docs(
    action: str,
    doc_category: str = "",  # Document category: architecture|phase_plan|checklist|research|bugs|wiki|custom
    section: Optional[str] = None,
    content: Optional[str] = None,
    patch: Optional[str] = None,
    patch_source_hash: Optional[str] = None,
    edit: Optional[Dict[str, Any] | str] = None,
    patch_mode: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    template: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    doc_name: Optional[str] = None,
    target_dir: Optional[str] = None,
    project: Optional[str] = None,  # Explicit project override (allows cross-project doc management)
) -> Dict[str, Any]:
    """Apply structured updates to architecture/phase/checklist documents and create research/bug documents."""
    state_snapshot = await server_module.state_manager.record_tool("manage_docs")
    # Apply Phase 1 exception healing to all parameters
    try:
        healed_params, healing_applied, healing_messages = _heal_manage_docs_parameters(
            action=action, doc_category=doc_category, section=section, content=content,
            patch=patch, patch_source_hash=patch_source_hash,
            edit=edit, patch_mode=patch_mode, start_line=start_line, end_line=end_line,
            template=template, metadata=metadata, dry_run=dry_run,
            doc_name=doc_name, target_dir=target_dir
        )

        # Update parameters with healed values
        action = healed_params["action"]
        doc_category = healed_params["doc_category"]
        section = healed_params["section"]
        content = healed_params["content"]
        patch = healed_params["patch"]
        patch_source_hash = healed_params["patch_source_hash"]
        edit = healed_params["edit"]
        patch_mode = healed_params["patch_mode"]
        start_line = healed_params["start_line"]
        end_line = healed_params["end_line"]
        template = healed_params["template"]
        metadata = healed_params["metadata"]
        dry_run = healed_params["dry_run"]
        doc_name = healed_params["doc_name"]
        target_dir = healed_params["target_dir"]

    except Exception as healing_error:
        error_payload = _MANAGE_DOCS_HELPER.error_response(
            "manage_docs parameter healing failed; no changes applied.",
            suggestion="Verify action/doc/section parameters and retry. For edits, prefer action='apply_patch'.",
            extra={"error_detail": str(healing_error)},
        )
        return error_payload

    # Check for deprecated action names and emit warnings
    deprecation_warning = None
    if action in DEPRECATED_ALIASES:
        new_action, default_params = DEPRECATED_ALIASES[action]
        deprecation_warning = (
            f"DEPRECATED: '{action}' is deprecated. "
            f"Use create(doc_type='{default_params.get('doc_type', 'custom')}') instead."
        )
        # Apply default params to metadata if not already set
        if metadata is None:
            metadata = {}
        for key, value in default_params.items():
            if key not in metadata:
                metadata[key] = value
        # Keep using old action name for now (handlers still expect it)
        # Task 2.2 already routes "create" correctly

    if healed_params.get("invalid_action"):
        error_payload = _MANAGE_DOCS_HELPER.error_response(
            f"Invalid manage_docs action '{action}'.",
            suggestion="Use action='apply_patch' for edits, 'replace_section' only for initial scaffolding.",
            extra={
                "allowed_actions": sorted(list({
                    "replace_section",
                    "append",
                    "status_update",
                    "apply_patch",
                    "replace_range",
                    "normalize_headers",
                    "generate_toc",
                    "list_sections",
                    "list_checklist_items",
                    "batch",
                    "create_doc",
                    "validate_crosslinks",
                    "search",
                    "create_research_doc",
                    "create_bug_report",
                    "create_review_report",
                    "create_agent_report_card",
                })),
                "healing_messages": healing_messages,
            },
        )
        return error_payload

    scaffold_flag = False
    if isinstance(metadata, dict):
        raw_scaffold = metadata.get("scaffold")
        if isinstance(raw_scaffold, bool):
            scaffold_flag = raw_scaffold
        elif isinstance(raw_scaffold, str):
            scaffold_flag = raw_scaffold.strip().lower() in {"true", "1", "yes"}

    # Normalize project parameter to handle hyphens, spaces, mixed case (Task Package 2.5)
    if project is not None:
        project = normalize_project_input(project)

    try:
        context = await _MANAGE_DOCS_HELPER.prepare_context(
            tool_name="manage_docs",
            agent_id=None,
            explicit_project=project,  # Allow cross-project doc management
            require_project=True,
            state_snapshot=state_snapshot,
            reminder_variables={"action": action, "scaffold": scaffold_flag},
        )
    except ProjectResolutionError as exc:
        payload = _MANAGE_DOCS_HELPER.translate_project_error(exc)
        payload.setdefault("suggestion", "Invoke set_project before managing docs.")
        payload.setdefault("reminders", [])
        return payload

    project = context.project or {}

    agent_identity = server_module.get_agent_identity()
    agent_id = "Scribe"
    if agent_identity:
        agent_id = await agent_identity.get_or_create_agent_id()

    backend = server_module.storage_backend
    registry_warning = None

    # Define EDIT actions that should trigger auto-registration
    EDIT_ACTIONS = {
        "list_sections",
        "replace_section",
        "apply_patch",
        "replace_range",
        "append",
        "status_update",
        "normalize_headers",
        "generate_toc",
        "search",
        "replace_text",
        "validate_crosslinks",
    }

    # Custom document path resolution (research, bugs, reviews, agent_cards)
    # This allows editing custom docs without requiring registration
    custom_doc_types = {"research", "bugs", "reviews", "agent_cards"}
    if action in EDIT_ACTIONS and doc_category in custom_doc_types and doc_name:
        # Attempt to resolve custom document path
        resolved_path = _resolve_custom_doc_path(
            project=project,
            doc_category=doc_category,
            doc_name=doc_name
        )

        if resolved_path:
            # Custom doc found - use it directly by temporarily updating project docs
            logger.info(f"Resolved custom document: {resolved_path}")

            # Create a temporary project dict with the resolved path
            # This allows the rest of manage_docs to work as normal
            project = project.copy()
            project["docs"] = project.get("docs", {}).copy()

            # Store the resolved path relative to docs_dir for consistency
            # Derive docs_dir from progress_log (source of truth from database)
            progress_log = project.get("progress_log")
            if progress_log:
                docs_dir = Path(progress_log).parent
                try:
                    relative_path = resolved_path.relative_to(docs_dir)
                    project["docs"][doc_category] = str(relative_path)
                except ValueError:
                    # If not relative to docs_dir, try relative to project root
                    project_root = Path(project.get("root", ""))
                    try:
                        relative_path = resolved_path.relative_to(project_root)
                        project["docs"][doc_category] = str(relative_path)
                    except ValueError:
                        # Fall back to absolute path
                        project["docs"][doc_category] = str(resolved_path)
            else:
                # No progress_log - use absolute path
                project["docs"][doc_category] = str(resolved_path)

            logger.info(f"Temporarily registered custom doc '{doc_category}' at: {project['docs'][doc_category]}")
            # Continue to edit logic (skip auto-registration)
        else:
            # Custom doc not found - return helpful error
            # Use slugified project name for accurate path hints
            project_slug = slugify_project_name(project.get('name', '<project>'))
            error_payload = _MANAGE_DOCS_HELPER.error_response(
                f"Custom document '{doc_name}' not found",
                suggestion=(
                    f"Ensure document was created with create_{doc_category}_doc action. "
                    f"Check doc_name spelling and verify the document exists. "
                    f"For research docs: check .scribe/docs/dev_plans/{project_slug}/research/ "
                    f"For bug reports: check docs/bugs/<category>/<date>_{doc_name}/"
                ),
                extra={
                    "doc_type": doc_category,
                    "doc_name": doc_name,
                    "searched_in": str(Path(project.get("progress_log")).parent) if project.get("progress_log") else "unknown",
                    "project_root": str(project.get("root"))
                }
            )
            return _MANAGE_DOCS_HELPER.apply_context_payload(error_payload, context)

    # Auto-register unregistered documents for EDIT operations (doc_name is the unique identifier)
    elif action in EDIT_ACTIONS and doc_name:
        docs = project.get("docs", {})

        # Check if document is registered
        if doc_name not in docs:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Document '{doc_name}' not registered, attempting auto-registration...")

            try:
                await _auto_register_document(project, doc_name)

                # Re-fetch project data to get updated docs mapping
                # We need to call prepare_context again to get fresh data from database
                try:
                    context = await _MANAGE_DOCS_HELPER.prepare_context(
                        tool_name="manage_docs",
                        agent_id=None,
                        require_project=True,
                        state_snapshot=state_snapshot,
                        reminder_variables={"action": action, "scaffold": scaffold_flag},
                    )
                    project = context.project or {}
                    logger.info(f"Successfully auto-registered and reloaded project context for '{doc_name}'")
                except Exception as reload_error:
                    logger.warning(f"Auto-registration succeeded but context reload failed: {reload_error}")
                    # Continue anyway - the database was updated successfully

            except Exception as e:
                error_payload = _MANAGE_DOCS_HELPER.error_response(
                    f"Auto-registration failed for document '{doc_name}'",
                    suggestion=(
                        f"Ensure the file exists or use 'generate_doc_templates' to create it. "
                        f"Error: {str(e)}"
                    ),
                    extra={"doc_name": doc_name, "auto_registration_error": str(e)},
                )
                return _MANAGE_DOCS_HELPER.apply_context_payload(error_payload, context)

    # Handle unified 'create' action with doc_type routing
    if action == "create":
        doc_type = metadata.get("doc_type", "custom") if isinstance(metadata, dict) else "custom"

        if doc_type == "custom":
            # Route to existing create_doc logic by changing action internally
            action = "create_doc"
            # Fall through to create_doc handler below (line 1611)
        elif doc_type == "research":
            # Route to existing create_research_doc logic
            return await _handle_special_document_creation(
                project,
                action="create_research_doc",
                doc_name=doc_name,
                target_dir=target_dir,
                content=content,
                metadata=metadata,
                dry_run=dry_run,
                agent_id=agent_id,
                storage_backend=backend,
                helper=_MANAGE_DOCS_HELPER,
                context=context,
            )
        elif doc_type == "bug":
            # Route to existing create_bug_report logic
            return await _handle_special_document_creation(
                project,
                action="create_bug_report",
                doc_name=doc_name,
                target_dir=target_dir,
                content=content,
                metadata=metadata,
                dry_run=dry_run,
                agent_id=agent_id,
                storage_backend=backend,
                helper=_MANAGE_DOCS_HELPER,
                context=context,
            )
        elif doc_type == "review":
            # Route to existing create_review_report logic
            return await _handle_special_document_creation(
                project,
                action="create_review_report",
                doc_name=doc_name,
                target_dir=target_dir,
                content=content,
                metadata=metadata,
                dry_run=dry_run,
                agent_id=agent_id,
                storage_backend=backend,
                helper=_MANAGE_DOCS_HELPER,
                context=context,
            )
        elif doc_type == "agent_card":
            # Route to existing create_agent_report_card logic
            return await _handle_special_document_creation(
                project,
                action="create_agent_report_card",
                doc_name=doc_name,
                target_dir=target_dir,
                content=content,
                metadata=metadata,
                dry_run=dry_run,
                agent_id=agent_id,
                storage_backend=backend,
                helper=_MANAGE_DOCS_HELPER,
                context=context,
            )
        else:
            return _MANAGE_DOCS_HELPER.error_response(
                f"Unknown doc_type: {doc_type}",
                suggestion="Valid doc_types: custom, research, bug, review, agent_card"
            )

    # Handle research, bug, review, and agent report card creation
    if action in ["create_research_doc", "create_bug_report", "create_review_report", "create_agent_report_card"]:
        response = await _handle_special_document_creation(
            project,
            action=action,
            doc_name=doc_name,
            target_dir=target_dir,
            content=content,
            metadata=metadata,
            dry_run=dry_run,
            agent_id=agent_id,
            storage_backend=backend,
            helper=_MANAGE_DOCS_HELPER,
            context=context,
        )
        # Add deprecation warning to response if present
        if deprecation_warning:
            response["deprecated"] = deprecation_warning
        return response

    if action == "list_sections":
        if not doc_name:
            response = {"ok": False, "error": "list_sections requires doc_name parameter"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
        return await _handle_list_sections(
            project,
            doc_name=doc_name,
            metadata=metadata,
            helper=_MANAGE_DOCS_HELPER,
            context=context,
        )
    if action == "list_checklist_items":
        if not doc_name:
            response = {"ok": False, "error": "list_checklist_items requires doc_name parameter"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
        return await _handle_list_checklist_items(
            project,
            doc_name=doc_name,
            metadata=metadata if isinstance(metadata, dict) else {},
            helper=_MANAGE_DOCS_HELPER,
            context=context,
        )

    if action == "search":
        search_meta = metadata if isinstance(metadata, dict) else {}
        query = (search_meta.get("query") or search_meta.get("search") or "").strip()
        if not query:
            response = {"ok": False, "error": "search requires metadata.query"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

        search_mode = _normalize_doc_search_mode(search_meta.get("search_mode"))
        if search_mode == "semantic":
            content_type_raw = search_meta.get("content_type")
            content_type = str(content_type_raw).strip().lower() if content_type_raw is not None else "all"
            repo_root = project.get("root")
            if isinstance(repo_root, str):
                repo_root = Path(repo_root)
            if content_type not in {"doc", "log"}:
                enabled_for_doc = _vector_search_enabled(repo_root, "doc")
                enabled_for_log = _vector_search_enabled(repo_root, "log")
                if not (enabled_for_doc or enabled_for_log):
                    response = {
                        "ok": False,
                        "error": "Semantic search disabled or unavailable",
                        "suggestion": "Enable plugin_config.enabled and vector_index_docs/logs, and ensure vector.json enabled",
                    }
                    return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
            elif not _vector_search_enabled(repo_root, content_type):
                response = {
                    "ok": False,
                    "error": "Semantic search disabled or unavailable",
                    "suggestion": "Enable plugin_config.enabled and vector_index_docs/logs, and ensure vector.json enabled",
                }
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

            vector_indexer = _get_vector_indexer()
            if not vector_indexer:
                response = {"ok": False, "error": "Vector indexer plugin not available"}
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

            filters: Dict[str, Any] = {}
            project_slugs = search_meta.get("project_slugs")
            if isinstance(project_slugs, list):
                filters["project_slugs"] = [str(slug).lower().replace(" ", "-") for slug in project_slugs if slug]
            project_slug_prefix = search_meta.get("project_slug_prefix")
            if project_slug_prefix:
                filters["project_slug_prefix"] = str(project_slug_prefix).lower().replace(" ", "-")
            project_slug = search_meta.get("project_slug")
            if project_slug and "project_slugs" not in filters and "project_slug_prefix" not in filters:
                filters["project_slug"] = str(project_slug).lower().replace(" ", "-")

            if search_meta.get("doc_type"):
                filters["doc_type"] = str(search_meta.get("doc_type"))
            if search_meta.get("file_path"):
                filters["file_path"] = str(search_meta.get("file_path"))
            if search_meta.get("time_start") or search_meta.get("time_end"):
                filters["time_range"] = {
                    "start": search_meta.get("time_start"),
                    "end": search_meta.get("time_end"),
                }

            min_similarity = search_meta.get("min_similarity")

            def _apply_similarity_threshold(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                if min_similarity is None:
                    return items
                try:
                    min_val = float(min_similarity)
                except (TypeError, ValueError):
                    return items
                return [r for r in items if r.get("similarity_score", 0) >= min_val]

            limits = _resolve_semantic_limits(search_meta=search_meta, repo_root=repo_root)
            if content_type in {"doc", "log"}:
                if limits["k_override"] is not None:
                    single_k = limits["total_k"]
                elif content_type == "doc":
                    single_k = limits["doc_k_override"] if limits["doc_k_override"] is not None else limits["default_doc_k"]
                else:
                    single_k = limits["log_k_override"] if limits["log_k_override"] is not None else limits["default_log_k"]
                filters["content_type"] = content_type
                results = vector_indexer.search_similar(query, single_k, filters)
                results = _apply_similarity_threshold(results)
                results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
                for item in results:
                    item["content_type"] = content_type
                limits_payload = {
                    "total_k": single_k,
                    "doc_k": single_k if content_type == "doc" else 0,
                    "log_k": single_k if content_type == "log" else 0,
                    "default_doc_k": limits["default_doc_k"],
                    "default_log_k": limits["default_log_k"],
                }
                response = {
                    "ok": True,
                    "action": "search",
                    "search_mode": "semantic",
                    "query": query,
                    "results_count": len(results),
                    "results": results,
                    "filters_applied": filters,
                    "limits": limits_payload,
                }
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

            # Default: search both docs and logs and return combined results.
            base_filters = filters.copy()
            doc_filters = {**base_filters, "content_type": "doc"}
            log_filters = {**base_filters, "content_type": "log"}
            doc_results = _apply_similarity_threshold(
                vector_indexer.search_similar(query, limits["doc_k"], doc_filters)
            )
            log_results = _apply_similarity_threshold(
                vector_indexer.search_similar(query, limits["log_k"], log_filters)
            )
            doc_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            log_results.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            for item in doc_results:
                item["content_type"] = "doc"
            for item in log_results:
                item["content_type"] = "log"
            combined = (doc_results + log_results)[: limits["total_k"]]
            response = {
                "ok": True,
                "action": "search",
                "search_mode": "semantic",
                "query": query,
                "results_count": len(combined),
                "results": combined,
                "results_by_type": {
                    "doc": doc_results,
                    "log": log_results,
                },
                "results_count_by_type": {
                    "doc": len(doc_results),
                    "log": len(log_results),
                },
                "filters_applied": {**base_filters, "content_type": "all"},
                "limits": {
                    "total_k": limits["total_k"],
                    "doc_k": limits["doc_k"],
                    "log_k": limits["log_k"],
                    "default_doc_k": limits["default_doc_k"],
                    "default_log_k": limits["default_log_k"],
                },
            }
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

        # exact/fuzzy searches against doc content
        if not doc_name:
            response = {"ok": False, "error": "search requires doc_name parameter (use '*' or 'all' to search all docs)"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
        targets = _iter_doc_search_targets(project, doc_name)
        if not targets:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

        fuzzy_threshold = float(search_meta.get("fuzzy_threshold", 0.8))
        results: List[Dict[str, Any]] = []
        for doc_key, path in targets:
            try:
                raw_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                parsed = parse_frontmatter(raw_text)
                text = parsed.body
            except ValueError:
                text = raw_text
            matches = _search_doc_lines(
                text=text,
                query=query,
                mode=search_mode,
                fuzzy_threshold=fuzzy_threshold,
            )
            if matches:
                results.append({
                    "doc": doc_key,
                    "path": str(path),
                    "matches": matches,
                })

        response = {
            "ok": True,
            "action": "search",
            "search_mode": search_mode,
            "query": query,
            "results_count": len(results),
            "results": results,
        }
        return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    if action == "batch":
        return await _handle_batch_operations(
            project,
            metadata=metadata,
            helper=_MANAGE_DOCS_HELPER,
            context=context,
        )

    allowed_doc_actions = {
        "replace_section",
        "append",
        "status_update",
        "apply_patch",
        "replace_range",
        "replace_text",
        "normalize_headers",
        "generate_toc",
        "validate_crosslinks",
    }
    if action in allowed_doc_actions:
        allowed_docs = set((project.get("docs") or {}).keys())
        if doc_name not in allowed_docs:
            response = {"ok": False, "error": f"DOC_NOT_FOUND: doc_name '{doc_name}' is not registered"}
            return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    if action == "create_doc" and isinstance(metadata, dict):
        register_existing = bool(metadata.get("register_existing"))
        if register_existing:
            register_key = metadata.get("register_as") or metadata.get("doc_name") or doc_name
            if not register_key:
                response = {
                    "ok": False,
                    "error": "register_existing requires metadata.register_as or metadata.doc_name",
                }
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
            try:
                doc_path = _resolve_create_doc_path(project, metadata, doc_name)
            except Exception as exc:
                response = {"ok": False, "error": f"register_existing failed to resolve path: {exc}"}
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)
            if doc_path.exists():
                docs_mapping = dict(project.get("docs") or {})
                docs_mapping[str(register_key)] = str(doc_path)
                project["docs"] = docs_mapping
                registry_warning = ""
                try:
                    await server_module.state_manager.set_current_project(
                        project.get("name"),
                        project,
                        agent_id=agent_id,
                        mirror_global=False,
                    )
                    # Also persist to database via StorageBackend API
                    backend = getattr(server_module, "storage_backend", None)
                    if backend:
                        import json as _json
                        await backend.update_project_docs(
                            project.get("name"), _json.dumps(docs_mapping)
                        )
                except Exception as exc:
                    registry_warning = f"Registry update failed: {exc}"
                response: Dict[str, Any] = {
                    "ok": True,
                    "doc_name": doc_name,
                    "section": None,
                    "action": action,
                    "path": str(doc_path),
                    "dry_run": dry_run,
                    "diff": "",
                    "warning": "register_existing used; no content was written.",
                }
                if registry_warning:
                    response.setdefault("warnings", []).append(registry_warning)
                return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    # Validate doc_name is provided for document operations
    if not doc_name:
        response = {"ok": False, "error": f"Action '{action}' requires doc_name parameter"}
        return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    try:
        change = await apply_doc_change(
            project,
            doc_name=doc_name,
            doc_category=doc_category,
            action=action,
            section=section,
            content=content,
            patch=patch,
            patch_source_hash=patch_source_hash,
            edit=edit,
            patch_mode=patch_mode,
            start_line=start_line,
            end_line=end_line,
            template=template,
            metadata=metadata,
            dry_run=dry_run,
        )
    except Exception as exc:
        response = {
            "ok": False,
            "error": str(exc),
        }
        return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)

    storage_record = None
    if backend and not dry_run and action != "validate_crosslinks":
        try:
            storage_record = await _get_or_create_storage_project(backend, project)
            await backend.record_doc_change(
                storage_record,
                doc=doc_name,
                section=section,
                action=action,
                agent=agent_id,
                metadata=metadata,
                sha_before=change.before_hash,
                sha_after=change.after_hash,
            )
        except Exception as exc:
            print(f"⚠️  Failed to record doc change in storage: {exc}")
        else:
            # Update Project Registry doc metrics (best-effort, SQLite-first).
            try:
                project_name = project.get("name", "")
                if project_name:
                    _PROJECT_REGISTRY.record_doc_update(
                        project_name,
                        doc_name=doc_name,
                        action=action,
                        before_hash=change.before_hash,
                        after_hash=change.after_hash,
                    )
            except Exception:
                pass

    log_error = None
    index_warning = None
    if not dry_run and action != "validate_crosslinks":
        # Use bulletproof metadata normalization
        healed_metadata, metadata_healed, metadata_messages = _normalize_metadata_with_healing(metadata)
        log_meta = healed_metadata
        log_meta.update(
            {
                "doc_name": doc_name,
                "doc_category": doc_category,
                "section": section or "",
                "action": action,
                "sha_after": change.after_hash,
            }
        )
        try:
            await append_entry(
                message=f"Doc update [{doc_name}] {section or 'full'} via {action}",
                status="info",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
            )
        except Exception as exc:
            log_error = str(exc)

        if change.success and change.path:
            try:
                await _index_doc_for_vector(
                    project=project,
                    doc_name=doc_name,
                    change_path=Path(change.path),
                    after_hash=change.after_hash or "",
                    agent_id=agent_id or "unknown",
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
            except Exception as exc:
                index_warning = str(exc)

    registry_warning = None
    response: Dict[str, Any] = {
        "ok": change.success,
        "action": action,
        "path": str(change.path) if change.success else "",
        "dry_run": dry_run,
        "diff": change.diff_preview,
    }
    # Only include doc_name/section in response when meaningful (not empty)
    if doc_name:
        response["doc_name"] = doc_name
    if section:
        response["section"] = section
    if change.success:
        response["hashes"] = {"before": change.before_hash, "after": change.after_hash}
    if change.extra:
        response["extra"] = change.extra
    if index_warning:
        response["index_warning"] = index_warning

    if change.success:
        repo_root = project.get("root")
        if isinstance(repo_root, str):
            repo_root = Path(repo_root)
        if not _vector_indexing_enabled(repo_root):
            reminders = list(context.reminders)
            reminders.append(
                {
                    "level": "warn",
                    "score": 8,
                    "emoji": "🧭",
                    "message": (
                        "Semantic doc indexing is disabled (vector_index_docs=false). "
                        "Enable it in .scribe/config/scribe.yaml and run "
                        "scripts/reindex_vector.py --docs to build embeddings for managed docs."
                    ),
                    "category": "vector_index_docs",
                    "tone": "strict",
                }
            )
            response["reminders"] = reminders

    if action == "create_doc" and change.success and isinstance(metadata, dict):
        register_doc = metadata.get("register_doc")
        if register_doc is None:
            # Default to registering any created doc unless explicitly disabled
            register_doc = True
        register_doc = bool(register_doc)
        # Priority: explicit register_as > doc_name (unique identifier from param or metadata)
        register_key = metadata.get("register_as") or metadata.get("doc_name") or doc_name
        if register_doc:
            if not register_key:
                return _MANAGE_DOCS_HELPER.apply_context_payload(
                    _MANAGE_DOCS_HELPER.error_response(
                        "register_doc requires metadata.register_as or metadata.doc_name"
                    ),
                    context,
                )
            docs_mapping = dict(project.get("docs") or {})
            docs_mapping[str(register_key)] = str(change.path)
            project["docs"] = docs_mapping
            try:
                await server_module.state_manager.set_current_project(
                    project.get("name"),
                    project,
                    agent_id=agent_id,
                    mirror_global=False,
                )
                # Also persist to database via StorageBackend API
                backend = getattr(server_module, "storage_backend", None)
                if backend:
                    import json as _json
                    await backend.update_project_docs(
                        project.get("name"), _json.dumps(docs_mapping)
                    )
            except Exception as exc:
                registry_warning = f"Registry update failed: {exc}"
            if metadata.get("register_doc") is None:
                response.setdefault("warnings", []).append(
                    "register_doc defaulted to true; set metadata.register_doc=false to skip registration."
                )

    if registry_warning:
        response.setdefault("warnings", []).append(registry_warning)

    # Add error information if operation failed
    if not change.success and change.error_message:
        response["error"] = change.error_message

    # Add verification information
    if not dry_run:
        response["verification_passed"] = change.verification_passed
        response["file_size_before"] = change.file_size_before
        response["file_size_after"] = change.file_size_after

    if log_error:
        response["log_warning"] = log_error

    # Only include full file preview if explicitly requested (token-heavy!)
    # The diff + preview_windows already provide sufficient context
    include_full_preview = bool(
        isinstance(metadata, dict) and metadata.get("include_full_preview")
    )
    if dry_run and include_full_preview:
        preview_content = change.content_written
        include_frontmatter = bool(
            isinstance(metadata, dict) and metadata.get("include_frontmatter_preview")
        )
        if preview_content and not include_frontmatter:
            try:
                while True:
                    parsed_preview = parse_frontmatter(preview_content)
                    if not parsed_preview.has_frontmatter:
                        break
                    preview_content = parsed_preview.body
                    if not preview_content.lstrip().startswith("---"):
                        break
            except Exception:
                pass
        response["preview"] = preview_content

    # Add deprecation warning to response if present
    if deprecation_warning:
        response["deprecated"] = deprecation_warning

    return _MANAGE_DOCS_HELPER.apply_context_payload(response, context)


def manage_docs_main():
    """CLI entry point for manage_docs functionality."""
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    async def _run_manage_docs(args):
        """Run manage_docs with provided CLI arguments."""
        try:
            result = await manage_docs(
                action=args.action,
                doc=args.doc,
                section=args.section,
                content=args.content,
                patch=args.patch,
                patch_source_hash=args.patch_source_hash,
                edit=args.edit,
                patch_mode=args.patch_mode,
                start_line=args.start_line,
                end_line=args.end_line,
                template=args.template,
                metadata=args.metadata,
                dry_run=args.dry_run,
            )

            if result.get("ok"):
                if "error_message" in result and result["error_message"]:
                    print(f"⚠️  Operation completed with warnings: {result['error_message']}")
                else:
                    print(f"✅ {result.get('message', 'Documentation updated successfully')}")

                if args.dry_run:
                    print("🔍 Dry run - no changes made")
                    if "preview" in result:
                        print("\nPreview:")
                        print(result["preview"])

                # Show verification status
                if "verification_passed" in result:
                    if result["verification_passed"]:
                        print("✅ File write verification passed")
                    else:
                        print("❌ File write verification failed")

                return 0
            else:
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
                return 1

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return 1

    parser = argparse.ArgumentParser(
        description="Manage project documentation with structured updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Replace a section in architecture guide
  manage_docs replace_section architecture directory_structure --template directory_structure

  # Update checklist status
  manage_docs status_update checklist phase_0 --metadata status=done proof=commit_123

  # Append content to document
  manage_docs append phase_plan --content "New phase details here"
        """
    )

    parser.add_argument(
        "action",
        choices=[
            "replace_section",
            "append",
            "status_update",
            "apply_patch",
            "replace_range",
            "list_sections",
            "list_checklist_items",
            "batch",
            "create_research_doc",
            "create_bug_report",
            "create_review_report",
            "create_agent_report_card",
        ],
        help="Action to perform on the document"
    )

    parser.add_argument(
        "doc",
        choices=["architecture", "phase_plan", "checklist", "progress_log", "doc_log", "security_log", "bug_log"],
        help="Document to modify"
    )

    parser.add_argument(
        "--section",
        help="Section ID (required for replace_section and status_update)"
    )

    parser.add_argument(
        "--content",
        help="Content to add/replace"
    )

    parser.add_argument(
        "--patch",
        help="Unified diff patch to apply"
    )

    parser.add_argument(
        "--patch-source-hash",
        help="SHA256 hash of the file content used to generate the patch"
    )

    parser.add_argument(
        "--edit",
        help="Structured edit payload as JSON string"
    )

    parser.add_argument(
        "--patch-mode",
        help="Patch mode for apply_patch (structured or unified)"
    )

    parser.add_argument(
        "--start-line",
        type=int,
        help="Start line (1-based) for replace_range"
    )

    parser.add_argument(
        "--end-line",
        type=int,
        help="End line (1-based) for replace_range"
    )

    parser.add_argument(
        "--template",
        help="Template fragment to use (from templates/fragments/)"
    )

    parser.add_argument(
        "--metadata",
        type=str,
        help="Metadata as JSON string (e.g., '{\"status\": \"done\", \"proof\": \"commit_123\"}')"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.action in ["replace_section", "status_update"] and not args.section:
        print("❌ Error: --section is required for replace_section and status_update actions")
        return 1

    if args.action == "apply_patch" and not (args.patch or args.content):
        if not args.edit:
            print("❌ Error: --edit is required for apply_patch structured mode")
            return 1

    if args.action == "apply_patch" and (args.patch or args.content) and not args.patch_mode:
        print("❌ Error: --patch-mode is required when providing a patch")
        return 1
    if args.action == "apply_patch" and args.patch_mode and args.patch_mode not in {"structured", "unified"}:
        print("❌ Error: --patch-mode must be 'structured' or 'unified'")
        return 1

    if args.action == "replace_range" and (args.start_line is None or args.end_line is None):
        print("❌ Error: --start-line and --end-line are required for replace_range")
        return 1

    if args.action not in ["apply_patch", "replace_range", "create_doc", "validate_crosslinks", "normalize_headers", "generate_toc"] and not args.content and not args.template:
        print("❌ Error: Either --content or --template must be provided")
        return 1

    # Parse metadata if provided
    metadata = None
    if args.metadata:
        try:
            import json
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in metadata: {args.metadata}")
            return 1

    edit = None
    if args.edit:
        try:
            import json
            edit = json.loads(args.edit)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in edit payload: {args.edit}")
            return 1

    # Run the operation
    args.edit = edit
    args.patch_mode = args.patch_mode
    return asyncio.run(_run_manage_docs(args))


async def _handle_list_sections(
    project: Dict[str, Any],
    doc_name: str,
    metadata: Optional[Dict[str, Any]],
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    """Return the list of section anchors for a document."""
    docs_mapping = project.get("docs") or {}
    path_str = docs_mapping.get(doc_name)
    if not path_str:
        # Try auto-registration before returning error
        from doc_management.manager import _resolve_doc_path
        from tools.get_project import get_active_project
        from storage import get_storage
        import json

        print(f"DEBUG: Attempting auto-registration for doc_name='{doc_name}', project='{project.get('name')}'")
        try:
            resolved_path = _resolve_doc_path(project, doc_name)
            print(f"DEBUG: Resolved path: {resolved_path}, exists: {resolved_path.exists()}")
            if resolved_path.exists():
                # Auto-register the document by updating docs_json in database
                project_name = project.get("name")
                storage = await get_storage()

                # Get current docs mapping and add new document
                current_docs = project.get("docs") or {}
                current_docs[doc_name] = str(resolved_path)

                # Update database directly
                docs_json = json.dumps(current_docs)
                await storage._execute(
                    "UPDATE scribe_projects SET docs_json = ? WHERE name = ?",
                    (docs_json, project_name)
                )

                # Refresh project state and retry
                project = await get_active_project()
                docs_mapping = project.get("docs") or {}
                path_str = docs_mapping.get(doc_name)
        except Exception as e:
            # If auto-registration fails, fall through to error
            import traceback
            print(f"DEBUG: Auto-registration failed: {e}")
            traceback.print_exc()
            pass

        # If still not registered, return error
        if not path_str:
            return helper.apply_context_payload(
                helper.error_response(f"Document '{doc_name}' is not registered for project '{project.get('name')}'."),
                context,
            )

    path = Path(path_str)
    if not path.exists():
        return helper.apply_context_payload(
            helper.error_response(f"Document path '{path}' does not exist."),
            context,
        )

    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    parsed = parse_frontmatter(text)
    body_lines = parsed.body.splitlines()
    body_line_offset = len(parsed.frontmatter_raw.splitlines()) if parsed.has_frontmatter else 0
    sections: List[Dict[str, Any]] = []
    duplicates: Dict[str, List[int]] = {}
    for line_no, line in enumerate(body_lines, start=1):
        stripped = line.strip()
        if stripped.startswith("<!-- ID:") and stripped.endswith("-->"):
            section_id = stripped[len("<!-- ID:"): -len("-->")].strip()
            duplicates.setdefault(section_id, []).append(line_no)
            sections.append(
                {
                    "id": section_id,
                    "line": line_no,
                    "file_line": line_no + body_line_offset,
                }
            )
    duplicate_sections = {
        section_id: lines for section_id, lines in duplicates.items() if len(lines) > 1
    }

    # Apply pagination if requested
    page = metadata.get("page", 1) if metadata else 1
    page_size = metadata.get("page_size", 50) if metadata else 50
    total_count = len(sections)
    start_idx, end_idx = PaginationCalculator.calculate_pagination_indices(page, page_size, total_count)
    paginated_sections = sections[start_idx:end_idx]

    response = {
        "ok": True,
        "doc_name": doc_name,
        "path": str(path),
        "sections": paginated_sections,
        "body_line_offset": body_line_offset,
        "frontmatter_line_count": body_line_offset,
        "hint": f"For full document structure, use: read_file(path='{path}', mode='scan_only')",
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "has_next": end_idx < total_count,
            "has_prev": page > 1,
        },
    }
    if duplicate_sections:
        response["duplicates"] = duplicate_sections
        response["warning"] = (
            "Duplicate section anchors detected; use apply_patch or fix anchors before replace_section."
        )
    return helper.apply_context_payload(response, context)


async def _handle_list_checklist_items(
    project: Dict[str, Any],
    doc_name: str,
    metadata: Dict[str, Any],
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    """Return checklist items with line numbers for replace_range usage."""
    docs_mapping = project.get("docs") or {}
    path_str = docs_mapping.get(doc_name)
    if not path_str:
        return helper.apply_context_payload(
            helper.error_response(f"Document '{doc_name}' is not registered for project '{project.get('name')}'."),
            context,
        )

    path = Path(path_str)
    if not path.exists():
        return helper.apply_context_payload(
            helper.error_response(f"Document path '{path}' does not exist."),
            context,
        )

    if doc_name != "checklist":
        return helper.apply_context_payload(
            helper.error_response("list_checklist_items is only supported for checklist documents."),
            context,
        )

    query_text = metadata.get("text")
    case_sensitive = metadata.get("case_sensitive", True)
    require_match = metadata.get("require_match", False)

    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    parsed = parse_frontmatter(text)
    body_lines = parsed.body.splitlines()
    body_line_offset = len(parsed.frontmatter_raw.splitlines()) if parsed.has_frontmatter else 0
    items: List[Dict[str, Any]] = []
    matches: List[Dict[str, Any]] = []
    pattern = re.compile(r"^- \[(?P<mark>[ xX])\]\s*(?P<text>.*)$")
    section_id = None
    duplicates: Dict[str, List[int]] = {}

    for line_no, line in enumerate(body_lines, start=1):
        stripped = line.strip()
        if stripped.startswith("<!-- ID:") and stripped.endswith("-->"):
            section_id = stripped[len("<!-- ID:"): -len("-->")].strip()
            duplicates.setdefault(section_id, []).append(line_no)
            continue

        match = pattern.match(stripped)
        if not match:
            continue
        item_text = match.group("text")
        status = "checked" if match.group("mark").lower() == "x" else "unchecked"
        entry = {
            "line": line_no,
            "start_line": line_no,
            "end_line": line_no,
            "file_line": line_no + body_line_offset,
            "status": status,
            "text": item_text,
            "raw": line,
            "section": section_id,
        }
        items.append(entry)
        if query_text is None:
            matches.append(entry)
        else:
            if case_sensitive:
                if item_text == query_text:
                    matches.append(entry)
            else:
                if item_text.lower() == str(query_text).lower():
                    matches.append(entry)

    if require_match and query_text and not matches:
        return helper.apply_context_payload(
            helper.error_response(f"No checklist items matched text: {query_text}"),
            context,
        )

    # Apply pagination if requested
    page = metadata.get("page", 1) if metadata else 1
    page_size = metadata.get("page_size", 20) if metadata else 20
    total_items_count = len(items)
    total_matches_count = len(matches)

    # Paginate items
    start_idx, end_idx = PaginationCalculator.calculate_pagination_indices(page, page_size, total_items_count)
    paginated_items = items[start_idx:end_idx]

    # Paginate matches separately if filtering
    match_start, match_end = PaginationCalculator.calculate_pagination_indices(page, page_size, total_matches_count)
    paginated_matches = matches[match_start:match_end]

    response = {
        "ok": True,
        "doc": doc_name,
        "path": str(path),
        "total_items": total_items_count,
        "items": paginated_items,
        "matches": paginated_matches,
        "body_line_offset": body_line_offset,
        "frontmatter_line_count": body_line_offset,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items_count,
            "total_matches": total_matches_count,
            "has_next": end_idx < total_items_count,
            "has_prev": page > 1,
        },
    }
    duplicate_sections = {
        section: lines for section, lines in duplicates.items() if len(lines) > 1
    }
    if duplicate_sections:
        response["duplicates"] = duplicate_sections
        response["warning"] = (
            "Duplicate section anchors detected; checklist items may map to ambiguous sections."
        )
    return helper.apply_context_payload(response, context)


async def _handle_batch_operations(
    project: Dict[str, Any],
    metadata: Optional[Dict[str, Any]],
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    """Execute a batch of manage_docs operations sequentially."""
    if not metadata or not isinstance(metadata, dict):
        return helper.apply_context_payload(
            helper.error_response("Batch action requires metadata with an 'operations' list."),
            context,
        )

    operations = metadata.get("operations")
    if not isinstance(operations, list):
        return helper.apply_context_payload(
            helper.error_response("Batch metadata must include an 'operations' list."),
            context,
        )

    results: List[Dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            return helper.apply_context_payload(
                helper.error_response(f"Batch operation at index {index} is not a valid object."),
                context,
            )
        if operation.get("action") == "batch":
            return helper.apply_context_payload(
                helper.error_response("Nested batch operations are not supported."),
                context,
            )
        batch_result = await manage_docs(**operation)
        results.append({"index": index, "result": batch_result})
        if not batch_result.get("ok"):
            return helper.apply_context_payload(
                {
                    "ok": False,
                    "error": f"Batch operation {index} failed",
                    "results": results,
                },
                context,
            )

    return helper.apply_context_payload(
        {
            "ok": True,
            "results": results,
        },
        context,
    )


async def _handle_special_document_creation(
    project: Dict[str, Any],
    action: str,
    doc_name: Optional[str],
    target_dir: Optional[str],
    content: Optional[str],
    metadata: Optional[Dict[str, Any]],
    dry_run: bool,
    agent_id: str,
    storage_backend: Any,
    helper: LoggingToolMixin,
    context: LoggingContext,
) -> Dict[str, Any]:
    """Handle creation of research, bug, review, and agent report card documents with Phase 1 exception healing."""
    # Apply Phase 1 exception healing to metadata
    healed_metadata, metadata_healed, metadata_messages = _normalize_metadata_with_healing(metadata)
    metadata = healed_metadata

    project_root = Path(project.get("root", ""))
    # Use actual docs_dir from project configuration (not hardcoded path)
    docs_dir_str = project.get("docs_dir", "")
    docs_dir = Path(docs_dir_str) if docs_dir_str else Path("")
    # Fallback if docs_dir not in project (shouldn't happen in practice)
    if not docs_dir or str(docs_dir) == "" or str(docs_dir) == ".":
        # Use slugified project name to match canonical folder structure (underscores, not hyphens)
        project_slug = slugify_project_name(project.get("name", ""))
        docs_dir = project_root / ".scribe" / "docs" / "dev_plans" / project_slug
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    template_name = ""
    doc_label = ""
    target_path: Optional[Path] = None
    index_updater: Optional[Callable[[], Awaitable[None]]] = None
    index_path: Optional[Path] = None
    extra_metadata: Dict[str, Any] = {}
    placement_warning: Optional[str] = None  # Set if research doc placement doesn't match PROGRESS_LOG

    if action == "create_research_doc":
        if not doc_name:
            return helper.apply_context_payload(
                helper.error_response(
                    "doc_name is required for research document creation",
                ),
                context,
            )
        # Sanitize the doc_name for filesystem safety
        import re
        # Replace spaces and special chars with underscores, keep alphanumeric and basic symbols
        safe_name = re.sub(r'[^\w\-_\.]', '_', doc_name)
        # Remove multiple consecutive underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        # Ensure it's not empty after sanitization
        if not safe_name:
            safe_name = f"research_{int(datetime.now().timestamp())}"

        # Support target_dir override for placing research docs outside default location
        override_dir = target_dir or metadata.get("target_dir")

        if override_dir:
            # User explicitly specified a custom location - use it
            research_dir = Path(override_dir)
            if not research_dir.is_absolute():
                research_dir = project_root / research_dir
        else:
            # Default: place in project's research folder
            research_dir = docs_dir / "research"

            # Verify placement aligns with PROGRESS_LOG location
            progress_log_path = project.get("progress_log", "")
            if progress_log_path:
                progress_log_dir = Path(progress_log_path).parent
                # Research should be sibling to PROGRESS_LOG (in same dev_plans/<project>/ folder)
                expected_parent = progress_log_dir
                actual_parent = docs_dir

                # Normalize paths for comparison
                try:
                    expected_resolved = expected_parent.resolve()
                    actual_resolved = actual_parent.resolve()
                    if expected_resolved != actual_resolved:
                        placement_warning = (
                            f"Research doc will be created in '{actual_resolved}/research/' "
                            f"but PROGRESS_LOG is in '{expected_resolved}'. "
                            f"Use target_dir parameter or metadata.target_dir to override placement."
                        )
                except Exception:
                    pass  # Path resolution failed, skip warning

        target_path = research_dir / f"{safe_name}.md"
        template_name = "RESEARCH_REPORT_TEMPLATE.md"
        doc_label = "research_report"
        extra_metadata = {
            "title": doc_name.replace("_", " ").title(),
            "doc_name": safe_name,
            "researcher": metadata.get("researcher", agent_id),
        }
        index_updater = lambda: _update_research_index(research_dir, agent_id)
        index_path = research_dir / "INDEX.md"
    elif action == "create_bug_report":
        category = metadata.get("category")
        if not category or not category.strip():
            return helper.apply_context_payload(
                helper.error_response(
                    "metadata with non-empty 'category' is required for bug report creation",
                ),
                context,
            )

        # Sanitize category
        import re
        category = re.sub(r'[^\w\-_\.]', '_', category.strip())

        slug = metadata.get("slug")
        if slug:
            # Sanitize slug as well
            slug = re.sub(r'[^\w\-_\.]', '_', str(slug).strip())
        if not slug:
            slug = f"bug_{int(now.timestamp())}"
        bug_dir = project_root / "docs" / "bugs" / category / f"{now.strftime('%Y-%m-%d')}_{slug}"
        target_path = bug_dir / "report.md"
        template_name = "BUG_REPORT_TEMPLATE.md"
        doc_label = "bug_report"
        extra_metadata = {
            "slug": slug,
            "category": category,
            "reported_at": metadata.get("reported_at", timestamp_str),
        }
        index_updater = lambda: _update_bug_index(project_root / "docs" / "bugs", agent_id)
        index_path = project_root / "docs" / "bugs" / "INDEX.md"
    elif action == "create_review_report":
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"REVIEW_REPORT_{stage}_{now.strftime('%Y-%m-%d')}_{now.strftime('%H%M')}.md"
        template_name = "REVIEW_REPORT_TEMPLATE.md"
        doc_label = "review_report"
        extra_metadata = {"stage": stage}
        index_updater = lambda: _update_review_index(docs_dir, agent_id)
        index_path = docs_dir / "REVIEW_INDEX.md"
    elif action == "create_agent_report_card":
        card_agent = metadata.get("agent_name", agent_id)
        stage = metadata.get("stage", "unknown")
        target_path = docs_dir / f"AGENT_REPORT_CARD_{card_agent}_{stage}_{now.strftime('%Y%m%d_%H%M')}.md"
        template_name = "AGENT_REPORT_CARD_TEMPLATE.md"
        doc_label = "agent_report_card"
        extra_metadata = {
            "agent_name": card_agent,
            "stage": stage,
        }
        index_updater = lambda: _update_agent_card_index(docs_dir, agent_id)
        index_path = docs_dir / "AGENT_CARDS_INDEX.md"
    else:
        return helper.apply_context_payload(
            helper.error_response(f"Unsupported special document action: {action}"),
            context,
        )

    prepared_metadata = _build_special_metadata(project, metadata, agent_id, extra_metadata)

    rendered_content = content
    if not rendered_content:
        try:
            if action == "create_review_report":
                rendered_content = await _render_review_report_template(
                    project,
                    agent_id,
                    prepared_metadata,
                )
            elif action == "create_agent_report_card":
                rendered_content = await _render_agent_report_card_template(
                    project,
                    agent_id,
                    prepared_metadata,
                )
            else:
                rendered_content = await _render_special_template(
                    project,
                    agent_id,
                    template_name,
                    metadata,
                    extra_metadata=extra_metadata,
                    prepared_metadata=prepared_metadata,
                )
        except DocumentOperationError as exc:
            return helper.apply_context_payload(
                helper.error_response(str(exc)),
                context,
            )

    if rendered_content is None:
        return helper.apply_context_payload(
            helper.error_response("Failed to render document content."),
            context,
        )

    try:
        target_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return helper.apply_context_payload(
            helper.error_response(
                f"Generated document path {target_path} is outside project root",
            ),
            context,
        )

    if dry_run:
        return helper.apply_context_payload(
            {
                "ok": True,
                "dry_run": True,
                "path": str(target_path),
                "content": rendered_content,
            },
            context,
        )

    before_hash = ""
    if target_path.exists():
        try:
            before_hash = _hash_text(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            before_hash = ""

    log_warning: Optional[str] = None

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(rendered_content, encoding="utf-8")

        after_hash = _hash_text(rendered_content)

        await _record_special_doc_change(
            storage_backend,
            project,
            agent_id,
            doc_label,
            target_path,
            prepared_metadata,
            before_hash,
            after_hash,
        )
        if doc_label == "agent_report_card": # Alias for Doc Category
            await _record_agent_report_card_metadata(
                storage_backend,
                project,
                agent_id,
                target_path,
                prepared_metadata,
            )

        healed_metadata, metadata_healed, metadata_messages = _normalize_metadata_with_healing(prepared_metadata)
        log_meta = healed_metadata
        log_meta.update(
            {
                "doc": doc_label,
                "section": "",
                "action": "create",
                "document_type": doc_label,
                "file_path": str(target_path),
                "file_size": target_path.stat().st_size,
            }
        )
        for key, value in list(log_meta.items()):
            if isinstance(value, (dict, list)):
                try:
                    log_meta[key] = json.dumps(value, sort_keys=True)
                except (TypeError, ValueError):
                    log_meta[key] = str(value)

        try:
            await append_entry(
                message=f"Created {doc_label.replace('_', ' ')}: {target_path.name}",
                status="success",
                meta=log_meta,
                agent=agent_id,
                log_type="doc_updates",
            )
        except Exception as exc:
            log_warning = str(exc)

        if index_updater:
            try:
                await index_updater()
            except Exception as exc:
                print(f"⚠️ Failed to update index for {doc_label}: {exc}")
                # Don't fail the whole operation if index update fails
                # The document was created successfully, just the index is stale

        # Register the newly created document in docs_json so manage_docs can find it later
        registration_warning: Optional[str] = None
        if storage_backend and project:
            try:
                project_name = project.get("name")
                if project_name:
                    # Build unique doc key from label and filename (without extension)
                    doc_key = f"{doc_label}_{target_path.stem}"

                    # Get current docs mapping
                    current_docs = project.get("docs", {})
                    current_docs[doc_key] = str(target_path)
                    docs_json = json.dumps(current_docs)

                    # Update database via StorageBackend API
                    await storage_backend.update_project_docs(project_name, docs_json)

                    # Update in-memory registry
                    try:
                        _PROJECT_REGISTRY.record_doc_update(
                            project_name=project_name,
                            doc=doc_key,
                            action="create",
                            before_hash=None,
                            after_hash=after_hash,
                        )
                    except Exception as reg_exc:
                        # Non-fatal - registry update is best-effort
                        registration_warning = f"Registry update failed: {reg_exc}"
            except Exception as exc:
                registration_warning = f"Doc registration failed: {exc}"
                # Don't fail the whole operation - file was created successfully

        # Also register the INDEX file if it exists (created by index_updater)
        if storage_backend and project and index_path and index_path.exists():
            try:
                project_name = project.get("name")
                if project_name:
                    # Build index doc key based on doc type
                    index_key = f"{doc_label}_index"

                    # Get current docs mapping (may have been updated above)
                    current_project = await storage_backend.fetch_project(project_name)
                    if current_project and current_project.docs_json:
                        current_docs = json.loads(current_project.docs_json)
                    else:
                        current_docs = project.get("docs", {})

                    current_docs[index_key] = str(index_path)
                    docs_json = json.dumps(current_docs)

                    await storage_backend.update_project_docs(project_name, docs_json)
            except Exception as exc:
                # Non-fatal - index registration is best-effort
                if registration_warning:
                    registration_warning += f"; Index registration failed: {exc}"
                else:
                    registration_warning = f"Index registration failed: {exc}"

        success_payload: Dict[str, Any] = {
            "ok": True,
            "path": str(target_path),
            "document_type": doc_label,
            "file_size": target_path.stat().st_size,
        }
        if log_warning:
            success_payload["log_warning"] = log_warning
        if registration_warning:
            success_payload["registration_warning"] = registration_warning
        if placement_warning:
            success_payload["placement_warning"] = placement_warning

        return helper.apply_context_payload(success_payload, context)

    except Exception as exc:
        return helper.apply_context_payload(
            helper.error_response(f"Failed to create document: {exc}"),
            context,
        )


async def _update_research_index(research_dir: Path, agent_id: str) -> None:
    """Update the research INDEX.md file."""
    from datetime import datetime
    index_path = research_dir / "INDEX.md"

    # Self-healing: validate and repair index if needed
    if not _validate_and_repair_index(index_path, research_dir):
        print(f"🔧 Auto-repairing research index for {research_dir.name}")

    # Get all research documents
    research_docs = []
    if research_dir.exists():
        # Look for all .md files except INDEX.md and any template files
        for doc_path in research_dir.glob("*.md"):
            if doc_path.name != "INDEX.md" and not doc_path.name.startswith("_"):
                stat = doc_path.stat()
                research_docs.append({
                    "name": doc_path.stem,
                    "path": doc_path.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })

    # Generate INDEX content
    content = f"""# Research Documents Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains research documents generated during the development process.

## Available Research Documents

"""

    if research_docs:
        # Sort by modification time (newest first)
        research_docs.sort(key=lambda x: x["modified"], reverse=True)

        for doc in research_docs:
            modified_time = datetime.fromtimestamp(doc["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{doc['name']}]({doc['path']})** - {modified_time} ({doc['size']} bytes)\n"
    else:
        content += "*No research documents found.*\n"

    content += f"""

## Index Information

- **Total Documents:** {len(research_docs)}
- **Index Location:** `{index_path.relative_to(research_dir.parent.parent)}`

---

*This index is automatically updated when research documents are created or modified.*"""

    # Write the index atomically
    if not _write_file_atomically(index_path, content):
        print(f"⚠️ Failed to update research index at {index_path}")


async def _update_bug_index(bugs_dir: Path, agent_id: str) -> None:
    """Update the main bugs INDEX.md file."""
    from datetime import datetime
    index_path = bugs_dir / "INDEX.md"

    # Get all bug reports
    bug_reports = []
    if bugs_dir.exists():
        for category_dir in bugs_dir.iterdir():
            if category_dir.is_dir() and category_dir.name != "archived":
                for bug_dir in category_dir.iterdir():
                    if bug_dir.is_dir():
                        report_path = bug_dir / "report.md"
                        if report_path.exists():
                            stat = report_path.stat()
                            bug_reports.append({
                                "category": category_dir.name,
                                "slug": bug_dir.name,
                                "path": str(report_path.relative_to(bugs_dir)),
                                "size": stat.st_size,
                                "modified": stat.st_mtime,
                            })

    # Generate INDEX content
    content = f"""# Bug Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains bug reports generated during development and testing.

## Bug Statistics

- **Total Reports:** {len(bug_reports)}
- **Categories:** {len(set(report['category'] for report in bug_reports))}

## Recent Bug Reports

"""

    if bug_reports:
        # Sort by modification time (newest first)
        bug_reports.sort(key=lambda x: x["modified"], reverse=True)

        for bug in bug_reports[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(bug["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{bug['category']}/{bug['slug']}]({bug['path']})** - {modified_time}\n"

        if len(bug_reports) > 20:
            content += f"\n*... and {len(bug_reports) - 20} older reports*\n"
    else:
        content += "*No bug reports found.*\n"

    content += f"""

## Browse by Category

"""

    # Group by category
    categories = {}
    for bug in bug_reports:
        if bug["category"] not in categories:
            categories[bug["category"]] = []
        categories[bug["category"]].append(bug)

    for category, bugs in sorted(categories.items()):
        content += f"### {category.title()} ({len(bugs)} reports)\n"
        for bug in bugs[:5]:  # Show first 5 per category
            content += f"- [{bug['slug']}]({bug['path']})\n"
        if len(bugs) > 5:
            content += f"- ... and {len(bugs) - 5} more\n"
        content += "\n"

    content += f"""
---

## Index Information

- **Index Location:** `{index_path}`
- **Total Categories:** {len(categories)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when bug reports are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _update_review_index(docs_dir: Path, agent_id: str) -> None:
    """Update the review reports INDEX.md file."""
    from datetime import datetime
    index_path = docs_dir / "REVIEW_INDEX.md"

    # Get all review reports
    review_reports = []
    for review_file in docs_dir.glob("REVIEW_REPORT_*.md"):
        if review_file.name != "REVIEW_INDEX.md":
            stat = review_file.stat()
            # Extract stage from filename
            try:
                # Format: REVIEW_REPORT_Stage3_2025-10-31_1203.md
                parts = review_file.stem.split('_')
                stage = parts[2] if len(parts) > 2 else "unknown"
                review_reports.append({
                    "name": review_file.stem,
                    "path": review_file.name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except:
                continue

    # Generate INDEX content
    content = f"""# Review Reports Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains review reports generated during the development quality assurance process.

## Review Statistics

- **Total Reports:** {len(review_reports)}
- **Stages Reviewed:** {len(set(report['stage'] for report in review_reports))}

## Recent Review Reports

"""

    if review_reports:
        # Sort by modification time (newest first)
        review_reports.sort(key=lambda x: x["modified"], reverse=True)

        for report in review_reports[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(report["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{report['name']}]({report['path']})** - {report['stage']} - {modified_time}\n"

        if len(review_reports) > 20:
            content += f"\n*... and {len(review_reports) - 20} older reports*\n"
    else:
        content += "*No review reports found.*\n"

    content += f"""

## Browse by Stage

"""

    # Group by stage
    stages = {}
    for report in review_reports:
        if report["stage"] not in stages:
            stages[report["stage"]] = []
        stages[report["stage"]].append(report)

    for stage, reports in sorted(stages.items()):
        content += f"### {stage.title()} ({len(reports)} reports)\n"
        for report in reports[:5]:  # Show first 5 per stage
            content += f"- [{report['name']}]({report['path']})\n"
        if len(reports) > 5:
            content += f"- ... and {len(reports) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Stages:** {len(stages)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when review reports are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _update_agent_card_index(docs_dir: Path, agent_id: str) -> None:
    """Update the agent report cards INDEX.md file."""
    from datetime import datetime
    index_path = docs_dir / "AGENT_CARDS_INDEX.md"

    # Get all agent report cards
    agent_cards = []
    for card_file in docs_dir.glob("AGENT_REPORT_CARD_*.md"):
        if card_file.name != "AGENT_CARDS_INDEX.md":
            stat = card_file.stat()
            # Extract agent name from filename
            try:
                # Format: AGENT_REPORT_CARD_ResearchAnalyst_Stage3_20251031_1203.md
                parts = card_file.stem.split('_')
                agent_name = parts[3] if len(parts) > 3 else "unknown"
                stage = parts[4] if len(parts) > 4 else "unknown"
                agent_cards.append({
                    "name": card_file.stem,
                    "path": card_file.name,
                    "agent": agent_name,
                    "stage": stage,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                })
            except:
                continue

    # Generate INDEX content
    content = f"""# Agent Report Cards Index

*Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}*

This directory contains agent performance evaluation reports generated during the development process.

## Agent Statistics

- **Total Reports:** {len(agent_cards)}
- **Agents Evaluated:** {len(set(report['agent'] for report in agent_cards))}
- **Stages Covered:** {len(set(report['stage'] for report in agent_cards))}

## Recent Agent Evaluations

"""

    if agent_cards:
        # Sort by modification time (newest first)
        agent_cards.sort(key=lambda x: x["modified"], reverse=True)

        for card in agent_cards[:20]:  # Show last 20
            modified_time = datetime.fromtimestamp(card["modified"]).strftime("%Y-%m-%d %H:%M")
            content += f"- **[{card['name']}]({card['path']})** - {card['agent']} - {card['stage']} - {modified_time}\n"

        if len(agent_cards) > 20:
            content += f"\n*... and {len(agent_cards) - 20} older evaluations*\n"
    else:
        content += "*No agent report cards found.*\n"

    content += f"""

## Browse by Agent

"""

    # Group by agent
    agents = {}
    for card in agent_cards:
        if card["agent"] not in agents:
            agents[card["agent"]] = []
        agents[card["agent"]].append(card)

    for agent, cards in sorted(agents.items()):
        content += f"### {agent} ({len(cards)} evaluations)\n"
        for card in cards[:5]:  # Show first 5 per agent
            content += f"- [{card['name']}]({card['path']})\n"
        if len(cards) > 5:
            content += f"- ... and {len(cards) - 5} more\n"
        content += "\n"

    content += f"""

## Index Information

- **Index Location:** `{index_path}`
- **Total Agents:** {len(agents)}
- **Last Scan:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}

---

*This index is automatically updated when agent report cards are created or modified.*"""

    # Write the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(content)


async def _render_review_report_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Render review report using Jinja2 template."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        # Initialize template engine
        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox"
        )

        # Prepare template context
        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        # Render template
        rendered = engine.render_template(
            template_name="REVIEW_REPORT_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for review report: {e}")
        # Fallback to basic content if template engine fails
        stage = prepared_metadata.get("stage", "unknown")
        overall_decision = prepared_metadata.get("overall_decision", "[PENDING]")
        final_decision = prepared_metadata.get("final_decision", overall_decision)
        return f"""# Review Report: {stage.replace('_', ' ').title()} Stage

**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Decision:** {overall_decision}

---

<!-- ID: final_decision -->
## Final Decision

**{final_decision}**

*This review report is part of the quality assurance process for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering review report template: {e}")
        raise DocumentOperationError(f"Failed to render review report template: {e}")


async def _render_agent_report_card_template(
    project: Dict[str, Any],
    agent_id: str,
    prepared_metadata: Dict[str, Any],
) -> str:
    """Render agent report card using Jinja2 template."""
    try:
        from scribe_mcp.template_engine import Jinja2TemplateEngine, TemplateEngineError

        # Initialize template engine
        engine = Jinja2TemplateEngine(
            project_root=Path(project.get("root", "")),
            project_name=project.get("name", ""),
            security_mode="sandbox"
        )

        # Prepare template context
        template_context = prepared_metadata.copy()
        template_context.setdefault("project_name", project.get("name", ""))
        template_context.setdefault("agent_id", agent_id)
        template_context.setdefault("timestamp", _current_timestamp())
        template_context.setdefault("agent_name", prepared_metadata.get("agent_name", agent_id))
        template_context.setdefault("stage", prepared_metadata.get("stage", "unknown"))

        # Render template
        rendered = engine.render_template(
            template_name="AGENT_REPORT_CARD_TEMPLATE.md",
            metadata=template_context
        )

        return rendered

    except (TemplateEngineError, ImportError) as e:
        print(f"⚠️ Template engine error for agent report card: {e}")
        # Fallback to basic content if template engine fails
        agent_name = prepared_metadata.get("agent_name", agent_id)
        stage = prepared_metadata.get("stage", "unknown")
        overall_grade = prepared_metadata.get("overall_grade", "[PENDING]")
        final_recommendation = prepared_metadata.get("final_recommendation", "[PENDING]")
        return f"""# Agent Performance Report Card

**Agent:** {agent_name}
**Review Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}
**Reviewer:** {agent_id}
**Project:** {project.get('name')}
**Stage:** {stage}

---

<!-- ID: executive_summary -->
## Executive Summary

**Overall Grade:** {overall_grade}

---

<!-- ID: final_assessment -->
## Final Assessment

**Overall Recommendation:** {final_recommendation}

*This agent report card is part of the performance management system for {project.get('name')}.*
"""
    except Exception as e:
        print(f"❌ Unexpected error rendering agent report card template: {e}")
        raise DocumentOperationError(f"Failed to render agent report card template: {e}")


if __name__ == "__main__":
    sys.exit(manage_docs_main())
