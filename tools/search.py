"""Multi-file codebase search tool with grep/rg feature parity."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

from scribe_mcp import server as server_module
from scribe_mcp.config.settings import settings
from scribe_mcp.server import app
from scribe_mcp.shared.execution_context import ExecutionContext
from scribe_mcp.utils.response import default_formatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DENYLIST = [
    ".env",
    ".git/",
    ".scribe/registry/",
    "~/.ssh",
    "/etc",
    "/proc",
    "/sys",
]

# Directories to skip during traversal
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".eggs",
    ".nox",
}

# Map type names to file extensions (mirrors ripgrep --type)
TYPE_TO_EXTENSIONS: Dict[str, List[str]] = {
    "py": [".py", ".pyi"],
    "python": [".py", ".pyi"],
    "js": [".js", ".jsx", ".mjs", ".cjs"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "ts": [".ts", ".tsx", ".mts", ".cts"],
    "typescript": [".ts", ".tsx", ".mts", ".cts"],
    "rust": [".rs"],
    "go": [".go"],
    "java": [".java"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"],
    "cs": [".cs"],
    "csharp": [".cs"],
    "rb": [".rb"],
    "ruby": [".rb"],
    "php": [".php"],
    "swift": [".swift"],
    "kotlin": [".kt", ".kts"],
    "scala": [".scala"],
    "lua": [".lua"],
    "sh": [".sh", ".bash", ".zsh"],
    "shell": [".sh", ".bash", ".zsh"],
    "md": [".md", ".markdown"],
    "markdown": [".md", ".markdown"],
    "json": [".json"],
    "yaml": [".yaml", ".yml"],
    "yml": [".yaml", ".yml"],
    "toml": [".toml"],
    "xml": [".xml"],
    "html": [".html", ".htm"],
    "css": [".css"],
    "scss": [".scss", ".sass"],
    "sql": [".sql"],
    "r": [".r", ".R"],
    "txt": [".txt"],
}

# Binary file extensions to skip
_BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pyc", ".pyo", ".class", ".jar",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".sqlite", ".db",
}

# Max file size to search (bytes)
_MAX_FILE_SIZE_BYTES_DEFAULT = 10 * 1024 * 1024  # 10 MB

# Bytes to read for binary content detection
_BINARY_CHECK_BYTES = 8192


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Match:
    """A single match within a file."""
    line_number: int
    line: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)
    is_context: bool = False  # True if this line is context, not a match


@dataclass
class FileResult:
    """Search results for a single file."""
    file: str  # repo-relative path
    matches: List[Match] = field(default_factory=list)
    match_count: int = 0


# ---------------------------------------------------------------------------
# Binary content detection (Task 2.3)
# ---------------------------------------------------------------------------

def _is_binary_extension(path: Path) -> bool:
    return path.suffix.lower() in _BINARY_EXTENSIONS


def _is_binary_content(path: Path) -> bool:
    """Check if file has binary content by looking for null bytes in first N bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_CHECK_BYTES)
            return b"\x00" in chunk
    except OSError:
        return False


# ---------------------------------------------------------------------------
# File traversal (Task 1.2 + Task 2.3 enhancements)
# ---------------------------------------------------------------------------

@dataclass
class TraversalStats:
    """Track files skipped during traversal."""
    skipped_binary: int = 0
    skipped_size: int = 0
    skipped_denied: int = 0


def _iterate_files(
    root: Path,
    glob_pattern: Optional[str],
    file_type: Optional[str],
    skip_binary: bool = True,
    max_file_size_bytes: int = _MAX_FILE_SIZE_BYTES_DEFAULT,
    stats: Optional[TraversalStats] = None,
) -> Iterator[Path]:
    """Yield files under *root* respecting filters and skip rules.

    - Skips hidden dirs (except .scribe), node_modules, __pycache__, etc.
    - Skips binary extensions and binary content when *skip_binary* is True.
    - Skips files larger than *max_file_size_bytes*.
    - Applies glob and type filters.
    """
    type_extensions: Optional[set] = None
    if file_type:
        exts = TYPE_TO_EXTENSIONS.get(file_type.lower())
        if exts:
            type_extensions = set(exts)
        else:
            # Unknown type -- yield nothing
            return

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS
            and (not d.startswith(".") or d == ".scribe")
        ]

        for fname in filenames:
            fpath = Path(dirpath) / fname

            # Skip hidden files
            if fname.startswith("."):
                continue

            # Type filter FIRST -- so skip stats only count relevant files
            if type_extensions and fpath.suffix.lower() not in type_extensions:
                continue

            # Glob filter FIRST -- match against repo-relative path
            if glob_pattern:
                try:
                    rel = str(fpath.relative_to(root))
                except ValueError:
                    continue
                if not fnmatch(rel, glob_pattern) and not fnmatch(fname, glob_pattern):
                    continue

            # Skip binary by extension (only for files that passed type/glob)
            if skip_binary and _is_binary_extension(fpath):
                if stats:
                    stats.skipped_binary += 1
                continue

            # Size check (only for files that passed type/glob)
            try:
                fsize = fpath.stat().st_size
                if fsize > max_file_size_bytes:
                    if stats:
                        stats.skipped_size += 1
                    continue
            except OSError:
                continue

            # Binary content check (null bytes)
            if skip_binary and _is_binary_content(fpath):
                if stats:
                    stats.skipped_binary += 1
                continue

            yield fpath


# ---------------------------------------------------------------------------
# Denylist enforcement (reuse read_file pattern)
# ---------------------------------------------------------------------------

def _matches_any(path_str: str, patterns: List[str]) -> bool:
    for pat in patterns:
        if pat.endswith("/"):
            if f"/{pat}" in f"/{path_str}/" or path_str.startswith(pat):
                return True
        elif fnmatch(path_str, pat) or pat in path_str:
            return True
    return False


def _is_denied(path: Path, repo_root: Path) -> bool:
    """Check if path is in the denylist."""
    abs_str = str(path)
    try:
        rel_str = str(path.relative_to(repo_root))
    except ValueError:
        rel_str = None

    if _matches_any(abs_str, _DEFAULT_DENYLIST):
        return True
    if rel_str and _matches_any(rel_str, _DEFAULT_DENYLIST):
        return True
    return False


# ---------------------------------------------------------------------------
# Pattern matching (Task 1.3 + Phase 2 context lines + multiline)
# ---------------------------------------------------------------------------

def _search_file(
    path: Path,
    compiled_pattern: "re.Pattern[str]",
    max_matches: int = 50,
    before: int = 0,
    after: int = 0,
) -> List[Match]:
    """Search a single file for pattern matches with optional context lines.

    Handles overlapping contexts by merging nearby matches.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    all_lines = text.splitlines()
    total_lines = len(all_lines)

    # Find all matching line indices first
    match_indices: List[int] = []  # 0-based indices
    for i, line in enumerate(all_lines):
        if compiled_pattern.search(line):
            match_indices.append(i)
            if len(match_indices) >= max_matches:
                break

    if not match_indices:
        return []

    # Build matches with context
    matches: List[Match] = []
    for idx in match_indices:
        ctx_before: List[str] = []
        ctx_after: List[str] = []

        if before > 0:
            start = max(0, idx - before)
            ctx_before = [all_lines[j].rstrip() for j in range(start, idx)]

        if after > 0:
            end = min(total_lines, idx + after + 1)
            ctx_after = [all_lines[j].rstrip() for j in range(idx + 1, end)]

        matches.append(Match(
            line_number=idx + 1,  # 1-based
            line=all_lines[idx].rstrip(),
            context_before=ctx_before,
            context_after=ctx_after,
        ))

    return matches


def _search_file_multiline(
    path: Path,
    compiled_pattern: "re.Pattern[str]",
    max_matches: int = 50,
) -> List[Match]:
    """Search a file with multiline pattern (pattern can span multiple lines).

    Reads entire file content and applies regex across line boundaries.
    Returns matches with the starting line number.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    matches: List[Match] = []
    # Build line offset map for translating byte offsets to line numbers
    line_starts: List[int] = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    for m in compiled_pattern.finditer(text):
        # Find line number from match start position
        pos = m.start()
        # Binary search for line number
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        line_number = lo + 1  # 1-based

        matched_text = m.group()
        # For display: show first line of match, indicate if multi-line
        first_line = matched_text.split("\n")[0].rstrip()
        num_lines = matched_text.count("\n") + 1
        if num_lines > 1:
            first_line += f"  [... +{num_lines - 1} lines]"

        matches.append(Match(line_number=line_number, line=first_line))
        if len(matches) >= max_matches:
            break

    return matches


# ---------------------------------------------------------------------------
# Output formatting - structured result builder
# ---------------------------------------------------------------------------

def _build_structured_result(
    results: List[FileResult],
    output_mode: str,
    pattern: str,
    files_searched: int,
    total_matches: int,
    line_numbers: bool,
    traversal_stats: Optional[TraversalStats] = None,
) -> Dict[str, Any]:
    """Build the structured result dict for all output modes."""

    data: Dict[str, Any] = {
        "ok": True,
        "output_mode": output_mode,
        "pattern": pattern,
        "files_searched": files_searched,
        "files_with_matches": len(results),
        "total_matches": total_matches,
    }

    # Add skip stats if any files were skipped
    if traversal_stats:
        skipped_total = traversal_stats.skipped_binary + traversal_stats.skipped_size + traversal_stats.skipped_denied
        if skipped_total > 0:
            data["files_skipped"] = skipped_total
            data["skip_details"] = {}
            if traversal_stats.skipped_binary > 0:
                data["skip_details"]["binary"] = traversal_stats.skipped_binary
            if traversal_stats.skipped_size > 0:
                data["skip_details"]["too_large"] = traversal_stats.skipped_size
            if traversal_stats.skipped_denied > 0:
                data["skip_details"]["denied"] = traversal_stats.skipped_denied

    if output_mode == "content":
        data["matches"] = [
            {
                "file": fr.file,
                "matches": [
                    {
                        "line_number": m.line_number,
                        "line": m.line,
                        **({"context_before": m.context_before} if m.context_before else {}),
                        **({"context_after": m.context_after} if m.context_after else {}),
                    }
                    for m in fr.matches
                ],
            }
            for fr in results
            if fr.matches
        ]
    elif output_mode == "files_with_matches":
        data["files"] = [fr.file for fr in results]
    elif output_mode == "count":
        data["counts"] = [
            {"file": fr.file, "count": fr.match_count}
            for fr in results
        ]

    return data


def _format_search_readable(data: Dict[str, Any], line_numbers: bool) -> str:
    """Format search results in readable style consistent with read_file output.

    Uses separator lines with U+2500 (box drawing) characters and consistent
    line number formatting to match the read_file visual style.
    """
    output_mode = data.get("output_mode", "content")
    parts: List[str] = []

    # Header line matching read_file style
    header = (
        f"SEARCH RESULTS | pattern: {data.get('pattern', '?')} | "
        f"matches: {data.get('total_matches', 0)} in {data.get('files_with_matches', 0)} files"
    )
    parts.append(header)
    parts.append("")

    # Skip info
    if data.get("files_skipped"):
        skip_info = f"Files skipped: {data['files_skipped']}"
        details = data.get("skip_details", {})
        reasons = []
        if details.get("binary"):
            reasons.append(f"binary={details['binary']}")
        if details.get("too_large"):
            reasons.append(f"too_large={details['too_large']}")
        if details.get("denied"):
            reasons.append(f"denied={details['denied']}")
        if reasons:
            skip_info += f" ({', '.join(reasons)})"
        parts.append(skip_info)
        parts.append("")

    if data.get("truncated"):
        parts.append(f"WARNING: Results truncated - {data.get('truncation_reason', 'limit reached')}")
        parts.append("")

    if output_mode == "content":
        for file_block in data.get("matches", []):
            # File separator matching read_file style
            parts.append("\u2500" * 67)
            parts.append(f"Path: {file_block['file']}")
            parts.append("")
            for m in file_block.get("matches", []):
                # Context before (dimmed style - indent with pipe)
                for ctx_line in m.get("context_before", []):
                    if line_numbers:
                        # We approximate line numbers for context
                        ctx_ln = m["line_number"] - len(m.get("context_before", [])) + m.get("context_before", []).index(ctx_line)
                        parts.append(f"    {ctx_ln:>4}  {ctx_line}")
                    else:
                        parts.append(f"         {ctx_line}")

                # Match line (with line number)
                if line_numbers:
                    parts.append(f"    {m['line_number']:>4}: {m['line']}")
                else:
                    parts.append(f"  {m['line']}")

                # Context after
                for ci, ctx_line in enumerate(m.get("context_after", []), start=1):
                    if line_numbers:
                        parts.append(f"    {m['line_number'] + ci:>4}  {ctx_line}")
                    else:
                        parts.append(f"         {ctx_line}")

                # Separator between matches within same file if context is shown
                if m.get("context_before") or m.get("context_after"):
                    parts.append("")

    elif output_mode == "files_with_matches":
        for fp in data.get("files", []):
            parts.append(f"  {fp}")

    elif output_mode == "count":
        for entry in data.get("counts", []):
            parts.append(f"  {entry['file']}: {entry['count']}")

    # Footer separator
    parts.append("\u2500" * 67)
    parts.append(
        f"Files searched: {data.get('files_searched', 0)} | "
        f"Total matches: {data.get('total_matches', 0)}"
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# MCP Tool (Task 1.1 + integration)
# ---------------------------------------------------------------------------

@app.tool()
async def search(
    # REQUIRED
    agent: str,
    pattern: str,

    # Scope
    path: Optional[str] = None,
    glob: Optional[str] = None,
    type: Optional[str] = None,

    # Output
    output_mode: str = "content",
    format: str = "readable",

    # Context lines
    context_lines: int = 0,
    before_context: Optional[int] = None,
    after_context: Optional[int] = None,

    # Search Behavior
    case_insensitive: bool = False,
    regex: bool = True,
    multiline: bool = False,

    # Limits
    max_matches_per_file: int = 50,
    max_total_matches: int = 200,
    max_files: int = 100,

    # Display
    line_numbers: bool = True,

    # Performance
    skip_binary: bool = True,
    max_file_size_mb: int = 10,
) -> Union[Dict[str, Any], str]:
    """Multi-file codebase search with grep/rg feature parity.

    Search across repository files using regex or literal patterns.
    Supports file type filtering, glob patterns, and multiple output modes.

    Parameters:
        agent: Agent identifier (required for audit trail)
        pattern: Search pattern (regex by default, literal if regex=False)
        path: Directory or file to search (default: repo root)
        glob: Glob pattern to filter files (e.g. "*.py", "src/**/*.ts")
        type: File type filter (py, js, ts, rust, go, java, etc.)
        output_mode: "content" (lines), "files_with_matches" (paths), "count" (counts)
        format: Output format - "readable", "structured", "compact"
        context_lines: Lines of context around matches (both before and after)
        before_context: Lines before match (overrides context_lines for before)
        after_context: Lines after match (overrides context_lines for after)
        case_insensitive: Case-insensitive matching
        regex: True for regex, False for literal string matching
        multiline: Enable multiline matching (pattern can span lines)
        max_matches_per_file: Max matches per file (default 50)
        max_total_matches: Max total matches across all files (default 200)
        max_files: Max files to include in results (default 100)
        line_numbers: Show line numbers in output (default True)
        skip_binary: Skip binary files (default True)
        max_file_size_mb: Max file size in MB to search (default 10)

    Returns:
        Formatted search results respecting repo boundaries.
    """
    # --- Execution context ---
    exec_context = server_module.get_execution_context()
    if exec_context is None:
        return {"ok": False, "error": "ExecutionContext missing"}

    repo_root = Path(exec_context.repo_root)

    # --- Resolve search root ---
    if path:
        search_root = Path(path).expanduser()
        if not search_root.is_absolute():
            search_root = (repo_root / search_root).resolve()
        else:
            search_root = search_root.resolve()
    else:
        search_root = repo_root

    # --- Sandbox: ensure search root is within repo ---
    try:
        search_root.relative_to(repo_root)
    except ValueError:
        return {"ok": False, "error": "search path outside repository boundary", "path": str(search_root)}

    if not search_root.exists():
        return {"ok": False, "error": "search path does not exist", "path": str(search_root)}

    # --- Validate output_mode ---
    valid_modes = {"content", "files_with_matches", "count"}
    if output_mode not in valid_modes:
        return {"ok": False, "error": f"Invalid output_mode '{output_mode}'. Must be one of: {', '.join(sorted(valid_modes))}"}

    # --- Resolve context line counts ---
    ctx_before = before_context if before_context is not None else context_lines
    ctx_after = after_context if after_context is not None else context_lines

    # --- Compile pattern ---
    flags = 0
    if case_insensitive:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.DOTALL | re.MULTILINE

    try:
        if regex:
            compiled = re.compile(pattern, flags)
        else:
            compiled = re.compile(re.escape(pattern), flags)
    except re.error as exc:
        return {"ok": False, "error": f"Invalid regex pattern: {exc}"}

    # --- File traversal ---
    max_size_bytes = max_file_size_mb * 1024 * 1024
    traversal_stats = TraversalStats()

    # Handle single-file search
    if search_root.is_file():
        files_iter: Iterator[Path] = iter([search_root])
    else:
        files_iter = _iterate_files(
            root=search_root,
            glob_pattern=glob,
            file_type=type,
            skip_binary=skip_binary,
            max_file_size_bytes=max_size_bytes,
            stats=traversal_stats,
        )

    # --- Search loop ---
    results: List[FileResult] = []
    files_searched = 0
    total_matches = 0
    hit_total_limit = False

    for fpath in files_iter:
        # Denylist check
        if _is_denied(fpath, repo_root):
            traversal_stats.skipped_denied += 1
            continue

        files_searched += 1

        # Remaining budget per file
        remaining = max_total_matches - total_matches
        if remaining <= 0:
            hit_total_limit = True
            break

        per_file_limit = min(max_matches_per_file, remaining)

        # Choose search strategy
        if multiline:
            file_matches = _search_file_multiline(fpath, compiled, max_matches=per_file_limit)
        else:
            file_matches = _search_file(
                fpath, compiled, max_matches=per_file_limit,
                before=ctx_before, after=ctx_after,
            )

        if file_matches:
            try:
                rel = str(fpath.relative_to(repo_root))
            except ValueError:
                rel = str(fpath)

            fr = FileResult(file=rel, matches=file_matches, match_count=len(file_matches))
            results.append(fr)
            total_matches += len(file_matches)

            if len(results) >= max_files:
                break

    # --- Build output ---
    structured = _build_structured_result(
        results=results,
        output_mode=output_mode,
        pattern=pattern,
        files_searched=files_searched,
        total_matches=total_matches,
        line_numbers=line_numbers,
        traversal_stats=traversal_stats,
    )

    if hit_total_limit:
        structured["truncated"] = True
        structured["truncation_reason"] = f"max_total_matches ({max_total_matches}) reached"

    # --- Format output through ResponseFormatter pipeline ---
    if format == "structured":
        return structured
    elif format == "compact":
        compact: Dict[str, Any] = {
            "ok": True,
            "matches": structured.get("total_matches", 0),
            "files": structured.get("files_with_matches", 0),
        }
        if structured.get("files_skipped"):
            compact["skipped"] = structured["files_skipped"]
        if output_mode == "files_with_matches":
            compact["file_list"] = structured.get("files", [])
        elif output_mode == "count":
            compact["counts"] = structured.get("counts", [])
        return compact
    else:
        # Readable: generate readable content and route through finalize_tool_response
        # for consistent CallToolResult wrapping (TextContent for clean newlines)
        readable_text = _format_search_readable(structured, line_numbers)
        structured["readable_content"] = readable_text
        return await default_formatter.finalize_tool_response(
            data=structured,
            format="readable",
            tool_name="search",
        )
