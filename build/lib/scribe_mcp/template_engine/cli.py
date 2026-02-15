#!/usr/bin/env python3
"""Template preview and testing CLI for Scribe MCP."""

import argparse
import json
import sys
from pathlib import Path

# Import directly to avoid circular imports issues
from scribe_mcp.template_engine.engine import Jinja2TemplateEngine, TemplateEngineError


def main():
    """CLI entry point for template testing."""
    parser = argparse.ArgumentParser(
        description="Test and preview Scribe MCP templates"
    )
    parser.add_argument(
        "--template", "-t",
        required=True,
        help="Template name to render"
    )
    parser.add_argument(
        "--project", "-p",
        default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--project-name", "-n",
        help="Project name (default: derived from directory)"
    )
    parser.add_argument(
        "--meta", "-m",
        help="Metadata as JSON string"
    )
    parser.add_argument(
        "--meta-file",
        help="Metadata from JSON file"
    )
    parser.add_argument(
        "--security", "-s",
        choices=["sandbox", "immutable", "unrestricted", "none"],
        default="sandbox",
        help="Security mode (default: sandbox)"
    )
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Disable legacy fallback rendering"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate template syntax, don't render"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable fail-hard mode (no legacy fallback on render errors)"
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available templates and exit"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Load metadata
    metadata = {}
    if args.meta:
        try:
            metadata = json.loads(args.meta)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --meta: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.meta_file:
        try:
            with open(args.meta_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Error: Cannot read metadata file {args.meta_file}: {e}", file=sys.stderr)
            sys.exit(1)

    # Initialize template engine
    try:
        project_root = Path(args.project).resolve()
        project_name = args.project_name or project_root.name

        engine = Jinja2TemplateEngine(
            project_root=project_root,
            project_name=project_name,
            security_mode=args.security
        )

        if args.verbose:
            print(f"Project root: {project_root}")
            print(f"Project name: {project_name}")
            print(f"Security mode: {args.security}")
            print(f"Template directories: {len(engine.template_dirs)}")
            for i, template_dir in enumerate(engine.template_dirs, 1):
                dir_type = getattr(engine, "_template_dir_types", {}).get(template_dir, "unknown")
                print(f"  {i}. {template_dir} [{dir_type}]")

    except Exception as e:
        print(f"Error: Failed to initialize template engine: {e}", file=sys.stderr)
        sys.exit(1)

    # List templates if requested
    if args.list_templates:
        templates = engine.list_templates()
        if templates:
            print("Available templates:")
            for template in sorted(templates):
                info = engine.get_template_info(template)
                print(f"  {template} ({info['template_type']}, {info['size_bytes']} bytes)")
        else:
            print("No templates found.")
        return

    # Validate or render template
    try:
        if args.validate_only:
            # Validate template only
            validation = engine.validate_template(args.template)
            if validation["valid"]:
                print(f"✅ Template '{args.template}' is valid")
                if args.verbose:
                    print(f"  Lines: {validation['line_count']}")
                    print(f"  Size: {validation['size_bytes']} bytes")
            else:
                print(f"❌ Template '{args.template}' validation failed:")
                for error in validation["errors"]:
                    print(f"  - {error}")
                sys.exit(1)
        else:
            # Render template (with optional strict/fail-hard mode)
            result = engine.render_template(
                template_name=args.template,
                metadata=metadata,
                strict=args.strict,
                fallback=not args.no_fallback
            )
            print(result)

    except TemplateEngineError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
