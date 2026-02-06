"""Read file tool with scan + chunk + stream semantics and provenance logging."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import yaml
import difflib

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.shared.execution_context import ExecutionContext
from scribe_mcp.shared.logging_utils import compose_log_line, default_status_emoji, resolve_logging_context
from scribe_mcp.utils.files import append_line
from scribe_mcp.utils.frontmatter import parse_frontmatter
from scribe_mcp.utils.sentinel_logs import append_sentinel_event
from scribe_mcp.utils.response import default_formatter


_DEFAULT_DENYLIST = [
    ".env",
    ".git/",
    ".scribe/registry/",
    "~/.ssh",
    "/etc",
    "/proc",
    "/sys",
]

_CHUNK_LINES = 200
_CHUNK_MAX_BYTES = 131072
_GLOB_CHARS = {"*", "?", "["}
_DEFAULT_MAX_MATCHES = 200
_FULL_MODE_TOKEN_LIMIT = 12000  # Max content tokens for mode='full' (formatted output ~80k chars)

# Lazy-load tiktoken encoder
_tiktoken_encoder = None

def _get_tiktoken_encoder():
    """Get or create tiktoken encoder (lazy loaded)."""
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")  # Claude's encoding
        except ImportError:
            return None
    return _tiktoken_encoder

def _count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken, fallback to char estimate."""
    encoder = _get_tiktoken_encoder()
    if encoder:
        return len(encoder.encode(text))
    # Fallback: ~4 chars per token
    return len(text) // 4


def _load_sentinel_config(repo_root: Path) -> Dict[str, Any]:
    config_path = repo_root / ".scribe" / "sentinel" / "sentinel_config.yaml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_patterns(values: Any) -> List[str]:
    if not values:
        return []
    if isinstance(values, list):
        normalized: List[str] = []
        for item in values:
            if not item:
                continue
            value = os.path.expanduser(str(item))
            normalized.append(value)
        return normalized
    return [os.path.expanduser(str(values))]


def _normalize_path(path_str: str) -> str:
    return path_str.replace("\\", "/")


def _pattern_is_glob(pattern: str) -> bool:
    return any(char in pattern for char in _GLOB_CHARS)


def _matches_any(path_str: str, patterns: Iterable[str]) -> bool:
    path_posix = _normalize_path(path_str)
    parts = [part for part in path_posix.split("/") if part]
    for pattern in patterns:
        if not pattern:
            continue
        normalized = _normalize_path(str(pattern))
        if _pattern_is_glob(normalized):
            if fnmatch(path_posix, normalized) or fnmatch(f"/{path_posix}", normalized):
                return True
            continue
        if "/" in normalized:
            if normalized in path_posix:
                return True
            continue
        if normalized in parts:
            return True
    return False


def _is_external_skill_path(path: Path) -> bool:
    parts = [part for part in _normalize_path(str(path)).split("/") if part]
    for idx, part in enumerate(parts[:-1]):
        if part in {".claude", ".codex"} and parts[idx + 1] == "skills":
            return True
    return False


def _enforce_path_policy(
    path: Path,
    repo_root: Path,
    *,
    allow_outside_repo: bool = False,
) -> Optional[str]:
    config = _load_sentinel_config(repo_root)
    allowlist = _normalize_patterns(config.get("allowlist"))
    denylist = _normalize_patterns(config.get("denylist")) or list(_DEFAULT_DENYLIST)

    abs_path = str(path)
    try:
        rel_path = str(path.relative_to(repo_root))
    except ValueError:
        rel_path = None

    if _matches_any(abs_path, denylist) or (rel_path and _matches_any(rel_path, denylist)):
        return "denylist_match"

    if rel_path is None:
        if _is_external_skill_path(path):
            return None
        if allow_outside_repo:
            return None
        if not _matches_any(abs_path, allowlist):
            return "absolute_path_not_allowlisted"

    if rel_path is not None:
        return None

    return None


def _scan_file(path: Path) -> Dict[str, Any]:
    size = 0
    line_count = 0
    has_crlf = False
    has_lf = False
    last_byte = None
    sha = None
    sample = b""

    import hashlib
    sha = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            sha.update(chunk)
            if len(sample) < 4096:
                remaining = 4096 - len(sample)
                sample += chunk[:remaining]
            if b"\r\n" in chunk:
                has_crlf = True
            if b"\n" in chunk and b"\r\n" not in chunk:
                has_lf = True
            line_count += chunk.count(b"\n")
            last_byte = chunk[-1]

    if size > 0 and line_count == 0:
        line_count = 1
    elif size > 0 and last_byte is not None and last_byte != ord("\n"):
        line_count = line_count + 1

    newline_type = "unknown"
    if has_crlf and has_lf:
        newline_type = "mixed"
    elif has_crlf:
        newline_type = "CRLF"
    elif has_lf:
        newline_type = "LF"

    encoding = "utf-8"
    try:
        sample.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        encoding = "latin-1"

    estimated_chunk_count = max(1, (line_count + _CHUNK_LINES - 1) // _CHUNK_LINES) if line_count else 0

    return {
        "byte_size": size,
        "line_count": line_count,
        "sha256": sha.hexdigest(),
        "newline_type": newline_type,
        "encoding": encoding,
        "estimated_chunk_count": estimated_chunk_count,
    }


def _read_frontmatter_header(path: Path, encoding: str) -> Dict[str, Any]:
    try:
        with path.open("rb") as handle:
            first = handle.readline()
            if not first:
                return {
                    "has_frontmatter": False,
                    "frontmatter_raw": "",
                    "frontmatter": {},
                    "frontmatter_line_count": 0,
                    "frontmatter_byte_count": 0,
                }
            if first.strip() != b"---":
                return {
                    "has_frontmatter": False,
                    "frontmatter_raw": "",
                    "frontmatter": {},
                    "frontmatter_line_count": 0,
                    "frontmatter_byte_count": 0,
                }

            lines = [first]
            while True:
                line = handle.readline()
                if not line:
                    return {
                        "has_frontmatter": True,
                        "frontmatter_raw": b"".join(lines).decode(encoding, errors="replace"),
                        "frontmatter": {},
                        "frontmatter_line_count": len(lines),
                        "frontmatter_byte_count": sum(len(item) for item in lines),
                        "frontmatter_error": "FRONTMATTER_PARSE_ERROR: missing closing '---' delimiter",
                    }
                lines.append(line)
                if line.strip() == b"---":
                    break

            raw_bytes = b"".join(lines)
            raw_text = raw_bytes.decode(encoding, errors="replace")
            try:
                parsed = parse_frontmatter(raw_text)
                data = parsed.frontmatter_data
                error = None
            except ValueError as exc:
                data = {}
                error = str(exc)

            return {
                "has_frontmatter": True,
                "frontmatter_raw": raw_text,
                "frontmatter": data,
                "frontmatter_line_count": len(lines),
                "frontmatter_byte_count": len(raw_bytes),
                "frontmatter_error": error,
            }
    except Exception as exc:
        return {
            "has_frontmatter": False,
            "frontmatter_raw": "",
            "frontmatter": {},
            "frontmatter_line_count": 0,
            "frontmatter_byte_count": 0,
            "frontmatter_error": f"FRONTMATTER_PARSE_ERROR: {exc}",
        }


def _iter_chunks(path: Path, encoding: str) -> Iterable[Dict[str, Any]]:
    chunk_index = 0
    current_line = 1
    chunk_line_start = None
    chunk_line_end = None
    chunk_bytes = 0
    segments: List[bytes] = []
    chunk_byte_start = 0
    chunk_byte_end = 0

    def flush_chunk() -> Optional[Dict[str, Any]]:
        nonlocal chunk_index, segments, chunk_bytes, chunk_line_start, chunk_line_end, chunk_byte_start, chunk_byte_end
        if not segments:
            return None
        text = b"".join(segments).decode(encoding, errors="replace")
        payload = {
            "chunk_index": chunk_index,
            "line_start": chunk_line_start or 1,
            "line_end": chunk_line_end or (chunk_line_start or 1),
            "byte_start": chunk_byte_start,
            "byte_end": chunk_byte_end,
            "content": text,
        }
        chunk_index += 1
        segments = []
        chunk_bytes = 0
        chunk_line_start = None
        chunk_line_end = None
        chunk_byte_start = 0
        chunk_byte_end = 0
        return payload

    with path.open("rb") as handle:
        while True:
            segment = handle.readline(_CHUNK_MAX_BYTES)
            if not segment:
                break

            segment_start = handle.tell() - len(segment)
            segment_end = handle.tell()
            if chunk_line_start is None:
                chunk_line_start = current_line
                chunk_byte_start = segment_start

            # Flush current chunk if adding the segment would exceed memory bound.
            if segments and (chunk_bytes + len(segment) > _CHUNK_MAX_BYTES):
                payload = flush_chunk()
                if payload:
                    yield payload
                chunk_line_start = current_line
                chunk_byte_start = segment_start

            segments.append(segment)
            chunk_bytes += len(segment)
            chunk_line_end = current_line
            chunk_byte_end = segment_end

            if segment.endswith(b"\n"):
                current_line += 1

            # Flush if we've hit line or byte thresholds.
            if chunk_line_start is not None:
                line_count = (chunk_line_end - chunk_line_start) + 1
                if line_count >= _CHUNK_LINES or chunk_bytes >= _CHUNK_MAX_BYTES:
                    payload = flush_chunk()
                    if payload:
                        yield payload

        payload = flush_chunk()
        if payload:
            yield payload


def _extract_line_range(path: Path, encoding: str, start_line: int, end_line: int) -> Dict[str, Any]:
    current_line = 0
    matched: List[bytes] = []
    byte_start = None
    byte_end = None

    with path.open("rb") as handle:
        while True:
            line = handle.readline()
            if not line:
                break
            current_line += 1
            if current_line < start_line:
                continue
            if byte_start is None:
                byte_start = handle.tell() - len(line)
            if current_line <= end_line:
                matched.append(line)
                byte_end = handle.tell()
            if current_line >= end_line:
                break

    return {
        "line_start": start_line,
        "line_end": end_line,
        "byte_start": byte_start or 0,
        "byte_end": byte_end or (byte_start or 0),
        "content": b"".join(matched).decode(encoding, errors="replace"),
    }


_REGEX_META_CHARS = set(".^$*+?{}[]\\|()")


def _infer_search_mode(pattern: str) -> str:
    if any(char in _REGEX_META_CHARS for char in pattern):
        return "regex"
    return "literal"


def _detect_file_type(path: Path) -> str:
    """Detect file type from extension."""
    suffix = path.suffix.lower()
    if suffix in {".py", ".pyw"}:
        return "python"
    if suffix in {".js", ".jsx"}:
        return "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".json"}:
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return "unknown"


def _find_workspace_root(target_file: Path) -> Optional[Path]:
    """Find workspace root by searching upward for markers.

    Searches upward from target_file for common workspace markers:
    - .git/ directory
    - pyproject.toml
    - setup.py
    - package.json

    Args:
        target_file: File to start searching from

    Returns:
        Workspace root Path if found, None otherwise

    Performance:
        - Caches results per directory to avoid repeated filesystem scans
        - Limits upward traversal to 10 levels maximum
    """
    # Cache keyed by directory path (avoid rescanning same directories)
    cache_key = str(target_file.parent.resolve())
    if not hasattr(_find_workspace_root, '_cache'):
        _find_workspace_root._cache = {}

    if cache_key in _find_workspace_root._cache:
        return _find_workspace_root._cache[cache_key]

    # Start from target file's directory
    current = target_file.parent.resolve()
    max_levels = 10

    # Workspace markers (in order of preference)
    markers = ['.git', 'pyproject.toml', 'setup.py', 'package.json']

    for _ in range(max_levels):
        # Check for any marker in current directory
        for marker in markers:
            marker_path = current / marker
            if marker_path.exists():
                # Found workspace root - cache and return
                _find_workspace_root._cache[cache_key] = current
                return current

        # Move up one level
        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    # No workspace root found - cache None and return
    _find_workspace_root._cache[cache_key] = None
    return None


def _resolve_import_path(
    module_name: str,
    level: int,
    current_file: Path,
    workspace_root: Optional[Path]
) -> Dict[str, Any]:
    """Resolve import to categorized type and path.

    Categorizes imports as:
    - stdlib: Python standard library modules
    - third_party: External packages (pip-installed)
    - local: Workspace-local modules
    - unresolved: Cannot determine type

    For local imports, attempts to resolve to actual file path.

    Args:
        module_name: Module name from import statement (e.g., "os" or "scribe_mcp.tools")
        level: Relative import level (0=absolute, 1+=relative dots)
        current_file: Path to file containing the import
        workspace_root: Workspace root directory (from _find_workspace_root)

    Returns:
        Dictionary with:
        - type: "stdlib" | "third_party" | "local" | "unresolved"
        - resolved_path: Absolute path string if local and found, None otherwise
        - exists: bool (for local imports only - whether resolved file exists)

    Performance:
        - Stdlib check is O(1) set lookup
        - Local resolution does minimal filesystem checks
        - Returns early for stdlib/unresolved cases
    """
    import sys

    # Stdlib detection (Python 3.10+)
    # Use sys.stdlib_module_names for accurate stdlib detection
    if level == 0 and module_name:
        # Extract top-level module (e.g., "os.path" -> "os")
        top_level = module_name.split('.')[0]

        # Check if it's stdlib (requires Python 3.10+)
        if hasattr(sys, 'stdlib_module_names') and top_level in sys.stdlib_module_names:
            return {
                "type": "stdlib",
                "resolved_path": None,
                "exists": None
            }

    # Relative imports (level > 0) - must be local
    if level > 0:
        if workspace_root is None:
            # Can't resolve without workspace root
            return {
                "type": "unresolved",
                "resolved_path": None,
                "exists": None
            }

        # Navigate up from current file by 'level - 1' directories
        # level=1 means "from ." (current package dir)
        # level=2 means "from .." (parent dir)
        # level=3 means "from ..." (grandparent dir)
        try:
            target_dir = current_file.parent.resolve()

            # Go up 'level - 1' directories (level=1 stays in current dir)
            for _ in range(level - 1):
                target_dir = target_dir.parent

            # Append module path if present
            if module_name:
                # Convert module.name to module/name
                module_path = module_name.replace('.', '/')
                target_path = target_dir / module_path
            else:
                # "from . import x" - just the directory
                target_path = target_dir

            # Check for .py file or __init__.py in directory
            if target_path.suffix == '':
                # Try directory/__init__.py first
                init_file = target_path / '__init__.py'
                if init_file.exists():
                    return {
                        "type": "local",
                        "resolved_path": str(init_file),
                        "exists": True
                    }

                # Try module.py
                py_file = target_path.with_suffix('.py')
                if py_file.exists():
                    return {
                        "type": "local",
                        "resolved_path": str(py_file),
                        "exists": True
                    }

                # Path doesn't exist
                return {
                    "type": "local",
                    "resolved_path": str(py_file),  # Show expected path
                    "exists": False
                }
            else:
                # Has suffix - check if exists
                return {
                    "type": "local",
                    "resolved_path": str(target_path),
                    "exists": target_path.exists()
                }

        except Exception:
            # Resolution failed
            return {
                "type": "unresolved",
                "resolved_path": None,
                "exists": None
            }

    # Absolute imports (level == 0) - check if local to workspace
    if workspace_root and module_name:
        # Try to resolve as workspace-local module
        # Common patterns: scribe_mcp.tools.append_entry -> scribe_mcp/tools/append_entry.py

        try:
            # Strip top-level package name if it matches workspace directory name
            # Example: workspace_root = /path/to/scribe_mcp/, module = scribe_mcp.storage.base
            #          Should resolve to storage/base.py, not scribe_mcp/storage/base.py
            workspace_name = workspace_root.name
            if module_name.startswith(workspace_name + '.'):
                # Strip the package prefix: "scribe_mcp.storage.base" -> "storage.base"
                module_path_relative = module_name[len(workspace_name) + 1:]
            else:
                # Use as-is (might be a different top-level import)
                module_path_relative = module_name

            # Convert module.name to path
            module_path = module_path_relative.replace('.', '/')

            # Try from workspace root
            target_path = workspace_root / module_path

            # Check for .py file or __init__.py
            if target_path.suffix == '':
                # Try directory/__init__.py first
                init_file = target_path / '__init__.py'
                if init_file.exists():
                    return {
                        "type": "local",
                        "resolved_path": str(init_file),
                        "exists": True
                    }

                # Try module.py
                py_file = target_path.with_suffix('.py')
                if py_file.exists():
                    return {
                        "type": "local",
                        "resolved_path": str(py_file),
                        "exists": True
                    }
            else:
                # Already has suffix
                if target_path.exists():
                    return {
                        "type": "local",
                        "resolved_path": str(target_path),
                        "exists": True
                    }

            # Didn't resolve to local file - likely third_party
            return {
                "type": "third_party",
                "resolved_path": None,
                "exists": None
            }

        except Exception:
            # Resolution failed - mark as unresolved
            return {
                "type": "unresolved",
                "resolved_path": None,
                "exists": None
            }

    # Default: unresolved (no module_name or no workspace_root)
    return {
        "type": "unresolved",
        "resolved_path": None,
        "exists": None
    }


def _scan_repository_imports(repo_root: Path, max_files: int = 500) -> Dict[str, List[str]]:
    """Scan repository for all Python files and extract their imports.

    Discovers all .py files recursively, excluding common build/cache directories,
    and extracts import statements from each file.

    Args:
        repo_root: Repository root directory to scan
        max_files: Maximum number of files to scan (prevents runaway scans)

    Returns:
        Dictionary mapping file paths to lists of imported module names:
        {
            "tools/append_entry.py": ["os", "sys", "pathlib.Path"],
            "storage/sqlite.py": ["sqlite3", "typing.Dict"],
            ...
        }

    Performance:
        - Target: <3 seconds for ~100 file repos (like scribe_mcp)
        - Logs progress every 50 files for large repos
        - Early termination if max_files exceeded

    Error Handling:
        - Skips files with syntax errors (logs warning, continues)
        - Skips files that can't be read (permissions, encoding issues)
        - Returns partial results if max_files limit hit
    """
    import ast
    import logging

    # Directories to exclude from scanning
    excluded_dirs = {'.git', '__pycache__', '.venv', 'node_modules', '.tox', 'venv', 'env', 'build', 'dist', '.eggs'}

    forward_index: Dict[str, List[str]] = {}
    files_scanned = 0
    files_skipped = 0

    try:
        # Find all .py files recursively
        all_py_files = []
        for py_file in repo_root.rglob('*.py'):
            # Check if file is in an excluded directory
            if any(excluded_dir in py_file.parts for excluded_dir in excluded_dirs):
                continue

            all_py_files.append(py_file)

            # Early termination check
            if len(all_py_files) >= max_files:
                logging.warning(f"Repository scan hit max_files limit ({max_files}). Stopping early.")
                break

        # Process each Python file
        for py_file in all_py_files:
            files_scanned += 1

            # Progress tracking for large repos
            if files_scanned % 50 == 0:
                logging.info(f"Repository scan progress: {files_scanned}/{len(all_py_files)} files scanned")

            try:
                # Read and parse file
                file_content = py_file.read_text(encoding='utf-8')
                tree = ast.parse(file_content, filename=str(py_file))

                # Extract imports (without resolution - just module names)
                imports_data = _extract_imports(tree, max_imports=200, current_file=None, workspace_root=None)

                # Extract just the module names
                imported_modules = []
                for import_info in imports_data:
                    module = import_info.get('module')
                    if module:
                        imported_modules.append(module)

                # Store in forward index with repo-relative path
                try:
                    relative_path = py_file.relative_to(repo_root)
                    forward_index[str(relative_path)] = imported_modules
                except ValueError:
                    # File not relative to repo_root - use absolute path
                    forward_index[str(py_file)] = imported_modules

            except SyntaxError as e:
                # Skip files with syntax errors
                files_skipped += 1
                logging.warning(f"Syntax error in {py_file}: {e}. Skipping.")
                continue

            except UnicodeDecodeError as e:
                # Skip files with encoding issues
                files_skipped += 1
                logging.warning(f"Encoding error in {py_file}: {e}. Skipping.")
                continue

            except Exception as e:
                # Skip files with other errors
                files_skipped += 1
                logging.warning(f"Error processing {py_file}: {e}. Skipping.")
                continue

        logging.info(f"Repository scan complete: {files_scanned} files scanned, {files_skipped} files skipped")

    except Exception as e:
        logging.error(f"Repository scan failed: {e}")
        # Return partial results
        return forward_index

    return forward_index


def _build_reverse_index(forward_index: Dict[str, List[str]], repo_root: Path) -> Dict[str, List[str]]:
    """Build reverse import index: map each file to all files that import it.

    Inverts the forward index (file → imports) to create reverse index (file → importers).
    Uses Phase 2's import resolution to map module names to actual file paths.

    Args:
        forward_index: Forward index from _scan_repository_imports()
                      Maps file paths to lists of imported module names
        repo_root: Repository root directory for path resolution

    Returns:
        Dictionary mapping imported file paths to lists of files that import them:
        {
            "tools/append_entry.py": ["tools/set_project.py", "tools/list_projects.py"],
            "storage/sqlite.py": ["tools/append_entry.py", "server.py"],
            ...
        }

    Algorithm:
        1. For each file in forward_index (the importing file)
        2. For each import in that file's import list
        3. Resolve the import to a file path using _resolve_import_path()
        4. Add the importing file to the reverse index under the imported file
        5. Deduplicate importer lists

    Error Handling:
        - Skips imports that can't be resolved to file paths
        - Handles missing workspace root (can't resolve local imports)
        - Normalizes all paths to repo-relative format for consistency
    """
    import logging

    reverse_index: Dict[str, List[str]] = {}

    # Track resolution stats for debugging
    resolved_count = 0
    unresolved_count = 0

    # Process each file in the forward index
    for importing_file, imported_modules in forward_index.items():
        # Convert importing file to absolute Path for resolution context
        importing_file_path = repo_root / importing_file

        # For each module imported by this file
        for module_name in imported_modules:
            try:
                # Resolve module name to file path
                # Note: Phase 2's _resolve_import_path expects:
                #   - module_name: the imported module
                #   - level: 0 for absolute imports (we don't track relative imports in forward_index)
                #   - current_file: the file doing the importing
                #   - workspace_root: for local import resolution

                resolution = _resolve_import_path(
                    module_name=module_name,
                    level=0,  # Forward index only has absolute imports
                    current_file=importing_file_path,
                    workspace_root=repo_root
                )

                # Only process local imports that resolved successfully
                if resolution['type'] == 'local' and resolution['resolved_path'] and resolution['exists']:
                    resolved_count += 1

                    # Normalize resolved path to repo-relative
                    try:
                        resolved_absolute = Path(resolution['resolved_path'])
                        resolved_relative = resolved_absolute.relative_to(repo_root)
                        imported_file = str(resolved_relative)
                    except ValueError:
                        # Path not relative to repo_root - use absolute
                        imported_file = resolution['resolved_path']

                    # Add importing file to reverse index
                    if imported_file not in reverse_index:
                        reverse_index[imported_file] = []

                    # Add importer (avoid duplicates)
                    if importing_file not in reverse_index[imported_file]:
                        reverse_index[imported_file].append(importing_file)

                else:
                    # Import didn't resolve to local file (stdlib, third_party, or unresolved)
                    unresolved_count += 1

            except Exception as e:
                # Resolution failed - skip this import
                unresolved_count += 1
                logging.debug(f"Failed to resolve import '{module_name}' from {importing_file}: {e}")
                continue

    logging.info(
        f"Reverse index built: {len(reverse_index)} files have importers. "
        f"Resolved {resolved_count} local imports, skipped {unresolved_count} non-local imports."
    )

    return reverse_index


def _calculate_impact_radius(file_path: str, reverse_index: Dict[str, List[str]]) -> Dict[str, Any]:
    """Calculate impact radius for a file based on reverse index.

    Determines how many files import the target file and categorizes the impact level.

    Args:
        file_path: Repo-relative path to file being analyzed
        reverse_index: Reverse index from _build_reverse_index()
                      Maps files to lists of files that import them

    Returns:
        Dictionary with impact analysis:
        {
            "count": int,              # Number of files that import this file
            "level": str,              # "low" | "medium" | "high"
            "importers": List[str],    # List of importing file paths (truncated if >20)
            "truncated": bool          # True if importer list was truncated
        }

    Impact Level Thresholds:
        - low: 0-4 importers
        - medium: 5-15 importers
        - high: 16+ importers

    Performance:
        - O(1) lookup in reverse index
        - Constant time categorization
    """
    # Get importers for this file (empty list if not in index)
    importers = reverse_index.get(file_path, [])
    count = len(importers)

    # Categorize impact level
    if count <= 4:
        level = "low"
    elif count <= 15:
        level = "medium"
    else:
        level = "high"

    # Truncate importer list if too long (prevent output explosion)
    truncated = False
    if count > 20:
        importers = importers[:20]
        truncated = True

    return {
        "count": count,
        "level": level,
        "importers": importers,
        "truncated": truncated
    }


# ============================================================================
# BOUNDARY ENFORCEMENT (Phase 4)
# ============================================================================

# Global cache for loaded boundary rules (avoid re-parsing YAML on every scan)
_boundary_rules_cache: Optional[Dict[str, Any]] = None
_boundary_rules_cache_path: Optional[Path] = None


def _load_boundary_rules(repo_root: Path) -> Optional[Dict]:
    """Load boundary rules from .scribe/config/boundary_rules.yaml.

    Args:
        repo_root: Repository root directory

    Returns:
        Parsed rules dict if file exists and enabled, None otherwise

    Caching:
        Rules are cached globally to avoid re-parsing on every scan.
        Cache is invalidated if file path changes.
    """
    global _boundary_rules_cache, _boundary_rules_cache_path

    config_path = repo_root / ".scribe" / "config" / "boundary_rules.yaml"

    # Check cache (path-aware invalidation)
    if _boundary_rules_cache is not None and _boundary_rules_cache_path == config_path:
        return _boundary_rules_cache

    # File doesn't exist - no boundary checking
    if not config_path.exists():
        _boundary_rules_cache = None
        _boundary_rules_cache_path = config_path
        return None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            rules = yaml.safe_load(f)

        # Check if enabled
        if not rules or not rules.get('enabled', False):
            _boundary_rules_cache = None
            _boundary_rules_cache_path = config_path
            return None

        # Validate and cache
        if _validate_boundary_rules(rules):
            _boundary_rules_cache = rules
            _boundary_rules_cache_path = config_path
            return rules
        else:
            logging.warning(f"Invalid boundary rules configuration in {config_path}")
            _boundary_rules_cache = None
            _boundary_rules_cache_path = config_path
            return None

    except Exception as e:
        logging.warning(f"Failed to load boundary rules from {config_path}: {e}")
        _boundary_rules_cache = None
        _boundary_rules_cache_path = config_path
        return None


def _validate_boundary_rules(rules: Dict) -> bool:
    """Validate boundary rules against schema requirements.

    Args:
        rules: Parsed YAML rules dict

    Returns:
        True if valid, False otherwise (with warnings logged)

    Validation:
        - Required fields: version, enabled, rules
        - Each rule needs: name, description, severity, pattern
        - Severity must be: error | warning | info
        - Pattern needs: source, forbidden_imports
    """
    if not isinstance(rules, dict):
        logging.warning("Boundary rules must be a dictionary")
        return False

    # Check required top-level fields
    if 'version' not in rules or 'enabled' not in rules or 'rules' not in rules:
        logging.warning("Boundary rules missing required fields (version, enabled, rules)")
        return False

    # Validate rules list
    rules_list = rules.get('rules', [])
    if not isinstance(rules_list, list):
        logging.warning("Boundary rules 'rules' field must be a list")
        return False

    valid_severities = {'error', 'warning', 'info'}

    for i, rule in enumerate(rules_list):
        if not isinstance(rule, dict):
            logging.warning(f"Boundary rule {i} must be a dictionary")
            return False

        # Check required rule fields
        if 'name' not in rule or 'description' not in rule or 'severity' not in rule or 'pattern' not in rule:
            logging.warning(f"Boundary rule {i} missing required fields (name, description, severity, pattern)")
            return False

        # Validate severity
        if rule['severity'] not in valid_severities:
            logging.warning(f"Boundary rule '{rule.get('name')}' has invalid severity: {rule['severity']} (must be error/warning/info)")
            return False

        # Validate pattern
        pattern = rule.get('pattern')
        if not isinstance(pattern, dict):
            logging.warning(f"Boundary rule '{rule.get('name')}' pattern must be a dictionary")
            return False

        if 'source' not in pattern or 'forbidden_imports' not in pattern:
            logging.warning(f"Boundary rule '{rule.get('name')}' pattern missing source or forbidden_imports")
            return False

        if not isinstance(pattern['forbidden_imports'], list) or not pattern['forbidden_imports']:
            logging.warning(f"Boundary rule '{rule.get('name')}' forbidden_imports must be non-empty list")
            return False

    return True


def _match_rule_pattern(file_path: str, pattern: str, repo_root: Path) -> bool:
    """Match a file path against a glob pattern.

    Args:
        file_path: File path to check (absolute or repo-relative)
        pattern: Glob pattern (e.g., "tools/**/*.py", "tests/**")
        repo_root: Repository root for path normalization

    Returns:
        True if file matches pattern, False otherwise

    Pattern Matching:
        - Supports ** for recursive matching
        - Case-insensitive on Windows, case-sensitive on Linux
        - Handles both absolute and relative paths
    """
    try:
        # Normalize file path to repo-relative
        file_path_obj = Path(file_path)
        if file_path_obj.is_absolute():
            try:
                file_relative = file_path_obj.relative_to(repo_root)
            except ValueError:
                # File not in repo - no match
                return False
        else:
            file_relative = file_path_obj

        # Convert to forward slashes for consistent matching
        file_str = str(file_relative).replace('\\', '/')
        pattern_str = pattern.replace('\\', '/')

        # Use fnmatch with ** support (convert ** to *)
        # fnmatch doesn't natively support **, so we handle it manually
        if '**' in pattern_str:
            import re
            # Convert glob pattern to regex
            # Strategy: Replace ** with placeholder, convert other wildcards, then restore **
            regex_pattern = pattern_str.replace('**', '\x00')  # Temporary placeholder
            regex_pattern = regex_pattern.replace('*', '[^/]*')  # Single * matches non-slash
            regex_pattern = regex_pattern.replace('?', '.')      # ? matches any single char

            # ** matches zero or more path segments (including /)
            # Use (.*/)? to make the path segment optional
            # But tools/**/file.py should match tools/file.py AND tools/a/b/file.py
            # So we need to be smarter: /**/  → (/.*)?/  or just  →  (.*/)?
            regex_pattern = regex_pattern.replace('/\x00/', '(/.*/|/)')  # /** matches zero or more dirs
            regex_pattern = regex_pattern.replace('\x00', '.*')  # Remaining ** (not between slashes)

            # Escape dots that are literal (like .py)
            # But don't escape the .* and [^/]* patterns we just added
            regex_pattern = re.sub(r'\.(?![*\[])', r'\\.', regex_pattern)
            regex_pattern = f'^{regex_pattern}$'

            return bool(re.match(regex_pattern, file_str))
        else:
            # Simple glob matching
            return fnmatch(file_str, pattern_str)

    except Exception as e:
        logging.warning(f"Pattern matching failed for {file_path} against {pattern}: {e}")
        return False


def _check_boundary_violations(
    file_path: str,
    imports: List[Dict],
    rules: Dict,
    repo_root: Path
) -> List[Dict]:
    """Check if imports violate boundary rules.

    Args:
        file_path: Path to file being analyzed (absolute or repo-relative)
        imports: List of import dicts from _extract_imports() with resolved paths
        rules: Parsed boundary rules from _load_boundary_rules()
        repo_root: Repository root directory

    Returns:
        List of violation dictionaries, empty if no violations:
        [
            {
                "rule_name": str,
                "severity": str,              # "error" | "warning" | "info"
                "violated_import": str,       # Imported path that violates rule
                "message": str,               # Rule description
                "line": int                   # Line number of import
            },
            ...
        ]

    Algorithm:
        1. For each rule, check if current file matches source pattern
        2. If match, check each import against forbidden_imports patterns
        3. Respect allowed_exceptions if specified
        4. Return all violations found
    """
    violations = []

    # Extract rules list
    rules_list = rules.get('rules', [])

    for rule in rules_list:
        rule_name = rule.get('name', 'Unknown Rule')
        severity = rule.get('severity', 'warning')
        description = rule.get('description', 'No description')
        pattern = rule.get('pattern', {})

        # Check if current file matches this rule's source pattern
        source_pattern = pattern.get('source', '')
        if not _match_rule_pattern(file_path, source_pattern, repo_root):
            continue  # Rule doesn't apply to this file

        # File matches - check imports against forbidden patterns
        forbidden_patterns = pattern.get('forbidden_imports', [])
        allowed_exceptions = pattern.get('allowed_exceptions', [])

        for imp in imports:
            # Get imported path (prefer resolved_path, fallback to module name)
            imported_path = imp.get('resolved_path')
            if not imported_path:
                # Use module name for matching (e.g., "tools.append_entry")
                module = imp.get('module', '')
                if not module:
                    continue
                imported_path = module

            line = imp.get('line', 0)

            # Check if this import matches any forbidden pattern
            violated = False
            for forbidden_pattern in forbidden_patterns:
                # Handle both path patterns (tools/**) and module patterns (scribe_mcp.tools.*)
                if '/' in forbidden_pattern or '**' in forbidden_pattern:
                    # Path-based pattern
                    if _match_rule_pattern(imported_path, forbidden_pattern, repo_root):
                        violated = True
                        break
                else:
                    # Module-based pattern (e.g., scribe_mcp.tools.*)
                    if '*' in forbidden_pattern:
                        # Convert to regex
                        pattern_regex = forbidden_pattern.replace('.', '\\.').replace('*', '.*')
                        pattern_regex = f'^{pattern_regex}$'
                        if re.match(pattern_regex, str(imported_path)):
                            violated = True
                            break
                    else:
                        # Exact match
                        if str(imported_path) == forbidden_pattern or str(imported_path).startswith(forbidden_pattern + '.'):
                            violated = True
                            break

            if not violated:
                continue

            # Check allowed exceptions
            is_exception = False
            for exception_pattern in allowed_exceptions:
                if '/' in exception_pattern or '**' in exception_pattern:
                    # Path-based exception
                    if _match_rule_pattern(imported_path, exception_pattern, repo_root):
                        is_exception = True
                        break
                else:
                    # Module-based exception
                    if str(imported_path) == exception_pattern or str(imported_path).startswith(exception_pattern + '.'):
                        is_exception = True
                        break

            if is_exception:
                continue

            # Violation confirmed!
            violations.append({
                "rule_name": rule_name,
                "severity": severity,
                "violated_import": str(imported_path),
                "message": description,
                "line": line
            })

    return violations


def _extract_imports(
    tree: Any,
    max_imports: int = 100,
    current_file: Optional[Path] = None,
    workspace_root: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Extract import statements from Python AST with resolution.

    Args:
        tree: Parsed AST tree from ast.parse()
        max_imports: Maximum number of imports to extract (default 100)
        current_file: Path to file being analyzed (for resolution context)
        workspace_root: Workspace root directory (for local import resolution)

    Returns:
        List of import dictionaries with schema:
        {
            "module": str,              # Module name
            "line": int,                # Line number of import
            "type": str,                # "import" or "from_import"
            "names": List[str],         # Imported names (for from_import)
            "alias": Optional[str],     # Alias if present (import x as y)
            "level": int,               # Relative import depth (0=absolute, 1+=relative)
            "import_type": str,         # "stdlib" | "third_party" | "local" | "unresolved" (Phase 2)
            "resolved_path": Optional[str],  # Absolute path if local and resolved (Phase 2)
            "exists": Optional[bool]    # Whether resolved file exists (Phase 2, local only)
        }
    """
    import ast

    imports = []

    for node in ast.walk(tree):
        # Handle: import module_name, import module_name as alias
        if isinstance(node, ast.Import):
            for alias in node.names:
                import_info = {
                    "module": alias.name,
                    "line": node.lineno,
                    "type": "import",
                    "names": None,  # ast.Import doesn't have specific names
                    "alias": alias.asname,  # None if no alias
                    "level": 0  # ast.Import is always absolute
                }

                # Phase 2: Resolve import path and type
                if current_file is not None:
                    resolution = _resolve_import_path(
                        module_name=alias.name,
                        level=0,
                        current_file=current_file,
                        workspace_root=workspace_root
                    )
                    import_info["import_type"] = resolution["type"]
                    import_info["resolved_path"] = resolution["resolved_path"]
                    import_info["exists"] = resolution["exists"]
                else:
                    # Resolution disabled (backward compatibility)
                    import_info["import_type"] = "unresolved"
                    import_info["resolved_path"] = None
                    import_info["exists"] = None

                imports.append(import_info)

                # Respect max_imports limit
                if len(imports) >= max_imports:
                    return imports

        # Handle: from module import name, from ..module import name
        elif isinstance(node, ast.ImportFrom):
            # Extract names from node.names list
            names = [alias.name for alias in node.names] if node.names else []

            import_info = {
                "module": node.module or "",  # Can be None for "from . import x"
                "line": node.lineno,
                "type": "from_import",
                "names": names,
                "alias": None,  # from_import uses names list, not single alias
                "level": node.level  # 0=absolute, 1+=relative dots
            }

            # Phase 2: Resolve import path and type
            if current_file is not None:
                resolution = _resolve_import_path(
                    module_name=node.module or "",
                    level=node.level,
                    current_file=current_file,
                    workspace_root=workspace_root
                )
                import_info["import_type"] = resolution["type"]
                import_info["resolved_path"] = resolution["resolved_path"]
                import_info["exists"] = resolution["exists"]
            else:
                # Resolution disabled (backward compatibility)
                import_info["import_type"] = "unresolved"
                import_info["resolved_path"] = None
                import_info["exists"] = None

            imports.append(import_info)

            # Respect max_imports limit
            if len(imports) >= max_imports:
                return imports

    return imports


def _get_full_signature(node: 'ast.FunctionDef') -> Dict[str, Any]:
    """Extract full function signature including types, defaults, and return type."""
    import ast

    params = []
    args = node.args

    # Build list of all parameters with their annotations and defaults
    all_args = args.args
    defaults = args.defaults

    # Defaults align to the END of args list
    num_defaults = len(defaults)
    num_args = len(all_args)

    for i, arg in enumerate(all_args):
        param_info = {"name": arg.arg}

        # Add type annotation if present
        if arg.annotation:
            try:
                param_info["type"] = ast.unparse(arg.annotation)
            except:
                param_info["type"] = "..."

        # Add default value if present (defaults align to end)
        default_idx = i - (num_args - num_defaults)
        if default_idx >= 0:
            try:
                param_info["default"] = ast.unparse(defaults[default_idx])
            except:
                param_info["default"] = "..."

        params.append(param_info)

    # Handle *args
    if args.vararg:
        vararg_info = {"name": f"*{args.vararg.arg}"}
        if args.vararg.annotation:
            try:
                vararg_info["type"] = ast.unparse(args.vararg.annotation)
            except:
                vararg_info["type"] = "..."
        params.append(vararg_info)

    # Handle **kwargs
    if args.kwarg:
        kwarg_info = {"name": f"**{args.kwarg.arg}"}
        if args.kwarg.annotation:
            try:
                kwarg_info["type"] = ast.unparse(args.kwarg.annotation)
            except:
                kwarg_info["type"] = "..."
        params.append(kwarg_info)

    # Get return type
    return_type = None
    if node.returns:
        try:
            return_type = ast.unparse(node.returns)
        except:
            return_type = "..."

    return {
        "params": params,
        "return_type": return_type
    }


def _extract_python_structure(path: Path, max_items: int = 50, structure_filter: Optional[str] = None) -> Dict[str, Any]:
    """Extract Python AST structure with line numbers.

    Args:
        path: Path to Python file
        max_items: Maximum items to return per category
        structure_filter: Optional regex pattern to filter classes/functions by name
    """
    import ast
    import re
    try:
        with path.open("r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return {"ok": False, "error": str(e), "type": "python"}

    functions = []
    classes = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Get full signature
            sig = _get_full_signature(node)

            func_info = {
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, 'end_lineno', node.lineno),  # Python 3.8+
                "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "params": sig["params"],
                "return_type": sig["return_type"],
                # Keep legacy args for backwards compat
                "args": [arg.arg for arg in node.args.args],
            }
            # Determine if it's a method (inside a class)
            for parent in ast.walk(tree):
                if isinstance(parent, ast.ClassDef):
                    if node in ast.walk(parent):
                        func_info["type"] = "method"
                        break
            if func_info["type"] != "method":
                functions.append(func_info)

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Get full signature for methods
                    sig = _get_full_signature(item)

                    methods.append({
                        "name": item.name,
                        "line": item.lineno,
                        "end_line": getattr(item, 'end_lineno', item.lineno),  # Python 3.8+
                        "is_async": isinstance(item, ast.AsyncFunctionDef),
                        "params": sig["params"],
                        "return_type": sig["return_type"],
                        # Keep legacy args for backwards compat
                        "args": [arg.arg for arg in item.args.args],
                    })
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": getattr(node, 'end_lineno', node.lineno),  # Python 3.8+
                "methods": methods,  # Store all methods (pagination handles display limits)
                "method_count": len(methods),
            })

    total_functions = len(functions)
    total_classes = len(classes)

    # Apply structure filter if provided
    if structure_filter:
        try:
            pattern = re.compile(structure_filter, re.IGNORECASE)
            functions = [f for f in functions if pattern.search(f['name'])]
            classes = [c for c in classes if pattern.search(c['name'])]
        except re.error as e:
            # Invalid regex - return error
            return {"ok": False, "error": f"Invalid regex pattern: {e}", "type": "python"}

    # When filtering is active, return all matches (pagination handles display)
    # When no filter, truncate to max_items for backwards compatibility
    if structure_filter:
        return_functions = functions
        return_classes = classes
        is_truncated = False
    else:
        return_functions = functions[:max_items]
        return_classes = classes[:max_items]
        is_truncated = total_functions > max_items or total_classes > max_items

    return {
        "ok": True,
        "type": "python",
        "functions": return_functions,
        "classes": return_classes,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "truncated": is_truncated,
        "filtered": structure_filter is not None,
        "filter_pattern": structure_filter if structure_filter else None,
        "filtered_function_count": len(functions) if structure_filter else None,
        "filtered_class_count": len(classes) if structure_filter else None,
    }


def _extract_markdown_structure(path: Path, max_headings: int = 100) -> Dict[str, Any]:
    """Extract markdown heading structure with line numbers."""
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError as e:
        return {"ok": False, "error": str(e), "type": "markdown"}

    headings = []
    for line_num, line in enumerate(lines, start=1):
        line = line.rstrip()
        if line.startswith("#"):
            # Count leading #'s
            level = 0
            for char in line:
                if char == "#":
                    level += 1
                else:
                    break
            text = line[level:].strip()
            if text:  # Only add if there's actual text
                headings.append({
                    "level": level,
                    "text": text,
                    "line": line_num,
                })

    total_headings = len(headings)

    return {
        "ok": True,
        "type": "markdown",
        "headings": headings[:max_headings],
        "total_headings": total_headings,
        "truncated": total_headings > max_headings,
    }


def _extract_javascript_structure(path: Path, file_type: str, max_items: int = 50) -> Dict[str, Any]:
    """Extract JavaScript/TypeScript structure using regex (AST would require external deps)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            source = f.read()
    except UnicodeDecodeError as e:
        return {"ok": False, "error": str(e), "type": file_type}

    functions = []
    classes = []

    # Function patterns: function name(...), const name = (...) =>, async function name(...)
    func_patterns = [
        r"^\s*(?:async\s+)?function\s+(\w+)\s*\(",
        r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    ]

    # Class pattern: class Name
    class_pattern = r"^\s*(?:export\s+)?class\s+(\w+)"

    lines = source.split("\n")
    for line_num, line in enumerate(lines, start=1):
        # Check for functions
        for pattern in func_patterns:
            match = re.match(pattern, line)
            if match:
                functions.append({
                    "name": match.group(1),
                    "line": line_num,
                    "type": "function",
                })
                break

        # Check for classes
        match = re.match(class_pattern, line)
        if match:
            classes.append({
                "name": match.group(1),
                "line": line_num,
            })

    total_functions = len(functions)
    total_classes = len(classes)

    return {
        "ok": True,
        "type": file_type,
        "functions": functions[:max_items],
        "classes": classes[:max_items],
        "total_functions": total_functions,
        "total_classes": total_classes,
        "truncated": total_functions > max_items or total_classes > max_items,
    }


def _search_file(
    path: Path,
    encoding: str,
    pattern: str,
    regex: bool,
    context_lines: int,
    max_matches: Optional[int],
    case_insensitive: bool,
    fuzzy_threshold: float,
) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    matcher = None
    if regex:
        try:
            flags = re.IGNORECASE if case_insensitive else 0
            matcher = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
    buffer: List[str] = []
    buffer_start = 1
    current_line = 0
    pattern_value = pattern.lower() if case_insensitive else pattern

    with path.open("rb") as handle:
        for raw_line in handle:
            current_line += 1
            line = raw_line.decode(encoding, errors="replace")
            buffer.append(line)
            if len(buffer) > context_lines * 2 + 1:
                buffer.pop(0)
                buffer_start += 1

            is_match = False
            score = None
            candidate = line.lower() if case_insensitive else line
            if regex:
                if matcher and matcher.search(line):
                    is_match = True
            elif fuzzy_threshold > 0:
                base = line.strip()
                candidate_text = base.lower() if case_insensitive else base
                score = difflib.SequenceMatcher(None, pattern_value, candidate_text).ratio()
                if score >= fuzzy_threshold:
                    is_match = True
            else:
                if pattern_value in candidate:
                    is_match = True

            if is_match:
                context_start = max(1, current_line - context_lines)
                context_end = current_line + context_lines
                snippet = buffer[-(context_lines * 2 + 1):]
                match_payload = {
                    "line_number": current_line,
                    "line": line,
                    "context_start": context_start,
                    "context_end": context_end,
                    "context": snippet,
                }
                if score is not None:
                    match_payload["match_score"] = score
                matches.append(match_payload)
                if max_matches is not None and len(matches) >= max_matches:
                    break

    return matches


async def _log_project_read(context: ExecutionContext, message: str, meta: Dict[str, Any]) -> None:
    """DEPRECATED: Do not use. Tool events should not go to PROGRESS_LOG.

    This function previously wrote tool events (like read_file_error) to the project's
    PROGRESS_LOG.md. This was incorrect because:
    1. Progress logs should only contain agent prose/audit notes from append_entry
    2. Tool events are logged to TOOL_LOG.jsonl via finalize_tool_response()

    This function is kept for backward compatibility but should be removed in a future version.
    """
    # NO-OP: This function is deprecated and should not be called.
    # Tool logging is handled by finalize_tool_response() → TOOL_LOG.jsonl
    import warnings
    warnings.warn(
        "_log_project_read is deprecated. Tool events should not go to PROGRESS_LOG.",
        DeprecationWarning,
        stacklevel=2
    )
    return  # Do nothing - tool events go to TOOL_LOG.jsonl, not PROGRESS_LOG


@app.tool()
async def read_file(
    agent: str,
    path: str,
    mode: str = "scan_only",
    chunk_index: Optional[List[int]] = None,
    start_chunk: Optional[int] = None,
    max_chunks: Optional[int] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    page_number: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,
    query: Optional[str] = None,
    search_mode: str = "regex",  # Changed default from "literal" to "regex" for better UX
    case_insensitive: Optional[bool] = None,
    context_lines: int = 0,
    max_matches: Optional[int] = None,
    fuzzy_threshold: Optional[float] = None,
    format: str = "readable",  # NEW: default is readable for agent-friendly output
    include_dependencies: bool = False,  # Phase 1: Include import dependency analysis
    include_impact: bool = False,  # Phase 3: Include impact radius analysis (requires include_dependencies=True)
    structure_filter: Optional[str] = None,  # Phase 5: Filter classes/functions by name (regex supported) in scan_only mode
    structure_page: int = 1,  # Phase 5: Page number for paginating structure results (methods, classes, functions)
    structure_page_size: int = 10,  # Phase 5: Items per page for structure pagination
    allow_outside_repo: bool = False,  # Allow reads outside repo_root (denylist still enforced)
    include_full_content: bool = False,  # Bypass token limit in mode='full' (for web dashboard/API use)
) -> Union[Dict[str, Any], str]:
    exec_context = server_module.get_execution_context()
    if exec_context is None:
        return {"ok": False, "error": "ExecutionContext missing"}

    # Validate include_impact requires include_dependencies
    if include_impact and not include_dependencies:
        return {"ok": False, "error": "include_impact=True requires include_dependencies=True"}

    repo_root = Path(exec_context.repo_root).resolve()
    requested_mode = mode.lower()
    target = Path(path).expanduser()

    # --- Security: symlink-aware path traversal prevention ---
    # Step 1: Check unresolved path for boundary escape attempts
    if not target.is_absolute():
        unresolved = repo_root / target
        # Normalize without resolving symlinks to catch '..' escapes
        try:
            normalized = unresolved.resolve(strict=False)
            if not str(normalized).startswith(str(repo_root)):
                return {"ok": False, "error": "read_file denied",
                        "reason": "path_traversal_blocked",
                        "message": f"Path escapes repository boundary: {path}"}
        except (OSError, ValueError):
            pass  # Let downstream checks handle truly broken paths

    # Step 2: Resolve path (follows symlinks)
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    else:
        target = target.resolve()

    # Step 3: Verify resolved path is still within repo (catches symlink escapes)
    try:
        rel_path = str(target.relative_to(repo_root))
    except ValueError:
        rel_path = None

    # Step 4: If target is a symlink, verify the symlink target is within repo
    raw_target = Path(path).expanduser()
    if not raw_target.is_absolute():
        raw_target = repo_root / raw_target
    if raw_target.is_symlink():
        link_dest = raw_target.resolve()
        if not str(link_dest).startswith(str(repo_root)):
            return {"ok": False, "error": "read_file denied",
                    "reason": "symlink_escape_blocked",
                    "message": f"Symlink target escapes repository boundary: {path}"}

    external_skill_path = _is_external_skill_path(target)
    audit_meta = {
        "execution_id": exec_context.execution_id,
        "session_id": exec_context.session_id,
        "intent": exec_context.intent,
        "agent_kind": exec_context.agent_identity.agent_kind,
        "agent_instance_id": exec_context.agent_identity.instance_id,
        "agent_sub_id": exec_context.agent_identity.sub_id,
        "agent_display_name": exec_context.agent_identity.display_name,
        "agent_model": exec_context.agent_identity.model,
        "allow_outside_repo": bool(allow_outside_repo),
        "external_skill_path": external_skill_path,
    }

    async def get_reminders(read_mode: str) -> List[Dict[str, Any]]:
        try:
            context = await resolve_logging_context(
                tool_name="read_file",
                server_module=server_module,
                agent_id=exec_context.agent_identity.instance_id,
                require_project=False,
                reminder_variables={"read_mode": read_mode},
            )
            return list(context.reminders or [])
        except Exception:
            return []

    async def finalize_response(payload: Dict[str, Any], read_mode: str) -> Union[Dict[str, Any], str]:
        payload.setdefault("mode", read_mode)
        payload["reminders"] = await get_reminders(read_mode)

        # NEW: Route through formatter for readable/structured/compact modes
        return await default_formatter.finalize_tool_response(
            data=payload,
            format=format,
            tool_name="read_file"
        )

    async def log_read(event_type: str, data: Dict[str, Any], *, include_md: bool = True) -> None:
        """Log read_file events to sentinel log only.

        NOTE: Tool events (read_file_error, scope_violation, etc.) should NOT go to
        PROGRESS_LOG. Progress logs are for agent prose/audit notes via append_entry.
        Tool logging is handled separately by finalize_tool_response() → TOOL_LOG.jsonl.
        """
        payload = {**audit_meta, **data}
        if exec_context.mode == "sentinel":
            append_sentinel_event(
                exec_context,
                event_type=event_type,
                data=payload,
                log_type="sentinel",
                include_md=include_md,
            )
        # Non-sentinel mode: NO-OP - tool events go to TOOL_LOG.jsonl via finalize_tool_response()
        # Previously this called _log_project_read() which incorrectly wrote to PROGRESS_LOG

    policy_error = _enforce_path_policy(
        target,
        repo_root,
        allow_outside_repo=allow_outside_repo,
    )
    if policy_error:
        await log_read(
            "scope_violation",
            {"reason": policy_error, "path": str(target)},
            include_md=True,
        )
        return await finalize_response({
            "ok": False,
            "error": "read_file denied",
            "reason": policy_error,
            "absolute_path": str(target),
            "repo_relative_path": rel_path,
        }, requested_mode)

    if not target.exists() or not target.is_file():
        from utils.path_suggestions import (
            classify_path_error,
            get_fuzzy_file_suggestions,
            get_directory_listing,
            build_search_suggestion,
        )

        # Classify the specific error type
        error_type = classify_path_error(target)
        error_messages = {
            "not_found": "file not found",
            "is_directory": "path is a directory",
            "permission_denied": "permission denied",
            "is_symlink": "path is a symbolic link (not a regular file)",
            "unknown": "file not accessible"
        }
        error_message = error_messages.get(error_type, "file not found")

        error_response = {
            "ok": False,
            "error": error_message,
            "error_type": error_type,
            "absolute_path": str(target),
            "repo_relative_path": rel_path,
        }

        # Only enrich errors for readable format (performance optimization)
        if format == "readable":
            # Fuzzy suggestions
            if target.parent.exists():
                suggestions = get_fuzzy_file_suggestions(
                    target.name,
                    target.parent,
                    include_directories=(error_type == "is_directory")
                )
                if suggestions:
                    error_response["similar_files"] = suggestions
                    best_match = suggestions[0]
                    error_response["suggestion"] = (
                        f"Did you mean '{best_match['name']}'? "
                        f"({int(best_match['score'] * 100)}% match)"
                    )

                # Parent directory listing
                listing = get_directory_listing(target.parent)
                if listing and not listing.get("permission_error"):
                    error_response["parent_directory"] = str(target.parent)
                    error_response["parent_listing"] = listing

            # Cross-tool suggestion
            if error_type in ("not_found", "permission_denied"):
                error_response["search_suggestion"] = build_search_suggestion(
                    pattern=target.stem,  # filename without extension
                    path=str(target.parent) if target.parent.exists() else str(repo_root),
                    agent=agent
                )

        await log_read(
            "read_file_error",
            {"reason": error_type, "path": str(target)},
            include_md=True,
        )

        return await finalize_response(error_response, requested_mode)

    scan = _scan_file(target)
    scan_payload = {
        "absolute_path": str(target),
        "repo_relative_path": rel_path,
        **scan,
    }

    # Record file read for edit_file enforcement (session tracking)
    if exec_context.session_id:
        try:
            await server_module.router_context_manager.record_file_read(
                exec_context.session_id,
                str(target),
            )
        except Exception:
            pass  # Non-critical: don't block reads if tracking fails

    encoding = scan["encoding"]
    frontmatter_info = _read_frontmatter_header(target, encoding)
    response: Dict[str, Any] = {
        "ok": True,
        "scan": scan_payload,
        "mode": mode,
        "frontmatter": frontmatter_info.get("frontmatter", {}),
        "frontmatter_raw": frontmatter_info.get("frontmatter_raw", ""),
        "frontmatter_line_count": frontmatter_info.get("frontmatter_line_count", 0),
        "frontmatter_byte_count": frontmatter_info.get("frontmatter_byte_count", 0),
        "has_frontmatter": frontmatter_info.get("has_frontmatter", False),
    }
    if frontmatter_info.get("frontmatter_error"):
        response["frontmatter_error"] = frontmatter_info.get("frontmatter_error")
    mode = mode.lower()
    if search is None and query:
        search = query
        if search_mode == "literal":
            search_mode = "smart"
    if chunk_index is None and mode == "chunk":
        chunk_index = [0]
    elif isinstance(chunk_index, (int, str)):
        chunk_index = [int(chunk_index)]

    if mode == "scan_only":
        # Add structure analysis based on file type
        file_type = _detect_file_type(target)
        structure = None

        if file_type == "python":
            structure = _extract_python_structure(target, max_items=50, structure_filter=structure_filter)

            # Phase 1: Dependency analysis (opt-in)
            # When include_dependencies=False, this block is skipped (zero overhead)
            if include_dependencies:
                import ast
                try:
                    with target.open("r", encoding="utf-8") as f:
                        source = f.read()
                    tree = ast.parse(source, filename=str(target))

                    # Phase 2: Find workspace root for resolution
                    workspace_root = _find_workspace_root(target)

                    # Extract imports from AST with resolution
                    imports_list = _extract_imports(
                        tree,
                        max_imports=100,
                        current_file=target,
                        workspace_root=workspace_root
                    )

                    # Build dependencies response object
                    truncated = len(imports_list) >= 100

                    # Phase 2: Populate unresolved list (imports that couldn't be resolved)
                    unresolved_imports = [
                        imp for imp in imports_list
                        if imp.get("import_type") == "unresolved"
                    ]

                    response["dependencies"] = {
                        "imports": imports_list,
                        "total_imports": len(imports_list),
                        "truncated": truncated,
                        "unresolved": unresolved_imports
                    }

                    # Phase 4: Boundary enforcement (automatic when include_dependencies=True)
                    # Load boundary rules and check for violations
                    try:
                        boundary_rules = _load_boundary_rules(repo_root)
                        if boundary_rules:
                            # Check for violations
                            violations = _check_boundary_violations(
                                file_path=str(target),
                                imports=imports_list,
                                rules=boundary_rules,
                                repo_root=repo_root
                            )

                            # Count errors
                            has_errors = any(v.get('severity') == 'error' for v in violations)

                            response["boundary_violations"] = {
                                "enabled": True,
                                "violations": violations,
                                "total_violations": len(violations),
                                "has_errors": has_errors
                            }
                        else:
                            # Rules disabled or missing
                            response["boundary_violations"] = {
                                "enabled": False
                            }
                    except Exception as e:
                        # Don't fail scan if boundary checking fails
                        logging.warning(f"Boundary checking failed: {e}")
                        response["boundary_violations"] = {
                            "enabled": False,
                            "error": str(e)
                        }

                    # Phase 3: Impact radius analysis (opt-in, requires dependencies)
                    if include_impact:
                        import time
                        import logging
                        try:
                            scan_start = time.time()

                            # Step 1: Scan repository for all imports (forward index)
                            forward_index = _scan_repository_imports(
                                repo_root=workspace_root or repo_root,
                                max_files=500
                            )

                            # Step 2: Build reverse index (file → importers)
                            reverse_index = _build_reverse_index(
                                forward_index=forward_index,
                                repo_root=workspace_root or repo_root
                            )

                            # Step 3: Calculate impact radius for current file
                            # Need repo-relative path for lookup
                            try:
                                file_relative = target.relative_to(workspace_root or repo_root)
                                impact_data = _calculate_impact_radius(
                                    file_path=str(file_relative),
                                    reverse_index=reverse_index
                                )
                            except ValueError:
                                # File not in workspace - use absolute path
                                impact_data = _calculate_impact_radius(
                                    file_path=str(target),
                                    reverse_index=reverse_index
                                )

                            scan_duration = time.time() - scan_start

                            # Add performance warning if scan took too long
                            if scan_duration > 5.0:
                                logging.warning(
                                    f"Impact radius scan took {scan_duration:.1f}s (threshold: 5s). "
                                    f"Consider caching in future."
                                )
                                impact_data["performance_warning"] = (
                                    f"Repository scan took {scan_duration:.1f}s. "
                                    f"Use include_impact sparingly - no caching in Phase 3."
                                )

                            response["impact_radius"] = impact_data

                        except Exception as e:
                            # Don't fail scan if impact analysis fails
                            logging.error(f"Impact radius analysis failed: {e}")
                            response["impact_radius"] = {
                                "error": f"Failed to calculate impact radius: {str(e)}",
                                "count": 0,
                                "level": "unknown",
                                "importers": [],
                                "truncated": False
                            }

                except (SyntaxError, UnicodeDecodeError) as e:
                    # Don't fail scan if dependency analysis fails
                    response["dependencies"] = {
                        "error": f"Failed to parse imports: {str(e)}",
                        "imports": [],
                        "total_imports": 0,
                        "truncated": False,
                        "unresolved": []
                    }
        elif file_type == "markdown":
            structure = _extract_markdown_structure(target, max_headings=100)
        elif file_type in {"javascript", "typescript"}:
            structure = _extract_javascript_structure(target, file_type, max_items=50)

        if structure:
            response["structure"] = structure
            # Add pagination info for structure browsing
            response["structure_pagination"] = {
                "page": structure_page,
                "page_size": structure_page_size,
            }

        # Add navigation hints for chunk/page reading
        line_count = scan.get("line_count", 0)
        chunk_count = scan.get("estimated_chunk_count", 0)
        response["navigation_hints"] = {
            "total_chunks": chunk_count,
            "suggested_chunk_size": min(5, chunk_count) if chunk_count > 0 else 1,
            "modes_available": ["chunk", "page", "line_range", "full_stream", "search"],
            "examples": {
                "read_chunk": f"read_file(path='{rel_path or target}', mode='chunk', chunk_index=[0])",
                "read_page": f"read_file(path='{rel_path or target}', mode='page', page_number=1, page_size=50)",
                "read_range": f"read_file(path='{rel_path or target}', mode='line_range', start_line=1, end_line=50)",
            }
        }

        # Add hint for advanced analysis (dependencies, impact, boundaries)
        if not include_dependencies:
            response["advanced_analysis_hint"] = {
                "message": "For dependency analysis, boundary checking, and impact radius, add include_dependencies=True",
                "example": f"read_file(path='{rel_path or target}', mode='scan_only', include_dependencies=True)",
                "features": ["import resolution", "boundary violation detection", "impact radius (with include_impact=True)"]
            }

        # SKILL.md special detection (Option B - urgent read indicator)
        if target.name == "SKILL.md":
            response["special_file"] = {
                "type": "SKILL",
                "requires_full_read": True,
                "urgency": "CRITICAL",
                "reason": "READ THE SKILL",
                "instruction": "This file contains critical operational rules that agents MUST follow. Use mode='page' or 'full_stream' to read complete content NOW.",
                "suggested_action": f"read_file(path='{rel_path or target}', mode='page', page_number=1, page_size=200)"
            }

        await log_read("read_file", {"read_mode": "scan_only", **scan_payload}, include_md=True)
        return await finalize_response(response, "scan_only")

    if mode == "chunk":
        if not chunk_index:
            return await finalize_response({
                "ok": False,
                "error": "chunk_index required for chunk mode",
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "chunk")
        try:
            wanted = {int(x) for x in chunk_index}
        except (TypeError, ValueError):
            return await finalize_response({
                "ok": False,
                "error": "chunk_index must be integers",
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "chunk")
        max_wanted = max(wanted) if wanted else -1
        remaining = set(wanted)
        chunks: List[Dict[str, Any]] = []
        for chunk in _iter_chunks(target, encoding):
            index = chunk["chunk_index"]
            if index in remaining:
                chunks.append(chunk)
                remaining.remove(index)
            if not remaining and index >= max_wanted:
                break
        response["chunks"] = chunks
        if frontmatter_info.get("has_frontmatter") and chunks:
            line_offset = frontmatter_info.get("frontmatter_line_count", 0)
            byte_offset = frontmatter_info.get("frontmatter_byte_count", 0)
            first_chunk = chunks[0]
            raw_frontmatter = frontmatter_info.get("frontmatter_raw", "")
            if raw_frontmatter and first_chunk.get("content", "").startswith(raw_frontmatter):
                first_chunk["frontmatter_stripped"] = True
                first_chunk["original_line_start"] = first_chunk.get("line_start")
                first_chunk["original_line_end"] = first_chunk.get("line_end")
                first_chunk["original_byte_start"] = first_chunk.get("byte_start")
                first_chunk["original_byte_end"] = first_chunk.get("byte_end")
                first_chunk["content"] = first_chunk.get("content", "")[len(raw_frontmatter):]
                if isinstance(first_chunk.get("line_start"), int):
                    first_chunk["line_start"] = max(1, first_chunk["line_start"] - line_offset)
                if isinstance(first_chunk.get("line_end"), int):
                    first_chunk["line_end"] = max(0, first_chunk["line_end"] - line_offset)
                if isinstance(first_chunk.get("byte_start"), int):
                    first_chunk["byte_start"] = max(0, first_chunk["byte_start"] - byte_offset)
                if isinstance(first_chunk.get("byte_end"), int):
                    first_chunk["byte_end"] = max(0, first_chunk["byte_end"] - byte_offset)
        await log_read(
            "read_file",
            {"read_mode": "chunk", "chunk_index": sorted(wanted), **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "chunk")

    if mode == "line_range":
        if start_line is None or end_line is None:
            return await finalize_response({"ok": False, "error": "start_line and end_line required for line_range"}, "line_range")
        if start_line < 1 or end_line < start_line:
            return await finalize_response({"ok": False, "error": "invalid line range"}, "line_range")
        chunk = _extract_line_range(target, encoding, int(start_line), int(end_line))
        response["chunk"] = chunk
        await log_read(
            "read_file",
            {"read_mode": "line_range", "line_start": start_line, "line_end": end_line, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "line_range")

    if mode == "page":
        if page_number is None:
            return await finalize_response({"ok": False, "error": "page_number required for page mode"}, "page")
        size = int(page_size or settings.default_page_size)
        start = (int(page_number) - 1) * size + 1
        end = start + size - 1
        chunk = _extract_line_range(target, encoding, start, end)
        response["chunk"] = chunk
        response["page_number"] = page_number
        response["page_size"] = size
        await log_read(
            "read_file",
            {"read_mode": "page", "page_number": page_number, "page_size": size, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "page")

    if mode == "full_stream":
        if start_chunk is not None and start_chunk < 0:
            return await finalize_response({"ok": False, "error": "start_chunk must be >= 0"}, "full_stream")
        if max_chunks is not None and max_chunks <= 0:
            return await finalize_response({"ok": False, "error": "max_chunks must be >= 1"}, "full_stream")
        start_index = int(start_chunk if start_chunk is not None else (chunk_index[0] if chunk_index else 0))
        max_chunk_count = int(max_chunks if max_chunks is not None else (page_size or 1))
        chunks: List[Dict[str, Any]] = []
        for chunk in _iter_chunks(target, encoding):
            if chunk["chunk_index"] < start_index:
                continue
            if len(chunks) >= max_chunk_count:
                break
            chunks.append(chunk)
        next_index = None
        if chunks:
            next_index = chunks[-1]["chunk_index"] + 1
            if next_index >= scan["estimated_chunk_count"]:
                next_index = None
        response["chunks"] = chunks
        response["next_chunk_index"] = next_index
        await log_read(
            "read_file",
            {"read_mode": "full_stream", "start_chunk": start_index, "max_chunks": max_chunk_count, **scan_payload},
            include_md=True,
        )
        return await finalize_response(response, "full_stream")

    if mode == "search":
        if not search:
            return await finalize_response({"ok": False, "error": "search pattern required for search mode"}, "search")
        if max_matches is None:
            max_matches = _DEFAULT_MAX_MATCHES
        if max_matches <= 0:
            return await finalize_response({"ok": False, "error": "max_matches must be >= 1"}, "search")
        original_mode = search_mode.lower()
        resolved_mode = original_mode
        if resolved_mode == "smart":
            resolved_mode = _infer_search_mode(search)
        if resolved_mode not in {"literal", "regex", "fuzzy"}:
            return await finalize_response({"ok": False, "error": f"Unsupported search_mode '{search_mode}'"}, "search")
        if case_insensitive is None:
            case_insensitive = resolved_mode in {"smart", "fuzzy"}
        if fuzzy_threshold is None:
            fuzzy_threshold = 0.7 if resolved_mode == "fuzzy" else 0.0
        if resolved_mode != "fuzzy":
            fuzzy_threshold = 0.0
        regex = resolved_mode == "regex"
        try:
            matches = _search_file(
                target,
                encoding,
                search,
                regex,
                int(context_lines),
                max_matches,
                case_insensitive,
                fuzzy_threshold,
            )
        except ValueError as exc:
            if original_mode == "smart":
                resolved_mode = "literal"
                regex = False
                if case_insensitive is None:
                    case_insensitive = False
                fuzzy_threshold = 0.0
                try:
                    matches = _search_file(
                        target,
                        encoding,
                        search,
                        regex,
                        int(context_lines),
                        max_matches,
                        case_insensitive,
                        fuzzy_threshold,
                    )
                except ValueError as fallback_exc:
                    await log_read(
                        "read_file_error",
                        {
                            "read_mode": "search",
                            "reason": "invalid_regex",
                            "search": search,
                            "search_mode": search_mode,
                            "error": str(fallback_exc),
                            **scan_payload,
                        },
                        include_md=True,
                    )
                    return await finalize_response({
                        "ok": False,
                        "error": "invalid regex",
                        "details": str(fallback_exc),
                        "absolute_path": str(target),
                        "repo_relative_path": rel_path,
                    }, "search")
                response["matches"] = matches
                response["max_matches"] = max_matches
                response["search_mode_fallback"] = "literal"
                response["search_mode_fallback_reason"] = "invalid_regex"
                await log_read(
                    "read_file",
                    {
                        "read_mode": "search",
                        "search": search,
                        "search_mode": search_mode,
                        "search_mode_resolved": resolved_mode,
                        "search_mode_fallback": "literal",
                        "case_insensitive": case_insensitive,
                        "fuzzy_threshold": None,
                        "context_lines": context_lines,
                        "max_matches": max_matches,
                        **scan_payload,
                    },
                    include_md=True,
                )
                return await finalize_response(response, "search")
            await log_read(
                "read_file_error",
                {
                    "read_mode": "search",
                    "reason": "invalid_regex",
                    "search": search,
                    "search_mode": search_mode,
                    "error": str(exc),
                    **scan_payload,
                },
                include_md=True,
            )
            return await finalize_response({
                "ok": False,
                "error": "invalid regex",
                "details": str(exc),
                "absolute_path": str(target),
                "repo_relative_path": rel_path,
            }, "search")
        response["matches"] = matches
        response["max_matches"] = max_matches
        await log_read(
            "read_file",
            {
                "read_mode": "search",
                "search": search,
                "search_mode": search_mode,
                "search_mode_resolved": resolved_mode,
                "case_insensitive": case_insensitive,
                "fuzzy_threshold": fuzzy_threshold if resolved_mode == "fuzzy" else None,
                "context_lines": context_lines,
                "max_matches": max_matches,
                **scan_payload,
            },
            include_md=True,
        )
        return await finalize_response(response, "search")

    if mode == "full":
        line_count = scan.get("line_count", 0)
        byte_size = scan.get("byte_size", 0)

        # Read file and check token count
        chunk = _extract_line_range(target, encoding, 1, line_count)
        content = chunk.get("content", "")
        token_count = _count_tokens(content)

        # Bypass truncation if include_full_content=True (for web dashboard/API use)
        if include_full_content or token_count <= _FULL_MODE_TOKEN_LIMIT:
            # File fits within token limit OR full content explicitly requested - return full file
            response["chunk"] = chunk
            response["full_file"] = True
            response["token_count"] = token_count
            response["include_full_content"] = include_full_content  # Track if bypass was used
            # Add warning when include_full_content bypasses normal limits
            if include_full_content and token_count > _FULL_MODE_TOKEN_LIMIT:
                response["full_content_warning"] = {
                    "message": f"Returning full file ({token_count:,} tokens) - exceeds normal limit of {_FULL_MODE_TOKEN_LIMIT:,}.",
                    "reason": "include_full_content=True requested (web dashboard/API mode)",
                    "byte_size": byte_size,
                    "line_count": line_count,
                }
            # Add usage hint for token-heavy operations
            if token_count > 5000 and not include_full_content:
                response["usage_hint"] = {
                    "message": f"This response uses {token_count:,} tokens. Consider mode='scan_only' for structure, or mode='search' for specific content.",
                    "alternatives": [
                        "mode='scan_only' - Get file structure without content (minimal tokens)",
                        "mode='search' - Find specific patterns (returns only matching lines)",
                        "mode='line_range' - Read specific sections you need",
                    ],
                }
            log_meta = {"read_mode": "full", "line_count": line_count, "token_count": token_count, **scan_payload}
            if include_full_content:
                log_meta["include_full_content"] = True
            await log_read(
                "read_file",
                log_meta,
                include_md=True,
            )
            return await finalize_response(response, "full")
        else:
            # File exceeds token limit - truncate to fit
            # Binary search to find how many lines fit in token limit
            low, high = 1, line_count
            best_lines = 100  # Minimum
            while low <= high:
                mid = (low + high) // 2
                test_chunk = _extract_line_range(target, encoding, 1, mid)
                test_tokens = _count_tokens(test_chunk.get("content", ""))
                if test_tokens <= _FULL_MODE_TOKEN_LIMIT:
                    best_lines = mid
                    low = mid + 1
                else:
                    high = mid - 1

            # Read the optimal number of lines
            chunk = _extract_line_range(target, encoding, 1, best_lines)
            actual_tokens = _count_tokens(chunk.get("content", ""))

            response["chunk"] = chunk
            response["full_file"] = False
            response["auto_truncated"] = True
            response["lines_shown"] = best_lines
            response["total_lines"] = line_count
            response["tokens_shown"] = actual_tokens
            response["token_limit"] = _FULL_MODE_TOKEN_LIMIT
            response["large_file_warning"] = {
                "message": f"File has {line_count:,} lines ({token_count:,} tokens). Showing first {best_lines:,} lines ({actual_tokens:,} tokens, limit: {_FULL_MODE_TOKEN_LIMIT:,}).",
                "recommendation": "Use mode='line_range' to read more, or mode='search' to find specific content.",
                "remaining_lines": line_count - best_lines,
                "examples": [
                    f"read_file(path='{rel_path or target}', mode='line_range', start_line={best_lines + 1}, end_line={min(best_lines + 500, line_count)})",
                    f"read_file(path='{rel_path or target}', mode='search', search='<pattern>')",
                    f"read_file(path='{rel_path or target}', mode='scan_only')  # Get structure without content",
                ],
            }
            response["usage_hint"] = {
                "message": f"mode='full' uses {actual_tokens:,} tokens. Consider targeted reads to save context.",
                "tip": "Use mode='scan_only' first to see structure, then mode='line_range' for specific sections.",
            }
            await log_read(
                "read_file",
                {"read_mode": "full", "auto_truncated": True, "line_count": line_count, "lines_shown": best_lines, "tokens_shown": actual_tokens, **scan_payload},
                include_md=True,
            )
            return await finalize_response(response, "full")

    # Unsupported mode - provide helpful error with valid options
    valid_modes = ["scan_only", "chunk", "line_range", "page", "full", "full_stream", "search"]
    return await finalize_response({
        "ok": False,
        "error": f"Unsupported read mode '{mode}'",
        "valid_modes": valid_modes,
        "mode_descriptions": {
            "scan_only": "Get file metadata and structure without content",
            "full": "Read entire file (auto-truncates large files to ~20k tokens)",
            "page": "Read paginated content (requires page_number)",
            "line_range": "Read specific lines (requires start_line, end_line)",
            "search": "Search for pattern in file (requires search parameter)",
            "chunk": "Read specific chunks by index (requires chunk_index)",
            "full_stream": "Stream chunks with pagination control",
        },
        "suggestion": f"Try mode='full' to read the file, or mode='page' with page_number=1 for pagination.",
    }, mode)
