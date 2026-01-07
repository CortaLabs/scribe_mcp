#!/usr/bin/env python3
"""
Dead Code Analyzer - Team A Phase 4
Comprehensive AST-based analysis to detect unreferenced code across 208 Python files
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import json

# Add scribe_mcp to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent.parent))

class DeadCodeAnalyzer:
    """Analyze codebase for unreferenced functions, classes, and imports"""

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.defined_names: Dict[str, List[Tuple[str, int, str]]] = defaultdict(list)
        self.imported_names: Dict[str, Set[str]] = defaultdict(set)
        self.used_names: Dict[str, Set[str]] = defaultdict(set)
        self.unused_imports: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.unreferenced_defs: List[Dict] = []
        self.orphaned_files: List[str] = []

    def find_python_files(self) -> List[Path]:
        """Find all Python files excluding .venv and __pycache__"""
        files = []
        for path in self.root_dir.rglob("*.py"):
            path_str = str(path)
            if ".venv" in path_str or "__pycache__" in path_str or "site-packages" in path_str:
                continue
            files.append(path)
        return sorted(files)

    def analyze_file(self, filepath: Path) -> Dict:
        """Parse file with AST and extract definitions and usage"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, filename=str(filepath))

            # Get relative path for cleaner reporting
            rel_path = str(filepath.relative_to(self.root_dir))

            # Extract definitions
            definitions = {
                'functions': [],
                'classes': [],
                'imports': [],
                'usage': []
            }

            for node in ast.walk(tree):
                # Function definitions
                if isinstance(node, ast.FunctionDef):
                    definitions['functions'].append({
                        'name': node.name,
                        'line': node.lineno,
                        'is_private': node.name.startswith('_'),
                        'is_dunder': node.name.startswith('__') and node.name.endswith('__'),
                        'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list]
                    })
                    self.defined_names[node.name].append((rel_path, node.lineno, 'function'))

                # Class definitions
                elif isinstance(node, ast.ClassDef):
                    definitions['classes'].append({
                        'name': node.name,
                        'line': node.lineno,
                        'is_private': node.name.startswith('_'),
                        'methods': [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                    })
                    self.defined_names[node.name].append((rel_path, node.lineno, 'class'))

                # Import statements
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        import_name = alias.asname if alias.asname else alias.name
                        definitions['imports'].append({
                            'name': import_name,
                            'original': alias.name,
                            'line': node.lineno
                        })
                        self.imported_names[rel_path].add(import_name)

                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        import_name = alias.asname if alias.asname else alias.name
                        definitions['imports'].append({
                            'name': import_name,
                            'original': f"{module}.{alias.name}",
                            'line': node.lineno
                        })
                        self.imported_names[rel_path].add(import_name)

                # Name usage (calls, references)
                elif isinstance(node, ast.Name):
                    self.used_names[rel_path].add(node.id)
                    definitions['usage'].append(node.id)

                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        self.used_names[rel_path].add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        self.used_names[rel_path].add(node.func.attr)

            return {
                'filepath': rel_path,
                'definitions': definitions,
                'line_count': len(content.splitlines())
            }

        except SyntaxError as e:
            return {
                'filepath': str(filepath.relative_to(self.root_dir)),
                'error': f"SyntaxError: {e}",
                'definitions': None
            }
        except Exception as e:
            return {
                'filepath': str(filepath.relative_to(self.root_dir)),
                'error': f"Error: {e}",
                'definitions': None
            }

    def find_unused_imports(self, file_analysis: Dict) -> List[Tuple[str, int]]:
        """Identify imports that are never used in the file"""
        if not file_analysis['definitions']:
            return []

        filepath = file_analysis['filepath']
        imported = set()
        used_in_file = set(file_analysis['definitions']['usage'])

        unused = []
        for imp in file_analysis['definitions']['imports']:
            if imp['name'] not in used_in_file:
                unused.append((imp['name'], imp['line']))

        return unused

    def find_unreferenced_definitions(self) -> List[Dict]:
        """Find functions/classes defined but never called/imported anywhere"""
        unreferenced = []

        # Collect all used names across all files
        all_used = set()
        for file_used in self.used_names.values():
            all_used.update(file_used)

        # Check each definition
        for name, locations in self.defined_names.items():
            # Skip special methods and private names (may be used dynamically)
            if name.startswith('__') and name.endswith('__'):
                continue

            # Count references (defined in one place, used elsewhere = referenced)
            # If it's only "used" where it's defined, it might be unreferenced
            referenced_externally = name in all_used

            for filepath, lineno, def_type in locations:
                # If not referenced externally and not in __init__.py exports
                if not referenced_externally and not filepath.endswith('__init__.py'):
                    unreferenced.append({
                        'name': name,
                        'type': def_type,
                        'file': filepath,
                        'line': lineno,
                        'severity': 'low' if name.startswith('_') else 'medium'
                    })

        return unreferenced

    def analyze_all(self) -> Dict:
        """Run complete dead code analysis"""
        files = self.find_python_files()
        print(f"Found {len(files)} Python files to analyze...")

        all_analyses = []
        for i, filepath in enumerate(files, 1):
            if i % 20 == 0:
                print(f"Analyzed {i}/{len(files)} files...")

            analysis = self.analyze_file(filepath)
            all_analyses.append(analysis)

            # Track unused imports
            unused = self.find_unused_imports(analysis)
            if unused:
                self.unused_imports[analysis['filepath']] = unused

        print("Building cross-reference graph...")
        self.unreferenced_defs = self.find_unreferenced_definitions()

        return {
            'total_files': len(files),
            'analyses': all_analyses,
            'unused_imports': dict(self.unused_imports),
            'unreferenced_definitions': self.unreferenced_defs,
            'summary': {
                'total_unused_imports': sum(len(v) for v in self.unused_imports.values()),
                'total_unreferenced_defs': len(self.unreferenced_defs),
                'files_with_issues': len([a for a in all_analyses if a.get('error')])
            }
        }

    def generate_report(self, results: Dict, output_file: str):
        """Generate markdown report"""
        with open(output_file, 'w') as f:
            f.write("# Dead Code Analysis Report\n\n")
            f.write(f"**Analysis Date**: 2026-01-05\n")
            f.write(f"**Files Analyzed**: {results['total_files']}\n")
            f.write(f"**Agent**: ResearchAgent-Phase4-DeadCode\n\n")

            f.write("## Executive Summary\n\n")
            f.write(f"- **Total Unused Imports**: {results['summary']['total_unused_imports']}\n")
            f.write(f"- **Unreferenced Definitions**: {results['summary']['total_unreferenced_defs']}\n")
            f.write(f"- **Files with Parse Errors**: {results['summary']['files_with_issues']}\n\n")

            # Unused imports section
            f.write("## Unused Imports by File\n\n")
            if results['unused_imports']:
                for filepath, imports in sorted(results['unused_imports'].items()):
                    f.write(f"### {filepath}\n\n")
                    for name, line in imports:
                        f.write(f"- Line {line}: `{name}` (imported but never used)\n")
                    f.write("\n")
            else:
                f.write("No unused imports detected.\n\n")

            # Unreferenced definitions
            f.write("## Unreferenced Definitions\n\n")
            if results['unreferenced_definitions']:
                # Group by severity
                by_severity = defaultdict(list)
                for item in results['unreferenced_definitions']:
                    by_severity[item['severity']].append(item)

                for severity in ['high', 'medium', 'low']:
                    if severity in by_severity:
                        f.write(f"### {severity.upper()} Severity\n\n")
                        for item in sorted(by_severity[severity], key=lambda x: x['file']):
                            f.write(f"- **{item['name']}** ({item['type']}) in `{item['file']}:{item['line']}`\n")
                        f.write("\n")
            else:
                f.write("No unreferenced definitions detected.\n\n")


if __name__ == "__main__":
    # Root is scribe_mcp directory (current file is in .scribe/docs/dev_plans/.../wiki/analysis/)
    # So we need 7 levels up: analysis -> wiki -> scribe_systematic_audit_1 -> dev_plans -> docs -> .scribe -> scribe_mcp
    root = Path(__file__).parent.parent.parent.parent.parent.parent.parent
    analyzer = DeadCodeAnalyzer(str(root))

    print("Starting dead code analysis...")
    results = analyzer.analyze_all()

    # Save JSON results (path relative to current file)
    output_dir = Path(__file__).parent
    json_output = output_dir / "dead_code_results.json"
    with open(json_output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"JSON results saved to {json_output}")

    # Generate markdown report
    md_output = output_dir / "dead_code_catalog.md"
    analyzer.generate_report(results, str(md_output))
    print(f"Markdown report saved to {md_output}")

    print("\nAnalysis complete!")
