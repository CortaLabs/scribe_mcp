"""Security and sandboxing for multi-repository Scribe deployment.

This module provides safety rails to ensure Scribe operations are contained
within the intended repository boundaries and respect repository-specific
permissions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set

from scribe_mcp.config.repo_config import RepoConfig


class PathSandbox:
    """Path sandboxing to ensure operations stay within repository boundaries."""

    def __init__(self, repo_config: RepoConfig):
        self.repo_root = repo_config.repo_root.resolve()
        self.allowed_paths: Set[Path] = set()
        self.denied_paths: Set[Path] = set()
        self._initialize_allowed_paths(repo_config)

    def _initialize_allowed_paths(self, config: RepoConfig) -> None:
        """Initialize the set of allowed paths for this repository."""
        # Always allow repository root
        self.allowed_paths.add(self.repo_root)

        # Allow documentation directory
        self.allowed_paths.add(config.dev_plans_dir.resolve())

        # Allow plugins directory if it exists
        if config.plugins_dir and config.plugins_dir.exists():
            self.allowed_paths.add(config.plugins_dir.resolve())

        # Allow custom templates directory if it exists
        if config.custom_templates_dir and config.custom_templates_dir.exists():
            self.allowed_paths.add(config.custom_templates_dir.resolve())

        # Allow scribe configuration directory
        scribe_dir = self.repo_root / ".scribe"
        if scribe_dir.exists():
            self.allowed_paths.add(scribe_dir.resolve())

        # Allow database directory if specified
        if config.db_path:
            db_parent = config.db_path.parent.resolve()
            self.allowed_paths.add(db_parent)

    def is_allowed(self, path: Path) -> bool:
        """
        Check if a path is allowed to be accessed.

        Args:
            path: Path to check

        Returns:
            True if path is allowed, False otherwise
        """
        # Security check 1: Reject null bytes in paths (path traversal via null injection)
        try:
            path_str = str(path)
            if '\x00' in path_str:
                return False
        except (ValueError, TypeError):
            # Path with null bytes or invalid path
            return False

        # Security check 2: Check for suspicious patterns before resolution
        try:
            path_str = str(path)
            # Reject URL-encoded path traversal patterns
            if '..%2f' in path_str.lower() or '..%5c' in path_str.lower():
                return False
        except (ValueError, TypeError):
            return False

        # Security check 3: Block ALL symlinks by default for maximum security
        # Symlinks can be hijacked and changed after initial validation
        try:
            if path.is_symlink():
                return False  # Block all symlinks
        except (OSError, ValueError, PermissionError):
            # Error checking symlink - safest to deny
            return False

        # Security check 4: Resolve path and check against allowed paths
        try:
            resolved_path = path.resolve()
        except (OSError, ValueError, RuntimeError):
            # Path resolution failed - safest to deny
            return False

        # Check if explicitly denied
        for denied_path in self.denied_paths:
            if resolved_path == denied_path or resolved_path.is_relative_to(denied_path):
                return False

        # Check if explicitly allowed
        for allowed_path in self.allowed_paths:
            if resolved_path == allowed_path or resolved_path.is_relative_to(allowed_path):
                return True

        # Default to deny
        return False

    def sandbox_path(self, path: Path) -> Path:
        """
        Ensure a path is within the sandbox, raising an exception if not.

        Args:
            path: Path to sandbox

        Returns:
            Same path if it's allowed

        Raises:
            SecurityError: If path is not allowed
        """
        if not self.is_allowed(path):
            raise SecurityError(f"Path {path} is outside allowed repository boundaries")
        return path

    def get_safe_relative_path(self, path: Path) -> Path:
        """
        Get a safe relative path within the repository.

        Args:
            path: Path to make relative

        Returns:
            Relative path within repository

        Raises:
            SecurityError: If path is not within repository
        """
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(self.repo_root):
            raise SecurityError(f"Path {path} is outside repository root {self.repo_root}")

        return resolved_path.relative_to(self.repo_root)


class PermissionChecker:
    """Permission checker for repository-specific operations."""

    def __init__(self, repo_config: RepoConfig):
        self.config = repo_config

    def check_permission(self, operation: str, context: Dict[str, Any] = None) -> bool:
        """
        Check if an operation is allowed.

        Args:
            operation: Operation type (read, write, append, rotate, etc.)
            context: Additional context for the operation

        Returns:
            True if operation is allowed, False otherwise
        """
        context = context or {}
        permissions = self.config.permissions

        # Check basic permissions
        if operation == "rotate" and not permissions.get("allow_rotate", True):
            return False

        if operation == "append" and not permissions.get("allow_append", True):
            return False

        if operation == "read" and not permissions.get("allow_read", True):
            return False

        if operation == "generate_docs" and not permissions.get("allow_generate_docs", True):
            return False

        if operation == "bulk_entries" and not permissions.get("allow_bulk_entries", True):
            return False

        # Check project requirement (opt-out for internal file helpers)
        if operation in ["append", "read", "rotate"] and permissions.get("require_project", False):
            if context.get("enforce_project") is False:
                return True
            if not context.get("project_name"):
                return False

        # Add custom permission logic here as needed

        return True

    def validate_operation(self, operation: str, context: Dict[str, Any] = None) -> None:
        """
        Validate an operation, raising an exception if not allowed.

        Args:
            operation: Operation type
            context: Additional context

        Raises:
            PermissionError: If operation is not allowed
        """
        if not self.check_permission(operation, context):
            raise PermissionError(f"Operation '{operation}' is not allowed for this repository")


class SecurityError(Exception):
    """Raised when a security constraint is violated."""
    pass


class PermissionError(Exception):
    """Raised when a permission constraint is violated."""
    pass


class MultiTenantSafety:
    """Multi-tenant safety coordinator for global Scribe deployment."""

    def __init__(self):
        self.active_sandboxes: Dict[str, PathSandbox] = {}
        self.active_permission_checkers: Dict[str, PermissionChecker] = {}

    def get_sandbox(self, repo_root: Path) -> PathSandbox:
        """
        Get or create a sandbox for a repository.

        Args:
            repo_root: Repository root path

        Returns:
            PathSandbox instance
        """
        repo_key = str(repo_root.resolve())

        if repo_key not in self.active_sandboxes:
            from scribe_mcp.config.repo_config import RepoDiscovery
            config = RepoDiscovery.load_config(repo_root)
            self.active_sandboxes[repo_key] = PathSandbox(config)
            self.active_permission_checkers[repo_key] = PermissionChecker(config)

        return self.active_sandboxes[repo_key]

    def get_permission_checker(self, repo_root: Path) -> PermissionChecker:
        """
        Get or create a permission checker for a repository.

        Args:
            repo_root: Repository root path

        Returns:
            PermissionChecker instance
        """
        repo_key = str(repo_root.resolve())

        if repo_key not in self.active_permission_checkers:
            self.get_sandbox(repo_root)  # This creates both sandbox and checker

        return self.active_permission_checkers[repo_key]

    def safe_file_operation(self, repo_root: Path, file_path: Path, operation: str, context: Dict[str, Any] = None) -> Path:
        """
        Perform a safe file operation within repository boundaries.

        Args:
            repo_root: Repository root
            file_path: File path to operate on
            operation: Type of operation
            context: Additional context

        Returns:
            Sanitized file path

        Raises:
            SecurityError: If path is not allowed
            PermissionError: If operation is not allowed
        """
        sandbox = self.get_sandbox(repo_root)
        permission_checker = self.get_permission_checker(repo_root)

        # Sandbox the path first so security errors surface before permission errors.
        safe_path = sandbox.sandbox_path(file_path)

        # Check permissions after sandbox validation.
        permission_checker.validate_operation(operation, context)

        return safe_path

    def validate_project_access(self, repo_root: Path, project_name: str, operation: str) -> None:
        """
        Validate access to a specific project within a repository.

        Args:
            repo_root: Repository root
            project_name: Project name
            operation: Operation type

        Raises:
            SecurityError: If project access is not allowed
            PermissionError: If operation is not allowed
        """
        from scribe_mcp.config.repo_config import RepoDiscovery

        config = RepoDiscovery.load_config(repo_root)
        project_path = config.get_project_docs_dir(project_name)

        sandbox = self.get_sandbox(repo_root)
        permission_checker = self.get_permission_checker(repo_root)

        # Check if project directory is within allowed paths
        if not sandbox.is_allowed(project_path):
            raise SecurityError(f"Project directory {project_path} is not within repository boundaries")

        # Check operation permissions
        context = {"project_name": project_name}
        permission_checker.validate_operation(operation, context)

    def cleanup_repository(self, repo_root: Path) -> None:
        """
        Cleanup sandbox and permission checker for a repository.

        Args:
            repo_root: Repository root to cleanup
        """
        repo_key = str(repo_root.resolve())
        self.active_sandboxes.pop(repo_key, None)
        self.active_permission_checkers.pop(repo_key, None)


# Global multi-tenant safety instance
_safety_instance: Optional[MultiTenantSafety] = None


def get_safety_instance() -> MultiTenantSafety:
    """Get the global multi-tenant safety instance."""
    global _safety_instance
    if _safety_instance is None:
        _safety_instance = MultiTenantSafety()
    return _safety_instance


def safe_path(repo_root: Path, path: Path) -> Path:
    """Get a sandboxed path within a repository."""
    return get_safety_instance().get_sandbox(repo_root).sandbox_path(path)


def check_permission(repo_root: Path, operation: str, context: Dict[str, Any] = None) -> bool:
    """Check if an operation is allowed for a repository."""
    return get_safety_instance().get_permission_checker(repo_root).check_permission(operation, context)


def validate_operation(repo_root: Path, operation: str, context: Dict[str, Any] = None) -> None:
    """Validate an operation for a repository."""
    get_safety_instance().get_permission_checker(repo_root).validate_operation(operation, context)


def safe_file_operation(repo_root: Path, file_path: Path, operation: str, context: Dict[str, Any] = None) -> Path:
    """Perform a safe file operation."""
    return get_safety_instance().safe_file_operation(repo_root, file_path, operation, context)


def validate_project_access(repo_root: Path, project_name: str, operation: str) -> None:
    """Validate access to a project."""
    get_safety_instance().validate_project_access(repo_root, project_name, operation)
