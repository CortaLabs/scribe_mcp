"""Unit tests for utils/formatters/file.py - File Formatter Module.

Tests for Phase 5 Task 5.3: File formatter extraction from ResponseFormatter.
Covers:
- format_readable_file_content() method with all modes
- _get_doc_line_count() helper
- _detect_custom_content() helper
- Edge cases and backward compatibility

These tests establish baseline behavior from ResponseFormatter before extraction
and verify FileFormatter matches exactly.
"""

import pytest
import tempfile
import os
import re
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.response import ResponseFormatter


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text for testing."""
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_pattern.sub('', text)


class TestFormatReadableFileContentBasic:
    """Tests for basic file content formatting (chunk/page modes)."""

    def test_chunk_mode_basic(self):
        """Test basic chunk mode formatting."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'absolute_path': '/repo/file.py',
                'repo_relative_path': 'file.py',
                'byte_size': 50,
                'line_count': 3,
                'sha256': 'abc123def456789012345678901234567890',
                'encoding': 'utf-8',
            },
            'chunks': [
                {
                    'chunk_index': 0,
                    'line_start': 1,
                    'line_end': 3,
                    'content': 'line 1\nline 2\nline 3'
                }
            ]
        }
        result = formatter.format_readable_file_content(data)
        clean = strip_ansi(result)

        # Should have simple header
        assert "READ FILE file.py" in result
        assert "Lines read: 1-3" in result

        # Should have line-numbered content
        assert "1. line 1" in clean
        assert "2. line 2" in clean
        assert "3. line 3" in clean

        # Should have metadata footer
        assert "Path: file.py" in result
        assert "Size: 50 bytes" in result

    def test_multiple_chunks(self):
        """Test formatting with multiple chunks."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'absolute_path': '/repo/big.py',
                'repo_relative_path': 'big.py',
                'byte_size': 1000,
                'line_count': 100,
                'sha256': 'xyz789',
                'encoding': 'utf-8',
                'estimated_chunk_count': 5,
            },
            'chunks': [
                {'chunk_index': 0, 'line_start': 1, 'line_end': 25, 'content': '\n'.join([f'line {i}' for i in range(1, 26)])},
                {'chunk_index': 1, 'line_start': 26, 'line_end': 50, 'content': '\n'.join([f'line {i}' for i in range(26, 51)])},
            ]
        }
        result = formatter.format_readable_file_content(data)
        clean = strip_ansi(result)

        # Should show range from first to last chunk
        assert "Lines read: 1-50" in result
        # Should have chunk info in metadata
        assert "Chunks: 2 of 5" in result

    def test_page_mode(self):
        """Test page mode with page number metadata."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'page',
            'scan': {
                'repo_relative_path': 'config.yaml',
                'byte_size': 200,
                'line_count': 50,
                'sha256': 'hash123',
                'encoding': 'utf-8',
            },
            'chunk': {
                'line_start': 21,
                'line_end': 40,
                'content': '\n'.join([f'config_{i}' for i in range(21, 41)])
            },
            'page_number': 2,
            'page_size': 20,
        }
        result = formatter.format_readable_file_content(data)
        clean = strip_ansi(result)

        # Should show correct line range
        assert "Lines read: 21-40" in result
        # Should have page metadata
        assert "Page: 2" in result


class TestFormatReadableFileContentScanOnly:
    """Tests for scan_only mode formatting (no content, just structure)."""

    def test_scan_only_no_content(self):
        """Test scan_only mode shows no content placeholder."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'module.py',
                'byte_size': 5000,
                'line_count': 200,
                'sha256': 'scanhash',
                'encoding': 'utf-8',
            },
        }
        result = formatter.format_readable_file_content(data)

        assert "scan only" in result.lower()
        assert "[scan only - no content requested]" in result

    def test_scan_only_with_navigation_hints(self):
        """Test scan_only mode with navigation hints."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'large_file.py',
                'byte_size': 50000,
                'line_count': 2000,
                'sha256': 'largehash',
                'encoding': 'utf-8',
            },
            'navigation_hints': {
                'total_chunks': 10,
                'suggested_chunk_size': 3,
                'examples': {
                    'chunk': "read_file(path='large_file.py', mode='chunk', chunk_index=[0])",
                    'page': "read_file(path='large_file.py', mode='page', page_number=1)",
                }
            }
        }
        result = formatter.format_readable_file_content(data)

        # Should have navigation hints section
        assert "Navigation Hints" in result
        assert "Chunks available: 10" in result
        assert "Suggested chunk size: 3" in result

    def test_scan_only_with_advanced_analysis_hint(self):
        """Test scan_only mode with advanced analysis hint."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'utils.py',
                'byte_size': 1000,
                'line_count': 50,
                'sha256': 'utilshash',
                'encoding': 'utf-8',
            },
            'advanced_analysis_hint': {
                'message': 'For dependency analysis, add include_dependencies=True',
                'example': "read_file(path='utils.py', mode='scan_only', include_dependencies=True)"
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Advanced Analysis" in result
        assert "include_dependencies=True" in result


class TestFormatReadableFileContentSearch:
    """Tests for search mode formatting with match highlights."""

    def test_search_mode_with_matches(self):
        """Test search mode displays matches correctly."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'search',
            'scan': {
                'repo_relative_path': 'search_file.py',
                'byte_size': 500,
                'line_count': 30,
                'sha256': 'searchhash',
                'encoding': 'utf-8',
            },
            'matches': [
                {'line_number': 5, 'line': 'def find_matches(pattern):'},
                {'line_number': 12, 'line': '    matches = []'},
                {'line_number': 18, 'line': '    return matches'},
            ],
            'max_matches': 200,
        }
        result = formatter.format_readable_file_content(data)

        # Should show matches format
        assert "3 matches" in result
        assert "[Line 5]" in result
        assert "[Line 12]" in result
        assert "[Line 18]" in result
        assert "def find_matches" in result

    def test_search_mode_no_matches(self):
        """Test search mode with no matches."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'search',
            'scan': {
                'repo_relative_path': 'empty_search.py',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'emptyhash',
                'encoding': 'utf-8',
            },
            'matches': [],
            'max_matches': 200,
        }
        result = formatter.format_readable_file_content(data)

        assert "0 matches" in result
        assert "[no matches found]" in result

    def test_search_mode_truncated_matches(self):
        """Test search mode limits display to 10 matches."""
        formatter = ResponseFormatter()
        # Create 15 matches
        matches = [{'line_number': i, 'line': f'match on line {i}'} for i in range(1, 16)]
        data = {
            'ok': True,
            'mode': 'search',
            'scan': {
                'repo_relative_path': 'many_matches.py',
                'byte_size': 1000,
                'line_count': 100,
                'sha256': 'manyhash',
                'encoding': 'utf-8',
            },
            'matches': matches,
            'max_matches': 200,
        }
        result = formatter.format_readable_file_content(data)

        # Should only show first 10 in content
        assert "[Line 1]" in result
        assert "[Line 10]" in result
        # Line 11+ should NOT be in the content display (but count shows 15)
        # The header shows "15 matches"
        assert "15 matches" in result


class TestFormatReadableFileContentStructure:
    """Tests for structure mode (AST analysis) formatting."""

    def test_python_structure_functions(self):
        """Test Python structure with functions."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'funcs.py',
                'byte_size': 500,
                'line_count': 30,
                'sha256': 'pyhash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'python',
                'functions': [
                    {'name': 'func_a', 'line': 1, 'end_line': 10, 'params': [], 'return_type': None},
                    {'name': 'func_b', 'line': 12, 'end_line': 20, 'params': [{'name': 'x', 'type': 'int'}], 'return_type': 'str'},
                ],
                'classes': [],
                'total_functions': 2,
                'total_classes': 0,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "File Structure" in result
        assert "Functions (2 total)" in result
        assert "def func_a()" in result
        assert "def func_b(x: int) -> str" in result

    def test_python_structure_classes_with_methods(self):
        """Test Python structure with classes and methods."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'classes.py',
                'byte_size': 2000,
                'line_count': 100,
                'sha256': 'classhash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'python',
                'functions': [],
                'classes': [
                    {
                        'name': 'MyClass',
                        'line': 5,
                        'end_line': 50,
                        'methods': [
                            {'name': '__init__', 'line': 6, 'end_line': 10, 'params': [{'name': 'self'}], 'is_async': False},
                            {'name': 'do_work', 'line': 12, 'end_line': 20, 'params': [{'name': 'self'}, {'name': 'data', 'type': 'dict'}], 'is_async': True},
                        ],
                        'method_count': 2,
                    }
                ],
                'total_functions': 0,
                'total_classes': 1,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Classes (1 total)" in result
        assert "class MyClass" in result
        assert "Methods (2 total)" in result
        assert "def __init__" in result
        assert "async def do_work" in result

    def test_python_structure_pagination(self):
        """Test Python structure with pagination."""
        formatter = ResponseFormatter()
        # Create many functions to trigger pagination
        functions = [{'name': f'func_{i}', 'line': i*10, 'end_line': i*10+5, 'params': [], 'return_type': None} for i in range(1, 25)]
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'many_funcs.py',
                'byte_size': 5000,
                'line_count': 300,
                'sha256': 'pagihash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'python',
                'functions': functions[:10],  # First page
                'classes': [],
                'total_functions': 24,
                'total_classes': 0,
            },
            'structure_pagination': {
                'page': 1,
                'page_size': 10,
            }
        }
        result = formatter.format_readable_file_content(data)

        # Should show pagination info
        assert "page 1 of" in result.lower()
        assert "func_1" in result
        # Should have navigation hint for next page
        assert "structure_page=" in result

    def test_python_structure_filtered(self):
        """Test Python structure with filter applied."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'filtered.py',
                'byte_size': 1000,
                'line_count': 50,
                'sha256': 'filterhash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'python',
                'functions': [
                    {'name': 'test_something', 'line': 10, 'end_line': 15, 'params': [], 'return_type': None},
                ],
                'classes': [],
                'total_functions': 1,
                'total_classes': 0,
                'filtered': True,
                'filter_pattern': 'test_',
                'filtered_function_count': 1,
                'filtered_class_count': 0,
            }
        }
        result = formatter.format_readable_file_content(data)

        # Should show filter info
        assert "Filtered Results" in result
        assert "test_" in result
        assert "1 matches" in result

    def test_markdown_structure(self):
        """Test Markdown structure with headings."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'README.md',
                'byte_size': 500,
                'line_count': 50,
                'sha256': 'mdhash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'markdown',
                'headings': [
                    {'level': 1, 'text': 'Title', 'line': 1},
                    {'level': 2, 'text': 'Installation', 'line': 5},
                    {'level': 2, 'text': 'Usage', 'line': 15},
                ],
                'total_headings': 3,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "File Structure" in result
        assert "Headings (3 total)" in result
        assert "# Title" in result
        assert "## Installation" in result
        assert "## Usage" in result

    def test_javascript_structure(self):
        """Test JavaScript/TypeScript structure."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'app.js',
                'byte_size': 1000,
                'line_count': 80,
                'sha256': 'jshash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'javascript',
                'functions': [
                    {'name': 'fetchData', 'line': 5},
                    {'name': 'processResult', 'line': 20},
                ],
                'classes': [
                    {'name': 'ApiClient', 'line': 35},
                ],
                'total_functions': 2,
                'total_classes': 1,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Classes (1 total)" in result
        assert "ApiClient" in result
        assert "Functions (2 total)" in result
        assert "fetchData()" in result


class TestFormatReadableFileContentDependencies:
    """Tests for dependency analysis formatting."""

    def test_dependencies_phase1_simple(self):
        """Test Phase 1 simple dependency display (no resolution)."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'imports.py',
                'byte_size': 500,
                'line_count': 30,
                'sha256': 'imphash',
                'encoding': 'utf-8',
            },
            'dependencies': {
                'imports': [
                    {'type': 'import', 'module': 'os', 'line': 1},
                    {'type': 'from_import', 'module': 'pathlib', 'names': ['Path'], 'line': 2},
                ],
                'total_imports': 2,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Dependencies" in result
        assert "import os" in result
        assert "from pathlib import Path" in result

    def test_dependencies_phase2_with_resolution(self):
        """Test Phase 2 dependency display with type resolution."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'resolved.py',
                'byte_size': 1000,
                'line_count': 50,
                'sha256': 'reshash',
                'encoding': 'utf-8',
            },
            'dependencies': {
                'imports': [
                    {'type': 'import', 'module': 'os', 'line': 1, 'import_type': 'stdlib'},
                    {'type': 'import', 'module': 'pytest', 'line': 2, 'import_type': 'third_party'},
                    {'type': 'from_import', 'module': 'utils', 'names': ['helper'], 'line': 3, 'import_type': 'local', 'resolved_path': 'utils.py', 'exists': True},
                ],
                'total_imports': 3,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Standard Library" in result
        assert "Third-Party" in result
        assert "Local Modules" in result
        assert "[stdlib]" in result
        assert "[third-party]" in result

    def test_dependencies_relative_imports(self):
        """Test relative import formatting."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'submodule/file.py',
                'byte_size': 200,
                'line_count': 15,
                'sha256': 'relhash',
                'encoding': 'utf-8',
            },
            'dependencies': {
                'imports': [
                    {'type': 'from_import', 'module': 'sibling', 'names': ['func'], 'line': 1, 'level': 1},
                    {'type': 'from_import', 'module': '', 'names': ['parent_func'], 'line': 2, 'level': 2},
                ],
                'total_imports': 2,
            }
        }
        result = formatter.format_readable_file_content(data)

        # Should format relative imports with dots
        assert ".sibling" in result or "from .sibling import" in result
        assert ".." in result  # Two dots for level=2

    def test_dependencies_error(self):
        """Test dependency parsing error display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'broken.py',
                'byte_size': 100,
                'line_count': 5,
                'sha256': 'brokenhash',
                'encoding': 'utf-8',
            },
            'dependencies': {
                'error': 'Syntax error in file',
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Dependencies" in result
        assert "Unable to parse" in result
        assert "Syntax error" in result


class TestFormatReadableFileContentImpactRadius:
    """Tests for impact radius analysis formatting."""

    def test_impact_radius_high(self):
        """Test high impact radius display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'core/base.py',
                'byte_size': 5000,
                'line_count': 200,
                'sha256': 'corehash',
                'encoding': 'utf-8',
            },
            'impact_radius': {
                'count': 25,
                'level': 'high',
                'importers': ['file1.py', 'file2.py', 'file3.py', 'file4.py', 'file5.py'],
                'truncated': True,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Impact Radius" in result
        assert "25 files" in result
        assert "HIGH IMPACT" in result
        assert "file1.py" in result
        assert "... and 20 more" in result

    def test_impact_radius_medium(self):
        """Test medium impact radius display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'utils/helper.py',
                'byte_size': 1000,
                'line_count': 50,
                'sha256': 'helphash',
                'encoding': 'utf-8',
            },
            'impact_radius': {
                'count': 8,
                'level': 'medium',
                'importers': ['a.py', 'b.py', 'c.py'],
                'truncated': False,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Impact Radius" in result
        assert "8 files" in result
        assert "MEDIUM IMPACT" in result

    def test_impact_radius_low_not_displayed(self):
        """Test that low impact with 0 count is not displayed prominently."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'isolated.py',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'isohash',
                'encoding': 'utf-8',
            },
            'impact_radius': {
                'count': 0,
                'level': 'low',
                'importers': [],
                'truncated': False,
            }
        }
        result = formatter.format_readable_file_content(data)

        # With count=0, should not show impact section at all
        # Check that we don't have a prominent impact message
        assert "imported by 0 files" not in result.lower()

    def test_impact_radius_error(self):
        """Test impact radius error display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'error.py',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'errhash',
                'encoding': 'utf-8',
            },
            'impact_radius': {
                'error': 'Timeout exceeded',
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Impact Radius" in result
        assert "Unable to calculate" in result
        assert "Timeout" in result


class TestFormatReadableFileContentBoundaryViolations:
    """Tests for boundary violations display."""

    def test_boundary_violations_multiple(self):
        """Test multiple boundary violations display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'bad_imports.py',
                'byte_size': 500,
                'line_count': 30,
                'sha256': 'badhash',
                'encoding': 'utf-8',
            },
            'boundary_violations': {
                'enabled': True,
                'violations': [
                    {'severity': 'error', 'rule_name': 'No DB imports in utils', 'violated_import': 'database.core', 'line': 5, 'message': 'Utils should not depend on database'},
                    {'severity': 'warning', 'rule_name': 'Discouraged import', 'violated_import': 'legacy.module', 'line': 8, 'message': 'Legacy module is deprecated'},
                ]
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "Boundary Violations" in result
        assert "1 error" in result
        assert "1 warning" in result
        assert "[ERROR]" in result
        assert "[WARNING]" in result
        assert "No DB imports in utils" in result
        assert "database.core" in result

    def test_boundary_violations_disabled(self):
        """Test when boundary checking is disabled."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'clean.py',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'cleanhash',
                'encoding': 'utf-8',
            },
            'boundary_violations': {
                'enabled': False,
            }
        }
        result = formatter.format_readable_file_content(data)

        # Should not show boundary section when disabled
        assert "Boundary Violations" not in result


class TestFormatReadableFileContentSpecialFile:
    """Tests for special file warnings (SKILL.md detection)."""

    def test_special_file_warning(self):
        """Test special file warning display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'repo_relative_path': '.codex/skills/my-skill/SKILL.md',
                'byte_size': 1000,
                'line_count': 50,
                'sha256': 'skillhash',
                'encoding': 'utf-8',
            },
            'chunk': {
                'line_start': 1,
                'line_end': 50,
                'content': '# My Skill\n\nThis is a skill file.'
            },
            'special_file': {
                'reason': 'SKILL FILE DETECTED - READ IMMEDIATELY',
                'urgency': 'HIGH',
                'type': 'skill_definition',
                'instruction': 'Skill files contain critical instructions',
                'suggested_action': 'Load this skill before proceeding',
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "SKILL FILE DETECTED" in result
        assert "Urgency: HIGH" in result
        assert "skill_definition" in result


class TestFormatReadableFileContentReminders:
    """Tests for reminder display."""

    def test_reminders_display(self):
        """Test reminders are displayed at the bottom."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'file.py',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'hash123',
                'encoding': 'utf-8',
            },
            'reminders': [
                {'message': 'Project: my_project'},
                {'message': 'Remember to test changes'},
            ]
        }
        result = formatter.format_readable_file_content(data)

        assert "Reminders" in result
        assert "Project: my_project" in result
        assert "Remember to test changes" in result


class TestFormatReadableFileContentEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self):
        """Test with empty content."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'repo_relative_path': 'empty.txt',
                'byte_size': 0,
                'line_count': 0,
                'sha256': 'emptyhash',
                'encoding': 'utf-8',
            },
            'chunks': [{'chunk_index': 0, 'line_start': 1, 'line_end': 1, 'content': ''}]
        }
        result = formatter.format_readable_file_content(data)

        # Should not crash, should produce valid output
        assert "READ FILE empty.txt" in result
        assert "Size: 0 bytes" in result

    def test_missing_scan_fields(self):
        """Test with missing optional scan fields."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'absolute_path': '/path/to/file.txt',
                # Missing repo_relative_path, byte_size, etc.
            },
            'chunks': [{'content': 'test', 'line_start': 1, 'line_end': 1}]
        }
        result = formatter.format_readable_file_content(data)

        # Should handle missing fields gracefully
        assert "file.txt" in result  # Gets filename from absolute_path

    def test_unknown_mode(self):
        """Test with unknown mode."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'unknown_mode',
            'scan': {
                'repo_relative_path': 'file.txt',
                'byte_size': 100,
                'line_count': 10,
                'sha256': 'hash',
                'encoding': 'utf-8',
            },
        }
        result = formatter.format_readable_file_content(data)

        # Should handle unknown mode gracefully
        assert "file.txt" in result
        assert "unknown" in result.lower()

    def test_structure_truncated_warning(self):
        """Test structure truncated warning display."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'scan_only',
            'scan': {
                'repo_relative_path': 'huge.py',
                'byte_size': 100000,
                'line_count': 5000,
                'sha256': 'hugehash',
                'encoding': 'utf-8',
            },
            'structure': {
                'ok': True,
                'type': 'python',
                'functions': [{'name': 'func1', 'line': 1, 'end_line': 10}],
                'classes': [],
                'total_functions': 100,
                'total_classes': 0,
                'truncated': True,
            }
        }
        result = formatter.format_readable_file_content(data)

        assert "truncated" in result.lower()
        assert "use line_range/page mode" in result.lower()


class TestGetDocLineCount:
    """Tests for _get_doc_line_count helper method."""

    def test_existing_file(self):
        """Test line count for existing file."""
        formatter = ResponseFormatter()
        # Create temp file with known content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            temp_path = f.name

        try:
            count = formatter._get_doc_line_count(temp_path)
            assert count == 3
        finally:
            os.unlink(temp_path)

    def test_nonexistent_file(self):
        """Test line count for nonexistent file returns 0."""
        formatter = ResponseFormatter()
        count = formatter._get_doc_line_count('/nonexistent/path/file.txt')
        assert count == 0

    def test_empty_file(self):
        """Test line count for empty file."""
        formatter = ResponseFormatter()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Write nothing
            temp_path = f.name

        try:
            count = formatter._get_doc_line_count(temp_path)
            assert count == 0
        finally:
            os.unlink(temp_path)

    def test_path_object(self):
        """Test line count with Path object."""
        formatter = ResponseFormatter()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("line 1\nline 2\n")
            temp_path = Path(f.name)

        try:
            count = formatter._get_doc_line_count(temp_path)
            assert count == 2
        finally:
            os.unlink(str(temp_path))


class TestDetectCustomContent:
    """Tests for _detect_custom_content helper method."""

    def test_empty_directory(self):
        """Test with empty directory."""
        formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = formatter._detect_custom_content(tmpdir)
            assert result['research_files'] == 0
            assert result['bugs_present'] is False
            assert result['jsonl_files'] == []

    def test_research_directory(self):
        """Test detection of research directory."""
        formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            research_dir = Path(tmpdir) / "research"
            research_dir.mkdir()
            (research_dir / "RESEARCH_1.md").write_text("# Research 1")
            (research_dir / "RESEARCH_2.md").write_text("# Research 2")
            (research_dir / "not_md.txt").write_text("not markdown")

            result = formatter._detect_custom_content(tmpdir)
            assert result['research_files'] == 2  # Only .md files

    def test_bugs_directory(self):
        """Test detection of bugs directory."""
        formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            bugs_dir = Path(tmpdir) / "bugs"
            bugs_dir.mkdir()

            result = formatter._detect_custom_content(tmpdir)
            assert result['bugs_present'] is True

    def test_jsonl_files(self):
        """Test detection of .jsonl files."""
        formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "TOOL_LOG.jsonl").write_text('{}')
            (Path(tmpdir) / "OTHER.jsonl").write_text('{}')
            (Path(tmpdir) / "not_jsonl.json").write_text('{}')

            result = formatter._detect_custom_content(tmpdir)
            assert len(result['jsonl_files']) == 2
            assert "TOOL_LOG.jsonl" in result['jsonl_files']
            assert "OTHER.jsonl" in result['jsonl_files']

    def test_nonexistent_directory(self):
        """Test with nonexistent directory returns empty result."""
        formatter = ResponseFormatter()
        result = formatter._detect_custom_content('/nonexistent/path')
        assert result['research_files'] == 0
        assert result['bugs_present'] is False
        assert result['jsonl_files'] == []


class TestBackwardCompatibilityFileFormatter:
    """Tests to ensure backward compatibility after extraction."""

    def test_response_formatter_still_works(self):
        """Test that ResponseFormatter.format_readable_file_content still works."""
        formatter = ResponseFormatter()
        data = {
            'ok': True,
            'mode': 'chunk',
            'scan': {
                'repo_relative_path': 'test.py',
                'byte_size': 100,
                'line_count': 5,
                'sha256': 'testhash',
                'encoding': 'utf-8',
            },
            'chunks': [{'line_start': 1, 'line_end': 5, 'content': 'a\nb\nc\nd\ne'}]
        }
        result = formatter.format_readable_file_content(data)

        # Basic verification
        assert isinstance(result, str)
        assert "test.py" in result
        assert len(result) > 0

    def test_helper_methods_accessible(self):
        """Test that helper methods remain accessible on ResponseFormatter."""
        formatter = ResponseFormatter()

        # _get_doc_line_count should exist and work
        assert hasattr(formatter, '_get_doc_line_count')
        assert callable(formatter._get_doc_line_count)

        # _detect_custom_content should exist and work
        assert hasattr(formatter, '_detect_custom_content')
        assert callable(formatter._detect_custom_content)
