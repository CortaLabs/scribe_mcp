#!/usr/bin/env python3
"""Scribe CLI utilities for repository management and diagnostics.

This script provides command-line utilities for managing Scribe configuration
and diagnosing issues with global Scribe deployment.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from scribe_mcp.config.repo_config import RepoDiscovery, RepoConfig, get_current_repo_config, reload_repo_config
from scribe_mcp.plugins.registry import initialize_plugins, get_plugin_registry, get_plugin_security_info
from scribe_mcp.security.sandbox import get_safety_instance, check_permission
from scribe_mcp.tools.rotate_log import verify_rotation_integrity, get_rotation_history
from scribe_mcp.tools.manage_docs import manage_docs_main as manage_docs_entrypoint


def init_repo(repo_path: Optional[Path] = None, force: bool = False) -> None:
    """Initialize Scribe configuration in a repository."""
    if repo_path is None:
        repo_path = Path.cwd()

    try:
        repo_root = RepoDiscovery.find_repo_root(repo_path)
        if not repo_root:
            print(f"❌ Could not find repository root at {repo_path}")
            print("   💡 Initialize a git repository or add a .scribe directory")
            sys.exit(1)

        config = RepoDiscovery.load_config(repo_root)

        # Check if already initialized
        scribe_config = repo_root / ".scribe" / "scribe.yaml"
        if scribe_config.exists() and not force:
            print(f"✅ Scribe is already initialized in {repo_root}")
            print(f"   Config file: {scribe_config}")
            return

        # Ensure configuration exists
        RepoDiscovery.ensure_config(repo_root, config)

        # Create basic directory structure
        docs_dir = config.dev_plans_dir
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Create .scribe directory structure
        scribe_dir = repo_root / ".scribe"
        plugins_dir = scribe_dir / "plugins"
        hooks_dir = scribe_dir / "hooks"
        templates_dir = scribe_dir / "templates"

        for directory in [plugins_dir, hooks_dir, templates_dir]:
            directory.mkdir(exist_ok=True)

        # Create example plugin
        example_plugin = plugins_dir / "example.py"
        if not example_plugin.exists():
            example_plugin.write_text("""# Example Scribe Plugin
from scribe_mcp.plugins.registry import TemplatePlugin, PolicyPlugin

class ExampleTemplatePlugin(TemplatePlugin):
    name = "example-templates"
    version = "1.0.0"
    description = "Example custom templates"

    def initialize(self, config):
        self.config = config

    def get_template(self, template_type):
        if template_type == "custom_architecture":
            return "# Custom Architecture Template\\n\\nThis is a custom template."
        return None

    def list_templates(self):
        return ["custom_architecture"]
""")

        # Create example hook
        example_hook = hooks_dir / "pre_append.py"
        if not example_hook.exists():
            example_hook.write_text("""# Example pre-append hook
def execute(entry_data):
    # Modify entry data before it's appended
    print(f"Hook: About to append entry: {entry_data.get('message', '')}")
    return entry_data
""")

        # Update .gitignore
        gitignore = repo_root / ".gitignore"
        gitignore_lines = []
        if gitignore.exists():
            gitignore_lines = gitignore.read_text().splitlines()

        scribe_ignores = [
            "# Scribe ignores",
            ".scribe/journals/",
            "*.db",
            "*.db-journal",
            ".scribe/cache/",
        ]

        for ignore in scribe_ignores:
            if ignore not in gitignore_lines:
                gitignore_lines.append(ignore)

        gitignore.write_text("\n".join(gitignore_lines) + "\n")

        print(f"✅ Initialized Scribe in {repo_root}")
        print(f"   📁 Config: {scribe_config}")
        print(f"   📁 Docs: {docs_dir}")
        print(f"   🔌 Plugins: {plugins_dir}")
        print(f"   🪝 Hooks: {hooks_dir}")
        print(f"   📋 Templates: {templates_dir}")
        print("   📝 Updated .gitignore")

    except Exception as e:
        print(f"❌ Failed to initialize Scribe: {e}")
        sys.exit(1)


def doctor(repo_path: Optional[Path] = None) -> None:
    """Run diagnostics on Scribe setup and configuration."""
    print("\n🔍 Scribe Doctor - Diagnosing your setup...\n")

    try:
        # Test repository discovery
        print("1. Repository Discovery:")
        repo_root = RepoDiscovery.find_repo_root(repo_path)
        if repo_root:
            print(f"   ✅ Found repository root: {repo_root}")
        else:
            print(f"   ❌ Could not find repository root from {repo_path or Path.cwd()}")
            return

        # Test configuration loading
        print("\n2. Configuration:")
        config = RepoDiscovery.load_config(repo_root)
        print(f"   ✅ Loaded configuration for repo: {config.repo_slug}")
        print(f"   📁 Dev plans directory: {config.dev_plans_dir}")
        print(f"   📄 Progress log name: {config.progress_log_name}")
        print(f"   🔌 Storage backend: {config.storage_backend}")

        # Test directory structure
        print("\n3. Directory Structure:")
        required_dirs = [config.dev_plans_dir]
        if config.plugins_dir:
            required_dirs.append(config.plugins_dir)

        for directory in required_dirs:
            if directory.exists():
                print(f"   ✅ {directory}")
            else:
                print(f"   ⚠️  {directory} (will be created on first use)")

        # Test permissions
        print("\n4. Permissions:")
        safety = get_safety_instance()
        sandbox = safety.get_sandbox(repo_root)
        permission_checker = safety.get_permission_checker(repo_root)

        test_operations = ["read", "append", "rotate", "generate_docs"]
        for operation in test_operations:
            allowed = permission_checker.check_permission(operation)
            status = "✅" if allowed else "❌"
            print(f"   {status} {operation}")

        # Test plugin system
        print("\n5. Plugin System:")
        try:
            initialize_plugins(config)
            registry = get_plugin_registry()
            print(f"   ✅ Plugin registry initialized")
            print(f"   🔌 Loaded {len(registry.plugins)} plugin(s)")

            for plugin_name, plugin in registry.plugins.items():
                print(f"      - {plugin_name} v{plugin.version}: {plugin.description}")

        except Exception as e:
            print(f"   ⚠️  Plugin system: {e}")

        # Test database connectivity (if applicable)
        print("\n6. Storage Backend:")
        try:
            if config.storage_backend == "sqlite":
                db_path = config.db_path or (repo_root / ".scribe" / "scribe.db")
                print(f"   📄 SQLite database: {db_path}")
                if db_path.exists():
                    print(f"   ✅ Database file exists")
                else:
                    print(f"   ℹ️  Database will be created on first use")
            elif config.storage_backend == "postgres":
                print(f"   🐘 PostgreSQL backend configured")
                print(f"   ℹ️  Database connectivity will be tested on server startup")

        except Exception as e:
            print(f"   ⚠️  Storage backend: {e}")

        # Test file system permissions
        print("\n7. File System Permissions:")
        test_file = config.dev_plans_dir / ".scribe_write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            print(f"   ✅ Can write to documentation directory")
        except Exception as e:
            print(f"   ❌ Cannot write to documentation directory: {e}")

        print("\n🎉 Diagnosis complete!")
        print("💡 If you see any warnings or errors, address them before using Scribe.")

    except Exception as e:
        print(f"❌ Doctor failed: {e}")
        sys.exit(1)


def use_repo(repo_path: Path) -> None:
    """Switch to a different repository for Scribe operations."""
    try:
        repo_root = RepoDiscovery.find_repo_root(repo_path)
        if not repo_root:
            print(f"❌ Could not find repository root at {repo_path}")
            sys.exit(1)

        # Reload configuration for the new repository
        global _current_repo_config
        _current_repo_config = None  # Force cache invalidation

        repo_root, config = get_current_repo_config(refresh=True)

        print(f"🎯 Switched to repository: {config.repo_slug}")
        print(f"   📁 Root: {repo_root}")
        print(f"   📁 Docs: {config.dev_plans_dir}")

        # Test if we can access the repository
        try:
            safety = get_safety_instance()
            sandbox = safety.get_sandbox(repo_root)
            print(f"   ✅ Repository is accessible")
        except Exception as e:
            print(f"   ⚠️  Repository access issue: {e}")

    except Exception as e:
        print(f"❌ Failed to switch repository: {e}")
        sys.exit(1)


def verify_logs_rotation(repo_path: Optional[Path] = None, project: Optional[str] = None, limit: int = 5) -> None:
    """Verify rotation integrity for logs."""
    try:
        repo_root, config = get_current_repo_config(refresh=True)

        print(f"🔍 Verifying Log Rotation Integrity")
        print(f"   Repository: {config.repo_slug}")
        print(f"   Root: {repo_root}")

        # Get rotation history
        if project:
            history = get_rotation_history(project_name=project, limit=limit)
        else:
            # Get for current active project
            from scribe_mcp.tools.agent_project_utils import get_active_project
            active_project = get_active_project()
            if active_project:
                history = get_rotation_history(project_name=active_project.get("name"), limit=limit)
            else:
                history = []

        if not history:
            print("   ℹ️  No rotation history found")
            return

        print(f"   Rotation History:")
        for i, rotation in enumerate(history, 1):
            rotation_id = rotation.get("id", "unknown")[:8]
            timestamp = rotation.get("timestamp", "unknown")
            entries_rotated = rotation.get("entries_rotated", 0)
            archive_size = rotation.get("archive_size", 0)

            print(f"   {i}. Rotation {rotation_id}")
            print(f"      Timestamp: {timestamp}")
            print(f"      Entries: {entries_rotated}")
            print(f"      Archive Size: {archive_size} bytes")

            # Verify integrity for this rotation
            if "rotation_id" in rotation:
                try:
                    verification = verify_rotation_integrity(rotation["rotation_id"])
                    if verification.get("valid", False):
                        print(f"      ✅ Integrity: VALID")
                    else:
                        print(f"      ❌ Integrity: INVALID - {verification.get('error', 'Unknown error')}")
                except Exception as e:
                    print(f"      ⚠️  Integrity: ERROR - {e}")

        print(f"   ✅ Rotation verification completed")

    except Exception as e:
        print(f"❌ Failed to verify rotation: {e}")
        import traceback
        traceback.print_exc()


def manage_docs_cli(args) -> None:
    """CLI wrapper for manage_docs functionality."""
    try:
        # Convert argparse namespace to dict and call manage_docs
        import sys
        sys.argv = ["manage-docs", args.action, args.doc]

        # Add command-line arguments
        if args.project:
            sys.argv.extend(["--project", args.project])
        if args.section:
            sys.argv.extend(["--section", args.section])
        if args.content:
            sys.argv.extend(["--content", args.content])
        if args.template:
            sys.argv.extend(["--template", args.template])
        if args.dry_run:
            sys.argv.append("--dry-run")
        if args.metadata:
            for meta in args.metadata:
                sys.argv.extend(["--metadata", meta])

        # Call the manage_docs main function
        manage_docs_entrypoint()

    except Exception as e:
        print(f"❌ Failed to manage docs: {e}")
        import traceback
        traceback.print_exc()


def status(repo_path: Optional[Path] = None) -> None:
    """Show current Scribe status and configuration."""
    try:
        repo_root, config = get_current_repo_config(refresh=True)

        print(f"📊 Scribe Status")
        print(f"   Repository: {config.repo_slug}")
        print(f"   Root: {repo_root}")
        print(f"   Storage: {config.storage_backend}")

        if config.plugins_dir and config.plugins_dir.exists():
            plugin_count = len(list(config.plugins_dir.glob("*.py")))
            print(f"   Plugins: {plugin_count} plugin(s)")

        # Show recent activity if possible
        progress_log = config.get_progress_log_path()
        if progress_log.exists():
            lines = progress_log.read_text().splitlines()
            if lines:
                last_line = lines[-1]
                print(f"   Last entry: {last_line[:100]}{'...' if len(last_line) > 100 else ''}")

    except Exception as e:
        print(f"❌ Failed to get status: {e}")
        sys.exit(1)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Scribe CLI - Repository management and diagnostics",
        prog="scribe-cli"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize Scribe in a repository")
    init_parser.add_argument("--path", type=Path, help="Repository path (default: current directory)")
    init_parser.add_argument("--force", action="store_true", help="Reinitialize even if already configured")

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Run diagnostics")
    doctor_parser.add_argument("--path", type=Path, help="Repository path to check (default: current directory)")

    # use command
    use_parser = subparsers.add_parser("use", help="Switch to a different repository")
    use_parser.add_argument("path", type=Path, help="Repository path to switch to")

    # status command
    status_parser = subparsers.add_parser("status", help="Show current Scribe status")
    status_parser.add_argument("--path", type=Path, help="Repository path (default: current directory)")

    # logs-verify command
    logs_verify_parser = subparsers.add_parser("logs-verify", help="Verify log rotation integrity")
    logs_verify_parser.add_argument("--project", help="Specific project to verify (default: active project)")
    logs_verify_parser.add_argument("--limit", type=int, default=5, help="Number of recent rotations to check (default: 5)")
    logs_verify_parser.add_argument("--path", type=Path, help="Repository path (default: current directory)")

    # manage-docs command
    manage_docs_parser = subparsers.add_parser("manage-docs", help="Manage project documentation")
    manage_docs_parser.add_argument("--project", help="Project name")
    manage_docs_parser.add_argument("--doc", required=True, help="Document to manage")
    manage_docs_parser.add_argument(
        "--action",
        required=True,
        choices=[
            "replace_section",
            "append",
            "status_update",
            "frontmatter_update",
            "quality_check",
            "scaffold_quality_check",
        ],
        help="Action to perform",
    )
    manage_docs_parser.add_argument("--section", help="Section ID for replace_section/status_update actions")
    manage_docs_parser.add_argument("--content", help="Content for actions")
    manage_docs_parser.add_argument("--template", help="Template to use")
    manage_docs_parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    manage_docs_parser.add_argument("--metadata", action="append", help="Metadata key=value pairs (can be used multiple times)")
    manage_docs_parser.add_argument("--path", type=Path, help="Repository path (default: current directory)")

    args = parser.parse_args()

    if args.command == "init":
        init_repo(args.path, args.force)
    elif args.command == "doctor":
        doctor(args.path)
    elif args.command == "use":
        use_repo(args.path)
    elif args.command == "status":
        status(args.path)
    elif args.command == "logs-verify":
        verify_logs_rotation(args.path, args.project, args.limit)
    elif args.command == "manage-docs":
        manage_docs_cli(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
