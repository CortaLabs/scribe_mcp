"""CLI helpers for manage_docs."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Awaitable, Callable


def run_manage_docs_cli(
    manage_docs_callable: Callable[..., Awaitable[dict[str, Any]]],
) -> int:
    """Parse CLI args and invoke manage_docs."""

    async def _run_manage_docs(args: argparse.Namespace) -> int:
        try:
            result = await manage_docs_callable(
                action=args.action,
                project=args.project,
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

                if "verification_passed" in result:
                    if result["verification_passed"]:
                        print("✅ File write verification passed")
                    else:
                        print("❌ File write verification failed")

                return 0

            print(f"❌ Error: {result.get('error', 'Unknown error')}")
            return 1
        except Exception as exc:
            print(f"❌ Unexpected error: {exc}")
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
        """,
    )

    parser.add_argument(
        "action",
        choices=[
            "replace_section",
            "append",
            "status_update",
            "frontmatter_update",
            "quality_check",
            "scaffold_quality_check",
            "apply_patch",
            "replace_range",
            "list_sections",
            "list_checklist_items",
            "preview_reconciliation",
            "batch",
            "create_research_doc",
            "create_bug_report",
            "create_review_report",
            "create_agent_report_card",
        ],
        help="Action to perform on the document",
    )

    parser.add_argument(
        "doc",
        help="Document to modify",
    )

    parser.add_argument(
        "--project",
        help="Project name to target",
    )

    parser.add_argument(
        "--section",
        help="Section ID (required for replace_section and status_update)",
    )

    parser.add_argument(
        "--content",
        help="Content to add/replace",
    )

    parser.add_argument(
        "--patch",
        help="Unified diff patch to apply",
    )

    parser.add_argument(
        "--patch-source-hash",
        help="SHA256 hash of the file content used to generate the patch",
    )

    parser.add_argument(
        "--edit",
        help="Structured edit payload as JSON string",
    )

    parser.add_argument(
        "--patch-mode",
        help="Patch mode for apply_patch (structured or unified)",
    )

    parser.add_argument(
        "--start-line",
        type=int,
        help="Start line (1-based) for replace_range",
    )

    parser.add_argument(
        "--end-line",
        type=int,
        help="End line (1-based) for replace_range",
    )

    parser.add_argument(
        "--template",
        help="Template fragment to use (from templates/fragments/)",
    )

    parser.add_argument(
        "--metadata",
        type=str,
        help='Metadata as JSON string (e.g., \'{"status": "done", "proof": "commit_123"}\')',
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them",
    )

    args = parser.parse_args()

    if args.action in ["replace_section", "status_update"] and not args.section:
        print("❌ Error: --section is required for replace_section and status_update actions")
        return 1

    if args.action == "apply_patch" and not (args.patch or args.content):
        if not args.edit:
            print("❌ Error: --edit is required for apply_patch structured mode")
            return 1

    if args.action == "apply_patch" and args.patch_mode and args.patch_mode not in {"structured", "unified"}:
        print("❌ Error: --patch-mode must be 'structured' or 'unified'")
        return 1

    if args.action == "replace_range" and (args.start_line is None or args.end_line is None):
        print("❌ Error: --start-line and --end-line are required for replace_range")
        return 1

    if (
        args.action
        not in [
            "apply_patch",
            "replace_range",
            "create_doc",
            "validate_crosslinks",
            "normalize_headers",
            "generate_toc",
            "preview_reconciliation",
            "frontmatter_update",
            "quality_check",
            "scaffold_quality_check",
            "list_sections",
            "list_checklist_items",
            "batch",
            "create_research_doc",
            "create_bug_report",
            "create_review_report",
            "create_agent_report_card",
        ]
        and not args.content
        and not args.template
    ):
        print("❌ Error: Either --content or --template must be provided")
        return 1

    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in metadata: {args.metadata}")
            return 1

    edit = None
    if args.edit:
        try:
            edit = json.loads(args.edit)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON in edit payload: {args.edit}")
            return 1

    args.edit = edit
    args.metadata = metadata
    return asyncio.run(_run_manage_docs(args))
