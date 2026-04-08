"""Jinja2-based template engine with security sandboxing and custom template support."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from jinja2 import (
    Environment,
    FileSystemLoader,
    TemplateNotFound,
    TemplateRuntimeError,
    TemplateSyntaxError,
    StrictUndefined,
)
from jinja2.exceptions import TemplateNotFound as TemplateNotFoundError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment

try:
    from scribe_mcp.config.repo_config import RepoConfig, RepoDiscovery
except Exception:  # pragma: no cover - repo config optional during bootstrap
    RepoConfig = None  # type: ignore
    RepoDiscovery = None  # type: ignore

# Import canonical slugify from utils (designed for early import safety)
from scribe_mcp.utils.slug import slugify_project_name
from scribe_mcp.config.paths import templates_dir


def get_template_root():
    """Get template root directory."""
    return templates_dir()

# Setup logging for template engine
template_logger = logging.getLogger(__name__)

# Legacy template pattern for backward compatibility
LEGACY_PATTERN = r'\{(\w+)\}'

# Default template variables available in all templates
DEFAULT_VARIABLES = {
    "project_name": "",
    "project_slug": "",
    "timestamp": "",
    "agent": "",
    "utcnow": "",
    "version": "1.0",
    "status": "active",
}

# Restricted builtins for security
RESTRICTED_BUILTINS = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
}


class TemplateEngineError(Exception):
    """Base exception for template engine errors."""
    pass


class TemplateValidationError(TemplateEngineError):
    """Raised when template validation fails."""
    pass


class TemplateRenderError(TemplateEngineError):
    """Raised when template rendering fails."""
    pass


class Jinja2TemplateEngine:
    """Jinja2-based template engine with security sandboxing and custom templates."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        project_name: Optional[str] = None,
        security_mode: str = "sandbox",
        repo_config: Optional["RepoConfig"] = None,
        template_pack: Optional[str] = None,
    ):
        """
        Initialize the Jinja2 template engine.

        Args:
            project_root: Root directory of the project
            project_name: Name of the project
            security_mode: Security mode - "sandbox", "immutable", or "none"
        """
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self.project_name = project_name or ""
        self.project_slug = slugify_project_name(project_name or "")
        self.repo_root: Path = self.project_root

        # Repository configuration (for templates pack/custom dirs)
        self.repo_config = repo_config or self._load_repo_config()
        self.template_pack = template_pack or (
            self.repo_config.templates_pack  # type: ignore[attr-defined]
            if self.repo_config and getattr(self.repo_config, "templates_pack", None)
            else "default"
        )

        # Template directories
        self._template_dir_types: Dict[Path, str] = {}
        self.template_dirs = self._discover_template_directories()

        if not self.template_dirs:
            raise TemplateEngineError("No template directories discovered. Ensure templates are available.")

        # Security mode setup
        self.security_mode = security_mode
        self.env = self._create_jinja2_environment()

        # Custom variables cache
        self._custom_variables: Optional[Dict[str, Any]] = None

        template_logger.debug(f"Initialized template engine for project '{project_name}' with {len(self.template_dirs)} template directories")

    def _load_repo_config(self) -> Optional["RepoConfig"]:
        """Attempt to load per-repo configuration for template packs/custom dirs."""
        if RepoDiscovery is None:
            return None
        try:
            repo_root = RepoDiscovery.find_repo_root(self.project_root)
            if repo_root:
                self.repo_root = repo_root
                return RepoDiscovery.load_config(repo_root)
        except Exception as exc:  # pragma: no cover - config optional
            template_logger.debug(f"Repo config load skipped: {exc}")
        return None

    def _discover_template_directories(self) -> List[Path]:
        """Discover template directories in order of precedence."""
        template_dirs: List[Path] = []
        seen: Set[Path] = set()

        def add_dir(path: Optional[Path], dir_type: str) -> None:
            if not path:
                return
            try:
                resolved = path.resolve()
            except FileNotFoundError:
                resolved = path
            if not resolved.exists() or not resolved.is_dir():
                template_logger.debug(f"Skipping missing template directory: {resolved}")
                return
            if resolved in seen:
                return
            template_dirs.append(resolved)
            self._template_dir_types[resolved] = dir_type
            seen.add(resolved)
            template_logger.debug(f"Registered template directory ({dir_type}): {resolved}")

        # 1. Project-specific custom templates (.scribe/templates/)
        add_dir(self.project_root / ".scribe" / "templates", "project_custom")

        # 2. Repo-level custom templates if configured
        if self.repo_config and getattr(self.repo_config, "custom_templates_dir", None):
            add_dir(self.repo_config.custom_templates_dir, "repo_custom")  # type: ignore[attr-defined]

        # 3. Project-root templates directory (optional pattern some repos use)
        add_dir(self.project_root / "templates", "project_templates")

        # 4. Built-in / global templates bundled with Scribe MCP
        try:
            builtin_root = get_template_root()
        except Exception as exc:
            template_logger.warning(f"Could not determine built-in template root: {exc}")
            builtin_root = None

        if builtin_root:
            add_dir(builtin_root / "custom", "builtin_custom")

            # Template pack directories (default pack lives under packs/<name>)
            pack_candidates = [
                builtin_root / "packs" / self.template_pack,
                builtin_root / self.template_pack,  # legacy layout fallback
            ]
            for pack_dir in pack_candidates:
                if pack_dir.exists():
                    add_dir(pack_dir, f"pack:{self.template_pack}")
                    add_dir(pack_dir / "documents", f"pack_documents:{self.template_pack}")
                    add_dir(pack_dir / "fragments", f"pack_fragments:{self.template_pack}")
                    break  # stop after first matching pack layout

            # Core built-in documents/fragments
            add_dir(builtin_root, "builtin_root")
            add_dir(builtin_root / "documents", "builtin_documents")
            add_dir(builtin_root / "fragments", "builtin_fragments")

        return template_dirs

    def _create_jinja2_environment(self) -> Environment:
        """Create Jinja2 environment with appropriate security settings."""
        # Common environment configuration
        common_kwargs = dict(
            loader=FileSystemLoader([str(d) for d in self.template_dirs]),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            undefined=StrictUndefined,  # Enable strict undefined checking
        )

        # Normalize security mode - accept both "none" and "unrestricted"
        normalized_mode = self.security_mode.lower()
        if normalized_mode in ("none", "unrestricted"):
            normalized_mode = "none"

        if normalized_mode == "immutable":
            # Most restrictive - no mutable operations
            env = ImmutableSandboxedEnvironment(**common_kwargs)
            template_logger.debug("Created immutable sandboxed environment with strict undefined")
        elif normalized_mode == "sandbox":
            # Balanced security - limited operations allowed
            env = SandboxedEnvironment(**common_kwargs)
            template_logger.debug("Created sandboxed environment with strict undefined")
        else:  # "none" or unrestricted
            env = Environment(**common_kwargs)
            template_logger.debug("Created unrestricted environment with strict undefined")

        # Add custom filters and globals
        self._add_custom_filters(env)
        self._add_custom_globals(env)

        return env

    def _add_custom_filters(self, env: Environment) -> None:
        """Add custom Jinja2 filters."""
        def slugify(text: str) -> str:
            """Convert text to URL-friendly slug."""
            return slugify_project_name(text)

        def format_bytes(size: int) -> str:
            """Format bytes in human-readable format."""
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"

        env.filters['slugify'] = slugify
        env.filters['format_bytes'] = format_bytes

    def _add_custom_globals(self, env: Environment) -> None:
        """Add custom global functions and variables."""
        project_root = self.project_root.resolve()
        allowed_extensions = {".md", ".markdown", ".txt", ".json"}

        def include_file(path: str) -> str:
            """Include file content safely, locked to project directory."""
            try:
                # Resolve path relative to project root and validate it stays within project
                target_path = (project_root / path).resolve()

                # Security check: ensure the resolved path is still within project_root
                if project_root not in target_path.parents and target_path != project_root:
                    return f"[Security: path '{path}' outside project directory]"

                # Restrict included files to a small, safe set of extensions
                if target_path.suffix.lower() not in allowed_extensions:
                    return f"[Security: unsupported file extension '{target_path.suffix}' for include_file]"

                if not target_path.exists():
                    return f"[File not found: {path}]"

                return target_path.read_text(encoding='utf-8')
            except Exception as e:
                return f"[Error reading file {path}: {e}]"

        env.globals['include_file'] = include_file
        env.globals['restricted_builtins'] = RESTRICTED_BUILTINS

    def load_custom_variables(self) -> Dict[str, Any]:
        """Load custom variables from .scribe/variables.json."""
        if self._custom_variables is not None:
            return self._custom_variables

        variables_file = self.project_root / ".scribe" / "variables.json"
        custom_vars = {}

        if variables_file.exists():
            try:
                with open(variables_file, 'r', encoding='utf-8') as f:
                    custom_vars = json.load(f)
                template_logger.debug(f"Loaded {len(custom_vars)} custom variables from {variables_file}")
            except json.JSONDecodeError as e:
                template_logger.warning(f"Invalid JSON in variables file {variables_file}: {e}")
            except Exception as e:
                template_logger.error(f"Error loading variables file {variables_file}: {e}")

        self._custom_variables = custom_vars
        return custom_vars

    def _build_context(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build template context from defaults, custom variables, and metadata."""
        context = DEFAULT_VARIABLES.copy()

        # Add project-specific defaults
        context.update({
            "project_name": self.project_name,
            "project_slug": self.project_slug,
            "project_root": str(self.project_root),
        })

        # Add time variables that were declared in defaults but never populated
        now = datetime.now(timezone.utc)
        context.update({
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "utcnow": now.isoformat(),
            "date_utc": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        })

        # Provide sensible defaults for legacy-compatible fields
        context.setdefault("author", "Scribe")

        # Add custom variables
        custom_vars = self.load_custom_variables()
        context.update(custom_vars)

        # Add runtime metadata (both as dict + flattened keys)
        metadata_payload = metadata.copy() if isinstance(metadata, dict) else {}
        context["metadata"] = metadata_payload
        if metadata_payload:
            context.update(metadata_payload)

        # Mirror key fields using uppercase variants for backward compatibility
        uppercase_keys = {
            "project_name",
            "project_slug",
            "project_root",
            "timestamp",
            "utcnow",
            "date_utc",
            "author",
            "agent",
            "version",
            "status",
        }
        for key in uppercase_keys:
            value = context.get(key)
            if value is None:
                continue
            context[key.upper()] = value

        return context

    def _render_legacy_template(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Legacy fallback for old {variable} template syntax.

        This provides backward compatibility with the old string-based templating system.
        """
        try:
            # Create a safe dictionary for str.format_map that returns empty string for missing keys
            class SafeDict(dict):
                def __missing__(self, key):
                    return f"{{?{key}}}"  # Mark missing variables

            safe_context = SafeDict(context)
            result = template_string.format_map(safe_context)
            template_logger.debug("Legacy template rendering successful")
            return result
        except Exception as e:
            template_logger.error(f"Legacy template rendering failed: {e}")
            raise TemplateRenderError(f"Both Jinja2 and legacy template rendering failed: {e}")

    def render_template(
        self,
        template_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        strict: bool = False,
        fallback: bool = True
    ) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Name of the template file
            metadata: Additional variables for template rendering
            strict: When True, operate in \"fail-hard\" mode and do not attempt legacy fallback.
                    When False, use best-effort rendering (including optional legacy fallback when enabled).

        Returns:
            Rendered template content

        Raises:
            TemplateNotFoundError: If template file is not found
            TemplateSyntaxError: If template has syntax errors
            TemplateRenderError: If rendering fails
        """
        try:
            # Load template
            template = self.env.get_template(template_name)

            # Build context
            context = self._build_context(metadata)

            # Render template (environment already has StrictUndefined configured)
            result = template.render(**context)

            template_logger.debug(f"Successfully rendered template '{template_name}' ({len(result)} chars)")
            return result

        except TemplateNotFound as e:
            raise TemplateNotFoundError(f"Template '{template_name}' not found in template directories: {self.template_dirs}")
        except (TemplateSyntaxError, TemplateRuntimeError) as e:
            # In strict mode, bypass legacy fallback and raise immediately.
            use_fallback = fallback and not strict
            if use_fallback:
                template_logger.warning(f"Jinja2 rendering failed for '{template_name}', attempting legacy fallback: {e}")
                try:
                    # Try to get template source and use legacy rendering
                    source, _, _ = self.env.loader.get_source(self.env, template_name)
                    context = self._build_context(metadata)
                    return self._render_legacy_template(source, context)
                except Exception as fallback_error:
                    template_logger.error(f"Legacy fallback also failed for '{template_name}': {fallback_error}")
                    raise TemplateRenderError(f"Both Jinja2 and legacy rendering failed for '{template_name}': {e}")
            else:
                if isinstance(e, TemplateSyntaxError):
                    raise TemplateValidationError(f"Template syntax error in '{template_name}': {e}")
                else:
                    raise TemplateRenderError(f"Template runtime error in '{template_name}': {e}")
        except Exception as e:
            raise TemplateRenderError(f"Unexpected error rendering template '{template_name}': {e}")

    def render_string(
        self,
        template_string: str,
        metadata: Optional[Dict[str, Any]] = None,
        strict: bool = False,
        fallback: bool = True
    ) -> str:
        """
        Render a template string with the given context.

        Args:
            template_string: Jinja2 template string
            metadata: Additional variables for template rendering
            strict: Whether to raise errors for undefined variables

        Returns:
            Rendered content
        """
        try:
            template = self.env.from_string(template_string)
            context = self._build_context(metadata)

            # Render template string (environment already has StrictUndefined configured)
            result = template.render(**context)

            template_logger.debug(f"Successfully rendered template string ({len(result)} chars)")
            return result

        except (TemplateSyntaxError, TemplateRuntimeError) as e:
            # In strict mode, bypass legacy fallback and raise immediately.
            use_fallback = fallback and not strict
            if use_fallback:
                template_logger.warning(f"Jinja2 rendering failed for template string, attempting legacy fallback: {e}")
                try:
                    context = self._build_context(metadata)
                    return self._render_legacy_template(template_string, context)
                except Exception as fallback_error:
                    template_logger.error(f"Legacy fallback also failed for template string: {fallback_error}")
                    raise TemplateRenderError(f"Both Jinja2 and legacy rendering failed for template string: {e}")
            else:
                if isinstance(e, TemplateSyntaxError):
                    raise TemplateValidationError(f"Template syntax error: {e}")
                else:
                    raise TemplateRenderError(f"Template runtime error: {e}")
        except Exception as e:
            raise TemplateRenderError(f"Unexpected error rendering template string: {e}")

    def validate_template(self, template_name: str) -> Dict[str, Any]:
        """
        Validate a template without rendering it.

        Returns:
            Validation result with success status and any errors
        """
        result = {
            "template": template_name,
            "valid": False,
            "errors": [],
            "warnings": [],
            "line_count": 0,
            "size_bytes": 0,
        }

        try:
            # Resolve source via loader for proper parsing and stats
            source, filename, uptodate = self.env.loader.get_source(self.env, template_name)

            # Get template stats
            if filename:
                result["size_bytes"] = Path(filename).stat().st_size if Path(filename).exists() else 0
                result["line_count"] = len(source.splitlines())

            # Parse without rendering to validate syntax
            self.env.parse(source)

            result["valid"] = True
            template_logger.debug(f"Template '{template_name}' validation passed")

        except TemplateNotFound:
            result["errors"].append(f"Template '{template_name}' not found")
        except TemplateSyntaxError as e:
            result["errors"].append(f"Syntax error at line {e.lineno}: {e.message}")
        except Exception as e:
            result["errors"].append(f"Validation error: {e}")

        return result

    def list_templates(self, extension: str = ".md") -> List[str]:
        """List all available templates with the given extension (recursive)."""
        templates = []

        for template_dir in self.template_dirs:
            # Use rglob for recursive discovery
            for template_path in template_dir.rglob(f"*{extension}"):
                relative_path = template_path.relative_to(template_dir)
                templates.append(str(relative_path))

        # Remove duplicates while preserving order
        seen = set()
        unique_templates = []
        for template in templates:
            if template not in seen:
                seen.add(template)
                unique_templates.append(template)

        return unique_templates

    def describe_template_directories(self) -> List[Dict[str, str]]:
        """Return metadata about each discovered template directory."""
        directories: List[Dict[str, str]] = []
        for template_dir in self.template_dirs:
            directories.append({
                "path": str(template_dir),
                "type": self._template_dir_types.get(template_dir, "unknown"),
            })
        return directories

    def get_template_info(self, template_name: str) -> Dict[str, Any]:
        """Get detailed information about a template."""
        info = {
            "name": template_name,
            "found": False,
            "path": None,
            "size_bytes": 0,
            "line_count": 0,
            "last_modified": None,
            "template_type": "unknown",
        }

        for template_dir in self.template_dirs:
            template_path = template_dir / template_name
            if template_path.exists():
                info["found"] = True
                info["path"] = str(template_path)
                info["size_bytes"] = template_path.stat().st_size
                info["line_count"] = len(template_path.read_text(encoding='utf-8').splitlines())
                info["last_modified"] = template_path.stat().st_mtime
                info["template_type"] = self._template_dir_types.get(template_dir, "unknown")
                break

        return info
