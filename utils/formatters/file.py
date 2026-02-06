"""File content formatting for read_file tool responses.

Phase 5 Task 5.3: Extracted from ResponseFormatter.format_readable_file_content.
Handles formatting of file content, structure analysis, dependencies, and metadata.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import BaseFormatter
from .ui import UIFormatter


class FileFormatter(BaseFormatter):
    """Formats file content, structure, and search results.

    Extracted from ResponseFormatter.format_readable_file_content.
    Handles multiple modes: scan_only, chunk, page, line_range, full, full_stream, search.
    """

    def __init__(self, token_warning_threshold: int = 4000):
        """Initialize FileFormatter.

        Args:
            token_warning_threshold: Token count that triggers warnings
        """
        super().__init__(token_warning_threshold)
        self._ui = UIFormatter(token_warning_threshold=token_warning_threshold)

    def format_readable_file_content(self, data: Dict[str, Any]) -> str:
        """
        Format read_file output in readable format with simple header, content first, metadata at bottom.

        Args:
            data: read_file response with 'scan', 'chunks', 'chunk', etc.

        Returns:
            Formatted string with one-line header, line-numbered content, metadata footer
        """
        # Extract scan metadata
        scan = data.get('scan', {})
        path = scan.get('repo_relative_path') or scan.get('absolute_path', 'unknown')
        mode = data.get('mode', 'unknown')

        # Get filename from path
        filename = os.path.basename(path)

        # Extract content based on mode and determine line range
        content = ''
        start_line = 1
        end_line = 1
        total_lines = scan.get('line_count', 0)

        if mode == 'scan_only':
            # No content for scan_only
            content = '[scan only - no content requested]'
            line_range = 'scan only'
        elif 'chunks' in data and data['chunks']:
            # Chunk mode - concatenate chunks
            chunks = data['chunks']
            content_parts = []
            for chunk in chunks:
                content_parts.append(chunk.get('content', ''))
            content = '\n'.join(content_parts)
            start_line = chunks[0].get('line_start', 1) if chunks else 1
            end_line = chunks[-1].get('line_end', start_line) if chunks else start_line
            line_range = f"{start_line}-{end_line}"
        elif 'chunk' in data:
            # Line range or page mode
            chunk = data['chunk']
            content = chunk.get('content', '')
            start_line = chunk.get('line_start', 1)
            end_line = chunk.get('line_end', start_line)
            line_range = f"{start_line}-{end_line}"
        elif 'matches' in data:
            # Search mode
            matches = data['matches']
            if matches:
                content_parts = []
                for match in matches[:10]:  # Limit to first 10 matches
                    line_num = match.get('line_number', '?')
                    line_text = match.get('line', '').rstrip()
                    content_parts.append(f"[Line {line_num}] {line_text}")
                content = '\n'.join(content_parts)
                line_range = f"{len(matches)} matches"
            else:
                content = '[no matches found]'
                line_range = '0 matches'
        else:
            line_range = 'unknown'

        # Build readable output with simple one-line header
        parts = []

        # ONE-LINE HEADER: "READ FILE filename.xyz | Lines read: 100-243"
        parts.append(f"READ FILE {filename} | Lines read: {line_range}")
        parts.append("")  # Blank line

        # CONTENT FIRST (with line numbers)
        if mode != 'scan_only' and content != '[no matches found]':
            parts.append(self._ui.add_line_numbers(content, start_line))
        else:
            parts.append(content)

        # SPECIAL FILE WARNING (SKILL.md detection) - STERN, NOT SEIZURE
        special_file = data.get('special_file')
        if special_file:
            parts.append("")
            parts.append("─" * 63)
            parts.append(f"🚨 {special_file.get('reason', 'SPECIAL FILE DETECTED')}")
            parts.append("─" * 63)
            parts.append(f"Urgency: {special_file.get('urgency', 'HIGH')}")
            parts.append(f"Type: {special_file.get('type', 'unknown')}")
            parts.append(f"Action Required: {special_file.get('instruction', 'Read file immediately')}")
            if special_file.get('suggested_action'):
                parts.append(f"→ {special_file.get('suggested_action')}")
            parts.append("─" * 63)

        # STRUCTURE ANALYSIS (Python AST, Markdown headings, JS/TS functions)
        structure = data.get('structure')
        if structure and structure.get('ok'):
            parts.append("")
            parts.append("📋 File Structure:")
            parts.append("")

            file_type = structure.get('type', 'unknown')

            if file_type == 'python':
                # Python functions and classes
                functions = structure.get('functions', [])
                classes = structure.get('classes', [])
                total_funcs = structure.get('total_functions', len(functions))
                total_classes = structure.get('total_classes', len(classes))

                # Get pagination params
                pagination = data.get('structure_pagination', {})
                page = pagination.get('page', 1)
                page_size = pagination.get('page_size', 10)

                # Check if filtering is active
                is_filtered = structure.get('filtered', False)
                filter_pattern = structure.get('filter_pattern')
                filtered_func_count = structure.get('filtered_function_count', 0)
                filtered_class_count = structure.get('filtered_class_count', 0)

                if is_filtered:
                    total_matches = filtered_func_count + filtered_class_count
                    parts.append(f"  🔍 Filtered Results ({total_matches} matches for '{filter_pattern}'):")
                    if filtered_class_count > 0:
                        parts.append(f"     Classes: {filtered_class_count}")
                    if filtered_func_count > 0:
                        parts.append(f"     Functions: {filtered_func_count}")
                    parts.append("")

                # Helper function to format a signature
                def format_signature(params_list, return_type=None):
                    """Format function/method signature with types and defaults."""
                    if not params_list:
                        sig = "()"
                    else:
                        param_strs = []
                        for p in params_list:
                            param_str = p['name']
                            if 'type' in p and p['type']:
                                param_str += f": {p['type']}"
                            if 'default' in p and p['default']:
                                param_str += f" = {p['default']}"
                            param_strs.append(param_str)
                        sig = f"({', '.join(param_strs)})"

                    if return_type:
                        sig += f" -> {return_type}"
                    return sig

                if classes:
                    # Paginate classes list ONLY if not filtered (when filtered, show all matched classes but paginate their methods)
                    if is_filtered:
                        paginated_classes = classes
                        class_total_pages = 1
                    else:
                        class_start = (page - 1) * page_size
                        class_end = class_start + page_size
                        paginated_classes = classes[class_start:class_end]
                        class_total_pages = (total_classes + page_size - 1) // page_size

                    if total_classes > page_size and not is_filtered:
                        parts.append(f"  Classes (page {page} of {class_total_pages}, showing {class_start + 1}-{min(class_end, total_classes)} of {total_classes}):")
                    else:
                        parts.append(f"  Classes ({total_classes} total):")

                    for cls in paginated_classes:
                        # Format class header with line range
                        cls_start_line = cls['line']
                        cls_end_line = cls.get('end_line', cls_start_line)
                        line_count = cls_end_line - cls_start_line + 1
                        line_info = f"lines {cls_start_line}-{cls_end_line} ({line_count} lines)" if cls_end_line > cls_start_line else f"line {cls_start_line}"
                        parts.append(f"    • class {cls['name']} at {line_info}")

                        # Show methods if available (with pagination)
                        methods = cls.get('methods', [])
                        method_count = cls.get('method_count', len(methods))
                        if methods:
                            # Paginate methods
                            start_idx = (page - 1) * page_size
                            end_idx = start_idx + page_size
                            paginated_methods = methods[start_idx:end_idx]
                            total_pages = (method_count + page_size - 1) // page_size

                            # Show pagination header if multiple pages
                            if method_count > page_size:
                                parts.append(f"        Methods (page {page} of {total_pages}, showing {start_idx + 1}-{min(end_idx, method_count)} of {method_count}):")
                            else:
                                parts.append(f"        Methods ({method_count} total):")

                            for method in paginated_methods:
                                async_prefix = "async " if method.get('is_async') else ""
                                method_params = method.get('params', [])
                                method_return = method.get('return_type')
                                sig = format_signature(method_params, method_return)

                                # Format method line range
                                m_start = method['line']
                                m_end = method.get('end_line', m_start)
                                m_count = m_end - m_start + 1
                                m_line_info = f"{m_start}-{m_end} ({m_count})" if m_end > m_start else str(m_start)

                                parts.append(f"          {async_prefix}def {method['name']}{sig} (lines {m_line_info})")

                            # Navigation hint for next/previous pages
                            if total_pages > 1:
                                nav_hints = []
                                if page > 1:
                                    nav_hints.append(f"structure_page={page - 1} for previous")
                                if page < total_pages:
                                    nav_hints.append(f"structure_page={page + 1} for next")
                                if nav_hints:
                                    parts.append(f"        💡 Use {' or '.join(nav_hints)}")
                        parts.append("")

                    # Add pagination navigation for classes
                    if class_total_pages > 1 and not is_filtered:
                        nav_hints = []
                        if page > 1:
                            nav_hints.append(f"structure_page={page - 1}")
                        if page < class_total_pages:
                            nav_hints.append(f"structure_page={page + 1}")
                        if nav_hints:
                            parts.append(f"    💡 Use {' or '.join(nav_hints)} to navigate")
                        parts.append("")

                if functions:
                    # Paginate functions list ONLY if not filtered (when filtered, show all matched functions)
                    if is_filtered:
                        paginated_funcs = functions
                        func_total_pages = 1
                    else:
                        func_start = (page - 1) * page_size
                        func_end = func_start + page_size
                        paginated_funcs = functions[func_start:func_end]
                        func_total_pages = (total_funcs + page_size - 1) // page_size

                    if total_funcs > page_size and not is_filtered:
                        parts.append(f"  Functions (page {page} of {func_total_pages}, showing {func_start + 1}-{min(func_end, total_funcs)} of {total_funcs}):")
                    else:
                        parts.append(f"  Functions ({total_funcs} total):")

                    for func in paginated_funcs:
                        func_params = func.get('params', [])
                        func_return = func.get('return_type')

                        # Fallback to old args format if params not available
                        if not func_params and func.get('args'):
                            sig = f"({', '.join(func['args'])})"
                        else:
                            sig = format_signature(func_params, func_return)

                        # Format function line range
                        f_start = func['line']
                        f_end = func.get('end_line', f_start)
                        f_count = f_end - f_start + 1
                        f_line_info = f"lines {f_start}-{f_end} ({f_count})" if f_end > f_start else f"line {f_start}"

                        async_prefix = "async " if func.get('type') == 'async_function' else ""
                        parts.append(f"    • {async_prefix}def {func['name']}{sig} at {f_line_info}")

                    # Add pagination navigation for functions
                    if func_total_pages > 1 and not is_filtered:
                        nav_hints = []
                        if page > 1:
                            nav_hints.append(f"structure_page={page - 1}")
                        if page < func_total_pages:
                            nav_hints.append(f"structure_page={page + 1}")
                        if nav_hints:
                            parts.append(f"    💡 Use {' or '.join(nav_hints)} to navigate")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

            elif file_type == 'markdown':
                # Markdown headings
                headings = structure.get('headings', [])
                total_headings = structure.get('total_headings', len(headings))

                parts.append(f"  Headings ({total_headings} total):")
                for heading in headings[:20]:  # Show first 20
                    indent = "  " * heading['level']
                    parts.append(f"    {indent}{'#' * heading['level']} {heading['text']} (line {heading['line']})")
                if total_headings > 20:
                    parts.append(f"    ... and {total_headings - 20} more headings")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

            elif file_type in {'javascript', 'typescript'}:
                # JavaScript/TypeScript functions and classes
                functions = structure.get('functions', [])
                classes = structure.get('classes', [])
                total_funcs = structure.get('total_functions', len(functions))
                total_classes = structure.get('total_classes', len(classes))

                if classes:
                    parts.append(f"  Classes ({total_classes} total):")
                    for cls in classes[:10]:
                        parts.append(f"    • {cls['name']} at line {cls['line']}")
                    if total_classes > 10:
                        parts.append(f"    ... and {total_classes - 10} more classes")
                    parts.append("")

                if functions:
                    parts.append(f"  Functions ({total_funcs} total):")
                    for func in functions[:10]:
                        parts.append(f"    • {func['name']}() at line {func['line']}")
                    if total_funcs > 10:
                        parts.append(f"    ... and {total_funcs - 10} more functions")

                if structure.get('truncated'):
                    parts.append("")
                    parts.append("  ⚠️  Structure truncated - use line_range/page mode for full details")

        # DEPENDENCIES ANALYSIS (Phase 1+2: Import extraction + resolution)
        dependencies = data.get('dependencies')
        if dependencies and not dependencies.get('error'):
            imports = dependencies.get('imports', [])
            total_imports = dependencies.get('total_imports', 0)
            truncated = dependencies.get('truncated', False)

            if imports:
                parts.append("")
                parts.append("📦 Dependencies:")
                parts.append("")

                # Phase 2: Group imports by type for better readability
                # Check if we have Phase 2 resolution data (import_type field exists)
                has_resolution = any(imp.get('import_type') is not None for imp in imports)

                if has_resolution:
                    # Group imports by type
                    grouped = defaultdict(list)
                    for imp in imports:
                        import_type = imp.get('import_type', 'unresolved')
                        grouped[import_type].append(imp)

                    # Display in order: stdlib, third_party, local, unresolved
                    display_limit_per_type = 10
                    type_order = ['stdlib', 'third_party', 'local', 'unresolved']
                    type_labels = {
                        'stdlib': '📚 Standard Library',
                        'third_party': '📦 Third-Party Packages',
                        'local': '📁 Local Modules',
                        'unresolved': '❓ Unresolved'
                    }

                    for import_type in type_order:
                        type_imports = grouped.get(import_type, [])
                        if not type_imports:
                            continue

                        parts.append(f"  {type_labels[import_type]} ({len(type_imports)}):")
                        parts.append("")

                        for imp in type_imports[:display_limit_per_type]:
                            imp_syntax = imp.get('type')  # 'import' or 'from_import'
                            module = imp.get('module', '')
                            line = imp.get('line', '?')
                            names = imp.get('names')
                            alias = imp.get('alias')
                            level = imp.get('level', 0)
                            resolved_path = imp.get('resolved_path')
                            exists = imp.get('exists')

                            # Format relative imports with dots
                            if level > 0:
                                dots = '.' * level
                                if module:
                                    module_display = f"{dots}{module}"
                                else:
                                    module_display = dots
                            else:
                                module_display = module

                            # Build base import statement
                            if imp_syntax == 'import':
                                if alias:
                                    import_stmt = f"import {module_display} as {alias}"
                                else:
                                    import_stmt = f"import {module_display}"
                            elif imp_syntax == 'from_import' and names:
                                names_str = ', '.join(names[:5])  # Show first 5 names
                                if len(names) > 5:
                                    names_str += f", ... ({len(names)} total)"
                                import_stmt = f"from {module_display} import {names_str}"
                            else:
                                import_stmt = f"import {module_display}"

                            # Add resolution info based on type
                            if import_type == 'stdlib':
                                parts.append(f"    → {import_stmt} (line {line}) [stdlib]")
                            elif import_type == 'third_party':
                                parts.append(f"    → {import_stmt} (line {line}) [third-party]")
                            elif import_type == 'local':
                                if resolved_path and exists:
                                    # Show resolved path (make it relative to workspace for readability)
                                    parts.append(f"    → {import_stmt} (line {line})")
                                    parts.append(f"       ✓ {resolved_path}")
                                elif resolved_path and exists is False:
                                    # Missing local import
                                    parts.append(f"    → {import_stmt} (line {line})")
                                    parts.append(f"       ✗ MISSING: {resolved_path}")
                                else:
                                    # Local but couldn't resolve path
                                    parts.append(f"    → {import_stmt} (line {line}) [local - path unresolved]")
                            else:  # unresolved
                                parts.append(f"    → {import_stmt} (line {line}) [unresolved]")

                        if len(type_imports) > display_limit_per_type:
                            parts.append(f"       ... and {len(type_imports) - display_limit_per_type} more {import_type} imports")
                        parts.append("")  # Blank line between groups

                else:
                    # Phase 1 fallback: No resolution data, show simple list
                    display_limit = 20
                    for imp in imports[:display_limit]:
                        imp_type = imp.get('type')
                        module = imp.get('module', '')
                        line = imp.get('line', '?')
                        names = imp.get('names')
                        alias = imp.get('alias')
                        level = imp.get('level', 0)

                        # Format relative imports with dots
                        if level > 0:
                            dots = '.' * level
                            if module:
                                module_display = f"{dots}{module}"
                            else:
                                module_display = dots
                        else:
                            module_display = module

                        # Format display based on import type
                        if imp_type == 'import':
                            if alias:
                                parts.append(f"    → import {module_display} as {alias} (line {line})")
                            else:
                                parts.append(f"    → import {module_display} (line {line})")
                        elif imp_type == 'from_import' and names:
                            names_str = ', '.join(names[:5])  # Show first 5 names
                            if len(names) > 5:
                                names_str += f", ... ({len(names)} total)"
                            parts.append(f"    → from {module_display} import {names_str} (line {line})")

                    # Show truncation message if needed
                    if total_imports > display_limit:
                        parts.append("")
                        parts.append(f"    ... and {total_imports - display_limit} more imports")

                if truncated:
                    parts.append("  ⚠️  Import list truncated at 100 - file may have more imports")

        elif dependencies and dependencies.get('error'):
            # Show error but don't spam output
            parts.append("")
            parts.append(f"📦 Dependencies: Unable to parse imports ({dependencies.get('error', 'unknown error')})")

        # STATIC ANALYSIS DISCLAIMER (Phase 4: Honest framing of limitations)
        # Show disclaimer when dependencies or impact radius are displayed
        if (dependencies and not dependencies.get('error')) or (data.get('impact_radius') and not data.get('impact_radius', {}).get('error')):
            parts.append("")
            parts.append("ℹ️  Note: Dependencies shown reflect static import analysis only. Runtime dependencies, dynamic imports, and reflection patterns are not detected.")

        # IMPACT RADIUS ANALYSIS (Phase 3: Reverse lookup / cross-file graphing)
        impact_radius = data.get('impact_radius')
        if impact_radius and not impact_radius.get('error'):
            count = impact_radius.get('count', 0)
            level = impact_radius.get('level', 'low')
            importers = impact_radius.get('importers', [])
            truncated = impact_radius.get('truncated', False)
            perf_warning = impact_radius.get('performance_warning')

            # Only show impact section if file is actually imported somewhere
            if count > 0:
                parts.append("")

                # Impact level display with appropriate emoji
                if level == 'high':
                    parts.append(f"🚨 Impact Radius: This file is imported by {count} files [HIGH IMPACT]")
                elif level == 'medium':
                    parts.append(f"⚠️  Impact Radius: This file is imported by {count} files [MEDIUM IMPACT]")
                else:
                    parts.append(f"Impact Radius: This file is imported by {count} files")

                parts.append("")

                # Show importer list
                if importers:
                    parts.append("  Files that import this:")
                    for importer in importers:
                        parts.append(f"    • {importer}")

                    # Truncation message
                    if truncated:
                        remaining = count - len(importers)
                        parts.append(f"    ... and {remaining} more files")

                # Performance warning if scan was slow
                if perf_warning:
                    parts.append("")
                    parts.append(f"  ⚠️  {perf_warning}")

        elif impact_radius and impact_radius.get('error'):
            # Show error but don't spam output
            parts.append("")
            parts.append(f"Impact Radius: Unable to calculate ({impact_radius.get('error', 'unknown error')})")

        # BOUNDARY VIOLATIONS (Phase 4: Forbidden import pattern detection)
        boundary_violations = data.get('boundary_violations')
        if boundary_violations and boundary_violations.get('enabled'):
            violations = boundary_violations.get('violations', [])
            if violations:
                # Count violations by severity
                errors = [v for v in violations if v.get('severity') == 'error']
                warnings = [v for v in violations if v.get('severity') == 'warning']
                infos = [v for v in violations if v.get('severity') == 'info']

                # Build summary
                parts.append("")
                summary_parts = []
                if errors:
                    summary_parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
                if warnings:
                    summary_parts.append(f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}")
                if infos:
                    summary_parts.append(f"{len(infos)} info")

                parts.append(f"🚫 Boundary Violations: {', '.join(summary_parts)}")
                parts.append("")

                # Sort violations by severity (errors first, then warnings, then info)
                severity_order = {'error': 0, 'warning': 1, 'info': 2}
                sorted_violations = sorted(violations, key=lambda v: severity_order.get(v.get('severity', 'info'), 3))

                # Display each violation
                for violation in sorted_violations:
                    severity = violation.get('severity', 'info').upper()
                    rule_name = violation.get('rule_name', 'Unknown Rule')
                    violated_import = violation.get('violated_import', '?')
                    message = violation.get('message', '')
                    line = violation.get('line', 0)

                    # Severity tag with visual distinction
                    parts.append(f"  [{severity}] {rule_name}")
                    parts.append(f"    → {violated_import} (line {line})")
                    if message:
                        parts.append(f"    {message}")
                    parts.append("")  # Blank line between violations

        # LARGE FILE WARNING (mode='full' auto-pagination)
        large_file_warning = data.get('large_file_warning')
        if large_file_warning:
            parts.append("")
            parts.append("⚠️  " + "─" * 59)
            parts.append(f"  {large_file_warning.get('message', 'Large file detected')}")
            parts.append("")
            parts.append(f"  💡 {large_file_warning.get('recommendation', 'Use pagination to read more')}")
            examples = large_file_warning.get('examples', [])
            if examples:
                parts.append("")
                parts.append("  Examples:")
                for example in examples[:3]:
                    parts.append(f"    • {example}")
            parts.append("⚠️  " + "─" * 59)

        # METADATA AT BOTTOM
        parts.append("")  # Blank line before metadata
        parts.append("─" * 63)  # Separator line

        # Build metadata lines
        metadata_lines = []
        metadata_lines.append(f"Path: {path}")
        metadata_lines.append(f"Size: {scan.get('byte_size', 0)} bytes | Total lines: {total_lines} | Encoding: {scan.get('encoding', 'utf-8')}")

        # Add mode-specific metadata
        if 'chunks' in data and len(data['chunks']) > 1:
            metadata_lines.append(f"Chunks: {len(data['chunks'])} of {scan.get('estimated_chunk_count', '?')}")
        if data.get('page_number'):
            page_info = f"Page: {data['page_number']} (size: {data.get('page_size', '?')})"
            if data.get('total_pages'):
                page_info += f" of {data['total_pages']} total"
            if data.get('auto_paginated'):
                page_info += " [auto-paginated]"
            metadata_lines.append(page_info)
        if 'max_matches' in data:
            metadata_lines.append(f"Matches: {len(data.get('matches', []))} of {data.get('max_matches', '?')} max")
        # Token count for full mode
        if data.get('token_count'):
            metadata_lines.append(f"Tokens: {data['token_count']:,}")
        if data.get('tokens_shown'):
            metadata_lines.append(f"Tokens shown: {data['tokens_shown']:,} of {data.get('token_limit', '?'):,} limit")
        if data.get('auto_truncated'):
            metadata_lines.append(f"Lines shown: {data.get('lines_shown', '?'):,} of {data.get('total_lines', '?'):,} [auto-truncated]")
        # Full content bypass warning (web dashboard mode)
        if data.get('full_content_warning'):
            warning = data['full_content_warning']
            metadata_lines.append(f"⚠️ Full content mode: {warning.get('message', 'Large file returned untruncated')}")

        # Add SHA256 (truncated)
        if scan.get('sha256'):
            metadata_lines.append(f"SHA256: {scan['sha256'][:16]}...")

        parts.extend(metadata_lines)

        # Add navigation hints if present (scan_only mode)
        nav_hints = data.get('navigation_hints')
        if nav_hints and mode == 'scan_only':
            parts.append("")
            parts.append("💡 Navigation Hints:")
            parts.append(f"   Chunks available: {nav_hints.get('total_chunks', 0)}")
            parts.append(f"   Suggested chunk size: {nav_hints.get('suggested_chunk_size', 1)}")
            examples = nav_hints.get('examples', {})
            if examples:
                parts.append("   Quick examples:")
                for mode_name, example in list(examples.items())[:3]:
                    parts.append(f"     • {example}")

        # Add advanced analysis hint if present (scan_only mode without dependencies)
        adv_hint = data.get('advanced_analysis_hint')
        if adv_hint and mode == 'scan_only':
            parts.append("")
            parts.append("🔬 Advanced Analysis:")
            parts.append(f"   {adv_hint.get('message', '')}")
            if adv_hint.get('example'):
                parts.append(f"   Example: {adv_hint['example']}")

        # Add usage hint if present (mode='full' token warnings)
        usage_hint = data.get('usage_hint')
        if usage_hint:
            parts.append("")
            parts.append("💡 Usage Hint:")
            parts.append(f"   {usage_hint.get('message', '')}")
            if usage_hint.get('tip'):
                parts.append(f"   Tip: {usage_hint['tip']}")
            if usage_hint.get('alternatives'):
                for alt in usage_hint['alternatives']:
                    parts.append(f"   • {alt}")

        # Add reminders if present
        reminders = data.get('reminders', [])
        if reminders:
            parts.append("")
            parts.append("⏰ Reminders:")
            for reminder in reminders:
                parts.append(f"   • {reminder.get('message', '')}")

        return '\n'.join(parts)

    def _get_doc_line_count(self, file_path: Union[str, Path]) -> int:
        """
        Get line count for a file using efficient method.

        Uses stat-based approach when possible, falls back to line counting.

        Args:
            file_path: Absolute or relative path to file

        Returns:
            Number of lines in file, or 0 if file doesn't exist
        """
        try:
            # Convert to Path object
            path = Path(file_path)

            # Check if file exists
            if not path.exists() or not path.is_file():
                return 0

            # Efficient line counting
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except (OSError, PermissionError):
            # Return 0 on any file access errors
            return 0

    def _detect_custom_content(self, docs_dir: Union[str, Path]) -> Dict[str, Any]:
        """
        Detect custom documents in project dev plan directory.

        Scans for:
        - research/ directory and file count
        - bugs/ directory (if present in dev plan)
        - .jsonl files (TOOL_LOG.jsonl, etc.)

        Args:
            docs_dir: Path to project dev plan directory
                      (e.g., .scribe/docs/dev_plans/project_name/)

        Returns:
            Dictionary with custom content info:
            {
                "research_files": 3,
                "bugs_present": False,
                "jsonl_files": ["TOOL_LOG.jsonl"]
            }
        """
        # Initialize result
        result = {
            "research_files": 0,
            "bugs_present": False,
            "jsonl_files": []
        }

        try:
            # Convert to Path object
            path = Path(docs_dir)

            # Check if directory exists
            if not path.exists() or not path.is_dir():
                return result

            # Scan for research directory
            research_dir = path / "research"
            if research_dir.exists() and research_dir.is_dir():
                result["research_files"] = len(list(research_dir.glob("*.md")))

            # Check for bugs directory (note: bugs are usually at .scribe/docs/bugs/, not in dev plan)
            bugs_dir = path / "bugs"
            result["bugs_present"] = bugs_dir.exists() and bugs_dir.is_dir()

            # Find .jsonl files in dev plan root
            result["jsonl_files"] = [f.name for f in path.glob("*.jsonl")]

            return result
        except (OSError, PermissionError):
            # Return empty result on directory access errors
            return result
